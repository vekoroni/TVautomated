"""Local Black-Scholes Greek computation for PHANTOM historical option rows.

MarketData historical EOD option chains preserve raw option tape fields but may
return null Greeks. This module computes an auditable local Greek set from the
archived MarketData fields without calling any external API.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple


VOL_MIN = 1.0e-6
VOL_MAX = 12.0
MAX_ITERATIONS = 100
PRICE_TOLERANCE_FLOOR = 1.0e-5


def to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if not math.isfinite(out):
            return None
        return out
    except Exception:
        return None


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1_d2(spot: float, strike: float, time_years: float, rate: float, vol: float) -> Tuple[float, float]:
    sqrt_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    return d1, d2


def black_scholes_price(side: str, spot: float, strike: float, time_years: float, rate: float, vol: float) -> float:
    side_l = str(side or "").lower()
    d1, d2 = _d1_d2(spot, strike, time_years, rate, vol)
    discount = math.exp(-rate * time_years)
    if side_l == "call":
        return spot * norm_cdf(d1) - strike * discount * norm_cdf(d2)
    if side_l == "put":
        return strike * discount * norm_cdf(-d2) - spot * norm_cdf(-d1)
    raise ValueError(f"unsupported option side: {side!r}")


def no_arbitrage_bounds(side: str, spot: float, strike: float, time_years: float, rate: float) -> Tuple[float, float]:
    discount = math.exp(-rate * time_years)
    side_l = str(side or "").lower()
    if side_l == "call":
        return max(0.0, spot - strike * discount), spot
    if side_l == "put":
        return max(0.0, strike * discount - spot), strike * discount
    return 0.0, float("inf")


def choose_market_price(row: Dict[str, Any]) -> Tuple[Optional[float], str, List[str]]:
    flags: List[str] = []
    mid = to_float(row.get("mid"))
    bid = to_float(row.get("bid"))
    ask = to_float(row.get("ask"))
    last = to_float(row.get("last"))

    if mid is not None and mid > 0:
        return mid, "mid", flags

    if bid is not None and ask is not None and bid >= 0 and ask > 0 and ask >= bid:
        spread_mid = (bid + ask) / 2.0
        if spread_mid > 0:
            flags.append("mid_rebuilt_from_bid_ask")
            return spread_mid, "bid_ask_mid", flags

    if last is not None and last > 0:
        flags.append("last_used_no_mid")
        return last, "last", flags

    return None, "none", ["no_valid_option_price"]


def solve_implied_vol(
    side: str,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    target_price: float,
) -> Tuple[Optional[float], int, Optional[str]]:
    lower_bound, upper_bound = no_arbitrage_bounds(side, spot, strike, time_years, rate)
    tolerance = max(PRICE_TOLERANCE_FLOOR, abs(target_price) * 1.0e-5)

    if target_price < lower_bound - max(0.01, abs(lower_bound) * 1.0e-4):
        return None, 0, f"PRICE_BELOW_NO_ARB: target={target_price:.8f} lower={lower_bound:.8f}"
    if target_price > upper_bound + max(0.01, abs(upper_bound) * 1.0e-4):
        return None, 0, f"PRICE_ABOVE_NO_ARB: target={target_price:.8f} upper={upper_bound:.8f}"

    target = max(target_price, lower_bound + 1.0e-8)
    if target <= lower_bound + max(1.0e-4, abs(lower_bound) * 1.0e-6):
        return VOL_MIN, 0, None

    lo = VOL_MIN
    hi = 0.50
    hi_price = black_scholes_price(side, spot, strike, time_years, rate, hi)
    while hi_price < target and hi < VOL_MAX:
        hi = min(VOL_MAX, hi * 2.0)
        hi_price = black_scholes_price(side, spot, strike, time_years, rate, hi)
        if hi >= VOL_MAX:
            break

    if hi_price < target - tolerance:
        return None, 0, f"PRICE_ABOVE_SOLVER_RANGE: target={target:.8f} max_price={hi_price:.8f}"

    iterations = 0
    mid_vol = hi
    for iterations in range(1, MAX_ITERATIONS + 1):
        mid_vol = (lo + hi) / 2.0
        price = black_scholes_price(side, spot, strike, time_years, rate, mid_vol)
        error = price - target
        if abs(error) <= tolerance:
            return mid_vol, iterations, None
        if error < 0:
            lo = mid_vol
        else:
            hi = mid_vol
    return mid_vol, iterations, None


def compute_greeks(side: str, spot: float, strike: float, dte: float, rate: float, iv: float) -> Dict[str, float]:
    time_years = max(float(dte) / 365.0, 1.0 / 365.0)
    d1, d2 = _d1_d2(spot, strike, time_years, rate, iv)
    sqrt_t = math.sqrt(time_years)
    pdf = norm_pdf(d1)
    discount = math.exp(-rate * time_years)
    side_l = str(side or "").lower()

    gamma = pdf / (spot * iv * sqrt_t)
    vega = spot * pdf * sqrt_t / 100.0

    if side_l == "call":
        delta = norm_cdf(d1)
        theta_annual = -(spot * pdf * iv) / (2.0 * sqrt_t) - rate * strike * discount * norm_cdf(d2)
    elif side_l == "put":
        delta = norm_cdf(d1) - 1.0
        theta_annual = -(spot * pdf * iv) / (2.0 * sqrt_t) + rate * strike * discount * norm_cdf(-d2)
    else:
        raise ValueError(f"unsupported option side: {side!r}")

    return {
        "iv": iv,
        "delta": delta,
        "gamma": gamma,
        "theta": theta_annual / 365.0,
        "vega": vega,
    }


@dataclass
class GreekResult:
    quality_status: str
    quality_flags: List[str]
    price_source: str
    market_price: Optional[float]
    risk_free_rate: float
    iv: Optional[float]
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    vega: Optional[float]
    solver_iterations: int = 0
    solver_error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "quality_status": self.quality_status,
            "quality_flags": ";".join(self.quality_flags),
            "price_source": self.price_source,
            "market_price": self.market_price,
            "risk_free_rate": self.risk_free_rate,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "solver_iterations": self.solver_iterations,
            "solver_error": self.solver_error,
        }


def compute_greeks_from_row(row: Dict[str, Any], risk_free_rate: float = 0.045) -> GreekResult:
    flags: List[str] = []
    side = str(row.get("side") or "").lower()
    spot = to_float(row.get("underlying_price") if "underlying_price" in row else row.get("underlyingPrice"))
    strike = to_float(row.get("strike"))
    dte = to_float(row.get("dte"))
    rate = to_float(risk_free_rate)
    if rate is None:
        rate = 0.045
    if rate > 1.0:
        rate = rate / 100.0
        flags.append("risk_free_rate_percent_normalized")

    market_price, price_source, price_flags = choose_market_price(row)
    flags.extend(price_flags)

    if side not in {"call", "put"}:
        return GreekResult("MISSING_INPUT", flags + ["invalid_side"], price_source, market_price, rate, None, None, None, None, None)
    if spot is None or spot <= 0:
        return GreekResult("MISSING_INPUT", flags + ["missing_underlying_price"], price_source, market_price, rate, None, None, None, None, None)
    if strike is None or strike <= 0:
        return GreekResult("MISSING_INPUT", flags + ["missing_strike"], price_source, market_price, rate, None, None, None, None, None)
    if dte is None or dte <= 0:
        return GreekResult("MISSING_INPUT", flags + ["missing_or_expired_dte"], price_source, market_price, rate, None, None, None, None, None)
    if market_price is None or market_price <= 0:
        return GreekResult("NO_VALID_PRICE", flags, price_source, market_price, rate, None, None, None, None, None)

    time_years = max(dte / 365.0, 1.0 / 365.0)
    solve_price = market_price
    adjusted_no_arb = False
    lower_bound, upper_bound = no_arbitrage_bounds(side, spot, strike, time_years, rate)
    if solve_price < lower_bound:
        violation = lower_bound - solve_price
        adjustment_limit = max(0.25, spot * 0.0025, abs(solve_price) * 0.01)
        if violation <= adjustment_limit:
            flags.append(f"price_below_no_arb_adjusted:{violation:.6f}")
            solve_price = lower_bound + 1.0e-8
            adjusted_no_arb = True
        else:
            return GreekResult(
                "PRICE_BELOW_NO_ARB",
                flags,
                price_source,
                market_price,
                rate,
                None,
                None,
                None,
                None,
                None,
                0,
                f"PRICE_BELOW_NO_ARB: target={market_price:.8f} lower={lower_bound:.8f}",
            )
    elif solve_price > upper_bound:
        violation = solve_price - upper_bound
        adjustment_limit = max(0.25, spot * 0.0025, abs(solve_price) * 0.01)
        if violation <= adjustment_limit:
            flags.append(f"price_above_no_arb_adjusted:{violation:.6f}")
            solve_price = upper_bound - 1.0e-8
            adjusted_no_arb = True
        else:
            return GreekResult(
                "PRICE_ABOVE_NO_ARB",
                flags,
                price_source,
                market_price,
                rate,
                None,
                None,
                None,
                None,
                None,
                0,
                f"PRICE_ABOVE_NO_ARB: target={market_price:.8f} upper={upper_bound:.8f}",
            )

    iv, iterations, solver_error = solve_implied_vol(side, spot, strike, time_years, rate, solve_price)
    if iv is None:
        status = "IV_SOLVE_FAILED"
        if solver_error and solver_error.startswith("PRICE_BELOW_NO_ARB"):
            status = "PRICE_BELOW_NO_ARB"
        elif solver_error and solver_error.startswith("PRICE_ABOVE"):
            status = "PRICE_ABOVE_SOLVER_RANGE"
        return GreekResult(status, flags, price_source, market_price, rate, None, None, None, None, None, iterations, solver_error or "")

    try:
        greeks = compute_greeks(side, spot, strike, dte, rate, iv)
    except Exception as exc:
        return GreekResult("GREEK_COMPUTE_FAILED", flags, price_source, market_price, rate, None, None, None, None, None, iterations, f"{type(exc).__name__}: {exc}")

    stored_iv = 0.0 if adjusted_no_arb and iv <= VOL_MIN * 10.0 else greeks["iv"]
    status = "OK_ADJUSTED_NO_ARB" if adjusted_no_arb else "OK"
    return GreekResult(
        status,
        flags,
        price_source,
        market_price,
        rate,
        stored_iv,
        greeks["delta"],
        greeks["gamma"],
        greeks["theta"],
        greeks["vega"],
        iterations,
        "",
    )
