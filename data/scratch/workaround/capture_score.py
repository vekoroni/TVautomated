#!/usr/bin/env python3
"""Option capture scorer (v1, 16 Oct 2026): what each trade made AVAILABLE during the hold vs what the rules captured.

For every hand-off row (pipeline) and every card, four separate answers (no hindsight in the rules):
  THESIS     did the stock move the card's way (half target touched before invalidation; close return sign)?
  AVAILABLE  the best executable value during the hold: the best closing BID (real quote where one was recorded,
             else Black-Scholes at that close) and the best intraday bid (model at the day's favourable extreme).
             Never the day's high print: a bid is what one contract could actually be sold into.
  PLANNED    what rules written before entry would have returned: resting good-till sells at +20/+30/+50% of premium,
             and the pipeline's half-target exit; else held to the latest close.
  ACTUAL     the latest close bid (or the real exit for a closed trade).

Model (Medium confidence): BS with r=4%, no dividend; IV solved from the entry quote and re-solved from every real
quote recorded later (live_options / monitor files); spread = entry quote spread (or the real quote's spread).
Run (repo root, PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\capture_score.py
Inputs: monitor\\scorecard\\capture_inputs\\bars.csv, option_marks.csv (export_capture_inputs.py),
        handoff\\split_*\\handoff.csv, monitor\\scorecard\\cards_for_capture.csv (card_day,ticker,contract,entry_price,status[,exit_price,exit_day]).
Writes monitor\\scorecard\\capture_rows_<date>.csv, capture_summary_<date>.csv, capture_report_<date>.md
"""
from __future__ import annotations

