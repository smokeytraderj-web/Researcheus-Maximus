"""Technical Analyst Agent web backend.

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import feedback as feedback_store
from backend import gate
from backend.credentials import load as load_credentials
from backend.jobs import (
    KEEP_REPORTS,
    default_reports_root,
    discard_all_reports,
    find_report,
    purge_expired_reports,
    purge_incomplete,
    registry,
)
from core.request_builder import build_request
from services.research_runner import ResearchRunner
from services.technical_runner import TechnicalRunner

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
# Reports go to the system temp directory, not into the project. Overridable
# with RESEARCHEUS_REPORTS_DIR for a deployment that mounts a volume.
REPORTS_ROOT = default_reports_root()

RESEARCH_MODES = {"general", "deep", "comparison"}

# Each run is CPU- and network-heavy and holds a worker thread for minutes.
# Without a cap, a handful of impatient clicks would exhaust the machine and
# make every run slower, so excess requests are refused with a clear message
# rather than silently queued behind an invisible backlog.
MAX_CONCURRENT_RUNS = int(os.environ.get("RESEARCHEUS_MAX_CONCURRENT_RUNS", "3"))
_run_slots = threading.Semaphore(MAX_CONCURRENT_RUNS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    # Crash leftovers (directories with no finished report) always go. Expired
    # reports go too unless the operator asked to keep them.
    purge_incomplete(REPORTS_ROOT)
    purge_expired_reports(REPORTS_ROOT)
    yield
    registry.shutdown()
    # Reports are temporary: leave nothing behind on the way out.
    discard_all_reports(REPORTS_ROOT)


app = FastAPI(title="Technical Analyst Agent", lifespan=lifespan)


# Paths that must answer before anyone has entered the code: the gate itself,
# the assets it is drawn with, liveness, and the report links -- which are the
# client-facing deliverable and are opened by people who do not have the code.
GATE_EXEMPT_PREFIXES = ("/api/unlock", "/api/health", "/r/", "/vendor/", "/unlock.html")


def _is_exempt(path: str) -> bool:
    return path.startswith(GATE_EXEMPT_PREFIXES)


@app.middleware("http")
async def require_access_code(request: Request, call_next):
    """Hold everything except the exempt paths behind the shared access code."""
    if _is_exempt(request.url.path) or gate.token_valid(request.cookies.get(gate.COOKIE_NAME, "")):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Enter the access code to continue."}, status_code=401)
    # Serve the gate in place, so the address the reader typed still stands
    # once they are through it.
    return FileResponse(WEB_DIR / "unlock.html", media_type="text/html", status_code=401)


class UnlockIn(BaseModel):
    code: str = Field(default="", max_length=32)


@app.post("/api/unlock")
def unlock(body: UnlockIn, request: Request) -> JSONResponse:
    """Exchange the shared code for a signed, expiring access cookie."""
    client = request.client.host if request.client else "unknown"
    if gate.locked_out(client):
        raise HTTPException(429, "Too many attempts. Try again later.")
    if not gate.code_matches(body.code):
        gate.record_failure(client)
        raise HTTPException(401, "That code was not recognised.")
    gate.clear_failures(client)
    response = JSONResponse({"unlocked": True})
    response.set_cookie(
        gate.COOKIE_NAME,
        gate.issue_token(),
        max_age=gate.TOKEN_TTL,
        httponly=True,
        samesite="lax",
        # Railway terminates TLS in front of the app and forwards over plain
        # HTTP, so the request's own scheme reads "http" there. The forwarded
        # header is what says how the browser actually connected.
        secure=(
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
        ),
    )
    return response


class ResearchStart(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    mode: str = "general"


class FeedbackIn(BaseModel):
    message: str = Field(default="", max_length=4000)
    helpful: bool | None = None
    job_id: str = Field(default="", max_length=64)


def _provider():
    """The research provider: live by default, demo only when forced.

    Keys are resolved server-side (environment, else the same OS keychain the
    desktop app uses). The browser never sends a key and the API never accepts
    one -- credentials must not travel over this boundary.
    """
    credentials = load_credentials()
    if not credentials.live_research:
        from research.demo_provider import DemoResearchProvider

        return DemoResearchProvider()
    from research.live_provider import LiveResearchProvider

    return LiveResearchProvider(
        credentials.provider,
        credentials.synthesis_key,
        credentials.model,
        False,  # YCharts needs desktop Excel; unavailable to a web server.
        credentials.tvremix_key,
    )


def _tvremix_key() -> str:
    return load_credentials().tvremix_key


def _discard_failed(job_id: str, job_dir: Path) -> None:
    """Drop a failed run's temporary session and its empty output directory."""
    import shutil

    registry.release_session(job_id)
    shutil.rmtree(job_dir, ignore_errors=True)


