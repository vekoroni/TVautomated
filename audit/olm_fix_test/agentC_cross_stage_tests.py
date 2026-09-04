"""Agent C - OLM remediation cross-stage integration tests (design SS11.4).

READ-ONLY validation harness. Writes only under audit/olm_fix_test/tmp_runs.
Does not modify any production file.

Chains real production functions:
  morning_gate._morning_liquidity_lifecycle()   (Morning Gate lifecycle assessment)
  -> execution_gate.execution_gate()            (sole positive capital authority)
  -> contracts.lab_control.opportunity_book_row / write_final_opportunity_book
     (Lab resolution + defence-in-depth)
  -> morning_handoff_finalizer.finalize_morning_handoff (SS7.4 reconciliation invariant)
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from contracts.direction_governance import resolve_governed_direction  # noqa: E402
from contracts.options_liquidity_execution_guard import (  # noqa: E402
    evaluate_olm_execution_guard,
)
from execution_gate import execution_gate  # noqa: E402
from contracts.lab_control import (  # noqa: E402
    opportunity_book_row,
    write_final_opportunity_book,
    write_final_run_manifest,
    build_final_run_manifest,
)
import morning_gate  # noqa: E402
import morning_handoff_finalizer as mhf  # noqa: E402

RESULTS = []


def record(test_id, name, design_ref, verdict, detail, evidence=None):
    RESULTS.append({
        "id": test_id,
        "name": name,
        "design_ref": design_ref,
        "verdict": verdict,
        "detail": detail,
        "evidence": evidence or "",
    })
    print(f"[{verdict}] {test_id} — {name}")
    print(f"    {detail}")
    if evidence:
        print(f"    evidence: {evidence}")


def _direction_fields(side: str, ticker: str, run_id: str) -> dict:
    return resolve_governed_direction(
        ticker=ticker,
        run_id=run_id,
        discovery_direction=side,
        governed_direction=side,
        governed_basis=f"agentC_test={side}",
        row={},
        decided_at_utc="2026-08-29T13:30:00+00:00",
    )


def _base_row(side: str, ticker: str, run_id: str) -> dict:
    strike = 100.0
    row = {
        "ticker": ticker,
        "run_id": run_id,
        "signal_price": 100.0,
        "thesis_spot": 100.0,
        "contract_strike": strike,
        "contract_dte": 30,
        "remaining_hold_sessions": 5,
        "garch_forecast_vol": 0.30,
        "pipeline_mode": "MORNING_VALIDATION",
        "run_pipeline_mode": "MORNING_VALIDATION",
        "thesis_id": f"{ticker}:{side}:AGENTC_TEST_SESSION",
    }
    row.update(_direction_fields(side, ticker, run_id))
    if side == "CALL":
        row["structural_target"] = 110.0
        row["invalidation_spot"] = 95.0
        symbol = "TESTC260918C00100000"
        delta_sign = 1.0
    else:
        row["structural_target"] = 90.0
        row["invalidation_spot"] = 105.0
        symbol = "TESTP260918P00100000"
        delta_sign = -1.0
    row["morning_selected_contract_symbol"] = symbol
    row["contract_symbol"] = symbol
    row["monetisability_contract_symbol"] = symbol
    row["monetisability_state"] = "MONETISABLE"
    row["morning_execution_permission"] = "GO"
    row["_delta_sign"] = delta_sign
    return row


def _live_data(bid: float, ask: float, delta_sign: float, current_spot: float = 100.0) -> dict:
    return {
        "live_price": current_spot,
        "live_contract_bid": bid,
        "live_contract_ask": ask,
        "live_contract_delta": 0.45 * delta_sign,
        "live_contract_iv": 0.35,
        "live_iv_rank": 50.0,
    }


def _apply_lifecycle(row, live_data, *, contract_changed=False, economics_recompute_complete=True):
    """Call the REAL Morning Gate lifecycle assessment function."""
    lifecycle = morning_gate._morning_liquidity_lifecycle(
        row, live_data,
        contract_changed=contract_changed,
        economics_recompute_complete=economics_recompute_complete,
    )
    merged = {**row, **lifecycle}
    # execution_gate reads live quote/delta straight off the row via
    # _live_option_data_from_row(); mirror what Morning Gate's live_data
    # carried so the exact same quote reaches the capital-authority stage.
    merged["live_contract_bid"] = live_data.get("live_contract_bid")
    merged["live_contract_ask"] = live_data.get("live_contract_ask")
    merged["live_contract_delta"] = live_data.get("live_contract_delta")
    merged["live_contract_iv"] = live_data.get("live_contract_iv")
    merged["live_iv_rank"] = live_data.get("live_iv_rank")
    return merged


def _run_chain(row, run_id, rank=1):
    """Morning lifecycle row -> execution_gate() -> Lab resolution -> opportunity_book_row().

    Mirrors contracts.lab_control.build_final_opportunity_book()'s own sequence
    (apply_lab_resolution() when lab_verdict is not already present, THEN
    opportunity_book_row()) so the positive (CONTINUE) path exercises the real
    resolve_lab_tradeability() logic exactly as production does, not just the
    defence-in-depth override branch.
    """
    from contracts.lab_control import apply_lab_resolution
    gated = execution_gate(row, require_olm=True)
    sig = dict(gated)
    sig.setdefault("pipeline_mode", "MORNING_VALIDATION")
    if "lab_verdict" not in sig or "morning_lab_alignment_status" not in sig:
        apply_lab_resolution(sig, {})
    lab_row = opportunity_book_row(sig, run_id, rank)
    return gated, lab_row


# ---------------------------------------------------------------------------
# Test 1: THESIS_INVALIDATED -> BLOCK -> BLOCKED / non-tradeable
# ---------------------------------------------------------------------------
def test_thesis_invalidated():
    tid, name, ref = "T1", "Morning THESIS_INVALIDATED -> Gate BLOCK -> Lab BLOCKED", "SS11.4 bullet 1"
    try:
        row = _base_row("CALL", "AGTC1", "20260829_000001")
        live = _live_data(bid=2.00, ask=2.05, delta_sign=row["_delta_sign"], current_spot=94.0)  # breaches invalidation=95
        row = _apply_lifecycle(row, live)
        assert row["morning_transition_state"] == "THESIS_INVALIDATED", f"fixture did not reach THESIS_INVALIDATED: {row['morning_transition_state']}"
        gated, lab_row = _run_chain(row, "20260829_000001")
        ok = (
            gated["final_action"] == "BLOCK"
            and gated["olm_guard_disposition"] == "BLOCK"
            and gated["olm_guard_reason"] == "OLM_THESIS_INVALIDATED"
            and lab_row["lab_verdict"] == "BLOCKED"
            and lab_row["lab_tradeable"] in (False, "False", "FALSE", "")
        )
        detail = (
            f"fixture morning_transition_state=THESIS_INVALIDATED; "
            f"gate final_action={gated['final_action']} olm_guard_disposition={gated['olm_guard_disposition']} "
            f"olm_guard_reason={gated['olm_guard_reason']}; "
            f"lab_verdict={lab_row['lab_verdict']} lab_tradeable={lab_row['lab_tradeable']}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_move_already_realized():
    tid, name, ref = "T2", "Morning MOVE_ALREADY_REALIZED -> Gate BLOCK -> Lab BLOCKED", "SS11.4 bullet 2"
    try:
        row = _base_row("CALL", "AGTC2", "20260829_000002")
        live = _live_data(bid=2.00, ask=2.05, delta_sign=row["_delta_sign"], current_spot=110.0)  # >= target=110
        row = _apply_lifecycle(row, live)
        assert row["morning_transition_state"] == "MOVE_ALREADY_REALIZED", f"fixture did not reach MOVE_ALREADY_REALIZED: {row['morning_transition_state']}"
        gated, lab_row = _run_chain(row, "20260829_000002")
        ok = (
            gated["final_action"] == "BLOCK"
            and gated["olm_guard_disposition"] == "BLOCK"
            and gated["olm_guard_reason"] == "OLM_MOVE_ALREADY_REALIZED"
            and lab_row["lab_verdict"] == "BLOCKED"
        )
        detail = (
            f"fixture morning_transition_state=MOVE_ALREADY_REALIZED; "
            f"gate final_action={gated['final_action']} olm_guard_reason={gated['olm_guard_reason']}; "
            f"lab_verdict={lab_row['lab_verdict']}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_liquidity_still_pending():
    tid, name, ref = "T3", "Morning LIQUIDITY_STILL_PENDING -> Gate MANUAL_REVIEW -> Lab non-tradeable, visible", "SS11.4 bullet 3"
    try:
        row = _base_row("CALL", "AGTC3", "20260829_000003")
        # neutral spot (no thesis progress) + wide spread -> LIQUIDITY_PENDING liquidity_state
        live = _live_data(bid=1.00, ask=2.00, delta_sign=row["_delta_sign"], current_spot=100.0)
        row = _apply_lifecycle(row, live)
        assert row["morning_transition_state"] == "LIQUIDITY_STILL_PENDING", f"fixture did not reach LIQUIDITY_STILL_PENDING: {row['morning_transition_state']}"
        gated, lab_row = _run_chain(row, "20260829_000003")
        row_present = bool(lab_row.get("ticker"))
        ok = (
            gated["final_action"] == "MANUAL_REVIEW"
            and gated["olm_guard_disposition"] == "MANUAL_REVIEW"
            and lab_row["lab_tradeable"] in (False, "False", "FALSE", "")
            and lab_row["lab_verdict"] not in ("GO", "GO_LIMIT", "PROBE")
            and row_present
        )
        detail = (
            f"fixture morning_transition_state=LIQUIDITY_STILL_PENDING liquidity_state={row.get('liquidity_state')}; "
            f"gate final_action={gated['final_action']}; lab_verdict={lab_row['lab_verdict']} "
            f"lab_tradeable={lab_row['lab_tradeable']} row_present_in_output={row_present}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_contract_reprice_required():
    tid, name, ref = "T4", "Replacement OCC w/o recomputed economics -> Gate CONTRACT_REPAIR -> Lab repair state", "SS11.4 bullet 4"
    try:
        row = _base_row("PUT", "AGTC4", "20260829_000004")
        live = _live_data(bid=2.00, ask=2.05, delta_sign=row["_delta_sign"], current_spot=100.0)
        row = _apply_lifecycle(row, live, contract_changed=True, economics_recompute_complete=False)
        assert row["morning_transition_state"] == "CONTRACT_REPRICE_REQUIRED", f"fixture did not reach CONTRACT_REPRICE_REQUIRED: {row['morning_transition_state']}"
        gated, lab_row = _run_chain(row, "20260829_000004")
        ok = (
            gated["final_action"] == "CONTRACT_REPAIR"
            and gated["olm_guard_disposition"] == "CONTRACT_REPAIR"
            and lab_row["lab_tradeable"] in (False, "False", "FALSE", "")
            and lab_row["lab_verdict"] == "CONTRACT_REPAIR"
        )
        detail = (
            f"fixture morning_transition_state=CONTRACT_REPRICE_REQUIRED (contract_changed=True, economics_recompute_complete=False); "
            f"gate final_action={gated['final_action']}; lab_verdict={lab_row['lab_verdict']} lab_tradeable={lab_row['lab_tradeable']}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_fully_repriced_positive_control():
    tid, name, ref = "T5", "Fully repriced coherent replacement -> existing gates decide normally (positive control)", "SS11.4 bullet 5"
    try:
        row = _base_row("CALL", "AGTC5", "20260829_000005")
        live = _live_data(bid=2.00, ask=2.05, delta_sign=row["_delta_sign"], current_spot=100.0)
        row = _apply_lifecycle(row, live, contract_changed=True, economics_recompute_complete=True)
        assert row["morning_transition_state"] == "EXECUTABLE_NOW", f"fixture did not reach EXECUTABLE_NOW: {row['morning_transition_state']}"
        gated, lab_row = _run_chain(row, "20260829_000005")
        ok = (
            gated["final_action"] == "BUY_NOW"
            and gated["olm_guard_disposition"] == "CONTINUE"
            and lab_row["lab_verdict"] == "GO"
            and lab_row["lab_tradeable"] in (True, "True", "TRUE")
        )
        detail = (
            f"fixture morning_transition_state=EXECUTABLE_NOW (repriced replacement, coherent); "
            f"gate final_action={gated['final_action']} olm_guard_disposition={gated['olm_guard_disposition']}; "
            f"lab_verdict={lab_row['lab_verdict']} lab_tradeable={lab_row['lab_tradeable']}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_malformed_buy_now_thesis_invalidated_defence_in_depth():
    tid, name, ref = "T6", "Malformed BUY_NOW + THESIS_INVALIDATED caught by Lab defence-in-depth (bypasses execution_gate)", "SS11.4 bullet 6 (SS7.3/SS5.1)"
    try:
        ticker = "AGTC6"
        run_id = "20260829_000006"
        direction = _direction_fields("CALL", ticker, run_id)
        # Simulate a stale export / buggy upstream: final_action and lab
        # verdict are ALREADY stamped BUY_NOW/GO/tradeable, as if some other
        # code path produced them, while the OLM lifecycle fields say the
        # thesis is invalidated. This bypasses execution_gate.execution_gate()
        # entirely and is fed straight into contracts.lab_control's row
        # resolution / opportunity-book materialiser.
        sig = {
            "ticker": ticker,
            "run_id": run_id,
            "pipeline_mode": "MORNING_VALIDATION",
            "run_pipeline_mode": "MORNING_VALIDATION",
            **direction,
            "final_action": "BUY_NOW",
            "lab_verdict": "GO",
            "lab_tradeable": True,
            "lab_status": "GO",
            "lab_execution_status": "BUY_NOW",
            "gate_reason": "FORGED_UPSTREAM_GO",
            "morning_selected_contract_symbol": "TESTC260918C00100000",
            "contract_symbol": "TESTC260918C00100000",
            "monetisability_state": "MONETISABLE",
            "monetisability_contract_symbol": "TESTC260918C00100000",
            "morning_execution_permission": "GO",
            # OLM lifecycle evidence says the thesis is dead.
            "lifecycle_contract_version": "OPTIONS-LIQUIDITY-LIFECYCLE-V1",
            "thesis_state": "ACTIVE",  # deliberately contradictory/malformed: thesis marked ACTIVE...
            "morning_transition_state": "THESIS_INVALIDATED",  # ...but transition says invalidated
            "remaining_runway_state": "THESIS_INVALIDATED",
            "liquidity_state": "EXECUTABLE_NOW",
            "executable_now": True,
        }
        pre_guard = evaluate_olm_execution_guard(sig, require_contract=True)
        lab_row = opportunity_book_row(dict(sig), run_id, 1)
        ok = (
            lab_row["lab_tradeable"] in (False, "False", "FALSE", "")
            and lab_row["lab_verdict"] != "GO"
            and lab_row["final_action"] != "BUY_NOW"
        )
        detail = (
            f"forged input: final_action=BUY_NOW lab_verdict=GO lab_tradeable=True with "
            f"morning_transition_state=THESIS_INVALIDATED; standalone guard disposition={pre_guard.disposition} "
            f"reason={pre_guard.reason}; "
            f"AFTER Lab defence-in-depth: lab_verdict={lab_row['lab_verdict']} "
            f"lab_tradeable={lab_row['lab_tradeable']} final_action={lab_row['final_action']} "
            f"execution_lock_reason={lab_row.get('execution_lock_reason')}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_lineage_retained():
    tid, name, ref = "T7", "Final opportunity book retains exact contract and quote lineage", "SS11.4 bullet 7"
    try:
        row = _base_row("CALL", "AGTC7", "20260829_000007")
        live = _live_data(bid=2.00, ask=2.05, delta_sign=row["_delta_sign"], current_spot=100.0)
        row = _apply_lifecycle(row, live)
        gated, lab_row = _run_chain(row, "20260829_000007")
        expected_symbol = row["morning_selected_contract_symbol"]
        lab_symbol = lab_row.get("selected_contract_symbols") or lab_row.get("contract_symbol") or lab_row.get("recommended_contract")
        lab_bid = lab_row.get("contract_bid")
        lab_ask = lab_row.get("contract_ask")
        quote_ts = lab_row.get("quote_as_of") or gated.get("quote_as_of")
        ok = (
            gated["final_action"] == "BUY_NOW"
            and expected_symbol in str(lab_symbol).replace("O:", "").strip().upper()
            and float(lab_bid) == 2.00
            and float(lab_ask) == 2.05
        )
        detail = (
            f"gated contract={gated.get('morning_selected_contract_symbol')} bid=2.00 ask=2.05; "
            f"lab row selected_contract_symbols/contract field={lab_symbol} contract_bid={lab_bid} "
            f"contract_ask={lab_ask} quote_as_of={quote_ts}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def test_interpreter_handoff_mismatch_blocked():
    tid, name, ref = "T8", "Pipeline Interpreter handoff blocks on actionable lifecycle contradiction", "SS11.4 bullet 8 (SS7.4)"
    scratch_runs = REPO_ROOT / "audit" / "olm_fix_test" / "tmp_runs"
    run_id = "20260829_000008"
    try:
        row = _base_row("CALL", "AGTC8", run_id)
        live = _live_data(bid=2.00, ask=2.05, delta_sign=row["_delta_sign"], current_spot=100.0)
        row = _apply_lifecycle(row, live)
        # This is a genuine EXECUTABLE_NOW / BUY_NOW-eligible row.
        source_rows = [dict(row)]

        # Simulate a stale/partial Lab export: patch write_final_opportunity_book
        # (the exact seam finalize_morning_handoff imports at call time) so the
        # Lab artifact it receives contradicts the just-computed Execution Gate
        # action for this ticker. Nothing else is mocked: run_execution_gate,
        # the OLM guard, and the SS7.4 reconciliation code all execute for real.
        from execution_gate import run_execution_gate
        real_gated_rows, real_gate_summary = run_execution_gate(
            signals=source_rows, run_id=run_id, output_dir=scratch_runs / run_id / "trades",
        )
        assert real_gated_rows[0]["final_action"] == "BUY_NOW", (
            f"positive-control fixture must reach BUY_NOW pre-corruption, got {real_gated_rows[0]['final_action']}"
        )

        corrupted_lab_row = dict(real_gated_rows[0])
        corrupted_lab_row["lab_verdict"] = "BLOCKED"
        corrupted_lab_row["lab_tradeable"] = False
        corrupted_lab_row["final_action"] = "BLOCK"
        fake_lab_book = {
            "rows": [corrupted_lab_row],
            "triage_csv_path": str(scratch_runs / run_id / "intelligence_lab" / "triage_fake.csv"),
            "csv_path": str(scratch_runs / run_id / "intelligence_lab" / "final_fake.csv"),
        }
        (scratch_runs / run_id / "intelligence_lab").mkdir(parents=True, exist_ok=True)
        (scratch_runs / run_id / "intelligence_lab" / "triage_fake.csv").write_text("ticker\n", encoding="utf-8")
        (scratch_runs / run_id / "intelligence_lab" / "final_fake.csv").write_text("ticker\n", encoding="utf-8")
        (scratch_runs / run_id / "morning_validation").mkdir(parents=True, exist_ok=True)
        morning_csv = scratch_runs / run_id / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
        import csv as _csv
        with morning_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = _csv.DictWriter(fh, fieldnames=list(source_rows[0].keys()))
            writer.writeheader()
            writer.writerow(source_rows[0])

        raised = None
        try:
            with patch("contracts.lab_control.write_final_opportunity_book", return_value=fake_lab_book):
                mhf.finalize_morning_handoff(
                    run_id, results=source_rows, runs_dir=scratch_runs, sync_interpreter=False,
                )
        except mhf.MorningHandoffError as exc:
            raised = str(exc)

        ok = raised is not None and "reconciliation failed" in raised.lower()
        detail = (
            f"pre-corruption execution_gate final_action=BUY_NOW (positive control confirmed); "
            f"finalize_morning_handoff raised MorningHandoffError={raised is not None}; message={raised}"
        )
        record(tid, name, ref, "PASS" if ok else "FAIL", detail)
    except Exception as exc:
        record(tid, name, ref, "BLOCKED", f"exception: {exc}", traceback.format_exc())


def main():
    test_thesis_invalidated()
    test_move_already_realized()
    test_liquidity_still_pending()
    test_contract_reprice_required()
    test_fully_repriced_positive_control()
    test_malformed_buy_now_thesis_invalidated_defence_in_depth()
    test_lineage_retained()
    test_interpreter_handoff_mismatch_blocked()

    out_path = REPO_ROOT / "audit" / "olm_fix_test" / "agentC_cross_stage_results.json"
    out_path.write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print("\n=== SUMMARY ===")
    for r in RESULTS:
        print(f"{r['id']}: {r['verdict']} - {r['name']}")


if __name__ == "__main__":
    main()
