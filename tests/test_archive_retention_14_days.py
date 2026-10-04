"""Archive retention (ACK 4 Oct 2026: "set a retention rule of 14 day and delete folders in the archive").

Phase 10 copied every run into data/archive and nothing ever removed it (8.2 GB of duplicates of runs that
still sat in data/output/runs). Business rules:
- After archiving, archive folders for runs more than 14 calendar days before the current run are deleted.
- The window is measured from the current run's date, not the wall clock, so a re-run gives the same result.
- Folders that are not named as a run are never touched.
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


def test_archives_older_than_14_days_are_deleted(tmp_path, monkeypatch):
    archive = _tree(tmp_path, monkeypatch, ["20260918_210000", "20260919_210000", "20260920_210000",
                                            "20261003_213716"])
    orch.prune_old_archives("20261003_213716")
    assert sorted(p.name for p in archive.iterdir()) == ["20260919_210000", "20260920_210000", "20261003_213716"]


def test_folders_not_named_as_runs_are_kept(tmp_path, monkeypatch):
    archive = _tree(tmp_path, monkeypatch, ["manual_notes", "20250101_000000"])
    orch.prune_old_archives("20261003_213716")
    assert [p.name for p in archive.iterdir()] == ["manual_notes"]


def test_unreadable_current_run_id_deletes_nothing(tmp_path, monkeypatch):
    archive = _tree(tmp_path, monkeypatch, ["20250101_000000"])
    orch.prune_old_archives("not_a_run")
    assert [p.name for p in archive.iterdir()] == ["20250101_000000"]
