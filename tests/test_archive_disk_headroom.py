"""Item G (AVS-SD-MON-003 Phase 0/1 fix spec, 20 Sep 2026): archive_outputs() refuses to start
when there isn't enough disk headroom, rather than failing mid-copy.

Root cause (evidenced, run 20260919_205844, logs/orchestrator.log): Phase 10 Archive failed with
[WinError 112] partway through shutil.copytree(), after already creating the destination directory
and copying some loose files - leaving a partially-populated archive directory and no completed
archive for that run. The fix is a pre-flight check: compare the source run's size against free
space on the archive drive before writing anything, and abort loudly with the shortfall if it
would not fit - never attempt a partial copy.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import intelligent_orchestrator as orch


@pytest.fixture
def run_tree(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    output_dir = tmp_path / "output_loose"
    archive_dir = tmp_path / "archive"
    runs_dir.mkdir()
    output_dir.mkdir()
    run_id = "20260920_000000"
    run_dir = runs_dir / run_id
    run_dir.mkdir()
    (run_dir / "options").mkdir()
    (run_dir / "options" / "options_intelligence.csv").write_bytes(b"x" * 2048)
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", runs_dir, raising=False)
    monkeypatch.setattr(orch.cfg, "OUTPUT_DIR", output_dir, raising=False)
    monkeypatch.setattr(orch.cfg, "ARCHIVE_DIR", archive_dir, raising=False)
    return SimpleNamespace(run_id=run_id, run_dir=run_dir, archive_dir=archive_dir)


def test_refuses_to_start_when_free_space_is_less_than_the_run_size(run_tree):
    tiny_free_bytes = 100  # far smaller than the 2048-byte fixture file
    with patch.object(shutil, "disk_usage", return_value=(10**12, 10**12 - tiny_free_bytes, tiny_free_bytes)):
        result = orch.archive_outputs(run_tree.run_id)

    assert result is False
    # No partial archive directory left behind - the check must run before any mkdir/copy.
    assert not (run_tree.archive_dir / run_tree.run_id).exists()


def test_proceeds_and_completes_when_headroom_is_sufficient(run_tree):
    plenty_free_bytes = 10**10  # 10GB, comfortably more than the fixture run
    with patch.object(shutil, "disk_usage", return_value=(10**12, 10**12 - plenty_free_bytes, plenty_free_bytes)):
        result = orch.archive_outputs(run_tree.run_id)

    assert result is True
    dest = run_tree.archive_dir / run_tree.run_id / "runs" / run_tree.run_id
    assert (dest / "options" / "options_intelligence.csv").is_file()


def test_missing_run_directory_is_still_reported_as_aborted(run_tree):
    result = orch.archive_outputs("NOT_A_REAL_RUN_ID")
    assert result is False


# ---------------------------------------------------------------------------
# ACK, 27 Sep 2026: the archive copy is a retention record of the run's decisions and evidence,
# not of the per-ticker package files. Packages are ~85% of a run (4.85 GB of 5.9 GB), are
# reproducible from the canonical stores, and the original run keeps them for its 90-day
# retention. Archiving them doubled the disk cost of every Evening run.
# ---------------------------------------------------------------------------

@pytest.fixture
def run_tree_with_packages(run_tree):
    packages = run_tree.run_dir / "packages"
    packages.mkdir()
    (packages / "AAPL.package.json").write_bytes(b"p" * 4096)
    (packages / "index.json").write_bytes(b"{}")
    (run_tree.run_dir / "intelligence_lab").mkdir()
    (run_tree.run_dir / "intelligence_lab" / "final_opportunity_book.json").write_bytes(b"b" * 1024)
    return run_tree


def test_archive_keeps_decisions_and_evidence_but_not_the_package_files(run_tree_with_packages):
    tree = run_tree_with_packages
    plenty = 10**10
    with patch.object(shutil, "disk_usage", return_value=(10**12, 10**12 - plenty, plenty)):
        assert orch.archive_outputs(tree.run_id) is True
    dest = tree.archive_dir / tree.run_id / "runs" / tree.run_id
    assert (dest / "options" / "options_intelligence.csv").is_file()
    assert (dest / "intelligence_lab" / "final_opportunity_book.json").is_file()
    assert not (dest / "packages").exists()
    # The original run is never touched by archiving.
    assert (tree.run_dir / "packages" / "AAPL.package.json").is_file()


def test_headroom_check_measures_only_what_will_be_copied(run_tree_with_packages):
    tree = run_tree_with_packages
    # Free space covers the 3 KB of non-package files (x1.2) but not the 7 KB run including packages.
    free = int((2048 + 1024) * orch.ARCHIVE_HEADROOM_MARGIN) + 100
    with patch.object(shutil, "disk_usage", return_value=(10**12, 10**12 - free, free)):
        assert orch.archive_outputs(tree.run_id) is True


def test_bulk_diagnostic_is_lossless_compressed_but_source_and_decisions_stay(run_tree):
    from scripts.artifact_retention import read_retained_artifact
    tree = run_tree
    relative = Path("diagnostics") / f"outcome_learning_{tree.run_id}.json"
    source = tree.run_dir / relative
    source.parent.mkdir()
    source.write_bytes(b"saved historical diagnostic " * 10000)
    with patch.object(shutil, "disk_usage", return_value=(10**12, 0, 10**12)):
        assert orch.archive_outputs(tree.run_id)
    dest = tree.archive_dir / tree.run_id / "runs" / tree.run_id / relative
    assert not dest.exists()
    assert read_retained_artifact(dest) == source.read_bytes()
    assert source.exists()


def test_same_name_in_unknown_folder_is_not_excluded(run_tree):
    tree = run_tree
    source = tree.run_dir / "evidence" / f"outcome_learning_{tree.run_id}.json"
    source.parent.mkdir()
    source.write_bytes(b"unknown evidence")
    with patch.object(shutil, "disk_usage", return_value=(10**12, 0, 10**12)):
        assert orch.archive_outputs(tree.run_id)
    assert (tree.archive_dir / tree.run_id / "runs" / tree.run_id / "evidence" / source.name).read_bytes() == b"unknown evidence"


def test_rearchive_preserves_previous_snapshot_instead_of_overwriting(run_tree):
    tree = run_tree
    source = tree.run_dir / "options" / "options_intelligence.csv"
    with patch.object(shutil, "disk_usage", return_value=(10**12, 0, 10**12)):
        assert orch.archive_outputs(tree.run_id)
        source.write_bytes(b"new revision")
        assert orch.archive_outputs(tree.run_id)
    original = tree.archive_dir / tree.run_id / "runs" / tree.run_id / "options" / source.name
    assert original.read_bytes() == b"x" * 2048
    revisions = list((tree.archive_dir / tree.run_id / "revisions").iterdir())
    assert len(revisions) == 1
    assert (revisions[0] / "runs" / tree.run_id / "options" / source.name).read_bytes() == b"new revision"


def test_run_age_never_authorises_whole_folder_removal(run_tree, monkeypatch):
    tree = run_tree
    monkeypatch.setattr(orch.cfg, "RUNS_RETENTION_DAYS", 0)
    orch.prune_old_runs()
    assert (tree.run_dir / "options" / "options_intelligence.csv").exists()
