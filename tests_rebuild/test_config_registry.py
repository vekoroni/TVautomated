"""P0-2 configuration registry: schema, append-only history, resolution, authority."""

from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from avshunter.config import (
    AuthorityState,
    ConfigError,
    ConfigRegistry,
    ValidationState,
)
from avshunter.config.adapters import load_lock, load_documents, update_lock, write_snapshot
from avshunter.config.model import SCHEMA_VERSION


def _entry(**overrides):
    base = {
        "config_key": "market_data.example_threshold",
        "version": 1,
        "value": 0.5,
        "value_type": "NUMBER",
        "unit": "fraction",
        "effective_from": "2026-09-17",
        "validation_state": "PROVISIONAL",
        "business_owner": "ACK",
        "approval_id": "ACK-20260916-TEST",
        "rationale": "test",
        "evidence_ref": None,
        "provenance": "NEW",
        "recorded_at_utc": "2026-09-16T00:00:00Z",
    }
    base.update(overrides)
    return base


def _document(*entries, prefixes=("market_data.",)):
    return {
        "schema_version": SCHEMA_VERSION,
        "context": "c1_market_data",
        "key_prefixes": list(prefixes),
        "entries": list(entries),
    }


# --- schema ---------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"unit": "furlongs"}, "not in vocabulary"),
        ({"value": "high"}, "does not match value_type"),
        ({"value_type": "INTEGER", "value": True}, "does not match value_type"),
        ({"approval_id": ""}, "approval_id"),
        ({"validation_state": "VALIDATED", "evidence_ref": None}, "requires evidence_ref"),
        ({"provenance": "copied"}, "provenance"),
        ({"config_key": "Bad Key"}, "invalid config_key"),
        ({"version": 0}, "positive integer"),
        ({"rationale": " "}, "rationale"),
    ],
)
def test_invalid_entries_are_rejected(overrides, message):
    with pytest.raises(ConfigError, match=message):
        ConfigRegistry.from_documents([_document(_entry(**overrides))])


def test_missing_field_is_rejected():
    raw = _entry()
    del raw["unit"]
    with pytest.raises(ConfigError, match="missing fields"):
        ConfigRegistry.from_documents([_document(raw)])


def test_key_must_belong_to_document_context():
    with pytest.raises(ConfigError, match="does not belong"):
        ConfigRegistry.from_documents([_document(_entry(config_key="ranking.margin"))])


def test_effective_from_must_be_a_session():
    with pytest.raises(ConfigError, match="not an XNYS session"):
        ConfigRegistry.from_documents([_document(_entry(effective_from="2026-09-19"))])  # Saturday


# --- history ----------------------------------------------------------------

def test_versions_must_be_contiguous():
    with pytest.raises(ConfigError, match="without gaps"):
        ConfigRegistry.from_documents([_document(_entry(version=2))])


def test_later_version_needs_later_effective_date():
    with pytest.raises(ConfigError, match="must be after"):
        ConfigRegistry.from_documents([
            _document(_entry(), _entry(version=2, value=0.6, effective_from="2026-09-17"))
        ])


def test_duplicate_entry_rejected():
    with pytest.raises(ConfigError, match="duplicate"):
        ConfigRegistry.from_documents([_document(_entry(), _entry())])


# --- resolution -------------------------------------------------------------

def test_resolution_follows_effective_dates_and_replay_keeps_old_value():
    registry = ConfigRegistry.from_documents([
        _document(_entry(), _entry(version=2, value=0.7, effective_from="2026-09-22"))
    ])
    assert registry.resolve(date(2026, 9, 17)).get("market_data.example_threshold").value == 0.5
    assert registry.resolve(date(2026, 9, 21)).get("market_data.example_threshold").value == 0.5
    later = registry.resolve(date(2026, 9, 22)).get("market_data.example_threshold")
    assert (later.value, later.version) == (0.7, 2)


def test_unresolvable_key_raises_never_defaults():
    registry = ConfigRegistry.from_documents([_document(_entry())])
    with pytest.raises(ConfigError, match="unresolvable"):
        registry.resolve(date(2026, 9, 16)).get("market_data.example_threshold")
    with pytest.raises(ConfigError, match="unresolvable"):
        registry.resolve(date(2026, 9, 17)).get("market_data.not_registered")


