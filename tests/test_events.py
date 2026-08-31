import datetime as dt
import unittest

from research.events import build_event_context, event_metrics, event_signals


def _payload(**overrides):
    payload = {
        "beat_stats": {
            "quarters": 8,
            "eps_beats": 8,
            "eps_beat_rate_pct": 100.0,
            "avg_eps_surprise_pct": 4.46,
        },
        "last_report": {
            "earnings_release_date": "2026-07-30",
            "eps_surprise_pct": 6.77,
            "revenue_surprise_pct": 0.35,
            "price_reaction": {"gap_open_pct": -8.58, "reaction_day_change_pct": -7.35},
        },
        "next_report_date": int(
            dt.datetime.combine(dt.date.today() + dt.timedelta(days=10), dt.time(12), dt.timezone.utc).timestamp()
        ),
    }
    payload.update(overrides)
    return payload


class EventContextTests(unittest.TestCase):
    def test_unix_next_report_date_becomes_a_date_and_countdown(self):
        context = build_event_context("NASDAQ:AAPL", _payload())
        self.assertEqual(context.next_report_date, (dt.date.today() + dt.timedelta(days=10)).isoformat())
        self.assertEqual(context.days_to_report, 10)

    def test_missing_payload_is_reported_as_unavailable_not_zeroed(self):
        context = build_event_context("NASDAQ:AAPL", {})
        self.assertFalse(context.available)
        self.assertEqual(context.next_report_date, "")
        self.assertIsNone(context.eps_beat_rate_pct)
        self.assertIsNone(context.last_reaction)

    def test_positioning_is_read_from_issuer_metadata_when_present(self):
        context = build_event_context(
            "NASDAQ:AAPL",
            _payload(),
            {"shortPercentOfFloat": 0.12, "heldPercentInstitutions": 0.62, "heldPercentInsiders": 0.0007},
        )
        self.assertAlmostEqual(context.short_percent_of_float, 0.12)
        self.assertAlmostEqual(context.institutional_holding, 0.62)

    def test_metrics_omit_fields_the_sources_did_not_supply(self):
        labels = [label for label, _value in event_metrics(build_event_context("X", _payload()))]
        self.assertIn("Next earnings report", labels)
        self.assertIn("EPS beat rate", labels)
        # No issuer metadata was passed, so no positioning rows may appear.
        self.assertNotIn("Short interest (% of float)", labels)
        self.assertNotIn("Institutional holding", labels)


class EventSignalTests(unittest.TestCase):
    def test_imminent_earnings_raise_event_risk(self):
        signals = event_signals(build_event_context("X", _payload()))
        self.assertTrue(any("event risk" in signal for signal in signals))

    def test_beat_that_sold_off_is_called_out_explicitly(self):
        signals = event_signals(build_event_context("X", _payload()))
        self.assertTrue(any("beats alone have not been enough" in signal for signal in signals))

    def test_miss_that_rallied_is_read_as_reset_expectations(self):
        payload = _payload(
            last_report={
                "earnings_release_date": "2026-07-30",
                "eps_surprise_pct": -4.0,
                "price_reaction": {"gap_open_pct": 1.2, "reaction_day_change_pct": 3.5},
            }
        )
        signals = event_signals(build_event_context("X", payload))
        self.assertTrue(any("reset lower" in signal for signal in signals))

    def test_habitual_beats_are_framed_as_the_base_case(self):
        signals = event_signals(build_event_context("X", _payload()))
        self.assertTrue(any("base case rather than a catalyst" in signal for signal in signals))

    def test_heavy_short_interest_is_flagged_as_a_rally_risk(self):
        signals = event_signals(build_event_context("X", _payload(), {"shortPercentOfFloat": 0.18}))
        self.assertTrue(any("covering" in signal for signal in signals))

    def test_light_short_interest_raises_no_squeeze_signal(self):
        signals = event_signals(build_event_context("X", _payload(), {"shortPercentOfFloat": 0.01}))
        self.assertFalse(any("covering" in signal for signal in signals))

    def test_distant_earnings_do_not_raise_event_risk(self):
        far = int(
            dt.datetime.combine(dt.date.today() + dt.timedelta(days=90), dt.time(12), dt.timezone.utc).timestamp()
        )
        signals = event_signals(build_event_context("X", _payload(next_report_date=far)))
        self.assertFalse(any("event risk" in signal for signal in signals))


if __name__ == "__main__":
    unittest.main()
