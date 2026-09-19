"""F7 (ACK, 19 Sep 2026): delta-weighted options flow is computed from real chain data.

Deep dive: compute_delta_weighted_oi was called throughout avshunter_options_intelligence.py
(dw_call_exposure_m, dw_put_exposure_m, dw_ratio, dw_signal, dw_pcr_vol) but was never defined.
The call site's broad `except Exception: dw_data = {}` swallowed the resulting NameError silently,
so every row reported "OPTIONS_CHAIN_VOLUME_NOT_AVAILABLE" and fell back to OI-only PCR even on
tickers where chain_snapshots.volume was genuinely populated (~50% of contracts, per the audit).
"""
from __future__ import annotations

import pandas as pd

import scripts.avshunter_options_intelligence as oi


def _chain(rows):
    return pd.DataFrame(rows)


def test_function_exists_and_is_wired_at_the_call_site():
    assert hasattr(oi, "compute_delta_weighted_oi")
    import inspect
    call_site = inspect.getsource(oi)
    block = call_site[call_site.index("Delta-weighted OI flow"): call_site.index("Delta-weighted OI flow") + 300]
    assert "compute_delta_weighted_oi(chain, spot)" in block


def test_volume_pcr_uses_real_printed_volume_not_a_bucket_default():
    chain = _chain([
        {"right": "C", "open_interest": 1000, "delta": 0.40, "volume": 500},
        {"right": "P", "open_interest": 1000, "delta": -0.40, "volume": 1500},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=100.0)
    assert result["dw_pcr_vol"] == 3.0  # 1500 put volume / 500 call volume, from real printed volume


def test_delta_weighted_ratio_differs_from_plain_oi_pcr_when_deltas_differ():
    # Equal open interest both sides, but puts carry much larger delta magnitude -
    # a delta-weighted ratio must diverge from the flat 1.0 an OI-only PCR would report.
    chain = _chain([
        {"right": "C", "open_interest": 1000, "delta": 0.10, "volume": None},
        {"right": "P", "open_interest": 1000, "delta": -0.80, "volume": None},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=50.0)
    assert result["dw_ratio"] == 8.0  # (0.80*1000) / (0.10*1000)
    assert result["dw_signal"] == "BEARISH"


def test_no_printed_volume_anywhere_reports_unavailable_not_fabricated():
    chain = _chain([
        {"right": "C", "open_interest": 500, "delta": 0.35, "volume": None},
        {"right": "P", "open_interest": 500, "delta": -0.35, "volume": None},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=75.0)
    assert result["dw_pcr_vol"] is None
    status = (
        'OK' if result.get('dw_pcr_vol') is not None else 'OI_ONLY_NO_INTRADAY_VOLUME'
    )
    assert status == 'OI_ONLY_NO_INTRADAY_VOLUME'


def test_empty_chain_returns_unknown_without_raising():
    result = oi.compute_delta_weighted_oi(pd.DataFrame(), spot=100.0)
    assert result["dw_pcr_vol"] is None
    assert result["dw_signal"] == "UNKNOWN"
