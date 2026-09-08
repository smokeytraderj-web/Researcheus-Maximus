"""Read a J.P. Morgan Markets company page, however the reader got it here.

THREE WAYS IN, ORDERED BY PRECISION. parse_jpmm_payload takes the portal's own
JSON -- every figure already typed, already labelled, already carrying its
currency -- and is what the browser hand-off sends. parse_jpmm_page reads the
page's rendered text, which is what the same hand-off falls back to for the few
fields the JSON does not carry: sector, region, the analyst, and the latest
note. The same function reads a page the advisor copied by hand, which is where
this started and still works when everything else has moved.

They degrade in that order deliberately. A portal restyle breaks the text
reading and leaves the JSON standing; an endpoint that moves breaks the JSON
and leaves the text standing; both can go and paste still works.

NO CREDENTIAL, EITHER WAY. The advisor is signed in under their own entitlement
and the figures are read in their own session, on a page already open in front
of them. Nothing here accepts, holds, forwards or logs a cookie, a token or any
other session material -- see _reject_secrets, which refuses a payload carrying
anything shaped like one rather than quietly passing it along.

WHAT IT WILL NOT DO. It does not guess. A field the source does not contain is
reported missing, by name, rather than filled with a plausible value -- a
research note carrying a price target nobody published is worse than one
carrying none. Nothing is saved from here either: the parse is shown for
confirmation and a person presses save, which is the same gate the rest of the
app puts in front of evidence.

The analyst's email address is dropped rather than stored. It is personal data,
it is not evidence, and the report has no use for it.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

# Profile rows are "Label   value", where the value is the last whitespace-run
# on the line. Labels carry their own units -- "Market cap ($ mn)" -- and are
# kept verbatim so nothing is reinterpreted into a unit we assumed.
_PROFILE_LABELS = (
    "price ($)", "date of price", "market cap", "shares o/s", "free float",
    "3m adv", "52-week range", "volatility", "bbg anr",
)
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_MONEY = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
_PERCENT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%")
_RATINGS = ("overweight", "neutral", "underweight", "not rated", "not covered")
_NOTE_KINDS = r"Equity|Credit|Economics|Strategy"


@dataclass
class ParsedPage:
    """What the paste yielded, and what it did not."""

    fields: dict = field(default_factory=dict)
    profile: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    # The house's own forward estimates, as (metric, ((period, value), ...)).
    # Periods carry the portal's actual/estimate marker -- "FY26E", "FY25A" --
    # so a reader can tell a reported figure from a forecast one, which is the
    # distinction the source hierarchy turns on.
    estimates: list = field(default_factory=list)

    def as_payload(self, house: str = "J.P. Morgan") -> dict:
        payload = {"house": house, **self.fields}
        payload["profile"] = [list(row) for row in self.profile]
        payload["estimates"] = [[metric, [list(cell) for cell in cells]] for metric, cells in self.estimates]
        return payload


# Strip rows that are the view itself rather than a row of the profile beneath
# it. Matched on the whole label, never a prefix: "Price Target ($)" and
# "Price ($)" differ by one word and mean entirely different things, and the
# second is the figure the report compares against this analysis's own price.
_STRIP_FIELDS = {
    "equity rating": "equity_rating",
    "price target": "price_target",
    "price target ($)": "price_target",
    "price target end date": "target_horizon",
}

# Fields nothing downstream can proceed without. HouseView.validate refuses a
# view missing any of them, so they are named here rather than at the save --
# a reader can fix what they are told is absent before pressing the button.
_REQUIRED = (
    ("ticker", "ticker"),
    ("equity_rating", "equity rating"),
    ("price_target", "price target"),
    ("published", "publication date"),
)

# Anything shaped like session material. The hand-off sends evidence and only
# evidence; a payload carrying one of these is refused outright rather than
# stripped, because a sender that included one is not the sender we designed
# for and the rest of what it sent has not earned any trust either.
_SECRET_KEYS = re.compile(
    r"cookie|session|token|auth|credential|password|passwd|secret|bearer|jwt|apikey|api[_-]key|csrf|xsrf",
    re.IGNORECASE,
)


_LABEL_STOPS = ("sector", "region", "equity rating", "price target", "end date", "subscribe", "coverage")


# The portal writes dates as "06 Aug, 2026" and "01 Sep 26". Freshness is
# computed with date.fromisoformat, so a date left in the portal's format parses
# as nothing -- and every pasted view would be reported "publication date not
# readable" and flagged stale on arrival.
_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y",
                 "%b %d %Y", "%B %d %Y", "%Y-%m-%d")


def normalise_date(text: str) -> str:
    """A portal date as ISO, or the text unchanged when it is not a date.

    Unchanged rather than dropped: a value this does not recognise is still
    what the page said, and the reader can correct it before saving.
    """
    cleaned = re.sub(r"[,]", "", (text or "").strip())
    if not cleaned:
        return ""
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return text.strip()


def _labelled(line: str, label: str) -> str:
    """The value following "Label:" on a line, stopping at the next label."""
    match = re.search(rf"{re.escape(label)}\s*:\s*(.*)", line, re.IGNORECASE)
    if not match:
        return ""
    value = match.group(1).strip()
    for stop in _LABEL_STOPS:
        cut = re.search(rf"\s{{2,}}{re.escape(stop)}\s*:", value, re.IGNORECASE)
        if cut:
            value = value[: cut.start()].strip()
    return value


def _clean(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = _EMAIL.sub("", raw).strip()
        if line:
            lines.append(line)
    return lines


def _after(lines: list[str], index: int) -> str:
    """The value on this line after its label, or the next line if it is bare."""
    return lines[index + 1].strip() if index + 1 < len(lines) else ""


def _is_label(line: str) -> bool:
    """Whether a line is another label rather than a value belonging to one.

    A bare label must never be read as the value of the label above it: that is
    how "Shares O/S (mn)" becomes the market capitalisation.
    """
    low = line.casefold()
    return line.rstrip().endswith(":") or any(low.startswith(label) for label in _PROFILE_LABELS)


def _authors(parts: list[str]) -> str:
    """Author names the page broke onto their own lines, rejoined.

    The separators are lines in their own right there -- a "|" between date and
    byline, a "," between each name -- so they are dropped rather than kept.
    Nothing marks the end of the byline, so the separators do: every name after
    the first is introduced by one. Two names running with nothing between them
    means the byline ended at the first, and the second belongs to whatever
    follows -- the profile table, which was being credited as a co-author.
    """
    names: list[str] = []
    separated = True
    for part in parts:
        if part.strip(" ,|") == "":
            separated = True
            continue
        if not separated:
            break
        names.append(part.strip(" ,|"))
        separated = False
    return ", ".join(names)


def parse_jpmm_page(text: str) -> ParsedPage:
    """Read the company page as copied. Everything found is reported; nothing is invented."""
    lines = _clean(text)
    parsed = ParsedPage()
    joined = "\n".join(lines)

    for index, line in enumerate(lines):
        low = line.casefold()

        # Ticker line: "Axon (AXON US)". The name is optional because the
        # rendered page sets the ticker chip on its own line beneath the name,
        # where requiring one left the security unidentified -- the single field
        # nothing downstream can proceed without.
        if "ticker" not in parsed.fields:
            match = re.match(r"^(.{0,80}?)\s*\(([A-Z][A-Z0-9.\-]{0,9})\s+[A-Z]{2}\)\s*$", line)
            if match:
                parsed.fields["ticker"] = match.group(2)

        # Labels share lines with other labels and with UI chrome -- the real
        # page reads "SUBSCRIBE  Sector: ...  Region: ..." on one line -- so
        # these are searched for anywhere, and stop at the next label.
        for name, label in (("sector", "Sector"), ("region", "Region")):
            if name in parsed.fields:
                continue
            found = _labelled(line, label)
            # Copied off the page these read "Sector: Aerospace & Defense" on one
            # line. Read out of the rendered page the label stands alone and the
            # value is beneath it, exactly as "Equity Rating:" already does.
            if not found and re.fullmatch(rf"{label}\s*:", line.strip(), re.IGNORECASE):
                found = _after(lines, index)
            if found:
                parsed.fields[name] = found

        if low.startswith("equity rating"):
            # The value sits after the colon, or on the next line when the
            # label stands alone -- which is how the page actually renders it.
            value = _labelled(line, "Equity Rating") or _after(lines, index)
            if value:
                parsed.fields["equity_rating"] = value
        elif low.startswith("equity analyst"):
            parsed.fields["analyst"] = _after(lines, index)
        elif low.startswith("price target"):
            value = line.split(":", 1)[1].strip() if ":" in line else _after(lines, index)
            # Copied, the price and its upside share a line: "$755.00  45.7%
            # Upside". Rendered, the label, the price and the upside are three
            # separate lines -- so the two that follow are searched as well.
            window = " ".join((value, _after(lines, index), _after(lines, index + 1)))
            money = _MONEY.search(value) or _MONEY.search(window)
            if money:
                parsed.fields["price_target"] = float(money.group(1).replace(",", ""))
            upside = _PERCENT.search(window)
            if upside and "upside" in window.casefold():
                parsed.fields["upside_pct"] = float(upside.group(1)) / 100
        elif low.startswith("end date"):
            parsed.fields["target_horizon"] = line.strip()

        # Profile rows, label kept exactly as the portal states it.
        if any(low.startswith(label) for label in _PROFILE_LABELS):
            parts = re.split(r"\s{2,}|\t", line)
            if len(parts) >= 2 and parts[-1].strip():
                parsed.profile.append((parts[0].strip(), parts[-1].strip()))
            # Copying the table preserves its columns, so the value is the last
            # whitespace-run on the label's own line. Reading the rendered page
            # gives one value per line instead, and every row was being lost --
            # taking the house's quoted price with it, which is the figure the
            # report compares against this analysis's own.
            elif (below := _after(lines, index)) and not _is_label(below):
                parsed.profile.append((line.strip(), below))

    parsed.fields.update(_parse_note(lines, joined))
    # The page dates the note, not the rating. Defaulting the view's date to the
    # note's is the honest reading -- a rating shown beside a note published that
    # day is that day's view -- and it stays editable before saving.
    if "published" not in parsed.fields and parsed.fields.get("note_published"):
        parsed.fields["published"] = parsed.fields["note_published"]
    # "Date of price" is a portal date too, and reads better as one.
    parsed.profile = [
        (label, normalise_date(value) if label.casefold().startswith("date of price") else value)
        for label, value in parsed.profile
    ]

    parsed.missing = _missing(parsed)
    return parsed


def _missing(parsed: ParsedPage) -> list[str]:
    """What the source did not carry, by name. Never filled in, only reported."""
    missing = [label for name, label in _REQUIRED if not parsed.fields.get(name)]
    if not parsed.profile:
        missing.append("equity profile")
    return missing


def _parse_note(lines: list[str], joined: str) -> dict:
    """The latest note: its title, byline and the abstract shown beneath it."""
    note: dict = {}
    anchor = None
    for index, line in enumerate(lines):
        if "latest earnings-related note" in line.casefold() or line.casefold().startswith("latest note"):
            anchor = index
            break
    if anchor is None:
        return note
    # Title is the first line after the heading; the byline is the first line
    # that opens with a category and a date; the abstract is what sits between.
    # The window reaches past the byline because the rendered page spends a
    # line on each author and each separator between them.
    body = lines[anchor + 1:anchor + 14]
    if not body:
        return note
    note["note_title"] = body[0]
    summary: list[str] = []
    for offset, line in enumerate(body[1:], start=1):
        byline = re.match(
            r"^(Equity|Credit|Economics|Strategy)\s+(\d{1,2}\s+\w+,?\s+\d{4})\s*\|?\s*(.*)$",
            line,
        )
        if byline:
            note["note_kind"] = byline.group(1)
            note["note_published"] = normalise_date(byline.group(2))
            note["note_authors"] = byline.group(3).strip()
            break
        # The same byline, broken across lines by the rendered page. Without
        # this the note carries no date, so the view inherits none either and
        # every automatically read page arrives reported as stale.
        if re.fullmatch(_NOTE_KINDS, line) and offset + 1 < len(body) and re.fullmatch(
            r"\d{1,2}\s+\w+,?\s+\d{4}", body[offset + 1]
        ):
            note["note_kind"] = line
            note["note_published"] = normalise_date(body[offset + 1])
            note["note_authors"] = _authors(body[offset + 2:])
            break
        # Bounded independently of the window above: a page with no byline to
        # stop at should not absorb the whole widened window as its abstract.
        if len(summary) < 5:
            summary.append(line)
    if summary:
        note["note_summary"] = " ".join(summary).strip()
    return note


class SecretInPayload(ValueError):
    """Raised when a hand-off carries something shaped like session material."""


def _reject_secrets(payload) -> None:
    """Refuse a payload that carries a cookie, a token or anything like one.

    The browser hand-off has no reason to send session material and every
    reason not to: the advisor's entitlement stays in their browser, and the
    app is deliberately built so that losing it would cost nothing. This walks
    the whole structure rather than checking the top level, because a nested
    "headers" object is exactly where such a thing would arrive by accident.

    Refused rather than quietly dropped. A sender that included a credential is
    not the sender this was designed for, and the rest of what it sent has not
    earned any more trust than the part that was caught.
    """
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if _SECRET_KEYS.search(str(key)):
                    raise SecretInPayload(
                        f"The import carried a field named {key!r}. Nothing from the "
                        "portal's session belongs here, so none of it was read."
                    )
                stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)


def _estimates(rows) -> list:
    """The house's forward estimates, metric by metric, exactly as published.

    Values are kept as their display strings -- "2,084", "25.5%" -- rather than
    parsed into numbers. They arrive already formatted to the house's own
    precision and units, and re-deriving those is how a margin becomes a ratio.
    """
    out = []
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        metric = str(row.get("displayName", "")).strip()
        items = row.get("dataItems")
        if not metric or not isinstance(items, dict):
            continue
        cells = [
            (str(period).strip(), str((cell or {}).get("displayValue", "")).strip())
            for period, cell in items.items()
            if isinstance(cell, dict) and str(cell.get("displayValue", "")).strip()
        ]
        if cells:
            out.append((metric, tuple(cells)))
    return out


def parse_jpmm_payload(strip, estimates=(), text: str = "", ticker: str = "") -> ParsedPage:
    """Read the company page from the portal's own JSON, text filling the gaps.

    The strip is authoritative for every figure it carries. It states each one
    already typed, already labelled and already carrying its currency, where
    reading the same numbers out of rendered text recovers them from line order
    and loses them the day the portal restyles.

    It does not carry everything. Sector, region, the covering analyst and the
    latest note have no endpoint behind them, so the page text supplies those
    through the same parser that reads a copied page -- and where the two
    disagree on a figure, the strip wins, because it is the source the other one
    was a reading of.
    """
    _reject_secrets({"strip": strip, "estimates": estimates})
    parsed = parse_jpmm_page(text) if str(text).strip() else ParsedPage()

    profile: list[tuple[str, str]] = []
    for row in strip or ():
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", "")).strip()
        value = str(row.get("value", "")).strip()
        if not label or not value:
            continue
        name = _STRIP_FIELDS.get(label.casefold())
        if name == "price_target":
            money = _MONEY.search(value) or re.search(r"([\d,]+(?:\.\d+)?)", value)
            if money:
                parsed.fields["price_target"] = float(money.group(1).replace(",", ""))
            # The currency the target is quoted in, from the row quoting it,
            # rather than assumed from the label's dollar sign -- a target on a
            # foreign listing carries one and is not in dollars.
            currency = str(row.get("currency", "")).strip()
            if currency:
                parsed.fields["currency"] = currency
        elif name == "target_horizon":
            # Kept in the portal's own words. Nothing computes on it, and a date
            # rewritten into another format is a date this app has restated.
            parsed.fields["target_horizon"] = f"End date {value}"[:32]
        elif name:
            parsed.fields[name] = value
        else:
            profile.append(
                (label, normalise_date(value) if label.casefold().startswith("date of price") else value)
            )

    # The strip's profile replaces one read from the text, because the text was
    # a reading of it. A strip that carried no profile leaves the text's alone
    # rather than blanking it: a worse source is still better than none.
    if profile:
        parsed.profile = profile
    if str(ticker).strip():
        parsed.fields["ticker"] = str(ticker).strip().upper()
    parsed.estimates = _estimates(estimates)
    parsed.missing = _missing(parsed)
    return parsed
