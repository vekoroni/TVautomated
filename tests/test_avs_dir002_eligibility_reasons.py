"""DIR-002 DSC-15: an eligibility exclusion is not a missing signal.

Superseded in part 4 Oct 2026 (ACK): price, volume, dollar-volume and ATR are now labels, not exclusions
(tests/test_avs_intake_labels_not_gates.py). Only the hard data rule remains an exclusion here.
"""

import pandas as pd
import pytest

import avshunter_discovery_ULTIMATE as discovery


def bars() -> pd.DataFrame:
    return pd.DataFrame({
        "open": [100.0] * 40,
        "high": [101.0] * 40,
        "low": [99.0] * 40,
        "close": [100.0] * 40,
        "volume": [1_000_000] * 40,
    })


@pytest.mark.parametrize(
    ("change", "config", "reason"),
    [
        (lambda frame: frame, {"min_bars": 41}, "ELIG_INSUFFICIENT_BARS"),
    ],
)
def test_each_ticker_eligibility_exclusion_has_its_own_reason(change, config, reason):
    diagnostic = {}
    result = discovery.scan_ticker_ultimate(
        "TEST", change(bars()), discovery.UltimateConfig(**config),
        wyckoff_engine=None, eligibility_diagnostic=diagnostic,
    )
    assert result is None
    assert diagnostic["reason_code"] == reason
