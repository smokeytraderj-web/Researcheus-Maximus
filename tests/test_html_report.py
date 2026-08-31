import unittest

from core.models import Rating
from reports.html_report import _stance


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
