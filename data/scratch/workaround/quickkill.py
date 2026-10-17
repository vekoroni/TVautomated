#!/usr/bin/env python3
"""Quick-kill screen for a hand-off batch (v1, 11 Oct 2026).

Five cheap checks run BEFORE a name goes to deep mining, so names fail in triage and not after an hour of mining:
  1 base rate   does the setup beat the ticker's normal days, over the thesis's own distance and time?  (needs the ticker pack)
  2 sector tag  does the hand-off's sector ETF agree with the ETF holdings files / Tastytrade's sector?
  3 earnings    Tastytrade date vs the hand-off date, and does it land before the median or 80th-percentile time?
  4 speed       does the best contract pay at the half target reached at the median time?
  5 spread      spread of the best contract at the hand-off quote, plus Tastytrade's options liquidity rating
Also carried from the hand-off (not new checks): invalidation odds >= half-target odds, and half-target odds under 15%.

Usage: python3 -I quickkill.py <handoff.csv> <holdings_dir> <packs_dir> <tt.json> <batch> <out.csv>
Flags are listed, never weighted or summed into a score. Context for ACK's decision, not a verdict.
"""
import glob, json, os, sys
import numpy as np, pandas as pd

HANDOFF, HOLD, PACKS, TTJ, BATCH, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6]
W = 15            # look-back for the setup proxies (same as the deep-dive base-rate script)
GAP = 10          # sessions between events so they do not overlap
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
# Tastytrade's sector labels are not GICS: each maps to the SPDR funds it can reasonably mean. Empty = cannot judge.
TT_MAP = {"Basic Materials": {"XLB"}, "Energy": {"XLE"}, "Technology": {"XLK", "XLC"}, "Healthcare": {"XLV"},
          "Financial": {"XLF"}, "Utilities": {"XLU"}, "Consumer Cyclical": {"XLY"}, "Consumer/Non-Cyclical": {"XLP"},
          "Capital Goods": {"XLI", "XLY"}, "Transportation": {"XLI", "XLE"}, "Services": set(), "Conglomerates": {"XLI"}}

def setup_family(setup, side):
    s = setup.lower()
    if "spring candidate" in s: return "spring"
    if "upthrust candidate" in s: return "upthrust"
    if "change-of-behaviour" in s: return None
    return "breakout" if side == "CALL" else "breakdown"

def load_prices(ticker):
    f = glob.glob(os.path.join(PACKS, ticker, "**", "prices_ohlcv_daily.csv"), recursive=True)
    if not f: return None
    p = pd.read_csv(f[0]).sort_values("trading_date").reset_index(drop=True)
    return p[p.bar_status == "COMPLETE"].reset_index(drop=True) if "bar_status" in p else p

