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

CRITERIA (v2) -- deliberately spread across five independent lenses so the
checklist cannot be swept by one strong theme (e.g. a hot momentum name):

1. Trend      -- price above both the 50-day and 200-day moving averages.
                 Needs sma200; a security too new to have one does not confirm.
2. Momentum   -- MACD above its signal line AND RSI(14) in [40, 75]: trending
                 with participation, but short of a blow-off top.
3. Relative strength -- total return over the same lookback beats the broad
                 benchmark (SPY) by at least 0 percentage points.
4. Quality    -- return on equity above 15%: the business earns a strong return
                 on the capital shareholders have in it.
5. Revisions  -- the consensus next-fiscal-year earnings estimate is higher than
                 it was 90 days ago; analysts are marking the business up.

WHY v2 DROPPED TWO CRITERIA (measured on 50 large-cap US equities, 2026-09-01):

* "Street conviction" (analyst mean target above price) passed **90%** of the
  time, with median implied upside +13.7% and a worst case of only -4.8%. A box
  that is ticked for nine names in ten cannot separate them, and the reason is
  structural: sell-side targets carry a documented upward bias. Worse, it
  correlated *negatively* with trend (-0.23) and momentum (-0.34) -- because
  targets lag price, it quietly rewarded stocks that had fallen, which is the
  opposite of what a reader sees in the words "street conviction".

* "Growth" (trailing revenue and earnings both positive) was the least
  computable criterion at 86% and is backward-looking. Revisions measure the
  same question -- is the business getting better? -- in the direction that
  actually moves prices, and estimate revisions are among the most consistently
  documented predictors of cross-sectional equity returns. Trailing growth is
  still reported in the fundamental section; it is simply no longer a checkbox.

Quality (ROE) earned its place on independence: against every other criterion
its correlation ran between -0.27 and +0.07, so it genuinely adds a lens rather
than restating the price-based ones. Measured pass rates for the v2 set are
32-71% with 94-100% evaluable, so each box discriminates.

Changing a threshold, adding, or removing a criterion is a policy change: bump
POLICY_VERSION and update this docstring in the same change.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "2.0"

_RSI_FLOOR = 40.0
_RSI_CEILING = 75.0
# Return on equity that marks a genuinely profitable business rather than one
# merely in the black. Measured pass rate 68% across the large-cap sample.
_ROE_FLOOR = 0.15
# Lookback for the estimate-revision comparison. Shorter windows are dominated
# by noise around a single earnings date.
_REVISION_LOOKBACK_DAYS = 90

# Plain-English, client-facing gloss for each criterion -- what it measures, not
# what this security scored.  Fixed per key, versioned with the policy above;
# `detail` on the criterion itself carries the security-specific evaluation.
_EXPLANATIONS = {
    "trend": "The stock's price relative to its own longer-run moving averages -- a measure of whether it sits in a sustained uptrend or downtrend.",
    "momentum": "The strength of short-term buying pressure: trending with participation, short of the overbought extreme where a pullback becomes likely.",
    "relative_strength": "The stock's total return against the S&P 500 over the same period -- outperformance, not simply a rising price.",
    "quality": "How much profit the company earns on the money shareholders have invested in it -- a high figure means the business itself is genuinely profitable, not just growing.",
    "revisions": "Whether analysts have raised or cut their earnings forecasts for next year over the past three months -- the direction expectations are moving, rather than where they stand.",
}


@dataclass(frozen=True, slots=True)
class ConvictionCriterion:
    key: str
    label: str
    passed: bool | None  # None = not confirmable from the available evidence
    detail: str
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.explanation:
            object.__setattr__(self, "explanation", _EXPLANATIONS.get(self.key, ""))

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


def _quality(return_on_equity: float | None) -> ConvictionCriterion:
    if return_on_equity is None:
        return ConvictionCriterion(
            "quality", "Quality", None, "Return on equity was not available from the data source."
        )
    passed = return_on_equity > _ROE_FLOOR
    detail = (
        f"Return on equity {return_on_equity:+.1%} is "
        f"{'above' if passed else 'not above'} the {_ROE_FLOOR:.0%} threshold."
    )
    return ConvictionCriterion("quality", "Quality", passed, detail)


def _revisions(
    eps_estimate_now: float | None,
    eps_estimate_prior: float | None,
) -> ConvictionCriterion:
    # A prior estimate at or below zero has no meaningful percentage change, and
    # a loss-making forecast turning less negative is not the same signal, so it
    # is reported unconfirmed rather than forced into a direction.
    if eps_estimate_now is None or eps_estimate_prior is None or eps_estimate_prior <= 0:
        return ConvictionCriterion(
            "revisions",
            "Revisions",
            None,
            f"A consensus earnings estimate from {_REVISION_LOOKBACK_DAYS} days ago was not available to compare against.",
        )
    passed = eps_estimate_now > eps_estimate_prior
    change = eps_estimate_now / eps_estimate_prior - 1.0
    detail = (
        f"Next-year consensus EPS ${eps_estimate_now:,.2f} versus ${eps_estimate_prior:,.2f} "
        f"{_REVISION_LOOKBACK_DAYS} days ago ({change:+.1%}) -- estimates "
        f"{'raised' if passed else 'cut' if change < 0 else 'unchanged'}."
    )
    return ConvictionCriterion("revisions", "Revisions", passed, detail)


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
    return_on_equity: float | None,
    eps_estimate_now: float | None,
    eps_estimate_prior: float | None,
    benchmark: str = "SPY",
) -> ConvictionChecklist:
    """Evaluate all five criteria from already-computed evidence; never fetches anything itself."""
    return ConvictionChecklist(
        (
            _trend(price, sma50, sma200),
            _momentum(rsi14, macd, macd_signal),
            _relative_strength(security_return_pct, benchmark_return_pct, benchmark),
            _quality(return_on_equity),
            _revisions(eps_estimate_now, eps_estimate_prior),
        )
    )
