#!/usr/bin/env python3
"""AVSHUNTER Options Intelligence - standalone research tool, v2.0 (11 Oct 2026).

Reads the opportunity folder (the decision ledger written by the triage), pulls each ticker's option chain once,
and writes factual option intelligence for every thesis. Nothing here trades, ranks by an opaque score, or claims a
win rate. Every snapshot is kept, so the files build a dated history for the data-mining work.

Run (Windows, repo venv, from the repo root):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\avshunter_options_standalone.py
    ... --ledger data\\scratch\\workaround\\decision_ledger_2026-10-12.csv --all      (every active thesis, not only focus)
    ... --tickers FRO DASH APH                                                      (only these tickers from the ledger)
    ... --wait-pipeline-options --workers 2      (parallel running: start fetching only after the evening pipeline's own
                                                  options stage has finished, so the two never call MarketData at once)
    ... --reuse-phantom --wait-pipeline-done --workers 2
                                                 (reuse the chains the evening run already fetched: read them from Phantom
                                                  for the evidence session, read-only; call MarketData only for names Phantom
                                                  does not have, or has too thin to judge - see PHANTOM_MIN_* below)
    ... --max-premium 3                           (the day's premium cap, per share: contracts at or under it are preferred;
                                                  a thesis with none under it keeps its best contract, flagged OVER_CAP)
Guard rail: --reserve-credits 20000 (default) stops fetching when MarketData reports fewer credits left than this, so
        the pipeline is never starved; the names not fetched are marked SKIPPED_CREDIT_RESERVE.
Colab:  %run avshunter_options_standalone.py --ledger decision_ledger_2026-10-12.csv
Keys:   MARKETDATA_API_KEY (default provider, the pipeline's canonical options source) or POLYGON_API_KEY with
        --provider polygon. Read from the environment or Colab Secrets. Keys are never printed or written.

Output: <out>/<YYYY-MM-DD_HHMM>/   (out defaults to data/scratch/options_intel next to the ledger's folder)
    chain_raw.csv.gz      every contract returned, both sides, with the provider timestamp  (the mining history)
    contracts_thesis.csv  side-correct contracts in the thesis window, with thesis-conditioned measures
    shortlist.csv         up to 3 contracts per thesis by the ordered rule below (not a recommendation)
    expiry_context.csv    per expiry: ATM IV, implied move, put/call OI and volume, OI walls
    thesis_summary.csv    one row per thesis: chain status, coverage, best contract, IV term, walls vs levels
    errors.csv, run_manifest.json

Thesis-conditioned measures (all from the ledger's own levels; Black-Scholes at the contract's own IV, no dividends,
European approximation - context, not a fill price):
    sessions_to_expiry       XNYS-approximate trading sessions from the as-of date (weekdays minus US holidays)
    covers_q50 / covers_q80  expiry leaves the median / planned-hold sessions plus the exit buffer
    breakeven_move_pct       move needed at expiry to recover the ask
    value_at_half_target_q50, value_at_level_q50, value_at_invalidation_q50
                             model value with the stock at that price after q50 sessions, less half the spread
    ret_half_target_q50 etc. that value / ask - 1
    intrinsic_share          intrinsic value / ask now
Shortlist rule (ordered, no weights): expiry >= 14 calendar days (7-13 only when it covers q50 and the move is at
least 1.5x the implied move, flagged); strike in the money at the level (call K <= level, put K >= level) and no more
than 5 strikes in the money; then pays at the half target by q50 > first expiry covering q80 > tighter spread class >
nearer the money.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# G5 (ACK 17 Oct 2026, D1): the contracts the shortlist chooses from are priced by the pipeline's one engine
# (domain/option_valuation.option_value: American tree, the ticker's dividend, the run's observed rate). If the repo
# modules cannot be imported, the tool still runs on its old European basis and every row says so.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
try:
    from domain.option_valuation import (american_crr_values, european_bsm_value, exercise_style, resolve_rate,
                                         valuation_policy)
    from canonical_data.dividend_history import dividend_inputs
    from canonical_data.market_rate_observation import rate_inputs
    SHARED_PRICING = True
    SHARED_PRICING_ERROR = ""
except Exception as _exc:  # noqa: BLE001 - stated on every row, never silent
    SHARED_PRICING = False
    SHARED_PRICING_ERROR = f"{type(_exc).__name__}: {_exc}"

VERSION = "avshunter_options_standalone_v2.8"
EXIT_BUFFER_SESSIONS = 2
MIN_DTE = 14
EXCEPTION_MIN_DTE = 7
EXCEPTION_MULTIPLE = 1.5
MAX_ITM_STRIKES = 5
MAX_MONEYNESS = 0.15   # strike within 15% of spot: stops deep in-the-money picks on low-priced names
SPREAD_CLASSES = [0.05, 0.10, 0.18, 0.25]
RATE = 0.042          # European context value only; decision values use PRICING (the run's observed rate)
PRICING = {"rate": None, "rate_basis": "RATE_UNAVAILABLE:NOT_SET"}   # set in main() from the ledger's source run
EUROPEAN_CONTEXT = "EUROPEAN_BS_NO_DIVIDEND_CONTEXT"
US_HOLIDAYS = {"2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-04-02",
               "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
DIRECTION = {"CALL": "CALL", "LONG_CALL": "CALL", "BUY_CALL": "CALL", "C": "CALL", "UP": "CALL", "BULL": "CALL",
             "PUT": "PUT", "LONG_PUT": "PUT", "BUY_PUT": "PUT", "P": "PUT", "DOWN": "PUT", "BEAR": "PUT"}


# ---------------------------------------------------------------- inputs
def find_ledger(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    hits = sorted(h for h in glob.glob(str(Path("data") / "scratch" / "workaround" / "decision_ledger_*.csv"))
                  if not h.endswith(("_outcomes.csv", "_summary.csv")))  # the outcome tracker writes decision_ledger_<date>_outcomes.csv
    if not hits:
        raise SystemExit("No ledger found: pass --ledger path\\to\\decision_ledger_YYYY-MM-DD.csv")
    return Path(hits[-1])


def load_ledger(path: Path, all_rows: bool, tickers: list[str] | None) -> pd.DataFrame:
    d = pd.read_csv(path)
    d.columns = [c.strip().lower() for c in d.columns]
    if "side" not in d and "direction" in d:
        d["side"] = d["direction"]
    d["side"] = d["side"].astype(str).str.upper().map(DIRECTION)
    d["ticker"] = d["ticker"].astype(str).str.upper().str.strip()
    if not all_rows and "focus_v3" in d:
        d = d[d["focus_v3"].astype(str).str.upper() == "TRUE"]
    if tickers:
        d = d[d["ticker"].isin([t.upper() for t in tickers])]
    d = d[d["side"].notna()].copy()
    for c in ["entry_ref", "half_target", "level", "invalidation", "q50_sessions", "q80_sessions", "ref_price"]:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    if "ledger_id" not in d:
        d["ledger_id"] = d["ticker"] + "_" + d["side"]
    return d


def get_key(name: str) -> str:
    try:
        from google.colab import userdata  # type: ignore
        v = userdata.get(name)
        if v:
            return v.strip()
    except Exception:
        pass
    return os.environ.get(name, "").strip()


# ---------------------------------------------------------------- reuse of the evening run's chains (Phantom)
PHANTOM_DB = Path("data") / "phantom" / "phantom_history.db"
PHANTOM_MIN_USABLE = 10          # fewer two-sided contracts than this: treat as missing and fetch
PHANTOM_MIN_EXPIRIES = 2         # fewer expiries than this: fetch


def read_phantom(path: Path, ticker: str, session: str) -> pd.DataFrame:
    """One ticker's chain for one session from Phantom chain_snapshots, read-only, in the tool's raw-chain format."""
    import sqlite3
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=60) as con:
        d = pd.read_sql_query(
            "SELECT option_symbol, side, strike, expiration_ts, underlying_price, bid, ask, iv, delta, gamma, theta, vega, "
            "open_interest, volume, updated_ts, source FROM chain_snapshots WHERE ticker=? AND quote_date=?",
            con, params=(ticker, session))
    if d.empty:
        return pd.DataFrame()
    occ = d.option_symbol.astype(str).str.replace(" ", "").str.extract(r"(\d{6})([CP])(\d{8})$")
    exp_occ = pd.to_datetime(occ[0], format="%y%m%d", errors="coerce").dt.date.astype(str)   # expiry from the OCC symbol
    exp_ts = pd.to_datetime(d.expiration_ts, unit="s", utc=True, errors="coerce").dt.date.astype(str)
    return pd.DataFrame({
        "contract": d.option_symbol, "right": d.side.astype(str).str[:1].str.upper(), "strike": d.strike,
        "expiry": exp_occ.where(occ[0].notna(), exp_ts), "spot": d.underlying_price,
        "bid": d.bid, "ask": d.ask, "iv": d.iv, "delta": d.delta, "gamma": d.gamma, "theta": d.theta, "vega": d.vega,
        "oi": d.open_interest, "volume": d.volume,
        "quote_time_utc": pd.to_datetime(d.updated_ts, unit="s", utc=True).astype(str), "phantom_source": d.source})


def phantom_enough(raw: pd.DataFrame, need_sessions: float, as_of: date) -> tuple[bool, str]:
    """Is the stored chain good enough to judge the thesis without a fresh fetch?"""
    if raw.empty:
        return False, "PHANTOM_MISSING"
    b, a = pd.to_numeric(raw.bid, errors="coerce"), pd.to_numeric(raw.ask, errors="coerce")
    usable = int(((b > 0) & (a >= b)).sum())
    exps = pd.to_datetime(raw.expiry, errors="coerce").dropna().dt.date.unique()
    if usable < PHANTOM_MIN_USABLE or len(exps) < PHANTOM_MIN_EXPIRIES:
        return False, f"PHANTOM_THIN ({usable} two-sided, {len(exps)} expiries)"
    furthest = max(sessions_between(as_of, e) for e in exps)
    if pd.notna(need_sessions) and furthest < need_sessions:
        return False, f"PHANTOM_SHORT (furthest expiry {furthest} sessions, thesis needs {int(need_sessions)})"
    return True, "PHANTOM_OK"


def wait_for_pipeline_done(ledger: pd.DataFrame, hours: float) -> None:
    """Wait until the evening run named in the ledger has written its final manifest (Phantom delivery is done by then)."""
    runs = ledger["source_run"].dropna().astype(str).unique() if "source_run" in ledger else []
    if len(runs) != 1:
        raise SystemExit("--wait-pipeline-done needs a ledger from build_thesis_ledger.py (one source_run)")
    rid = runs[0]
    mark = Path("data") / "output" / "runs" / rid / "final_run_manifest.json"
    deadline = time.time() + hours * 3600
    print(f"waiting for run {rid} to finish (final_run_manifest.json) ...")
    while not mark.exists():
        if time.time() > deadline:
            raise SystemExit(f"gave up after {hours}h: run {rid} has not finished")
        time.sleep(60)
    time.sleep(120)
    print(f"evening run finished; starting at {datetime.now().strftime('%H:%M:%S')}")


# ---------------------------------------------------------------- guard rails
CREDITS = {"remaining_min": None, "stopped": False, "reserve": 20000}


def note_credits(r) -> None:
    """Track MarketData's remaining-credits header (if it sends one) and stop before the reserve is reached."""
    v = r.headers.get("X-Api-Ratelimit-Remaining")
    try:
        v = int(float(v))
    except (TypeError, ValueError):
        return
    if CREDITS["remaining_min"] is None or v < CREDITS["remaining_min"]:
        CREDITS["remaining_min"] = v
    if v < CREDITS["reserve"]:
        CREDITS["stopped"] = True


