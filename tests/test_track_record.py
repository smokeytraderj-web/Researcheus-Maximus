import unittest

from research.track_record import BUY_SIDE_RATINGS, build_picks, score_picks


def _row(date, ticker, rating, price, horizon="Medium Term"):
    return {
        "logged_at": date,
        "ticker": ticker,
        "company": f"{ticker} Inc.",
        "horizon": horizon,
        "rating": rating,
        "confidence": "High",
        "price": str(price),
    }


class PickConstructionTests(unittest.TestCase):
    """These rules decide what the product is judged on, so they must not drift."""

    def test_buy_side_rating_opens_a_pick(self):
        for rating in BUY_SIDE_RATINGS:
            picks = build_picks([_row("2026-01-05", "AAPL", rating, 100.0)])
            self.assertEqual(len(picks), 1, rating)
            self.assertTrue(picks[0].is_open)
            self.assertEqual(picks[0].entry_price, 100.0)

    def test_hold_or_sell_alone_is_not_a_pick(self):
        for rating in ("Hold", "Reduce", "Sell", "Avoid"):
            self.assertEqual(build_picks([_row("2026-01-05", "KO", rating, 60.0)]), (), rating)

    def test_reaffirming_a_buy_does_not_reset_the_entry(self):
        picks = build_picks([
            _row("2026-01-05", "AAPL", "Buy", 100.0),
            _row("2026-02-05", "AAPL", "Add", 130.0),
            _row("2026-03-05", "AAPL", "Strong Buy", 150.0),
        ])
        self.assertEqual(len(picks), 1)
        # The original call is what gets judged, not the cheapest restatement.
        self.assertEqual(picks[0].entry_price, 100.0)
        self.assertEqual(picks[0].opened_at, "2026-01-05")
        self.assertTrue(picks[0].is_open)

    def test_a_non_buy_rating_closes_the_pick_at_that_price(self):
        picks = build_picks([
            _row("2026-01-05", "AAPL", "Buy", 100.0),
            _row("2026-04-05", "AAPL", "Hold", 120.0),
        ])
        self.assertEqual(len(picks), 1)
        self.assertFalse(picks[0].is_open)
        self.assertEqual(picks[0].exit_price, 120.0)
        self.assertEqual(picks[0].closed_by_rating, "Hold")

    def test_a_later_buy_opens_a_second_separate_pick(self):
        picks = build_picks([
            _row("2026-01-05", "AAPL", "Buy", 100.0),
            _row("2026-04-05", "AAPL", "Hold", 120.0),
            _row("2026-06-05", "AAPL", "Buy", 110.0),
        ])
        self.assertEqual(len(picks), 2)
        self.assertFalse(picks[0].is_open)
        self.assertTrue(picks[1].is_open)
        self.assertEqual(picks[1].entry_price, 110.0)

    def test_a_sell_before_any_buy_is_ignored(self):
        picks = build_picks([
            _row("2026-01-05", "NVDA", "Sell", 100.0),
            _row("2026-02-05", "NVDA", "Buy", 90.0),
        ])
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].entry_price, 90.0)

    def test_rows_out_of_order_are_still_paired_chronologically(self):
        picks = build_picks([
            _row("2026-04-05", "AAPL", "Hold", 120.0),
            _row("2026-01-05", "AAPL", "Buy", 100.0),
        ])
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].opened_at, "2026-01-05")
        self.assertEqual(picks[0].closed_at, "2026-04-05")

    def test_securities_are_tracked_independently(self):
        picks = build_picks([
            _row("2026-01-05", "AAPL", "Buy", 100.0),
            _row("2026-01-06", "MSFT", "Buy", 400.0),
            _row("2026-02-06", "MSFT", "Sell", 380.0),
        ])
        self.assertEqual({p.ticker for p in picks}, {"AAPL", "MSFT"})
        self.assertTrue(next(p for p in picks if p.ticker == "AAPL").is_open)
        self.assertFalse(next(p for p in picks if p.ticker == "MSFT").is_open)

    def test_a_missing_price_cannot_open_a_pick(self):
        self.assertEqual(build_picks([_row("2026-01-05", "AAPL", "Buy", 0)]), ())


class ScoringTests(unittest.TestCase):
    def _picks(self):
        return build_picks([
            _row("2026-01-05", "AAPL", "Buy", 100.0),
            _row("2026-04-05", "AAPL", "Hold", 120.0),
            _row("2026-02-01", "MSFT", "Buy", 400.0),
        ])

    def test_closed_and_open_picks_are_both_scored(self):
        record = score_picks(
            self._picks(),
            current_price=lambda ticker: 440.0 if ticker == "MSFT" else None,
            benchmark_return=lambda start, end: 0.05,
            today="2026-08-30",
        )
        self.assertEqual(len(record.scored), 2)
        by_ticker = {item.pick.ticker: item for item in record.scored}
        self.assertAlmostEqual(by_ticker["AAPL"].return_pct, 0.20, places=6)
        self.assertAlmostEqual(by_ticker["MSFT"].return_pct, 0.10, places=6)
        self.assertAlmostEqual(by_ticker["AAPL"].excess_pct, 0.15, places=6)

    def test_a_pick_without_a_resolvable_price_is_reported_not_dropped(self):
        record = score_picks(
            self._picks(),
            current_price=lambda _ticker: None,  # open pick cannot be marked
            benchmark_return=lambda _s, _e: None,
            today="2026-08-30",
        )
        self.assertEqual(len(record.scored), 1)
        self.assertEqual(len(record.unscored), 1)
        self.assertEqual(record.unscored[0].ticker, "MSFT")
        # An unmeasurable benchmark leaves the comparison blank rather than zero.
        self.assertIsNone(record.scored[0].benchmark_return_pct)
        self.assertIsNone(record.scored[0].excess_pct)

    def test_summary_statistics_reflect_only_scored_picks(self):
        record = score_picks(
            build_picks([
                _row("2026-01-05", "AAPL", "Buy", 100.0),
                _row("2026-04-05", "AAPL", "Hold", 120.0),   # +20%
                _row("2026-01-05", "XYZ", "Buy", 100.0),
                _row("2026-04-05", "XYZ", "Hold", 80.0),     # -20%
            ]),
            current_price=lambda _t: None,
            benchmark_return=lambda _s, _e: 0.0,
            today="2026-08-30",
        )
        self.assertEqual(len(record.scored), 2)
        self.assertAlmostEqual(record.hit_rate, 0.5)
        self.assertAlmostEqual(record.average_return_pct, 0.0, places=6)

    def test_an_empty_log_produces_an_empty_record(self):
        record = score_picks((), lambda _t: None, lambda _s, _e: None)
        self.assertFalse(record.has_picks)
        self.assertIsNone(record.hit_rate)
        self.assertIsNone(record.average_return_pct)


if __name__ == "__main__":
    unittest.main()
