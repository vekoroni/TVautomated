"""QA gate for the Morning Thesis Validator.

Runs deterministic validation cases plus a latest-run merge sanity check.
No broker calls and no live quote calls.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import resolve_lab_tradeability
try:
    from morning_thesis_validator import latest_run_id, run_morning_validation, validate_candidate  # type: ignore[import-not-found]
    _LEGACY_MORNING_VALIDATOR_AVAILABLE = True
except ModuleNotFoundError:
    latest_run_id = None
    run_morning_validation = None
    validate_candidate = None
    _LEGACY_MORNING_VALIDATOR_AVAILABLE = False


def _candidate(**overrides):
    row = {
        "run_id": "qa_run",
        "ticker": "QA",
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
    }
    row.update(overrides)
    return row


def _live(**overrides):
    row = {
        "live_price": 101,
        "live_vwap": 100,
        "live_orb_high": 100.5,
        "live_orb_low": 99.5,
        "live_contract_bid": 1.0,
        "live_contract_ask": 1.06,
        "live_contract_mid": 1.03,
        "live_data_timestamp_utc": "2099-01-01T14:45:00Z",
    }
    row.update(overrides)
    return row


def main() -> int:
    if not _LEGACY_MORNING_VALIDATOR_AVAILABLE:
        print(
            "RETIRED: qa_morning_validator.py targeted morning_thesis_validator.py. "
            "Use pytest tests/test_morning_gate_authority.py "
            "tests/test_morning_gate_contract_repair.py."
        )
        return 2
    results = []

    def check(name: str, condition: bool, detail: dict):
        results.append({"name": name, "passed": bool(condition), "detail": detail})

    row = validate_candidate(_candidate(), _live(), pipeline_mode="EOD")
    check(
        "CALL above VWAP + ORB high + tight spread => GO",
        row["morning_execution_permission"] == "GO" and row["morning_execution_route"] == "GO_NOW" and row["execution_permission"] == "GO",
        row,
    )

    row = validate_candidate(_candidate(), _live(live_price=94, live_vwap=96, live_orb_high=97, live_orb_low=95), pipeline_mode="EOD")
    check("CALL rejects VWAP + invalidation broken => BLOCKED", row["execution_permission"] == "BLOCKED", row)

    row = validate_candidate(
        _candidate(direction="PUT", target_price=95, invalidation_price=102, state_transition_label="BALANCE_TO_DOWNSIDE_EXPANSION"),
        _live(live_price=99, live_vwap=100, live_orb_high=100.5, live_orb_low=99.5),
        pipeline_mode="EOD",
    )
    check("PUT below VWAP + ORB low + tight spread => GO", row["execution_permission"] == "GO", row)

    row = validate_candidate(
        _candidate(direction="PUT", target_price=95, invalidation_price=102, state_transition_label="BALANCE_TO_DOWNSIDE_EXPANSION"),
        _live(live_price=103, live_vwap=100, live_orb_high=102, live_orb_low=99),
        pipeline_mode="EOD",
    )
    check("PUT reclaims VWAP + invalidation broken => BLOCKED", row["execution_permission"] == "BLOCKED", row)

    row = validate_candidate(_candidate(), {}, pipeline_mode="EOD")
    check("Missing live price => NO_LIVE_DATA / WAIT", row["live_validation_state"] == "NO_LIVE_DATA" and row["execution_permission"] == "WAIT", row)

    row = validate_candidate(_candidate(), _live(live_data_timestamp_utc="2000-01-01T00:00:00Z"), pipeline_mode="EOD")
    check("Stale quote => STALE / WAIT", row["live_validation_state"] == "STALE" and row["execution_permission"] == "WAIT", row)

    row = validate_candidate(_candidate(), _live(live_contract_bid=1.0, live_contract_ask=1.3, live_contract_mid=1.15), pipeline_mode="EOD")
    check("Option spread > 15% => CONTRACT_REPAIR", row["morning_execution_permission"] == "CONTRACT_REPAIR", row)

    row = validate_candidate(_candidate(), _live(live_contract_bid=1.0, live_contract_ask=1.12, live_contract_mid=1.06), pipeline_mode="EOD")
    check("Option spread 8-15% => GO_LIMIT", row["morning_execution_permission"] == "GO_LIMIT", row)

    row = validate_candidate(_candidate(lab_verdict="ARMED"), _live(), pipeline_mode="EOD")
    check("Evening ARMED can upgrade to GO", row["execution_permission"] == "GO", row)

    row = validate_candidate(_candidate(), _live(live_price=100.1, live_vwap=100, live_orb_high=101, live_orb_low=99), pipeline_mode="EOD")
    check("Evening GO can downgrade to WAIT/ARMED/PROBE", row["morning_execution_permission"] in {"WAIT", "ARMED", "PROBE"}, row)

    row = validate_candidate(_candidate(lab_verdict="BLOCKED"), _live(), pipeline_mode="EOD")
    check("Evening BLOCKED cannot upgrade to GO", row["execution_permission"] == "BLOCKED", row)

    row = validate_candidate(_candidate(state_transition_label="HIGH_ENTROPY_CHOP"), _live(live_price=100.2, live_orb_high=101), pipeline_mode="EOD")
    check("HIGH_ENTROPY_CHOP requires stronger confirmation", row["execution_permission"] != "GO", row)

    row = validate_candidate(_candidate(state_transition_label="NO_TRANSITION_EDGE"), _live(), pipeline_mode="EOD")
    check("NO_TRANSITION_EDGE cannot promote to GO", row["execution_permission"] != "GO" and row["physics_transition_confirmed"] == "WAIT", row)

    row = validate_candidate(_candidate(state_transition_label="CHOP_CONTINUATION"), _live(), pipeline_mode="EOD")
    check("CHOP_CONTINUATION can confirm on decisive expansion", row["execution_permission"] == "GO" and row["physics_transition_confirmed"] == "TRUE", row)

    row = validate_candidate(_candidate(state_transition_label="CHOP_CONTINUATION"), _live(live_price=100.1, live_orb_high=101), pipeline_mode="EOD")
    check("CHOP_CONTINUATION waits without decisive expansion", row["execution_permission"] != "GO" and row["physics_transition_confirmed"] == "WAIT", row)

    row = validate_candidate(_candidate(state_transition_label="BALANCE_TO_UPSIDE_EXPANSION"), _live(live_price=100.2, live_orb_high=101), pipeline_mode="EOD")
    check("Physics transition compared against live behaviour", row["physics_transition_confirmed"] in {"WAIT", "TRUE", "FALSE", "UNKNOWN"}, row)

    runs_dir = ROOT / "data" / "output" / "runs"
    run_id = latest_run_id(runs_dir)
    merge_detail = {"run_id": run_id}
    if run_id:
        qa_dir = ROOT / "data" / "output" / "qa" / "morning_validator"
        qa_dir.mkdir(parents=True, exist_ok=True)
        run_morning_validation(
            run_id=run_id,
            runs_dir=runs_dir,
            output_path=qa_dir / f"morning_validated_trades_{run_id}_qa.csv",
            max_signals=5,
            live_mode=False,
            paper_mode=True,
            pipeline_mode="EOD",
        )
        mod_path = ROOT / "intelligence-lab" / "intelligence_lab.py"
        spec = importlib.util.spec_from_file_location("intelligence_lab", mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        payload = mod._load_run(run_id)
        sig = next((s for s in payload.get("signals", []) if s.get("mv__morning_execution_permission") or s.get("mv__execution_permission")), {})
        merge_detail.update({
            "ticker": sig.get("ticker"),
            "mv": sig.get("mv__morning_execution_permission") or sig.get("mv__execution_permission"),
            "legacy_mv": sig.get("mv__execution_permission"),
            "lab_verdict": sig.get("lab_verdict"),
            "alignment": sig.get("morning_lab_alignment_status"),
        })
        check("Morning validation fields merge into Lab payload", bool(sig.get("mv__morning_execution_permission") or sig.get("mv__execution_permission")), merge_detail)
        alignment_conflicts = [
            {
                "ticker": s.get("ticker"),
                "mv": s.get("mv__morning_execution_permission") or s.get("mv__execution_permission"),
                "lab_verdict": s.get("lab_verdict"),
                "alignment": s.get("morning_lab_alignment_status"),
            }
            for s in payload.get("signals", [])
            if (s.get("mv__morning_execution_permission") or s.get("mv__execution_permission"))
            and str(s.get("morning_lab_alignment_status") or "").upper() == "CONFLICT"
        ]
        check("No Morning Validator / Lab alignment conflicts in payload", not alignment_conflicts, {"conflicts": alignment_conflicts[:10]})
    else:
        check("Morning validation fields merge into Lab payload", False, merge_detail)

    blocked = resolve_lab_tradeability(
        {"ticker": "QA", "mv__morning_execution_permission": "BLOCKED", "mv__execution_permission": "BLOCKED", "mv__live_validation_state": "REJECTED", "strike": 100, "expiry": "2099-01-19", "premium_mid": 1},
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    check("Lab entry disabled when MV execution permission BLOCKED", blocked["lab_verdict"] == "BLOCKED" and not blocked["lab_tradeable"], blocked)
    check("Blocked MV aligns to blocked Lab verdict", blocked.get("morning_lab_alignment_status") == "ALIGNED_BLOCKED", blocked)

    wait = resolve_lab_tradeability(
        {"ticker": "QA", "lab_verdict": "GO", "mv__morning_execution_permission": "WAIT", "mv__execution_permission": "WAIT", "mv__live_validation_state": "WAIT_RETEST", "strike": 100, "expiry": "2099-01-19", "premium_mid": 1},
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    check("Morning WAIT cannot display as Lab GO", wait["lab_verdict"] == "WAIT" and wait.get("morning_lab_alignment_status") == "ALIGNED", wait)

    passed = all(r["passed"] for r in results)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "results": results,
    }
    out_dir = ROOT / "data" / "output" / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "qa_morning_validator_latest.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
