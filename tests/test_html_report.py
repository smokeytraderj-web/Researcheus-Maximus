import unittest

from core.models import Rating
import tempfile
from pathlib import Path

from core.request_builder import build_request
from reports.html_report import _stance, build_research_html
from research.demo_provider import DemoResearchProvider


class SpecialistStanceTests(unittest.TestCase):
    """The stance chip tells the reader where the workstreams agree, so its
    wording has to follow directional agreement rather than exact rating equality."""

    def test_same_direction_supports_even_when_labels_differ(self):
        self.assertEqual(_stance(Rating.BUY, Rating.STRONG_BUY), ("supports", "Supports"))
        self.assertEqual(_stance(Rating.ADD, Rating.BUY), ("supports", "Supports"))
        self.assertEqual(_stance(Rating.SELL, Rating.REDUCE), ("supports", "Supports"))

    def test_identical_ratings_support(self):
        self.assertEqual(_stance(Rating.HOLD, Rating.HOLD), ("supports", "Supports"))

    def test_opposite_directions_challenge(self):
        self.assertEqual(_stance(Rating.SELL, Rating.BUY), ("challenges", "Challenges"))
        self.assertEqual(_stance(Rating.STRONG_BUY, Rating.AVOID), ("challenges", "Challenges"))

    def test_neutral_against_directional_is_partial_not_a_conflict(self):
        self.assertEqual(_stance(Rating.HOLD, Rating.BUY), ("partial", "Partial"))
        self.assertEqual(_stance(Rating.BUY, Rating.HOLD), ("partial", "Partial"))
        self.assertEqual(_stance(Rating.HOLD, Rating.SELL), ("partial", "Partial"))


if __name__ == "__main__":
    unittest.main()


