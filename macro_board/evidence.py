"""Measured evidence: what each ETF did next when macro conditions looked like today.

A lean is a statement about recorded history (analog sessions, independent windows,
held-out check), never a forecast with authority.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from .conditions import MISSING, analog_mask


def forward_returns(opens: pd.DataFrame, closes: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return from the next session's open to the close ``horizon`` sessions later (what a
    human reading the board after the close could have traded). NaN until complete."""
    entry = opens.shift(-1)
    exit_ = closes.shift(-horizon)
    return exit_ / entry - 1.0


def effective_n(positions: Sequence[int] | np.ndarray, horizon: int) -> int:
    """Number of non-overlapping ``horizon``-session windows among signal positions
    (greedy thinning): consecutive signal days share most of their outcome."""
    ordered = np.sort(np.asarray(positions, dtype=int))
    if horizon <= 1:
        return int(np.unique(ordered).size)
    count, last = 0, None
    for position in ordered.tolist():
        if last is None or position - last >= horizon:
            count += 1
            last = position
    return count


def summarise(returns: pd.Series | np.ndarray, positions: np.ndarray, horizon: int, *, full: bool = True,
              level: float = 0.8) -> dict:
    """Stats in percent. The interval is a Student-t interval for the mean on independent
    windows (n_eff), so overlapping sessions do not narrow it."""
    values = np.asarray(returns, dtype=float) * 100.0
    n = int(values.size)
    if n == 0:
        return {"n": 0, "n_eff": 0, "mean_pct": None, "median_pct": None, "hit_rate": None,
                "std_pct": None, "t": None, "p10_pct": None, "p90_pct": None, "mean_abs_pct": None,
                "ci_low_pct": None, "ci_high_pct": None}
    n_eff = effective_n(positions, horizon)
    std = float(np.std(values, ddof=1)) if n > 1 else float("nan")
    mean = float(np.mean(values))
    t = mean / (std / np.sqrt(n_eff)) if n_eff >= 2 and std > 0 else float("nan")
    stats = {"n": n, "n_eff": n_eff, "mean_pct": mean, "std_pct": std, "t": None if np.isnan(t) else float(t),
             "hit_rate": float(np.mean(values > 0))}
    if full:
        p10, median, p90 = np.percentile(values, [10, 50, 90])
        stats.update({"median_pct": float(median), "p10_pct": float(p10), "p90_pct": float(p90),
                      "mean_abs_pct": float(np.mean(np.abs(values)))})
        half = None
        if n_eff >= 2 and std > 0:
            half = float(student_t.ppf(0.5 + level / 2.0, n_eff - 1) * std / np.sqrt(n_eff))
        stats.update({"ci_low_pct": None if half is None else mean - half,
                      "ci_high_pct": None if half is None else mean + half})
    return stats


def decide_lean(stats: Mapping, horizon: int, settings: Mapping) -> str:
    if (stats.get("n_eff") or 0) < int(settings["min_effective_n"]):
        return "INSUFFICIENT_SAMPLE"
    t, mean = stats.get("t"), stats.get("mean_pct")
    if t is None or mean is None:
        return "INSUFFICIENT_SAMPLE"
    if abs(t) < float(settings["lean_t_min"]) or abs(mean) < float(settings["lean_min_abs_mean_pct"][str(horizon)]):
        return "NO_CLEAR_LEAN"
    return "UP" if mean > 0 else "DOWN"


def holdout_check(lean: str, holdout: Mapping, settings: Mapping) -> str:
    if lean not in ("UP", "DOWN"):
        return "NOT_APPLICABLE"
    if (holdout.get("n_eff") or 0) < int(settings["min_effective_n_holdout"]) or holdout.get("mean_pct") is None:
        return "HOLDOUT_THIN"
    agrees = (holdout["mean_pct"] > 0) == (lean == "UP")
    return "HOLDOUT_AGREES" if agrees else "HOLDOUT_DISAGREES"


def _round(stats: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()}


def ticker_evidence(fwd: pd.Series, mask: pd.Series, horizon: int, settings: Mapping, *,
                    suppress_lean: bool = False) -> dict:
    """Base rate, analog stats, train-period lean and held-out check for one ETF/horizon.

    ``baseline_lean`` is the price-only lean (all history, same train window) so the board can
    show what macro adds beyond the ETF's own drift. ``suppress_lean`` withholds the lean for
    path-dependent products (leveraged, inverse, volatility) while still showing the evidence."""
    valid = fwd.notna()
    if int(valid.sum()) < int(settings["min_history_sessions"]):
        return {"lean": "INSUFFICIENT_HISTORY", "holdout": "NOT_APPLICABLE", "baseline_lean": "INSUFFICIENT_HISTORY",
                "history_sessions": int(valid.sum())}
    level = float(settings.get("interval_level", 0.8))
    positions = pd.Series(np.arange(len(fwd)), index=fwd.index)

    def stats(selector):
        return summarise(fwd[selector], positions[selector].to_numpy(), horizon, level=level)

    base = stats(valid)
    valid_index = fwd.index[valid]
    cutoff = valid_index[int(len(valid_index) * (1.0 - float(settings["holdout_fraction"])))]
    analog = valid & mask
    train, hold = analog & (fwd.index < cutoff), analog & (fwd.index >= cutoff)
    analog_stats, train_stats, hold_stats = stats(analog), stats(train), stats(hold)
    base_train = stats(valid & (fwd.index < cutoff))
    lean = decide_lean(train_stats, horizon, settings)
    baseline_lean = decide_lean(base_train, horizon, settings)
    if suppress_lean:
        lean = baseline_lean = "PATH_DEPENDENT"
    excess = None
    if analog_stats["mean_pct"] is not None and base["mean_pct"] is not None:
        excess = analog_stats["mean_pct"] - base["mean_pct"]
    return {
        "lean": lean, "holdout": holdout_check(lean, hold_stats, settings), "baseline_lean": baseline_lean,
        "history_sessions": int(valid.sum()), "holdout_from": str(cutoff.date()),
        "base": _round(base), "analog": _round(analog_stats), "train": _round(train_stats),
        "holdout_stats": _round(hold_stats), "excess_vs_base_pct": None if excess is None else round(excess, 4),
    }