def test_resolve_requires_session_date():
    registry = ConfigRegistry.from_documents([_document(_entry())])
    with pytest.raises(ConfigError, match="not an XNYS session"):
        registry.resolve(date(2026, 9, 20))


def test_retired_value_cannot_be_used():
    registry = ConfigRegistry.from_documents([
        _document(_entry(), _entry(version=2, validation_state="RETIRED", effective_from="2026-09-18"))
    ])
    with pytest.raises(ConfigError, match="RETIRED"):
        registry.resolve(date(2026, 9, 18)).get("market_data.example_threshold")


def test_authority_coupling():
    registry = ConfigRegistry.from_documents([
        _document(
            _entry(),
            _entry(config_key="market_data.validated_threshold", validation_state="VALIDATED",
                   evidence_ref="Enhancements/replications/R1/REPORT.md"),
        )
    ])
    snapshot = registry.resolve(date(2026, 9, 17))
    assert snapshot.get("market_data.example_threshold", authority=AuthorityState.SHADOW).value == 0.5
    with pytest.raises(ConfigError, match="only use VALIDATED"):
        snapshot.get("market_data.example_threshold", authority=AuthorityState.AUTHORITATIVE)
    with pytest.raises(ConfigError, match="only use VALIDATED"):
        snapshot.require_validated("market_data.example_threshold")
    validated = snapshot.require_validated("market_data.validated_threshold")
    assert validated.validation_state is ValidationState.VALIDATED


def test_snapshot_is_deterministic_and_value_sensitive():
    first = ConfigRegistry.from_documents([_document(_entry())]).resolve(date(2026, 9, 17))
    again = ConfigRegistry.from_documents([_document(_entry())]).resolve(date(2026, 9, 17))
    changed = ConfigRegistry.from_documents([_document(_entry(value=0.51))]).resolve(date(2026, 9, 17))
    assert first.snapshot_id == again.snapshot_id
    assert first.snapshot_id != changed.snapshot_id


# --- lock (append-only) -------------------------------------------------------

def test_lock_detects_modified_and_removed_entries():
    registry = ConfigRegistry.from_documents([_document(_entry())])
    lock = registry.lock_manifest()
    with pytest.raises(ConfigError, match="modified"):
        ConfigRegistry.from_documents([_document(_entry(value=0.9))], lock)
    with pytest.raises(ConfigError, match="removed"):
        ConfigRegistry.from_documents(
            [_document(_entry(config_key="market_data.other"))], lock
        )


def test_lock_allows_appending_new_versions():
    registry = ConfigRegistry.from_documents([_document(_entry())])
    lock = registry.lock_manifest()
    extended = ConfigRegistry.from_documents(
        [_document(_entry(), _entry(version=2, value=0.8, effective_from="2026-09-18"))], lock
    )
    assert len(extended.entries()) == 2


def test_update_lock_refuses_edits(tmp_path):
    (tmp_path / "c1.json").write_text(json.dumps(_document(_entry())), encoding="utf-8")
    update_lock(tmp_path)
    edited = _document(_entry(value=0.99))
    (tmp_path / "c1.json").write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(ConfigError, match="append-only"):
        update_lock(tmp_path)


def test_write_snapshot_round_trip(tmp_path):
    snapshot = ConfigRegistry.from_documents([_document(_entry())]).resolve(date(2026, 9, 17))
    path = write_snapshot(snapshot, tmp_path / "run" / "config_snapshot.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["snapshot_id"] == snapshot.snapshot_id
    assert payload["values"][0]["config_key"] == "market_data.example_threshold"


# --- the committed registry ---------------------------------------------------

def test_committed_registry_is_valid_and_locked():
    documents = load_documents()
    registry = ConfigRegistry.from_documents(documents, load_lock())
    assert registry.lock_manifest() == load_lock()
    snapshot = registry.resolve(date(2026, 9, 17))
    assert snapshot.get("market_data.capture_coverage_threshold").value == 0.95
    assert snapshot.get("run.production_gate_failure_mode").value == "DOWNGRADE_TO_RESEARCH"
    assert all(item.validation_state is ValidationState.PROVISIONAL for item in snapshot.values)


def test_committed_documents_not_mutated_by_loading():
    documents = load_documents()
    before = copy.deepcopy(documents)
    ConfigRegistry.from_documents(documents, load_lock())
    assert documents == before
