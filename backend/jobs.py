"""Research job tracking and finished-report storage for the web backend.

Reports are **temporary by default**. They are written to the system temp
directory -- never into the project -- expire after REPORT_TTL, and the whole
directory is deleted when the server stops. Nothing accumulates, matching the
desktop app's disposable-session rule, where the report the user deliberately
exports is the only retained artifact.

The consequence is deliberate and worth stating: a shared link is good for the
lifetime of the server plus the TTL, not forever. Set RESEARCHEUS_KEEP_REPORTS=1
to keep reports instead, which is what a hosted deployment with a mounted volume
wants.

Two lifetimes are kept apart within that:

* The **job record** is in-memory progress state, only so the browser can poll
  a run it just started.
* The **report file** outlives the job record, so a link still resolves after
  the run has been forgotten -- until it expires or the server stops.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

JobStatus = Literal["running", "ready", "failed"]

# How long a *job record* stays pollable. Not how long a report lives.
JOB_TTL = timedelta(hours=6)

# How long a finished report survives before it is deleted. Reports are
# temporary unless RESEARCHEUS_KEEP_REPORTS is set.
REPORT_TTL = timedelta(hours=int(os.environ.get("RESEARCHEUS_REPORT_TTL_HOURS", "6")))
KEEP_REPORTS = os.environ.get("RESEARCHEUS_KEEP_REPORTS", "").strip().lower() in {"1", "true", "yes"}


def default_reports_root() -> Path:
    """Where reports are written.

    The system temp directory, not the project: a research tool should not
    silently accumulate client-question output inside the user's source tree.
    A deployment that wants durable links overrides this with
    RESEARCHEUS_REPORTS_DIR and mounts a volume there.
    """
    override = os.environ.get("RESEARCHEUS_REPORTS_DIR", "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "researcheus-reports"


def purge_expired_reports(reports_root: Path) -> int:
    """Delete reports past REPORT_TTL. Returns how many went."""
    if KEEP_REPORTS or not reports_root.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - REPORT_TTL
    removed = 0
    for entry in reports_root.iterdir():
        if not entry.is_dir():
            continue
        modified = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed


def discard_all_reports(reports_root: Path) -> None:
    """Delete every report. Called on shutdown so nothing is left behind."""
    if KEEP_REPORTS:
        return
    shutil.rmtree(reports_root, ignore_errors=True)

# Job ids are generated here and also arrive from the URL, where they index
# straight into the reports directory -- so they must be validated as opaque
# hex before ever touching the filesystem.
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def is_valid_job_id(value: str) -> bool:
    return bool(JOB_ID_PATTERN.match(value))


def report_dir(reports_root: Path, job_id: str) -> Path | None:
    """The directory holding one job's report, or None if the id is not safe."""
    if not is_valid_job_id(job_id):
        return None
    return reports_root / job_id


def find_report(reports_root: Path, job_id: str) -> Path | None:
    """Locate a finished report on disk, independent of the job registry.

    This is what keeps a shared link alive: the report is found by looking in
    the filesystem, so it still resolves once the in-memory job has expired or
    the server has been restarted.
    """
    directory = report_dir(reports_root, job_id)
    if directory is None or not directory.is_dir():
        return None
    reports = sorted(directory.glob("*.html"))
    return reports[0] if reports else None


def list_reports(reports_root: Path, limit: int = 50) -> list[dict]:
    """Finished reports on disk, newest first.

    Read from the filesystem rather than the job registry so the list survives
    a restart -- the same reason /r/{id} resolves from disk.
    """
    if not reports_root.is_dir():
        return []
    found: list[tuple[float, dict]] = []
    for entry in reports_root.iterdir():
        if not entry.is_dir() or not is_valid_job_id(entry.name):
            continue
        reports = sorted(entry.glob("*.html"))
        if not reports:
            continue
        report = reports[0]
        modified = report.stat().st_mtime
        found.append(
            (
                modified,
                {
                    "id": entry.name,
                    # The exported filename already carries ticker and report
                    # type ("AXON_Medium_Term_Research.html").
                    "title": report.stem.replace("_", " "),
                    "created_at": datetime.fromtimestamp(modified, timezone.utc).isoformat(),
                    "report_url": f"/r/{entry.name}",
                },
            )
        )
    found.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in found[:limit]]


def purge_incomplete(reports_root: Path) -> None:
    """Remove crash leftovers: job directories holding no finished report.

    Finished reports are deliberately preserved -- deleting them would break
    every link already shared.
    """
    if not reports_root.is_dir():
        return
    for entry in reports_root.iterdir():
        if entry.is_dir() and not any(entry.glob("*.html")):
            shutil.rmtree(entry, ignore_errors=True)


@dataclass
class ResearchJob:
    id: str
    mode: str
    prompt: str
    status: JobStatus = "running"
    stage: str = "Preparing evidence"
    error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Temporary session directory for an in-flight run, deleted when it ends.
    session_root: Path | None = None
    ticker: str = ""
    company_name: str = ""
    rating: str = ""
    demo_mode: bool = True

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) - self.created_at > JOB_TTL

    def public(self) -> dict:
        """The client-visible view. Never exposes filesystem paths."""
        data = {
            "id": self.id,
            "mode": self.mode,
            "status": self.status,
            "stage": self.stage,
            "created_at": self.created_at.isoformat(),
        }
        if self.status == "ready":
            data.update(
                {
                    "ticker": self.ticker,
                    "company_name": self.company_name,
                    "rating": self.rating,
                    "demo_mode": self.demo_mode,
                    "report_url": f"/r/{self.id}",
                }
            )
        elif self.status == "failed":
            data["error"] = self.error
        return data


class JobRegistry:
    """Thread-safe store of in-flight and recently finished job records."""

    def __init__(self) -> None:
        self._jobs: dict[str, ResearchJob] = {}
        self._lock = threading.Lock()

    def create(self, mode: str, prompt: str) -> ResearchJob:
        job = ResearchJob(id=new_job_id(), mode=mode, prompt=prompt)
        with self._lock:
            self._jobs[job.id] = job
        self.purge_expired()
        return job

    def get(self, job_id: str) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job and job.expired:
            self.forget(job_id)
            return None
        return job

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def release_session(self, job_id: str) -> None:
        """Delete a job's temporary session directory, keeping its report."""
        with self._lock:
            job = self._jobs.get(job_id)
            session_root = job.session_root if job else None
            if job:
                job.session_root = None
        if session_root:
            shutil.rmtree(session_root, ignore_errors=True)

    def forget(self, job_id: str) -> None:
        """Drop a job record. The finished report on disk is left in place."""
        self.release_session(job_id)
        with self._lock:
            self._jobs.pop(job_id, None)

    def purge_expired(self) -> None:
        with self._lock:
            stale = [job_id for job_id, job in self._jobs.items() if job.expired]
        for job_id in stale:
            self.forget(job_id)

    def shutdown(self) -> None:
        """Release temporary sessions on shutdown. Reports are preserved."""
        with self._lock:
            job_ids = list(self._jobs)
        for job_id in job_ids:
            self.release_session(job_id)


registry = JobRegistry()
