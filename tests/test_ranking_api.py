import io
import threading
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.ranking import attach_ranking_routes
from test_stock_ranking import history


def test_api_completes_partial_batch_and_exports_no_fake_score(monkeypatch):
    import yfinance
    class Ticker:
        def __init__(self,symbol): self.symbol=symbol
        def history(self,**kwargs):
            if self.symbol=='MISSING': raise RuntimeError('network failure')
            return history(.0005 if self.symbol=='SPY' else .001)
    monkeypatch.setattr('backend.ranking.fetch_history',lambda symbol,session,basis=None: Ticker(symbol).history())
    app=FastAPI();slots=threading.Semaphore(1);attach_ranking_routes(app,slots)
    with TestClient(app) as client:
        r=client.post('/api/ranking',json={'text':'AAPL MSFT MISSING AAPL'})
        assert r.status_code==200
        job=r.json()
        for _ in range(100):
            job=client.get('/api/ranking/'+job['id']).json()
            if job['status']!='running':break
            time.sleep(.01)
        assert job['status']=='complete'
        assert len(job['rows'])==3
        assert [r['ticker'] for r in job['rows']]==['AAPL','MSFT','MISSING']
        assert 'score' not in job['rows'][-1]
        assert slots.acquire(blocking=False)


def test_csv_excel_upload_and_slot_limit():
    import pandas as pd
    app=FastAPI();slots=threading.Semaphore(0);attach_ranking_routes(app,slots)
    with TestClient(app) as client:
        assert client.post('/api/ranking',json={'text':'AAPL'}).status_code==429
        assert client.post('/api/ranking',json={'text':'AAPL <script>'}).status_code==400
        assert client.post('/api/ranking/parse?filename=list.csv',content='Ticker,Other\nAAPL,1\nMSFT,2').json()['tickers']==['AAPL','MSFT']
        workbook=io.BytesIO();pd.DataFrame({'Ticker':['AAPL','MSFT']}).to_excel(workbook,index=False)
        assert client.post('/api/ranking/parse?filename=list.xlsx',content=workbook.getvalue()).json()['tickers']==['AAPL','MSFT']
        assert client.post('/api/ranking/parse?filename=list.csv',content=b'x'*2_000_001).status_code==413
        assert client.get('/api/ranking/nonexistent').status_code==404


def test_fifty_plus_stocks_complete_with_independent_scores(monkeypatch):
    import yfinance
    class Ticker:
        def __init__(self,symbol): self.symbol=symbol
        def history(self,**kwargs): return history(.0005 if self.symbol=='SPY' else .001)
    monkeypatch.setattr('backend.ranking.fetch_history',lambda symbol,session,basis=None: Ticker(symbol).history())
    app=FastAPI();attach_ranking_routes(app,threading.Semaphore(1))
    with TestClient(app) as client:
        job=client.post('/api/ranking',json={'text':' '.join('T'+str(i) for i in range(60))}).json()
        for _ in range(400):
            job=client.get('/api/ranking/'+job['id']).json()
            if job['status']!='running': break
            time.sleep(.01)
        assert job['status']=='complete' and len(job['rows'])==60
        assert len({r['score'] for r in job['rows']})==1


def test_benchmark_failure_is_explicit_and_releases_slot(monkeypatch):
    import yfinance
    def fail(*args,**kwargs): raise RuntimeError('benchmark unavailable')
    monkeypatch.setattr('backend.ranking.fetch_history',fail)
    app=FastAPI();slots=threading.Semaphore(1);attach_ranking_routes(app,slots)
    with TestClient(app) as client:
        job=client.post('/api/ranking',json={'text':'AAPL'}).json()
        for _ in range(100):
            job=client.get('/api/ranking/'+job['id']).json()
            if job['status']!='running':break
            time.sleep(.01)
        assert job['status']=='failed' and job['rows']==[]
        assert slots.acquire(blocking=False)


def test_full_app_protects_ranking_and_serves_scorecard():
    from backend.app import app
    from backend import gate
    with TestClient(app) as client:
        assert client.post('/api/ranking',json={'text':'AAPL'}).status_code==401
        assert client.get('/rank-stocks').status_code==401
        client.cookies.set(gate.COOKIE_NAME,gate.issue_token())
        page=client.get('/rank-stocks')
        assert page.status_code==200 and 'Technical Scorecard' in page.text
        assert 'Rank Stocks' in client.get('/portfolio').text
        response=client.get('/api/ranking/missing')
        assert response.status_code==404 and response.headers['cache-control']=='no-store'


def test_raw_benchmark_fallback_requires_matching_stock_basis(monkeypatch):
    calls=[]
    def fetch(symbol,session,basis=None):
        calls.append((symbol,basis))
        if symbol!='SPY':assert basis=='unadjusted'
        result=history(.0005 if symbol=='SPY' else .001)
        result.attrs.update(basis='unadjusted',source='Nasdaq',url='https://www.nasdaq.com/')
        return result
    monkeypatch.setattr('backend.ranking.fetch_history',fetch)
    app=FastAPI();attach_ranking_routes(app,threading.Semaphore(1))
    with TestClient(app) as client:
        job=client.post('/api/ranking',json={'text':'AAPL'}).json()
        for _ in range(100):
            job=client.get('/api/ranking/'+job['id']).json()
            if job['status']!='running':break
            time.sleep(.01)
        assert job['status']=='complete'
        assert job['rows'][0]['price_basis']=='unadjusted'
        assert job['rows'][0]['data_provider']=='Nasdaq'
        assert calls==[('SPY',None),('AAPL','unadjusted')]


def test_analytics_and_pdf_use_existing_history_and_hide_internal_data(monkeypatch):
    import numpy as np
    import pandas as pd
    from pypdf import PdfReader
    calls=[];rng=np.random.default_rng(12);dates=pd.bdate_range(end=pd.Timestamp.now(tz='UTC').normalize(),periods=300)
    common=rng.normal(.001,.012,len(dates));frames={}
    for symbol in ['SPY','AAA','BBB']:
        close=100*np.cumprod(1+common+rng.normal(0,.004,len(dates)))
        frames[symbol]=pd.DataFrame({'Close':close,'High':close*1.01,'Low':close*.99,'Volume':1000000},index=dates)
    def fetch(symbol,session,basis=None):calls.append(symbol);return frames[symbol]
    monkeypatch.setattr('backend.ranking.fetch_history',fetch)
    app=FastAPI();attach_ranking_routes(app,threading.Semaphore(1))
    with TestClient(app) as client:
        job=client.post('/api/ranking',json={'text':'AAA BBB'}).json()
        for _ in range(100):
            job=client.get('/api/ranking/'+job['id']).json()
            if job['status']!='running':break
            time.sleep(.01)
        assert not any(k.startswith('_') for k in job)
        assert client.get('/api/ranking/'+job['id']+'/analytics').json()['available']
        assert client.get('/api/ranking/'+job['id']+'/analytics?market_adjusted=true').json()['market_adjusted']
        response=client.get('/api/ranking/'+job['id']+'/pdf')
        assert response.status_code==200 and response.headers['content-type']=='application/pdf'
        reader=PdfReader(io.BytesIO(response.content));assert len(reader.pages)>=5
        assert 'Technical Stock Scorecard' in reader.pages[0].extract_text()
        assert calls==['SPY','AAA','BBB']
