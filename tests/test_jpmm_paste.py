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


# The strip exactly as /research/company/AXON.O/earning-strip returned it in the
# advisor's own session. Note the trailing spaces on some labels, and that
# "Price ($)" and "Price Target ($)" differ by one word.
STRIP = [
    {"label": "Equity Rating", "value": "Overweight", "currency": ""},
    {"label": "Price ($)", "value": "515.67", "currency": "USD"},
    {"label": "Date of price ", "value": "04 Sep 26", "currency": ""},
    {"label": "Price Target ($)", "value": "755.00", "currency": "USD"},
    {"label": "Price target end date ", "value": "31-Dec-27", "currency": ""},
    {"label": "Shares O/S (mn)", "value": "82", "currency": ""},
    {"label": "52-week range ($)", "value": "792.16-339.01", "currency": "USD"},
    {"label": "Market cap ($ mn)", "value": "42,531.43", "currency": "USD"},
    {"label": "Exchange rate ", "value": "1.00", "currency": ""},
    {"label": "Free float (%) ", "value": "94.8%", "currency": ""},
    {"label": "3M ADV (mn)", "value": "0.99", "currency": ""},
    {"label": "3M ADV ($ mn)", "value": "529.5", "currency": "USD"},
    {"label": "Volatility (90 Day) ", "value": "73", "currency": ""},
    {"label": "Index ", "value": "RUSSELL 2000", "currency": ""},
    {"label": "BBG ANR (Buy | Hold | Sell) ", "value": "19|1|0", "currency": ""},
]

ESTIMATES = [
    {"displayName": " Revenue FY ($ mn)", "dataItems": {
        "FY24A": {"displayValue": "2,084"}, "FY25A": {"displayValue": "2,780"},
        "FY26E": {"displayValue": "3,720"}}},
    {"displayName": " EBITDA margin FY ", "dataItems": {
        "FY24A": {"displayValue": "24.9%"}, "FY26E": {"displayValue": "25.6%"}}},
]


class PayloadTests(unittest.TestCase):
    """The portal states every figure already typed and labelled. Read that and
    nothing has to be recovered from the shape of rendered text."""

    def setUp(self):
        from research.jpmm_paste import parse_jpmm_payload
        self.parsed = parse_jpmm_payload(STRIP, ESTIMATES, RENDERED, ticker="AXON")

    def test_the_call_comes_from_the_strip_not_the_text(self):
        fields = self.parsed.fields
        self.assertEqual(fields["equity_rating"], "Overweight")
        self.assertEqual(fields["price_target"], 755.0)
        self.assertEqual(fields["currency"], "USD")
        self.assertEqual(fields["target_horizon"], "End date 31-Dec-27")

    def test_the_strips_fresher_price_wins_over_the_rendered_one(self):
        # The page had 506.98 cached; the strip answered 515.67. The strip is
        # the source the page was a rendering of, so it wins.
        rows = dict(self.parsed.profile)
        self.assertEqual(rows["Price ($)"], "515.67")

    def test_price_target_is_never_mistaken_for_price(self):
        # They differ by one word, and the second is what the report compares
        # against this analysis's own price.
        rows = dict(self.parsed.profile)
        self.assertNotIn("Price Target ($)", rows)
        self.assertEqual(self.parsed.fields["price_target"], 755.0)
        self.assertEqual(rows["Price ($)"], "515.67")

    def test_every_profile_row_the_strip_carries_is_kept_with_its_label(self):
        rows = dict(self.parsed.profile)
        # 15 strip rows, less the three that are the view itself.
        self.assertEqual(len(self.parsed.profile), 12)
        self.assertEqual(rows["Market cap ($ mn)"], "42,531.43")
        self.assertEqual(rows["Index"], "RUSSELL 2000")           # not on the page at all
        self.assertEqual(rows["BBG ANR (Buy | Hold | Sell)"], "19|1|0")

    def test_the_price_date_is_normalised_so_freshness_can_read_it(self):
        self.assertEqual(dict(self.parsed.profile)["Date of price"], "2026-09-04")

    def test_the_text_supplies_only_what_the_strip_does_not_carry(self):
        fields = self.parsed.fields
        self.assertEqual(fields["sector"], "Aerospace & Defense")
        self.assertEqual(fields["analyst"], "Joseph Cardoso")
        self.assertEqual(fields["published"], "2026-07-16")

    def test_the_estimates_keep_their_periods_and_their_published_precision(self):
        estimates = dict(self.parsed.estimates)
        # The portal pads its metric names with a leading space; that is
        # formatting, not the name, so it does not survive into the report.
        revenue = dict(estimates["Revenue FY ($ mn)"])
        self.assertEqual(revenue["FY24A"], "2,084")   # actual
        self.assertEqual(revenue["FY26E"], "3,720")   # estimate, marked as one
        self.assertEqual(dict(estimates["EBITDA margin FY"])["FY24A"], "24.9%")

    def test_a_complete_payload_reports_nothing_missing(self):
        self.assertEqual(self.parsed.missing, [])

    def test_the_house_price_reaches_the_comparison(self):
        from core.models import HouseView
        view = HouseView(
            house="J.P. Morgan", ticker="AXON", equity_rating="Overweight",
            price_target=755.0, published="2026-07-16",
            profile=tuple(tuple(row) for row in self.parsed.profile),
        )
        self.assertEqual(view.profile_price(), (515.67, "2026-09-04"))


