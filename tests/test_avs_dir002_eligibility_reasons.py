"""DIR-002 DSC-15: an eligibility exclusion is not a missing signal."""

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
        (lambda frame: frame.assign(close=2.0), {}, "ELIG_PRICE_RANGE"),
        (lambda frame: frame.assign(volume=100), {}, "ELIG_AVG_VOLUME"),
        (lambda frame: frame, {"min_adv_dollars": 200_000_000}, "ELIG_ADV_DOLLARS_OPTION_PROXY"),
        (lambda frame: frame, {"min_atr_dollars": 5.0}, "ELIG_ATR_DOLLARS_OPTION_PROXY"),
        (lambda frame: frame, {"min_atr_pct": 5.0}, "ELIG_ATR_PCT_OPTION_PROXY"),
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
