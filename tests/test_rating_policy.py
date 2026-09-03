import unittest

from core.models import Rating
from core.rating_policy import (
    APPLIES_TO,
    DEFINITIONS,
    POLICY_VERSION,
    applies_to,
    definition,
    is_constructive,
    is_negative,
)


class RatingPolicyTests(unittest.TestCase):
    """The labels existed as a bare enum, so the difference between Buy and Add
    lived only in a score threshold and in whatever a reader assumed."""

    def test_every_label_carries_a_definition(self):
        for rating in Rating:
            with self.subTest(rating=rating):
                self.assertTrue(definition(rating).strip())
                self.assertTrue(applies_to(rating).strip())

    def test_no_definition_exists_for_a_label_that_does_not(self):
        # The seven are the seven. A new label needs a policy edit, not a default.
        self.assertEqual(set(DEFINITIONS), set(Rating))
        self.assertEqual(set(APPLIES_TO), set(Rating))

    def test_buy_speaks_to_starting_a_position_and_add_to_growing_one(self):
        # The distinction that prompted writing this down: a reader holding the
        # name and a reader holding none must not act identically on one word.
        self.assertIn("Initiating", applies_to(Rating.BUY))
        self.assertIn("existing position", applies_to(Rating.ADD))
        self.assertIn("initiating a position", definition(Rating.BUY))
        self.assertIn("rather than initiating one here", definition(Rating.ADD))

    def test_add_states_that_it_is_conditional(self):
        self.assertIn("qualified", definition(Rating.ADD))

    def test_reduce_is_trimming_and_sell_is_exiting(self):
        self.assertIn("not closing it", definition(Rating.REDUCE))
        self.assertIn("exiting", definition(Rating.SELL))

    def test_the_constructive_and_negative_sets_do_not_overlap(self):
        for rating in Rating:
            with self.subTest(rating=rating):
                self.assertFalse(is_constructive(rating) and is_negative(rating))
        self.assertFalse(is_constructive(Rating.HOLD) or is_negative(Rating.HOLD))

    def test_the_policy_is_versioned(self):
        self.assertRegex(POLICY_VERSION, r"^\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
