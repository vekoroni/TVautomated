"""Score the old pipeline's dated recommendations against what happened (ACK 18 Sep 2026). Research only.

Inputs (frozen copies, sha256 in the manifest): the `avshunter_signals_*.csv` exports from ACK's OneDrive,
21 May - 2 Aug 2026. Each row is one recommendation: ticker, direction, strike, expiry, recorded premium mid,
structural target, verdict and priority rank, stamped with the run id (the signal time).

Rules, fixed before looking at results:
  - One record per recommendation: dedupe on (run, ticker, direction, strike, expiry); where a run was exported
    twice, the later export wins (morning-updated).
  - Signal time is the run id (UTC). Entry session: the run date if the run finished before the US open
    (13:30 UTC) and it is a session, else the next session.
  - Underlying: direction-signed return from the entry-session open to the close h sessions later (h = 5, 10, 20);
    target reached if the high (CALL) / low (PUT) touched the structural target within 20 sessions.
  - Option: contract rebuilt from ticker/expiry/side/strike (OCC). Stored chains for this period are weekly
    snapshots, so the exit is the first snapshot on or after h sessions, but never after the contract's last
    usable session (expiry minus 2 sessions); if none, the last snapshot inside the contract's life (CAPPED).
    Headline returns are executable: buy at the ASK of the first stored snapshot on or after the entry session
    (within 7 calendar days), sell at the BID of the first snapshot on or after h sessions later. The recorded
    premium mid is also scored ("mid in, bid out") for comparison only: 14% of recorded premiums sit outside
    0.5-2x the market mid near entry (e.g. WM 250 put recorded at 0.05 against a ~21 market), so it is not a
    reliable entry price.
  - Nothing is excluded for being bad. Missing data is counted and reported, never treated as zero.

  venv\\Scripts\\python.exe Enhancements\\research\\legacy_signal_scoring.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from avshunter.c12_outcome.adapters import prices  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session  # noqa: E402

SOURCE = Path(r"C:\Users\ACKVerissimo\OneDrive")
HERE = Path(__file__).resolve().parent / "legacy_signals"
INPUTS = HERE / "inputs"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
HORIZONS = (5, 10, 20)
EXIT_BUFFER_SESSIONS = 2
US_OPEN_UTC_HOUR = 13.5


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_inputs() -> dict:
    INPUTS.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for src in sorted(SOURCE.glob("avshunter_signals_*.csv")):
        dst = INPUTS / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        manifest[src.name] = sha256(dst)
    (HERE / "inputs_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def next_session(day: date) -> date:
    day += timedelta(days=1)
    while not is_xnys_session(day):
        day += timedelta(days=1)
    return day


def entry_session(run_id: str) -> date:
    stamp = datetime.strptime(run_id[:15], "%Y%m%d_%H%M%S")
    day = stamp.date()
    before_open = stamp.hour + stamp.minute / 60.0 < US_OPEN_UTC_HOUR
    return day if (before_open and is_xnys_session(day)) else next_session(day)


def last_usable(expiry: date) -> date:
    session = expiry if is_xnys_session(expiry) else previous_xnys_session(expiry)
    for _ in range(EXIT_BUFFER_SESSIONS):
        session = previous_xnys_session(session)
    return session


def occ(ticker: str, expiry: date, direction: str, strike: float) -> str:
    return f"{ticker}{expiry:%y%m%d}{'C' if direction == 'CALL' else 'P'}{int(round(strike * 1000)):08d}"


def load_signals() -> pd.DataFrame:
    frames = []
    for path in sorted(INPUTS.glob("avshunter_signals_*.csv")):
        d = pd.read_csv(path, low_memory=False)
        d["source_file"] = path.name
        d["export_stamp"] = path.stem.split("_")[-2] + "_" + path.stem.split("_")[-1]
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["Direction"] = d["Direction"].astype(str).str.upper()
    d = d[d["Direction"].isin(["CALL", "PUT"])].copy()
    d["Run_ID"] = d["Run_ID"].astype(str)
    key = ["Run_ID", "Ticker", "Direction", "Strike", "Expiry"]
    d = d.sort_values("export_stamp").drop_duplicates(key, keep="last")
    return d.reset_index(drop=True)


def score(d: pd.DataFrame) -> pd.DataFrame:
    d["entry_session"] = d["Run_ID"].map(entry_session)
    start, end = min(d["entry_session"]), prices.latest_session(prices.DEFAULT_PRICE_DB)
    bars = prices.load_bars(set(d["Ticker"].astype(str).str.upper()), start, end, prices.DEFAULT_PRICE_DB)
    chain = sqlite3.connect(f"file:{CHAIN_DB.as_posix()}?mode=ro", uri=True)
    out = []
    try:
        for r in d.itertuples():
            ticker, sign = str(r.Ticker).upper(), (1.0 if r.Direction == "CALL" else -1.0)
            rec = {"run_id": r.Run_ID, "ticker": ticker, "direction": r.Direction, "verdict": r.Verdict,
                   "priority_rank": r.Priority_Rank, "ev_decision": getattr(r, "EV_Decision", None),
                   "entry_session": r.entry_session, "premium_mid": r.Premium_Mid, "strike": r.Strike,
                   "expiry": r.Expiry, "target": r.Structural_Target}
            path = [b for b in bars.get(ticker, []) if b.session >= r.entry_session]
            if not path or path[0].session != r.entry_session:
                rec["underlying_state"] = "NO_BAR_AT_ENTRY"
                out.append(rec)
                continue
            entry = path[0].open
            rec["underlying_state"] = "OK"
            for h in HORIZONS:
                rec[f"u_ret_{h}"] = sign * (path[h].close / entry - 1.0) if len(path) > h else np.nan
            window = path[1:21] if len(path) > 1 else []
            try:
                target = float(r.Structural_Target)
            except (TypeError, ValueError):
                target = np.nan
            if np.isfinite(target) and window:
                touched = [b for b in window if (b.high >= target if sign > 0 else b.low <= target)]
                rec["target_reached_20"] = bool(touched) if len(path) > 20 else (True if touched else np.nan)
            try:
                expiry = date.fromisoformat(str(r.Expiry)[:10])
                strike, premium = float(r.Strike), float(r.Premium_Mid)
            except (TypeError, ValueError):
                rec["option_state"] = "CONTRACT_UNPARSEABLE"
                out.append(rec)
                continue
            if not (np.isfinite(premium) and premium > 0):
                rec["option_state"] = "NO_RECORDED_PREMIUM"
                out.append(rec)
                continue
            symbol, usable = occ(ticker, expiry, r.Direction, strike), last_usable(expiry)
            snaps = chain.execute(
                "SELECT quote_date, bid, ask FROM chain_snapshots WHERE ticker = ? AND option_symbol = ? "
                "AND quote_date > ? AND quote_date <= ? ORDER BY quote_date",
                (ticker, symbol, r.entry_session.isoformat(), usable.isoformat())).fetchall()
            rec["contract"] = symbol
            if not snaps:
                rec["option_state"] = "NO_CHAIN_SNAPSHOT"
                out.append(rec)
                continue
            rec["option_state"] = "OK"
            sessions = [b.session for b in path]
            entry_snap = chain.execute(
                "SELECT quote_date, bid, ask FROM chain_snapshots WHERE ticker = ? AND option_symbol = ? "
                "AND quote_date >= ? AND quote_date <= ? AND ask > 0 ORDER BY quote_date LIMIT 1",
                (ticker, symbol, r.entry_session.isoformat(),
                 min(r.entry_session + timedelta(days=7), usable).isoformat())).fetchone()
            if entry_snap:
                rec["x_entry_date"], rec["x_entry_ask"] = entry_snap[0], entry_snap[2]
                rec["premium_vs_market_mid"] = premium / ((entry_snap[1] + entry_snap[2]) / 2)                     if entry_snap[1] is not None else np.nan
                x_start = date.fromisoformat(entry_snap[0])
                x_sessions = [s for s in sessions if s >= x_start]
                later = [s for s in snaps if s[0] > entry_snap[0]]
                for h in HORIZONS:
                    due = x_sessions[h] if len(x_sessions) > h else None
                    pick = next((s for s in later if due and s[0] >= due.isoformat()), None)
                    state = "AT_HORIZON"
                    if pick is None and later:
                        pick, state = later[-1], ("CAPPED_AT_CONTRACT_LIFE" if due is not None
                                                  else "OPEN_MARKED_LATEST")
                    if pick is None:
                        rec[f"x_state_{h}"] = "NO_LATER_SNAPSHOT"
                        continue
                    rec[f"x_state_{h}"] = state
                    rec[f"x_ret_{h}"] = (pick[1] / entry_snap[2] - 1.0) if pick[1] is not None else np.nan
            else:
                rec["x_state_5"] = "NO_ENTRY_SNAPSHOT"
            for h in HORIZONS:
                due = sessions[h] if len(sessions) > h else None
                pick = next((s for s in snaps if due and s[0] >= due.isoformat()), None)
                state = "AT_HORIZON"
                if pick is None:
                    pick, state = snaps[-1], "CAPPED_AT_CONTRACT_LIFE"
                    if due is None and usable > (sessions[-1] if sessions else usable):
                        state = "OPEN_MARKED_LATEST"
                bid, ask = pick[1], pick[2]
                rec[f"o_state_{h}"] = state
                rec[f"o_exit_date_{h}"] = pick[0]
                rec[f"o_ret_bid_{h}"] = (bid / premium - 1.0) if bid is not None and bid >= 0 else np.nan
                rec[f"o_ret_mid_{h}"] = (((bid + ask) / 2) / premium - 1.0) if bid is not None and ask else np.nan
            out.append(rec)
    finally:
        chain.close()
    return pd.DataFrame(out)


def summarise(s: pd.DataFrame) -> dict:
    def block(g: pd.DataFrame) -> dict:
        res = {"n": int(len(g))}
        for h in HORIZONS:
            u = g[f"u_ret_{h}"].dropna() if f"u_ret_{h}" in g else pd.Series(dtype=float)
            o = g[f"x_ret_{h}"].dropna() if f"x_ret_{h}" in g else pd.Series(dtype=float)
            m = g[f"o_ret_bid_{h}"].dropna() if f"o_ret_bid_{h}" in g else pd.Series(dtype=float)
            res[f"h{h}"] = {
                "underlying_n": int(len(u)), "underlying_mean": round(float(u.mean()), 4) if len(u) else None,
                "underlying_hit": round(float((u > 0).mean()), 3) if len(u) else None,
                "option_n": int(len(o)), "option_mean_bid": round(float(o.mean()), 4) if len(o) else None,
                "option_median_bid": round(float(o.median()), 4) if len(o) else None,
                "option_hit": round(float((o > 0).mean()), 3) if len(o) else None,
                "option_share_ge_100pct": round(float((o >= 1).mean()), 3) if len(o) else None,
                "recorded_premium_basis_median": round(float(m.median()), 4) if len(m) else None}
        t = g["target_reached_20"].dropna() if "target_reached_20" in g else pd.Series(dtype=float)
        res["target_reached_20"] = round(float(t.astype(float).mean()), 3) if len(t) else None
        return res
    s = s.copy()
    s["rank_num"] = pd.to_numeric(s["priority_rank"], errors="coerce")
    groups = {"ALL": s, "CALL": s[s.direction == "CALL"], "PUT": s[s.direction == "PUT"],
              "TOP5_PER_RUN": s[s.rank_num <= 5], "TOP10_PER_RUN": s[s.rank_num <= 10],
              "RANK_ABOVE_10": s[s.rank_num > 10]}
    for v in s["verdict"].dropna().astype(str).value_counts().index[:6]:
        groups[f"VERDICT_{v}"] = s[s.verdict.astype(str) == v]
    return {
        "records": int(len(s)), "runs": sorted(s["run_id"].unique().tolist()),
        "underlying_state": s["underlying_state"].value_counts(dropna=False).to_dict(),
        "option_state": s["option_state"].value_counts(dropna=False).to_dict() if "option_state" in s else {},
        "groups": {k: block(g) for k, g in groups.items() if len(g)},
    }


def main() -> int:
    manifest = freeze_inputs()
    signals = load_signals()
    scored = score(signals)
    HERE.mkdir(parents=True, exist_ok=True)
    scored.to_csv(HERE / "legacy_signal_scores.csv", index=False)
    summary = summarise(scored)
    summary["inputs"] = manifest
    summary["price_store_latest"] = prices.latest_session(prices.DEFAULT_PRICE_DB).isoformat()
    (HERE / "legacy_signal_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("records", "runs", "underlying_state", "option_state")}, indent=2,
                     default=str))
    for k, v in summary["groups"].items():
        print(k, json.dumps(v, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
