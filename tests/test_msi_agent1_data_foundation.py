from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from canonical_data import (
    CanonicalFeatureFlags, CanonicalMarketObservationResolver, CanonicalRegistry,
    CanonicalMinuteBarResolver,
    DatasetType, FreshnessState, LifecycleManager, LifecycleState,
    evaluate_freshness, is_early_close, is_xnys_session, normalise_minute_bars,
    normalise_occ_symbol, parse_exact_option_quote, parse_marketdata_option_response,
    parse_occ_symbol, session_bounds, session_snapshot,
)
from canonical_data.errors import FetchNotAuthorised
from market_structure.lifecycle import direction_relationship, transition_lifecycle
from market_structure.params import MS_PARAMS_V1
from market_structure.service import calculate_market_structure_evidence


FIXTURES = Path(__file__).parent / "fixtures" / "marketdata"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class MarketDataContractTests(unittest.TestCase):
    def test_scalar_and_list_shapes_normalise_to_v2(self):
        scalar = parse_marketdata_option_response(fixture("option_quote_scalar_ok.json"), ticker="AAPL")
        listed = parse_marketdata_option_response(fixture("option_chain_list_sizes.json"), ticker="AAPL")
        self.assertEqual(len(scalar), 1); self.assertEqual(len(listed), 2)
        self.assertEqual(scalar.iloc[0].symbol, "AAPL260918C00200000")
        self.assertEqual(scalar.iloc[0].bid_size, 12)
        self.assertEqual(listed.iloc[1].bid_size_quality, "OBSERVED_ZERO")
        self.assertEqual(listed.iloc[1].ask_size_quality, "MISSING")

    def test_zero_bid_is_observed_one_sided_not_missing(self):
        quote = parse_exact_option_quote(fixture("option_chain_list_sizes.json"), ticker="AAPL", symbol="AAPL260918P00200000")
        self.assertEqual(quote["bid"], 0.0); self.assertEqual(quote["mid"], 1.5)
        self.assertEqual(quote["quote_quality"], "ONE_SIDED"); self.assertFalse(quote["executable_now"])
        self.assertIn("ZERO_BID", quote["quality_flags"])

    def test_negative_size_rejected_and_crossed_exact_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid displayed size"):
            parse_marketdata_option_response(fixture("option_quote_negative_size.json"), ticker="AAPL")
        crossed = parse_marketdata_option_response(fixture("option_quote_crossed.json"), ticker="AAPL")
        self.assertEqual(crossed.iloc[0].quote_quality, "INVALID")
        with self.assertRaisesRegex(ValueError, "crossed"):
            parse_exact_option_quote(fixture("option_quote_crossed.json"), ticker="AAPL", symbol="AAPL260918C00200000")

    def test_no_data_and_incompatible_parallel_array(self):
        self.assertTrue(parse_marketdata_option_response(fixture("option_quote_no_data.json"), ticker="AAPL").empty)
        bad = fixture("option_chain_list_sizes.json"); bad["bidSize"] = [1, 2, 3]
        with self.assertRaisesRegex(ValueError, "parallel-array"):
            parse_marketdata_option_response(bad, ticker="AAPL")


class IdentityAndSessionTests(unittest.TestCase):
    def test_compact_occ_preserves_adjusted_root(self):
        self.assertEqual(normalise_occ_symbol(" O:AAPL1 260918P00200000 "), "AAPL1260918P00200000")
        identity = parse_occ_symbol("AAPL1260918P00200000")
        self.assertEqual(identity.root, "AAPL1"); self.assertEqual(identity.side, "PUT")

    def test_xnys_dst_holiday_and_early_close(self):
        january_open, _ = session_bounds(date(2026, 1, 5))
        march_open, _ = session_bounds(date(2026, 3, 9))
        self.assertEqual(january_open.hour, 14); self.assertEqual(march_open.hour, 13)
        self.assertTrue(is_early_close(date(2026, 11, 27)))
        self.assertFalse(is_xnys_session(date(2021, 12, 31)))
        _, early_close = session_bounds(date(2026, 11, 27)); self.assertEqual(early_close.hour, 18)
        thanksgiving = session_snapshot(datetime(2026, 11, 26, 15, tzinfo=timezone.utc))
        self.assertEqual(thanksgiving.state.value, "CLOSED")

    def test_semantic_eod_and_live_freshness(self):
        now = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)  # Monday premarket
        self.assertEqual(evaluate_freshness(as_of=datetime(2026,8,28,20,tzinfo=timezone.utc), dataset_session=date(2026,8,28), domain="OPTION_CHAIN", now=now), FreshnessState.EOD_CURRENT)
        self.assertEqual(evaluate_freshness(as_of=now, dataset_session=date(2026,8,31), domain="LIVE_OPTION", now=now), FreshnessState.FRESH)


