import unittest

from research.jpmm_paste import parse_jpmm_page

# The AXON company page as it reads when copied off J.P. Morgan Markets,
# including the UI chrome that shares a line with the labels.
PAGE = """Axon (AXON US)
SUBSCRIBE   Sector: Aerospace & Defense   Region: North America

Equity Analyst
Joseph Cardoso
joseph.cardoso@jpmchase.com

Equity Rating:
Overweight
Price Target:
$755.00  45.7% Upside
End date 31 Dec 2027

Highlights
Latest Earnings-Related Note
Axon: 2Q26 Review: Raises Revenue Bar in Typical Fashion
Axon reported solid 2Q26 results, with revenue and EBITDA ahead of expectations.
Equity  06 Aug, 2026 | Joseph Cardoso, Marc Vitenzon + 1

Equity Profile
Price ($)                       518.30
Date of price                   01 Sep 26
Market cap ($ mn)               42,748
Shares O/S (mn)                 82
Free float (%)                  94.8%
3M ADV ($ mn)                   531.1
52-week range ($)               792.16-339.01
Volatility (90 Day)             72
BBG ANR (Buy | Hold | Sell)     19|1|0
"""


class ParseTests(unittest.TestCase):
    """The reader copies what is on screen under their own entitlement. Nothing
    here reaches the portal, and nothing is guessed."""

    def setUp(self):
        self.parsed = parse_jpmm_page(PAGE)

    def test_the_security_and_the_call_are_read(self):
        self.assertEqual(self.parsed.fields["ticker"], "AXON")
        self.assertEqual(self.parsed.fields["equity_rating"], "Overweight")
        self.assertEqual(self.parsed.fields["price_target"], 755.0)
        self.assertAlmostEqual(self.parsed.fields["upside_pct"], 0.457)
        self.assertEqual(self.parsed.fields["target_horizon"], "End date 31 Dec 2027")

    def test_a_rating_whose_value_is_on_the_next_line_is_still_read(self):
        # "Equity Rating:" stands alone; the value is beneath it.
        self.assertEqual(self.parsed.fields["equity_rating"], "Overweight")

    def test_labels_sharing_a_line_with_chrome_are_still_read(self):
        # The real line is "SUBSCRIBE   Sector: ...   Region: ...".
        self.assertEqual(self.parsed.fields["sector"], "Aerospace & Defense")
        self.assertEqual(self.parsed.fields["region"], "North America")

    def test_the_profile_keeps_its_labels_verbatim_with_their_units(self):
        rows = dict(self.parsed.profile)
        self.assertEqual(rows["Market cap ($ mn)"], "42,748")
        self.assertEqual(rows["BBG ANR (Buy | Hold | Sell)"], "19|1|0")
        self.assertEqual(len(self.parsed.profile), 9)

    def test_the_note_is_read_with_its_byline(self):
        fields = self.parsed.fields
        self.assertIn("2Q26 Review", fields["note_title"])
        self.assertEqual(fields["note_kind"], "Equity")
        self.assertEqual(fields["note_published"], "2026-08-06")   # normalised on parse
        self.assertIn("Marc Vitenzon", fields["note_authors"])
        self.assertIn("ahead of expectations", fields["note_summary"])

    def test_the_analyst_email_is_dropped(self):
        # Personal data, not evidence, and the report has no use for it.
        self.assertNotIn("jpmchase", repr(self.parsed.fields))
        self.assertNotIn("@", self.parsed.fields.get("analyst", ""))
        self.assertEqual(self.parsed.fields["analyst"], "Joseph Cardoso")

    def test_a_complete_page_reports_nothing_missing(self):
        self.assertEqual(self.parsed.missing, [])


class RefusalTests(unittest.TestCase):
    """A note carrying a price target nobody published is worse than one
    carrying none, so absence is reported rather than filled."""

    def test_missing_fields_are_named_not_invented(self):
        parsed = parse_jpmm_page("Axon (AXON US)\nSector: Aerospace & Defense\n")
        self.assertIn("equity rating", parsed.missing)
        self.assertIn("price target", parsed.missing)
        self.assertIn("equity profile", parsed.missing)
        self.assertNotIn("price_target", parsed.fields)
        self.assertNotIn("equity_rating", parsed.fields)

    def test_empty_text_yields_nothing_and_says_so(self):
        parsed = parse_jpmm_page("")
        self.assertEqual(parsed.profile, [])
        self.assertIn("ticker", parsed.missing)

    def test_unrelated_text_does_not_produce_a_view(self):
        parsed = parse_jpmm_page("Some notes I made about the market this morning.")
        self.assertNotIn("ticker", parsed.fields)
        self.assertNotIn("price_target", parsed.fields)

    def test_the_payload_names_the_house(self):
        payload = parse_jpmm_page(PAGE).as_payload()
        self.assertEqual(payload["house"], "J.P. Morgan")
        self.assertEqual(payload["ticker"], "AXON")


if __name__ == "__main__":
    unittest.main()


