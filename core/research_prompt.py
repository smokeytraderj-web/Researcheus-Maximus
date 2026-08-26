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
    "PLEASE",
    "RESEARCH",
    "SELL",
    "SHOULD",
    "THE",
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
    if len(lines) > 1:
        return first_line.lstrip("$"), prompt

    for separator in (" — ", " – ", " | ", ": "):
        if separator in first_line:
            candidate = first_line.split(separator, 1)[0].strip().lstrip("$")
            if candidate:
                return candidate, prompt

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
