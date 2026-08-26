import unittest

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
from core.models import Rating


class ClientAssessmentTests(unittest.TestCase):
    def test_buy_and_sell_become_supporting_assessments(self):
        self.assertEqual(technical_setup(Rating.SELL), "Bearish")
        self.assertEqual(fundamental_outlook(Rating.BUY), "Positive")

    def test_hold_becomes_neutral_or_balanced_by_lens(self):
        self.assertEqual(technical_setup(Rating.HOLD), "Neutral")
        self.assertEqual(fundamental_outlook(Rating.HOLD), "Balanced")

    def test_positive_business_and_bearish_chart_are_reconciled(self):
        self.assertEqual(
            assessment_interpretation(Rating.SELL, Rating.BUY),
            "Good underlying company, but the current entry setup is weak.",
        )


if __name__ == "__main__":
    unittest.main()
