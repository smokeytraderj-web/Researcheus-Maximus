import math
import unittest

from research.options import (
    ExpiryVolatility,
    OptionsSnapshot,
    atm_implied_volatility,
    build_expiry_volatility,
    delta_skew,
    expected_move,
    options_insight,
)


class ExpectedMoveTests(unittest.TestCase):
    def test_one_year_at_twenty_percent_is_twenty_percent_of_spot(self):
        self.assertAlmostEqual(expected_move(100.0, 20.0, 365), 20.0, places=6)

    def test_move_scales_with_the_square_root_of_time(self):
        quarter = expected_move(100.0, 20.0, 91)
        year = expected_move(100.0, 20.0, 365)
        self.assertAlmostEqual(quarter / year, math.sqrt(91 / 365), places=6)

    def test_degenerate_inputs_produce_no_move_rather_than_an_error(self):
        self.assertEqual(expected_move(0.0, 20.0, 30), 0.0)
        self.assertEqual(expected_move(100.0, 0.0, 30), 0.0)
        self.assertEqual(expected_move(100.0, 20.0, 0), 0.0)


class SkewTests(unittest.TestCase):
    def _contracts(self, deltas, ivs):
        return [{"delta": d, "iv": v} for d, v in zip(deltas, ivs)]

    def test_richer_puts_report_positive_skew(self):
        calls = self._contracts([0.35, 0.20], [22.0, 24.0])
        puts = self._contracts([-0.35, -0.20], [26.0, 28.0])
        self.assertAlmostEqual(delta_skew(calls, puts), 4.0, places=6)

    def test_richer_calls_report_negative_skew(self):
        calls = self._contracts([0.35, 0.20], [28.0, 30.0])
        puts = self._contracts([-0.35, -0.20], [22.0, 24.0])
        self.assertLess(delta_skew(calls, puts), 0.0)

    def test_chain_too_narrow_reports_nothing_rather_than_extrapolating(self):
        # Neither side is quoted out to 0.25 delta.
        calls = self._contracts([0.68, 0.40], [22.0, 23.0])
        puts = self._contracts([-0.60, -0.35], [25.0, 26.0])
        self.assertIsNone(delta_skew(calls, puts))

    def test_missing_greeks_are_ignored_not_guessed(self):
        calls = self._contracts([0.35, 0.20], [22.0, 24.0])
        puts = [{"delta": None, "iv": 26.0}, {"delta": -0.20, "iv": 28.0}]
        self.assertIsNone(delta_skew(calls, puts))


class AtmVolatilityTests(unittest.TestCase):
    def test_interpolates_between_bracketing_strikes(self):
        contracts = [{"strike": 300.0, "iv": 20.0}, {"strike": 320.0, "iv": 24.0}]
        self.assertAlmostEqual(atm_implied_volatility(contracts, 310.0), 22.0, places=6)

    def test_spot_outside_quoted_strikes_uses_the_nearest_quote(self):
        contracts = [{"strike": 300.0, "iv": 20.0}, {"strike": 320.0, "iv": 24.0}]
        self.assertEqual(atm_implied_volatility(contracts, 500.0), 24.0)

    def test_no_usable_quotes_reports_nothing(self):
        self.assertIsNone(atm_implied_volatility([], 310.0))
        self.assertIsNone(atm_implied_volatility([{"strike": None, "iv": None}], 310.0))


class ExpiryBuildTests(unittest.TestCase):
    def _chain(self, **overrides):
        chain = {
            "expiration": "2026-09-18",
            "underlying_price": 320.0,
            "calls": [
                {"strike": 310.0, "iv": 24.0, "delta": 0.65, "days_till_expiration": 18},
                {"strike": 330.0, "iv": 22.0, "delta": 0.20, "days_till_expiration": 18},
            ],
            "puts": [
                {"strike": 310.0, "iv": 24.0, "delta": -0.20, "days_till_expiration": 18},
                {"strike": 330.0, "iv": 22.0, "delta": -0.65, "days_till_expiration": 18},
            ],
        }
        chain.update(overrides)
        return chain

    def test_builds_a_summary_from_a_valid_chain(self):
        summary = build_expiry_volatility(self._chain())
        self.assertEqual(summary.expiration, "2026-09-18")
        self.assertEqual(summary.days_to_expiry, 18)
        self.assertAlmostEqual(summary.atm_iv, 23.0, places=6)
        self.assertGreater(summary.expected_move, 0.0)
        self.assertAlmostEqual(summary.expected_move_pct, summary.expected_move / 320.0, places=9)

    def test_empty_or_priceless_chain_yields_nothing(self):
        self.assertIsNone(build_expiry_volatility(self._chain(calls=[], puts=[])))
        self.assertIsNone(build_expiry_volatility(self._chain(underlying_price=0)))
        self.assertIsNone(build_expiry_volatility(self._chain(underlying_price=None)))


class InsightTests(unittest.TestCase):
    def _snapshot(self, expiries):
        return OptionsSnapshot("NASDAQ:AAPL", 320.0, tuple(expiries), (), (), (), "")

    def test_insight_names_volatility_and_expected_move(self):
        front = ExpiryVolatility("2026-09-18", 18, 24.0, 12.5, 0.039, 0.4)
        text = options_insight(self._snapshot([front]))
        self.assertIn("24.0%", text)
        self.assertIn("18 days", text)
        self.assertIn("12.50", text)
        self.assertIn("balanced", text)

    def test_pronounced_put_skew_is_called_out(self):
        front = ExpiryVolatility("2026-09-18", 18, 24.0, 12.5, 0.039, 5.0)
        self.assertIn("paying up for downside protection", options_insight(self._snapshot([front])))

    def test_term_structure_is_described_when_more_than_one_expiry(self):
        front = ExpiryVolatility("2026-09-18", 18, 22.0, 10.0, 0.03, None)
        back = ExpiryVolatility("2026-12-18", 109, 26.0, 30.0, 0.09, None)
        self.assertIn("rising with time", options_insight(self._snapshot([front, back])))

    def test_no_expiries_yields_no_sentence(self):
        self.assertEqual(options_insight(self._snapshot([])), "")


if __name__ == "__main__":
    unittest.main()
