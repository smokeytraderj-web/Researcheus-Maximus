import json
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
    render_stop_loss_evidence_chart,
    render_total_return_chart,
    render_volume_profile_chart,
    render_trade_case_chart,
    strategies,
    stop_loss_decision_insights,
    technical_action_plan,
    technical_finding,
    total_return_chart_insights,
    trend_decision_insight,
    VALUE_AREA_SHARE,
    volume_profile,
    volume_profile_insight,
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
        if plan.reward_risk < 1.5:
            self.assertIn("No order", plan.order_type)
            self.assertEqual(plan.options_strategy, "")
        else:
            self.assertIn("call spread", plan.options_strategy.lower())
            self.assertIn("entire debit", plan.options_risk.lower())

    def test_stop_loss_evidence_explains_structure_volatility_and_payoff(self):
        history = self._history()
        snapshot = analyze_history(history)
        plan = technical_action_plan(snapshot, Rating.BUY, "EQUITY")
        insights = stop_loss_decision_insights(snapshot, plan)
        self.assertEqual(len(insights), 4)
        self.assertIn("Structure:", insights[0])
        self.assertIn("ATR", insights[1])
        self.assertIn("reward/risk", insights[2])
        with tempfile.TemporaryDirectory() as folder:
            output = render_stop_loss_evidence_chart(
                history,
                "AXON",
                snapshot,
                plan,
                Path(folder) / "stop-evidence.png",
            )
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)

    def test_choppy_action_plan_uses_patient_limit_and_cash_secured_put(self):
        history = self._history()
        x = np.arange(len(history))
        history["Close"] = 100 + np.sin(x / 3) * 1.5
        history["High"] = history["Close"] + 1
        history["Low"] = history["Close"] - 1
        snapshot = analyze_history(history)
        plan = technical_action_plan(snapshot, Rating.HOLD, "ETF")
        self.assertIn(plan.market_condition, {"Choppy / range-bound", "Volatile and mixed"})
        if plan.reward_risk < 1.5:
            self.assertIn("No order", plan.order_type)
            self.assertEqual(plan.options_strategy, "")
        else:
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

    def test_unknown_security_type_does_not_invent_options(self):
        snapshot = analyze_history(self._history())
        plan = technical_action_plan(snapshot, Rating.BUY, "")
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

    def test_ytd_total_return_chart_and_bullets_use_the_same_visible_dates(self):
        primary = self._history()
        benchmark = self._history()
        benchmark["Close"] = np.linspace(100, 120, len(benchmark))
        histories = {"AXON": primary, "SPY": benchmark}
        insights = total_return_chart_insights(
            histories,
            "AXON",
            "SPY",
            "YTD",
            Rating.BUY,
            "2025-01-01",
            "2025-12-31",
        )
        self.assertEqual(len(insights), 3)
        self.assertIn("AXON returned", insights[0])
        self.assertIn("outperformed", insights[1])
        self.assertIn("supports", insights[2])
        with tempfile.TemporaryDirectory() as folder:
            output = render_total_return_chart(
                histories,
                Path(folder) / "ytd-total-return.png",
                "YTD",
                "SPY",
                "2025-01-01",
                "2025-12-31",
            )
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)

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
                render_stop_loss_evidence_chart(
                    primary,
                    "AXON",
                    analyze_history(primary),
                    technical_action_plan(analyze_history(primary), Rating.BUY, "EQUITY"),
                    root / "stop-loss.png",
                ),
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