def wait_for_pipeline_options(ledger: pd.DataFrame, hours: float) -> None:
    """Wait until the evening run named in the ledger has finished its own options stage."""
    runs = ledger["source_run"].dropna().astype(str).unique() if "source_run" in ledger else []
    if len(runs) != 1:
        raise SystemExit("--wait-pipeline-options needs a ledger from build_thesis_ledger.py (one source_run)")
    rid = runs[0]
    run = Path("data") / "output" / "runs" / rid
    marks = [run / "diagnostics" / f"station_options_{rid}.json", run / "options" / f"options_intelligence_summary_{rid}.json"]
    deadline = time.time() + hours * 3600
    print(f"waiting for run {rid} to finish its options stage ...")
    while not any(m.exists() for m in marks):
        if time.time() > deadline:
            raise SystemExit(f"gave up after {hours}h: run {rid} has not finished its options stage")
        time.sleep(60)
    time.sleep(60)
    print(f"pipeline options stage finished; starting at {datetime.now().strftime('%H:%M:%S')}")


# ---------------------------------------------------------------- providers
def fetch_marketdata(ticker: str, key: str, to_date: date, session: requests.Session) -> tuple[pd.DataFrame, dict]:
    url = f"https://api.marketdata.app/v1/options/chain/{ticker}/"
    params = {"from": date.today().isoformat(), "to": to_date.isoformat(), "minOpenInterest": 0, "mode": "cached"}
    meta = {"provider": "marketdata", "http_status": None}
    for attempt in range(4):
        r = session.get(url, params=params, headers={"Authorization": f"Token {key}"}, timeout=40)
        meta["http_status"] = r.status_code
        note_credits(r)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 5 * 2 ** attempt))
            continue
        break
    if r.status_code == 404:
        return pd.DataFrame(), {**meta, "status": "NO_OPTIONS_DATA"}
    if not r.ok:
        return pd.DataFrame(), {**meta, "status": f"HTTP_{r.status_code}"}
    data = r.json()
    if data.get("s") != "ok":
        return pd.DataFrame(), {**meta, "status": f"PROVIDER_{data.get('s')}"}
    n = len(data.get("optionSymbol", []))

    def col(k):
        v = data.get(k)
        return v if isinstance(v, list) and len(v) == n else [None] * n

    exp = [datetime.fromtimestamp(int(x), tz=timezone.utc).date().isoformat() if x else None for x in col("expiration")]
    upd = [datetime.fromtimestamp(int(x), tz=timezone.utc).isoformat() if x else None for x in col("updated")]
    df = pd.DataFrame({"contract": col("optionSymbol"), "right": [str(s).lower()[:1].upper() for s in col("side")],
                       "strike": col("strike"), "expiry": exp, "spot": col("underlyingPrice"), "bid": col("bid"),
                       "ask": col("ask"), "iv": col("iv"), "delta": col("delta"), "gamma": col("gamma"),
                       "theta": col("theta"), "vega": col("vega"), "oi": col("openInterest"), "volume": col("volume"),
                       "quote_time_utc": upd})
    meta["freshness"] = "REALTIME" if r.status_code == 200 else ("DELAYED_OR_CACHED" if r.status_code == 203 else "UNKNOWN")
    return df, {**meta, "status": "OK"}


