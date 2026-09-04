from __future__ import annotations

import csv
import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INTERPRETER = ROOT / "pipeline_interpreter"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(INTERPRETER) not in sys.path:
    sys.path.insert(0, str(INTERPRETER))

from contracts.interpreter_handoff import (  # noqa: E402
    AUTHORITY_MAP_VERSION,
    BUNDLE_SCHEMA_VERSION,
    HandoffValidationError,
    artifact_record,
    publish_handoff_manifest,
    validate_handoff_manifest,
)
from contracts.lab_evidence_overlay import (  # noqa: E402
    OverlayValidationError,
    apply_latest_compatible_overlays,
    build_overlay,
)
from assessment_contract import (  # noqa: E402
    AssessmentStatus,
    build_assessment,
)
from evidence_resolver import (  # noqa: E402
    EvidenceResolutionError,
    IntendedUse,
    resolve_interpreter_evidence,
)
from macro_context import load_macro_packet  # noqa: E402


RUN_ID = "20260830_120000"
TICKER = "AAA"
CONTRACT = "AAA260918C00100000"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(
    tmp_path: Path, *, freshness: str = "FRESH", macro_freshness: str | None = None
) -> tuple[Path, dict, dict]:
    run = tmp_path / RUN_ID
    lab = run / "intelligence_lab"
    interp = run / "interpreter"
    diagnostics = run / "diagnostics"
    macro_dir = run / "macro"
    for folder in (lab, interp, diagnostics, macro_dir):
        folder.mkdir(parents=True)

    bundle_id = str(uuid.uuid4())
    governed = {
        "run_id": RUN_ID,
        "ticker": TICKER,
        "thesis_id": "THESIS-1",
        "trade_idea_id": "IDEA-1",
        "selected_structure_id": "STRUCT-1",
        "selected_contract_symbol": CONTRACT,
        "selected_quote_snapshot_id": "QUOTE-1",
        "governed_direction": "CALL",
        "thesis_state": "TRADEABLE_NOW",
        "olm_guard_disposition": "ELIGIBLE",
        "final_action": "BUY_NOW",
        "capital_permission": "CAPITAL_ALLOWED",
    }
    book = lab / "lab_signal_book_v3.csv"
    with book.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(governed))
        writer.writeheader()
        writer.writerow(governed)
    book_manifest = lab / "lab_signal_book_v3.manifest.json"
    book_manifest.write_text(json.dumps({"schema_version": "lab_signal_book_v3"}))
    macro = macro_dir / "macro_quant_packet.json"
    macro.write_text(json.dumps({
        "packet_id": "MACRO-1", "macro_context_state": "TAILWIND",
        "sector_rotation": {"XLK": "TAILWIND"}, "final_action": "BLOCK",
    }))
    bundle = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "authority_map_version": AUTHORITY_MAP_VERSION,
        "bundle_id": bundle_id,
        "bundle_created_utc": "2026-08-30T11:30:00+00:00",
        "run_id": RUN_ID,
        "pipeline_mode": "MORNING_VALIDATION",
        "ticker": TICKER,
        "thesis_id": "THESIS-1",
        "trade_idea_id": "IDEA-1",
        "selected_structure_id": "STRUCT-1",
        "selected_contract_symbol": CONTRACT,
        "selected_quote_snapshot_id": "QUOTE-1",
        "authority_map": {"final_action": "MORNING_EXECUTION_GATE"},
        "freshness_map": {
            "exact_option_quote": freshness,
            "underlying_quote": freshness,
            **({"macro_quant_packet": macro_freshness} if macro_freshness else {}),
        },
        "governed_record": governed,
        "market_structure": {"ms_direction_relationship": "ALIGNED"},
        "macro_quant_packet": {
            "packet_id": "MACRO-1", "path": str(macro), "sha256": _sha(macro),
            "as_of_utc": "2026-08-30T11:20:00+00:00", "session_date": "2026-08-30",
            "freshness": "FRESH", "quality": "COMPLETE", "macro_context_state": "TAILWIND",
        },
    }
    bundles = interp / "interpreter_evidence_bundle_v1.jsonl"
    bundles.write_text(json.dumps(bundle) + "\n")
    reconciliation = diagnostics / "msi_reconciliation.json"
    reconciliation.write_text(json.dumps({"status": "PASS"}))
    records = [
        artifact_record("LAB_BOOK", book, "lab_signal_book_v3"),
        artifact_record("LAB_BOOK_MANIFEST", book_manifest, "lab_signal_book_v3.manifest"),
        artifact_record("INTERPRETER_BUNDLES", bundles, BUNDLE_SCHEMA_VERSION),
        artifact_record("RECONCILIATION_REPORT", reconciliation, "msi_reconciliation_v1"),
    ]
    manifest = interp / "handoff_manifest.json"
    publish_handoff_manifest(
        manifest,
        run_id=RUN_ID,
        pipeline_mode="MORNING_VALIDATION",
        session_date="2026-08-30",
        run_kind="PRODUCTION",
        run_status="ACCEPTED",
        required_stage_status={"EOD": "PASS", "MORNING_GATE": "COMPLETED", "LAB": "PASS"},
        morning_gate_completed_utc="2026-08-30T11:25:00+00:00",
        artifacts=records,
        ticker_count=1,
        bundle_count=1,
        reconciliation_status="PASS",
        producer_version="test",
    )
    return manifest, bundle, governed


