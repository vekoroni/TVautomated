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
QUALITY_VOL_SCALE_UNAVAILABLE = "VOL_SCALE_UNAVAILABLE"
QUALITY_NO_SELECTED_CONTRACT = "NO_SELECTED_CONTRACT"

# Item 2 (ACK 17 Sep 2026): reality calibration. The actuarial percentiles are pooled by state, so they
# are re-scaled to the ticker's own volatility forecast (p10-p90 width), and exits pay the half-spread.
SESSIONS_PER_YEAR = 252
Z_P90 = 1.2815515655446004   # standard normal 90th percentile: p10-p90 width = 2 * Z_P90 * sigma

EMPTY_COLUMNS = (
    "emp_expected_r", "emp_p_profit", "emp_p_double", "emp_p_triple",
    "emp_p_total_loss", "emp_e_r_given_win", "emp_e_r_given_loss",
    "emp_skew", "emp_n_obs", "emp_horizon_used", "emp_quality_flag",
    "emp_vol_scale", "emp_exit_half_spread",
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


def scaled_percentile_returns(returns, forecast_vol: float, sessions: int):
    """Re-scale percentile returns so the p10-p90 width matches the ticker's own volatility forecast.

    Scaling is done on log returns around the median log return (consistent with the lognormal width
    2 * Z_P90 * sigma * sqrt(sessions / 252)), so scaled scenarios can never imply a non-positive price.
    Returns (scaled simple returns, scale). Ordering and relative spacing (the empirical shape) are kept.
    """
    logs = [math.log1p(r) for r in returns]
    by_label = dict(zip(PERCENTILE_LABELS, logs))
    median = by_label["p50"]
    pooled_width = by_label["p90"] - by_label["p10"]
    target_width = 2.0 * Z_P90 * forecast_vol * math.sqrt(sessions / SESSIONS_PER_YEAR)
    scale = target_width / pooled_width
    return [math.expm1(median + (l - median) * scale) for l in logs], scale


OPTIONS_ROW_FIELD_MAP = (
    ("contract_bid", "bid"), ("contract_ask", "ask"), ("contract_iv", "live_iv"),
    ("underlying_price", "live_spot"), ("entry_spot", "live_spot"), ("stock_price", "live_spot"),
    ("strike", "strike"), ("contract_dte", "dte"), ("dte", "dte"), ("final_direction", "direction"),
    ("layer2__recommended_hold_days", "hold_days"), ("layer2__preferred_horizon", "preferred_horizon"),
    ("layer2__n_obs_5d", "n_obs_5d"), ("layer2__n_obs_10d", "n_obs_10d"), ("layer2__n_obs_20d", "n_obs_20d"),
    ("l3_forward_realised_vol", "forecast_vol"),
)


def candidate_from_options_row(row: dict) -> dict:
    """Map an evening options-output row onto this module's candidate fields (first present value wins)."""
    def present(value) -> bool:
        return value is not None and value != "" and not (isinstance(value, float) and math.isnan(value))

    candidate = {}
    for key, value in row.items():
        if key.startswith("layer2__outcomes__") and present(value):
            candidate[key[len("layer2__outcomes__"):]] = value
    for source, target in OPTIONS_ROW_FIELD_MAP:
        if target not in candidate and present(row.get(source)):
            candidate[target] = row[source]
    if "state_match_method" not in candidate and present(row.get("layer2__state_match_method")):
        candidate["state_match_method"] = row["layer2__state_match_method"]
    return candidate


def _null_result(quality_flag: str, horizon_used: Optional[str] = None, n_obs: Optional[int] = None) -> dict:
    out = {col: None for col in EMPTY_COLUMNS}
    out["emp_quality_flag"] = quality_flag
    out["emp_horizon_used"] = horizon_used
    out["emp_n_obs"] = n_obs
    return out


def _finite_or_none(value) -> Optional[float]:
    """Float value, or None when missing, blank, non-numeric or non-finite (NaN is missing)."""
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


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
    # A missing Layer 3 forecast (None / "" / NaN, e.g. MISSING_PRICE_HISTORY) leaves the
    # vol-divergence gate not evaluated; it is never compared as a number.
    live_iv_f = _finite_or_none(live_iv)
    forecast_vol_f = _finite_or_none(forecast_vol)
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

    if forecast_vol_f is None or forecast_vol_f <= 0:
        return _null_result(QUALITY_VOL_SCALE_UNAVAILABLE, horizon_used=horizon, n_obs=n_obs)
    by_label = dict(zip(PERCENTILE_LABELS, pctl_returns))
    if min(pctl_returns) <= -1.0 or by_label["p90"] < by_label["p10"]:
        return _null_result(QUALITY_BAD_INPUT, horizon_used=horizon, n_obs=n_obs)
    if by_label["p90"] > by_label["p10"]:
        pctl_returns, vol_scale = scaled_percentile_returns(pctl_returns, forecast_vol_f, int(horizon.rstrip("d")))
    else:
        vol_scale = None   # a zero-width (deterministic) distribution has no dispersion to re-scale
    exit_half_spread = (ask - bid) / 2.0

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
        value_i = max(value_i - exit_half_spread, 0.0)      # the exit is sold at the bid
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
        "emp_vol_scale": round(vol_scale, 6) if vol_scale is not None else None,
        "emp_exit_half_spread": round(exit_half_spread, 6),
    }


