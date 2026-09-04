from __future__ import annotations

import json
from pathlib import Path

import intelligent_orchestrator as orchestrator


def test_run_meta_status_is_advanced_atomically(tmp_path: Path, monkeypatch) -> None:
    run_id = "20260830_120000"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    meta_path = run_dir / "run_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "canonical_run_id": run_id,
                "run_status": "IN_PROGRESS",
                "pipeline_mode": "EOD",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)

    orchestrator._update_run_meta_status(
        run_id,
        "COMPLETED",
        pipeline_mode="EOD",
    )

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["canonical_run_id"] == run_id
    assert payload["run_status"] == "COMPLETED"
    assert payload["pipeline_mode"] == "EOD"
    assert payload["status_updated_at_utc"]
    assert not meta_path.with_suffix(".json.tmp").exists()


def test_run_meta_rejects_unknown_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(orchestrator.cfg, "RUNS_DIR", tmp_path)
    try:
        orchestrator._update_run_meta_status("run", "TRADEABLE")
    except ValueError as error:
        assert "invalid run status" in str(error)
    else:
        raise AssertionError("unknown run status must fail closed")
