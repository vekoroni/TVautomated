"""Deterministic dealer-gamma calculations for completed option sessions."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd


CALCULATION_VERSION = "swing_gex_v1"


@dataclass(frozen=True, slots=True)
class GammaExposureConfig:
    dte_min: int = 7
    dte_max: int = 56
    contract_multiplier: int = 100
    risk_free_rate: float = 0.04
    dividend_yield: float = 0.0
    minimum_contracts: int = 25
    minimum_gamma_coverage: float = 0.80
    flip_grid_low: float = 0.80
    flip_grid_high: float = 1.20
    flip_grid_points: int = 161

    @property
    def scope_name(self) -> str:
        return f"SWING_GEX_{self.dte_min}_{self.dte_max}D"


@dataclass(frozen=True, slots=True)
class GammaExposureResult:
    ticker: str
    session_date: str
    summary: dict[str, Any]
    by_strike: pd.DataFrame


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _bs_gamma(
    spot: float,
    strike: float,
    time_years: float,
    volatility: float,
    rate: float,
    dividend_yield: float,
) -> float:
    if min(spot, strike, time_years, volatility) <= 0:
        return 0.0
    root_t = math.sqrt(time_years)
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_years
    ) / (volatility * root_t)
    return math.exp(-dividend_yield * time_years) * _normal_pdf(d1) / (
        spot * volatility * root_t
    )


def _flip_level(frame: pd.DataFrame, spot: float, config: GammaExposureConfig) -> float | None:
    usable = frame.dropna(subset=["strike", "dte", "iv", "open_interest", "side"])
    usable = usable[(usable["iv"] > 0) & (usable["dte"] > 0) & (usable["open_interest"] > 0)]
    if usable.empty:
        return None
    low = spot * config.flip_grid_low
    high = spot * config.flip_grid_high
    if config.flip_grid_points < 3 or low <= 0 or high <= low:
        return None
    step = (high - low) / float(config.flip_grid_points - 1)
    levels: list[tuple[float, float]] = []
    rows = usable[["strike", "dte", "iv", "open_interest", "side"]].to_dict("records")
    for index in range(config.flip_grid_points):
        trial_spot = low + step * index
        total = 0.0
        for row in rows:
            sign = 1.0 if str(row["side"]).strip().upper() == "CALL" else -1.0
            gamma = _bs_gamma(
                trial_spot,
                float(row["strike"]),
                float(row["dte"]) / 365.0,
                float(row["iv"]),
                config.risk_free_rate,
                config.dividend_yield,
            )
            total += (
                sign
                * gamma
                * float(row["open_interest"])
                * config.contract_multiplier
                * trial_spot
                * trial_spot
                * 0.01
            )
        levels.append((trial_spot, total))
    crossings: list[float] = []
    for (left_spot, left_value), (right_spot, right_value) in zip(levels, levels[1:]):
        if left_value == 0:
            crossings.append(left_spot)
        elif left_value * right_value < 0:
            fraction = abs(left_value) / (abs(left_value) + abs(right_value))
            crossings.append(left_spot + fraction * (right_spot - left_spot))
    return round(min(crossings, key=lambda value: abs(value - spot)), 4) if crossings else None


def calculate_gamma_exposure(
    chain: pd.DataFrame,
    *,
    ticker: str,
    session_date: str,
    config: GammaExposureConfig | None = None,
) -> GammaExposureResult:
    """Calculate a swing-horizon GEX surface from one immutable chain snapshot."""

    cfg = config or GammaExposureConfig()
    required = {
        "ticker", "quote_date", "option_symbol", "side", "strike", "dte",
        "open_interest", "underlying_price", "gamma", "iv",
    }
    missing = sorted(required - set(chain.columns))
    if missing:
        raise ValueError(f"option chain missing required columns: {missing}")
    frame = chain.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["side"] = frame["side"].astype(str).str.upper().str.strip()
    sessions = set(frame["quote_date"].dropna().astype(str).str[:10])
    if sessions != {str(session_date)[:10]}:
        raise ValueError(f"mixed or incorrect option sessions: {sorted(sessions)}")
    frame = frame[
        (frame["ticker"] == ticker.upper())
        & frame["side"].isin(["CALL", "PUT"])
    ]
    for column in ("strike", "dte", "open_interest", "underlying_price", "gamma", "iv"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[frame["dte"].between(cfg.dte_min, cfg.dte_max, inclusive="both")]
    if frame.empty:
        raise ValueError(f"no contracts in {cfg.scope_name}")

    spot_values = frame["underlying_price"].dropna()
    if spot_values.empty or float(spot_values.median()) <= 0:
        raise ValueError("underlying spot is unavailable")
    spot = float(spot_values.median())
    gamma_coverage = float(frame["gamma"].notna().mean())
    iv_coverage = float(frame["iv"].notna().mean())
    usable = frame.dropna(subset=["gamma", "strike", "open_interest"])
    usable = usable[(usable["gamma"] >= 0) & (usable["open_interest"] >= 0)]
    if len(usable) < cfg.minimum_contracts:
        raise ValueError(
            f"insufficient contracts: {len(usable)} < {cfg.minimum_contracts}"
        )
    if gamma_coverage < cfg.minimum_gamma_coverage:
        raise ValueError(
            f"insufficient gamma coverage: {gamma_coverage:.1%} < {cfg.minimum_gamma_coverage:.1%}"
        )

    usable["signed_gex_usd_1pct"] = (
        usable["gamma"]
        * usable["open_interest"]
        * cfg.contract_multiplier
        * spot
        * spot
        * 0.01
        * usable["side"].map({"CALL": 1.0, "PUT": -1.0})
    )
    usable["call_gex_usd_1pct"] = usable["signed_gex_usd_1pct"].where(
        usable["side"] == "CALL", 0.0
    )
    usable["put_gex_usd_1pct"] = usable["signed_gex_usd_1pct"].where(
        usable["side"] == "PUT", 0.0
    )
    usable["call_oi"] = usable["open_interest"].where(usable["side"] == "CALL", 0.0)
    usable["put_oi"] = usable["open_interest"].where(usable["side"] == "PUT", 0.0)
    by_strike = (
        usable.groupby("strike", as_index=False)
        .agg(
            call_gex_usd_1pct=("call_gex_usd_1pct", "sum"),
            put_gex_usd_1pct=("put_gex_usd_1pct", "sum"),
            net_gex_usd_1pct=("signed_gex_usd_1pct", "sum"),
            call_oi=("call_oi", "sum"),
            put_oi=("put_oi", "sum"),
            contracts=("option_symbol", "nunique"),
        )
        .sort_values("strike")
        .reset_index(drop=True)
    )
    call_rows = by_strike[by_strike["call_gex_usd_1pct"] > 0]
    put_rows = by_strike[by_strike["put_gex_usd_1pct"] < 0]
    call_wall = float(call_rows.loc[call_rows["call_gex_usd_1pct"].idxmax(), "strike"]) if not call_rows.empty else None
    put_wall = float(put_rows.loc[put_rows["put_gex_usd_1pct"].idxmin(), "strike"]) if not put_rows.empty else None
    call_gex = float(usable["call_gex_usd_1pct"].sum())
    put_gex = float(usable["put_gex_usd_1pct"].sum())
    net_gex = call_gex + put_gex
    gross = abs(call_gex) + abs(put_gex)
    balance = abs(net_gex) / gross if gross else 0.0
    regime = "POSITIVE" if net_gex > 0 else "NEGATIVE" if net_gex < 0 else "NEUTRAL"
    stress = "HIGH" if balance < 0.10 else "MEDIUM" if balance < 0.25 else "LOW"
    flip = _flip_level(usable, spot, cfg)
    quality_flags: list[str] = []
    if iv_coverage < cfg.minimum_gamma_coverage:
        quality_flags.append("PARTIAL_IV_COVERAGE")
    if flip is None:
        quality_flags.append("NO_ZERO_GAMMA_CROSSING_IN_GRID")

    summary = {
        "Ticker": ticker.upper(),
        "Date": str(session_date)[:10],
        "As_Of": str(session_date)[:10] + "T20:00:00Z",
        "Data_Mode": "HISTORICAL",
        "Scope": cfg.scope_name,
        "Calculation_Version": CALCULATION_VERSION,
        "Spot": round(spot, 6),
        "Net_GEX_Bn": round(net_gex / 1_000_000_000.0, 6),
        "Call_GEX_Bn": round(call_gex / 1_000_000_000.0, 6),
        "Put_GEX_Bn": round(put_gex / 1_000_000_000.0, 6),
        "Regime": regime,
        "Gamma_Flip": flip,
        "Call_Wall": call_wall,
        "Put_Wall": put_wall,
        "GEX_Stress": stress,
        "Contracts_Used": int(usable["option_symbol"].nunique()),
        "Gamma_Coverage": round(gamma_coverage, 6),
        "IV_Coverage": round(iv_coverage, 6),
        "Data_Status": "OK",
        "Quality_Flags": "|".join(quality_flags),
    }
    by_strike.insert(0, "Ticker", ticker.upper())
    by_strike.insert(1, "Date", str(session_date)[:10])
    by_strike.insert(2, "Spot", spot)
    by_strike.insert(3, "Scope", cfg.scope_name)
    return GammaExposureResult(ticker.upper(), str(session_date)[:10], summary, by_strike)


__all__ = [
    "CALCULATION_VERSION",
    "GammaExposureConfig",
    "GammaExposureResult",
    "calculate_gamma_exposure",
]
