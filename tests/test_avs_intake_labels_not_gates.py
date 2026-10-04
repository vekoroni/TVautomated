"""Discovery intake (ACK 4 Oct 2026): share price, volume and ATR are labels, never reasons to drop a ticker.

"we should have the ability to trade even penny stocks if we want to." The $5-$500 price band, the 20-day
average volume, the dollar volume and the ATR floors were share-trading filters applied before any analysis
(run 20261003_213716: 433 + 773 + 287 + 15 tickers dropped unanalysed, including MSFT, META, LLY, AMAT, SMH).
Business rules:
- A ticker outside the price band, below the volume or ATR floors is analysed like any other ticker.
- What it is outside of is disclosed on the row (intake_flags, price_band).
- Hard data rules still drop: a ticker with too few bars cannot be analysed.
Supersedes the price/volume/ATR cases of tests/test_avs_dir002_eligibility_reasons.py (DSC-15).
"""
import pandas as pd
import pytest

import avshunter_discovery_ULTIMATE as discovery


class _ReachedAnalysis(Exception):
    pass


class _Engine:
    def analyze(self, *args, **kwargs):
        raise _ReachedAnalysis()


def bars(**overrides) -> pd.DataFrame:
    frame = pd.DataFrame({"open": [100.0] * 40, "high": [101.0] * 40, "low": [99.0] * 40,
                          "close": [100.0] * 40, "volume": [1_000_000] * 40})
    return frame.assign(**overrides)


@pytest.mark.parametrize(("frame", "config", "flag"), [
    (bars(open=2.0, high=2.02, low=1.98, close=2.0), {}, "PRICE_BELOW_MIN"),
    (bars(open=900.0, high=909.0, low=891.0, close=900.0), {}, "PRICE_ABOVE_MAX"),
    (bars(volume=100), {}, "AVG_VOLUME_BELOW_MIN"),
    (bars(), {"min_adv_dollars": 200_000_000}, "ADV_DOLLARS_BELOW_MIN"),
    (bars(), {"min_atr_dollars": 5.0}, "ATR_DOLLARS_BELOW_MIN"),
    (bars(), {"min_atr_pct": 5.0}, "ATR_PCT_BELOW_MIN"),
])
def test_share_filters_label_but_never_drop(frame, config, flag):
    diagnostic = {}
    with pytest.raises(_ReachedAnalysis):          # the ticker goes on to be analysed
        discovery.scan_ticker_ultimate("TEST", frame, discovery.UltimateConfig(**config),
                                       wyckoff_engine=_Engine(), eligibility_diagnostic=diagnostic)
    assert "reason_code" not in diagnostic
    assert flag in discovery.intake_flags(frame, discovery.UltimateConfig(**config))


def test_price_band_is_disclosed():
    cfg = discovery.UltimateConfig()
    assert discovery.price_band(2.0, cfg) == "BELOW_5"
    assert discovery.price_band(100.0, cfg) == "5_TO_500"
    assert discovery.price_band(900.0, cfg) == "ABOVE_500"


def test_a_clean_ticker_has_no_flags():
    assert discovery.intake_flags(bars(), discovery.UltimateConfig()) == []


def test_too_few_bars_still_drops():
    diagnostic = {}
    result = discovery.scan_ticker_ultimate("TEST", bars(), discovery.UltimateConfig(min_bars=41),
                                            wyckoff_engine=_Engine(), eligibility_diagnostic=diagnostic)
    assert result is None and diagnostic["reason_code"] == "ELIG_INSUFFICIENT_BARS"
