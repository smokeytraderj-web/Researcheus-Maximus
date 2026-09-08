"""Parse a J.P. Morgan Markets company page that a reader has copied.

WHY PASTE. The advisor is already on the page, signed in under their own
entitlement. Copying what is on screen needs no automation against the portal,
no credential, and no answer to the question of whether scraping it would be
permitted -- so this works today and stays clear of the access controls
entirely. An entitled API can replace this module later without touching
anything downstream.

WHAT IT WILL NOT DO. It does not guess. A field the text does not contain is
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

    def as_payload(self, house: str = "J.P. Morgan") -> dict:
        payload = {"house": house, **self.fields}
        payload["profile"] = [list(row) for row in self.profile]
        return payload


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

    for name, label in (
        ("ticker", "ticker"),
        ("equity_rating", "equity rating"),
        ("price_target", "price target"),
    ):
        if name not in parsed.fields:
            parsed.missing.append(label)
    if not parsed.profile:
        parsed.missing.append("equity profile")
    return parsed


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