def _run_research(job_id: str, prompt: str, mode: str) -> None:
    """Execute one research run in a worker thread."""
    job_dir = REPORTS_ROOT / job_id
    try:
        request = build_request(prompt, mode)
        registry.update(job_id, stage="Retrieving evidence")
        runner = ResearchRunner(provider=_provider())
        prepared = runner.prepare(request)
        registry.update(job_id, stage="Building the report", session_root=prepared.session.root)
        job_dir.mkdir(parents=True, exist_ok=True)
        runner.finalize(prepared, job_dir)
        result = prepared.result
        # finalize() already cleaned up the temporary session; the report now
        # lives in job_dir and is served from there by find_report().
        registry.update(
            job_id,
            status="ready",
            stage="Ready",
            session_root=None,
            ticker=result.identity.ticker,
            company_name=result.identity.company_name,
            rating=result.lead_rating.value,
            demo_mode=result.demo_mode,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as a message
        logger.exception("Research job %s failed", job_id)
        # The message is shown to the user; never leak a traceback or a path.
        registry.update(job_id, status="failed", stage="Failed", error=str(exc) or "Research failed.")
        _discard_failed(job_id, job_dir)
    finally:
        _run_slots.release()


def _run_technical(job_id: str, prompt: str) -> None:
    """Execute one Technical Quick Report run in a worker thread."""
    job_dir = REPORTS_ROOT / job_id
    try:
        api_key = _tvremix_key()
        if not api_key:
            raise RuntimeError(
                "The Technical Quick Report needs a TV Remix key configured on the server."
            )
        registry.update(job_id, stage="Reading technical structure")
        prepared = TechnicalRunner(api_key=api_key).prepare(prompt)
        registry.update(job_id, session_root=prepared.session.root)
        job_dir.mkdir(parents=True, exist_ok=True)
        destination = job_dir / prepared.suggested_html_filename
        destination.write_bytes(prepared.interactive_path.read_bytes())
        prepared.session.cleanup()
        report = prepared.report
        registry.update(
            job_id,
            status="ready",
            stage="Ready",
            session_root=None,
            ticker=getattr(report, "resolved_symbol", ""),
            company_name=getattr(report, "company_name", ""),
            demo_mode=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Technical job %s failed", job_id)
        registry.update(job_id, status="failed", stage="Failed", error=str(exc) or "Research failed.")
        _discard_failed(job_id, job_dir)
    finally:
        _run_slots.release()


@app.post("/api/research")
def start_research(body: ResearchStart) -> dict:
    """Start a research run and return its job id immediately."""
    mode = body.mode.strip().lower()
    if mode not in RESEARCH_MODES and mode != "technical":
        raise HTTPException(400, f"Unknown research mode: {body.mode}")
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Enter a company name or ticker.")
    purge_expired_reports(REPORTS_ROOT)
    if not _run_slots.acquire(blocking=False):
        raise HTTPException(
            503,
            f"{MAX_CONCURRENT_RUNS} research runs are already in progress. "
            "Wait for one to finish, then try again.",
        )
    try:
        job = registry.create(mode, prompt)
        target = _run_technical if mode == "technical" else _run_research
        args = (job.id, prompt) if mode == "technical" else (job.id, prompt, mode)
        threading.Thread(target=target, args=args, daemon=True).start()
    except Exception:
        # The worker never started, so nothing else will release the slot.
        _run_slots.release()
        raise
    return job.public()


@app.get("/api/research/{job_id}")
def research_status(job_id: str) -> dict:
    job = registry.get(job_id)
    if not job:
        raise HTTPException(404, "That research run is no longer available.")
    return job.public()


@app.get("/r/{job_id}")
def view_report(job_id: str) -> FileResponse:
    """Serve the finished report -- this is the shareable link.

    Resolved from disk rather than from the job registry, so a link keeps
    working after the in-memory job has expired and across server restarts.
    The id is validated as opaque hex before it reaches the filesystem.
    """
    report = find_report(REPORTS_ROOT, job_id)
    if report is None:
        raise HTTPException(404, "That report is no longer available.")
    return FileResponse(report, media_type="text/html")


@app.post("/api/feedback")
def submit_feedback(body: FeedbackIn) -> dict:
    """Record a reader's feedback on a report for later human review.

    This never alters a rating or an analysis. See backend/feedback.py.
    """
    if not body.message.strip() and body.helpful is None:
        raise HTTPException(400, "Add a comment or say whether the report helped.")
    job = registry.get(body.job_id) if body.job_id else None
    feedback_store.record(
        REPORTS_ROOT,
        message=body.message,
        helpful=body.helpful,
        job_id=body.job_id,
        ticker=job.ticker if job else "",
        mode=job.mode if job else "",
    )
    return {"recorded": True}


@app.get("/api/feedback")
def list_feedback() -> dict:
    """Everything recorded, for review. Counts plus the entries themselves."""
    return {"summary": feedback_store.summarise(REPORTS_ROOT), "entries": feedback_store.read_all(REPORTS_ROOT)}


@app.get("/api/health")
def health() -> dict:
    """Liveness, plus which workflows this server can actually run.

    The frontend uses this to say up front when a workflow is unavailable,
    rather than letting the user start a run that is certain to fail.
    """
    return {"status": "ok", "reports_retained": KEEP_REPORTS, **load_credentials().status()}


# The frontend is served last so /api and /r win over the static mount.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
