import unittest

from core.assessments import (
    assessment_interpretation,
    condense_reasoning,
    fundamental_outlook,
    technical_setup,
)
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


class CondenseReasoningTests(unittest.TestCase):
    """The Why block must explain the view, not repeat the page back."""

    SAMPLE = (
        "Apple Inc. is a conditional buy candidate on the available evidence. "
        "Apple Inc. receives a Buy rating for the medium term horizon. "
        "The lead framework weights fundamental evidence 50% and technical evidence 50% for this horizon. "
        "The technical setup is bullish, and the fundamental outlook is positive. "
        "The business outlook and current entry setup are both constructive. "
        "A confirmed close above $344.57 would strengthen the case."
    )

    def test_internal_methodology_never_reaches_the_reader(self):
        self.assertNotIn("weights fundamental evidence", condense_reasoning(self.SAMPLE))
        self.assertNotIn("50%", condense_reasoning(self.SAMPLE))

    def test_restatement_of_the_rating_and_labels_is_dropped(self):
        out = condense_reasoning(self.SAMPLE)
        self.assertNotIn("receives a Buy rating", out)
        self.assertNotIn("The technical setup is bullish", out)
        self.assertNotIn("are both constructive", out)

    def test_evidence_bearing_sentences_survive(self):
        out = condense_reasoning(self.SAMPLE)
        self.assertIn("$344.57", out)
        self.assertIn("conditional buy candidate", out)

    def test_company_suffixes_do_not_split_a_sentence(self):
        # Splitting on ". " turned "Apple Inc. receives a Buy rating." into two,
        # dropped the half carrying the verb, and stranded "Apple Inc." alone.
        out = condense_reasoning(self.SAMPLE)
        self.assertNotIn("Apple Inc. A confirmed", out)
        self.assertFalse(any(part.strip() == "Apple Inc." for part in out.split(". ")))

    def test_filtering_never_empties_the_answer(self):
        # A thin Why is worse than a repetitive one.
        only_boilerplate = "The technical setup is bullish, and the fundamental outlook is positive."
        self.assertEqual(condense_reasoning(only_boilerplate), only_boilerplate)

    def test_blank_input_stays_blank(self):
        self.assertEqual(condense_reasoning("   "), "")


if __name__ == "__main__":
    unittest.main()
