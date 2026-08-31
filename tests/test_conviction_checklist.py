import unittest

from core.conviction_checklist import POLICY_VERSION, evaluate_conviction_checklist


def _base(**overrides):
    values = dict(
        price=800.0, sma50=760.0, sma200=650.0,
        rsi14=58.0, macd=12.0, macd_signal=8.0,
        security_return_pct=0.22, benchmark_return_pct=0.09,
        revenue_growth_pct=0.31, earnings_growth_pct=0.44,
        analyst_target=880.0,
    )
    values.update(overrides)
    return evaluate_conviction_checklist(**values)


class ConvictionChecklistTests(unittest.TestCase):
    """Every criterion is a policy decision, not a guess -- these fixtures pin
    the exact thresholds so a later change to them is a deliberate diff, not drift."""

    def test_always_returns_exactly_five_criteria_in_order(self):
        checklist = _base()
        self.assertEqual(checklist.total_count, 5)
        self.assertEqual(
            [item.key for item in checklist.criteria],
            ["trend", "momentum", "relative_strength", "growth", "street_conviction"],
        )
        self.assertEqual(checklist.policy_version, POLICY_VERSION)

    def test_engineered_case_passes_all_five(self):
        checklist = _base()
        self.assertTrue(checklist.is_perfect)
        self.assertEqual(checklist.passed_count, 5)
        self.assertTrue(all(item.passed is True for item in checklist.criteria))

    def test_engineered_case_fails_all_five(self):
        checklist = _base(
            price=100.0, sma50=105.0, sma200=110.0,
            rsi14=32.0, macd=-1.0, macd_signal=0.5,
            security_return_pct=-0.05, benchmark_return_pct=0.08,
            revenue_growth_pct=0.03, earnings_growth_pct=-0.02,
            analyst_target=95.0,
        )
        self.assertEqual(checklist.passed_count, 0)
        self.assertFalse(checklist.is_perfect)
        self.assertTrue(all(item.passed is False for item in checklist.criteria))

    def test_trend_requires_price_above_both_averages(self):
        self.assertTrue(_base(price=800, sma50=760, sma200=650).criteria[0].passed)
        self.assertFalse(_base(price=700, sma50=760, sma200=650).criteria[0].passed)  # below 50d
        self.assertFalse(_base(price=800, sma50=760, sma200=850).criteria[0].passed)  # below 200d

    def test_trend_is_unconfirmed_without_a_200_day_average(self):
        criterion = _base(sma200=None).criteria[0]
        self.assertIsNone(criterion.passed)
        self.assertEqual(criterion.status, "unconfirmed")

    def test_momentum_requires_macd_bullish_and_rsi_in_range(self):
        self.assertTrue(_base(macd=12, macd_signal=8, rsi14=58).criteria[1].passed)
        self.assertFalse(_base(macd=5, macd_signal=8, rsi14=58).criteria[1].passed)  # MACD bearish
        self.assertFalse(_base(macd=12, macd_signal=8, rsi14=30).criteria[1].passed)  # RSI too low
        self.assertFalse(_base(macd=12, macd_signal=8, rsi14=90).criteria[1].passed)  # RSI too high

    def test_momentum_range_boundaries_are_inclusive(self):
        self.assertTrue(_base(macd=1, macd_signal=0, rsi14=40.0).criteria[1].passed)
        self.assertTrue(_base(macd=1, macd_signal=0, rsi14=75.0).criteria[1].passed)
        self.assertFalse(_base(macd=1, macd_signal=0, rsi14=39.9).criteria[1].passed)
        self.assertFalse(_base(macd=1, macd_signal=0, rsi14=75.1).criteria[1].passed)

    def test_relative_strength_requires_beating_the_benchmark(self):
        self.assertTrue(_base(security_return_pct=0.10, benchmark_return_pct=0.05).criteria[2].passed)
        self.assertTrue(_base(security_return_pct=0.05, benchmark_return_pct=0.05).criteria[2].passed)  # tie passes
        self.assertFalse(_base(security_return_pct=0.02, benchmark_return_pct=0.05).criteria[2].passed)

    def test_relative_strength_unconfirmed_without_a_benchmark_series(self):
        criterion = _base(benchmark_return_pct=None).criteria[2]
        self.assertIsNone(criterion.passed)

    def test_growth_requires_both_measures_positive(self):
        self.assertTrue(_base(revenue_growth_pct=0.1, earnings_growth_pct=0.1).criteria[3].passed)
        self.assertFalse(_base(revenue_growth_pct=0.1, earnings_growth_pct=-0.1).criteria[3].passed)
        self.assertFalse(_base(revenue_growth_pct=-0.1, earnings_growth_pct=0.1).criteria[3].passed)

    def test_growth_unconfirmed_when_either_figure_is_missing(self):
        self.assertIsNone(_base(revenue_growth_pct=None).criteria[3].passed)
        self.assertIsNone(_base(earnings_growth_pct=None).criteria[3].passed)

    def test_street_conviction_requires_target_above_price(self):
        self.assertTrue(_base(price=100, analyst_target=110).criteria[4].passed)
        self.assertFalse(_base(price=100, analyst_target=90).criteria[4].passed)

    def test_street_conviction_unconfirmed_without_a_target(self):
        self.assertIsNone(_base(analyst_target=None).criteria[4].passed)
        self.assertIsNone(_base(analyst_target=0).criteria[4].passed)

    def test_unconfirmed_criteria_are_never_counted_as_passed(self):
        checklist = _base(sma200=None, revenue_growth_pct=None, earnings_growth_pct=None, analyst_target=None)
        self.assertEqual(checklist.unconfirmed_count, 3)
        self.assertLessEqual(checklist.passed_count, 2)
        self.assertFalse(checklist.is_perfect)

    def test_real_axon_style_evidence_is_a_mixed_read_not_a_rubber_stamp(self):
        # Fixture pinned to a real observed AXON snapshot: strong trend and street
        # support, but momentum has cooled and earnings growth was negative. The
        # checklist must not wave this through as a clean 5/5.
        checklist = _base(
            price=566.56, sma50=560.14, sma200=506.29,
            rsi14=46.26, macd=13.02, macd_signal=19.75,
            security_return_pct=0.188, benchmark_return_pct=0.011,
            revenue_growth_pct=0.353, earnings_growth_pct=-0.182,
            analyst_target=693.40,
        )
        self.assertEqual(checklist.passed_count, 3)
        self.assertFalse(checklist.criteria[1].passed)  # momentum
        self.assertFalse(checklist.criteria[3].passed)  # growth


if __name__ == "__main__":
    unittest.main()
