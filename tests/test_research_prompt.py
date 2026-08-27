import unittest
import datetime as dt

from core.research_prompt import (
    append_revision_instructions,
    classify_research_intent,
    is_historical_trade_request,
    parse_comparison_prompt,
    parse_custom_range,
    parse_deep_analysis_prompt,
    parse_overview_chart_request,
    parse_portfolio_allocation,
    parse_portfolio_exposure,
    parse_research_prompt,
)


class ResearchPromptTests(unittest.TestCase):
    def test_deep_prompt_preserves_sector_benchmark_request(self):
        query, brief, comparisons, charts = parse_deep_analysis_prompt(
            "Compare the stock AXON to SPY and its respective sector and benchmarks"
        )
        self.assertEqual(query, "AXON")
        self.assertIn("sector and benchmarks", brief)
        self.assertEqual(comparisons, ("SPY",))
        self.assertIn("relative_performance", charts)

    def test_multiline_prompt_uses_first_line_as_security(self):
        query, brief = parse_research_prompt("WMT\nIs this an attractive entry after the pullback?")
        self.assertEqual(query, "WMT")
        self.assertIn("attractive entry", brief)

    def test_delimited_company_prompt_preserves_full_brief(self):
        prompt = "Walmart — Emphasize downside risk and valuation"
        query, brief = parse_research_prompt(prompt)
        self.assertEqual(query, "Walmart")
        self.assertEqual(brief, prompt)

    def test_ticker_is_extracted_from_conversational_prompt(self):
        query, _ = parse_research_prompt("Should I add AXON after earnings?")
        self.assertEqual(query, "AXON")

    def test_fund_summary_request_preserves_the_complete_instruction(self):
        prompt = "Give me a report on ACYN and tell me a little about the fund in a summary to start the report."
        query, brief = parse_research_prompt(prompt)
        self.assertEqual(query, "ACYN")
        self.assertEqual(brief, prompt)

    def test_company_is_extracted_from_conversational_prompt(self):
        query, _ = parse_research_prompt("Should I buy Walmart?")
        self.assertEqual(query, "Walmart")

    def test_revision_instructions_preserve_original_brief(self):
        revised = append_revision_instructions("Research WMT", "Make the entry strategy conservative.")
        self.assertIn("Research WMT", revised)
        self.assertIn("Requested modifications to the revised report", revised)
        self.assertIn("entry strategy conservative", revised)

    def test_lead_chart_request_is_explicit_or_defaults_to_annotated_price(self):
        self.assertEqual(parse_overview_chart_request("AXON - show a Fibonacci chart"), "fibonacci")
        self.assertEqual(parse_overview_chart_request("AXON - show a stop-loss chart"), "stop_loss")
        self.assertEqual(parse_overview_chart_request("AXON - show an RSI chart"), "momentum")
        self.assertEqual(parse_overview_chart_request("AXON - show a price chart"), "price_trend")
        self.assertEqual(parse_overview_chart_request("AXON - show a total return chart"), "relative_performance")
        self.assertEqual(parse_overview_chart_request("Give me a report on AXON"), "")

    def test_deep_prompt_extracts_comparisons_and_requested_risk_chart(self):
        query, brief, comparisons, charts = parse_deep_analysis_prompt(
            "AVGO - Compare against NVDA, SOXX, and SPY. Show RSI, MACD, drawdown, and volatility."
        )
        self.assertEqual(query, "AVGO")
        self.assertEqual(comparisons, ("NVDA", "SOXX", "SPY"))
        self.assertIn("relative_performance", charts)
        self.assertIn("risk", charts)
        self.assertIn("drawdown", brief)

    def test_deep_prompt_ignores_indicator_names_and_defaults_to_spy(self):
        query, _brief, comparisons, charts = parse_deep_analysis_prompt("AXON - Analyze RSI, MACD, ATR, and SMA trends.")
        self.assertEqual(query, "AXON")
        self.assertEqual(comparisons, ("SPY",))
        self.assertEqual(charts, ("price_trend", "stop_loss", "momentum", "relative_performance"))

    def test_revision_can_add_comparisons_and_chart_types(self):
        revised = append_revision_instructions(
            "AVGO - Compare against SPY.",
            "Add NVDA and include drawdown and volatility charts.",
        )
        _query, _brief, comparisons, charts = parse_deep_analysis_prompt(revised)
        self.assertEqual(comparisons, ("SPY", "NVDA"))
        self.assertIn("risk", charts)

    def test_comparison_prompt_extracts_two_tickers_and_preserves_question(self):
        prompt = "AVGO vs NVDA - Which currently offers better value?"
        primary, secondary, brief = parse_comparison_prompt(prompt)
        self.assertEqual((primary, secondary), ("AVGO", "NVDA"))
        self.assertEqual(brief, prompt)

    def test_comparison_prompt_accepts_company_names(self):
        primary, secondary, _brief = parse_comparison_prompt("Apple versus Microsoft")
        self.assertEqual((primary, secondary), ("Apple", "Microsoft"))

    def test_full_analysis_question_resolves_ticker_and_buy_intent(self):
        prompt = "Full analysis of TSLA — is it a good opportunity to buy?"
        query, brief = parse_research_prompt(prompt)
        self.assertEqual(query, "TSLA")
        self.assertEqual(classify_research_intent(brief), "buy")

    def test_open_ended_position_and_sell_questions_are_classified(self):
        query, brief = parse_research_prompt("Should I sell my TSLA position?")
        self.assertEqual(query, "TSLA")
        self.assertEqual(classify_research_intent(brief), "sell")
        self.assertEqual(classify_research_intent("What about my Apple position?"), "position")

    def test_custom_range_accepts_iso_dates_months_and_since(self):
        today = dt.date(2026, 8, 26)
        self.assertEqual(
            parse_custom_range("Analyze TSLA from 2024-01-01 to 2025-12-31", today=today),
            ("2024-01-01", "2025-12-31"),
        )
        self.assertEqual(
            parse_custom_range("Analyze TSLA from January 2024 to June 2025", today=today),
            ("2024-01-01", "2025-06-30"),
        )
        self.assertEqual(
            parse_custom_range("Analyze TSLA since March 2024", today=today),
            ("2024-03-01", "2026-08-26"),
        )
        self.assertEqual(
            parse_custom_range("Show QQQ trade examples from the past year", today=today),
            ("2025-08-26", "2026-08-26"),
        )

    def test_portfolio_fit_and_historical_trade_prompts_are_classified(self):
        prompt = "Is BDMIX good for a 70/30 portfolio?"
        query, brief = parse_research_prompt(prompt)
        self.assertEqual(query, "BDMIX")
        self.assertEqual(parse_portfolio_allocation(brief), (70, 30))
        self.assertEqual(classify_research_intent(brief), "portfolio_fit")

        trade_prompt = "Show QQQ trades with stop loss indicators and real chart snapshots from the past year"
        query, brief = parse_research_prompt(trade_prompt)
        self.assertEqual(query, "QQQ")
        self.assertTrue(is_historical_trade_request(brief))
        self.assertEqual(classify_research_intent(brief), "historical_trade_examples")
        _query, _brief, _comparisons, charts = parse_deep_analysis_prompt(trade_prompt)
        self.assertIn("historical_trades", charts)

    def test_conversational_portfolio_concentration_is_preserved(self):
        brief = "TSLA, I have a portfolio that is 90% equities and 20 percent of that is tech. Is it a good decision to buy?"
        self.assertEqual(classify_research_intent(brief), "portfolio_context")
        self.assertEqual(parse_portfolio_exposure(brief), (90.0, 20.0, "tech", True))

    def test_comparison_prompt_stops_before_custom_range(self):
        primary, secondary, _brief = parse_comparison_prompt(
            "AVGO vs NVDA from January 2024 to June 2025"
        )
        self.assertEqual((primary, secondary), ("AVGO", "NVDA"))


if __name__ == "__main__":
    unittest.main()
