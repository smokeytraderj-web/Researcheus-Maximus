"""Live market research provider with deterministic indicators and optional AI synthesis."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.parse import quote

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
from core.models import ChartRecord, Confidence, Horizon, Rating, ResearchRequest, ResearchResult, SecurityIdentity, SourceRecord
from research.comparison import build_comparison_assessment
from research.synthesis import deterministic_synthesis, ollama_synthesize, openai_synthesize
from research.technical import (
    analyze_history,
    incorporate_relative_performance,
    render_chart,
    render_momentum_chart,
    render_relative_performance_chart,
    render_risk_chart,
    risk_chart_insight,
    strategies,
    technical_finding,
)
from research.ycharts_excel import METRICS as YCHARTS_METRICS, retrieve_ycharts_metrics
from security.certificates import verified_market_session


def _first_number(mapping: dict, *keys):
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)):
            return value
    return None


def _metric(value, *, money=False, percent=False):
    if not isinstance(value, (int, float)):
        return "Unavailable"
    if money:
        if abs(value) >= 1_000_000_000:
            return f"${value / 1_000_000_000:,.2f}B"
        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:,.2f}M"
        return f"${value:,.2f}"
    if percent:
        return f"{value:.1%}"
    return f"{value:,.2f}"


def _tradingview_exchange(exchange: str) -> str:
    value = exchange.upper().replace(" ", "")
    if any(token in value for token in ("NASDAQ", "NMS", "NGM", "NCM")):
        return "NASDAQ"
    if "NYSE" in value or value in {"NYQ", "ASE"}:
        return "NYSE"
    if "AMEX" in value:
        return "AMEX"
    return value or "NASDAQ"


def _combine_ratings(
    technical: Rating,
    fundamental: Rating,
    horizon: Horizon,
    deep_analysis: bool = False,
) -> tuple[Rating, int, int]:
    """Return one horizon-weighted lead rating and transparent component weights."""
    if deep_analysis:
        technical_weight, fundamental_weight = (70, 30)
    else:
        technical_weight, fundamental_weight = {
            Horizon.SHORT: (80, 20),
            Horizon.MEDIUM: (50, 50),
            Horizon.LONG: (20, 80),
            Horizon.ALL: (50, 50),
        }[horizon]
    ratings = list(Rating)
    weighted_index = (
        ratings.index(technical) * technical_weight + ratings.index(fundamental) * fundamental_weight
    ) / 100
    index = int(weighted_index + 0.5)
    return ratings[max(0, min(len(ratings) - 1, index))], technical_weight, fundamental_weight


def _direct_decision_answer(
    request: ResearchRequest,
    company: str,
    lead: Rating,
    technical: Rating,
) -> str:
    """Answer the user's decision directly while keeping the conclusion conditional."""
    positive = {Rating.STRONG_BUY, Rating.BUY, Rating.ADD}
    negative = {Rating.REDUCE, Rating.SELL, Rating.AVOID}
    historical = bool(request.custom_end and request.custom_end < dt.date.today().isoformat())
    timing = technical_setup(technical).lower()
    if historical:
        return (
            f"Historical conclusion: at the {request.custom_end} range end, {company} rated {lead.value} "
            f"with a {timing} technical setup. This describes that period and is not a current buy or sell conclusion."
        )
    if request.decision_intent == "buy":
        if lead in positive:
            return (
                f"Direct answer: {company} is a conditional {lead.value.lower()} candidate on the available evidence, "
                f"but the {timing} setup means entry timing and the stated confirmation levels still matter."
            )
        if lead in negative:
            return (
                f"Direct answer: the available evidence does not support a new purchase of {company} now; "
                f"the overall view is {lead.value} and the technical setup is {timing}."
            )
        return (
            f"Direct answer: {company} is not a clear buy at this setup. The evidence supports Hold, "
            f"with a {timing} technical picture and better entry conditions listed below."
        )
    if request.decision_intent == "sell":
        if lead in negative:
            return (
                f"Direct answer: the evidence supports considering a reduction or sale of {company}, "
                "subject to taxes, position size, and the investor's original thesis."
            )
        if lead in positive:
            return (
                f"Direct answer: the available evidence does not support an outright sale of {company}; "
                f"the overall view is {lead.value}, though the listed invalidation levels should be monitored."
            )
        return (
            f"Direct answer: the evidence supports holding or trimming selectively rather than an automatic full sale of {company}."
        )
    if request.decision_intent == "position":
        action = "hold or add only on confirmation" if lead in positive else "review for reduction" if lead in negative else "hold and monitor"
        return f"Position answer: the current evidence supports {action}; the overall view is {lead.value} with a {timing} setup."
    return f"Overall conclusion: {company} rates {lead.value} on the available evidence, with a {timing} technical setup."