class PayloadRefusalTests(unittest.TestCase):
    """The strip is not trusted more than the text was. What it does not carry
    is still reported by name, and what it must never carry is refused."""

    def test_a_strip_without_a_target_says_so_rather_than_inventing_one(self):
        from research.jpmm_paste import parse_jpmm_payload
        thin = [row for row in STRIP if "target" not in row["label"].casefold()]
        parsed = parse_jpmm_payload(thin, (), "", ticker="AXON")
        self.assertIn("price target", parsed.missing)
        self.assertNotIn("price_target", parsed.fields)

    def test_the_text_still_answers_for_a_figure_the_strip_lost(self):
        # Degrading, not refusing: the page text is a worse source than the
        # strip and a better one than nothing.
        from research.jpmm_paste import parse_jpmm_payload
        thin = [row for row in STRIP if "target" not in row["label"].casefold()]
        parsed = parse_jpmm_payload(thin, (), RENDERED, ticker="AXON")
        self.assertEqual(parsed.fields["price_target"], 755.0)
        self.assertNotIn("price target", parsed.missing)

    def test_a_payload_with_no_text_still_names_what_it_lacks(self):
        # No text means no note, so no publication date -- and HouseView
        # refuses an undated view, so it is named here rather than at the save.
        from research.jpmm_paste import parse_jpmm_payload
        parsed = parse_jpmm_payload(STRIP, (), "", ticker="AXON")
        self.assertIn("publication date", parsed.missing)
        self.assertEqual(parsed.fields["equity_rating"], "Overweight")

    def test_an_empty_strip_yields_no_view(self):
        from research.jpmm_paste import parse_jpmm_payload
        parsed = parse_jpmm_payload([], (), "")
        self.assertIn("ticker", parsed.missing)
        self.assertIn("equity profile", parsed.missing)

    def test_a_payload_carrying_session_material_is_refused_outright(self):
        # Not stripped and passed on: a sender that included a credential is not
        # the sender this was built for, so none of what it sent is read.
        from research.jpmm_paste import SecretInPayload, parse_jpmm_payload
        for poisoned in (
            [{"label": "Equity Rating", "value": "Overweight", "cookie": "JSESSIONID=abc"}],
            [{"label": "x", "value": "1", "meta": {"headers": {"Authorization": "Bearer ey."}}}],
            [{"label": "x", "value": "1", "csrfToken": "zzz"}],
        ):
            with self.subTest(poisoned=poisoned):
                with self.assertRaises(SecretInPayload):
                    parse_jpmm_payload(poisoned, (), "")

    def test_ordinary_evidence_is_not_mistaken_for_a_secret(self):
        from research.jpmm_paste import parse_jpmm_payload
        parsed = parse_jpmm_payload(STRIP, ESTIMATES, RENDERED, ticker="AXON")
        self.assertEqual(parsed.fields["equity_rating"], "Overweight")
