from __future__ import annotations

import pandas as pd

from scripts.promote_ev3_barrier_cache import validate_candidate
from vanguard.ev3_stage0 import EV3_BARRIER_SCHEMA_VERSION


def _candidate() -> pd.DataFrame:
    rows = []
    for target in (0.10, 0.20):
        for stop in (0.05, 0.10):
            rows.append(
                {
                    "state_key": "A|B|C|D|E|F|G",
                    "direction": "CALL",
                    "horizon_sessions": 10,
                    "target_distance_fraction": target,
                    "stop_distance_fraction": stop,
                    "p_target_first": 0.50,
                    "p_stop_first": 0.30,
                    "p_timeout": 0.20,
                    "n_effective": 100,
                    "schema_version": EV3_BARRIER_SCHEMA_VERSION,
                    "calculation_version": "fixture-v1",
                }
            )
    return pd.DataFrame(rows)


def test_cache_promotion_validator_requires_complete_unique_exhaustive_grid() -> None:
    audit = validate_candidate(
        _candidate(), targets=(0.10, 0.20), stops=(0.05, 0.10), horizons=(10,),
    )
    assert audit["status"] == "PASS"
    assert audit["rows"] == 4
    assert audit["duplicates"] == 0


def test_cache_promotion_validator_rejects_incomplete_grid() -> None:
    incomplete = _candidate().iloc[:-1].copy()
    try:
        validate_candidate(
            incomplete, targets=(0.10, 0.20), stops=(0.05, 0.10), horizons=(10,),
        )
    except ValueError as exc:
        assert "complete grid" in str(exc)
    else:
        raise AssertionError("incomplete cache unexpectedly passed promotion validation")
