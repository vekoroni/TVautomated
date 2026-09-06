from types import SimpleNamespace
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import execution_intelligence_runner as eil
from position_sizing_engine import compute_position_size


def _ev():
    return SimpleNamespace(
        ev_conf_adj=0.025,
        ev_status="PASS_SMALL",
        primary_reason="TEST",
        contract_efficiency_flag=False,
    )


def _candidate_row(signal="CURRENT_EDGE"):
    return {
        "ticker": "ABT",
        "signal_type": signal,
        "momentum_tier": "TIER_2_ACTIVE",
        "eil_v3_verdict": "EXECUTE",
        "options_verdict": "EXECUTE",
        "options_score": 72.0,
        "rr_options": 2.2,
        "contract_premium": 1.75,
        "contract_oi": 850,
        "contract_volume": 140,
        "contract_spread_pct": 0.08,
        "trigger_quality": "STRONG",
        "catalyst_trade_class": "",
        "direction_conflict": "",
    }


def test_runner_declares_pse_retired():
    assert eil._PSE_AVAILABLE is False
    assert eil.PSE_RETIRED_POLICY == "PSE_IGNORED_MANUAL_SIZING"


def test_retired_overlay_zeroes_size_without_blocking_candidate():
    row = eil._apply_retired_sizing_overlay(_candidate_row(), _ev())
    row = eil._apply_signal_authority_policy(row)
    row = eil._finalize_execution_authority(row)

    assert row["sizing_policy"] == eil.PSE_RETIRED_POLICY
    assert row["pse_engine_state"] == "IGNORED_MANUAL_SIZING"
    assert row["pse_trade_veto"] is False
    assert row["manual_sizing_required"] is True
    assert row["candidate_size_status"] == "MANUAL_SIZING_REQUIRED"
    assert row["pse_final_size"] == 0.0
    assert row["fd_size"] == 0.0
    assert row["capital_permission"] == "EOD_CANDIDATE_ONLY"
    assert row["eod_candidate_authorized"] is True
    assert row["execution_authorized"] is False
    assert row["effective_execution_verdict"] == "MORNING_VALIDATION_REQUIRED"


def test_options_research_block_overrides_legacy_execute_candidate():
    row = _candidate_row()
    row.update(
        {
            "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY",
            "final_route": "OPTIONS_BLOCKED",
            "options_research_score": 88.0,
            "hard_vetoes": "SPREAD_GT_15PCT",
            "missing_data": "",
        }
    )

    row = eil._apply_retired_sizing_overlay(row, _ev())
    row = eil._apply_signal_authority_policy(row)
    row = eil._finalize_execution_authority(row)

    assert row["capital_permission"] == "NO"
    assert row["eod_candidate_authorized"] is False
    assert row["effective_execution_verdict"] == "OPTIONS_REPAIR_REQUIRED"
    assert "OPTIONS_RESEARCH_BLOCKED" in row["signal_authority_reason"]
    assert "SPREAD_GT_15PCT" in row["signal_authority_reason"]


def test_options_research_go_route_can_promote_without_legacy_options_verdict():
    row = _candidate_row()
    row.update(
        {
            "options_verdict": "BLOCKED",
            "options_score": 0.0,
            "execution_permission": "NONE_OPTIONS_RESEARCH_ONLY",
            "final_route": "OPTIONS_GO_REVIEW",
            "options_research_score": 82.0,
            "hard_vetoes": "",
            "missing_data": "",
            "trigger_state": "TRIGGER_CONFIRMED",
        }
    )

    row = eil._apply_retired_sizing_overlay(row, _ev())
    row = eil._apply_signal_authority_policy(row)
    row = eil._finalize_execution_authority(row)

    assert row["capital_permission"] == "EOD_CANDIDATE_ONLY"
    assert row["eod_candidate_authorized"] is True
    assert "OPTIONS_RESEARCH_OPTIONS_GO_REVIEW" in row["signal_authority_reason"]


def test_data_missing_remains_not_authorized():
    row = eil._apply_retired_sizing_overlay(_candidate_row("DATA_MISSING"), _ev())
    row = eil._apply_signal_authority_policy(row)
    row = eil._finalize_execution_authority(row)

    assert row["capital_permission"] == "NO"
    assert row["execution_authorized"] is False
    assert row["eod_candidate_authorized"] is False
    assert row["effective_execution_verdict"] == "DATA_REPAIR_REQUIRED"


def test_directional_candidate_without_invalidation_is_not_authorized():
    row = _candidate_row()
    row.update({"governed_direction": "PUT", "invalidation_state": "MISSING"})
    row = eil._apply_retired_sizing_overlay(row, _ev())
    row = eil._apply_signal_authority_policy(row)
    row = eil._finalize_execution_authority(row)
    assert row["capital_permission"] == "NO"
    assert row["eod_candidate_authorized"] is False
    assert row["effective_execution_verdict"] == "DATA_REPAIR_REQUIRED"
    assert row["execution_authority_reason"] == "MISSING_GOVERNED_INVALIDATION"


def test_directional_candidate_with_governed_invalidation_remains_eligible():
    row = _candidate_row()
    row.update({
        "governed_direction": "CALL", "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
    })
    row = eil._apply_retired_sizing_overlay(row, _ev())
    row = eil._apply_signal_authority_policy(row)
    row = eil._finalize_execution_authority(row)
    assert row["capital_permission"] == "EOD_CANDIDATE_ONLY"
    assert row["eod_candidate_authorized"] is True


def test_direct_pse_call_is_retired_by_default():
    result = compute_position_size(_candidate_row(), _ev())

    assert result.pse_final_size == 0.0
    assert result.pse_execution_mode == "SIZING_IGNORED_REVIEW"
    assert result.pse_block_reason == ""
    assert result.pse_size_breakdown == "PSE_IGNORED_MANUAL_SIZING"


def test_dataframe_defang_cannot_reauthorize_data_missing():
    frame = pd.DataFrame(
        [{
            "ticker": "MISS",
            "signal_type": "DATA_MISSING",
            "momentum_tier": "DATA_MISSING",
            "pse_execution_mode": "FATAL_BLOCK",
            "pse_block_reason": "CAMPAIGN_OR_EXECUTION_INVALID",
            "pse_final_size": 0.0,
            "fd_size": 0.0,
        }]
    )

    row = eil._defang_invalid_campaign_fatal_blocks(frame).iloc[0]

    assert row["capital_permission"] == "NO"
    assert row["eod_candidate_permission"] == "NO"
    assert bool(row["eod_candidate_authorized"]) is False
    assert row["effective_execution_verdict"] == "DATA_REPAIR_REQUIRED"


def test_dataframe_defang_keeps_options_blocked_fail_closed():
    frame = pd.DataFrame(
        [{
            "ticker": "BLOCK",
            "signal_type": "CURRENT_EDGE",
            "momentum_tier": "TIER_2_ACTIVE",
            "pse_execution_mode": "FATAL_BLOCK",
            "pse_block_reason": "CAMPAIGN_OR_EXECUTION_INVALID",
            "pse_final_size": 0.0,
            "fd_size": 0.0,
            "final_route": "OPTIONS_BLOCKED",
            "hard_vetoes": "SPREAD_GT_15PCT",
        }]
    )

    row = eil._defang_invalid_campaign_fatal_blocks(frame).iloc[0]

    assert row["capital_permission"] == "NO"
    assert row["eod_candidate_permission"] == "CONTRACT_REPAIR_REQUIRED"
    assert bool(row["eod_candidate_authorized"]) is False
    assert row["effective_execution_verdict"] == "OPTIONS_REPAIR_REQUIRED"
