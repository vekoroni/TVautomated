"""AVS signal accuracy audit (read-only).

Independently recomputes the key signal fields of one pipeline run from raw
inputs and reports where the published values disagree.

Raw sources (never written):
  * data/canonical/historical_prices.sqlite           point-in-time daily OHLCV
  * data/canonical/market_observations/option_chain/  raw MarketData chains
Published sources (never written):
  * data/output/runs/<run_id>/discovery, options, morning_validation, intelligence_lab

Outputs go to audit/signal_accuracy/runs/<run_id>/ only.

Usage:
  venv\\Scripts\\python.exe audit\\signal_accuracy\\signal_accuracy_audit.py --run-id 20260914_214012
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAIN_ROOT = REPO / "data" / "canonical" / "market_observations" / "option_chain"

NYSE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1),
}
OCC_RE = re.compile(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$")
DIRECTIONAL = {"CALL", "PUT"}
READY_STATUSES = {"EOD_TRIGGER_READY", "EOD_THESIS_READY_REPAIR_AT_OPEN"}

# Tolerances
TOL_PRICE = 0.011          # underlying prices are published at 2 dp
TOL_LEVEL = 0.006          # invalidation/target compared across stages
TOL_OPT = 0.0051           # option bid/ask/mid
TOL_ATR_REL = 0.01
TOL_PCT = 0.02             # percentage-point fields (atr_pct, gap_pct, range_pct)
TOL_ADX = 1.0
TOL_RR = 0.02
TOL_SPREAD_FRAC = 0.0005
TOL_IV = 0.002
TOL_DELTA = 0.005


# ─────────────────────────────── helpers ────────────────────────────────────
def f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def s(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip()


def sessions_after(asof: date, expiry: date) -> int:
    n, d = 0, asof + timedelta(days=1)
    while d <= expiry:
        if d.weekday() < 5 and d not in NYSE_HOLIDAYS:
            n += 1
        d += timedelta(days=1)
    return n


def last_completed_session(asof: date) -> date:
    d = asof
    while d.weekday() >= 5 or d in NYSE_HOLIDAYS:
        d -= timedelta(days=1)
    return d


def bs_delta(spot, strike, calendar_days, iv, right, rate=0.04):
    if not spot or not strike or iv is None or iv <= 0.01 or calendar_days is None:
        return None
    T = max(calendar_days, 1) / 365.0
    d1 = (math.log(spot / strike) + (rate + iv * iv / 2) * T) / (iv * math.sqrt(T))
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return nd1 if right == "CALL" else nd1 - 1


def parse_occ(symbol: str):
    m = OCC_RE.match(s(symbol).upper())
    if not m:
        return None
    root, ymd, right, strike = m.groups()
    return {
        "underlying": root,
        "expiry": datetime.strptime(ymd, "%y%m%d").date(),
        "right": "CALL" if right == "C" else "PUT",
        "strike": int(strike) / 1000.0,
    }


class Recorder:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.rows: list[dict] = []

    def add(self, ticker, stage, field, check_id, status, published=None,
            recomputed=None, reason="", severity=None):
        diff = None
        pf, rf = f(published), f(recomputed)
        if pf is not None and rf is not None:
            diff = round(abs(pf - rf), 6)
        self.rows.append({
            "run_id": self.run_id, "ticker": ticker, "stage": stage, "field": field,
            "check_id": check_id, "status": status,
            "published": published if not isinstance(published, float) else round(published, 6),
            "recomputed": recomputed if not isinstance(recomputed, float) else round(recomputed, 6),
            "abs_diff": diff, "reason": reason,
        })

    def compare(self, ticker, stage, field, check_id, published, recomputed, tol,
                rel=False, missing_status="NOT_EVALUABLE", reason=""):
        pf, rf = f(published), f(recomputed)
        if rf is None:
            self.add(ticker, stage, field, check_id, "NOT_EVALUABLE", published, recomputed,
                     reason or "recomputation input unavailable")
            return
        if pf is None:
            self.add(ticker, stage, field, check_id, missing_status, published, recomputed,
                     reason or "published value missing")
            return
        limit = tol * max(abs(rf), 1e-9) if rel else tol
        ok = abs(pf - rf) <= limit
        self.add(ticker, stage, field, check_id, "PASS" if ok else "FAIL", pf, rf,
                 "" if ok else (reason or f"differs by {abs(pf - rf):.6g} (tolerance {limit:.6g})"))


# ─────────────────────────────── loaders ────────────────────────────────────
def read_csv(path: Path, wanted: list[str]) -> pd.DataFrame:
    cols = pd.read_csv(path, nrows=0).columns
    use = [c for c in wanted if c in cols]
    df = pd.read_csv(path, usecols=use, low_memory=False)
    for c in wanted:
        if c not in df.columns:
            df[c] = np.nan
    return df.drop_duplicates("ticker").set_index("ticker", drop=False)


def load_prices(tickers: list[str], asof: date, cutoff_utc: str) -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{PRICE_DB}?mode=ro", uri=True)
    start = (asof - timedelta(days=620)).isoformat()
    out: dict[str, pd.DataFrame] = {}
    chunk = 400
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        q = (
            "SELECT ticker, trading_date, adjustment_convention, open, high, low, close, volume, "
            "bar_status, observed_at FROM ohlcv_daily WHERE trading_date BETWEEN ? AND ? "
            f"AND ticker IN ({','.join('?' * len(part))})"
        )
        df = pd.read_sql_query(q, con, params=[start, asof.isoformat(), *part])
        for t, g in df.groupby("ticker"):
            conv = g["adjustment_convention"].value_counts().idxmax()
            out[t] = g[g["adjustment_convention"] == conv].sort_values("trading_date").reset_index(drop=True)
    # Bars revised after the run: restore the value the run could have seen.
    rev_cols = [r[1] for r in con.execute("PRAGMA table_info(ohlcv_daily_revisions)")]
    ts_col = next((c for c in rev_cols if c in ("revised_at", "recorded_at", "created_at", "observed_at")), None)
    revised = set()
    if ts_col:
        q = (f"SELECT ticker, trading_date, previous_values_json, {ts_col} AS ts FROM ohlcv_daily_revisions "
             f"WHERE {ts_col} > ? AND trading_date >= ? ORDER BY {ts_col} ASC")
        for t, d, prev, _ in con.execute(q, (cutoff_utc, start)):
            if t not in out or (t, d) in revised:
                continue
            revised.add((t, d))
            try:
                pv = json.loads(prev)
            except Exception:
                continue
            g = out[t]
            idx = g.index[g["trading_date"] == d]
            for k in ("open", "high", "low", "close", "volume"):
                if k in pv and len(idx):
                    g.loc[idx, k] = pv[k]
    con.close()
    return out


def load_chain_quotes(tickers_symbols: dict[str, set], session: date, dataset_ids: dict[str, str]):
    """Return {symbol: raw contract dict} for the requested symbols only."""
    found: dict[str, dict] = {}
    source: dict[str, str] = {}
    day_dir = CHAIN_ROOT / session.isoformat()
    for ticker, symbols in tickers_symbols.items():
        tdir = day_dir / ticker
        if not tdir.is_dir():
            continue
        files = sorted(tdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        preferred = dataset_ids.get(ticker)
        if preferred:
            files.sort(key=lambda p: p.stem != preferred)
        remaining = set(symbols)
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            contracts = payload if isinstance(payload, list) else payload.get("contracts", [])
            for c in contracts:
                sym = s(c.get("symbol")).upper()
                if sym in remaining:
                    found[sym] = c
                    source[sym] = path.name
                    remaining.discard(sym)
            if not remaining:
                break
    return found, source


# ─────────────────────────────── checks ─────────────────────────────────────
def indicator_recompute(bars: pd.DataFrame) -> dict:
    df = bars
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().iloc[-1]
    dm_p = high.diff()
    dm_m = -low.diff()
    dm_p = dm_p.where((dm_p > dm_m) & (dm_p > 0), 0.0)
    dm_m = dm_m.where((dm_m > dm_p) & (dm_m > 0), 0.0)
    atr_s = tr.ewm(span=14, adjust=False).mean()
    di_p = 100 * dm_p.ewm(span=14, adjust=False).mean() / atr_s
    di_m = 100 * dm_m.ewm(span=14, adjust=False).mean() / atr_s
    dx = 100 * (di_p - di_m).abs() / (di_p + di_m + 1e-10)
    adx = dx.ewm(span=14, adjust=False).mean().iloc[-1]
    px = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(df) >= 2 else px
    return {
        "close": px,
        "atr14": float(atr14) if pd.notna(atr14) else None,
        "atr_pct": float(atr14) / px * 100 if pd.notna(atr14) and px > 0 else None,
        "gap_pct": (float(df["open"].iloc[-1]) - prev) / prev * 100 if prev > 0 else None,
        "range_pct": (float(high.iloc[-1]) - float(low.iloc[-1])) / px * 100 if px > 0 else None,
        "adx": float(adx) if pd.notna(adx) else None,
    }


def check_underlying(rec: Recorder, disc: pd.DataFrame, prices, session: date, downstream: set):
    for t, r in disc.iterrows():
        bars = prices.get(t)
        asof_pub = s(r["bar_data_asof"])[:10]
        if bars is None or bars.empty:
            rec.add(t, "discovery", "bar_data_asof", "U01_BARS_CURRENT", "NOT_EVALUABLE", asof_pub, None,
                    "ticker has no bars in historical_prices.sqlite")
            continue
        db_last = bars["trading_date"].iloc[-1]
        ok_current = asof_pub == session.isoformat()
        if ok_current:
            rec.add(t, "discovery", "bar_data_asof", "U01_BARS_CURRENT", "PASS", asof_pub, session.isoformat())
        else:
            # Stale discovery rows are a defect only if they reach options or later stages.
            leaked = t in downstream
            rec.add(t, "discovery", "bar_data_asof", "U01_BARS_CURRENT", "FAIL" if leaked else "INFO",
                    asof_pub, session.isoformat(),
                    f"signal built on bars ending {asof_pub}; DB last bar {db_last}; "
                    + ("PROPAGATED downstream" if leaked else "contained: dropped before options"))
        if not ok_current and s(r["is_stale"]).lower() != "true":
            rec.add(t, "discovery", "is_stale", "U02_STALE_FLAG_HONEST", "FAIL", r["is_stale"], True,
                    "stale bars not flagged is_stale")
        if not ok_current:
            continue  # indicators on stale frames are not comparable to the canonical history
        # Recompute on the bars the signal claims to use
        used = bars[bars["trading_date"] <= asof_pub] if asof_pub else bars
        if len(used) < 20:
            rec.add(t, "discovery", "stock_price", "U03_CLOSE_MATCH", "NOT_EVALUABLE", r["stock_price"], None,
                    f"only {len(used)} bars available up to {asof_pub}")
            continue
        ind = indicator_recompute(used)
        rec.compare(t, "discovery", "stock_price", "U03_CLOSE_MATCH", r["stock_price"], ind["close"], TOL_PRICE)
        sess_bar = bars[bars["trading_date"] == session.isoformat()]
        if len(sess_bar):
            rec.compare(t, "discovery", "stock_price", "U04_PRICE_IS_SESSION_CLOSE", r["stock_price"],
                        float(sess_bar["close"].iloc[0]), TOL_PRICE,
                        reason=f"published price is not the {session} close")
        atr_tol = max(TOL_ATR_REL * abs(ind["atr14"] or 0), 0.0051)  # ATR_14 is published at 2 dp
        rec.compare(t, "discovery", "ATR_14", "U05_ATR14", r["ATR_14"], ind["atr14"], atr_tol)
        rec.compare(t, "discovery", "atr_pct", "U06_ATR_PCT", r["atr_pct"], ind["atr_pct"], TOL_PCT)
        rec.compare(t, "discovery", "gap_pct", "U07_GAP_PCT", r["gap_pct"], ind["gap_pct"], TOL_PCT)
        rec.compare(t, "discovery", "range_pct", "U08_RANGE_PCT", r["range_pct"], ind["range_pct"], TOL_PCT)
        rec.compare(t, "discovery", "adx_14", "U09_ADX14", r["adx_14"], ind["adx"], TOL_ADX)


def check_geometry(rec: Recorder, t: str, stage: str, direction: str, spot, inv, tgt, atr, rr_pub=None,
                   require_target: bool = False):
    spot, inv, tgt, atr = f(spot), f(inv), f(tgt), f(atr)
    if direction not in DIRECTIONAL:
        return
    if spot is None:
        rec.add(t, stage, "spot", "G00_SPOT_PRESENT", "FAIL", None, None, "no spot price")
        return
    if inv is None:
        rec.add(t, stage, "invalidation", "G01_INVALIDATION_PRESENT", "FAIL", None, None,
                f"{direction} candidate has no invalidation level")
    else:
        ok = inv < spot if direction == "CALL" else inv > spot
        rec.add(t, stage, "invalidation", "G02_INVALIDATION_SIDE", "PASS" if ok else "FAIL", inv, spot,
                "" if ok else f"{direction} invalidation on wrong side of spot")
        if atr:
            dist = abs(spot - inv) / atr
            ok = 0.25 <= dist <= 8
            rec.add(t, stage, "invalidation", "G03_INVALIDATION_DISTANCE_ATR", "PASS" if ok else "WARN",
                    round(dist, 2), "0.25-8 ATR", "" if ok else f"invalidation {dist:.1f} ATR from spot")
    if tgt is None:
        rec.add(t, stage, "target", "G04_TARGET_PRESENT", "FAIL" if require_target else "WARN", None, None,
                f"{direction} candidate has no target")
    else:
        if tgt <= 0:
            rec.add(t, stage, "target", "G05_TARGET_POSITIVE", "FAIL", tgt, ">0", "target price is not positive")
        else:
            rec.add(t, stage, "target", "G05_TARGET_POSITIVE", "PASS", tgt, ">0")
        ok = tgt > spot if direction == "CALL" else tgt < spot
        rec.add(t, stage, "target", "G06_TARGET_SIDE", "PASS" if ok else "FAIL", tgt, spot,
                "" if ok else f"{direction} target on wrong side of spot")
        if atr and tgt > 0:
            dist = abs(tgt - spot) / atr
            ok = dist <= 15
            rec.add(t, stage, "target", "G07_TARGET_DISTANCE_ATR", "PASS" if ok else "WARN", round(dist, 2),
                    "<=15 ATR", "" if ok else f"target {dist:.1f} ATR from spot")
    if rr_pub is not None and inv is not None and tgt is not None and abs(spot - inv) > 0:
        rr = abs(tgt - spot) / abs(spot - inv)
        rec.compare(t, stage, "rr_underlying", "G08_RR_RECOMPUTE", rr_pub, rr, TOL_RR)


def check_cross_stage(rec: Recorder, t: str, field: str, check_id: str, values: list[tuple[str, object]], tol):
    present = [(stg, f(v)) for stg, v in values if f(v) is not None]
    for stg, v in values:
        if f(v) == 0.0:
            rec.add(t, stg, field, "Z01_ZERO_AS_MISSING", "FAIL", 0.0, None,
                    f"{field} published as 0.0 (missing value disguised as a price)")
    nonzero = [(stg, v) for stg, v in present if v != 0.0]
    if len(nonzero) < 2:
        return
    ref_stage, ref = nonzero[0]
    for stg, v in nonzero[1:]:
        ok = abs(v - ref) <= tol
        rec.add(t, stg, field, check_id, "PASS" if ok else "FAIL", v, ref,
                "" if ok else f"{stg} disagrees with {ref_stage}")


def check_contract(rec: Recorder, t: str, stage: str, row: dict, raw: dict | None, session: date,
                   direction: str, spot, eod_status: str):
    sym = s(row.get("contract_symbol")).upper()
    occ = parse_occ(sym)
    if not occ:
        return
    strike, expiry_pub = f(row.get("strike")), s(row.get("expiry"))[:10]
    rec.compare(t, stage, "strike", "C01_STRIKE_MATCHES_SYMBOL", strike, occ["strike"], 0.0005)
    ok = expiry_pub == occ["expiry"].isoformat()
    rec.add(t, stage, "expiry", "C02_EXPIRY_MATCHES_SYMBOL", "PASS" if ok else "FAIL", expiry_pub,
            occ["expiry"].isoformat(), "" if ok else "expiry field disagrees with contract symbol")
    if direction in DIRECTIONAL:
        ok = occ["right"] == direction
        rec.add(t, stage, "contract_symbol", "C03_SIDE_MATCHES_DIRECTION", "PASS" if ok else "FAIL", occ["right"],
                direction, "" if ok else "contract right is opposite to the published direction")
    cal = (occ["expiry"] - session).days
    rec.compare(t, stage, "dte", "C04_CALENDAR_DTE", row.get("dte"), cal, 0.5)
    rec.compare(t, stage, "contract_dte", "C05_SESSION_DTE", row.get("contract_dte"),
                sessions_after(session, occ["expiry"]), 0.5)

    bid, ask, mid = f(row.get("contract_bid")), f(row.get("contract_ask")), f(row.get("contract_mid"))
    if bid is not None and ask is not None and ask > 0 and bid >= 0 and ask >= bid:
        m = (bid + ask) / 2
        frac = (ask - bid) / m if m > 0 else None
        rec.compare(t, stage, "contract_mid", "C06_MID_RECOMPUTE", mid, m, TOL_OPT)
        for fld in ("contract_spread_pct", "execution_viability_spread_fraction_mid", "spread_fraction_mid"):
            if fld in row:
                rec.compare(t, stage, fld, "C07_SPREAD_FRACTION", row.get(fld), frac, TOL_SPREAD_FRAC)
        for fld in ("execution_viability_spread_pct", "spread_pct", "spread_pct_of_mid"):
            if fld in row:
                rec.compare(t, stage, fld, "C08_SPREAD_PERCENT", row.get(fld),
                            frac * 100 if frac is not None else None, TOL_SPREAD_FRAC * 100)
        if frac is not None and eod_status in READY_STATUSES:
            ok = frac <= 0.5
            rec.add(t, stage, "spread", "T01_READY_BUT_UNTRADEABLE_SPREAD", "PASS" if ok else "WARN",
                    round(frac, 4), "<=0.50", "" if ok else f"{eod_status} with {frac:.0%} spread")
        if bid == 0 and eod_status in READY_STATUSES:
            rec.add(t, stage, "contract_bid", "T02_READY_WITH_ZERO_BID", "WARN", 0.0, ">0",
                    f"{eod_status} contract has no bid")
    elif ask is not None and bid is not None and ask < bid:
        rec.add(t, stage, "contract_ask", "C09_CROSSED_QUOTE", "FAIL", ask, bid, "ask below bid")

    iv = f(row.get("contract_iv"))
    if iv is not None:
        ok = 0.02 <= iv <= 3.0
        rec.add(t, stage, "contract_iv", "T03_IV_PLAUSIBLE", "PASS" if ok else "WARN", iv, "0.02-3.0",
                "" if ok else "implausible implied volatility")
    delta = f(row.get("contract_delta"))
    if delta is not None:
        ok = (0 <= delta <= 1) if occ["right"] == "CALL" else (-1 <= delta <= 0)
        rec.add(t, stage, "contract_delta", "C10_DELTA_SIGN", "PASS" if ok else "FAIL", delta, occ["right"],
                "" if ok else "delta sign inconsistent with contract right")

    ts = s(row.get("contract_quote_timestamp_utc") or row.get("selected_quote_timestamp_utc"))
    if ts:
        ok = ts[:10] == session.isoformat()
        rec.add(t, stage, "quote_timestamp", "C11_QUOTE_FROM_SESSION", "PASS" if ok else "FAIL", ts,
                session.isoformat(), "" if ok else "quote is not from the evidence session")

    if raw is None:
        rec.add(t, stage, "contract_symbol", "R00_CONTRACT_IN_RAW_CHAIN", "FAIL", sym, None,
                "selected contract not found in the raw chain observation for the session")
        return
    rec.add(t, stage, "contract_symbol", "R00_CONTRACT_IN_RAW_CHAIN", "PASS", sym, sym)
    rec.compare(t, stage, "contract_bid", "R01_BID_MATCHES_RAW", bid, raw.get("bid"), TOL_OPT)
    rec.compare(t, stage, "contract_ask", "R02_ASK_MATCHES_RAW", ask, raw.get("ask"), TOL_OPT)
    rec.compare(t, stage, "contract_iv", "R03_IV_MATCHES_RAW", iv, raw.get("implied_vol"), TOL_IV)
    # Delta: the pipeline may replace provider delta with a model delta. Arbitrate against an
    # independent Black-Scholes delta built from the provider IV; fail only when the published
    # delta is materially wrong AND the provider delta is the better estimate.
    rdelta, riv = f(raw.get("delta")), f(raw.get("implied_vol"))
    bs = bs_delta(f(spot), occ["strike"], (occ["expiry"] - session).days, riv, occ["right"])
    if delta is None or bs is None:
        rec.add(t, stage, "contract_delta", "R04_DELTA_VS_INDEPENDENT_BS", "NOT_EVALUABLE", delta, bs,
                "delta or BS inputs unavailable")
    else:
        err_pub = abs(delta - bs)
        err_raw = abs(rdelta - bs) if rdelta is not None else float("inf")
        if err_pub <= 0.05:
            status, why = "PASS", ""
        elif err_pub > 0.10 and err_raw < err_pub:
            status, why = "FAIL", f"published delta off by {err_pub:.2f} vs BS; provider delta {rdelta} off by {err_raw:.2f}"
        else:
            status, why = "WARN", f"published delta off by {err_pub:.2f} vs BS"
        rec.add(t, stage, "contract_delta", "R04_DELTA_VS_INDEPENDENT_BS", status, delta, round(bs, 4), why)
    if riv is not None and riv <= 0.001:
        rec.add(t, stage, "contract_iv", "R05_RAW_IV_PLACEHOLDER", "WARN", riv, ">0.001",
                "provider IV is a placeholder; greeks are unreliable")
    uspot = f(raw.get("underlying_price"))
    if uspot and f(spot):
        diff = abs(uspot - f(spot)) / f(spot)
        ok = diff <= 0.01
        rec.add(t, stage, "spot", "R06_SPOT_MATCHES_CHAIN_UNDERLYING", "PASS" if ok else "WARN", f(spot), uspot,
                "" if ok else f"signal spot differs from chain underlying by {diff:.1%}")


# ─────────────────────────────── main ───────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--golden-size", type=int, default=30)
    args = ap.parse_args()
    run_id = args.run_id
    run_dir = REPO / "data" / "output" / "runs" / run_id
    out_dir = REPO / "audit" / "signal_accuracy" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((run_dir / "final_run_manifest.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    cutoff = manifest.get("created_at_utc") or datetime.utcnow().isoformat()
    run_date = datetime.strptime(run_id[:8], "%Y%m%d").date()
    session = last_completed_session(run_date)

    disc = read_csv(run_dir / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv", [
        "ticker", "tier", "stock_price", "entry_price", "bar_data_asof", "is_stale", "data_source", "ATR_14",
        "atr_pct", "gap_pct", "range_pct", "adx_14", "direction", "governed_invalidation_spot",
        "governed_invalidation_source", "structural_stop", "structural_target", "structural_target_source",
        "rr_underlying"])
    opts = read_csv(run_dir / "options" / f"options_intelligence_{run_id}.csv", [
        "ticker", "entry_spot", "underlying_price", "target_spot", "structural_target", "invalidation_spot",
        "invalidation_source", "canonical_direction", "contract_strike", "contract_expiry", "contract_dte",
        "contract_bid", "contract_ask", "contract_mid", "contract_spread_pct", "contract_iv", "contract_delta",
        "contract_quote_timestamp_utc", "selected_quote_dataset_id", "rr_underlying"])
    morn = read_csv(run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv", [
        "ticker", "final_direction", "signal_price", "target_price", "invalidation_spot", "invalidation_level",
        "exit_invalidation_price", "contract_symbol", "strike", "expiry", "dte", "contract_dte", "contract_bid",
        "contract_ask", "contract_mid", "contract_spread_pct", "contract_iv", "contract_delta",
        "execution_viability_spread_pct", "execution_viability_spread_fraction_mid",
        "selected_quote_timestamp_utc", "eod_candidate_status", "atr_14"])
    lab = read_csv(run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv", [
        "ticker", "tier", "final_direction", "underlying_price", "signal_price", "target_price",
        "structural_target", "invalidation_price", "contract_symbol", "strike", "expiry", "dte", "contract_dte",
        "contract_bid", "contract_ask", "contract_mid", "spread_pct", "spread_pct_of_mid", "spread_fraction_mid",
        "contract_iv", "contract_delta", "selected_quote_timestamp_utc", "lab_status", "opportunity_tier"])

    rec = Recorder(run_id)
    tickers = sorted(set(disc.index) | set(opts.index))
    print(f"[audit] run {run_id} session {session} tickers {len(tickers)} cutoff {cutoff}")

    prices = load_prices(tickers, session, cutoff)
    print(f"[audit] loaded bars for {len(prices)} tickers")
    check_underlying(rec, disc, prices, session, downstream=set(opts.index))

    # Raw chain lookup for every selected contract
    wanted: dict[str, set] = defaultdict(set)
    for frame in (morn, lab):
        for t, sym in frame["contract_symbol"].items():
            if parse_occ(sym):
                wanted[t].add(s(sym).upper())
    ds_ids = {t: s(v) for t, v in opts["selected_quote_dataset_id"].items() if s(v)}
    raw_quotes, raw_src = load_chain_quotes(wanted, session, ds_ids)
    print(f"[audit] raw chain quotes matched {len(raw_quotes)} of {sum(len(v) for v in wanted.values())}")

    for t in opts.index:
        o = opts.loc[t]
        m = morn.loc[t] if t in morn.index else None
        l = lab.loc[t] if t in lab.index else None
        d = disc.loc[t] if t in disc.index else None
        direction = s(o["canonical_direction"]).upper()
        bars = prices.get(t)
        atr = None
        if bars is not None and len(bars) >= 15:
            atr = indicator_recompute(bars[bars["trading_date"] <= session.isoformat()])["atr14"]
        eod_status = s(m["eod_candidate_status"]) if m is not None else ""
        ready = eod_status in READY_STATUSES

        # Direction continuity
        if d is not None:
            dd = s(d["direction"]).upper()
            if dd and dd != direction:
                rec.add(t, "options", "direction", "X01_DIRECTION_CHANGED_AFTER_DISCOVERY", "INFO", direction, dd,
                        "governed arbitration changed discovery direction")
        for stg, frame_row, col in (("morning", m, "final_direction"), ("lab", l, "final_direction")):
            if frame_row is not None:
                v = s(frame_row[col]).upper()
                ok = v == direction
                rec.add(t, stg, "direction", "X02_DIRECTION_CONSISTENT", "PASS" if ok else "FAIL", v, direction,
                        "" if ok else "direction changed between options and downstream stage")

        # Cross-stage level consistency (+ zero-as-missing)
        check_cross_stage(rec, t, "spot", "X03_SPOT_CONSISTENT", [
            ("discovery", d["stock_price"] if d is not None else None), ("options", o["entry_spot"]),
            ("morning", m["signal_price"] if m is not None else None),
            ("lab", l["underlying_price"] if l is not None else None)], TOL_PRICE)
        check_cross_stage(rec, t, "invalidation", "X04_INVALIDATION_CONSISTENT", [
            ("discovery", d["governed_invalidation_spot"] if d is not None else None),
            ("options", o["invalidation_spot"]),
            ("morning", m["invalidation_spot"] if m is not None else None),
            ("morning.exit_invalidation_price", m["exit_invalidation_price"] if m is not None else None),
            ("lab", l["invalidation_price"] if l is not None else None)], TOL_LEVEL)
        check_cross_stage(rec, t, "target", "X05_TARGET_CONSISTENT", [
            ("options", o["target_spot"]), ("morning", m["target_price"] if m is not None else None),
            ("lab", l["target_price"] if l is not None else None)], TOL_LEVEL)
        if m is not None and l is not None:
            ms, ls_ = s(m["contract_symbol"]).upper(), s(l["contract_symbol"]).upper()
            if ms or ls_:
                ok = ms == ls_
                rec.add(t, "lab", "contract_symbol", "X06_CONTRACT_CONSISTENT", "PASS" if ok else "FAIL", ls_, ms,
                        "" if ok else "lab shows a different contract from morning candidates")
            for fld in ("strike", "contract_ask", "contract_mid"):
                vals = [("morning", m[fld]), ("lab", l[fld])]
                if fld == "strike":
                    vals.insert(0, ("options", o["contract_strike"]))
                else:
                    vals.insert(0, ("options", o[fld]))
                check_cross_stage(rec, t, fld, "X07_CONTRACT_FIELDS_CONSISTENT", vals, TOL_OPT)

        # Geometry on the options stage (authoritative thesis) and the Lab book (what the user sees)
        check_geometry(rec, t, "options", direction, o["entry_spot"], o["invalidation_spot"], o["target_spot"],
                       atr, rr_pub=f(o["rr_underlying"]), require_target=ready)
        if l is not None:
            check_geometry(rec, t, "lab", s(l["final_direction"]).upper(), l["underlying_price"],
                           l["invalidation_price"], l["target_price"], atr, require_target=ready)

        # Contract vs raw chain
        for stg, frame_row in (("morning", m), ("lab", l)):
            if frame_row is None:
                continue
            row = frame_row.to_dict()
            if stg == "morning":
                row["contract_quote_timestamp_utc"] = row.get("selected_quote_timestamp_utc")
            sym = s(row.get("contract_symbol")).upper()
            check_contract(rec, t, stg, row, raw_quotes.get(sym), session, direction,
                           o["entry_spot"], eod_status)

    checks = pd.DataFrame(rec.rows)

    # Scope tags
    actionable = set(morn.index[morn["eod_candidate_status"] == "EOD_TRIGGER_READY"])
    tier_ab = set(lab.index[lab["tier"].astype(str).str.upper().isin(["A", "B"])])
    checks["scope_trigger_ready"] = checks["ticker"].isin(actionable)
    checks["scope_tier_ab"] = checks["ticker"].isin(tier_ab)
    checks.to_csv(out_dir / "checks.csv", index=False)

    def summarise(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        g = frame.pivot_table(index=keys, columns="status", values="ticker", aggfunc="count", fill_value=0)
        for c in ("PASS", "FAIL", "WARN", "NOT_EVALUABLE", "INFO"):
            if c not in g.columns:
                g[c] = 0
        g["evaluated"] = g["PASS"] + g["FAIL"] + g["WARN"]
        g["fail_rate"] = (g["FAIL"] / g["evaluated"].replace(0, np.nan)).round(4)
        g["warn_rate"] = (g["WARN"] / g["evaluated"].replace(0, np.nan)).round(4)
        return g.reset_index().sort_values(["fail_rate", "FAIL"], ascending=False)

    by_check = summarise(checks, ["check_id"])
    by_check_stage = summarise(checks, ["stage", "field", "check_id"])
    by_check_ready = summarise(checks[checks["scope_trigger_ready"]], ["check_id"])
    by_check.to_csv(out_dir / "summary_by_check.csv", index=False)
    by_check_stage.to_csv(out_dir / "summary_by_stage_field.csv", index=False)
    by_check_ready.to_csv(out_dir / "summary_by_check_trigger_ready.csv", index=False)

    samples = (checks[checks["status"].isin(["FAIL", "WARN"])]
               .groupby("check_id")["ticker"].apply(lambda x: ",".join(sorted(set(x))[:12])).to_dict())
    reasons = (checks[checks["status"].isin(["FAIL", "WARN"])]
               .groupby("check_id")["reason"].agg(lambda x: x.value_counts().index[0]).to_dict())

    # Tickers with no failures at all among directional, contract-bearing rows
    fail_tickers = set(checks.loc[checks["status"] == "FAIL", "ticker"])
    directional = set(opts.index[opts["canonical_direction"].isin(list(DIRECTIONAL))])
    with_contract = set(morn.index[morn["contract_symbol"].map(lambda v: parse_occ(v) is not None)])
    clean = sorted((directional & with_contract) - fail_tickers)
    clean_ready = sorted(set(clean) & actionable)

    # Golden reference: stratified sample of recomputed truth
    rng = np.random.default_rng(20260915)
    pool = sorted(directional & with_contract & set(prices))
    strata = defaultdict(list)
    for t in pool:
        strata[(s(opts.loc[t, "canonical_direction"]), t in actionable)].append(t)
    golden = []
    per = max(1, args.golden_size // max(len(strata), 1))
    for key in sorted(strata):
        members = strata[key]
        golden += list(rng.choice(members, size=min(per, len(members)), replace=False))
    grows = []
    for t in sorted(golden):
        bars = prices[t]
        ind = indicator_recompute(bars[bars["trading_date"] <= session.isoformat()])
        sym = s(morn.loc[t, "contract_symbol"]).upper()
        occ = parse_occ(sym)
        raw = raw_quotes.get(sym) or {}
        rb, ra = f(raw.get("bid")), f(raw.get("ask"))
        grows.append({
            "run_id": run_id, "session": session.isoformat(), "ticker": t,
            "direction": s(opts.loc[t, "canonical_direction"]), "eod_candidate_status": s(morn.loc[t, "eod_candidate_status"]),
            "close": round(ind["close"], 4), "atr14": round(ind["atr14"], 4) if ind["atr14"] else None,
            "atr_pct": round(ind["atr_pct"], 4) if ind["atr_pct"] else None,
            "gap_pct": round(ind["gap_pct"], 4) if ind["gap_pct"] is not None else None,
            "range_pct": round(ind["range_pct"], 4) if ind["range_pct"] is not None else None,
            "adx14": round(ind["adx"], 3) if ind["adx"] else None,
            "published_invalidation": f(opts.loc[t, "invalidation_spot"]),
            "published_target": f(opts.loc[t, "target_spot"]),
            "contract_symbol": sym, "strike": occ["strike"], "expiry": occ["expiry"].isoformat(),
            "calendar_dte": (occ["expiry"] - session).days, "session_dte": sessions_after(session, occ["expiry"]),
            "raw_bid": rb, "raw_ask": ra, "raw_mid": round((rb + ra) / 2, 4) if rb is not None and ra is not None else None,
            "raw_spread_fraction": round((ra - rb) / ((ra + rb) / 2), 6) if rb is not None and ra and (ra + rb) > 0 else None,
            "raw_iv": f(raw.get("implied_vol")), "raw_delta": f(raw.get("delta")),
            "raw_chain_file": raw_src.get(sym, ""),
            "has_any_fail": t in fail_tickers,
        })
    pd.DataFrame(grows).to_csv(out_dir / "golden_reference.csv", index=False)

    summary = {
        "run_id": run_id, "session": session.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_git_describe": run_meta.get("git_describe"), "price_cutoff_utc": cutoff,
        "tickers_discovery": int(len(disc)), "tickers_options": int(len(opts)),
        "directional_with_contract": int(len(directional & with_contract)),
        "trigger_ready": int(len(actionable)),
        "checks_total": int(len(checks)),
        "status_counts": checks["status"].value_counts().to_dict(),
        "tickers_with_any_fail": int(len(fail_tickers)),
        "clean_directional_contract_tickers": len(clean),
        "clean_trigger_ready_tickers": len(clean_ready),
        "clean_trigger_ready_list": clean_ready,
        "raw_contracts_matched": len(raw_quotes),
        "by_check": [
            {**{k: (int(v) if isinstance(v, (np.integer,)) else (None if isinstance(v, float) and math.isnan(v) else v))
                for k, v in r.items()},
             "example_reason": reasons.get(r["check_id"], ""), "sample_tickers": samples.get(r["check_id"], "")}
            for r in by_check.to_dict("records")
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # Markdown report
    lines = [
        f"# Signal accuracy audit — run {run_id}",
        "",
        f"Session {session} · code `{run_meta.get('git_describe')}` · generated {summary['generated_utc']}",
        "",
        "Each published field was recomputed independently from raw inputs "
        "(point-in-time OHLCV in `historical_prices.sqlite`, raw MarketData chain observations) "
        "and compared across stages. Read-only; nothing in the pipeline was modified.",
        "",
        "## Headline",
        "",
        f"- Tickers: discovery {len(disc)}, options {len(opts)}, directional with a contract {len(directional & with_contract)}, trigger-ready {len(actionable)}",
        f"- Checks run: {len(checks):,} → " + ", ".join(f"{k} {v:,}" for k, v in summary["status_counts"].items()),
        f"- Tickers with at least one FAIL: {len(fail_tickers)}",
        f"- **Clean** directional candidates with a contract (zero FAILs): **{len(clean)}**; of which trigger-ready: **{len(clean_ready)}**",
        "",
        "## Checks ranked by failure rate",
        "",
        "| Check | Evaluated | FAIL | WARN | Fail rate | Typical reason | Sample tickers |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for r in by_check.to_dict("records"):
        if r["evaluated"] == 0 and r["NOT_EVALUABLE"] == 0:
            continue
        fr = "" if pd.isna(r["fail_rate"]) else f"{r['fail_rate']:.1%}"
        lines.append(f"| {r['check_id']} | {r['evaluated']} | {r['FAIL']} | {r['WARN']} | {fr} | "
                     f"{reasons.get(r['check_id'], '')} | {samples.get(r['check_id'], '')} |")
    lines += ["", "## Trigger-ready candidates only", "",
              "| Check | Evaluated | FAIL | WARN | Fail rate |", "|---|---:|---:|---:|---:|"]
    for r in by_check_ready.to_dict("records"):
        if r["FAIL"] or r["WARN"]:
            fr = "" if pd.isna(r["fail_rate"]) else f"{r['fail_rate']:.1%}"
            lines.append(f"| {r['check_id']} | {r['evaluated']} | {r['FAIL']} | {r['WARN']} | {fr} |")
    lines += ["", "## Files", "",
              "- `checks.csv` — one row per check (ticker, stage, field, published, recomputed, status, reason)",
              "- `summary_by_check.csv`, `summary_by_stage_field.csv`, `summary_by_check_trigger_ready.csv`",
              "- `golden_reference.csv` — stratified sample of independently recomputed values, reusable as a regression reference",
              "- `summary.json` — machine-readable totals and the clean trigger-ready list", ""]
    (out_dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[audit] wrote {out_dir}")


if __name__ == "__main__":
    main()
