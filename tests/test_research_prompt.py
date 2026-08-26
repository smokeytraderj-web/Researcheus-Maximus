import unittest

from core.research_prompt import append_revision_instructions, parse_research_prompt


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


if __name__ == "__main__":
    unittest.main()
