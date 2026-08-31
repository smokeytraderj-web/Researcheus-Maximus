"""Build the track-record report from the call log and live prices."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from core.session import ResearchSession
from reports.call_log import CALL_LOG_FILENAME
from reports.track_record_report import build_track_record_html
from research.technical import render_track_record_chart
from research.track_record import (
    build_equity_curve,
    build_picks,
    read_call_log,
    score_picks,
)

BENCHMARK = "SPY"


class TrackRecordRunner:
    """Reads the log, prices the picks, and renders the report."""

    def __init__(self, session_root: Path | None = None):
        self.session_root = session_root

    def _history(self, tickers: list[str], start: str):
        """Daily closes for each ticker plus the benchmark, keyed by symbol."""
        import yfinance as yf

        history: dict = {}
        for symbol in tickers:
            try:
                frame = yf.Ticker(symbol).history(start=start, auto_adjust=False)
                closes = frame["Close"].dropna() if "Close" in frame else None
                if closes is not None and len(closes) > 1:
                    closes.index = closes.index.tz_localize(None)
                    history[symbol] = closes
            except Exception:  # noqa: BLE001 - a missing series leaves that pick unscored
                continue
        return history

    def build(self, log_directory: Path) -> tuple[Path, ResearchSession, object]:
        """Render the report; returns (path, session, record). Caller cleans the session up."""
        now = dt.datetime.now().astimezone()
        rows = read_call_log(log_directory / CALL_LOG_FILENAME)
        picks = build_picks(rows)
        session = ResearchSession.create(self.session_root)
        try:
            if not picks:
                record = score_picks((), lambda _t: None, lambda _a, _b: None, BENCHMARK, now.date().isoformat())
                path = build_track_record_html(record, "", now.isoformat(), session.preview / "track_record.html")
                return path, session, record

            earliest = min(pick.opened_at for pick in picks)
            symbols = sorted({pick.ticker for pick in picks})
            history = self._history(symbols + [BENCHMARK], earliest)
            benchmark_series = history.get(BENCHMARK)

            def current_price(ticker: str):
                series = history.get(ticker)
                return float(series.iloc[-1]) if series is not None and len(series) else None

            def benchmark_return(start: str, end: str):
                if benchmark_series is None or not start:
                    return None
                import pandas as pd

                opening = benchmark_series.asof(pd.Timestamp(start))
                closing = (
                    benchmark_series.asof(pd.Timestamp(end)) if end else float(benchmark_series.iloc[-1])
                )
                if not opening or not closing or opening <= 0:
                    return None
                return float(closing) / float(opening) - 1.0

            record = score_picks(picks, current_price, benchmark_return, BENCHMARK, now.date().isoformat())

            chart_path = ""
            index, curve, benchmark_curve = build_equity_curve(
                picks, {k: v for k, v in history.items() if k != BENCHMARK}, benchmark_series
            )
            if index is not None and curve is not None and len(curve) > 1:
                chart_path = str(
                    render_track_record_chart(
                        index, curve, benchmark_curve, BENCHMARK, session.working / "track-record.png"
                    )
                )

            path = build_track_record_html(record, chart_path, now.isoformat(), session.preview / "track_record.html")
            return path, session, record
        except Exception:
            session.cleanup()
            raise
