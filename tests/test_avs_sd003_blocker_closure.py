from __future__ import annotations

from pathlib import Path

import pandas as pd

from avshunter_discovery_ULTIMATE import _governed_bar_evidence
from contracts.lab_control import opportunity_book_row
from handoff_contract_audit import _semantic_contract_audit, audit_run
from scripts.macro_quant_packet import build_macro_quant_packet, macro_quant_columns_for_row


def test_stale_discovery_bars_receive_named_governed_fallback() -> None:
    assert _governed_bar_evidence("STALE_CACHE", 1) == (
        True,
        "APPROVED_FALLBACK",
        "STALE_SOURCE_FALLBACK",
    )
    assert _governed_bar_evidence("CACHE_OK", 6) == (
        True,
        "APPROVED_FALLBACK",
        "STALE_SOURCE_FALLBACK",
    )
    assert _governed_bar_evidence("CACHE_OK", 1) == (
        False,
        "COMPLETED_SESSION",
        "CURRENT_CANONICAL_HISTORY",
    )


def test_governed_bar_evidence_is_preserved_in_lab_record() -> None:
    row = opportunity_book_row(
        {
            "ticker": "STALE",
            "direction": "CALL",
            "bar_data_source": "STALE_CACHE",
            "bar_data_asof": "2026-09-01",
            "bar_data_days_old": 6,
            "bar_evidence_state": "APPROVED_FALLBACK",
            "bar_evidence_reason": "STALE_SOURCE_FALLBACK",
            "is_stale": True,
        },
        run_id="TEST_RUN",
        rank=1,
    )
    assert row["bar_data_source"] == "STALE_CACHE"
    assert row["bar_data_asof"] == "2026-09-01"
    assert row["bar_data_days_old"] == 6
    assert row["bar_evidence_state"] == "APPROVED_FALLBACK"
    assert row["bar_evidence_reason"] == "STALE_SOURCE_FALLBACK"
    assert row["is_stale"] is True


def test_macro_packet_identity_is_deterministic_and_advisory() -> None:
    raw = {
        "contract_version": "macro_contract_v1_0",
        "as_of_utc": "2026-09-04T20:00:00Z",
        "report_date": "2026-09-04",
        "regime_state": "TRANSITIONAL",
        "macro_conviction": 0.55,
        "notes": "Rotation favours energy; use as context only.",
    }
    first = build_macro_quant_packet(raw, "missing-fixture.json")
    second = build_macro_quant_packet(raw, "missing-fixture.json")
    assert first["macro_packet_id"] == second["macro_packet_id"]
    assert first["macro_packet_sha256"] == second["macro_packet_sha256"]
    assert len(first["macro_source_fingerprint"]) == 64
    assert first["macro_session_date"] == "2026-09-04"
    assert first["macro_authority"] == "ADVISORY_ONLY"
    columns = macro_quant_columns_for_row(first, {"ticker": "X", "sector": "Energy"})
    for field in (
        "macro_packet_id",
        "macro_packet_sha256",
        "macro_source_fingerprint",
        "macro_as_of_utc",
        "macro_session_date",
        "macro_plain_language_advisory",
        "macro_authority",
    ):
        assert columns[field]