def fetch_polygon(ticker: str, key: str, to_date: date, session: requests.Session) -> tuple[pd.DataFrame, dict]:
    url = f"https://api.polygon.io/v3/snapshot/options/{ticker}"
    params = {"limit": 250, "expiration_date.lte": to_date.isoformat()}
    out, meta = [], {"provider": "polygon"}
    for _ in range(60):
        for attempt in range(4):
            r = session.get(url, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=40)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            break
        meta["http_status"] = r.status_code
        if not r.ok:
            return pd.DataFrame(out), {**meta, "status": f"HTTP_{r.status_code}"}
        payload = r.json()
        for x in payload.get("results") or []:
            det, q, day, g = x.get("details") or {}, x.get("last_quote") or {}, x.get("day") or {}, x.get("greeks") or {}
            out.append({"contract": x.get("ticker"), "right": str(det.get("contract_type", "")).upper()[:1],
                        "strike": det.get("strike_price"), "expiry": det.get("expiration_date"),
                        "spot": (x.get("underlying_asset") or {}).get("price"), "bid": q.get("bid"), "ask": q.get("ask"),
                        "iv": x.get("implied_volatility"), "delta": g.get("delta"), "gamma": g.get("gamma"),
                        "theta": g.get("theta"), "vega": g.get("vega"), "oi": x.get("open_interest"),
                        "volume": day.get("volume"), "quote_time_utc": q.get("last_updated")})
        url, params = payload.get("next_url"), None
        if not url:
            break
    return pd.DataFrame(out), {**meta, "status": "OK" if out else "NO_OPTIONS_DATA"}


# ---------------------------------------------------------------- calendar and model
def sessions_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    days = pd.bdate_range(start + timedelta(days=1), end)
    return int(sum(1 for d in days if d.strftime("%Y-%m-%d") not in US_HOLIDAYS))


def bs_value(spot, strike, years, iv, right):
    spot, strike, years, iv = (np.asarray(x, float) for x in (spot, strike, years, iv))
    intrinsic = np.where(right == "C", np.maximum(spot - strike, 0), np.maximum(strike - spot, 0))
    ok = (years > 0) & (iv > 0) & (spot > 0) & (strike > 0)
    with np.errstate(all="ignore"):
        sq = iv * np.sqrt(np.where(ok, years, 1))
        d1 = (np.log(np.where(ok, spot / strike, 1)) + (RATE + 0.5 * iv ** 2) * np.where(ok, years, 1)) / np.where(ok, sq, 1)
        d2 = d1 - sq
        from math import erf
        N = np.vectorize(lambda x: 0.5 * (1 + erf(x / math.sqrt(2))))
        disc = np.exp(-RATE * np.where(ok, years, 0))
        call = spot * N(d1) - strike * disc * N(d2)
        put = strike * disc * N(-d2) - spot * N(-d1)
    val = np.where(right == "C", call, put)
    return np.where(ok, np.maximum(val, intrinsic), intrinsic)


