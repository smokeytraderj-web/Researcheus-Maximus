"""Orchestrate the standalone Technical Analysis feature (TV Remix only, disposable session)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from core.models import TVTechnicalReport
from core.session import ResearchSession
from reports.tvremix_report import build_tvremix_html
from research.tvremix_charts import render_tvremix_price_chart, render_tvremix_sparkline
from research.tvremix_provider import fetch_tvremix_technical_report
from services.research_runner import _safe_name, _verify_html


@dataclass(frozen=True, slots=True)
class PreparedTechnical:
    session: ResearchSession
    query: str
    report: TVTechnicalReport
    interactive_path: Path
    suggested_html_filename: str


class TechnicalRunner:
    def __init__(self, api_key: str = "", session_root: Path | None = None):
        self.api_key = api_key
        self.session_root = session_root

    def prepare(self, query: str) -> PreparedTechnical:
        query = query.strip()
        if not query:
            raise ValueError("Enter a ticker or company name.")
        session = ResearchSession.create(self.session_root)
        try:
            report, bars = fetch_tvremix_technical_report(query, self.api_key)
            if not report.available:
                raise RuntimeError(report.error or "TV Remix did not return usable technical data.")
            if bars:
                price_path = render_tvremix_price_chart(
                    bars, report.levels, report.current_price, report.resolved_symbol.split(":")[-1], session.working / "price.png"
                )
                sparkline_path = render_tvremix_sparkline(bars, session.working / "sparkline.png")
                report = replace(report, price_chart_path=str(price_path), sparkline_path=str(sparkline_path))
            interactive = session.preview / "technical_analysis.html"
            build_tvremix_html(report, interactive)
            _verify_html(interactive)
            filename = _safe_name(f"{report.resolved_symbol.split(':')[-1]}_Technical_Analysis.html")
            return PreparedTechnical(session, query, report, interactive, filename)
        except Exception:
            session.cleanup()
            raise

    def finalize(self, prepared: PreparedTechnical) -> None:
        prepared.session.cleanup()

    def cancel(self, prepared: PreparedTechnical) -> None:
        prepared.session.cleanup()
