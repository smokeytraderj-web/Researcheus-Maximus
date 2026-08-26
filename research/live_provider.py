"""Live market research provider with deterministic indicators and optional AI synthesis."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
from core.models import ChartRecord, Confidence, Horizon, PortfolioFitAssessment, Rating, ResearchRequest, ResearchResult, SecurityIdentity, SourceRecord
from research.comparison import build_comparison_assessment
from research.synthesis import deterministic_synthesis, ollama_synthesize, openai_synthesize
from research.technical import (
    analyze_history,
    fibonacci_decision_insight,
    historical_trade_examples,
    incorporate_relative_performance,
    momentum_decision_insight,
    render_chart,
    render_fibonacci_chart,
    render_momentum_chart,
    render_relative_performance_chart,
    render_risk_chart,
    render_stop_loss_evidence_chart,
    render_total_return_chart,
    render_trade_case_chart,
    relative_performance_returns,
    risk_chart_insight,
    stop_loss_decision_insights,
    strategies,
    technical_action_plan,
    technical_finding,
    total_return_chart_insights,
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


_SECTOR_BENCHMARKS = {
    "basic materials": ("XLB", "Materials Select Sector SPDR Fund"),
    "communication services": ("XLC", "Communication Services Select Sector SPDR Fund"),
    "consumer cyclical": ("XLY", "Consumer Discretionary Select Sector SPDR Fund"),
    "consumer defensive": ("XLP", "Consumer Staples Select Sector SPDR Fund"),
    "energy": ("XLE", "Energy Select Sector SPDR Fund"),
    "financial services": ("XLF", "Financial Select Sector SPDR Fund"),
    "healthcare": ("XLV", "Health Care Select Sector SPDR Fund"),
    "industrials": ("XLI", "Industrial Select Sector SPDR Fund"),
    "real estate": ("XLRE", "Real Estate Select Sector SPDR Fund"),
    "technology": ("XLK", "Technology Select Sector SPDR Fund"),
    "utilities": ("XLU", "Utilities Select Sector SPDR Fund"),
}


def _comparison_benchmark(primary_info: dict, secondary_info: dict) -> tuple[str, str]:
    """Choose an industry benchmark when possible, then sector, then broad market."""
    primary_industry = str(primary_info.get("industry") or "").lower()
    secondary_industry = str(secondary_info.get("industry") or "").lower()
    if "semiconductor" in primary_industry and "semiconductor" in secondary_industry:
        return "SOXX", "iShares Semiconductor ETF"
    primary_sector = str(primary_info.get("sector") or "").lower()
    secondary_sector = str(secondary_info.get("sector") or "").lower()
    if primary_sector and primary_sector == secondary_sector and primary_sector in _SECTOR_BENCHMARKS:
        return _SECTOR_BENCHMARKS[primary_sector]
    return "SPY", "SPDR S&P 500 ETF Trust (broad-market benchmark)"


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
            Horizon.ALL: (70, 30),
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
    portfolio_fit: PortfolioFitAssessment | None = None,
    historical_case_count: int = 0,
) -> str:
    """Answer the user's decision directly while keeping the conclusion conditional."""
    positive = {Rating.STRONG_BUY, Rating.BUY, Rating.ADD}
    negative = {Rating.REDUCE, Rating.SELL, Rating.AVOID}
    historical = bool(request.custom_end and request.custom_end < dt.date.today().isoformat())
    timing = technical_setup(technical).lower()
    if request.decision_intent == "portfolio_fit" and portfolio_fit is not None:
        return f"Portfolio-fit answer: {portfolio_fit.fit_label}. {portfolio_fit.summary}"
    if request.decision_intent == "historical_trade_examples":
        if historical_case_count:
            return (
                f"Historical case-study answer: {historical_case_count} rules-based long-entry example"
                f"{'s' if historical_case_count != 1 else ''} met the stated filters in the selected range. "
                "Each example uses only information available at the signal date and shows its hypothetical entry, protective stop, and exit."
            )
        return (
            "Historical case-study answer: no entry met every rule in the selected range; the report does not invent a trade to fill the request."
        )
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


def _external_user_context(request: ResearchRequest) -> dict:
    """Send only research instructions—not private position fields—to external synthesis."""
    return {
        "question": request.question,
        "decision_intent": request.decision_intent,
        "portfolio_allocation": request.portfolio_allocation or None,
        "historical_trade_examples": request.historical_trade_examples,
        "custom_analysis_range": (
            {"start": request.custom_start, "end": request.custom_end}
            if request.custom_start
            else None
        ),
    }


