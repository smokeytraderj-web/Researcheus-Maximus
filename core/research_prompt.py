"""Helpers for the single-box research and revision workflow."""

from __future__ import annotations

import calendar
import datetime as dt
import re


_TICKER = re.compile(r"(?<![A-Za-z0-9])\$?([A-Z]{1,5}(?:[.-][A-Z])?)(?![A-Za-z0-9])")

# Conversational words that end a security candidate. Without a broad stop-word
# list, the non-greedy captures below keep eating trailing prose (e.g. "is this
# a buying opportunity") instead of stopping at the ticker/company name itself.
_QUERY_STOP_WORDS = (
    "and", "to", "from", "since", "with", "as", "is", "are", "was", "given",
    "right", "now", "today", "currently", "still", "buying", "selling",
    "holding", "adding", "worth", "good", "bad", "great", "opportunity",
    "opportunities", "position", "positions", "entry", "chart", "charts",
    "analysis", "analyze", "after", "before", "near", "at", "following",
    "for", "because",
)

# Shared right-hand boundary for the "buy/sell/hold X", "analysis of X",
# "what about X", and "evaluate X" patterns below.
_QUERY_STOP_BOUNDARY = r"(?=\s+(?:" + "|".join(_QUERY_STOP_WORDS) + r")\b|[?!.,]|$)"

# Filler words the verb-prefix regex can latch onto when the verb follows the
# ticker rather than precedes it, e.g. "a good opportunity to buy now".
_VERB_ADJACENT_FILLERS = {"now", "today", "here", "again", "later", "then", "it", "that", "this", "one", "soon"}
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


def _is_security_candidate(value: str) -> bool:
    """Whether a verb-prefix capture is plausibly a security rather than prose.

    "buy", "sell" and "hold" are also nouns, so "Is AAPL a buy for a medium term
    hold?" fires the verb pattern on "a buy" and captures the prose after it --
    "for a medium term hold" -- while the real ticker sits earlier in the
    sentence. The tell is that such a capture opens with a word that would have
    ended it had it appeared anywhere else, so a candidate is rejected when its
    first word is a stop word. Rejecting sends the caller on to the ticker scan,
    which finds the security the user actually named.

    Deliberately not a capitalisation test: "should i buy apple" is a real
    request for Apple, and requiring a capital would throw it away.
    """
    candidate = value.strip().lower()
    if not candidate or candidate in _VERB_ADJACENT_FILLERS:
        return False
    return candidate.split()[0] not in _QUERY_STOP_WORDS


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
        + _QUERY_STOP_BOUNDARY,
        first_line,
        flags=re.IGNORECASE,
    )
    # "Is TSLA a good opportunity to buy now" puts the verb after the ticker, so
    # the pattern above latches onto a filler word ("now") following the verb
    # instead. Skip a filler-word match so the ticker scan below can find the
    # real security earlier in the sentence.
    if company and _is_security_candidate(company.group(1)):
        candidate = re.sub(r"\s+position$", "", company.group(1).strip(), flags=re.IGNORECASE)
        return _clean_security_candidate(candidate), prompt

    open_ended_company_patterns = (
        r"\b(?:full|complete|detailed)?\s*analysis\s+of\s+([A-Z][A-Za-z0-9.&' -]{1,60}?)" + _QUERY_STOP_BOUNDARY,
        r"\bwhat\s+about\s+(?:my\s+)?([A-Z][A-Za-z0-9.&' -]{1,60}?)" + _QUERY_STOP_BOUNDARY,
        r"\bevaluate\s+(?:my\s+)?([A-Z][A-Za-z0-9.&' -]{1,60}?)" + _QUERY_STOP_BOUNDARY,
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


# Horizon wording, checked longest-phrase-first so "long term" is not matched by a
# looser "term" rule. Only an explicit statement changes the horizon; silence keeps
# the All Horizons default rather than guessing a timeframe the user never gave.
_HORIZON_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "All Horizons",
        ("all horizons", "every horizon", "all time frames", "all timeframes", "short medium and long"),
    ),
    (
        "Long Term",
        (
            "long term", "long-term", "longterm", "buy and hold", "buy-and-hold", "hold forever",
            "retirement", "for my kids", "next decade", "ten years", "10 years", "five years",
            "5 years", "several years", "for years", "multi-year", "multiyear", "lifetime",
        ),
    ),
    (
        "Medium Term",
        (
            "medium term", "medium-term", "mediumterm", "intermediate term", "intermediate-term",
            "next few months", "next couple of months", "next couple months", "coming months",
            "next quarter", "this quarter", "six months", "6 months", "next year", "12 months",
            "rest of the year", "remainder of the year",
        ),
    ),
    (
        "Short Term",
        (
            "short term", "short-term", "shortterm", "near term", "near-term", "swing trade",
            "swing trading", "day trade", "day trading", "next few days", "next couple of days",
            "next couple days", "next week", "next two weeks", "coming weeks", "next few weeks",
            "this week", "quick trade", "quick flip", "few sessions", "intraday",
        ),
    ),
)


