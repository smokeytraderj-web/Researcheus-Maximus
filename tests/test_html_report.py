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
        self.assertIn("s-check-read", deck)
        self.assertNotIn("is above both the 50-day", deck[deck.index("s-checks"):deck.index("s-checks") + 3000])

    def test_the_deck_carries_its_own_disclosure(self):
        # A deck leaves the room without the report attached to it.
        html = self._render("general")
        deck = html[html.index('class="deck"'):]
        self.assertIn("Firm compliance review is required", deck)
        self.assertIn("Internal use only", deck)
