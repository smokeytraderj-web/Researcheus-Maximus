import tempfile
import unittest
from pathlib import Path

from core.models import HouseNote, HouseView
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
        self.assertIn("Overweight", html)
        self.assertIn("$255.00", html)
        self.assertIn("A+", html)
        # Computed, not hardcoded: the age depends on today, and pinning a
        # number made this fail the moment the clock moved past it.
        import datetime as _dt
        age = (_dt.date.today() - _dt.date(2026, 8, 14)).days
        self.assertIn(f"published {age} days ago", html)   # dated, not silently current

    def test_every_house_figure_carries_the_house_name(self):
        # The figures are woven in among our own, so attribution has to travel
        # with each number rather than sitting in a section heading above them.
        html = self._render((_view(ticker="AXON"),))
        for label in ("J.P. Morgan rating", "J.P. Morgan target", "J.P. Morgan credit"):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_the_house_figures_sit_in_the_data_block_not_a_section_of_their_own(self):
        # Given a page to itself a house's rating read as a second verdict.
        html = self._render((_view(ticker="AXON"),))
        self.assertNotIn('id="houses"', html)
        self.assertIn('class="topline house-line"', html)

    def test_a_stale_view_says_so(self):
        html = self._render((_view(ticker="AXON", published="2024-01-05"),))
        self.assertIn("confirm it still stands", html)

    def test_nothing_is_added_when_nothing_is_cited(self):
        # The stylesheet always carries the rules; the markup must not appear.
        html = self._render(())
        self.assertNotIn('class="topline house-line"', html)
        self.assertNotIn("Research houses &mdash;", html)
        self.assertNotIn("hv-note-block", html.split("</style>")[1])

    def test_the_house_rating_is_never_presented_as_our_rating(self):
        # An Overweight from another firm is not this app's Buy: the scales
        # differ, and the report must say whose call is whose.
        html = self._render((_view(ticker="AXON"),))
        self.assertIn("each on its own scale, not this report", html)
        self.assertEqual(html.count('class="rating-word'), 1)


if __name__ == "__main__":
    unittest.main()


def _jpmm(**overrides) -> HouseView:
    """The AXON page as it actually reads on J.P. Morgan Markets."""
    values = dict(
        house="J.P. Morgan", ticker="AXON", equity_rating="Overweight",
        price_target=755.0, target_horizon="End date 31 Dec 2027", upside_pct=0.457,
        analyst="Joseph Cardoso", published="2026-08-06",
        sector="Aerospace & Defense", region="North America",
        profile=(
            ("Price ($)", "518.30"), ("Date of price", "01 Sep 26"),
            ("Market cap ($ mn)", "42,748"), ("Shares O/S (mn)", "82"),
            ("Free float (%)", "94.8%"), ("3M ADV ($ mn)", "531.1"),
            ("52-week range ($)", "792.16-339.01"), ("Volatility (90 Day)", "72"),
            ("BBG ANR (Buy | Hold | Sell)", "19|1|0"),
        ),
        latest_note=HouseNote(
            title="Axon: 2Q26 Review: Raises Revenue Bar in Typical Fashion",
            summary="Revenue and EBITDA ahead of expectations on broad-based momentum.",
            published="2026-08-06", authors="Joseph Cardoso, Marc Vitenzon", kind="Equity",
        ),
    )
    values.update(overrides)
    return HouseView(**values)


class EquityProfileTests(unittest.TestCase):
    def test_the_profile_price_and_its_date_are_read_back(self):
        price, dated = _jpmm().profile_price()
        self.assertEqual(price, 518.30)
        self.assertEqual(dated, "01 Sep 26")

    def test_a_profile_row_must_be_a_labelled_value(self):
        with self.assertRaises(ValueError):
            _jpmm(profile=(("", "518.30"),)).validate()

    def test_a_note_must_be_titled_and_dated(self):
        with self.assertRaises(ValueError):
            _jpmm(latest_note=HouseNote(title="", published="2026-08-06")).validate()
        with self.assertRaises(ValueError):
            _jpmm(latest_note=HouseNote(title="A note", published="")).validate()

    def test_the_whole_page_survives_a_store_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "house_views.json"
            house_views.save(_jpmm(), path)
            back = house_views.for_ticker("AXON", path)[0]
            self.assertEqual(back.upside_pct, 0.457)
            self.assertEqual(back.sector, "Aerospace & Defense")
            self.assertEqual(len(back.profile), 9)
            self.assertEqual(back.profile[8], ("BBG ANR (Buy | Hold | Sell)", "19|1|0"))
            self.assertEqual(back.latest_note.authors, "Joseph Cardoso, Marc Vitenzon")


class PriceDisagreementTests(unittest.TestCase):
    """The house quotes upside against its own price on its own date. When that
    price and ours differ materially the report has to say so, or the upside
    reads as if it were measured against ours."""

    def test_close_prices_raise_nothing(self):
        self.assertEqual(house_views.price_disagreement(_jpmm(), 520.0), "")

    def test_a_material_gap_is_reported_with_both_prices_and_the_date(self):
        text = house_views.price_disagreement(_jpmm(), 455.0)
        self.assertIn("$518.30", text)
        self.assertIn("$455.00", text)
        self.assertIn("01 Sep 26", text)
        self.assertIn("their own price", text)

    def test_a_house_quoting_no_price_raises_nothing(self):
        self.assertEqual(house_views.price_disagreement(_jpmm(profile=()), 455.0), "")


class JpmmReportTests(ReportIntegrationTests):
    def test_the_full_page_renders_rating_profile_and_note(self):
        html = self._render((_jpmm(),))
        for expected in ("Overweight", "$755.00", "+45.7%",
                         "Aerospace &amp; Defense",
                         "Market cap ($ mn)", "42,748", "19|1|0",
                         "2Q26 Review", "broad-based momentum"):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)

    def test_a_disagreeing_house_price_is_flagged_in_the_report(self):
        # The demo result prices AXON around $76, far from the profile's $518.
        html = self._render((_jpmm(ticker="AXON"),))
        self.assertIn("their upside is measured against their own price", html)
