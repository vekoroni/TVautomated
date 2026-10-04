"""DIR-002 §4.2-4.3 / DSC-01..10, 23, 25: side evidence is built once, mirrored.

Business rules under test:
- A side-bearing structural observation is computed by one side-parameterised
  rule in log-price space, so a log-reflected chart gives exactly the
  mirrored evidence (R-2a).
- Low volume, a tie, missing bars or a short history never produce a side.
- Trend is context only and needs >= 200 completed bars.
"""
from __future__ import annotations

import ast
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import WyckoffEngine_3101_v2 as wyckoff
import wyckoff_crabel_precor_logic_v2 as precor
from WyckoffEngine_3101_v2 import side_structural_evidence
from wyckoff_crabel_precor_logic_v2 import symmetric_precor_intent

POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "config" / "dir002_side_evidence_v1.json").read_text(
        encoding="utf-8"
    )
)
MIRROR = {
    "BULL": "BEAR", "BEAR": "BULL", "SPRING": "UTAD", "UTAD": "SPRING", "SOS": "SOW",
    "SOW": "SOS", "LPS": "LPSY", "LPSY": "LPS", "SC_TEST": "BC_TEST", "BC_TEST": "SC_TEST",
    "BUY_SETUP": "SELL_SETUP", "SELL_SETUP": "BUY_SETUP", "BUYERS": "SELLERS",
    "SELLERS": "BUYERS", "ACCUMULATION": "DISTRIBUTION", "DISTRIBUTION": "ACCUMULATION",
    "SPRING_CANDIDATE": "UTAD_CANDIDATE", "UTAD_CANDIDATE": "SPRING_CANDIDATE",
    "SC": "BC", "BC": "SC",
}


def reflect(frame: pd.DataFrame, k: float = 100.0) -> pd.DataFrame:
    out = frame.copy()
    out["open"] = k * k / frame["open"]
    out["close"] = k * k / frame["close"]
    out["high"] = k * k / frame["low"]
    out["low"] = k * k / frame["high"]
    return out


def flat(n: int = 60, start: str = "2026-01-02") -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    close = 100 * close / close[-1]
    frame = pd.DataFrame({
        "date": pd.bdate_range(start, periods=n),
        "open": close * np.exp(rng.normal(0, 0.001, n)),
        "close": close,
        "volume": rng.integers(900_000, 1_100_000, n).astype(float),
    })
    frame["high"] = np.maximum(frame["open"], frame["close"]) * math.exp(0.012)
    frame["low"] = np.minimum(frame["open"], frame["close"]) * math.exp(-0.012)
    return frame


def set_bar(frame, i, o, h, l, c, v=None):
    frame.loc[i, ["open", "high", "low", "close"]] = [o, h, l, c]
    if v is not None:
        frame.loc[i, "volume"] = v


def spring_chart() -> pd.DataFrame:
    frame = flat()
    n = len(frame)
    low = float(frame["low"].iloc[n - 25:n - 4].min())
    set_bar(frame, n - 3, 99.5, 100.0, low * math.exp(-0.05), low * math.exp(-0.03))
    set_bar(frame, n - 2, low * 1.0, 101.0, low * math.exp(-0.01), 100.5)
    set_bar(frame, n - 1, 100.4, 101.2, 99.8, 100.9)
    return frame


def assert_mirrored(a: dict, b: dict, path: str = "") -> None:
    assert set(a) == set(b), path
    for key in a:
        x, y = a[key], b[key]
        if key.startswith("bull") or key.startswith("bear") or key in {"range_low", "range_high"}:
            continue
        if isinstance(x, dict):
            assert_mirrored(x, y, f"{path}.{key}")
        elif isinstance(x, float) and isinstance(y, float):
            assert math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12), f"{path}.{key}: {x} vs {y}"
        else:
            assert MIRROR.get(x, x) == y or x == y, f"{path}.{key}: {x} vs {y}"


def assert_sides_swapped(original: dict, mirrored: dict) -> None:
    for name in ("bull", "bear"):
        other = "bear" if name == "bull" else "bull"
        left, right = original[name], mirrored[other]
        assert set(left) == set(right)
        for key, value in left.items():
            if key == "event_session":
                assert value == right[key]
            elif isinstance(value, float):
                assert math.isclose(value, right[key], rel_tol=1e-9, abs_tol=1e-12), key
            else:
                assert MIRROR.get(value, value) == right[key], (name, key, value, right[key])


def test_spring_is_bull_event_and_its_reflection_is_bear_utad():
    bars = spring_chart()
    original = side_structural_evidence(bars, POLICY)
    mirrored = side_structural_evidence(reflect(bars), POLICY)
    assert original["status"] == "EVALUATED"
    assert original["bull"]["event_type"] == "SPRING"
    assert original["bull"]["event_strength"] > 0
    assert original["bear"]["event_type"] == "NONE"
    assert mirrored["bear"]["event_type"] == "UTAD"
    assert_sides_swapped(original, mirrored)


def test_upside_breakout_needs_acceptance_after_the_breakout_bar():
    frame = flat()
    n = len(frame)
    high = float(frame["high"].iloc[n - 25:n - 3].max())
    set_bar(frame, n - 2, 100.0, high * math.exp(0.06), 99.9, high * math.exp(0.055))
    set_bar(frame, n - 1, high * 1.05, high * math.exp(0.08), high * math.exp(0.03), high * math.exp(0.07))
    accepted = side_structural_evidence(frame, POLICY)
    assert accepted["bull"]["event_type"] == "SOS"
    assert side_structural_evidence(reflect(frame), POLICY)["bear"]["event_type"] == "SOW"

    unconfirmed = frame.iloc[:-1].reset_index(drop=True)
    assert side_structural_evidence(unconfirmed, POLICY)["bull"]["event_type"] == "NONE"


