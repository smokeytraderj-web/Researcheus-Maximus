"""Feedback capture for the web app.

What this does: records what a reader says about a specific report, with the
report's ticker and mode for context, so the analysis can be reviewed and
improved deliberately.

What this deliberately does NOT do: change any rating, threshold, or analysis
on its own. A research tool that silently rewired its own conclusions from
unvetted public input would be both easy to poison and impossible to audit --
and it would break the evidence rules the rest of the app is built on, where
every fact carries a source and generated prose is never evidence for another
step. Improvement happens by a person reading this and changing the code or the
rating policy, which is a reviewable change with a version behind it.

Feedback is stored as JSON lines next to the reports, and is subject to the
same retention rule: temporary unless the operator opts into keeping it.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()

MAX_MESSAGE = 4000
FEEDBACK_FILE = "feedback.jsonl"


def record(
    root: Path,
    *,
    message: str,
    helpful: bool | None,
    job_id: str = "",
    ticker: str = "",
    mode: str = "",
) -> None:
    """Append one feedback entry. Never raises into the request path."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "helpful": helpful,
        "message": message.strip()[:MAX_MESSAGE],
        "job_id": job_id,
        "ticker": ticker,
        "mode": mode,
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        with _lock, (root / FEEDBACK_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        # Losing a feedback line must never fail the user's request.
        pass


def read_all(root: Path, limit: int = 200) -> list[dict]:
    """Recorded feedback, newest first, for review."""
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
    return list(reversed(entries))[:limit]


def summarise(root: Path) -> dict:
    """Counts only -- enough to see at a glance whether anything needs reading."""
    entries = read_all(root, limit=10_000)
    helpful = sum(1 for e in entries if e.get("helpful") is True)
    unhelpful = sum(1 for e in entries if e.get("helpful") is False)
    return {
        "total": len(entries),
        "helpful": helpful,
        "unhelpful": unhelpful,
        "with_comment": sum(1 for e in entries if e.get("message")),
    }
