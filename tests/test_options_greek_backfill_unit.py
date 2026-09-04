from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class _Normal:
    @staticmethod
    def pdf(value):
        arr = np.asarray(value, dtype=float)
        return np.exp(-0.5 * arr**2) / math.sqrt(2.0 * math.pi)

    @staticmethod
    def cdf(value):
        arr = np.asarray(value, dtype=float)
        erf = np.vectorize(math.erf, otypes=[float])
        return 0.5 * (1.0 + erf(arr / math.sqrt(2.0)))


def _load_backfill(solved_iv: float = 0.30):
    source = (
        ROOT / "scripts" / "avshunter_options_intelligence.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "backfill_greeks_vectorised"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {
        "pd": pd,
        "np": np,
        "norm": _Normal,
        "RISK_FREE_RATE": 0.04,
        "solve_iv": lambda *_args, **_kwargs: solved_iv,
    }
    exec(compile(module, str(ROOT / "scripts" / "avshunter_options_intelligence.py"), "exec"), namespace)
    return namespace["backfill_greeks_vectorised"]


def test_missing_iv_is_solved_without_overwriting_vendor_greeks() -> None:
    backfill = _load_backfill()
    frame = pd.DataFrame(
        [
            {
                "underlying_price": 100.0,
                "strike": 100.0,
                "dte": 30,
                "right": "C",
                "mark": 2.50,
                "bid": 2.40,
                "ask": 2.60,
                "implied_vol": np.nan,
                "gamma": 0.021,
                "delta": 0.51,
                "theta": -0.04,
                "vega": 0.11,
            }
        ]
    )

    result = backfill(frame)

    assert result.loc[0, "implied_vol"] == 0.30
    assert result.loc[0, "implied_vol_source"] == "BSM_SOLVED_FROM_MARK_V1"
    assert result.loc[0, "gamma"] == 0.021
    assert result.loc[0, "delta"] == 0.51
    assert result.loc[0, "theta"] == -0.04
    assert result.loc[0, "vega"] == 0.11


def test_missing_greeks_are_filled_from_existing_iv() -> None:
    backfill = _load_backfill()
    frame = pd.DataFrame(
        [
            {
                "underlying_price": 100.0,
                "strike": 105.0,
                "dte": 30,
                "right": "P",
                "mark": 3.00,
                "bid": 2.90,
                "ask": 3.10,
                "implied_vol": 0.25,
                "gamma": np.nan,
                "delta": np.nan,
                "theta": np.nan,
                "vega": np.nan,
            }
        ]
    )

    result = backfill(frame)

    assert result.loc[0, "implied_vol"] == 0.25
    assert result.loc[0, "gamma"] > 0
    assert -1.0 < result.loc[0, "delta"] < 0.0
    assert result.loc[0, "theta"] < 0
    assert result.loc[0, "vega"] > 0
