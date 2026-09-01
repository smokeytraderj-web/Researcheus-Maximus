"""In-memory research job registry for the web backend.

Research takes minutes, so the HTTP layer cannot run it inline: a job is
started in a worker thread, the client polls for status, and the finished
report is served from the job record. Jobs live in process memory only --
nothing is persisted, matching the desktop app's disposable-session rule.
"""

from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

JobStatus = Literal["running", "ready", "failed"]

# A finished report is kept only long enough for the user to open and read it.
# Nothing here is a retained artifact; the desktop app's exported HTML remains
# the record copy.
JOB_TTL = timedelta(hours=2)


@dataclass
class ResearchJob:
    id: str
    mode: str
    prompt: str
    status: JobStatus = "running"
    stage: str = "Preparing evidence"
    error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Populated once the run succeeds.
    report_path: Path | None = None
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
    """Thread-safe store for in-flight and finished research jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, ResearchJob] = {}
        self._lock = threading.Lock()

    def create(self, mode: str, prompt: str) -> ResearchJob:
        job = ResearchJob(id=uuid.uuid4().hex[:12], mode=mode, prompt=prompt)
        with self._lock:
            self._jobs[job.id] = job
        self.purge_expired()
        return job

    def get(self, job_id: str) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job and job.expired:
            self.discard(job_id)
            return None
        return job

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def discard(self, job_id: str) -> None:
        """Drop a job and delete whatever temporary session it still holds."""
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and job.session_root:
            shutil.rmtree(job.session_root, ignore_errors=True)

    def purge_expired(self) -> None:
        with self._lock:
            stale = [job_id for job_id, job in self._jobs.items() if job.expired]
        for job_id in stale:
            self.discard(job_id)

    def shutdown(self) -> None:
        """Delete every session directory still held. Called on app shutdown."""
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for job in jobs:
            if job.session_root:
                shutil.rmtree(job.session_root, ignore_errors=True)


registry = JobRegistry()