_DIVIDENDS: dict = {}
AS_OF = date.today()   # the analysis session (set from --as-of in main); replays read the cache as of that day (UAT-07)


def dividend_for(ticker: str, spot: float) -> dict:
    """The ticker's dividend yield from the tastytrade metrics cache as of the analysis session, as the card engine
    reads it (cached per ticker and session, so a later cache never changes a replay)."""
    key = (str(ticker).upper(), AS_OF)
    if key not in _DIVIDENDS:
        _DIVIDENDS[key] = dividend_inputs(key[0], as_of=AS_OF, spot=spot)
    return _DIVIDENDS[key]


def pricing_basis_for_ledger(ledger: pd.DataFrame, runs_dir: Path | None = None) -> dict:
    """The observed rate of the run the ledger was built from (its most common source_run)."""
    runs = REPO_ROOT / "data" / "output" / "runs" if runs_dir is None else Path(runs_dir)
    src = ledger["source_run"].dropna().astype(str) if "source_run" in ledger else pd.Series(dtype=str)
    if src.empty:
        return {"rate": None, "rate_basis": "RATE_UNAVAILABLE:LEDGER_HAS_NO_SOURCE_RUN"}
    return rate_inputs(runs / src.mode().iloc[0])


def shortlist_candidates(x: pd.DataFrame) -> pd.Series:
    """Every row the shortlist can choose from (the rule in shortlist(), as one mask)."""
    if x.empty:
        return pd.Series(False, index=x.index)
    mask = x["in_window"] & x["strike_in_set"] & x["usable"]
    if MAX_PREMIUM is not None:
        mask = mask | (x["in_window"] & x["usable"] & x["strike_itm_at_level"]
                       & ((x["strike"] / x["spot"] - 1).abs() <= 0.25) & (x["ask"] <= MAX_PREMIUM))
    return mask


def american_values(x: pd.DataFrame, t: pd.Series, prices: dict, years: pd.Series, iv: pd.Series) -> pd.DataFrame:
    """G5: re-value the shortlist candidates with the one engine; keep the European values beside them."""
    for name in prices:
        x[f"value_at_{name}_q50_european"] = x[f"value_at_{name}_q50"]
        x[f"ret_{name}_q50_european"] = x[f"ret_{name}_q50"]
    x["pays_at_half_target_q50_european"] = x["pays_at_half_target_q50"]
    x["value_model"] = EUROPEAN_CONTEXT
    if not SHARED_PRICING:
        x["value_model"] = f"{EUROPEAN_CONTEXT}:SHARED_PRICING_UNAVAILABLE"
        return x
    spot = float(x["spot"].median())
    div = dividend_for(t["ticker"], spot)
    q = div.get("dividend_yield") or 0.0
    style = exercise_style(t["ticker"])
    # UAT-06: the rate actually used is published; with no observed rate it is the governed fallback, labelled
    rate, rate_label = resolve_rate(PRICING.get("rate"), PRICING.get("rate_basis"))
    x["value_rate"] = rate
    x["value_rate_basis"] = rate_label
    x["value_dividend_yield"] = q
    x["value_dividend_basis"] = div.get("dividend_basis")
    half_spread = (x["ask"] - x["bid"]) / 2
    cand = x.index[shortlist_candidates(x) & iv.notna()]
    if len(cand):
        is_call = (x.loc[cand, "right"] == "C").to_numpy()
        # an American call on a stock with no dividend is never exercised early: the closed form is exact (and fast)
        european = np.full(len(cand), style == "EUROPEAN") | (is_call & (q <= 0))
        steps = int(valuation_policy()["crr_steps"])
        for name, px in prices.items():
            if px is None or pd.isna(px):
                continue
            val = np.empty(len(cand))
            for j, i in enumerate(cand):
                if european[j]:
                    val[j] = european_bsm_value("CALL" if is_call[j] else "PUT", float(px), float(x.at[i, "strike"]),
                                                float(years.at[i]), float(iv.at[i]), rate=rate, dividend_yield=q)
            tree = ~european
            if tree.any():
                val[tree] = american_crr_values(float(px), x.loc[cand, "strike"].to_numpy()[tree],
                                                years.loc[cand].to_numpy()[tree], rate, q,
                                                iv.loc[cand].to_numpy()[tree], is_call[tree], steps=steps)
            x.loc[cand, f"value_at_{name}_q50"] = np.maximum(val - half_spread.loc[cand].to_numpy(), 0.0)
        x.loc[cand, "value_model"] = np.where(european, "BSM_EUROPEAN", "AMERICAN_CRR")
    for name in prices:
        x[f"ret_{name}_q50"] = x[f"value_at_{name}_q50"] / x["ask"].replace(0, np.nan) - 1
    x["pays_at_half_target_q50"] = x["ret_half_target_q50"] > 0
    return x


