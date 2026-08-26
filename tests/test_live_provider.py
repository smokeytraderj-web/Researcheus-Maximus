import unittest

import numpy as np
import pandas as pd

from core.models import Horizon, Rating, ResearchRequest
from research.live_provider import (
    LiveResearchProvider,
    _combine_ratings,
    _comparison_benchmark,
    _direct_chart_history,
    _direct_decision_answer,
    _nasdaq_history,
    _usable_ycharts_metric,
)


class _Ticker:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def history(self, **_kwargs):
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return value


class _YF:
    def __init__(self, output):
        self.output = output

    def download(self, *_args, **_kwargs):
        return self.output


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "chart": {
                "result": [{
                    "timestamp": [1_700_000_000, 1_700_086_400],
                    "indicators": {"quote": [{
                        "open": [100.0, 101.0], "high": [102.0, 103.0],
                        "low": [99.0, 100.0], "close": [101.0, 102.0],
                        "volume": [1_000_000, 1_100_000],
                    }]},
                }],
                "error": None,
            }
        }


class _Session:
    def get(self, *_args, **_kwargs):
        return _Response()


class _NasdaqResponse(_Response):
    def json(self):
        return {
            "data": {
                "tradesTable": {
                    "rows": [
                        {"date": "08/25/2026", "close": "$350.20", "volume": "1,100,000", "open": "$345.00", "high": "$352.00", "low": "$344.00"},
                        {"date": "08/24/2026", "close": "$346.00", "volume": "1,000,000", "open": "$342.00", "high": "$348.00", "low": "$340.00"},
                    ]
                }
            },
            "status": {"rCode": 200},
        }


class _NasdaqSession:
    def get(self, *_args, **_kwargs):
        return _NasdaqResponse()


def _history(rows=260):
    dates = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = np.linspace(100, 140, rows)
    return pd.DataFrame({"Close": close, "High": close + 1, "Low": close - 1, "Volume": 1_000_000}, index=dates)


class HistoryFallbackTests(unittest.TestCase):
    def test_comparison_benchmark_prefers_industry_then_sector(self):
        self.assertEqual(
            _comparison_benchmark(
                {"sector": "Technology", "industry": "Semiconductors"},
                {"sector": "Technology", "industry": "Semiconductor Equipment"},
            )[0],
            "SOXX",
        )
        self.assertEqual(
            _comparison_benchmark({"sector": "Industrials"}, {"sector": "Industrials"})[0],
            "XLI",
        )
        self.assertEqual(
            _comparison_benchmark({"sector": "Technology"}, {"sector": "Healthcare"})[0],
            "SPY",
        )

    def test_zero_ycharts_target_is_not_usable_evidence(self):
        self.assertFalse(_usable_ycharts_metric("YCharts price target", 0))
        self.assertTrue(_usable_ycharts_metric("YCharts price target", 245.0))
        self.assertTrue(_usable_ycharts_metric("YCharts price target upside", -0.08))

    def test_uses_second_ticker_history_attempt(self):
        result = LiveResearchProvider._history(_YF(pd.DataFrame()), _Ticker([pd.DataFrame(), _history()]), "AXON")
        self.assertEqual(len(result), 260)

    def test_custom_range_filters_history_and_marks_analysis_context(self):
        frame = _history(320)
        result = LiveResearchProvider._history(
            _YF(pd.DataFrame()),
            _Ticker([frame]),
            "TSLA",
            None,
            "2025-03-01",
            "2025-12-01",
        )
        self.assertTrue(result.attrs["custom_range"])
        self.assertEqual(result.attrs["analysis_range_label"], "2025-03-01 to 2025-12-01")
        self.assertGreaterEqual(result.index.min(), pd.Timestamp("2025-03-01"))
        self.assertLessEqual(result.index.max(), pd.Timestamp("2025-12-01"))

    def test_uses_download_after_history_errors(self):
        result = LiveResearchProvider._history(_YF(_history()), _Ticker([RuntimeError("one"), RuntimeError("two")]), "AXON")
        self.assertIn("Close", result.columns)

    def test_reports_all_empty_attempts(self):
        with self.assertRaisesRegex(RuntimeError, "No usable live price history"):
            LiveResearchProvider._history(_YF(pd.DataFrame()), _Ticker([pd.DataFrame(), pd.DataFrame()]), "AXON")

    def test_direct_chart_fallback_has_expected_ohlcv(self):
        history = _direct_chart_history(_Session(), "TSLA")
        self.assertEqual(list(history.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(history.attrs["market_data_source"], "Yahoo Finance direct chart API")

    def test_uses_direct_chart_after_ticker_history_errors(self):
        result = LiveResearchProvider._history(
            _YF(pd.DataFrame()), _Ticker([RuntimeError("one"), RuntimeError("two")]), "TSLA", _Session()
        )
        self.assertEqual(len(result), 2)

    def test_nasdaq_fallback_normalizes_currency_and_dates(self):
        history = _nasdaq_history(_NasdaqSession(), "TSLA")
        self.assertEqual(float(history.iloc[-1]["Close"]), 350.20)
        self.assertEqual(history.attrs["market_data_source"], "Nasdaq historical prices")

    def test_long_term_rating_prioritizes_fundamentals(self):
        lead, technical_weight, fundamental_weight = _combine_ratings(Rating.SELL, Rating.HOLD, Horizon.LONG)
        self.assertEqual(lead, Rating.HOLD)
        self.assertEqual((technical_weight, fundamental_weight), (20, 80))

    def test_deep_analysis_prioritizes_technical_evidence(self):
        lead, technical_weight, fundamental_weight = _combine_ratings(
            Rating.SELL,
            Rating.BUY,
            Horizon.ALL,
            deep_analysis=True,
        )
        self.assertEqual(lead, Rating.REDUCE)
        self.assertEqual((technical_weight, fundamental_weight), (70, 30))

    def test_buy_question_gets_a_direct_conditional_answer(self):
        answer = _direct_decision_answer(
            ResearchRequest("TSLA", Horizon.ALL, decision_intent="buy"),
            "Tesla",
            Rating.HOLD,
            Rating.REDUCE,
        )
        self.assertTrue(answer.startswith("Direct answer:"))
        self.assertIn("not a clear buy", answer)

    def test_historical_range_is_not_presented_as_current_advice(self):
        answer = _direct_decision_answer(
            ResearchRequest(
                "TSLA",
                Horizon.ALL,
                decision_intent="buy",
                custom_start="2024-01-01",
                custom_end="2025-01-01",
            ),
            "Tesla",
            Rating.BUY,
            Rating.BUY,
        )
        self.assertTrue(answer.startswith("Historical conclusion:"))
        self.assertIn("not a current buy or sell conclusion", answer)


if __name__ == "__main__":
    unittest.main()
