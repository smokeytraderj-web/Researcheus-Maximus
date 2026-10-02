"""Verified price-history fallbacks with explicit price-basis provenance."""
from __future__ import annotations
import datetime as dt
import logging
from urllib.parse import quote
import pandas as pd
from research.stock_ranking import clean_history

logger = logging.getLogger(__name__)


def yahoo_chart(session, symbol, host, adjusted=True):
    url = f'https://{host}/v8/finance/chart/{quote(symbol, safe="")}'
    response = session.get(url, params={'interval':'1d','range':'2y','events':'div,splits','includeAdjustedClose':'true'}, timeout=15)
    response.raise_for_status()
    payload=response.json().get('chart',{})
    results=payload.get('result') or []
    if payload.get('error') or not results: raise ValueError('Yahoo chart unavailable')
    result=results[0]; indicators=result.get('indicators') or {}; bars=(indicators.get('quote') or [{}])[0]
    frame=pd.DataFrame({k:bars.get(k.lower(),[]) for k in ['Close','High','Low','Volume']},index=pd.to_datetime(result.get('timestamp',[]),unit='s',utc=True))
    if adjusted:
        values=(indicators.get('adjclose') or [{}])[0].get('adjclose')
        if not values or len(values)!=len(frame):raise ValueError('Adjusted prices unavailable')
        adj=pd.Series(values,index=frame.index,dtype=float)
        factor=adj/frame.Close
        for col in ['Close','High','Low']:frame[col]=frame[col]*factor
    frame.attrs.update(source='Yahoo Finance chart API',url=f'https://finance.yahoo.com/quote/{quote(symbol,safe="")}/history/',basis='adjusted' if adjusted else 'unadjusted')
    return clean_history(frame)


def nasdaq_history(session,symbol):
    end=dt.date.today();start=end-dt.timedelta(days=740)
    for asset in (['etf','stocks'] if symbol=='SPY' else ['stocks','etf']):
        try:
            response=session.get(f'https://api.nasdaq.com/api/quote/{quote(symbol,safe="")}/historical',params={'assetclass':asset,'fromdate':start.isoformat(),'todate':end.isoformat(),'limit':5000},headers={'Accept':'application/json, text/plain, */*','Origin':'https://www.nasdaq.com','Referer':'https://www.nasdaq.com/'},timeout=15)
            response.raise_for_status();payload=response.json()
            rows=(((payload.get('data') or {}).get('tradesTable') or {}).get('rows')) or []
            if not rows:raise ValueError('Nasdaq history unavailable')
            frame=pd.DataFrame(rows).rename(columns={'date':'Date','close':'Close','high':'High','low':'Low','volume':'Volume'})
            for col in ['Close','High','Low','Volume']:frame[col]=pd.to_numeric(frame[col].astype(str).str.replace('$','',regex=False).str.replace(',','',regex=False),errors='coerce')
            frame.index=pd.to_datetime(frame.pop('Date'),utc=True)
            frame.attrs.update(source='Nasdaq historical prices',url=f'https://www.nasdaq.com/market-activity/{asset}/{quote(symbol.lower(),safe="")}/historical',basis='unadjusted')
            data=clean_history(frame)
            if data.Close.pct_change().abs().max()>.4:raise ValueError('Unadjusted history has a possible corporate-action discontinuity')
            return data
        except Exception as exc:
            logger.info('Ranking Nasdaq fallback %s/%s failed (%s)',symbol,asset,type(exc).__name__)
    raise ValueError('Nasdaq history unavailable')


def fetch_history(symbol,session,basis=None):
    """Validate each candidate before accepting it; never fabricate a fallback."""
    import yfinance as yf
    adjusted=basis!='unadjusted'
    # Bypass Yahoo's cookie/crumb flow first, then try the supported client.
    attempts=[lambda: yahoo_chart(session,symbol,'query1.finance.yahoo.com',adjusted),lambda:yahoo_chart(session,symbol,'query2.finance.yahoo.com',adjusted)]
    def client():
        frame=yf.Ticker(symbol,session=session).history(period='2y',auto_adjust=adjusted,timeout=15)
        frame.attrs.update(source='Yahoo Finance / yfinance',url=f'https://finance.yahoo.com/quote/{quote(symbol,safe="")}/history/',basis='adjusted' if adjusted else 'unadjusted')
        return clean_history(frame)
    attempts.append(client)
    if basis!='adjusted': attempts.append(lambda:nasdaq_history(session,symbol))
    for attempt in attempts:
        try:
            frame=clean_history(attempt())
            if basis and frame.attrs.get('basis')!=basis:raise ValueError('Price basis mismatch')
            return frame
        except Exception as exc:
            logger.warning('Ranking history %s fallback failed (%s)',symbol,type(exc).__name__)
    raise ValueError('No verified recent history available')
