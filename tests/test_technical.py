import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from core.models import Horizon, Rating, SpecialistFinding
from research.technical import (
    analyze_history,
    incorporate_relative_performance,
    render_chart,
    render_momentum_chart,
    render_relative_performance_chart,
    render_risk_chart,
    strategies,
    technical_finding,
)


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
        self.assertGreater(snapshot.fib_swing_high, snapshot.fib_swing_low)
        self.assertGreater(snapshot.fib_38_2, snapshot.fib_50)
        self.assertGreater(snapshot.fib_50, snapshot.fib_61_8)

    def test_finding_uses_fixed_rating_scale(self):
        finding = technical_finding(analyze_history(self._history()))
        self.assertIn(finding.rating.value, {"Strong Buy", "Buy", "Add", "Hold", "Reduce", "Sell", "Avoid"})
        self.assertGreaterEqual(len(finding.signals), 3)
        self.assertTrue(any("Fibonacci" in signal for signal in finding.signals))

    def test_custom_range_drives_fibonacci_and_performance_window(self):
        frame = self._history()
        frame.attrs["custom_range"] = True
        frame.attrs["analysis_range_label"] = "2025-01-01 to 2025-12-31"
        snapshot = analyze_history(frame)
        self.assertEqual(snapshot.fibonacci_range_label, "2025-01-01 to 2025-12-31")
        self.assertEqual(snapshot.performance_label, "Analysis-range")
        self.assertAlmostEqual(snapshot.fib_swing_low, float(frame["Low"].min()))

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

    def test_relative_outperformance_strengthens_the_technical_rating(self):
        primary = self._history()
        benchmark = self._history()
        benchmark["Close"] = np.linspace(100, 104, len(benchmark))
        finding = SpecialistFinding(Rating.HOLD, "Base technical view.", ("Base signal.",))
        revised, metrics, insight = incorporate_relative_performance(finding, primary, {"SPY": benchmark})
        self.assertEqual(revised.rating, Rating.ADD)
        self.assertEqual(metrics[0][0], "3-month return vs. SPY")
        self.assertIn("moved the technical rating", insight)

    def test_deep_analysis_charts_render(self):
        primary = self._history()
        benchmark = self._history()
        benchmark["Close"] = np.linspace(100, 145, len(benchmark))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outputs = (
                render_chart(primary, "AXON", analyze_history(primary), root / "price.png"),
                render_momentum_chart(primary, "AXON", root / "momentum.png"),
                render_relative_performance_chart(
                    {"AXON": primary, "SPY": benchmark},
                    root / "relative.png",
                ),
                render_risk_chart(primary, "AXON", root / "risk.png"),
            )
            for output in outputs:
                self.assertTrue(output.is_file())
                self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
