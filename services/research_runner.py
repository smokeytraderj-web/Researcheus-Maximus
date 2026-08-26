"""Orchestrate a disposable research session and final PDF export."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from core.models import ResearchRequest, ResearchResult
from core.session import ResearchSession
from reports.pdf_report import build_research_pdf
from research.demo_provider import DemoResearchProvider


@dataclass(frozen=True, slots=True)
class PreparedResearch:
    session: ResearchSession
    request: ResearchRequest
    result: ResearchResult
    preview_path: Path
    suggested_filename: str


def _safe_name(value: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return clean or "Stock_Research"


def _versioned_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    version = 2
    while True:
        candidate = directory / f"{stem}_v{version}{suffix}"
        if not candidate.exists():
            return candidate
        version += 1


def _verify_pdf(path: Path) -> int:
    if not path.is_file() or path.stat().st_size < 500:
        raise RuntimeError("The generated PDF is missing or incomplete.")
    reader = PdfReader(path)
    if not reader.pages:
        raise RuntimeError("The generated PDF has no pages.")
    return len(reader.pages)


class ResearchRunner:
    def __init__(self, provider=None, session_root: Path | None = None):
        self.provider = provider or DemoResearchProvider()
        self.session_root = session_root

    def prepare(self, request: ResearchRequest) -> PreparedResearch:
        request.validate()
        session = ResearchSession.create(self.session_root)
        try:
            result = self.provider.run(request, session.working)
            preview = session.preview / "research.pdf"
            build_research_pdf(result, request, preview)
            _verify_pdf(preview)
            if request.comparison_analysis and result.comparison:
                filename = _safe_name(
                    f"{result.identity.ticker}_vs_{result.comparison.secondary_identity.ticker}_Security_Comparison.pdf"
                )
            else:
                report_name = "Deep_Technical_Analysis" if request.deep_analysis else f"{request.horizon.value}_Research"
                filename = _safe_name(f"{result.identity.ticker}_{report_name}.pdf")
            return PreparedResearch(session, request, result, preview, filename)
        except Exception:
            session.cleanup()
            raise

    def finalize(self, prepared: PreparedResearch, output_directory: Path) -> Path:
        _verify_pdf(prepared.preview_path)
        output_directory.mkdir(parents=True, exist_ok=True)
        final_path = _versioned_path(output_directory, prepared.suggested_filename)
        shutil.copy2(prepared.preview_path, final_path)
        try:
            _verify_pdf(final_path)
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
        prepared.session.cleanup()
        return final_path

    def cancel(self, prepared: PreparedResearch) -> None:
        prepared.session.cleanup()
