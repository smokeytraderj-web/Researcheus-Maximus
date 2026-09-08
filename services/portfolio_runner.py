"""Run RM's existing engine once per holding, retaining its complete reports."""

from __future__ import annotations

import dataclasses
import math
import shutil
from pathlib import Path

from core.models import ChartRecord, ResearchRequest
from core.request_builder import build_request
from core.session import ResearchSession
from reports.html_report import build_research_html
from services.research_runner import _verify_html, _with_house_views


class PortfolioRunner:
    def __init__(self, provider_factory, session_root: Path | None = None):
        self.provider_factory = provider_factory
        self.session_root = session_root

    def research(self, holding: dict, weighting: str, mode: str, question: str,
                 output: Path) -> dict:
        ticker = holding["ticker"]
        # The ticker is bound explicitly: a question mentioning another holding
        # must never make the parser research that other security instead.
        brief = question.strip() or "Assess this existing holding and explain the investment view, evidence, risks and what would change the view."
        parsed = build_request(f"{ticker} - {brief}", mode)
        context = f"Existing holding: {ticker}. "
        if weighting == "weight":
            context += f"Portfolio weight: {holding['amount']:.4g}%. "
        request = dataclasses.replace(
            parsed, query=ticker, question=context + brief,
            quantity=holding["amount"] if weighting == "shares" else None,
            comparison_analysis=False, comparison_query="",
        )
        request.validate()
        session = ResearchSession.create(self.session_root)
        try:
            result = _with_house_views(self.provider_factory().run(request, session.working))
            result.validate()
            if result.identity.ticker.upper() != ticker:
                raise ValueError("The returned security differs from the entered ticker. Confirm its exact listing and rerun.")
            if result.identity.currency != "USD":
                raise ValueError("This version needs USD-listed holdings. Currency conversion is not available.")
            if not math.isfinite(result.current_price) or result.current_price <= 0:
                raise ValueError("No valid current price was returned.")
            output.mkdir(parents=True, exist_ok=True)
            report_path = output / "research.html"
            build_research_html(result, request, report_path)
            _verify_html(report_path)
            charts = []
            seen = set()
            candidates = [result.overview_chart]
            candidates += list(result.chartbook)
            if result.chart_path:
                candidates.append(ChartRecord("Price structure", result.chart_path, ""))
            for chart in candidates:
                if not chart or not chart.path or chart.path in seen:
                    continue
                source = Path(chart.path)
                if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
                    continue
                seen.add(chart.path)
                filename = f"chart-{len(charts)}{source.suffix.lower()}"
                shutil.copy2(source, output / filename)
                charts.append({"title": chart.title, "file": filename, "insight": chart.insight})
            return {
                "status": "ready", "ticker": ticker, "company_name": result.identity.company_name,
                "exchange": result.identity.exchange, "currency": result.identity.currency,
                "price": result.current_price, "as_of": result.as_of,
                "rating": result.lead_rating.value, "confidence": result.confidence.value,
                "summary": result.executive_summary, "answer": result.request_response,
                "technical": dataclasses.asdict(result.technical),
                "fundamental": dataclasses.asdict(result.fundamental),
                "metrics": result.key_metrics, "risks": result.risks,
                "catalysts": result.catalysts, "change_conditions": result.change_conditions,
                "sentiment": result.sentiment, "sources": [dataclasses.asdict(s) for s in result.sources],
                "limitations": result.limitations, "ycharts_status": result.ycharts_status,
                "plan": dataclasses.asdict(result.technical_plan) if result.technical_plan else None,
                "horizon_views": [dataclasses.asdict(h) for h in result.horizon_views],
                "demo_mode": result.demo_mode, "charts": charts,
            }
        except Exception:
            shutil.rmtree(output, ignore_errors=True)
            raise
        finally:
            session.cleanup()
