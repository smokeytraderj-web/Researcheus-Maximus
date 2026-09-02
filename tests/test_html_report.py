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
