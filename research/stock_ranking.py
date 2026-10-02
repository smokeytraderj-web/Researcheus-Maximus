"""Independent daily-chart setup scores. Versioned, deterministic, no LLM."""
from __future__ import annotations
import re
import numpy as np
import pandas as pd

VERSION = '1.1'
WEIGHTS = {'trend': .30, 'momentum': .20, 'relative_strength': .20, 'entry_risk': .20, 'volume': .10}

def parse_tickers(text: str) -> list[str]:
    tokens = re.split(r'[\s,;|]+', text.upper().strip())
    result = []
    for token in tokens:
        token = token.strip('"\'').removeprefix('$')
        if not token or token in {'TICKER', 'TICKERS', 'SYMBOL', 'SYMBOLS'}:
            continue
        if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', token):
            raise ValueError(f'Invalid ticker: {token[:30]}. Supply tickers only.')
        if token not in result:
            result.append(token)
    if not 1 <= len(result) <= 200:
        raise ValueError('Enter between 1 and 200 unique tickers.')
    return result

def clean_history(frame):
    required = ['Close', 'High', 'Low', 'Volume']
    if frame is None or not set(required).issubset(frame.columns):
        raise ValueError('Daily OHLCV data unavailable.')
    data = frame[required].copy()
    data.index = pd.to_datetime(data.index, utc=True).normalize()
    data = data[~data.index.duplicated(keep='last')].sort_index()
    data = data.apply(pd.to_numeric, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    data = data[(data.Close > 0) & (data.High >= data.Low) & (data.Low > 0) & (data.Volume >= 0)]
    if len(data) < 220:
        raise ValueError('At least 220 valid daily sessions are required.')
    if (pd.Timestamp.now(tz='UTC').normalize() - data.index[-1]).days > 7:
        raise ValueError('Latest market data is stale; no score assigned.')
    return data

def score_stock(ticker, frame, benchmark):
    d, b = clean_history(frame), clean_history(benchmark)
    common = d.index.intersection(b.index)
    if len(common) < 64 or common[-1] != d.index[-1] or common[-1] != b.index[-1]:
        raise ValueError('S&P 500 comparison lacks aligned recent sessions.')
    c = d.Close; price = float(c.iloc[-1])
    ma20, ma50, ma200 = [c.rolling(n).mean() for n in (20, 50, 200)]
    delta = c.diff(); gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rsi = float((100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1])
    if not np.isfinite(rsi): rsi = 100. if gain.iloc[-1] > 0 else 50.
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); hist = macd - macd.ewm(span=9, adjust=False).mean()
    tr = pd.concat([d.High-d.Low, (d.High-c.shift()).abs(), (d.Low-c.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1]); atr_pct = atr / price * 100
    trend = sum([25*(price > ma200.iloc[-1]), 20*(price > ma50.iloc[-1]), 20*(ma50.iloc[-1] > ma200.iloc[-1]), 20*(ma50.iloc[-1] > ma50.iloc[-21]), 15*(ma200.iloc[-1] > ma200.iloc[-21])])
    rsi_points = 50 if 45 <= rsi <= 65 else 35 if 40 <= rsi < 45 or 65 < rsi <= 70 else 15 if 30 <= rsi < 40 or 70 < rsi <= 80 else 0
    momentum = rsi_points + 25*(hist.iloc[-1] > 0) + 25*(hist.iloc[-1] > hist.iloc[-6])
    dc, bc = d.loc[common].Close, b.loc[common].Close
    excess21 = float((dc.iloc[-1]/dc.iloc[-22] - bc.iloc[-1]/bc.iloc[-22])*100)
    excess63 = float((dc.iloc[-1]/dc.iloc[-64] - bc.iloc[-1]/bc.iloc[-64])*100)
    strength = float(np.clip(50 + 2*excess21 + 3*excess63, 0, 100))
    extension = (price / float(ma20.iloc[-1]) - 1)*100
    support = float(d.Low.iloc[-20:].min()); stop = support - .5*atr; distance = (price-stop)/price*100
    # Prefer a supported uptrend with moderate extension and volatility.
    entry = (40 if price > ma50.iloc[-1] and -2 <= extension <= 5 else 20 if price > ma50.iloc[-1] and extension <= 10 else 0) + (35 if 0 < distance <= 8 else 20 if 0 < distance <= 12 else 0) + (25 if atr_pct <= 3 else 15 if atr_pct <= 5 else 0)
    volumes = d.Volume.iloc[-21:-1]; avg = float(volumes.mean())
    vol_ratio = float(d.Volume.iloc[-1]/avg) if avg > 0 else None
    # Directional volume balance avoids awarding a high score to selloffs.
    flow = (np.sign(c.diff().iloc[-20:]) * d.Volume.iloc[-20:]).sum()
    total = float(d.Volume.iloc[-20:].sum())
    if total <= 0: raise ValueError('Volume data unavailable; no complete technical score.')
    volume = float(np.clip(50 + 50*float(flow)/total, 0, 100))
    components = dict(zip(WEIGHTS, map(float, [trend, momentum, strength, entry, volume])))
    score = round(1 + 9*sum(components[k]*WEIGHTS[k] for k in WEIGHTS)/100, 1)
    reason = ('Healthy uptrend' if trend >= 80 else 'Mixed trend' if trend >= 45 else 'Weak trend') + ('; outperforming SPY' if excess63 > 0 else '; lagging SPY') + ('; extended entry.' if extension > 5 else '; supported entry.' if entry >= 75 else '; entry risk needs review.')
    trend_phrase = 'a healthy uptrend' if trend >= 80 else 'a mixed trend' if trend >= 45 else 'a weak trend'
    if rsi > 70:
        momentum_phrase = f'momentum looks stretched with RSI at {rsi:.0f}'
    elif rsi < 30:
        momentum_phrase = f'RSI at {rsi:.0f} signals oversold conditions without confirming a reversal'
    elif hist.iloc[-1] > hist.iloc[-6]:
        momentum_phrase = 'momentum is improving' if hist.iloc[-1] > 0 else 'momentum is recovering but MACD remains negative'
    else:
        momentum_phrase = 'positive momentum is fading' if hist.iloc[-1] > 0 else 'momentum remains weak'
    strength_phrase = f'outperformed SPY by {excess63:.1f} percentage points' if excess63 >= 0 else f'lagged SPY by {abs(excess63):.1f} percentage points'
    if extension > 5:
        entry_phrase = f'the entry is extended at {extension:.1f}% above the 20-day average'
    elif distance > 8:
        entry_phrase = f'the support-based stop reference is {distance:.1f}% below price, leaving a wider risk range'
    elif price <= ma50.iloc[-1]:
        entry_phrase = 'price remains below the 50-day average, so trend confirmation is still missing'
    else:
        entry_phrase = f'price is near its short-term trend with a {distance:.1f}% distance to the support-based stop reference'
    qualitative = f"{ticker} shows {trend_phrase}, while {momentum_phrase}. It has {strength_phrase} over 63 trading sessions, and {entry_phrase}."
    return {'ticker':ticker, 'status':'ready', 'score':score, 'return_prior100d':round(float((c.iloc[-101]/c.iloc[-201]-1)*100),2), 'return_100d':round(float((c.iloc[-1]/c.iloc[-101]-1)*100),2), 'return_200d':round(float((c.iloc[-1]/c.iloc[-201]-1)*100),2), 'return_1y':round(float((c.iloc[-1]/c.iloc[-253]-1)*100),2) if len(c)>=253 else None, 'reason':reason, 'qualitative_summary':qualitative, 'as_of':d.index[-1].date().isoformat(), 'price':round(price,2), 'rsi':round(rsi,1), 'macd_histogram':round(float(hist.iloc[-1]),4), 'ma20':round(float(ma20.iloc[-1]),2), 'ma50':round(float(ma50.iloc[-1]),2), 'ma200':round(float(ma200.iloc[-1]),2), 'atr_pct':round(atr_pct,2), 'extension_pct':round(extension,2), 'support':round(support,2), 'stop_reference':round(stop,2), 'stop_distance_pct':round(distance,2), 'volume_ratio':round(vol_ratio,2) if vol_ratio is not None else None, 'excess_21d':round(excess21,2), 'excess_63d':round(excess63,2), 'components':{k:round(v,1) for k,v in components.items()}, 'source':frame.attrs.get('url', f'https://finance.yahoo.com/quote/{ticker}/history/'), 'data_provider':frame.attrs.get('source', 'Yahoo Finance'), 'price_basis':frame.attrs.get('basis', 'adjusted'), 'benchmark_provider':benchmark.attrs.get('source', 'Yahoo Finance')}
