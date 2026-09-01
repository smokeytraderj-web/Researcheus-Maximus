"""Researcheus Maximus web backend.

Serves the same research workflows as the PySide6 desktop app over HTTP. The
desktop app is unchanged and still runs standalone; both surfaces call the same
core (`core.request_builder` -> `services.*Runner` -> `reports.*`), so a
question asked here and the same question asked in the desktop window produce
the same report.

Run locally:
    uvicorn backend.app:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.jobs import registry
from core.request_builder import build_request
from services.research_runner import ResearchRunner
from services.technical_runner import TechnicalRunner

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
REPORTS_ROOT = ROOT / "output" / "web-sessions"

RESEARCH_MODES = {"general", "deep", "comparison"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    # Clear anything a previous crash left behind, mirroring the desktop app's
    # startup purge of abandoned sessions.
    for stale in REPORTS_ROOT.iterdir():
        if stale.is_dir():
            import shutil

            shutil.rmtree(stale, ignore_errors=True)
    yield
    registry.shutdown()


app = FastAPI(title="Researcheus Maximus", lifespan=lifespan)


class ResearchStart(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    mode: str = "general"


def _live_provider():
    """A live provider when the server is configured for it, else None.

    Keys come from the server environment only. The browser never sends a key
    and the API never accepts one -- credentials must not travel over this
    boundary (CLAUDE.md: never request credentials through custom UI).
    """
    api_key = os.environ.get("RESEARCHEUS_API_KEY", "").strip()
    if not api_key:
        return None
    from research.live_provider import LiveResearchProvider

    return LiveResearchProvider(
        os.environ.get("RESEARCHEUS_SYNTHESIS_PROVIDER", "OpenAI"),
        api_key,
        os.environ.get("RESEARCHEUS_MODEL", "").strip(),
        False,  # YCharts needs desktop Excel; unavailable to a web server.
        os.environ.get("RESEARCHEUS_TVREMIX_KEY", "").strip(),
    )


def _run_research(job_id: str, prompt: str, mode: str) -> None:
    """Execute one research run in a worker thread."""
    job_dir = REPORTS_ROOT / job_id
    try:
        request = build_request(prompt, mode)
        registry.update(job_id, stage="Retrieving evidence")
        runner = ResearchRunner(provider=_live_provider())
        prepared = runner.prepare(request)
        registry.update(job_id, stage="Building the report", session_root=prepared.session.root)
        job_dir.mkdir(parents=True, exist_ok=True)
        report = runner.finalize(prepared, job_dir)
        result = prepared.result
        registry.update(
            job_id,
            status="ready",
            stage="Ready",
            report_path=report,
            session_root=job_dir,
            ticker=result.identity.ticker,
            company_name=result.identity.company_name,
            rating=result.lead_rating.value,
            demo_mode=result.demo_mode,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as a message
        logger.exception("Research job %s failed", job_id)
        # The message is shown to the user; never leak a traceback or a path.
        registry.update(job_id, status="failed", stage="Failed", error=str(exc) or "Research failed.")


def _run_technical(job_id: str, prompt: str) -> None:
    """Execute one Technical Quick Report run in a worker thread."""
    job_dir = REPORTS_ROOT / job_id
    try:
        api_key = os.environ.get("RESEARCHEUS_TVREMIX_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "The Technical Quick Report needs a TV Remix key configured on the server."
            )
        registry.update(job_id, stage="Reading technical structure")
        prepared = TechnicalRunner(api_key=api_key).prepare(prompt)
        job_dir.mkdir(parents=True, exist_ok=True)
        destination = job_dir / "report.html"
        destination.write_bytes(prepared.interactive_path.read_bytes())
        prepared.session.cleanup()
        report = prepared.report
        registry.update(
            job_id,
            status="ready",
            stage="Ready",
            report_path=destination,
            session_root=job_dir,
            ticker=getattr(report, "resolved_symbol", ""),
            company_name=getattr(report, "company_name", ""),
            demo_mode=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Technical job %s failed", job_id)
        registry.update(job_id, status="failed", stage="Failed", error=str(exc) or "Research failed.")


@app.post("/api/research")
def start_research(body: ResearchStart) -> dict:
    """Start a research run and return its job id immediately."""
    mode = body.mode.strip().lower()
    if mode not in RESEARCH_MODES and mode != "technical":
        raise HTTPException(400, f"Unknown research mode: {body.mode}")
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Enter a company name or ticker.")
    job = registry.create(mode, prompt)
    target = _run_technical if mode == "technical" else _run_research
    args = (job.id, prompt) if mode == "technical" else (job.id, prompt, mode)
    threading.Thread(target=target, args=args, daemon=True).start()
    return job.public()


@app.get("/api/research/{job_id}")
def research_status(job_id: str) -> dict:
    job = registry.get(job_id)
    if not job:
        raise HTTPException(404, "That research run is no longer available.")
    return job.public()


@app.get("/r/{job_id}", response_class=HTMLResponse)
def view_report(job_id: str) -> FileResponse:
    """Serve the finished report -- this is the shareable link."""
    job = registry.get(job_id)
    if not job or job.status != "ready" or not job.report_path:
        raise HTTPException(404, "That report is no longer available.")
    if not job.report_path.is_file():
        raise HTTPException(404, "That report is no longer available.")
    return FileResponse(job.report_path, media_type="text/html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "live_research": _live_provider() is not None}


# The frontend is served last so /api and /r win over the static mount.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