class MinuteAndStructureTests(unittest.TestCase):
    @staticmethod
    def bars() -> pd.DataFrame:
        start = pd.Timestamp("2026-08-28T13:30:00Z")
        rows=[]
        for index in range(120):
            base = 100.0 if index < 60 else 103.0
            rows.append({"timestamp_utc": start+pd.Timedelta(minutes=index), "open":base, "high":base+0.05,
                         "low":base-0.05, "close":base+0.02, "volume":1000, "session_segment":"REGULAR"})
        return normalise_minute_bars(pd.DataFrame(rows),ticker="TEST")

    def test_minute_contract_computes_canonical_vwap(self):
        bars=self.bars(); self.assertEqual(len(bars),120)
        self.assertTrue(bars.vwap_canonical.notna().all())
        self.assertEqual(set(bars.adjustment_convention),{"UNADJUSTED"})

    def test_structure_is_proposed_and_advisory_only(self):
        evidence=calculate_market_structure_evidence(ticker="TEST",session_date=date(2026,8,28),run_id="R1",bars=self.bars(),
            exchange_tick=0.01,atr14=2.0,regular_open_utc=datetime(2026,8,28,13,30,tzinfo=timezone.utc),governed_direction="CALL",
            input_dataset_ids=("D1",),input_hashes=("H1",))
        self.assertEqual(evidence["ms_parameter_calibration_status"],"PROPOSED_NOT_CALIBRATED")
        self.assertEqual(evidence["ms_authority"],"ADVISORY_ONLY")
        self.assertFalse(evidence["ms_can_grant_capital"]); self.assertFalse(evidence["ms_can_reverse_direction"])
        self.assertTrue(all(key.startswith("ms_") or key in {"ticker","session_date","run_id"} for key in evidence))

    def test_lifecycle_and_relationship_are_deterministic(self):
        accepted=transition_lifecycle(prior="MS_DEVELOPING",detected=True,accepted=True,repair_pct=0.1)
        self.assertEqual(accepted,"MS_ACCEPTED")
        self.assertEqual(direction_relationship(governed_direction="CALL",structure_direction="ABOVE",lifecycle=accepted,quality="ONE_MINUTE_ESTIMATED"),"ALIGNED")
        self.assertEqual(direction_relationship(governed_direction="PUT",structure_direction="ABOVE",lifecycle="MS_REPAIRING",quality="ONE_MINUTE_ESTIMATED"),"NEUTRAL")
        self.assertEqual(MS_PARAMS_V1.calibration_status,"PROPOSED_NOT_CALIBRATED")


