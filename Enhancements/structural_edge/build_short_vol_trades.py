"""Structural edge study, stage 1 (read-only): build short-volatility trades from stored chains.

For every ticker and every weekly entry session (latest stored session of each ISO week), and for two
tenors (20-45 DTE, target 30; 7-20 DTE, target 14), pick ONE expiry (closest to target) and build:
  - short ATM straddle            (strike nearest the underlying, both legs two-sided)
  - short 25-delta strangle       (OTM put / call with local delta closest to 0.25)
  - iron condor                   (short 25d legs, long wings ~10 delta further OTM: closest to 15d)
  - put credit spread             (short 25d put, long ~15d put)
Wings must be >= 5 delta further OTM than the short leg (else no trade, recorded).
Fills: sold legs at the BID, bought legs at the ASK (no mid fills). Exits:
  - hold:  settle at intrinsic from the underlying close on / just before expiration (price store,
           split-adjusted; converted to chain units by the entry-session chain/close factor)
  - mid:   close at the later stored session nearest half-life (within +-7 calendar days) where ALL legs
           have a two-sided quote: buy shorts at the ASK, sell longs at the BID; else recorded missing
  - tp50:  first later stored session where the cost to close (ask for shorts, bid for longs) <= 50% of
           the entry credit; otherwise hold to expiry (sessions where a leg is unquoted are skipped)
Deltas / IVs: computed locally (Black-Scholes, r = 4.5% as stored in options_greeks_history, q = 0,
calendar DTE / 365) from the stored mid of OTM contracts for EVERY session, so one method is used
throughout (provider greeks exist only on a few sessions).
Integrity: price bars with a one-bar move >= 10x or sub-cent closes inside [entry - 60 bars, expiry]
exclude the trade; a chain-underlying / close factor that moves > 3% between entry and any stored
session up to expiry + 14 days (split in the window) excludes the trade; entry factor must be known.
Point-in-time: EWMA(0.94) forecast uses closes up to and including the entry session.

  venv\\Scripts\\python.exe Enhancements\\structural_edge\\build_short_vol_trades.py [--workers 7] [--limit N]
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import sqlite3
import time

import numpy as np
import pandas as pd
from scipy.special import ndtr

MAIN = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
PRICES = MAIN / "data" / "canonical" / "historical_prices.sqlite"
CHAINS = MAIN / "data" / "phantom" / "phantom_history.db"
HERE = Path(__file__).resolve().parent
OUT_TRADES = HERE / "short_vol_trades.parquet"
OUT_META = HERE / "short_vol_trades_build_meta.json"

RISK_FREE = 0.045
TENORS = {"t20_45": (20, 45, 30), "t07_20": (7, 20, 14)}
SHORT_DELTA = 0.25
WING_DELTA = 0.15
MIN_WING_DELTA_GAP = 0.05  # wing must be at least 5 delta further OTM than the short leg (40-strike window)
SHORT_DELTA_TOLERANCE = (0.15, 0.35)
PRICE_BREAK_RATIO = 10.0
SUB_CENT = 0.01
FACTOR_TOLERANCE = 0.03
EWMA_LAMBDA = 0.94
MIN_BARS = 80
MID_WINDOW_DAYS = 7
TP_FRACTION = 0.5
FIRST_DATE, LAST_DATE = "2000-01-01", "2100-01-01"


def bs_price(is_call, S, K, T, sigma):
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (RISK_FREE + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    disc = np.exp(-RISK_FREE * T)
    call = S * ndtr(d1) - K * disc * ndtr(d2)
    put = K * disc * ndtr(-d2) - S * ndtr(-d1)
    return np.where(is_call, call, put), d1


def implied_vol_and_delta(is_call, S, K, T, price):
    lo = np.full(price.shape, 1e-4)
    hi = np.full(price.shape, 5.0)
    p_lo, _ = bs_price(is_call, S, K, T, lo)
    p_hi, _ = bs_price(is_call, S, K, T, hi)
    valid = (price > p_lo) & (price < p_hi)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        p, _ = bs_price(is_call, S, K, T, mid)
        above = p > price
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    iv = 0.5 * (lo + hi)
    _, d1 = bs_price(is_call, S, K, T, iv)
    delta = np.where(is_call, ndtr(d1), ndtr(d1) - 1.0)
    iv = np.where(valid, iv, np.nan)
    delta = np.where(valid, delta, np.nan)
    return iv, delta


def load_prices(pc, ticker):
    frame = pd.read_sql_query(
        "SELECT trading_date, close FROM ohlcv_daily WHERE ticker = ? AND adjustment_convention = 'POLYGON_SPLIT_ADJUSTED' "
        "AND bar_status = 'COMPLETE' AND trading_date BETWEEN ? AND ? ORDER BY trading_date",
        pc, params=(ticker, FIRST_DATE, LAST_DATE))
    if len(frame) < MIN_BARS:
        return None
    frame["trading_date"] = pd.to_datetime(frame["trading_date"])
    frame = frame.set_index("trading_date")
    close = frame["close"].astype(float)
    ratio = close / close.shift(1)
    bad = (close < SUB_CENT) | (ratio >= PRICE_BREAK_RATIO) | (ratio <= 1.0 / PRICE_BREAK_RATIO)
    r = np.log(close / close.shift(1))
    r = r.where(~bad)
    ewma = np.sqrt((r.fillna(0.0) ** 2).ewm(alpha=1 - EWMA_LAMBDA, adjust=False).mean())
    return pd.DataFrame({"close": close, "bad": bad.astype(int), "r": r, "ewma_daily": ewma})


def price_on_or_before(prices, day):
    idx = prices.index.searchsorted(day, side="right") - 1
    return idx if idx >= 0 else None


def build_ticker(ticker):
    reasons = Counter()
    trades = []
    cc = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    pc = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    try:
        prices = load_prices(pc, ticker)
        if prices is None:
            reasons["no_price_history"] += 1
            return ticker, trades, reasons
        chain = pd.read_sql_query(
            "SELECT quote_date, option_symbol, expiration_ts, side, strike, dte, bid, ask, underlying_price "
            "FROM chain_snapshots WHERE ticker = ? AND quote_date BETWEEN ? AND ?",
            cc, params=(ticker, FIRST_DATE, LAST_DATE))
    finally:
        cc.close()
        pc.close()
    if chain.empty:
        reasons["no_chain"] += 1
        return ticker, trades, reasons
    chain["qd"] = pd.to_datetime(chain["quote_date"])
    chain["exp"] = pd.to_datetime(chain["expiration_ts"], unit="s").dt.normalize()
    chain["two_sided"] = (chain["bid"] > 0) & (chain["ask"] > chain["bid"])
    chain["mid_q"] = (chain["bid"] + chain["ask"]) / 2.0
    last_price_day = prices.index[-1]

    # chain-units / price-store factor per stored session (split detection)
    und = chain.groupby("qd")["underlying_price"].median()
    factor = {}
    for day, u in und.items():
        i = price_on_or_before(prices, day)
        if i is not None and prices.index[i] == day and u and u > 0:
            factor[day] = float(u) / float(prices["close"].iloc[i])
    sessions = sorted(chain["qd"].unique())
    # quotes by session for exits: {session: {symbol: (bid, ask)}}
    q2 = chain[chain["two_sided"]]
    quotes = {d: dict(zip(g["option_symbol"], zip(g["bid"], g["ask"]))) for d, g in q2.groupby("qd")}

    iso = pd.Series(sessions).dt.isocalendar()
    weekly = pd.DataFrame({"d": sessions, "y": iso["year"].values, "w": iso["week"].values}).groupby(["y", "w"])["d"].max()

    for entry in weekly.values:
        entry = pd.Timestamp(entry)
        day_rows = chain[(chain["qd"] == entry)]
        pi = price_on_or_before(prices, entry)
        if pi is None or prices.index[pi] != entry or pi < 60:
            reasons["entry_no_price_bar"] += 1
            continue
        f_entry = factor.get(entry)
        if f_entry is None:
            reasons["entry_no_factor"] += 1
            continue
        S = float(day_rows["underlying_price"].median())
        ewma_daily = float(prices["ewma_daily"].iloc[pi])
        if not (ewma_daily > 0) or prices["bad"].iloc[pi - 60:pi + 1].any():
            reasons["entry_price_integrity"] += 1
            continue
        for tenor, (lo, hi, target) in TENORS.items():
            exp_dte = day_rows.groupby("exp")["dte"].median()
            cand = exp_dte[(exp_dte >= lo) & (exp_dte <= hi)]
            if cand.empty:
                reasons[f"{tenor}:no_expiry"] += 1
                continue
            expiry = (cand - target).abs().sort_values(kind="stable").index[0]
            if expiry > last_price_day:
                reasons[f"{tenor}:not_yet_expired"] += 1
                continue
            ei = price_on_or_before(prices, expiry)
            window = prices.iloc[pi:ei + 1]
            if window["bad"].any():
                reasons[f"{tenor}:window_price_integrity"] += 1
                continue
            later_factors = [v for d, v in factor.items() if entry < d <= expiry + pd.Timedelta(days=14)]
            if any(abs(v / f_entry - 1.0) > FACTOR_TOLERANCE for v in later_factors):
                reasons[f"{tenor}:split_in_window"] += 1
                continue
            S_T = float(prices["close"].iloc[ei]) * f_entry
            rets = window["r"].iloc[1:]
            max_abs_ret = float(rets.abs().max()) if len(rets) else 0.0
            delivered = float(np.sqrt((rets ** 2).mean()) * math.sqrt(252)) if len(rets) else float("nan")

            ex = day_rows[(day_rows["exp"] == expiry) & day_rows["two_sided"]].copy()
            if ex.empty:
                reasons[f"{tenor}:no_two_sided"] += 1
                continue
            T = max(float(ex["dte"].median()), 0.5) / 365.0
            is_call = (ex["side"] == "call").to_numpy()
            iv, delta = implied_vol_and_delta(is_call, S, ex["strike"].to_numpy(float), T, ex["mid_q"].to_numpy(float))
            ex["iv"], ex["delta"] = iv, delta
            calls = ex[ex["side"] == "call"].sort_values("strike")
            puts = ex[ex["side"] == "put"].sort_values("strike")
            otm_c = calls[(calls["strike"] >= S) & calls["delta"].notna()]
            otm_p = puts[(puts["strike"] <= S) & puts["delta"].notna()]
            atm_iv = np.nanmean([otm_c["iv"].iloc[0] if len(otm_c) else np.nan,
                                 otm_p["iv"].iloc[-1] if len(otm_p) else np.nan]) if (len(otm_c) or len(otm_p)) else np.nan
            base = {"ticker": ticker, "entry": entry.date().isoformat(), "expiry": expiry.date().isoformat(),
                    "tenor": tenor, "dte": float(ex["dte"].median()), "S": S, "S_T": S_T,
                    "atm_iv": float(atm_iv) if atm_iv == atm_iv else np.nan,
                    "ewma_annual": ewma_daily * math.sqrt(252), "delivered_annual": delivered,
                    "max_abs_ret_over_sigma": max_abs_ret / ewma_daily,
                    "underlying_ret": S_T / S - 1.0}

            structures = {}
            common = sorted(set(calls["strike"]) & set(puts["strike"]))
            if common:
                K = min(common, key=lambda k: (abs(k - S), k))
                c = calls[calls["strike"] == K].iloc[0]
                p = puts[puts["strike"] == K].iloc[0]
                structures["short_straddle"] = ([("short", c), ("short", p)], "naked")
            else:
                reasons[f"{tenor}:straddle_no_common_strike"] += 1

            sp = sc = None
            if len(otm_p):
                j = (otm_p["delta"].abs() - SHORT_DELTA).abs().idxmin()
                if SHORT_DELTA_TOLERANCE[0] <= abs(otm_p.loc[j, "delta"]) <= SHORT_DELTA_TOLERANCE[1]:
                    sp = otm_p.loc[j]
            if len(otm_c):
                j = (otm_c["delta"].abs() - SHORT_DELTA).abs().idxmin()
                if SHORT_DELTA_TOLERANCE[0] <= abs(otm_c.loc[j, "delta"]) <= SHORT_DELTA_TOLERANCE[1]:
                    sc = otm_c.loc[j]
            lp = lc = None
            if sp is not None:
                w = otm_p[otm_p["strike"] < sp["strike"]]
                if len(w):
                    cand_lp = w.loc[(w["delta"].abs() - WING_DELTA).abs().idxmin()]
                    if abs(cand_lp["delta"]) <= abs(sp["delta"]) - MIN_WING_DELTA_GAP:
                        lp = cand_lp
            if sc is not None:
                w = otm_c[otm_c["strike"] > sc["strike"]]
                if len(w):
                    cand_lc = w.loc[(w["delta"].abs() - WING_DELTA).abs().idxmin()]
                    if abs(cand_lc["delta"]) <= abs(sc["delta"]) - MIN_WING_DELTA_GAP:
                        lc = cand_lc
            if sp is not None and sc is not None:
                structures["short_strangle_25d"] = ([("short", sp), ("short", sc)], "naked")
                if lp is not None and lc is not None:
                    structures["iron_condor_25_15"] = ([("short", sp), ("short", sc), ("long", lp), ("long", lc)], "defined")
                else:
                    reasons[f"{tenor}:condor_no_wing"] += 1
            else:
                reasons[f"{tenor}:no_25d_legs"] += 1
            if sp is not None and lp is None:
                reasons[f"{tenor}:put_wing_outside_stored_strikes"] += 1
            if sp is not None and lp is not None:
                structures["put_credit_spread_25_15"] = ([("short", sp), ("long", lp)], "defined")

            for name, (legs, risk_kind) in structures.items():
                credit = sum(l["bid"] if pos == "short" else -l["ask"] for pos, l in legs)
                mid_credit = sum(l["mid_q"] if pos == "short" else -l["mid_q"] for pos, l in legs)
                if credit <= 0:
                    reasons[f"{tenor}:{name}:non_positive_credit"] += 1
                    continue

                def intrinsic(l):
                    return max(S_T - l["strike"], 0.0) if l["side"] == "call" else max(l["strike"] - S_T, 0.0)

                settle = sum(intrinsic(l) if pos == "short" else -intrinsic(l) for pos, l in legs)
                pnl_hold = credit - settle
                if risk_kind == "naked":
                    risk = 0.20 * S
                else:
                    shorts = {l["side"]: l["strike"] for pos, l in legs if pos == "short"}
                    longs = {l["side"]: l["strike"] for pos, l in legs if pos == "long"}
                    widths = [abs(shorts[s] - longs[s]) for s in longs]
                    risk = max(widths) - credit
                    if risk <= 0:
                        reasons[f"{tenor}:{name}:non_positive_risk"] += 1
                        continue
                syms = [(pos, l["option_symbol"]) for pos, l in legs]
                later = [d for d in sessions if entry < d < expiry]
                closes = []
                for d in later:
                    qd = quotes.get(d, {})
                    if all(s in qd for _, s in syms):
                        cost = sum(qd[s][1] if pos == "short" else -qd[s][0] for pos, s in syms)
                        closes.append((d, cost))
                half = entry + (expiry - entry) / 2
                pnl_mid, mid_day = np.nan, None
                near = [(abs((d - half).days), d, cst) for d, cst in closes if abs((d - half).days) <= MID_WINDOW_DAYS]
                if near:
                    _, mid_day, cst = min(near, key=lambda x: (x[0], x[1]))
                    pnl_mid = credit - cst
                pnl_tp, tp_day = pnl_hold, None
                for d, cst in closes:
                    if cst <= TP_FRACTION * credit:
                        pnl_tp, tp_day = credit - cst, d
                        break
                legs_spread = [(l["ask"] - l["bid"]) / l["mid_q"] for _, l in legs]
                rec = dict(base)
                rec.update({
                    "strategy": name, "risk_kind": risk_kind, "credit": credit, "mid_credit": mid_credit,
                    "risk": risk, "max_leg_spread": float(max(legs_spread)),
                    "short_strikes": ",".join(f"{l['side'][0]}{l['strike']:g}" for pos, l in legs if pos == "short"),
                    "long_strikes": ",".join(f"{l['side'][0]}{l['strike']:g}" for pos, l in legs if pos == "long"),
                    "short_put_delta": float(sp["delta"]) if sp is not None and name != "short_straddle" else np.nan,
                    "short_call_delta": float(sc["delta"]) if sc is not None and name in ("short_strangle_25d", "iron_condor_25_15") else np.nan,
                    "long_put_delta": float(lp["delta"]) if lp is not None and name in ("iron_condor_25_15", "put_credit_spread_25_15") else np.nan,
                    "long_call_delta": float(lc["delta"]) if lc is not None and name == "iron_condor_25_15" else np.nan,
                    "pnl_hold": pnl_hold, "ret_hold": pnl_hold / risk,
                    "pnl_mid": pnl_mid, "ret_mid": pnl_mid / risk if pnl_mid == pnl_mid else np.nan,
                    "mid_exit_day": mid_day.date().isoformat() if mid_day is not None else None,
                    "pnl_tp50": pnl_tp, "ret_tp50": pnl_tp / risk,
                    "tp50_exit_day": tp_day.date().isoformat() if tp_day is not None else None,
                    "n_later_quoted_sessions": len(closes), "n_later_sessions": len(later),
                })
                trades.append(rec)
    return ticker, trades, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()
    cc = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    tickers = [r[0] for r in cc.execute(
        "WITH RECURSIVE t(x) AS (SELECT MIN(ticker) FROM chain_snapshots UNION ALL "
        "SELECT (SELECT MIN(ticker) FROM chain_snapshots WHERE ticker > t.x) FROM t WHERE t.x IS NOT NULL) "
        "SELECT x FROM t WHERE x IS NOT NULL")]
    cc.close()
    if args.tickers:
        tickers = args.tickers.split(",")
    if args.limit:
        tickers = tickers[: args.limit]
    t0 = time.time()
    all_trades, reasons, errors = [], Counter(), {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(build_ticker, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futs), 1):
            t = futs[fut]
            try:
                _, tr, rs = fut.result()
                all_trades.extend(tr)
                reasons.update(rs)
            except Exception as exc:  # recorded, never silently dropped
                errors[t] = repr(exc)
            if i % 200 == 0:
                print(f"{i}/{len(tickers)} tickers, {len(all_trades)} trades, {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(all_trades)
    df.to_parquet(OUT_TRADES, index=False)
    OUT_META.write_text(json.dumps({"tickers": len(tickers), "trades": len(df), "errors": errors,
                                    "exclusion_reasons": dict(reasons.most_common()),
                                    "runtime_s": round(time.time() - t0, 1)}, indent=2))
    print(len(df), "trades;", len(errors), "errors;", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