# ---------------------------------------------------------------- analysis
def prepare_chain(raw: pd.DataFrame, as_of: date) -> pd.DataFrame:
    c = raw.copy()
    for k in ["strike", "spot", "bid", "ask", "iv", "delta", "gamma", "theta", "vega", "oi", "volume"]:
        c[k] = pd.to_numeric(c[k], errors="coerce")
    c = c[c["right"].isin(["C", "P"]) & c["expiry"].notna()].copy()
    c["expiry"] = pd.to_datetime(c["expiry"]).dt.date
    c["dte_calendar_days"] = [(e - as_of).days for e in c["expiry"]]
    c = c[c["dte_calendar_days"] >= 1]
    c["sessions_to_expiry"] = [sessions_between(as_of, e) for e in c["expiry"]]
    c["mid"] = (c["bid"] + c["ask"]) / 2
    c["spread_fraction_of_mid"] = (c["ask"] - c["bid"]) / c["mid"].replace(0, np.nan)
    c["valid_quote"] = (c["bid"] >= 0) & (c["ask"] > 0) & (c["ask"] >= c["bid"]) & (c["spot"] > 0)
    # quote sanity: ask not above the strike (put) or the stock price (call), ask not below intrinsic
    intr = np.where(c["right"] == "C", np.maximum(c["spot"] - c["strike"], 0), np.maximum(c["strike"] - c["spot"], 0))
    c["intrinsic"] = intr
    cap = np.where(c["right"] == "P", c["strike"], c["spot"])
    c["iv_plausible"] = c["iv"].between(0.03, 5.0)
    c["quote_sane"] = c["valid_quote"] & (c["ask"] <= cap) & (c["ask"] >= intr)
    c["usable"] = c["quote_sane"] & (c["bid"] > 0) & c["iv_plausible"]
    return c


def expiry_context(c: pd.DataFrame, ticker: str) -> pd.DataFrame:
    rows = []
    for exp, g in c.groupby("expiry"):
        spot = g["spot"].median()
        gu = g[g["usable"]] if g["usable"].any() else g.iloc[0:0]
        atm = gu.loc[(gu["strike"] - spot).abs().sort_values().index[:4]]
        atm_iv = atm["iv"].median()
        days = g["dte_calendar_days"].iloc[0]
        calls, puts = g[g["right"] == "C"], g[g["right"] == "P"]

        def wall(x):
            a = x.groupby("strike")["oi"].sum(min_count=1).dropna()
            return float(a.idxmax()) if len(a) and a.max() > 0 else None
        rows.append({"ticker": ticker, "expiry": str(exp), "dte_calendar_days": days,
                     "sessions_to_expiry": g["sessions_to_expiry"].iloc[0], "atm_iv": atm_iv,
                     "implied_move_pct": atm_iv * math.sqrt(days / 365) * 100 if pd.notna(atm_iv) else None,
                     "call_oi": calls["oi"].sum(min_count=1), "put_oi": puts["oi"].sum(min_count=1),
                     "call_volume": calls["volume"].sum(min_count=1), "put_volume": puts["volume"].sum(min_count=1),
                     "call_oi_wall": wall(calls), "put_oi_wall": wall(puts), "contracts": len(g)})
    return pd.DataFrame(rows)


def thesis_view(c: pd.DataFrame, t: pd.Series, ectx: pd.DataFrame) -> pd.DataFrame:
    right = "C" if t["side"] == "CALL" else "P"
    s = 1 if right == "C" else -1
    x = c[c["right"] == right].copy()
    if x.empty:
        return x
    q50 = t.get("q50_sessions") if pd.notna(t.get("q50_sessions")) else 10
    q80 = t.get("q80_sessions") if pd.notna(t.get("q80_sessions")) else 2 * q50
    x["sessions_to_last_exit"] = x["sessions_to_expiry"] - EXIT_BUFFER_SESSIONS
    x["covers_q50"] = x["sessions_to_last_exit"] >= q50
    x["covers_q80"] = x["sessions_to_last_exit"] >= q80
    level, half, inv = t.get("level"), t.get("half_target"), t.get("invalidation")
    spot = x["spot"].median()
    if pd.isna(half) and pd.notna(level):
        half = spot + (level - spot) / 2
    x["strike_itm_at_level"] = (x["strike"] <= level) if s > 0 else (x["strike"] >= level)
    # rank strikes by moneyness now: count of strikes in the money
    itm_now = (x["strike"] < spot) if s > 0 else (x["strike"] > spot)
    x["itm_rank"] = 0
    for exp, g in x.groupby("expiry"):
        k = g.loc[itm_now.loc[g.index], "strike"]
        order = k.sort_values(ascending=(s < 0)).index  # nearest-to-money first
        x.loc[order, "itm_rank"] = np.arange(1, len(order) + 1)
    x["strike_in_set"] = (x["strike_itm_at_level"] & (x["itm_rank"] <= MAX_ITM_STRIKES)
                          & ((x["strike"] / spot - 1).abs() <= MAX_MONEYNESS))
    x["breakeven_at_expiry"] = x["strike"] + s * x["ask"]
    x["breakeven_move_pct"] = (x["breakeven_at_expiry"] / spot - 1) * s * 100
    x["anticipated_move_pct"] = (level / spot - 1) * s * 100 if pd.notna(level) else np.nan
    x["intrinsic_share"] = x["intrinsic"] / x["ask"].replace(0, np.nan)
    yrs = np.maximum(x["sessions_to_expiry"] - q50, 0) / 252
    half_spread = (x["ask"] - x["bid"]) / 2
    for name, px in [("half_target", half), ("level", level), ("invalidation", inv)]:
        if pd.isna(px):
            x[f"value_at_{name}_q50"] = np.nan
            x[f"ret_{name}_q50"] = np.nan
            continue
        iv_use = x["iv"].where(x["iv_plausible"], np.nan)
        v = bs_value(np.full(len(x), px), x["strike"], yrs, iv_use.fillna(iv_use.median()), x["right"].to_numpy())
        x[f"value_at_{name}_q50"] = np.maximum(v - half_spread, 0)
        x[f"ret_{name}_q50"] = x[f"value_at_{name}_q50"] / x["ask"].replace(0, np.nan) - 1
    x["pays_at_half_target_q50"] = x["ret_half_target_q50"] > 0
    im = ectx.set_index("expiry")["implied_move_pct"].to_dict()
    x["implied_move_pct"] = [im.get(str(e)) for e in x["expiry"]]
    x["move_to_implied_multiple"] = x["anticipated_move_pct"] / pd.to_numeric(x["implied_move_pct"], errors="coerce")
    x["exception_short_dated"] = (x["dte_calendar_days"].between(EXCEPTION_MIN_DTE, MIN_DTE - 1) & x["covers_q50"]
                                  & (x["move_to_implied_multiple"] >= EXCEPTION_MULTIPLE))
    # floor: 14 calendar days AND the expiry leaves the median time plus the exit buffer (or the short-dated exception)
    x["in_window"] = ((x["dte_calendar_days"] >= MIN_DTE) & x["covers_q50"]) | x["exception_short_dated"]
    x["spread_class"] = np.digitize(x["spread_fraction_of_mid"].fillna(9), SPREAD_CLASSES)  # 0 best .. 4 worst
    x["ledger_id"] = t["ledger_id"]
    iv_all = x["iv"].where(x["iv_plausible"], np.nan)
    x = american_values(x, t, {"half_target": half, "level": level, "invalidation": inv}, yrs,
                        iv_all.fillna(iv_all.median()))
    return x


