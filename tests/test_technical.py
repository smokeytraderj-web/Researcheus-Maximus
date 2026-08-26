import unittest

import numpy as np
import pandas as pd

from core.models import Horizon
from research.technical import analyze_history, strategies, technical_finding


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

    def test_weak_trend_strategy_requires_reclaim_before_entry(self):
        frame = self._history()
        frame.loc[frame.index[-30]:, "Close"] = np.linspace(170, 120, 30)
        frame.loc[frame.index[-30]:, "High"] = frame.loc[frame.index[-30]:, "Close"] + 2
        frame.loc[frame.index[-30]:, "Low"] = frame.loc[frame.index[-30]:, "Close"] - 2
        snapshot = analyze_history(frame)
        first = strategies(snapshot, Horizon.LONG)[0]
        self.assertEqual(first.name, "Trend reclaim / staged entry")
        self.assertIn("Wait for a close back", first.action_zone)


if __name__ == "__main__":
    unittest.main()