def base_rate(p, side, family, d_atr, h_q50, h_q80):
    """First-touch test with symmetric barriers d_atr ATRs either side of the event close, inside h_q80 sessions."""
    o, h, l, c = [p[k].values.astype(float) for k in ("open", "high", "low", "close")]
    n = len(p); dirn = 1 if side == "CALL" else -1
    tr = np.maximum(h - l, np.maximum(abs(h - np.r_[c[0], c[:-1]]), abs(l - np.r_[c[0], c[:-1]])))
    atr = pd.Series(tr).rolling(14).mean().values
    H = int(h_q80); Hm = int(h_q50)
    def outcome(i):
        up, dn = c[i] + d_atr * atr[i], c[i] - d_atr * atr[i]
        fav_by_median = False
        for k in range(i + 1, min(i + H, n - 1) + 1):
            hit_up, hit_dn = h[k] >= up, l[k] <= dn
            if hit_up and hit_dn: return ("both", False)
            if hit_up: return ("fav" if dirn > 0 else "adv", dirn > 0 and k - i <= Hm)
            if hit_dn: return ("fav" if dirn < 0 else "adv", dirn < 0 and k - i <= Hm)
        return ("none", fav_by_median)
    first = max(W + 1, 15); last = n - H - 1
    if last - first < 60: return {"br_note": "history too short"}
    cond = {"breakout": lambda i: c[i] > h[i - W:i].max(),
            "breakdown": lambda i: c[i] < l[i - W:i].min(),
            "spring": lambda i: l[i] < l[i - W:i].min() and c[i] > l[i - W:i].min(),
            "upthrust": lambda i: h[i] > h[i - W:i].max() and c[i] < h[i - W:i].max()}[family]
    ev, prev = [], -99
    for i in range(first, last + 1):
        if cond(i) and i - prev > GAP: ev.append(i); prev = i
    def rates(idx):
        r = [outcome(i) for i in idx]; m = len(r)
        return (sum(x[0] == "fav" for x in r) / m, sum(x[0] == "adv" for x in r) / m, sum(x[1] for x in r) / m) if m else (np.nan,) * 3
    cf, ca, cm = rates(range(first, last + 1)); ef, ea, em = rates(ev); ne = len(ev)
    out = {"br_proxy": family, "br_events": ne, "br_barrier_atr": round(d_atr, 2), "br_window_sessions": H,
           "br_event_fav_first": round(ef, 2) if ne else np.nan, "br_control_fav_first": round(cf, 2),
           "br_event_adv_first": round(ea, 2) if ne else np.nan, "br_control_adv_first": round(ca, 2),
           "br_control_reach_by_median": round(cm, 2), "br_event_reach_by_median": round(em, 2) if ne else np.nan,
           "atr14": round(float(atr[-1]), 3), "last_bar": p.trading_date.iloc[-1], "last_close": float(c[-1])}
    if atr[-1] / c[-1] < 0.003: out["br_read"] = "PRICE_PINNED_NOT_TESTABLE"      # e.g. a stock held at a deal price
    elif cf + ca < 0.5: out["br_read"] = "TARGET_RARELY_REACHED_IN_WINDOW"          # neither barrier reached in most windows
    elif ne < 8: out["br_read"] = "TOO_FEW_EVENTS"
    else:
        se = (ef * (1 - ef) / ne) ** 0.5; diff = ef - cf
        out["br_diff_pts"] = round(diff * 100); out["br_se_pts"] = round(se * 100)
        out["br_read"] = "BEATS_NORMAL_DAYS" if diff > se else ("WORSE_THAN_NORMAL_DAYS" if diff < -se else "NO_BETTER_THAN_NORMAL_DAYS")
    return out

h = pd.read_csv(HANDOFF); h = h[h.batch == BATCH].copy()
tt = json.load(open(TTJ))
hold = {}
for f in glob.glob(os.path.join(HOLD, "*_latest.json")):
    j = json.load(open(f))
    if j["etf"] in SECTOR_ETFS:
        for r in j["holdings"]:
            if r.get("ticker"): hold[r["ticker"].upper()] = j["etf"]