class VolumeProfileTests(unittest.TestCase):
    def _history(self, volume=None) -> pd.DataFrame:
        index = pd.bdate_range("2025-06-02", periods=200)
        generator = np.random.default_rng(12)
        close = pd.Series(300 + np.cumsum(generator.normal(0.1, 2.5, len(index))), index=index)
        return pd.DataFrame(
            {
                "Open": close.shift(1).fillna(close),
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": generator.integers(30_000_000, 90_000_000, len(index)) if volume is None else volume,
            },
            index=index,
        )

    def test_profile_conserves_volume_and_brackets_the_point_of_control(self):
        history = self._history()
        profile = volume_profile(history)
        self.assertIsNotNone(profile)
        # Every share traded is placed somewhere in the profile, never invented or lost.
        self.assertAlmostEqual(profile.total_volume, float(history["Volume"].sum()), delta=1.0)
        self.assertLessEqual(profile.value_area_low, profile.point_of_control)
        self.assertGreaterEqual(profile.value_area_high, profile.point_of_control)
        self.assertGreaterEqual(profile.point_of_control, float(history["Low"].min()))
        self.assertLessEqual(profile.point_of_control, float(history["High"].max()))

    def test_value_area_covers_at_least_the_target_share(self):
        profile = volume_profile(self._history())
        inside = sum(
            level_volume
            for price, level_volume in zip(profile.prices, profile.volumes)
            if profile.value_area_low <= price <= profile.value_area_high
        )
        self.assertGreaterEqual(inside / profile.total_volume, VALUE_AREA_SHARE)

    def test_point_of_control_lands_where_volume_concentrates(self):
        # Pin most volume into a narrow band and check the profile finds it.
        history = self._history()
        history["Close"] = 300.0
        history["High"] = 301.0
        history["Low"] = 299.0
        history.iloc[:20, history.columns.get_loc("Close")] = 260.0
        history.iloc[:20, history.columns.get_loc("High")] = 261.0
        history.iloc[:20, history.columns.get_loc("Low")] = 259.0
        profile = volume_profile(history)
        self.assertAlmostEqual(profile.point_of_control, 300.0, delta=2.0)

    def test_zero_volume_security_publishes_no_profile(self):
        self.assertIsNone(volume_profile(self._history(volume=0)))

    def test_insight_states_where_price_sits_relative_to_value(self):
        profile = volume_profile(self._history())
        above = volume_profile_insight(profile, profile.value_area_high + 25.0)
        below = volume_profile_insight(profile, profile.value_area_low - 25.0)
        inside = volume_profile_insight(profile, profile.point_of_control)
        self.assertIn("above the value area", above)
        self.assertIn("below the value area", below)
        self.assertIn("inside the value area", inside)

    def test_chart_renders_from_a_valid_profile(self):
        history = self._history()
        profile = volume_profile(history)
        with tempfile.TemporaryDirectory() as folder:
            output = render_volume_profile_chart(history, "AAPL", profile, Path(folder) / "vp.png")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)


class ChartHoverSidecarTests(unittest.TestCase):
    """The hover overlay is positioned purely from these fractions, so if the
    geometry drifts the read-out silently stops matching the pixels beneath it."""

    def _history(self) -> pd.DataFrame:
        index = pd.bdate_range("2025-06-02", periods=220)
        generator = np.random.default_rng(3)
        close = pd.Series(300 + np.cumsum(generator.normal(0.2, 3.0, len(index))), index=index)
        return pd.DataFrame(
            {
                "Open": close.shift(1).fillna(close),
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": generator.integers(30_000_000, 90_000_000, len(index)),
            },
            index=index,
        )

    def _sidecar(self, chart_path: Path) -> dict:
        sidecar = chart_path.with_suffix(chart_path.suffix + ".json")
        self.assertTrue(sidecar.is_file(), "chart did not write its hover sidecar")
        return json.loads(sidecar.read_text(encoding="utf-8"))

    def test_price_chart_sidecar_geometry_is_inside_the_image(self):
        history = self._history()
        snapshot = analyze_history(history)
        with tempfile.TemporaryDirectory() as folder:
            chart = render_chart(history, "AAPL", snapshot, Path(folder) / "price.png")
            data = self._sidecar(chart)

        frame = data["frame"]
        for edge in ("left", "right", "top", "bottom"):
            self.assertGreaterEqual(frame[edge], 0.0)
            self.assertLessEqual(frame[edge], 1.0)
        self.assertLess(frame["left"], frame["right"])
        self.assertLess(frame["top"], frame["bottom"])

        points = data["points"]
        self.assertGreater(len(points), 50)
        # Dates run left to right, and every close sits inside the plot area.
        self.assertEqual([p["x"] for p in points], sorted(p["x"] for p in points))
        for point in points:
            self.assertGreaterEqual(point["x"], 0.0)
            self.assertLessEqual(point["x"], 1.0)
            self.assertGreaterEqual(point["y"], 0.0)
            self.assertLessEqual(point["y"], 1.0)
            self.assertEqual(len(point["values"]), len(data["series"]))

    def test_momentum_sidecar_spans_both_panels_and_has_no_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            chart = render_momentum_chart(self._history(), "AAPL", Path(folder) / "momentum.png")
            data = self._sidecar(chart)

        # RSI over MACD: the crosshair covers most of the image height.
        self.assertGreater(data["frame"]["bottom"] - data["frame"]["top"], 0.5)
        self.assertIn("RSI (14)", data["series"])
        self.assertIn("MACD", data["series"])
        # A dot would be ambiguous across two y-axes, so none is published.
        self.assertTrue(all(point["y"] is None for point in data["points"]))


if __name__ == "__main__":
    unittest.main()
