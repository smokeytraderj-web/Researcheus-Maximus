"""Exercise portfolio jobs and their reports over the HTTP contract."""
from __future__ import annotations
import io
import json
import threading
import time
import zipfile
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.portfolio import attach_portfolio_routes
from research.demo_provider import DemoResearchProvider

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(tmp_path):
    app = FastAPI()
    slots = threading.Semaphore(1)
    shutdown = attach_portfolio_routes(app,tmp_path,ROOT/'web',DemoResearchProvider,slots)
    with TestClient(app) as client:
        yield client,tmp_path,slots
    shutdown()


def finish(client,job_id):
    deadline = time.monotonic()+45
    while time.monotonic() < deadline:
        response = client.get('/api/portfolio/'+job_id)
        assert response.status_code == 200
        data = response.json()
        if data['status'] != 'running': return data
        time.sleep(.05)
    raise AssertionError('Portfolio did not finish within the test deadline')


def test_two_positions_full_rm_charts_reports_and_download(api):
    client, root, slots = api
    response = client.post('/api/portfolio',json={'positions':[{'ticker':'AAPL','amount':60},{'ticker':'MSFT','amount':40}],'mode':'deep'})
    assert response.status_code == 200
    job_id = response.json()['id']
    done = finish(client,job_id)
    assert done['status'] == 'ready'
    assert done['assessment']['coverage_pct'] == 100
    assert done['assessment']['rating'] == 'Constructive'
    assert done['demo_mode'] is True
    first,second = done['positions']
    assert first['price'] != second['price']
    assert first['ticker'] == 'AAPL' and second['ticker'] == 'MSFT'
    assert any('Fibonacci' in c['title'] for c in first['charts'])
    assert any('Momentum' in c['title'] for c in first['charts'])
    for p in done['positions']:
        report = client.get(p['report_url'])
        assert report.status_code == 200
        assert p['ticker'] in report.text and 'Technical Analyst Agent' in report.text
        assert 'data:image/' in report.text
        assert client.get(p['charts'][0]['url']).status_code == 200
    bundle = client.get('/api/portfolio/'+job_id+'/download')
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = archive.namelist()
        assert {'Portfolio_RM.html','position-0/research.html','position-1/research.html','fonts/fonts.css'} <= set(names)
        html = archive.read('Portfolio_RM.html').decode()
        assert 'window.PORTFOLIO_SNAPSHOT=' in html
        assert 'src="/portfolio.js"' not in html
        assert 'href="/portfolio.css"' not in html
        assert 'position-0/chart-0.png' in html
        assert 'position-1/research.html' in html
    assert slots.acquire(blocking=False)
    slots.release()
    # Disk snapshot remains usable after reconstructing the in-memory registry.
    restarted = FastAPI()
    stop = attach_portfolio_routes(restarted,root,ROOT/'web',DemoResearchProvider,slots)
    with TestClient(restarted) as other:
        assert other.get('/api/portfolio/'+job_id).json()['assessment'] == done['assessment']
    stop()


def test_partial_failure_does_not_hide_missing_weight_or_expose_provider_error(api):
    client, root, _ = api
    def result(self,holding,weighting,mode,question,output):
        if holding['ticker'] == 'MSFT': raise RuntimeError('secret-key /private/path')
        return dict(status='ready',ticker='AAPL',company_name='Apple',rating='Buy',price=100,currency='USD',demo_mode=False,charts=[])
    with mock.patch('backend.portfolio.PortfolioRunner.research',result):
        start = client.post('/api/portfolio',json={'positions':[{'ticker':'AAPL','amount':30},{'ticker':'MSFT','amount':70}]}).json()
        done = finish(client,start['id'])
    assert done['status'] == 'partial'
    assert done['assessment']['rating'] == 'Incomplete research'
    assert done['assessment']['coverage_pct'] == 30
    assert done['positions'][1]['weight'] == 70
    assert 'secret-key' not in json.dumps(done) and '/private/path' not in json.dumps(done)
    assert client.get('/api/portfolio/'+start['id']+'/positions/1/report').status_code == 404