rows = []
for _, r in h.iterrows():
    t, side = r.ticker, r.side; x = {"ledger_id": r.ledger_id, "ticker": t, "side": side, "setup": r.setup, "timeframe": r.timeframe}
    flags = []
    # 1 base rate
    fam = setup_family(r.setup, side); p = load_prices(t)
    if p is None: x["br_read"] = "NO_PACK"
    elif fam is None: x["br_read"] = "NOT_TESTED"
    else:
        # the hand-off has no median/80th-percentile time for some weekly and monthly theses: fall back to 15 / 30 sessions and say so
        h50, h80 = (r.q50_sessions, r.q80_sessions) if pd.notna(r.q80_sessions) else (15, 30)
        x["br_window_source"] = "handoff q50/q80" if pd.notna(r.q80_sessions) else "fallback 15/30 sessions (no time in hand-off)"
        b = base_rate(p, side, fam, 1.0, h50, h80)   # first pass only to get ATR
        if "atr14" in b:
            d = abs(r.half_target - r.ref_price) / b["atr14"]
            b = base_rate(p, side, fam, d, h50, h80)
            b["ref_vs_last_close"] = round(r.ref_price - b["last_close"], 3)
        x.update(b); x.setdefault("br_read", b.get("br_note", "NOT_TESTED"))
    if x["br_read"] == "WORSE_THAN_NORMAL_DAYS": flags.append("BASE_RATE_WORSE")
    elif x["br_read"] == "PRICE_PINNED_NOT_TESTABLE": flags.append("PRICE_PINNED")
    elif x["br_read"] == "TARGET_RARELY_REACHED_IN_WINDOW": flags.append("TARGET_RARELY_REACHED_IN_WINDOW")
    elif x["br_read"] == "NO_BETTER_THAN_NORMAL_DAYS": flags.append("BASE_RATE_NO_BETTER")
    # 2 sector tag
    m = tt.get(t, {}); x["handoff_sector_etf"] = r.sector_etf; x["handoff_money"] = r.money
    x["holdings_sector_etf"] = hold.get(t, ""); x["tt_sector"] = m.get("sector", ""); x["tt_industry"] = m.get("industry", "")
    if hold.get(t):
        x["sector_read"] = "CONFIRMED_BY_HOLDINGS" if hold[t] == r.sector_etf else "MISMATCH_VS_HOLDINGS"
    elif r.sector_etf not in SECTOR_ETFS: x["sector_read"] = "ETF_OR_UNMAPPED"
    elif m.get("sector") and TT_MAP.get(m["sector"]):
        x["sector_read"] = "CONSISTENT_WITH_TASTYTRADE" if r.sector_etf in TT_MAP[m["sector"]] else "CONFLICTS_WITH_TASTYTRADE"
    else: x["sector_read"] = "NOT_VERIFIABLE"
    if x["sector_read"] in ("MISMATCH_VS_HOLDINGS", "CONFLICTS_WITH_TASTYTRADE"): flags.append("SECTOR_TAG_SUSPECT")
    # 3 earnings
    x["earnings_vs_hold"] = ""; x["handoff_earnings"] = r.earnings_date; x["tt_earnings"] = m.get("earnings", ""); x["earnings_sessions"] = r.earnings_sessions
    if not m: x["earnings_read"] = "NOT_RECHECKED"
    elif pd.isna(r.earnings_date) and not m.get("earnings"): x["earnings_read"] = "NONE"
    elif m.get("earnings_past"): x["earnings_read"] = "TT_SHOWS_LAST_REPORT_ONLY"
    else: x["earnings_read"] = "DATE_CONFIRMED" if str(r.earnings_date) == m.get("earnings") else "DATE_DIFFERS"
    if x["earnings_read"] == "DATE_DIFFERS": flags.append("EARNINGS_DATE_DIFFERS")
    if pd.notna(r.earnings_sessions) and pd.notna(r.q50_sessions):
        if r.earnings_sessions <= r.q50_sessions:
            flags.append("EARNINGS_BEFORE_MEDIAN_TIME")
            x["earnings_vs_hold"] = "BEFORE_MEDIAN_TIME"
        elif r.earnings_sessions <= r.q80_sessions: x["earnings_vs_hold"] = "BEFORE_80TH_PCT_TIME"
        else: x["earnings_vs_hold"] = "AFTER_80TH_PCT_TIME"
    elif pd.notna(r.earnings_sessions) and r.earnings_sessions <= 10: flags.append("EARNINGS_WITHIN_10_SESSIONS")
    # 4 speed
    x["ret_half_at_median"] = r.best_ret_half_target_q50; x["ret_level_at_median"] = r.best_ret_level_q50
    x["q50_sessions"] = r.q50_sessions; x["q80_sessions"] = r.q80_sessions
    if pd.notna(r.best_ret_half_target_q50) and r.best_ret_half_target_q50 < 0.10: flags.append("PAYS_UNDER_10PCT_AT_HALF")
    # 5 spread / liquidity
    x["best_contract"] = r.best_contract; x["bid"] = r.best_bid; x["ask"] = r.best_ask; x["spread_fraction"] = r.best_spread_fraction
    x["tt_liquidity_rating"] = m.get("liq", "")
    if r.best_spread_fraction > 0.25: flags.append("SPREAD_OVER_25PCT")
    elif r.best_spread_fraction > 0.15: flags.append("SPREAD_15_TO_25PCT")
    if m.get("liq") == 1: flags.append("LIQUIDITY_RATING_1")
    x["p_half_target_first"] = r.p_half_target_first; x["p_invalidation_first"] = r.p_invalidation_first
    if r.p_invalidation_first >= r.p_half_target_first: flags.append("INVALIDATION_ODDS_GE_HALF_TARGET_ODDS")
    if r.p_half_target_first < 0.15: flags.append("HALF_TARGET_ODDS_UNDER_15PCT")
    x["flags"] = "; ".join(flags); x["n_flags"] = len(flags)
    rows.append(x)
d = pd.DataFrame(rows)
d.to_csv(OUT, index=False)
print(d[["ticker", "side", "br_read", "sector_read", "earnings_read", "n_flags", "flags"]].to_string())
