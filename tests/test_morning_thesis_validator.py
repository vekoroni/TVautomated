from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

import pytest

pytest.skip(
    "Legacy morning_thesis_validator was retired; production coverage lives in "
    "test_morning_gate_authority.py and test_morning_gate_contract_repair.py.",
    allow_module_level=True,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import resolve_lab_tradeability
from morning_thesis_validator import run_morning_validation, validate_candidate


def _candidate(**overrides):
    base = {
        "run_id": "test_run",
        "ticker": "AAA",
        "lab_verdict": "GO",
        "direction": "CALL",
        "strike": 100,
        "expiry": "2099-01-19",
        "dte": 30,
        "premium_mid": 1.0,
        "target_price": 105,
        "invalidation_price": 95,
        "state_transition_label": "BALANCE_TO_UPSIDE_EXPANSION",
        "priority_score": 90,
        "rr_predicted": 2.0,
        "ev_predicted": 0.2,
        "win_prob_predicted": 0.6,
    }
    base.update(overrides)
    return base


def _live(**overrides):
    base = {
        "live_price": 101,
        "live_vwap": 100,
        "live_orb_high": 100.5,
        "live_orb_low": 99.5,
        "live_bid": 100.95,
        "live_ask": 101.05,
        "live_mid": 101,
        "live_contract_bid": 1.0,
        "live_contract_ask": 1.06,
        "live_contract_mid": 1.03,
        "live_contract_volume": 100,
        "live_contract_open_interest": 500,
        "live_data_timestamp_utc": "2099-01-01T14:45:00Z",
    }
    base.update(overrides)
    return base


def test_core_validation_states() -> None:
    call_go = validate_candidate(_candidate(), _live(), pipeline_mode="EOD")
    assert call_go["live_validation_state"] == "CONFIRMED"
    assert call_go["morning_execution_permission"] == "GO"
    assert call_go["morning_execution_route"] == "GO_NOW"
    assert call_go["execution_permission"] == "GO"

    call_block = validate_candidate(
        _candidate(),
        _live(live_price=94, live_vwap=96, live_orb_high=97, live_orb_low=95, live_mid=94),
        pipeline_mode="EOD",
    )
    assert call_block["execution_permission"] == "BLOCKED"
    assert "invalidation" in call_block["rejection_reason"].lower()

    put_go = validate_candidate(
        _candidate(direction="PUT", target_price=95, invalidation_price=102, state_transition_label="BALANCE_TO_DOWNSIDE_EXPANSION"),
        _live(live_price=99, live_vwap=100, live_orb_high=100.5, live_orb_low=99.5, live_mid=99),
        pipeline_mode="EOD",
    )
    assert put_go["execution_permission"] == "GO"

    put_block = validate_candidate(
        _candidate(direction="PUT", target_price=95, invalidation_price=102, state_transition_label="BALANCE_TO_DOWNSIDE_EXPANSION"),
        _live(live_price=103, live_vwap=100, live_orb_high=102, live_orb_low=99, live_mid=103),
        pipeline_mode="EOD",
    )
    assert put_block["execution_permission"] == "BLOCKED"

    missing_live = validate_candidate(_candidate(), {}, pipeline_mode="EOD")
    assert missing_live["live_validation_state"] == "NO_LIVE_DATA"
    assert missing_live["morning_execution_permission"] == "WAIT"
    assert missing_live["morning_execution_route"] == "WAIT"
    assert missing_live["execution_permission"] == "WAIT"

    stale = validate_candidate(_candidate(), _live(live_data_timestamp_utc="2000-01-01T00:00:00Z"), pipeline_mode="EOD")
    assert stale["live_validation_state"] == "STALE"
    assert stale["execution_permission"] == "WAIT"

    options_research_baton = validate_candidate(
        _candidate(execution_permission="NONE_OPTIONS_RESEARCH_ONLY"),
        _live(),
        pipeline_mode="EOD",
    )
    assert options_research_baton["options_research_permission"] == "NONE_OPTIONS_RESEARCH_ONLY"
    assert options_research_baton["morning_execution_permission"] == "GO"
    assert options_research_baton["execution_permission"] == "GO"


def test_liquidity_and_upgrade_downgrade_rules() -> None:
    wide = validate_candidate(
        _candidate(),
        _live(live_contract_bid=1.0, live_contract_ask=1.3, live_contract_mid=1.15),
        pipeline_mode="EOD",
    )
    assert wide["execution_permission"] == "CONTRACT_REPAIR"
    assert wide["spread_confirmed"] == "FALSE"
    assert wide["contract_tradability_state"] == "REPAIR_REQUIRED"

    caution = validate_candidate(
        _candidate(),
        _live(live_contract_bid=1.0, live_contract_ask=1.12, live_contract_mid=1.06),
        pipeline_mode="EOD",
    )
    assert caution["execution_permission"] == "GO_LIMIT"
    assert caution["spread_confirmed"] == "CAUTION"

    armed_to_go = validate_candidate(_candidate(lab_verdict="ARMED"), _live(), pipeline_mode="EOD")
    assert armed_to_go["execution_permission"] == "GO"

    unclear = validate_candidate(
        _candidate(),
        _live(live_price=100.1, live_vwap=100, live_orb_high=101, live_orb_low=99, live_mid=100.1),
        pipeline_mode="EOD",
    )
    assert unclear["execution_permission"] in {"WAIT", "ARMED", "PROBE"}

    blocked_stays_blocked = validate_candidate(_candidate(lab_verdict="BLOCKED"), _live(), pipeline_mode="EOD")
    assert blocked_stays_blocked["execution_permission"] == "BLOCKED"

    high_entropy = validate_candidate(
        _candidate(state_transition_label="HIGH_ENTROPY_CHOP"),
        _live(live_price=100.2, live_vwap=100, live_orb_high=101, live_orb_low=99, live_mid=100.2),
        pipeline_mode="EOD",
    )
    assert high_entropy["execution_permission"] != "GO"


def test_horizon_aware_routing_and_contract_side_repair() -> None:
    medium_no_transition = validate_candidate(
        _candidate(state_transition_label="NO_TRANSITION_EDGE", horizon_bucket="6_10D"),
        _live(),
        pipeline_mode="MORNING_VALIDATION",
    )
    assert medium_no_transition["morning_execution_permission"] == "GO_LIMIT"
    assert medium_no_transition["morning_execution_route"] == "GO_LIMIT"
    assert medium_no_transition["execution_permission"] == "GO_LIMIT"
    assert medium_no_transition["morning_execution_lane"] == "GO_LIMIT"
    assert medium_no_transition["eod_thesis_confirmed"] == "TRUE"

    short_no_transition = validate_candidate(
        _candidate(state_transition_label="NO_TRANSITION_EDGE", horizon_bucket="1_5D"),
        _live(),
        pipeline_mode="MORNING_VALIDATION",
    )
    assert short_no_transition["execution_permission"] == "ARMED"

    side_conflict = validate_candidate(
        _candidate(
            primary_direction="PUT",
            direction="PUT",
            selected_contract_side="CALL",
            target_price=95,
            invalidation_price=102,
            state_transition_label="BALANCE_TO_DOWNSIDE_EXPANSION",
        ),
        _live(live_price=99, live_vwap=100, live_orb_high=100.5, live_orb_low=99.5, live_mid=99),
        pipeline_mode="MORNING_VALIDATION",
    )
    assert side_conflict["execution_permission"] == "CONTRACT_REPAIR"
    assert side_conflict["direction_alignment_status"] == "CONTRACT_SIDE_CONFLICT"


def test_outputs_and_lab_resolver() -> None:
    blocked = resolve_lab_tradeability(
        {
            "ticker": "AAA",
            "mv__morning_execution_permission": "BLOCKED",
            "mv__execution_permission": "BLOCKED",
            "mv__live_validation_state": "REJECTED",
            "strike": 100,
            "expiry": "2099-01-19",
            "premium_mid": 1.0,
            "rr_options": 1.5,
            "ev2_decision_hint": "MODERATE",
        },
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert blocked["lab_verdict"] == "BLOCKED"
    assert blocked["lab_tradeable"] is False
    assert blocked["morning_lab_alignment_status"] == "ALIGNED_BLOCKED"

    go_limit = resolve_lab_tradeability(
        {
            "ticker": "AAA",
            "mv__morning_execution_permission": "GO_LIMIT",
            "mv__execution_permission": "GO_LIMIT",
            "mv__live_validation_state": "CONFIRMED",
            "strike": 100,
            "expiry": "2099-01-19",
            "premium_mid": 1.0,
            "rr_options": 1.5,
            "ev2_decision_hint": "MODERATE",
        },
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert go_limit["lab_verdict"] == "GO_LIMIT"
    assert go_limit["lab_tradeable"] is True
    assert go_limit["morning_lab_alignment_status"] == "ALIGNED"

    wait = resolve_lab_tradeability(
        {
            "ticker": "AAA",
            "lab_verdict": "GO",
            "mv__morning_execution_permission": "WAIT",
            "mv__execution_permission": "WAIT",
            "mv__live_validation_state": "WAIT_RETEST",
            "strike": 100,
            "expiry": "2099-01-19",
            "premium_mid": 1.0,
            "rr_options": 1.5,
            "ev2_decision_hint": "MODERATE",
        },
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert wait["lab_verdict"] == "WAIT"
    assert wait["lab_tradeable"] is False
    assert wait["morning_lab_alignment_status"] == "ALIGNED"

    with tempfile.TemporaryDirectory() as td:
        runs = Path(td)
        run_id = "20990101_093000"
        book = runs / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv"
        book.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            _candidate(run_id=run_id, ticker="AAA", lab_verdict="GO"),
            _candidate(run_id=run_id, ticker="BBB", lab_verdict="ARMED"),
            _candidate(run_id=run_id, ticker="CCC", lab_verdict="BLOCKED"),
        ]
        with book.open("w", encoding="utf-8", newline="") as fh:
            fields = sorted({k for r in rows for k in r})
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        out = runs / run_id / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
        result = run_morning_validation(
            run_id=run_id,
            output_path=out,
            runs_dir=runs,
            max_signals=10,
            live_mode=False,
            paper_mode=True,
            pipeline_mode="EOD",
        )
        packet = out.parent / f"morning_validation_packet_{run_id}.json"
        assert out.exists()
        assert packet.exists()
        assert len(result) == 2
        payload = json.loads(packet.read_text(encoding="utf-8"))
        assert payload["summary"]["validated_count"] == 2
        with out.open("r", encoding="utf-8-sig", newline="") as fh:
            csv_rows = list(csv.DictReader(fh))
        assert all(r.get("live_validation_state") for r in csv_rows)
        assert all(r.get("morning_execution_permission") for r in csv_rows)
        assert all(r.get("morning_execution_route") for r in csv_rows)
        assert all(r.get("execution_permission") for r in csv_rows)


if __name__ == "__main__":
    test_core_validation_states()
    test_liquidity_and_upgrade_downgrade_rules()
    test_horizon_aware_routing_and_contract_side_repair()
    test_outputs_and_lab_resolver()
    print("morning thesis validator tests passed: 3 groups")
