import unittest

from core.models import Horizon, ResearchRequest


class ResearchRequestTests(unittest.TestCase):
    def test_ticker_or_company_is_required(self):
        with self.assertRaises(ValueError):
            ResearchRequest("", Horizon.SHORT).validate()

    def test_optional_position_values_must_be_positive(self):
        with self.assertRaises(ValueError):
            ResearchRequest("AXON", Horizon.MEDIUM, purchase_price=-1).validate()

    def test_deep_analysis_limits_comparison_count(self):
        with self.assertRaisesRegex(ValueError, "up to three"):
            ResearchRequest(
                "AXON",
                Horizon.ALL,
                deep_analysis=True,
                comparison_symbols=("SPY", "QQQ", "IWM", "DIA"),
            ).validate()

    def test_security_comparison_requires_second_security(self):
        with self.assertRaisesRegex(ValueError, "two securities"):
            ResearchRequest("AVGO", Horizon.ALL, comparison_analysis=True).validate()


if __name__ == "__main__":
    unittest.main()
