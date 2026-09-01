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

v2.1 widened coverage without moving a threshold. Revisions now judges the
*direction* of the estimate, which is meaningful whether or not the company is
expected to earn money: requiring a positive base had silently excluded every
loss-making issuer -- growth names and turnarounds among them -- from ever
confirming the criterion. A percentage is still quoted only off a positive base,
where it means something. The lookback also falls back through 60, 30 and 7 days
because the 90-day column is not always populated (this feed writes an absent
estimate as 0.0, which must not be read as a forecast of breaking even), and the
report states which window it actually used. Quality falls back to net income
over shareholders' equity when the summary field is absent. For a fund both
criteria report "not applicable" rather than "not available", because they
describe company earnings a fund does not have.

Quality (ROE) earned its place on independence: against every other criterion
its correlation ran between -0.27 and +0.07, so it genuinely adds a lens rather
than restating the price-based ones. Measured pass rates for the v2 set are
32-71% with 94-100% evaluable, so each box discriminates.

Changing a threshold, adding, or removing a criterion is a policy change: bump
POLICY_VERSION and update this docstring in the same change.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "2.1"

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


# How each criterion reads in prose, confirmed and not, for the narrative below.
# Phrased as findings rather than labels, so the paragraph reads like an analyst
# wrote it instead of a checklist being recited back.
_NARRATIVE_PHRASES = {
    "trend": (
        "price is holding above both its 50-day and 200-day averages",
        "price has lost one or both of its long-run averages",
    ),
    "momentum": (
        "momentum is participating without being stretched",
        "momentum is not confirming the move",
    ),
    "relative_strength": (
        "it has outpaced the S&P 500 over the same window",
        "it has lagged the S&P 500 over the same window",
    ),
    "quality": (
        "the business earns a strong return on shareholder capital",
        "returns on shareholder capital fall short of the bar",
    ),
    "revisions": (
        "analysts have been raising next-year earnings estimates",
        "analysts have been cutting next-year earnings estimates",
    ),
}


def _join(parts: list[str]) -> str:
    """Oxford-comma list: 'a', 'a and b', 'a, b, and c'."""
    if len(parts) <= 1:
        return parts[0] if parts else ""
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def checklist_narrative(checklist: "ConvictionChecklist", *, rating: str = "") -> str:
    """One readable paragraph explaining how the five checks combine.

    Assembled deterministically from the criteria themselves -- no model text is
    an input, exactly as for the boxes -- so the prose can never drift from the
    score it is describing. It names what confirmed, what did not, and what could
    not be judged, and closes on what the dissent means for the rating, which is
    the part a reader actually wants and the boxes alone cannot say.
    """
    if checklist is None or not checklist.criteria:
        return ""
    confirmed, failed, unknown, inapplicable = [], [], [], []
    for item in checklist.criteria:
        phrases = _NARRATIVE_PHRASES.get(item.key)
        if not phrases:
            continue
        if item.passed is True:
            confirmed.append(phrases[0])
        elif item.passed is False:
            failed.append(phrases[1])
        # "Does not apply" and "could not be retrieved" are different findings,
        # and telling a reader a fund's earnings data was unavailable would
        # invite them to retry for something that does not exist.
        elif item.detail.startswith("Not applicable"):
            inapplicable.append(item.label.lower())
        else:
            unknown.append(item.label.lower())

    judged = checklist.total_count - checklist.unconfirmed_count
    sentences = [
        f"{checklist.passed_count} of the {judged} checks that could be judged confirm."
        if checklist.unconfirmed_count
        else f"{checklist.passed_count} of the {checklist.total_count} checks confirm."
    ]
    if confirmed:
        sentences.append(f"In favour: {_join(confirmed)}.")
    if failed:
        lead = "Against" if confirmed else "The evidence against"
        sentences.append(f"{lead}: {_join(failed)}.")
    if inapplicable:
        sentences.append(
            f"{_join([u.capitalize() for u in inapplicable])} "
            f"{'do' if len(inapplicable) > 1 else 'does'} not apply to a fund, "
            f"which has no company earnings of its own."
        )
    if unknown:
        sentences.append(
            f"{_join([u.capitalize() for u in unknown])} could not be judged from the available evidence, "
            "so {} counted neither way.".format("they were" if len(unknown) > 1 else "it was")
        )

    # What the balance means. Stated as weight of evidence, never as a promise.
    if rating:
        if not failed and confirmed:
            sentences.append(f"Nothing in the checklist argues against the {rating} view.")
        elif failed and confirmed:
            sentences.append(
                f"The {rating} view rests on the balance of these, not on agreement: "
                f"{'the dissent is' if len(failed) == 1 else 'the dissents are'} what would need to change first."
            )
        elif failed and not confirmed:
            sentences.append(f"The checklist offers no support for a constructive view here, which the {rating} rating reflects.")
    return " ".join(sentences)


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


