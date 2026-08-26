import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from core.models import Horizon, Rating, SpecialistFinding
from research.technical import (
    analyze_history,
    fibonacci_decision_insight,
    historical_trade_examples,
    incorporate_relative_performance,
    momentum_decision_insight,
    render_chart,
    render_fibonacci_chart,
    render_momentum_chart,
    render_relative_performance_chart,
    render_risk_chart,
    render_trade_case_chart,
    strategies,
    technical_action_plan,
    technical_finding,
    trend_decision_insight,
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
        self.assertIn("Because price", finding.summary)

    def test_deep_chart_insights_connect_evidence_to_the_decision(self):
        snapshot = analyze_history(self._history())
        rating = technical_finding(snapshot).rating
        trend = trend_decision_insight(snapshot, rating)
        fibonacci = fibonacci_decision_insight(snapshot, rating)
        momentum = momentum_decision_insight(snapshot, rating)
        self.assertIn("Because price", trend)
        self.assertIn("setup", trend)
        self.assertIn("setup", fibonacci)
        self.assertIn("MACD", momentum)
        self.assertIn("RSI", momentum)

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

    def test_zero_volume_fund_omits_volume_evidence_and_renders_clean_chart(self):
        history = self._history()
        history["Volume"] = 0
        snapshot = analyze_history(history)
        self.assertFalse(snapshot.volume_available)
        self.assertFalse(any(label.startswith("Volume") for label, _value in snapshot.as_metrics()))
        self.assertIn("volume was excluded", technical_finding(snapshot).signals[-1])
        with tempfile.TemporaryDirectory() as folder:
            output = render_chart(history, "BDMIX", snapshot, Path(folder) / "fund-price.png")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)

    def test_weak_trend_strategy_requires_reclaim_before_entry(self):
        frame = self._history()
        frame.loc[frame.index[-30]:, "Close"] = np.linspace(170, 120, 30)
        frame.loc[frame.index[-30]:, "High"] = frame.loc[frame.index[-30]:, "Close"] + 2
        frame.loc[frame.index[-30]:, "Low"] = frame.loc[frame.index[-30]:, "Close"] - 2
        snapshot = analyze_history(frame)
        first = strategies(snapshot, Horizon.LONG)[0]
        self.assertEqual(first.name, "Wait for the trend to improve")
        self.assertIn("moves back above", first.action_zone)

    def test_action_plan_builds_entry_stop_targets_and_defined_risk_option(self):
        snapshot = analyze_history(self._history())
        plan = technical_action_plan(snapshot, Rating.BUY, "EQUITY")
        self.assertLess(plan.entry_low, plan.entry_high)
        self.assertLess(plan.stop_level, plan.entry_low)
        self.assertGreater(plan.first_target, (plan.entry_low + plan.entry_high) / 2)
        self.assertGreater(plan.stop_pct, 0)
        self.assertIn("calculated rather than fixed at 7%", plan.rationale[1])
        self.assertIn("call spread", plan.options_strategy.lower())
        self.assertIn("entire debit", plan.options_risk.lower())

    def test_choppy_action_plan_uses_patient_limit_and_cash_secured_put(self):
        history = self._history()
        x = np.arange(len(history))
        history["Close"] = 100 + np.sin(x / 3) * 1.5
        history["High"] = history["Close"] + 1
        history["Low"] = history["Close"] - 1
        snapshot = analyze_history(history)
        plan = technical_action_plan(snapshot, Rating.HOLD, "ETF")
        self.assertIn(plan.market_condition, {"Choppy / range-bound", "Volatile and mixed"})
        self.assertIn("patient", plan.order_type.lower())
        self.assertIn("cash-secured put", plan.options_strategy.lower())
        self.assertIn("assignment", plan.options_risk.lower())

    def test_bearish_action_plan_requires_reclaim_and_avoids_new_calls(self):
        history = self._history()
        history["Close"] = np.linspace(170, 100, len(history))
        history["High"] = history["Close"] + 2
        history["Low"] = history["Close"] - 2
        snapshot = analyze_history(history)
        plan = technical_action_plan(snapshot, Rating.REDUCE, "EQUITY")
        self.assertTrue(plan.stance.startswith("Wait"))
        self.assertIn("No order", plan.order_type)
        self.assertIn("protective put", plan.options_strategy.lower())

    def test_mutual_fund_action_plan_does_not_invent_options(self):
        snapshot = analyze_history(self._history())
        plan = technical_action_plan(snapshot, Rating.ADD, "MUTUALFUND")
        self.assertEqual(plan.options_strategy, "")

    def test_action_plan_annotations_render_on_primary_chart(self):
        history = self._history()
        snapshot = analyze_history(history)
        plan = technical_action_plan(snapshot, Rating.BUY, "EQUITY")
        with tempfile.TemporaryDirectory() as folder:
            output = render_chart(history, "AXON", snapshot, Path(folder) / "action-plan.png", plan)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)

    def test_relative_outperformance_strengthens_the_technical_rating(self):
        primary = self._history()
        benchmark = self._history()
        benchmark["Close"] = np.linspace(100, 104, len(benchmark))
        finding = SpecialistFinding(Rating.HOLD, "Base technical view.", ("Base signal.",))
        revised, metrics, insight = incorporate_relative_performance(finding, primary, {"SPY": benchmark})
        self.assertEqual(revised.rating, Rating.ADD)
        self.assertEqual(metrics[0][0], "3-month return vs. SPY")
        self.assertIn("changed the Technical Setup from Neutral to Bullish", insight)

    def test_deep_analysis_charts_render(self):
        primary = self._history()
        benchmark = self._history()
        benchmark["Close"] = np.linspace(100, 145, len(benchmark))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outputs = (
                render_chart(primary, "AXON", analyze_history(primary), root / "price.png"),
                render_fibonacci_chart(primary, "AXON", analyze_history(primary), root / "fibonacci.png"),
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

    def test_historical_trade_cases_are_rules_based_and_rendered(self):
        count = 260
        x = np.arange(count)
        close = 100 + x * 0.2 + np.sin(x / 10) * 5
        history = pd.DataFrame(
            {
                "Open": close + 0.1,
                "Close": close,
                "High": close + 1,
                "Low": close - 1,
                "Volume": np.full(count, 1_000_000),
            },
            index=pd.date_range("2025-01-01", periods=count, freq="B"),
        )
        cases = historical_trade_examples(history)
        self.assertGreaterEqual(len(cases), 2)
        for case in cases:
            self.assertLess(case.signal_date, case.entry_date)
            self.assertLess(case.initial_stop, case.entry_price)
        with tempfile.TemporaryDirectory() as folder:
            output = render_trade_case_chart(history, "QQQ", cases[0], Path(folder) / "trade.png")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
