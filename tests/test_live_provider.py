import unittest

import numpy as np
import pandas as pd

from research.live_provider import LiveResearchProvider


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


def _history(rows=260):
    dates = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = np.linspace(100, 140, rows)
    return pd.DataFrame({"Close": close, "High": close + 1, "Low": close - 1, "Volume": 1_000_000}, index=dates)


class HistoryFallbackTests(unittest.TestCase):
    def test_uses_second_ticker_history_attempt(self):
        result = LiveResearchProvider._history(_YF(pd.DataFrame()), _Ticker([pd.DataFrame(), _history()]), "AXON")
        self.assertEqual(len(result), 260)

    def test_uses_download_after_history_errors(self):
        result = LiveResearchProvider._history(_YF(_history()), _Ticker([RuntimeError("one"), RuntimeError("two")]), "AXON")
        self.assertIn("Close", result.columns)

    def test_reports_all_empty_attempts(self):
        with self.assertRaisesRegex(RuntimeError, "No usable live price history"):
            LiveResearchProvider._history(_YF(pd.DataFrame()), _Ticker([pd.DataFrame(), pd.DataFrame()]), "AXON")


if __name__ == "__main__":
    unittest.main()
