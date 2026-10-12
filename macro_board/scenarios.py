"""Scenario watch (ACK 6 Oct 2026): forward-looking, pre-registered trade scenarios per ETF.

ACK's example: "based on certain conditions QQQ cannot sustain a high of the year for 3 sessions so
I would position puts". A scenario is a trigger built from fixed price primitives, optional macro
condition states and a side (PUT/CALL). For every board ETF the board shows

  * the forward-looking status: TRIGGERED today, WATCHING (level, closes left, deadline session),
    PARTIAL (price met, a macro condition not yet), or NOT_ACTIVE;
  * what followed every past trigger: move in the hypothesis's direction, one expected move in
    favour first vs against first, excursions, and a long-option expectancy proxy (ATM, runway x the
    horizon, bought at the ask and sold at the bid) against buying the same option on every session;
  * a verdict (EDGE / OPPOSITE / NO_EDGE / THIN) with a held-out check;
  * a live record: evening triggers are written once and scored out of sample.

Long options are judged on payoff after costs, not hit rate (ACK, 7 Oct). The option proxy has no
historical quotes: implied vol = realised vol x config iv_over_rv, flat over the hold. Display only:
it never scores, ranks or gates the pipeline (CLAUDE.md rule 6).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.special import ndtr
from scipy.stats import norm

from .evidence import effective_n
from .momentum import streak as streak_series

STATES = ("TRIGGERED", "WATCHING", "PARTIAL", "NOT_ACTIVE")
VERDICTS = ("EDGE", "OPPOSITE", "NO_EDGE", "THIN")


# --- inputs ------------------------------------------------------------------------------------

def daily_move_pct(closes: pd.Series, sessions: int = 20) -> pd.Series:
    """One daily move in percent: realised vol of the sessions BEFORE the day (no self-inflation)."""
    return np.log(closes).diff().rolling(sessions, min_periods=sessions).std().shift(1) * 100.0


# --- triggers -----------------------------------------------------------------------------------

def _new_extreme(c: np.ndarray, lookback: int, extreme: str) -> np.ndarray:
    s = pd.Series(c)
    prior = s.shift(1).rolling(lookback, min_periods=lookback)
    ref = prior.max() if extreme == "high" else prior.min()
    hit = (s >= ref) if extreme == "high" else (s <= ref)
    return (hit & ref.notna() & s.notna()).to_numpy()


def _condition_mask(index: pd.Index, states: pd.DataFrame | None, conditions: Mapping | None) -> np.ndarray:
    if not conditions:
        return np.ones(len(index), dtype=bool)
    if states is None:
        return np.zeros(len(index), dtype=bool)
    aligned = states.reindex(index)
    mask = np.ones(len(index), dtype=bool)
    for key, wanted in conditions.items():
        if key not in aligned.columns:
            return np.zeros(len(index), dtype=bool)
        mask &= (aligned[key] == wanted).to_numpy()
    return mask


def _price_events(rule: Mapping, c: np.ndarray, dm: np.ndarray) -> np.ndarray:
    kind = rule["type"]
    n = len(c)
    out = np.zeros(n, dtype=bool)
    if kind in ("failed_extreme", "held_extreme"):
        lookback, hold, extreme = int(rule["lookback"]), int(rule["hold_sessions"]), rule["extreme"]
        depth = float(rule.get("min_depth_daily_moves", 0))
        new = _new_extreme(c, lookback, extreme)
        for d in np.flatnonzero(new):
            e = d + hold
            if e >= n:
                continue
            window = c[d + 1:e + 1]
            if not np.all(np.isfinite(window)):
                continue
            if kind == "failed_extreme":
                failed = window.max() < c[d] if extreme == "high" else window.min() > c[d]
                gap = (c[d] - c[e]) / c[d] * 100.0 if extreme == "high" else (c[e] - c[d]) / c[d] * 100.0
                if failed and (depth <= 0 or (np.isfinite(dm[d]) and gap >= depth * dm[d])):
                    out[e] = True
            else:
                held = c[e] >= c[d] if extreme == "high" else c[e] <= c[d]
                if held:
                    out[e] = True
    elif kind == "near_extreme":
        lookback, within, extreme = int(rule["lookback"]), float(rule["within_daily_moves"]), rule["extreme"]
        s = pd.Series(c)
        roll = s.rolling(lookback, min_periods=lookback)
        ref = (roll.max() if extreme == "high" else roll.min()).to_numpy()
        dist = np.abs(ref - c) / c * 100.0
        out = np.isfinite(dist) & np.isfinite(dm) & (dist <= within * dm)
    elif kind == "streak":
        need = int(rule["min"])
        st = streak_series(pd.Series(c)).to_numpy()
        target = need if rule["direction"] == "up" else -need
        out = st == target
    elif kind == "big_day":
        k = float(rule["min_daily_moves"])
        move = np.full(n, np.nan)
        move[1:] = (c[1:] / c[:-1] - 1.0) * 100.0
        ok = np.isfinite(move) & np.isfinite(dm)
        out = ok & ((move <= -k * dm) if rule["direction"] == "down" else (move >= k * dm))
    else:
        raise ValueError(f"unknown scenario trigger type {kind!r}")
    return out


def detect(rule: Mapping, closes: pd.Series, *, daily_move_pct: pd.Series, states: pd.DataFrame | None = None,
           conditions: Mapping | None = None) -> np.ndarray:
    """Positions (in ``closes``) of sessions on whose close the scenario triggered."""
    c = closes.to_numpy(dtype=float)
    dm = daily_move_pct.reindex(closes.index).to_numpy(dtype=float)
    events = _price_events(rule, c, dm) & _condition_mask(closes.index, states, conditions)
    return np.flatnonzero(events)


# --- forward-looking status -----------------------------------------------------------------------

def _unmet(index_date, states: pd.DataFrame | None, conditions: Mapping | None) -> list[str]:
    if not conditions:
        return []
    out = []
    for key, wanted in conditions.items():
        now = None if states is None or key not in states.columns or index_date not in states.index else states.loc[index_date, key]
        if now != wanted:
            out.append(f"{key} {wanted} (now {now if now is not None else 'MISSING'})")
    return out


def status(rule: Mapping, closes: pd.Series, *, daily_move_pct: pd.Series, future_sessions: Sequence,
           states: pd.DataFrame | None = None, conditions: Mapping | None = None) -> dict:
    c = closes.to_numpy(dtype=float)
    last = len(c) - 1
    if last < 1 or not np.isfinite(c[last]):
        return {"state": "NOT_ACTIVE", "text": "No current price."}
    dm = daily_move_pct.reindex(closes.index).to_numpy(dtype=float)
    today = closes.index[last]
    unmet = _unmet(today, states, conditions)
    price_now = _price_events(rule, c, dm)
    out = {"as_of": str(today.date()), "level": None, "deadline": None, "closes_left": None}
    if price_now[last]:
        if unmet:
            return {**out, "state": "PARTIAL", "text": f"Price condition met on the {today.date()} close; waiting for " + "; ".join(unmet) + "."}
        return {**out, "state": "TRIGGERED", "text": f"Triggered on the {today.date()} close. Entry would be the next open."}
    kind = rule["type"]
    if kind in ("failed_extreme", "held_extreme"):
        lookback, hold, extreme = int(rule["lookback"]), int(rule["hold_sessions"]), rule["extreme"]
        new = _new_extreme(c, lookback, extreme)
        for d in range(last, max(-1, last - hold), -1):
            if not new[d]:
                continue
            after = c[d + 1:last + 1]
            bettered = after.size and ((after.max() >= c[d]) if extreme == "high" else (after.min() <= c[d]))
            if kind == "failed_extreme" and bettered:
                break
            closes_left = hold - (last - d)
            step = d + hold - last - 1
            deadline = str(future_sessions[step]) if 0 <= step < len(future_sessions) else None
            word = "closing high" if extreme == "high" else "closing low"
            side = "below" if extreme == "high" else "above"
            if kind == "failed_extreme":
                text = (f"New {lookback}-session {word} {c[d]:.2f} on {closes.index[d].date()}. Triggers if the next "
                        f"{closes_left} close(s) stay {side} {c[d]:.2f} (deadline {deadline or 'next sessions'}).")
            else:
                text = (f"New {lookback}-session {word} {c[d]:.2f} on {closes.index[d].date()}. Triggers if the close on "
                        f"{deadline or 'the deadline session'} is still {'at or above' if extreme == 'high' else 'at or below'} {c[d]:.2f}.")
            if unmet:
                text += " Also needs " + "; ".join(unmet) + " on the trigger day."
            return {**out, "state": "WATCHING", "text": text, "level": round(float(c[d]), 4), "deadline": deadline,
                    "closes_left": closes_left}
        return {**out, "state": "NOT_ACTIVE", "text": "No recent extreme to watch."}
    if kind == "streak":
        st = streak_series(closes).iloc[-1]
        need = int(rule["min"]) * (1 if rule["direction"] == "up" else -1)
        if np.isfinite(st) and st == need - (1 if need > 0 else -1):
            return {**out, "state": "WATCHING", "closes_left": 1, "deadline": str(future_sessions[0]) if future_sessions else None,
                    "text": f"{int(abs(st))} {'up' if need > 0 else 'down'} closes in a row; one more triggers."}
    if kind == "near_extreme":
        lookback, within, extreme = int(rule["lookback"]), float(rule["within_daily_moves"]), rule["extreme"]
        ref = (np.nanmax if extreme == "high" else np.nanmin)(c[max(0, last - lookback + 1):last + 1])
        dist_moves = abs(ref - c[last]) / c[last] * 100.0 / dm[last] if np.isfinite(dm[last]) and dm[last] > 0 else None
        if dist_moves is not None and dist_moves <= 2 * within:
            return {**out, "state": "WATCHING", "level": round(float(ref), 4),
                    "text": f"{dist_moves:.1f} daily moves from the {lookback}-session {extreme} {ref:.2f}; triggers within {within:g}."}
    return {**out, "state": "NOT_ACTIVE", "text": "Conditions not met."}


# --- outcomes: what a long option would have paid ------------------------------------------------

def _bs(kind: str, s: float, k: float, t: float, sigma: float) -> float:
    if t <= 0 or sigma <= 0:
        return max(0.0, (s - k) if kind == "CALL" else (k - s))
    v = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + 0.5 * v * v) / v
    d2 = d1 - v
    return s * norm.cdf(d1) - k * norm.cdf(d2) if kind == "CALL" else k * norm.cdf(-d2) - s * norm.cdf(-d1)


def option_multiple(*, side: str, entry: float, exit: float, horizon: int, sigma_annual_pct: float, cfg: Mapping) -> float | None:
    """Return on an ATM long option bought at the ask on ``entry`` and sold at the bid after ``horizon``
    sessions; expiry = runway_multiple x horizon sessions; vol = sigma x iv_over_rv, flat."""
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (entry, exit, sigma_annual_pct)) or entry <= 0:
        return None
    sigma = sigma_annual_pct / 100.0 * float(cfg["iv_over_rv"])
    t0 = float(cfg["runway_multiple"]) * horizon / 252.0
    t1 = t0 - horizon / 252.0
    p0 = _bs(side, entry, entry, t0, sigma)
    p1 = _bs(side, exit, entry, t1, sigma)
    half = float(cfg["spread_pct_of_premium"]) / 200.0
    ask, bid = p0 * (1 + half), p1 * (1 - half)
    return None if ask <= 0 else bid / ask - 1.0


def _bs_vec(kind: str, s: np.ndarray, k: np.ndarray, t: float, sigma: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        v = sigma * math.sqrt(t)
        d1 = (np.log(s / k) + 0.5 * v * v) / v
        d2 = d1 - v
        if kind == "CALL":
            return s * ndtr(d1) - k * ndtr(d2)
        return k * ndtr(-d2) - s * ndtr(-d1)


def baseline_multiple(opens: pd.Series, closes: pd.Series, rv_annual_pct: pd.Series, *, side: str, horizon: int,
                      cfg: Mapping) -> float | None:
    """Mean option_multiple of buying the same option on every session (vectorised outcome())."""
    entry = opens.shift(-1).to_numpy(dtype=float)
    exit_ = closes.shift(-horizon).to_numpy(dtype=float)
    sigma = rv_annual_pct.to_numpy(dtype=float) / 100.0 * float(cfg["iv_over_rv"])
    ok = np.isfinite(entry) & np.isfinite(exit_) & np.isfinite(sigma) & (entry > 0) & (sigma > 0)
    if not ok.any():
        return None
    e, x, sg = entry[ok], exit_[ok], sigma[ok]
    t0 = float(cfg["runway_multiple"]) * horizon / 252.0
    t1 = t0 - horizon / 252.0
    p0 = _bs_vec(side, e, e, t0, sg)
    p1 = _bs_vec(side, x, e, t1, sg) if t1 > 0 else np.maximum(0.0, (x - e) if side == "CALL" else (e - x))
    half = float(cfg["spread_pct_of_premium"]) / 200.0
    ask, bid = p0 * (1 + half), p1 * (1 - half)
    m = bid / ask - 1.0
    m = m[np.isfinite(m) & (ask > 0)]
    return round(float(m.mean()), 6) if m.size else None


def _outcome_arr(event: int, side: str, horizon: int, o: np.ndarray, c: np.ndarray, dm: np.ndarray, rv: np.ndarray,
                 dates: Sequence[str], cfg: Mapping) -> dict | None:
    entry_i, exit_i = event + 1, event + horizon
    if exit_i >= len(c):
        return None
    ov = o[entry_i]
    path = c[entry_i:exit_i + 1]
    if not math.isfinite(ov) or ov <= 0 or not np.all(np.isfinite(path)):
        return None
    sign = 1.0 if side == "CALL" else -1.0
    signed = sign * (path / ov - 1.0) * 100.0
    first = "NEITHER"
    if math.isfinite(dm[event]) and dm[event] > 0:
        barrier = dm[event] * math.sqrt(horizon)
        fav, adv = np.flatnonzero(signed >= barrier), np.flatnonzero(signed <= -barrier)
        if fav.size and (not adv.size or fav[0] < adv[0]):
            first = "FAVOURABLE"
        elif adv.size:
            first = "ADVERSE"
    return {"event": int(event), "trigger_session": dates[event], "entry_session": dates[entry_i],
            "exit_session": dates[exit_i], "side_move_pct": round(float(signed[-1]), 4), "first": first,
            "mfe_pct": round(float(signed.max()), 4), "mae_pct": round(float(signed.min()), 4),
            "option_multiple": option_multiple(side=side, entry=float(ov), exit=float(path[-1]), horizon=horizon,
                                               sigma_annual_pct=float(rv[event]), cfg=cfg) if math.isfinite(rv[event]) else None}


def outcomes_vec(events: np.ndarray, side: str, horizon: int, o: np.ndarray, c: np.ndarray, dm: np.ndarray,
                 rv: np.ndarray, dates: Sequence[str], cfg: Mapping) -> list[dict]:
    """Same result as _outcome_arr for every event, in one array pass (sliding windows + vector pricing)."""
    events = np.asarray(events, dtype=int)
    events = events[events + horizon < len(c)]
    if events.size == 0:
        return []
    windows = np.lib.stride_tricks.sliding_window_view(c, horizon)[events + 1]      # closes entry .. exit
    entry = o[events + 1]
    ok = np.isfinite(entry) & (entry > 0) & np.all(np.isfinite(windows), axis=1)
    events, windows, entry = events[ok], windows[ok], entry[ok]
    if events.size == 0:
        return []
    sign = 1.0 if side == "CALL" else -1.0
    signed = sign * (windows / entry[:, None] - 1.0) * 100.0
    barrier = dm[events] * math.sqrt(horizon)
    has_b = np.isfinite(barrier) & (barrier > 0)
    big = horizon + 1
    fav_i = np.where(signed >= barrier[:, None], np.arange(horizon)[None, :], big).min(axis=1)
    adv_i = np.where(signed <= -barrier[:, None], np.arange(horizon)[None, :], big).min(axis=1)
    first = np.where(~has_b, "NEITHER", np.where((fav_i < big) & (fav_i < adv_i), "FAVOURABLE",
                                                 np.where(adv_i < big, "ADVERSE", "NEITHER")))
    sigma = rv[events] / 100.0 * float(cfg["iv_over_rv"])
    t0 = float(cfg["runway_multiple"]) * horizon / 252.0
    t1 = t0 - horizon / 252.0
    p0 = _bs_vec(side, entry, entry, t0, sigma)
    exit_ = windows[:, -1]
    p1 = _bs_vec(side, exit_, entry, t1, sigma) if t1 > 0 else np.maximum(0.0, (exit_ - entry) if side == "CALL" else (entry - exit_))
    half = float(cfg["spread_pct_of_premium"]) / 200.0
    with np.errstate(divide="ignore", invalid="ignore"):
        mult = (p1 * (1 - half)) / (p0 * (1 + half)) - 1.0
    mult_ok = np.isfinite(mult) & np.isfinite(sigma) & (sigma > 0) & (p0 > 0)
    rows = []
    for j, e in enumerate(events):
        rows.append({"event": int(e), "trigger_session": dates[e], "entry_session": dates[e + 1],
                     "exit_session": dates[e + horizon], "side_move_pct": round(float(signed[j, -1]), 4),
                     "first": str(first[j]), "mfe_pct": round(float(signed[j].max()), 4),
                     "mae_pct": round(float(signed[j].min()), 4),
                     "option_multiple": float(mult[j]) if mult_ok[j] else None})
    return rows


def outcome(*, event: int, side: str, horizon: int, opens: pd.Series, closes: pd.Series, daily_move_pct: pd.Series,
            rv_annual_pct: pd.Series, cfg: Mapping) -> dict | None:
    """Next open -> close ``horizon`` sessions after the trigger day (board convention)."""
    return _outcome_arr(event, side, horizon, opens.to_numpy(dtype=float), closes.to_numpy(dtype=float),
                        daily_move_pct.reindex(closes.index).to_numpy(dtype=float),
                        rv_annual_pct.reindex(closes.index).to_numpy(dtype=float),
                        [str(d.date()) for d in closes.index], cfg)


# --- verdict ----------------------------------------------------------------------------------------

def _t(values: np.ndarray, n_eff: int) -> float | None:
    if values.size < 2 or n_eff < 2:
        return None
    sd = float(np.std(values, ddof=1))
    return None if sd <= 0 else float(np.mean(values)) / (sd / math.sqrt(n_eff))


def _mean_of(rows: Sequence[Mapping], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(float(np.mean(vals)), 4) if vals else None


def verdict(rows: Sequence[Mapping], *, baseline_multiple: float | None, horizon: int, settings: Mapping) -> dict:
    rows = sorted((r for r in rows if r.get("option_multiple") is not None), key=lambda r: r["event"])
    n = len(rows)
    n_eff = effective_n([r["event"] for r in rows], horizon) if rows else 0
    out = {"n": n, "n_eff": n_eff, "baseline_multiple": baseline_multiple, "verdict": "THIN", "holdout": "NOT_APPLICABLE"}
    if not rows:
        return out
    mult = np.array([r["option_multiple"] for r in rows], dtype=float)
    side = np.array([r["side_move_pct"] for r in rows], dtype=float)
    firsts = [r.get("first") for r in rows]
    wins, losses = mult[mult > 0], mult[mult <= 0]
    diff = float(mult.mean()) - (baseline_multiple or 0.0)
    t_diff = _t(mult - (baseline_multiple or 0.0), n_eff)
    t_side = _t(side, n_eff)
    out.update({
        "option_expectancy": round(float(mult.mean()), 4), "option_win_rate": round(float((mult > 0).mean()), 4),
        "avg_win": round(float(wins.mean()), 4) if wins.size else None,
        "avg_loss": round(float(losses.mean()), 4) if losses.size else None,
        "edge_vs_every_session": round(diff, 4), "t_edge": None if t_diff is None else round(t_diff, 3),
        "side_move_mean_pct": round(float(side.mean()), 4), "side_move_median_pct": round(float(np.median(side)), 4),
        "t_side": None if t_side is None else round(t_side, 3), "side_right_rate": round(float((side > 0).mean()), 4),
        "favourable_first_rate": round(firsts.count("FAVOURABLE") / n, 4),
        "adverse_first_rate": round(firsts.count("ADVERSE") / n, 4),
        "mfe_mean_pct": _mean_of(rows, "mfe_pct"), "mae_mean_pct": _mean_of(rows, "mae_pct"),
    })
    if n_eff < int(settings["min_effective_n"]):
        return out
    hold_n = max(1, int(math.ceil(n * float(settings["holdout_fraction"]))))
    hold = rows[-hold_n:]
    hold_eff = effective_n([r["event"] for r in hold], horizon)
    hold_diff = float(np.mean([r["option_multiple"] for r in hold])) - (baseline_multiple or 0.0)
    hold_side = float(np.mean([r["side_move_pct"] for r in hold]))
    t_min = float(settings["lean_t_min"])

    def holdout(sign_ok: bool) -> str:
        if hold_eff < int(settings["min_effective_n_holdout"]):
            return "THIN"
        return "AGREES" if sign_ok else "DISAGREES"

    if diff > 0 and t_diff is not None and t_diff >= t_min:
        out.update({"verdict": "EDGE", "holdout": holdout(hold_diff > 0)})
    elif t_side is not None and t_side <= -t_min:
        out.update({"verdict": "OPPOSITE", "holdout": holdout(hold_side < 0)})
    else:
        out["verdict"] = "NO_EDGE"
    return out


# --- many tests at once: Benjamini-Hochberg false-discovery check -----------------------------------

def fdr_flags(pvalues: Sequence[float], q: float) -> list[bool]:
    """True where a result survives Benjamini-Hochberg at false-discovery rate q."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    cutoff = 0
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= rank / m * q:
            cutoff = rank
    keep = set(order[:cutoff])
    return [i in keep for i in range(m)]


