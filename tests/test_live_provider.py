import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from core.models import Horizon, Rating, ResearchRequest
from research.live_provider import (
    LiveResearchProvider,
    _combine_ratings,
    _build_portfolio_fit,
    _comparison_benchmark,
    _direct_chart_history,
    _direct_decision_answer,
    _enrich_fund_info,
    _external_user_context,
    _request_specific_response,
    _nasdaq_history,
    _portfolio_context_answer,
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
        self.assertFalse(_usable_ycharts_metric("YCharts price target upside", 0))
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

    def test_main_all_horizons_rating_is_technically_led(self):
        lead, technical_weight, fundamental_weight = _combine_ratings(
            Rating.BUY,
            Rating.REDUCE,
            Horizon.ALL,
        )
        self.assertEqual((technical_weight, fundamental_weight), (70, 30))
        self.assertEqual(lead, Rating.ADD)

    def test_buy_question_gets_a_direct_conditional_answer(self):
        answer = _direct_decision_answer(
            ResearchRequest("TSLA", Horizon.ALL, decision_intent="buy"),
            "Tesla",
            Rating.HOLD,
            Rating.REDUCE,
        )
        self.assertTrue(answer.startswith("Direct answer:"))
        self.assertIn("not a clear buy", answer)

    def test_portfolio_concentration_question_gets_a_personalized_answer(self):
        request = ResearchRequest(
            "TSLA",
            Horizon.ALL,
            question="TSLA, I have a portfolio that is 90% equities and 20 percent of that is tech. Is it a good decision to buy?",
            decision_intent="portfolio_context",
        )
        answer = _portfolio_context_answer(
            request,
            "Tesla",
            {"sector": "Consumer Cyclical"},
            Rating.HOLD,
            Rating.REDUCE,
        )
        self.assertIn("would not add Tesla now", answer)
        self.assertIn("about 18% of the total portfolio", answer)
        self.assertIn("Consumer Cyclical", answer)

    def test_external_synthesis_context_excludes_private_position_fields(self):
        context = _external_user_context(
            ResearchRequest(
                "ACYN",
                Horizon.ALL,
                purchase_price=19.25,
                quantity=500,
                risk_tolerance="conservative",
                question="Give me a report on ACYN and tell me a little about the fund in a summary to start.",
            )
        )
        self.assertIn("question", context)
        self.assertNotIn("purchase_price", context)
        self.assertNotIn("quantity", context)
        self.assertNotIn("risk_tolerance", context)

    def test_fund_summary_request_is_answered_before_generic_analysis(self):
        request = ResearchRequest(
            "ACYN",
            Horizon.ALL,
            question="Give me a report on ACYN and tell me a little about the fund in a summary to start the report.",
        )
        response = _request_specific_response(
            request,
            "FT Vest Laddered Autocallable Barrier & Income ETF",
            "ACYN",
            {
                "quoteType": "ETF",
                "category": "Derivative Income",
                "fundFamily": "First Trust",
                "longBusinessSummary": "The fund uses a laddered portfolio of structured outcome strategies. It seeks income with defined barrier exposure.",
                "annualReportExpenseRatio": 0.0095,
            },
            Rating.HOLD,
            Rating.BUY,
            "Generic fundamental screen.",
        )
        self.assertIn("exchange-traded fund", response)
        self.assertIn("First Trust", response)
        self.assertIn("Derivative Income", response)
        self.assertIn("structured outcome strategies", response)
        self.assertIn("0.95%", response)

    def test_deterministic_fallback_does_not_replace_a_specific_question_with_boilerplate(self):
        request = ResearchRequest(
            "TSLA",
            Horizon.ALL,
            question="How exposed is TSLA to changes in regulatory-credit revenue?",
        )
        response = _request_specific_response(
            request,
            "Tesla",
            "TSLA",
            {"quoteType": "EQUITY"},
            Rating.HOLD,
            Rating.REDUCE,
            "The fundamental screen combines growth, valuation, leverage, and available analyst-consensus evidence.",
        )
        self.assertIn("could not fully answer the specific question", response)
        self.assertIn("regulatory-credit revenue", response)
        self.assertNotIn("fundamental screen combines", response)

    def test_opportunity_question_gets_a_direct_answer_without_ai_synthesis(self):
        request = ResearchRequest(
            "AXON",
            Horizon.ALL,
            question="Is AXON a good opportunity?",
            decision_intent="buy",
        )
        response = _request_specific_response(
            request,
            "Axon Enterprise",
            "AXON",
            {"quoteType": "EQUITY"},
            Rating.ADD,
            Rating.HOLD,
            "The fundamental screen combines growth, valuation, leverage, and available analyst-consensus evidence.",
        )
        self.assertTrue(response.startswith("Direct answer:"))
        self.assertIn("conditional add candidate", response.lower())
        self.assertNotIn("could not fully answer", response)

    def test_portfolio_fit_identifies_fixed_income_sleeve(self):
        request = ResearchRequest(
            "BDMIX",
            Horizon.ALL,
            decision_intent="portfolio_fit",
            portfolio_allocation=(70, 30),
        )
        fit = _build_portfolio_fit(
            request,
            {"category": "Intermediate Core-Plus Bond", "bondPosition": 0.92, "annualReportExpenseRatio": 0.0065},
            "Example Bond Fund",
        )
        self.assertIsNotNone(fit)
        self.assertEqual(fit.security_role, "Fixed-income sleeve")
        self.assertIn("30%", fit.fit_label)
        answer = _direct_decision_answer(request, "Example Bond Fund", Rating.HOLD, Rating.HOLD, fit)
        self.assertTrue(answer.startswith("Portfolio-fit answer:"))

    def test_fund_specific_data_populates_missing_profile_fields(self):
        operations = pd.DataFrame(
            {"BDMIX": [0.0134, 0.82, 2_500_000_000]},
            index=["Annual Report Expense Ratio", "Annual Holdings Turnover", "Total Net Assets"],
        )
        bond_holdings = pd.DataFrame(
            {"BDMIX": [3.2, 5.4, "A"]},
            index=["Duration", "Maturity", "Credit Quality"],
        )
        funds = SimpleNamespace(
            fund_overview={"categoryName": "Equity Market Neutral", "family": "BlackRock", "legalType": "Open Ended Investment Company"},
            description="A long-short equity market neutral strategy.",
            asset_classes={"stockPosition": 0.88, "bondPosition": 0.02, "cashPosition": 0.10},
            fund_operations=operations,
            bond_holdings=bond_holdings,
            quote_type=lambda: "MUTUALFUND",
        )
        enriched = _enrich_fund_info(SimpleNamespace(funds_data=funds), "BDMIX", {"longName": "BlackRock Global Equity Mkt Neutral Instl"})
        self.assertEqual(enriched["category"], "Equity Market Neutral")
        self.assertEqual(enriched["fundFamily"], "BlackRock")
        self.assertEqual(enriched["stockPosition"], 0.88)
        self.assertEqual(enriched["annualReportExpenseRatio"], 0.0134)
        self.assertEqual(enriched["fundDuration"], 3.2)

    def test_market_neutral_fund_is_not_forced_into_equity_or_bond_sleeve(self):
        request = ResearchRequest("BDMIX", Horizon.ALL, portfolio_allocation=(70, 30))
        fit = _build_portfolio_fit(
            request,
            {"category": "Equity Market Neutral", "longName": "BlackRock Global Equity Mkt Neutral Instl"},
            "BlackRock Global Equity Mkt Neutral Instl",
        )
        self.assertEqual(fit.security_role, "Alternative / diversifier sleeve")
        self.assertIn("not a direct 70/30", fit.fit_label.lower())

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