def test_atomic_handoff_and_resolver_exact_identity(tmp_path: Path) -> None:
    manifest, bundle, governed = _fixture(tmp_path)
    validated = validate_handoff_manifest(manifest)
    assert validated.manifest["run_status"] == "ACCEPTED"
    evidence = resolve_interpreter_evidence(
        TICKER, manifest_path=manifest, intended_use=IntendedUse.EXECUTABLE_SESSION
    )
    assert evidence.bundle["bundle_id"] == bundle["bundle_id"]
    assert evidence.book_row["final_action"] == governed["final_action"]
    assert evidence.macro.state.value == "TAILWIND"
    assert evidence.macro.ignored_authority_fields == ("final_action",)


def test_handoff_hash_tamper_fails_closed(tmp_path: Path) -> None:
    manifest, _, _ = _fixture(tmp_path)
    book = tmp_path / RUN_ID / "intelligence_lab" / "lab_signal_book_v3.csv"
    book.write_text(book.read_text() + "\n")
    with pytest.raises(HandoffValidationError, match="HASH_MISMATCH"):
        validate_handoff_manifest(manifest)


def test_handoff_rejects_same_ticker_with_different_contract_identity(
    tmp_path: Path,
) -> None:
    manifest, _, _ = _fixture(tmp_path)
    run = tmp_path / RUN_ID
    book = run / "intelligence_lab" / "lab_signal_book_v3.csv"
    rows = list(csv.DictReader(book.open(encoding="utf-8")))
    rows[0]["selected_contract_symbol"] = "AAA260918C00999000"
    with book.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for record in payload["artifacts"]:
        if record["role"] == "LAB_BOOK":
            record["sha256"] = _sha(book)
            record["size_bytes"] = book.stat().st_size
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HandoffValidationError, match="IDENTITY_MISMATCH:selected_contract_symbol"):
        validate_handoff_manifest(manifest)


def test_stale_bundle_returns_refresh_requirement_but_makes_no_call(tmp_path: Path) -> None:
    manifest, _, _ = _fixture(tmp_path, freshness="STALE")
    with pytest.raises(EvidenceResolutionError, match="EVIDENCE_REFRESH_REQUIRED"):
        resolve_interpreter_evidence(TICKER, manifest_path=manifest)
    evidence = resolve_interpreter_evidence(
        TICKER, manifest_path=manifest, require_current=False
    )
    assert evidence.refresh_required["provider_calls_made"] == 0
    assert evidence.refresh_required["selected_contract_symbol"] == CONTRACT


