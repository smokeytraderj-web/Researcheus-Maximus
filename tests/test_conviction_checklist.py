import unittest

from core.conviction_checklist import POLICY_VERSION, evaluate_conviction_checklist


def _base(**overrides):
    values = dict(
        price=800.0, sma50=760.0, sma200=650.0,
        rsi14=58.0, macd=12.0, macd_signal=8.0,
        security_return_pct=0.22, benchmark_return_pct=0.09,
        return_on_equity=0.31,
        eps_estimate_now=9.20, eps_estimate_prior=8.60,
    )
    values.update(overrides)
    return evaluate_conviction_checklist(**values)


class ConvictionChecklistTests(unittest.TestCase):
    """Every criterion is a policy decision, not a guess -- these fixtures pin
    the exact thresholds so a later change to them is a deliberate diff, not drift."""

    def test_always_returns_exactly_five_criteria_in_order(self):
        checklist = _base()
        self.assertEqual(checklist.total_count, 5)
        self.assertEqual(
            [item.key for item in checklist.criteria],
            ["trend", "momentum", "relative_strength", "quality", "revisions"],
        )
        self.assertEqual(checklist.policy_version, POLICY_VERSION)

    def test_engineered_case_passes_all_five(self):
        checklist = _base()
        self.assertTrue(checklist.is_perfect)
        self.assertEqual(checklist.passed_count, 5)
        self.assertTrue(all(item.passed is True for item in checklist.criteria))

    def test_engineered_case_fails_all_five(self):
        checklist = _base(
            price=100.0, sma50=105.0, sma200=110.0,
            rsi14=32.0, macd=-1.0, macd_signal=0.5,
            security_return_pct=-0.05, benchmark_return_pct=0.08,
            return_on_equity=0.04,
            eps_estimate_now=3.10, eps_estimate_prior=3.60,
        )
        self.assertEqual(checklist.passed_count, 0)
        self.assertFalse(checklist.is_perfect)
        self.assertTrue(all(item.passed is False for item in checklist.criteria))

    def test_trend_requires_price_above_both_averages(self):
        self.assertTrue(_base(price=800, sma50=760, sma200=650).criteria[0].passed)
        self.assertFalse(_base(price=700, sma50=760, sma200=650).criteria[0].passed)  # below 50d
        self.assertFalse(_base(price=800, sma50=760, sma200=850).criteria[0].passed)  # below 200d

    def test_trend_is_unconfirmed_without_a_200_day_average(self):
        criterion = _base(sma200=None).criteria[0]
        self.assertIsNone(criterion.passed)
        self.assertEqual(criterion.status, "unconfirmed")

    def test_momentum_requires_macd_bullish_and_rsi_in_range(self):
        self.assertTrue(_base(macd=12, macd_signal=8, rsi14=58).criteria[1].passed)
        self.assertFalse(_base(macd=5, macd_signal=8, rsi14=58).criteria[1].passed)  # MACD bearish
        self.assertFalse(_base(macd=12, macd_signal=8, rsi14=30).criteria[1].passed)  # RSI too low
        self.assertFalse(_base(macd=12, macd_signal=8, rsi14=90).criteria[1].passed)  # RSI too high

    def test_momentum_range_boundaries_are_inclusive(self):
        self.assertTrue(_base(macd=1, macd_signal=0, rsi14=40.0).criteria[1].passed)
        self.assertTrue(_base(macd=1, macd_signal=0, rsi14=75.0).criteria[1].passed)
        self.assertFalse(_base(macd=1, macd_signal=0, rsi14=39.9).criteria[1].passed)
        self.assertFalse(_base(macd=1, macd_signal=0, rsi14=75.1).criteria[1].passed)

    def test_relative_strength_requires_beating_the_benchmark_by_the_margin(self):
        self.assertTrue(_base(security_return_pct=0.10, benchmark_return_pct=0.05).criteria[2].passed)
        self.assertFalse(_base(security_return_pct=0.05, benchmark_return_pct=0.05).criteria[2].passed)  # a tie is not a lead
        self.assertFalse(_base(security_return_pct=0.02, benchmark_return_pct=0.05).criteria[2].passed)

    def test_relative_strength_margin_boundary(self):
        # Exactly the margin confirms; a hair under does not.
        self.assertTrue(_base(security_return_pct=0.08, benchmark_return_pct=0.05).criteria[2].passed)
        self.assertFalse(_base(security_return_pct=0.0799, benchmark_return_pct=0.05).criteria[2].passed)

    def test_a_dead_heat_no_longer_confirms(self):
        # The case that prompted v2.2: +1.5% against the benchmark's +1.4% was
        # reported as "ahead of the S&P 500" on a tenth of a point.
        criterion = _base(security_return_pct=0.015, benchmark_return_pct=0.014).criteria[2]
        self.assertFalse(criterion.passed)

    def test_a_narrow_lead_is_not_described_as_lagging(self):
        # It misses the criterion while still being ahead, and the report must
        # not tell a reader it is behind.
        detail = _base(security_return_pct=0.015, benchmark_return_pct=0.014).criteria[2].detail
        self.assertIn("ahead by", detail)
        self.assertNotIn("behind by", detail)

    def test_relative_strength_unconfirmed_without_a_benchmark_series(self):
        criterion = _base(benchmark_return_pct=None).criteria[2]
        self.assertIsNone(criterion.passed)

    def test_quality_requires_roe_above_the_threshold(self):
        self.assertTrue(_base(return_on_equity=0.16).criteria[3].passed)
        self.assertFalse(_base(return_on_equity=0.15).criteria[3].passed)  # threshold is exclusive
        self.assertFalse(_base(return_on_equity=0.02).criteria[3].passed)
        self.assertFalse(_base(return_on_equity=-0.10).criteria[3].passed)

    def test_quality_unconfirmed_when_roe_is_missing(self):
        self.assertIsNone(_base(return_on_equity=None).criteria[3].passed)

    def test_revisions_require_estimates_to_have_risen(self):
        self.assertTrue(_base(eps_estimate_now=9.2, eps_estimate_prior=8.6).criteria[4].passed)
        self.assertFalse(_base(eps_estimate_now=8.0, eps_estimate_prior=8.6).criteria[4].passed)
        self.assertFalse(_base(eps_estimate_now=8.6, eps_estimate_prior=8.6).criteria[4].passed)  # flat is not a raise

    def test_revisions_unconfirmed_without_a_usable_prior_estimate(self):
        self.assertIsNone(_base(eps_estimate_prior=None).criteria[4].passed)
        self.assertIsNone(_base(eps_estimate_now=None).criteria[4].passed)

    def test_revisions_work_for_loss_making_issuers(self):
        # A next-year forecast moving from -$2.39 to -$2.00 is analysts marking
        # the business up, exactly as $9.20 from $8.60 is. Requiring a positive
        # base silently excluded every loss-maker from ever confirming this.
        narrowing = _base(eps_estimate_now=-2.00, eps_estimate_prior=-2.39).criteria[4]
        self.assertTrue(narrowing.passed)
        self.assertIn("narrowed", narrowing.detail)
        self.assertIn("-$2.00", narrowing.detail)
        widening = _base(eps_estimate_now=-5.17, eps_estimate_prior=-4.67).criteria[4]
        self.assertFalse(widening.passed)
        self.assertIn("widened", widening.detail)
        # No percentage is quoted off a negative base, where it would be nonsense.
        self.assertNotIn("%", narrowing.detail)

    def test_revisions_state_the_window_actually_compared(self):
        detail = _base(revision_window_days=30).criteria[4].detail
        self.assertIn("30 days ago", detail)

    def test_narrative_names_what_would_change_the_view(self):
        # "The dissent is what would need to change" is true of any dissent and
        # so tells the reader nothing. Name the thing to watch.
        from core.conviction_checklist import checklist_narrative
        text = checklist_narrative(_base(eps_estimate_now=8.0, eps_estimate_prior=8.6), rating="Buy")
        self.assertIn("watch for estimates turning back up", text)
        self.assertNotIn("what would need to change first", text)

    def test_narrative_reports_the_balance_and_both_sides(self):
        from core.conviction_checklist import checklist_narrative
        text = checklist_narrative(_base(eps_estimate_now=8.0, eps_estimate_prior=8.6), rating="Buy")
        self.assertIn("4 of the 5 checks confirm", text)
        self.assertIn("In favour:", text)
        self.assertIn("Against:", text)

    def test_narrative_for_a_fund_says_inapplicable_not_unavailable(self):
        from core.conviction_checklist import checklist_narrative
        text = checklist_narrative(_base(is_fund=True), rating="Hold")
        self.assertIn("do not apply to a fund", text)
        self.assertNotIn("could not be judged", text)

    def test_a_fund_reports_the_two_company_criteria_as_inapplicable(self):
        # A fund has no return on equity and no earnings consensus. Saying "not
        # available" would read as a retrieval failure that a retry might fix.
        checklist = _base(is_fund=True)
        for criterion in checklist.criteria[3:]:
            self.assertIsNone(criterion.passed)
            self.assertIn("Not applicable to a fund", criterion.detail)
        self.assertEqual(checklist.unconfirmed_count, 2)

    def test_street_conviction_is_gone_from_the_policy(self):
        # Removed in v2: it passed 90% of the time across 50 large caps, so it
        # could not separate them, and it correlated negatively with trend and
        # momentum -- rewarding stocks that had fallen, which is the opposite of
        # what "street conviction" reads as. See the policy docstring.
        self.assertNotIn("street_conviction", [item.key for item in _base().criteria])
        self.assertNotIn("growth", [item.key for item in _base().criteria])

    def test_unconfirmed_criteria_are_never_counted_as_passed(self):
        checklist = _base(sma200=None, return_on_equity=None, eps_estimate_prior=None)
        self.assertEqual(checklist.unconfirmed_count, 3)
        self.assertLessEqual(checklist.passed_count, 2)
        self.assertFalse(checklist.is_perfect)

    def test_real_axon_style_evidence_is_a_mixed_read_not_a_rubber_stamp(self):
        # Fixture pinned to a real observed AXON snapshot: strong trend and
        # relative strength, but momentum has cooled and returns on equity are
        # thin. The checklist must not wave this through as a clean 5/5.
        checklist = _base(
            price=566.56, sma50=560.14, sma200=506.29,
            rsi14=46.26, macd=13.02, macd_signal=19.75,
            security_return_pct=0.188, benchmark_return_pct=0.011,
            return_on_equity=0.118,
            eps_estimate_now=2.41, eps_estimate_prior=2.28,
        )
        self.assertEqual(checklist.passed_count, 3)
        self.assertFalse(checklist.criteria[1].passed)  # momentum
        self.assertFalse(checklist.criteria[3].passed)  # quality


class MethodologyDocumentTests(unittest.TestCase):
    """web/methodology.html states the policy to readers. If the policy moves and
    the document does not, the published reasoning becomes wrong -- which is worse
    than not publishing it."""

    @staticmethod
    def _document() -> str:
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "web" / "methodology.html").read_text(encoding="utf-8")

    def test_the_document_states_the_current_policy_version(self):
        self.assertIn(f"Policy version {POLICY_VERSION}", self._document())

    def test_the_document_names_the_five_current_criteria(self):
        text = self._document()
        for label in ("Trend", "Momentum", "Relative strength", "Quality", "Revisions"):
            with self.subTest(label=label):
                self.assertIn(f">{label}</td>", text)

    def test_the_document_does_not_present_removed_criteria_as_current(self):
        text = self._document()
        table = text[text.index("<tbody"):text.index("</tbody>")]
        self.assertNotIn("Street conviction", table)
        self.assertNotIn(">Growth</td>", table)


if __name__ == "__main__":
    unittest.main()