class ReadingOrderTests(unittest.TestCase):
    """The checklist is the first evidence a reader meets, and the reasoning
    follows it. The metrics strip is reference detail and sits after both -- it
    previously separated the boxes from the answer they explain, and on the
    Technical report it also pushed the checklist off printed page one.

    The rating is stated once, in the masthead. It used to appear there and
    again in a centred block below, at the same size, reading as two verdicts."""

    MARKERS = (
        ("rating", 'class="rating"'),
        ("checklist", 'class="cc-card"'),
        ("why", 'class="why-block"'),
        ("strip", 'class="topline"'),
    )

    def _order(self, html: str) -> list[str]:
        found = []
        for name, marker in self.MARKERS:
            index = html.find(marker)
            self.assertGreaterEqual(index, 0, f"{name} missing from the report")
            found.append((index, name))
        return [name for _, name in sorted(found)]

    def _render(self, mode: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_request("AXON price structure and momentum", mode)
            result = DemoResearchProvider().run(request, Path(tmp))
            target = Path(tmp) / "report.html"
            build_research_html(result, request, target)
            return target.read_text(encoding="utf-8")

    def test_general_brief_reads_rating_checklist_why_then_strip(self):
        self.assertEqual(self._order(self._render("general")),
                         ["rating", "checklist", "why", "strip"])

    def test_technical_report_uses_the_same_order(self):
        self.assertEqual(self._order(self._render("deep")),
                         ["rating", "checklist", "why", "strip"])

    def test_the_rating_is_stated_once_per_report(self):
        for mode in ("general", "deep"):
            with self.subTest(mode=mode):
                html = self._render(mode)
                self.assertNotIn('class="verdict-hero"', html)
                self.assertEqual(html.count('class="rating-word'), 1)


class PrintLayoutTests(unittest.TestCase):
    """What print does is invisible in the HTML, so these pin the rules that a
    rendered PDF proved were needed."""

    def _render(self, mode: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_request("AXON price structure and momentum", mode)
            result = DemoResearchProvider().run(request, Path(tmp))
            target = Path(tmp) / "report.html"
            build_research_html(result, request, target)
            return target.read_text(encoding="utf-8")

    def test_print_restores_the_desktop_grids_over_the_mobile_breakpoint(self):
        # A printed Letter page is ~816px, which trips the approved template's
        # 900px mobile breakpoint. Both reports were silently printing as a
        # phone: a stacked masthead, half-width strips, and the Conviction
        # Checklist in two columns with an orphan fifth card -- against the
        # spec's "one column per criterion".
        html = self._render("deep")
        print_css = html[html.index("@media print{.chart-image"):]
        self.assertIn(".cc-grid{grid-template-columns:repeat(5,minmax(0,1fr))}", print_css)
        self.assertIn(".topline{grid-template-columns:repeat(4,1fr)}", print_css)
        self.assertIn(".head{flex-direction:row}", print_css)

    def test_technical_print_starts_each_major_section_on_its_own_page(self):
        html = self._render("deep")
        for rule in (
            ".tech-report #plan{break-before:page}",
            ".tech-report #sources{break-before:page}",
            ".tech-report .evidence-panel + .evidence-panel{break-before:page}",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, html)

    def test_no_page_break_is_pinned_before_the_fundamentals_running_strip(self):
        # #fundamentals already opens a page-view; a break before it only strands
        # the running strip above it on a page of its own.
        self.assertNotIn(".tech-report #fundamentals{break-before:page}", self._render("deep"))

    def test_the_scenario_controls_do_not_print_but_its_conclusions_do(self):
        html = self._render("deep")
        self.assertIn(".tech-report .scn-chips,.tech-report .scn-slider{display:none!important}", html)
        # The graph, the action zone and the outcome figures are static
        # conclusions and must survive into print.
        for kept in ("scn-scale", 'id="zone"', "scn-out"):
            with self.subTest(kept=kept):
                self.assertIn(kept, html)

    def test_the_general_brief_keeps_its_approved_three_page_form(self):
        # Section-per-page was applied to the Technical report only; the General
        # brief's three-page contract is pinned in CLAUDE.md.
        html = self._render("general")
        for rule in (".general-brief #plan{break-before:page}", ".general-brief #sources{break-before:page}"):
            with self.subTest(rule=rule):
                self.assertNotIn(rule, html)


class SlideDeckTests(unittest.TestCase):
    """The deck is an export of the same report, not a second version of it."""

    def _render(self, mode: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            request = build_request("AXON price structure and momentum", mode)
            result = DemoResearchProvider().run(request, Path(tmp))
            target = Path(tmp) / "report.html"
            build_research_html(result, request, target)
            return target.read_text(encoding="utf-8")

    def test_both_reports_carry_a_deck_and_an_export_button(self):
        for mode in ("general", "deep"):
            with self.subTest(mode=mode):
                html = self._render(mode)
                self.assertIn('id="deckBtn"', html)
                self.assertIn('class="deck"', html)
                self.assertGreaterEqual(html.count('<section class="slide">'), 5)

    def test_the_deck_is_hidden_until_the_button_turns_it_on(self):
        # A reader opening the report must see the report, not a deck stacked
        # underneath it.
        html = self._render("general")
        self.assertIn(".deck{display:none}", html)
        self.assertIn("body.deck-on .deck{display:block}", html)

    def test_the_landscape_page_box_is_only_applied_while_printing_the_deck(self):
        # @page cannot be scoped to a class, so an always-present landscape rule
        # would silently re-page the ordinary Print / save PDF output too.
        html = self._render("general")
        self.assertNotIn("@page{size:297mm", html.split("<body")[0])
        self.assertIn("pageStyle.textContent='@page{size:297mm 167mm;margin:0}'", html)

    def test_slides_stay_at_slide_density(self):
        # The deck is not the report reproduced. Slides carried the criteria's
        # full sentences and two paragraphs of reasoning, which is a page, not
        # something read from across a room. This is the guard against drifting
        # back: no slide may exceed a readable word count.
        import re
        for mode in ("general", "deep"):
            with self.subTest(mode=mode):
                html = self._render(mode)
                deck = html[html.index('class="deck"'):]
                slides = re.findall(r'<section class="slide">(.*?)</section>', deck, re.S)
                self.assertGreaterEqual(len(slides), 5)
                for index, slide in enumerate(slides, 1):
                    words = len(re.sub(r"<[^>]+>", " ", slide).split())
                    self.assertLessEqual(
                        words, 110,
                        f"slide {index} carries {words} words -- that is a page, not a slide",
                    )

    def test_slide_readings_are_short_not_the_report_sentences(self):
        html = self._render("general")
        deck = html[html.index('class="deck"'):]
        # The report says "Price $325.13 is above both the 50-day ... averages."
        # The slide says "Above the 50 and 200-day".
        # The checklist on a slide is the report's own five cards, so it carries
        # the same criterion detail. What it must not carry is the report's
        # surrounding apparatus -- tooltips, info controls, print captions.
        checks = deck.index('class="s-checks"')
        panel = deck[checks:checks + 4000]
        self.assertIn("Trend", panel)
        for apparatus in ("cc-info", "cc-tip", "cc-explain"):
            with self.subTest(apparatus=apparatus):
                self.assertNotIn(apparatus, panel)

    def test_slides_are_numbered_and_carry_the_running_foot(self):
        # A deck is presented away from the report; a reader needs to know where
        # they are in it and whose it is.
        deck = self._render("deep")
        self.assertIn("Page 1 of ", deck)
        self.assertIn("Gottfried &amp; Somberg Wealth Management", deck)

    def test_the_deck_follows_the_firm_client_deck_template(self):
        # Navy ground, the firm monogram to the approved geometry, a gold rule
        # under every page title, serif throughout -- the template the firm
        # already presents to clients (reference: Bloom portfolio review).
        deck_page = self._render("deep")
        deck = deck_page[deck_page.index('class="deck"'):]
        self.assertIn('class="slide cover"', deck)      # the navy title cover
        self.assertIn('class="s-rule"', deck)           # gold rule under titles
        self.assertIn('class="s-mono"', deck)           # the firm's mark
        self.assertIn("#BFA054", deck_page)             # the template's gold

    def test_the_cover_carries_the_firm_mark_as_an_embedded_image(self):
        # The real seal, not a redrawn approximation of it -- and inlined, so a
        # report opened from a mail attachment with no network still shows it.
        from reports.html_report import _firm_mark
        mark = _firm_mark()
        self.assertTrue(mark.startswith('<img src="data:image/png;base64,'), mark[:60])
        deck = self._render("general")
        self.assertIn(mark, deck)

    def test_the_deck_has_no_contents_or_disclosure_slide(self):
        # Both were cut: a seven-page deck does not need a table of contents,
        # and the disclosure travels on the cover instead of taking a page.
        deck = self._render("deep")
        deck = deck[deck.index('class="deck"'):]
        self.assertNotIn("s-contents", deck)
        self.assertNotIn(">Contents<", deck)
        self.assertNotIn(">Disclosure<", deck)

    def test_the_disclosure_still_travels_with_the_deck(self):
        # Cutting the slide must not cut the disclosure: a deck is shown without
        # the report attached to it.
        deck = self._render("deep")
        deck = deck[deck.index('class="deck"'):]
        self.assertIn("Firm compliance review is required", deck)
        self.assertIn("Internal use only", deck)
        self.assertIn("possible loss of principal", deck)

    def test_the_deck_sets_everything_in_the_template_serif(self):
        # The reference deck is Garamond for display and a Times-class serif for
        # text, with no sans and no mono anywhere.
        html = self._render("deep")
        self.assertIn("EB+Garamond", html)
        deck_css = html[html.index(".deck{display:none}"):html.index('<div class="deck">')]
        self.assertIn("'Source Serif 4',Georgia,'Times New Roman',serif", deck_css)
        self.assertIn("'EB Garamond',Garamond,Georgia,serif", deck_css)
        for face in ("IBM Plex Sans", "IBM Plex Mono"):
            with self.subTest(face=face):
                self.assertNotIn(face, deck_css)

    def test_slide_labels_name_the_slide_rather_than_selling_it(self):
        # "Our recommendation" / "Why we say Add" / "Four views of the same
        # question" read as a pitch. A research deck labels what is on the page.
        for mode in ("general", "deep"):
            with self.subTest(mode=mode):
                deck = self._render(mode)
                deck = deck[deck.index('class="deck"'):]
                for corny in ("Our recommendation", "Why we say", "views of the same question"):
                    self.assertNotIn(corny, deck)

    def test_the_deck_never_prints_navy_type_on_the_navy_slide(self):
        # The disclosure slide hardcoded the report's navy for its emphasis,
        # which was invisible once the slide went back to a navy ground.
        deck = self._render("general")
        deck = deck[deck.index('class="deck"'):]
        self.assertNotIn("#14213D", deck)

    def test_the_deck_carries_its_own_disclosure(self):
        # A deck leaves the room without the report attached to it.
        html = self._render("general")
        deck = html[html.index('class="deck"'):]
        self.assertIn("Firm compliance review is required", deck)
        self.assertIn("Internal use only", deck)


class HorizonSplitReportTests(unittest.TestCase):
    """All Horizons is the default when a request does not name one, so this is
    most reports. The spec forbids collapsing conflicting horizon conclusions
    into one vague statement."""

    def _render(self, technical, fundamental):
        import dataclasses
        from core.horizons import horizon_views
        from reports.html_report import build_research_html
        with tempfile.TemporaryDirectory() as tmp:
            request = build_request("AXON", "general")
            result = DemoResearchProvider().run(request, Path(tmp))
            result = dataclasses.replace(
                result, horizon_views=horizon_views(technical, fundamental)
            )
            target = Path(tmp) / "report.html"
            build_research_html(result, request, target)
            return target.read_text(encoding="utf-8")

    def test_a_split_shows_all_three_conclusions(self):
        html = self._render(Rating.SELL, Rating.BUY)
        self.assertIn('id="horizons"', html)
        for expected in ("Short Term", "Medium Term", "Long Term",
                         "The horizons disagree"):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)

    def test_a_split_is_named_in_the_masthead_rather_than_hidden_under_one_word(self):
        html = self._render(Rating.SELL, Rating.BUY)
        self.assertIn("Short Reduce · Medium Hold · Long Add", html)
        # The rating is still stated once; the subline qualifies it.
        self.assertEqual(html.count('class="rating-word'), 1)

    def test_agreement_costs_one_line_not_a_section(self):
        # The brief is a pinned three pages; three columns of the same word
        # would spend one of them saying nothing.
        html = self._render(Rating.BUY, Rating.BUY)
        self.assertIn("hz-agree", html)
        self.assertNotIn('id="horizons"', html)
        self.assertIn("the horizons agree", html)

    def test_agreement_leaves_the_masthead_subline_alone(self):
        html = self._render(Rating.BUY, Rating.BUY)
        self.assertIn("All Horizons view", html)

    def test_print_keeps_the_three_conclusions_and_drops_the_furniture(self):
        html = self._render(Rating.SELL, Rating.BUY)
        self.assertIn(".general-brief #horizons .sec-head{display:none}", html)
        self.assertIn(".general-brief .hz-note{display:none}", html)
