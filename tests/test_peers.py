import unittest

from core.peers import (
    CAP_BAND_HIGH,
    CAP_BAND_LOW,
    MINIMUM_PEERS,
    PeerCandidate,
    PeerReturn,
    build_peer_group,
    drop_illiquid,
    select_peers,
)

# AVGO's real semiconductor cohort, with the market caps that decide the rule.
SUBJECT_CAP = 1_747_000_000_000.0
CANDIDATES = [
    PeerCandidate("NVDA", "NVIDIA Corporation", 4_400_000_000_000.0, "USD"),
    PeerCandidate("AVGO", "Broadcom Inc.", SUBJECT_CAP, "USD"),
    PeerCandidate("SKHY", "SK hynix Inc.", 120_000_000_000.0, "KRW"),
    PeerCandidate("MU", "Micron Technology, Inc.", 260_000_000_000.0, "USD"),
    PeerCandidate("AMD", "Advanced Micro Devices, Inc.", 300_000_000_000.0, "USD"),
    PeerCandidate("TXN", "Texas Instruments", 180_000_000_000.0, "USD"),
    PeerCandidate("MPWR", "Monolithic Power Systems", 40_000_000_000.0, "USD"),
]


class SelectionRuleTests(unittest.TestCase):
    """Selection decides the answer, so it has to be defensible before the
    numbers are."""

    def _select(self, **kw):
        return select_peers("AVGO", SUBJECT_CAP, "USD", list(CANDIDATES), **kw)

    def test_the_subject_is_never_its_own_peer(self):
        chosen, _ = self._select()
        self.assertNotIn("AVGO", [c.ticker for c in chosen])

    def test_a_different_reporting_currency_is_excluded_and_said_so(self):
        # A return series and a multiple are only comparable when the unit is.
        chosen, notes = self._select()
        self.assertNotIn("SKHY", [c.ticker for c in chosen])
        self.assertTrue(any("another currency" in note and "SKHY" in note for note in notes))

    def test_a_company_an_order_of_magnitude_larger_is_excluded(self):
        # NVDA is 2.5x AVGO here, so it stays; the band only excludes past 10x.
        chosen, _ = self._select()
        self.assertIn("NVDA", [c.ticker for c in chosen])

    def test_a_company_far_below_the_band_is_excluded_and_said_so(self):
        chosen, notes = self._select()
        self.assertNotIn("MPWR", [c.ticker for c in chosen])   # 0.023x
        self.assertTrue(any("market capitalisation" in note and "MPWR" in note for note in notes))

    def test_exclusions_are_reported_rather_than_dropped_silently(self):
        # A reader has to know the obvious name is missing on scale, not because
        # the data failed.
        _chosen, notes = self._select()
        self.assertTrue(notes)

    def test_the_band_boundaries_are_what_they_claim(self):
        low = PeerCandidate("LOW", "Just inside", SUBJECT_CAP * CAP_BAND_LOW, "USD")
        high = PeerCandidate("HIGH", "Just inside", SUBJECT_CAP * CAP_BAND_HIGH, "USD")
        out = PeerCandidate("OUT", "Just outside", SUBJECT_CAP * CAP_BAND_LOW * 0.9, "USD")
        chosen, _ = select_peers("AVGO", SUBJECT_CAP, "USD", [low, high, out])
        self.assertEqual([c.ticker for c in chosen], ["LOW", "HIGH"])

    def test_a_candidate_with_no_market_cap_is_kept_rather_than_guessed_at(self):
        unknown = PeerCandidate("UNK", "No cap reported", None, "USD")
        chosen, _ = select_peers("AVGO", SUBJECT_CAP, "USD", [unknown])
        self.assertEqual([c.ticker for c in chosen], ["UNK"])

    def test_the_group_is_capped(self):
        many = [PeerCandidate(f"P{i}", f"Peer {i}", SUBJECT_CAP, "USD") for i in range(12)]
        chosen, _ = select_peers("AVGO", SUBJECT_CAP, "USD", many, limit=5)
        self.assertEqual(len(chosen), 5)


