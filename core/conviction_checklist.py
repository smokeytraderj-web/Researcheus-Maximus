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
                 benchmark (SPY) by at least _RELATIVE_STRENGTH_MARGIN.
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

v2.2 gave relative strength a margin. It had been a bare `>=` against the
benchmark, so a security returning +1.5% against SPY's +1.4% confirmed the
criterion and the report told the reader it was "ahead of the S&P 500". Over the
64-session default window a tenth of a point is noise, and a box that flips on
noise cannot discriminate however sound the factor behind it. The criterion now
requires a margin, which is a statement about measurement, not about relative
strength itself: cross-sectional momentum is among the most replicated
predictors in the literature, and the fault was in reading a rounding error as
outperformance.

The margin is flat rather than scaled to the window. Almost every report uses
the 64-session default, and a fixed figure is one a reader can hold in mind;
the cost is that a custom range of a month or of five years measures the same
three points against very different amounts of drift, so the report states the
window alongside the figures.

HOW THE CHECKLIST IS NARRATED (`checklist_paragraphs`): the prose is assembled
from the criteria, never from model text, so it cannot drift from the score. It
is written in two movements rather than as a list. The first groups the findings
by lens -- the three price criteria together, the two business criteria together
-- because "every price-based lens agrees" tells a reader what kind of evidence
is carrying the call, and therefore what kind of evidence would break it, which
five ticked boxes cannot. The second takes the dissent seriously: it names what
does not confirm, sets a concrete counterweight against it, says what it is not
grounds for, and states what the case rests on and what it does not. This is not
a policy change and does not move POLICY_VERSION -- no threshold, criterion or
score is affected, only how the same result is put into words.

Changing a threshold, adding, or removing a criterion is a policy change: bump
POLICY_VERSION and update this docstring in the same change.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

POLICY_VERSION = "2.2"

_RSI_FLOOR = 40.0
_RSI_CEILING = 75.0
# Return on equity that marks a genuinely profitable business rather than one
# merely in the black. Measured pass rate 68% across the large-cap sample.
_ROE_FLOOR = 0.15
# Lookback for the estimate-revision comparison. Shorter windows are dominated
# by noise around a single earnings date.
_REVISION_LOOKBACK_DAYS = 90
# How far ahead of the benchmark counts as ahead. Three points over the
# 64-session default window is small enough that a genuinely leading stock still
# clears it, and large enough that a dead heat does not.
_RELATIVE_STRENGTH_MARGIN = 0.03

