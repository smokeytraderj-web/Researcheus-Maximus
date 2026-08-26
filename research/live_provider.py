"""Live market research provider with deterministic indicators and optional AI synthesis."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.parse import quote

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
from core.models import Confidence, Horizon, Rating, ResearchRequest, ResearchResult, SecurityIdentity, SourceRecord
from research.synthesis import deterministic_synthesis, ollama_synthesize, openai_synthesize
from research.technical import analyze_history, render_chart, strategies, technical_finding
from research.ycharts_excel import retrieve_ycharts_metrics
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


def _combine_ratings(technical: Rating, fundamental: Rating, horizon: Horizon) -> tuple[Rating, int, int]:
    """Return one horizon-weighted lead rating and transparent component weights."""
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


def _format_ycharts_metric(label: str, value: object) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    lowered = label.lower()
    if "upside" in lowered:
        return _metric(value, percent=True)
    if "price target" in lowered or "capitalization" in lowered:
        return _metric(value, money=True)
    return _metric(value)


def _direct_chart_history(session, symbol: str):
    """Retrieve Yahoo's public chart JSON without the cookie/crumb workflow."""
    import pandas as pd

    if session is None:
        raise RuntimeError("verified market session was unavailable")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    response = session.get(
        url,
        params={"range": "2y", "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"},
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


def _nasdaq_history(session, symbol: str):
    """Retrieve a second, attributed US-market history when Yahoo is throttled."""
    import pandas as pd

    if session is None:
        raise RuntimeError("verified market session was unavailable")
    end = dt.date.today()
    start = end - dt.timedelta(days=740)
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
    def _history(yf, ticker, symbol: str, session=None):
        """Retrieve normalized daily history across yfinance API variations."""
        import pandas as pd

        failures = []
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
            history = self._history(yf, ticker, symbol, self._market_session)
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
            "technical": dict(snapshot.as_metrics()),
            "user_context": {
                "purchase_price": request.purchase_price,
                "quantity": request.quantity,
                "risk_tolerance": request.risk_tolerance,
                "question": request.question,
            },
        }
        ycharts_values = ()
        ycharts_errors = ()
        ycharts_audit = ()
        if self.use_ycharts and workspace is not None:
            ycharts = retrieve_ycharts_metrics(symbol, workspace)
            ycharts_values = ycharts.values
            ycharts_errors = ycharts.errors
            ycharts_audit = ycharts.audit
            if ycharts_values:
                market["ycharts_excel"] = dict(ycharts_values)
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
        technical = technical_finding(snapshot)
        lead, technical_weight, fundamental_weight = _combine_ratings(technical.rating, synthesis.fundamental.rating, request.horizon)
        limitations = list(synthesis.limitations)
        limitations.extend(ycharts_errors)
        if errors and self.synthesis_provider.lower() == "automatic":
            limitations.append("Automatic provider fallback: " + " | ".join(errors))
        confidence = Confidence.LOW if synthesis.provider_label == "Deterministic fallback" else Confidence.MEDIUM
        chart_path = ""
        if workspace is not None:
            chart_path = str(render_chart(history, symbol, snapshot, workspace / "technical-chart.png"))
        history_source = str(history.attrs.get("market_data_source") or "Yahoo Finance market data")
        history_url = str(history.attrs.get("market_data_url") or f"https://finance.yahoo.com/quote/{quote(symbol)}")
        sources = [
            SourceRecord(history_source, history_url, now, "Price history used for the technical analysis"),
            SourceRecord("Yahoo Finance security page", f"https://finance.yahoo.com/quote/{quote(symbol)}", now, "Quote metadata, fundamentals, and news feed when available"),
            SourceRecord("TradingView chart", f"https://www.tradingview.com/chart/?symbol={quote(_tradingview_exchange(exchange))}%3A{quote(symbol)}", now, "Direct chart review link"),
            SourceRecord("YCharts", f"https://ycharts.com/companies/{quote(symbol)}", now, "Authenticated supplemental review link; no YCharts values were silently inferred"),
            SourceRecord("SEC EDGAR", f"https://www.sec.gov/edgar/search/#/q={quote(symbol)}", now, "Official filing research link"),
        ]
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
            ("Current price", _metric(snapshot.price, money=True)),
            ("Market capitalization", _metric(info.get("marketCap"), money=True)),
            ("Trailing / forward P/E", f"{_metric(info.get('trailingPE'))} / {_metric(info.get('forwardPE'))}"),
            ("Revenue / earnings growth", f"{_metric(info.get('revenueGrowth'), percent=True)} / {_metric(info.get('earningsGrowth'), percent=True)}"),
            ("Analyst mean target", _metric(info.get("targetMeanPrice"), money=True)),
            ("Analyst target implied upside", _metric(analyst_upside, percent=True)),
            ("Street consensus (Yahoo)", str(info.get("recommendationKey") or "Unavailable").replace("_", " ").title()),
        ) + ycharts_metrics + snapshot.as_metrics()
        interpretation = assessment_interpretation(technical.rating, synthesis.fundamental.rating)
        executive = (
            f"{company} receives a {lead.value} rating for the {request.horizon.value.lower()} horizon. "
            f"The lead framework weights fundamental evidence {fundamental_weight}% and technical evidence {technical_weight}% for this horizon. "
            f"The technical setup is {technical_setup(technical.rating).lower()}, and the fundamental outlook is "
            f"{fundamental_outlook(synthesis.fundamental.rating).lower()}. {interpretation} "
            f"{technical.summary}"
        )
        result = ResearchResult(
            SecurityIdentity(company, symbol, exchange, currency), request.horizon, now, snapshot.price,
            technical, synthesis.fundamental, synthesis.sentiment, lead, confidence, executive,
            key_metrics, strategies(snapshot, request.horizon), synthesis.risks, synthesis.catalysts,
            synthesis.change_conditions, tuple(sources), synthesis.provider_label, tuple(limitations), chart_path, False, tuple(ycharts_audit)
        )
        result.validate()
        return result
