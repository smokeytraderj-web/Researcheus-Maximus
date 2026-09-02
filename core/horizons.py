"""Horizon weighting policy: how the two workstreams combine into a rating.

Rating semantics live here rather than in a data source, so both providers
share one policy and a change to it is one reviewable diff.

An All Horizons request asks three questions. It used to be answered with a
single rating built on a technical-heavy 70/30 blend, which is the collapse the
product spec forbids in as many words: "Produce distinct conclusions and
strategy implications for Short, Medium, and Long Term. Do not collapse
conflicting horizon conclusions into one vague statement."

That mattered more than an edge case would: All Horizons is the default for a
request that does not name one, so most reports were taking it. The case it hid
is the one worth reading -- a business the fundamental work rates well while the
chart is falling, where the near-term and long-term answers genuinely differ.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.models import Horizon, HorizonView, Rating


# How much each workstream counts, by horizon. A short-horizon question leans on
# price structure; a long-horizon one leans on the business.
#
# All Horizons is the balanced weighting rather than the technical-heavy 70/30 it
# used to carry. A request spanning every horizon has no reason to privilege the
# near-term lens, and the single figure it produces is only ever a summary of the
# three stated separately -- see horizon_views.
_HORIZON_WEIGHTS = {
    Horizon.SHORT: (80, 20),
    Horizon.MEDIUM: (50, 50),
    Horizon.LONG: (20, 80),
    Horizon.ALL: (50, 50),
}


def horizon_views(technical: Rating, fundamental: Rating) -> tuple[HorizonView, ...]:
    """The Short, Medium and Long conclusions, each with its own weighting.

    Produced for an All Horizons request, which asks three questions. Blending
    them into one rating hid exactly the case the question exists for: a
    business the fundamental work rates well while the chart is falling, where
    the near-term and long-term answers genuinely differ.
    """
    views = []
    for horizon in (Horizon.SHORT, Horizon.MEDIUM, Horizon.LONG):
        technical_weight, fundamental_weight = _HORIZON_WEIGHTS[horizon]
        rating, _tw, _fw = _combine_ratings(technical, fundamental, horizon)
        leans = (
            "price structure and momentum"
            if technical_weight > fundamental_weight
            else "the business and its valuation"
            if fundamental_weight > technical_weight
            else "both equally"
        )
        views.append(
            HorizonView(
                horizon=horizon,
                rating=rating,
                technical_weight=technical_weight,
                fundamental_weight=fundamental_weight,
                rationale=(
                    f"Weighs {leans}: technical {technical.value.lower()}, "
                    f"fundamental {fundamental.value.lower()}."
                ),
            )
        )
    return tuple(views)


def horizon_split_summary(views: Sequence[HorizonView]) -> str:
    """One line saying whether the horizons agree, and how they differ if not."""
    if not views:
        return ""
    ratings = {view.rating for view in views}
    if len(ratings) == 1:
        return f"Short, medium and long term all read {views[0].rating.value}."
    parts = " · ".join(
        f"{view.horizon.value.replace(' Term', '')} {view.rating.value}" for view in views
    )
    return f"The horizons disagree — {parts}."


def _combine_ratings(
    technical: Rating,
    fundamental: Rating,
    horizon: Horizon,
    deep_analysis: bool = False,
) -> tuple[Rating, int, int]:
    """Return one horizon-weighted lead rating and transparent component weights."""
    if deep_analysis:
        technical_weight, fundamental_weight = (70, 30)
    else:
        technical_weight, fundamental_weight = _HORIZON_WEIGHTS[horizon]
    ratings = list(Rating)
    weighted_index = (
        ratings.index(technical) * technical_weight + ratings.index(fundamental) * fundamental_weight
    ) / 100
    index = int(weighted_index + 0.5)
    return ratings[max(0, min(len(ratings) - 1, index))], technical_weight, fundamental_weight
