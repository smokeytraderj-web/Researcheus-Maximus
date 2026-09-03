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
