"""Peer group selection and comparison.

WHY A RULE AND NOT A LIST. "Similar companies" is the part of a comparison that
decides its answer, so the selection has to be defensible before the numbers
are. A hand-picked peer set flatters whatever it was picked to show, and a set
picked only by sector puts a $2B company beside a $2T one and calls the
valuation gap a finding. The rule here is deterministic, stated in the report,
and narrow enough to refuse rather than produce a set it cannot defend.

THE RULE, in order:

1. Start from the industry the data provider assigns to *this* security, and
   that industry's most significant companies by market weight. The subject is
   not compared against a classification chosen for it here.
2. Drop the subject itself.
3. Drop anything reporting in a different currency. A return series and a
   valuation multiple are only comparable when the unit is.
4. Drop anything outside a market-capitalisation band around the subject. Scale
   changes what a multiple means; beyond an order of magnitude either way these
   are not peers, whatever the classification says.
5. Keep the largest few that survive, and if fewer than MINIMUM_PEERS do, report
   no peer set at all. One odd survivor is worse than none: a reader takes a
   comparison as evidence that a comparable group was found.

WHAT IS COMPARED. Returns over identical dates, computed here from the same
price history the rest of the analysis uses, so the periods align by
construction. Valuation multiples come from the provider already normalised and
are shown as context with that stated -- fiscal periods across an industry do
not line up, and this module does not pretend to have checked that they do.

NOT AN INPUT TO THE CHECKLIST. The Conviction Checklist's relative-strength
criterion stays measured against the broad benchmark. Swapping in a peer group
would change what the criterion means, which is a policy change requiring a
version bump and a measured pass rate -- not a side effect of adding a feature.
"""

from __future__ import annotations

from dataclasses import dataclass

# Scale changes what a valuation multiple means. An order of magnitude either
# way is wide enough to keep a real industry cohort and narrow enough to exclude
# the mega-cap that dominates every list in its sector.
CAP_BAND_LOW = 0.1
CAP_BAND_HIGH = 10.0
# Below this the group is not a group, and a "peer comparison" against one name
# reads as more evidence than it is.
MINIMUM_PEERS = 2
MAX_PEERS = 5
# A thinly traded line prices on its own schedule: gaps, stale marks and a
# return series that is partly an artefact of nobody trading. Classification and
# market capitalisation do not catch it -- a foreign issuer's US over-the-counter
# line carries the parent's full market cap while trading a rounding error of it.
MINIMUM_DOLLAR_VOLUME = 5_000_000.0


@dataclass(frozen=True, slots=True)
class PeerCandidate:
    ticker: str
    name: str
    market_cap: float | None = None
    currency: str = ""


@dataclass(frozen=True, slots=True)
class PeerReturn:
    ticker: str
    name: str
    return_pct: float | None
    market_cap: float | None = None
    forward_pe: float | None = None
    dollar_volume: float | None = None


@dataclass(frozen=True, slots=True)
class PeerGroup:
    """The chosen peers, and the reasoning a reader needs to judge the choice."""

    industry: str
    members: tuple[PeerReturn, ...]
    subject_return_pct: float | None = None
    window_label: str = ""
    selection_rule: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return len([m for m in self.members if m.return_pct is not None]) >= MINIMUM_PEERS

    def median_return(self) -> float | None:
        values = sorted(m.return_pct for m in self.members if m.return_pct is not None)
        if not values:
            return None
        middle = len(values) // 2
        if len(values) % 2:
            return values[middle]
        return (values[middle - 1] + values[middle]) / 2

    def standing(self) -> str:
        """Where the subject sits in its own peer group, in plain words."""
        ranked = [m.return_pct for m in self.members if m.return_pct is not None]
        if self.subject_return_pct is None or not ranked:
            return ""
        behind = sum(1 for value in ranked if value < self.subject_return_pct)
        total = len(ranked) + 1
        place = len(ranked) - behind + 1
        median = self.median_return()
        gap = ""
        if median is not None:
            lead = self.subject_return_pct - median
            gap = (
                f", {abs(lead):.1%} {'ahead of' if lead >= 0 else 'behind'} the group median"
            )
        return f"{place} of {total} over the same dates{gap}"


def select_peers(
    subject_ticker: str,
    subject_cap: float | None,
    subject_currency: str,
    candidates: list[PeerCandidate],
    *,
    limit: int = MAX_PEERS,
) -> tuple[tuple[PeerCandidate, ...], tuple[str, ...]]:
    """Apply the rule. Returns the chosen peers and what was excluded, and why.

    Exclusions are returned rather than dropped silently: a reader judging a peer
    comparison needs to know that the obvious name is missing because it is ten
    times the size, not because the data was unavailable.
    """
    subject = subject_ticker.strip().upper()
    kept: list[PeerCandidate] = []
    notes: list[str] = []
    off_scale: list[str] = []
    off_currency: list[str] = []
    for candidate in candidates:
        if candidate.ticker.strip().upper() == subject:
            continue
        if subject_currency and candidate.currency and candidate.currency != subject_currency:
            off_currency.append(candidate.ticker)
            continue
        if subject_cap and candidate.market_cap:
            ratio = candidate.market_cap / subject_cap
            if ratio < CAP_BAND_LOW or ratio > CAP_BAND_HIGH:
                off_scale.append(candidate.ticker)
                continue
        kept.append(candidate)
        if len(kept) == limit:
            break
    if off_scale:
        notes.append(
            f"Excluded as outside {CAP_BAND_LOW:g}x-{CAP_BAND_HIGH:g}x the subject's market "
            f"capitalisation: {', '.join(off_scale)}."
        )
    if off_currency:
        notes.append(f"Excluded as reporting in another currency: {', '.join(off_currency)}.")
    return tuple(kept), tuple(notes)


def selection_rule_text(industry: str) -> str:
    """How the group was chosen, for the report to state alongside it."""
    return (
        f"The {industry.lower()} industry's largest companies by market weight, excluding any "
        f"outside {CAP_BAND_LOW:g}x-{CAP_BAND_HIGH:g}x this company's market capitalisation or "
        "reporting in another currency."
    )


def drop_illiquid(
    members: list[PeerReturn], floor: float = MINIMUM_DOLLAR_VOLUME
) -> tuple[list[PeerReturn], tuple[str, ...]]:
    """Remove peers too thinly traded for their price series to mean much.

    Runs after history is fetched, because that is where the volume is. A peer
    with no volume reported is kept rather than guessed about, and said so.
    """
    kept, thin, unknown = [], [], []
    for member in members:
        if member.dollar_volume is None:
            unknown.append(member.ticker)
            kept.append(member)
        elif member.dollar_volume < floor:
            thin.append(member.ticker)
        else:
            kept.append(member)
    notes = []
    if thin:
        notes.append(
            f"Excluded as too thinly traded to compare on price: {', '.join(thin)} "
            f"(under ${floor / 1_000_000:,.0f}M average daily value)."
        )
    if unknown:
        notes.append(f"Traded value not reported, so liquidity is unverified: {', '.join(unknown)}.")
    return kept, tuple(notes)


def build_peer_group(
    industry: str,
    members: list[PeerReturn],
    subject_return_pct: float | None,
    window_label: str,
    limitations: tuple[str, ...] = (),
) -> PeerGroup | None:
    """Assemble the group, or nothing when too few peers survived the rule."""
    group = PeerGroup(
        industry=industry,
        members=tuple(members),
        subject_return_pct=subject_return_pct,
        window_label=window_label,
        selection_rule=selection_rule_text(industry),
        limitations=limitations,
    )
    return group if group.usable else None
