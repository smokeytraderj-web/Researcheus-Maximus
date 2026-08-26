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

    def test_overview_chart_must_use_a_supported_chart_type(self):
        ResearchRequest("AXON", Horizon.ALL, overview_chart="fibonacci").validate()
        with self.assertRaisesRegex(ValueError, "overview chart"):
            ResearchRequest("AXON", Horizon.ALL, overview_chart="candlestick_cloud").validate()

    def test_security_comparison_requires_second_security(self):
        with self.assertRaisesRegex(ValueError, "two securities"):
            ResearchRequest("AVGO", Horizon.ALL, comparison_analysis=True).validate()

    def test_portfolio_allocation_must_total_one_hundred(self):
        ResearchRequest("BDMIX", Horizon.ALL, portfolio_allocation=(70, 30)).validate()
        with self.assertRaisesRegex(ValueError, "totaling 100"):
            ResearchRequest("BDMIX", Horizon.ALL, portfolio_allocation=(60, 30)).validate()

    def test_custom_range_requires_valid_order_and_minimum_length(self):
        with self.assertRaisesRegex(ValueError, "before"):
            ResearchRequest(
                "TSLA",
                Horizon.ALL,
                custom_start="2025-12-31",
                custom_end="2025-01-01",
            ).validate()
        with self.assertRaisesRegex(ValueError, "90-day"):
            ResearchRequest(
                "TSLA",
                Horizon.ALL,
                custom_start="2025-01-01",
                custom_end="2025-02-01",
            ).validate()


if __name__ == "__main__":
    unittest.main()
