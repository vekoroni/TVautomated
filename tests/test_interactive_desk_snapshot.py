"""Frozen Evening parent for the Lab-to-Interpreter report workflow."""

from __future__ import annotations

import json

import pytest


def _run(tmp_path, *, mode="EOD", status="COMPLETED"):
    root = tmp_path / "20260922_000106"
    lab = root / "intelligence_lab"
    lab.mkdir(parents=True)
    (root / "final_run_manifest.json").write_text(json.dumps({
        "run_id": root.name, "pipeline_mode": mode,
        "pipeline_technical_health": "PASS", "fatal_flags": [],
        "created_at_utc": "2026-09-22T01:00:00+00:00",
    }), encoding="utf-8")
    (root / "run_meta.json").write_text(json.dumps({
        "canonical_run_id": root.name, "pipeline_mode": mode, "run_status": status,
    }), encoding="utf-8")
    (lab / f"final_opportunity_book_{root.name}.json").write_text(json.dumps({
        "run_id": root.name, "candidate_count": 2,
        "rows": [
            {"run_id": root.name, "ticker": "AAA", "direction": "CALL", "target_price": 110},
            {"run_id": root.name, "ticker": "BBB", "direction": "PUT", "contract_symbol": ""},
        ],
    }), encoding="utf-8")
    return root


def test_evening_snapshot_survives_mutable_morning_files(tmp_path):
    from pipeline_interpreter.interactive_snapshot import load_eod_snapshot, publish_eod_snapshot

    root = _run(tmp_path)
    receipt = publish_eod_snapshot(root)
    assert receipt["run_id"] == root.name
    assert receipt["authority"] == "ADVISORY_ONLY"
    assert [row["ticker"] for row in load_eod_snapshot(root)["rows"]] == ["AAA", "BBB"]
    # Morning rewrites the live files for the same run; the Evening parent is unchanged.
    (root / "final_run_manifest.json").write_text('{"pipeline_mode":"MORNING_VALIDATION"}')
    (root / "intelligence_lab" / f"final_opportunity_book_{root.name}.json").write_text('{}')
    assert [row["ticker"] for row in load_eod_snapshot(root)["rows"]] == ["AAA", "BBB"]
    assert publish_eod_snapshot(root) == receipt


@pytest.mark.parametrize("mode,status", [("MORNING_VALIDATION", "COMPLETED"), ("EOD", "IN_PROGRESS")])
def test_snapshot_rejects_nonterminal_or_non_eod_source(tmp_path, mode, status):
    from pipeline_interpreter.interactive_snapshot import SnapshotError, publish_eod_snapshot

    with pytest.raises(SnapshotError):
        publish_eod_snapshot(_run(tmp_path, mode=mode, status=status))


def test_snapshot_detects_tampered_frozen_book(tmp_path):
    from pipeline_interpreter.interactive_snapshot import SnapshotError, load_eod_snapshot, publish_eod_snapshot

    root = _run(tmp_path)
    publish_eod_snapshot(root)
    target = root / "interpreter" / "eod_review_v1" / "book.json.gz"
    with target.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(SnapshotError):
        load_eod_snapshot(root)


def test_nonfatal_degraded_evening_is_preserved_with_health_disclosure(tmp_path):
    from pipeline_interpreter.interactive_snapshot import publish_eod_snapshot

    root = _run(tmp_path)
    manifest_path = root / "final_run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["pipeline_technical_health"] = "DEGRADED"
    manifest_path.write_text(json.dumps(manifest))
    receipt = publish_eod_snapshot(root)
    assert receipt["eod_technical_health"] == "DEGRADED"