# Plain-English, client-facing gloss for each criterion -- what it measures, not
# what this security scored.  Fixed per key, versioned with the policy above;
# `detail` on the criterion itself carries the security-specific evaluation.
_EXPLANATIONS = {
    "trend": "The stock's price relative to its own longer-run moving averages -- a measure of whether it sits in a sustained uptrend or downtrend.",
    "momentum": "The strength of short-term buying pressure: trending with participation, short of the overbought extreme where a pullback becomes likely.",
    "relative_strength": "The stock's total return against the S&P 500 over the same period -- outperformance, not simply a rising price. It must lead by a clear margin, so that a dead heat is not read as strength.",
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
    # A short, security-specific quantity as a clause -- "the stock returned +42%
    # against SPY's +18%". `detail` states the criterion's own verdict at length;
    # this is the same evidence cut short enough to sit inside a sentence about a
    # different criterion, which is what a contrast needs.
    figure: str = ""

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


# Slide-length readings of each criterion, confirmed and not. A deck is read
# from across a room in a few seconds, so these are three or four words where the
# report's sentence is thirty. They say the same thing at a different distance.
_SLIDE_PHRASES = {
    "trend": ("Above the 50 and 200-day", "Below its long-run averages"),
    "momentum": ("Momentum participating", "Momentum not confirming"),
    # Not "Behind the S&P 500": a stock ahead by less than the margin misses the
    # criterion while still being ahead, and the slide must not say otherwise.
    # "No clear lead" keeps that true in half the width, which matters in a
    # five-column strip where the longer phrase ran to four lines.
    "relative_strength": ("Ahead of the S&P 500", "No clear lead on the S&P 500"),
    "quality": ("Strong return on capital", "Thin return on capital"),
    "revisions": ("Estimates rising", "Estimates falling"),
}


def checklist_headlines(checklist: "ConvictionChecklist") -> tuple[tuple[str, str, str], ...]:
    """(label, slide-length reading, status) for each criterion, for the deck."""
    if checklist is None or not checklist.criteria:
        return ()
    rows = []
    for item in checklist.criteria:
        phrases = _SLIDE_PHRASES.get(item.key)
        if not phrases:
            continue
        if item.passed is True:
            reading = phrases[0]
        elif item.passed is False:
            reading = phrases[1]
        else:
            reading = "Not applicable" if item.detail.startswith("Not applicable") else "Not confirmed"
        rows.append((item.label, reading, item.status))
    return tuple(rows)


def checklist_watch(checklist: "ConvictionChecklist") -> str:
    """The single thing to watch: what the failing criteria would need to do."""
    if checklist is None:
        return ""
    watch = [_WOULD_CHANGE[item.key] for item in checklist.criteria
             if item.passed is False and item.key in _WOULD_CHANGE]
    return _join(watch)


# What would have to change for a failing criterion to confirm. Naming it is the
# difference between "the dissent would need to change" -- true of any dissent,
# and so worth nothing -- and telling the reader what to watch.
_WOULD_CHANGE = {
    "trend": "price reclaiming both long-run averages",
    "momentum": "momentum confirming rather than fading",
    "relative_strength": "the stock pulling clearly ahead of the market",
    "quality": "returns on shareholder capital improving",
    "revisions": "estimates turning back up",
}

# How each criterion reads in prose, confirmed and not. Phrased as findings
# rather than labels, so the paragraph reads like an analyst wrote it instead of
# a checklist being recited back.
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
        "it has not pulled clearly ahead of the S&P 500 over the same window",
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


# The three price-based lenses and the two business ones. Grouping is the whole
# point of the paragraph: "every price-based lens agrees" says something a flat
# list of five findings cannot, because it tells a reader what *kind* of evidence
# is carrying the call -- and therefore what kind of evidence would break it.
_PRICE_KEYS = ("trend", "momentum", "relative_strength")
_BUSINESS_KEYS = ("quality", "revisions")

# What a confirmed criterion means the case is resting on. The three price
# criteria collapse to one word when two or more of them agree: a reader deciding
# what they are exposed to needs "price and profitability", not a list of three
# correlated price measures dressed up as three independent supports.
_RELIANCE = {
    "trend": "the trend",
    "momentum": "momentum",
    "relative_strength": "relative strength",
    "quality": "profitability",
    "revisions": "improving expectations",
}

# Findings in the business register, which is a different register from price.
_BUSINESS_PHRASES = {
    "quality": ("returns on shareholder capital are strong", "returns on shareholder capital are thin"),
    "revisions": ("analysts are raising next-year estimates", "analysts are cutting next-year estimates"),
}

_NUMBER_WORDS = ("None", "One", "Two", "Three", "Four", "Five")

# Preference order for the criterion quoted as the counterweight to a dissent.
# Relative strength first because a return against the market is the most
# concrete thing on the list; momentum last because an RSI reading is the least.
_CONTRAST_ORDER = ("relative_strength", "quality", "trend", "revisions", "momentum")

_BEARISH_RATINGS = {"reduce", "sell", "avoid"}


def _word(count: int) -> str:
    return _NUMBER_WORDS[count] if 0 <= count < len(_NUMBER_WORDS) else str(count)


def _characterisation(passed: int, judged: int, partial: bool) -> str:
    """The score as a picture. Weight of evidence, never a forecast.

    `partial` says some criteria could not be judged, which is why a full house
    is not called a clean sweep there -- it is a clean read of less evidence.
    """
    if judged == 0:
        return "too little to judge on"
    share = passed / judged
    if share == 1:
        return "as clean a read as this evidence allows" if partial else "a clean sweep"
    if share >= 0.75:
        return "a constructive picture"
    if share > 0.5:
        return "a mixed but net-positive picture"
    if share == 0.5:
        return "an evenly split picture"
    if share > 0:
        return "a weak picture"
    return "no support at all"


def _reliance(passed_keys: list[str]) -> list[str]:
    """What the case actually rests on, in the coarsest honest terms."""
    price = [key for key in passed_keys if key in _PRICE_KEYS]
    parts = []
    if len(price) >= 2:
        parts.append("price")
    elif price:
        parts.append(_RELIANCE[price[0]])
    parts.extend(_RELIANCE[key] for key in _BUSINESS_KEYS if key in passed_keys)
    return parts


def _pick(seed: str, key: str, options: tuple[str, ...]) -> str:
    """Choose one of several equivalent phrasings, deterministically.

    Variation, not randomness. Every note used to open with the same sentence
    frame, which made the reasoning read as a form letter and made two different
    securities look like the same analysis. But a research note cannot reword
    itself on re-read: the same evidence has to produce the same words, or a
    reader who returns to a note finds a different one and two runs of one
    result appear to disagree.

    The seed is the security and the analysis date, so the wording varies across
    names and across days while staying fixed for any one note. Options must be
    interchangeable in meaning -- this varies how a finding is said, never what
    is said.
    """
    if not options:
        return ""
    if not seed:
        return options[0]
    digest = hashlib.sha256(f"{seed}|{key}".encode("utf-8")).digest()
    return options[digest[0] % len(options)]


def checklist_paragraphs(
    checklist: "ConvictionChecklist", *, rating: str = "", seed: str = ""
) -> tuple[str, ...]:
    """How the five checks combine, as an analyst would actually put it.

    Two movements. The first reports the balance grouped by lens -- price
    evidence together, business evidence together -- because what carries a call
    is more useful than which five boxes were ticked. The second takes the
    dissent seriously: it names what does not confirm, sets a concrete
    counterweight against it, says what it is *not* grounds for, and then states
    precisely what the reader is relying on and what they are not.

    Assembled deterministically from the criteria themselves -- no model text is
    an input, exactly as for the boxes -- so the prose can never drift from the
    score it is describing. An earlier version read "In favour: a, b, c, and d.
    Against: e", which is the checklist recited back rather than read.
    """
    if checklist is None or not checklist.criteria:
        return ()
    passed_keys, failed_keys, unknown, inapplicable = [], [], [], []
    figures: dict[str, str] = {}
    for item in checklist.criteria:
        figures[item.key] = item.figure
        if item.passed is True:
            passed_keys.append(item.key)
        elif item.passed is False:
            failed_keys.append(item.key)
        # "Does not apply" and "could not be retrieved" are different findings,
        # and telling a reader a fund's earnings data was unavailable would
        # invite them to retry for something that does not exist.
        elif item.detail.startswith("Not applicable"):
            inapplicable.append(item.label.lower())
        else:
            unknown.append(item.label.lower())

    judged = checklist.total_count - checklist.unconfirmed_count
    partial = bool(checklist.unconfirmed_count)
    picture = _characterisation(checklist.passed_count, judged, partial)
    if not passed_keys:
        # "No support at all" after "not one confirms" is the same sentence twice.
        opening = _pick(seed, "none", (
            f"Not one of the {_word(judged).lower()} checks confirms",
            f"None of the {_word(judged).lower()} checks confirms",
            f"The checklist confirms nothing here: {_word(judged).lower()} checks, none of them met",
        ))
    elif partial:
        opening = _pick(seed, "partial", (
            f"{_word(checklist.passed_count)} of the {_word(judged).lower()} that could be "
            f"judged confirm — {picture}",
            f"Of the {_word(judged).lower()} checks that could be judged, "
            f"{_word(checklist.passed_count).lower()} confirm — {picture}",
        ))
    else:
        count, total = _word(checklist.passed_count), _word(checklist.total_count).lower()
        opening = _pick(seed, "score", (
            f"{count} of {total} is {picture}",
            f"{count} checks of {total} confirm — {picture}",
            f"The checklist comes in at {count.lower()} of {total}, {picture}",
        ))

    # Price evidence as a group. This paragraph carries what confirms; the
    # dissent paragraph carries what does not, at length. Spelling the failures
    # out in both is how the old version came to read as a list read twice, so
    # failures appear here only as their names, or in full when nothing passed.
    price_pass = [key for key in _PRICE_KEYS if key in passed_keys]
    price_fail = [key for key in _PRICE_KEYS if key in failed_keys]
    price_said = [_NARRATIVE_PHRASES[key][0] for key in price_pass]
    if price_pass and not price_fail:
        joined = _join(price_said)
        grouping = _pick(seed, "price-agree", (
            f"every price-based lens agrees: {joined}",
            f"the price evidence points one way: {joined}",
            f"nothing in the price evidence dissents: {joined}",
        )) if len(price_pass) > 1 else f"the price evidence agrees: {joined}"
    elif price_pass and price_fail:
        names = _join([_RELIANCE[key] for key in price_fail])
        verb = "do" if len(price_fail) > 1 else "does"
        grouping = _pick(seed, "price-split", (
            f"the price evidence is split: {_join(price_said)}, while {names} {verb} not confirm",
            f"the price evidence pulls both ways: {_join(price_said)}, against {names}",
            f"price is not of one mind: {_join(price_said)}, but {names} {verb} not follow",
        ))
    elif price_fail:
        grouping = "no price-based lens supports it: " + _join(
            [_NARRATIVE_PHRASES[key][1] for key in price_fail]
        )
    else:
        grouping = ""
    # An em dash already carries the partial opening, so a second clause hung off
    # it with "and" reads as a run-on. Start a sentence instead.
    if not grouping:
        first = opening + "."
    elif partial and passed_keys:
        first = f"{opening}. {grouping[:1].upper()}{grouping[1:]}."
    else:
        first = f"{opening}, and {grouping}."

    # Business evidence, in its own register and its own sentence. Confirmations
    # only, for the same reason -- unless nothing at all confirmed, in which case
    # there is no dissent paragraph to hold the failures.
    business_pass = [key for key in _BUSINESS_KEYS if key in passed_keys]
    if business_pass:
        said = _join([_BUSINESS_PHRASES[key][0] for key in business_pass])
        first += _pick(seed, "business", (
            f" On the business, {said}.",
            f" Away from the chart, {said}.",
            f" The business side adds that {said}.",
        ))
    elif not passed_keys:
        business_fail = [key for key in _BUSINESS_KEYS if key in failed_keys]
        if business_fail:
            first += f" On the business, {_join([_BUSINESS_PHRASES[key][1] for key in business_fail])}."
    if inapplicable:
        first += (
            f" {_join([item.capitalize() for item in inapplicable])} "
            f"{'do' if len(inapplicable) > 1 else 'does'} not apply to a fund, "
            "which has no company earnings of its own."
        )
    if unknown:
        first += (
            f" {_join([item.capitalize() for item in unknown])} could not be judged from the "
            "available evidence, so {} counted neither way.".format(
                "they were" if len(unknown) > 1 else "it was"
            )
        )

    paragraphs = [first]
    second = _dissent_paragraph(passed_keys, failed_keys, figures, rating, seed)
    if second:
        paragraphs.append(second)
    return tuple(paragraphs)


def _dissent_paragraph(
    passed_keys: list[str],
    failed_keys: list[str],
    figures: dict[str, str],
    rating: str,
    seed: str = "",
) -> str:
    """The part a reader actually wants: what the disagreement costs them.

    A dissent is only useful if it is priced. Naming it, weighing it against the
    strongest thing that does confirm, and then saying what the case rests on --
    and what it does not -- is the difference between a checklist and a view.
    """
    resting_on = _reliance(passed_keys)
    reliance = _join(resting_on)
    contrary = "buy" if rating.strip().lower() in _BEARISH_RATINGS else "sell"

    if not failed_keys:
        if not passed_keys:
            return ""
        text = "Nothing on the list argues the other way."
        if reliance:
            text += (
                f" That makes this a case resting on {reliance}"
                f"{' all' if len(resting_on) > 1 else ''} continuing to hold: "
                "the risk here is deterioration, not the absence of support."
            )
        if rating:
            text += f" The {rating} view is the balance of that evidence, not a guarantee of it."
        return text

    if not passed_keys:
        if not rating:
            return ""
        return (
            "There is no counterweight to set against that. The checklist offers no support for a "
            f"constructive view here, which the {rating} rating reflects."
        )

    # The strongest confirmed criterion, quoted with its own figure, so the
    # dissent is set against something concrete rather than against a mood.
    counterweight = next(
        (figures[key] for key in _CONTRAST_ORDER if key in passed_keys and figures.get(key)), ""
    )
    lead = _pick(seed, "dissent-lead", (
        "The one that does not confirm is the interesting one.",
        "The dissent is where the work is.",
        "What does not confirm is the part worth reading.",
    )) if len(failed_keys) == 1 else _pick(seed, "dissent-lead-many", (
        f"{_word(len(failed_keys))} do not confirm, and they are the interesting ones.",
        f"{_word(len(failed_keys))} dissent, and the dissent is where the work is.",
        f"{_word(len(failed_keys))} do not confirm, which is the part worth reading.",
    ))
    body = _join([_NARRATIVE_PHRASES[key][1] for key in failed_keys])
    text = f"{lead} {body[:1].upper()}{body[1:]}"
    text += f", while {counterweight}." if counterweight else "."

    if rating:
        text += _pick(seed, "not-a-reason", (
            f" That is not on its own a reason to {contrary}, and the {rating} rating still stands.",
            f" On its own it does not overturn the {rating} view, which still stands.",
            f" It is not grounds to {contrary} by itself; the {rating} rating holds.",
        ))
    # "and not momentum and relative strength" stacks two ands on one clause; the
    # dissent is a set of things the case does *not* rest on, which is an "or".
    dissent = " or ".join(_RELIANCE[key] for key in failed_keys if key in _RELIANCE)
    if reliance and dissent:
        text += _pick(seed, "rests-on", (
            f" It is a reason to be precise about what the case rests on: {reliance}, "
            f"and not on {dissent} — because that is what this evidence does not show.",
            f" It does mean being clear about what is carrying this: {reliance}, "
            f"not {dissent}, which the evidence does not support.",
            f" What it changes is the footing: this rests on {reliance} rather than on "
            f"{dissent}, and the difference matters if that is what you were relying on.",
        ))
    watch = _join([_WOULD_CHANGE[key] for key in failed_keys if key in _WOULD_CHANGE])
    if watch:
        text += f" Watch for {watch}."
    return text


def checklist_narrative(
    checklist: "ConvictionChecklist", *, rating: str = "", seed: str = ""
) -> str:
    """The paragraphs as one string, for callers that render a single block."""
    return " ".join(checklist_paragraphs(checklist, rating=rating, seed=seed))


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
    return ConvictionCriterion(
        "trend", "Trend", passed, detail,
        figure=f"price is holding {price / sma200 - 1:+.0%} against its 200-day average",
    )


def _distinguishable(first: float, second: float, places: int = 2, limit: int = 4) -> tuple[str, str]:
    """Format two figures with enough precision to show that they differ.

    "MACD is above its signal (2.67 vs 2.67)" is a sentence that contradicts
    itself in front of the reader. The two values genuinely do differ -- just not
    at two decimal places -- so the fix is precision, not softer wording: a
    report that states a comparison must show the figures that decided it. Stops
    at four places; two values equal that far apart are equal for this purpose,
    and the criterion fails in that case anyway.
    """
    while places < limit and f"{first:.{places}f}" == f"{second:.{places}f}":
        places += 1
    return f"{first:.{places}f}", f"{second:.{places}f}"


def _macd_reading(macd: float, macd_signal: float) -> str:
    """How the MACD comparison is stated, so it never contradicts itself.

    Two values that print identically cannot be offered as evidence that one is
    above the other. Where four decimal places still tie, the honest statement
    is the size of the gap, not a pair of matching numbers.
    """
    macd_text, signal_text = _distinguishable(macd, macd_signal)
    if macd_text != signal_text:
        return f"{macd_text} vs {signal_text}"
    return f"both {macd_text} to four decimal places"


def _momentum(rsi14: float, macd: float, macd_signal: float) -> ConvictionCriterion:
    macd_bullish = macd > macd_signal
    rsi_healthy = _RSI_FLOOR <= rsi14 <= _RSI_CEILING
    passed = macd_bullish and rsi_healthy
    macd_text, signal_text = _distinguishable(macd, macd_signal)
    reading = _macd_reading(macd, macd_signal)
    lead = (
        "MACD is above its signal"
        if macd_text != signal_text
        else "MACD is above its signal by less than a rounding error"
    )
    detail = (
        f"{lead} ({reading}) and RSI is {rsi14:.1f}, "
        f"inside the {_RSI_FLOOR:.0f}-{_RSI_CEILING:.0f} constructive range."
        if passed
        else f"MACD {reading}; RSI {rsi14:.1f} "
        f"({'below' if rsi14 < _RSI_FLOOR else 'above' if rsi14 > _RSI_CEILING else 'inside'} the "
        f"{_RSI_FLOOR:.0f}-{_RSI_CEILING:.0f} range) -- momentum does not confirm both conditions."
    )
    return ConvictionCriterion(
        "momentum", "Momentum", passed, detail, figure=f"RSI sits at {rsi14:.0f}"
    )


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
    lead = security_return_pct - benchmark_return_pct
    passed = lead >= _RELATIVE_STRENGTH_MARGIN
    # The gap is quoted, not just the two returns, because the gap is the
    # criterion -- and a reader who sees +1.5% against +1.4% marked as a miss is
    # owed the margin that decided it.
    detail = (
        f"Returned {security_return_pct:+.1%} versus {benchmark}'s {benchmark_return_pct:+.1%} "
        f"over the same dates -- {'ahead by' if lead >= 0 else 'behind by'} {abs(lead):.1%}, "
        f"{'clearing' if passed else 'short of'} the {_RELATIVE_STRENGTH_MARGIN:.0%} margin."
    )
    return ConvictionCriterion(
        "relative_strength", "Relative strength", passed, detail,
        figure=(
            f"the stock returned {security_return_pct:+.0%} against "
            f"{benchmark}'s {benchmark_return_pct:+.0%} over the same window"
        ),
    )


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
    return ConvictionCriterion(
        "quality", "Quality", passed, detail,
        figure=f"the business earns {return_on_equity:.0%} on shareholder capital",
    )


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
    return ConvictionCriterion(
        "revisions", "Revisions", passed, detail,
        figure=f"next-year consensus has moved from {prior_text} to {now_text}",
    )


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
