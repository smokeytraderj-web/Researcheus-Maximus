import unittest

from core.research_prompt import (
    append_revision_instructions,
    parse_comparison_prompt,
    parse_deep_analysis_prompt,
    parse_research_prompt,
)


class ResearchPromptTests(unittest.TestCase):
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

    def test_company_is_extracted_from_conversational_prompt(self):
        query, _ = parse_research_prompt("Should I buy Walmart?")
        self.assertEqual(query, "Walmart")

    def test_revision_instructions_preserve_original_brief(self):
        revised = append_revision_instructions("Research WMT", "Make the entry strategy conservative.")
        self.assertIn("Research WMT", revised)
        self.assertIn("Requested modifications to the revised report", revised)
        self.assertIn("entry strategy conservative", revised)

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
        self.assertEqual(charts, ("price_trend", "momentum", "relative_performance"))

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


if __name__ == "__main__":
    unittest.main()
