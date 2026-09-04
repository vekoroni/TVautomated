"""Agent A OLM fix validation runner.

Executes fixture-driven scenarios directly against the CURRENT production
code paths (and, for TC-07, also the pre-change backup) to independently
verify claims in OLM_BLOCKER_REMEDIATION_IMPLEMENTATION_20260829.md against
the design in OLM_BLOCKER_REMEDIATION_SOLUTION_DESIGN_20260829.md.

Does not modify any production file. Writes only to this directory.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from contracts.direction_governance import resolve_governed_direction  # noqa: E402
import execution_gate  # noqa: E402  (current, post-fix module)
from contracts.options_liquidity_execution_guard import (  # noqa: E402
    evaluate_olm_execution_guard,
)

RESULTS = {}


def record(tc, **kwargs):
    RESULTS[tc] = kwargs
    print(f"\n===== {tc} =====")
    for k, v in kwargs.items():
        print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
# Load the PRE-CHANGE backup execution_gate.py as a separately-named module
# so we can run the true "before" reproduction against the exact same fixture.
# ---------------------------------------------------------------------------
BACKUP_PATH = ROOT / "backups" / "olm_blocker_remediation_prechange_20260829_2035" / "execution_gate.py"
spec = importlib.util.spec_from_file_location("execution_gate_BEFORE_FIX", str(BACKUP_PATH))
execution_gate_before = importlib.util.module_from_spec(spec)
spec.loader.exec_module(execution_gate_before)


def gdr(ticker, direction, run_id="TESTA_20260829"):
    return resolve_governed_direction(
        ticker=ticker,
        run_id=run_id,
        discovery_direction=direction,
        governed_direction=direction,
        governed_basis=f"test={direction}",
        row={},
        decided_at_utc="2026-08-29T13:30:00+00:00",
    )


def base_row(ticker, direction, **overrides):
    """A coherent, fully-populated governed-direction row with an
    EXECUTABLE_NOW OLM lifecycle attached (the 'everything clean' baseline)."""
    contract_symbol = f"O:{ticker}260918{'C' if direction == 'CALL' else 'P'}00104000"
    row = {
        **gdr(ticker, direction),
        "ticker": ticker,
        "pipeline_mode": "MORNING_VALIDATION",
        "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": contract_symbol,
        "morning_selected_contract_symbol": contract_symbol,
        "contract_symbol": contract_symbol,
        "selected_contract_side": direction,
        "signal_price": 100.0,
        "strike": 104.0,
        "expiry": "2026-09-18",
        "dte": 20,
        "live_contract_bid": 1.85,
        "live_contract_ask": 1.95,
        "live_contract_mid": 1.90,
        "live_contract_delta": 0.44 if direction == "CALL" else -0.44,
        "live_contract_iv": 0.35,
        "live_iv_rank": 50,
        "contract_bid": 1.85,
        "contract_ask": 1.95,
        "contract_mid": 1.90,
        "contract_delta": 0.44 if direction == "CALL" else -0.44,
        "lifecycle_contract_version": "OPTIONS-LIQUIDITY-LIFECYCLE-V1",
        "thesis_state": "ACTIVE",
        "liquidity_state": "EXECUTABLE_NOW",
        "morning_transition_state": "EXECUTABLE_NOW",
        "remaining_runway_state": "THESIS_ACTIVE",
        "executable_now": True,
        "maturation_execution_authority": False,
    }
    row.update(overrides)
    return row


# ===========================================================================
# TEST 1: TC-07 exact reproduction (before / after)
# ===========================================================================
def test_tc07():
    row_before = {
        **gdr("TC07", "CALL", run_id="TEST_OLM_TC07_20260829"),
        "ticker": "TC07",
        "morning_execution_permission": "GO",
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": "O:TC07260918C00104000",
        "morning_selected_contract_symbol": "O:TC07260918C00104000",
        "contract_symbol": "O:TC07260918C00104000",
        "signal_price": 94.0,
        "live_contract_bid": 1.85, "live_contract_ask": 1.95,
        "live_contract_delta": 0.44, "live_contract_iv": 0.35,
        "liquidity_state": "EXECUTABLE_NOW",
        "morning_transition_state": "THESIS_INVALIDATED",
        "executable_now": True,
    }
    row_after = copy.deepcopy(row_before)

    before = execution_gate_before.execution_gate(row_before)
    after_default = execution_gate.execution_gate(copy.deepcopy(row_after))
    after_prod = execution_gate.execution_gate(copy.deepcopy(row_after), require_olm=True)

    record(
        "TC-07",
        before_final_action=before.get("final_action"),
        before_gate_reason=before.get("gate_reason"),
        after_default_final_action=after_default.get("final_action"),
        after_default_gate_reason=after_default.get("gate_reason"),
        after_prod_final_action=after_prod.get("final_action"),
        after_prod_gate_reason=after_prod.get("gate_reason"),
        after_prod_olm_guard_disposition=after_prod.get("olm_guard_disposition"),
        after_prod_olm_guard_pass=after_prod.get("olm_guard_pass"),
    )
    return before, after_default, after_prod


# ===========================================================================
# TEST 2: full §11.2 unit-test matrix, CALL and PUT
# ===========================================================================
MATRIX = [
    ("THESIS_INVALIDATED", "BLOCK"),
    ("MOVE_ALREADY_REALIZED", "BLOCK"),
    ("CONTRACT_REPRICE_REQUIRED", "CONTRACT_REPAIR"),
    ("WAIT_FOR_PULLBACK", "MANUAL_REVIEW"),
    ("GAP_CONFIRMATION_EXTENDED", "MANUAL_REVIEW"),
    ("LIQUIDITY_STILL_PENDING", "MANUAL_REVIEW"),
    ("EOD_PENDING_MORNING_REQUOTE", "MANUAL_REVIEW"),
    ("EXECUTABLE_NOW", "BUY_NOW"),
]


def test_matrix():
    out = {}
    for direction in ("CALL", "PUT"):
        for transition, expected in MATRIX:
            row = base_row(f"MX{direction[0]}", direction, morning_transition_state=transition)
            # For terminal/defer states, thesis/runway/liquidity fields would
            # realistically also change; test the guard's own precedence by
            # varying transition alone (baseline) AND with fully-coherent
            # companion fields, since design table keys off morning_transition_state.
            result = execution_gate.execution_gate(row, require_olm=True)
            key = f"{direction}:{transition}"
            out[key] = {
                "expected": expected,
                "actual_final_action": result.get("final_action"),
                "actual_gate_reason": result.get("gate_reason"),
                "olm_guard_pass": result.get("olm_guard_pass"),
                "capital_zero": result.get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
                "pass": result.get("final_action") == expected,
            }
    record("MATRIX_11_2", **out)
    return out


def test_gap_confirmation_with_runway():
    results = {}
    for direction in ("CALL", "PUT"):
        # Coherent but fails an existing check: force spread > 15% (SPREAD_MAX)
        row_fail = base_row(
            f"GCRF{direction[0]}", direction,
            morning_transition_state="GAP_CONFIRMATION_WITH_RUNWAY",
            live_contract_bid=1.00, live_contract_ask=1.40,  # 28.5% spread -> COST_DESTRUCTION
            contract_bid=1.00, contract_ask=1.40,
        )
        r_fail = execution_gate.execution_gate(row_fail, require_olm=True)
        # Coherent and clean -> should reach BUY_NOW
        row_ok = base_row(
            f"GCRO{direction[0]}", direction,
            morning_transition_state="GAP_CONFIRMATION_WITH_RUNWAY",
        )
        r_ok = execution_gate.execution_gate(row_ok, require_olm=True)
        results[direction] = {
            "wide_spread_final_action": r_fail.get("final_action"),
            "wide_spread_capital_granted": r_fail.get("final_action") in ("BUY_NOW", "BUY_SMALL"),
            "wide_spread_gate_reason": r_fail.get("gate_reason"),
            "olm_disposition_on_fail_case": r_fail.get("olm_guard_disposition"),
            "clean_final_action": r_ok.get("final_action"),
            "clean_reaches_buy_now": r_ok.get("final_action") == "BUY_NOW",
        }
    record("GAP_CONFIRMATION_WITH_RUNWAY_CONTINUE_NOT_CAPITAL", **results)
    return results


def test_executable_now_still_reaches_buy_now():
    results = {}
    for direction in ("CALL", "PUT"):
        row = base_row(f"EXN{direction[0]}", direction)
        r = execution_gate.execution_gate(row, require_olm=True)
        results[direction] = {
            "final_action": r.get("final_action"),
            "pass": r.get("final_action") == "BUY_NOW",
        }
    record("EXECUTABLE_NOW_REACHES_BUY_NOW", **results)
    return results


def test_executable_now_false():
    results = {}
    for direction in ("CALL", "PUT"):
        row = base_row(f"ENF{direction[0]}", direction, executable_now=False)
        r = execution_gate.execution_gate(row, require_olm=True)
        results[direction] = {
            "final_action": r.get("final_action"),
            "capital_zero": r.get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
            "gate_reason": r.get("gate_reason"),
        }
    record("EXECUTABLE_NOW_FALSE_NO_CAPITAL", **results)
    return results


def test_contradictory_combination():
    results = {}
    for direction in ("CALL", "PUT"):
        row_thesis = base_row(f"CTA{direction[0]}", direction, thesis_state="DATA_INCOMPLETE")
        r_thesis = execution_gate.execution_gate(row_thesis, require_olm=True)
        row_liq = base_row(f"CTB{direction[0]}", direction, liquidity_state="LIQUIDITY_PENDING")
        r_liq = execution_gate.execution_gate(row_liq, require_olm=True)
        results[direction] = {
            "non_active_thesis_final_action": r_thesis.get("final_action"),
            "non_active_thesis_capital_zero": r_thesis.get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
            "non_executable_liquidity_final_action": r_liq.get("final_action"),
            "non_executable_liquidity_capital_zero": r_liq.get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
        }
    record("CONTRADICTORY_COMBINATION_NO_CAPITAL", **results)
    return results


def test_unknown_missing_state_production_required():
    results = {}
    for direction in ("CALL", "PUT"):
        row = base_row(f"UNK{direction[0]}", direction, morning_transition_state="")
        rows, summary = execution_gate.run_execution_gate([row], "TESTA_UNKNOWN", ROOT / "audit" / "olm_fix_test" / "_tmp_out")
        results[direction] = {
            "final_action": rows[0].get("final_action"),
            "gate_reason": rows[0].get("gate_reason"),
            "capital_zero": rows[0].get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
            "olm_guard_disposition_counts": summary.get("olm_guard_disposition_counts"),
        }
        # Also true "missing" (field absent entirely, not empty string)
        row2 = base_row(f"MIS{direction[0]}", direction)
        row2.pop("morning_transition_state", None)
        rows2, summary2 = execution_gate.run_execution_gate([row2], "TESTA_MISSING", ROOT / "audit" / "olm_fix_test" / "_tmp_out")
        results[direction + "_field_absent"] = {
            "final_action": rows2[0].get("final_action"),
            "gate_reason": rows2[0].get("gate_reason"),
            "capital_zero": rows2[0].get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
        }
    record("UNKNOWN_MISSING_STATE_PRODUCTION_REQUIRED", **results)
    return results


def test_legacy_fixture_compatibility():
    results = {}
    for direction in ("CALL", "PUT"):
        legacy = base_row(f"LEG{direction[0]}", direction)
        for field in (
            "lifecycle_contract_version", "thesis_state", "liquidity_state",
            "morning_transition_state", "remaining_runway_state", "executable_now",
            "maturation_execution_authority",
        ):
            legacy.pop(field, None)
        compat = execution_gate.execution_gate(copy.deepcopy(legacy))
        rows, summary = execution_gate.run_execution_gate(
            [copy.deepcopy(legacy)], "TESTA_LEGACY", ROOT / "audit" / "olm_fix_test" / "_tmp_out"
        )
        results[direction] = {
            "compat_mode_final_action": compat.get("final_action"),
            "compat_mode_olm_guard_disposition": compat.get("olm_guard_disposition"),
            "compat_mode_olm_guard_reason": compat.get("olm_guard_reason"),
            "production_batch_final_action": rows[0].get("final_action"),
            "production_batch_gate_reason": rows[0].get("gate_reason"),
            "production_batch_capital_zero": rows[0].get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
        }
    record("LEGACY_FIXTURE_COMPATIBILITY", **results)
    return results


def test_high_maturation_score_never_overrides():
    results = {}
    for direction in ("CALL", "PUT"):
        row_terminal = base_row(
            f"HMA{direction[0]}", direction,
            morning_transition_state="THESIS_INVALIDATED",
            thesis_state="INVALIDATED",
            remaining_runway_state="THESIS_INVALIDATED",
            executable_now=False,
            maturation_score_1d=100.0, maturation_score_2d=100.0, maturation_score_3d=100.0,
            maturation_execution_authority=False,
        )
        r_terminal = execution_gate.execution_gate(row_terminal, require_olm=True)
        row_pending = base_row(
            f"HMB{direction[0]}", direction,
            morning_transition_state="LIQUIDITY_STILL_PENDING",
            maturation_score_1d=100.0, maturation_score_2d=100.0, maturation_score_3d=100.0,
        )
        r_pending = execution_gate.execution_gate(row_pending, require_olm=True)
        # maturation_execution_authority=True itself must be treated as corruption
        row_authority_claim = base_row(
            f"HMC{direction[0]}", direction,
            maturation_execution_authority=True,
        )
        r_authority_claim = execution_gate.execution_gate(row_authority_claim, require_olm=True)
        results[direction] = {
            "high_score_terminal_final_action": r_terminal.get("final_action"),
            "high_score_terminal_capital_zero": r_terminal.get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
            "high_score_pending_final_action": r_pending.get("final_action"),
            "high_score_pending_capital_zero": r_pending.get("final_action") not in ("BUY_NOW", "BUY_SMALL"),
            "maturation_authority_claim_true_final_action": r_authority_claim.get("final_action"),
            "maturation_authority_claim_true_reason": r_authority_claim.get("gate_reason"),
        }
    record("HIGH_MATURATION_SCORE_NEVER_OVERRIDES", **results)
    return results


# ===========================================================================
# TEST 4: §7.2 reason codes — literal attribution
# ===========================================================================
def test_reason_codes():
    design_codes = [
        "OLM_THESIS_INVALIDATED",
        "OLM_MOVE_ALREADY_REALIZED",
        "OLM_CONTRACT_REPRICE_REQUIRED",
        "OLM_WAIT_FOR_PULLBACK",
        "OLM_GAP_CONFIRMATION_EXTENDED",
        "OLM_LIQUIDITY_STILL_PENDING",
        "OLM_MORNING_REQUOTE_REQUIRED",
        "OLM_CONTRACT_INCOHERENT",
        "OLM_STATE_MISSING_OR_UNKNOWN",
    ]
    triggers = {
        "OLM_THESIS_INVALIDATED": dict(morning_transition_state="THESIS_INVALIDATED"),
        "OLM_MOVE_ALREADY_REALIZED": dict(morning_transition_state="MOVE_ALREADY_REALIZED"),
        "OLM_CONTRACT_REPRICE_REQUIRED": dict(morning_transition_state="CONTRACT_REPRICE_REQUIRED"),
        "OLM_WAIT_FOR_PULLBACK": dict(morning_transition_state="WAIT_FOR_PULLBACK"),
        "OLM_GAP_CONFIRMATION_EXTENDED": dict(morning_transition_state="GAP_CONFIRMATION_EXTENDED"),
        "OLM_LIQUIDITY_STILL_PENDING": dict(morning_transition_state="LIQUIDITY_STILL_PENDING"),
        "OLM_MORNING_REQUOTE_REQUIRED (design) / attempt via EOD_PENDING_MORNING_REQUOTE transition": dict(
            morning_transition_state="EOD_PENDING_MORNING_REQUOTE"
        ),
        "OLM_CONTRACT_INCOHERENT (design) / attempt via contradictory executable transition": dict(
            morning_transition_state="EXECUTABLE_NOW", thesis_state="INVALIDATED",
            remaining_runway_state="THESIS_INVALIDATED",
        ),
        "OLM_STATE_MISSING_OR_UNKNOWN (design) / attempt via missing transition, production-required": dict(
            morning_transition_state="",
        ),
    }
    results = {}
    for label, overrides in triggers.items():
        row = base_row("RC", "CALL", **overrides)
        decision = evaluate_olm_execution_guard(row, require_contract=True)
        results[label] = {
            "literal_reason_emitted": decision.reason,
            "disposition": decision.disposition,
        }
    results["_design_code_literal_match"] = {
        code: (code in {v["literal_reason_emitted"] for v in results.values() if isinstance(v, dict)})
        for code in design_codes
    }
    record("REASON_CODES", **results)
    return results


if __name__ == "__main__":
    test_tc07()
    test_matrix()
    test_gap_confirmation_with_runway()
    test_executable_now_still_reaches_buy_now()
    test_executable_now_false()
    test_contradictory_combination()
    test_unknown_missing_state_production_required()
    test_legacy_fixture_compatibility()
    test_high_maturation_score_never_overrides()
    test_reason_codes()

    out_path = ROOT / "audit" / "olm_fix_test" / "agent_a_results.json"
    out_path.write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(f"\n\nWrote {out_path}")