import argparse
import glob
import math
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "capture_score_v1"
WORK = Path("data") / "scratch" / "workaround"
R = 0.04
TP_LEVELS = (0.20, 0.30, 0.50)
OCC = re.compile(r"^([A-Z]{1,6})\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def parse_occ(s):
    m = OCC.match(str(s).replace(" ", "").upper())
    if not m:
        return None
    t, yy, mm, dd, cp, k = m.groups()
    return t, date(2000 + int(yy), int(mm), int(dd)), cp, int(k) / 1000


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, v, cp):
    if T <= 0 or v <= 0:
        return max(0.0, (S - K) if cp == "C" else (K - S))
    d1 = (math.log(S / K) + (R + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    if cp == "C":
        return S * ncdf(d1) - K * math.exp(-R * T) * ncdf(d2)
    return K * math.exp(-R * T) * ncdf(-d2) - S * ncdf(-d1)


def solve_iv(price, S, K, T, cp):
    intrinsic = max(0.0, (S - K) if cp == "C" else (K - S))
    if not price or price <= intrinsic + 1e-4 or T <= 0:
        return None
    lo, hi = 0.01, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs(S, K, T, mid, cp) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def yf(d0, exp):
    return max((exp - d0).days, 0) / 365.0


def replay(contract, entry_day, entry_price, entry_S, spread_frac, bars, marks, iv0=None, exit_price=None, exit_day=None):
    """Day-by-day path after entry. Returns dict of capture metrics or None."""
    p = parse_occ(contract)
    if p is None or bars.empty:
        return None
    _, exp, cp, K = p
    d_entry = datetime.strptime(entry_day, "%Y-%m-%d").date()
    iv = iv0 or solve_iv(entry_price, entry_S, K, yf(d_entry, exp), cp)
    if not iv:
        return None
    sf = spread_frac if (spread_frac is not None and 0 <= spread_frac < 2) else 0.10
    path = bars[bars.trading_date > entry_day].sort_values("trading_date")
    if exit_day:
        path = path[path.trading_date <= exit_day]
    mk = marks.set_index("date") if not marks.empty else None
    days = []
    for b in path.itertuples():
        d = datetime.strptime(b.trading_date, "%Y-%m-%d").date()
        T = yf(d, exp)
        real = None
        if mk is not None and b.trading_date in mk.index:
            r = mk.loc[b.trading_date]
            r = r.iloc[-1] if isinstance(r, pd.DataFrame) else r
            if pd.notna(r.bid) and pd.notna(r.ask) and r.ask > 0:
                real = r
                rmid = (r.bid + r.ask) / 2
                iv_new = solve_iv(rmid, b.close, K, T, cp)
                iv = iv_new or iv
                if rmid > 0:
                    sf = (r.ask - r.bid) / rmid
        model_mid_close = bs(b.close, K, T, iv, cp)
        close_bid = float(real.bid) if real is not None else max(0.0, model_mid_close * (1 - sf / 2))
        fav_S = b.high if cp == "C" else b.low
        adv_S = b.low if cp == "C" else b.high
        best_bid = max(close_bid, bs(fav_S, K, T, iv, cp) * (1 - sf / 2))
        worst_bid = min(close_bid, bs(adv_S, K, T, iv, cp) * (1 - sf / 2))
        days.append(dict(day=b.trading_date, close_bid=close_bid, best_bid=best_bid, worst_bid=worst_bid,
                         real=real is not None, S_close=b.close, S_fav=fav_S, iv=iv))
    if not days:
        return None
    D = pd.DataFrame(days)
    E = entry_price
    ret = lambda x: x / E - 1
    out = dict(sessions=len(D), real_marks=int(D.real.sum()), iv_entry=round(iv0 or 0, 3),
               mfe_close_bid_pct=round(ret(D.close_bid.max()) * 100, 1),
               mfe_intraday_bid_pct=round(ret(D.best_bid.max()) * 100, 1),
               mae_intraday_bid_pct=round(ret(D.worst_bid.min()) * 100, 1),
               day_of_mfe=int(D.best_bid.values.argmax()) + 1,
               first_close_profit_day=(int(np.argmax(D.close_bid.values > E)) + 1) if (D.close_bid > E).any() else None,
               closes_in_profit=int((D.close_bid > E).sum()),
               last_day=D.day.iloc[-1])
    actual = exit_price if exit_price is not None else D.close_bid.iloc[-1]
    out["actual_pct"] = round(ret(actual) * 100, 1)
    out["gave_back_pts"] = round(out["mfe_close_bid_pct"] - out["actual_pct"], 1)
    for lv in TP_LEVELS:
        tgt = E * (1 + lv)
        hit = np.where(D.best_bid.values >= tgt)[0]
        out[f"tp{int(lv*100)}_hit_day"] = int(hit[0]) + 1 if len(hit) else None
        out[f"tp{int(lv*100)}_pct"] = round(lv * 100, 1) if len(hit) else out["actual_pct"]
    return out


def load_marks(path):
    if not Path(path).exists():
        return pd.DataFrame(columns=["date", "contract", "bid", "ask"])
    m = pd.read_csv(path)
    m["contract"] = m.contract.astype(str).str.replace(" ", "").str.upper()
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default=str(WORK / "monitor" / "scorecard" / "capture_inputs"))
    ap.add_argument("--handoffs", default=str(WORK / "handoff" / "split_*" / "handoff.csv"))
    ap.add_argument("--cards", default=str(WORK / "monitor" / "scorecard" / "cards_for_capture.csv"))
    ap.add_argument("--extra-marks", default="", help="optional CSV of extra quotes: date,contract,bid,ask")
    ap.add_argument("--out", default=str(WORK / "monitor" / "scorecard"))
    a = ap.parse_args()
    inp = Path(a.inputs)
    bars = pd.read_csv(inp / "bars.csv")
    marks = load_marks(inp / "option_marks.csv")
    if a.extra_marks:
        marks = pd.concat([marks, load_marks(a.extra_marks)], ignore_index=True)
    bars_by = {t: g for t, g in bars.groupby("ticker")}
    marks_by = {c: g for c, g in marks.groupby("contract")}
    rows = []

    H = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(a.handoffs))], ignore_index=True) if glob.glob(a.handoffs) else pd.DataFrame()
    H = H.drop_duplicates("ledger_id") if len(H) else H
    for r in H.itertuples():
        t, dsess = str(r.ticker).upper(), str(r.ledger_id)[:10]
        b = bars_by.get(t, pd.DataFrame(columns=bars.columns))
        b = b[b.trading_date >= dsess].sort_values("trading_date")
        base = dict(group="pipeline", ledger_id=r.ledger_id, ticker=t, side=r.side, money=getattr(r, "money", None),
                    state=r.state, contract=r.best_contract, best_ask=r.best_ask, best_bid=r.best_bid)
        if b.empty or pd.isna(r.best_contract) or pd.isna(r.best_ask) or r.best_ask <= 0:
            rows.append({**base, "entry_status": "NO_DATA"})
            continue
        sgn = 1 if r.side == "CALL" else -1
        if str(r.state).startswith("READY"):
            ei, eS, eday_close = 0, float(b.open.iloc[0]), False
        else:
            hit = np.where((b.close.values - r.trigger) * sgn > 0)[0]
            if not len(hit):
                rows.append({**base, "entry_status": "NOT_TRIGGERED"})
                continue
            ei, eS, eday_close = int(hit[0]), float(b.close.iloc[hit[0]]), True
        eday = b.trading_date.iloc[ei]
        p = parse_occ(r.best_contract)
        if p is None:
            rows.append({**base, "entry_status": "BAD_CONTRACT"})
            continue
        _, exp, cp, K = p
        mid0 = (r.best_bid + r.best_ask) / 2
        sf = (r.best_ask - r.best_bid) / mid0 if mid0 > 0 else 0.1
        iv = r.best_iv if pd.notna(r.best_iv) and r.best_iv > 0 else solve_iv(mid0, r.ref_price, K, yf(datetime.strptime(dsess, "%Y-%m-%d").date(), exp), cp)
        T0 = yf(datetime.strptime(eday, "%Y-%m-%d").date(), exp)
        emid = bs(eS, K, T0, iv, cp)
        # the entry day itself counts as path for an OPEN entry (sell later the same day is possible)
        bb = b if not eday_close else b
        prev_day = b.trading_date.iloc[ei - 1] if (not eday_close and ei > 0) else None
        for basis, E in (("ask", emid * (1 + sf / 2)), ("mid", emid)):
            res = replay(r.best_contract, eday if eday_close else (prev_day or str(pd.Timestamp(eday) - pd.Timedelta(days=1))[:10]),
                         E, eS, sf, bb, marks_by.get(str(r.best_contract).upper(), pd.DataFrame()), iv0=iv)
            if res is None:
                rows.append({**base, "entry_status": "NO_PATH_YET", "entry_day": eday, "entry_basis": basis})
                continue
            row = {**base, "entry_status": "ENTERED", "entry_rule": "CLOSE" if eday_close else "OPEN", "entry_day": eday,
                   "entry_S": eS, "entry_basis": basis, "entry_price": round(E, 3), "spread_frac": round(sf, 3),
                   "within_cap": E <= 5.0, "spread_ok": sf <= 0.25, **res}
            path = b[b.trading_date >= eday]
            if pd.notna(getattr(r, "half_target", np.nan)) and pd.notna(getattr(r, "invalidation", np.nan)):
                ht, inv = r.half_target, r.invalidation
                st = "OPEN"
                for x in path.itertuples():
                    t_hit = (x.high >= ht) if sgn > 0 else (x.low <= ht)
                    i_hit = (x.low <= inv) if sgn > 0 else (x.high >= inv)
                    if i_hit:
                        st = "INVALIDATED"; break
                    if t_hit:
                        st = "HALF_TARGET"
                        Tt = yf(datetime.strptime(x.trading_date, "%Y-%m-%d").date(), exp)
                        row["half_target_exit_pct"] = round((bs(ht, K, Tt, row.get("iv_entry") or iv, cp) * (1 - sf / 2) / E - 1) * 100, 1)
                        break
                row["thesis"] = st
                row["stock_ret_pct"] = round((path.close.iloc[-1] / eS - 1) * sgn * 100, 2)
                row.setdefault("half_target_exit_pct", row["actual_pct"])
            rows.append(row)

    if Path(a.cards).exists():
        C = pd.read_csv(a.cards)
        for c in C.itertuples():
            t = str(c.ticker).upper()
            b = bars_by.get(t, pd.DataFrame(columns=bars.columns))
            eb = b[b.trading_date <= c.card_day].sort_values("trading_date")
            if eb.empty:
                rows.append(dict(group="card", ticker=t, contract=c.contract, card_day=c.card_day, status=c.status, entry_status="NO_DATA"))
                continue
            eS = float(eb.close.iloc[-1])
            ex_p = getattr(c, "exit_price", np.nan)
            ex_d = getattr(c, "exit_day", np.nan)
            res = replay(c.contract, c.card_day, float(c.entry_price), eS, getattr(c, "spread_frac", np.nan) if hasattr(c, "spread_frac") else None,
                         b, marks_by.get(str(c.contract).replace(" ", "").upper(), pd.DataFrame()),
                         exit_price=None if pd.isna(ex_p) else float(ex_p), exit_day=None if pd.isna(ex_d) else str(ex_d))
            if res is None:
                rows.append(dict(group="card", ticker=t, contract=c.contract, card_day=c.card_day, status=c.status, entry_status="NO_IV"))
                continue
            rows.append(dict(group="card", ticker=t, contract=c.contract, card_day=c.card_day, status=c.status, entry_status="ENTERED",
                             entry_day=c.card_day, entry_S=eS, entry_basis="card", entry_price=float(c.entry_price), **res))

    D = pd.DataFrame(rows)
    stamp = datetime.now().strftime("%Y-%m-%d")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    D.to_csv(out / f"capture_rows_{stamp}.csv", index=False)
    S = summarise(D)
    S.to_csv(out / f"capture_summary_{stamp}.csv", index=False)
    print(S.to_string(index=False))
    print(f"{VERSION}: {len(D)} rows -> {out}")


