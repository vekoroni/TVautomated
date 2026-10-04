"""DIR-002 DWN-01/05: fresh authority and frozen-record crossover."""

import json

import pytest

from contracts.direction_governance import (
    approved_direction_policy_tuples,
    resolve_governed_direction,
    validate_direction_record,
)


def _row(authority: str = "DISCOVERY_GOVERNED") -> dict:
    return resolve_governed_direction(
        ticker="AAPL",
        run_id="20261001_010101",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="structural",
        authority=authority,
        row={
            "thesis__side": "BULL" if authority == "DISCOVERY_GOVERNED" else "",
            "vanguard_edge_direction": "PUT",
            "directional_force": -20,
        },
        decided_at_utc="2026-10-01T00:00:00+00:00",
    )


def test_fresh_discovery_governed_record_has_no_retired_votes() -> None:
    row = _row()
    assert row["final_direction"] == "CALL"
    assert row["direction_resolution_evidence_count"] == 0
    assert json.loads(row["direction_resolution_evidence_json"]) == []
    assert row["direction_resolution_call_score"] == 0
    assert row["direction_resolution_put_score"] == 0
    assert validate_direction_record(row) == (True, "DIRECTION_INTEGRITY_CONFIRMED")


def test_historical_record_retains_its_original_policy_tuple() -> None:
    historical = _row("OPTIONS_INTELLIGENCE")
    fresh = _row()
    assert historical["direction_resolution_evidence_count"] > 0
    assert historical["dir_calc_version"] == "dir_v1.2.0"
    assert historical["direction_policy_version"] == "strangle_resolution_v1.1.0"
    assert historical["direction_policy_sha256"] == "ab24f3710543dfe59d1b9b191ca8156cad9093c42e98913796befd3d414e75f1"
    assert fresh["dir_calc_version"] != historical["dir_calc_version"]
    assert validate_direction_record(historical) == (True, "DIRECTION_INTEGRITY_CONFIRMED")
    assert (fresh["dir_calc_version"], fresh["direction_policy_version"], fresh["direction_policy_sha256"]) in approved_direction_policy_tuples()
    assert (historical["dir_calc_version"], historical["direction_policy_version"], historical["direction_policy_sha256"]) in approved_direction_policy_tuples()


def test_policy_tuple_cannot_be_spliced_into_a_valid_record() -> None:
    row = _row()
    row["direction_policy_sha256"] = "0" * 64
    assert validate_direction_record(row)[0] is False


def test_old_discovery_authority_without_canonical_thesis_stays_prior_policy() -> None:
    row = resolve_governed_direction(
        ticker="AAPL",
        run_id="20261001_010101",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="old Discovery row",
        authority="DISCOVERY_GOVERNED",
        row={"vanguard_edge_direction": "PUT"},
        decided_at_utc="2026-10-01T00:00:00+00:00",
    )
    assert row["dir_calc_version"] == "dir_v1.2.0"
    assert validate_direction_record(row)[0] is True


@pytest.mark.parametrize(
    "authority,thesis_side",
    [("DISCOVERY_GOVERNED", "BUYERS"), ("OPTIONS_INTELLIGENCE", "BULL")],
)
def test_declared_thesis_cannot_fall_back_to_legacy_resolution(authority, thesis_side) -> None:
    with pytest.raises(ValueError, match="THESIS"):
        resolve_governed_direction(
            ticker="AAPL",
            run_id="20261001_010101",
            discovery_direction="CALL",
            governed_direction="CALL",
            governed_basis="test",
            authority=authority,
            row={"thesis__side": thesis_side, "vanguard_edge_direction": "PUT"},
            decided_at_utc="2026-10-01T00:00:00+00:00",
        )


def test_mixed_versions_are_not_uniform_within_one_run() -> None:
    from contracts.direction_governance import direction_policy_uniformity

    fresh = _row()
    historical = _row("OPTIONS_INTELLIGENCE")
    assert direction_policy_uniformity([fresh]) == (True, "OK")
    assert direction_policy_uniformity([historical]) == (True, "OK")
    assert direction_policy_uniformity([fresh, historical])[0] is False
