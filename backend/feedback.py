"""Feedback capture for the web app.

What this does: records what a reader says about a specific report, with the
report's ticker and mode for context, so the analysis can be reviewed and
improved deliberately. Optionally mirrors each entry into a Google Doc so the
log can be read without shell access to the server.

What this deliberately does NOT do: change any rating, threshold, or analysis
on its own. A research tool that silently rewired its own conclusions from
unvetted public input would be both easy to poison and impossible to audit --
and it would break the evidence rules the rest of the app is built on, where
every fact carries a source and generated prose is never evidence for another
step. Improvement happens by a person reading this and changing the code or the
rating policy, which is a reviewable change with a version behind it.

WHERE IT IS KEPT. Feedback used to be deleted along with the reports: shutdown
called rmtree on the whole reports directory, and the feedback file sat inside
it. It now lives in a reserved subdirectory that the report retention path skips
by name, so reports stay deliberately temporary while feedback does not.

That covers cleanup, not the host. The reports root defaults to the system temp
directory, which a container host wipes on restart, so on a platform that
redeploys by replacing the container feedback still needs somewhere to go:
either RESEARCHEUS_FEEDBACK_DIR pointing at a mounted volume, or the Google Doc
mirror below. Without one of those, a deploy still loses the file.

THE GOOGLE DOC. Set RESEARCHEUS_FEEDBACK_WEBHOOK to the URL of a Google Apps
Script web app bound to a document (see backend/README.md for the script). Each
entry is POSTed as JSON and appended to the doc. The local file stays the record
of truth: delivery is best-effort and a webhook that is down, slow, or
misconfigured can never lose an entry or fail a reader's request. Undelivered
entries are retried on the next submission and at startup, tracked by a cursor
into this append-only file -- no queue, no second store to keep consistent.

No credential ever reaches this module. An Apps Script web app is authorised by
its URL alone, which is why it is used here in preference to the Docs API: this
app holds no Google tokens and cannot act as the user.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.RLock()

MAX_MESSAGE = 4000
FEEDBACK_FILE = "feedback.jsonl"
# How many entries have been delivered to the webhook. The log is append-only,
# so a count is a complete description of what is left to send.
CURSOR_FILE = "feedback.delivered"
WEBHOOK_ENV = "RESEARCHEUS_FEEDBACK_WEBHOOK"
FEEDBACK_DIR_ENV = "RESEARCHEUS_FEEDBACK_DIR"
DELIVERY_TIMEOUT = 10
# A single submission should not turn into an unbounded catch-up run inside the
# request path.
MAX_CATCH_UP = 50


# Reserved: job ids are 12 hex characters, so this can never collide with one,
# and the retention path skips it by name.
FEEDBACK_DIRNAME = "_feedback"


def feedback_dir(reports_root: Path) -> Path:
    """Where feedback is kept. Inside the reports root, but exempt from its purge.

    Deliberately not a sibling of the reports root: the default root lives in the
    system temp directory, so a sibling is shared by every process that uses the
    default -- which in the test suite meant every test writing into one file.
    """
    override = os.environ.get(FEEDBACK_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return reports_root / FEEDBACK_DIRNAME


def webhook_url() -> str:
    return os.environ.get(WEBHOOK_ENV, "").strip()


def record(
    reports_root: Path,
    *,
    message: str,
    helpful: bool | None,
    job_id: str = "",
    ticker: str = "",
    mode: str = "",
) -> None:
    """Append one feedback entry, then try to mirror it. Never raises."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "helpful": helpful,
        "message": message.strip()[:MAX_MESSAGE],
        "job_id": job_id,
        "ticker": ticker,
        "mode": mode,
    }
    root = feedback_dir(reports_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        with _lock, (root / FEEDBACK_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        # Losing a feedback line must never fail the user's request.
        return
    # Delivery happens off the request path: the reader should not wait on, or
    # ever see, a third party being slow.
    if webhook_url():
        threading.Thread(target=flush, args=(reports_root,), daemon=True).start()


def _entries(root: Path) -> list[dict]:
    path = root / FEEDBACK_FILE
    if not path.is_file():
        return []
    entries: list[dict] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries


def _cursor(root: Path) -> int:
    try:
        return int((root / CURSOR_FILE).read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def _set_cursor(root: Path, value: int) -> None:
    try:
        (root / CURSOR_FILE).write_text(str(value), encoding="utf-8")
    except OSError:
        pass


def flush(reports_root: Path) -> int:
    """Send anything not yet delivered to the Doc. Returns how many went.

    Safe to call at any time and from anywhere: it takes the same lock as the
    writer, sends in order, and advances the cursor one entry at a time, so an
    interruption re-sends at most the entry that was in flight.
    """
    url = webhook_url()
    if not url:
        return 0
    root = feedback_dir(reports_root)
    with _lock:
        entries = _entries(root)
        start = min(_cursor(root), len(entries))
        pending = entries[start:start + MAX_CATCH_UP]
        sent = 0
        for offset, entry in enumerate(pending):
            if not _post(url, entry):
                break
            sent += 1
            _set_cursor(root, start + offset + 1)
    return sent


def _post(url: str, entry: dict) -> bool:
    """One delivery attempt. Any failure is reported, never raised."""
    payload = json.dumps(entry).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=DELIVERY_TIMEOUT) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def read_all(reports_root: Path, limit: int = 200) -> list[dict]:
    """Recorded feedback, newest first, for review."""
    return list(reversed(_entries(feedback_dir(reports_root))))[:limit]


def summarise(reports_root: Path) -> dict:
    """Counts only -- enough to see at a glance whether anything needs reading."""
    root = feedback_dir(reports_root)
    entries = _entries(root)
    return {
        "total": len(entries),
        "helpful": sum(1 for e in entries if e.get("helpful") is True),
        "unhelpful": sum(1 for e in entries if e.get("helpful") is False),
        "with_comment": sum(1 for e in entries if e.get("message")),
        "mirrored_to_doc": bool(webhook_url()),
        "awaiting_delivery": max(0, len(entries) - _cursor(root)) if webhook_url() else 0,
    }
