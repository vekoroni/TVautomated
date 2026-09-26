"""INT-001 scenario suite 1: macro truth from publication to the Interpreter packet.

Simulated operator situations, all offline (no provider, no live run):
  M1  the operator drops a macro packet that claims non-advisory authority;
  M2  a legacy projection file drifts from the Dropbox authority (the 25 Sep class of fault);
  M3  Evening annotates a run-scoped copy; a second run must not silently reuse different bytes;
  M4  the run-frozen macro snapshot becomes the Interpreter packet; the packet is tamper-checked;
  M5  the Interpreter packet's session differs from the governed run session (as in the stored
      TEST run 20260925_061649) and the manifest must call it INVALID, not AVAILABLE;
  M6  a Lab row asks for advisory macro fields; no authority key may leak and an unmapped sector
      must not be reported as FAVOURED.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "pipeline_interpreter") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline_interpreter"))

import intelligent_orchestrator as orchestrator  # noqa: E402
from canonical_data.macro_publication import (  # noqa: E402
    macro_projection_paths,
    publish_macro_projections,
    validate_macro_projection_alignment,
    write_authoritative_macro,
)
from contracts.interpreter_macro_context import (  # noqa: E402
    AUTHORITY_STATEMENT,
    FORBIDDEN_AUTHORITY_KEYS,
    advisory_fields_for_row,
    materialize_interpreter_macro_context,
)
from contracts.lab_control import build_final_run_manifest  # noqa: E402
from pipeline_interpreter.macro_context import MacroPacketError, load_macro_packet  # noqa: E402


def _realistic_macro(**overrides) -> dict:
    """A packet shaped like the 25 Sep run's macro_snapshot.json (subset)."""
    packet = {
        "contract_version": "macro_contract_v1_0",
        "macro_authority": "ADVISORY_ONLY",
        "as_of_utc": "2026-09-25T05:39:11Z",
        "report_date": "2026-09-25",
        "regime_state": "TRANSITIONAL_BEARISH",
        "regime_drift_status": "DRIFTING",
        "risk_on_switch": "RISK_OFF",
        "dir_bias": "BEARISH",
        "conviction_score": 0.55,
        "macro_conviction": 0.55,
        "liquidity_status": "CONTRACTING",
        "liquidity_pulse": "CONTRACTING",
        "volatility_mode": "ELEVATED",
        "vix_contango": False,
        "vix_spot": 21.4,
        "usd_state": "STRONG",
        "size_multiplier": 0.5,
        "sector_rotation": {"sector_bias_map": {"Financials": "FAVOURED", "Technology": "HEADWIND"}},
        "extras": {"rates": {"t10y": 4.31}, "volatility": {"regime": "ELEVATED"}},
        "macro_quant_packet": {
            "macro_generated_at_utc": "2026-09-25T05:39:11Z",
            "macro_freshness_status": "FRESH",
            "macro_data_quality": "PARTIAL",
            "macro_regime_label": "TRANSITIONAL",
            "macro_active_conflict_flags": [],
        },
        "horizon_routing": {
            bucket: {"direction": "NEUTRAL", "bias": "NEUTRAL", "bullish_prob_pct": 50.0,
                     "go_no_go": "GO_SELECTIVE", "size_multiplier": 0.5, "confidence": 0,
                     "confirm_required": []}
            for bucket in ("1_5d", "6_10d", "11_20d")
        },
    }
    packet.update(overrides)
    return packet


def _dropbox_authority(root: Path) -> Path:
    authority = root / "dropbox" / "macro" / "macro_intelligence_latest.json"
    authority.parent.mkdir(parents=True, exist_ok=True)
    return authority


# --------------------------------------------------------------------------- M1
def test_m1_macro_claiming_capital_authority_is_refused_and_projections_untouched(tmp_path):
    authority = _dropbox_authority(tmp_path)
    write_authoritative_macro(authority, _realistic_macro())
    baseline = [p.read_bytes() for p in macro_projection_paths(tmp_path)]

    with pytest.raises(ValueError, match="ADVISORY_ONLY"):
        write_authoritative_macro(authority, _realistic_macro(macro_authority="CAPITAL_ALLOCATION"))

    assert [p.read_bytes() for p in macro_projection_paths(tmp_path)] == baseline
    assert json.loads(authority.read_text(encoding="utf-8"))["macro_authority"] == "ADVISORY_ONLY"


