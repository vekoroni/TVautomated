from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from market_structure.service import calculate_market_structure_evidence


def _evidence(run_id: str) -> dict:
    bars = pd.DataFrame(
        [
            {
                "timestamp_utc": "2026-08-28T13:30:00Z",
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.1,
                "volume": 1000,
                "session_segment": "REGULAR",
                "vwap_canonical": 100.0,
            }
        ]
    )
    return calculate_market_structure_evidence(
        ticker="AAA",
        session_date=date(2026, 8, 28),
        run_id=run_id,
        bars=bars,
        exchange_tick=0.01,
        atr14=2.0,
        regular_open_utc=datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc),
        governed_direction="CALL",
        input_dataset_ids=("DATASET-A", "DATASET-B"),
        input_hashes=("HASH-A", "HASH-B"),
    )


def test_evidence_id_is_sha256_and_cross_run_content_stable() -> None:
    first = _evidence("RUN-1")
    second = _evidence("RUN-2")
    assert len(first["ms_evidence_id"]) == 64
    int(first["ms_evidence_id"], 16)
    assert first["ms_evidence_id"] == second["ms_evidence_id"]


def test_ordered_input_dataset_ids_change_evidence_identity() -> None:
    first = _evidence("RUN-1")
    bars = pd.DataFrame(
        [{
            "timestamp_utc": "2026-08-28T13:30:00Z",
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.1,
            "volume": 1000,
            "session_segment": "REGULAR",
            "vwap_canonical": 100.0,
        }]
    )
    reversed_ids = calculate_market_structure_evidence(
        ticker="AAA",
        session_date=date(2026, 8, 28),
        run_id="RUN-1",
        bars=bars,
        exchange_tick=0.01,
        atr14=2.0,
        regular_open_utc=datetime(2026, 8, 28, 13, 30, tzinfo=timezone.utc),
        governed_direction="CALL",
        input_dataset_ids=("DATASET-B", "DATASET-A"),
        input_hashes=("HASH-B", "HASH-A"),
    )
    assert first["ms_evidence_id"] != reversed_ids["ms_evidence_id"]
