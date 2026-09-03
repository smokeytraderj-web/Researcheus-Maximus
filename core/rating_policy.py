"""What each of the seven rating labels means.

The labels existed as an enum with no definitions anywhere, which meant the
difference between Buy and Add lived only in a score threshold and in whatever
a reader assumed. The product spec requires rating semantics to be defined in a
versioned policy file, and this is that file. Changing a definition is a policy
change: bump POLICY_VERSION in the same edit.

TWO THINGS THESE LABELS ARE NOT.

They are not a forecast. Each states the weight of evidence for a course of
action at the stated horizon, on the evidence cited in the note, at the time
stated on it.

They are not another firm's scale. An Overweight from a research house is not
this firm's Buy: different definitions, different horizons, different firm. A
house's rating is always shown in that house's own words (see core/peers.py and
the house-view model).

THE DISTINCTION THAT NEEDED WRITING DOWN. Buy and Add are both constructive.
Buy speaks to a position that does not exist yet: the evidence supports putting
it on here. Add speaks to one that does: the evidence supports more of it, but
usually on a condition -- a pullback into the entry zone, or a confirmation the
note names -- rather than at any price today. A reader holding the name and a
reader holding none should not act identically on the same word, which is why
these are two labels and not one.
"""

from __future__ import annotations

from core.models import Rating

POLICY_VERSION = "1.0"

# Ordered from most to least constructive, matching Rating's own order so a
# reader and the code agree on which direction is which.
DEFINITIONS: dict[Rating, str] = {
    Rating.STRONG_BUY: (
        "The evidence is aligned across the workstreams and the entry is favourable now. "
        "Supports initiating a full position at current levels."
    ),
    Rating.BUY: (
        "Constructive, with no material dissent that changes the conclusion. Supports "
        "initiating a position at current levels."
    ),
    Rating.ADD: (
        "Constructive, but qualified. Supports increasing an existing position rather than "
        "initiating one here — usually on a stated condition, such as a pullback into the "
        "entry zone or the confirmation the note names."
    ),
    Rating.HOLD: (
        "The evidence supports neither adding nor reducing. Maintain the position as it "
        "stands and watch the stated triggers."
    ),
    Rating.REDUCE: (
        "The evidence has deteriorated but does not require exit. Supports trimming the "
        "position, not closing it."
    ),
    Rating.SELL: (
        "The case the position was held on no longer holds. Supports exiting."
    ),
    Rating.AVOID: (
        "Not a position this analysis supports holding at any size at present, whether or "
        "not one is already held."
    ),
}

# What each label speaks to, so the difference between the two constructive ones
# is legible without reading the full definition.
APPLIES_TO: dict[Rating, str] = {
    Rating.STRONG_BUY: "Initiating a position",
    Rating.BUY: "Initiating a position",
    Rating.ADD: "Increasing an existing position",
    Rating.HOLD: "Holding what is held",
    Rating.REDUCE: "Trimming an existing position",
    Rating.SELL: "Closing a position",
    Rating.AVOID: "Not owning it",
}


def definition(rating: Rating) -> str:
    """What this rating means. Every label has one; there is no default."""
    return DEFINITIONS[rating]


def applies_to(rating: Rating) -> str:
    """The position a reader has to be in for this rating to speak to them."""
    return APPLIES_TO[rating]


def is_constructive(rating: Rating) -> bool:
    return rating in {Rating.STRONG_BUY, Rating.BUY, Rating.ADD}


def is_negative(rating: Rating) -> bool:
    return rating in {Rating.REDUCE, Rating.SELL, Rating.AVOID}
