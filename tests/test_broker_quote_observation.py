"""No-network exact-symbol broker observation contract regressions."""

import unittest

from domain.broker_quote_observation import observe_tastytrade_quote


FETCH = "2026-09-21T14:00:00Z"
SHARE = {
    "symbol": "META", "instrument-type": "Equity", "bid": "556.09",
    "ask": "556.23", "bid-size": "320.0", "ask-size": "40.0",
    "updated-at": "2026-09-21T13:58:51.032Z", "is-trading-halted": False,
}
OPTION = {
    "symbol": "O:QBTS261120C00018000", "instrument-type": "Equity Option",
    "bid": "2.10", "ask": "2.25", "bid-size": "14",
    "ask-size": "12", "updated-at": "2026-09-21T13:59:00Z",
    "is-trading-halted": False,
}


class BrokerQuoteObservationTests(unittest.TestCase):
    def test_recorded_equity_shape_exact_symbol_and_provenance(self):
        other = dict(SHARE, symbol="AAPL", bid="999")
        obs = observe_tastytrade_quote({"items": [other, SHARE]},
            requested_symbol="meta", instrument_type="Equity", fetched_at_utc=FETCH)
        self.assertEqual(obs.requested_symbol, "META")
        self.assertEqual(obs.bid, "556.09")
        self.assertEqual(obs.ask, "556.23")
        self.assertEqual(obs.provider_updated_at_utc, "2026-09-21T13:58:51.032000Z")
        self.assertEqual(obs.fetched_at_utc, FETCH)
        self.assertEqual(obs.quote_state, "TWO_SIDED_OBSERVED")
        self.assertTrue(obs.supports_execution_review)
        self.assertEqual(obs.authority, "ADVISORY_ONLY")
        self.assertEqual(len(obs.observation_hash), 64)

    def test_exact_occ_requires_independent_multiplier_match(self):
        args = dict(requested_symbol="QBTS 261120C00018000",
                    instrument_type="Equity Option", fetched_at_utc=FETCH)
        unverified = observe_tastytrade_quote([OPTION], **args)
        self.assertEqual(unverified.requested_symbol, "QBTS261120C00018000")
        self.assertEqual(unverified.multiplier_state, "UNVERIFIED")
        self.assertFalse(unverified.supports_execution_review)
        mismatch = observe_tastytrade_quote([OPTION], **args,
            selected_contract_multiplier=100, broker_contract_multiplier=10)
        self.assertEqual(mismatch.multiplier_state, "MISMATCH")
        self.assertFalse(mismatch.supports_execution_review)
        matched = observe_tastytrade_quote([OPTION], **args,
            selected_contract_multiplier=100, broker_contract_multiplier=100)
        self.assertEqual(matched.multiplier_state, "VERIFIED")
        self.assertTrue(matched.supports_execution_review)

    def test_adjusted_root_is_not_rewritten(self):
        adjusted = dict(OPTION, symbol="QBTS1261120C00018000")
        obs = observe_tastytrade_quote([adjusted],
            requested_symbol="QBTS261120C00018000",
            instrument_type="Equity Option", fetched_at_utc=FETCH,
            selected_contract_multiplier=100, broker_contract_multiplier=100)
        self.assertEqual(obs.identity_state, "NOT_RETURNED")
        self.assertFalse(obs.supports_execution_review)

    def test_missing_symbol_is_not_substituted(self):
        obs = observe_tastytrade_quote({"items": [SHARE]},
            requested_symbol="MSFT", instrument_type="Equity", fetched_at_utc=FETCH)
        self.assertEqual(obs.identity_state, "NOT_RETURNED")
        self.assertIsNone(obs.bid)
        self.assertFalse(obs.supports_execution_review)

    def test_duplicate_exact_symbol_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "ambiguous duplicate"):
            observe_tastytrade_quote([SHARE, dict(SHARE)],
                requested_symbol="META", instrument_type="Equity", fetched_at_utc=FETCH)

    def test_timestamp_absent_or_after_fetch_does_not_support_review(self):
        for quote, state in (({k: v for k, v in SHARE.items() if k != "updated-at"},
                              "PROVIDER_TIME_MISSING"),
                             (dict(SHARE, **{"updated-at": "2026-09-21T14:01:00Z"}),
                              "AFTER_FETCH")):
            with self.subTest(state=state):
                obs = observe_tastytrade_quote([quote], requested_symbol="META",
                    instrument_type="Equity", fetched_at_utc=FETCH)
                self.assertEqual(obs.time_state, state)
                self.assertFalse(obs.supports_execution_review)

    def test_quote_quality_states_do_not_invalidate_thesis(self):
        for changes, state in (({"bid": None}, "ONE_SIDED"),
                               ({"bid": "600"}, "CROSSED"),
                               ({"ask-size": "0"}, "NO_DISPLAYED_SIZE"),
                               ({"is-trading-halted": True}, "HALTED"),
                               ({"ask": "NaN"}, "INVALID_QUOTE_DATA")):
            with self.subTest(state=state):
                obs = observe_tastytrade_quote([dict(SHARE, **changes)],
                    requested_symbol="META", instrument_type="Equity", fetched_at_utc=FETCH)
                self.assertEqual(obs.quote_state, state)
                self.assertFalse(obs.supports_execution_review)
                self.assertEqual(obs.authority, "ADVISORY_ONLY")

    def test_missing_sizes_are_not_zero_filled(self):
        obs = observe_tastytrade_quote([{"symbol": "META", "instrument-type": "Equity",
            "bid": "556", "ask": "557", "updated-at": FETCH}],
            requested_symbol="META", instrument_type="Equity", fetched_at_utc=FETCH)
        self.assertIsNone(obs.bid_size)
        self.assertEqual(obs.quote_state, "SIZE_MISSING")
        self.assertFalse(obs.supports_execution_review)


if __name__ == "__main__":
    unittest.main()