def test_assessment_copies_authority_and_rejects_override(tmp_path: Path) -> None:
    _, bundle, _ = _fixture(tmp_path)
    clean = build_assessment(
        bundle=bundle,
        model_output={
            "strengthening_weakening": "STRENGTHENING",
            "agreement_conflict": "ALIGNED",
            "manual_checks": ["confirm wall"],
            "data_gaps": [],
            "plain_language_reason": "Evidence is strengthening; human review remains required.",
        },
        model_id="gpt-test",
        prompt_version="msi-1",
        prompt_hash="a" * 64,
    )
    assert clean["assessment_status"] == AssessmentStatus.VALID.value
    assert clean["final_action"] == "BUY_NOW"
    rejected = build_assessment(
        bundle=bundle,
        model_output={
            "strengthening_weakening": "STRENGTHENING",
            "agreement_conflict": "ALIGNED",
            "manual_checks": [],
            "data_gaps": [],
            "plain_language_reason": "Direction: PUT. Capital is approved.",
        },
        model_id="gpt-test",
        prompt_version="msi-1",
        prompt_hash="a" * 64,
    )
    assert rejected["assessment_status"] == AssessmentStatus.REJECTED_GOVERNANCE_CONFLICT.value


def test_overlay_cannot_replace_authority(tmp_path: Path) -> None:
    _, bundle, governed = _fixture(tmp_path)
    with pytest.raises(OverlayValidationError, match="AUTHORITY_FIELD"):
        build_overlay(
            run_id=RUN_ID, ticker=TICKER, bundle_id=bundle["bundle_id"],
            fields={"final_action": "BLOCK"}, source="test",
        )
    overlay = build_overlay(
        run_id=RUN_ID, ticker=TICKER, bundle_id=bundle["bundle_id"],
        fields={"current_contract_bid": 1.2, "quote_freshness": "FRESH"}, source="test",
    )
    row = {**governed, "bundle_id": bundle["bundle_id"]}
    merged = apply_latest_compatible_overlays([row], [overlay])[0]
    assert merged["current_contract_bid"] == 1.2
    assert merged["final_action"] == "BUY_NOW"
    no_bundle = apply_latest_compatible_overlays([governed], [overlay])[0]
    assert "current_contract_bid" not in no_bundle


def test_macro_packet_is_advisory_and_hash_bound(tmp_path: Path) -> None:
    manifest, bundle, _ = _fixture(tmp_path)
    context = load_macro_packet(
        bundle["macro_quant_packet"], run_root=manifest.parent.parent
    )
    assert "final_action" not in context.advisory
    assert "ADVISORY_ONLY" in context.authority_statement


def test_stale_macro_is_visible_but_does_not_block_current_trade_evidence(
    tmp_path: Path,
) -> None:
    manifest, bundle, _ = _fixture(tmp_path, macro_freshness="STALE")
    evidence = resolve_interpreter_evidence(TICKER, manifest_path=manifest)
    assert evidence.refresh_required is None
    assessment = build_assessment(
        bundle=bundle,
        model_output={
            "strengthening_weakening": "UNCHANGED",
            "agreement_conflict": "MACRO_CONTEXT_STALE",
            "manual_checks": [],
            "data_gaps": ["macro packet stale"],
            "plain_language_reason": "Ticker and selected-contract evidence remain current.",
        },
        model_id="gpt-test",
        prompt_version="msi-1",
        prompt_hash="b" * 64,
    )
    assert assessment["assessment_status"] == AssessmentStatus.VALID.value


def test_lab_msi_view_contains_all_approved_evidence_groups() -> None:
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    for label in (
        "Current Selected-Contract Quote", "Underlying Session Evidence",
        "Market Structure Lifecycle", "Interpreter Assessment — Advisory Only",
        "MICROSTRUCTURE_NOT_OBSERVED",
    ):
        assert label in html


def test_resolver_source_contains_no_provider_client_or_http_call() -> None:
    source = (INTERPRETER / "evidence_resolver.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("import requests", "import httpx", "import polygon", "marketdataapi"):
        assert forbidden not in lowered
