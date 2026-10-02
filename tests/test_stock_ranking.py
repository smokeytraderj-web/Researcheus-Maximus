import numpy as np
import pandas as pd
import pytest
from research.stock_ranking import parse_tickers, score_stock, WEIGHTS

def history(growth=.001, volume=1_000_000):
    dates=pd.bdate_range(end=pd.Timestamp.now(tz='UTC').normalize(),periods=280)
    close=100*np.exp(np.arange(280)*growth)
    return pd.DataFrame({'Close':close,'High':close*1.01,'Low':close*.99,'Volume':volume},index=dates)

def test_parser_handles_large_lists_headers_duplicates_and_rejects_bad_input():
    assert parse_tickers('Ticker\n$aapl, MSFT; AAPL | BRK-B')==['AAPL','MSFT','BRK-B']
    assert len(parse_tickers(' '.join('T'+str(i) for i in range(200))))==200
    with pytest.raises(ValueError): parse_tickers(' '.join('T'+str(i) for i in range(201)))
    with pytest.raises(ValueError): parse_tickers('AAPL <script>')

def test_independent_score_formula_and_bearish_trend():
    benchmark=history(.0005)
    bull=score_stock('BULL',history(.001),benchmark)
    bear=score_stock('BEAR',history(-.002),benchmark)
    assert bull['score']>bear['score']
    assert bull['score']==round(1+9*sum(bull['components'][k]*w for k,w in WEIGHTS.items())/100,1)
    assert bull['components']['trend']==100
    assert bear['components']['trend']==0
    assert 1<=bear['score']<=10 and 1<=bull['score']<=10
    assert bull['excess_63d']>0 and bear['excess_63d']<0

def test_missing_short_stale_or_misaligned_history_has_no_score():
    frame=history();benchmark=history()
    with pytest.raises(ValueError): score_stock('IPO',frame.iloc[-50:],benchmark)
    with pytest.raises(ValueError): score_stock('OLD',frame.iloc[:-20],benchmark)
    with pytest.raises(ValueError): score_stock('BAD',frame,benchmark.iloc[:-1])
    with pytest.raises(ValueError): score_stock('NOVOL',history(volume=0),benchmark)

def test_flat_prices_are_finite_and_volume_selloffs_are_not_rewarded():
    flat=score_stock('FLAT',history(0),history(0))
    assert flat['rsi']==50
    assert np.isfinite(flat['score'])
    up=score_stock('UP',history(.001),history())
    down=score_stock('DOWN',history(-.001),history())
    assert up['components']['volume']>down['components']['volume']


def test_qualitative_summary_is_specific_to_the_measured_ticker():
    row=score_stock('BEAR',history(-.002),history(.0005))
    summary=row['qualitative_summary']
    assert summary.startswith('BEAR shows a weak trend')
    assert 'lagged SPY' in summary
    assert '63 trading sessions' in summary
    assert len(summary)<450