# --------------------------------------------------------------------------- M2
def test_m2_drifted_projection_fails_evening_preflight_until_republished(tmp_path, monkeypatch):
    authority = _dropbox_authority(tmp_path)
    write_authoritative_macro(authority, _realistic_macro())
    legacy_projection = macro_projection_paths(tmp_path)[1]
    stale = _realistic_macro(regime_state="RISK_ON_BULLISH", as_of_utc="2026-09-18T05:00:00Z")
    legacy_projection.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(orchestrator.cfg, "MACRO_DIR", authority.parent)
    monkeypatch.setattr(orchestrator.cfg, "MACRO_FILE", authority)

    alignment = validate_macro_projection_alignment(authority)
    assert alignment["aligned"] is False
    assert str(legacy_projection.resolve()) in alignment["stale_or_missing"]
    ready, reason, _ = orchestrator.check_macro_json()
    assert ready is False
    assert "not synchronized" in reason

    publish_macro_projections(authority)
    ready, reason, path = orchestrator.check_macro_json()
    assert ready is True, reason
    assert path == authority
    assert json.loads(legacy_projection.read_text(encoding="utf-8"))["regime_state"] == "TRANSITIONAL_BEARISH"


# --------------------------------------------------------------------------- M3
def test_m3_run_scoped_copy_is_immutable_evidence_for_that_run(tmp_path, monkeypatch):
    authority = _dropbox_authority(tmp_path)
    write_authoritative_macro(authority, _realistic_macro())
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs")

    first = orchestrator._run_scoped_macro_copy("20260926_230000", authority)
    assert first.read_bytes() == authority.read_bytes()
    # Same bytes again is idempotent.
    assert orchestrator._run_scoped_macro_copy("20260926_230000", authority) == first

    # The operator re-drops a different packet mid-run: the run keeps its frozen copy.
    write_authoritative_macro(authority, _realistic_macro(regime_state="RISK_ON_BULLISH"))
    with pytest.raises(RuntimeError, match="different evidence"):
        orchestrator._run_scoped_macro_copy("20260926_230000", authority)
    assert json.loads(first.read_text(encoding="utf-8"))["regime_state"] == "TRANSITIONAL_BEARISH"
    # A new run picks up the new packet in its own scope.
    second = orchestrator._run_scoped_macro_copy("20260927_230000", authority)
    assert json.loads(second.read_text(encoding="utf-8"))["regime_state"] == "RISK_ON_BULLISH"


# --------------------------------------------------------------------------- M4
def _run_with_snapshot(tmp_path: Path, run_id: str, macro: dict) -> Path:
    run = tmp_path / "runs" / run_id
    run.mkdir(parents=True)
    (run / "macro_snapshot.json").write_text(json.dumps(macro), encoding="utf-8")
    return run


def test_m4_run_snapshot_becomes_tamper_checked_interpreter_packet(tmp_path):
    run = _run_with_snapshot(tmp_path, "20260925_061649", _realistic_macro(
        macro_capital_authority="FULL", trade_go=True,  # authority-looking keys must be stripped
    ))
    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-09-24", macro_dir=tmp_path / "absent", prefer_run_snapshot=True,
    )
    packet, reference = result["packet"], result["reference"]
    assert packet["source_manifest"]["core_macro"]["status"] == "RUN_SNAPSHOT"
    assert packet["authority_statement"] == AUTHORITY_STATEMENT
    assert packet["macro_context_state"] == "NEUTRAL"
    assert packet["regime_state"] == "TRANSITIONAL_BEARISH"

    context = load_macro_packet(reference, run_root=run, ticker="XLF")
    assert context.state.value == "NEUTRAL"
    assert context.freshness == "FRESH"
    assert not (set(context.advisory) & FORBIDDEN_AUTHORITY_KEYS)
    assert context.advisory["macro_quant_packet"]["macro_data_quality"] == "PARTIAL"

    # A later edit of the packet on disk is detected before any prompt is built.
    packet_path = Path(result["packet_path"])
    edited = json.loads(packet_path.read_text(encoding="utf-8"))
    edited["regime_state"] = "RISK_ON_BULLISH"
    packet_path.write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(MacroPacketError, match="HASH_MISMATCH"):
        load_macro_packet(reference, run_root=run)

    # A packet outside the run root is refused even when its hash matches.
    outside = tmp_path / "elsewhere.json"
    outside.write_bytes(packet_path.read_bytes())
    with pytest.raises(MacroPacketError, match="OUTSIDE_RUN"):
        load_macro_packet({**reference, "path": str(outside)}, run_root=run)


