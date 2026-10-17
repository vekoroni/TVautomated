"""One option valuation engine (output-trust item 4, D5-1; ACK decision 2, 9 Oct 2026).

Replaces four payoff producers with four definitions (SMCI 8 Oct: +207%, 2.16x, -2.1%, -38%) by one engine:
- US stock and ETF options: EV3's American Cox-Ross-Rubinstein pricer (vanguard.ev_engine_v3.american_option_price),
  reused, not copied.
- European index options (config european_style_roots): Black-Scholes-Merton.
- Rate and continuous dividend yield are inputs carried with their basis; a missing yield is ASSUMED_ZERO, stated.
- Costs (config): entry at the ask plus the opening fee; exit at the model value less half the quoted spread, less the
  closing fee. Returns are on the premium paid (net of fees).
Proof: tests/test_ot4_one_valuation_engine.py (textbook benchmarks, call = European without dividends, convergence,
an independent finite-difference American model). Display and ranking input only; no capital authority.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Mapping, Optional

CONSTANTS_PATH = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
VALUATION_FIELDS = (
    "valuation_model", "valuation_version", "valuation_rate_annual", "valuation_rate_basis",
    "valuation_dividend_yield_annual", "valuation_dividend_basis", "valuation_cost_basis",
    "valuation_entry_cost_usd_per_share", "scenario_exit_sessions", "scenario_iv_basis",
    "scenario_target_exit_spot", "scenario_target_return_on_premium",
    "scenario_invalidation_exit_spot", "scenario_invalidation_return_on_premium",
    "scenario_stall_return_on_premium", "scenario_target_earnings_iv_return_on_premium",
)
_N = NormalDist()


@lru_cache(maxsize=1)
def valuation_policy() -> Dict[str, Any]:
    return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8-sig"))["option_valuation"]


def exercise_style(underlying: Any) -> str:
    root = str(underlying or "").strip().upper()
    return "EUROPEAN" if root in set(valuation_policy()["european_style_roots"]) else "AMERICAN"


def _intrinsic(side: str, spot: float, strike: float) -> float:
    return max(spot - strike, 0.0) if side == "CALL" else max(strike - spot, 0.0)


def european_bsm_value(side: str, spot: float, strike: float, years: float, vol: float, *, rate: float,
                       dividend_yield: float) -> float:
    """Black-Scholes-Merton with a continuous dividend yield; intrinsic at the boundaries."""
    side = str(side).upper()
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return _intrinsic(side, spot, strike)
    sq = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * vol * vol) * years) / sq
    d2 = d1 - sq
    disc_s, disc_k = spot * math.exp(-dividend_yield * years), strike * math.exp(-rate * years)
    if side == "CALL":
        return disc_s * _N.cdf(d1) - disc_k * _N.cdf(d2)
    return disc_k * _N.cdf(-d2) - disc_s * _N.cdf(-d1)


def american_crr_value(spot: float, strike: float, years: float, rate: float, dividend_yield: float,
                       volatility: float, direction: str, *, steps: int = 100) -> float:
    """Cox-Ross-Rubinstein American value: the same model and arithmetic as EV3's tree
    (vanguard.ev_engine_v3.american_option_price), owned here so the module's speed does not depend on a frozen
    file (G5/G9, ACK 17 Oct 2026, D3). Each level's spot prices are stepped from the level above (divide by `up`)
    instead of rebuilt with powers: about 40 ms -> a few ms per value at 300 steps; values equal EV3's to 1e-9
    (tests/test_g5_owner_crr_tree.py)."""
    import numpy as np
    is_call = str(direction).upper() == "CALL"
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if years <= 0 or volatility <= 0 or steps <= 0:
        return intrinsic
    dt = years / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    denominator = up - down
    if denominator <= 0:
        return intrinsic
    probability = min(max((math.exp((rate - dividend_yield) * dt) - down) / denominator, 0.0), 1.0)
    discount = math.exp(-rate * dt)
    indices = np.arange(steps + 1)
    spots = spot * (up ** (steps - indices)) * (down ** indices)
    values = np.maximum(spots - strike, 0.0) if is_call else np.maximum(strike - spots, 0.0)
    for _level in range(steps - 1, -1, -1):
        values = discount * (probability * values[:-1] + (1.0 - probability) * values[1:])
        spots = spots[:-1] * down          # node (level, j) = node (level + 1, j) / up
        exercise = np.maximum(spots - strike, 0.0) if is_call else np.maximum(strike - spots, 0.0)
        values = np.maximum(values, exercise)
    return float(values[0])


def american_crr_values(spot, strike, years, rate, dividend_yield, volatility, is_call, *, steps: int = 100):
    """american_crr_value for many contracts in one pass (arrays; each row has its own inputs). The same tree,
    vectorised across rows so the per-level cost is shared: for Lane B's shortlist (G5, ACK 17 Oct 2026)."""
    import numpy as np
    s, k, t, r, q, v = (np.asarray(x, float).reshape(-1) for x in np.broadcast_arrays(
        spot, strike, years, rate, dividend_yield, volatility))
    call = np.broadcast_to(np.asarray(is_call, bool), s.shape)
    intrinsic = np.where(call, np.maximum(s - k, 0.0), np.maximum(k - s, 0.0))
    out = intrinsic.astype(float).copy()
    ok = (t > 0) & (v > 0) & (s > 0) & (k > 0) & (steps > 0)
    if not ok.any():
        return out
    s, k, t, r, q, v, c = s[ok], k[ok], t[ok], r[ok], q[ok], v[ok], call[ok]
    dt = t / steps
    up = np.exp(v * np.sqrt(dt))
    down = 1.0 / up
    p = np.clip((np.exp((r - q) * dt) - down) / (up - down), 0.0, 1.0)[:, None]
    disc = np.exp(-r * dt)[:, None]
    idx = np.arange(steps + 1)
    spots = s[:, None] * (up[:, None] ** (steps - idx)) * (down[:, None] ** idx)
    kk, cc, dd = k[:, None], c[:, None], down[:, None]
    values = np.where(cc, np.maximum(spots - kk, 0.0), np.maximum(kk - spots, 0.0))
    for _level in range(steps - 1, -1, -1):
        values = disc * (p * values[:, :-1] + (1.0 - p) * values[:, 1:])
        spots = spots[:, :-1] * dd
        values = np.maximum(values, np.where(cc, np.maximum(spots - kk, 0.0), np.maximum(kk - spots, 0.0)))
    out[ok] = values[:, 0]
    return out


