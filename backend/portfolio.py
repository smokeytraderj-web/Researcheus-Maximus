"""Protected portfolio jobs, incremental results and an offline research bundle."""

from __future__ import annotations

import copy
import dataclasses
import json
import logging
import re
import secrets
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.jobs import REPORT_TTL, purge_expired_reports
from core.portfolio import parse_holdings, summarize, validate_holdings
from services.portfolio_runner import PortfolioRunner

logger = logging.getLogger(__name__)


# The two tags the offline bundle inlines. Patterns rather than exact strings
# because both carry a ?v= cache-busting query that changes; module-level so the
# test guarding them and the code relying on them cannot drift apart.
STYLE_TAG = re.compile(r'<link rel="stylesheet" href="/portfolio\.css(?:\?[^"]*)?">')
SCRIPT_TAG = re.compile(r'<script src="/portfolio\.js(?:\?[^"]*)?" defer></script>')
ID = re.compile(r"^[0-9a-f]{32}$")
# Matplotlib has process-global state. Portfolio workers deliberately run one
# holding at a time and serialize across portfolio jobs as well.
_work_lock = threading.Lock()


class HoldingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ticker: str = Field(min_length=1, max_length=16)
    amount: float = Field(default=1, gt=0, le=1e12)


class PortfolioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positions: list[HoldingIn] = Field(min_length=1, max_length=50)
    weighting: Literal["weight", "value", "shares", "equal"] = "weight"
    mode: Literal["general", "deep"] = "deep"
    question: str = Field(default="", max_length=2000)


class ParseIn(BaseModel):
    text: str = Field(max_length=20_000)
    weighting: Literal["weight", "value", "shares", "equal"] = "weight"


def _check_question(question: str) -> None:
    prohibited = (
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", r"\b\d{3}-\d{2}-\d{4}\b",
        r"\b\d{8,}\b", r"\b(?:account|routing|password|api[ _-]?key|ssn|date of birth)\s*[:=#]",
        r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{10,}",
    )
    if any(re.search(pattern, question, re.I) for pattern in prohibited):
        raise ValueError("Remove client, account, contact and credential details. Include only the investment question.")


def _public(job: dict) -> dict:
    data = copy.deepcopy(job)
    data.pop("cancel", None)
    assessment = summarize(data["positions"], data["weighting"])
    data["positions"] = assessment.pop("positions")
    data["assessment"] = assessment
    data["demo_mode"] = any(p.get("demo_mode") for p in data["positions"])
    data["finished_count"] = sum(p["status"] in {"ready", "failed"} for p in data["positions"])
    return data


