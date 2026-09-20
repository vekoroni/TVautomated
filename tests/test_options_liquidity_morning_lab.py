from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.direction_governance import resolve_governed_direction
from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row


RUN_ID = "20990102_083000"
ORIGINAL = "O:AAA990119C00100000"
REPLACEMENT = "O:AAA990119C00105000"


DECISION_CRITICAL_LIQUIDITY_FIELDS = {
    "thesis_id",
    "thesis_state",
    "liquidity_state",
    "morning_transition_state",
    "recovery_disposition",
    "executable_now",
    "moneyness_state",
    "delta_band",
    "minimum_required_dte",
    "dte_buffer_sessions",
    "atm_distance_sigma",
    "remaining_runway_pct",
    "remaining_runway_state",
    "maturation_state_1d",
    "maturation_state_2d",
    "maturation_state_3d",
    "maturation_score_1d",
    "maturation_score_2d",
    "maturation_score_3d",
    "maturation_score_is_probability",
    "maturation_execution_authority",
    "previous_contract_symbol",
    "contract_changed",
    "contract_selection_reason",
    "quote_as_of",
    "quote_freshness",
    "option_chain_dataset_id",
    "selected_quote_dataset_id",
    "liquidity_persistence_status",
    "morning_liquidity_persistence_status",
}


def _direction_record() -> dict:
    return resolve_governed_direction(
        ticker="AAA",
        run_id=RUN_ID,
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2099-01-02T08:30:00+00:00",
    )


def _signal(**overrides) -> dict:
    row = {
        "ticker": "AAA",
        "canonical_direction": "CALL",
        "lab_verdict": "WAIT",
        "lab_tradeable": False,
        "morning_lab_alignment_status": "EXACT_MATCH",
        "lifecycle_contract_version": "options-liquidity-lifecycle-v1",
        "thesis_state": "ACTIVE",
        "remaining_runway_state": "THESIS_ACTIVE",
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "TEST_GOVERNED_THESIS",
        **_direction_record(),
    }
    row.update(overrides)
    return row


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_liquidity_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_governed_book_schema_contains_decision_critical_liquidity_fields() -> None:
    """The Lab baton must not lose lifecycle fields produced upstream."""
    assert DECISION_CRITICAL_LIQUIDITY_FIELDS.issubset(set(FINAL_BOOK_FIELDS))


def test_liquidity_pending_survives_governed_lab_materialisation() -> None:
    row = opportunity_book_row(
        _signal(
            thesis_id="THESIS-AAA-CALL-001",
            thesis_state="ACTIVE",
            liquidity_state="LIQUIDITY_PENDING",
            morning_transition_state="LIQUIDITY_STILL_PENDING",
            recovery_disposition="MONITOR",
            executable_now=False,
            moneyness_state="OTM",
            delta_band="DEVELOPING_OTM",
            minimum_required_dte=15,
            dte_buffer_sessions=7,
            atm_distance_sigma=0.72,
            remaining_runway_pct=11.5,
            remaining_runway_state="THESIS_ACTIVE",
            maturation_state_1d="DEVELOPING",
            maturation_state_2d="LIKELY",
            maturation_state_3d="LIKELY",
            maturation_score_1d=0.42,
            maturation_score_2d=0.68,
            maturation_score_3d=0.74,
            maturation_score_is_probability=False,
            maturation_execution_authority=False,
            quote_as_of="2099-01-02T08:29:59+00:00",
            quote_freshness="FRESH",
        ),
        RUN_ID,
        1,
    )

    assert row["thesis_state"] == "ACTIVE"
    assert row["liquidity_state"] == "LIQUIDITY_PENDING"
    assert row["morning_transition_state"] == "LIQUIDITY_STILL_PENDING"
    assert row["executable_now"] is False
    assert row["maturation_score_2d"] == 0.68
    assert row["maturation_score_is_probability"] is False
    assert row["maturation_execution_authority"] is False
    assert row["lab_tradeable"] is False


