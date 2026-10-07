"""Business rules for the liquidity monitor (Colab "Global Macro + Repo Money Flow", v3.7).

The thresholds were written in basis points and dollars; FRED publishes HY/IG OAS in percent
(BAMLH0A0HYM2 3.10 = 310 bp) and the overnight reverse repo in $ billions (RRPONTSYD).
1. Credit stress reads HY OAS in percent against the same 350 / 500 / 800 bp levels.
2. Repo stress, the liquidity regime and the RRP label read RRP in $ billions against the same
   $1.2T / $1.5T / $2.0T levels.
3. The VIX legs come from Cboe's published daily history (Polygon index data is outside the
   plan); the parser reads both Cboe file shapes.
No network, no live data.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_liquidity_monitor_v3_7.py"


def _module():
    spec = importlib.util.spec_from_file_location("liquidity_monitor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # must not fetch, exit or write on import
    return module


@pytest.mark.parametrize("hy_oas_pct, expected", [
    (3.10, "NORMAL"),      # 310 bp — the 6 Oct 2026 print
    (3.60, "WIDE"),        # 360 bp > 350
    (5.50, "ELEVATED"),    # 550 bp > 500
    (8.50, "EXTREME"),     # 850 bp > 800
    (None, "MISSING"),
])
def test_credit_stress_reads_hy_oas_in_percent_against_the_bp_levels(hy_oas_pct, expected):
    assert _module().credit_stress_label(hy_oas_pct) == expected


@pytest.mark.parametrize("rrp_bn, rrp_z, expected", [
    (2500.0, math.nan, 90),    # $2.5T > $2.0T
    (1300.0, math.nan, 60),    # $1.3T > $1.2T
    (5.2, math.nan, 20),       # $5.2bn — near-exhausted facility
    (5.2, 2.5, 90),            # the z-score leg still applies
    (None, 2.5, 20),           # no RRP print -> no score lift (v3.5 behaviour)
])
def test_repo_stress_reads_rrp_in_billions(rrp_bn, rrp_z, expected):
    assert _module().repo_stress_score(rrp_bn, rrp_z) == expected


def test_liquidity_regime_reads_rrp_in_billions():
    m = _module()
    assert m.liquidity_regime(change_walcl=0.0002, latest_rrp_bn=2500.0, days_since=0) == "Draining"
    assert m.liquidity_regime(change_walcl=0.002, latest_rrp_bn=5.2, days_since=3) == "Flooded (3d old)"
    assert m.liquidity_regime(change_walcl=0.002, latest_rrp_bn=1600.0, days_since=0) == "Neutral"
    assert m.liquidity_regime(change_walcl=-0.001, latest_rrp_bn=5.2, days_since=9) == "Draining (STALE - 9d old)"


def test_rrp_label_converts_billions_to_trillions():
    m = _module()
    assert m.rrp_trillions_label(2500.0) == "2.50T"
    assert m.rrp_trillions_label(5.2) == "0.01T"
    assert m.rrp_trillions_label(None) == "N/A"


def test_cboe_history_parses_both_published_file_shapes():
    m = _module()
    ohlc = "DATE,OPEN,HIGH,LOW,CLOSE\n10/02/2026,15.1,15.9,14.8,15.31\n10/05/2026,15.3,15.8,15.0,15.52\n"
    single = "DATE,VVIX\n10/02/2026,84.10\n10/05/2026,85.46\n"
    vix = m.parse_cboe_history(ohlc, "VIX")
    vvix = m.parse_cboe_history(single, "VVIX")
    assert vix.index[-1] == pd.Timestamp("2026-10-05") and vix.iloc[-1] == 15.52
    assert vvix.index[-1] == pd.Timestamp("2026-10-05") and vvix.iloc[-1] == 85.46
