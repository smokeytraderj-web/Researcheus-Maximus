"""Helpers for the single-box research and revision workflow."""

from __future__ import annotations

import calendar
import datetime as dt
import re


_TICKER = re.compile(r"(?<![A-Za-z0-9])\$?([A-Z]{1,5}(?:[.-][A-Z])?)(?![A-Za-z0-9])")
_TICKER_STOPWORDS = {
    "A",
    "ADD",
    "ANALYZE",
    "BUY",
    "CAN",
    "HOLD",
    "I",
    "IS",
    "ATR",
    "EMA",
    "ETF",
    "MACD",
    "PLEASE",
    "RESEARCH",
    "RSI",
    "SELL",
    "SHOULD",
    "SMA",
    "THE",
    "USD",
    "VS",
    "WHAT",
    "YOU",
}


def _clean_security_candidate(value: str) -> str:
    candidate = value.strip().lstrip("$")
    for match in _TICKER.finditer(candidate):
        ticker = match.group(1)
        if ticker not in _TICKER_STOPWORDS:
            return ticker
    candidate = re.sub(
        r"^(?:please\s+)?(?:(?:full|complete|detailed)\s+)?(?:research|analysis|analyze)\s+(?:of\s+)?",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip()
    return candidate


def parse_research_prompt(value: str) -> tuple[str, str]:
    """Extract a resolvable security query while preserving the user's full brief."""
    prompt = value.strip()
    if not prompt:
        return "", ""

    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    first_line = lines[0]
    for separator in (" — ", " – ", " - ", " | ", ": "):
        if separator in first_line:
            candidate = _clean_security_candidate(first_line.split(separator, 1)[0])
            if candidate:
                return candidate, prompt

    if len(lines) > 1:
        return _clean_security_candidate(first_line), prompt

    company = re.search(
        r"\b(?:research|analyze|buy|sell|hold|add)\s+"
        r"(?:my\s+)?(?:shares?\s+(?:of|in)\s+)?"
        r"([A-Z][A-Za-z0-9.&' -]{1,60}?)"
        r"(?=\s+(?:after|before|near|at|following|for|because)\b|[?!.,]|$)",
        first_line,
        flags=re.IGNORECASE,
    )
    if company:
        candidate = re.sub(r"\s+position$", "", company.group(1).strip(), flags=re.IGNORECASE)
        return _clean_security_candidate(candidate), prompt

    open_ended_company_patterns = (
        r"\b(?:full|complete|detailed)?\s*analysis\s+of\s+([A-Z][A-Za-z0-9.&' -]{1,60}?)(?=\s+(?:and|to|from|since|with)\b|[?!.,]|$)",
        r"\bwhat\s+about\s+(?:my\s+)?([A-Z][A-Za-z0-9.&' -]{1,60}?)(?:\s+position)?(?=[?!.,]|$)",
        r"\bevaluate\s+(?:my\s+)?([A-Z][A-Za-z0-9.&' -]{1,60}?)(?:\s+position)?(?=[?!.,]|$)",
    )
    for pattern in open_ended_company_patterns:
        match = re.search(pattern, first_line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(), prompt

    for match in _TICKER.finditer(first_line):
        ticker = match.group(1)
        if ticker not in _TICKER_STOPWORDS:
            return ticker, prompt

    return first_line.lstrip("$"), prompt


def append_revision_instructions(original: str, revision: str) -> str:
    """Preserve the research brief and add an explicit report-revision mandate."""
    clean_original = original.strip()
    clean_revision = revision.strip()
    if not clean_revision:
        return clean_original
    prefix = f"{clean_original}\n\n" if clean_original else ""
    return f"{prefix}Requested modifications to the revised report:\n{clean_revision}"


def classify_research_intent(value: str) -> str:
    """Classify the decision being asked without changing the user's wording."""
    lowered = value.lower()
    if parse_portfolio_allocation(value):
        return "portfolio_fit"
    if "portfolio" in lowered and (
        re.search(r"\b\d{1,3}(?:\.\d+)?\s*(?:%|percent)\b", lowered)
        or any(term in lowered for term in ("allocation", "concentration", "exposure", "equities", "equity sleeve"))
    ):
        return "portfolio_context"
    if is_historical_trade_request(value):
        return "historical_trade_examples"
    if any(term in lowered for term in ("should i sell", "time to sell", "exit", "reduce my position")):
        return "sell"
    if any(
        term in lowered
        for term in (
            "should i buy",
            "good opportunity to buy",
            "good decision to buy",
            "good choice to buy",
            "a good buy",
            "good entry",
            "worth buying",
        )
    ):
        return "buy"
    if any(term in lowered for term in ("my position", "this position", "what about my", "should i hold", "should i add")):
        return "position"
    if any(term in lowered for term in ("full analysis", "complete analysis", "deep dive", "everything about")):
        return "full_analysis"
    return "research"


def parse_overview_chart_request(value: str) -> str:
    """Identify an explicitly requested lead chart; blank means annotated price structure."""
    lowered = value.lower()
    if any(term in lowered for term in ("stop loss chart", "stop-loss chart", "stop evidence chart", "invalidation chart")):
        return "stop_loss"
    if any(term in lowered for term in ("fibonacci chart", "fib chart", "fibonacci levels chart")):
        return "fibonacci"
    if any(term in lowered for term in ("momentum chart", "rsi chart", "macd chart")):
        return "momentum"
    if any(term in lowered for term in ("price chart", "trend chart", "moving average chart")):
        return "price_trend"
    if any(term in lowered for term in ("relative performance chart", "total return chart", "performance chart")):
        return "relative_performance"
    return ""


def parse_portfolio_allocation(value: str) -> tuple[int, int]:
    """Extract a conventional equity/fixed-income allocation such as 70/30."""
    match = re.search(r"\b(\d{1,3})\s*(?:/|-)\s*(\d{1,3})\b", value)
    if not match:
        return ()
    equity, fixed_income = int(match.group(1)), int(match.group(2))
    if equity < 0 or fixed_income < 0 or equity + fixed_income != 100:
        return ()
    return equity, fixed_income


def parse_portfolio_exposure(value: str) -> tuple[float | None, float | None, str, bool]:
    """Extract stated equity and sector exposure from conversational portfolio context."""
    equity_match = re.search(
        r"\b(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s*(?:in\s+|is\s+)?equities?\b",
        value,
        flags=re.IGNORECASE,
    )
    sector_match = re.search(
        r"\b(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(that|(?:my|the)\s+equity(?:\s+sleeve)?)\s+(?:is|in)\s+([A-Za-z][A-Za-z &-]{1,30}?)(?=[,.;?!]|\s+(?:and|so|should|is\s+it)\b|$)",
        value,
        flags=re.IGNORECASE,
    )
    equity_pct = float(equity_match.group(1)) if equity_match else None
    sector_pct = float(sector_match.group(1)) if sector_match else None
    sector = sector_match.group(3).strip().lower() if sector_match else ""
    if equity_pct is not None and not 0 <= equity_pct <= 100:
        equity_pct = None
    if sector_pct is not None and not 0 <= sector_pct <= 100:
        sector_pct = None
    return equity_pct, sector_pct, sector, bool(sector_match)


def is_historical_trade_request(value: str) -> bool:
    """Recognize requests for dated, hypothetical historical trade examples."""
    lowered = value.lower()
    trade_terms = ("entered a trade", "entry examples", "trade examples", "would have bought", "paper trade")
    history_terms = ("past year", "last year", "historical", "in the past", "backtest")
    has_trade_language = any(term in lowered for term in trade_terms) or (
        "stop loss" in lowered and any(term in lowered for term in ("trade", "entry", "bought", "buy"))
    )
    return has_trade_language and any(term in lowered for term in history_terms)


def _month_date(value: str, *, end_of_month: bool) -> dt.date | None:
    clean = re.sub(r"\s+", " ", value.strip())
    for pattern in ("%B %Y", "%b %Y"):
        try:
            parsed = dt.datetime.strptime(clean.title(), pattern).date()
            day = calendar.monthrange(parsed.year, parsed.month)[1] if end_of_month else 1
            return parsed.replace(day=day)
        except ValueError:
            continue
    return None


def parse_custom_range(value: str, *, today: dt.date | None = None) -> tuple[str, str]:
    """Parse an optional ISO or month-name analysis range from a research brief."""
    prompt = value.strip()
    if not prompt:
        return "", ""
    today = today or dt.date.today()
    if re.search(r"\b(?:past|last|previous)\s+(?:one\s+)?year\b", prompt, flags=re.IGNORECASE):
        try:
            start = today.replace(year=today.year - 1)
        except ValueError:
            start = today.replace(year=today.year - 1, day=28)
        return start.isoformat(), today.isoformat()
    iso = re.search(
        r"(?:from|between|range\s*:?)?\s*(\d{4}-\d{2}-\d{2})\s+(?:to|through|until|and)\s+(\d{4}-\d{2}-\d{2}|today|now)",
        prompt,
        flags=re.IGNORECASE,
    )
    if iso:
        end = today.isoformat() if iso.group(2).lower() in {"today", "now"} else iso.group(2)
        return iso.group(1), end

    month = re.search(
        r"(?:from|between|range\s*:?)\s+([A-Za-z]{3,9}\s+\d{4})\s+(?:to|through|until|and)\s+([A-Za-z]{3,9}\s+\d{4}|today|now)",
        prompt,
        flags=re.IGNORECASE,
    )
    if month:
        start = _month_date(month.group(1), end_of_month=False)
        end = today if month.group(2).lower() in {"today", "now"} else _month_date(month.group(2), end_of_month=True)
        if start and end:
            return start.isoformat(), end.isoformat()

    since = re.search(
        r"\bsince\s+(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{4})",
        prompt,
        flags=re.IGNORECASE,
    )
    if since:
        raw = since.group(1)
        try:
            start = dt.date.fromisoformat(raw)
        except ValueError:
            start = _month_date(raw, end_of_month=False)
        if start:
            return start.isoformat(), today.isoformat()
    return "", ""


def parse_deep_analysis_prompt(value: str) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """Parse a technical-analysis brief, comparisons, and supported chart requests."""
    query, prompt = parse_research_prompt(value)
    if not prompt:
        return "", "", (), ()

    primary = query.upper().lstrip("$")
    symbols = []
    for match in _TICKER.finditer(prompt):
        symbol = match.group(1).upper()
        if symbol in _TICKER_STOPWORDS or symbol == primary or symbol in symbols:
            continue
        symbols.append(symbol)
    comparisons = tuple(symbols[:3]) or ("SPY",)

    lowered = prompt.lower()
    charts = ["price_trend", "stop_loss", "momentum", "relative_performance", "fibonacci"]
    if any(term in lowered for term in ("drawdown", "volatility", "risk chart", "risk profile")):
        charts.append("risk")
    if is_historical_trade_request(prompt):
        charts.append("historical_trades")
    return query, prompt, comparisons, tuple(charts)


def parse_comparison_prompt(value: str) -> tuple[str, str, str]:
    """Extract two security or fund queries from a conversational comparison brief."""
    prompt = value.strip()
    if not prompt:
        return "", "", ""
    first_line = next((line.strip() for line in prompt.splitlines() if line.strip()), prompt)
    versus = re.split(r"\s+(?:vs\.?|versus)\s+", first_line, maxsplit=1, flags=re.IGNORECASE)
    if len(versus) == 2:
        primary = re.sub(r"^compare\s+", "", versus[0], flags=re.IGNORECASE).strip(" $:,-")
        secondary = re.split(
            r"\s+(?:—|–|-)\s+|\s*\|\s*|:\s+|\s+(?=which\b|what\b|from\b|since\b)",
            versus[1],
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" $:,-")
        return primary, secondary, prompt

    compare = re.match(
        r"compare\s+(.+?)\s+(?:with|to|and)\s+(.+?)(?:\s+(?:—|–|-)\s+|\s*\|\s*|:\s+|[?.]|$)",
        first_line,
        flags=re.IGNORECASE,
    )
    if compare:
        return compare.group(1).strip(" $:,-"), compare.group(2).strip(" $:,-"), prompt

    symbols = []
    for match in _TICKER.finditer(prompt):
        symbol = match.group(1).upper()
        if symbol not in _TICKER_STOPWORDS and symbol not in symbols:
            symbols.append(symbol)
    if len(symbols) >= 2:
        return symbols[0], symbols[1], prompt
    return "", "", prompt