def test_replacement_contract_identity_and_recomputed_economics_reach_lab() -> None:
    """A replacement is a new economic object; only its exact evaluation may pass."""
    row = opportunity_book_row(
        _signal(
            lab_verdict="GO_LIMIT",
            lab_tradeable=True,
            final_action="BUY_SMALL",
            instrument="LONG_CALL",
            contract_symbol=REPLACEMENT,
            morning_selected_contract_symbol=REPLACEMENT,
            previous_contract_symbol=ORIGINAL,
            contract_symbol_original=ORIGINAL,
            contract_repair_resolved_at_open="TRUE",
            contract_changed=True,
            contract_selection_reason="NEIGHBOURING_STRIKE_EXECUTABLE",
            selected_contract_economics_ready=True,
            rr_recompute_status="COMPLETE",
            monetisability_status="COMPLETE",
            monetisability_state="MONETISABLE",
            monetisability_contract_symbol=REPLACEMENT,
            morning_transition_state="EXECUTABLE_NOW",
            liquidity_state="EXECUTABLE_NOW",
            executable_now=True,
            contract_bid=2.40,
            contract_ask=2.50,
            premium_mid=2.45,
            strike=105,
            expiry="2099-01-19",
            dte=17,
        ),
        RUN_ID,
        1,
    )

    assert row["contract_symbol"] == REPLACEMENT
    assert row["monetisability_contract_symbol"] == REPLACEMENT
    assert row["selected_contract_economics_ready"] is True
    assert row["economics_comparable"] is True
    assert row["previous_contract_symbol"] == ORIGINAL
    assert row["contract_changed"] is True
    assert row["morning_transition_state"] == "EXECUTABLE_NOW"
    assert row["lab_tradeable"] is True


def test_contract_reprice_required_is_never_tradeable() -> None:
    row = opportunity_book_row(
        _signal(
            lab_verdict="GO_LIMIT",
            lab_tradeable=True,
            final_action="BUY_SMALL",
            instrument="LONG_CALL",
            contract_symbol=REPLACEMENT,
            morning_selected_contract_symbol=REPLACEMENT,
            previous_contract_symbol=ORIGINAL,
            contract_symbol_original=ORIGINAL,
            contract_repair_resolved_at_open="TRUE",
            contract_changed=True,
            selected_contract_economics_ready=False,
            economics_recompute_required="TRUE",
            morning_transition_state="CONTRACT_REPRICE_REQUIRED",
            liquidity_state="EXECUTABLE_NOW",
            executable_now=True,
            strike=105,
            expiry="2099-01-19",
            dte=17,
        ),
        RUN_ID,
        1,
    )

    assert row["morning_transition_state"] == "CONTRACT_REPRICE_REQUIRED"
    assert row["economics_comparable"] is False
    assert row["lab_tradeable"] is False
    assert row["lab_verdict"] == "CONTRACT_REPAIR"


def test_lab_compact_projection_exposes_liquidity_lifecycle_without_inference() -> None:
    lab = _load_lab_module()
    source = {
        "lab_schema_version": "lab_signal_book_v2",
        "ticker": "AAA",
        "thesis_state": "ACTIVE",
        "liquidity_state": "LIQUIDITY_PENDING",
        "morning_transition_state": "WAIT_FOR_PULLBACK",
        "executable_now": False,
        "moneyness_state": "ATM",
        "delta_band": "CORE_EXECUTION",
        "atm_distance_sigma": 0.08,
        "remaining_runway_pct": 6.4,
        "remaining_runway_state": "GAP_CONFIRMATION_EXTENDED",
        "maturation_score_2d": 0.71,
        "maturation_score_is_probability": False,
        "maturation_execution_authority": False,
        "quote_as_of": "2099-01-02T08:29:59+00:00",
        "quote_freshness": "FRESH",
        "lab_tradeable": False,
    }

    projected = lab._governed_ui_projection(source)
    compact = lab._compact_lab_signal(projected)

    for field in DECISION_CRITICAL_LIQUIDITY_FIELDS - {
        "thesis_id", "recovery_disposition", "minimum_required_dte",
        "dte_buffer_sessions", "maturation_state_1d", "maturation_state_2d",
        "maturation_state_3d", "maturation_score_1d", "maturation_score_3d",
        "previous_contract_symbol", "contract_changed", "contract_selection_reason",
    }:
        if field in source:
            assert compact[field] == source[field]
    assert compact["morning_transition_state"] == "WAIT_FOR_PULLBACK"
    assert compact["lab_tradeable"] is False


def test_intelligence_lab_has_trader_facing_liquidity_labels() -> None:
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    for label in (
        "Liquidity State",
        "Morning Post-Open Contract State",
        "Distance to ATM",
        "Remaining Runway",
        "Quote Freshness",
        "Canonical Quote Lineage",
        "Contract Changed",
    ):
        assert label in html
    assert "monitoring estimate only — not a probability and cannot authorize entry" in html