def parse_horizon(value: str) -> str:
    """The analysis horizon the user actually stated, or '' when they stated none.

    The horizon changes lookbacks, signal emphasis and weighting, so inferring one
    that was never asked for would quietly change the answer.  Blank means the
    caller should keep its own default.
    """
    lowered = value.lower()
    for horizon, phrases in _HORIZON_PHRASES:
        if any(phrase in lowered for phrase in phrases):
            return horizon
    return ""


def classify_research_intent(value: str) -> str:
    """Classify the decision being asked without changing the user's wording."""
    lowered = value.lower()
    # Checked before the broader buy/sell wording below, because these questions
    if parse_portfolio_allocation(value):
        return "portfolio_fit"
    if "portfolio" in lowered and (
        re.search(r"\b\d{1,3}(?:\.\d+)?\s*(?:%|percent)\b", lowered)
        or any(term in lowered for term in ("allocation", "concentration", "exposure", "equities", "equity sleeve"))
    ):
        return "portfolio_context"
    if is_historical_trade_request(value):
        return "historical_trade_examples"
    # These sit above the broad buy/sell wording because such questions usually
    # arrive wrapped in it ("should I buy, and where do I put a stop?"), but below
    # the portfolio and back-test checks, which describe a whole workflow rather
    # than one question -- a back-test prompt may mention stops in passing.
    if any(
        term in lowered
        for term in ("stop loss", "stop-loss", "where do i put my stop", "where should i set a stop", "invalidation")
    ):
        return "stop_loss"
    if any(
        term in lowered
        for term in (
            "option", "options", "call spread", "put spread", "covered call", "cash-secured put",
            "hedge", "hedging", "protect my position", "collar",
        )
    ):
        return "options"
    if any(
        term in lowered
        for term in (
            "overvalued", "undervalued", "over valued", "under valued", "too expensive",
            "fairly valued", "fair value", "cheap here", "expensive here", "valuation",
        )
    ):
        return "valuation"
    if any(
        term in lowered
        for term in (
            "buy now or wait", "wait for a pullback", "should i wait", "is now a good time",
            "better entry", "wait for a dip", "chase it", "chasing",
        )
    ):
        return "timing"
    if any(
        term in lowered
        for term in ("dividend", "yield", "income", "payout", "distribution")
    ):
        return "income"
    if any(
        term in lowered
        for term in ("before earnings", "after earnings", "into earnings", "earnings report", "next earnings")
    ):
        return "earnings"
    if any(term in lowered for term in ("should i sell", "time to sell", "exit", "reduce my position")):
        return "sell"
    if any(
        term in lowered
        for term in (
            "should i buy",
            "good opportunity to buy",
            "good opportunity",
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
