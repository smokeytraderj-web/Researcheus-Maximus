"""Turn the call log into a scored record of the buy-side picks this tool made.

The rules, fixed deliberately so the record cannot be flattered after the fact:

* A **buy-side rating** (Strong Buy, Buy, Add) opens a pick at that report's price.
* The pick stays open until the same security is researched again and comes back
  with a rating that is *not* buy-side; it closes at that later report's price.
* Re-confirming a buy-side view does not reset the entry -- the original call is
  what gets judged.
* Picks still open are marked to the current price and labelled as open.

Every pick is measured against SPY over its own dates, so a rising market is not
counted as skill.  Nothing here invents a price: a pick whose prices cannot be
resolved is reported as unscored rather than dropped or estimated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

BUY_SIDE_RATINGS = ("Strong Buy", "Buy", "Add")


@dataclass(frozen=True, slots=True)
class Pick:
    ticker: str
    company: str
    rating: str
    horizon: str
    confidence: str
    opened_at: str
    entry_price: float
    closed_at: str = ""
    exit_price: float | None = None
    closed_by_rating: str = ""

    @property
    def is_open(self) -> bool:
        return not self.closed_at


@dataclass(frozen=True, slots=True)
class ScoredPick:
    pick: Pick
    exit_price: float
    priced_at: str
    return_pct: float
    benchmark_return_pct: float | None

    @property
    def excess_pct(self) -> float | None:
        if self.benchmark_return_pct is None:
            return None
        return self.return_pct - self.benchmark_return_pct

    @property
    def went_right(self) -> bool:
        return self.return_pct > 0


@dataclass(frozen=True, slots=True)
class TrackRecord:
    scored: tuple[ScoredPick, ...]
    unscored: tuple[Pick, ...]
    benchmark: str

    @property
    def has_picks(self) -> bool:
        return bool(self.scored or self.unscored)

    @property
    def closed(self) -> tuple[ScoredPick, ...]:
        return tuple(item for item in self.scored if not item.pick.is_open)

    @property
    def open(self) -> tuple[ScoredPick, ...]:
        return tuple(item for item in self.scored if item.pick.is_open)

    @property
    def hit_rate(self) -> float | None:
        if not self.scored:
            return None
        return sum(1 for item in self.scored if item.went_right) / len(self.scored)

    @property
    def average_return_pct(self) -> float | None:
        if not self.scored:
            return None
        return sum(item.return_pct for item in self.scored) / len(self.scored)

    @property
    def average_excess_pct(self) -> float | None:
        measured = [item.excess_pct for item in self.scored if item.excess_pct is not None]
        if not measured:
            return None
        return sum(measured) / len(measured)


def read_call_log(path: Path) -> tuple[dict, ...]:
    """Rows from the call-log CSV, oldest first; an empty tuple when there is none."""
    if not path.is_file():
        return ()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("ticker")]
    return tuple(sorted(rows, key=lambda row: (row.get("ticker", ""), row.get("logged_at", ""))))


def _price(row: dict) -> float | None:
    try:
        value = float(row.get("price") or 0.0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def build_picks(rows) -> tuple[Pick, ...]:
    """Walk each security's calls in order and pair buy-side entries with their exits."""
    picks: list[Pick] = []
    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        by_ticker.setdefault(str(row.get("ticker") or ""), []).append(row)

    for ticker, history in by_ticker.items():
        history = sorted(history, key=lambda row: str(row.get("logged_at") or ""))
        open_pick: Pick | None = None
        for row in history:
            rating = str(row.get("rating") or "").strip()
            price = _price(row)
            stamp = str(row.get("logged_at") or "")[:10]
            if rating in BUY_SIDE_RATINGS:
                # A repeat buy-side call re-affirms the existing pick; the first
                # call is the one being judged, so the entry is left alone.
                if open_pick is None and price is not None:
                    open_pick = Pick(
                        ticker=ticker,
                        company=str(row.get("company") or ticker),
                        rating=rating,
                        horizon=str(row.get("horizon") or ""),
                        confidence=str(row.get("confidence") or ""),
                        opened_at=stamp,
                        entry_price=price,
                    )
                continue
            if open_pick is not None:
                picks.append(
                    replace(open_pick, closed_at=stamp, exit_price=price, closed_by_rating=rating)
                )
                open_pick = None
        if open_pick is not None:
            picks.append(open_pick)

    picks.sort(key=lambda item: (item.opened_at, item.ticker))
    return tuple(picks)


def build_equity_curve(picks, price_history: dict, benchmark_history=None):
    """Equal-weighted daily curve of whatever picks were live on each date.

    Weighting is spread across the picks open that day and sits in cash when none
    are, so the curve reflects only the periods the tool actually had a call out --
    it never back-fills a position before the call was made.

    Returns ``(index, picks_cumulative, benchmark_cumulative)`` as pandas objects,
    or ``(None, None, None)`` when there is not enough price history to draw it.
    """
    import pandas as pd

    usable = {
        ticker: series.dropna().astype(float)
        for ticker, series in price_history.items()
        if series is not None and len(series.dropna()) > 1
    }
    if not usable or not picks:
        return None, None, None

    index = None
    for series in usable.values():
        index = series.index if index is None else index.union(series.index)
    if index is None or len(index) < 2:
        return None, None, None
    index = index.sort_values()

    daily_returns = pd.DataFrame(
        {ticker: series.reindex(index).ffill().pct_change() for ticker, series in usable.items()}
    )

    # Mask each security to the days its own pick was live.
    live = pd.DataFrame(False, index=index, columns=daily_returns.columns)
    for pick in picks:
        if pick.ticker not in live.columns:
            continue
        start = pd.Timestamp(pick.opened_at)
        end = pd.Timestamp(pick.closed_at) if pick.closed_at else index[-1]
        live.loc[(index > start) & (index <= end), pick.ticker] = True

    masked = daily_returns.where(live)
    portfolio = masked.mean(axis=1).fillna(0.0)
    cumulative = (1.0 + portfolio).cumprod() - 1.0

    benchmark_cumulative = None
    if benchmark_history is not None and len(benchmark_history.dropna()) > 1:
        benchmark = benchmark_history.dropna().astype(float).reindex(index).ffill()
        benchmark_cumulative = benchmark / benchmark.iloc[0] - 1.0

    return index, cumulative, benchmark_cumulative


def score_picks(
    picks,
    current_price,
    benchmark_return,
    benchmark: str = "SPY",
    today: str = "",
) -> TrackRecord:
    """Score picks using injected price lookups so the maths stays testable.

    ``current_price(ticker) -> float | None`` supplies a mark for open picks.
    ``benchmark_return(start, end) -> float | None`` gives the benchmark's return
    over the pick's own dates; ``None`` simply leaves the comparison blank.
    """
    scored: list[ScoredPick] = []
    unscored: list[Pick] = []
    for pick in picks:
        if pick.is_open:
            exit_price = current_price(pick.ticker)
            priced_at = today
        else:
            exit_price = pick.exit_price
            priced_at = pick.closed_at
        if not exit_price or exit_price <= 0 or pick.entry_price <= 0:
            unscored.append(pick)
            continue
        scored.append(
            ScoredPick(
                pick=pick,
                exit_price=float(exit_price),
                priced_at=priced_at,
                return_pct=float(exit_price) / pick.entry_price - 1.0,
                benchmark_return_pct=benchmark_return(pick.opened_at, priced_at),
            )
        )
    return TrackRecord(scored=tuple(scored), unscored=tuple(unscored), benchmark=benchmark)
