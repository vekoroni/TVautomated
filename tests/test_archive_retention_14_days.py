"""ACK 14 Nov: artifact retention supersedes age-only archive-folder deletion.

Older decisions, books, unknown evidence and manual folders must survive.
The old 14-day constant remains compatibility metadata, not delete authority.
"""
from __future__ import annotations

import intelligent_orchestrator as orch


def _tree(tmp_path, monkeypatch, names):
    archive = tmp_path / "archive"
    for name in names:
        (archive / name / "runs").mkdir(parents=True)
        (archive / name / "runs" / "book.csv").write_text("x")
    monkeypatch.setattr(orch.cfg, "ARCHIVE_DIR", archive, raising=False)
    return archive


def test_retention_window_is_14_days():
    assert orch.cfg.ARCHIVE_RETENTION_DAYS == 14


def test_old_archive_evidence_is_not_deleted_merely_due_to_age(tmp_path, monkeypatch):
    archive = _tree(tmp_path, monkeypatch, ["20260918_210000", "20260919_210000", "20260920_210000",
                                            "20261003_213716"])
    orch.prune_old_archives("20261003_213716")
    assert sorted(p.name for p in archive.iterdir()) == ["20260918_210000", "20260919_210000", "20260920_210000", "20261003_213716"]


def test_folders_not_named_as_runs_are_kept(tmp_path, monkeypatch):
    archive = _tree(tmp_path, monkeypatch, ["manual_notes", "20250101_000000"])
    orch.prune_old_archives("20261003_213716")
    assert sorted(p.name for p in archive.iterdir()) == ["20250101_000000", "manual_notes"]


def test_unreadable_current_run_id_deletes_nothing(tmp_path, monkeypatch):
    archive = _tree(tmp_path, monkeypatch, ["20250101_000000"])
    orch.prune_old_archives("not_a_run")
    assert [p.name for p in archive.iterdir()] == ["20250101_000000"]
