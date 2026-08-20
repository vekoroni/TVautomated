from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vanguard.physics_state_engine import (  # noqa: E402
    PHYSICS_FIELDS,
    append_physics_fields_from_source,
    calculate_market_physics,
    enrich_with_market_physics,
)


def _base(**overrides):
    row = {
        "ticker": "AAPL",
        "atr_percentile": 20,
        "iv_rank": 25,
        "adx_14": 35,
        "return_5d": 0.03,
        "return_10d": 0.04,
        "trend_direction": "UP",
        "vwap_bias": "ABOVE",
        "volume_ratio": 1.4,
        "structure_quality": "STRONG",
        "phase_v2": "MARKUP",
        "macro_regime_label": "RISK_ON",
        "ticker_sector_alignment": "ALIGNED",
        "layer2__adjusted_prob_target_hit": 0.58,
        "contract_spread_pct": 0.04,
        "avg_volume": 3_000_000,
    }
    row.update(overrides)
    return row


def test_physics_engine_returns_all_required_fields_for_normal_row() -> None:
    out = calculate_market_physics(_base())
    for field in PHYSICS_FIELDS:
        assert field in out
        assert out[field] not in ("", None)


def test_high_compression_bullish_force_low_entropy_upside_expansion() -> None:
    out = calculate_market_physics(_base(atr_percentile=8, iv_rank=10, trend_direction="UP", vwap_bias="ABOVE"))
    assert out["hidden_state_label"] == "COMPRESSED_BULLISH_FORCE"
    assert out["state_transition_label"] == "BALANCE_TO_UPSIDE_EXPANSION"


def test_high_compression_bearish_force_low_entropy_downside_expansion() -> None:
    out = calculate_market_physics(_base(
        atr_percentile=8,
        iv_rank=10,
        return_5d=-0.04,
        return_10d=-0.05,
        trend_direction="DOWN",
        vwap_bias="BELOW",
        macro_regime_label="RISK_OFF",
    ))
    assert out["hidden_state_label"] == "COMPRESSED_BEARISH_FORCE"
    assert out["state_transition_label"] == "BALANCE_TO_DOWNSIDE_EXPANSION"


def test_high_entropy_weak_force_no_transition_edge() -> None:
    out = calculate_market_physics(_base(
        atr_percentile=100,
        iv_rank=100,
        adx_14=0,
        return_5d=0,
        return_10d=0,
        trend_direction="",
        vwap_bias="",
        macro_regime_label="",
        ticker_sector_alignment="",
        structure_quality="",
        phase_v2="",
    ))
    assert out["hidden_state_label"] == "HIGH_ENTROPY_CHOP"
    assert out["state_transition_label"] == "NO_TRANSITION_EDGE"


def test_high_inertia_bullish_force_continuation_up() -> None:
    out = calculate_market_physics(_base(atr_percentile=70, iv_rank=50, adx_14=90, trend_direction="UP"))
    assert out["state_transition_label"] == "CONTINUATION_UP"


def test_high_inertia_bearish_force_continuation_down() -> None:
    out = calculate_market_physics(_base(
        atr_percentile=70,
        iv_rank=50,
        adx_14=90,
        return_5d=-0.03,
        return_10d=-0.04,
        trend_direction="DOWN",
        vwap_bias="BELOW",
        macro_regime_label="RISK_OFF",
    ))
    assert out["state_transition_label"] == "CONTINUATION_DOWN"


def test_high_friction_penalises_but_does_not_delete_signal() -> None:
    df = pd.DataFrame([_base(ticker="FRIC", contract_spread_pct=0.30, avg_volume=100_000)])
    out = enrich_with_market_physics(df)
    assert len(out) == 1
    assert out.loc[0, "ticker"] == "FRIC"
    assert out.loc[0, "liquidity_friction_score"] >= 70
    assert out.loc[0, "physics_state_id"]


def test_physics_fields_are_appended_to_vanguard_output_shape() -> None:
    df = pd.DataFrame([_base(existing_col="KEEP_ME")])
    out = enrich_with_market_physics(df)
    assert "existing_col" in out.columns
    assert out.loc[0, "existing_col"] == "KEEP_ME"
    assert all(field in out.columns for field in PHYSICS_FIELDS)


def test_physics_fields_survive_handoff_into_eil_enriched_shape() -> None:
    source = enrich_with_market_physics(pd.DataFrame([_base(ticker="AAPL")]))
    target = pd.DataFrame([{"ticker": "AAPL", "eil_v3_verdict": "PASS"}])
    out = append_physics_fields_from_source(target, source)
    assert out.loc[0, "physics_state_id"] == source.loc[0, "physics_state_id"]
    assert out.loc[0, "state_transition_label"] == source.loc[0, "state_transition_label"]


def test_no_existing_columns_removed() -> None:
    df = pd.DataFrame([_base(ticker="AAPL", custom_baton="PRESERVE")])
    before = set(df.columns)
    out = enrich_with_market_physics(df)
    assert before.issubset(set(out.columns))
    assert out.loc[0, "custom_baton"] == "PRESERVE"


def _run_direct() -> None:
    tests = [obj for name, obj in globals().items() if name.startswith("test_") and callable(obj)]
    for test in tests:
        test()
    print(f"market_physics tests passed: {len(tests)}")


if __name__ == "__main__":
    _run_direct()
