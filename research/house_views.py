"""Third-party research house views, entered once and reused.

WHAT THIS IS FOR. An advisor entitled to a research portal -- J.P. Morgan
Markets is the case this was built for -- reads a name's equity rating, price
target and credit rating there, and wants those to appear in the report beside
everything else. This holds them.

WHAT IT DELIBERATELY IS NOT. It is not a scraper and holds no credentials. The
advisor reads the portal under their own entitlement, in their own session, and
records the figures; this stores and cites them. That keeps the app clear of
the portal's access controls entirely, and it keeps the licensing question where
it belongs -- attributed facts with a date and a source, not reproduced
analysis. Swapping in an entitled API later replaces this module and touches
nothing else, which is the point of the boundary.

WHAT IS STORED. A rating in the house's own words, never translated into this
app's seven-label scale (see HouseView). One current view per house per ticker:
entering a new one supersedes the old, because two live views from one house is
not a state that exists. Everything carries the date it was published, so a view
that has gone stale says so in the report rather than passing as current.

WHERE. RESEARCHEUS_DATA_DIR if set, else a directory under the user's home.
Deliberately not the reports directory: reports are temporary and swept, and
these are meant to outlive them. On a container host that replaces the container
on deploy, home is ephemeral too -- point RESEARCHEUS_DATA_DIR at a mounted
volume there.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from core.models import HouseView

_lock = threading.Lock()

DATA_DIR_ENV = "RESEARCHEUS_DATA_DIR"
STORE_FILE = "house_views.json"
# Beyond this a published view is reported as stale rather than current. Sell-side
# ratings are revisited around earnings, so two quarters without a republication
# is long enough that the reader should be told before weighing it.
STALE_AFTER_DAYS = 180

_FIELDS = (
    "house", "ticker", "equity_rating", "price_target", "currency", "target_horizon",
    "credit_rating", "credit_rating_scale", "analyst", "published", "document",
    "locator", "retrieved_at",
)


def store_path() -> Path:
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    root = Path(override) if override else Path.home() / ".researcheus"
    return root / STORE_FILE


def _key(house: str, ticker: str) -> str:
    return f"{house.strip().casefold()}|{ticker.strip().upper()}"


def _load(path: Path) -> dict[str, dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _to_view(record: dict) -> HouseView | None:
    """Rebuild a stored record, dropping anything that no longer validates.

    A record written by an older version, or edited by hand into an invalid
    state, is skipped rather than surfaced: a malformed citation in a client
    report is worse than a missing one.
    """
    try:
        view = HouseView(
            **{field: record.get(field, "") for field in _FIELDS if field != "price_target"},
            price_target=record.get("price_target"),
            profile=tuple(tuple(row) for row in record.get("profile", ())),
            notes=tuple(record.get("notes", ())),
        )
        view.validate()
    except (TypeError, ValueError):
        return None
    return view


def save(view: HouseView, path: Path | None = None) -> None:
    """Record a house's current view, superseding any earlier one from it."""
    view.validate()
    target = path or store_path()
    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = _load(target)
        data[_key(view.house, view.ticker)] = {
            **{field: getattr(view, field) for field in _FIELDS},
            "profile": [list(row) for row in view.profile],
            "notes": list(view.notes),
        }
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def remove(house: str, ticker: str, path: Path | None = None) -> bool:
    """Drop a stored view. Returns whether there was one to drop."""
    target = path or store_path()
    with _lock:
        data = _load(target)
        if data.pop(_key(house, ticker), None) is None:
            return False
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return True


def for_ticker(ticker: str, path: Path | None = None) -> tuple[HouseView, ...]:
    """Every stored view for one security, house name order."""
    wanted = ticker.strip().upper()
    if not wanted:
        return ()
    views = [
        view
        for record in _load(path or store_path()).values()
        if (view := _to_view(record)) is not None and view.ticker.strip().upper() == wanted
    ]
    return tuple(sorted(views, key=lambda v: v.house.casefold()))


def all_views(path: Path | None = None) -> tuple[HouseView, ...]:
    views = [v for record in _load(path or store_path()).values() if (v := _to_view(record))]
    return tuple(sorted(views, key=lambda v: (v.ticker.upper(), v.house.casefold())))


def freshness(view: HouseView, as_of: str) -> tuple[str, bool]:
    """How the view's age reads, and whether it counts as stale.

    Age is always stated. A reader weighing a price target needs to know whether
    it was published last week or last year, and a rating with no age beside it
    silently reads as current.
    """
    age = view.age_days(as_of)
    if age is None:
        return "publication date not readable", True
    if age < 0:
        return f"published {abs(age)} days after the analysis date", True
    if age == 0:
        return "published today", False
    if age == 1:
        return "published yesterday", False
    if age < 45:
        return f"published {age} days ago", False
    months = round(age / 30.4)
    return f"published about {months} month{'s' if months != 1 else ''} ago", age > STALE_AFTER_DAYS