def summarise(D):
    E = D[D.get("entry_status", "") == "ENTERED"].copy()
    groups = []
    if len(E):
        P = E[E.group == "pipeline"]
        for basis in ("ask", "mid"):
            Pb = P[P.entry_basis == basis]
            groups += [(f"pipeline all, entry at {basis}", Pb),
                       (f"pipeline within cap + spread<=25%, entry at {basis}", Pb[Pb.within_cap & Pb.spread_ok]),
                       (f"pipeline cap + spread + money WITH, entry at {basis}", Pb[Pb.within_cap & Pb.spread_ok & (Pb.money == "WITH")])]
        groups.append(("cards (card price)", E[E.group == "card"]))
        groups.append(("real trades", E[(E.group == "card") & E.status.astype(str).str.startswith("FILLED")]))
    rows = []
    for name, g in groups:
        if not len(g):
            continue
        losers = g[g.actual_pct < 0]
        rows.append({
            "group": name, "n": len(g),
            "thesis_half_target_pct": round((g.get("thesis", pd.Series(dtype=str)) == "HALF_TARGET").mean() * 100, 0) if "thesis" in g else None,
            "available_best_close_bid_median": g.mfe_close_bid_pct.median(),
            "available_best_intraday_bid_median": g.mfe_intraday_bid_pct.median(),
            "pct_rows_ever_in_profit_close": round((g.mfe_close_bid_pct > 0).mean() * 100, 0),
            "actual_now_median": g.actual_pct.median(), "actual_now_mean": round(g.actual_pct.mean(), 1),
            "win_now_pct": round((g.actual_pct > 0).mean() * 100, 0),
            "gave_back_median_pts": g.gave_back_pts.median(),
            "losers_now": len(losers),
            "losers_once_profit_close_pct": round((losers.mfe_close_bid_pct > 0).mean() * 100, 0) if len(losers) else None,
            "losers_once_up20_intraday_pct": round((losers.mfe_intraday_bid_pct >= 20).mean() * 100, 0) if len(losers) else None,
            **{f"rest_sell_+{int(l*100)}_mean": round(g[f"tp{int(l*100)}_pct"].mean(), 1) for l in TP_LEVELS},
            **{f"rest_sell_+{int(l*100)}_fill_pct": round(g[f"tp{int(l*100)}_hit_day"].notna().mean() * 100, 0) for l in TP_LEVELS},
            "half_target_rule_mean": round(g["half_target_exit_pct"].mean(), 1) if "half_target_exit_pct" in g and g["half_target_exit_pct"].notna().any() else None,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()
