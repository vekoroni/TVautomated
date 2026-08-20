# test_vanguard_contract.py
"""
Unit tests (pytest) for Vanguard contract validation.
Run:
    pytest -q
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from vanguard_contract import (
    VanguardInput, RegimeSnapshot, validate_vanguard_input, CONTRACT_VERSION
)


def _make_daily_df(rows: int = 900) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp.utcnow().normalize(), periods=rows, tz="UTC")
    df = pd.DataFrame({
        "open": np.linspace(100, 120, rows),
        "high": np.linspace(101, 121, rows),
        "low": np.linspace(99, 119, rows),
        "close": np.linspace(100, 120, rows) + np.random.normal(0, 0.5, rows),
        "volume": np.random.randint(1_000_000, 3_000_000, rows),
    }, index=idx)
    return df


def _fresh_regime() -> RegimeSnapshot:
    as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return RegimeSnapshot(
        as_of_utc=as_of,
        regime_state="Transitional",
        dir_bias="Selective Risk-On",
        vol_mode="Rising but contained",
        regime_drift_status="Stable",
        macro_conviction="Medium"
    )


def test_valid_input_passes():
    vin = VanguardInput(
        contract_version=CONTRACT_VERSION,
        ticker="AAPL",
        daily_df=_make_daily_df(900),
        intraday_df=None,
        regime=_fresh_regime(),
        metadata={"source": "polygon", "refresh_status": "ok"}
    )
    res = validate_vanguard_input(vin)
    assert res.ok is True
    assert res.score >= 90
    assert len(res.issues) == 0


def test_bad_ticker_rejected():
    vin = VanguardInput(
        contract_version=CONTRACT_VERSION,
        ticker="SHOP.TO",
        daily_df=_make_daily_df(900),
        intraday_df=None,
        regime=_fresh_regime(),
        metadata={}
    )
    res = validate_vanguard_input(vin)
    assert res.ok is False
    assert any(i.field == "ticker" for i in res.issues)


def test_stale_regime_rejected():
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    regime = RegimeSnapshot(
        as_of_utc=old,
        regime_state="Transitional",
        dir_bias="Selective Risk-On",
        vol_mode="Rising but contained",
        regime_drift_status="Stable",
        macro_conviction="Medium"
    )
    vin = VanguardInput(
        contract_version=CONTRACT_VERSION,
        ticker="MSFT",
        daily_df=_make_daily_df(900),
        intraday_df=None,
        regime=regime,
        metadata={}
    )
    res = validate_vanguard_input(vin)
    assert res.ok is False
    assert any(i.code == "REGIME_STALE" for i in res.issues)


def test_insufficient_history_rejected():
    vin = VanguardInput(
        contract_version=CONTRACT_VERSION,
        ticker="NVDA",
        daily_df=_make_daily_df(300),  # too short
        intraday_df=None,
        regime=_fresh_regime(),
        metadata={}
    )
    res = validate_vanguard_input(vin)
    assert res.ok is False
    assert any(i.code == "DAILY_DF_TOO_SHORT" for i in res.issues)


def test_nans_in_recent_window_rejected():
    df = _make_daily_df(900)
    df.loc[df.index[-10:], "close"] = np.nan
    vin = VanguardInput(
        contract_version=CONTRACT_VERSION,
        ticker="AMD",
        daily_df=df,
        intraday_df=None,
        regime=_fresh_regime(),
        metadata={}
    )
    res = validate_vanguard_input(vin)
    assert res.ok is False
    assert any(i.code == "DAILY_DF_NANS_IN_CRITICAL_WINDOW" for i in res.issues)