def option_value(side: str, spot: float, strike: float, years: float, vol: float, *, rate: float,
                 dividend_yield: float, style: str = "AMERICAN") -> Dict[str, Any]:
    """The one model value per share, with the model named."""
    side = str(side).upper()
    if str(style).upper() == "EUROPEAN":
        return {"value": european_bsm_value(side, spot, strike, years, vol, rate=rate, dividend_yield=dividend_yield),
                "model": "BSM_EUROPEAN"}
    if spot <= 0 or strike <= 0:
        return {"value": _intrinsic(side, spot, strike), "model": "AMERICAN_CRR"}
    value = american_crr_value(spot, strike, years, rate, dividend_yield, vol, side,
                               steps=int(valuation_policy()["crr_steps"]))
    return {"value": float(value), "model": "AMERICAN_CRR"}


def entry_cost_usd_per_share(ask: float) -> float:
    return float(ask) + float(valuation_policy()["fee_usd_per_contract_open"]) / 100.0


def exit_proceeds_usd_per_share(model_value: float, *, bid: Optional[float], ask: float) -> float:
    """Model value less half the quoted spread, less the closing fee; floored at zero (a worthless option is not sold,
    so the loss never exceeds the premium and opening fee)."""
    half_spread = max(float(ask) - float(bid), 0.0) / 2.0 if bid is not None else 0.0
    return max(model_value - half_spread - float(valuation_policy()["fee_usd_per_contract_close"]) / 100.0, 0.0)


def cost_basis(bid: Optional[float]) -> str:
    pol = valuation_policy()
    spread = pol["exit_spread_rule"] if bid is not None else "EXIT_SPREAD_UNKNOWN_NOT_DEDUCTED"
    return (f"{pol['entry_price_rule']}|{spread}|fees ${pol['fee_usd_per_contract_open']:.2f} open "
            f"${pol['fee_usd_per_contract_close']:.2f} close per contract")


def resolve_rate(rate: Any, basis: Any) -> tuple[float, str]:
    try:
        value = float(rate)
        if math.isfinite(value):
            return value, str(basis or "CALLER_RATE")
    except (TypeError, ValueError):
        pass
    pol = valuation_policy()
    return float(pol["rate_annual_fallback"]), f"GOVERNED_FALLBACK:{pol['rate_fallback_basis']}"


def resolve_dividend(dividend_yield: Any, basis: Any) -> tuple[float, str]:
    try:
        value = float(dividend_yield)
        if math.isfinite(value) and value >= 0:
            return value, str(basis or "DIVIDEND_YIELD_SUPPLIED")
    except (TypeError, ValueError):
        pass
    reason = str(basis or "")
    return 0.0, reason if reason.startswith("ASSUMED_ZERO") else "ASSUMED_ZERO:NOT_SUPPLIED"


def return_on_premium(model_value: Optional[float], *, bid: Optional[float], ask: float) -> Optional[float]:
    if model_value is None:
        return None
    return round(exit_proceeds_usd_per_share(model_value, bid=bid, ask=ask) / entry_cost_usd_per_share(ask) - 1.0, 4)


def scenario_value(contract: Mapping[str, Any], side: str, at_spot: float, years: float, vol: float, *,
                   rate: float, dividend_yield: float) -> Dict[str, Any]:
    style = exercise_style(contract.get("underlying"))
    return option_value(side, at_spot, float(contract["strike"]), max(years, 0.0), vol, rate=rate,
                        dividend_yield=dividend_yield, style=style)
