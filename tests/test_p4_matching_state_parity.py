"""Phase 4 / RC03-RC19: the live matching state means what the v7 database meant (one owner: actuarial_core_v7).

Business rule (R2 one owner per fact; training-serving parity): every dimension Vanguard uses to match history
is computed live by the same function that labelled the v7 database. Phase 4 measured, on run 20261006_060401,
live vs v7 agreement of 75/200 for structure_quality (live WEAK on all 200), 131/200 trend_direction and
104/200 trend_maturity. The fast last-bar mode must give exactly the database's values.
"""
import numpy as np
import pandas as pd

from vanguard.core.actuarial_core_v7 import calculate_core_state, compute_technicals
from vanguard.layer2_statistical.state_calculator import StateVectorCalculator, db_consistent_core_dims
from vanguard.schemas.input_schema import TechnicalData

DIMS = ("vol_regime", "trend_direction", "trend_maturity", "structure_quality", "phase_v2", "momentum_bucket",
        "location_bucket")


def _bars(n=420, seed=11, drift=0.0005):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.018, n)))
    spread = close * 0.012
    return pd.DataFrame({"date": pd.bdate_range("2024-06-03", periods=n).strftime("%Y-%m-%d"),
                         "open": close, "high": close + spread, "low": close - spread, "close": close,
                         "volume": rng.integers(5e5, 2e6, n).astype(float)})


def test_last_rank_only_mode_gives_the_databases_last_row():
    df = _bars()
    full, fast = compute_technicals(df), compute_technicals(df, last_rank_only=True)
    for col in ("atr_percentile_252", "bb_percentile_252"):
        assert fast[col].iloc[-1] == full[col].iloc[-1]


def test_live_matching_dims_equal_the_v7_state_on_the_same_bars():
    for seed, drift in ((11, 0.0005), (5, -0.001), (9, 0.0)):
        df = _bars(seed=seed, drift=drift)
        tech = compute_technicals(df)
        expected = calculate_core_state(tech, len(tech) - 1)
        got = db_consistent_core_dims(df)
        assert {d: got[d] for d in DIMS} == {d: expected[d] for d in DIMS}


def test_state_calculator_applies_the_v7_dims_and_labels_the_basis():
    df = _bars(seed=5, drift=-0.001)
    trend = {"direction": "DOWN", "maturity": "MIDDLE"}
    structure = {"quality": "WEAK"}
    StateVectorCalculator()._apply_matching_parity(TechnicalData(ohlcv=df, atr_current=1.0), trend, structure)
    v7 = db_consistent_core_dims(df)
    assert (trend["direction"], trend["maturity"], structure["quality"]) == (
        v7["trend_direction"], v7["trend_maturity"], v7["structure_quality"])
    assert structure["matching_state_basis"] == "V7_CORE_STATE"
    assert structure["legacy_auction_structure_quality"] == "WEAK"


def test_without_enough_bars_the_legacy_rule_stays_and_says_so():
    trend, structure = {"direction": "UP", "maturity": "EARLY"}, {"quality": "WEAK"}
    StateVectorCalculator()._apply_matching_parity(TechnicalData(atr_current=1.0), trend, structure)
    assert structure["matching_state_basis"] == "LEGACY_RUNTIME_RULE_BARS_INSUFFICIENT"
    assert trend["direction"] == "UP"