def apply_fdr(rows: Sequence[dict], q: float) -> dict:
    """Mark each scenario x ETF x horizon result with survives_fdr, across the whole library
    (every result counts as one try), and return the trial count."""
    cells = [v for r in rows for v in (r.get("by_horizon") or {}).values()]
    p_edge = [1.0 - float(ndtr(v["t_edge"])) if v.get("t_edge") is not None else 1.0 for v in cells]
    p_opp = [float(ndtr(v["t_side"])) if v.get("t_side") is not None else 1.0 for v in cells]
    keep_edge, keep_opp = fdr_flags(p_edge, q), fdr_flags(p_opp, q)
    for v, ke, ko in zip(cells, keep_edge, keep_opp):
        v["survives_fdr"] = (v.get("verdict") == "EDGE" and ke) or (v.get("verdict") == "OPPOSITE" and ko)
    return {"tests": len(cells), "q": q,
            "edges": sum(1 for v in cells if v.get("verdict") == "EDGE"),
            "edges_surviving": sum(1 for v in cells if v.get("verdict") == "EDGE" and v["survives_fdr"]),
            "opposites": sum(1 for v in cells if v.get("verdict") == "OPPOSITE"),
            "opposites_surviving": sum(1 for v in cells if v.get("verdict") == "OPPOSITE" and v["survives_fdr"])}