def attach_portfolio_routes(app, reports_root: Path, web_dir: Path, provider_factory, slots):
    router = APIRouter(prefix="/api/portfolio")
    jobs: dict[str, dict] = {}
    lock = threading.RLock()

    def get(job_id: str) -> dict:
        if not ID.fullmatch(job_id):
            raise HTTPException(404, "That portfolio is no longer available.")
        with lock:
            job = jobs.get(job_id)
            if job and job["status"] == "running":
                return _public(job)
            if job and datetime.now(timezone.utc) - datetime.fromisoformat(job["created_at"]) <= REPORT_TTL:
                return _public(job)
            jobs.pop(job_id, None)
        purge_expired_reports(reports_root)
        snapshot = reports_root / job_id / "portfolio.json"
        if snapshot.is_file():
            return json.loads(snapshot.read_text(encoding="utf-8"))
        raise HTTPException(404, "That portfolio is no longer available. Start a new review.")

    def worker(job_id: str):
        directory = reports_root / job_id
        try:
            with _work_lock:
                with lock:
                    job = jobs[job_id]
                    count = len(job["positions"])
                runner = PortfolioRunner(provider_factory)
                for index in range(count):
                    with lock:
                        if job["cancel"]:
                            break
                        position = copy.deepcopy(job["positions"][index])
                        if position["ticker"] == "CASH":
                            continue
                        job["stage"] = f"Researching {position['ticker']} · {index + 1} of {count}"
                        job["positions"][index]["status"] = "running"
                    try:
                        detail = runner.research(position, job["weighting"], job["mode"], job["question"], directory / f"position-{index}")
                        detail["report_url"] = f"/api/portfolio/{job_id}/positions/{index}/report"
                        for chart_index, chart in enumerate(detail["charts"]):
                            chart["url"] = f"/api/portfolio/{job_id}/positions/{index}/charts/{chart_index}"
                        # Catch non-JSON numeric evidence before publishing any result.
                        json.dumps(detail, allow_nan=False)
                        with lock:
                            job["positions"][index].update(detail)
                    except Exception as exc:
                        # Provider errors can include URLs, credentials or local paths.
                        # Do not expose or log the raw exception text.
                        logger.warning("Portfolio holding research failed (%s)", type(exc).__name__)
                        error = "Research could not be completed. Verify this USD ticker and retry; check the configured data providers if it persists."
                        if isinstance(exc, ValueError) and str(exc) in {
                            "The returned security differs from the entered ticker. Confirm its exact listing and rerun.",
                            "This version needs USD-listed holdings. Currency conversion is not available.",
                            "No valid current price was returned.",
                        }:
                            error = str(exc)
                        with lock:
                            job["positions"][index].update(status="failed", error=error)
                with lock:
                    if job["cancel"]:
                        job.update(status="cancelled", stage="Cancelled")
                        for position in job["positions"]:
                            if position["status"] in {"queued", "running"}:
                                position.update(status="failed", error="Research was cancelled.")
                        shutil.rmtree(directory, ignore_errors=True)
                    else:
                        failed = sum(p["status"] == "failed" for p in job["positions"])
                        job.update(status="partial" if failed else "ready", stage="Review incomplete holdings" if failed else "Research complete")
                        data = _public(job)
                        directory.mkdir(parents=True, exist_ok=True)
                        temporary = directory / "portfolio.json.tmp"
                        temporary.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
                        temporary.replace(directory / "portfolio.json")
        except Exception:
            logger.warning("Portfolio job could not finish")
            with lock:
                if job_id in jobs:
                    jobs[job_id].update(status="failed", stage="Unable to finish. Please retry.")
            shutil.rmtree(directory, ignore_errors=True)
        finally:
            slots.release()

    @router.post("/parse")
    def parse(body: ParseIn):
        try:
            holdings = parse_holdings(body.text, body.weighting)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"positions": [dataclasses.asdict(h) for h in holdings], "weighting": body.weighting}

    @router.post("")
    def start(body: PortfolioIn):
        try:
            holdings = validate_holdings([p.model_dump() for p in body.positions], body.weighting)
            _check_question(body.question)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not slots.acquire(blocking=False):
            raise HTTPException(503, "Research is at capacity. Wait for an active run to finish, then retry.")
        purge_expired_reports(reports_root)
        job_id = secrets.token_hex(16)
        job = {
            "id": job_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "weighting": body.weighting, "mode": body.mode, "question": body.question,
            "status": "running", "stage": "Preparing portfolio research", "cancel": False,
            "positions": [dict(dataclasses.asdict(h), status="ready" if h.ticker == "CASH" else "queued",
                               company_name="US dollar cash" if h.ticker == "CASH" else "") for h in holdings],
        }
        with lock:
            stale = [key for key, old in jobs.items() if old["status"] != "running" and datetime.now(timezone.utc) - datetime.fromisoformat(old["created_at"]) > REPORT_TTL]
            for key in stale:
                jobs.pop(key, None)
            jobs[job_id] = job
            initial = _public(job)
        try:
            threading.Thread(target=worker, args=(job_id,), daemon=True).start()
        except Exception:
            slots.release()
            with lock:
                jobs.pop(job_id, None)
            raise
        return initial

    @router.get("/{job_id}")
    def status(job_id: str):
        return get(job_id)

    @router.post("/{job_id}/cancel")
    def cancel(job_id: str):
        get(job_id)
        with lock:
            job = jobs.get(job_id)
            if job and job["status"] == "running":
                job["cancel"] = True
                job["stage"] = "Stopping after the current holding"
        return {"accepted": True}

    def position_for(job_id: str, index: int):
        data = get(job_id)
        if data["status"] == "cancelled" or not 0 <= index < len(data["positions"]):
            raise HTTPException(404, "That position is not available.")
        position = data["positions"][index]
        if position["status"] != "ready" or position["ticker"] == "CASH":
            raise HTTPException(404, "That position's research is not ready.")
        return position

    @router.get("/{job_id}/positions/{index}/report")
    def report(job_id: str, index: int, download: bool = False):
        position = position_for(job_id, index)
        path = reports_root / job_id / f"position-{index}" / "research.html"
        if not path.is_file():
            raise HTTPException(404, "That report has expired.")
        filename = f"{position['ticker']}_RM_Research.html" if download else None
        return FileResponse(path, media_type="text/html", filename=filename)

    @router.get("/{job_id}/positions/{index}/charts/{chart_index}")
    def chart(job_id: str, index: int, chart_index: int):
        position = position_for(job_id, index)
        if not 0 <= chart_index < len(position["charts"]):
            raise HTTPException(404, "That chart is unavailable.")
        path = reports_root / job_id / f"position-{index}" / position["charts"][chart_index]["file"]
        if not path.is_file():
            raise HTTPException(404, "That chart has expired.")
        return FileResponse(path)

    @router.get("/{job_id}/download")
    def download(job_id: str):
        data = get(job_id)
        if data["status"] not in {"ready", "partial"}:
            raise HTTPException(409, "Wait for research to finish before downloading.")
        directory = reports_root / job_id
        # Create a private, per-request zip to avoid concurrent writers.
        import tempfile
        from starlette.background import BackgroundTask

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
            destination = Path(handle.name)
        try:
            snapshot = copy.deepcopy(data)
            for index, position in enumerate(snapshot["positions"]):
                if position.get("report_url"):
                    position["report_url"] = f"position-{index}/research.html"
                for chart in position.get("charts", []):
                    chart["url"] = f"position-{index}/{chart['file']}"
            html = (web_dir / "portfolio.html").read_text(encoding="utf-8")
            html = html.replace('<link rel="stylesheet" href="/workspace-theme.css?v=1">', '<style>' + (web_dir / 'workspace-theme.css').read_text(encoding='utf-8') + '</style>')
            html = html.replace('href="/vendor/fonts/fonts.css"', 'href="fonts/fonts.css"')
            # Matched by pattern rather than by exact string. These two tags
            # carry a ?v= cache-busting query, and an exact match silently did
            # nothing once it appeared -- producing a bundle whose stylesheet
            # and script still pointed at absolute paths that do not exist
            # offline, and which carried no snapshot at all. A substitution
            # that has to happen should fail loudly when it cannot.
            html, styles = STYLE_TAG.subn(
                lambda _: "<style>" + (web_dir / "portfolio.css").read_text(encoding="utf-8") + "</style>",
                html,
            )
            payload = json.dumps(snapshot, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            html, scripts = SCRIPT_TAG.subn(
                lambda _: "<script>window.PORTFOLIO_SNAPSHOT=" + payload + ";</script><script>"
                + (web_dir / "portfolio.js").read_text(encoding="utf-8") + "</script>",
                html,
            )
            if not styles or not scripts:
                raise RuntimeError(
                    "The portfolio page no longer carries the stylesheet and script tags the "
                    "offline bundle inlines; a downloaded portfolio would not open."
                )
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("Portfolio_RM.html", html)
                for file in directory.glob("position-*/*"):
                    if file.is_file():
                        bundle.write(file, str(file.relative_to(directory)))
                for font in (web_dir / "vendor/fonts").iterdir():
                    if font.is_file():
                        bundle.write(font, "fonts/" + font.name)
            return FileResponse(destination, media_type="application/zip", filename="Portfolio_RM_Research.zip", background=BackgroundTask(destination.unlink, missing_ok=True))
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    app.include_router(router)

    def shutdown():
        with lock:
            for job in jobs.values():
                job["cancel"] = True

    return shutdown
