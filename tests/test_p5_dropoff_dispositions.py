"""Phase 5.5 / RC12: the drop-off audit states where each candidate actually went, in the manifest-era pipeline.

Business rules:
- The evening runs package-free (AVS-PKG-002): the canonical manifest is the intake stage. A Discovery row is never
  "pending package build" when no package stage exists (Codex 7 Oct: all 1,814 rows of run 20261006_060401 said
  PENDING_PACKAGE_BUILD while Vanguard, Options, EIL, execution and EOD outputs were recorded).
- A manifest refusal is an evidence drop with the manifest's own reason (e.g. HISTORY_BEHIND_EVIDENCE_SESSION).
- Each drop states its reason class separately: SELECTION, SCOPE, RESOURCE, EVIDENCE, ECONOMIC, HANDOFF, GATE,
  PROGRESS (not finished yet), SURVIVED.
- Each row carries the thesis it belongs to (side, readiness, governing candidate) - one candidate, one story.
"""
import json

import pandas as pd

import dropoff_audit as da

RUN = "20990101_000000"


def _csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _run(tmp_path, *, manifest=True):
    run = tmp_path / RUN
    _csv(run / "universe" / f"scanner_augmented_universe_{RUN}.csv",
         [{"ticker": t} for t in ("AAA", "BBB", "CCC", "DDD", "ZZZ")])
    _csv(run / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv", [
        {"ticker": "AAA", "tier": 1, "precor_intent": "BUY_SETUP", "thesis__side": "BULL",
         "thesis__readiness": "READY_FOR_HUMAN_REVIEW", "thesis_trigger_candidate_id": "AAA|1d|SOS|2098-12-20"},
        {"ticker": "BBB", "tier": 1, "precor_intent": "BUY_SETUP", "thesis__side": "BEAR",
         "thesis__readiness": "WAIT_TRIGGER", "thesis_trigger_candidate_id": "BBB|1w|UT|2098-12-01"},
        {"ticker": "CCC", "tier": 3, "precor_intent": "WAIT"},
        {"ticker": "DDD", "tier": 1, "precor_intent": "BUY_SETUP"},
    ])
    if manifest:
        (run / "canonical_manifest.json").write_text(json.dumps({"run_id": RUN, "tickers": [
            {"ticker": t, "dcv_verdict": t != "DDD", "bar_count": 300,
             "dcv_reason": "HISTORY_BEHIND_EVIDENCE_SESSION" if t == "DDD" else "VALID"}
            for t in ("AAA", "BBB", "CCC", "DDD")]}), encoding="utf-8")
    _csv(run / "vanguard" / "vanguard_signals.csv", [{"ticker": t, "verdict": "CONTEXT"} for t in ("AAA", "BBB", "CCC")])
    _csv(run / "options" / f"options_intelligence_{RUN}.csv", [
        {"ticker": "AAA", "options_verdict": "ARMED", "options_score": 55, "recommended_contract": "AAA990119C00100000"},
        {"ticker": "BBB", "options_verdict": "STAND_DOWN", "options_score": 0, "stand_down_reason": "WIDE SPREAD 35%"},
    ])
    _csv(run / "superbrain" / f"eil_enriched_{RUN}.csv", [{"ticker": "AAA", "eil_v3_verdict": "WATCH"}])
    _csv(run / "morning_validation" / f"morning_candidates_{RUN}.csv",
         [{"ticker": "AAA", "eod_candidate_status": "EOD_CANDIDATE"}])
    out = da.build_dropoff_audit(RUN, runs_dir=tmp_path)
    return out.set_index("ticker")


def test_manifest_era_rows_are_never_pending_a_package_build(tmp_path):
    out = _run(tmp_path)
    assert not out.dropoff_stage.eq("PENDING_PACKAGE_BUILD").any()
    assert out.loc["AAA", "dropoff_stage"] == "AFTER_EOD_BEFORE_MORNING"
    assert out.loc["AAA", "dropoff_reason_class"] == "PROGRESS"


def test_a_manifest_refusal_is_an_evidence_drop_with_its_own_reason(tmp_path):
    out = _run(tmp_path)
    assert out.loc["DDD", "dropoff_stage"] == "CANONICAL_MANIFEST"
    assert out.loc["DDD", "dropoff_reason"] == "HISTORY_BEHIND_EVIDENCE_SESSION"
    assert out.loc["DDD", "dropoff_reason_class"] == "EVIDENCE"


def test_scope_economic_and_selection_reasons_are_separated(tmp_path):
    out = _run(tmp_path)
    assert out.loc["CCC", "dropoff_stage"] == "BETWEEN_VANGUARD_AND_OPTIONS"
    # Phase 5.4 (ACK 8 Oct 2026): Options has no tier/WAIT scope rule any more, so a Vanguard row with no Options row
    # is a handoff gap, never a scope exclusion.
    assert out.loc["CCC", "dropoff_reason_class"] == "HANDOFF"
    assert out.loc["BBB", "dropoff_stage"] == "OPTIONS_INTELLIGENCE"
    assert out.loc["BBB", "dropoff_reason_class"] == "ECONOMIC"
    assert out.loc["ZZZ", "dropoff_reason_class"] == "SELECTION"


def test_each_row_names_its_thesis(tmp_path):
    out = _run(tmp_path)
    assert out.loc["AAA", "thesis_side"] == "BULL"
    assert out.loc["AAA", "thesis_readiness"] == "READY_FOR_HUMAN_REVIEW"
    assert out.loc["AAA", "thesis_candidate_id"] == "AAA|1d|SOS|2098-12-20"
    assert out.loc["BBB", "thesis_readiness"] == "WAIT_TRIGGER"


def test_without_manifest_or_packages_intake_is_pending_not_a_package_build(tmp_path):
    out = _run(tmp_path, manifest=False)
    assert out.loc["DDD", "dropoff_stage"] == "PENDING_INTAKE"
    assert out.loc["DDD", "dropoff_reason_class"] == "PROGRESS"


def test_current_morning_permissions_are_classified_not_unknown():
    # Run 20261006_060401 replay: 58 rows were UNKNOWN because the audit predates these Morning permissions.
    base = {"disc__tier": "1", "man__dcv_verdict": "TRUE", "vg__verdict": "CONTEXT", "oi__options_verdict": "ARMED",
            "oi__options_score": "55", "oi__recommended_contract": "AAA990119C00100000", "eil__eil_v3_verdict": "WATCH",
            "eod__eod_candidate_status": "EOD_CANDIDATE"}
    avail = {"man": True, "oi": True, "eil": True, "eod": True, "mv": True}
    stage, reason, _ = da._reason({**base, "mv__execution_permission": "HUMAN_APPROVAL_REQUIRED",
                                   "mv__live_validation_state": "CONFIRMED"}, avail)
    assert (stage, reason) == ("SURVIVED", "HUMAN_APPROVAL_REQUIRED")
    row = {**base, "mv__execution_permission": "CONTRACT_REPAIR", "mv__live_validation_state": "CONTRACT_REPAIR"}
    stage, reason, _ = da._reason(row, avail)
    assert stage == "MORNING_VALIDATION" and da._reason_class(row, stage, reason) == "ECONOMIC"
