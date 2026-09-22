"""Business-rule tests for synchronized advisory macro publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _payload(*, regime: str = "TRANSITIONAL") -> dict:
    return {
        "contract_version": "macro_contract_v1_0",
        "macro_authority": "ADVISORY_ONLY",
        "regime_state": regime,
        "report_date": "2026-09-20",
    }


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_macro_publication_repairs_missing_and_stale_projections(tmp_path):
    """Every active macro reader must receive the exact authoritative bytes."""

    from canonical_data.macro_publication import (
        macro_projection_paths,
        publish_macro_projections,
        validate_macro_projection_alignment,
    )

    authority = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    _write(authority, _payload())
    paths = macro_projection_paths(tmp_path)
    _write(paths[0], _payload(regime="STALE"))

    before = validate_macro_projection_alignment(authority, paths)
    assert before["aligned"] is False
    assert set(before["stale_or_missing"]) == {str(path.resolve()) for path in paths}

    receipt = publish_macro_projections(authority, paths)
    after = validate_macro_projection_alignment(authority, paths)

    expected_hash = hashlib.sha256(authority.read_bytes()).hexdigest()
    assert after["aligned"] is True
    assert receipt["authority"] == "ADVISORY_ONLY"
    assert receipt["sha256"] == expected_hash
    assert all(path.read_bytes() == authority.read_bytes() for path in paths)


def test_macro_publication_rejects_non_advisory_or_non_object_payload(tmp_path):
    """Projection cannot launder malformed or decision-authoritative content."""

    from canonical_data.macro_publication import publish_macro_projections

    authority = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    projection = tmp_path / "data" / "macro" / authority.name

    _write(authority, ["not", "a", "macro", "object"])
    with pytest.raises(ValueError, match="JSON object"):
        publish_macro_projections(authority, (projection,))

    _write(authority, {**_payload(), "macro_authority": "CAPITAL_AUTHORITY"})
    with pytest.raises(ValueError, match="ADVISORY_ONLY"):
        publish_macro_projections(authority, (projection,))


def test_rotation_patch_publishes_all_macro_projections(tmp_path, monkeypatch):
    """A post-build rotation annotation must not leave one reader behind."""

    import rapid_rotation_flag as rrf
    from canonical_data.macro_publication import macro_projection_paths

    authority = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    _write(authority, _payload())
    monkeypatch.setattr(rrf, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(rrf, "MACRO_JSON_PATH", authority)

    assert rrf.patch_macro_json({"rotation_override": "NORMAL"}) is True
    assert all(path.read_bytes() == authority.read_bytes() for path in macro_projection_paths(tmp_path))


def test_rotation_provider_key_is_environment_only(monkeypatch):
    """A missing credential remains unavailable and is never embedded in source."""

    import rapid_rotation_flag as rrf

    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    result = rrf.get_polygon_change("SPY")
    assert result["status"] == "CREDENTIAL_UNAVAILABLE"
    assert result["pct_change"] is None


def test_evening_preflight_rejects_divergent_macro_projection(tmp_path, monkeypatch):
    """A future evening run must detect divergence before reading stale advice."""

    import intelligent_orchestrator as orchestrator
    from canonical_data.macro_publication import macro_projection_paths

    authority = tmp_path / "dropbox" / "macro" / "macro_intelligence_latest.json"
    payload = {
        **_payload(),
        "risk_on_switch": "NEUTRAL",
        "dir_bias": "NEUTRAL",
        "regime_drift_status": "STABLE",
        "conviction_score": 0.5,
        "macro_conviction": 0.5,
        "liquidity_status": "STABLE",
        "volatility_mode": "NORMAL",
        "vix_contango": 1.0,
        "as_of_utc": "2026-09-20T00:00:00Z",
    }
    _write(authority, payload)
    projections = macro_projection_paths(tmp_path)
    _write(projections[0], payload)
    _write(projections[1], {**payload, "regime_state": "STALE"})
    monkeypatch.setattr(orchestrator.cfg, "MACRO_DIR", authority.parent)
    monkeypatch.setattr(orchestrator.cfg, "MACRO_FILE", authority)

    ok, message, selected = orchestrator.check_macro_json()

    assert ok is False
    assert selected is None
    assert "not synchronized" in message
