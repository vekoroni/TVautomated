"""G5 measurement (read-only): how far each lane's pricing basis sits from the market, and what one basis changes.

Lane A: the 15 Oct Lab cards (card engine: American CRR, rate 0.0422 fallback, tastytrade dividend, vendor IV held).
Lane B: the 16 Oct split shortlist (avshunter_options_standalone: European BS, rate 0.042, no dividend, vendor IV held).
One basis: IV re-implied from the quoted mid with the American CRR, the run's live T-bill rate and the tastytrade
dividend yield; the same scenario then re-valued with that IV.

Usage: venv\\Scripts\\python.exe Enhancements\\options_valuation_review\\g5_basis_measure.py
"""
from __future__ import annotations

import glob
import json
import math
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.dividend_history import dividend_inputs  # noqa: E402
from canonical_data.market_rate_observation import load_market_rate  # noqa: E402
from contracts.lab_review_projection import CARD_FIELDS  # noqa: E402
from vanguard.ev_engine_v3 import american_option_price  # noqa: E402

STEPS = 150          # inversion tree; the card uses 300 (within 0.2% of 4,000 steps per OT4 test)


def occ(sym: str):
    s = str(sym).strip()
    root = s[:-15]
    return root, date(2000 + int(s[-15:-13]), int(s[-13:-11]), int(s[-11:-9])), s[-9], int(s[-8:]) / 1000.0


def crr(spot, k, years, r, q, vol, side, steps=STEPS):
    return american_option_price(spot, k, years, r, q, vol, side, steps=steps)


