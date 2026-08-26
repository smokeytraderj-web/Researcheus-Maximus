import unittest

import numpy as np
import pandas as pd

from research.technical import analyze_history, technical_finding


class TechnicalAnalysisTests(unittest.TestCase):
    def _history(self, count=260):
        dates = pd.date_range("2025-01-01", periods=count, freq="B")
        close = np.linspace(100, 170, count) + np.sin(np.arange(count) / 8) * 2
        return pd.DataFrame(
            {
                "Close": close,
                "High": close + 2,
                "Low": close - 2,
                "Volume": np.linspace(1_000_000, 1_400_000, count),
            },
            index=dates,
        )

    def test_calculates_multi_factor_snapshot(self):
        snapshot = analyze_history(self._history())
        self.assertGreater(snapshot.price, snapshot.sma50)
        self.assertIsNotNone(snapshot.sma200)
        self.assertGreater(snapshot.resistance, snapshot.support)
        self.assertGreater(snapshot.atr14, 0)

    def test_finding_uses_fixed_rating_scale(self):
        finding = technical_finding(analyze_history(self._history()))
        self.assertIn(finding.rating.value, {"Strong Buy", "Buy", "Add", "Hold", "Reduce", "Sell", "Avoid"})
        self.assertGreaterEqual(len(finding.signals), 3)

    def test_rejects_insufficient_history(self):
        with self.assertRaises(ValueError):
            analyze_history(self._history(30))


if __name__ == "__main__":
    unittest.main()
