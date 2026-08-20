from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_options_intelligence_nan_tier_defaults_to_tier_2():
    import avshunter_options_intelligence as oi

    assert oi._safe_int(float("nan"), 2) == 2
    ctx = oi.parse_structural_context(
        pd.Series(
            {
                "ticker": "NANT",
                "tier": float("nan"),
                "phase": "C",
                "precor_intent": "BUY_NOW",
                "spot_price": 100.0,
            }
        )
    )
    assert ctx["tier"] == 2


def test_actuarial_lookup_respects_cache_catalyst_vocabulary_none():
    builder_path = Path(r"C:\Users\ACKVerissimo\vanguard\actuarial_cache_builder.py")
    spec = importlib.util.spec_from_file_location("actuarial_cache_builder_regression", builder_path)
    acb = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(acb)

    state_key = "NORMAL|SIDEWAYS|NEUTRAL|MODERATE|ACCUMULATION|TRANSITIONAL|SIDEWAYS_RANGING|NONE|MID"
    cache = pd.DataFrame(
        [
            {
                "state_key": state_key,
                "sample_size": 1234,
                "valid": True,
                "expected_move_5d": 0.01,
                "expected_move_10d": 0.02,
                "expected_move_20d": 0.03,
                "win_rate_5d": 0.55,
                "win_rate_10d": 0.56,
                "win_rate_20d": 0.57,
                "risk_5d": -0.01,
                "risk_10d": -0.02,
                "risk_20d": -0.03,
                "efficiency_10d": 1.1,
                "vol_5d": 0.2,
                "vol_10d": 0.25,
                "vol_20d": 0.3,
                "avg_days_to_10pct": 8.0,
                "cache_built_at": "test",
            }
        ]
    )

    # Runtime callers may still send DATA_WEAK; the lookup must adapt to the
    # cache vocabulary instead of forcing every no-catalyst row into no_match.
    state = {
        "vol_regime": "NORMAL",
        "trend_direction": "SIDEWAYS",
        "structure_quality": "NEUTRAL",
        "adx_bucket": "MODERATE",
        "wyckoff_phase_bucket": "ACCUMULATION",
        "macro_regime": "TRANSITIONAL",
        "trend_maturity": "SIDEWAYS_RANGING",
        "catalyst_proximity": "DATA_WEAK",
        "atr_pct_bucket": "MID",
    }
    result = acb.lookup_state(state, cache)

    assert result.no_match is False
    assert result.matched_key == state_key
    assert result.sample_size == 1234