MAX_PREMIUM = None   # set from --max-premium (per share)


def shortlist(x: pd.DataFrame) -> pd.DataFrame:
    if x.empty:
        return x
    core = x["in_window"] & x["strike_in_set"] & x["usable"]
    # with a premium cap, also consider out-of-the-money strikes between the price and the level (up to 25% away)
    y = pd.concat([x[core], x[shortlist_candidates(x) & ~core]]).copy()
    if y.empty:
        return y
    y["within_cap"] = (y["ask"] <= MAX_PREMIUM) if MAX_PREMIUM is not None else True
    first_q80 = y.loc[y["covers_q80"], "expiry"].min() if y["covers_q80"].any() else None
    y["is_first_q80_expiry"] = y["expiry"].eq(first_q80) if first_q80 is not None else False
    y["dist_money"] = (y["strike"] / y["spot"] - 1).abs()
    y = y.sort_values(["within_cap", "pays_at_half_target_q50", "is_first_q80_expiry", "covers_q50", "spread_class", "dist_money"],
                      ascending=[False, False, False, False, True, True])
    return y.head(3).assign(shortlist_rank=lambda d: np.arange(1, len(d) + 1))


# ---------------------------------------------------------------- run
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger")
    ap.add_argument("--all", action="store_true", help="every active thesis, not only focus_v3")
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--provider", choices=["marketdata", "polygon"], default="marketdata")
    ap.add_argument("--max-dte", type=int, default=140, help="furthest expiry fetched, calendar days (140 reaches the February monthly)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out")
    ap.add_argument("--as-of", help="analysis session YYYY-MM-DD (default today); use the original date for replays")
    ap.add_argument("--offline-chain", help="a saved chain_raw.csv.gz (or test CSV): re-analyse without calling the provider")
    ap.add_argument("--wait-pipeline-options", action="store_true", help="wait for the evening run's own options stage to finish first")
    ap.add_argument("--wait-hours", type=float, default=10)
    ap.add_argument("--reserve-credits", type=int, default=20000, help="stop fetching below this many MarketData credits left")
    ap.add_argument("--max-premium", type=float, help="the day's premium cap per share, e.g. 3 (preference, not a filter)")
    ap.add_argument("--reuse-phantom", nargs="?", const=str(PHANTOM_DB), help="read the evening run's chains from Phantom; fetch only the gaps")
    ap.add_argument("--wait-pipeline-done", action="store_true", help="wait for the evening run to finish (use with --reuse-phantom)")
    a = ap.parse_args()
    CREDITS["reserve"] = a.reserve_credits
    global MAX_PREMIUM
    MAX_PREMIUM = a.max_premium

    ledger_path = find_ledger(a.ledger)
    theses = load_ledger(ledger_path, a.all, a.tickers)
    if a.tickers:
        missing = sorted({t.upper() for t in a.tickers} - set(theses["ticker"]))
        if missing:
            print("not in the selected ledger rows (use --all if they are outside focus):", " ".join(missing))
    if theses.empty:
        raise SystemExit("No theses selected from the ledger")
    if a.wait_pipeline_done and not a.offline_chain:
        wait_for_pipeline_done(theses, a.wait_hours)
    elif a.wait_pipeline_options and not a.offline_chain:
        wait_for_pipeline_options(theses, a.wait_hours)
    as_of = date.fromisoformat(a.as_of) if a.as_of else date.today()
    global PRICING, AS_OF
    AS_OF = as_of
    PRICING = (pricing_basis_for_ledger(theses) if SHARED_PRICING
               else {"rate": None, "rate_basis": "SHARED_PRICING_UNAVAILABLE"})
    engine = ("domain.option_valuation (American, dividends)" if SHARED_PRICING
              else "European fallback: " + SHARED_PRICING_ERROR)
    print(f"pricing: shortlist candidates on {engine}; rate {PRICING.get('rate')} ({PRICING.get('rate_basis')})")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_root = Path(a.out) if a.out else ledger_path.parent.parent / "options_intel"
    dest = out_root / stamp
    dest.mkdir(parents=True, exist_ok=True)
    tickers = sorted(theses["ticker"].unique())
    print(f"{VERSION}: {len(theses)} theses, {len(tickers)} tickers from {ledger_path.name} -> {dest}")

    chains, metas = {}, {}
    reuse_log = []
    if a.reuse_phantom and not a.offline_chain:
        ppath = Path(a.reuse_phantom)
        sess = sorted(theses["evidence_as_of"].dropna().astype(str).str[:10].unique()) if "evidence_as_of" in theses else []
        if not ppath.exists() or len(sess) != 1:
            print(f"reuse-phantom: not used ({'Phantom not found' if not ppath.exists() else 'ledger has no single evidence session'}); fetching all")
        else:
            # an expiry beyond what our own fetch would reach (--max-dte) is no reason to refetch
            reach = sessions_between(as_of, as_of + timedelta(days=a.max_dte))
            # stored chain must at least reach the median time plus the exit buffer (the tool's own minimum window)
            need = (theses.groupby("ticker")["q50_sessions"].max() + EXIT_BUFFER_SESSIONS).clip(upper=reach - 5)
            for t in tickers:
                try:
                    raw = read_phantom(ppath, t, sess[0])
                except Exception as e:  # a read failure is a gap, never fatal
                    raw, why = pd.DataFrame(), f"PHANTOM_READ_ERROR {type(e).__name__}"
                else:
                    if not raw.empty and pd.to_numeric(raw["spot"], errors="coerce").isna().all():
                        ref = pd.to_numeric(theses.loc[theses["ticker"] == t, "ref_price"], errors="coerce").dropna()
                        raw["spot"] = ref.iat[0] if len(ref) else np.nan   # stored chain has no underlying price: use the ledger's close
                    ok, why = phantom_enough(raw, need.get(t, np.nan), as_of)
                    if ok:
                        chains[t] = raw.drop(columns=["phantom_source"])
                        metas[t] = {"provider": "phantom:" + str(raw["phantom_source"].mode().iat[0] if raw["phantom_source"].notna().any() else ""),
                                    "status": "OK", "freshness": f"SESSION_{sess[0]}"}
                reuse_log.append({"ticker": t, "result": why, "rows": int(len(raw))})
            got = sum(1 for r in reuse_log if r["result"] == "PHANTOM_OK")
            print(f"reuse-phantom: {got} of {len(tickers)} tickers read from Phantom for session {sess[0]}; fetching {len(tickers) - got}")
    to_fetch = [t for t in tickers if t not in chains]
    if a.offline_chain:
        off = pd.read_csv(a.offline_chain)
        base_cols = ["contract", "right", "strike", "expiry", "spot", "bid", "ask", "iv", "delta", "gamma", "theta", "vega", "oi", "volume", "quote_time_utc"]
        for t in tickers:
            chains[t] = off.loc[off["ticker"].astype(str).str.upper() == t, [c for c in base_cols if c in off.columns]]
            metas[t] = {"provider": "offline", "status": "OK" if len(chains[t]) else "NO_OPTIONS_DATA"}
    else:
        key = get_key("MARKETDATA_API_KEY" if a.provider == "marketdata" else "POLYGON_API_KEY")
        if not key and to_fetch:
            raise SystemExit(f"Set {'MARKETDATA_API_KEY' if a.provider == 'marketdata' else 'POLYGON_API_KEY'}")
        fetch = fetch_marketdata if a.provider == "marketdata" else fetch_polygon
        to_date = as_of + timedelta(days=a.max_dte)
        session = requests.Session()

        def job(t):
            time.sleep(0.1)
            if CREDITS["stopped"]:
                return t, pd.DataFrame(), {"provider": a.provider, "status": "SKIPPED_CREDIT_RESERVE"}
            try:
                return t, *fetch(t, key, to_date, session)
            except Exception as e:  # network or parsing failure is recorded, never fatal
                return t, pd.DataFrame(), {"provider": a.provider, "status": f"ERROR_{type(e).__name__}"}
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for i, fut in enumerate(as_completed([ex.submit(job, t) for t in to_fetch]), 1):
                t, df, meta = fut.result()
                chains[t], metas[t] = df, meta
                if i % 25 == 0 or i == len(to_fetch):
                    print(f"  fetched {i}/{len(to_fetch)}")

    raw_frames, view_frames, short_frames, ctx_frames, summary, errors = [], [], [], [], [], []
    for t in tickers:
        raw = chains.get(t, pd.DataFrame())
        meta = metas.get(t, {})
        if raw.empty:
            for _, th in theses[theses["ticker"] == t].iterrows():
                summary.append({"ledger_id": th["ledger_id"], "ticker": t, "side": th["side"], "chain_status": meta.get("status", "NO_CHAIN")})
            errors.append({"ticker": t, "status": meta.get("status"), "http_status": meta.get("http_status")})
            continue
        c = prepare_chain(raw, as_of)
        raw_frames.append(c.assign(ticker=t, provider=meta.get("provider"), freshness=meta.get("freshness"), as_of=str(as_of)))
        ectx = expiry_context(c, t)
        ctx_frames.append(ectx)
        for _, th in theses[theses["ticker"] == t].iterrows():
            v = thesis_view(c, th, ectx)
            sl = shortlist(v)
            view_frames.append(v.assign(ticker=t))
            short_frames.append(sl.assign(ticker=t))
            spot = c["spot"].median()
            near = ectx[ectx["dte_calendar_days"] >= MIN_DTE].head(1)
            far = ectx.tail(1)
            best = sl.iloc[0] if len(sl) else None
            summary.append({
                "ledger_id": th["ledger_id"], "ticker": t, "side": th["side"], "chain_status": "OK",
                "provider": meta.get("provider"), "freshness": meta.get("freshness"), "spot": spot,
                "ledger_ref_price": th.get("ref_price"), "level": th.get("level"), "half_target": th.get("half_target"),
                "invalidation": th.get("invalidation"), "q50_sessions": th.get("q50_sessions"), "q80_sessions": th.get("q80_sessions"),
                "expiries": len(ectx), "furthest_sessions": int(ectx["sessions_to_expiry"].max()),
                "any_expiry_covers_q50": bool(v["covers_q50"].any()) if len(v) else False,
                "any_expiry_covers_q80": bool(v["covers_q80"].any()) if len(v) else False,
                "contracts_in_window_and_strike_set": int((v["in_window"] & v["strike_in_set"] & v["usable"]).sum()) if len(v) else 0,
                "anticipated_move_pct": v["anticipated_move_pct"].iloc[0] if len(v) else None,
                "level_vs_implied_move_far": (v["anticipated_move_pct"].iloc[0] / far["implied_move_pct"].iloc[0]) if len(v) and len(far) and pd.notna(far["implied_move_pct"].iloc[0]) and far["implied_move_pct"].iloc[0] > 0 else None,
                "near_atm_iv": near["atm_iv"].iloc[0] if len(near) else None,
                "far_atm_iv": far["atm_iv"].iloc[0] if len(far) else None,
                "near_implied_move_pct": near["implied_move_pct"].iloc[0] if len(near) else None,
                "call_oi_wall_near": near["call_oi_wall"].iloc[0] if len(near) else None,
                "put_oi_wall_near": near["put_oi_wall"].iloc[0] if len(near) else None,
                "put_call_oi_ratio_all": (c.loc[c.right == "P", "oi"].sum() / c.loc[c.right == "C", "oi"].sum()) if c.loc[c.right == "C", "oi"].sum() > 0 else None,
                "best_contract": best["contract"] if best is not None else None,
                "best_expiry": str(best["expiry"]) if best is not None else None,
                "best_strike": best["strike"] if best is not None else None,
                "best_bid": best["bid"] if best is not None else None, "best_ask": best["ask"] if best is not None else None,
                "best_spread_fraction": best["spread_fraction_of_mid"] if best is not None else None,
                "best_delta": best["delta"] if best is not None else None, "best_iv": best["iv"] if best is not None else None,
                "best_ret_half_target_q50": best["ret_half_target_q50"] if best is not None else None,
                "best_ret_level_q50": best["ret_level_q50"] if best is not None else None,
                "best_ret_invalidation_q50": best["ret_invalidation_q50"] if best is not None else None,
                "best_within_cap": (bool(best["within_cap"]) if best is not None else None) if MAX_PREMIUM is not None else None,
                "premium_cap": MAX_PREMIUM,
                "best_covers_q80": bool(best["covers_q80"]) if best is not None else None,
                "best_is_short_dated_exception": bool(best["exception_short_dated"]) if best is not None else None,
                "contract_state": (("NO_EXPIRY_COVERS_MEDIAN" if len(v) and not v["covers_q50"].any() else "NO_USABLE_CONTRACT_IN_WINDOW") if best is None else
                                   "COVERS_PLANNED_HOLD" if best["covers_q80"] else
                                   "SHORT_DATED_EXCEPTION" if best["exception_short_dated"] else "COVERS_MEDIAN_ONLY")})

    def save(name, frames, gz=False):
        df = pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else pd.DataFrame()
        df.to_csv(dest / name, index=False, compression="gzip" if gz else None)
        return len(df)
    n_raw = save("chain_raw.csv.gz", raw_frames, gz=True)
    n_view = save("contracts_thesis.csv", view_frames)
    n_short = save("shortlist.csv", short_frames)
    save("expiry_context.csv", ctx_frames)
    summ = pd.DataFrame(summary)
    if "level_vs_implied_move_far" in summ:
        summ["level_flag"] = np.where(pd.to_numeric(summ["level_vs_implied_move_far"], errors="coerce") > 3,
                                      "LEVEL_BEYOND_3X_IMPLIED_MOVE_TO_FURTHEST_EXPIRY", "")
    summ.to_csv(dest / "thesis_summary.csv", index=False)
    pd.DataFrame(errors, columns=["ticker", "status", "http_status"]).to_csv(dest / "errors.csv", index=False)
    manifest = {"version": VERSION, "as_of": str(as_of), "created_local": stamp, "ledger": str(ledger_path),
                "theses": len(theses), "tickers": len(tickers), "provider": a.provider if not a.offline_chain else "offline",
                "rows": {"chain_raw": n_raw, "contracts_thesis": n_view, "shortlist": n_short},
                "chain_status": pd.Series([m.get("status") for m in metas.values()]).value_counts().to_dict(),
                "reuse_phantom": {"used": bool(reuse_log), "from_phantom": sum(1 for r in reuse_log if r["result"] == "PHANTOM_OK"),
                                  "fetched": len(to_fetch) if not a.offline_chain else 0,
                                  "gap_reasons": pd.Series([r["result"].split(" ")[0] for r in reuse_log if r["result"] != "PHANTOM_OK"]).value_counts().to_dict()},
                "credits": {"reserve": CREDITS["reserve"], "lowest_remaining_seen": CREDITS["remaining_min"],
                            "stopped_at_reserve": CREDITS["stopped"]},
                "rules": {"exit_buffer_sessions": EXIT_BUFFER_SESSIONS, "min_dte": MIN_DTE, "exception_min_dte": EXCEPTION_MIN_DTE,
                          "exception_multiple": EXCEPTION_MULTIPLE, "max_itm_strikes": MAX_ITM_STRIKES, "max_moneyness": MAX_MONEYNESS,
                          "spread_classes": SPREAD_CLASSES, "rate": RATE, "max_dte_fetched": a.max_dte},
                "pricing": {"shared_engine": SHARED_PRICING, "decision_rate": PRICING.get("rate"),
                            "decision_rate_basis": PRICING.get("rate_basis"),
                            "candidates": "American tree with dividends (domain.option_valuation); other rows "
                                          + EUROPEAN_CONTEXT}}
    if reuse_log:
        pd.DataFrame(reuse_log).to_csv(dest / "reuse_phantom.csv", index=False)
    (dest / "run_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    print("chain status:", manifest["chain_status"])
    if not a.offline_chain:
        print("MarketData credits: lowest remaining seen", CREDITS["remaining_min"] if CREDITS["remaining_min"] is not None else "(header not sent)",
              "| stopped at reserve" if CREDITS["stopped"] else "")
    print("saved:", dest)


if __name__ == "__main__":
    main()
