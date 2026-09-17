"""Signal research plan A — price-based hypotheses H1-H12 (read-only; pre-registered in SIGNAL_RESEARCH_PLAN_A.md).

Full universe (tickers with >= 320 complete bars), vectorised panel, evaluation every 5th session, train 2022-09..2024-12,
test 2025-01..2026-08, horizons 5/10/20 sessions, liquidity universe median 20-session dollar volume >= $5M.
Outputs: signal_research_a_price_summary.csv / .json and a per-date IC table.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent
HORIZONS = (5, 10, 20)
STEP = 5
TRAIN_END, TEST_START = "2024-12-31", "2025-01-01"
EVAL_START = "2022-09-01"
MIN_CROSS_SECTION = 100
LIQUIDITY_USD = 5_000_000
EXPECTED_SIGN = {"H1": 1, "H2": 1, "H3": 1, "H4": 1, "H5": 1, "H6": -1, "H7": -1, "H8": 1, "H9": 1, "H10": 1, "H11": 1, "H12": 1}


def load_panel():
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    keep = [r[0] for r in con.execute("SELECT ticker FROM ohlcv_daily WHERE bar_status='COMPLETE' GROUP BY ticker HAVING COUNT(*) >= 320")]
    con.execute("CREATE TEMP TABLE k(t TEXT PRIMARY KEY)")
    con.executemany("INSERT INTO k VALUES (?)", [(t,) for t in keep])
    df = pd.read_sql_query("SELECT o.ticker, o.trading_date, o.open, o.high, o.low, o.close, o.volume FROM ohlcv_daily o "
                           "JOIN k ON k.t = o.ticker WHERE o.bar_status='COMPLETE'", con)
    con.close()
    panel = {f: df.pivot(index="trading_date", columns="ticker", values=f).sort_index() for f in ("open", "high", "low", "close", "volume")}
    return panel


def newey_west_t(x: np.ndarray, lag: int) -> float:
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 10:
        return float("nan")
    d = x - x.mean()
    gamma0 = (d @ d) / n
    var = gamma0
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        var += 2 * w * (d[k:] @ d[:-k]) / n
    return float(x.mean() / math.sqrt(var / n)) if var > 0 else float("nan")


def rank_residual(y: pd.Series, control: pd.Series) -> pd.Series:
    ry, rc = y.rank(), control.rank()
    ok = ry.notna() & rc.notna()
    if ok.sum() < 10:
        return pd.Series(np.nan, index=y.index)
    beta = np.polyfit(rc[ok], ry[ok], 1)
    out = pd.Series(np.nan, index=y.index)
    out[ok] = ry[ok] - (beta[0] * rc[ok] + beta[1])
    return out


def main():
    p = load_panel()
    close, high, low, open_, vol = p["close"], p["high"], p["low"], p["open"], p["volume"]
    logc = np.log(close.where(close > 0))
    ret1 = logc.diff()
    # DQ-12: exclude ticker-dates whose [t-260, t+20] window contains a 10x one-bar move or a sub-cent close
    bad = ((ret1.abs() >= math.log(10)) | (close < 0.01)).astype(float)
    bad_past = bad.rolling(261, min_periods=1).max()
    bad_future = bad[::-1].rolling(21, min_periods=1).max()[::-1]
    clean = (bad_past < 1) & (bad_future < 1)

    dollar = (close * vol).rolling(20, min_periods=15).median()
    liquid = dollar >= LIQUIDITY_USD
    net_day = ret1.sub(ret1.median(axis=1), axis=0)
    tp = (high + low + close) / 3
    atr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()]).groupby(level=0).max().rolling(14).mean()
    atr = atr.reindex(close.index)[close.columns]

    signals = {}
    signals["H1"] = -(logc - logc.shift(5))
    signals["H2"] = -((logc - logc.shift(5)).sub((logc - logc.shift(5)).median(axis=1), axis=0))
    signals["H3"] = (logc.shift(21) - logc.shift(252))
    signals["H4"] = close / close.rolling(252, min_periods=200).max()
    signals["H5"] = close / close.rolling(252, min_periods=200).min() - 1
    # H6 move age: sessions since the close last set a 20-session high or low
    extreme = (close >= close.rolling(20, min_periods=20).max()) | (close <= close.rolling(20, min_periods=20).min())
    age = np.zeros(close.shape)
    ext = extreme.to_numpy()
    counter = np.full(close.shape[1], np.nan)
    for i in range(close.shape[0]):
        counter = np.where(ext[i], 0.0, counter + 1)
        age[i] = counter
    signals["H6"] = pd.DataFrame(age, index=close.index, columns=close.columns)
    vwap20 = (tp * vol).rolling(20, min_periods=15).sum() / vol.rolling(20, min_periods=15).sum()
    signals["H7"] = close / vwap20 - 1
    signals["H8"] = np.sign(ret1) * np.log(vol / vol.rolling(20, min_periods=15).median())
    gap = open_ - close.shift()
    event = (gap.abs() >= 2 * atr.shift()) & (vol >= 2 * vol.rolling(20, min_periods=15).median().shift())
    gap_sign = np.sign(gap).where(event)
    signals["H9"] = gap_sign.ffill(limit=4)
    signals["H10"] = -ret1.rolling(60, min_periods=50).std()
    signals["H11"] = -net_day.rolling(60, min_periods=50).std()
    signals["H12"] = (logc - logc.shift(60)) / (ret1.rolling(60, min_periods=50).std() * math.sqrt(60))
    # share spread (Abdi-Ranaldo) for the economic-size test
    eta = (np.log(high) + np.log(low)) / 2
    prod = (logc - eta) * (logc - eta.shift(-1))
    ar_spread = np.sqrt((4 * prod.shift(1).rolling(60, min_periods=20).mean()).clip(lower=0))

    fwd = {h: (logc.shift(-h) - logc) for h in HORIZONS}
    dates = [d for d in close.index[260::STEP] if d >= EVAL_START and close.index.get_loc(d) + max(HORIZONS) < len(close.index)]
    records = []
    for d in dates:
        universe = clean.loc[d] & liquid.loc[d].fillna(False)
        reversal = signals["H1"].loc[d]
        for h in HORIZONS:
            y = fwd[h].loc[d]
            ok_y = universe & y.notna()
            if ok_y.sum() < MIN_CROSS_SECTION:
                continue
            ynet = y[ok_y] - y[ok_y].median()
            for name, sig in signals.items():
                x = sig.loc[d][ok_y]
                ok = x.notna() & np.isfinite(x)
                if ok.sum() < MIN_CROSS_SECTION or x[ok].nunique() < 3:
                    continue
                ic = stats.spearmanr(x[ok], ynet[ok]).statistic
                q = pd.qcut(x[ok].rank(method="first"), 5, labels=False)
                top_bottom = float(ynet[ok][q == 4].mean() - ynet[ok][q == 0].mean())
                partial = np.nan
                if name != "H1":
                    rx = rank_residual(x[ok], reversal[ok_y][ok])
                    ry = rank_residual(ynet[ok], reversal[ok_y][ok])
                    okp = rx.notna() & ry.notna()
                    if okp.sum() >= MIN_CROSS_SECTION:
                        partial = stats.spearmanr(rx[okp], ry[okp]).statistic
                spread = float(ar_spread.loc[d][ok_y][ok][(q == 4) | (q == 0)].median())
                records.append({"date": d, "year": d[:4], "period": "TRAIN" if d <= TRAIN_END else "TEST", "signal": name,
                                "horizon": h, "ic": ic, "partial_ic_vs_reversal": partial, "top_bottom_net": top_bottom,
                                "median_share_spread": spread, "n": int(ok.sum())})
    ic = pd.DataFrame(records)
    ic.to_csv(OUT / "signal_research_a_price_per_date.csv", index=False)

    rows = []
    for (name, h), g in ic.groupby(["signal", "horizon"]):
        lag = max(0, math.ceil(h / STEP) - 1)
        row = {"signal": name, "horizon": h, "expected_sign": EXPECTED_SIGN[name]}
        for period in ("TRAIN", "TEST"):
            s = g[g["period"] == period]
            row[f"{period.lower()}_dates"] = len(s)
            row[f"{period.lower()}_ic"] = float(s["ic"].mean()) if len(s) else np.nan
            row[f"{period.lower()}_t"] = newey_west_t(s["ic"].to_numpy(), lag) if len(s) else np.nan
            row[f"{period.lower()}_positive_share"] = float((np.sign(s["ic"]) == EXPECTED_SIGN[name]).mean()) if len(s) else np.nan
            row[f"{period.lower()}_partial_ic"] = float(s["partial_ic_vs_reversal"].mean()) if len(s) else np.nan
            row[f"{period.lower()}_partial_t"] = newey_west_t(s["partial_ic_vs_reversal"].to_numpy(), lag) if len(s) else np.nan
            row[f"{period.lower()}_top_bottom_net"] = float(s["top_bottom_net"].mean()) if len(s) else np.nan
            row[f"{period.lower()}_median_share_spread"] = float(s["median_share_spread"].median()) if len(s) else np.nan
        yearly = g.groupby("year")["ic"].mean()
        row["yearly_ic"] = {k: round(float(v), 4) for k, v in yearly.items()}
        row["same_sign_years"] = int((np.sign(yearly) == EXPECTED_SIGN[name]).sum())
        row["years"] = len(yearly)
        rows.append(row)
    sm = pd.DataFrame(rows)
    sm["test_p"] = [2 * stats.norm.sf(abs(t)) if np.isfinite(t) else 1.0 for t in sm["test_t"]]
    order = sm["test_p"].sort_values().index
    m = len(sm)
    thresholds = pd.Series(0.10 * np.arange(1, m + 1) / m, index=order)
    passed = sm.loc[order, "test_p"] <= thresholds
    cutoff = passed[passed].index[-1] if passed.any() else None
    sm["test_fdr"] = False
    if cutoff is not None:
        sm.loc[order[: list(order).index(cutoff) + 1], "test_fdr"] = True
    es = sm["expected_sign"]
    sm["c1_train"] = (np.sign(sm["train_ic"]) == es) & (sm["train_t"].abs() >= 2.5) & (sm["train_positive_share"] >= 0.55)
    sm["c2_test"] = (np.sign(sm["test_ic"]) == es) & (sm["test_t"].abs() >= 2.0) & sm["test_fdr"]
    sm["c3_years"] = sm["same_sign_years"] >= 4
    sm["c4_economic"] = (sm["horizon"] == 10) & ((sm["test_top_bottom_net"] * es) > sm["test_median_share_spread"])
    sm["c5_not_reversal"] = (sm["signal"] == "H1") | ((np.sign(sm["test_partial_ic"]) == es) & (sm["test_partial_t"].abs() >= 2.0))
    sm["passes_1_to_3_and_5"] = sm["c1_train"] & sm["c2_test"] & sm["c3_years"] & sm["c5_not_reversal"]
    sm.to_csv(OUT / "signal_research_a_price_summary.csv", index=False)
    (OUT / "signal_research_a_price_summary.json").write_text(sm.to_json(orient="records", indent=2), encoding="utf-8")
    cols = ["signal", "horizon", "train_ic", "train_t", "test_ic", "test_t", "same_sign_years", "test_partial_t",
            "test_top_bottom_net", "test_median_share_spread", "c1_train", "c2_test", "c3_years", "c4_economic", "c5_not_reversal"]
    print(f"dates {ic['date'].nunique()}, median cross-section {int(ic['n'].median())}")
    print(sm[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
