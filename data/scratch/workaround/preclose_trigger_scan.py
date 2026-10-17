#!/usr/bin/env python3
"""Pre-close trigger scan (v2, 14 Oct 2026) - which theses are about to confirm on TODAY's close.

v2 (14 Oct fix inbox F-001, N3, T2): also scans every name carded today (cards_<session>.csv from collect_decisions.py,
else the split triage list), not only the ledger focus names (NAT was carded on 13 Oct but missing from the scan);
joins the card decision, side and contract, flags a card whose side differs from the ledger thesis (use the card
levels), writes each quote age in minutes and marks quotes older than 15 minutes STALE.

The standing rule is: a waiting thesis is entered only after a close beyond its trigger. Deciding the next morning
loses a session (FRO, 12 Oct: trigger confirmed Thursday, mined Monday, missed). This scan runs at the same cut-off as
the pre-close macro report (15:10 ET) and lists, from the ledger and live stock quotes:

    CLOSING_BEYOND      price is beyond the trigger now (by up to 1 ATR): enter near the close if still beyond at ~15:50 ET
    CLOSING_BEYOND_EXTENDED  beyond by more than 1 ATR: the chase caution applies (smaller size or wait for a retest)
    WITHIN_0.25ATR      not yet beyond, but a quarter of a day's range away: watch into the close
    MOVE_GONE           already past the half target: do not chase
    INVALIDATED         beyond the invalidation: record PASS
    READY_IN_RANGE      already-confirmed theses still between entry and half target (context)
    (everything else is listed as NOT_NOW in the CSV only)

It does not decide anything: the pre-close macro report supplies the vetoes (event risk overnight), the ticker card
supplies the contract. Read-only on the ledger. One MarketData stock quote per name (1 credit each), with the same
credit reserve as the options tool. Keys from the environment, never printed.

Run from the repo root at about 15:10 ET (20:10 UK):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\preclose_trigger_scan.py                (focus names)
    venv\\Scripts\\python.exe data\\scratch\\workaround\\preclose_trigger_scan.py --all          (every active thesis)
    venv\\Scripts\\python.exe data\\scratch\\workaround\\preclose_trigger_scan.py --quotes-csv q.csv   (offline test: ticker,last)
Writes data/scratch/workaround/preclose/preclose_<YYYY-MM-DD_HHMM>.csv and .md
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "preclose_trigger_scan_v2"
STALE_MIN = 15
WORK = Path("data") / "scratch" / "workaround"
ORDER = {"CLOSING_BEYOND": 0, "CLOSING_BEYOND_EXTENDED": 1, "WITHIN_0.25ATR": 2, "MOVE_GONE": 3, "INVALIDATED": 4,
         "READY_IN_RANGE": 5, "NOT_NOW": 6, "NO_QUOTE": 7}


def newest_ledger() -> Path:
    hits = sorted(h for h in glob.glob(str(WORK / "decision_ledger_*.csv")) if not h.endswith(("_outcomes.csv", "_summary.csv")))
    if not hits:
        raise SystemExit("No decision ledger in data\\scratch\\workaround")
    return Path(hits[-1])


def quote_marketdata(ticker: str, key: str, reserve: int, state: dict) -> tuple[str, float, str]:
    import requests
    if state["stopped"]:
        return ticker, np.nan, "SKIPPED_CREDIT_RESERVE"
    url = f"https://api.marketdata.app/v1/stocks/quotes/{ticker}/"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"Authorization": f"Token {key}"}, timeout=20)
        except Exception as e:
            return ticker, np.nan, f"ERROR_{type(e).__name__}"
        rem = r.headers.get("X-Api-Ratelimit-Remaining")
        try:
            if rem is not None and int(float(rem)) < reserve:
                state["stopped"] = True
        except ValueError:
            pass
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(3 * (attempt + 1))
            continue
        break
    if not r.ok:
        return ticker, np.nan, f"HTTP_{r.status_code}"
    d = r.json()
    for k in ("last", "mid"):
        v = d.get(k)
        if isinstance(v, list) and v and v[0] is not None:
            upd = d.get("updated")
            if isinstance(upd, list) and upd and upd[0]:
                ts = int(upd[0])
                return ticker, float(v[0]), f"OK {k} {datetime.fromtimestamp(ts).strftime('%H:%M')} @{ts}"
            return ticker, float(v[0]), f"OK {k}"
    return ticker, np.nan, "NO_PRICE"


def carded(handoff):
    """Names on today's split triage list, with the card decision when collect_decisions.py has run."""
    if handoff is None or not Path(handoff).exists():
        return pd.DataFrame(columns=["ledger_id"])
    handoff = Path(handoff)
    cards = sorted(handoff.glob("cards_*.csv"))
    if cards:
        c = pd.read_csv(cards[-1], low_memory=False)
    else:
        tri = [pd.read_csv(f, low_memory=False) for f in sorted(handoff.glob("batch*_triage_*.csv"))]
        c = pd.concat(tri, ignore_index=True) if tri else pd.DataFrame(columns=["ledger_id"])
    keep = [k for k in ["ledger_id", "decision", "card_side", "contract", "status"] if k in c.columns]
    return c[keep].rename(columns={"decision": "card_decision", "contract": "card_contract", "status": "card_status"})


