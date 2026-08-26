import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from core.models import Horizon, ResearchRequest
from services.research_runner import ResearchRunner


class ResearchRunnerTests(unittest.TestCase):
    def test_prepare_and_finalize_demo_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runner = ResearchRunner(session_root=root / "sessions")
            prepared = runner.prepare(ResearchRequest("AXON", Horizon.MEDIUM, 300, 10))
            session_path = prepared.session.root
            self.assertTrue(prepared.preview_path.is_file())
            reader = PdfReader(prepared.preview_path)
            self.assertEqual(len(reader.pages), 2)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("OVERALL RATING", report_text)
            self.assertIn("TECHNICAL SETUP", report_text)
            self.assertIn("FUNDAMENTAL OUTLOOK", report_text)
            self.assertNotIn("LEAD\n", report_text)
            final = runner.finalize(prepared, root / "output")
            self.assertTrue(final.is_file())
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
            runner.cancel(prepared)


if __name__ == "__main__":
    unittest.main()
