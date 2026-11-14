"""Offline native event timestamp compatibility and exact-byte intake regression."""
import copy
import hashlib
import json
from datetime import datetime, timezone

import pytest
from contracts.macro_feed_delivery import source_observation_time
from contracts.macro_export_receipt import receive_export


def packet(cutoff="2026-11-10T21:34:00Z"):
    return {"schema_version": "avshunter_us_economic_event_impact_v1_0",
            "run_context": {"manual_review_required": True, "automatic_execution_enabled": False},
            "events": [{"event_id": "BOWMAN", "event_name": "Bowman outlook",
                        "market_perception": {"observation_window": {"information_cutoff_utc": cutoff}}}]}


def test_nested_cutoff_and_equivalent_direct_alias_preserve_source_clock():
    value = packet()
    original = copy.deepcopy(value)
    assert source_observation_time("events", value) == "2026-11-10T21:34:00Z"
    assert value == original
    value["events"][0]["information_cutoff_utc"] = "2026-11-10T16:34:00-05:00"
    assert source_observation_time("events", value) == "2026-11-10T16:34:00-05:00"


@pytest.mark.parametrize("cutoff", ["garbage", "2026-11-10T21:34:00"])
def test_invalid_or_timezone_free_nested_cutoff_rejected(cutoff):
    with pytest.raises(ValueError):
        source_observation_time("events", packet(cutoff))


def test_conflicting_event_aliases_rejected():
    value = packet()
    value["events"][0]["information_cutoff_utc"] = "2026-11-10T20:30:00Z"
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_TIMESTAMP_CONFLICT"):
        source_observation_time("events", value)


def test_missing_event_cutoff_never_uses_release_date_or_receipt_time():
    value = packet(None)
    value["generated_from_report_date"] = "2026-11-10"
    value["events"][0]["release_time"] = {"utc": "2026-11-10T20:30:00Z"}
    assert source_observation_time("events", value) is None
    value["events"].append(packet()["events"][0])
    assert source_observation_time("events", value) is None


def test_multiple_events_use_latest_complete_source_cutoff():
    value = packet()
    value["events"].append(packet("2026-11-10T22:00:00Z")["events"][0])
    assert source_observation_time("events", value) == "2026-11-10T22:00:00Z"


def test_exact_byte_intake_and_out_of_order_preserve_accepted_archive(tmp_path):
    config = {"expected_feeds": ["events"], "max_packet_bytes": 10485760,
              "state_directory": "state", "macro_directory": "macro",
              "default_manifest": "incoming/manifest.json"}
    path = tmp_path / "source.json"
    raw = (json.dumps(packet(), indent=2) + "\n").encode()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    def receive():
        return receive_export(path, root=tmp_path, config=config, source_chat="producer",
                              source_message="message", now=datetime(2026, 11, 11, tzinfo=timezone.utc))
    receipt = receive()
    assert receipt["delivery"]["status"] == "COMPLETE"
    assert (tmp_path / "state/archive" / (digest + ".json")).read_bytes() == raw
    registry_path = tmp_path / "state/accepted.json"
    accepted = registry_path.read_bytes()
    assert json.loads(accepted)["events"]["source_observation_at_utc"] == "2026-11-10T21:34:00Z"
    for cutoff, error in [("2026-11-10T20:30:00Z", "SOURCE_OBSERVATION_OUT_OF_ORDER"),
                          (None, "SOURCE_OBSERVATION_TIMESTAMP_MISSING")]:
        path.write_text(json.dumps(packet(cutoff)))
        rejected = receive()["delivery"]
        assert rejected["feeds"]["events"]["error"] == error
        assert registry_path.read_bytes() == accepted


@pytest.mark.parametrize("location", ["context", "direct", "nested"])
def test_explicit_utc_text_cutoff_normalises_without_mutation(location):
    value = packet(None)
    text = "2026-11-11 06:57:40 UTC"
    if location == "context":
        value["run_context"]["information_cutoff_utc"] = text
    elif location == "direct":
        value["events"][0]["information_cutoff_utc"] = text
    else:
        value["events"][0]["market_perception"]["observation_window"]["information_cutoff_utc"] = text
    original = copy.deepcopy(value)
    assert source_observation_time("events", value) == "2026-11-11T06:57:40Z"
    assert value == original


@pytest.mark.parametrize("text", ["2026-11-11 06:57:40", "2026-11-11 06:57:40 GMT",
    "2026-11-11 06:57:40 EST", "2026-11-11 06:57 UTC", "2026-11-11 06:57:40 utc",
    "2026-11-11 06:57:40 UTC ", "2026-02-30 06:57:40 UTC", "2026-11-11 24:00:00 UTC"])
def test_utc_compatibility_rejects_other_spellings_and_invalid_dates(text):
    value = packet()
    value["run_context"]["information_cutoff_utc"] = text
    with pytest.raises(ValueError):
        source_observation_time("events", value)


def test_utc_text_and_iso_aliases_compare_by_instant():
    value = packet("2026-11-11 06:57:40 UTC")
    value["events"][0]["information_cutoff_utc"] = "2026-11-11T01:57:40-05:00"
    assert source_observation_time("events", value) == "2026-11-11T01:57:40-05:00"
    value["events"][0]["information_cutoff_utc"] = "2026-11-11T06:57:41Z"
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_TIMESTAMP_CONFLICT"):
        source_observation_time("events", value)


def test_generic_envelope_parser_still_rejects_utc_text():
    from contracts.macro_feed_delivery import _stamp
    with pytest.raises(ValueError):
        _stamp("2026-11-11 06:57:40 UTC")


def test_utc_text_intake_preserves_bytes_and_rejects_stale_source(tmp_path):
    config = {"expected_feeds": ["events"], "max_packet_bytes": 10485760,
              "state_directory": "state", "macro_directory": "macro",
              "default_manifest": "incoming/manifest.json"}
    path = tmp_path / "source.json"
    def receive(cutoff):
        value = packet(cutoff)
        value["run_context"]["information_cutoff_utc"] = cutoff
        raw = (json.dumps(value, indent=2) + "\n").encode()
        path.write_bytes(raw)
        result = receive_export(path, root=tmp_path, config=config, source_chat="producer",
            source_message="message", now=datetime(2026, 11, 11, 12, tzinfo=timezone.utc))
        return result, raw
    for cutoff in ["2026-11-11 00:21:35 UTC", "2026-11-11 06:57:40 UTC"]:
        result, raw = receive(cutoff)
        assert result["delivery"]["status"] == "COMPLETE"
        digest = hashlib.sha256(raw).hexdigest()
        assert (tmp_path / "state/archive" / (digest + ".json")).read_bytes() == raw
    registry = tmp_path / "state/accepted.json"
    accepted = registry.read_bytes()
    assert json.loads(accepted)["events"]["source_observation_at_utc"] == "2026-11-11T06:57:40Z"
    result, _ = receive("2026-11-11 00:21:35 UTC")
    assert result["delivery"]["feeds"]["events"]["error"] == "SOURCE_OBSERVATION_OUT_OF_ORDER"
    assert registry.read_bytes() == accepted