def _format_ycharts_metric(label: str, value: object) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    lowered = label.lower()
    if "upside" in lowered:
        return _metric(value, percent=True)
    if "price target" in lowered or "capitalization" in lowered:
        return _metric(value, money=True)
    return _metric(value)


def _direct_chart_history(session, symbol: str, start_date: str = "", end_date: str = ""):
    """Retrieve Yahoo's public chart JSON without the cookie/crumb workflow."""
    import pandas as pd

    if session is None:
        raise RuntimeError("verified market session was unavailable")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    params = {"interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"}
    if start_date and end_date:
        start = dt.date.fromisoformat(start_date)
        end = dt.date.fromisoformat(end_date) + dt.timedelta(days=1)
        params.update(
            {
                "period1": int(dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc).timestamp()),
                "period2": int(dt.datetime.combine(end, dt.time.min, tzinfo=dt.timezone.utc).timestamp()),
            }
        )
    else:
        params["range"] = "2y"
    response = session.get(
        url,
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    chart = response.json().get("chart", {})
    if chart.get("error"):
        raise RuntimeError(str(chart["error"].get("description") or chart["error"]))
    results = chart.get("result") or []
    if not results:
        raise RuntimeError("direct chart endpoint returned no result")
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_rows = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    frame = pd.DataFrame(
        {
            "Open": quote_rows.get("open") or [],
            "High": quote_rows.get("high") or [],
            "Low": quote_rows.get("low") or [],
            "Close": quote_rows.get("close") or [],
            "Volume": quote_rows.get("volume") or [],
        },
        index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None),
    )
    frame = frame.dropna(subset=["Close", "High", "Low", "Volume"])
    frame.attrs["market_data_source"] = "Yahoo Finance direct chart API"
    frame.attrs["market_data_url"] = url
    return frame