# ── Item 2 increment 2 (ACK 17 Sep 2026): volatility-range, exit-path valuation (shadow) ──────────────────
#
# Paths exit exactly as the outcome scorer does (invalidation first -> invalidation level; target first ->
# target; otherwise the horizon close), are repriced with the contract's IV and sold at the bid. There is no
# directional drift (direction skill is not established) and daily moves come from the calibrated empirical
# innovation distribution. Volatility is a range: forecast x calibrated forecast-error bands (p10/p50/p90).
# Ranking should use the cautious (lowest) expected return; the upside is reported beside it.

import numpy as _np
from scipy.special import ndtr as _ndtr

PATH_QUALITY_OK = "OK"
PATH_NO_MARKET = "NO_MARKET"
PATH_VOL_UNAVAILABLE = "VOL_SCALE_UNAVAILABLE"
PATH_GEOMETRY_UNAVAILABLE = "GEOMETRY_UNAVAILABLE"
PATH_BAD_INPUT = "BAD_INPUT"
CALENDAR_DAYS_PER_SESSION = 7.0 / 5.0
PATH_COLUMNS = (
    "emp_path_r_cautious", "emp_path_r_central", "emp_path_r_upside",
    "emp_path_p_target_first_central", "emp_path_p_stop_first_central",
    "emp_path_vol_low", "emp_path_vol_central", "emp_path_vol_high",
    "emp_path_horizon_band", "emp_path_target_state", "emp_path_quality_flag", "emp_path_forecast_source",
    "emp_path_last_exit_sessions", "emp_path_forced_exit_share",
)
PATH_CONTRACT_NOT_HOLDABLE = "CONTRACT_NOT_HOLDABLE"
PATH_CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"


def _load_path_settings() -> dict:
    """Governed path-valuation settings (config/governed_constants_v1.json, fail-closed)."""
    import json as _json
    from pathlib import Path as _Path
    payload = _json.loads((_Path(__file__).resolve().parent / "config" / "governed_constants_v1.json")
                          .read_text(encoding="utf-8-sig"))
    settings = dict(payload["empirical_path_valuation"])
    if settings.get("version") != "empirical_path_valuation_v1":
        raise ValueError("unsupported empirical_path_valuation version")
    if int(settings["paths"]) <= 0:
        raise ValueError("empirical_path_valuation.paths must be positive")
    if int(settings["share_spread_min_sessions"]) <= 0 or int(settings["share_spread_window_sessions"]) < int(settings["share_spread_min_sessions"]):
        raise ValueError("empirical_path_valuation share spread window must cover the minimum sessions")
    settings["share_spread_min_sessions"] = int(settings["share_spread_min_sessions"])
    settings["share_spread_window_sessions"] = int(settings["share_spread_window_sessions"])
    settings["paths"], settings["seed"] = int(settings["paths"]), int(settings["seed"])
    settings["option_exit_buffer_sessions"] = int(settings["option_exit_buffer_sessions"])
    if settings["option_exit_buffer_sessions"] < 0:
        raise ValueError("empirical_path_valuation.option_exit_buffer_sessions must not be negative")
    return settings