def test_low_volume_alone_never_produces_a_side():
    frame = flat()
    frame.loc[len(frame) - 10:, "volume"] = 200_000.0
    evidence = side_structural_evidence(frame, POLICY)
    assert evidence["bull"]["event_type"] == "NONE"
    assert evidence["bear"]["event_type"] == "NONE"


def test_selling_climax_test_mirrors_buying_climax_test():
    frame = flat()
    n = len(frame)
    # The climax defines the range low (outside the 10-bar break window); the
    # later low-volume test holds above it without breaking the range.
    set_bar(frame, n - 15, 100.0, 100.2, 93.0, 96.8, 3_000_000)
    set_bar(frame, n - 3, 96.0, 97.0, 93.6, 96.5, 400_000)
    original = side_structural_evidence(frame, POLICY)
    mirrored = side_structural_evidence(reflect(frame), POLICY)
    assert original["bull"]["event_type"] == "SC_TEST"
    assert mirrored["bear"]["event_type"] == "BC_TEST"
    assert_sides_swapped(original, mirrored)


def test_trend_needs_two_hundred_completed_bars():
    short = flat(150)
    evidence = side_structural_evidence(short, POLICY)
    assert evidence["trend_status"] == "TREND_INSUFFICIENT_HISTORY"
    assert evidence["bull"]["trend_aligned"] is False
    assert evidence["bear"]["trend_aligned"] is False

    up = flat(260)
    up["close"] = 50 * np.exp(np.linspace(0, 0.8, 260))
    up["open"] = up["close"] * math.exp(-0.002)
    up["high"] = up["close"] * math.exp(0.01)
    up["low"] = up["open"] * math.exp(-0.01)
    evidence = side_structural_evidence(up, POLICY)
    assert evidence["trend_status"] == "EVALUATED"
    assert evidence["bull"]["trend_aligned"] is True
    assert evidence["bear"]["trend_aligned"] is False
    assert side_structural_evidence(reflect(up, 60.0), POLICY)["bear"]["trend_aligned"] is True


@pytest.mark.parametrize("seed", range(12))
def test_random_charts_give_exactly_mirrored_evidence(seed):
    rng = np.random.default_rng(seed)
    n = 260
    close = 80 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    frame = pd.DataFrame({
        "date": pd.bdate_range("2025-01-02", periods=n),
        "open": close * np.exp(rng.normal(0, 0.01, n)),
        "close": close,
        "volume": rng.lognormal(13, 0.6, n),
    })
    frame["high"] = np.maximum(frame["open"], frame["close"]) * np.exp(rng.uniform(0, 0.03, n))
    frame["low"] = np.minimum(frame["open"], frame["close"]) * np.exp(-rng.uniform(0, 0.03, n))
    k = float(frame["close"].iloc[-1])
    original = side_structural_evidence(frame, POLICY)
    mirrored = side_structural_evidence(reflect(frame, k), POLICY)
    assert_sides_swapped(original, mirrored)
    assert_mirrored(original, mirrored)
    assert math.isclose(mirrored["range_low"], k * k / original["range_high"], rel_tol=1e-9)
    assert math.isclose(mirrored["range_high"], k * k / original["range_low"], rel_tol=1e-9)
    intent = symmetric_precor_intent(frame, POLICY)
    m_intent = symmetric_precor_intent(reflect(frame, k), POLICY)
    for key in ("intent", "intent_basis", "mode", "phase", "control", "primary_event", "status"):
        assert MIRROR.get(intent[key], intent[key]) == m_intent[key], key


def test_missing_or_invalid_bars_are_not_evaluated_never_zero():
    frame = flat()
    frame.loc[len(frame) - 2, "close"] = float("nan")
    evidence = side_structural_evidence(frame, POLICY)
    assert evidence["status"].startswith("NOT_EVALUATED")
    assert evidence["bull"]["control_score"] is None
    assert evidence["bear"]["event_strength"] is None
    assert side_structural_evidence(flat(15), POLICY)["status"] == "NOT_EVALUATED_INSUFFICIENT_BARS"


def test_precor_symmetric_intent_never_defaults_to_buy_or_accumulation():
    short = flat(40)
    result = symmetric_precor_intent(short, POLICY)
    assert result["intent"] == "WAIT"
    assert result["mode"] == "UNKNOWN"
    assert result["status"] == "NOT_EVALUATED_INSUFFICIENT_BARS"
    level = flat(120)
    level["close"] = 100.0
    level["open"] = 100.0
    level["high"] = 100.5
    level["low"] = 99.5
    flat_result = symmetric_precor_intent(level, POLICY)
    assert flat_result["mode"] == "UNKNOWN"
    assert flat_result["intent"] not in {"BUY_SETUP", "SELL_SETUP"}


def test_kernel_has_no_max_over_side_bearing_dicts():
    for module in (wyckoff, precor):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and (
                node.name.startswith("_side_") or node.name in {
                    "side_structural_evidence", "symmetric_precor_intent", "structural_events",
                }
            ):
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and getattr(call.func, "id", "") in {"max", "min"}:
                        assert not any(k.arg == "key" for k in call.keywords), node.name