def _short_provider_description(value: object, limit: int = 520) -> str:
    """Return up to two complete provider-description sentences for a report opener."""
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    sentences = []
    for sentence in text.replace("!", ".").replace("?", ".").split("."):
        clean = sentence.strip()
        if clean:
            sentences.append(clean + ".")
        if len(sentences) == 2:
            break
    summary = " ".join(sentences) or text
    if len(summary) <= limit:
        return summary
    shortened = summary[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened + "…"


def _fund_request_summary(company: str, symbol: str, info: dict) -> str:
    """Build a factual, concise fund overview from available provider fields."""
    quote_type = str(info.get("quoteType") or "fund").upper()
    security_type = "exchange-traded fund" if quote_type == "ETF" else "mutual fund" if quote_type == "MUTUALFUND" else "fund"
    category = str(info.get("category") or info.get("legalType") or "").strip()
    family = str(info.get("fundFamily") or "").strip()
    description = _short_provider_description(info.get("longBusinessSummary"))
    opener = f"{company} ({symbol}) is a {security_type}"
    if family:
        opener += f" from {family}"
    if category:
        opener += f" classified as {category}"
    opener += "."
    details = []
    expense = _as_fraction(_first_number(info, "annualReportExpenseRatio", "netExpenseRatio"))
    if expense is not None:
        details.append(f"reported expense ratio {expense:.2%}")
    assets = _first_number(info, "totalAssets", "netAssets")
    if isinstance(assets, (int, float)):
        details.append(f"reported net assets {_metric(assets, money=True)}")
    fund_yield = _as_fraction(info.get("yield"))
    if fund_yield is not None:
        details.append(f"reported distribution yield {fund_yield:.2%}")
    facts = f" Available provider fields show {', '.join(details)}." if details else ""
    return " ".join(part for part in (opener, description, facts) if part).strip()


def _request_specific_response(
    request: ResearchRequest,
    company: str,
    symbol: str,
    info: dict,
    lead: Rating,
    technical: Rating,
    fundamental_summary: str,
    portfolio_fit: PortfolioFitAssessment | None = None,
    historical_case_count: int = 0,
    comparison_verdict: str = "",
) -> str:
    """Answer the user's stated research focus before the standard report framework."""
    question = request.question.lower()
    asks_for_overview = any(
        phrase in question
        for phrase in ("tell me about", "tell me a little", "about the fund", "fund summary", "summary to start", "what is this fund", "overview of")
    )
    quote_type = str(info.get("quoteType") or "").upper()
    is_fund = quote_type in {"ETF", "MUTUALFUND"} or bool(info.get("category") or info.get("fundFamily"))
    if asks_for_overview and is_fund:
        return _fund_request_summary(company, symbol, info)
    if comparison_verdict:
        return comparison_verdict
    direct = _direct_decision_answer(request, company, lead, technical, portfolio_fit, historical_case_count)
    if request.decision_intent != "research":
        return direct
    if request.question.strip() and fundamental_summary.strip():
        return fundamental_summary.strip()
    return direct


def _as_fraction(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number / 100 if number > 1.5 else number


def _usable_fund_value(value: object) -> bool:
    """Return True for provider values that can safely populate fund fields."""
    if value is None:
        return False
    try:
        import pandas as pd

        if pd.isna(value):
            return False
    except (ImportError, TypeError, ValueError):
        pass
    return not isinstance(value, str) or value.strip().lower() not in {"", "none", "n/a", "unavailable"}


def _set_fund_value(target: dict, key: str, value: object) -> None:
    if _usable_fund_value(value) and not _usable_fund_value(target.get(key)):
        target[key] = value


def _fund_table_value(table, row: str, symbol: str) -> object:
    """Read a fund-data row without assuming that Yahoo preserved the ticker column label."""
    try:
        if table is None or table.empty or row not in table.index:
            return None
        if symbol in table.columns:
            return table.loc[row, symbol]
        candidate_columns = [column for column in table.columns if str(column).lower() != "category average"]
        return table.loc[row, candidate_columns[0]] if candidate_columns else None
    except Exception:
        return None


def _infer_fund_category(info: dict) -> str:
    descriptor = " ".join(
        str(info.get(key) or "")
        for key in ("longName", "shortName", "longBusinessSummary", "legalType")
    ).lower()
    if "market neutral" in descriptor:
        return "Equity Market Neutral"
    if any(term in descriptor for term in ("balanced", "allocation", "multi-asset", "target risk")):
        return "Allocation"
    if any(term in descriptor for term in ("bond", "fixed income", "municipal", "government income", "credit")):
        return "Fixed Income"
    if any(term in descriptor for term in ("equity", "stock", "growth", "value")):
        return "Equity"
    return "Other - fact sheet classification required"


def _infer_fund_family(info: dict) -> str:
    descriptor = " ".join(str(info.get(key) or "") for key in ("longName", "shortName")).lower()
    for needle, family in (
        ("blackrock", "BlackRock"),
        ("ishares", "iShares / BlackRock"),
        ("vanguard", "Vanguard"),
        ("fidelity", "Fidelity"),
        ("t. rowe price", "T. Rowe Price"),
        ("jpmorgan", "J.P. Morgan"),
        ("pimco", "PIMCO"),
        ("invesco", "Invesco"),
        ("franklin", "Franklin Templeton"),
    ):
        if needle in descriptor:
            return family
    return ""


def _enrich_fund_info(ticker, symbol: str, info: dict) -> dict:
    """Merge yfinance's fund-specific profile, allocation, fee, and risk fields."""
    enriched = dict(info)
    try:
        funds = ticker.funds_data
        overview = funds.fund_overview or {}
        _set_fund_value(enriched, "category", overview.get("categoryName"))
        _set_fund_value(enriched, "fundFamily", overview.get("family"))
        _set_fund_value(enriched, "legalType", overview.get("legalType"))
        _set_fund_value(enriched, "longBusinessSummary", funds.description)
        _set_fund_value(enriched, "quoteType", funds.quote_type())

        for key, value in (funds.asset_classes or {}).items():
            _set_fund_value(enriched, key, value)

        operations = funds.fund_operations
        _set_fund_value(
            enriched,
            "annualReportExpenseRatio",
            _fund_table_value(operations, "Annual Report Expense Ratio", symbol),
        )
        _set_fund_value(
            enriched,
            "annualHoldingsTurnover",
            _fund_table_value(operations, "Annual Holdings Turnover", symbol),
        )
        _set_fund_value(
            enriched,
            "totalAssets",
            _fund_table_value(operations, "Total Net Assets", symbol),
        )

        bond_holdings = funds.bond_holdings
        _set_fund_value(enriched, "fundDuration", _fund_table_value(bond_holdings, "Duration", symbol))
        _set_fund_value(enriched, "fundMaturity", _fund_table_value(bond_holdings, "Maturity", symbol))
        _set_fund_value(
            enriched,
            "fundCreditQuality",
            _fund_table_value(bond_holdings, "Credit Quality", symbol),
        )
        enriched["fundCategorySource"] = "Yahoo Finance fund profile"
    except Exception:
        pass

    if not _usable_fund_value(enriched.get("category")):
        enriched["category"] = _infer_fund_category(enriched)
        enriched["fundCategorySource"] = "Inferred from the provider name/description"
    if not _usable_fund_value(enriched.get("fundFamily")):
        inferred_family = _infer_fund_family(enriched)
        if inferred_family:
            enriched["fundFamily"] = inferred_family
            enriched["fundFamilySource"] = "Inferred from the provider name"
    return enriched


def _build_portfolio_fit(
    request: ResearchRequest,
    info: dict,
    company: str,
) -> PortfolioFitAssessment | None:
    if not request.portfolio_allocation:
        return None
    equity_target, fixed_income_target = request.portfolio_allocation
    category = str(info.get("category") or info.get("legalType") or "Other - fact sheet classification required")
    category_source = str(info.get("fundCategorySource") or "Provider classification")
    descriptor = " ".join(
        str(info.get(key) or "")
        for key in ("category", "legalType", "longBusinessSummary", "longName")
    ).lower()
    stock_weight = _as_fraction(_first_number(info, "stockPosition", "equityPosition"))
    bond_weight = _as_fraction(_first_number(info, "bondPosition", "fixedIncomePosition"))
    if "market neutral" in descriptor:
        role = "Alternative / diversifier sleeve"
    elif stock_weight is not None and stock_weight >= 0.65:
        role = "Equity sleeve"
    elif bond_weight is not None and bond_weight >= 0.65:
        role = "Fixed-income sleeve"
    elif any(term in descriptor for term in ("allocation", "balanced", "multi-asset", "target-risk")):
        role = "Blended allocation fund"
    elif any(term in descriptor for term in ("bond", "fixed income", "municipal", "government income", "credit")):
        role = "Fixed-income sleeve"
    elif any(term in descriptor for term in ("equity", "stock", "growth", "value", "large blend", "small blend")):
        role = "Equity sleeve"
    else:
        role = "Role needs confirmation"

    if role == "Alternative / diversifier sleeve":
        fit_label = "Potential diversifier - not a direct 70/30 building block"
        summary = (
            f"{company} uses a market-neutral equity strategy, so it should not automatically be counted as either "
            f"the {equity_target}% equity sleeve or the {fixed_income_target}% bond sleeve."
        )
        watchouts = (
            "Confirm long, short, gross, and net exposure in the latest fact sheet.",
            "Compare beta, volatility, drawdown, and correlation with both stocks and bonds.",
            "Decide whether the allocation will sit outside the 70/30 core or reduce another sleeve explicitly.",
        )
    elif role == "Equity sleeve":
        fit_label = f"Potential fit for part of the {equity_target}% equity sleeve"
        summary = f"{company} should be judged as an equity holding, not as the portfolio's {fixed_income_target}% defensive allocation."
        watchouts = ("Avoid letting one fund create unintended style or manager concentration.", "Confirm overlap with the other equity holdings.")
    elif role == "Fixed-income sleeve":
        fit_label = f"Potential fit for part of the {fixed_income_target}% fixed-income sleeve"
        summary = f"{company} may serve the defensive side of a {equity_target}/{fixed_income_target} portfolio, subject to its duration, credit, and fee profile."
        watchouts = ("Confirm duration and credit quality before treating it as a core bond holding.", "Higher-yielding or flexible-income funds may not behave like high-quality bonds in a selloff.")
    elif role == "Blended allocation fund":
        fit_label = "Requires look-through before adding"
        summary = f"{company} already mixes asset classes, so adding it without a look-through can move the total portfolio away from the intended {equity_target}/{fixed_income_target} split."
        watchouts = ("Use the fund's current asset mix when calculating the total portfolio allocation.", "Do not count the entire position as either stocks or bonds.")
    else:
        fit_label = "Not enough allocation data for a reliable fit conclusion"
        summary = f"The available provider data does not clearly identify which part of a {equity_target}/{fixed_income_target} portfolio {company} should fill."
        watchouts = ("Review the latest fact sheet and holdings allocation.", "Confirm expenses, liquidity, and the intended portfolio role before purchase.")

    evidence = [f"Fund strategy: {category} ({category_source.lower()}).", f"Proposed role: {role}."]
    if stock_weight is not None:
        evidence.append(f"Reported stock allocation: {stock_weight:.1%}.")
    if bond_weight is not None:
        evidence.append(f"Reported bond allocation: {bond_weight:.1%}.")
    expense = _as_fraction(_first_number(info, "annualReportExpenseRatio", "netExpenseRatio"))
    if expense is not None:
        evidence.append(f"Reported expense ratio: {expense:.2%}.")
    return PortfolioFitAssessment(
        equity_target,
        fixed_income_target,
        role,
        fit_label,
        summary,
        tuple(evidence),
        watchouts,
    )


def _format_ycharts_metric(label: str, value: object) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    lowered = label.lower()
    if "upside" in lowered:
        return _metric(value, percent=True)
    if "price target" in lowered or "capitalization" in lowered:
        return _metric(value, money=True)
    return _metric(value)


def _usable_ycharts_metric(label: str, value: object) -> bool:
    """Reject placeholder values that could be mistaken for real YCharts evidence."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "n/a", "none", "unavailable", "-"}
    if not isinstance(value, (int, float)):
        return False
    if "price target" in label.lower():
        if "upside" in label.lower():
            return value != 0
        return value > 0
    return True


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
                candidates = [
                    item
                    for item in (search.quotes or [])
                    if item.get("quoteType") in {"EQUITY", "ETF", "MUTUALFUND"}
                ]
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
        deep_sector_benchmark = ""
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
        resolved_quote_type = str(info.get("quoteType") or resolved.get("quoteType") or "").upper()
        if request.portfolio_allocation or resolved_quote_type in {"ETF", "MUTUALFUND", "MUTUAL FUND"}:
            info = _enrich_fund_info(ticker, symbol, info)
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
        quote_type = str(info.get("quoteType") or resolved.get("quoteType") or "")
        if request.deep_analysis and any(
            term in request.question.lower()
            for term in ("sector", "industry benchmark", "respective benchmark", "benchmarks")
        ):
            requested_benchmarks = ["SPY"]
            sector_ticker, _sector_label = _comparison_benchmark(info, info)
            deep_sector_benchmark = sector_ticker
            if sector_ticker not in requested_benchmarks:
                requested_benchmarks.append(sector_ticker)
            for requested_benchmark in requested_benchmarks:
                if requested_benchmark == symbol or requested_benchmark in comparison_histories:
                    continue
                try:
                    benchmark_security = yf.Ticker(requested_benchmark, session=self._market_session)
                    comparison_histories[requested_benchmark] = self._history(
                        yf,
                        benchmark_security,
                        requested_benchmark,
                        self._market_session,
                        request.custom_start,
                        request.custom_end,
                    )
                except Exception:
                    comparison_failures.append(
                        f"{requested_benchmark}: requested benchmark history was unavailable"
                    )
            technical = technical_finding(snapshot)
            relative_metrics = ()
            relative_insight = ""
            if comparison_histories:
                technical, relative_metrics, relative_insight = incorporate_relative_performance(
                    technical,
                    history,
                    comparison_histories,
                )
        overview_histories: dict[str, object] = {}
        overview_benchmark = "SPY"
        overview_start = request.custom_start or dt.date.today().replace(month=1, day=1).isoformat()
        overview_end = request.custom_end or dt.date.today().isoformat()
        overview_period_label = (
            f"{request.custom_start} to {request.custom_end}"
            if request.custom_start and request.custom_end
            else "YTD"
        )
        if not request.comparison_analysis and request.overview_chart in {"", "relative_performance"}:
            if request.overview_chart == "relative_performance" and comparison_histories:
                overview_histories = {symbol: history, **comparison_histories}
                overview_benchmark = "SPY" if "SPY" in comparison_histories else deep_sector_benchmark
            else:
                overview_histories = {symbol: history}
                if symbol == "SPY":
                    overview_benchmark = ""
                else:
                    try:
                        spy_history = comparison_histories.get("SPY")
                        if spy_history is None:
                            spy_ticker = yf.Ticker("SPY", session=self._market_session)
                            spy_history = self._history(
                                yf,
                                spy_ticker,
                                "SPY",
                                self._market_session,
                                request.custom_start,
                                request.custom_end,
                            )
                        overview_histories["SPY"] = spy_history
                    except Exception:
                        comparison_failures.append("SPY: YTD benchmark history was unavailable")
        primary_identity = SecurityIdentity(company, symbol, exchange, currency)
        portfolio_fit = _build_portfolio_fit(request, info, company)
        trade_cases = historical_trade_examples(history) if request.historical_trade_examples else ()
        comparison_assessment = None
        comparison_info = {}
        secondary_snapshot = None
        secondary_identity = None
        secondary_technical = None
        secondary_symbol = ""
        benchmark_ticker = ""
        benchmark_label = ""
        benchmark_return = None
        primary_chart_return = None
        secondary_chart_return = None
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
                comparison_histories[secondary_symbol] = secondary_history
                benchmark_ticker, benchmark_label = _comparison_benchmark(info, comparison_info)
                if benchmark_ticker in {symbol, secondary_symbol}:
                    benchmark_ticker = "SPY"
                    benchmark_label = "SPDR S&P 500 ETF Trust (broad-market benchmark)"
                try:
                    benchmark_security = yf.Ticker(benchmark_ticker, session=self._market_session)
                    benchmark_history = self._history(
                        yf,
                        benchmark_security,
                        benchmark_ticker,
                        self._market_session,
                        request.custom_start,
                        request.custom_end,
                    )
                    comparison_histories[benchmark_ticker] = benchmark_history
                except Exception:
                    comparison_failures.append(
                        f"{benchmark_ticker}: sector benchmark history was unavailable"
                    )
                chart_returns = relative_performance_returns(
                    {symbol: history, **comparison_histories}
                )
                primary_chart_return = chart_returns.get(symbol)
                secondary_chart_return = chart_returns.get(secondary_symbol)
                benchmark_return = chart_returns.get(benchmark_ticker)
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
                    benchmark_ticker,
                    benchmark_label,
                    benchmark_return,
                    primary_chart_return,
                    secondary_chart_return,
                )
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
            "security_type": quote_type,
            "fund_category": info.get("category"),
            "fund_family": info.get("fundFamily"),
            "fund_expense_ratio": _first_number(info, "annualReportExpenseRatio", "netExpenseRatio"),
            "fund_yield": info.get("yield"),
            "fund_stock_position": _first_number(info, "stockPosition", "equityPosition"),
            "fund_bond_position": _first_number(info, "bondPosition", "fixedIncomePosition"),
            "comparison_symbols": tuple(comparison_histories),
            "user_context": _external_user_context(request),
        }
        if portfolio_fit is not None:
            market["portfolio_fit"] = {
                "target_allocation": f"{portfolio_fit.equity_target_pct}/{portfolio_fit.fixed_income_target_pct}",
                "security_role": portfolio_fit.security_role,
                "fit_label": portfolio_fit.fit_label,
                "summary": portfolio_fit.summary,
                "evidence": portfolio_fit.evidence,
                "watchouts": portfolio_fit.watchouts,
            }
        if request.historical_trade_examples:
            market["historical_trade_case_count"] = len(trade_cases)
            market["historical_trade_method"] = (
                "Long-only case studies: signal after the close when price reclaims SMA20, SMA50 is rising, "
                "MACD is improving, RSI is 45-72, and volume is at least 0.8x its 20-day average; entry is the next session."
            )
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
                "sector": comparison_info.get("sector"),
                "industry": comparison_info.get("industry"),
                "market_cap": comparison_info.get("marketCap"),
                "trailing_pe": comparison_info.get("trailingPE"),
                "price_to_book": comparison_info.get("priceToBook"),
                "enterprise_to_ebitda": comparison_info.get("enterpriseToEbitda"),
                "operating_margin": comparison_info.get("operatingMargins"),
                "return_on_equity": comparison_info.get("returnOnEquity"),
                "free_cash_flow": comparison_info.get("freeCashflow"),
                "debt_to_equity": comparison_info.get("debtToEquity"),
                "beta": comparison_info.get("beta"),
                "technical": dict(secondary_snapshot.as_metrics()),
            }
            market["comparison_benchmark"] = {
                "ticker": benchmark_ticker,
                "name": benchmark_label,
                "chart_period_return": benchmark_return,
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
                        benchmark_ticker,
                        benchmark_label,
                        benchmark_return,
                        primary_chart_return,
                        secondary_chart_return,
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
        technical_plan = technical_action_plan(snapshot, technical.rating, quote_type)
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
        overview_chart = None
        if workspace is not None:
            if request.comparison_analysis and comparison_histories:
                chart_path = str(
                    render_relative_performance_chart(
                        {symbol: history, **comparison_histories},
                        workspace / "security-comparison-chart.png",
                        benchmark_ticker,
                    )
                )
            else:
                chart_path = str(
                    render_chart(
                        history,
                        symbol,
                        snapshot,
                        workspace / "technical-chart.png",
                        technical_plan,
                    )
                )
            if not request.comparison_analysis:
                try:
                    if request.overview_chart == "price_trend":
                        overview_chart = ChartRecord(
                            "Price Trend and Moving Averages",
                            chart_path,
                            technical.summary,
                            (technical.summary, *technical.signals[:2]),
                        )
                    elif request.overview_chart == "stop_loss":
                        lead_stop_path = render_stop_loss_evidence_chart(
                            history,
                            symbol,
                            snapshot,
                            technical_plan,
                            workspace / "lead-stop-loss-evidence.png",
                        )
                        stop_insights = stop_loss_decision_insights(snapshot, technical_plan)
                        overview_chart = ChartRecord(
                            "Stop-Loss Evidence",
                            str(lead_stop_path),
                            stop_insights[0],
                            stop_insights,
                        )
                    elif request.overview_chart == "fibonacci":
                        lead_fibonacci_path = render_fibonacci_chart(
                            history,
                            symbol,
                            snapshot,
                            workspace / "lead-fibonacci-chart.png",
                        )
                        fibonacci_insight = fibonacci_decision_insight(snapshot, technical.rating)
                        overview_chart = ChartRecord(
                            "Fibonacci Structure",
                            str(lead_fibonacci_path),
                            fibonacci_insight,
                            (fibonacci_insight,),
                        )
                    elif request.overview_chart == "momentum":
                        lead_momentum_path = render_momentum_chart(
                            history,
                            symbol,
                            workspace / "lead-momentum-chart.png",
                        )
                        momentum_insight = momentum_decision_insight(snapshot, technical.rating)
                        overview_chart = ChartRecord(
                            "Momentum - RSI and MACD",
                            str(lead_momentum_path),
                            momentum_insight,
                            (momentum_insight,),
                        )
                    elif overview_histories:
                        lead_total_return_path = render_total_return_chart(
                            overview_histories,
                            workspace / "lead-total-return-chart.png",
                            overview_period_label,
                            overview_benchmark,
                            overview_start,
                            overview_end,
                        )
                        overview_insights = total_return_chart_insights(
                            overview_histories,
                            symbol,
                            overview_benchmark,
                            overview_period_label,
                            technical.rating,
                            overview_start,
                            overview_end,
                        )
                        overview_chart = ChartRecord(
                            f"{overview_period_label} Total Return",
                            str(lead_total_return_path),
                            overview_insights[0] if overview_insights else "",
                            overview_insights,
                        )
                except Exception as exc:
                    limitations.append(f"Lead performance chart unavailable: {exc}")
            if request.deep_analysis:
                stop_path = render_stop_loss_evidence_chart(
                    history,
                    symbol,
                    snapshot,
                    technical_plan,
                    workspace / "stop-loss-evidence.png",
                )
                stop_insights = stop_loss_decision_insights(snapshot, technical_plan)
                chartbook.append(
                    ChartRecord(
                        "Stop-Loss Evidence",
                        str(stop_path),
                        stop_insights[0],
                        stop_insights,
                    )
                )
                fibonacci_path = render_fibonacci_chart(
                    history,
                    symbol,
                    snapshot,
                    workspace / "fibonacci-chart.png",
                )
                chartbook.append(
                    ChartRecord(
                        "Fibonacci Structure",
                        str(fibonacci_path),
                        fibonacci_decision_insight(snapshot, technical.rating),
                    )
                )
                if "momentum" in request.requested_charts:
                    momentum_path = render_momentum_chart(history, symbol, workspace / "momentum-chart.png")
                    chartbook.append(
                        ChartRecord(
                            "Momentum - RSI and MACD",
                            str(momentum_path),
                            momentum_decision_insight(snapshot, technical.rating),
                        )
                    )
                if "relative_performance" in request.requested_charts and comparison_histories:
                    relative_path = render_relative_performance_chart(
                        {symbol: history, **comparison_histories},
                        workspace / "relative-performance-chart.png",
                        deep_sector_benchmark,
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
            if request.historical_trade_examples and trade_cases:
                rendered_cases = []
                for index, trade_case in enumerate(trade_cases, start=1):
                    case_path = render_trade_case_chart(
                        history,
                        symbol,
                        trade_case,
                        workspace / f"historical-trade-{index}.png",
                    )
                    rendered_cases.append(replace(trade_case, chart_path=str(case_path)))
                trade_cases = tuple(rendered_cases)
        history_source = str(history.attrs.get("market_data_source") or "Yahoo Finance market data")
        history_url = str(history.attrs.get("market_data_url") or f"https://finance.yahoo.com/quote/{quote(symbol)}")
        sources = [
            SourceRecord(history_source, history_url, now, "Price history used for the technical analysis"),
            SourceRecord("Yahoo Finance security page", f"https://finance.yahoo.com/quote/{quote(symbol)}", now, "Quote metadata, fundamentals, and news feed when available"),
            SourceRecord("TradingView chart", f"https://www.tradingview.com/chart/?symbol={quote(_tradingview_exchange(exchange))}%3A{quote(symbol)}", now, "Direct chart review link"),
            SourceRecord("YCharts", f"https://ycharts.com/companies/{quote(symbol)}", now, "Authenticated supplemental review link; no YCharts values were silently inferred"),
            SourceRecord("SEC EDGAR", f"https://www.sec.gov/edgar/search/#/q={quote(symbol)}", now, "Official filing research link"),
        ]
        if "SPY" in overview_histories and symbol != "SPY" and "SPY" not in comparison_histories:
            spy_overview_history = overview_histories["SPY"]
            spy_source = str(spy_overview_history.attrs.get("market_data_source") or "Yahoo Finance market data")
            spy_url = str(
                spy_overview_history.attrs.get("market_data_url")
                or "https://finance.yahoo.com/quote/SPY"
            )
            sources.append(
                SourceRecord(
                    f"{spy_source} - SPY",
                    spy_url,
                    now,
                    "SPY benchmark history used for the lead total-return chart",
                )
            )
        if technical_plan.options_strategy:
            sources.extend(
                (
                    SourceRecord(
                        "Options Industry Council strategy education",
                        "https://www.optionseducation.org/strategies",
                        now,
                        "Options strategy mechanics and risk education",
                    ),
                    SourceRecord(
                        "FINRA options risks",
                        "https://www.finra.org/investors/insights/options-z-basics-greeks",
                        now,
                        "Options leverage, expiration, assignment, and suitability risks",
                    ),
                )
            )
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
            if label in visible_ycharts and _usable_ycharts_metric(label, value)
        )
        raw_analyst_target = info.get("targetMeanPrice")
        analyst_target = raw_analyst_target if isinstance(raw_analyst_target, (int, float)) and raw_analyst_target > 0 else None
        analyst_upside = analyst_target / snapshot.price - 1 if analyst_target is not None else None
        fund_metrics = []
        if quote_type.upper() in {"ETF", "MUTUALFUND", "MUTUAL FUND"} or portfolio_fit is not None:
            fund_metrics.append(("Security type", quote_type.replace("MUTUALFUND", "Mutual fund").title()))
            if _usable_fund_value(info.get("category")):
                fund_metrics.append(("Fund strategy", str(info["category"])))
            if _usable_fund_value(info.get("fundFamily")):
                fund_metrics.append(("Fund family", str(info["fundFamily"])))
            expense = _as_fraction(_first_number(info, "annualReportExpenseRatio", "netExpenseRatio"))
            fund_yield = _as_fraction(info.get("yield"))
            stock_weight = _as_fraction(_first_number(info, "stockPosition", "equityPosition"))
            bond_weight = _as_fraction(_first_number(info, "bondPosition", "fixedIncomePosition"))
            cash_weight = _as_fraction(info.get("cashPosition"))
            if expense is not None:
                fund_metrics.append(("Expense ratio", _metric(expense, percent=True)))
            if fund_yield is not None:
                fund_metrics.append(("Distribution yield", _metric(fund_yield, percent=True)))
            total_assets = _first_number(info, "totalAssets", "totalNetAssets")
            if total_assets is not None:
                fund_metrics.append(("Fund net assets", _metric(total_assets, money=True)))
            turnover = _as_fraction(info.get("annualHoldingsTurnover"))
            if turnover is not None:
                fund_metrics.append(("Annual holdings turnover", _metric(turnover, percent=True)))
            if stock_weight is not None or bond_weight is not None or cash_weight is not None:
                allocation_parts = []
                for allocation_label, allocation_value in (
                    ("Stock", stock_weight),
                    ("Bond", bond_weight),
                    ("Cash", cash_weight),
                ):
                    if allocation_value is not None:
                        allocation_parts.append(f"{allocation_label} {_metric(allocation_value, percent=True)}")
                fund_metrics.append(
                    (
                        "Reported asset allocation",
                        " | ".join(allocation_parts),
                    )
                )
            for label, key, suffix in (
                ("Fund duration", "fundDuration", " years"),
                ("Fund maturity", "fundMaturity", " years"),
                ("Fund credit quality", "fundCreditQuality", ""),
            ):
                value = info.get(key)
                if _usable_fund_value(value):
                    rendered = f"{float(value):.2f}{suffix}" if isinstance(value, (int, float)) else str(value)
                    fund_metrics.append((label, rendered))
        action_metrics = (
            ("Planned entry zone", f"${technical_plan.entry_low:,.2f}-${technical_plan.entry_high:,.2f}"),
            (
                "Technical stop / invalidation",
                f"${technical_plan.stop_level:,.2f} ({technical_plan.stop_pct:.1%} below entry midpoint)",
            ),
            (
                "First / second target",
                f"${technical_plan.first_target:,.2f} / ${technical_plan.second_target:,.2f}",
            ),
            ("Estimated reward / risk", f"{technical_plan.reward_risk:.2f}x to first target"),
        )
        key_metrics = position_metrics + tuple(fund_metrics) + action_metrics + (
            ("Range-end price" if request.custom_start else "Current price", _metric(snapshot.price, money=True)),
            ("Market capitalization", _metric(info.get("marketCap"), money=True)),
            ("Trailing / forward P/E", f"{_metric(info.get('trailingPE'))} / {_metric(info.get('forwardPE'))}"),
            ("Revenue growth", _metric(info.get("revenueGrowth"), percent=True)),
            ("Earnings growth", _metric(info.get("earningsGrowth"), percent=True)),
            ("Analyst mean target", _metric(analyst_target, money=True)),
            ("Analyst target implied upside", _metric(analyst_upside, percent=True)),
            ("Street consensus (Yahoo)", str(info.get("recommendationKey") or "Unavailable").replace("_", " ").title()),
        ) + ycharts_metrics + snapshot.as_metrics() + relative_metrics
        interpretation = assessment_interpretation(technical.rating, synthesis.fundamental.rating)
        executive = (
            f"{_direct_decision_answer(request, company, lead, technical.rating, portfolio_fit, len(trade_cases))} "
            f"{company} receives a {lead.value} rating for the {request.horizon.value.lower()} horizon. "
            f"The lead framework weights fundamental evidence {fundamental_weight}% and technical evidence {technical_weight}% for this horizon. "
            f"The technical setup is {technical_setup(technical.rating).lower()}, and the fundamental outlook is "
            f"{fundamental_outlook(synthesis.fundamental.rating).lower()}. {interpretation} "
            f"{technical.summary}"
        )
        request_response = _request_specific_response(
            request,
            company,
            symbol,
            info,
            lead,
            technical.rating,
            synthesis.fundamental.summary,
            portfolio_fit,
            len(trade_cases),
            comparison_assessment.verdict if comparison_assessment else "",
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
            request_response=request_response,
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
            historical_trade_cases=tuple(trade_cases),
            portfolio_fit=portfolio_fit,
            technical_plan=technical_plan,
            overview_chart=overview_chart,
        )
        result.validate()
        return result
