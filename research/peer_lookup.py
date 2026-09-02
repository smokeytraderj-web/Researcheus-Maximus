"""Fetching the evidence a peer comparison needs.

Kept apart from core/peers.py, which holds the rule and the arithmetic and
touches no network. This is the adapter: it asks the data provider for an
industry's constituents and their history, and hands typed evidence back. A
provider change lands here and nowhere else.

Every failure is a missing peer group, never a partial one built from whatever
answered. A comparison assembled from the names that happened to respond is not
the group the rule chose.
"""

from __future__ import annotations

import logging

from core.peers import (
    PeerCandidate,
    PeerGroup,
    PeerReturn,
    build_peer_group,
    drop_illiquid,
    select_peers,
)

logger = logging.getLogger(__name__)

# Enough of the industry to survive the rule's exclusions without asking the
# provider for a hundred names.
CANDIDATE_DEPTH = 14


def _cap_and_currency(ticker_factory, symbol: str) -> tuple[float | None, str, float | None]:
    try:
        info = ticker_factory(symbol).info
    except Exception:  # noqa: BLE001 - a peer that will not answer is simply not a peer
        return None, "", None
    return info.get("marketCap"), str(info.get("currency") or "").upper(), info.get("forwardPE")


def peer_group_for(
    ticker_factory,
    industry_factory,
    download,
    *,
    symbol: str,
    industry_key: str,
    industry_label: str,
    market_cap: float | None,
    currency: str,
    period: str = "3mo",
    window_label: str = "three months",
) -> PeerGroup | None:
    """Build the peer group for one security, or nothing if it cannot be defended."""
    if not industry_key:
        return None
    try:
        top = industry_factory(industry_key).top_companies
    except Exception:  # noqa: BLE001
        logger.info("Peer lookup: no industry constituents for %s", industry_key)
        return None
    if top is None or not len(top):
        return None

    candidates = []
    for peer_symbol, row in list(top.iterrows())[:CANDIDATE_DEPTH]:
        cap, peer_currency, _pe = _cap_and_currency(ticker_factory, str(peer_symbol))
        candidates.append(
            PeerCandidate(str(peer_symbol), str(row.get("name") or peer_symbol), cap, peer_currency)
        )
    chosen, notes = select_peers(symbol, market_cap, currency, candidates)
    if not chosen:
        return None

    symbols = [symbol] + [candidate.ticker for candidate in chosen]
    try:
        frame = download(symbols, period=period, progress=False, auto_adjust=True)
        closes = frame["Close"].dropna()
        volumes = frame["Volume"]
    except Exception:  # noqa: BLE001
        logger.info("Peer lookup: history unavailable for %s", symbol)
        return None
    if symbol not in closes or len(closes) < 2:
        return None

    def total_return(column: str) -> float | None:
        if column not in closes:
            return None
        series = closes[column]
        if len(series) < 2 or not series.iloc[0]:
            return None
        return float(series.iloc[-1] / series.iloc[0] - 1)

    def traded_value(column: str) -> float | None:
        if column not in closes or column not in volumes:
            return None
        try:
            return float((closes[column] * volumes[column]).median())
        except Exception:  # noqa: BLE001
            return None

    members = []
    for candidate in chosen:
        _cap, _cur, forward_pe = _cap_and_currency(ticker_factory, candidate.ticker)
        members.append(
            PeerReturn(
                ticker=candidate.ticker,
                name=candidate.name,
                return_pct=total_return(candidate.ticker),
                market_cap=candidate.market_cap,
                forward_pe=forward_pe,
                dollar_volume=traded_value(candidate.ticker),
            )
        )
    members = [member for member in members if member.return_pct is not None]
    members, liquidity_notes = drop_illiquid(members)
    return build_peer_group(
        industry_label or industry_key,
        members,
        total_return(symbol),
        f"{window_label} to {closes.index[-1].date().isoformat()}",
        notes + liquidity_notes,
    )
