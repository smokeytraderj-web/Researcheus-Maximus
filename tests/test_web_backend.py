"""The web backend must behave exactly like the desktop app it mirrors."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import os
import tempfile
from pathlib import Path
from unittest import mock

from backend.jobs import (
    JOB_TTL,
    REPORT_TTL,
    JobRegistry,
    default_reports_root,
    discard_all_reports,
    find_report,
    is_valid_job_id,
    list_reports,
    purge_expired_reports,
    purge_incomplete,
)
from backend import feedback as feedback_store
from backend.credentials import SYNTHESIS_ENV, TVREMIX_ENV
from backend.credentials import load as load_credentials
from core.models import Horizon
from core.request_builder import build_general_request, build_request
from research.live_provider import _eps_revision, _recent_growth, _return_on_equity
from security import secret_store

import pandas as pd


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

    def test_listing_is_newest_first_and_titled_from_the_filename(self) -> None:
        older = self._write_report("a" * 12, "AXON_Long_Term_Research.html")
        newer = self._write_report("b" * 12, "NVDA_Deep_Technical_Analysis.html")
        os.utime(older, (1_000_000, 1_000_000))
        os.utime(newer, (2_000_000, 2_000_000))
        listed = list_reports(self.root)
        self.assertEqual([item["title"] for item in listed],
                         ["NVDA Deep Technical Analysis", "AXON Long Term Research"])
        self.assertEqual(listed[0]["report_url"], "/r/" + "b" * 12)

    def test_listing_ignores_unfinished_and_foreign_directories(self) -> None:
        (self.root / ("c" * 12)).mkdir()        # no report yet
        (self.root / "not-a-job-id").mkdir()    # not ours
        self._write_report("d" * 12)
        listed = list_reports(self.root)
        self.assertEqual([item["id"] for item in listed], ["d" * 12])

    def test_listing_is_empty_when_nothing_has_been_produced(self) -> None:
        self.assertEqual(list_reports(self.root), [])

    def test_reports_default_to_the_temp_directory_not_the_project(self) -> None:
        # A research tool must not silently accumulate output inside the repo.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESEARCHEUS_REPORTS_DIR", None)
            root = default_reports_root()
        self.assertTrue(str(root).startswith(tempfile.gettempdir()))
        self.assertNotIn("Researcheus-Maximus", str(root))

    def test_reports_directory_can_be_overridden_for_deployment(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCHEUS_REPORTS_DIR": "/srv/reports"}):
            self.assertEqual(default_reports_root(), Path("/srv/reports"))

    def test_expired_reports_are_deleted(self) -> None:
        fresh = self._write_report("a" * 12)
        stale = self._write_report("b" * 12)
        old = (datetime.now(timezone.utc) - REPORT_TTL - timedelta(hours=1)).timestamp()
        os.utime(stale.parent, (old, old))
        removed = purge_expired_reports(self.root)
        self.assertEqual(removed, 1)
        self.assertTrue(fresh.exists())
        self.assertFalse(stale.parent.exists())

    def test_shutdown_leaves_nothing_behind(self) -> None:
        self._write_report("a" * 12)
        discard_all_reports(self.root)
        self.assertFalse(self.root.exists())


class CredentialResolutionTests(unittest.TestCase):
    """The web server must find the same keys the desktop app remembers."""

    def setUp(self) -> None:
        self._env = {k: os.environ.get(k) for k in (SYNTHESIS_ENV, TVREMIX_ENV)}
        for key in self._env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_environment_key_is_used_and_reported(self) -> None:
        os.environ[SYNTHESIS_ENV] = "env-value"
        credentials = load_credentials()
        self.assertEqual(credentials.synthesis_key, "env-value")
        self.assertEqual(credentials.synthesis_source, "environment")
        self.assertTrue(credentials.live_research)

    def test_keychain_is_consulted_when_the_environment_is_empty(self) -> None:
        with mock.patch.object(secret_store, "load_secret", return_value="stored-value"):
            credentials = load_credentials()
        self.assertEqual(credentials.synthesis_key, "stored-value")
        self.assertEqual(credentials.synthesis_source, "keychain")

    def test_environment_wins_over_the_keychain(self) -> None:
        os.environ[TVREMIX_ENV] = "env-value"
        with mock.patch.object(secret_store, "load_secret", return_value="stored-value"):
            credentials = load_credentials()
        self.assertEqual(credentials.tvremix_key, "env-value")
        self.assertEqual(credentials.tvremix_source, "environment")

    def test_live_research_does_not_require_an_ai_key(self) -> None:
        # Market data comes from yfinance and TV Remix; the synthesis key only
        # buys an AI-written narrative. Gating live mode on it served synthetic
        # numbers to real questions, which is the worst failure this app has.
        with mock.patch.object(secret_store, "load_secret", return_value=""):
            credentials = load_credentials()
        self.assertTrue(credentials.live_research)
        self.assertFalse(credentials.ai_synthesis)
        self.assertFalse(credentials.technical_research)
        self.assertEqual(credentials.synthesis_source, "none")

    def test_demo_is_only_ever_explicit(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCHEUS_DEMO": "1"}):
            self.assertFalse(load_credentials().live_research)
        with mock.patch.dict(os.environ, {"RESEARCHEUS_DEMO": "0"}):
            self.assertTrue(load_credentials().live_research)

    def test_status_never_exposes_a_key(self) -> None:
        os.environ[SYNTHESIS_ENV] = "super-secret-value"
        os.environ[TVREMIX_ENV] = "another-secret"
        status = load_credentials().status()
        rendered = repr(status)
        self.assertNotIn("super-secret-value", rendered)
        self.assertNotIn("another-secret", rendered)
        self.assertTrue(status["live_research"])


class GrowthFreshnessTests(unittest.TestCase):
    """Growth must be the most recent year-over-year figure, and say so.

    Growth is no longer a Conviction Checklist criterion (policy v2), but it is
    still reported in the fundamental section, so its freshness rules still hold.
    """

    def test_quarterly_year_over_year_is_preferred_over_the_annual_figure(self) -> None:
        # Four quarters back is the same quarter a year earlier.
        frame = pd.DataFrame(
            [[200.0, 180.0, 160.0, 140.0, 100.0], [40.0, 36.0, 32.0, 28.0, 20.0]],
            index=["Total Revenue", "Net Income"],
            columns=pd.to_datetime(
                ["2026-04-30", "2026-01-31", "2025-10-31", "2025-07-31", "2025-04-30"]
            ),
        )
        ticker = mock.Mock(quarterly_income_stmt=frame)
        # The annual figure is deliberately different, so preferring it would show.
        info = {"revenueGrowth": 9.99, "earningsGrowth": 9.99}
        revenue, earnings, period = _recent_growth(ticker, info)
        self.assertAlmostEqual(revenue, 1.0)   # 200 vs 100
        self.assertAlmostEqual(earnings, 1.0)  # 40 vs 20
        self.assertIn("most recent quarter", period)
        self.assertIn("2026-04-30", period)

    def test_annual_figure_is_the_labelled_fallback(self) -> None:
        ticker = mock.Mock(quarterly_income_stmt=pd.DataFrame())
        info = {"revenueGrowth": 0.12, "earningsGrowth": 0.20, "lastFiscalYearEnd": 1769299200}
        revenue, earnings, period = _recent_growth(ticker, info)
        self.assertEqual(revenue, 0.12)
        self.assertEqual(earnings, 0.20)
        self.assertIn("fiscal year ended", period)

    def test_negative_base_is_reported_as_unavailable_not_as_growth(self) -> None:
        frame = pd.DataFrame(
            [[200.0, 180.0, 160.0, 140.0, 100.0], [40.0, 36.0, 32.0, 28.0, -20.0]],
            index=["Total Revenue", "Net Income"],
            columns=pd.to_datetime(
                ["2026-04-30", "2026-01-31", "2025-10-31", "2025-07-31", "2025-04-30"]
            ),
        )
        ticker = mock.Mock(quarterly_income_stmt=frame)
        _revenue, earnings, _period = _recent_growth(ticker, {})
        # Growth off a negative base is meaningless, not merely large.
        self.assertIsNone(earnings)


class EpsRevisionTests(unittest.TestCase):
    """The Revisions criterion compares next-year consensus against an earlier date."""

    @staticmethod
    def _trend_frame(**rows) -> pd.DataFrame:
        return pd.DataFrame(rows, index=["current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo"]).T

    def test_next_fiscal_year_estimate_is_read_against_ninety_days_ago(self) -> None:
        frame = self._trend_frame(
            **{"0y": [8.81, 8.80, 8.76, 8.75, 8.75], "+1y": [9.53, 9.53, 9.71, 9.67, 9.65]}
        )
        now, prior, window = _eps_revision(mock.Mock(eps_trend=frame))
        # The next full year, not the current one which is largely locked in.
        self.assertAlmostEqual(now, 9.53)
        self.assertAlmostEqual(prior, 9.65)
        self.assertEqual(window, 90)

    def test_zero_is_treated_as_no_estimate_and_a_shorter_window_is_used(self) -> None:
        # Paramount's real shape: 0.0 at 60 and 90 days is a null written as a
        # number, not a forecast of breaking even. Taking it at face value would
        # compare against an estimate that was never made.
        frame = self._trend_frame(**{"+1y": [-7.38, -14.6, -14.6, 0.0, 0.0]})
        now, prior, window = _eps_revision(mock.Mock(eps_trend=frame))
        self.assertAlmostEqual(now, -7.38)
        self.assertAlmostEqual(prior, -14.6)
        self.assertEqual(window, 30)

    def test_current_year_is_the_fallback_when_next_year_is_absent(self) -> None:
        frame = self._trend_frame(**{"0y": [8.81, 8.80, 8.76, 8.75, 8.70]})
        now, prior, window = _eps_revision(mock.Mock(eps_trend=frame))
        self.assertAlmostEqual(now, 8.81)
        self.assertAlmostEqual(prior, 8.70)
        self.assertEqual(window, 90)

    def test_missing_frame_or_period_is_unavailable_never_guessed(self) -> None:
        self.assertEqual(_eps_revision(mock.Mock(eps_trend=None)), (None, None, 0))
        self.assertEqual(_eps_revision(mock.Mock(eps_trend=pd.DataFrame())), (None, None, 0))
        only_quarters = self._trend_frame(**{"0q": [1.0, 1.0, 1.0, 1.0, 1.0]})
        self.assertEqual(_eps_revision(mock.Mock(eps_trend=only_quarters)), (None, None, 0))

    def test_a_provider_error_is_not_an_error(self) -> None:
        broken = mock.Mock()
        type(broken).eps_trend = mock.PropertyMock(side_effect=RuntimeError("upstream down"))
        self.assertEqual(_eps_revision(broken), (None, None, 0))

    def test_all_prior_columns_unusable_is_unavailable(self) -> None:
        frame = self._trend_frame(**{"+1y": [9.5, 0.0, 0.0, 0.0, float("nan")]})
        self.assertEqual(_eps_revision(mock.Mock(eps_trend=frame)), (None, None, 0))


class ReturnOnEquityTests(unittest.TestCase):
    """Quality falls back to the statements rather than reporting nothing."""

    @staticmethod
    def _balance(equity: float) -> pd.DataFrame:
        return pd.DataFrame(
            [[equity, equity * 0.9]],
            index=["Stockholders Equity"],
            columns=pd.to_datetime(["2026-06-30", "2026-03-31"]),
        )

    def test_summary_field_is_used_when_present(self) -> None:
        ticker = mock.Mock(quarterly_balance_sheet=self._balance(1_000.0))
        self.assertAlmostEqual(_return_on_equity(ticker, {"returnOnEquity": 0.42}), 0.42)

    def test_derived_from_net_income_and_equity_when_the_summary_is_missing(self) -> None:
        ticker = mock.Mock(quarterly_balance_sheet=self._balance(1_000.0))
        self.assertAlmostEqual(_return_on_equity(ticker, {"netIncomeToCommon": 250.0}), 0.25)

    def test_negative_equity_is_unavailable_not_a_wild_ratio(self) -> None:
        ticker = mock.Mock(quarterly_balance_sheet=self._balance(-500.0))
        self.assertIsNone(_return_on_equity(ticker, {"netIncomeToCommon": 250.0}))

    def test_no_inputs_at_all_is_unavailable(self) -> None:
        ticker = mock.Mock(quarterly_balance_sheet=pd.DataFrame())
        self.assertIsNone(_return_on_equity(ticker, {}))


class FeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_feedback_is_recorded_with_report_context(self) -> None:
        feedback_store.record(
            self.root, message="Growth looked stale", helpful=False,
            job_id="a" * 12, ticker="NVDA", mode="general",
        )
        entries = feedback_store.read_all(self.root)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ticker"], "NVDA")
        self.assertFalse(entries[0]["helpful"])

    def test_newest_feedback_comes_first(self) -> None:
        feedback_store.record(self.root, message="first", helpful=True)
        feedback_store.record(self.root, message="second", helpful=True)
        self.assertEqual(feedback_store.read_all(self.root)[0]["message"], "second")

    def test_summary_counts_both_directions(self) -> None:
        feedback_store.record(self.root, message="", helpful=True)
        feedback_store.record(self.root, message="bad", helpful=False)
        summary = feedback_store.summarise(self.root)
        self.assertEqual(summary, {"total": 2, "helpful": 1, "unhelpful": 1, "with_comment": 1})

    def test_overlong_message_is_truncated_not_rejected(self) -> None:
        feedback_store.record(self.root, message="x" * 10_000, helpful=None)
        self.assertLessEqual(len(feedback_store.read_all(self.root)[0]["message"]), feedback_store.MAX_MESSAGE)

    def test_reading_before_anything_is_written_is_empty(self) -> None:
        self.assertEqual(feedback_store.read_all(self.root), [])
        self.assertEqual(feedback_store.summarise(self.root)["total"], 0)

    def test_a_corrupt_line_does_not_lose_the_rest(self) -> None:
        feedback_store.record(self.root, message="good", helpful=True)
        with (self.root / feedback_store.FEEDBACK_FILE).open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        self.assertEqual(len(feedback_store.read_all(self.root)), 1)


if __name__ == "__main__":
    unittest.main()
