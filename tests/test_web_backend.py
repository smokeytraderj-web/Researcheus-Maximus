"""The web backend must behave exactly like the desktop app it mirrors."""

from __future__ import annotations

import unittest
from datetime import timedelta

import tempfile
from pathlib import Path

from backend.jobs import (
    JOB_TTL,
    JobRegistry,
    find_report,
    is_valid_job_id,
    purge_incomplete,
)
from core.models import Horizon
from core.request_builder import build_general_request, build_request


class SharedRequestBuildingTests(unittest.TestCase):
    """A question must parse the same whichever surface it arrives through."""

    def test_general_request_reads_the_stated_horizon(self) -> None:
        request = build_request("Should I buy AXON for the long term?", "general")
        self.assertEqual(request.query, "AXON")
        self.assertEqual(request.horizon, Horizon.LONG)
        self.assertEqual(request.decision_intent, "buy")

    def test_horizon_defaults_to_all_when_unstated(self) -> None:
        self.assertEqual(build_general_request("AXON").horizon, Horizon.ALL)

    def test_comparison_request_carries_both_securities(self) -> None:
        request = build_request("AVGO vs NVDA - which is the better buy?", "comparison")
        self.assertTrue(request.comparison_analysis)
        self.assertTrue(request.comparison_query.strip())

    def test_deep_request_is_flagged_for_the_technical_workflow(self) -> None:
        self.assertTrue(build_request("AXON price structure", "deep").deep_analysis)

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_request("AXON", "portfolio")

    def test_empty_prompt_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_request("   ", "general")


class JobRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = JobRegistry()

    def test_job_starts_running_and_hides_internal_fields(self) -> None:
        job = self.registry.create("general", "AXON")
        public = job.public()
        self.assertEqual(public["status"], "running")
        # Filesystem paths must never reach the client.
        self.assertNotIn("session_root", public)
        self.assertNotIn("prompt", public)

    def test_ready_job_exposes_a_report_url(self) -> None:
        job = self.registry.create("general", "AXON")
        self.registry.update(job.id, status="ready", ticker="AXON", rating="Add")
        public = self.registry.get(job.id).public()
        self.assertEqual(public["report_url"], f"/r/{job.id}")
        self.assertEqual(public["rating"], "Add")

    def test_failed_job_reports_its_error(self) -> None:
        job = self.registry.create("general", "AXON")
        self.registry.update(job.id, status="failed", error="No data.")
        self.assertEqual(self.registry.get(job.id).public()["error"], "No data.")

    def test_expired_jobs_are_dropped(self) -> None:
        job = self.registry.create("general", "AXON")
        job.created_at -= JOB_TTL + timedelta(minutes=1)
        self.assertIsNone(self.registry.get(job.id))

    def test_unknown_job_is_absent(self) -> None:
        self.assertIsNone(self.registry.get("nope"))


class SharedReportLinkTests(unittest.TestCase):
    """A shared link must outlive the job record and the server process."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_report(self, job_id: str, name: str = "AXON_Research.html") -> Path:
        directory = self.root / job_id
        directory.mkdir(parents=True)
        report = directory / name
        report.write_text("<html></html>", encoding="utf-8")
        return report

    def test_report_is_found_without_any_job_record(self) -> None:
        # The registry is deliberately not involved: this is what makes a link
        # survive job expiry and a server restart.
        report = self._write_report("a1b2c3d4e5f6")
        self.assertEqual(find_report(self.root, "a1b2c3d4e5f6"), report)

    def test_missing_report_resolves_to_none(self) -> None:
        self.assertIsNone(find_report(self.root, "a1b2c3d4e5f6"))

    def test_startup_purge_keeps_finished_reports(self) -> None:
        self._write_report("a1b2c3d4e5f6")
        purge_incomplete(self.root)
        self.assertIsNotNone(find_report(self.root, "a1b2c3d4e5f6"))

    def test_startup_purge_removes_crash_leftovers(self) -> None:
        (self.root / "ffffffffffff").mkdir(parents=True)
        purge_incomplete(self.root)
        self.assertFalse((self.root / "ffffffffffff").exists())

    def test_job_ids_outside_the_hex_format_are_rejected(self) -> None:
        for bad in ("../../etc/passwd", "..", "a" * 13, "A1B2C3D4E5F6", "", "a1b2c3d4e5f/"):
            self.assertFalse(is_valid_job_id(bad), bad)

    def test_traversal_attempt_never_resolves_a_file(self) -> None:
        outside = self.root / "secret.html"
        outside.write_text("<html></html>", encoding="utf-8")
        self.assertIsNone(find_report(self.root / "jobs", "../secret"))


if __name__ == "__main__":
    unittest.main()