PATH_SETTINGS = _load_path_settings()


def path_inputs_from_options_row(row: dict, *, thesis_window_sessions: int | None) -> dict:
    """Map an evening options-output row to compute_path_option_ev inputs.

    A clipped Layer 3 forecast is never used for value (ACK 17 Sep 2026): the raw model output is used and
    the source is recorded. The valuation window is the governed thesis window (``outcome.window_sessions``,
    ACK D2(a) 18 Sep 2026), capped per contract by its last exit session inside the simulation; the actuarial
    recommended hold is not used, and a missing window is reported as bad input, never replaced (R1).
    """
    def first(*keys):
        for key in keys:
            value = _finite_or_none(row.get(key))
            if value is not None:
                return value
        return None

    state = str(row.get("l3_forecast_state") or "")
    raw = first("l3_forward_realised_vol_raw")
    if raw is not None and raw > 0:
        forecast, source = raw, "RAW_UNCLIPPED"
    elif state.startswith("CLIPPED"):
        forecast, source = None, "CLIPPED_WITHOUT_RAW"
    else:
        forecast, source = first("l3_forward_realised_vol"), "L3_FORECAST"
    direction = str(row.get("final_direction") or row.get("direction") or "").strip().upper()
    return {
        "side": {"CALL": "call", "PUT": "put"}.get(direction, ""),
        "spot": first("underlying_price", "entry_spot", "stock_price"),
        "strike": first("strike", "contract_strike"),
        "dte": first("contract_dte", "dte"),
        "bid": first("contract_bid"), "ask": first("contract_ask"), "iv": first("contract_iv"),
        "rate": DEFAULT_RISK_FREE_RATE,
        "target": first("structural_target", "target_spot"),
        "invalidation": first("invalidation_spot", "invalidation_price"),
        "hold_sessions": thesis_window_sessions,
        "forecast_vol": forecast, "forecast_source": source,
    }


def sample_innovations(quantiles: dict, rng, size) -> "_np.ndarray":
    """Draw daily innovations by inverse-CDF interpolation of calibrated quantiles; zero mean, unit variance."""
    levels = _np.asarray(quantiles["levels"], dtype=float)
    values = _np.asarray(quantiles["values"], dtype=float)
    uniforms = rng.uniform(levels[0], levels[-1], size)
    draws = _np.interp(uniforms, levels, values)
    return (draws - draws.mean()) / draws.std()


