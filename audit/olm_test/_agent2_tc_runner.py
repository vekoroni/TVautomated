"""OLM validation test runner - Agent 2.

Executes fixture-driven scenarios directly against the real OLM code paths.
All run_ids are tagged TEST_OLM_TC<N>_20260829 and use tmp/copy databases only.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from contracts.options_liquidity_lifecycle import (  # noqa: E402
    LifecycleInputs,
    classify_current_executability,
    classify_moneyness,
    classify_remaining_runway,
    evaluate_maturation_horizons,
    evaluate_options_liquidity_lifecycle,
)
from contracts.direction_governance import resolve_governed_direction  # noqa: E402
from canonical_data.contracts import (  # noqa: E402
    CompletenessStatus, DataScope, DatasetRecord, DatasetType,
)
from canonical_data.errors import DatasetValidationError  # noqa: E402
from canonical_data.option_liquidity_lifecycle import (  # noqa: E402
    ContractLiquidityState, MonitorState, OptionLiquidityLifecycleStore, ThesisState,
    OptionLifecycleConflict,
)
from canonical_data.registry import CanonicalRegistry  # noqa: E402
import morning_gate  # noqa: E402
import execution_gate  # noqa: E402
from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row  # noqa: E402

import importlib.util

spec = importlib.util.spec_from_file_location(
    "avshunter_options_intelligence", str(ROOT / "scripts" / "avshunter_options_intelligence.py")
)
oi_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oi_mod)

import pandas as pd  # noqa: E402

RESULTS = {}


def record(tc, **kwargs):
    RESULTS[tc] = kwargs
    print(f"\n===== {tc} =====")
    for k, v in kwargs.items():
        print(f"  {k}: {v}")


def new_store(tag: str):
    tmp = Path(tempfile.mkdtemp(prefix=f"olm_{tag}_"))
    registry = CanonicalRegistry(tmp / "control_plane.sqlite")
    registry.initialise()
    run_id = f"TEST_OLM_{tag}_20260829"
    registry.register_run(run_id, "EVENING", date(2026, 8, 29))
    store = OptionLiquidityLifecycleStore(registry)
    store.initialise()
    return tmp, registry, store, run_id


def register_dataset(registry, run_id, ticker, session, quote_time, tag):
    dataset_id = f"chain-{ticker.lower()}-{tag.lower()}"
    payload = registry.database_path.parent / f"{dataset_id}.parquet"
    payload.write_bytes(b"PAR1-test-PAR1")
    registry.register_dataset(
        DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id=ticker,
            session_date=session,
            scope=DataScope(start_date=session, end_date=session, dte_min=1, dte_max=90, sides=("CALL", "PUT")),
            provider="MARKETDATA",
            content_hash="a" * 64,
            completeness_status=CompletenessStatus.COMPLETE,
            storage_uri=str(payload),
            observed_at=quote_time,
            as_of=quote_time,
            adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="option_chain_v1",
            source_run_id=run_id,
        )
    )
    return dataset_id


# ---------------------------------------------------------------------------
# TC-01 / TC-02 : OTM illiquid EOD -> ATM/liquid day2 transition (CALL / PUT)
# ---------------------------------------------------------------------------
def tc_01_02(side: str, tc: str):
    # Day 1: OTM, wide spread -> LIQUIDITY_PENDING
    if side == "CALL":
        day1 = evaluate_options_liquidity_lifecycle(LifecycleInputs(
            side="CALL", spot=100.0, strike=106.0, delta=0.28,
            bid=1.00, ask=1.60, bid_size=5, ask_size=5, quote_age_seconds=30,
            dte=25, remaining_hold_sessions=8, forecast_vol_annual=0.45,
            thesis_spot=100.0, current_spot=100.0, structural_target=115.0,
            invalidation_spot=93.0,
        ))
        day2 = evaluate_options_liquidity_lifecycle(LifecycleInputs(
            side="CALL", spot=105.8, strike=106.0, delta=0.48,
            bid=2.30, ask=2.42, bid_size=15, ask_size=20, quote_age_seconds=20,
            dte=24, remaining_hold_sessions=8, forecast_vol_annual=0.45,
            thesis_spot=100.0, current_spot=105.8, structural_target=115.0,
            invalidation_spot=93.0,
        ))
    else:
        day1 = evaluate_options_liquidity_lifecycle(LifecycleInputs(
            side="PUT", spot=100.0, strike=94.0, delta=-0.28,
            bid=1.00, ask=1.60, bid_size=5, ask_size=5, quote_age_seconds=30,
            dte=25, remaining_hold_sessions=8, forecast_vol_annual=0.45,
            thesis_spot=100.0, current_spot=100.0, structural_target=85.0,
            invalidation_spot=107.0,
        ))
        day2 = evaluate_options_liquidity_lifecycle(LifecycleInputs(
            side="PUT", spot=94.2, strike=94.0, delta=-0.48,
            bid=2.30, ask=2.42, bid_size=15, ask_size=20, quote_age_seconds=20,
            dte=24, remaining_hold_sessions=8, forecast_vol_annual=0.45,
            thesis_spot=100.0, current_spot=94.2, structural_target=85.0,
            invalidation_spot=107.0,
        ))
    record(
        tc,
        day1_liquidity_state=day1["liquidity_state"],
        day1_moneyness_state=day1["moneyness_state"],
        day1_executable_now=day1["executable_now"],
        day2_liquidity_state=day2["liquidity_state"],
        day2_moneyness_state=day2["moneyness_state"],
        day2_executable_now=day2["executable_now"],
        day2_morning_transition_would_be=(
            "EXECUTABLE_NOW" if day2["liquidity_state"] == "EXECUTABLE_NOW"
            and day2["remaining_runway_state"] not in {"THESIS_INVALIDATED", "MOVE_ALREADY_REALIZED"}
            else "NOT_EXECUTABLE"
        ),
    )
    return day1, day2


# ---------------------------------------------------------------------------
# TC-03 / TC-04 : OI is not a hard gate (classifier has no OI parameter at all)
# ---------------------------------------------------------------------------
def tc_03_04():
    import inspect
    sig = inspect.signature(classify_current_executability)
    has_oi_param = any("interest" in p.lower() or p.lower() in ("oi", "volume") for p in sig.parameters)

    low_oi_tight = classify_current_executability(
        bid=4.95, ask=5.05, bid_size=12, ask_size=10, quote_age_seconds=10,
        dte=25, minimum_required_dte=15, moneyness_treatment="PREFERRED_EXECUTION",
    )
    high_oi_zero_bid = classify_current_executability(
        bid=0, ask=0.55, bid_size=0, ask_size=25, quote_age_seconds=10,
        dte=25, minimum_required_dte=15, moneyness_treatment="PREFERRED_EXECUTION",
    )
    record(
        "TC-03",
        classifier_signature_has_oi_param=has_oi_param,
        low_oi_tight_fresh_result=low_oi_tight["liquidity_state"],
        executable_now=low_oi_tight["executable_now"],
    )
    record(
        "TC-04",
        classifier_signature_has_oi_param=has_oi_param,
        high_oi_zero_bid_result=high_oi_zero_bid["liquidity_state"],
        executable_now=high_oi_zero_bid["executable_now"],
    )
    return low_oi_tight, high_oi_zero_bid


# ---------------------------------------------------------------------------
# TC-05 : wide-spread contract stays monitored, never BUY_NOW/BUY_SMALL
# ---------------------------------------------------------------------------
def tc_05():
    wide = classify_current_executability(
        bid=1.00, ask=1.55, bid_size=8, ask_size=8, quote_age_seconds=15,
        dte=25, minimum_required_dte=15, moneyness_treatment="PREFERRED_EXECUTION",
    )
    gdr = resolve_governed_direction(
        ticker="WIDE", run_id="TEST_OLM_TC05_20260829", discovery_direction="CALL",
        governed_direction="CALL", governed_basis="test=CALL", row={},
        decided_at_utc="2026-08-29T13:30:00+00:00",
    )
    row = {
        **gdr,
        "ticker": "WIDE",
        "morning_execution_permission": "GO",
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": "O:WIDE260918C00100000",
        "morning_selected_contract_symbol": "O:WIDE260918C00100000",
        "contract_symbol": "O:WIDE260918C00100000",
        "campaign_verdict": "READY_EXECUTE",
        "live_contract_bid": wide["bid"],
        "live_contract_ask": wide["ask"],
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.35,
        # OLM state present on the row but execution_gate.py never reads it:
        "liquidity_state": wide["liquidity_state"],
        "morning_transition_state": "LIQUIDITY_STILL_PENDING",
        "executable_now": wide["executable_now"],
    }
    gated = execution_gate.execution_gate(row)
    record(
        "TC-05",
        olm_liquidity_state=wide["liquidity_state"],
        olm_executable_now=wide["executable_now"],
        olm_spread_pct=wide["spread_pct"],
        execution_gate_final_action=gated["final_action"],
        execution_gate_reason=gated.get("gate_reason"),
        execution_gate_reads_olm_fields=False,
        lab_control_overrides_only_for="CONTRACT_REPRICE_REQUIRED (per contracts/lab_control.py:2119)",
    )
    return wide, gated


# ---------------------------------------------------------------------------
# TC-06 : MOVE_ALREADY_REALIZED (target reached but move mostly consumed)
# ---------------------------------------------------------------------------
def tc_06():
    result = classify_remaining_runway(
        "CALL", thesis_spot=100, current_spot=113.5, structural_target=115,
        invalidation_spot=95, one_session_expected_move_abs=6,
    )
    record(
        "TC-06",
        remaining_runway_state=result["remaining_runway_state"],
        thesis_move_consumed_factor=result["thesis_move_consumed_factor"],
        remaining_runway_factor=result["remaining_runway_factor"],
    )
    return result


# ---------------------------------------------------------------------------
# TC-07 : THESIS_INVALIDATED -> monitoring stops (maturation ineligible)
# ---------------------------------------------------------------------------
def tc_07():
    runway = classify_remaining_runway(
        "CALL", thesis_spot=100, current_spot=94, structural_target=115, invalidation_spot=95,
    )
    liquidity = classify_current_executability(
        bid=1.00, ask=1.30, quote_age_seconds=20, dte=25, minimum_required_dte=15,
        moneyness_treatment="MONITOR_OTM_MATURATION",
    )
    maturation = evaluate_maturation_horizons(
        "CALL", spot=94, strike=104, forecast_vol_annual=0.45,
        liquidity_assessment=liquidity,
        remaining_runway_factor=runway["remaining_runway_factor"],
        thesis_active=(runway["remaining_runway_state"] not in {"THESIS_INVALIDATED", "MOVE_ALREADY_REALIZED"}),
    )

    # Secondary check: does the *execution authority* gate (execution_gate.py,
    # Phase 11) independently stop a thesis OLM has marked THESIS_INVALIDATED,
    # given execution_gate.py has zero references to any OLM field/state?
    gdr = resolve_governed_direction(
        ticker="TC07", run_id="TEST_OLM_TC07_20260829", discovery_direction="CALL",
        governed_direction="CALL", governed_basis="test=CALL", row={},
        decided_at_utc="2026-08-29T13:30:00+00:00",
    )
    row = {
        **gdr,
        "ticker": "TC07",
        "morning_execution_permission": "GO",
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": "O:TC07260918C00104000",
        "morning_selected_contract_symbol": "O:TC07260918C00104000",
        "contract_symbol": "O:TC07260918C00104000",
        "signal_price": 94.0,
        "live_contract_bid": 1.85, "live_contract_ask": 1.95,
        "live_contract_delta": 0.44, "live_contract_iv": 0.35,
        # OLM says the thesis is dead; execution_gate.py never reads this field:
        "liquidity_state": liquidity["liquidity_state"],
        "morning_transition_state": "THESIS_INVALIDATED",
        "executable_now": liquidity["executable_now"],
    }
    gated = execution_gate.execution_gate(row)

    record(
        "TC-07",
        remaining_runway_state=runway["remaining_runway_state"],
        maturation_eligibility=maturation["maturation_eligibility"],
        maturation_score_1d=maturation["maturation_score_1d"],
        execution_gate_final_action_despite_thesis_invalidated=gated["final_action"],
        execution_gate_reason=gated.get("gate_reason"),
        execution_gate_reads_morning_transition_state=False,
    )
    return runway, maturation, gated


# ---------------------------------------------------------------------------
# TC-08 : neighbouring-strike / contract-family repair selection
# ---------------------------------------------------------------------------
def tc_08():
    now = datetime.now(timezone.utc).isoformat()

    def run(oi, volume, label):
        rows = [dict(
            right="C", strike=102, dte=20, expiration_date="2026-09-18",
            bid=1.00, ask=1.05, delta=0.30, gamma=0.02, theta=-0.03, vega=0.06,
            implied_vol=0.35, quote_timestamp_utc=now, open_interest=oi, volume=volume,
            symbol=f"TEST08{label}260918C00102000",
        )]
        df = pd.DataFrame(rows)
        ctx = {"direction": "CALL", "dte_window": (7, 30, 60), "spot": 100.0,
               "structural_target": 110.0, "dte_config": {}}
        return oi_mod.select_repair_alternative_contracts(df, ctx, selected_contract=None, limit=5)

    low_oi_tight_spread = run(oi=5, volume=2, label="LOW")
    at_threshold = run(oi=oi_mod.EV3_MIN_OPEN_INTEREST, volume=2, label="AT")
    zero_oi = run(oi=0, volume=0, label="ZERO")
    record(
        "TC-08",
        EV3_MIN_OPEN_INTEREST=oi_mod.EV3_MIN_OPEN_INTEREST,
        EV3_MIN_VOLUME=oi_mod.EV3_MIN_VOLUME,
        neighbour_low_oi5_vol2_tight_fresh_spread_selected=len(low_oi_tight_spread) > 0,
        neighbour_oi_at_threshold_selected=len(at_threshold) > 0,
        neighbour_zero_oi_selected=len(zero_oi) > 0,
        finding=(
            "select_repair_alternative_contracts() hard-gates on "
            "open_interest>=50 and volume>=1 -- a liquid/tight-fresh-quote "
            "neighbour with OI below 50 is DROPPED, contradicting the "
            "documented principle that OI/volume are ranking evidence, not "
            "acquisition gates (classify_current_executability has NO oi "
            "parameter at all, by contrast)."
        ),
    )
    return low_oi_tight_spread, at_threshold, zero_oi


# ---------------------------------------------------------------------------
# TC-09 : replacement contract -> full economics recomputation required
# ---------------------------------------------------------------------------
def tc_09():
    tmp, registry, store, run_id = new_store("TC09")
    try:
        session = date(2026, 8, 29)
        quote_time = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
        store.record_thesis_event(
            thesis_id="TC09-CALL-1", event_key="EOD-CREATED", run_id=run_id,
            ticker="TC09", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="LIQUIDITY_PENDING",
            structural_target=115.0, invalidation_spot=93.0,
            horizon_end_date=date(2026, 9, 4),
        )
        dataset_id = register_dataset(registry, run_id, "TC09", session, quote_time, "TC09")
        original = store.record_contract_observation(
            thesis_id="TC09-CALL-1", run_id=run_id, ticker="TC09",
            contract_symbol="TC09260918C00106000", option_side="CALL",
            quote_as_of=quote_time, source_dataset_id=dataset_id,
            spot=101.0, strike=106.0, expiration=date(2026, 9, 18), dte=20,
            delta=0.28, bid=0.40, ask=0.70, bid_size=3, ask_size=3,
            spread_pct=54.5, volume=4, open_interest=9, iv=0.52,
            liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
            maturation_score_1d=30.0, maturation_score_2d=45.0, maturation_score_3d=55.0,
        ).record
        replacement = store.record_contract_observation(
            thesis_id="TC09-CALL-1", run_id=run_id, ticker="TC09",
            contract_symbol="TC09260918C00104000", option_side="CALL",
            quote_as_of=quote_time + timedelta(minutes=5), source_dataset_id=dataset_id,
            spot=103.5, strike=104.0, expiration=date(2026, 9, 18), dte=20,
            delta=0.44, bid=1.85, ask=1.95, bid_size=25, ask_size=30,
            spread_pct=5.26, volume=210, open_interest=640, iv=0.41,
            liquidity_state=ContractLiquidityState.EXECUTABLE_NOW,
            maturation_score_1d=100.0, maturation_score_2d=100.0, maturation_score_3d=100.0,
        ).record

        blocked = None
        try:
            store.record_selection_event(
                thesis_id="TC09-CALL-1", event_key="MORNING-REPAIR-BAD", run_id=run_id,
                previous_contract_symbol=original.contract_symbol,
                selected_contract_symbol=replacement.contract_symbol,
                selected_observation_id=replacement.observation_id,
                selection_reason="NEIGHBOURING_STRIKE_EXECUTABLE",
                economics_recomputed=False, expected_version=None,
            )
        except DatasetValidationError as exc:
            blocked = str(exc)

        selection = store.record_selection_event(
            thesis_id="TC09-CALL-1", event_key="MORNING-REPAIR-OK", run_id=run_id,
            previous_contract_symbol=original.contract_symbol,
            selected_contract_symbol=replacement.contract_symbol,
            selected_observation_id=replacement.observation_id,
            selection_reason="NEIGHBOURING_STRIKE_EXECUTABLE",
            economics_recomputed=True, expected_version=None,
        ).record

        record(
            "TC-09",
            economics_recomputed_false_blocked_by=blocked,
            selection_succeeded_with_recompute=selection.economics_recomputed,
            original_symbol=original.contract_symbol, original_strike=original.strike,
            original_delta=original.delta, original_bid=original.bid, original_ask=original.ask,
            original_liquidity_state=original.liquidity_state.value,
            replacement_symbol=replacement.contract_symbol, replacement_strike=replacement.strike,
            replacement_delta=replacement.delta, replacement_bid=replacement.bid,
            replacement_ask=replacement.ask,
            replacement_liquidity_state=replacement.liquidity_state.value,
            fields_distinct=(original.strike != replacement.strike
                              and original.delta != replacement.delta
                              and original.bid != replacement.bid
                              and original.observation_id != replacement.observation_id),
        )
        return blocked, selection, original, replacement
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# TC-10 : stale quote -> historical context only, never live executable
# ---------------------------------------------------------------------------
def tc_10():
    stale = classify_current_executability(
        bid=4.80, ask=5.00, bid_size=10, ask_size=10, quote_age_seconds=3600,
        dte=25, minimum_required_dte=15, moneyness_treatment="PREFERRED_EXECUTION",
    )
    tmp, registry, store, run_id = new_store("TC10")
    try:
        session = date(2026, 8, 29)
        eod_quote_time = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
        store.record_thesis_event(
            thesis_id="TC10-CALL-1", event_key="EOD-CREATED", run_id=run_id,
            ticker="TC10", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="LIQUIDITY_PENDING",
            structural_target=115.0, invalidation_spot=93.0,
            horizon_end_date=date(2026, 9, 4),
        )
        dataset_id = register_dataset(registry, run_id, "TC10", session, eod_quote_time, "TC10")
        store.record_contract_observation(
            thesis_id="TC10-CALL-1", run_id=run_id, ticker="TC10",
            contract_symbol="TC10260918C00106000", option_side="CALL",
            quote_as_of=eod_quote_time, source_dataset_id=dataset_id,
            spot=101.0, strike=106.0, expiration=date(2026, 9, 18), dte=20,
            delta=0.28, bid=4.80, ask=5.00, bid_size=10, ask_size=10,
            spread_pct=4.08, volume=4, open_interest=9, iv=0.52,
            liquidity_state=ContractLiquidityState.EXECUTABLE_NOW,
        )
        # Next morning, ~14h later: EOD close observation is now far outside
        # freshness window -> should_fetch must demand a fresh MarketData quote,
        # not treat the EOD close as still executable.
        morning_now = eod_quote_time + timedelta(hours=14)
        decision = store.should_fetch("TC10-CALL-1", freshness_seconds=15 * 60, now=morning_now)
        record(
            "TC-10",
            classifier_stale_quote_result=stale["liquidity_state"],
            classifier_executable_now=stale["executable_now"],
            cds_should_fetch_next_morning=decision.should_fetch,
            cds_should_fetch_reason=decision.reason,
            eod_close_still_returned_as_latest_observation_context=(decision.latest_observation is not None),
            eod_close_liquidity_state_label=(
                decision.latest_observation.liquidity_state.value if decision.latest_observation else None
            ),
        )
        return stale, decision
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# TC-11 : morning live quote overrides EOD context
# ---------------------------------------------------------------------------
def tc_11():
    row = {
        "ticker": "TC11",
        "final_direction": "CALL",
        "thesis_id": "TC11-CALL-1",
        "thesis_spot": 100.0,
        "structural_target": 115.0,
        "invalidation_spot": 93.0,
        "contract_strike": 106.0,
        "contract_dte": 20,
        "remaining_hold_sessions": 8,
        "garch_forecast_vol": 0.45,
        "contract_symbol": "TC11260918C00106000",
        "morning_selected_contract_symbol": "TC11260918C00106000",
        # Stale/EOD-only bid-ask fields that _morning_liquidity_lifecycle
        # deliberately never reads for bid/ask (only live_data is read):
        "contract_bid": 999.0,
        "contract_ask": 999.0,
    }
    live_data_fresh = {
        "live_price": 105.8,
        "live_contract_bid": 2.30,
        "live_contract_ask": 2.42,
        "live_contract_delta": 0.48,
        "live_contract_iv": 0.40,
        "live_contract_provider_updated": "2026-08-29T13:31:00Z",
        "selected_long_leg": {"strike": 106.0, "dte": 19},
    }
    assessment = morning_gate._morning_liquidity_lifecycle(
        row, live_data_fresh, contract_changed=False, economics_recompute_complete=True,
    )
    record(
        "TC-11",
        bid_used=assessment.get("bid"),
        ask_used=assessment.get("ask"),
        current_spot_used=assessment.get("thesis_move_realised") is not None,
        liquidity_state=assessment.get("liquidity_state"),
        morning_transition_state=assessment.get("morning_transition_state"),
        eod_stale_bid_ask_ignored=(assessment.get("bid") == 2.30 and assessment.get("ask") == 2.42),
    )
    return assessment


# ---------------------------------------------------------------------------
# TC-14 : terminal thesis -> zero subsequent option-quote fetch requests
# ---------------------------------------------------------------------------
def tc_14():
    tmp, registry, store, run_id = new_store("TC14")
    try:
        session = date(2026, 8, 29)
        quote_time = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
        store.record_thesis_event(
            thesis_id="TC14-CALL-1", event_key="EOD-CREATED", run_id=run_id,
            ticker="TC14", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="LIQUIDITY_PENDING",
            structural_target=115.0, invalidation_spot=93.0,
            horizon_end_date=date(2026, 9, 4),
        )
        dataset_id = register_dataset(registry, run_id, "TC14", session, quote_time, "TC14")
        store.record_contract_observation(
            thesis_id="TC14-CALL-1", run_id=run_id, ticker="TC14",
            contract_symbol="TC14260918C00106000", option_side="CALL",
            quote_as_of=quote_time, source_dataset_id=dataset_id,
            spot=101.0, strike=106.0, expiration=date(2026, 9, 18), dte=20,
            delta=0.28, bid=0.40, ask=0.70, bid_size=3, ask_size=3,
            spread_pct=54.5, volume=4, open_interest=9, iv=0.52,
            liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
        )
        store.record_thesis_event(
            thesis_id="TC14-CALL-1", event_key="THESIS-INVALIDATED", run_id=run_id,
            ticker="TC14", direction="CALL", thesis_state=ThesisState.INVALIDATED,
            monitor_state=MonitorState.TERMINAL, reason_code="INVALIDATION_CROSSED",
            expected_version=1,
        )

        calls = {"live_contract": 0}

        def _boom_fetch_live_contract(occ_symbol):
            calls["live_contract"] += 1
            raise AssertionError("terminal thesis must not trigger a live option fetch")

        with (
            _patch(morning_gate, "_fetch_live_price", lambda t: {"live_price": 101.0}),
            _patch(morning_gate, "_fetch_options_skew", lambda t: {}),
            _patch(morning_gate, "_fetch_live_contract", _boom_fetch_live_contract),
        ):
            live = morning_gate._fetch_all_live(
                [{
                    "ticker": "TC14",
                    "thesis_id": "TC14-CALL-1",
                    "direction": "CALL",
                    "canonical_direction": "CALL",
                    "options_strategy": "LONG_CALL",
                    "contract_symbol": "TC14260918C00106000",
                }],
                spread_threshold=25.0,
                liquidity_store=store,
                liquidity_freshness_seconds=10**9,
            )["TC14"]

        worklist = store.active_monitor_worklist(freshness_seconds=0, now=quote_time)
        decision = store.should_fetch("TC14-CALL-1", freshness_seconds=0, now=quote_time)
        record(
            "TC-14",
            live_contract_fetch_calls_after_terminal=calls["live_contract"],
            should_fetch_after_terminal=decision.should_fetch,
            should_fetch_reason=decision.reason,
            active_monitor_worklist_len=len(worklist),
            morning_fetch_resolution=live.get("live_options_resolution"),
        )
        return calls, decision, worklist, live
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _patch:
    def __init__(self, module, name, func):
        self.module, self.name, self.func = module, name, func

    def __enter__(self):
        self.orig = getattr(self.module, self.name)
        setattr(self.module, self.name, self.func)
        return self

    def __exit__(self, *a):
        setattr(self.module, self.name, self.orig)


# ---------------------------------------------------------------------------
# TC-15 : CDS returns identical observation to two different consumers
# ---------------------------------------------------------------------------
def tc_15():
    tmp, registry, store, run_id = new_store("TC15")
    try:
        session = date(2026, 8, 29)
        quote_time = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)
        store.record_thesis_event(
            thesis_id="TC15-CALL-1", event_key="EOD-CREATED", run_id=run_id,
            ticker="TC15", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="LIQUIDITY_PENDING",
            structural_target=115.0, invalidation_spot=93.0,
            horizon_end_date=date(2026, 9, 4),
        )
        dataset_id = register_dataset(registry, run_id, "TC15", session, quote_time, "TC15")
        store.record_contract_observation(
            thesis_id="TC15-CALL-1", run_id=run_id, ticker="TC15",
            contract_symbol="TC15260918C00106000", option_side="CALL",
            quote_as_of=quote_time, source_dataset_id=dataset_id,
            spot=101.0, strike=106.0, expiration=date(2026, 9, 18), dte=20,
            delta=0.28, bid=0.40, ask=0.70, bid_size=3, ask_size=3,
            spread_pct=54.5, volume=4, open_interest=9, iv=0.52,
            liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
        )
        # Consumer A: store.latest_observation() (the governed accessor)
        consumer_a = store.latest_observation("TC15-CALL-1")
        # Consumer B: a wholly independent raw SQL path against the same db file
        with registry.connection() as connection:
            row = connection.execute(
                "SELECT * FROM option_contract_observations WHERE thesis_id = ? "
                "ORDER BY quote_as_of DESC, observed_at DESC LIMIT 1",
                ("TC15-CALL-1",),
            ).fetchone()
        consumer_b_bid = row["bid"]
        consumer_b_ask = row["ask"]
        consumer_b_symbol = row["contract_symbol"]
        consumer_b_hash = row["payload_hash"]
        identical = (
            consumer_a.bid == consumer_b_bid
            and consumer_a.ask == consumer_b_ask
            and consumer_a.contract_symbol == consumer_b_symbol
            and consumer_a.payload_hash == consumer_b_hash
        )
        record(
            "TC-15",
            consumer_a_bid=consumer_a.bid, consumer_a_ask=consumer_a.ask,
            consumer_a_symbol=consumer_a.contract_symbol, consumer_a_hash=consumer_a.payload_hash,
            consumer_b_bid=consumer_b_bid, consumer_b_ask=consumer_b_ask,
            consumer_b_symbol=consumer_b_symbol, consumer_b_hash=consumer_b_hash,
            identical=identical,
        )
        return identical
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# TC-12 : deep ITM classified via policy table (not lottery-ticket geometry)
# ---------------------------------------------------------------------------
def tc_12():
    result = classify_moneyness("CALL", spot=120, strike=90, delta=0.86)
    result_boundary = classify_moneyness("CALL", spot=100, strike=100, delta=0.68)
    record(
        "TC-12",
        deep_itm_delta_086_treatment=result["moneyness_treatment"],
        deep_itm_delta_086_band=result["delta_band"],
        review_band_delta_068_treatment=result_boundary["moneyness_treatment"],
        review_band_delta_068_band=result_boundary["delta_band"],
    )
    return result, result_boundary


# ---------------------------------------------------------------------------
# TC-13 : Phase A/B production route never emits a debit spread
# ---------------------------------------------------------------------------
def tc_13():
    def make_row(phase, intent="BUY_SETUP"):
        return pd.Series({
            "ticker": "TC13", "tier": 2, "phase": phase, "precor_intent": intent,
            "dominant_trend": "UP", "stock_price": 100.0, "entry_price": 100.0,
            "stop_loss": 97.0, "composite_score": 60, "win_probability": 55,
            "crabel_pattern": "", "run_id": "TEST_OLM_TC13_20260829",
            "generated_at_utc": "2026-08-29T12:00:00Z",
        })

    outputs = {}
    for phase in ["A", "B", "C", "D", "E"]:
        ctx = oi_mod.parse_structural_context(make_row(phase))
        outputs[phase] = (ctx.get("direction"), ctx.get("preferred_strategy"))
    put_ctx = oi_mod.parse_structural_context(make_row("A", intent="SELL_SETUP"))
    outputs["A_PUT"] = (put_ctx.get("direction"), put_ctx.get("preferred_strategy"))

    all_single_leg = all(
        v[1] in {"LONG_CALL", "LONG_PUT", "NO_DIRECTIONAL_STRATEGY"} for v in outputs.values()
    )
    record(
        "TC-13",
        phase_A=outputs["A"], phase_B=outputs["B"], phase_C=outputs["C"],
        phase_D=outputs["D"], phase_E=outputs["E"], phase_A_put=outputs["A_PUT"],
        never_a_spread_across_all_phases=all_single_leg,
    )
    return outputs


# ---------------------------------------------------------------------------
# TC-16 : Lab display field names match contracts/lab_control.py exactly
# ---------------------------------------------------------------------------
def tc_16():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "intelligence-lab" / "static" / "AVSHUNTER_sector_ui_patch.js").read_text(encoding="utf-8")
    field_set = set(FINAL_BOOK_FIELDS)
    olm_fields = [
        "thesis_id", "thesis_state", "liquidity_state", "morning_transition_state",
        "recovery_disposition", "executable_now", "moneyness_state", "delta_band",
        "minimum_required_dte", "dte_buffer_sessions", "atm_distance_sigma",
        "remaining_runway_pct", "remaining_runway_state", "maturation_state_1d",
        "maturation_state_2d", "maturation_state_3d", "maturation_score_1d",
        "maturation_score_2d", "maturation_score_3d", "maturation_score_is_probability",
        "maturation_execution_authority", "previous_contract_symbol", "contract_changed",
        "contract_selection_reason", "quote_as_of", "quote_freshness",
    ]
    referenced_in_html = {f: (f in html) for f in olm_fields}
    referenced_in_js = {f: (f in js) for f in olm_fields}
    not_in_book = [f for f in olm_fields if f not in field_set]
    referenced_but_missing_from_book = [
        f for f in olm_fields if (referenced_in_html[f] or referenced_in_js[f]) and f not in field_set
    ]
    record(
        "TC-16",
        all_olm_fields_in_FINAL_BOOK_FIELDS=(len(not_in_book) == 0),
        not_in_book=not_in_book,
        referenced_in_html_count=sum(referenced_in_html.values()),
        referenced_in_js_count=sum(referenced_in_js.values()),
        referenced_but_missing_from_book=referenced_but_missing_from_book,
        html_fields_missing=[f for f, v in referenced_in_html.items() if not v],
        js_fields_missing=[f for f, v in referenced_in_js.items() if not v],
    )
    return referenced_in_html, referenced_in_js, not_in_book


if __name__ == "__main__":
    tc_01_02("CALL", "TC-01")
    tc_01_02("PUT", "TC-02")
    tc_03_04()
    tc_05()
    tc_06()
    tc_07()
    tc_08()
    tc_09()
    tc_10()
    tc_11()
    tc_12()
    tc_13()
    tc_14()
    tc_15()
    tc_16()

    out_path = Path(__file__).parent / "_agent2_tc_results.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print(f"\n\nWrote {out_path}")
