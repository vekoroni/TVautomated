"""INT-001 scenario suite 6: read-only replay of the stored TEST run 20260925_061649.

The stored run is evidence of current behaviour (design §2), not a prospective baseline. This
suite never writes into the run. It re-materialises every published Lab row from its own frozen
`source_payload_json` through the current governed materialiser and checks the A1 alias, the
convexity truth and population preservation against the pre-fix book; it re-runs the horizon
audit against the receipt's numbers; and it rebuilds the run manifest to compare grains.

Slow: reads about 350 MB of stored artefacts. Run alone: one file per process.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import build_final_run_manifest, opportunity_book_row  # noqa: E402
from tools.avs_int001_horizon_audit import audit_rows  # noqa: E402

RUN = "20260925_061649"
RUNS_DIR = ROOT / "data" / "output" / "runs"
RUN_DIR = RUNS_DIR / RUN
BOOK_CSV = RUN_DIR / "intelligence_lab" / f"final_opportunity_book_{RUN}.csv"
MANIFEST = RUN_DIR / "final_run_manifest.json"

pytestmark = pytest.mark.skipif(not BOOK_CSV.exists(), reason="stored TEST run not present")

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def _u(value) -> str:
    return str(value if value is not None else "").strip().upper()


def _missing(value) -> bool:
    return _u(value) in {"", "NONE", "NAN", "NULL", "N/A", "MISSING", "UNKNOWN"}


@pytest.fixture(scope="module")
def stored_rows() -> list[dict]:
    with BOOK_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def replayed_rows(stored_rows) -> list[dict]:
    out = []
    for rank, row in enumerate(stored_rows, 1):
        payload = json.loads(row["source_payload_json"])
        out.append(opportunity_book_row(payload, RUN, rank))
    return out


@pytest.fixture(scope="module")
def stored_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_r0_stored_book_is_the_pre_fix_population_described_in_the_receipts(stored_rows):
    assert len(stored_rows) == 1549
    assert len({r["trade_idea_id"] for r in stored_rows}) == 1549
    assert all(_missing(r.get("invalidation_spot")) for r in stored_rows)
    assert sum(not _missing(r.get("invalidation_price")) for r in stored_rows) == 1180
    assert sum(not _missing(r.get("convexity_score")) for r in stored_rows) == 1549
    assert all(_missing(r.get("convexity_score_source")) for r in stored_rows)
    assert all(r.get("pipeline_mode") == "MORNING_VALIDATION" for r in stored_rows)
    assert all(r.get("validation_event_id") and r.get("morning_execution_mode") for r in stored_rows)


def test_r1_replay_preserves_every_row_identity_and_direction(stored_rows, replayed_rows):
    assert len(replayed_rows) == len(stored_rows)
    for stored, replay in zip(stored_rows, replayed_rows):
        assert replay["ticker"] == stored["ticker"]
        assert replay["trade_idea_id"] == stored["trade_idea_id"]
        assert _u(replay["canonical_direction"]) == _u(stored["canonical_direction"])
        assert replay["run_id"] == RUN


def test_r2_a1_alias_now_covers_exactly_the_side_checked_sourced_invalidations(replayed_rows):
    aliased = [r for r in replayed_rows if not _missing(r.get("invalidation_spot"))]
    priced = [r for r in replayed_rows if not _missing(r.get("invalidation_price"))]
    assert len(priced) == 1180
    assert len(aliased) == 1180
    for row in aliased:
        assert float(row["invalidation_spot"]) == float(row["invalidation_price"])
        assert _u(row["invalidation_state"]) == "AVAILABLE"
        assert not _missing(row["invalidation_source"])
        assert json.loads(row["field_provenance_json"])["invalidation_spot"].endswith("side_checked_invalidation_alias")
        spot = float(row["signal_price"] or row["underlying_price"] or 0)
        if spot and _u(row["canonical_direction"]) == "CALL":
            assert float(row["invalidation_spot"]) < spot
        elif spot:
            assert float(row["invalidation_spot"]) > spot
    wrong_side = [r for r in replayed_rows if "INVALIDATION_WRONG_SIDE" in _u(r.get("lab_coherence_flags"))]
    assert all(_missing(r.get("invalidation_spot")) for r in wrong_side)


def test_r3_replay_never_widens_tradeability_and_every_tradeable_row_has_a_sourced_stop(stored_rows, replayed_rows):
    stored_tradeable = {r["trade_idea_id"] for r in stored_rows if _u(r.get("lab_tradeable")) == "TRUE"}
    replay_tradeable = {r["trade_idea_id"] for r in replayed_rows if r.get("lab_tradeable") is True}
    assert replay_tradeable <= stored_tradeable
    for row in replayed_rows:
        if row.get("lab_tradeable") is True:
            assert not _missing(row["invalidation_spot"])
            assert not _missing(row["invalidation_source"])
            assert row["check_direction_integrity_pass"] is True
        assert row["maturation_execution_authority"] is False
        assert row["position_size_display"] == "HUMAN DETERMINED"


def test_r4_convexity_is_withheld_on_the_whole_population_without_losing_components(replayed_rows):
    states = {r["convexity_data_state"] for r in replayed_rows}
    assert states <= {"UNVERIFIED_SOURCE", "NOT_GOVERNED", "DATA_DEFECT"}
    assert "AVAILABLE" not in states
    assert all(_missing(r.get("convexity_score")) for r in replayed_rows)
    assert sum(not _missing(r.get("target_price")) for r in replayed_rows) >= 1100


def test_r5_horizon_audit_reproduces_the_receipt_counts(stored_rows):
    result = audit_rows(stored_rows)
    six_ten = result["by_horizon"]["6_10D"]
    assert six_ten["comparable"] == 334
    assert six_ten["legacy_false_review"] == 88
    assert six_ten["not_comparable"] == 101
    assert "11_20D" not in result["by_horizon"] or result["by_horizon"]["11_20D"]["comparable"] == 0
    assert "not a trading outcome" in result["meaning"]


def test_r6_replayed_evening_buckets_are_typed_and_no_row_is_silently_neutral(replayed_rows):
    buckets = {}
    for row in replayed_rows:
        buckets[row["evening_thesis_bucket"]] = buckets.get(row["evening_thesis_bucket"], 0) + 1
    assert set(buckets) <= {
        "EOD_ACTION_SETUP_READY", "EOD_TRIGGER_WATCH", "EOD_CONTRACT_WATCH", "EOD_EVIDENCE_REVIEW",
        "EOD_DIRECTION_EVIDENCE_REVIEW", "EOD_TARGET_FEASIBILITY_REVIEW", "EOD_THESIS_INVALIDATED",
        "EOD_NOT_EVALUATED",
    }
    assert sum(buckets.values()) == 1549
    # Morning rows carry a frozen Evening bucket; the replay must not recompute it from Morning prices.
    assert buckets.get("EOD_NOT_EVALUATED", 0) < 1549


@pytest.fixture(scope="module")
def rebuilt_manifest():
    before = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    manifest = build_final_run_manifest(RUN, RUNS_DIR, pipeline_mode="MORNING_VALIDATION")
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == before
    return manifest


def test_r7_rebuilt_manifest_reconciles_counts_with_the_stored_one(stored_manifest, rebuilt_manifest):
    assert rebuilt_manifest["row_counts"] == stored_manifest["row_counts"]
    assert rebuilt_manifest["missing_selected_handoff"] == {"invalidation_spot": 175}
    assert rebuilt_manifest["pipeline_semantic_health"] == "DEGRADED"
    assert rebuilt_manifest["fatal_flags"] == []
    geometry = rebuilt_manifest.get("thesis_geometry") or rebuilt_manifest.get("thesis_geometry_completeness") or {}
    if geometry:
        assert geometry["population"] >= geometry["actionable_population"]
        assert geometry["missing_invalidation"] <= geometry["population"]


def test_r8_interpreter_macro_handoff_in_the_stored_run_is_typed_invalid_not_available(rebuilt_manifest):
    env = rebuilt_manifest["worker3_market_environment"]
    assert env["status"] == "INVALID"
    assert env["error"] == "packet session differs from governed run session"
    assert env["trading_authority"] is False


def test_r9_run_label_does_not_say_execution_ready_while_selected_handoff_is_incomplete(rebuilt_manifest):
    assert rebuilt_manifest["semantic_defect_count"] == 175
    assert rebuilt_manifest["run_tradeable_label"] != "EXECUTION_READY"