def condition_sensitivity(fwd: pd.Series, states: pd.DataFrame, current: Mapping[str, str], horizon: int) -> dict:
    """Per condition: mean forward return when the condition is in today's state minus when it
    is observed in another state (missing excluded), with a Welch t on independent windows."""
    out = {}
    values = fwd.to_numpy(dtype=float)
    valid = np.isfinite(values)
    positions = np.arange(values.size)
    for key, state in current.items():
        if state == MISSING or key not in states.columns:
            out[key] = {"state": state, "excess_pct": None, "t": None, "n_eff_in": 0, "mean_in_pct": None}
            continue
        column = states[key].to_numpy()
        inside = valid & (column == state)
        outside = valid & (column != state) & (column != MISSING)
        a = summarise(values[inside], positions[inside], horizon, full=False)
        b = summarise(values[outside], positions[outside], horizon, full=False)
        excess = t = None
        if a["mean_pct"] is not None and b["mean_pct"] is not None and a["n_eff"] >= 2 and b["n_eff"] >= 2:
            excess = a["mean_pct"] - b["mean_pct"]
            se = np.sqrt((a["std_pct"] ** 2) / a["n_eff"] + (b["std_pct"] ** 2) / b["n_eff"])
            t = excess / se if se > 0 else None
        out[key] = {"state": state, "excess_pct": None if excess is None else round(float(excess), 4),
                    "t": None if t is None or not np.isfinite(t) else round(float(t), 3),
                    "n_eff_in": a["n_eff"], "mean_in_pct": None if a["mean_pct"] is None else round(a["mean_pct"], 4)}
    return out


def choose_analog_depth(states: pd.DataFrame, current: Mapping[str, str], settings: Mapping,
                        max_horizon: int) -> tuple[float, pd.Series, list[dict]]:
    """Loosen the match level from exact towards the floor until the analog set holds enough
    independent ``max_horizon`` windows. Returns (level used, mask, ladder)."""
    ladder = []
    usable = pd.Series(True, index=states.index)
    usable.iloc[-max_horizon:] = False                       # no completed forward window yet
    chosen = None
    for level in settings["analog_match_levels"]:
        mask, _ = analog_mask(states, current, float(level))
        positions = np.flatnonzero((mask & usable).to_numpy())
        n_eff = effective_n(positions, max_horizon)
        ladder.append({"level": float(level), "sessions": int(positions.size), "n_eff": n_eff})
        if chosen is None and n_eff >= int(settings["analog_target_effective_n"]):
            chosen = (float(level), mask)
    if chosen is None:
        level = float(settings["analog_match_levels"][-1])
        chosen = (level, analog_mask(states, current, level)[0])
    return chosen[0], chosen[1], ladder


def build_evidence(*, opens: pd.DataFrame, closes: pd.DataFrame, states: pd.DataFrame, current: Mapping[str, str],
                   tickers: Sequence[str], horizons: Sequence[int], settings: Mapping,
                   path_dependent: Mapping[str, Sequence[int]] | None = None) -> dict:
    """``path_dependent``: ticker -> horizons on which a lean may still be shown."""
    level, mask, ladder = choose_analog_depth(states, current, settings, max(horizons))
    result = {"analog_sessions": int(mask.sum()), "match_level": level, "ladder": ladder,
              "mask": mask, "per_ticker": {}}
    for horizon in horizons:
        fwd_all = forward_returns(opens, closes, horizon)
        for ticker in tickers:
            if ticker not in fwd_all.columns:
                continue
            fwd = fwd_all[ticker]
            entry = result["per_ticker"].setdefault(ticker, {"evidence": {}, "sensitivity": {}})
            allowed = None if path_dependent is None else path_dependent.get(ticker)
            suppress = allowed is not None and horizon not in allowed
            entry["evidence"][str(horizon)] = ticker_evidence(fwd, mask, horizon, settings, suppress_lean=suppress)
            entry["sensitivity"][str(horizon)] = condition_sensitivity(fwd, states, current, horizon)
    return result
