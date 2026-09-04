from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.apply_ev3_authority import apply_overlay


def _artifacts(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    options = tmp_path / "options.csv"
    results = tmp_path / "results.parquet"
    status = tmp_path / "status.json"
    cache = tmp_path / "governed.parquet"
    pd.DataFrame([{"ticker": "GOOD"}, {"ticker": "BAD"}]).to_csv(options, index=False)
    pd.DataFrame(
        [
            {
                "source_row_index": 0,
                "ticker": "GOOD",
                "ev3_status": "EVALUATED_SHADOW",
                "ev3_absolute_state": "POSITIVE_UNVALIDATED",
                "ev3_reason_code": "SHADOW_ONLY",
                "ev3_ev_lower_bound_return": 0.08,
            },
            {
                "source_row_index": 1,
                "ticker": "BAD",
                "ev3_status": "EVALUATED_SHADOW",
                "ev3_absolute_state": "NEGATIVE_EV",
                "ev3_reason_code": "SHADOW_ONLY",
                "ev3_ev_lower_bound_return": -0.10,
            },
        ]
    ).to_parquet(results, index=False)
    cache.write_bytes(b"governed-fixture")
    status.write_text(
        json.dumps(
            {
                "technical_health": "PASS",
                "health": "SHADOW_COMPLETE",
                "evaluation_clock_mode": "REALTIME_STRICT",
                "system_defects": {},
                "unclassified_rejections": {},
                "evaluation_coverage": 1.0,
                "adjudication_coverage": 1.0,
                "barrier_cache_path": str(cache),
            }
        ),
        encoding="utf-8",
    )
    return options, results, status, cache


def test_shadow_overlay_is_visible_but_cannot_grant_ev_eligibility(tmp_path: Path) -> None:
    options, results, status, cache = _artifacts(tmp_path)
    outcome = apply_overlay(
        options, results, status, options,
        authority_requested=False, governed_final_cache=cache,
    )
    frame = pd.read_csv(options)
    assert outcome["production_authority"] is False
    assert set(frame["ev3_authority_mode"]) == {"PRODUCTION_EVIDENCE_ADVISORY"}
    assert set(frame["ev3_monetisation_permission"]) == {"ADVISORY_ONLY"}
    assert not frame["ev3_ev_eligible"].astype(bool).any()
    assert options.with_name("options_pre_ev3_authority.csv").exists()
    apply_overlay(
        options, results, status, options,
        authority_requested=False, governed_final_cache=cache,
    )
    reapplied = pd.read_csv(options)
    assert not reapplied.columns.duplicated().any()


def test_authority_request_is_retired_and_all_states_remain_advisory(tmp_path: Path) -> None:
    options, results, status, cache = _artifacts(tmp_path)
    outcome = apply_overlay(
        options, results, status, options,
        authority_requested=True, governed_final_cache=cache,
    )
    frame = pd.read_csv(options)
    assert outcome["production_authority"] is False
    assert set(frame["ev3_authority_mode"]) == {"PRODUCTION_EVIDENCE_ADVISORY"}
    assert set(frame["ev3_monetisation_permission"]) == {"ADVISORY_ONLY"}
    assert not frame["ev3_ev_eligible"].astype(bool).any()
    assert "EV_AUTHORITY_RETIRED_ADVISORY_ONLY" in outcome["authority_activation_reasons"]


def test_requested_authority_fails_closed_when_readiness_gate_fails(tmp_path: Path) -> None:
    options, results, status, cache = _artifacts(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["adjudication_coverage"] = 0.50
    status.write_text(json.dumps(payload), encoding="utf-8")
    outcome = apply_overlay(
        options, results, status, options,
        authority_requested=True, governed_final_cache=cache,
    )
    frame = pd.read_csv(options)
    assert outcome["production_authority"] is False
    assert "ADJUDICATION_COVERAGE_BELOW_95_PERCENT" in outcome["authority_activation_reasons"]
    assert "EV_AUTHORITY_RETIRED_ADVISORY_ONLY" in outcome["authority_activation_reasons"]
    assert set(frame["ev3_authority_mode"]) == {"PRODUCTION_EVIDENCE_ADVISORY"}
    assert not frame["ev3_ev_eligible"].astype(bool).any()
