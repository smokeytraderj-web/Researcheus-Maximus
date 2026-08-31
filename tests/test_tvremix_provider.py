import unittest

from research.tvremix_provider import _build_levels, tag_macd, tag_rsi, tag_sma


class TVRemixIndicatorTaggingTests(unittest.TestCase):
    def test_tag_rsi_thresholds(self):
        self.assertEqual(tag_rsi(75.0), "Sell")
        self.assertEqual(tag_rsi(25.0), "Buy")
        self.assertEqual(tag_rsi(50.0), "Neutral")
        self.assertEqual(tag_rsi(70.0), "Neutral")
        self.assertEqual(tag_rsi(30.0), "Neutral")
        self.assertEqual(tag_rsi(None), "")

    def test_tag_macd_above_below_signal(self):
        self.assertEqual(tag_macd(1.5, 0.9), "Buy")
        self.assertEqual(tag_macd(-0.5, 0.2), "Sell")
        self.assertEqual(tag_macd(None, 0.2), "")
        self.assertEqual(tag_macd(1.0, None), "")

    def test_tag_sma_price_above_below(self):
        self.assertEqual(tag_sma(320.0, 310.0), "Buy")
        self.assertEqual(tag_sma(300.0, 310.0), "Sell")
        self.assertEqual(tag_sma(None, 310.0), "")


class TVRemixLevelBuildingTests(unittest.TestCase):
    def test_fib_levels_sorted_descending_with_now_inserted(self):
        levels = _build_levels(swing_high=200.0, swing_low=100.0, current_price=150.0)
        prices = [level.price for level in levels]
        self.assertEqual(prices, sorted(prices, reverse=True))
        now_level = next(level for level in levels if level.label == "Now")
        self.assertEqual(now_level.price, 150.0)
        self.assertEqual(now_level.pct_from_now, 0.0)
        swing_high_level = next(level for level in levels if "swing high" in level.label)
        self.assertEqual(swing_high_level.price, 200.0)
        swing_low_level = next(level for level in levels if "swing low" in level.label)
        self.assertEqual(swing_low_level.price, 100.0)

    def test_pct_from_now_reflects_distance(self):
        levels = _build_levels(swing_high=110.0, swing_low=90.0, current_price=100.0)
        by_label = {level.label: level for level in levels}
        self.assertAlmostEqual(by_label["Fib 100% (swing high)"].pct_from_now, 0.10, places=4)
        self.assertAlmostEqual(by_label["Fib 0% (swing low)"].pct_from_now, -0.10, places=4)


if __name__ == "__main__":
    unittest.main()
