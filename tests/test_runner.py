import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from pypdf import PdfReader

from core.models import Horizon, ResearchRequest, SourceRecord
from services.research_runner import ResearchRunner
from research.demo_provider import DemoResearchProvider


class _OperationalLimitationProvider:
    def run(self, request, workspace=None):
        result = DemoResearchProvider().run(request, workspace)
        return replace(
            result,
            limitations=(
                "No AI research provider was available; fundamental and sentiment coverage is reduced.",
                "The installed YCharts add-in was detected but returned no usable metrics.",
                'YCharts consensus rating was unavailable: Excel returned #NAME?. Cell F2: =YCI("TSLA","consensus_recommendation_label")',
            ),
        )


class _ManySourcesProvider:
    def run(self, request, workspace=None):
        result = DemoResearchProvider().run(request, workspace)
        return replace(
            result,
            sources=tuple(
                SourceRecord(
                    f"Source {index}",
                    f"https://example.com/source-{index}",
                    result.as_of,
                    f"Evidence area {index}",
                )
                for index in range(1, 9)
            ),
        )


class ResearchRunnerTests(unittest.TestCase):
    def test_prepare_and_finalize_demo_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runner = ResearchRunner(session_root=root / "sessions")
            prepared = runner.prepare(
                ResearchRequest("AXON", Horizon.MEDIUM, 300, 10, question="Give me a report on AXON.")
            )
            session_path = prepared.session.root
            self.assertTrue(prepared.preview_path.is_file())
            self.assertTrue(prepared.interactive_path.is_file())
            interactive = prepared.interactive_path.read_text(encoding="utf-8")
            self.assertIn("General Research", interactive)
            self.assertIn("The answer", interactive)
            self.assertIn("Give me a report on AXON.", interactive)
            self.assertIn("Direct answer", interactive)
            self.assertIn("data:image/png;base64,", interactive)
            self.assertNotIn("Scenario tester", interactive)
            reader = PdfReader(prepared.preview_path)
            self.assertEqual(len(reader.pages), 3)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            first_page = reader.pages[0].extract_text() or ""
            second_page = reader.pages[1].extract_text() or ""
            final_page = reader.pages[-1].extract_text() or ""
            self.assertIn("Researcheus Maximus", first_page)
            self.assertIn("CLIENT Q&A BRIEF", first_page)
            self.assertIn("THE QUESTION", first_page)
            self.assertIn("Give me a report on AXON.", first_page)
            self.assertIn("OUR ANSWER", first_page)
            self.assertIn("OVERALL VIEW", first_page)
            self.assertIn("WHY THIS ANSWER", first_page)
            self.assertNotIn("OVERALL RATING", first_page)
            self.assertNotIn("TECHNICAL SETUP", first_page)
            self.assertNotIn("FUNDAMENTAL OUTLOOK", first_page)
            self.assertNotIn("Annotated Price Structure", first_page)
            self.assertNotIn("KEY CHART TAKEAWAYS", report_text)
            self.assertNotIn("WHAT THIS CHART SHOWS", report_text)
            self.assertIn("What To Do Now", second_page)
            self.assertIn("ACTION PLAN", second_page)
            self.assertIn("POSITION", second_page)
            self.assertIn("ENTRY", second_page)
            self.assertIn("STOP", second_page)
            self.assertIn("TARGETS", second_page)
            self.assertIn("CONFIRMATION", second_page)
            self.assertIn("INVALIDATION", second_page)
            self.assertNotIn("OPTIONS / HEDGE", report_text)
            self.assertIn("Evidence Behind the Answer", final_page)
            self.assertIn("KEY EVIDENCE", final_page)
            self.assertIn("ESSENTIAL FACTS", final_page)
            self.assertIn("Sources", final_page)
            self.assertIn("Disclosure:", final_page)
            self.assertNotIn("Sources", "\n".join(page.extract_text() or "" for page in reader.pages[:-1]))
            self.assertNotIn("Possible Investment Approaches", report_text)
            self.assertNotIn("Interpretation:", report_text)
            self.assertNotIn("LEAD\n", report_text)
            final = runner.finalize(prepared, root / "output")
            self.assertTrue(final.is_file())
            self.assertEqual(final.suffix, ".html")
            self.assertFalse(session_path.exists())

    def test_cancel_cleans_session(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(session_root=Path(folder))
            prepared = runner.prepare(ResearchRequest("Apple", Horizon.LONG))
            session_path = prepared.session.root
            runner.cancel(prepared)
            self.assertFalse(session_path.exists())

    def test_exports_use_versioned_filenames(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runner = ResearchRunner(session_root=root / "sessions")
            first = runner.prepare(ResearchRequest("WMT", Horizon.SHORT))
            first_path = runner.finalize(first, root / "output")
            second = runner.prepare(ResearchRequest("WMT", Horizon.SHORT))
            second_path = runner.finalize(second, root / "output")
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(second_path.stem.endswith("_v2"))

    def test_deep_analysis_uses_distinct_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(session_root=Path(folder))
            prepared = runner.prepare(
                ResearchRequest(
                    "AXON",
                    Horizon.ALL,
                    deep_analysis=True,
                    comparison_symbols=("SPY",),
                    requested_charts=("price_trend", "momentum", "relative_performance"),
                )
            )
            self.assertEqual(prepared.suggested_filename, "AXON_Deep_Technical_Analysis.pdf")
            self.assertEqual(prepared.suggested_html_filename, "AXON_Deep_Technical_Analysis.html")
            interactive = prepared.interactive_path.read_text(encoding="utf-8")
            self.assertIn("Technical Research", interactive)
            self.assertIn("Scenario tester", interactive)
            self.assertIn("Price structure", interactive)
            self.assertIn("Momentum", interactive)
            self.assertIn("Relative strength", interactive)
            self.assertIn("Fibonacci", interactive)
            self.assertIn("data:image/png;base64,", interactive)
            reader = PdfReader(prepared.preview_path)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            first_page = reader.pages[0].extract_text() or ""
            second_page = reader.pages[1].extract_text() or ""
            self.assertIn("TECHNICAL RESEARCH", first_page)
            self.assertIn("THE CALL", first_page)
            self.assertIn("PRICE STRUCTURE", first_page)
            self.assertNotIn("OVERALL RATING", first_page)
            self.assertIn("Position and Risk Plan", second_page)
            self.assertIn("ACTION PLAN", second_page)
            self.assertIn("Momentum - RSI and MACD", report_text)
            self.assertIn("Relative Performance", report_text)
            self.assertIn("Fibonacci Structure", report_text)
            self.assertIn("Sources and Disclosure", reader.pages[-1].extract_text() or "")
            self.assertNotIn(
                "Sources and Disclosure",
                "\n".join(page.extract_text() or "" for page in reader.pages[:-1]),
            )
            runner.cancel(prepared)

    def test_explicit_lead_chart_appears_after_the_direct_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(session_root=Path(folder))
            prepared = runner.prepare(
                ResearchRequest(
                    "AXON",
                    Horizon.ALL,
                    question="Show a Fibonacci chart and explain the setup.",
                    overview_chart="fibonacci",
                )
            )
            reader = PdfReader(prepared.preview_path)
            first_page = reader.pages[0].extract_text() or ""
            second_page = reader.pages[1].extract_text() or ""
            self.assertNotIn("Fibonacci Structure", first_page)
            self.assertIn("Fibonacci Structure", second_page)
            self.assertNotIn("WHAT THIS CHART SHOWS", second_page)
            runner.cancel(prepared)

    def test_explicit_stop_loss_chart_leads_with_structural_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(session_root=Path(folder))
            prepared = runner.prepare(
                ResearchRequest(
                    "AXON",
                    Horizon.ALL,
                    question="Show a stop-loss chart and explain the evidence.",
                    overview_chart="stop_loss",
                )
            )
            reader = PdfReader(prepared.preview_path)
            first_page = reader.pages[0].extract_text() or ""
            second_page = reader.pages[1].extract_text() or ""
            self.assertNotIn("Stop-Loss Evidence", first_page)
            self.assertIn("Stop-Loss Evidence", second_page)
            runner.cancel(prepared)

    def test_options_only_appear_when_the_general_prompt_requests_them(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(session_root=Path(folder))
            prepared = runner.prepare(
                ResearchRequest(
                    "AXON",
                    Horizon.ALL,
                    question="Should I buy AXON, and what defined-risk options strategy could I use?",
                )
            )
            reader = PdfReader(prepared.preview_path)
            self.assertEqual(len(reader.pages), 3)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("OPTIONS / HEDGE", reader.pages[1].extract_text() or "")
            self.assertIn("Options involve leverage", report_text)
            runner.cancel(prepared)

    def test_comparison_uses_two_ticker_filename_and_dedicated_sources_page(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(session_root=Path(folder))
            prepared = runner.prepare(
                ResearchRequest(
                    "AVGO",
                    Horizon.ALL,
                    comparison_analysis=True,
                    comparison_query="NVDA",
                    question="Which currently offers better value?",
                )
            )
            self.assertEqual(prepared.suggested_filename, "AVGO_vs_NVDA_Security_Comparison.pdf")
            reader = PdfReader(prepared.preview_path)
            self.assertEqual(len(reader.pages), 4)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("CURRENT EVIDENCE PREFERENCE", report_text)
            self.assertIn("Side-by-Side Evidence", report_text)
            self.assertIn("Sources and Disclosure", reader.pages[-1].extract_text() or "")
            self.assertNotIn("Confidence:", report_text)
            runner.cancel(prepared)

    def test_client_pdf_omits_operational_provider_and_excel_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(
                provider=_OperationalLimitationProvider(),
                session_root=Path(folder),
            )
            prepared = runner.prepare(ResearchRequest("TSLA", Horizon.ALL))
            report_text = "\n".join(
                page.extract_text() or "" for page in PdfReader(prepared.preview_path).pages
            )
            self.assertNotIn("No AI research provider", report_text)
            self.assertNotIn("YCharts add-in", report_text)
            self.assertNotIn("#NAME?", report_text)
            runner.cancel(prepared)

    def test_full_source_list_is_confined_to_the_final_page(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = ResearchRunner(provider=_ManySourcesProvider(), session_root=Path(folder))
            prepared = runner.prepare(ResearchRequest("AXON", Horizon.ALL))
            reader = PdfReader(prepared.preview_path)
            self.assertEqual(len(reader.pages), 3)
            final_page = reader.pages[-1].extract_text() or ""
            earlier_pages = "\n".join(page.extract_text() or "" for page in reader.pages[:-1])
            self.assertIn("Evidence Behind the Answer", final_page)
            self.assertIn("Source 1", final_page)
            self.assertIn("Source 8", final_page)
            self.assertNotIn("Source 1", earlier_pages)
            self.assertNotIn("Disclosure:", earlier_pages)
            runner.cancel(prepared)


if __name__ == "__main__":
    unittest.main()
