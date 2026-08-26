"""Live market research provider with deterministic indicators and optional AI synthesis."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from urllib.parse import quote

from core.models import Confidence, Horizon, Rating, ResearchRequest, ResearchResult, SecurityIdentity, SourceRecord
from research.synthesis import deterministic_synthesis, ollama_synthesize, openai_synthesize
from research.technical import analyze_history, render_chart, strategies, technical_finding
from research.ycharts_excel import retrieve_ycharts_metrics


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


class LiveResearchProvider:
    def __init__(self, synthesis_provider: str = "Automatic", api_key: str = "", model: str = "", use_ycharts: bool = True):
        self.synthesis_provider = synthesis_provider
        self.api_key = api_key
        self.model = model
        self.use_ycharts = use_ycharts

    def _resolve(self, query: str):
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Live market support is not installed. Re-run pip install -r requirements.txt.") from exc
        cleaned = query.strip()
        candidates = []
        try:
            search = yf.Search(cleaned, max_results=8, news_count=0)
            candidates = [item for item in (search.quotes or []) if item.get("quoteType") in {"EQUITY", "ETF"}]
        except Exception:
            candidates = []
        upper = cleaned.upper()
        exact = next((item for item in candidates if str(item.get("symbol", "")).upper() == upper), None)
        selected = exact or (candidates[0] if candidates else {"symbol": upper})
        symbol = str(selected.get("symbol", upper)).upper()
        if not symbol or len(symbol) > 20:
            raise ValueError("The company or ticker could not be resolved.")
        return yf.Ticker(symbol), selected

    def run(self, request: ResearchRequest, workspace: Path | None = None) -> ResearchResult:
        request.validate()
        ticker, resolved = self._resolve(request.query)
        symbol = str(resolved.get("symbol") or ticker.ticker).upper()
        try:
            history = ticker.history(period="2y", interval="1d", auto_adjust=True, repair=False, timeout=20)
        except Exception as exc:
            raise RuntimeError(f"Live price history for {symbol} could not be retrieved.") from exc
        snapshot = analyze_history(history)
        try:
            info = ticker.get_info() or {}
        except Exception:
            info = {}
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
        if self.use_ycharts and workspace is not None:
            ycharts = retrieve_ycharts_metrics(symbol, workspace)
            ycharts_values = ycharts.values
            ycharts_errors = ycharts.errors
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
            synthesis = deterministic_synthesis(info, news, now)
        technical = technical_finding(snapshot)
        rating_value = (list(Rating).index(technical.rating) + list(Rating).index(synthesis.fundamental.rating)) / 2
        if request.horizon == Horizon.SHORT:
            rating_value = list(Rating).index(technical.rating) * 0.7 + list(Rating).index(synthesis.fundamental.rating) * 0.3
        elif request.horizon == Horizon.LONG:
            rating_value = list(Rating).index(technical.rating) * 0.3 + list(Rating).index(synthesis.fundamental.rating) * 0.7
        lead = list(Rating)[max(0, min(len(Rating) - 1, round(rating_value)))]
        limitations = list(synthesis.limitations)
        limitations.extend(ycharts_errors)
        if errors and self.synthesis_provider.lower() == "automatic":
            limitations.append("Automatic provider fallback: " + " | ".join(errors))
        confidence = Confidence.LOW if synthesis.provider_label == "Deterministic fallback" else Confidence.MEDIUM
        chart_path = ""
        if workspace is not None:
            chart_path = str(render_chart(history, symbol, snapshot, workspace / "technical-chart.png"))
        sources = [
            SourceRecord("Yahoo Finance market data", f"https://finance.yahoo.com/quote/{quote(symbol)}", now, "Price history, quote metadata, fundamentals, and news feed"),
            SourceRecord("TradingView chart", f"https://www.tradingview.com/chart/?symbol={quote(_tradingview_exchange(exchange))}%3A{quote(symbol)}", now, "Direct chart review link"),
            SourceRecord("YCharts", f"https://ycharts.com/companies/{quote(symbol)}", now, "Authenticated supplemental review link; no YCharts values were silently inferred"),
            SourceRecord("SEC EDGAR", f"https://www.sec.gov/edgar/search/#/q={quote(symbol)}", now, "Official filing research link"),
        ]
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
        ycharts_metrics = tuple((label, _metric(value, money=("target" in label.lower() or "capitalization" in label.lower()), percent="upside" in label.lower()) if isinstance(value, (int, float)) else str(value)) for label, value in ycharts_values)
        key_metrics = position_metrics + (
            ("Current price", _metric(snapshot.price, money=True)),
            ("Market capitalization", _metric(info.get("marketCap"), money=True)),
            ("Trailing / forward P/E", f"{_metric(info.get('trailingPE'))} / {_metric(info.get('forwardPE'))}"),
            ("Revenue / earnings growth", f"{_metric(info.get('revenueGrowth'), percent=True)} / {_metric(info.get('earningsGrowth'), percent=True)}"),
            ("Analyst mean target", _metric(info.get("targetMeanPrice"), money=True)),
            ("Provider recommendation", str(info.get("recommendationKey") or "Unavailable").replace("_", " ").title()),
        ) + ycharts_metrics + snapshot.as_metrics()
        executive = (
            f"{company} receives a {lead.value} rating for the {request.horizon.value.lower()} horizon. "
            f"Technical analysis is {technical.rating.value}, while fundamental analysis is {synthesis.fundamental.rating.value}. "
            f"{technical.summary} {synthesis.fundamental.summary}"
        )
        result = ResearchResult(
            SecurityIdentity(company, symbol, exchange, currency), request.horizon, now, snapshot.price,
            technical, synthesis.fundamental, synthesis.sentiment, lead, confidence, executive,
            key_metrics, strategies(snapshot, request.horizon), synthesis.risks, synthesis.catalysts,
            synthesis.change_conditions, tuple(sources), synthesis.provider_label, tuple(limitations), chart_path, False
        )
        result.validate()
        return result
