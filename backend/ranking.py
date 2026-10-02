"""Bounded, temporary ranking jobs using the existing shared access gate."""
import copy
import io
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from research.stock_ranking import parse_tickers, score_stock, clean_history, VERSION, WEIGHTS

class RankingIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)

def attach_ranking_routes(app, slots):
    router = APIRouter(prefix='/api/ranking')
    jobs = {}; lock = threading.RLock(); stopping = threading.Event()
    def prune():
        for key in list(jobs):
            if jobs[key]['status'] != 'running' and time.time()-jobs[key]['started'] > 3600: jobs.pop(key)
    def snapshot(job):
        out = copy.deepcopy(job); out.pop('started', None)
        out['rows'].sort(key=lambda r: (r['status'] != 'ready', -r.get('score',0), r['ticker']))
        return out
    def worker(key):
        try:
            import yfinance as yf
            benchmark = clean_history(yf.Ticker('SPY').history(period='2y', auto_adjust=True, timeout=20))
            for ticker in jobs[key]['tickers']:
                if stopping.is_set(): break
                try:
                    frame = yf.Ticker(ticker).history(period='2y', auto_adjust=True, timeout=20)
                    row = score_stock(ticker, frame, benchmark)
                except Exception:
                    row = {'ticker':ticker, 'status':'unavailable', 'reason':'Insufficient, stale, or unavailable market data. No score assigned.'}
                with lock: jobs[key]['rows'].append(row)
            with lock: jobs[key]['status'] = 'complete' if not stopping.is_set() else 'cancelled'
        except Exception:
            with lock:
                jobs[key]['status'] = 'failed'; jobs[key]['error'] = 'SPY benchmark data is unavailable. Retry later; no scores were fabricated.'
        finally:
            with lock: jobs[key]["started"] = time.time()
            slots.release()
    @router.post('/parse')
    async def parse(request: Request, filename: str = ''):
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 2_000_000: raise HTTPException(413, 'File limit is 2 MB.')
        try:
            import pandas as pd
            if filename.lower().endswith('.xlsx'):
                import zipfile
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    if sum(x.file_size for x in archive.infolist()) > 10_000_000: raise ValueError('Workbook is too large.')
                frame = pd.read_excel(io.BytesIO(payload), header=None, nrows=5001, usecols=[0], engine='openpyxl')
            elif filename.lower().endswith(('.csv','.tsv')):
                frame = pd.read_csv(io.BytesIO(payload), header=None, sep='\t' if filename.lower().endswith('.tsv') else ',', nrows=5001, usecols=[0])
            else: raise ValueError('Use CSV, TSV, or XLSX with tickers in the first column.')
            if len(frame) > 5000: raise ValueError('Too many input rows.')
            return {'tickers':parse_tickers('\n'.join(frame.iloc[:,0].dropna().astype(str)))}
        except Exception as exc: raise HTTPException(400, 'Use a simple ticker column, up to 200 stocks, in CSV / TSV / XLSX.') from exc
    @router.post('')
    def start(body: RankingIn):
        try: tickers = parse_tickers(body.text)
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc
        with lock:
            prune()
            if any(j['status']=='running' for j in jobs.values()): raise HTTPException(409, 'A ranking is already running. Wait for it to finish.')
            if len(jobs) >= 10: raise HTTPException(429, 'Too many recent ranking runs. Try later.')
            if not slots.acquire(blocking=False): raise HTTPException(429, 'Research is busy. Try again after the current run.')
            key=secrets.token_hex(16)
            jobs[key]={'id':key,'started':time.time(),'status':'running','tickers':tickers,'rows':[],'version':VERSION,'weights':WEIGHTS,'horizon':'1–3 months','benchmark':'SPY','source':'Yahoo Finance adjusted daily OHLCV'}
            try: threading.Thread(target=worker,args=(key,),daemon=True).start()
            except Exception:
                jobs.pop(key); slots.release(); raise
            return snapshot(jobs[key])
    @router.get('/{key}')
    def get(key: str):
        with lock:
            prune()
            if key not in jobs: raise HTTPException(404,'This scorecard expired. Start a new ranking.')
            return snapshot(jobs[key])
    app.include_router(router)
    return stopping.set
