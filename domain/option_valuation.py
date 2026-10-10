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


def option_value(side: str, spot: float, strike: float, years: float, vol: float, *, rate: float,
                 dividend_yield: float, style: str = "AMERICAN") -> Dict[str, Any]:
    """The one model value per share, with the model named."""
    side = str(side).upper()
    if str(style).upper() == "EUROPEAN":
        return {"value": european_bsm_value(side, spot, strike, years, vol, rate=rate, dividend_yield=dividend_yield),
                "model": "BSM_EUROPEAN"}
    from vanguard.ev_engine_v3 import american_option_price
    if spot <= 0 or strike <= 0:
        return {"value": _intrinsic(side, spot, strike), "model": "AMERICAN_CRR"}
    value = american_option_price(spot, strike, years, rate, dividend_yield, vol, side,
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