def classify(r) -> str:
    s = 1 if r.side == "CALL" else -1
    p, atr = r.price, r.atr
    if pd.isna(p) or pd.isna(atr) or atr <= 0:
        return "NO_QUOTE"
    if (r.invalidation - p) * s >= 0:
        return "INVALIDATED"
    if pd.notna(r.half_target) and (p - r.half_target) * s >= 0:
        return "MOVE_GONE"
    if str(r.readiness).startswith("READY"):
        return "READY_IN_RANGE"
    beyond = (p - r.trigger) * s
    if beyond > atr:
        return "CLOSING_BEYOND_EXTENDED"   # more than 1 ATR past the trigger: the chase caution applies
    if beyond > 0:
        return "CLOSING_BEYOND"
    if -beyond <= 0.25 * atr:
        return "WITHIN_0.25ATR"
    return "NOT_NOW"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger")
    ap.add_argument("--all", action="store_true", help="every active thesis, not only focus")
    ap.add_argument("--quotes-csv", help="offline test: a CSV with ticker,last")
    ap.add_argument("--reserve-credits", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--handoff", help="split hand-off folder whose carded names are added (default: split_handoff in today_context.json)")
    a = ap.parse_args()

    lp = Path(a.ledger) if a.ledger else newest_ledger()
    L = pd.read_csv(lp)
    hp = a.handoff
    if hp is None and (WORK / "today_context.json").exists():
        try:
            hp = json.loads((WORK / "today_context.json").read_text(encoding="utf-8-sig"))["split_handoff"]
        except Exception:
            hp = None
    K = carded(hp)
    lost = sorted(set(K["ledger_id"].dropna()) - set(L["ledger_id"]))
    if lost:
        print(f"WARNING: {len(lost)} carded names are not in {lp.name} (check them by hand): {', '.join(map(str, lost[:15]))}")
    if not a.all and "focus_v3" in L:
        L = L[(L["focus_v3"].astype(str).str.upper() == "TRUE") | L["ledger_id"].isin(K["ledger_id"])]
    L = L[L["readiness"].astype(str).isin(["WAIT_TRIGGER", "READY_FOR_HUMAN_REVIEW", "MANUAL"])].copy()
    for k in ["trigger", "invalidation", "half_target", "atr", "ref_price", "level"]:
        L[k] = pd.to_numeric(L[k], errors="coerce")
    tickers = sorted(L["ticker"].astype(str).str.upper().unique())
    print(f"{VERSION}: {len(L)} theses, {len(tickers)} tickers from {lp.name}")

    if a.quotes_csv:
        q = pd.read_csv(a.quotes_csv)
        prices = {str(t).upper(): (float(v), "OFFLINE") for t, v in zip(q["ticker"], q["last"])}
    else:
        key = os.environ.get("MARKETDATA_API_KEY", "").strip()
        if not key:
            raise SystemExit("Set MARKETDATA_API_KEY in this window (see the open-check notes)")
        state = {"stopped": False}
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            res = list(ex.map(lambda t: quote_marketdata(t, key, a.reserve_credits, state), tickers))
        prices = {t: (p, why) for t, p, why in res}
    L["price"] = L["ticker"].map(lambda t: prices.get(t, (np.nan, "NO_QUOTE"))[0])
    L["quote_status"] = L["ticker"].map(lambda t: prices.get(t, (np.nan, "NO_QUOTE"))[1])
    s = np.where(L["side"] == "CALL", 1, -1)
    L["beyond_trigger_atr"] = ((L["price"] - L["trigger"]) * s / L["atr"]).round(2)
    L["to_invalidation_atr"] = ((L["price"] - L["invalidation"]) * s / L["atr"]).round(2)
    L["to_half_target_atr"] = ((L["half_target"] - L["price"]) * s / L["atr"]).round(2)
    L["move_since_ref_pct"] = ((L["price"] / L["ref_price"] - 1) * 100).round(2)
    L["scan"] = L.apply(classify, axis=1)
    now = datetime.now()

    def age(q):   # from the quote's epoch stamp ("@<epoch>"), so yesterday's last trade is not read as today's time
        m = re.search(r"@(\d{9,})", str(q))
        return round((time.time() - int(m.group(1))) / 60, 1) if m else np.nan
    L["quote_age_min"] = L["quote_status"].map(age)
    L["quote_flag"] = np.select([L["quote_age_min"].isna(), L["quote_age_min"] < -2, L["quote_age_min"] > STALE_MIN],
                                ["NO_TIME", "CLOCK_SKEW", "STALE"], "LIVE")
    if len(K):
        L = L.merge(K, on="ledger_id", how="left")
        mined = K[K["card_status"] == "CARDED"] if "card_status" in K else K
        L["carded"] = L["ledger_id"].isin(mined["ledger_id"])
        for k in ("card_decision", "card_side", "card_contract", "card_status"):
            if k in L:
                L[k] = L[k].fillna("")
        cs = L["card_side"].fillna("").astype(str) if "card_side" in L else pd.Series("", index=L.index)
        L["card_side_differs"] = (cs != "") & (cs != L["side"].astype(str))
    else:
        L["carded"], L["card_side_differs"] = False, False
    L["scan_rank"] = L["scan"].map(ORDER)
    L = L.sort_values(["scan_rank", "beyond_trigger_atr"], ascending=[True, False])

    out = WORK / "preclose"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    cols = ["scan", "carded", "card_decision", "card_side", "card_side_differs", "card_contract", "ledger_id", "ticker", "side",
            "readiness", "setup", "timeframe", "price", "quote_status", "quote_age_min", "quote_flag", "trigger",
            "beyond_trigger_atr", "half_target", "to_half_target_atr", "invalidation", "to_invalidation_atr", "level",
            "move_since_ref_pct", "q50_sessions", "q80_sessions", "money", "earnings_date", "size_note"]
    cols = [c for c in cols if c in L.columns]
    L[cols].to_csv(out / f"preclose_{stamp}.csv", index=False)
    lines = [f"# Pre-close trigger scan {stamp}", "", f"Ledger `{lp.name}` - {len(L)} theses. Prices are live quotes at the "
             "time shown; a thesis counts only if it is still beyond its trigger at the close. Check the pre-close macro "
             "report's vetoes before entering.", ""]
    st = L[L["quote_flag"] == "STALE"]
    if len(st):
        lines += [f"**{len(st)} quotes older than {STALE_MIN} minutes** (do not decide on them): {', '.join(st.ticker.head(20))}", ""]
    cd = L[L["carded"]]
    if len(cd):
        lines += [f"## Carded today ({len(cd)}): the card's own close zone decides; this is the ledger thesis view", ""]
        for r in cd.itertuples():
            note = " - CARD SIDE DIFFERS from the ledger thesis: use the card's levels" if r.card_side_differs else ""
            lines.append(f"- {r.ticker} {r.side} [{r.scan}] {r.price} ({r.quote_flag}) vs trigger {r.trigger} ({r.beyond_trigger_atr:+} ATR); "
                         f"card {getattr(r, 'card_decision', '')} {getattr(r, 'card_side', '')} {getattr(r, 'card_contract', '')}{note}")
        lines.append("")
    for k in ["CLOSING_BEYOND", "CLOSING_BEYOND_EXTENDED", "WITHIN_0.25ATR", "MOVE_GONE", "INVALIDATED"]:
        g = L[L["scan"] == k]
        lines += [f"## {k} ({len(g)})", ""]
        for r in g.itertuples():
            lines.append(f"- {r.ticker} {r.side}: {r.price} vs trigger {r.trigger} ({r.beyond_trigger_atr:+} ATR); "
                         f"half target {r.half_target}, invalidation {r.invalidation}; {getattr(r, 'setup', '')} {getattr(r, 'timeframe', '')}; `{r.ledger_id}`")
        lines.append("")
    (out / f"preclose_{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    print(L["scan"].value_counts().to_dict())
    print("saved:", out / f"preclose_{stamp}.csv")


if __name__ == "__main__":
    main()