def _bs_vector(side: str, spot, strike: float, time_years, rate: float, vol: float):
    spot = _np.asarray(spot, dtype=float)
    time_years = _np.asarray(time_years, dtype=float)
    intrinsic = _np.maximum(spot - strike, 0.0) if side == "call" else _np.maximum(strike - spot, 0.0)
    live = time_years > 0
    t = _np.where(live, time_years, 1.0)
    sqrt_t = _np.sqrt(t)
    d1 = (_np.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    discount = _np.exp(-rate * t)
    if side == "call":
        priced = spot * _ndtr(d1) - strike * discount * _ndtr(d2)
    else:
        priced = strike * discount * _ndtr(-d2) - spot * _ndtr(-d1)
    return _np.where(live, priced, intrinsic)


def _path_null(flag: str) -> dict:
    out = {column: None for column in PATH_COLUMNS}
    out["emp_path_quality_flag"] = flag
    return out


def _simulate_path_exits(*, side, spot, strike, dte, bid, ask, iv, rate, target, invalidation, hold_sessions,
                         forecast_vol, calibration: dict, paths: int, seed: int):
    """Validate inputs and simulate exits for the p10 / p50 / p90 volatility scenarios.

    Returns (flag, context, scenarios). On a quality failure scenarios is None. Each scenario holds the exit
    session index, exit price and stop-first / target-first masks shared by every expression valued on it.
    """
    values = {name: _finite_or_none(v) for name, v in dict(spot=spot, strike=strike, dte=dte, bid=bid, ask=ask, iv=iv,
                                                           rate=rate, forecast_vol=forecast_vol).items()}
    side = str(side or "").strip().lower()
    if side not in ("call", "put") or any(values[k] is None for k in ("spot", "strike", "dte", "iv", "rate")) \
            or values["spot"] <= 0 or values["strike"] <= 0 or values["iv"] <= 0:
        return PATH_BAD_INPUT, None, None
    if values["bid"] is None or values["ask"] is None or values["bid"] <= 0 or values["ask"] <= 0 or values["ask"] < values["bid"]:
        return PATH_NO_MARKET, None, None
    if values["forecast_vol"] is None or values["forecast_vol"] <= 0:
        return PATH_VOL_UNAVAILABLE, None, None
    sign = 1.0 if side == "call" else -1.0
    stop = _finite_or_none(invalidation)
    if stop is None or stop <= 0 or sign * (values["spot"] - stop) <= 0:
        return PATH_GEOMETRY_UNAVAILABLE, None, None
    goal = _finite_or_none(target)
    target_state = "LEVEL"
    if goal is None:
        target_state = "NONE"
    elif goal <= 0 or sign * (goal - values["spot"]) <= 0:
        goal, target_state = None, "INVALID_IGNORED"
    try:
        sessions = max(1, int(round(float(hold_sessions))))
    except (TypeError, ValueError):
        return PATH_BAD_INPUT, None, None
    # ACK decision C3(b): the option is valued only until its own last exit session (expiry minus the exit
    # buffer); the thesis window is not shortened, but moves after the contract must be sold are never credited.
    option_life = int(math.floor(values["dte"] / CALENDAR_DAYS_PER_SESSION)) - PATH_SETTINGS["option_exit_buffer_sessions"]
    if option_life < 1:
        return PATH_CONTRACT_NOT_HOLDABLE, None, None
    option_window = min(sessions, option_life)
    bands = {int(k): v for k, v in calibration["forecast_error_bands"].items()}
    band_key = min([k for k in bands if k >= sessions] or [max(bands)])
    band = bands[band_key]

    rng = _np.random.default_rng(seed)
    innovations = sample_innovations(calibration["innovation_quantiles"], rng, (int(paths), sessions))
    stop_uniforms = rng.uniform(0.0, 1.0, (int(paths), sessions))
    target_uniforms = rng.uniform(0.0, 1.0, (int(paths), sessions))
    scenarios = {}
    for label in ("p10", "p50", "p90"):
        vol = values["forecast_vol"] * float(band[label])
        daily = vol / math.sqrt(SESSIONS_PER_YEAR)
        prices = values["spot"] * _np.exp(_np.cumsum(daily * innovations - 0.5 * daily * daily, axis=1))
        previous = _np.concatenate([_np.full((int(paths), 1), values["spot"]), prices[:, :-1]], axis=1)

        def touched(level, uniforms, beyond):
            # close beyond the level, or an intraday touch between two closes on the same side
            # (Brownian-bridge crossing probability exp(-2 ln(a/L) ln(b/L) / sigma^2)), matching the
            # scorer's use of session highs and lows
            closed_beyond = beyond(prices)
            both_inside = ~beyond(previous) & ~closed_beyond
            with _np.errstate(divide="ignore", invalid="ignore"):
                crossing = _np.exp(-2.0 * _np.log(previous / level) * _np.log(prices / level) / (daily * daily))
            return closed_beyond | (both_inside & (uniforms < _np.nan_to_num(crossing)))

        stop_hit = touched(stop, stop_uniforms, lambda x: sign * (x - stop) <= 0)
        stop_any = stop_hit.any(axis=1)
        stop_at = _np.where(stop_any, stop_hit.argmax(axis=1), sessions)
        if goal is not None:
            target_hit = touched(goal, target_uniforms, lambda x: sign * (x - goal) >= 0)
            target_any = target_hit.any(axis=1)
            target_at = _np.where(target_any, target_hit.argmax(axis=1), sessions)
        else:
            target_any = _np.zeros(int(paths), dtype=bool)
            target_at = _np.full(int(paths), sessions)
        stop_first = stop_any & (stop_at <= target_at)            # same-session touch counts as stop (scorer policy)
        target_first = target_any & ~stop_first
        exit_index = _np.where(stop_first, stop_at, _np.where(target_first, target_at, sessions - 1))
        exit_price = _np.where(stop_first, stop, _np.where(target_first, goal if goal is not None else 0.0,
                                                           prices[:, sessions - 1]))
        scenarios[label] = {"vol": vol, "exit_index": exit_index, "exit_price": exit_price,
                            "stop_first": stop_first, "target_first": target_first, "prices": prices}
    context = {"values": values, "side": side, "sign": sign, "stop": stop, "sessions": sessions,
               "band_key": band_key, "target_state": target_state, "option_window": option_window}
    return PATH_QUALITY_OK, context, scenarios


def _option_result(context, scenarios) -> dict:
    values, sessions = context["values"], context["sessions"]
    half_spread = (values["ask"] - values["bid"]) / 2.0
    session_index = _np.arange(1, sessions + 1)
    results = {}
    last = context["option_window"] - 1                      # 0-based index of the contract's last exit session
    for label, sc in scenarios.items():
        forced = sc["exit_index"] > last                   # still unresolved when the contract must be sold
        exit_index = _np.where(forced, last, sc["exit_index"])
        exit_price = _np.where(forced, sc["prices"][:, last], sc["exit_price"])
        remaining = (values["dte"] - session_index[exit_index] * CALENDAR_DAYS_PER_SESSION) / 365.0
        exit_value = _np.maximum(_bs_vector(context["side"], exit_price, values["strike"], remaining,
                                            values["rate"], values["iv"]) - half_spread, 0.0)
        results[label] = {"r": float(exit_value.mean() / values["ask"] - 1.0), "vol": sc["vol"],
                          "p_target": float((sc["target_first"] & ~forced).mean()),
                          "p_stop": float((sc["stop_first"] & ~forced).mean()),
                          "forced": float(forced.mean())}
    returns = [results[k]["r"] for k in ("p10", "p50", "p90")]
    return {
        "emp_path_r_cautious": round(min(returns), 6),
        "emp_path_r_central": round(results["p50"]["r"], 6),
        "emp_path_r_upside": round(max(returns), 6),
        "emp_path_p_target_first_central": round(results["p50"]["p_target"], 6),
        "emp_path_p_stop_first_central": round(results["p50"]["p_stop"], 6),
        "emp_path_vol_low": results["p10"]["vol"],
        "emp_path_vol_central": results["p50"]["vol"],
        "emp_path_vol_high": results["p90"]["vol"],
        "emp_path_horizon_band": context["band_key"],
        "emp_path_target_state": context["target_state"],
        "emp_path_last_exit_sessions": context["option_window"],
        "emp_path_forced_exit_share": round(results["p50"]["forced"], 6),
        "emp_path_quality_flag": PATH_QUALITY_OK,
    }


def compute_path_option_ev(*, side, spot, strike, dte, bid, ask, iv, rate, target, invalidation, hold_sessions,
                           forecast_vol, calibration: dict, paths: int, seed: int) -> dict:
    flag, context, scenarios = _simulate_path_exits(
        side=side, spot=spot, strike=strike, dte=dte, bid=bid, ask=ask, iv=iv, rate=rate, target=target,
        invalidation=invalidation, hold_sessions=hold_sessions, forecast_vol=forecast_vol,
        calibration=calibration, paths=paths, seed=seed)
    if flag != PATH_QUALITY_OK:
        return _path_null(flag)
    return _option_result(context, scenarios)


# ── Item 2 increment 3 (ACK 17 Sep 2026): shares on the same paths, and the expression preference ─────────

SHARE_SPREAD_UNAVAILABLE = "SHARE_SPREAD_UNAVAILABLE"
PREFERENCE_UNAVAILABLE = "PREFERENCE_UNAVAILABLE"
SHARE_COLUMNS = (
    "emp_share_r_cautious", "emp_share_r_central", "emp_share_r_upside", "emp_share_spread_estimate",
    "emp_share_quality_flag", "emp_expression_preference", "emp_expression_preference_margin",
)


def abdi_ranaldo_spread(high, low, close, min_sessions=None):
    """Effective bid-ask spread (fraction) from daily high, low and close — Abdi and Ranaldo (2017).

    s^2 = 4 * mean[(c_t - eta_t)(c_t - eta_(t+1))] with c = ln close and eta = (ln high + ln low) / 2; a negative
    mean is reported as 0. Fewer than the governed minimum of usable sessions returns None (never a default).
    """
    minimum = PATH_SETTINGS["share_spread_min_sessions"] if min_sessions is None else int(min_sessions)
    h = _np.asarray(high, dtype=float)
    l = _np.asarray(low, dtype=float)
    c = _np.asarray(close, dtype=float)
    valid = _np.isfinite(h) & _np.isfinite(l) & _np.isfinite(c) & (h > 0) & (l > 0) & (c > 0) & (h >= l)
    if valid.sum() < minimum + 1:
        return None
    h, l, c = h[valid], l[valid], c[valid]
    eta = (_np.log(h) + _np.log(l)) / 2.0
    lc = _np.log(c)
    products = (lc[:-1] - eta[:-1]) * (lc[:-1] - eta[1:])
    if products.size < minimum:
        return None
    return float(math.sqrt(max(4.0 * float(products.mean()), 0.0)))


def expression_preference(option_r_cautious, share_r_cautious) -> str:
    """OPTION / SHARES from the cautious values per unit of capital at risk; NEITHER when neither is positive."""
    option_r = _finite_or_none(option_r_cautious)
    share_r = _finite_or_none(share_r_cautious)
    if option_r is None or share_r is None:
        return PREFERENCE_UNAVAILABLE
    if option_r <= 0 and share_r <= 0:
        return "NEITHER"
    return "OPTION" if option_r > share_r else "SHARES"


def compute_path_expression_ev(*, side, spot, strike, dte, bid, ask, iv, rate, target, invalidation, hold_sessions,
                               forecast_vol, share_spread, calibration: dict, paths: int, seed: int) -> dict:
    flag, context, scenarios = _simulate_path_exits(
        side=side, spot=spot, strike=strike, dte=dte, bid=bid, ask=ask, iv=iv, rate=rate, target=target,
        invalidation=invalidation, hold_sessions=hold_sessions, forecast_vol=forecast_vol,
        calibration=calibration, paths=paths, seed=seed)
    out = {column: None for column in SHARE_COLUMNS}
    if flag != PATH_QUALITY_OK:
        out.update(_path_null(flag))
        out["emp_share_quality_flag"] = flag
        out["emp_expression_preference"] = PREFERENCE_UNAVAILABLE
        return out
    out.update(_option_result(context, scenarios))
    spread = _finite_or_none(share_spread)
    if spread is None or spread < 0:
        out["emp_share_quality_flag"] = SHARE_SPREAD_UNAVAILABLE
        out["emp_expression_preference"] = PREFERENCE_UNAVAILABLE
        return out
    half = spread / 2.0
    sign, spot_value, stop = context["sign"], context["values"]["spot"], context["stop"]
    entry = spot_value * (1.0 + sign * half)                     # buy at the ask (short: sell at the bid)
    risk = sign * (entry - stop * (1.0 - sign * half))            # entry to the stop exit, per share
    if not risk > 0:
        out["emp_share_quality_flag"] = PATH_GEOMETRY_UNAVAILABLE
        out["emp_expression_preference"] = PREFERENCE_UNAVAILABLE
        return out
    share_r = {}
    for label, sc in scenarios.items():
        exit_net = sc["exit_price"] * (1.0 - sign * half)          # sell at the bid (short: buy back at the ask)
        share_r[label] = float((sign * (exit_net - entry)).mean() / risk)
    returns = [share_r[k] for k in ("p10", "p50", "p90")]
    out.update({
        "emp_share_r_cautious": round(min(returns), 6),
        "emp_share_r_central": round(share_r["p50"], 6),
        "emp_share_r_upside": round(max(returns), 6),
        "emp_share_spread_estimate": spread,
        "emp_share_quality_flag": PATH_QUALITY_OK,
    })
    out["emp_expression_preference"] = expression_preference(out["emp_path_r_cautious"], out["emp_share_r_cautious"])
    out["emp_expression_preference_margin"] = round(out["emp_path_r_cautious"] - out["emp_share_r_cautious"], 6)
    return out
