"""Helpers for the single-box research and revision workflow."""

from __future__ import annotations

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


def parse_research_prompt(value: str) -> tuple[str, str]:
    """Extract a resolvable security query while preserving the user's full brief."""
    prompt = value.strip()
    if not prompt:
        return "", ""

    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    first_line = lines[0]
    for separator in (" — ", " – ", " - ", " | ", ": "):
        if separator in first_line:
            candidate = first_line.split(separator, 1)[0].strip().lstrip("$")
            if candidate:
                return candidate, prompt

    if len(lines) > 1:
        return first_line.lstrip("$"), prompt

    company = re.search(
        r"\b(?:research|analyze|buy|sell|hold|add)\s+"
        r"(?:shares?\s+(?:of|in)\s+)?"
        r"([A-Z][A-Za-z0-9.&' -]{1,60}?)"
        r"(?=\s+(?:after|before|near|at|following|for|because)\b|[?!.,]|$)",
        first_line,
        flags=re.IGNORECASE,
    )
    if company:
        return company.group(1).strip(), prompt

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
    charts = ["price_trend", "momentum", "relative_performance"]
    if any(term in lowered for term in ("drawdown", "volatility", "risk chart", "risk profile")):
        charts.append("risk")
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
        secondary = re.split(r"\s+(?:—|–|-)\s+|\s*\|\s*|:\s+", versus[1], maxsplit=1)[0].strip(" $:,-")
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
