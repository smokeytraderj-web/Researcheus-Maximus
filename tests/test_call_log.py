import csv
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from core.models import Horizon, ResearchRequest
from reports.call_log import CALL_LOG_FILENAME, append_call
from research.demo_provider import DemoResearchProvider
from services.research_runner import ResearchRunner


def _result(query="AAPL", question="Should I buy?"):
    request = ResearchRequest(query=query, horizon=Horizon.MEDIUM, question=question)
    with tempfile.TemporaryDirectory() as work:
        return request, DemoResearchProvider().run(request, Path(work))


class CallLogTests(unittest.TestCase):
    def test_appends_rows_under_a_single_header(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for ticker in ("AAPL", "MSFT", "NVDA"):
                request, result = _result(ticker)
                append_call(directory, result, request)
            with (directory / CALL_LOG_FILENAME).open() as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 3)
        self.assertEqual((directory / CALL_LOG_FILENAME).name, "researcheus_call_log.csv")

    def test_records_the_call_and_nothing_sensitive(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            request, result = _result(question="I hold 4000 shares at $180, should I add?")
            log = append_call(directory, result, request)
            text = log.read_text(encoding="utf-8")
            with log.open() as handle:
                row = list(csv.DictReader(handle))[0]

        self.assertEqual(row["ticker"], result.identity.ticker)
        self.assertEqual(row["rating"], result.lead_rating.value)
        self.assertEqual(row["confidence"], result.confidence.value)
        # The question carried position detail; none of it may reach the log.
        self.assertNotIn("4000", text)
        self.assertNotIn("180", text.replace(row["price"], ""))
        self.assertNotIn("should I add", text)

    def test_finalize_skips_demo_runs_so_the_record_stays_real(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            runner = ResearchRunner(provider=DemoResearchProvider())
            prepared = runner.prepare(ResearchRequest(query="AAPL", horizon=Horizon.MEDIUM, question="Buy?"))
            self.assertTrue(prepared.result.demo_mode)
            runner.finalize(prepared, out)
            self.assertFalse((out / CALL_LOG_FILENAME).exists())

    def test_finalize_logs_a_live_run(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            runner = ResearchRunner(provider=DemoResearchProvider())
            prepared = runner.prepare(ResearchRequest(query="AAPL", horizon=Horizon.MEDIUM, question="Buy?"))
            prepared = replace(prepared, result=replace(prepared.result, demo_mode=False))
            runner.finalize(prepared, out)
            self.assertTrue((out / CALL_LOG_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
