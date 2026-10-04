"""BEH-001 corrected evaluation, stage B: score stage-A candidates with the C12 outcome scorer.

A2-1 as clarified in the Part 4 decisions. Rules fixed before results are read:
- Own timeframe: a 1d candidate is followed on daily bars, 1w on weekly bars and 1mo on
  monthly bars, built from completed daily bars strictly after the cut (the first period
  holds post-cut days only, so no pre-cut extreme leaks in). Research limit:
  1d 250 bars, 1w 104 bars, 1mo 24 bars (about two years for weekly and monthly).
- Passage rules are C12's (avshunter/c12_outcome/passage.py): target touched by the
  favourable extreme, invalidation by the adverse extreme, both in one bar = AMBIGUOUS
  (counted as invalidation), a missing bar = DATA_GAP (censored), no touch by the data end
  = OPEN_CENSORED. Unresolved is censored, never success or failure.
- Tests (reference = close at the cut):
    ACT          DETECTED candidates: trigger before invalidation (activation);
    OUT_ACTIVATED ACTIVATED candidates: Outcome_Level before invalidation (RQ-1);
    OUT_DETECTED DETECTED candidates: Outcome_Level before invalidation over the whole path.
  A geometry with a level on the wrong side of the reference is NOT_SCORABLE and counted.
- Baseline: C12 matched base rate. The candidate's own barrier distances, in its own
  timeframe ATR(14) units, are applied on the same date and in the same direction to every
  ticker in the panel. Same-date matching removes market drift; there is no 50% reference.
- Statistics: Aalen-Johansen cumulative incidence (C12 estimators) at fixed own-timeframe
  horizons. Interval: block bootstrap over cut blocks (1d: 2 cuts; 1w: 6 cuts; 1mo: 12 cuts),
  2,000 resamples, seed 20261001, 2.5%/97.5%. ESTIMABLE needs >= 100 scorable candidates
  and >= 20 blocks; weekly and monthly windows overlap across blocks, so their intervals
  are wider in truth than shown.
- Populations: ALL, ORIGINAL (Discovery-eligible at the cut) and NEWLY_ADMITTED (ineligible).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from avshunter.c12_outcome.base_rate import Panel, matched_incidence  # noqa: E402
from avshunter.c12_outcome.estimators import _curves, _multiplicities  # noqa: E402
from avshunter.c12_outcome.geometry import classify  # noqa: E402
from avshunter.c12_outcome.model import Bar, Direction, OutcomeState  # noqa: E402
from avshunter.c12_outcome.passage import evaluate_passage  # noqa: E402
from dir002_replay import read_bars, select_tickers  # noqa: E402

WINDOW = {"1d": 250, "1w": 104, "1mo": 24}
HORIZONS = {"1d": (5, 10, 20, 60, 120, 250), "1w": (4, 13, 26, 52, 104), "1mo": (3, 6, 12, 24)}
BLOCK_CUTS = {"1d": 2, "1w": 6, "1mo": 12}
RESAMPLES, SEED, LO, HI = 2000, 20261001, 0.025, 0.975
T, S, C = 0, 1, 2


def period_key(index: pd.DatetimeIndex, tf: str):
    if tf == "1d":
        return index
    return index.to_period("W-FRI" if tf == "1w" else "M")


def load_wide(tickers):
    frames = {}
    for t in tickers:
        try:
            f = read_bars(t)
        except Exception:
            continue
        if not f.empty:
            frames[t] = f.set_index("date")
    cols = sorted(frames)
    wide = {f: pd.DataFrame({t: frames[t][f] for t in cols}).sort_index() for f in ("open", "high", "low", "close")}
    return cols, wide


def own_tf_bars(wide, rows: pd.Index, tf: str):
    """Aggregate daily rows to own-timeframe bars; returns (labels, open, high, low, close) arrays."""
    keys = period_key(rows, tf)
    o = wide["open"].loc[rows].groupby(keys).first()
    h = wide["high"].loc[rows].groupby(keys).max()
    lo = wide["low"].loc[rows].groupby(keys).min()
    c = wide["close"].loc[rows].groupby(keys).last()
    last_day = pd.Series(rows, index=rows).groupby(keys).max()
    return last_day.to_numpy(), o.to_numpy(), h.to_numpy(), lo.to_numpy(), c.to_numpy()


def atr_at(wide, dates: pd.DatetimeIndex, cut_pos: int, tf: str, period: int = 14) -> np.ndarray:
    span = {"1d": period + 1, "1w": 5 * (period + 3), "1mo": 23 * (period + 3)}[tf]
    rows = dates[max(0, cut_pos + 1 - span): cut_pos + 1]
    _, _, h, lo, c = own_tf_bars(wide, rows, tf)
    if len(c) <= period:
        return np.full(h.shape[1], np.nan)
    h, lo, c = h[-(period + 1):], lo[-(period + 1):], c[-(period + 1):]
    tr = np.maximum.reduce([h[1:] - lo[1:], np.abs(h[1:] - c[:-1]), np.abs(lo[1:] - c[:-1])])
    atr = tr.mean(axis=0)
    return np.where(atr > 0, atr, np.nan)


class Group:
    def __init__(self, n_blocks: int, window: int):
        self.obs = np.zeros((n_blocks, 3, window + 1))
        self.base = np.zeros((n_blocks, 3, window + 1))
        self.n = 0
        self.not_scorable = 0
        self.ambiguous = 0
        self.blocks = set()


def summarise(g: Group, tf: str, rng_seed: int) -> dict:
    window = WINDOW[tf]
    used = sorted(g.blocks)
    obs, base = g.obs[used], g.base[used]
    t_o, s_o, _ = _curves(obs.sum(0))
    t_b, s_b, _ = _curves(base.sum(0))
    mult = _multiplicities(len(used), RESAMPLES, rng_seed) if used else np.zeros((0, 0))
    rt_o, rs_o, _ = _curves(np.einsum("rb,bct->rct", mult, obs)) if used else (None, None, None)
    rt_b, _, _ = _curves(np.einsum("rb,bct->rct", mult, base)) if used else (None, None, None)
    censored = float(obs[:, C, :].sum())
    out = {"n": g.n, "scorable": int(obs.sum()), "not_scorable": g.not_scorable, "ambiguous": g.ambiguous,
           "censored": int(censored), "blocks": len(used),
           "estimability": "ESTIMABLE" if obs.sum() >= 100 and len(used) >= 20 else "NOT_ESTIMABLE"}
    for h in HORIZONS[tf]:
        if h > window or not used:
            continue
        i = h - 1
        ex = rt_o[:, i] - rt_b[:, i]
        out[f"h{h}"] = {
            "target_obs": round(float(t_o[i]), 4), "target_base": round(float(t_b[i]), 4),
            "excess": round(float(t_o[i] - t_b[i]), 4),
            "excess_lo": round(float(np.quantile(ex, LO)), 4), "excess_hi": round(float(np.quantile(ex, HI)), 4),
            "stop_obs": round(float(s_o[i]), 4), "stop_base": round(float(s_b[i]), 4),
            "target_obs_lo": round(float(np.quantile(rt_o[:, i], LO)), 4),
            "target_obs_hi": round(float(np.quantile(rt_o[:, i], HI)), 4)}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", required=True)
    p.add_argument("--tickers", type=int, default=500)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    rows = [json.loads(l) for l in open(a.candidates, encoding="utf-8")]
    rows = [r for r in rows if "engine_error" not in r]
    engine_errors = sum(1 for _ in open(a.candidates, encoding="utf-8")) - len(rows)
    cand = pd.DataFrame(rows)
    tickers, wide = load_wide(select_tickers(a.tickers))
    col = {t: i for i, t in enumerate(tickers)}
    dates = wide["close"].index
    pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
    cuts = sorted(cand["cut"].unique())
    cut_index = {c: i for i, c in enumerate(cuts)}
    groups: dict = {}
    seeds = {}

    def group(key, tf):
        if key not in groups:
            groups[key] = Group(len(cuts) // BLOCK_CUTS[tf] + 1, WINDOW[tf])
            seeds[key] = SEED
        return groups[key]

    for cut in cuts:
        cp = pos[cut]
        for tf in WINDOW:
            sub = cand[(cand["cut"] == cut) & (cand["tf"] == tf)]
            if sub.empty:
                continue
            fwd_rows = dates[cp + 1:]
            labels, fo, fh, fl, fc = own_tf_bars(wide, fwd_rows, tf) if len(fwd_rows) else ([], *(np.zeros((0, len(tickers))),) * 4)
            labels, fo, fh, fl, fc = labels[:WINDOW[tf]], fo[:WINDOW[tf]], fh[:WINDOW[tf]], fl[:WINDOW[tf]], fc[:WINDOW[tf]]
            ref = wide["close"].iloc[cp].to_numpy()
            panel = Panel(tuple([dates[cp].date()] + [pd.Timestamp(x).date() for x in labels]), tuple(tickers),
                          np.vstack([ref, fo]), np.vstack([ref, fh]), np.vstack([ref, fl]), np.vstack([ref, fc]))
            atr = atr_at(wide, dates, cp, tf)
            sessions = list(panel.sessions[1:])
            block = cut_index[cut] // BLOCK_CUTS[tf]
            for r in sub.itertuples(index=False):
                j = col.get(r.ticker)
                if j is None:
                    continue
                tests = []
                if r.state == "DETECTED":
                    tests.append(("ACT", r.trigger))
                if r.outcome is not None and not (isinstance(r.outcome, float) and np.isnan(r.outcome)):
                    tests.append(("OUT_ACTIVATED" if r.state == "ACTIVATED" else "OUT_DETECTED", r.outcome))
                pop = "ORIGINAL" if r.eligibility == "ELIGIBLE" else "NEWLY_ADMITTED"
                for test, target in tests:
                    keys = [(test, tf, r.scope, r.type, r.dir, "ALL"), (test, tf, "*", "*", r.dir, "ALL"),
                            (test, tf, "*", "*", r.dir, pop), (test, tf, "*", "*", "*", "ALL"),
                            (test, tf, "*", "*", "*", pop)]
                    gs = [group(k, tf) for k in keys]
                    for g in gs:
                        g.n += 1
                    geometry = classify(r.dir, r.close, r.invalidation, target, None)
                    a_j = atr[j]
                    if not geometry.scorable or geometry.target_state.value != "LEVEL" or not np.isfinite(a_j):
                        for g in gs:
                            g.not_scorable += 1
                        continue
                    bars = {}
                    for k, s in enumerate(sessions):
                        if np.isfinite(fh[k, j]) and np.isfinite(fl[k, j]):
                            bars[s] = Bar(s, float(fo[k, j]), float(fh[k, j]), float(fl[k, j]), float(fc[k, j]))
                    res = evaluate_passage(geometry, sessions, bars, WINDOW[tf])
                    if res.state is OutcomeState.TARGET_FIRST:
                        cause, time = T, res.resolution_session
                    elif res.state in (OutcomeState.STOP_FIRST, OutcomeState.AMBIGUOUS):
                        cause, time = S, res.resolution_session
                    else:
                        cause, time = C, res.sessions_observed
                    direction = Direction(r.dir)
                    m = matched_incidence(direction, abs(target - r.close) / a_j, abs(r.close - r.invalidation) / a_j,
                                          panel, 0, len(sessions), atr)
                    tf_frac = np.asarray(m.target_fractions)
                    sf_frac = np.asarray(m.stop_fractions)
                    for g in gs:
                        g.blocks.add(block)
                        g.obs[block, cause, min(max(time, 0), WINDOW[tf])] += 1
                        if res.state is OutcomeState.AMBIGUOUS:
                            g.ambiguous += 1
                        if len(tf_frac):
                            g.base[block, T, 1:len(tf_frac) + 1] += tf_frac
                            g.base[block, S, 1:len(sf_frac) + 1] += sf_frac
                        remainder = 1.0 - tf_frac.sum() - sf_frac.sum()
                        if remainder > 0:
                            g.base[block, C, len(sessions)] += remainder
        print(f"cut {cut} done", flush=True)

    out = []
    for key, g in groups.items():
        test, tf, scope, kind, direction, pop = key
        out.append({"test": test, "tf": tf, "scope": scope, "type": kind, "dir": direction, "population": pop,
                    **summarise(g, tf, seeds[key])})
    meta = {"candidates_file": a.candidates, "engine_errors": engine_errors, "tickers_in_panel": len(tickers),
            "cuts": len(cuts), "first_cut": cuts[0], "last_cut": cuts[-1], "data_end": str(dates[-1].date())}
    Path(a.out).write_text(json.dumps({"meta": meta, "groups": out}, indent=1, default=str), encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
