"""EOD preparation may be healthy while Morning trade permission remains pending."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase_verifier", ROOT / "tools/avs_verify/avs_verify.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
RULES = json.loads((ROOT / "tools/avs_verify/avs_verify_rules.json").read_text(encoding="utf-8"))


def manifest():
    return {
        "run_tradeable": False,
        "pipeline_technical_health": "PASS", "pipeline_semantic_health": "PASS",
        "fatal_flags": [], "conflict_flags": [],
        "stale_flags": ["EOD_MORNING_VALIDATION_PENDING"],
        "next_action": "NEEDS_MORNING_VALIDATION",
        "run_execution_permission": "MORNING_VALIDATION_REQUIRED",
        "morning_capital_permission": "MORNING_VALIDATION_REQUIRED",
        "row_counts": {"morning_candidates": 2777, "morning_validation": 0},
    }


def check(man, phase="evening", count=2777, trades=()):
    f = verifier.F({})
    preparation = verifier.evening_preparation_only(man, RULES, phase, count, len(trades))
    verifier.r_self_report(man, RULES, phase, count, f, tradeable_count=len(trades))
    return f, verifier.decide(f, trades, preparation_only=preparation)


def test_complete_evening_handoff_is_not_a_failed_morning_book():
    man = manifest()
    before = copy.deepcopy(man)
    findings, (verdict, clean, reason) = check(man)
    assert verdict == "TRUST_WITH_CAVEATS" and clean == []
    assert "No trade permission" in reason
    assert next(b for b in findings.book if b["rule"] == "R24_MANIFEST_RECONCILE")["status"] == "PASS"
    assert man == before  # reporting never changes permission or manifest evidence


@pytest.mark.parametrize("changes", [
    {"pipeline_technical_health": "FAILED"},
    {"pipeline_semantic_health": "DEGRADED"},
    {"fatal_flags": ["BROKEN_HANDOFF"]},
    {"conflict_flags": ["AUTHORITY_CONFLICT"]},
    {"next_action": "REPAIR_REQUIRED"},
    {"run_execution_permission": "BLOCKED"},
    {"morning_capital_permission": "BLOCKED"},
    {"run_execution_permission": None},
    {"row_counts": {"morning_candidates": 2776, "morning_validation": 0}},
    {"row_counts": {"morning_validation": 0}},
])
def test_real_failure_or_missing_preparation_evidence_keeps_the_restriction(changes):
    man = manifest()
    man.update(changes)
    assert check(man)[1][0] == "DO_NOT_TRADE"


def test_morning_and_actionable_eod_rows_never_use_the_pending_exception():
    assert check(manifest(), phase="morning", count=0)[1][0] == "DO_NOT_TRADE"
    assert check(manifest(), trades=[0])[1][0] == "DO_NOT_TRADE"
    assert check(manifest(), count=0)[1][0] == "DO_NOT_TRADE"


def test_other_book_failures_and_missing_evidence_still_override_preparation():
    f, _ = check(manifest())
    f.b("R02_DUPLICATE_HEADERS", "P0", "FAIL", "conflicting values")
    assert verifier.decide(f, [], preparation_only=True)[0] == "DO_NOT_TRADE"
    f, _ = check(manifest())
    f.b("R03_CRITICAL_COLUMNS", "P0", "FAIL", "missing columns")
    assert verifier.decide(f, [], preparation_only=True)[0] == "UNVERIFIED"
    f, _ = check(manifest())
    f.b("R19_QUOTE_FRESH", "P0", "UNCERTAIN", "missing evidence")
    assert verifier.decide(f, [], preparation_only=True)[0] == "UNVERIFIED"


def test_genuine_morning_clear_and_failed_rows_keep_existing_verdicts():
    assert verifier.decide(verifier.F({}), [0])[0] == "TRUST"
    f = verifier.F({})
    f.r(0, "R13_QUOTES", "P0", "bid exceeds ask")
    assert verifier.decide(f, [0])[0] == "DO_NOT_TRADE"


def test_scorecard_separates_preparation_review_from_a_calculation_failure(tmp_path):
    from domain.run_scorecard import build_scorecard
    run = tmp_path / "runs/R1"
    run.mkdir(parents=True)
    (run / "final_run_manifest.json").write_text(json.dumps(manifest()))
    report_dir = tmp_path / "verify/R1/evening"
    report_dir.mkdir(parents=True)
    (report_dir / "verify_report.json").write_text(json.dumps({
        "verdict": "TRUST_WITH_CAVEATS", "reason": "Morning validation required",
        "verification_scope": "EOD_PREPARATION", "execution_permission": "MORNING_VALIDATION_REQUIRED",
    }))
    card = build_scorecard(run, run_id="R1", phase="evening", verify_root=tmp_path / "verify")
    assert card["overall"] == "REVIEW"
    assert card["sections"]["calculation"]["status"] == "REVIEW"
    assert card["sections"]["calculation"]["facts"]["execution_permission"] == "MORNING_VALIDATION_REQUIRED"
