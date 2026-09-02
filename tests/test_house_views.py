import tempfile
import unittest
from pathlib import Path

from core.models import HouseView
from research import house_views


def _view(**overrides) -> HouseView:
    values = dict(
        house="J.P. Morgan", ticker="AAPL", equity_rating="Overweight",
        price_target=255.0, target_horizon="Dec-26", credit_rating="A+",
        credit_rating_scale="S&P", analyst="A. Analyst", published="2026-08-14",
        document="Apple Inc. — Raising estimates", locator="jpmm:doc/12345",
    )
    values.update(overrides)
    return HouseView(**values)


class HouseViewModelTests(unittest.TestCase):
    """A citation that cannot be weighed is worse than no citation."""

    def test_a_complete_view_validates(self):
        _view().validate()

    def test_a_view_must_name_its_house_and_security(self):
        with self.assertRaises(ValueError):
            _view(house="  ").validate()
        with self.assertRaises(ValueError):
            _view(ticker="").validate()

    def test_a_view_carrying_nothing_is_not_evidence(self):
        with self.assertRaises(ValueError):
            _view(equity_rating="", credit_rating="", price_target=None).validate()

    def test_an_undated_view_is_rejected(self):
        # Without a date a reader cannot tell last week's target from last year's.
        with self.assertRaises(ValueError):
            _view(published="").validate()

    def test_a_credit_rating_alone_is_enough(self):
        _view(equity_rating="", price_target=None).validate()

    def test_a_target_must_be_a_real_price(self):
        with self.assertRaises(ValueError):
            _view(price_target=0).validate()
        with self.assertRaises(ValueError):
            _view(price_target=-10).validate()


class FreshnessTests(unittest.TestCase):
    def test_age_is_always_stated(self):
        text, stale = house_views.freshness(_view(published="2026-09-01"), "2026-09-02")
        self.assertEqual(text, "published yesterday")
        self.assertFalse(stale)

    def test_an_old_view_is_reported_stale(self):
        text, stale = house_views.freshness(_view(published="2025-06-01"), "2026-09-02")
        self.assertIn("month", text)
        self.assertTrue(stale)

    def test_an_unreadable_date_is_stale_not_silently_current(self):
        text, stale = house_views.freshness(_view(published="whenever"), "2026-09-02")
        self.assertTrue(stale)
        self.assertIn("not readable", text)

    def test_a_view_dated_after_the_analysis_is_flagged(self):
        _text, stale = house_views.freshness(_view(published="2026-12-01"), "2026-09-02")
        self.assertTrue(stale)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "house_views.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_saved_view_comes_back_for_its_ticker(self):
        house_views.save(_view(), self.path)
        found = house_views.for_ticker("aapl", self.path)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].equity_rating, "Overweight")
        self.assertEqual(found[0].price_target, 255.0)

    def test_a_new_view_from_the_same_house_supersedes_the_old_one(self):
        # Two live views from one house is not a state that exists.
        house_views.save(_view(price_target=255.0), self.path)
        house_views.save(_view(price_target=280.0, published="2026-09-01"), self.path)
        found = house_views.for_ticker("AAPL", self.path)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].price_target, 280.0)

    def test_views_from_different_houses_both_stand(self):
        house_views.save(_view(), self.path)
        house_views.save(_view(house="Morgan Stanley", equity_rating="Equal-weight"), self.path)
        self.assertEqual(len(house_views.for_ticker("AAPL", self.path)), 2)

    def test_other_tickers_are_not_returned(self):
        house_views.save(_view(), self.path)
        self.assertEqual(house_views.for_ticker("MSFT", self.path), ())

    def test_a_corrupt_record_is_skipped_not_surfaced(self):
        # A malformed citation in a client report is worse than a missing one.
        house_views.save(_view(), self.path)
        self.path.write_text('{"bad|X": {"house": "X", "ticker": "AAPL"}}', encoding="utf-8")
        self.assertEqual(house_views.for_ticker("AAPL", self.path), ())

    def test_an_unreadable_store_is_empty_not_an_error(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(house_views.all_views(self.path), ())

    def test_removing_a_view(self):
        house_views.save(_view(), self.path)
        self.assertTrue(house_views.remove("J.P. Morgan", "AAPL", self.path))
        self.assertFalse(house_views.remove("J.P. Morgan", "AAPL", self.path))

    def test_the_store_is_never_the_reports_directory(self):
        # Reports are swept; these are meant to outlive them.
        from backend.jobs import default_reports_root
        self.assertNotIn(default_reports_root().resolve(), house_views.store_path().resolve().parents)


class ReportIntegrationTests(unittest.TestCase):
    """The house's call is evidence beside our rating, never folded into it."""

    def _render(self, views):
        import dataclasses
        from core.request_builder import build_request
        from reports.html_report import build_research_html
        from research.demo_provider import DemoResearchProvider
        with tempfile.TemporaryDirectory() as tmp:
            request = build_request("AXON", "deep")
            result = DemoResearchProvider().run(request, Path(tmp))
            result = dataclasses.replace(result, house_views=views)
            target = Path(tmp) / "report.html"
            build_research_html(result, request, target)
            return target.read_text(encoding="utf-8")

    def test_a_cited_view_shows_its_house_rating_target_and_age(self):
        html = self._render((_view(ticker="AXON"),))
        self.assertIn("Research house views", html)
        self.assertIn("J.P. Morgan", html)
        self.assertIn("Overweight", html)
        self.assertIn("$255.00", html)
        self.assertIn("A+", html)
        self.assertIn("published 19 days ago", html)   # dated, not silently current

    def test_a_stale_view_says_so(self):
        html = self._render((_view(ticker="AXON", published="2024-01-05"),))
        self.assertIn("confirm it still stands", html)

    def test_the_section_is_absent_when_nothing_is_cited(self):
        self.assertNotIn("Research house views", self._render(()))

    def test_the_house_rating_is_never_presented_as_our_rating(self):
        # An Overweight from another firm is not this app's Buy: the scales
        # differ, and the report must say whose call is whose.
        html = self._render((_view(ticker="AXON"),))
        self.assertIn("which is not this report's", html)
        self.assertEqual(html.count('class="rating-word'), 1)


if __name__ == "__main__":
    unittest.main()
