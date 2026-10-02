import pandas as pd
import pytest
from research import ranking_data
from test_stock_ranking import history


def test_chart_applies_adjustment_to_all_price_columns():
    d=history()
    class Response:
        def raise_for_status(self):pass
        def json(self):
            return {'chart':{'result':[{'timestamp':[int(x.timestamp()) for x in d.index],'indicators':{'quote':[{'close':d.Close.tolist(),'high':d.High.tolist(),'low':d.Low.tolist(),'volume':d.Volume.tolist()}],'adjclose':[{'adjclose':(d.Close*.5).tolist()}]}}]}}
    class Session:
        def get(self,*args,**kwargs):return Response()
    frame=ranking_data.yahoo_chart(Session(),'AAPL','query1.finance.yahoo.com')
    assert frame.Close.iloc[-1]==pytest.approx(d.Close.iloc[-1]*.5)
    assert frame.High.iloc[-1]==pytest.approx(d.High.iloc[-1]*.5)
    assert frame.Low.iloc[-1]==pytest.approx(d.Low.iloc[-1]*.5)
    assert frame.attrs['basis']=='adjusted'


def test_secondary_yahoo_host_runs_when_first_fails(monkeypatch):
    calls=[]
    def chart(session,symbol,host,adjusted=True):
        calls.append(host)
        if host.startswith('query1'):raise ValueError('rate limited')
        result=history();result.attrs['basis']='adjusted';return result
    monkeypatch.setattr(ranking_data,'yahoo_chart',chart)
    assert len(ranking_data.fetch_history('SPY',object()))==280
    assert len(calls)==2


def test_nasdaq_fallback_and_explicit_adjusted_requirement(monkeypatch):
    def unavailable(*args,**kwargs):raise ValueError('blocked')
    monkeypatch.setattr(ranking_data,'yahoo_chart',unavailable)
    monkeypatch.setattr('yfinance.Ticker',unavailable)
    def nasdaq(*args):
        result=history();result.attrs.update(basis='unadjusted',source='Nasdaq');return result
    monkeypatch.setattr(ranking_data,'nasdaq_history',nasdaq)
    assert ranking_data.fetch_history('SPY',object()).attrs['basis']=='unadjusted'
    with pytest.raises(ValueError):ranking_data.fetch_history('SPY',object(),basis='adjusted')


def test_spy_nasdaq_requests_etf_assetclass_first():
    d=history()
    class Session:
        def get(self,url,params,**kwargs):
            assert params['assetclass']=='etf'
            class Response:
                def raise_for_status(self):pass
                def json(self):return {'data':{'tradesTable':{'rows':[{'date':x.strftime('%m/%d/%Y'),'close':str(row.Close),'high':str(row.High),'low':str(row.Low),'volume':str(row.Volume)} for x,row in d.iterrows()]}}}
            return Response()
    assert ranking_data.nasdaq_history(Session(),'SPY').attrs['basis']=='unadjusted'
