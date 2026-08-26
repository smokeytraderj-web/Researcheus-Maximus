"""Deterministic demo provider for end-to-end UI and PDF validation.

This provider intentionally produces synthetic evidence. It must never be
presented as live market research.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from core.models import (
    Confidence,
    Rating,
    ResearchRequest,
    ResearchResult,
    SecurityIdentity,
    SourceRecord,
    SpecialistFinding,
    Strategy,
)


KNOWN = {
    "AAPL": ("Apple Inc.", "AAPL", "NASDAQ"),
    "APPLE": ("Apple Inc.", "AAPL", "NASDAQ"),
    "AXON": ("Axon Enterprise, Inc.", "AXON", "NASDAQ"),
    "WMT": ("Walmart Inc.", "WMT", "NYSE"),
    "WALMART": ("Walmart Inc.", "WMT", "NYSE"),
    "MSFT": ("Microsoft Corporation", "MSFT", "NASDAQ"),
    "MICROSOFT": ("Microsoft Corporation", "MSFT", "NASDAQ"),
}


class DemoResearchProvider:
    """Return stable synthetic content without calling external services."""

    def run(self, request: ResearchRequest, workspace=None) -> ResearchResult:
        request.validate()
        key = request.query.strip().upper()
        company, ticker, exchange = KNOWN.get(
            key, (request.query.strip().title(), key.replace(" ", "")[:8], "Unconfirmed")
        )
        digest = hashlib.sha256(ticker.encode("utf-8")).digest()
        price = round(40 + int.from_bytes(digest[:2], "big") % 360 + digest[2] / 255, 2)
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
        result = ResearchResult(
            identity=SecurityIdentity(company, ticker, exchange, "USD"),
            horizon=request.horizon,
            as_of=now,
            current_price=price,
            technical=SpecialistFinding(
                Rating.ADD,
                "The synthetic multi-timeframe setup is constructive but requires confirmation.",
                (
                    "Price is modeled above a rising intermediate trend average.",
                    "Momentum is positive without an extreme synthetic reading.",
                    "Volume confirmation remains incomplete in demo mode.",
                ),
            ),
            fundamental=SpecialistFinding(
                Rating.HOLD,
                "The synthetic business profile is stable, while valuation leaves limited margin for error.",
                (
                    "Modeled earnings direction is positive.",
                    "Modeled valuation is above its illustrative historical range.",
                    "No live SEC or YCharts facts are used in demo mode.",
                ),
            ),
            sentiment="Neutral to constructive in synthetic demo data; no public posts were retrieved.",
            lead_rating=Rating.ADD,
            confidence=Confidence.LOW,
            executive_summary=(
                f"{company} receives an illustrative Add rating for the {request.horizon.value.lower()} horizon. "
                "The demo technical setup is constructive, while the demo fundamental view is more balanced. "
                "This result validates the application workflow and is not live investment research."
            ),
            key_metrics=(
                ("Illustrative current price", f"${price:,.2f}"),
                ("Technical setup", "Bullish"),
                ("Fundamental outlook", "Balanced"),
                ("Overall confidence", "Low — demo evidence"),
            ),
            strategies=(
                Strategy(
                    "Confirmation entry",
                    "After a confirmed move above modeled resistance",
                    "Price and volume confirm together",
                    "Close back below the breakout area",
                    "False breakout and broad-market reversal",
                ),
                Strategy(
                    "Pullback monitor",
                    "Near modeled trend support",
                    "Support holds and momentum turns higher",
                    "Sustained break below modeled support",
                    "Momentum deterioration",
                ),
            ),
            risks=(
                "All values and signals in this build are synthetic.",
                "Live earnings, valuation, chart, and event risks have not been retrieved.",
            ),
            catalysts=("Live catalyst research is not connected in demo mode.",),
            change_conditions=(
                "A live-source conflict or materially different technical structure.",
                "New official filings, earnings results, or guidance.",
            ),
            sources=(
                SourceRecord("Researcheus Demo Provider", "synthetic://demo", now, "Workflow validation only"),
            ),
            provider_label="Deterministic demo provider",
            limitations=("Synthetic values only; no live research sources were contacted.",),
            demo_mode=True,
        )
        result.validate()
        return result