def _nasdaq_history(session, symbol: str, start_date: str = "", end_date: str = ""):
    """Retrieve a second, attributed US-market history when Yahoo is throttled."""
    import pandas as pd

    if session is None:
        raise RuntimeError("verified market session was unavailable")
    end = dt.date.fromisoformat(end_date) if end_date else dt.date.today()
    start = dt.date.fromisoformat(start_date) if start_date else end - dt.timedelta(days=740)
    api_url = f"https://api.nasdaq.com/api/quote/{quote(symbol, safe='')}/historical"
    response = session.get(
        api_url,
        params={
            "assetclass": "stocks",
            "fromdate": start.isoformat(),
            "todate": end.isoformat(),
            "limit": 5000,
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": f"https://www.nasdaq.com/market-activity/stocks/{quote(symbol.lower(), safe='')}/historical",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    status = payload.get("status") or {}
    if status.get("rCode") not in (None, 200):
        raise RuntimeError("Nasdaq historical endpoint rejected the request")
    rows = ((((payload.get("data") or {}).get("tradesTable") or {}).get("rows")) or [])
    if not rows:
        raise RuntimeError("Nasdaq historical endpoint returned no rows")
    frame = pd.DataFrame(rows).rename(
        columns={"date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    for column in ("Open", "High", "Low", "Close", "Volume"):
        frame[column] = pd.to_numeric(
            frame[column].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
            errors="coerce",
        )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Close", "High", "Low", "Volume"]).set_index("Date").sort_index()
    frame = frame[["Open", "High", "Low", "Close", "Volume"]]
    frame.attrs["market_data_source"] = "Nasdaq historical prices"
    frame.attrs["market_data_url"] = f"https://www.nasdaq.com/market-activity/stocks/{quote(symbol.lower(), safe='')}/historical"
    return frame


def _nasdaq_quote_metadata(session, symbol: str) -> dict:
    """Return basic identity metadata when Yahoo quote metadata is unavailable."""
    if session is None:
        return {}
    response = session.get(
        f"https://api.nasdaq.com/api/quote/{quote(symbol, safe='')}/info",
        params={"assetclass": "stocks"},
        headers={
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": f"https://www.nasdaq.com/market-activity/stocks/{quote(symbol.lower(), safe='')}",
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    if not data:
        return {}
    company_name = str(data.get("companyName") or "").removesuffix(" Common Stock")
    return {
        "longName": company_name,
        "fullExchangeName": data.get("exchange"),
        "currency": (data.get("primaryData") or {}).get("currency") or "USD",
        "quoteType": data.get("stockType") or "Equity",
    }


class LiveResearchProvider:
    def __init__(self, synthesis_provider: str = "Automatic", api_key: str = "", model: str = "", use_ycharts: bool = True):
        self.synthesis_provider = synthesis_provider
        self.api_key = api_key
        self.model = model
        self.use_ycharts = use_ycharts
        self._market_session = None

    def _resolve(self, query: str):
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Live market support is not installed. Re-run pip install -r requirements.txt.") from exc
        self._market_session = verified_market_session()
        cleaned = query.strip()
        candidates = []
        upper = cleaned.upper()
        looks_like_ticker = cleaned == upper and " " not in cleaned and len(cleaned) <= 10
        if not looks_like_ticker:
            try:
                search = yf.Search(cleaned, max_results=8, news_count=0, session=self._market_session)
                candidates = [item for item in (search.quotes or []) if item.get("quoteType") in {"EQUITY", "ETF"}]
            except Exception:
                candidates = []
        exact = next((item for item in candidates if str(item.get("symbol", "")).upper() == upper), None)
        selected = exact or (candidates[0] if candidates else {"symbol": upper})
        symbol = str(selected.get("symbol", upper)).upper()
        if not symbol or len(symbol) > 20:
            raise ValueError("The company or ticker could not be resolved.")
        selected = dict(selected)
        selected["originalQuery"] = cleaned
        return yf, yf.Ticker(symbol, session=self._market_session), selected

    @staticmethod
    def _history(
        yf,
        ticker,
        symbol: str,
        session=None,
        start_date: str = "",
        end_date: str = "",
    ):
        """Retrieve normalized daily history across yfinance API variations."""
        import pandas as pd

        failures = []
        if start_date and end_date:
            inclusive_end = (dt.date.fromisoformat(end_date) + dt.timedelta(days=1)).isoformat()
            attempts = (
                lambda: _direct_chart_history(session, symbol, start_date, end_date),
                lambda: _nasdaq_history(session, symbol, start_date, end_date),
                lambda: ticker.history(start=start_date, end=inclusive_end, interval="1d", auto_adjust=True),
                lambda: yf.download(
                    symbol,
                    start=start_date,
                    end=inclusive_end,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                    session=session,
                ),
            )
        else:
            attempts = (
                lambda: _direct_chart_history(session, symbol),
                lambda: _nasdaq_history(session, symbol),
                lambda: ticker.history(period="2y", interval="1d", auto_adjust=True),
                lambda: ticker.history(period="5y", interval="1d", auto_adjust=True),
                lambda: yf.download(symbol, period="2y", interval="1d", auto_adjust=True, progress=False, threads=False, session=session),
            )
        for attempt in attempts:
            try:
                history = attempt()
                if history is None or history.empty:
                    failures.append("provider returned no rows")
                    continue
                if isinstance(history.columns, pd.MultiIndex):
                    if symbol in history.columns.get_level_values(-1):
                        history = history.xs(symbol, axis=1, level=-1)
                    else:
                        history.columns = history.columns.get_level_values(0)
                if {"Close", "High", "Low", "Volume"}.issubset(history.columns):
                    if start_date and end_date:
                        history = history.loc[
                            (history.index >= start_date) & (history.index <= end_date)
                        ].copy()
                        history.attrs["custom_range"] = True
                        history.attrs["analysis_range_label"] = f"{start_date} to {end_date}"
                        if len(history) < 60:
                            failures.append("custom range returned fewer than 60 trading sessions")
                            continue
                    return history
                failures.append("provider returned incomplete OHLCV columns")
            except Exception as exc:
                failures.append(f"{type(exc).__name__}: {exc}")
        detail = " | ".join(failures[-5:])
        raise RuntimeError(f"No usable live price history was returned for {symbol}. {detail}")

    def run(self, request: ResearchRequest, workspace: Path | None = None) -> ResearchResult:
        request.validate()
        yf, ticker, resolved = self._resolve(request.query)
        symbol = str(resolved.get("symbol") or ticker.ticker).upper()
        try:
            history = self._history(
                yf,
                ticker,
                symbol,
                self._market_session,
                request.custom_start,
                request.custom_end,
            )
        except Exception as exc:
            original = str(resolved.get("originalQuery") or request.query).upper()
            correction = f" The search resolved {original} to {symbol}; confirm that correction." if original != symbol else ""
            if original == "SPCX":
                correction = " SPCX is not a conventional exchange-listed Yahoo Finance symbol. If you meant SPX Technologies, use SPXC; private or pre-IPO securities are outside the current live-price workflow."
            detail = str(exc)
            if "certificate" in detail.lower() or "curl: (60)" in detail.lower():
                raise RuntimeError(
                    "A secure connection to the market-data provider could not be established even after "
                    "loading Windows trusted certificates. Close the app, run pip install -r requirements.txt, "
                    "and try again. If this is a managed work computer, the company network certificate may "
                    "need to be added to Windows Trusted Root Certification Authorities. SSL verification was "
                    "not disabled."
                ) from exc
            raise RuntimeError(f"Live price history for {symbol} could not be retrieved.{correction} Details: {detail}") from exc
        snapshot = analyze_history(history)
        comparison_histories = {}
        comparison_failures = []
        if request.deep_analysis:
            for comparison_symbol in request.comparison_symbols:
                cleaned_comparison = comparison_symbol.strip().upper()
                if not cleaned_comparison or cleaned_comparison == symbol:
                    continue
                try:
                    comparison_ticker = yf.Ticker(cleaned_comparison, session=self._market_session)
                    comparison_histories[cleaned_comparison] = self._history(
                        yf,
                        comparison_ticker,
                        cleaned_comparison,
                        self._market_session,
                        request.custom_start,
                        request.custom_end,
                    )
                except Exception:
                    comparison_failures.append(f"{cleaned_comparison}: live comparison history was unavailable")
        technical = technical_finding(snapshot)
        relative_metrics = ()
        relative_insight = ""
        if request.deep_analysis and comparison_histories:
            technical, relative_metrics, relative_insight = incorporate_relative_performance(
                technical,
                history,
                comparison_histories,
            )
        try:
            info = ticker.get_info() or {}
        except Exception:
            info = {}
        metadata_fallback_used = False
        if not info.get("longName") or not info.get("fullExchangeName"):
            try:
                fallback_info = _nasdaq_quote_metadata(self._market_session, symbol)
            except Exception:
                fallback_info = {}
            for key, value in fallback_info.items():
                if value and not info.get(key):
                    info[key] = value
                    metadata_fallback_used = True
        company = str(info.get("longName") or resolved.get("longname") or resolved.get("shortname") or symbol)
        exchange = str(info.get("fullExchangeName") or resolved.get("exchange") or "Unconfirmed")
        currency = str(info.get("currency") or "USD")
        quote_type = str(info.get("quoteType") or resolved.get("quoteType") or "Equity")
        primary_identity = SecurityIdentity(company, symbol, exchange, currency)
        comparison_assessment = None
        comparison_info = {}
        secondary_snapshot = None
        secondary_identity = None
        secondary_technical = None
        secondary_symbol = ""
        if request.comparison_analysis:
            try:
                secondary_yf, secondary_ticker, secondary_resolved = self._resolve(request.comparison_query)
                secondary_symbol = str(secondary_resolved.get("symbol") or secondary_ticker.ticker).upper()
                if secondary_symbol == symbol:
                    raise ValueError("Choose two different securities or funds to compare.")
                secondary_history = self._history(
                    secondary_yf,
                    secondary_ticker,
                    secondary_symbol,
                    self._market_session,
                    request.custom_start,
                    request.custom_end,
                )
                secondary_snapshot = analyze_history(secondary_history)
                try:
                    comparison_info = secondary_ticker.get_info() or {}
                except Exception:
                    comparison_info = {}
                if not comparison_info.get("longName") or not comparison_info.get("fullExchangeName"):
                    try:
                        secondary_fallback = _nasdaq_quote_metadata(self._market_session, secondary_symbol)
                    except Exception:
                        secondary_fallback = {}
                    for key, value in secondary_fallback.items():
                        if value and not comparison_info.get(key):
                            comparison_info[key] = value
                secondary_identity = SecurityIdentity(
                    str(
                        comparison_info.get("longName")
                        or secondary_resolved.get("longname")
                        or secondary_resolved.get("shortname")
                        or secondary_symbol
                    ),
                    secondary_symbol,
                    str(
                        comparison_info.get("fullExchangeName")
                        or secondary_resolved.get("exchange")
                        or "Unconfirmed"
                    ),
                    str(comparison_info.get("currency") or "USD"),
                )
                secondary_technical = technical_finding(secondary_snapshot)
                comparison_assessment = build_comparison_assessment(
                    primary_identity,
                    snapshot.price,
                    info,
                    snapshot,
                    technical,
                    secondary_identity,
                    secondary_snapshot.price,
                    comparison_info,
                    secondary_snapshot,
                    secondary_technical,
                )
                comparison_histories[secondary_symbol] = secondary_history
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"The second security ({request.comparison_query}) could not be retrieved for comparison. "
                    f"Confirm the company or ticker and try again. Details: {exc}"
                ) from exc
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
        try:
            raw_news = ticker.get_news(count=10) or []
        except Exception:
            raw_news = []
        news = []
        for item in raw_news:
            content = item.get("content", item)
            link = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
            if isinstance(link, dict):
                link = link.get("url", "")
            news.append({"title": content.get("title", ""), "publisher": content.get("provider", {}).get("displayName", ""), "url": link, "published": content.get("pubDate", "")})
        market = {
            "current_price": snapshot.price,
            "market_cap": info.get("marketCap"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            "price_to_book": info.get("priceToBook"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin": info.get("profitMargins"),
            "free_cash_flow": info.get("freeCashflow"),
            "debt_to_equity": info.get("debtToEquity"),
            "analyst_target_mean": info.get("targetMeanPrice"),
            "analyst_recommendation": info.get("recommendationKey"),
            "technical": dict(snapshot.as_metrics() + relative_metrics),
            "analysis_mode": "Deep Technical Analysis" if request.deep_analysis else "Standard Research",
            "comparison_symbols": tuple(comparison_histories),
            "user_context": {
                "purchase_price": request.purchase_price,
                "quantity": request.quantity,
                "risk_tolerance": request.risk_tolerance,
                "question": request.question,
                "decision_intent": request.decision_intent,
                "custom_analysis_range": (
                    {"start": request.custom_start, "end": request.custom_end}
                    if request.custom_start
                    else None
                ),
            },
        }
        if comparison_assessment and secondary_snapshot is not None:
            market["analysis_mode"] = "Security Comparison"
            market["comparison_security"] = {
                "company": comparison_assessment.secondary_identity.company_name,
                "ticker": comparison_assessment.secondary_identity.ticker,
                "current_price": comparison_assessment.secondary_price,
                "forward_pe": comparison_info.get("forwardPE"),
                "price_to_sales": comparison_info.get("priceToSalesTrailing12Months"),
                "revenue_growth": comparison_info.get("revenueGrowth"),
                "earnings_growth": comparison_info.get("earningsGrowth"),
                "profit_margin": comparison_info.get("profitMargins"),
                "analyst_target_mean": comparison_info.get("targetMeanPrice"),
                "technical": dict(secondary_snapshot.as_metrics()),
            }
        ycharts_values = ()
        ycharts_errors = ()
        ycharts_audit = ()
        ycharts_status = "YCharts disabled - supplemental YCharts data is not included in this report."
        if self.use_ycharts and workspace is not None:
            ycharts = retrieve_ycharts_metrics(symbol, workspace)
            ycharts_values = ycharts.values
            ycharts_errors = ycharts.errors
            ycharts_audit = ycharts.audit
            if ycharts_values:
                market["ycharts_excel"] = dict(ycharts_values)
            primary_loaded = len(ycharts_values)
            primary_expected = len(YCHARTS_METRICS)
            if primary_loaded == primary_expected:
                ycharts_status = f"YCharts connected - all {primary_expected} supplemental metrics loaded."
            elif primary_loaded:
                ycharts_status = (
                    f"YCharts partially available - {primary_loaded} of {primary_expected} metrics loaded for {symbol}. "
                    "The report can continue, but some YCharts evidence is missing."
                )
            else:
                ycharts_status = (
                    f"YCharts unavailable - no supplemental metrics loaded for {symbol}. "
                    "The report can continue, but it will be missing YCharts ratings, targets, and valuation data."
                )
            if request.comparison_analysis and secondary_symbol:
                secondary_ycharts = retrieve_ycharts_metrics(secondary_symbol, workspace)
                ycharts_errors = tuple(ycharts_errors) + tuple(
                    f"{secondary_symbol}: {error}" for error in secondary_ycharts.errors
                )
                ycharts_audit = tuple(
                    (f"{cell} ({symbol})", formula, status) for cell, formula, status in ycharts_audit
                ) + tuple(
                    (f"{cell} ({secondary_symbol})", formula, status)
                    for cell, formula, status in secondary_ycharts.audit
                )
                primary_comparison_info = dict(info)
                secondary_comparison_info = dict(comparison_info)
                primary_ycharts = dict(ycharts_values)
                secondary_ycharts_values = dict(secondary_ycharts.values)
                secondary_loaded = len(secondary_ycharts.values)
                total_loaded = primary_loaded + secondary_loaded
                total_expected = primary_expected * 2
                if total_loaded == total_expected:
                    ycharts_status = f"YCharts connected - all {total_expected} comparison metrics loaded."
                elif total_loaded:
                    ycharts_status = (
                        f"YCharts partially available - {total_loaded} of {total_expected} comparison metrics loaded. "
                        "The comparison can continue, but some YCharts evidence is missing."
                    )
                else:
                    ycharts_status = (
                        "YCharts unavailable - no supplemental comparison metrics loaded. The comparison can continue, "
                        "but it will be missing YCharts ratings, targets, and valuation data."
                    )
                for target, evidence in (
                    (primary_comparison_info, primary_ycharts),
                    (secondary_comparison_info, secondary_ycharts_values),
                ):
                    target.setdefault("forwardPE", evidence.get("YCharts P/E ratio"))
                    target.setdefault(
                        "priceToSalesTrailing12Months",
                        evidence.get("YCharts price/sales ratio"),
                    )
                    target.setdefault("targetMeanPrice", evidence.get("YCharts price target"))
                if secondary_identity and secondary_snapshot and secondary_technical:
                    comparison_assessment = build_comparison_assessment(
                        primary_identity,
                        snapshot.price,
                        primary_comparison_info,
                        snapshot,
                        technical,
                        secondary_identity,
                        secondary_snapshot.price,
                        secondary_comparison_info,
                        secondary_snapshot,
                        secondary_technical,
                    )
        provider = self.synthesis_provider.lower()
        errors = []
        synthesis = None
        if provider in {"automatic", "openai"}:
            try:
                synthesis = openai_synthesize(company, symbol, request.horizon, market, news, now, self.api_key, self.model)
            except Exception as exc:
                errors.append(str(exc))
                if provider == "openai":
                    raise
        if synthesis is None and provider in {"automatic", "ollama"}:
            try:
                synthesis = ollama_synthesize(company, symbol, request.horizon, market, news, now, self.model)
            except Exception as exc:
                errors.append(str(exc))
                if provider == "ollama":
                    raise
        if synthesis is None:
            synthesis = deterministic_synthesis(info, news, now, snapshot.price, dict(ycharts_values))
        lead, technical_weight, fundamental_weight = _combine_ratings(
            technical.rating,
            synthesis.fundamental.rating,
            request.horizon,
            request.deep_analysis,
        )
        limitations = list(synthesis.limitations)
        limitations.extend(ycharts_errors)
        if request.custom_end and request.custom_end < dt.date.today().isoformat():
            limitations.append(
                f"Technical evidence and price end on {request.custom_end}; fundamental, news, and consensus fields may reflect later provider updates."
            )
        if comparison_failures:
            limitations.append("Comparison data unavailable: " + " | ".join(comparison_failures))
        if errors and self.synthesis_provider.lower() == "automatic":
            limitations.append("Automatic provider fallback: " + " | ".join(errors))
        confidence = Confidence.LOW if synthesis.provider_label == "Deterministic fallback" else Confidence.MEDIUM
        chart_path = ""
        chartbook = []
        if workspace is not None:
            if request.comparison_analysis and comparison_histories:
                chart_path = str(
                    render_relative_performance_chart(
                        {symbol: history, **comparison_histories},
                        workspace / "security-comparison-chart.png",
                    )
                )
            else:
                chart_path = str(render_chart(history, symbol, snapshot, workspace / "technical-chart.png"))
            if request.deep_analysis:
                if "momentum" in request.requested_charts:
                    momentum_path = render_momentum_chart(history, symbol, workspace / "momentum-chart.png")
                    momentum_direction = "positive" if snapshot.macd > snapshot.macd_signal else "negative"
                    chartbook.append(
                        ChartRecord(
                            "Momentum - RSI and MACD",
                            str(momentum_path),
                            f"RSI is {snapshot.rsi14:.1f}; MACD momentum is {momentum_direction} ({snapshot.macd:.2f} versus {snapshot.macd_signal:.2f}).",
                        )
                    )
                if "relative_performance" in request.requested_charts and comparison_histories:
                    relative_path = render_relative_performance_chart(
                        {symbol: history, **comparison_histories},
                        workspace / "relative-performance-chart.png",
                    )
                    chartbook.append(
                        ChartRecord(
                            "Relative Performance",
                            str(relative_path),
                            relative_insight or "Normalized performance comparison across common trading dates.",
                        )
                    )
                if "risk" in request.requested_charts:
                    risk_path = render_risk_chart(history, symbol, workspace / "risk-chart.png")
                    chartbook.append(
                        ChartRecord(
                            "Drawdown and Volatility",
                            str(risk_path),
                            risk_chart_insight(history, symbol),
                        )
                    )
        history_source = str(history.attrs.get("market_data_source") or "Yahoo Finance market data")
        history_url = str(history.attrs.get("market_data_url") or f"https://finance.yahoo.com/quote/{quote(symbol)}")
        sources = [
            SourceRecord(history_source, history_url, now, "Price history used for the technical analysis"),
            SourceRecord("Yahoo Finance security page", f"https://finance.yahoo.com/quote/{quote(symbol)}", now, "Quote metadata, fundamentals, and news feed when available"),
            SourceRecord("TradingView chart", f"https://www.tradingview.com/chart/?symbol={quote(_tradingview_exchange(exchange))}%3A{quote(symbol)}", now, "Direct chart review link"),
            SourceRecord("YCharts", f"https://ycharts.com/companies/{quote(symbol)}", now, "Authenticated supplemental review link; no YCharts values were silently inferred"),
            SourceRecord("SEC EDGAR", f"https://www.sec.gov/edgar/search/#/q={quote(symbol)}", now, "Official filing research link"),
        ]
        for comparison_symbol, comparison_history in comparison_histories.items():
            comparison_source = str(comparison_history.attrs.get("market_data_source") or "Yahoo Finance market data")
            comparison_url = str(
                comparison_history.attrs.get("market_data_url")
                or f"https://finance.yahoo.com/quote/{quote(comparison_symbol)}"
            )
            sources.append(
                SourceRecord(
                    f"{comparison_source} - {comparison_symbol}",
                    comparison_url,
                    now,
                    "Comparison history used for normalized performance and side-by-side analysis",
                )
            )
        if metadata_fallback_used:
            sources.insert(1, SourceRecord("Nasdaq company information", f"https://www.nasdaq.com/market-activity/stocks/{quote(symbol.lower())}", now, "Company identity and exchange metadata"))
        sources.extend(synthesis.sources)
        position_metrics = ()
        if request.purchase_price is not None:
            position_metrics += (
                ("User purchase price", _metric(request.purchase_price, money=True)),
                ("Gain/loss from purchase price", _metric(snapshot.price / request.purchase_price - 1, percent=True)),
            )
        if request.quantity is not None:
            position_metrics += (
                ("User quantity", f"{request.quantity:,.4f}".rstrip("0").rstrip(".")),
                ("Illustrative current position value", _metric(snapshot.price * request.quantity, money=True)),
            )
        visible_ycharts = {
            "YCharts consensus rating",
            "YCharts price target",
            "YCharts price target low",
            "YCharts price target high",
            "YCharts price target upside",
        }
        ycharts_metrics = tuple(
            (label, _format_ycharts_metric(label, value))
            for label, value in ycharts_values
            if label in visible_ycharts
        )
        analyst_target = info.get("targetMeanPrice")
        analyst_upside = analyst_target / snapshot.price - 1 if isinstance(analyst_target, (int, float)) and analyst_target > 0 else None
        key_metrics = position_metrics + (
            ("Range-end price" if request.custom_start else "Current price", _metric(snapshot.price, money=True)),
            ("Market capitalization", _metric(info.get("marketCap"), money=True)),
            ("Trailing / forward P/E", f"{_metric(info.get('trailingPE'))} / {_metric(info.get('forwardPE'))}"),
            ("Revenue / earnings growth", f"{_metric(info.get('revenueGrowth'), percent=True)} / {_metric(info.get('earningsGrowth'), percent=True)}"),
            ("Analyst mean target", _metric(info.get("targetMeanPrice"), money=True)),
            ("Analyst target implied upside", _metric(analyst_upside, percent=True)),
            ("Street consensus (Yahoo)", str(info.get("recommendationKey") or "Unavailable").replace("_", " ").title()),
        ) + ycharts_metrics + snapshot.as_metrics() + relative_metrics
        interpretation = assessment_interpretation(technical.rating, synthesis.fundamental.rating)
        executive = (
            f"{_direct_decision_answer(request, company, lead, technical.rating)} "
            f"{company} receives a {lead.value} rating for the {request.horizon.value.lower()} horizon. "
            f"The lead framework weights fundamental evidence {fundamental_weight}% and technical evidence {technical_weight}% for this horizon. "
            f"The technical setup is {technical_setup(technical.rating).lower()}, and the fundamental outlook is "
            f"{fundamental_outlook(synthesis.fundamental.rating).lower()}. {interpretation} "
            f"{technical.summary}"
        )
        result = ResearchResult(
            identity=primary_identity,
            horizon=request.horizon,
            as_of=now,
            current_price=snapshot.price,
            technical=technical,
            fundamental=synthesis.fundamental,
            sentiment=synthesis.sentiment,
            lead_rating=lead,
            confidence=confidence,
            executive_summary=executive,
            key_metrics=key_metrics,
            strategies=strategies(snapshot, request.horizon),
            risks=synthesis.risks,
            catalysts=synthesis.catalysts,
            change_conditions=synthesis.change_conditions,
            sources=tuple(sources),
            provider_label=synthesis.provider_label,
            limitations=tuple(limitations),
            chart_path=chart_path,
            demo_mode=False,
            ycharts_audit=tuple(ycharts_audit),
            analysis_mode=(
                "Security Comparison"
                if request.comparison_analysis
                else "Deep Technical Analysis"
                if request.deep_analysis
                else "Standard Research"
            ),
            chartbook=tuple(chartbook),
            comparison=comparison_assessment,
            ycharts_status=ycharts_status,
        )
        result.validate()
        return result
