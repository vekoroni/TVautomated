"""Daily outcome tracker for the decision ledger (workaround week, from 12 Oct 2026). Read-only on the price store.

Every ledger row is tracked whether or not it was traded, so the evidence has no selection bias.
Run from the repo root after the price store has the new session (e.g. after the Evening):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\track_outcomes.py data\\scratch\\workaround\\decision_ledger_2026-10-12.csv
Writes next to the ledger: <ledger>_outcomes.csv and <ledger>_summary.csv (overwritten each run).

Rules (frozen; change only with a new version number):
  ENTRY   READY rows: open of the first session on/after decision_session.
          WAIT rows: close of the first session on/after decision_session that closes beyond the trigger
          (call: close > trigger, put: close < trigger). No such close yet = NOT_TRIGGERED.
  PATH    from the session after a close entry (same session for an open entry), daily high/low.
          TARGET = level touched; STOP = practical_stop touched; INVALIDATED = invalidation touched.
          If target and stop are touched in the same session the result is STOP (conservative).
  RULE B  (v2) half_target touched before invalidation, same path and window: status_half_vs_invalidation.
  WINDOW  q80_sessions after entry (planned hold); still open after that = EXPIRED, scored at that close.
  MFE/MAE favourable / adverse excursion from entry, in % and in ATR, after 1, 2, 3, 5 and 10 sessions.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "track_outcomes_v2"
PRICE_DB = Path.cwd() / "data" / "canonical" / "historical_prices.sqlite"
HORIZONS = (1, 2, 3, 5, 10)


def load_prices(tickers, since):
    marks = ",".join("?" * len(tickers))
    with sqlite3.connect(f"file:{PRICE_DB.as_posix()}?mode=ro", uri=True) as con:
        return pd.read_sql_query(
            f"SELECT ticker, trading_date, open, high, low, close FROM ohlcv_daily "
            f"WHERE bar_status='COMPLETE' AND trading_date >= ? AND ticker IN ({marks}) ORDER BY ticker, trading_date",
            con, params=[since, *tickers])


def track(row, bars):
    side = 1 if row.side == "CALL" else -1
    out = {"ledger_id": row.ledger_id, "tracker_version": VERSION}
    b = bars[bars.trading_date >= row.decision_session].reset_index(drop=True)
    out["sessions_available"] = len(b)
    out["last_session"] = b.trading_date.iloc[-1] if len(b) else None
    if b.empty:
        out["status"] = "NO_DATA_YET"
        return out
    if str(row.readiness).startswith("READY"):
        ei, entry, path_from = 0, float(b.open.iloc[0]), 0
        out["entry_rule"] = "OPEN"
    else:
        hit = np.where((b.close - row.trigger) * side > 0)[0]
        if len(hit) == 0:
            out["status"] = "NOT_TRIGGERED"
            return out
        ei, entry, path_from = int(hit[0]), float(b.close.iloc[hit[0]]), int(hit[0]) + 1
        out["entry_rule"] = "CLOSE_BEYOND_TRIGGER"
    out["entry_session"], out["entry_price"] = b.trading_date.iloc[ei], round(entry, 4)
    window = int(row.q80_sessions) if pd.notna(row.q80_sessions) else 20
    p = b.iloc[path_from:path_from + window].reset_index(drop=True)
    fav = (p.high - entry) if side > 0 else (entry - p.low)
    adv = (entry - p.low) if side > 0 else (p.high - entry)
    for h in HORIZONS:
        if len(p) >= h:
            out[f"mfe_pct_{h}d"] = round(fav.iloc[:h].max() / entry * 100, 2)
            out[f"mae_pct_{h}d"] = round(adv.iloc[:h].max() / entry * 100, 2)
            out[f"mfe_atr_{h}d"] = round(fav.iloc[:h].max() / row.atr, 2)
            out[f"mae_atr_{h}d"] = round(adv.iloc[:h].max() / row.atr, 2)
            out[f"close_ret_pct_{h}d"] = round((p.close.iloc[h - 1] / entry - 1) * side * 100, 2)
    status, when = "OPEN", None
    for i in range(len(p)):
        hi, lo = p.high.iloc[i], p.low.iloc[i]
        t_hit = (hi >= row.level) if side > 0 else (lo <= row.level)
        s_hit = (lo <= row.practical_stop) if side > 0 else (hi >= row.practical_stop)
        inv_hit = (lo <= row.invalidation) if side > 0 else (hi >= row.invalidation)
        if s_hit or inv_hit:
            status = "STOP_SAME_BAR_AS_TARGET" if t_hit else ("INVALIDATED" if inv_hit else "STOP")
            when = i + 1
            break
        if t_hit:
            status, when = "TARGET", i + 1
            break
    status_b, when_b = "OPEN", None
    if "half_target" in row._fields and pd.notna(row.half_target):
        for i in range(len(p)):
            hi, lo = p.high.iloc[i], p.low.iloc[i]
            t_hit = (hi >= row.half_target) if side > 0 else (lo <= row.half_target)
            inv_hit = (lo <= row.invalidation) if side > 0 else (hi >= row.invalidation)
            if inv_hit:
                status_b, when_b = ("INVALIDATED_SAME_BAR_AS_HALF" if t_hit else "INVALIDATED"), i + 1
                break
            if t_hit:
                status_b, when_b = "HALF_TARGET", i + 1
                break
        if status_b == "OPEN" and len(p) >= window:
            status_b, when_b = "EXPIRED", window
    out["status_half_vs_invalidation"], out["sessions_to_half_outcome"] = status_b, when_b
    if status == "OPEN" and len(p) >= window:
        status, when = "EXPIRED", window
        out["expired_ret_pct"] = round((p.close.iloc[window - 1] / entry - 1) * side * 100, 2)
    out["status"], out["sessions_to_outcome"] = status, when
    return out


def main():
    ledger_path = Path(sys.argv[1])
    led = pd.read_csv(ledger_path)
    if not PRICE_DB.exists():
        raise SystemExit("run from the AVSHUNTER-Intelligence folder (price store not found)")
    since = led.decision_session.min()
    prices = load_prices(sorted(led.ticker.unique()), since)
    groups = {t: g for t, g in prices.groupby("ticker")}
    rows = [track(r, groups.get(r.ticker, prices.iloc[0:0])) for r in led.itertuples()]
    keep = [c for c in ["ledger_id", "ticker", "side", "state", "coherence", "money", "realisation", "focus", "focus_v3", "size_note", "decision", "contract_note"] if c in led.columns]
    out = led[keep].merge(
        pd.DataFrame(rows), on="ledger_id", how="left")
    out.to_csv(ledger_path.with_name(ledger_path.stem + "_outcomes.csv"), index=False)
    done = out[out.status.isin(["TARGET", "STOP", "INVALIDATED", "STOP_SAME_BAR_AS_TARGET", "EXPIRED"])]
    summary = []
    for key in [k for k in ["state", "coherence", "money", "realisation", "side", "focus", "focus_v3", "decision"] if k in out.columns]:
        for val, g in out.groupby(key, dropna=False):
            d = g[g.ledger_id.isin(done.ledger_id)]
            summary.append({"group": key, "value": val, "rows": len(g),
                            "triggered_or_entered": int(g.entry_price.notna().sum()),
                            "resolved": len(d), "target": int((d.status == "TARGET").sum()),
                            "stop_or_invalidated": int(d.status.isin(["STOP", "INVALIDATED", "STOP_SAME_BAR_AS_TARGET"]).sum()),
                            "expired": int((d.status == "EXPIRED").sum()),
                            "half_target_first": int((g.get("status_half_vs_invalidation") == "HALF_TARGET").sum()),
                            "invalidated_first": int(g.get("status_half_vs_invalidation", pd.Series(dtype=str)).astype(str).str.startswith("INVALIDATED").sum()),
                            "target_rate_of_resolved": round((d.status == "TARGET").mean(), 3) if len(d) else None,
                            "median_mfe_atr_2d": g.get("mfe_atr_2d", pd.Series(dtype=float)).median(),
                            "median_mae_atr_2d": g.get("mae_atr_2d", pd.Series(dtype=float)).median()})
    pd.DataFrame(summary).to_csv(ledger_path.with_name(ledger_path.stem + "_summary.csv"), index=False)
    print(out.status.value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
