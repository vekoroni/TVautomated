"""
Empirical Option EV — shadow computation (Actuarial Distribution sprint, Phase 2).
====================================================================================

Uses the per-horizon return percentiles retained by FIX-AD-1
(vanguard/layer2_statistical/actuarial_query.py's _calculate_outcomes()) to
price the selected contract's payoff at the actual exit horizon under the
database's own empirical return distribution — instead of assuming a
parametric (lognormal) shape, and instead of pricing at expiry when the real
plan is a multi-day swing exit with time value still on the contract.

NO AUTHORITY. This module does not gate, rank, filter, veto, replace, or size
anything. It emits `emp_*` columns that sit beside `ev_conf_adj`/`ev_status`
so the two can be compared on realised outcomes later — see the standing
limitation in ACTUARIAL_DISTRIBUTION_SPRINT_REPORT.md. Nothing in this
pipeline may branch on these columns. Does not modify ev_engine_v2.py.

Design notes (deliberate, do not "simplify" away):
  - Priced at the exit horizon (DTE - hold_days remaining), not at expiry.
    A 3-12 day hold on a 21-DTE contract exits with real time value left;
    terminal-payoff EV systematically understates a swing trade.
  - Priced on the ASK, never the mid. Median live spread across the book is
    ~32% — EV on mid is fiction the trader never actually receives.
  - No parametric fit. The percentile points ARE the distribution; the whole
    point of this sprint is to stop discarding the database's measured tails
    in favour of a two-point (win-rate x median) or lognormal summary.
  - Percentile spacing is uneven (p1->p5 spans 4 probability points, p40->p50
    spans 10) and must be weighted accordingly — see _percentile_weights().
    An unweighted mean over the 13 points biases toward the dense middle and
    hides exactly the tail this sprint exists to expose.
  - Horizon selection matches the actual intended hold window (preferred
    horizon / recommended_hold_days), not the contract's DTE.
  - A confidently wrong P(R>=1.0) is worse than no number — every failure
    mode below emits nulls, never a fabricated 0.0.

Known, disclosed limitations:
  - Percentile points are a 13-point discretisation of the true empirical
    CDF, not the full sample. Extreme moves inside the p01/p99 tails (which
    the underlying sample DOES contain, per FIX-AD-1) are represented only by
    their boundary point's value, not their own internal spread. Skew and
    P(R<=-1.0)/P(R>=2.0) are therefore somewhat conservative versions of what
    the full retained sample would show — a real improvement on median-only
    EV, but still coarser than the underlying data.
  - Reprices with a single flat IV (the contract's live IV, held constant
    across scenarios) rather than a forecast vol surface at the future exit
    date. There is no vol-surface forecast available upstream to do better.
  - The STALE_QUOTE gate requires a live quote timestamp. Archived per-run
    CSVs used for offline validation carry no such field, so that gate can be
    exercised only in a live run — it is implemented and unit-tested, but
    could not be demonstrated end-to-end from static data.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from compute_greeks_bs import black_scholes_price  # noqa: E402

DEFAULT_RISK_FREE_RATE = 0.045   # matches scripts/phantom_compute_historical_greeks.py convention
DEFAULT_N_OBS_FLOOR = 100        # see Phase 0.2 census: ANALOGUE_MIN_SAMPLES=100, and 97% of a
                                  # real run's book already clears this — see sprint report

PERCENTILE_LEVELS = (0.01, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99)
PERCENTILE_LABELS = ("p01", "p05", "p10", "p20", "p30", "p40", "p50", "p60", "p70", "p80", "p90", "p95", "p99")

QUALITY_OK = "OK"
QUALITY_THIN_SAMPLE = "THIN_SAMPLE"
QUALITY_NO_MARKET = "NO_MARKET"
QUALITY_STALE_QUOTE = "STALE_QUOTE"
QUALITY_UNKNOWN_TIER = "UNKNOWN_MATCH_TIER"
QUALITY_VOL_DIVERGENCE = "VOL_DIVERGENCE_BLOCK"
QUALITY_BAD_INPUT = "BAD_INPUT"

EMPTY_COLUMNS = (
    "emp_expected_r", "emp_p_profit", "emp_p_double", "emp_p_triple",
    "emp_p_total_loss", "emp_e_r_given_win", "emp_e_r_given_loss",
    "emp_skew", "emp_n_obs", "emp_horizon_used", "emp_quality_flag",
)


def _percentile_weights() -> tuple:
    """
    Weight each percentile point by the width of probability space it
    represents, not by point count. Boundary points (p01, p99) extend all
    the way to 0.0 / 1.0 since there is no finer resolution below/above them.

    Implemented as breakpoints-between-midpoints so the weights are
    guaranteed (by telescoping) to sum to exactly 1.0 — verified in the
    module's own self-check at import time below, and in the test suite.
    """
    breakpoints = [0.0]
    for i in range(len(PERCENTILE_LEVELS) - 1):
        breakpoints.append((PERCENTILE_LEVELS[i] + PERCENTILE_LEVELS[i + 1]) / 2.0)
    breakpoints.append(1.0)
    return tuple(breakpoints[i + 1] - breakpoints[i] for i in range(len(PERCENTILE_LEVELS)))


PERCENTILE_WEIGHTS = _percentile_weights()
assert abs(sum(PERCENTILE_WEIGHTS) - 1.0) < 1e-9, "percentile weights must sum to 1.0"


def _null_result(quality_flag: str, horizon_used: Optional[str] = None, n_obs: Optional[int] = None) -> dict:
    out = {col: None for col in EMPTY_COLUMNS}
    out["emp_quality_flag"] = quality_flag
    out["emp_horizon_used"] = horizon_used
    out["emp_n_obs"] = n_obs
    return out


def _select_horizon(get) -> Optional[str]:
    """
    Map the actuarial layer's preferred horizon to the 5d/10d/20d percentile
    set. Must reflect the actual intended hold window, not contract DTE.
    Falls back to nearest-of-{5,10,20} from an explicit hold_days if
    preferred_horizon is absent, so a caller that only has hold_days still
    gets a deterministic answer rather than an unnecessary null.
    """
    raw = str(
        get("preferred_horizon") or get("layer2__preferred_horizon") or ""
    ).strip().upper().replace("_", "")
    if raw in ("5", "5D", "5DAY", "5DAYS"):
        return "5d"
    if raw in ("10", "10D", "10DAY", "10DAYS"):
        return "10d"
    if raw in ("20", "20D", "20DAY", "20DAYS"):
        return "20d"

    hold_days = get("hold_days")
    if hold_days is None:
        hold_days = get("recommended_hold_days") or get("layer2__recommended_hold_days")
    try:
        hold_days = float(hold_days)
    except (TypeError, ValueError):
        return None
    nearest = min((5, 10, 20), key=lambda h: abs(h - hold_days))
    return f"{nearest}d"


def compute_empirical_option_ev(candidate: dict, n_obs_floor: int = DEFAULT_N_OBS_FLOOR) -> dict:
    """
    Compute the empirical, ask-net, exit-horizon option EV distribution for
    one candidate. Returns exactly the columns in EMPTY_COLUMNS — nulls
    (never fabricated numbers) whenever a quality gate fires.

    Expected keys on `candidate` (missing/None keys are treated as absent —
    each is tried under a bare name first, then a layer2__-prefixed name,
    matching this pipeline's existing field-lookup convention):
      state_match_method / layer2__state_match_method   -- EXACT/RELAXED/ANALOGUE/UNKNOWN
      bid, ask                                            -- contract quote (options_bid/options_ask also tried)
      quote_age_minutes                                   -- optional; None = unknown, gate not evaluated
      forecast_vol / l3_forward_realised_vol              -- optional; paired with live_iv for the vol-divergence gate
      live_iv / contract_iv                               -- option's current implied vol (also used for BS repricing)
      preferred_horizon / layer2__preferred_horizon        -- "5D"/"10D"/"20D"
      hold_days / recommended_hold_days / layer2__recommended_hold_days
      n_obs_5d / n_obs_10d / n_obs_20d                     -- from FIX-AD-1
      ret_pctl_<h>_<p01..p99>                              -- from FIX-AD-1
      live_spot / underlying_price
      strike / contract_strike
      dte / contract_dte
      direction                                            -- "CALL"/"PUT"
      risk_free_rate                                       -- optional, default 0.045
    """
    def g(*keys, default=None):
        for k in keys:
            v = candidate.get(k)
            if v is not None and v != "":
                return v
        return default

    match_tier = str(g("state_match_method", "layer2__state_match_method", default="UNKNOWN")).upper()
    if match_tier in ("UNKNOWN", ""):
        return _null_result(QUALITY_UNKNOWN_TIER)

    bid = g("bid", "options_bid", "contract_bid")
    ask = g("ask", "options_ask", "contract_ask")
    try:
        bid = float(bid) if bid is not None else None
        ask = float(ask) if ask is not None else None
    except (TypeError, ValueError):
        bid = ask = None
    if bid is None or bid <= 0 or ask is None or ask <= 0:
        return _null_result(QUALITY_NO_MARKET)

    quote_age_minutes = g("quote_age_minutes")
    if quote_age_minutes is not None:
        try:
            if float(quote_age_minutes) > 30:
                return _null_result(QUALITY_STALE_QUOTE)
        except (TypeError, ValueError):
            pass

    live_iv = g("live_iv", "contract_iv")
    forecast_vol = g("forecast_vol", "l3_forward_realised_vol")
    try:
        live_iv_f = float(live_iv) if live_iv is not None else None
        forecast_vol_f = float(forecast_vol) if forecast_vol is not None else None
    except (TypeError, ValueError):
        live_iv_f = forecast_vol_f = None
    if live_iv_f and forecast_vol_f is not None and (forecast_vol_f / live_iv_f) >= 2.0:
        return _null_result(QUALITY_VOL_DIVERGENCE)

    horizon = _select_horizon(g)
    if horizon is None:
        return _null_result(QUALITY_BAD_INPUT)

    n_obs = g(f"n_obs_{horizon}")
    try:
        n_obs = int(n_obs) if n_obs is not None else None
    except (TypeError, ValueError):
        n_obs = None
    if n_obs is None or n_obs < n_obs_floor:
        return _null_result(QUALITY_THIN_SAMPLE, horizon_used=horizon, n_obs=n_obs)

    pctl_returns = []
    for label in PERCENTILE_LABELS:
        v = g(f"ret_pctl_{horizon}_{label}")
        if v is None:
            return _null_result(QUALITY_THIN_SAMPLE, horizon_used=horizon, n_obs=n_obs)
        try:
            pctl_returns.append(float(v))
        except (TypeError, ValueError):
            return _null_result(QUALITY_THIN_SAMPLE, horizon_used=horizon, n_obs=n_obs)

    spot = g("live_spot", "underlying_price")
    strike = g("strike", "contract_strike")
    dte = g("dte", "contract_dte")
    hold_days = g("hold_days", "recommended_hold_days", "layer2__recommended_hold_days")
    direction = str(g("direction", default="CALL")).strip().lower()
    rate = g("risk_free_rate", default=DEFAULT_RISK_FREE_RATE)
    try:
        spot = float(spot); strike = float(strike); dte = float(dte); hold_days = float(hold_days)
        rate = float(rate)
    except (TypeError, ValueError):
        return _null_result(QUALITY_BAD_INPUT, horizon_used=horizon, n_obs=n_obs)
    if direction not in ("call", "put") or spot <= 0 or strike <= 0 or not live_iv_f or live_iv_f <= 0:
        return _null_result(QUALITY_BAD_INPUT, horizon_used=horizon, n_obs=n_obs)

    remaining_days = max(dte - hold_days, 0.0)
    time_years = remaining_days / 365.0

    r_values = []
    for r_i in pctl_returns:
        s_i = spot * (1.0 + r_i)
        if time_years <= 0:
            value_i = max(s_i - strike, 0.0) if direction == "call" else max(strike - s_i, 0.0)
        else:
            value_i = black_scholes_price(direction, s_i, strike, time_years, rate, live_iv_f)
        r_values.append((value_i - ask) / ask)

    expected_r = sum(w * r for w, r in zip(PERCENTILE_WEIGHTS, r_values))
    p_profit = sum(w for w, r in zip(PERCENTILE_WEIGHTS, r_values) if r >= 0)
    p_double = sum(w for w, r in zip(PERCENTILE_WEIGHTS, r_values) if r >= 1.0)
    p_triple = sum(w for w, r in zip(PERCENTILE_WEIGHTS, r_values) if r >= 2.0)
    p_total_loss = sum(w for w, r in zip(PERCENTILE_WEIGHTS, r_values) if r <= -1.0)

    win_pairs = [(w, r) for w, r in zip(PERCENTILE_WEIGHTS, r_values) if r >= 0]
    loss_pairs = [(w, r) for w, r in zip(PERCENTILE_WEIGHTS, r_values) if r < 0]
    win_weight = sum(w for w, _ in win_pairs)
    loss_weight = sum(w for w, _ in loss_pairs)
    e_r_given_win = (sum(w * r for w, r in win_pairs) / win_weight) if win_weight > 0 else None
    e_r_given_loss = (sum(w * r for w, r in loss_pairs) / loss_weight) if loss_weight > 0 else None

    variance = sum(w * (r - expected_r) ** 2 for w, r in zip(PERCENTILE_WEIGHTS, r_values))
    std = math.sqrt(variance) if variance > 0 else 0.0
    skew = (
        sum(w * (r - expected_r) ** 3 for w, r in zip(PERCENTILE_WEIGHTS, r_values)) / (std ** 3)
        if std > 0 else 0.0
    )

    return {
        "emp_expected_r": round(expected_r, 6),
        "emp_p_profit": round(p_profit, 6),
        "emp_p_double": round(p_double, 6),
        "emp_p_triple": round(p_triple, 6),
        "emp_p_total_loss": round(p_total_loss, 6),
        "emp_e_r_given_win": round(e_r_given_win, 6) if e_r_given_win is not None else None,
        "emp_e_r_given_loss": round(e_r_given_loss, 6) if e_r_given_loss is not None else None,
        "emp_skew": round(skew, 6),
        "emp_n_obs": n_obs,
        "emp_horizon_used": horizon,
        "emp_quality_flag": QUALITY_OK,
    }
