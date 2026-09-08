"""Numerical and intake regressions for multi-position research."""
from __future__ import annotations
import dataclasses
import math
from pathlib import Path
from unittest import mock

import pytest

from core.models import Rating
from core.portfolio import parse_holdings, summarize, validate_holdings
from research.demo_provider import DemoResearchProvider
from services.portfolio_runner import PortfolioRunner


def position(ticker, amount, rating='Hold', status='ready', price=100, currency='USD'):
    return dict(ticker=ticker, amount=amount, rating=rating, status=status, price=price, currency=currency)


@pytest.mark.parametrize('text,method', [
    ('Ticker,Weight\nAAPL,60%\nMSFT,40%', 'weight'),
    ('Symbol\tMarket value\nAAPL\t$6000\nMSFT\t$4000', 'value'),
    ('Ticker,Shares\nBRK-B,1.5\nMSFT,4', 'shares'),
    ('AAPL, MSFT, NVDA', 'equal'),
    ('\ufeffTicker,Weight\nAAPL,60\nCASH,40', 'weight'),
])
def test_parse_supported_input(text, method):
    assert len(parse_holdings(text, method)) >= 2


@pytest.mark.parametrize('text,method', [
    ('Ticker,Weight\nAAPL,50\nMSFT,40', 'weight'),
    ('AAPL,50\naapl,50', 'weight'),
    ('AAPL,-10\nMSFT,110', 'weight'),
    ('AAPL,nan', 'shares'),
    ('AAPL,inf', 'value'),
    ('AAPL,5%', 'shares'),
    ('Ticker,Weight\nAAPL,50\nMSFT,50', 'value'),
    ('Ticker,Weight,Account\nAAPL,100,12345678', 'weight'),
    ('CASH', 'equal'),
    ('AAPL,100', 'equal'),
    ('../AAPL,100', 'weight'),
])
def test_reject_ambiguous_or_invalid_holdings(text, method):
    with pytest.raises(ValueError):
        parse_holdings(text, method)


def test_reject_duplicates_counts_and_nonfinite_api_values():
    for rows in [[dict(ticker='AAPL',amount=math.nan)],
                 [dict(ticker='AAPL',amount=True)],
                 [dict(ticker='AAPL',amount=1)]*51]:
        with pytest.raises(ValueError):
            validate_holdings(rows, 'shares')


def test_weighted_rating_uses_exposure_not_number_of_tickers():
    a = summarize([position('AAPL',80,'Sell'),position('MSFT',10,'Buy'),position('NVDA',10,'Strong Buy')], 'weight')
    assert a['score'] == pytest.approx(-1.1)
    assert a['rating'] == 'Defensive'
    assert a['negative_pct'] == 80
    assert a['largest'] == {'ticker':'AAPL','weight':80}


def test_market_values_and_shares_produce_equivalent_allocations():
    a = summarize([position('AAPL',2,price=150),position('MSFT',1,price=100)],'shares')
    b = summarize([position('AAPL',300),position('MSFT',100)],'value')
    assert [p['weight'] for p in a['positions']] == [p['weight'] for p in b['positions']] == [75,25]
    assert a['total_value'] == b['total_value'] == 400


def test_cash_does_not_invent_a_security_rating():
    a = summarize([position('AAPL',20,'Add'),position('CASH',80,rating=None)],'weight')
    assert a['rating'] == 'Constructive'
    assert a['score'] == 1
    assert a['positive_pct'] == 20
    assert a['cash_pct'] == 80
    assert a['coverage_pct'] == 100
    assert not a['flags']
    assert summarize([position('CASH',100,rating=None)],'weight')['rating'] == 'Cash only'


def test_failed_weight_stays_in_denominator_and_blocks_portfolio_rating():
    a = summarize([position('AAPL',40,'Buy'),position('MSFT',60,status='failed')], 'weight')
    assert a['coverage_pct'] == 40
    assert a['score'] is None
    assert a['rating'] == 'Incomplete research'
    assert [p['weight'] for p in a['positions']] == [40,60]


def test_missing_share_price_does_not_renormalize_remaining_holdings():
    a = summarize([position('AAPL',10,'Buy'),position('MSFT',10,status='failed')], 'shares')
    assert a['coverage_pct'] is None
    assert a['score'] is None
    assert all(p['weight'] is None for p in a['positions'])


def test_mixed_currencies_never_sum_without_fx():
    a = summarize([position('AAPL',10),position('SHOP.TO',10,currency='CAD')], 'shares')
    assert a['total_value'] is None
    assert a['score'] is None


def test_runner_keeps_ticker_binding_and_cleans_sessions(tmp_path):
    seen = []
    class Provider:
        def run(self, request, workspace):
            seen.append(request)
            return DemoResearchProvider().run(request)  # no charts needed for this contract
    runner = PortfolioRunner(Provider, tmp_path/'sessions')
    result = runner.research({'ticker':'AAPL','amount':25}, 'weight', 'general',
                             'How does this holding compare with MSFT?', tmp_path/'output')
    assert seen[0].query == 'AAPL'
    assert '25%' in seen[0].question
    assert result['ticker'] == 'AAPL'
    assert result['demo_mode'] is True
    html = (tmp_path/'output/research.html').read_text()
    assert 'AAPL' in html and 'Technical Analyst Agent' in html
    assert not list((tmp_path/'sessions').glob('*/working'))


@pytest.mark.parametrize('change', ['identity','currency','price'])
def test_runner_rejects_wrong_identity_currency_and_nan_price(tmp_path,change):
    class Provider:
        def run(self,request,workspace):
            result = DemoResearchProvider().run(request)
            if change == 'identity': return dataclasses.replace(result,identity=dataclasses.replace(result.identity,ticker='MSFT'))
            if change == 'currency': return dataclasses.replace(result,identity=dataclasses.replace(result.identity,currency='CAD'))
            return dataclasses.replace(result,current_price=math.nan)
    with pytest.raises(ValueError):
        PortfolioRunner(Provider,tmp_path/'sessions').research({'ticker':'AAPL','amount':100},'weight','deep','',tmp_path/'output')
    assert not (tmp_path/'output').exists()