# --- live record -------------------------------------------------------------------------------------

def _key(rec: Mapping) -> tuple:
    return rec.get("scenario"), rec.get("ticker"), rec.get("trigger_session")


def record_triggers(path: Path, records: Sequence[Mapping]) -> int:
    """Append triggers not yet recorded (one per scenario, ticker and trigger session)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(_key(json.loads(line)))
            except ValueError:
                continue
    new = [r for r in records if _key(r) not in seen]
    with path.open("a", encoding="utf-8") as fh:
        for r in new:
            fh.write(json.dumps(r) + "\n")
    return len(new)


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# --- orchestration ---------------------------------------------------------------------------------

def _compact(v: Mapping) -> dict:
    out = {}
    for k, x in v.items():
        if k == "macro_like_today" and isinstance(x, Mapping):
            out[k] = _compact(x)
        elif isinstance(x, float):
            out[k] = round(x, 3)
        else:
            out[k] = x
    return out


def build(*, opens: pd.DataFrame, closes: pd.DataFrame, states: pd.DataFrame, analog_mask: pd.Series | None,
          tickers: Sequence[str], future_sessions: Sequence, cfg: Mapping, evidence_settings: Mapping,
          ledger_path: Path, record: bool, focus: Sequence[str]) -> dict:
    horizons = [int(h) for h in cfg["horizons"]]
    opt = cfg["option_proxy"]
    library = cfg["library"]
    rows_out, live, triggers = [], [], []
    baselines: dict = {}
    for t in tickers:
        if t not in closes.columns:
            continue
        c = closes[t]
        if int(c.notna().sum()) < int(cfg["min_history_sessions"]):
            continue
        o = opens[t]
        dm = daily_move_pct(c, int(opt["rv_sessions"]))
        rv = dm * math.sqrt(252.0)
        o_a, c_a, dm_a, rv_a = (x.to_numpy(dtype=float) for x in (o, c, dm, rv))
        dates = [str(d.date()) for d in c.index]
        for side in ("PUT", "CALL"):
            for h in horizons:
                baselines[(t, side, h)] = baseline_multiple(o, c, rv, side=side, horizon=h, cfg=opt)
        for sc in library:
            if sc.get("applies_to") not in (None, "all") and t not in sc.get("applies_to", []):
                continue
            rule, cond, side = sc["trigger"], sc.get("conditions") or {}, sc["side"]
            events = detect(rule, c, daily_move_pct=dm, states=states, conditions=cond)
            per_h, recent = {}, []
            for h in horizons:
                outs = outcomes_vec(events, side, h, o_a, c_a, dm_a, rv_a, dates, opt)
                v = verdict(outs, baseline_multiple=baselines.get((t, side, h)), horizon=h, settings=evidence_settings)
                if analog_mask is not None and outs:
                    m = analog_mask.reindex(c.index).fillna(False).to_numpy()
                    sub = [r for r in outs if m[r["event"]]]
                    v["macro_like_today"] = {"n": len(sub), "n_eff": effective_n([r["event"] for r in sub], h) if sub else 0,
                                             "option_expectancy": round(float(np.mean([r["option_multiple"] for r in sub if r["option_multiple"] is not None])), 4)
                                             if sub and any(r["option_multiple"] is not None for r in sub) else None,
                                             "side_move_mean_pct": round(float(np.mean([r["side_move_pct"] for r in sub])), 4) if sub else None}
                per_h[str(h)] = _compact(v)
                if h == int(cfg["detail_horizon"]):
                    # [trigger session, move for the hypothesis %, which side was hit first, option return]
                    recent = [[r["trigger_session"], round(r["side_move_pct"], 2), r["first"][0],
                               None if r["option_multiple"] is None else round(r["option_multiple"], 3)]
                              for r in outs[-int(cfg["recent_events"]):][::-1]]
            st = status(rule, c, daily_move_pct=dm, future_sessions=future_sessions, states=states, conditions=cond)
            row = {"scenario": sc["id"], "ticker": t, "side": side, "events": int(len(events)), "status": st,
                   "by_horizon": per_h, "recent": recent}
            rows_out.append(row)
            if st["state"] in ("TRIGGERED", "WATCHING", "PARTIAL"):
                live.append({"scenario": sc["id"], "ticker": t, "side": side, **st,
                             "record": per_h.get(str(cfg["detail_horizon"]))})
            if st["state"] == "TRIGGERED":
                triggers.append({"scenario": sc["id"], "ticker": t, "side": side, "trigger_session": st["as_of"],
                                 "registered": sc.get("registered")})
    multiple_tests = apply_fdr(rows_out, float(cfg["fdr_q"]))
    recorded = record_triggers(ledger_path, triggers) if record and triggers else 0
    ledger = []
    for rec in read_ledger(ledger_path):
        t = rec.get("ticker")
        if t not in closes.columns:
            continue
        idx = closes.index.get_indexer([pd.Timestamp(rec["trigger_session"])])[0]
        c = closes[t]
        dm = daily_move_pct(c, int(opt["rv_sessions"]))
        scored = {}
        for h in horizons:
            r = outcome(event=int(idx), side=rec["side"], horizon=h, opens=opens[t], closes=c, daily_move_pct=dm,
                        rv_annual_pct=dm * math.sqrt(252.0), cfg=opt) if idx >= 0 else None
            scored[str(h)] = None if r is None else {k: r[k] for k in ("side_move_pct", "first", "option_multiple", "exit_session")}
        ledger.append({**rec, "scored": scored})
    order = {s: i for i, s in enumerate(STATES)}
    live.sort(key=lambda x: (order.get(x["state"], 9), 0 if x["ticker"] in focus else 1, x["ticker"]))
    return {"library": library, "horizons": horizons, "rows": rows_out, "live": live, "ledger": ledger[::-1],
            "recorded_this_build": recorded, "multiple_tests": multiple_tests, "settings": {k: v for k, v in cfg.items() if k != "library"}}
