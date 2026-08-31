"""Event and positioning context: what is scheduled, and how the market last reacted.

Bounded by what the earnings feed actually carries.  It publishes per-quarter
surprise history and beat rates, but price reaction for the **most recent report
only** -- so this module reports that one reaction and never implies a series of
them.  Positioning (short interest, institutional and insider holding) comes from
the issuer metadata already fetched for the fundamentals.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EarningsReaction:
    release_date: str
    eps_surprise_pct: float | None
    revenue_surprise_pct: float | None
    gap_open_pct: float | None
    reaction_day_change_pct: float | None


@dataclass(frozen=True, slots=True)
class EventContext:
    symbol: str
    next_report_date: str
    days_to_report: int | None
    quarters_measured: int
    eps_beat_rate_pct: float | None
    avg_eps_surprise_pct: float | None
    last_reaction: EarningsReaction | None
    short_percent_of_float: float | None
    institutional_holding: float | None
    insider_holding: float | None
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.error and bool(self.next_report_date or self.last_reaction or self.quarters_measured)


def _days_until(date_text: str) -> int | None:
    try:
        return (dt.date.fromisoformat(date_text) - dt.date.today()).days
    except (ValueError, TypeError):
        return None


def build_event_context(
    symbol: str,
    earnings: dict,
    info: dict | None = None,
) -> EventContext:
    """Assemble scheduled-event and positioning context from already-fetched payloads."""
    info = info or {}
    stats = earnings.get("beat_stats") or {}
    last = earnings.get("last_report") or {}
    reaction_payload = last.get("price_reaction") or {}

    raw_next = earnings.get("next_report_date")
    next_date = ""
    if isinstance(raw_next, (int, float)) and raw_next > 0:
        # The feed returns the next release as a unix timestamp.
        next_date = dt.datetime.fromtimestamp(float(raw_next), dt.timezone.utc).date().isoformat()
    elif isinstance(raw_next, str) and raw_next:
        next_date = raw_next[:10]

    reaction = None
    if last.get("earnings_release_date"):
        reaction = EarningsReaction(
            release_date=str(last.get("earnings_release_date"))[:10],
            eps_surprise_pct=_as_float(last.get("eps_surprise_pct")),
            revenue_surprise_pct=_as_float(last.get("revenue_surprise_pct")),
            gap_open_pct=_as_float(reaction_payload.get("gap_open_pct")),
            reaction_day_change_pct=_as_float(reaction_payload.get("reaction_day_change_pct")),
        )

    return EventContext(
        symbol=symbol,
        next_report_date=next_date,
        days_to_report=_days_until(next_date) if next_date else None,
        quarters_measured=int(stats.get("quarters") or 0),
        eps_beat_rate_pct=_as_float(stats.get("eps_beat_rate_pct")),
        avg_eps_surprise_pct=_as_float(stats.get("avg_eps_surprise_pct")),
        last_reaction=reaction,
        short_percent_of_float=_as_float(info.get("shortPercentOfFloat")),
        institutional_holding=_as_float(info.get("heldPercentInstitutions")),
        insider_holding=_as_float(info.get("heldPercentInsiders")),
    )


def _as_float(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def event_metrics(context: EventContext) -> tuple[tuple[str, str], ...]:
    """Report metrics, omitting anything the sources did not supply."""
    rows: list[tuple[str, str]] = []
    if context.next_report_date:
        when = f" (in {context.days_to_report}d)" if context.days_to_report is not None else ""
        rows.append(("Next earnings report", f"{context.next_report_date}{when}"))
    if context.eps_beat_rate_pct is not None and context.quarters_measured:
        rows.append(
            ("EPS beat rate", f"{context.eps_beat_rate_pct:.0f}% of last {context.quarters_measured} quarters")
        )
    if context.avg_eps_surprise_pct is not None:
        rows.append(("Average EPS surprise", f"{context.avg_eps_surprise_pct:+.2f}%"))
    reaction = context.last_reaction
    if reaction is not None:
        if reaction.eps_surprise_pct is not None:
            rows.append((f"Last report ({reaction.release_date}) EPS surprise", f"{reaction.eps_surprise_pct:+.2f}%"))
        if reaction.reaction_day_change_pct is not None:
            gap = f" (gap {reaction.gap_open_pct:+.2f}%)" if reaction.gap_open_pct is not None else ""
            rows.append(("Price reaction to last report", f"{reaction.reaction_day_change_pct:+.2f}%{gap}"))
    if context.short_percent_of_float is not None:
        rows.append(("Short interest (% of float)", f"{context.short_percent_of_float:.2%}"))
    if context.institutional_holding is not None:
        rows.append(("Institutional holding", f"{context.institutional_holding:.1%}"))
    if context.insider_holding is not None:
        rows.append(("Insider holding", f"{context.insider_holding:.2%}"))
    return tuple(rows)


def event_signals(context: EventContext) -> tuple[str, ...]:
    """Event observations worth weighing against the technical read."""
    signals: list[str] = []
    if context.days_to_report is not None and 0 <= context.days_to_report <= 21:
        signals.append(
            f"Earnings land on {context.next_report_date}, in {context.days_to_report} days, so any "
            "position taken now carries event risk before the technical setup can resolve."
        )
    reaction = context.last_reaction
    if reaction is not None and reaction.eps_surprise_pct is not None and reaction.reaction_day_change_pct is not None:
        beat = reaction.eps_surprise_pct > 0
        fell = reaction.reaction_day_change_pct < 0
        if beat and fell:
            signals.append(
                f"The last report beat EPS by {reaction.eps_surprise_pct:.2f}% yet the stock fell "
                f"{abs(reaction.reaction_day_change_pct):.2f}% on the reaction day — the market was "
                "positioned for more, so beats alone have not been enough."
            )
        elif not beat and not fell:
            signals.append(
                f"The last report missed EPS by {abs(reaction.eps_surprise_pct):.2f}% yet the stock rose "
                f"{reaction.reaction_day_change_pct:.2f}% on the reaction day, which suggests expectations "
                "were already reset lower."
            )
        else:
            signals.append(
                f"The last report moved the stock {reaction.reaction_day_change_pct:+.2f}% on the reaction "
                f"day against an EPS surprise of {reaction.eps_surprise_pct:+.2f}%."
            )
    if context.eps_beat_rate_pct is not None and context.quarters_measured >= 4:
        if context.eps_beat_rate_pct >= 90:
            signals.append(
                f"Management has beaten EPS in {context.eps_beat_rate_pct:.0f}% of the last "
                f"{context.quarters_measured} quarters, so a beat is largely the base case rather than a catalyst."
            )
        elif context.eps_beat_rate_pct <= 50:
            signals.append(
                f"EPS has beaten in only {context.eps_beat_rate_pct:.0f}% of the last "
                f"{context.quarters_measured} quarters, making guidance less reliable as support."
            )
    if context.short_percent_of_float is not None and context.short_percent_of_float >= 0.10:
        signals.append(
            f"Short interest is {context.short_percent_of_float:.1%} of float, high enough that sharp "
            "counter-trend rallies can be driven by covering rather than by fundamentals."
        )
    return tuple(signals)