def _quality(return_on_equity: float | None, not_applicable: str = "") -> ConvictionCriterion:
    if not_applicable:
        return ConvictionCriterion("quality", "Quality", None, not_applicable)
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


def _money(value: float) -> str:
    """A signed dollar figure, so a negative estimate reads as -$2.00."""
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def _revisions(
    eps_estimate_now: float | None,
    eps_estimate_prior: float | None,
    window_days: int = _REVISION_LOOKBACK_DAYS,
    not_applicable: str = "",
) -> ConvictionCriterion:
    if not_applicable:
        return ConvictionCriterion("revisions", "Revisions", None, not_applicable)
    if eps_estimate_now is None or eps_estimate_prior is None:
        return ConvictionCriterion(
            "revisions",
            "Revisions",
            None,
            "No earlier consensus earnings estimate was available to compare against.",
        )
    # Direction is the criterion, and direction is meaningful whether or not the
    # company is expected to earn money: a next-year forecast moving from -$2.39
    # to -$2.00 is analysts marking the business up, exactly as $9.20 from $8.60
    # is. An earlier version required a positive base, which silently excluded
    # every loss-making issuer -- growth names and turnarounds among them -- from
    # ever confirming this criterion.
    passed = eps_estimate_now > eps_estimate_prior
    now_text, prior_text = _money(eps_estimate_now), _money(eps_estimate_prior)
    if eps_estimate_prior > 0:
        # A percentage is only meaningful off a positive base.
        change = f" ({eps_estimate_now / eps_estimate_prior - 1.0:+.1%})"
        movement = "raised" if passed else "cut" if eps_estimate_now < eps_estimate_prior else "unchanged"
    else:
        change = ""
        movement = (
            "loss forecast narrowed" if passed
            else "loss forecast widened" if eps_estimate_now < eps_estimate_prior
            else "unchanged"
        )
    detail = (
        f"Next-year consensus EPS {now_text} versus {prior_text} "
        f"{window_days} days ago{change} -- {movement}."
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
    revision_window_days: int = _REVISION_LOOKBACK_DAYS,
    is_fund: bool = False,
    benchmark: str = "SPY",
) -> ConvictionChecklist:
    """Evaluate all five criteria from already-computed evidence; never fetches anything itself."""
    # A fund has no return on equity and no earnings consensus -- not because
    # the data is missing, but because the measures do not apply to it. Saying
    # so is more honest than "not available", which reads like a retrieval
    # failure the reader might expect to resolve on a retry.
    fund_note = "Not applicable to a fund, which has no company earnings of its own." if is_fund else ""
    return ConvictionChecklist(
        (
            _trend(price, sma50, sma200),
            _momentum(rsi14, macd, macd_signal),
            _relative_strength(security_return_pct, benchmark_return_pct, benchmark),
            _quality(return_on_equity, fund_note),
            _revisions(eps_estimate_now, eps_estimate_prior, revision_window_days, fund_note),
        )
    )
