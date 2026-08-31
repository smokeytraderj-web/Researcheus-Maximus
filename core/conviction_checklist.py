"""The five-point Conviction Checklist: a versioned policy for the checkboxes.

This is supplementary evidence, not a rating. It never renames, replaces, or
overrides the seven-label Rating System (Strong Buy .. Avoid) or the Lead
Analyst's synthesis -- it is one more transparent, deterministic view of the
same evidence, shown alongside the rating so a reader can see at a glance how
many of five well-established, independent criteria the current picture
actually satisfies.

Each criterion is deterministic and threshold-based -- no model judgment, no
LLM text becomes an input here. A criterion that cannot be evaluated from the
available evidence is reported as not-confirmed (with the reason stated), not
guessed or silently skipped, and its report row is what states that gap.

CRITERIA (v1) -- deliberately spread across five independent lenses so the
checklist cannot be swept by one strong theme (e.g. a hot momentum name):

1. Trend      -- price above both the 50-day and 200-day moving averages.
                 Needs sma200; a security too new to have one does not confirm.
2. Momentum   -- MACD above its signal line AND RSI(14) in [40, 75]: trending
                 with participation, but short of a blow-off top.
3. Relative strength -- total return over the same lookback beats the broad
                 benchmark (SPY) by at least 0 percentage points.
4. Growth     -- both revenue growth and earnings growth (most recent
                 year-over-year, as reported by the data source) are positive.
5. Street conviction -- the analyst mean price target sits above the current
                 price (positive implied upside).

Changing a threshold, adding, or removing a criterion is a policy change: bump
POLICY_VERSION and update this docstring in the same change.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "1.0"

_RSI_FLOOR = 40.0
_RSI_CEILING = 75.0


@dataclass(frozen=True, slots=True)
class ConvictionCriterion:
    key: str
    label: str
    passed: bool | None  # None = not confirmable from the available evidence
    detail: str

    @property
    def status(self) -> str:
        if self.passed is None:
            return "unconfirmed"
        return "pass" if self.passed else "fail"


@dataclass(frozen=True, slots=True)
class ConvictionChecklist:
    criteria: tuple[ConvictionCriterion, ...]
    policy_version: str = POLICY_VERSION

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.criteria if item.passed is True)

    @property
    def total_count(self) -> int:
        return len(self.criteria)

    @property
    def unconfirmed_count(self) -> int:
        return sum(1 for item in self.criteria if item.passed is None)

    @property
    def is_perfect(self) -> bool:
        return self.total_count > 0 and self.passed_count == self.total_count


def _trend(price: float, sma50: float, sma200: float | None) -> ConvictionCriterion:
    if sma200 is None:
        return ConvictionCriterion(
            "trend", "Trend", None, "A 200-day average is not yet available for this security."
        )
    passed = price > sma50 and price > sma200
    detail = (
        f"Price ${price:,.2f} is above both the 50-day (${sma50:,.2f}) and 200-day (${sma200:,.2f}) averages."
        if passed
        else f"Price ${price:,.2f} is not above both the 50-day (${sma50:,.2f}) and 200-day (${sma200:,.2f}) averages."
    )
    return ConvictionCriterion("trend", "Trend", passed, detail)


def _momentum(rsi14: float, macd: float, macd_signal: float) -> ConvictionCriterion:
    macd_bullish = macd > macd_signal
    rsi_healthy = _RSI_FLOOR <= rsi14 <= _RSI_CEILING
    passed = macd_bullish and rsi_healthy
    detail = (
        f"MACD is above its signal ({macd:.2f} vs {macd_signal:.2f}) and RSI is {rsi14:.1f}, "
        f"inside the {_RSI_FLOOR:.0f}-{_RSI_CEILING:.0f} constructive range."
        if passed
        else f"MACD {macd:.2f} vs signal {macd_signal:.2f}; RSI {rsi14:.1f} "
        f"({'below' if rsi14 < _RSI_FLOOR else 'above' if rsi14 > _RSI_CEILING else 'inside'} the "
        f"{_RSI_FLOOR:.0f}-{_RSI_CEILING:.0f} range) -- momentum does not confirm both conditions."
    )
    return ConvictionCriterion("momentum", "Momentum", passed, detail)


def _relative_strength(
    security_return_pct: float | None, benchmark_return_pct: float | None, benchmark: str
) -> ConvictionCriterion:
    if security_return_pct is None or benchmark_return_pct is None:
        return ConvictionCriterion(
            "relative_strength",
            "Relative strength",
            None,
            f"A comparable return series against {benchmark} was not available.",
        )
    passed = security_return_pct >= benchmark_return_pct
    detail = (
        f"Returned {security_return_pct:+.1%} versus {benchmark}'s {benchmark_return_pct:+.1%} over the same dates."
    )
    return ConvictionCriterion("relative_strength", "Relative strength", passed, detail)


def _growth(revenue_growth_pct: float | None, earnings_growth_pct: float | None) -> ConvictionCriterion:
    if revenue_growth_pct is None or earnings_growth_pct is None:
        return ConvictionCriterion(
            "growth", "Growth", None, "Revenue and/or earnings growth were not both available from the data source."
        )
    passed = revenue_growth_pct > 0 and earnings_growth_pct > 0
    detail = (
        f"Revenue growth {revenue_growth_pct:+.1%} and earnings growth {earnings_growth_pct:+.1%}, "
        f"both {'positive' if passed else 'not both positive'}."
    )
    return ConvictionCriterion("growth", "Growth", passed, detail)


def _street_conviction(current_price: float, analyst_target: float | None) -> ConvictionCriterion:
    if analyst_target is None or analyst_target <= 0:
        return ConvictionCriterion(
            "street_conviction", "Street conviction", None, "No analyst mean price target was available."
        )
    passed = analyst_target > current_price
    upside = analyst_target / current_price - 1.0
    detail = f"Analyst mean target ${analyst_target:,.2f} implies {upside:+.1%} versus the current price."
    return ConvictionCriterion("street_conviction", "Street conviction", passed, detail)


def evaluate_conviction_checklist(
    *,
    price: float,
    sma50: float,
    sma200: float | None,
    rsi14: float,
    macd: float,
    macd_signal: float,
    security_return_pct: float | None,
    benchmark_return_pct: float | None,
    revenue_growth_pct: float | None,
    earnings_growth_pct: float | None,
    analyst_target: float | None,
    benchmark: str = "SPY",
) -> ConvictionChecklist:
    """Evaluate all five criteria from already-computed evidence; never fetches anything itself."""
    return ConvictionChecklist(
        (
            _trend(price, sma50, sma200),
            _momentum(rsi14, macd, macd_signal),
            _relative_strength(security_return_pct, benchmark_return_pct, benchmark),
            _growth(revenue_growth_pct, earnings_growth_pct),
            _street_conviction(price, analyst_target),
        )
    )
