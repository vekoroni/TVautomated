"""M-REVIEW-01 (ACK approved 10 Oct 2026): Morning authority comes from the thesis, not the legacy Vanguard label.

Root cause (run 20261008_220129): Vanguard's legacy actuarial signal_type (STRUCTURAL_MATCH "no current edge") became
capital_permission WATCH_ONLY in the execution layer, then NOT_AUTHORIZED, and the Morning gate blocked 862 rows before
any review - 282 activated theses among them. ACK's decisions: Vanguard is context and never decides; legacy
classifiers are inactive. Design + replay: Enhancements/phase7/M_REVIEW_01_THESIS_AUTHORITY_DESIGN_20261010.md.

Business rules:
- Kept: provenance (FINAL_EXECUTION), the options route block, the missing-invalidation block.
- Removed as a gate: the legacy capital permission / authorization state / eod_candidate_authorized; published as
  context (legacy_execution_permission_context), never read by a gate.
- Added: an adopted thesis is required (missing readiness is not a thesis).
- Everything after it (direction, contract, viability, pays, GO eligibility) is unchanged.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import morning_gate  # noqa: E402
from test_morning_gate_authority import _gate, _row  # noqa: E402

LEGACY_WATCH = {"capital_permission": "WATCH_ONLY", "capital_authorization_state": "NOT_AUTHORIZED",
                "eod_candidate_authorized": False, "signal_authority_reason": "STRUCTURAL_MATCH_NO_CURRENT_EDGE"}


def test_a_legacy_watch_label_no_longer_blocks_an_activated_thesis():
    gated = _gate(_row(**LEGACY_WATCH, thesis__readiness="READY_FOR_HUMAN_REVIEW"))
    assert gated["verdict"] == "GO"
    assert gated["legacy_execution_permission_context"] == "WATCH_ONLY:STRUCTURAL_MATCH_NO_CURRENT_EDGE"


def test_no_adopted_thesis_is_not_authority():
    for readiness in ("NOT_ADOPTED", "NOT_MEASURED", None):
        gated = _gate(_row(thesis__readiness=readiness))
        assert gated["verdict"] == "BLOCK", readiness
        assert gated["morning_unlock_condition"].startswith("NO_ADOPTED_THESIS")


def test_provenance_route_and_missing_invalidation_still_block():
    ready = {"thesis__readiness": "READY_FOR_HUMAN_REVIEW"}
    assert _gate(_row(**ready, authority_source_stage="EOD"))["morning_unlock_condition"].startswith("UNSAFE_AUTHORITY_SOURCE")
    assert _gate(_row(**ready, final_route="OPTIONS_BLOCKED"))["morning_unlock_condition"].startswith(
        "UPSTREAM_OPTIONS_ROUTE_BLOCKED")
    missing = _gate(_row(**ready, capital_authorization_state="NOT_AUTHORIZED_INVALIDATION_MISSING"))
    assert missing["verdict"] == "BLOCK" and missing["morning_unlock_condition"] == "UPSTREAM_INVALIDATION_MISSING"


def test_the_legacy_label_is_context_only():
    src = inspect.getsource(morning_gate._check_upstream_authority)
    for legacy in ('"capital_permission"', '"eod_candidate_authorized"', "EOD_CANDIDATE_ONLY"):
        assert legacy not in src


def test_the_legacy_label_reaches_the_card_as_vanguard_context():
    import json
    import subprocess
    from contracts.lab_control import opportunity_book_row
    from contracts.thesis_record import VANGUARD_CONTEXT_FIELDS
    assert "legacy_execution_permission_context" in VANGUARD_CONTEXT_FIELDS
    row = opportunity_book_row({"ticker": "WYNN", "direction": "CALL",
                                "legacy_execution_permission_context": "WATCH_ONLY:STRUCTURAL_MATCH_NO_CURRENT_EDGE"},
                               "RUN", 1)
    assert row["legacy_execution_permission_context"] == "WATCH_ONLY:STRUCTURAL_MATCH_NO_CURRENT_EDGE"
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    out = subprocess.run(["node"], input=card + f"\nconsole.log(JSON.stringify(renderTradeCard({json.dumps(row)})"
                         ".includes('legacy execution label WATCH_ONLY:STRUCTURAL_MATCH_NO_CURRENT_EDGE (context only)')));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.stdout.strip().splitlines()[-1] == "true", out.stderr