def bs_euro(spot, k, years, r, vol, side):
    if years <= 0 or vol <= 0:
        return max(spot - k, 0) if side == "CALL" else max(k - spot, 0)
    d1 = (math.log(spot / k) + (r + 0.5 * vol * vol) * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if side == "CALL":
        return spot * N(d1) - k * math.exp(-r * years) * N(d2)
    return k * math.exp(-r * years) * N(-d2) - spot * N(-d1)


def implied_from_mid(mid, spot, k, years, r, q, side):
    intrinsic = max(spot - k, 0) if side == "CALL" else max(k - spot, 0)
    if not (mid > 0) or years <= 0 or mid <= intrinsic + 1e-6:
        return None
    lo, hi = 0.01, 6.0
    if crr(spot, k, years, r, q, hi, side) < mid:
        return None
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if crr(spot, k, years, r, q, m, side) > mid:
            hi = m
        else:
            lo = m
    return 0.5 * (lo + hi)


def chain_spot(ticker: str, day: str):
    for f in glob.glob(str(ROOT / f"data/canonical/market_observations/option_chain/{day}/{ticker}/*.json")):
        for q in json.load(open(f)):
            if q.get("underlying_price"):
                return float(q["underlying_price"])
    return None


def summarise(name, d):
    print(f"\n=== {name}: {len(d)} contracts, IV re-implied for {d['iv_mid'].notna().sum()}")
    e = d["entry_err_pct"].dropna()
    print(f"entry: current basis model value vs mid, % of mid  p10 {e.quantile(.1):+.1f}  p50 {e.median():+.1f}  "
          f"p90 {e.quantile(.9):+.1f}  |err|>5%: {(e.abs() > 5).mean():.0%}  |err|>10%: {(e.abs() > 10).mean():.0%}")
    v = (d["iv_mid"] - d["iv_vendor"]).dropna() * 100
    print(f"IV: re-implied minus vendor, vol points  p10 {v.quantile(.1):+.1f}  p50 {v.median():+.1f}  p90 {v.quantile(.9):+.1f}")
    t = (d["ret_one_basis"] - d["ret_current"]).dropna() * 100
    print(f"target return: one basis minus current, % points  p10 {t.quantile(.1):+.1f}  p50 {t.median():+.1f}  "
          f"p90 {t.quantile(.9):+.1f}  |change|>10pts: {(t.abs() > 10).mean():.0%}")
    both = d.dropna(subset=["ret_current", "ret_one_basis"])
    for thr in (0.0, 0.20):
        flip = ((both["ret_current"] >= thr) != (both["ret_one_basis"] >= thr))
        print(f"decision 'return >= {thr:.0%}' flips: {int(flip.sum())} of {len(both)} "
              f"(to pass {int((~(both['ret_current'] >= thr) & (both['ret_one_basis'] >= thr)).sum())}, "
              f"to fail {int(((both['ret_current'] >= thr) & ~(both['ret_one_basis'] >= thr)).sum())})")
    return both


# ---------------- Lane A: 15 Oct Lab cards ----------------
RUN, DAY = "20261015_225021", "2026-10-15"
rate_live = load_market_rate(ROOT / f"data/output/runs/{RUN}/macro_snapshot.json").rate_annual_fraction
per_session = json.load(open(ROOT / "config/governed_constants_v1.json"))["anticipated_move"]["calendar_days_per_session"]
f = glob.glob(str(ROOT / f"data/output/runs/{RUN}/intelligence_lab/review_projection/review-*.sqlite"))[0]
con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
cards = pd.DataFrame([dict(zip(CARD_FIELDS, json.loads(r[0])["values"])) for r in con.execute("select card_json from rows")])
num = lambda c: pd.to_numeric(cards[c], errors="coerce")
for c in ("contract_bid", "contract_ask", "contract_iv", "scenario_exit_sessions", "scenario_target_exit_spot",
          "valuation_dividend_yield_annual", "scenario_target_return_on_premium", "rank_expected_multiple",
          "anticipated_value_multiple_q50", "lab_rank"):
    cards[c] = num(c)
a = cards[cards["contract_symbol"].astype(str).str.len() > 15].dropna(
    subset=["contract_bid", "contract_ask", "contract_iv", "scenario_exit_sessions", "scenario_target_exit_spot"]).copy()
spots = {t: chain_spot(t, DAY) for t in a["ticker"].unique()}
fee_o, fee_c = 1.10 / 100, 0.10 / 100
rows = []
for _, r in a.iterrows():
    root, exp, right, k = occ(r["contract_symbol"])
    side = "CALL" if right == "C" else "PUT"
    s0 = spots.get(r["ticker"])
    bid, ask, ivv = r["contract_bid"], r["contract_ask"], r["contract_iv"]
    if not s0 or ask <= 0 or bid < 0 or ask < bid:
        continue
    mid, q = (bid + ask) / 2, (r["valuation_dividend_yield_annual"] if pd.notna(r["valuation_dividend_yield_annual"]) else 0.0)
    dte = (exp - date.fromisoformat(DAY)).days
    t_now, t_exit = dte / 365, max(dte - r["scenario_exit_sessions"] * per_session, 0) / 365
    cur_now = crr(s0, k, t_now, 0.0422, q, ivv, side)
    iv_mid = implied_from_mid(mid, s0, k, t_now, rate_live, q, side)
    def ret(vol, rate):
        v = crr(r["scenario_target_exit_spot"], k, t_exit, rate, q, vol, side, steps=300)
        return max(v - (ask - bid) / 2 - fee_c, 0) / (ask + fee_o) - 1
    rows.append({"ticker": r["ticker"], "lab_rank": r["lab_rank"], "card_ret": r["scenario_target_return_on_premium"],
                 "rank_expected": r["rank_expected_multiple"], "multiple": r["anticipated_value_multiple_q50"],
                 "entry_err_pct": (cur_now / mid - 1) * 100, "iv_vendor": ivv, "iv_mid": iv_mid,
                 "ret_current": ret(ivv, 0.0422), "ret_one_basis": ret(iv_mid, rate_live) if iv_mid else None})
A = pd.DataFrame(rows)
rep = (A["ret_current"] - A["card_ret"]).abs()
print(f"Lane A reproduction check: |my current-basis return - card return| < 0.01 for {(rep[rep.notna()] < 0.01).mean():.0%} of {rep.notna().sum()} valued cards")
print(f"live rate {rate_live} vs card fallback 0.0422")
bothA = summarise("LANE A - Lab cards 15 Oct (card engine)", A)
x = bothA.dropna(subset=["rank_expected", "multiple"]).copy()
x = x[x["multiple"] > 0]
x["hit"] = (x["rank_expected"] + 1) / x["multiple"]
x["rank_new"] = x["hit"] * (1 + x["ret_one_basis"]) - 1
top = lambda col: set(x.sort_values(col, ascending=False).head(50).index)
print(f"rank: top-50 by expected multiple, overlap current vs one basis: {len(top('rank_expected') & top('rank_new'))} of 50 "
      f"(n={len(x)})")

# ---------------- Lane B: 16 Oct split shortlist ----------------
B_DIR = ROOT / "data/scratch/options_intel/2026-10-16_0859"
sl = pd.read_csv(B_DIR / "shortlist.csv", low_memory=False)
led = pd.read_csv(ROOT / "data/scratch/workaround/decision_ledger_2026-10-16.csv", low_memory=False,
                  usecols=lambda c: c in ("ledger_id", "half_target", "level", "q50_sessions"))
sl = sl.merge(led, on="ledger_id", how="left")
rows = []
for _, r in sl.iterrows():
    side = "CALL" if str(r["right"]).upper().startswith("C") else "PUT"
    s0, k, bid, ask, ivv = r["spot"], r["strike"], r["bid"], r["ask"], r["iv"]
    if any(pd.isna(v) for v in (s0, k, bid, ask, ivv)) or ask <= 0 or ask < bid or ivv <= 0:
        continue
    q50 = r["q50_sessions"] if pd.notna(r["q50_sessions"]) else 10
    half = r["half_target"] if pd.notna(r["half_target"]) else (s0 + (r["level"] - s0) / 2 if pd.notna(r["level"]) else None)
    if half is None or pd.isna(half):
        continue
    mid = (bid + ask) / 2
    t_now, t_exit = r["sessions_to_expiry"] / 252, max(r["sessions_to_expiry"] - q50, 0) / 252
    qd = dividend_inputs(r["ticker"], as_of="2026-10-16", spot=s0).get("dividend_yield") or 0.0
    cur_now = bs_euro(s0, k, t_now, 0.042, ivv, side)
    iv_mid = implied_from_mid(mid, s0, k, t_now, rate_live, qd, side)
    cur = max(bs_euro(half, k, t_exit, 0.042, ivv, side) - (ask - bid) / 2, 0) / ask - 1
    one = (max(crr(half, k, t_exit, rate_live, qd, iv_mid, side, steps=300) - (ask - bid) / 2, 0) / ask - 1) if iv_mid else None
    rows.append({"ticker": r["ticker"], "ledger_id": r["ledger_id"], "contract": r.get("contract"), "q": qd,
                 "entry_err_pct": (cur_now / mid - 1) * 100, "iv_vendor": ivv, "iv_mid": iv_mid,
                 "ret_current": cur, "ret_one_basis": one, "tool_ret": r.get("ret_half_target_q50")})
B = pd.DataFrame(rows)
rep = (B["ret_current"] - pd.to_numeric(B["tool_ret"], errors="coerce")).abs()
print(f"\nLane B reproduction check: |my current-basis return - tool return| < 0.01 for {(rep[rep.notna()] < 0.01).mean():.0%} of {rep.notna().sum()}")
print(f"Lane B: dividend yield > 0 for {(B['q'] > 0).sum()} of {len(B)} shortlist contracts (the tool assumes none)")
summarise("LANE B - split shortlist 16 Oct (standalone tool)", B)
out = Path(__file__).with_name("g5_basis_measure_20261017.csv")
pd.concat([A.assign(lane="A"), B.assign(lane="B")]).to_csv(out, index=False)
print(f"\nrows written: {out}")
