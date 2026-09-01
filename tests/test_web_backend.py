"""The web backend must behave exactly like the desktop app it mirrors."""

from __future__ import annotations

import unittest
from datetime import timedelta

from backend.jobs import JobRegistry
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
        self.assertNotIn("report_path", public)
        self.assertNotIn("session_root", public)

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
        job.created_at -= timedelta(hours=3)
        self.assertIsNone(self.registry.get(job.id))

    def test_unknown_job_is_absent(self) -> None:
        self.assertIsNone(self.registry.get("nope"))


if __name__ == "__main__":
    unittest.main()
