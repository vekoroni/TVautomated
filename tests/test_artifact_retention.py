"""Storage safety: lossless artifacts, no age-only evidence deletion."""
import gzip
import json
from pathlib import Path

import pytest

from scripts.artifact_retention import archive_diagnostic, compact_archives, read_retained_artifact


RUN = "20261111_231951"


def tree(tmp_path):
    runs = tmp_path / "runs"
    archives = tmp_path / "archive"
    source = runs / RUN / "diagnostics" / f"outcome_learning_{RUN}.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"evidence":[' + b'"historical",' * 10000 + b'null]}')
    destination = archives / RUN / "runs" / RUN / "diagnostics" / source.name
    destination.parent.mkdir(parents=True)
    return runs, archives, source, destination


def test_duplicate_archive_is_compressed_without_losing_any_evidence(tmp_path):
    runs, archives, source, destination = tree(tmp_path)
    destination.write_bytes(source.read_bytes())
    original = source.read_bytes()
    report = compact_archives(archives)
    assert report["status"] == "COMPLETE"
    assert not destination.exists()
    assert source.read_bytes() == original
    assert read_retained_artifact(destination) == original
    assert gzip.decompress(destination.with_suffix(".json.gz").read_bytes()) == original
    receipt = json.loads((archives / RUN / "artifact_retention.json").read_text())
    assert receipt["artifacts"][0]["sha256"]


def test_differing_historical_archive_preserves_its_own_bytes(tmp_path):
    runs, archives, source, destination = tree(tmp_path)
    destination.write_bytes(b'{"historical_revision":1}')
    compact_archives(archives)
    assert read_retained_artifact(destination) == b'{"historical_revision":1}'
    assert b"historical_revision" not in source.read_bytes()


def test_corrupt_existing_compressed_keeper_never_deletes_original(tmp_path):
    _, archives, _, destination = tree(tmp_path)
    destination.write_bytes(b"important historical evidence")
    destination.with_suffix(".json.gz").write_bytes(b"corrupt")
    with pytest.raises((OSError, ValueError)):
        compact_archives(archives)
    assert destination.read_bytes() == b"important historical evidence"


def test_existing_gzip_with_other_content_is_not_overwritten(tmp_path):
    _, archives, _, destination = tree(tmp_path)
    destination.write_bytes(b"current")
    destination.with_suffix(".json.gz").write_bytes(gzip.compress(b"different"))
    with pytest.raises(ValueError, match="conflict"):
        compact_archives(archives)
    assert destination.read_bytes() == b"current"
    assert gzip.decompress(destination.with_suffix(".json.gz").read_bytes()) == b"different"


def test_unknown_artifacts_and_live_databases_are_never_touched(tmp_path):
    _, archives, _, destination = tree(tmp_path)
    other = destination.parent / "unrecognised.json"
    other.write_bytes(b"keep")
    database = archives / RUN / "historical.sqlite"
    database.write_bytes(b"database")
    compact_archives(archives)
    assert other.read_bytes() == b"keep"
    assert database.read_bytes() == b"database"


def test_new_archives_write_lossless_compressed_diagnostics_directly(tmp_path):
    _, archives, source, destination = tree(tmp_path)
    result = archive_diagnostic(source, destination, archives / RUN)
    assert result["compressed_bytes"] < result["original_bytes"]
    assert not destination.exists()
    assert read_retained_artifact(destination) == source.read_bytes()


def test_manual_archive_folders_are_not_processed(tmp_path):
    manual = tmp_path / "manual" / "runs" / RUN / "diagnostics"
    manual.mkdir(parents=True)
    file = manual / f"outcome_learning_{RUN}.json"
    file.write_bytes(b"manual evidence")
    compact_archives(tmp_path)
    assert file.exists()


def test_symlinked_artifact_fails_closed(tmp_path):
    _, archives, source, destination = tree(tmp_path)
    try:
        destination.symlink_to(source)
    except OSError:
        pytest.skip("Windows symlink permission unavailable")
    with pytest.raises(ValueError):
        compact_archives(archives)
    assert source.exists()


def test_plan_does_not_write_or_remove_anything(tmp_path):
    _, archives, source, destination = tree(tmp_path)
    destination.write_bytes(source.read_bytes())
    before = sorted(str(p.relative_to(archives)) for p in archives.rglob("*"))
    report = compact_archives(archives, execute=False)
    assert report["status"] == "PLAN"
    assert sorted(str(p.relative_to(archives)) for p in archives.rglob("*")) == before
    assert destination.exists()


def test_path_traversal_is_rejected_before_writes(tmp_path):
    _, archives, source, _ = tree(tmp_path)
    with pytest.raises(ValueError):
        archive_diagnostic(source, archives / ".." / "escape" / "diagnostics" / source.name, archives)
    assert not (tmp_path / "escape").exists()


def test_failed_receipt_write_keeps_original(tmp_path, monkeypatch):
    import scripts.artifact_retention as retention
    _, archives, source, destination = tree(tmp_path)
    destination.write_bytes(source.read_bytes())
    def failed(*args, **kwargs):
        raise OSError("receipt unavailable")
    monkeypatch.setattr(retention, "_atomic_json", failed)
    with pytest.raises(OSError, match="receipt"):
        compact_archives(archives)
    assert destination.read_bytes() == source.read_bytes()


def test_restoring_tampered_evidence_fails_hash_verification(tmp_path):
    _, archives, source, destination = tree(tmp_path)
    destination.write_bytes(source.read_bytes())
    compact_archives(archives)
    destination.with_suffix(".json.gz").write_bytes(gzip.compress(b"tampered"))
    with pytest.raises(ValueError, match="verification"):
        read_retained_artifact(destination)


def test_archive_lock_blocks_concurrent_compaction(tmp_path):
    _, archives, source, destination = tree(tmp_path)
    destination.write_bytes(source.read_bytes())
    (archives / RUN / ".artifact-retention.lock").write_text("another worker")
    with pytest.raises(FileExistsError):
        compact_archives(archives)
    assert destination.read_bytes() == source.read_bytes()


def test_repeated_compaction_is_idempotent(tmp_path):
    _, archives, source, destination = tree(tmp_path)
    destination.write_bytes(source.read_bytes())
    compact_archives(archives)
    before = destination.with_suffix(".json.gz").read_bytes()
    result = compact_archives(archives)
    assert result["records"] == []
    assert destination.with_suffix(".json.gz").read_bytes() == before
