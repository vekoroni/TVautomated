"""Regression coverage for the 25 September macro publication handoff failure."""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import intelligent_orchestrator as orchestrator
from canonical_data.macro_publication import (
    macro_projection_paths,
    publish_macro_projections,
    validate_macro_projection_alignment,
)


def test_evening_annotations_change_only_run_scoped_macro(tmp_path, monkeypatch):
    authority = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    authority.parent.mkdir(parents=True)
    authority.write_text(json.dumps({
        "contract_version": "macro_contract_v1_0",
        "macro_authority": "ADVISORY_ONLY",
        "regime_state": "TRANSITIONAL",
    }), encoding="utf-8")
    publish_macro_projections(authority)
    original_bytes = authority.read_bytes()
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path / "runs")

    runtime = orchestrator._run_scoped_macro_copy("20260925_230000", authority)
    amended = json.loads(runtime.read_text(encoding="utf-8"))
    amended["extras"] = {"bond_macro": {"flag": "PARTIAL"}}
    runtime.write_text(json.dumps(amended), encoding="utf-8")

    assert authority.read_bytes() == original_bytes
    assert validate_macro_projection_alignment(authority)["aligned"] is True
    assert json.loads(runtime.read_text(encoding="utf-8"))["extras"]["bond_macro"]


def test_neutral_advisory_fallback_satisfies_pin_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator.cfg, "BASE_DIR", tmp_path)
    monkeypatch.setattr(orchestrator.cfg, "OUTPUT_DIR", tmp_path / "data" / "output")
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path / "data" / "output" / "runs")
    source = tmp_path / "fallback.json"
    payload = orchestrator._neutral_macro_payload()
    source.write_text(json.dumps(payload), encoding="utf-8")

    assert payload["contract_version"] == "macro_contract_v1_0"
    assert payload["macro_availability"] == "UNAVAILABLE_NEUTRAL_FALLBACK"
    assert payload["macro_authority"] == "ADVISORY_ONLY"
    assert orchestrator.pin_run_directory("20260925_230001", source) is True
    pinned = json.loads((orchestrator.cfg.RUNS_DIR / "20260925_230001" /
                         "macro_snapshot.json").read_text(encoding="utf-8"))
    assert pinned["macro_availability"] == "UNAVAILABLE_NEUTRAL_FALLBACK"


def test_evening_uses_run_scoped_macro_for_horizon_router():
    source = inspect.getsource(orchestrator.evening_workflow)
    assert "_run_scoped_macro_copy(session_id, macro_path)" in source
    assert "run_horizon_router(macro_path, canonical_run_id)" in source
    assert "run_horizon_router(cfg.MACRO_FILE" not in source
    assert source.index("MACRO_PUBLICATION_PREFLIGHT_FAILED") < source.index(
        "synchronise_completed_session_gex")


def test_divergent_macro_aborts_before_provider_acquisition(tmp_path, monkeypatch):
    import orchestrator.completed_session_gex as completed_gex

    authority = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    authority.parent.mkdir(parents=True)
    authority.write_text(json.dumps({
        "contract_version": "macro_contract_v1_0", "macro_authority": "ADVISORY_ONLY",
    }), encoding="utf-8")
    publish_macro_projections(authority)
    projection = macro_projection_paths(tmp_path)[0]
    projection.write_text('{"stale": true}', encoding="utf-8")
    monkeypatch.setattr(orchestrator.cfg, "MACRO_DIR", authority.parent)
    monkeypatch.setattr(orchestrator.cfg, "MACRO_FILE", authority)
    called = []
    monkeypatch.setattr(completed_gex, "synchronise_completed_session_gex",
                        lambda **_kwargs: called.append(True))

    result = orchestrator.evening_workflow(
        run_id="20260925_230002", data_mode="AUTO",
        as_of_utc=datetime(2026, 9, 25, 22, 0, tzinfo=timezone.utc),
    )

    assert result is False
    assert called == []