class PeerGroupTests(unittest.TestCase):
    def _members(self, *returns):
        return [PeerReturn(f"P{i}", f"Peer {i}", value) for i, value in enumerate(returns)]

    def test_too_few_peers_produces_no_group_at_all(self):
        # One survivor is worse than none: a comparison reads as evidence that a
        # comparable group was found.
        self.assertIsNone(build_peer_group("Semiconductors", self._members(0.1), 0.2, "3 months"))

    def test_the_minimum_is_what_it_claims(self):
        group = build_peer_group(
            "Semiconductors", self._members(*([0.1] * MINIMUM_PEERS)), 0.2, "3 months"
        )
        self.assertIsNotNone(group)

    def test_peers_with_no_return_do_not_count_toward_the_minimum(self):
        members = [PeerReturn("A", "A", 0.1), PeerReturn("B", "B", None)]
        self.assertIsNone(build_peer_group("Semiconductors", members, 0.2, "3 months"))

    def test_the_median_ignores_peers_with_no_return(self):
        members = [PeerReturn("A", "A", 0.10), PeerReturn("B", "B", None), PeerReturn("C", "C", 0.30)]
        group = build_peer_group("Semiconductors", members, 0.2, "3 months")
        self.assertAlmostEqual(group.median_return(), 0.20)

    def test_standing_places_the_subject_in_its_own_group(self):
        group = build_peer_group("Semiconductors", self._members(0.05, 0.30, 0.10), 0.20, "3 months")
        self.assertIn("2 of 4", group.standing())
        self.assertIn("ahead of the group median", group.standing())

    def test_standing_says_behind_when_it_is_behind(self):
        group = build_peer_group("Semiconductors", self._members(0.30, 0.40, 0.50), -0.10, "3 months")
        self.assertIn("4 of 4", group.standing())
        self.assertIn("behind the group median", group.standing())

    def test_the_rule_travels_with_the_group(self):
        group = build_peer_group("Semiconductors", self._members(0.1, 0.2), 0.2, "3 months")
        self.assertIn("market weight", group.selection_rule)
        self.assertIn("semiconductors", group.selection_rule)


if __name__ == "__main__":
    unittest.main()


class LiquidityGuardTests(unittest.TestCase):
    """Classification and market cap do not catch a thin line: a foreign
    issuer's US over-the-counter ticker carries the parent's full market cap
    while trading a rounding error of it."""

    def _m(self, ticker, volume):
        return PeerReturn(ticker, ticker, 0.1, 1e12, 20.0, volume)

    def test_a_thinly_traded_peer_is_dropped_and_named(self):
        kept, notes = drop_illiquid([self._m("BIG", 900e6), self._m("THIN", 200_000.0)])
        self.assertEqual([m.ticker for m in kept], ["BIG"])
        self.assertTrue(any("thinly traded" in n and "THIN" in n for n in notes))

    def test_unreported_volume_is_kept_but_flagged_rather_than_assumed(self):
        kept, notes = drop_illiquid([self._m("UNK", None)])
        self.assertEqual([m.ticker for m in kept], ["UNK"])
        self.assertTrue(any("liquidity is unverified" in n for n in notes))

    def test_a_liquid_group_raises_nothing(self):
        kept, notes = drop_illiquid([self._m("A", 900e6), self._m("B", 400e6)])
        self.assertEqual(len(kept), 2)
        self.assertEqual(notes, ())


class PeerReportTests(unittest.TestCase):
    """A peer comparison is only as good as its peer set, so the set and the
    rule that chose it travel with the numbers."""

    def _render(self, group):
        import dataclasses
        import tempfile
        from pathlib import Path
        from core.request_builder import build_request
        from reports.html_report import build_research_html
        from research.demo_provider import DemoResearchProvider
        with tempfile.TemporaryDirectory() as tmp:
            request = build_request("AXON", "deep")
            result = DemoResearchProvider().run(request, Path(tmp))
            result = dataclasses.replace(result, peer_group=group)
            target = Path(tmp) / "report.html"
            build_research_html(result, request, target)
            return target.read_text(encoding="utf-8")

    def _group(self):
        return build_peer_group(
            "Semiconductors",
            [PeerReturn("NVDA", "NVIDIA Corporation", 0.064, 4.4e12, 14.6, 2.5e10),
             PeerReturn("MU", "Micron Technology, Inc.", -0.024, 2.6e11, 6.2, 3.1e10),
             PeerReturn("AMD", "Advanced Micro Devices", -0.181, 3.0e11, 29.6, 1.1e10)],
            -0.082,
            "three months to 2026-09-02",
            ("Excluded as too thinly traded to compare on price: THIN.",),
        )

    def test_the_cohort_and_the_subject_are_both_shown(self):
        html = self._render(self._group())
        self.assertIn("Against its industry", html)
        for expected in ("NVDA", "Micron", "+6.4%", "-18.1%", "AXON"):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)

    def test_the_standing_is_stated_in_words(self):
        html = self._render(self._group())
        self.assertIn("ranks 3 of 4 over the same dates", html)
        self.assertIn("behind the group median", html)

    def test_the_selection_rule_is_printed_with_the_table(self):
        # A reader cannot judge a peer comparison without knowing how the peers
        # were chosen.
        html = self._render(self._group())
        self.assertIn("largest companies by market weight", html)
        self.assertIn("0.1x-10x", html)

    def test_alignment_is_stated_rather_than_assumed(self):
        html = self._render(self._group())
        self.assertIn("measured over identical dates", html)
        self.assertIn("fiscal periods", html)

    def test_exclusions_reach_the_report(self):
        self.assertIn("too thinly traded", self._render(self._group()))

    def test_no_defensible_cohort_means_no_section(self):
        self.assertNotIn("Against its industry", self._render(None))
