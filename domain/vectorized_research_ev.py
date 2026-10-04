"""Vectorized research-only ask-to-bid valuation on common empirical paths.

This is a computational accelerator for an *uncalibrated* unconditional
baseline. It is never the governed C8 probability owner or trade authority.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy.special import ndtr

from domain.research_path_baseline import RelativePath


def value_research_contract(
    paths: Sequence[RelativePath], *, spot: float, target: float | None,
    stop: float | None, right: str, strike: float, ask: float, bid: float,
    implied_vol: float, multiplier: int, expiry_sessions: int,
    last_exit_session: int, iv_multiplier: float = 1.0,
    commission_usd_round_trip: float = 0.0,
    extra_slippage_fraction_of_spread_each_side: float = 0.0,
) -> dict:
    if (not paths or right not in {"CALL", "PUT"} or multiplier <= 0
            or not 1 <= last_exit_session <= min(20, expiry_sessions)
            or not all(math.isfinite(x) and x > 0 for x in
                       (spot, strike, ask, implied_vol, iv_multiplier))
            or not 0 <= bid <= ask or commission_usd_round_trip < 0
            or extra_slippage_fraction_of_spread_each_side < 0):
        raise ValueError("invalid research quote, path or exit clock")
    if any(len(path.bars) < last_exit_session for path in paths):
        raise ValueError("incomplete empirical research path")
    matrix = np.asarray([path.bars[:last_exit_session] for path in paths], dtype=np.float64) * spot
    if matrix.shape != (len(paths), last_exit_session, 4) or not np.isfinite(matrix).all():
        raise ValueError("research path matrix invalid")
    opened, high, low, close = (matrix[:, :, index] for index in range(4))
    if (np.any(low <= 0) or np.any(low > np.minimum(opened, close))
            or np.any(np.maximum(opened, close) > high)):
        raise ValueError("research OHLC geometry invalid")
    barriers = target is not None and stop is not None
    if barriers:
        if (not math.isfinite(target) or not math.isfinite(stop) or target <= 0 or stop <= 0
                or (right == "CALL" and not stop < spot < target)
                or (right == "PUT" and not target < spot < stop)):
            raise ValueError("research barrier geometry invalid")
        target_hit = high >= target if right == "CALL" else low <= target
        stop_hit = low <= stop if right == "CALL" else high >= stop
        any_hit = target_hit | stop_hit
        hit_exists = any_hit.any(axis=1)
        first = np.argmax(any_hit, axis=1)
        exit_index = np.where(hit_exists, first, last_exit_session - 1)
        rows = np.arange(len(paths))
        stop_event = hit_exists & stop_hit[rows, exit_index]
        target_event = hit_exists & ~stop_event
    else:
        exit_index = np.full(len(paths), last_exit_session - 1, dtype=np.int32)
        stop_event = target_event = np.zeros(len(paths), dtype=bool)
        rows = np.arange(len(paths))
    exit_day = exit_index + 1
    exit_spot = close[rows, exit_index].copy()
    exit_open = opened[rows, exit_index]
    if barriers:
        if right == "CALL":
            exit_spot = np.where(stop_event, np.minimum(exit_open, stop), exit_spot)
            exit_spot = np.where(target_event, np.maximum(exit_open, target), exit_spot)
        else:
            exit_spot = np.where(stop_event, np.maximum(exit_open, stop), exit_spot)
            exit_spot = np.where(target_event, np.minimum(exit_open, target), exit_spot)
    years = np.maximum(expiry_sessions - exit_day, 0) / 252.0
    volatility = implied_vol * iv_multiplier
    intrinsic = (np.maximum(exit_spot - strike, 0.0) if right == "CALL"
                 else np.maximum(strike - exit_spot, 0.0))
    sigma_root = volatility * np.sqrt(years)
    safe_root = np.where(sigma_root > 0, sigma_root, 1.0)
    d1 = (np.log(exit_spot / strike) + 0.5 * volatility**2 * years) / safe_root
    d2 = d1 - sigma_root
    if right == "CALL":
        theoretical = exit_spot * ndtr(d1) - strike * ndtr(d2)
    else:
        theoretical = strike * ndtr(-d2) - exit_spot * ndtr(-d1)
    mark = np.maximum(np.where(years > 0, theoretical, intrinsic), intrinsic)
    spread = ask - bid
    slippage = spread * extra_slippage_fraction_of_spread_each_side
    entry_cost = (ask + slippage) * multiplier + commission_usd_round_trip / 2
    proceeds = np.maximum(mark - spread / 2 - slippage, 0.0) * multiplier
    proceeds -= commission_usd_round_trip / 2
    returns = (proceeds - entry_cost) / entry_cost
    return {"state": "RESEARCH_EV_UNCALIBRATED",
            "ev_fraction": float(returns.mean()),
            "ev_usd": float((proceeds - entry_cost).mean()),
            "entry_cost_usd": float(entry_cost),
            "per_path_return_fraction": returns.tolist(),
            "event_weights": {
                "TARGET_FIRST": float(target_event.mean()),
                "STOP_FIRST": float(stop_event.mean()),
                "FORCED_EXIT": float((~target_event & ~stop_event).mean()),
            },
            "exit_policy": ("FIRST_TARGET_STOP_OR_TIME" if barriers
                            else "TIME_ONLY_NO_GOVERNED_BARRIERS"),
            "path_count": len(paths), "authority": "RESEARCH_ONLY"}