class DateNormalisationTests(unittest.TestCase):
    """Freshness is computed with date.fromisoformat. A date left in the
    portal's own format parses as nothing, so every pasted view would arrive
    reported "publication date not readable" and flagged stale."""

    def test_portal_formats_become_iso(self):
        from research.jpmm_paste import normalise_date
        for raw, expected in (
            ("06 Aug, 2026", "2026-08-06"),
            ("01 Sep 26", "2026-09-01"),
            ("Aug 6 2026", "2026-08-06"),
            ("2026-08-06", "2026-08-06"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalise_date(raw), expected)

    def test_something_that_is_not_a_date_is_left_alone_not_dropped(self):
        # Still what the page said; the reader corrects it before saving.
        from research.jpmm_paste import normalise_date
        self.assertEqual(normalise_date("sometime last week"), "sometime last week")
        self.assertEqual(normalise_date(""), "")

    def test_the_parsed_view_carries_a_date_freshness_can_read(self):
        import datetime as dt
        parsed = parse_jpmm_page(PAGE)
        self.assertEqual(parsed.fields["published"], "2026-08-06")
        dt.date.fromisoformat(parsed.fields["published"])   # must not raise

    def test_the_view_date_defaults_to_the_note_it_was_shown_with(self):
        parsed = parse_jpmm_page(PAGE)
        self.assertEqual(parsed.fields["published"], parsed.fields["note_published"])

    def test_the_profile_price_date_is_normalised_too(self):
        rows = dict(parse_jpmm_page(PAGE).profile)
        self.assertEqual(rows["Date of price"], "2026-09-01")

    def test_a_view_parsed_from_the_page_is_not_born_stale(self):
        from core.models import HouseNote, HouseView
        from research import house_views
        parsed = parse_jpmm_page(PAGE)
        view = HouseView(
            house="J.P. Morgan",
            ticker=parsed.fields["ticker"],
            equity_rating=parsed.fields["equity_rating"],
            price_target=parsed.fields["price_target"],
            published=parsed.fields["published"],
        )
        view.validate()
        age, stale = house_views.freshness(view, "2026-09-03")
        self.assertNotIn("not readable", age)
        self.assertFalse(stale)


# The same page as the browser renders it, rather than as the clipboard hands
# it over. Copying the Equity Profile preserves its columns; reading the page
# itself gives one value per line, and the label/value pairing that the copied
# form gets from whitespace has to come from the line order instead.
RENDERED = """Axon 

(AXON US)
SUBSCRIBE

Sector:
 Aerospace & Defense
Region: North America
Equity Analyst
Joseph Cardoso
joseph.cardoso@jpmchase.com

 COVERAGE
Equity Rating:
Overweight
Price Target:
$755.00
40.3% Upside
End date 31 Dec 2027
Highlights
Latest Earnings-Related Note
Axon: 2Q26 Review: Raises Revenue Bar in Typical Fashion

Revenue and EBITDA came in ahead of expectations.

Equity

16 Jul, 2026

|

Joseph Cardoso

, 

Manmohanpreet Singh

Equity Profile
Price ($)
506.98
Date of price
02 Sep 26
Market cap ($ mn)
41,815
Shares O/S (mn)
82
Free float (%)
94.8%
3M ADV ($ mn)
534.4
52-week range ($)
792.16-339.01
Volatility (90 Day)
72
BBG ANR (Buy | Hold | Sell)
19|1|0
"""


class RenderedPageTests(unittest.TestCase):
    """The same reader, the same entitlement, the same page -- read rather than
    retyped. It has to yield the same view the copied form does, because a
    half-read page is not a cheaper view, it is a wrong one."""

    def setUp(self):
        self.parsed = parse_jpmm_page(RENDERED)

    def test_the_call_survives_the_line_per_value_layout(self):
        fields = self.parsed.fields
        self.assertEqual(fields["ticker"], "AXON")
        self.assertEqual(fields["equity_rating"], "Overweight")
        self.assertEqual(fields["price_target"], 755.0)
        self.assertAlmostEqual(fields["upside_pct"], 0.403)
        self.assertEqual(fields["target_horizon"], "End date 31 Dec 2027")

    def test_a_label_whose_value_is_beneath_it_is_still_read(self):
        # "Sector:" stands alone here; copied, it shares its line with the value.
        self.assertEqual(self.parsed.fields["sector"], "Aerospace & Defense")
        self.assertEqual(self.parsed.fields["region"], "North America")

    def test_the_whole_profile_is_read_not_just_the_rows_that_fit_one_line(self):
        rows = dict(self.parsed.profile)
        self.assertEqual(len(self.parsed.profile), 9)
        self.assertEqual(rows["Price ($)"], "506.98")
        self.assertEqual(rows["Market cap ($ mn)"], "41,815")
        self.assertEqual(rows["BBG ANR (Buy | Hold | Sell)"], "19|1|0")

    def test_the_house_price_reaches_the_comparison_that_needs_it(self):
        # Without the profile there is no house price, and the report's
        # disagreement check silently never fires.
        from core.models import HouseView
        view = HouseView(
            house="J.P. Morgan", ticker="AXON", equity_rating="Overweight",
            price_target=755.0, published="2026-07-16",
            profile=tuple(tuple(row) for row in self.parsed.profile),
        )
        price, dated = view.profile_price()
        self.assertEqual(price, 506.98)
        self.assertEqual(dated, "2026-09-02")

    def test_a_byline_broken_across_lines_still_dates_the_note(self):
        fields = self.parsed.fields
        self.assertEqual(fields["note_kind"], "Equity")
        self.assertEqual(fields["note_published"], "2026-07-16")
        self.assertEqual(fields["published"], "2026-07-16")

    def test_the_byline_ends_where_the_authors_do(self):
        # Nothing marks its end, so read too far it credited the note to the
        # profile table beneath: "Joseph Cardoso, ..., Price ($), 506.98".
        authors = self.parsed.fields["note_authors"]
        self.assertEqual(authors, "Joseph Cardoso, Manmohanpreet Singh")

    def test_the_analyst_email_is_dropped_here_too(self):
        self.assertNotIn("jpmchase", repr(self.parsed.fields))

    def test_a_complete_rendered_page_reports_nothing_missing(self):
        self.assertEqual(self.parsed.missing, [])
