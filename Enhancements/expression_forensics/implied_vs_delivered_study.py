"""Implied vs delivered volatility (read-only): is option premium priced above the movement that follows?

For every ticker and every session with option IV in options_greeks_history (local COMPUTED_BS and
any provider rows recorded there), take the at-the-money IV (median IV of contracts with |delta| in
[0.40, 0.60]) for two tenors (7–19 and 20–45 DTE). Compare with:
  - delivered volatility over the next 10 / 20 sessions (zero-mean RMS of daily log returns, price store),
  - the EWMA (0.94) realised forecast available at the same session (point-in-time).
Annualisation: delivered and EWMA per-session volatility x sqrt(252); IV as solved on a 365-day basis.
Jump windows: a daily move > 4x the EWMA daily forecast inside the delivered window (event proxy; no
historical earnings calendar exists).

  venv\\Scripts\\python.exe Enhancements\\expression_forensics\\implied_vs_delivered_study.py
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
PRICES = MAIN / "data" / "canonical" / "historical_prices.sqlite"
CHAINS = MAIN / "data" / "phantom" / "phantom_history.db"
OUT = Path(__file__).resolve().parent / "implied_vs_delivered_study.json"
SESSIONS_PER_YEAR = 252
TENORS = {"short_7_19": (7, 19), "month_20_45": (20, 45)}
HORIZONS = (10, 20)
JUMP_MULTIPLE = 4.0


def price_table(con, ticker):
    frame = pd.read_sql_query("SELECT trading_date, close FROM ohlcv_daily WHERE ticker = ? AND bar_status = 'COMPLETE' "
                              "ORDER BY trading_date", con, params=(ticker,), index_col="trading_date")
    frame = frame[frame["close"] > 0]
    if len(frame) < 80:
        return None
    r = np.log(frame["close"] / frame["close"].shift(1))
    out = pd.DataFrame(index=frame.index)
    out["ewma"] = np.sqrt((r ** 2).ewm(alpha=1 - 0.94, adjust=False).mean())
    for h in HORIZONS:
        out[f"delivered_{h}"] = np.sqrt((r ** 2).shift(-1).rolling(h).mean().shift(-(h - 1)))
        out[f"maxabs_{h}"] = r.abs().shift(-1).rolling(h).max().shift(-(h - 1))
    return out


def main():
    pc = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    cc = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in pc.execute("SELECT DISTINCT ticker FROM ohlcv_daily")]
    records = []
    for i, ticker in enumerate(tickers):
        iv_rows = cc.execute(
            "SELECT snapshot_date, dte, iv FROM options_greeks_history WHERE ticker = ? AND quality_status LIKE 'OK%' "
            "AND iv > 0 AND ABS(delta) BETWEEN 0.40 AND 0.60 AND dte BETWEEN 7 AND 45", (ticker,)).fetchall()
        if not iv_rows:
            continue
        prices = price_table(pc, ticker)
        if prices is None:
            continue
        cells = defaultdict(list)
        for day, dte, iv in iv_rows:
            for tenor, (lo, hi) in TENORS.items():
                if lo <= dte <= hi:
                    cells[(day, tenor)].append(iv)
        for (day, tenor), ivs in cells.items():
            if day not in prices.index:
                continue
            row = prices.loc[day]
            atm_iv = float(np.median(ivs))
            ewma_annual = float(row["ewma"]) * math.sqrt(SESSIONS_PER_YEAR)
            rec = {"ticker": ticker, "session": day, "tenor": tenor, "atm_iv": atm_iv, "ewma_annual": ewma_annual}
            for h in HORIZONS:
                d = row[f"delivered_{h}"]
                if pd.notna(d) and d > 0:
                    rec[f"delivered_{h}_annual"] = float(d) * math.sqrt(SESSIONS_PER_YEAR)
                    rec[f"jump_{h}"] = bool(row[f"maxabs_{h}"] > JUMP_MULTIPLE * row["ewma"])
            records.append(rec)
        if i % 500 == 0:
            print(f"{i}/{len(tickers)} records={len(records)}", flush=True)
    frame = pd.DataFrame(records)
    summary = {"records": len(frame), "tickers": int(frame["ticker"].nunique()), "sessions": sorted(frame["session"].unique().tolist())}
    results = []
    for tenor in TENORS:
        for h in HORIZONS:
            col = f"delivered_{h}_annual"
            sub = frame[(frame["tenor"] == tenor) & frame[col].notna() & (frame["ewma_annual"] > 0)]
            for label, part in (("ALL", sub), ("NO_JUMP", sub[~sub[f"jump_{h}"].astype(bool)]), ("JUMP", sub[sub[f"jump_{h}"].astype(bool)])):
                if part.empty:
                    continue
                log_iv_premium = np.log(part["atm_iv"] / part[col])
                x_iv = (part[col] ** 2) / (part["atm_iv"] ** 2)
                x_ew = (part[col] ** 2) / (part["ewma_annual"] ** 2)
                results.append({
                    "tenor": tenor, "horizon": h, "subset": label, "n": int(len(part)),
                    "sessions": int(part["session"].nunique()),
                    "median_iv_over_delivered": float(np.exp(np.median(log_iv_premium))),
                    "share_iv_above_delivered": float(np.mean(log_iv_premium > 0)),
                    "median_ewma_over_delivered": float(np.exp(np.median(np.log(part["ewma_annual"] / part[col])))),
                    "qlike_iv": float(np.mean(x_iv - np.log(x_iv) - 1)),
                    "qlike_ewma": float(np.mean(x_ew - np.log(x_ew) - 1)),
                    "mean_abs_log_iv": float(np.mean(np.abs(log_iv_premium))),
                    "mean_abs_log_ewma": float(np.mean(np.abs(np.log(part["ewma_annual"] / part[col])))),
                    "median_iv_over_ewma": float(np.exp(np.median(np.log(part["atm_iv"] / part["ewma_annual"])))),
                })
    # IV premium by IV-vs-EWMA band: does "IV cheap vs our forecast" predict IV below delivered?
    bands = []
    sub = frame[(frame["tenor"] == "month_20_45") & frame["delivered_20_annual"].notna() & (frame["ewma_annual"] > 0)].copy()
    sub["iv_over_ewma"] = sub["atm_iv"] / sub["ewma_annual"]
    sub["band"] = pd.cut(sub["iv_over_ewma"], [0, 0.8, 1.0, 1.2, 1.5, 2.0, np.inf])
    for band, part in sub.groupby("band", observed=True):
        bands.append({"iv_over_ewma": str(band), "n": int(len(part)),
                      "median_iv_over_delivered": float(np.exp(np.median(np.log(part["atm_iv"] / part["delivered_20_annual"])))),
                      "share_delivered_above_iv": float(np.mean(part["delivered_20_annual"] > part["atm_iv"]))})
    payload = {"summary": {k: v for k, v in summary.items() if k != "sessions"}, "session_count": len(summary["sessions"]),
               "first_session": summary["sessions"][0], "last_session": summary["sessions"][-1],
               "results": results, "iv_cheapness_bands_20_45dte_h20": bands}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"]), payload["session_count"], payload["first_session"], payload["last_session"])
    for r in results:
        print(f"{r['tenor']:>12} h{r['horizon']} {r['subset']:>7} n={r['n']:>7} sess={r['sessions']:>3} IV/deliv={r['median_iv_over_delivered']:.2f} "
              f"IV>deliv={r['share_iv_above_delivered']:.2f} EWMA/deliv={r['median_ewma_over_delivered']:.2f} "
              f"QLIKE iv={r['qlike_iv']:.3f} ewma={r['qlike_ewma']:.3f} |log| iv={r['mean_abs_log_iv']:.3f} ewma={r['mean_abs_log_ewma']:.3f} IV/EWMA={r['median_iv_over_ewma']:.2f}")
    for b in bands:
        print(b)


if __name__ == "__main__":
    main()