def test_m4b_stale_or_conflicting_macro_is_a_typed_state_not_a_neutral_default(tmp_path):
    stale = _realistic_macro()
    stale["macro_quant_packet"]["macro_freshness_status"] = "STALE"
    run = _run_with_snapshot(tmp_path, "20260925_061650", stale)
    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-09-24", macro_dir=tmp_path / "absent", prefer_run_snapshot=True,
    )
    assert result["packet"]["macro_context_state"] == "STALE_CONTEXT"
    assert load_macro_packet(result["reference"], run_root=run).state.value == "STALE_CONTEXT"

    conflicting = _realistic_macro()
    conflicting["macro_quant_packet"]["macro_active_conflict_flags"] = ["GEX_DUAL_SOURCE_DIVERGENCE"]
    run2 = _run_with_snapshot(tmp_path, "20260925_061651", conflicting)
    result2 = materialize_interpreter_macro_context(
        run_dir=run2, session_date="2026-09-24", macro_dir=tmp_path / "absent", prefer_run_snapshot=True,
    )
    assert result2["packet"]["macro_context_state"] == "CONFLICTING_SOURCES"
    assert result2["packet"]["conflicts"] == ["GEX_DUAL_SOURCE_DIVERGENCE"]


# --------------------------------------------------------------------------- M5
def _minimal_run(tmp_path: Path, run_id: str, *, session: str, packet_session: str) -> Path:
    runs = tmp_path / "runs"
    run = _run_with_snapshot(tmp_path, run_id, _realistic_macro())
    (run / "run_meta.json").write_text(json.dumps({
        "run_condition": "TEST",
        "dynamic_plan": {"last_completed_session": session},
    }), encoding="utf-8")
    materialize_interpreter_macro_context(
        run_dir=run, session_date=packet_session, macro_dir=tmp_path / "absent", prefer_run_snapshot=True,
    )
    return runs


def test_m5_manifest_rejects_interpreter_packet_from_a_different_session(tmp_path):
    # The stored TEST run has last_completed_session 2026-09-24 but a packet dated 2026-09-25.
    runs = _minimal_run(tmp_path, "20260925_061649", session="2026-09-24", packet_session="2026-09-25")
    manifest = build_final_run_manifest("20260925_061649", runs, pipeline_mode="EOD")
    env = manifest["worker3_market_environment"]
    assert env["status"] == "INVALID"
    assert "session differs" in env["error"]
    assert env["trading_authority"] is False
    assert env["packet_sha256"]


def test_m5b_manifest_accepts_session_aligned_advisory_packet(tmp_path):
    runs = _minimal_run(tmp_path, "20260926_230000", session="2026-09-25", packet_session="2026-09-25")
    manifest = build_final_run_manifest("20260926_230000", runs, pipeline_mode="EOD")
    env = manifest["worker3_market_environment"]
    assert env["status"] == "AVAILABLE"
    assert env["error"] == ""
    assert env["authority"] == "ADVISORY_ONLY"
    assert env["trading_authority"] is False
    # An empty run has no candidates; it must not read as execution-ready.
    assert manifest["run_tradeable"] is False
    assert manifest["run_tradeable_label"] != "EXECUTION_READY"


# --------------------------------------------------------------------------- M6
def test_m6_row_advisory_fields_are_display_only_and_never_invent_alignment(tmp_path):
    run = _run_with_snapshot(tmp_path, "20260925_061652", _realistic_macro())
    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-09-24", macro_dir=tmp_path / "absent", prefer_run_snapshot=True,
    )
    packet, sha = result["packet"], result["reference"]["sha256"]

    financial = advisory_fields_for_row(packet, {"ticker": "XLF", "sector": "Financials"}, packet_sha256=sha)
    tech = advisory_fields_for_row(packet, {"ticker": "NVDA", "gics_sector": "Technology"}, packet_sha256=sha)
    unmapped = advisory_fields_for_row(packet, {"ticker": "ZZZZ", "sector": ""}, packet_sha256=sha)

    assert financial["macro_sector_alignment"] == "FAVOURED"
    assert tech["macro_sector_alignment"] == "HEADWIND"
    assert unmapped["macro_sector_alignment"] == "UNMAPPED"
    for fields in (financial, tech, unmapped):
        assert fields["macro_authority"] == AUTHORITY_STATEMENT
        assert "ADVISORY_ONLY" in fields["macro_authority"]
        assert fields["macro_data_role"] == "ADVISORY_ONLY"
        assert fields["macro_packet_sha256"] == sha
        assert not (set(fields) & FORBIDDEN_AUTHORITY_KEYS)
        assert not any(key in fields for key in ("size_multiplier", "go_no_go", "final_action"))
