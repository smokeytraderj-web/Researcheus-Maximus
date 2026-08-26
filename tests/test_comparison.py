import unittest

from core.models import Rating, SecurityIdentity, SpecialistFinding
from research.comparison import build_comparison_assessment
from research.technical import TechnicalSnapshot


def _snapshot(price: float, return_3m: float, score: int) -> TechnicalSnapshot:
    return TechnicalSnapshot(
        price=price,
        sma20=price * 0.98,
        sma50=price * 0.95,
        sma200=price * 0.90,
        rsi14=58,
        macd=2,
        macd_signal=1,
        atr14=3,
        volume_ratio=1.1,
        support=price * 0.9,
        resistance=price * 1.05,
        return_1m=0.04,
        return_3m=return_3m,
        fib_swing_low=price * 0.75,
        fib_swing_high=price * 1.05,
        fib_38_2=price * 0.94,
        fib_50=price * 0.90,
        fib_61_8=price * 0.86,
        score=score,
    )


class ComparisonAssessmentTests(unittest.TestCase):
    def test_prefers_security_with_more_like_for_like_edges(self):
        primary = SecurityIdentity("Alpha Inc.", "AAA", "NASDAQ", "USD")
        secondary = SecurityIdentity("Beta Inc.", "BBB", "NASDAQ", "USD")
        primary_technical = SpecialistFinding(Rating.BUY, "Constructive.", ())
        secondary_technical = SpecialistFinding(Rating.HOLD, "Mixed.", ())
        assessment = build_comparison_assessment(
            primary,
            100,
            {"forwardPE": 20, "revenueGrowth": 0.18, "profitMargins": 0.25},
            _snapshot(100, 0.20, 5),
            primary_technical,
            secondary,
            80,
            {"forwardPE": 28, "revenueGrowth": 0.10, "profitMargins": 0.16},
            _snapshot(80, 0.05, 0),
            secondary_technical,
        )
        self.assertEqual(assessment.preferred_ticker, "AAA")
        self.assertTrue(any(row[0] == "Forward P/E" and row[3] == "AAA" for row in assessment.metrics))

    def test_fund_expense_ratio_is_compared_when_available_for_both(self):
        finding = SpecialistFinding(Rating.HOLD, "Balanced.", ())
        assessment = build_comparison_assessment(
            SecurityIdentity("Fund A", "FUNA", "NYSE Arca", "USD"),
            100,
            {"annualReportExpenseRatio": 0.0009},
            _snapshot(100, 0.08, 0),
            finding,
            SecurityIdentity("Fund B", "FUNB", "NYSE Arca", "USD"),
            100,
            {"annualReportExpenseRatio": 0.0020},
            _snapshot(100, 0.08, 0),
            finding,
        )
        self.assertTrue(any(row[0] == "Fund expense ratio" and row[3] == "FUNA" for row in assessment.metrics))

    def test_equal_available_evidence_returns_no_clear_edge(self):
        finding = SpecialistFinding(Rating.HOLD, "Balanced.", ())
        snapshot = _snapshot(100, 0.08, 0)
        assessment = build_comparison_assessment(
            SecurityIdentity("Alpha", "AAA", "NYSE", "USD"),
            100,
            {"forwardPE": 20},
            snapshot,
            finding,
            SecurityIdentity("Beta", "BBB", "NYSE", "USD"),
            100,
            {"forwardPE": 20},
            snapshot,
            finding,
        )
        self.assertEqual(assessment.preferred_ticker, "No clear edge")

    def test_sector_benchmark_returns_are_explained_in_scorecard(self):
        finding = SpecialistFinding(Rating.HOLD, "Balanced.", ())
        assessment = build_comparison_assessment(
            SecurityIdentity("Alpha", "AAA", "NYSE", "USD"),
            100,
            {"sector": "Technology", "industry": "Semiconductors", "marketCap": 10_000_000_000},
            _snapshot(100, 0.12, 0),
            finding,
            SecurityIdentity("Beta", "BBB", "NYSE", "USD"),
            100,
            {"sector": "Technology", "industry": "Semiconductors", "marketCap": 8_000_000_000},
            _snapshot(100, 0.08, 0),
            finding,
            "SOXX",
            "iShares Semiconductor ETF",
            0.10,
            0.25,
            0.14,
        )
        self.assertEqual(assessment.benchmark_ticker, "SOXX")
        self.assertTrue(any(row[0] == "Chart-period total return" for row in assessment.metrics))
        self.assertTrue(any(row[0] == "Excess return vs. SOXX" for row in assessment.metrics))


if __name__ == "__main__":
    unittest.main()
