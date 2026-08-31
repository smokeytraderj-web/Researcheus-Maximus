"""Append-only log of the calls this tool has made, for scoring them later.

A deliberate, narrow exception to the delete-everything session rule: it records
what was called and when, and nothing else.  No question text, no position size,
no purchase price, no client detail, no research content -- so a stale log cannot
leak anything the privacy rules protect.  One row per finalised report, CSV so it
opens directly in Excel.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.models import ResearchRequest, ResearchResult

CALL_LOG_FILENAME = "researcheus_call_log.csv"

_COLUMNS = (
    "logged_at",
    "ticker",
    "company",
    "horizon",
    "rating",
    "confidence",
    "price",
    "technical_rating",
    "fundamental_rating",
)


def append_call(directory: Path, result: ResearchResult, request: ResearchRequest) -> Path:
    """Append one finalised call, creating the file with a header if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / CALL_LOG_FILENAME
    is_new = not destination.exists()
    row = {
        "logged_at": result.as_of,
        "ticker": result.identity.ticker,
        "company": result.identity.company_name,
        "horizon": request.horizon.value,
        "rating": result.lead_rating.value,
        "confidence": result.confidence.value,
        "price": f"{result.current_price:.2f}",
        "technical_rating": result.technical.rating.value,
        "fundamental_rating": result.fundamental.rating.value,
    }
    with destination.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    return destination
