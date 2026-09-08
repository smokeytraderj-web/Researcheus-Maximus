"""Portfolio intake and a transparent roll-up of RM's security ratings.

Position weights stay distinct from conviction. Missing evidence is never
silently dropped and a weighted opinion is not an expected return or risk score.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass

from core.models import Rating

MAX_HOLDINGS = 50
WEIGHTINGS = {"weight", "value", "shares", "equal"}
TICKER = re.compile(r"^[A-Z][A-Z0-9.^=-]{0,15}$")
RATING_SCORES = {
    Rating.STRONG_BUY.value: 3, Rating.BUY.value: 2, Rating.ADD.value: 1,
    Rating.HOLD.value: 0, Rating.REDUCE.value: -1, Rating.SELL.value: -2,
    Rating.AVOID.value: -3,
}
METHODOLOGY = (
    "Portfolio view v1.0: allocation-weighted RM ratings, scored Strong Buy +3, "
    "Buy +2, Add +1, Hold 0, Reduce −1, Sell −2 and Avoid −3. The invested "
    "portion is Constructive at +1 or above, Defensive at −1 or below, and "
    "Mixed between them. Cash is shown separately and has no security rating. "
    "All securities must have usable research before an overall view is issued. "
    "Concentration is flagged at a 25% single-security weight or 60% in the "
    "largest three securities. These are review thresholds, not suitability "
    "limits. This is an opinion summary, not a forecast, correlation analysis "
    "or a portfolio risk model. Weights and market values use USD only."
)


@dataclass(frozen=True)
class Holding:
    ticker: str
    amount: float = 1


def validate_holdings(rows: list[dict], weighting: str) -> tuple[Holding, ...]:
    if weighting not in WEIGHTINGS:
        raise ValueError("Choose weights, USD market values, shares, or equal weighting.")
    if not 1 <= len(rows) <= MAX_HOLDINGS:
        raise ValueError(f"Enter between 1 and {MAX_HOLDINGS} positions.")
    holdings = []
    seen = set()
    for index, row in enumerate(rows, 1):
        ticker = str(row.get("ticker", "")).strip().upper()
        if not TICKER.fullmatch(ticker):
            raise ValueError(f"Row {index}: enter an exact listed ticker, without account or client details.")
        if ticker in seen:
            raise ValueError(f"{ticker} appears more than once. Combine its lots into one position.")
        seen.add(ticker)
        raw_amount = row.get("amount", 1 if weighting == "equal" else None)
        if isinstance(raw_amount, bool):
            raise ValueError(f"Row {index}: enter a positive numeric amount.")
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {index}: enter a positive numeric amount.") from exc
        if not math.isfinite(amount) or not 0 < amount <= 1e12:
            raise ValueError(f"Row {index}: amounts must be finite and greater than zero (maximum 1 trillion).")
        if weighting == "equal" and amount != 1:
            raise ValueError("Equal weighting accepts tickers only. Remove amounts or select their weighting method.")
        if ticker == "CASH" and weighting in {"equal", "shares"}:
            raise ValueError("Include CASH using weight (%) or USD market value.")
        holdings.append(Holding(ticker, amount))
    if weighting == "weight" and not math.isclose(sum(h.amount for h in holdings), 100, abs_tol=0.01):
        total = sum(h.amount for h in holdings)
        raise ValueError(f"Weights total {total:,.2f}%. They must total 100%; add CASH for uninvested cash.")
    return tuple(holdings)


def parse_holdings(text: str, weighting: str) -> tuple[Holding, ...]:
    """Accept narrowly scoped CSV/TSV or pasted rows; never guess a weighting."""
    if len(text) > 20_000:
        raise ValueError("The holdings text is too large. Include only tickers and amounts.")
    clean = text.lstrip("\ufeff").strip()
    if not clean:
        raise ValueError("Paste your holdings first.")
    delimiter = "\t" if "\t" in clean else "," if "," in clean else None
    if delimiter:
        try:
            rows = list(csv.reader(io.StringIO(clean), delimiter=delimiter, strict=True))
        except csv.Error as exc:
            raise ValueError("The CSV could not be read. Check its quotes and columns.") from exc
    else:
        rows = [line.split() for line in clean.splitlines()]
    rows = [[cell.strip() for cell in row] for row in rows if any(cell.strip() for cell in row)]
    # A comma-separated ticker list is allowed only when equal weighting was chosen.
    if weighting == "equal" and len(rows) == 1 and all(TICKER.fullmatch(c.upper()) for c in rows[0]):
        rows = [[c] for c in rows[0]]
    headers = {
        "weight": {"weight", "weight (%)", "weight%", "allocation", "allocation (%)"},
        "value": {"value", "market value", "market value (usd)", "value (usd)"},
        "shares": {"shares", "quantity", "qty"},
        "equal": set(),
    }
    if rows and rows[0][0].casefold() in {"ticker", "symbol"}:
        header = rows.pop(0)
        expected = 1 if weighting == "equal" else 2
        if len(header) != expected or (expected == 2 and header[1].casefold() not in headers.get(weighting, set())):
            raise ValueError("The column header does not match the selected weighting. Use Ticker and the selected amount only.")
    parsed = []
    for index, row in enumerate(rows, 1):
        if len(row) != (1 if weighting == "equal" else 2):
            raise ValueError(f"Row {index}: use only a ticker" + ("." if weighting == "equal" else " and its amount."))
        value = "1" if weighting == "equal" else row[1]
        # Unit markers must match the choice; a misplaced % must not become shares.
        if "%" in value and weighting != "weight" or "$" in value and weighting != "value":
            raise ValueError(f"Row {index}: the amount's unit does not match the weighting method.")
        value = value.removesuffix("%").removeprefix("$").replace(",", "").strip()
        parsed.append({"ticker": row[0], "amount": value})
    return validate_holdings(parsed, weighting)


def summarize(positions: list[dict], weighting: str) -> dict:
    """Return weights and a conservative assessment, including partial runs."""
    weights = None
    total_value = None
    if weighting == "shares":
        if all(p["status"] == "ready" and p.get("currency") == "USD"
               and math.isfinite(p.get("price", 0)) and p.get("price", 0) > 0 for p in positions):
            values = [p["amount"] * p["price"] for p in positions]
            total_value = sum(values)
            weights = [100 * value / total_value for value in values]
    else:
        total = sum(p["amount"] for p in positions)
        weights = [100 * p["amount"] / total for p in positions]
        if weighting == "value":
            total_value = total
    weighted_positions = [dict(p, weight=weights[i] if weights else None) for i, p in enumerate(positions)]
    securities = [p for p in weighted_positions if p["ticker"] != "CASH"]
    covered = [p for p in securities if p["status"] == "ready" and p.get("rating") in RATING_SCORES]
    cash_weight = sum(p["weight"] or 0 for p in weighted_positions if p["ticker"] == "CASH") if weights else None
    coverage = sum(p["weight"] for p in weighted_positions if p["status"] == "ready") if weights else None
    concentration = sorted(securities, key=lambda p: p["weight"] or 0, reverse=True)
    largest = concentration[0] if concentration and weights else None
    top_three = sum(p["weight"] for p in concentration[:3]) if weights else None
    complete = len(covered) == len(securities) and weights is not None
    score = None
    label = "Awaiting research"
    if complete and covered:
        invested_weight = sum(p["weight"] for p in covered)
        score = sum(p["weight"] * RATING_SCORES[p["rating"]] for p in covered) / invested_weight
        label = "Constructive" if score >= 1 - 1e-10 else "Defensive" if score <= -1 + 1e-10 else "Mixed"
    elif complete:
        label = "Cash only"
    elif any(p["status"] == "failed" for p in positions):
        label = "Incomplete research"
    elif any(p["status"] == "running" for p in positions):
        label = "Researching"
    positive = sum(p["weight"] for p in covered if RATING_SCORES[p["rating"]] > 0) if weights else None
    negative = sum(p["weight"] for p in covered if RATING_SCORES[p["rating"]] < 0) if weights else None
    neutral = sum(p["weight"] for p in covered if RATING_SCORES[p["rating"]] == 0) if weights else None
    flags = []
    if largest and largest["weight"] >= 25:
        flags.append(f"{largest['ticker']} is {largest['weight']:.1f}% of the portfolio; review single-position concentration.")
    if top_three is not None and top_three >= 60 and len(securities) > 1:
        flags.append(f"The largest three securities represent {top_three:.1f}% of the portfolio.")
    if complete and covered:
        narrative = f"{positive:.1f}% of the portfolio has constructive RM ratings, {neutral:.1f}% is Hold and {negative:.1f}% is rated Reduce, Sell or Avoid."
        if cash_weight:
            narrative += f" Cash is {cash_weight:.1f}%."
        if flags:
            narrative += " " + flags[0]
    elif complete:
        narrative = "The portfolio is entirely cash. There are no security ratings to aggregate."
    else:
        narrative = f"{len(covered)} of {len(securities)} securities have usable research. The overall view will appear when every holding is covered."
        if weights is None:
            narrative += " Allocation weights need valid USD prices for every share-based position."
    return {
        "rating": label, "score": score, "summary": narrative, "complete": complete,
        "coverage_pct": coverage, "researched_count": len(covered), "security_count": len(securities),
        "cash_pct": cash_weight, "total_value": total_value, "largest":
        {"ticker": largest["ticker"], "weight": largest["weight"]} if largest else None,
        "top_three_pct": top_three, "concentration": "Review concentration" if flags else "No threshold flagged" if weights else "Pending prices",
        "flags": flags, "positive_pct": positive, "neutral_pct": neutral, "negative_pct": negative,
        "positions": weighted_positions, "methodology": METHODOLOGY,
    }