class CanonicalResolverTests(unittest.TestCase):
    def test_chain_fetch_is_idempotent_and_non_worklisted_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); registry=CanonicalRegistry(root/"control.sqlite"); registry.initialise()
            session=date(2026,8,28); registry.register_run("R1","EVENING",session)
            lifecycle=LifecycleManager(registry)
            for ticker in ("AAPL","DROP"):
                event=lifecycle.register("R1",ticker,allowed_capabilities=(DatasetType.OPTION_CHAIN,))
                event=lifecycle.transition("R1",ticker,LifecycleState.ACTIVE_CORE,stage="PACKAGES",reason_code="TEST",expected_version=event.version,allowed_capabilities=(DatasetType.OPTION_CHAIN,))
                lifecycle.transition("R1",ticker,LifecycleState.ACTIVE_OPTIONS,stage="OPTIONS",reason_code="TEST",expected_version=event.version,allowed_capabilities=(DatasetType.OPTION_CHAIN,))
            lifecycle.create_worklist("R1","OPTIONS",DatasetType.OPTION_CHAIN,("AAPL",))
            flags=CanonicalFeatureFlags(enabled=True,write_through=True,stage_gating_enforced=True,offline_replay=False,ohlcv_mode="ACTIVE")
            resolver=CanonicalMarketObservationResolver(registry_path=root/"control.sqlite",payload_root=root/"payloads",run_id="R1",flags=flags)
            calls=[]
            chain_payload=fixture("option_chain_list_sizes.json")
            friday_close=int(datetime(2026,8,28,20,0,tzinfo=timezone.utc).timestamp())
            chain_payload["updated"]=[friday_close] * len(chain_payload["optionSymbol"])
            first=resolver.option_chain(ticker="AAPL",session_date=session,dte_max=110,min_open_interest=0,fetch=lambda ticker:(calls.append(ticker) or chain_payload))
            second=resolver.option_chain(ticker="AAPL",session_date=session,dte_max=110,min_open_interest=0,fetch=lambda ticker:(calls.append(ticker) or chain_payload))
            self.assertEqual(first.resolution,"PROVIDER_FETCH"); self.assertIn(second.resolution,{"EXACT_HIT","SUPERSET_HIT"}); self.assertEqual(calls,["AAPL"])
            with self.assertRaises(FetchNotAuthorised):
                resolver.option_chain(ticker="DROP",session_date=session,dte_max=110,min_open_interest=0,fetch=lambda _:chain_payload)

    def test_exact_quote_and_minute_partition_are_immutable_cache_hits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); registry=CanonicalRegistry(root/"control.sqlite"); registry.initialise()
            session=date(2026,8,30); registry.register_run("R2","MORNING",session)
            lifecycle=LifecycleManager(registry)
            event=lifecycle.register("R2","AAPL",allowed_capabilities=(DatasetType.EXACT_OPTION_QUOTE,DatasetType.INTRADAY_BAR))
            event=lifecycle.transition("R2","AAPL",LifecycleState.ACTIVE_CORE,stage="PACKAGES",reason_code="TEST",expected_version=event.version,allowed_capabilities=(DatasetType.EXACT_OPTION_QUOTE,DatasetType.INTRADAY_BAR))
            event=lifecycle.transition("R2","AAPL",LifecycleState.ACTIVE_MORNING,stage="MORNING_GATE",reason_code="TEST",expected_version=event.version,allowed_capabilities=(DatasetType.EXACT_OPTION_QUOTE,DatasetType.INTRADAY_BAR))
            lifecycle.create_worklist("R2","MORNING_GATE",DatasetType.EXACT_OPTION_QUOTE,("AAPL",))
            flags=CanonicalFeatureFlags(enabled=True,write_through=True,stage_gating_enforced=True,offline_replay=False,ohlcv_mode="ACTIVE")
            resolver=CanonicalMarketObservationResolver(registry_path=root/"control.sqlite",payload_root=root/"payloads",run_id="R2",flags=flags)
            calls=[]; symbol="AAPL260918C00200000"
            first=resolver.exact_option_quote(ticker="AAPL",symbol=symbol,session_date=session,freshness_seconds=10**9,fetch=lambda ticker,occ:(calls.append((ticker,occ)) or fixture("option_quote_scalar_ok.json")))
            second=resolver.exact_option_quote(ticker="AAPL",symbol=symbol,session_date=session,freshness_seconds=10**9,fetch=lambda ticker,occ:(calls.append((ticker,occ)) or fixture("option_quote_scalar_ok.json")))
            self.assertEqual(first.payload["bid_size"],12); self.assertEqual(calls,[("AAPL",symbol)])
            self.assertIn(second.resolution,{"EXACT_HIT","SUPERSET_HIT"})

            # Advance the same active ticker to the derived structure worklist.
            event=lifecycle.latest("R2","AAPL")
            lifecycle.transition("R2","AAPL",LifecycleState.ACTIVE_MORNING,stage="MARKET_STRUCTURE",reason_code="TEST",expected_version=event.version,allowed_capabilities=(DatasetType.INTRADAY_BAR,))
            lifecycle.create_worklist("R2","MARKET_STRUCTURE",DatasetType.INTRADAY_BAR,("AAPL",))
            minutes=CanonicalMinuteBarResolver(registry_path=root/"control.sqlite",payload_root=root/"payloads",run_id="R2",flags=flags)
            start=datetime(2026,8,30,13,30,tzinfo=timezone.utc); end=start+pd.Timedelta(minutes=2); minute_calls=[]
            def fetch_minutes(ticker,gap_start,gap_end):
                minute_calls.append((gap_start,gap_end)); stamps=pd.date_range(gap_start,gap_end,freq="min")
                return pd.DataFrame({"timestamp_utc":stamps,"open":100,"high":101,"low":99,"close":100.5,"volume":100})
            minute_first=minutes.resolve(ticker="AAPL",session_date=session,start_utc=start,end_utc=end,fetch_missing=fetch_minutes,provider="LICENSED_AGGREGATES")
            minute_second=minutes.resolve(ticker="AAPL",session_date=session,start_utc=start,end_utc=end,fetch_missing=fetch_minutes,provider="LICENSED_AGGREGATES")
            self.assertEqual(len(minute_first.frame),3); self.assertEqual(minute_first.physical_fetches,1)
            self.assertEqual(minute_second.physical_fetches,0); self.assertEqual(len(minute_calls),1)


if __name__ == "__main__":
    unittest.main()
