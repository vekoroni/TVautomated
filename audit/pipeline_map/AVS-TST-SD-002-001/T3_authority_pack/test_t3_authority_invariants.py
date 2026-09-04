"""AVS-TST-SD-002-001 / T3 authority-invariant adversarial pack.

Each test attempts to violate one row of the AVS-SD-002 section 7 authority
matrix or the AVS-AR-003 section 8 alignment table.  Direction-bearing probes
run CALL / PUT / OTHER.  Read-only against production modules.

Test ids map to T3_authority_matrix.csv.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from canonical_data.run_plan import RequestedAction, resolve_run_plan  # noqa: E402
from canonical_data.session_clock import session_bounds  # noqa: E402
from contracts.direction_governance import resolve_governed_direction  # noqa: E402
from contracts.interpreter_handoff import (  # noqa: E402
    HandoffValidationError,
    validate_handoff_manifest,
)
from contracts.interpreter_handoff_materializer import (  # noqa: E402
    materialize_interpreter_handoff,
)
from contracts.market_profile_evidence import MarketProfileEvidence  # noqa: E402
from execution_gate import execution_gate  # noqa: E402
from macro_horizon_router import route_signals_by_horizon  # noqa: E402
from market_structure.completed_profile import build_profile_evidence  # noqa: E402
from orchestrator.dynamic_validation import (  # noqa: E402
    FrozenThesis,
    UnderlyingObservation,
    validate_thesis,
)
from vanguard.layer1_auction.auction_synthesizer import AuctionStateSynthesizer  # noqa: E402
from vanguard.layer2_statistical.state_calculator import StateVectorCalculator  # noqa: E402
from vanguard.schemas.input_schema import (  # noqa: E402
    CalendarData,
    MacroData,
    MicrostructureData,
    OptionsData,
    TechnicalData,
    VanguardInput,
)

SESSION = date(2026, 8, 31)
DIRECTIONS = ["CALL", "PUT", "OTHER"]


# ---------------------------------------------------------------- helpers ---

def _intraday(interval: int = 5, count: int | None = None) -> pd.DataFrame:
    open_utc, close_utc = session_bounds(SESSION)
    stamps = pd.date_range(open_utc, close_utc, freq=f"{interval}min")
    if count is not None:
        stamps = stamps[:count]
    index = pd.Series(range(len(stamps)), dtype=float)
    center = 100.0 + (index % 12) * 0.05
    return pd.DataFrame({
        "timestamp_utc": stamps, "open": center, "high": center + 0.20,
        "low": center - 0.20, "close": center + 0.05,
        "volume": 1_000.0 + index * 10, "interval_minutes": interval,
        "session_segment": "REGULAR", "provider_observed_at_utc": stamps,
        "observed_at": stamps,
    })


def _evidence() -> MarketProfileEvidence:
    open_utc, close_utc = session_bounds(SESSION)
    return build_profile_evidence(
        ticker="AAPL", session_date=SESSION, evidence_state="COMPLETED_SESSION",
        bars=_intraday(), exchange_tick=0.01, atr14=2.0,
        regular_open_utc=open_utc, input_dataset_ids=("bars-1",),
        input_hashes=("hash-1",), completeness_status="COMPLETE",
        calculated_at_utc=close_utc,
    )


def _vanguard_input(evidence, *, required=True, macro=None) -> VanguardInput:
    return VanguardInput(
        ticker="AAPL",
        analysis_timestamp=datetime(2026, 8, 31, 21, tzinfo=timezone.utc),
        current_price=100.25, calendar=CalendarData(), options=OptionsData(),
        technical=TechnicalData(ohlcv=pd.DataFrame()),
        microstructure=MicrostructureData(), macro=macro or MacroData(),
        market_profile_evidence=evidence, market_profile_contract_required=required,
    )


def _gate_stub(_thesis, _underlying, quote, transition, _plan):
    return {"action": "ELIGIBLE" if transition == "THESIS_CONFIRMED" and quote else "NO_TRADE",
            "capital_authority": "EXECUTION_GATE"}


def _thesis(direction: str) -> FrozenThesis:
    if direction == "CALL":
        return FrozenThesis("THESIS-AAPL", "AAPL", "CALL", SESSION.isoformat(),
                            100.0, 110.0, 95.0, "AAPL260918C00100000",
                            trigger=101.0, maximum_entry=106.0)
    if direction == "PUT":
        return FrozenThesis("THESIS-AAPL", "AAPL", "PUT", SESSION.isoformat(),
                            100.0, 90.0, 105.0, "AAPL260918P00100000",
                            trigger=99.0, maximum_entry=94.0)
    # The contract's third direction is NON_DIRECTIONAL; "UNRESOLVED" is
    # rejected outright by FrozenThesis.__post_init__ (recorded in T3 notes).
    return FrozenThesis("THESIS-AAPL", "AAPL", "NON_DIRECTIONAL", SESSION.isoformat(),
                        100.0, 110.0, 95.0, "", trigger=None, maximum_entry=None)


def _plan(at: datetime, action=RequestedAction.VALIDATE):
    return resolve_run_plan(
        requested_action=action, as_of_utc=at, evidence_cutoff_utc=at,
        existing_thesis_id="THESIS-AAPL", existing_thesis_session=SESSION,
        authorised_tickers=("AAPL",), pipeline_run_id="T3",
    )


def _gate_row(direction: str, **over) -> dict:
    side = direction if direction in {"CALL", "PUT"} else "UNRESOLVED"
    symbol = "AAA260918C00100000" if direction == "CALL" else "AAA260918P00100000"
    row = {
        "ticker": "AAA", "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE", "execution_verdict": "BUY_NOW",
        "contract_symbol": symbol, "live_contract_bid": 4.9,
        "live_contract_ask": 5.0, "live_contract_mid": 4.95,
        "live_contract_delta": 0.45, "live_contract_iv": 0.40,
        "live_iv_rank": 50, "signal_price": 100,
        "monetisability_state": "MONETISABLE", "monetisability_reason": "T3",
        "monetisability_contract_symbol": symbol, "selected_contract_side": side,
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "execution_viability_reason": "T3",
        "execution_viability_contract_symbol": symbol,
        "execution_viability_eligible": True,
        "execution_viability_reviewable": True,
    }
    if direction in {"CALL", "PUT"}:
        row.update(resolve_governed_direction(
            ticker="AAA", run_id="20990101_010101", discovery_direction=direction,
            governed_direction=direction, governed_basis=f"t3={direction}",
            row={}, decided_at_utc="2099-01-01T01:01:01+00:00"))
    row.update(over)
    return row


# =========================================================== A3-01 ==========
# Market Profile packet with injected direction/action/capital keys must never
# propagate.  AVS-SD-002 sections 5.5, 8.2; authority matrix "advisory_evidence".

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a3_01_injected_authority_keys_never_propagate(direction: str) -> None:
    payload = _evidence().to_dict()
    contaminated = {
        **payload,
        "direction": direction,
        "governed_direction": direction,
        "final_action": "BUY_NOW",
        "capital_permission": True,
        "can_grant_capital": True,
        "can_reverse_direction": True,
        "ready_to_trade": True,
    }
    rebuilt = MarketProfileEvidence.from_mapping(contaminated)
    # (a) the packet schema must have no direction/action/capital field at all
    assert not hasattr(rebuilt, "direction")
    assert not hasattr(rebuilt, "final_action")
    assert "direction" not in rebuilt.to_dict()
    assert "final_action" not in rebuilt.to_dict()
    assert "capital_permission" not in rebuilt.to_dict()
    # (b) Vanguard must not be made ready_to_trade by the injected keys
    verdict = AuctionStateSynthesizer().synthesize(_vanguard_input(contaminated))
    assert verdict.ready_to_trade is False


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a3_01b_injected_capital_authority_must_be_pinned_false(direction: str) -> None:
    """MarketProfileEvidence.from_mapping must PIN, not merely default, the
    authority fields.

    AVS-SD-002 sections 5.5/8.2 and contracts/dynamic_session_authority_v1.json
    ("Market Profile ... have no capital authority") make these constants of the
    contract, not caller-supplied values.  This test is EXPECTED TO FAIL against
    the current tree -- that failure is the defect.
    """
    contaminated = {
        **_evidence().to_dict(),
        "direction": direction,
        "authority": "CAPITAL",
        "can_grant_capital": True,
        "can_reverse_direction": True,
    }
    rebuilt = MarketProfileEvidence.from_mapping(contaminated)
    assert rebuilt.can_grant_capital is False, (
        "a supplied packet set can_grant_capital=True on the profile contract"
    )
    assert rebuilt.can_reverse_direction is False
    assert rebuilt.authority == "ADVISORY_ONLY"
    assert rebuilt.to_dict()["can_grant_capital"] is False


# =========================================================== A3-02 ==========
# Extreme macro vs absent macro: bitwise-equal Discovery / L2 / route / gate.

def _macro(extreme: bool):
    if extreme:
        return SimpleNamespace(vix=85.0, vix_history=[10, 20, 40, 60, 85],
                               spy_trend="DOWN")
    return SimpleNamespace(vix=0.0, vix_history=[], spy_trend="")


def test_a3_02a_discovery_prior_is_bitwise_macro_invariant() -> None:
    from avshunter_discovery_ULTIMATE import (
        UltimateConfig, apply_state_prior_adjustment, assign_tier,
    )
    cfg = UltimateConfig()
    regimes = ["RISK_ON", "RISK_OFF", "TRANSITIONAL", "CRISIS", "", "UNKNOWN", None]
    for bucket in ("A", "B", "C", "D", "E", "UNKNOWN"):
        for maturity in ("EARLY", "MID", "LATE", "EXHAUSTED"):
            results = {
                repr(apply_state_prior_adjustment(70.0, bucket, r, maturity))
                for r in regimes
            }
            assert len(results) == 1, (
                f"prior varies with macro for bucket={bucket} maturity={maturity}: {results}"
            )
    # tier floors are macro-free by signature and by config
    for composite in (24.0, 34.9, 49.9, 50.0, 67.9, 71.9, 90.0):
        assert assign_tier(50.0, 50.0, composite, cfg) == assign_tier(
            50.0, 50.0, composite, cfg
        )


def test_a3_02b_discovery_threshold_injection_is_bitwise_macro_invariant(tmp_path) -> None:
    from regime_threshold_injector import apply_regime_to_config

    def snapshot():
        return SimpleNamespace(tier1_min=50.0, tier2_min=35.0, tier3_min=25.0,
                               compression_max=0.85, extreme_compression=0.60,
                               min_avg_vol20=500_000)

    absent = apply_regime_to_config(snapshot(), None)
    extreme_path = tmp_path / "macro.json"
    extreme_path.write_text(json.dumps({
        "regime_state": "CRISIS", "risk_on_off_switch": "RISK_OFF",
        "vol_mode": "FEAR_SPIKE", "macro_momentum_score": 0.0,
    }), encoding="utf-8")
    extreme = apply_regime_to_config(snapshot(), extreme_path)
    core = lambda c: (c.tier1_min, c.tier2_min, c.tier3_min,
                      c.compression_max, c.extreme_compression, c.min_avg_vol20)
    assert core(absent) == core(extreme)


def test_a3_02c_vanguard_l2_regime_is_bitwise_macro_invariant() -> None:
    calc = StateVectorCalculator()
    assert calc._calculate_macro_regime(_macro(True)) == calc._calculate_macro_regime(_macro(False))
    assert calc._calculate_macro_regime(_macro(True)) == {
        "regime": "TRANSITIONAL", "vix_percentile": 50.0
    }


@pytest.mark.parametrize("direction", ["CALL", "PUT", "STRANGLE"])
def test_a3_02d_horizon_route_is_bitwise_macro_invariant(direction, tmp_path) -> None:
    instrument = {"CALL": "LONG_CALL", "PUT": "LONG_PUT", "STRANGLE": "STRANGLE"}[direction]
    signal = {"ticker": "AAPL", "instrument": instrument, "dte": 30,
              "expected_holding_days": 7}
    absent = route_signals_by_horizon(None, [dict(signal)])
    extreme_path = tmp_path / "macro.json"
    extreme_path.write_text(json.dumps({
        "regime_state": "CRISIS", "risk_on_off_switch": "RISK_OFF",
        "horizon_routing": {}, "macro_momentum_score": 0.0,
    }), encoding="utf-8")
    extreme = route_signals_by_horizon(extreme_path, [dict(signal)])

    def flat(routed):
        return {bucket: [(s.ticker, s.instrument, s.horizon, s.action,
                          s.size_multiplier, s.macro_permitted, s.block_reason)
                         for s in items]
                for bucket, items in routed.items()}

    assert flat(absent) == flat(extreme)
    if direction != "STRANGLE":
        assert absent["blocked"] == []


def test_a3_02f_unsupported_instrument_must_be_recorded_not_dropped() -> None:
    """AVS-SD-002 section 12 / frozen invariant: input_count must equal
    processed + excluded + deferred + exception_count.

    A STRANGLE signal is discarded by ``continue`` at
    macro_horizon_router.py:349-351 and appears in no bucket, so the router's
    population does not reconcile.  Pre-existing (identical in the Phase 0
    baseline) and not addressed by the Phase 2 router work.  EXPECTED TO FAIL.
    """
    routed = route_signals_by_horizon(
        None, [{"ticker": "AAPL", "instrument": "STRANGLE", "dte": 30,
                "expected_holding_days": 7}]
    )
    total = sum(len(items) for items in routed.values())
    assert total == 1, (
        "one input signal produced zero routed or blocked records; "
        "the unsupported instrument was silently dropped"
    )


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a3_02e_execution_gate_action_is_bitwise_macro_invariant(direction: str) -> None:
    plain = execution_gate(_gate_row(direction))
    macro_loaded = execution_gate(_gate_row(
        direction, macro_regime="CRISIS", active_regime="RISK_OFF",
        macro_no_go="TRUE", bond_macro_state="STRESS",
        macro_sector_signal="REDUCE", vix_current=85.0,
    ))
    assert plain["final_action"] == macro_loaded["final_action"]
    assert plain["gate_reason"] == macro_loaded["gate_reason"]


# =========================================================== A3-03 ==========
# Developing profile at RTH with a contradicting relationship cannot change
# direction, action or capital.  Rev 1.1 section 10; SD-002 section 7.

@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_a3_03_contradicting_developing_profile_changes_nothing(direction: str) -> None:
    at = datetime(2026, 9, 1, 15, tzinfo=timezone.utc)
    price = 102.0 if direction == "CALL" else 98.0
    baseline = validate_thesis(
        _plan(at), _thesis(direction),
        resolve_underlying=lambda *_: UnderlyingObservation(
            "U-1", "AAPL", price, "2026-09-01T15:00:00Z", "DS-1"),
        resolve_option_quote=lambda *_: {"observation_id": "Q-1"},
        resolve_developing_profile=lambda *_: {"evidence_id": "P-1"},
        execution_gate=_gate_stub,
    )
    contradicting = validate_thesis(
        _plan(at), _thesis(direction),
        resolve_underlying=lambda *_: UnderlyingObservation(
            "U-1", "AAPL", price, "2026-09-01T15:00:00Z", "DS-1"),
        resolve_option_quote=lambda *_: {"observation_id": "Q-1"},
        resolve_developing_profile=lambda *_: {
            "evidence_id": "P-1",
            "relationship": "CONTRADICTING",
            "direction": "PUT" if direction == "CALL" else "CALL",
            "final_action": "BLOCK",
            "capital_permission": False,
            "can_reverse_direction": True,
        },
        execution_gate=_gate_stub,
    )
    assert contradicting.direction == baseline.direction == direction
    assert contradicting.transition == baseline.transition
    assert contradicting.can_reverse_direction is False
    assert contradicting.execution_gate_result == baseline.execution_gate_result


# =========================================================== A3-04 ==========
# Current price gapped through invalidation, both directions plus OTHER.

@pytest.mark.parametrize(
    ("direction", "price", "expected"),
    [
        ("CALL", 94.0, "THESIS_INVALIDATED"),
        ("PUT", 106.0, "THESIS_INVALIDATED"),
        ("CALL", 102.0, "THESIS_CONFIRMED"),
        ("PUT", 98.0, "THESIS_CONFIRMED"),
        ("CALL", 107.0, "ENTRY_RUNWAY_EXHAUSTED"),
        ("PUT", 93.0, "ENTRY_RUNWAY_EXHAUSTED"),
    ],
)
def test_a3_04a_mirror_geometry_is_symmetric(direction, price, expected) -> None:
    """Adds the two CALL mirrors the shipped Phase 5 pack omits."""
    event = validate_thesis(
        _plan(datetime(2026, 9, 1, 12, tzinfo=timezone.utc)), _thesis(direction),
        resolve_underlying=lambda *_: UnderlyingObservation(
            "U", "AAPL", price, "2026-09-01T12:00:00Z", "DS"),
        resolve_option_quote=lambda *_: {"observation_id": "Q"},
        execution_gate=_gate_stub,
    )
    assert event.transition == expected


def test_a3_04b_unresolved_direction_makes_no_transition_and_no_acquisition() -> None:
    calls: list[str] = []
    event = validate_thesis(
        _plan(datetime(2026, 9, 1, 15, tzinfo=timezone.utc)), _thesis("OTHER"),
        resolve_underlying=lambda *_: (calls.append("underlying") or
                                       UnderlyingObservation("U", "AAPL", 102.0,
                                                             "2026-09-01T15:00:00Z", "DS")),
        resolve_option_quote=lambda *_: calls.append("option"),
        resolve_developing_profile=lambda *_: calls.append("profile"),
        execution_gate=_gate_stub,
    )
    assert event.transition not in {"THESIS_CONFIRMED", "THESIS_INVALIDATED",
                                    "ENTRY_RUNWAY_EXHAUSTED"}
    assert "option" not in calls
    assert "profile" not in calls


# =========================================================== A3-05/06 =======
# Lab/Interpreter bundle tampering must fail closed.

def _handoff_row(**over) -> dict:
    row = {
        "run_id": "20260904_220000", "pipeline_mode": "MORNING_VALIDATION",
        "ticker": "AAA", "thesis_id": "THESIS:AAA", "trade_idea_id": "IDEA:AAA",
        "selected_structure_id": "STRUCT:AAA",
        "selected_contract_symbol": "AAA260918C00100000",
        "selected_quote_snapshot_id": "QUOTE-2", "governed_direction": "CALL",
        "thesis_state": "TRADEABLE_NOW", "olm_guard_disposition": "ELIGIBLE",
        "final_action": "BUY_SMALL", "capital_permission": "CAPITAL_LIMITED",
        "current_quote_timestamp_utc": "2026-09-08T12:00:00Z",
        "evidence_session_date": SESSION.isoformat(), "completed_close": 100.0,
        "target_spot": 110.0, "invalidation_spot": 95.0,
        "planned_hold_sessions": 5,
        "completed_profile_evidence_id": "PROFILE-EOD-1",
    }
    row.update(over)
    return row


def _validation_event(price: float = 102.0):
    plan = resolve_run_plan(
        requested_action="VALIDATE",
        as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        existing_thesis_id="BOOK-1", existing_thesis_session=date(2026, 9, 4),
        authorised_tickers=("AAA",), pipeline_run_id="20260904_220000",
    )
    thesis = FrozenThesis("THESIS:AAA", "AAA", "CALL", date(2026, 9, 4).isoformat(),
                          100.0, 110.0, 95.0, "AAA260918C00100000",
                          trigger=101.0, maximum_entry=106.0)
    return validate_thesis(
        plan, thesis,
        resolve_underlying=lambda *_: UnderlyingObservation(
            f"U-{price}", "AAA", price, "2026-09-08T12:00:00Z", f"DS-{price}"),
        resolve_option_quote=lambda *_: {"observation_id": "QUOTE-2"},
        execution_gate=lambda *_: {"action": "BUY_SMALL",
                                   "capital_authority": "EXECUTION_GATE"},
    )


def _materialise(tmp_path: Path, *, rows, events, sub: str):
    return materialize_interpreter_handoff(
        run_id="20260904_220000", rows=rows, run_root=tmp_path / sub / "20260904_220000",
        pipeline_mode="MORNING_VALIDATION", session_date="2026-09-08",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-09-08T12:01:00Z",
        validation_events=events, require_validation_lineage=True,
    )


def test_a3_05_hand_edited_final_action_fails_closed(tmp_path: Path) -> None:
    event = _validation_event()
    result = _materialise(tmp_path, rows=[_handoff_row()], events=[event], sub="ok")
    manifest_path = Path(result["handoff_manifest_path"])
    assert validate_handoff_manifest(manifest_path).bundles

    # Tamper the published Lab book row: upgrade the action after publication.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    book_file = Path(
        next(a["path"] for a in manifest["artifacts"] if a["role"] == "LAB_BOOK")
    )
    assert book_file.is_file()
    text = book_file.read_text(encoding="utf-8")
    assert "BUY_SMALL" in text
    book_file.write_text(text.replace("BUY_SMALL", "BUY_NOW"), encoding="utf-8")
    with pytest.raises(HandoffValidationError):
        validate_handoff_manifest(manifest_path)


def test_a3_05b_hand_edited_interpreter_bundle_fails_closed(tmp_path: Path) -> None:
    event = _validation_event()
    result = _materialise(tmp_path, rows=[_handoff_row()], events=[event], sub="bundle")
    manifest_path = Path(result["handoff_manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    bundle_file = Path(
        next(a["path"] for a in manifest["artifacts"]
             if a["role"] == "INTERPRETER_BUNDLES")
    )
    text = bundle_file.read_text(encoding="utf-8")
    assert "BUY_SMALL" in text
    bundle_file.write_text(text.replace("BUY_SMALL", "BUY_NOW"), encoding="utf-8")
    with pytest.raises(HandoffValidationError):
        validate_handoff_manifest(manifest_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticker", "BBB"),
        ("governed_direction", "PUT"),
        ("selected_contract_symbol", "AAA260918P00100000"),
        ("thesis_id", "THESIS:OTHER"),
    ],
)
def test_a3_06_identity_mismatch_fails_closed(tmp_path: Path, field, value) -> None:
    event = _validation_event()
    bad = {**event.to_dict()}
    key = {"ticker": "ticker", "governed_direction": "direction",
           "selected_contract_symbol": "selected_contract",
           "thesis_id": "thesis_id"}[field]
    bad[key] = value
    with pytest.raises(HandoffValidationError):
        _materialise(tmp_path, rows=[_handoff_row()], events=[bad],
                     sub=f"bad-{field}")


def test_a3_06b_contract_episode_mismatch_fails_closed(tmp_path: Path) -> None:
    event = _validation_event()
    bad = {**event.to_dict(), "selected_contract": "AAA260918C00105000"}
    with pytest.raises(HandoffValidationError):
        _materialise(tmp_path, rows=[_handoff_row()], events=[bad], sub="episode")


# =========================================================== A3-07 ==========
# Legacy negative rr_options must demote nothing anywhere on the path.

@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_a3_07_negative_rr_demotes_nothing(direction: str) -> None:
    from eod_candidate_engine import classify_tier
    from scripts.avshunter_options_intelligence import derive_verdict
    from contracts.long_option_policy import quote_spread_fraction

    base_tier = {
        "options_score": 50, "composite": 65, "eil_v3_verdict": "EXECUTE",
        "trigger_quality": "STRONG", "trigger_go_eligible": "TRUE",
        "catalyst_trade_class": "DATED_CATALYST_CONFIRMED",
        "catalyst_data_quality": "CONFIRMED", "sb_conv_score": 3,
        "direction_conflict_status": "RESOLVED",
        "direction": direction, "governed_direction": direction,
    }
    assert classify_tier({**base_tier, "rr": -999, "rr_underlying": -999}) == \
           classify_tier({**base_tier, "rr": 999, "rr_underlying": 999}) == "A"

    ctx = {"intent": "BUY", "direction": direction, "near_event": False,
           "structural_target": 110.0 if direction == "CALL" else 90.0}
    contract = {"dte": 30, "expiry": "2026-10-01", "bid": 2.0, "ask": 2.1,
                "mark": 2.05, "spread_pct": quote_spread_fraction(2.0, 2.1),
                "mark_synthetic": False}
    low = derive_verdict(90, ctx, {"iv_regime": "NORMAL"},
                         {"theta_drag_pct": 10, "option_value_at_target": 5,
                          "rr_options": -999}, [], contract=contract)
    high = derive_verdict(90, ctx, {"iv_regime": "NORMAL"},
                          {"theta_drag_pct": 10, "option_value_at_target": 5,
                           "rr_options": 999}, [], contract=contract)
    assert low == high and low[0] == "EXECUTE"

    plain = execution_gate(_gate_row(direction))
    negative = execution_gate(_gate_row(direction, rr_options=-999,
                                        rr_premium_expected=-999, rr=-999))
    assert plain["final_action"] == negative["final_action"]


# =========================================================== A3-09 ==========
# Plan identity: same inputs -> one plan hash; changed cutoff -> new invocation
# linked by supersedes_/retry_of_.

def test_a3_09a_identical_plan_is_idempotent_and_hash_stable() -> None:
    at = datetime(2026, 9, 3, 13, tzinfo=timezone.utc)
    first = _plan(at)
    second = _plan(at)
    assert first.plan_hash == second.plan_hash
    assert first.invocation_id == second.invocation_id


def test_a3_09b_changed_cutoff_mints_a_new_linked_invocation() -> None:
    at = datetime(2026, 9, 3, 13, tzinfo=timezone.utc)
    first = _plan(at)
    later = resolve_run_plan(
        requested_action=RequestedAction.VALIDATE, as_of_utc=at.replace(second=1),
        evidence_cutoff_utc=at.replace(second=1),
        existing_thesis_id="THESIS-AAPL", existing_thesis_session=SESSION,
        authorised_tickers=("AAPL",), pipeline_run_id="T3",
        supersedes_invocation_id=first.invocation_id,
    )
    assert later.invocation_id != first.invocation_id
    assert later.plan_hash != first.plan_hash
    assert (later.supersedes_invocation_id or later.retry_of_invocation_id) == \
           first.invocation_id


def test_a3_09c_ticker_order_does_not_change_the_plan_hash() -> None:
    at = datetime(2026, 9, 3, 13, tzinfo=timezone.utc)
    a = resolve_run_plan(requested_action=RequestedAction.VALIDATE, as_of_utc=at,
                         evidence_cutoff_utc=at, existing_thesis_id="T",
                         existing_thesis_session=SESSION,
                         authorised_tickers=("AAPL", "MSFT"), pipeline_run_id="T3")
    b = resolve_run_plan(requested_action=RequestedAction.VALIDATE, as_of_utc=at,
                         evidence_cutoff_utc=at, existing_thesis_id="T",
                         existing_thesis_session=SESSION,
                         authorised_tickers=("MSFT", "AAPL"), pipeline_run_id="T3")
    assert a.plan_hash == b.plan_hash


def test_a3_09d_added_ticker_changes_the_plan_hash() -> None:
    at = datetime(2026, 9, 3, 13, tzinfo=timezone.utc)
    a = resolve_run_plan(requested_action=RequestedAction.VALIDATE, as_of_utc=at,
                         evidence_cutoff_utc=at, existing_thesis_id="T",
                         existing_thesis_session=SESSION,
                         authorised_tickers=("AAPL", "MSFT"), pipeline_run_id="T3")
    c = resolve_run_plan(requested_action=RequestedAction.VALIDATE, as_of_utc=at,
                         evidence_cutoff_utc=at, existing_thesis_id="T",
                         existing_thesis_session=SESSION,
                         authorised_tickers=("AAPL", "MSFT", "NVDA"),
                         pipeline_run_id="T3")
    assert a.plan_hash != c.plan_hash


# =========================================================== A3-10 ==========
# Append-only ledger rejects UPDATE and DELETE from a raw connection.

def test_a3_10_ledger_rejects_raw_update_and_delete(tmp_path: Path) -> None:
    from canonical_data.decision_outcome_ledger import (
        DecisionOutcomeLedger, make_ledger_event,
    )
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    event = make_ledger_event(
        event_type="VALIDATION", occurred_at_utc="2026-09-08T12:00:00Z",
        run_id="20260904_220000", ticker="AAA", thesis_id="THESIS:AAA",
        validation_event_id="V-1", payload={"transition": "THESIS_CONFIRMED"})
    assert ledger.append(event) is True
    assert ledger.append(event) is False
    with sqlite3.connect(ledger.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE ledger_events SET ticker='BBB'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM ledger_events")
        assert connection.execute(
            "SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 1


# =========================================================== A3-11 ==========
# AVS-SD-002 section 14.4.6 / Phase 7 claim: the Interpreter resolver's import
# graph must contain no provider client and no urllib request path.

def test_a3_11_interpreter_import_graph_has_no_provider_client() -> None:
    """EXPECTED TO FAIL.

    ``pipeline_interpreter/evidence_resolver.py:27`` imports
    ``canonical_data.bundle_freshness``, which executes ``canonical_data``'s
    package ``__init__``.  Phase 3 added an eager re-export of
    ``MarketDataStockCandleAdapter`` there, and that module imports
    ``urllib.request`` and holds the live
    ``https://api.marketdata.app/v1/stocks/candles/`` URL.  The provider client
    is therefore inside the Interpreter's in-process import graph.
    """
    import subprocess

    probe = (
        "import sys;"
        "sys.path.insert(0,'.');"
        "sys.path.insert(0,'pipeline_interpreter');"
        "before=set(sys.modules);"
        "import pipeline_interpreter.evidence_resolver;"
        "new=set(sys.modules)-before;"
        "keys=('requests','httpx','urllib.request','urllib3','aiohttp',"
        "'polygon','marketdata','live_market_reader',"
        "'alternative_contract_selector','http.client');"
        "bad=[m for m in sorted(new) if any(k in m.lower() for k in keys)];"
        "print(';'.join(bad))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], cwd=str(REPO),
        capture_output=True, text=True, check=True,
    )
    pulled = [m for m in completed.stdout.strip().split(";") if m]
    assert pulled == [], f"provider/network modules in Interpreter graph: {pulled}"


def test_a3_11b_retired_interpreter_commands_refuse_without_substituting(capsys) -> None:
    """'Switch to the PUT' / 'pick a different strike' must be a refusal."""
    interpreter = REPO / "pipeline_interpreter"
    if str(interpreter) not in sys.path:
        sys.path.insert(0, str(interpreter))
    import pipeline_interpreter_commands as cmds

    assert cmds.cmd_live("AAA AAA260918P00100000 put") is None
    out = capsys.readouterr().out
    assert "[RETIRED]" in out
    assert "cannot call a market-data provider" in out

    assert cmds.cmd_morning("anything.csv") is None
    out = capsys.readouterr().out
    assert "[RETIRED]" in out
    assert "second validation authority" in out


def test_a3_11c_retired_provider_modules_are_not_imported_by_production() -> None:
    """live_market_reader / alternative_contract_selector unreachable."""
    interpreter = REPO / "pipeline_interpreter"
    if str(interpreter) not in sys.path:
        sys.path.insert(0, str(interpreter))
    import pipeline_interpreter_commands as cmds  # noqa: F401

    assert "live_market_reader" not in sys.modules
    assert "alternative_contract_selector" not in sys.modules


# =========================================================== A3-12 ==========
# AVS-SD-002 section 12 population identity:
#   input_count == processed + excluded + deferred + exception_count
# is an EQUALITY.  ThesisStageResult enforces only an inequality.

def test_a3_12a_population_inflation_is_rejected() -> None:
    from orchestrator.dynamic_thesis import ThesisStageResult
    with pytest.raises(ValueError, match="exceeds its input population"):
        ThesisStageResult(stage="DISCOVERY", status="COMPLETED",
                          input_count=10, output_count=9, deferred_count=2)


def test_a3_12b_population_loss_must_also_be_rejected() -> None:
    """EXPECTED TO FAIL.

    orchestrator/dynamic_thesis.py:52 checks only
    ``output_count + deferred_count > input_count``.  A stage that consumes 10
    tickers and accounts for 3 -- losing 7 with no excluded, deferred or
    exception record -- is accepted, and ``exception_count`` never enters the
    comparison at all.
    """
    from orchestrator.dynamic_thesis import ThesisStageResult
    with pytest.raises(ValueError):
        ThesisStageResult(stage="DISCOVERY", status="COMPLETED",
                          input_count=10, output_count=3, deferred_count=0,
                          exception_count=0)
