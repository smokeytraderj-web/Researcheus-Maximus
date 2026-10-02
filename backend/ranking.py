"""Bounded, temporary ranking jobs using the existing shared access gate."""
import copy
import io
import logging
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from research.stock_ranking import parse_tickers, score_stock, clean_history, VERSION, WEIGHTS

from research.ranking_data import fetch_history
from research.ranking_correlations import analyze_correlations
from security.certificates import verified_market_session

logger = logging.getLogger(__name__)

class RankingIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)

def attach_ranking_routes(app, slots):
    router = APIRouter(prefix='/api/ranking')
    jobs = {}; lock = threading.RLock(); stopping = threading.Event()
    def prune():
        for key in list(jobs):
            if jobs[key]['status'] != 'running' and time.time()-jobs[key]['started'] > 3600: jobs.pop(key)
    def snapshot(job):
        out = copy.deepcopy({k:v for k,v in job.items() if not k.startswith('_')}); out.pop('started', None)
        out['rows'].sort(key=lambda r: (r['status'] != 'ready', -r.get('score',0), r['ticker']))
        return out
    def worker(key):
        try:
            session = verified_market_session()
            benchmark = fetch_history('SPY', session)
            benchmarks = {benchmark.attrs.get('basis', 'adjusted'): benchmark}
            with lock:
                jobs[key]['benchmark_source'] = benchmark.attrs.get('source', 'Market history')
                jobs[key]['_benchmarks'] = {k:v.Close.iloc[-270:].copy() for k,v in benchmarks.items()}
            for ticker in jobs[key]['tickers']:
                if stopping.is_set(): break
                try:
                    frame = fetch_history(ticker, session, basis='unadjusted' if benchmark.attrs.get('basis') == 'unadjusted' else None)
                    basis = frame.attrs.get('basis', 'adjusted')
                    if basis not in benchmarks:
                        benchmarks[basis] = fetch_history('SPY', session, basis=basis)
                    row = score_stock(ticker, frame, benchmarks[basis])
                    with lock:
                        jobs[key]['_histories'][ticker] = frame.Close.iloc[-270:].copy()
                        jobs[key]['_benchmarks'][basis] = benchmarks[basis].Close.iloc[-270:].copy()
                except Exception as exc:
                    logger.warning("Ranking %s unavailable (%s)", ticker, type(exc).__name__)
                    row = {'ticker':ticker, 'status':'unavailable', 'reason':'Insufficient, stale, or unavailable market data. No score assigned.'}
                with lock: jobs[key]['rows'].append(row)
            with lock: jobs[key]['status'] = 'complete' if not stopping.is_set() else 'cancelled'
        except Exception as exc:
            logger.warning("Ranking benchmark failed (%s)", type(exc).__name__)
            with lock:
                jobs[key]['status'] = 'failed'; jobs[key]['error'] = 'SPY benchmark data is unavailable. Retry later; no scores were fabricated.'
        finally:
            if 'session' in locals():
                try: session.close()
                except Exception: pass
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
            jobs[key]={'id':key,'started':time.time(),'status':'running','tickers':tickers,'rows':[],'version':VERSION,'weights':WEIGHTS,'horizon':'1–3 months','benchmark':'SPY','source':'Verified daily OHLCV · Yahoo Finance / Nasdaq fallback','_histories':{},'_benchmarks':{},'_analytics':{}}
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
    @router.get('/{key}/analytics')
    def analytics(key: str, limit: int = Query(default=20, ge=2, le=50), market_adjusted: bool = False):
        with lock:
            prune()
            if key not in jobs: raise HTTPException(404, 'This scorecard expired. Start a new ranking.')
            job = jobs[key]
            if job['status'] != 'complete': raise HTTPException(409, 'Wait for ranking to complete before comparing returns.')
            cache_key = (limit, market_adjusted)
            if cache_key not in job['_analytics']:
                job['_analytics'][cache_key] = analyze_correlations(job['rows'], job['_histories'], job['_benchmarks'], limit, market_adjusted)
            return copy.deepcopy(job['_analytics'][cache_key])
    @router.get('/{key}/pdf')
    def pdf(key: str, limit: int = Query(default=20, ge=2, le=50), market_adjusted: bool = False):
        comparisons = analytics(key, limit, market_adjusted)
        with lock:
            job = snapshot(jobs[key])
        if not slots.acquire(blocking=False): raise HTTPException(429, 'Research is busy. Try the PDF download again shortly.')
        try:
            from reports.ranking_pdf import build_ranking_pdf
            content = build_ranking_pdf(job, comparisons)
            return Response(content, media_type='application/pdf', headers={'Content-Disposition':'attachment; filename="GSWM_Technical_Scorecard.pdf"','Cache-Control':'no-store'})
        finally: slots.release()
    app.include_router(router)
    return stopping.set