def test_cancel_stops_before_next_holding_and_releases_slot(api):
    client, root, slots = api
    entered, release = threading.Event(), threading.Event()
    called = []
    def blocked(self,holding,weighting,mode,question,output):
        called.append(holding['ticker']); entered.set(); release.wait(10)
        return dict(status='ready',ticker=holding['ticker'],rating='Hold',price=100,currency='USD',charts=[])
    with mock.patch('backend.portfolio.PortfolioRunner.research',blocked):
        start = client.post('/api/portfolio',json={'positions':[{'ticker':'AAPL','amount':50},{'ticker':'MSFT','amount':50}]}).json()
        assert entered.wait(5)
        assert client.post('/api/portfolio',json={'positions':[{'ticker':'AAPL','amount':100}]}).status_code == 503
        assert client.post('/api/portfolio/'+start['id']+'/cancel').status_code == 200
        release.set(); done = finish(client,start['id'])
    assert done['status'] == 'cancelled'
    assert called == ['AAPL']
    assert not (root/start['id']).exists()
    assert client.get('/api/portfolio/'+start['id']+'/positions/0/report').status_code == 404
    assert slots.acquire(blocking=False)
    slots.release()


def test_intake_validation_and_invalid_paths(api):
    client,_,_ = api
    assert client.post('/api/portfolio/parse',json={'text':'Ticker,Weight\nAAPL,90','weighting':'weight'}).status_code == 400
    assert client.post('/api/portfolio',json={'positions':[{'ticker':'AAPL','amount':100}],'question':'account: 123456789'}).status_code == 400
    assert client.get('/api/portfolio/not-a-job').status_code == 404
    assert client.get('/api/portfolio/'+'a'*32+'/positions/-1/report').status_code == 404


def test_portfolio_data_and_reports_remain_behind_access_gate():
    from backend.app import app
    from backend import gate
    with TestClient(app) as client:
        assert client.get('/api/portfolio/'+'a'*32).status_code == 401
        assert client.get('/api/portfolio/'+'a'*32+'/positions/0/report').status_code == 401
        assert client.post('/api/portfolio/parse',json={'text':'AAPL,100'}).status_code == 401
        client.cookies.set(gate.COOKIE_NAME,gate.issue_token())
        response = client.post('/api/portfolio/parse',json={'text':'AAPL,100'})
        assert response.status_code == 200
        assert response.headers['Cache-Control'] == 'no-store'
        assert 'Evaluate portfolio' in client.get('/').text
        assert 'Portfolio RM' in client.get('/portfolio').text


def test_combined_site_navigation_and_shared_access_cookie():
    from backend.app import app
    from backend import gate
    with TestClient(app) as client:
        assert client.get('/').status_code == 401
        assert client.get('/portfolio').status_code == 401
        client.cookies.set(gate.COOKIE_NAME, gate.issue_token())
        home = client.get('/')
        portfolio = client.get('/portfolio')
        assert home.status_code == portfolio.status_code == 200
        assert 'href="/portfolio"' in home.text
        assert 'Evaluate portfolio' in home.text
        assert 'id="queryBox"' in home.text and 'id="deepBox"' in home.text
        assert 'href="/" class="button secondary" id="backToResearch"' in portfolio.text
        assert 'window.PORTFOLIO_SNAPSHOT=' not in portfolio.text
        assert '/single-stock.html' not in portfolio.text
        redirect = client.get('/portfolio/', follow_redirects=False)
        assert redirect.status_code == 307 and redirect.headers['location'] == '/portfolio'
        assert client.get('/portfolio.css').status_code == 200
        assert client.get('/portfolio.js').status_code == 200
        assert client.post('/api/portfolio/parse',json={'text':'AAPL,100'}).status_code == 200
