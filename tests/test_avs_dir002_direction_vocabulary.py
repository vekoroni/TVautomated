"""DIR-002 DWN-08: direction parsing must not infer a side from prose."""

import pytest

from domain.thesis_direction import normalise_direction


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CALL", "CALL"),
        ("PUT", "PUT"),
        ("BULL", "CALL"),
        ("BEAR", "PUT"),
        ("BUY", "CALL"),
        ("SELL", "PUT"),
        ("LONG", "CALL"),
        ("SHORT", "PUT"),
        ("BUY_SETUP", "CALL"),
        ("SELL_SETUP", "PUT"),
        ("BULLISH", "CALL"),
        ("BEARISH", "PUT"),
        ("STRADDLE", "NON_DIRECTIONAL"),
        ("TRANSITION", "NON_DIRECTIONAL"),
        ("BULL|BEAR", "UNRESOLVED"),
        ("BUYERS", "UNRESOLVED"),
        ("INPUT_MISSING", "UNRESOLVED"),
        ("CALL_PENDING", "UNRESOLVED"),
        ("LONG_PUT", "UNRESOLVED"),
    ],
)
def test_exact_direction_vocabulary(raw, expected):
    assert normalise_direction(raw) == expected


def test_legacy_nondirectional_mapping_remains_explicit():
    assert normalise_direction("TRANSITION", strangle_for_non_directional=True) == "STRANGLE"
    assert normalise_direction("BULL|BEAR", strangle_for_non_directional=True) == "UNRESOLVED"