def test_known_bad_cross_stage_contract_triggers_explicit_semantic_failures() -> None:
    frames = {
        "vanguard": pd.DataFrame([{
            "ticker": "BAD", "profile_type": "INSUFFICIENT_DATA",
            "market_profile_state": "NOT_EVALUATED", "poc": 0.0,
            "auction_state": "ALIGNED", "ready_to_trade": True,
        }]),
        "options_intelligence": pd.DataFrame([{
            "ticker": "BAD", "direction": "CALL", "options_verdict": "ARMED",
            "invalidation_state": "MISSING", "invalidation_spot": None,
            "stand_down_reason": "TypeError: unsupported operand",
            "contract_bid_size": 20, "contract_ask_size": 30,
            "contract_quote_quality": "TWO_SIDED",
            "governed_direction_record_sha256": "source-hash",
            "data_source": "STALE_CACHE", "is_stale": True,
        }]),
        "eod_candidates": pd.DataFrame([{
            "ticker": "BAD", "direction": "CALL",
            "eod_candidate_status": "EOD_TRIGGER_READY",
            "eod_candidate_permission": "MORNING_VALIDATION_REQUIRED",
            "invalidation_state": "MISSING", "invalidation_spot": None,
        }]),
        "lab": pd.DataFrame([{
            "ticker": "BAD", "direction": "CALL", "final_action": "BUY_NOW",
            "lab_tradeable": True, "invalidation_state": "MISSING",
            "invalidation_price": None,
            "governed_direction_record_sha256": "different-hash",
        }]),
    }
    records = _semantic_contract_audit(frames, {name: f"{name}.csv" for name in frames})
    statuses = {record["status"] for record in records}
    assert {
        "ARMED_WITHOUT_GOVERNED_INVALIDATION",
        "EOD_CANDIDATE_WITHOUT_GOVERNED_INVALIDATION",
        "LAB_EXECUTABLE_WITHOUT_GOVERNED_INVALIDATION",
        "RAW_INTERPRETER_TEXT_PUBLISHED",
        "INSUFFICIENT_PROFILE_MARKED_ALIGNED",
        "MISSING_PROFILE_LEVEL_PUBLISHED_AS_ZERO",
        "UPSTREAM_FIELD_UNIVERSALLY_LOST",
        "DIRECTION_LINEAGE_HASH_MISMATCH",
        "STALE_BAR_FALLBACK_UNNAMED",
    } <= statuses


def test_no_capital_is_a_valid_fail_closed_options_permission() -> None:
    records = _semantic_contract_audit(
        {
            "options_intelligence": pd.DataFrame([{
                "ticker": "SAFE",
                "direction": "NON_DIRECTIONAL",
                "execution_permission": "NO_CAPITAL",
                "final_route": "OPTIONS_BLOCKED",
            }]),
        },
        {"options_intelligence": "options.csv"},
    )
    assert "OPTIONS_PERMISSION_NOT_RESEARCH_ONLY" not in {
        record["status"] for record in records
    }


def test_eod_finalisation_materialises_lab_before_audit_and_manifest_refresh() -> None:
    source = (Path(__file__).resolve().parents[1] / "intelligent_orchestrator.py").read_text(
        encoding="utf-8"
    )
    lab_write = source.index("_lab_book = write_final_opportunity_book(")
    audit_write = source.index(
        "_handoff_audit = _audit_handoff_contract(canonical_run_id"
    )
    uat_write = source.index(
        "_uat_report = write_uat_audit_report(canonical_run_id"
    )
    manifest_refresh = source.index("_manifest = _refresh_final_run_manifest(")
    worker3_macro = source.index(
        "_worker3_macro = materialize_worker3_market_environment("
    )
    assert lab_write < worker3_macro < audit_write < uat_write < manifest_refresh


def _write_empty_shadow_fixture(root: Path, *, eligible: bool) -> tuple[Path, str]:
    run_id = "EMPTY_TEST"
    run_dir = root / run_id
    morning = run_dir / "morning_validation"
    morning.mkdir(parents=True)
    pd.DataFrame(columns=["ticker", "shadow_opportunity_score"]).to_csv(
        morning / f"missed_opportunity_shadow_book_{run_id}.csv", index=False
    )
    pd.DataFrame([{
        "ticker": "X",
        "shadow_opportunity_score": 55 if eligible else 10,
        "eod_candidate_status": "EOD_BLOCK",
    }]).to_csv(morning / f"eod_dropoff_audit_{run_id}.csv", index=False)
    return root, run_id


def test_empty_shadow_book_requires_dropoff_corroboration(tmp_path: Path) -> None:
    runs_dir, run_id = _write_empty_shadow_fixture(tmp_path / "ok", eligible=False)
    result = audit_run(run_id, runs_dir=runs_dir)
    rows = pd.read_csv(result["output_csv"])
    shadow = rows[rows["stage"].eq("shadow_book")]
    assert shadow["status"].tolist() == ["EMPTY_BY_DESIGN"]

    runs_dir, run_id = _write_empty_shadow_fixture(tmp_path / "bad", eligible=True)
    result = audit_run(run_id, runs_dir=runs_dir)
    rows = pd.read_csv(result["output_csv"])
    shadow = rows[rows["stage"].eq("shadow_book")]
    assert shadow["status"].tolist() == ["EMPTY_UNEXPECTED"]
    assert shadow["severity"].tolist() == ["FAIL"]
