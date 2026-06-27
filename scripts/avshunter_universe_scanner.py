#!/usr/bin/env python3
"""
AVSHUNTER UNIVERSE OPTIONS MISPRICING SCANNER v7.0
===================================================
Two-tier scanner operating INDEPENDENTLY of the main pipeline universe.
Purpose: find cheap/mispriced options the pipeline would never see.

DUAL API ARCHITECTURE
─────────────────────
Polygon.io    — price OHLC (RV calculation), live options chain (bid/ask/OI/Greeks),
                Tier 1 dynamic universe discovery via active contracts endpoint.

MarketData.app — real historical IV for true IV Rank computation.
                 Trader plan: real-time options data, unlimited history,
                 100,000 credits/day (resets 9:30am ET).
                 Credit strategy: SQLite IV cache — cold start pulls 52 weeks
                 of weekly ATM IV per ticker (one-time cost), then only
                 refreshes the trailing week on each subsequent run (~2 credits
                 per ticker per day vs ~104 credits cold start).

IV RANK ACCURACY
────────────────
v4.0 and earlier: synthetic proxy RV×1.2 — confidence ~65%
v5.0:             real 52-week weekly ATM IV from MarketData.app — confidence ~95%
Fallback:         if MarketData.app unavailable, reverts to RV×1.2 proxy with warning.

TIER 1 — DYNAMIC (run daily, ~15-30 mins)
  Source: Polygon /v3/reference/options/contracts — pulls ALL active option
  contracts in 7-45 DTE window, extracts unique underlying tickers.
  No predefined list. Purely market-driven. ~400-800 names.

TIER 2 — BROAD SWEEP (run weekly or on-demand, ~2-3 hrs)
  Source: Built-in broad universe ~250 names covering sectors, ETFs,
  high-vol mid-caps. Catches slow-burn mispricings.

PIPELINE HANDSHAKE (passive, non-blocking)
  Writes scanner_manifest.json → data/output/universe_scanner/
  Orchestrator Phase 0 reads on --evening run if manifest < 24hrs old.
  NEW tickers (not in pipeline) → injected into discovery.
  KNOWN tickers → VMS fields available via scanner_context_{run_id}.json.
  Pipeline NEVER blocked if scanner has not run.

STANDALONE RUN MODES
  python avshunter_universe_scanner.py --tier1
  python avshunter_universe_scanner.py --tier2
  python avshunter_universe_scanner.py --tier1 --tier2
  python avshunter_universe_scanner.py --tickers NVDA,TSLA,AMD
  python avshunter_universe_scanner.py --tier1 --dry-run
  python avshunter_universe_scanner.py --tier1 --top-n 30
  python avshunter_universe_scanner.py --rebuild-iv-cache   (cold start / refresh)
  python avshunter_universe_scanner.py --test               (zero API calls, ~30 seconds)

TEST MODE (--test)
  Validates full scanner pipeline logic end-to-end with zero API calls.
  Uses 5 hardcoded tickers with synthetic OHLCV, options chain, and IV history.
  Writes real output files and scanner_manifest.json so orchestrator Phase 0
  handshake can be tested immediately after with --validate.
  Safe to run at any time. No Polygon or MarketData credits consumed.
"""

import os
import sys
import json
import time
import sqlite3
import logging
import argparse
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# ============================================================
# PATHS
# ============================================================
BASE_DIR   = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "output" / "universe_scanner"
LOGS_DIR   = BASE_DIR / "data" / "logs"
DB_DIR     = BASE_DIR / "data" / "cache"

# IV history SQLite cache — lives alongside actuarial DB
IV_CACHE_DB = DB_DIR / "iv_history_cache.db"

# Pipeline universe — for overlap tagging only, never scanned
PIPELINE_UNIVERSE_FILE = BASE_DIR / "data" / "universe" / "polygon_liquid_universe.csv"

# ============================================================
# CONFIG
# ============================================================
POLYGON_API_KEY     = os.environ.get("POLYGON_API_KEY",    "YOUR_POLYGON_API_KEY")
MARKETDATA_API_KEY  = os.environ.get("MARKETDATA_API_KEY", "YOUR_MARKETDATA_API_KEY")

LOOKBACK_DAYS       = 120
RV_WINDOW           = 20
MAX_WORKERS         = 5
CALL_DELAY          = 0.25

# Contract filters
MIN_DTE              = 7
MAX_DTE              = 60      # Extended: 45→60 to capture longer-dated setups
MAX_SPREAD_PCT       = 0.15    # Hard block: >15% spread — reject contract
SPREAD_WARN_PCT      = 0.10    # Soft warn: >10% spread — flag, apply score penalty
MIN_MID              = 0.05    # Lowered: 0.25→0.05 — low-priced stocks have sub-$0.25 premiums
MAX_MONEYNESS        = 0.20    # Fixed: 5%→20% — was blocking almost all low-price stocks (AAL, AAA etc)

# Spread rationale:
# Liquid large-caps (SPY, QQQ, AAPL): typically 1-4% spread
# Mid-cap with active options: typically 4-8% spread
# Higher-priced / higher-vol names (NVDA, TSLA, AMZN): 8-15% structurally normal
# >15%: market maker extracting too much edge — reject regardless of underlying price
# >10%: flag with warning + score penalty — tradeable but requires discipline

# VMS thresholds
VMS_GO_THRESHOLD    = 75
VMS_PROBE_THRESHOLD = 60

# IV Rank: 52 weeks of weekly samples = 52 data points per ticker
IV_RANK_WEEKS       = 52
IV_RANK_SAMPLE_DAYS = 7        # weekly sampling interval
# Cache considered fresh if updated within this many days
IV_CACHE_MAX_AGE_DAYS = 7

# Pipeline handshake
MANIFEST_MAX_AGE_HOURS = 24

# ============================================================
# TIER 2 BROAD SWEEP UNIVERSE
# Deliberately separate from the pipeline's 1,999 tickers.
# ============================================================
TIER2_UNIVERSE = list(dict.fromkeys([
    # Large cap high options activity
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","AMD","INTC",
    "CRM","ORCL","ADBE","NOW","SNOW","DDOG","CRWD","NET","ZS","PANW","FTNT",
    "OKTA","MDB","PLTR","UBER","LYFT","ABNB","DASH","COIN","HOOD",
    # Financials
    "JPM","BAC","GS","MS","C","WFC","BLK","SCHW","AXP","COF","DFS","SYF",
    # Healthcare / Biotech
    "UNH","JNJ","PFE","MRNA","ABBV","BMY","LLY","GILD","BIIB","REGN",
    "VRTX","ALNY","IONS","BEAM","EDIT","NTLA","CRSP","PACB","ILMN",
    # Energy
    "XOM","CVX","OXY","SLB","MPC","VLO","PSX","HAL","BKR","FANG",
    # Consumer
    "WMT","TGT","COST","MCD","SBUX","NKE","LULU","DECK","SKX",
    # EV / Clean energy
    "RIVN","LCID","CHPT","BLNK","EVGO","NKLA","FSR","WKHS",
    "ENPH","SEDG","FSLR","RUN","PLUG","BE","SPWR","ARRY","NOVA",
    # ETFs — basket vs component IV divergence
    "SPY","QQQ","IWM","DIA","XLF","XLE","XLK","XLV","XLI","XLB",
    "XLC","XLY","XLP","XLU","XLRE","GLD","SLV","TLT","HYG","LQD",
    "ARKK","ARKG","ARKF","ARKW","SQQQ","TQQQ","UVXY","VXX",
    # Speculative / persistent cheap IV cycles
    "GME","AMC","SPCE","OPEN","DKNG","PENN","MGM","WYNN","LVS","CZR",
    "NCLH","CCL","RCL","AAL","DAL","UAL","LUV",
    # Tech mid-cap
    "ROKU","SNAP","PINS","RBLX","U","ZM","DOCU","TWLO","BILL","HUBS",
    "VEEV","PAYC","GPN","FIS","FISV","MA","V","PYPL","SQ","AFRM",
    "UPST","SOFI","LC",
    # Semiconductors
    "MU","SMCI","AVGO","QCOM","TXN","LRCX","AMAT","KLAC","ASML",
    "MRVL","SWKS","QRVO","MPWR","WOLF","ON","AMBA","SITM",
    # Chinese ADRs
    "BABA","JD","PDD","BIDU","NIO","XPEV","LI","TIGR",
    # Healthcare services
    "CVS","CI","HUM","MOH","CNC","ELV","HCA","THC","UHS",
    # REITs — compression plays
    "AMT","CCI","EQIX","PLD","SPG","O","NNN","VICI","GLPI","IIPR",
    # Crypto-adjacent
    "MSTR","CLSK","RIOT","MARA","HUT","BTBT",
    # Quantum / emerging
    "IONQ","RGTI","QUBT","QBTS",
    # Macro-sensitive
    "FCX","AA","X","NUE","CLF","MP","CTRA","DVN","EOG","APA",
    "USB","PNC","TFC","RF","HBAN","CFG",
]))


# ============================================================
# TEST MODE — synthetic data (zero API calls)
# 5 tickers covering: GO, PROBE, WAIT, BLOCK scenarios + ETF
# ============================================================
TEST_UNIVERSE = ["AAPL", "MSFT", "SPY", "QQQ", "NVDA"]

def _synthetic_price_data(ticker: str) -> dict:
    """
    Generate realistic synthetic price + RV data for test mode.
    No Polygon API call made. Covers range of RV/compression scenarios.
    """
    import numpy as np
    from datetime import datetime, timedelta

    # Deterministic but varied per ticker
    seeds = {"AAPL": 42, "MSFT": 43, "SPY": 44, "QQQ": 45, "NVDA": 46}
    rng   = np.random.default_rng(seeds.get(ticker, 42))

    spots = {"AAPL": 185.0, "MSFT": 415.0, "SPY": 520.0, "QQQ": 440.0, "NVDA": 875.0}
    spot  = spots.get(ticker, 200.0)

    # Generate 120 days of synthetic returns
    n       = 120
    returns = rng.normal(0.0005, 0.015, n)
    rv_20   = float(np.std(returns[-20:]) * np.sqrt(252))

    # ATR percentile — varied to test compression signal
    atr_pcts = {"AAPL": 0.18, "MSFT": 0.55, "SPY": 0.22, "QQQ": 0.68, "NVDA": 0.12}
    atr_pct  = atr_pcts.get(ticker, 0.40)

    # Build rv_series as pandas Series
    rv_vals = []
    for i in range(20, n):
        rv_vals.append(float(np.std(returns[i-20:i]) * np.sqrt(252)))
    rv_series = pd.Series(rv_vals)

    return {
        "spot":        spot,
        "rv":          rv_20,
        "rv_series":   rv_series,
        "compression": atr_pct < 0.25,
        "expansion":   atr_pct > 0.75,
        "atr_pct":     round(atr_pct, 3),
    }


def _synthetic_options_chain(ticker: str, spot: float) -> pd.DataFrame:
    """
    Generate realistic synthetic options chain for test mode.
    No Polygon API call made. Covers puts/calls across DTE buckets.
    Designed so some tickers pass VMS gates (GO/PROBE) and some don't.
    """
    today = datetime.today()
    rows  = []

    # IV levels per ticker — varied to test scoring
    iv_levels = {
        "AAPL": 0.22,   # low IV → should score well on IV rank
        "MSFT": 0.28,
        "SPY":  0.15,   # very low IV
        "QQQ":  0.20,
        "NVDA": 0.45,   # high IV → lower score
    }
    base_iv = iv_levels.get(ticker, 0.30)

    for contract_type in ["call", "put"]:
        for dte_days in [8, 14, 21, 35]:               # removed 4 — below MIN_DTE=7
            expiry = today + timedelta(days=dte_days)
            for moneyness in [-0.03, -0.01, 0.0, 0.01, 0.03]:
                strike = round(spot * (1 + moneyness) / 5) * 5  # round to $5
                iv     = base_iv * (1 + abs(moneyness) * 2)     # smile
                if contract_type == "put":
                    iv *= 1.05  # slight put skew
                mid = max(0.30, spot * iv * np.sqrt(dte_days / 252) * 0.4)
                bid = round(mid * 0.98, 2)              # 4% spread — passes SPREAD_WARN_PCT(10%) and MAX_SPREAD_PCT(15%)
                ask = round(mid * 1.02, 2)              # 4% spread — no spread warning flag
                oi  = int(500 + abs(moneyness) * 5000)
                delta = 0.5 - moneyness * 10 if contract_type == "call" else -0.5 + moneyness * 10

                rows.append({
                    "contract_type":      contract_type,
                    "strike_price":       float(strike),
                    "expiration_date":    pd.Timestamp(expiry),
                    "implied_volatility": round(iv, 4),
                    "bid":                bid,
                    "ask":                ask,
                    "open_interest":      oi,
                    "delta":              round(delta, 3),
                    "vega":               round(mid * 0.1, 4),
                })

    return pd.DataFrame(rows)


def _synthetic_iv_series(ticker: str) -> pd.Series:
    """
    Generate synthetic 52-week weekly IV history for test mode.
    No MarketData.app API call made. Returns Series for IV rank computation.
    """
    seeds = {"AAPL": 10, "MSFT": 11, "SPY": 12, "QQQ": 13, "NVDA": 14}
    rng   = np.random.default_rng(seeds.get(ticker, 10))

    iv_means = {"AAPL": 0.24, "MSFT": 0.27, "SPY": 0.16, "QQQ": 0.19, "NVDA": 0.50}
    mean_iv  = iv_means.get(ticker, 0.30)

    vals  = rng.normal(mean_iv, mean_iv * 0.15, 52).clip(0.05, 1.5)
    dates = pd.date_range(end=datetime.today(), periods=52, freq="W")
    return pd.Series(vals, index=dates)


def process_ticker_test(ticker: str, conn: sqlite3.Connection) -> Optional[dict]:
    """
    Test mode version of process_ticker.
    Uses synthetic data — zero API calls, completes in milliseconds per ticker.
    """
    price_data = _synthetic_price_data(ticker)
    options_df = _synthetic_options_chain(ticker, price_data["spot"])
    iv_series  = _synthetic_iv_series(ticker)

    if options_df.empty:
        return None

    vms = compute_vms(price_data, options_df, iv_series)
    if not vms:
        return None

    # Override iv_rank_source to show TEST clearly in output
    vms["iv_rank_source"]     = "TEST_SYNTHETIC"
    vms["iv_rank_confidence"] = 1.0   # synthetic is perfectly deterministic

    contracts = score_long_contracts(ticker, options_df, price_data["spot"], vms)

    return {
        "ticker":       ticker,
        "spot":         round(price_data["spot"], 2),
        "vms":          vms,
        "contracts":    contracts,
        "chain_source": "synthetic",   # Bug 2 fix: 'chain' doesn't exist in test mode
    }


def run_test_scan(pipeline_universe: set, top_n: int = 10) -> tuple:
    """
    Run full scanner pipeline in test mode against 5 synthetic tickers.
    Zero API calls. Validates:
      - VMS scoring engine (IV rank, RV vs IV, compression, term, skew)
      - Contract scanner (filtering, scoring)
      - Output writing (manifest, CSVs)
      - Pipeline handshake (manifest readable by orchestrator Phase 0)
    Completes in ~10-30 seconds.
    """
    log.info("=" * 65)
    log.info("TEST MODE — synthetic data, zero API calls")
    log.info(f"Universe: {TEST_UNIVERSE}")
    log.info("=" * 65)

    conn = init_iv_cache()
    all_contracts = []
    vms_summary   = []

    for ticker in TEST_UNIVERSE:
        result = process_ticker_test(ticker, conn)
        if result:
            v   = result["vms"]
            tag = "KNOWN" if ticker in pipeline_universe else "NEW"

            vms_summary.append({
                "ticker":              ticker,
                "spot":                result["spot"],
                "iv":                  v["iv"],
                "rv":                  v["rv"],
                "vol_spread":          v["vol_spread"],
                "iv_rank":             v["iv_rank"],
                "iv_rank_source":      v["iv_rank_source"],
                "iv_rank_confidence":  v["iv_rank_confidence"],
                "iv_history_points":   v["iv_history_points"],
                "compression":         v["compression"],
                "term_slope":          v["term_slope"],
                "skew":                v["skew"],
                "score":               v["score"],
                "decision":            v["decision"],
                "n_contracts":         len(result["contracts"]),
                "pipeline_tag":        tag,
                "tier":                "TEST",
            })

            for c in result["contracts"]:
                c["pipeline_tag"] = tag
                c["tier"]         = "TEST"
            all_contracts.extend(result["contracts"])

            log.info(
                "  ✓ %s [%s] %s score=%d | RV=%.3f IV=%.3f spread=%+.3f | "
                "contracts=%d",
                ticker, tag, v["decision"], v["score"],
                v["rv"], v["iv"], v["vol_spread"], len(result["contracts"])
            )
        else:
            log.warning("  ✗ %s | No result (synthetic data failure)", ticker)

    conn.close()

    vms_df = (
        pd.DataFrame(vms_summary).sort_values("score", ascending=False).reset_index(drop=True)
        if vms_summary else pd.DataFrame()
    )
    contracts_df = (
        pd.DataFrame(all_contracts).sort_values("olis_score", ascending=False).reset_index(drop=True)
        if all_contracts else pd.DataFrame()
    )

    # Validation assertions — confirm engine is working
    log.info("")
    log.info("TEST VALIDATION:")
    passed = failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            log.info("  ✅ PASS  %s%s", name, f" ({detail})" if detail else "")
            passed += 1
        else:
            log.warning("  ❌ FAIL  %s%s", name, f" ({detail})" if detail else "")
            failed += 1

    check("VMS scores computed for all tickers",   len(vms_df) == len(TEST_UNIVERSE))
    check("At least one GO or PROBE signal",        not vms_df.empty and vms_df["decision"].isin(["GO","PROBE"]).any())
    check("Contracts produced for GO/PROBE",        len(contracts_df) > 0)
    check("iv_rank_source = TEST_SYNTHETIC",        not vms_df.empty and (vms_df["iv_rank_source"] == "TEST_SYNTHETIC").all())
    check("vol_spread computed",                    not vms_df.empty and vms_df["vol_spread"].notna().all())
    check("pipeline_tag assigned",                  not vms_df.empty and vms_df["pipeline_tag"].notna().all())
    check("contract_score > 0",                     not contracts_df.empty and (contracts_df["olis_score"] > 0).all())
    check("DTE within 7-60 range",                  not contracts_df.empty and contracts_df["dte"].between(7,60).all())
    check("spread_pct <= 15%",                      not contracts_df.empty and (contracts_df["spread_pct"] <= 15.0).all())

    log.info("")
    log.info("TEST RESULT: %d passed / %d failed", passed, failed)
    if failed == 0:
        log.info("✅ ALL TESTS PASSED — scanner engine is working correctly")
        log.info("   Run --validate to test orchestrator Phase 0 handshake:")
        log.info("   python intelligent_orchestrator.py --validate --run-id <run_id>")
    else:
        log.warning("⚠️  %d test(s) FAILED — review scanner logic before production run", failed)

    return contracts_df, vms_df

# ============================================================
# LOGGING
# ============================================================
LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOGS_DIR / f"universe_scanner_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
log = logging.getLogger("AVS-SCANNER")

# ============================================================
# IV HISTORY CACHE — SQLite
# Stores weekly ATM IV samples per ticker.
# Cold start: 52 weeks × ticker (one-time credit cost).
# Warm run: only fetches trailing week (~2 credits per ticker).
# ============================================================

def init_iv_cache() -> sqlite3.Connection:
    """Initialise IV cache database. Creates tables if absent."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(IV_CACHE_DB), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            ticker      TEXT    NOT NULL,
            sample_date TEXT    NOT NULL,   -- YYYY-MM-DD
            atm_iv      REAL,               -- ATM implied volatility
            source      TEXT    DEFAULT 'marketdata',
            updated_at  TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, sample_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iv_cache_meta (
            ticker          TEXT PRIMARY KEY,
            last_full_build TEXT,           -- date of last 52-week cold start
            last_refresh    TEXT            -- date of last weekly refresh
        )
    """)
    conn.commit()
    return conn


def get_cached_iv_series(conn: sqlite3.Connection, ticker: str) -> pd.Series:
    """Load cached IV history for a ticker. Returns Series indexed by date."""
    rows = conn.execute(
        "SELECT sample_date, atm_iv FROM iv_history WHERE ticker=? ORDER BY sample_date",
        (ticker,)
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["date", "iv"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["iv"].dropna()


def needs_cold_start(conn: sqlite3.Connection, ticker: str) -> bool:
    """True if ticker has no cache or last full build was > IV_CACHE_MAX_AGE_DAYS ago."""
    row = conn.execute(
        "SELECT last_full_build FROM iv_cache_meta WHERE ticker=?", (ticker,)
    ).fetchone()
    if not row or not row[0]:
        return True
    last = datetime.fromisoformat(row[0]).date()
    return (date.today() - last).days > IV_CACHE_MAX_AGE_DAYS * 7  # rebuild monthly


def needs_refresh(conn: sqlite3.Connection, ticker: str) -> bool:
    """True if no refresh this week."""
    row = conn.execute(
        "SELECT last_refresh FROM iv_cache_meta WHERE ticker=?", (ticker,)
    ).fetchone()
    if not row or not row[0]:
        return True
    last = datetime.fromisoformat(row[0]).date()
    return (date.today() - last).days >= IV_RANK_SAMPLE_DAYS


def upsert_iv_records(conn: sqlite3.Connection, ticker: str,
                      records: list, is_cold_start: bool = False) -> None:
    """Write IV records to cache. records = [(date_str, iv_float), ...]"""
    conn.executemany(
        "INSERT OR REPLACE INTO iv_history (ticker, sample_date, atm_iv) VALUES (?,?,?)",
        [(ticker, d, iv) for d, iv in records]
    )
    today_str = date.today().isoformat()
    if is_cold_start:
        conn.execute(
            """INSERT OR REPLACE INTO iv_cache_meta (ticker, last_full_build, last_refresh)
               VALUES (?, ?, ?)""",
            (ticker, today_str, today_str)
        )
    else:
        conn.execute(
            """INSERT OR REPLACE INTO iv_cache_meta (ticker, last_full_build, last_refresh)
               VALUES (?, COALESCE((SELECT last_full_build FROM iv_cache_meta WHERE ticker=?), ?), ?)""",
            (ticker, ticker, today_str, today_str)
        )
    conn.commit()


# ============================================================
# MARKETDATA.APP API
# ============================================================

def marketdata_get(url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
    """MarketData.app API call with retry."""
    headers = {"Authorization": f"Bearer {MARKETDATA_API_KEY}"}
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                wait = 5 * (attempt + 1)
                log.warning(f"MarketData rate limit — sleeping {wait}s")
                time.sleep(wait)
            elif r.status_code == 402:
                log.warning("MarketData: credit limit reached for today")
                return None
            elif r.status_code == 404:
                return None
            else:
                log.debug(f"MarketData HTTP {r.status_code}: {url[:70]}")
                return None
        except requests.exceptions.Timeout:
            time.sleep(0.5)
        except Exception as e:
            log.debug(f"MarketData error: {e}")
            return None
    return None


def fetch_atm_iv_marketdata(ticker: str, query_date: str, spot: float) -> Optional[float]:
    """
    Fetch ATM IV for a ticker on a specific date from MarketData.app.
    Uses the option chain endpoint filtered to 30 DTE ± 7 days,
    nearest-to-spot strike, call side only.
    Costs 1 credit per contract returned (we limit to 2 strikes).

    query_date: YYYY-MM-DD
    Returns: ATM IV float or None if unavailable.
    """
    # Target expiry: ~30 DTE from query_date
    q_date    = datetime.strptime(query_date, "%Y-%m-%d").date()
    exp_from  = (q_date + timedelta(days=23)).isoformat()
    exp_to    = (q_date + timedelta(days=37)).isoformat()

    url = f"https://api.marketdata.app/v1/options/chain/{ticker}/"
    params = {
        "expiration":   exp_from,    # nearest expiry >= exp_from
        "dte":          30,
        "side":         "call",
        "strikeLimit":  2,           # only 2 strikes nearest ATM = 2 credits
        "date":         query_date,
        "columns":      "optionSymbol,strike,iv",
    }

    data = marketdata_get(url, params)
    if not data or data.get("s") != "ok":
        return None

    iv_list     = data.get("iv", [])
    strike_list = data.get("strike", [])

    if not iv_list or not strike_list:
        return None

    # Find nearest-to-spot strike
    best_iv     = None
    best_dist   = float("inf")
    for strike, iv in zip(strike_list, iv_list):
        if iv is None:
            continue
        dist = abs(float(strike) - spot)
        if dist < best_dist:
            best_dist = dist
            best_iv   = float(iv)

    return best_iv


def build_iv_history_marketdata(ticker: str, spot: float,
                                conn: sqlite3.Connection,
                                cold_start: bool = False) -> pd.Series:
    """
    Build or refresh IV history for a ticker using MarketData.app.

    Cold start: fetches IV_RANK_WEEKS weekly samples going back 52 weeks.
    Warm refresh: fetches only the trailing IV_RANK_SAMPLE_DAYS period.

    Stores results in SQLite IV cache.
    Returns full IV series (including cached history).
    """
    today      = date.today()
    records    = []
    credit_cost = 0

    if cold_start:
        # Weekly samples back 52 weeks
        sample_dates = [
            (today - timedelta(weeks=w)).isoformat()
            for w in range(IV_RANK_WEEKS)
        ]
        log.debug(f"  {ticker}: IV cold start — {len(sample_dates)} weekly samples")
    else:
        # Only the trailing week
        sample_dates = [today.isoformat()]
        log.debug(f"  {ticker}: IV warm refresh — 1 sample")

    for d_str in sample_dates:
        iv = fetch_atm_iv_marketdata(ticker, d_str, spot)
        if iv is not None:
            records.append((d_str, iv))
            credit_cost += 2  # ~2 per call (2 strikes returned)
        time.sleep(0.1)  # gentle pacing

    if records:
        upsert_iv_records(conn, ticker, records, is_cold_start=cold_start)
        log.debug(f"  {ticker}: {len(records)} IV records cached (credits used: ~{credit_cost})")

    return get_cached_iv_series(conn, ticker)


def get_iv_series(ticker: str, spot: float, conn: sqlite3.Connection) -> pd.Series:
    """
    Return IV history series for a ticker, using cache intelligently.
    Falls back to empty series if MarketData unavailable.
    """
    if MARKETDATA_API_KEY == "YOUR_MARKETDATA_API_KEY":
        return pd.Series(dtype=float)  # no key — caller uses RV proxy fallback

    cold = needs_cold_start(conn, ticker)
    warm = needs_refresh(conn, ticker)

    if cold:
        return build_iv_history_marketdata(ticker, spot, conn, cold_start=True)
    elif warm:
        return build_iv_history_marketdata(ticker, spot, conn, cold_start=False)
    else:
        return get_cached_iv_series(conn, ticker)


# ============================================================
# POLYGON API
# ============================================================

def polygon_get(url: str, retries: int = 3) -> Optional[dict]:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=12)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                wait = 3 * (attempt + 1)
                log.warning(f"Polygon rate limit — sleeping {wait}s")
                time.sleep(wait)
            elif r.status_code == 403:
                log.debug(f"Polygon 403: {url[:70]}")
                return None
            else:
                log.debug(f"Polygon HTTP {r.status_code}: {url[:70]}")
                return None
        except requests.exceptions.Timeout:
            time.sleep(0.5)
        except Exception as e:
            log.debug(f"Polygon error: {e}")
            return None
    return None


def fetch_price_data(ticker: str) -> Optional[dict]:
    end_date   = datetime.today()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start_date.date()}/{end_date.date()}"
        f"?adjusted=true&sort=asc&limit=200&apiKey={POLYGON_API_KEY}"
    )
    data = polygon_get(url)
    if not data or "results" not in data or len(data["results"]) < RV_WINDOW + 5:
        return None

    df            = pd.DataFrame(data["results"])
    df["date"]    = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    df["returns"] = np.log(df["c"] / df["c"].shift(1))
    df["rv"]      = df["returns"].rolling(RV_WINDOW).std() * np.sqrt(252)
    df["atr"]     = (df["c"] - df["c"].shift(1)).abs().rolling(14).mean()
    atr_pct       = df["atr"].rank(pct=True).iloc[-1]
    rv_val        = df["rv"].iloc[-1]

    if pd.isna(rv_val):
        return None

    close        = df["c"]
    spot         = float(close.iloc[-1])

    # ── Direction signals — required by VMS direction voting ─────────────────
    # Momentum: 20-day log return (was silently missing → all votes = 0/0 → NEUTRAL)
    momentum_20d = float(np.log(close.iloc[-1] / close.iloc[-21])) if len(close) >= 21 else 0.0

    # Moving averages
    ma20         = float(close.rolling(20).mean().iloc[-1])  if len(close) >= 20 else spot
    ma50         = float(close.rolling(50).mean().iloc[-1])  if len(close) >= 50 else spot
    above_ma20   = bool(spot > ma20)
    above_ma50   = bool(spot > ma50)

    # RSI-14
    delta_c      = close.diff()
    gain         = delta_c.clip(lower=0).rolling(14).mean()
    loss         = (-delta_c.clip(upper=0)).rolling(14).mean()
    rs           = gain / loss.replace(0, np.nan)
    rsi_series   = 100 - (100 / (1 + rs))
    rsi_14       = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    return {
        "spot":         spot,
        "rv":           float(rv_val),
        "rv_series":    df["rv"].dropna(),
        "compression":  bool(atr_pct < 0.25),
        "expansion":    bool(atr_pct > 0.75),
        "atr_pct":      round(float(atr_pct), 3),
        # Direction signals — now computed, not silently defaulted
        "momentum_20d": round(momentum_20d, 4),
        "above_ma20":   above_ma20,
        "above_ma50":   above_ma50,
        "rsi_14":       round(rsi_14, 1),
        "ma20":         round(ma20, 4),
        "ma50":         round(ma50, 4),
    }


def fetch_options_chain_marketdata(ticker: str, direction_side: str = "all") -> Optional[list]:
    """
    PRIMARY: Live options chain from MarketData.app.
    direction_side: "call", "put", or "all" — passed directly to MD to reduce credits.
    Returns records in the nested structure process_ticker() expects.
    """
    url    = f"https://api.marketdata.app/v1/options/chain/{ticker}/"
    params = {
        "dte":     f"{MIN_DTE}-{MAX_DTE}",
        "side":    direction_side if direction_side != "all" else None,
        "columns": "optionSymbol,side,strike,expiration,bid,ask,mid,"
                   "openInterest,volume,iv,delta,vega,dte",
    }
    # Remove None params
    params = {k: v for k, v in params.items() if v is not None}

    data = marketdata_get(url, params)
    if not data or data.get("s") != "ok":
        return None

    symbols     = data.get("optionSymbol", [])
    sides       = data.get("side",         [])
    strikes     = data.get("strike",       [])
    expirations = data.get("expiration",   [])
    bids        = data.get("bid",          [])
    asks        = data.get("ask",          [])
    mids        = data.get("mid",          [])
    ois         = data.get("openInterest", [])
    vols        = data.get("volume",       [])
    ivs         = data.get("iv",           [])
    deltas      = data.get("delta",        [])
    vegas       = data.get("vega",         [])

    if not symbols:
        return None

    records = []
    for i in range(len(symbols)):
        try:
            bid = bids[i] if i < len(bids) else None
            ask = asks[i] if i < len(asks) else None
            mid = mids[i] if i < len(mids) else None
            if (bid is None or bid == 0) and mid:
                bid = round(mid * 0.97, 2)
                ask = round(mid * 1.03, 2)
            exp_raw = expirations[i] if i < len(expirations) else None
            if isinstance(exp_raw, (int, float)):
                import datetime as _dt
                exp_str = _dt.datetime.utcfromtimestamp(exp_raw).strftime("%Y-%m-%d")
            else:
                exp_str = str(exp_raw) if exp_raw else None
            records.append({
                "details": {
                    "contract_type":   sides[i]   if i < len(sides)   else None,
                    "strike_price":    strikes[i]  if i < len(strikes)  else None,
                    "expiration_date": exp_str,
                },
                "greeks":     {"delta": deltas[i] if i < len(deltas) else None,
                               "vega":  vegas[i]  if i < len(vegas)  else None},
                "last_quote": {"bid": bid, "ask": ask},
                "implied_volatility": ivs[i] if i < len(ivs) else None,
                "open_interest":      ois[i] if i < len(ois) else None,
                "volume":             vols[i] if i < len(vols) else None,
                "_source": "marketdata",
            })
        except Exception:
            continue

    return records if records else None


def fetch_options_chain(ticker: str, direction_side: str = "all") -> Optional[list]:
    """
    PRIMARY:  MarketData.app — direction-aware, real bid/ask/mid.
    FALLBACK: Polygon snapshot — used if MarketData returns no data.
    """
    if MARKETDATA_API_KEY and MARKETDATA_API_KEY != "YOUR_MARKETDATA_API_KEY":
        result = fetch_options_chain_marketdata(ticker, direction_side)
        if result:
            return result
        log.debug(f"  {ticker}: MarketData chain empty — falling back to Polygon snapshot")

    # Polygon snapshot fallback
    url = (
        f"https://api.polygon.io/v3/snapshot/options/{ticker}"
        f"?limit=250&apiKey={POLYGON_API_KEY}"
    )
    data = polygon_get(url)
    if not data or "results" not in data:
        return None

    results = data["results"]
    while "next_url" in data:
        nxt = polygon_get(f"{data['next_url']}&apiKey={POLYGON_API_KEY}")
        if not nxt or "results" not in nxt:
            break
        results.extend(nxt["results"])
        data = nxt
        time.sleep(CALL_DELAY)

    for r in results:
        r["_source"] = "polygon"
    return results


# ============================================================
# TIER 1 DYNAMIC UNIVERSE BUILDER
# ============================================================

def build_tier1_universe() -> list:
    """
    Pull all active Polygon option contracts in 7-45 DTE window.
    Extract unique underlying tickers — purely market-driven.
    """
    log.info("Tier 1: Querying Polygon for all active options contracts...")

    date_min = (datetime.today() + timedelta(days=MIN_DTE)).date()
    date_max = (datetime.today() + timedelta(days=MAX_DTE)).date()

    url = (
        f"https://api.polygon.io/v3/reference/options/contracts"
        f"?expiration_date.gte={date_min}"
        f"&expiration_date.lte={date_max}"
        f"&expired=false&limit=1000&apiKey={POLYGON_API_KEY}"
    )

    all_contracts = []
    pages, max_pages = 0, 25

    data = polygon_get(url)
    if not data:
        log.error("Tier 1: Polygon options contracts endpoint unreachable")
        return []

    while data and pages < max_pages:
        all_contracts.extend(data.get("results", []))
        pages += 1
        if "next_url" not in data:
            break
        time.sleep(CALL_DELAY)
        data = polygon_get(f"{data['next_url']}&apiKey={POLYGON_API_KEY}")

    log.info(f"Tier 1: {len(all_contracts)} contracts across {pages} pages")

    tickers = sorted({
        c.get("underlying_ticker", "")
        for c in all_contracts
        if c.get("underlying_ticker", "")
        and 1 <= len(c.get("underlying_ticker", "")) <= 5
        and "." not in c.get("underlying_ticker", "")
        and "/" not in c.get("underlying_ticker", "")
        and c.get("underlying_ticker", "").isalpha()
    })

    log.info(f"Tier 1: Dynamic universe = {len(tickers)} unique optionable tickers")
    return tickers


# ============================================================
# VMS SCORING ENGINE — v5.0 with real IV Rank
# ============================================================

def compute_vms(price_data: dict, options_df: pd.DataFrame,
                iv_series: pd.Series) -> Optional[dict]:
    """
    Volatility Mispricing Score (0-100).

    IV Rank source priority:
      1. Real historical IV from MarketData.app (iv_series non-empty) — ~95% confidence
      2. Synthetic proxy RV×1.2 (iv_series empty / API unavailable) — ~65% confidence

    Primary signal: RV > IV = market underpricing actual movement.
    """
    spot        = price_data["spot"]
    rv_current  = price_data["rv"]
    rv_series   = price_data["rv_series"]
    compression = price_data["compression"]

    # ATM IV from Polygon live chain
    options_df["dist"] = (options_df["strike_price"] - spot).abs()
    atm        = options_df.nsmallest(10, "dist")
    iv_current = atm["implied_volatility"].mean()

    if pd.isna(iv_current) or iv_current <= 0:
        return None

    # IV Rank — real vs synthetic
    if len(iv_series) >= 10:
        # Real IV rank from MarketData.app historical data
        iv_min   = iv_series.min()
        iv_max   = iv_series.max()
        iv_rank  = float((iv_current - iv_min) / (iv_max - iv_min)) if iv_max > iv_min else 0.5
        iv_rank_source = "REAL"
        iv_rank_confidence = 0.95
    else:
        # Synthetic proxy fallback
        iv_proxy = rv_series * 1.2
        iv_min   = iv_proxy.min()
        iv_max   = iv_proxy.max()
        iv_rank  = float((iv_current - iv_min) / (iv_max - iv_min)) if iv_max > iv_min else 0.5
        iv_rank_source = "SYNTHETIC"
        iv_rank_confidence = 0.65

    # Term structure
    options_df["dte"] = (options_df["expiration_date"] - datetime.today()).dt.days
    short_iv   = options_df[options_df["dte"] < 14]["implied_volatility"].mean()
    long_iv    = options_df[options_df["dte"] > 30]["implied_volatility"].mean()
    term_slope = float(short_iv - long_iv) if not (pd.isna(short_iv) or pd.isna(long_iv)) else 0.0

    # Skew
    put_iv  = options_df[options_df["contract_type"] == "put"]["implied_volatility"].mean()
    call_iv = options_df[options_df["contract_type"] == "call"]["implied_volatility"].mean()
    skew    = float(put_iv - call_iv) if not (pd.isna(put_iv) or pd.isna(call_iv)) else 0.0

    # Score
    score = 0
    score += 20 if iv_rank < 0.3 else (0 if iv_rank > 0.7 else 10)

    vol_spread     = float(rv_current - iv_current)
    vol_spread_pts = 25 if vol_spread > 0 else 0
    score += vol_spread_pts

    score += 20 if compression else 0
    score += 15 if term_slope >= 0 else 10
    score += 20 if abs(skew) < 0.05 else (10 if skew > 0 else 5)

    decision = (
        "GO"    if score >= VMS_GO_THRESHOLD    else
        "PROBE" if score >= VMS_PROBE_THRESHOLD else
        "WAIT"  if score >= 45                  else
        "BLOCK"
    )

    # Direction voting
    momentum_20d = price_data.get("momentum_20d", 0.0) or 0.0
    above_ma20   = price_data.get("above_ma20", None)
    above_ma50   = price_data.get("above_ma50", None)
    rsi_14       = price_data.get("rsi_14", 50.0) or 50.0

    call_votes = 0; put_votes = 0
    if momentum_20d >  0.03:  call_votes += 2
    elif momentum_20d > 0.0:  call_votes += 1
    elif momentum_20d < -0.03: put_votes += 2
    elif momentum_20d < 0.0:   put_votes += 1
    if above_ma20 is True:  call_votes += 1
    if above_ma20 is False: put_votes  += 1
    if above_ma50 is True:  call_votes += 1
    if above_ma50 is False: put_votes  += 1
    if rsi_14 > 70:  put_votes  += 1
    elif rsi_14 < 30: call_votes += 1
    if skew > 0.05:    call_votes += 1
    elif skew < -0.05: put_votes  += 1
    if compression and momentum_20d >= 0: call_votes += 1
    elif compression:                     put_votes  += 1

    if call_votes > put_votes:
        direction = "CALL"; direction_side = "call"
        direction_reason = f"momentum={momentum_20d:+.1%} rsi={rsi_14:.0f} ma={'above' if above_ma20 else 'below'} votes={call_votes}C/{put_votes}P"
    elif put_votes > call_votes:
        direction = "PUT"; direction_side = "put"
        direction_reason = f"momentum={momentum_20d:+.1%} rsi={rsi_14:.0f} ma={'above' if above_ma20 else 'below'} votes={call_votes}C/{put_votes}P"
    else:
        direction = "NEUTRAL"; direction_side = "all"
        direction_reason = f"tied votes={call_votes}C/{put_votes}P — straddle candidate"

    return {
        "iv":                  round(iv_current, 4),
        "rv":                  round(rv_current, 4),
        "vol_spread":          round(vol_spread, 4),
        "iv_rank":             round(iv_rank, 3),
        "iv_rank_source":      iv_rank_source,
        "iv_rank_confidence":  iv_rank_confidence,
        "iv_history_points":   len(iv_series),
        "term_slope":          round(term_slope, 4),
        "skew":                round(skew, 4),
        "compression":         compression,
        "atr_pct":             price_data["atr_pct"],
        "score":               score,
        "decision":            decision,
        "direction":           direction,
        "direction_side":      direction_side,
        "direction_reason":    direction_reason,
        "momentum_20d":        round(momentum_20d, 4),
        "rsi_14":              round(rsi_14, 1),
        "above_ma20":          above_ma20,
        "above_ma50":          above_ma50,
    }


# ============================================================
# AVSHUNTER OPTIONS LONG INTELLIGENCE SCORE (OLIS)  v7.0
# ============================================================
# Proprietary algorithm. NOT a clone of any retail scanner.
#
# DESIGN PHILOSOPHY
# ─────────────────
# Long options are an asymmetric instrument. A long call or put
# can only lose the premium paid but can return multiples of that.
# The algorithm should therefore reward:
#   (a) Cheap entry — buy vol when it is historically suppressed
#   (b) Correct direction — the move must be aligned with the thesis
#   (c) Room to run — the contract must survive long enough to pay
#   (d) Ticker character fit — the stock's own vol behaviour must
#       justify the DTE and strike chosen
#   (e) Exit readiness — enough market interest to close the trade
#
# ARCHITECTURE
# ────────────
# Three-layer cascade:
#
#   Layer 1 — PRE-SCREEN (binary)
#     Hard elimination before any scoring. Contracts that fail
#     pre-screen are discarded entirely. These protect capital.
#
#   Layer 2 — OLIS COMPOSITE (0-100 weighted score)
#     Five components with proprietary weights:
#       A. VOL MISPRICING INDEX (VMI)     weight=0.30
#          Core edge signal. Uses VMS vol_spread and iv_rank
#          in combination — both must confirm. Single-signal
#          cheapness is penalised.
#       B. DIRECTIONAL CONVICTION (DC)    weight=0.25
#          Multi-signal direction read. Momentum + MA structure
#          + RSI regime + skew surface. Mismatch between contract
#          side and conviction is a hard weight reducer, not a
#          soft penalty.
#       C. CONTRACT FIT SCORE (CFS)       weight=0.20
#          Delta zone, DTE calibrated to the ticker's own RV
#          (high-RV tickers need more DTE to let the move develop),
#          and spread efficiency.
#       D. PAYOFF GEOMETRY (PG)           weight=0.15
#          Breakeven normalised to the ticker's own daily vol
#          (not an absolute % threshold). Computes how many daily
#          expected moves the stock needs to make to profit.
#          A stock that moves 3% daily and needs a 6% move = 2 days.
#          A stock that moves 0.5% daily needing 6% = 12 days.
#          Same absolute % is a very different risk profile.
#       E. MARKET MICROSTRUCTURE (MM)     weight=0.10
#          Execution quality only. Spread tightness and OI depth.
#          Volume purposely de-weighted — high volume on options
#          can signal either smart money OR retail crowding.
#          OI is a better liquidity proxy for long holds.
#
#   Layer 3 — CONVICTION GATE (VMS multiplier)
#     Final score multiplied by VMS quality factor:
#       GO    (VMS ≥75): ×1.00 — full score
#       PROBE (VMS ≥60): ×0.85 — 15% haircut
#       WAIT  (VMS ≥45): ×0.65 — structural weakness
#       BLOCK (VMS <45): contract not processed
#     This means a perfect 100-point contract on a WAIT ticker
#     scores 65 — correctly below PRIME threshold.
#
# VERDICT TAXONOMY
# ────────────────
#   PRIME_LONG  — OLIS ≥ 74  High conviction. Both vol edge and
#                              direction confirmed. Enter now.
#   SETUP_LONG  — OLIS 54-73  Good setup. One dimension weaker.
#                              Valid trade, size smaller.
#   WATCH_LONG  — OLIS 36-53  Thesis forming. Revisit in 1-2 days.
#   PASS        — OLIS < 36   No edge identifiable.
#
# OUTPUT
# ──────
# Per ticker: best matching call + best matching put if both score
# above WATCH_LONG. Otherwise best contract only. Maximum
# MAX_CONTRACTS_PER_TICKER surfaced regardless of verdict.
# All scored contracts retained in full CSV for analysis.
# ============================================================

# ── OLIS thresholds ───────────────────────────────────────────────────────────
PRIME_LONG_THRESHOLD  = 74
SETUP_LONG_THRESHOLD  = 54
WATCH_LONG_THRESHOLD  = 36
MAX_CONTRACTS_PER_TICKER = 2

# ── Component weights (must sum to 1.0) ───────────────────────────────────────
W_VMI = 0.30   # Vol Mispricing Index
W_DC  = 0.25   # Directional Conviction
W_CFS = 0.20   # Contract Fit Score
W_PG  = 0.15   # Payoff Geometry
W_MM  = 0.10   # Market Microstructure

# ── VMS conviction multipliers ────────────────────────────────────────────────
VMS_MULTIPLIER = {"GO": 1.00, "PROBE": 0.85, "WAIT": 0.65, "BLOCK": 0.0}

# ── Pre-screen constants ──────────────────────────────────────────────────────
PS_MAX_IVR         = 0.72   # Never buy when vol already expensive (>72nd percentile)
PS_MIN_OI          = 75     # Minimum OI — below this is untradeable illiquidity
PS_MIN_DTE         = 8      # Theta acceleration below 8 DTE destroys long value
PS_MAX_DTE         = 60     # Beyond 60 DTE the vol mispricing opportunity dissipates
PS_MAX_SPREAD_RAT  = 0.18   # Bid-ask spread > 18% of mid — execution edge destroyed
PS_MIN_PREM        = 0.04   # Minimum mid price — avoids sub-penny noise
PS_MAX_MONEYNESS   = 0.20   # Max distance from spot — beyond 20% OTM is too far
PS_MIN_ABS_DELTA   = 0.08   # Lottery tickets excluded — needs real directional exposure

# ── Daily vol normalisation ───────────────────────────────────────────────────
# Used in Payoff Geometry to express breakeven in "expected daily moves"
# rather than raw percentage.
TRADING_DAYS_YEAR  = 252


def _pre_screen(iv_rank: float, oi: int, dte: int, mid: float,
                spread_ratio: float, moneyness_pct: float,
                abs_delta: float, vms_decision: str) -> Optional[str]:
    """
    Layer 1: Binary pre-screen. Returns rejection reason or None if passes.
    Ordered from cheapest to most expensive check.
    """
    if vms_decision == "BLOCK":
        return "PS_VMS_BLOCK"
    if dte < PS_MIN_DTE:
        return f"PS_THETA_ZONE: DTE={dte}"
    if dte > PS_MAX_DTE:
        return f"PS_DTE_TOO_FAR: DTE={dte}"
    if mid < PS_MIN_PREM:
        return f"PS_SUB_PENNY: mid={mid:.3f}"
    if spread_ratio > PS_MAX_SPREAD_RAT:
        return f"PS_WIDE_SPREAD: {spread_ratio:.1%}"
    if moneyness_pct > PS_MAX_MONEYNESS:
        return f"PS_TOO_FAR_OTM: {moneyness_pct:.1%}"
    if oi < PS_MIN_OI:
        return f"PS_THIN_MARKET: OI={oi}"
    if iv_rank > PS_MAX_IVR:
        return f"PS_EXPENSIVE_VOL: IVR={iv_rank:.2f}"
    if abs_delta < PS_MIN_ABS_DELTA:
        return f"PS_NO_DELTA: |Δ|={abs_delta:.2f}"
    return None


def _component_vmi(iv_contract: float, rv: float,
                   iv_rank: float, iv_rank_source: str,
                   term_slope: float) -> tuple[float, list]:
    """
    Component A — Vol Mispricing Index (VMI).
    Score 0-100. Weighted ×0.30 in composite.

    Requires BOTH iv_rank cheapness AND positive vol spread (RV>IV)
    to score above 60. A contract that is cheap on rank but where
    RV < IV is penalised — the mispricing signal is not confirmed.

    term_slope adds or subtracts based on the vol surface structure.
    A backwardated surface (short IV > long IV, slope > 0) means near-term
    fear is already priced — slightly unfavourable for long premium entry.
    Contango (slope ≤ 0) means longer-dated vol is rich relative to front,
    which is neutral to favourable.
    """
    score   = 0.0
    reasons = []

    vol_spread = rv - iv_contract  # positive = RV > IV = underpriced vol

    # IV Rank component (0-40 pts)
    if iv_rank < 0.15:
        ivr_pts = 40; reasons.append(f"IVR={iv_rank:.2f} extreme cheapness")
    elif iv_rank < 0.25:
        ivr_pts = 32; reasons.append(f"IVR={iv_rank:.2f} historically cheap")
    elif iv_rank < 0.35:
        ivr_pts = 22; reasons.append(f"IVR={iv_rank:.2f} below median")
    elif iv_rank < 0.50:
        ivr_pts = 12
    elif iv_rank < 0.65:
        ivr_pts = 5
    else:
        ivr_pts = 0; reasons.append(f"IVR={iv_rank:.2f} elevated, no rank edge")
    score += ivr_pts

    # Vol spread component (0-45 pts)
    if vol_spread > 0.08:
        vsp_pts = 45; reasons.append(f"RV-IV={vol_spread:+.3f} strong mispricing")
    elif vol_spread > 0.04:
        vsp_pts = 35; reasons.append(f"RV-IV={vol_spread:+.3f} clear edge")
    elif vol_spread > 0.01:
        vsp_pts = 22; reasons.append(f"RV-IV={vol_spread:+.3f} mild edge")
    elif vol_spread > -0.01:
        vsp_pts = 10  # roughly fair value
    elif vol_spread > -0.04:
        vsp_pts = 4
    else:
        vsp_pts = 0; reasons.append(f"IV>RV by {-vol_spread:.3f} vol overpriced")
    score += vsp_pts

    # Dual-confirmation bonus: both signals pointing same direction
    # Reward is non-linear — both cheap = more than sum of parts
    if ivr_pts >= 22 and vsp_pts >= 22:
        score += 10; reasons.append("dual-confirm: rank+spread both positive")
    elif ivr_pts == 0 and vsp_pts == 0:
        score -= 5  # both negative = compounding weakness

    # Real IV rank quality bonus
    if iv_rank_source == "REAL":
        score += 5; reasons.append("real IV rank (95% conf)")

    # Term structure modifier (±5 pts)
    if term_slope > 0.03:
        score -= 5; reasons.append(f"backwardation: near fear priced in")
    elif term_slope < -0.02:
        score += 5; reasons.append(f"contango: front vol cheap vs back")

    return min(100.0, max(0.0, score)), reasons


def _component_dc(contract_type: str, direction: str,
                  momentum_20d: float, rsi_14: float,
                  above_ma20: bool, above_ma50: bool,
                  skew: float, compression: bool) -> tuple[float, list]:
    """
    Component B — Directional Conviction (DC).
    Score 0-100. Weighted ×0.25 in composite.

    Direction mismatch between contract side and VMS thesis is not
    a soft penalty — it is a hard multiplier of 0.30. A CALL when
    the thesis is PUT cannot score above 30/100 on this component
    regardless of other signals. This enforces discipline: don't
    buy the wrong side just because vol is cheap.
    """
    score   = 0.0
    reasons = []
    ctype   = contract_type.lower() if contract_type else ""

    # Direction alignment multiplier
    if direction == "CALL" and ctype == "call":
        dir_mult = 1.0; reasons.append("thesis CALL ✓")
    elif direction == "PUT" and ctype == "put":
        dir_mult = 1.0; reasons.append("thesis PUT ✓")
    elif direction == "NEUTRAL":
        dir_mult = 0.70; reasons.append("neutral: half-weight both sides")
    else:
        dir_mult = 0.25; reasons.append(f"mismatch: thesis={direction} contract={ctype}")

    # Momentum signal (0-30 pts before multiplier)
    if ctype == "call":
        if momentum_20d > 0.06:
            mom_pts = 30; reasons.append(f"momentum={momentum_20d:+.1%} strong bull")
        elif momentum_20d > 0.02:
            mom_pts = 20; reasons.append(f"momentum={momentum_20d:+.1%} bull")
        elif momentum_20d > 0.0:
            mom_pts = 10
        elif momentum_20d > -0.02:
            mom_pts = 3
        else:
            mom_pts = 0
    else:  # put
        if momentum_20d < -0.06:
            mom_pts = 30; reasons.append(f"momentum={momentum_20d:+.1%} strong bear")
        elif momentum_20d < -0.02:
            mom_pts = 20; reasons.append(f"momentum={momentum_20d:+.1%} bear")
        elif momentum_20d < 0.0:
            mom_pts = 10
        elif momentum_20d < 0.02:
            mom_pts = 3
        else:
            mom_pts = 0
    score += mom_pts

    # MA structure (0-25 pts) — trend regime confirmation
    if ctype == "call":
        if above_ma20 and above_ma50:
            score += 25; reasons.append("above MA20+MA50 bull regime")
        elif above_ma20:
            score += 15; reasons.append("above MA20")
        elif above_ma50:
            score += 8
        else:
            score += 0
    else:  # put
        if not above_ma20 and not above_ma50:
            score += 25; reasons.append("below MA20+MA50 bear regime")
        elif not above_ma20:
            score += 15; reasons.append("below MA20")
        elif not above_ma50:
            score += 8
        else:
            score += 0

    # RSI regime (0-20 pts) — mean reversion context
    if ctype == "call":
        if rsi_14 < 30:
            score += 20; reasons.append(f"RSI={rsi_14:.0f} oversold reversal setup")
        elif rsi_14 < 40:
            score += 12; reasons.append(f"RSI={rsi_14:.0f} depressed")
        elif rsi_14 < 55:
            score += 5  # neutral range
        elif rsi_14 > 70:
            score -= 5  # overbought, buying calls here is late
    else:  # put
        if rsi_14 > 70:
            score += 20; reasons.append(f"RSI={rsi_14:.0f} overbought reversal setup")
        elif rsi_14 > 60:
            score += 12; reasons.append(f"RSI={rsi_14:.0f} elevated")
        elif rsi_14 > 45:
            score += 5
        elif rsi_14 < 30:
            score -= 5  # oversold, buying puts here is late

    # Skew surface tells us which side the market is hedging
    # Positive skew = put_iv > call_iv = downside fear in market
    # Buying puts when fear is already priced in REDUCES edge (you're buying expensive)
    # Buying calls when fear exists = cheap relative to put side (structural edge)
    if ctype == "call" and skew > 0.05:
        score += 10; reasons.append(f"skew={skew:.3f}: calls cheap vs puts")
    elif ctype == "call" and skew < -0.05:
        score -= 5; reasons.append(f"skew={skew:.3f}: call premium elevated")
    elif ctype == "put" and skew < -0.05:
        score += 10; reasons.append(f"skew={skew:.3f}: puts cheap vs calls")
    elif ctype == "put" and skew > 0.08:
        score -= 8; reasons.append(f"skew={skew:.3f}: put fear premium already priced")

    # Compression: coiled spring — vol breakout likely, direction matters
    if compression:
        if ctype == "call" and above_ma20:
            score += 8; reasons.append("compression + bull trend: breakout setup")
        elif ctype == "put" and not above_ma20:
            score += 8; reasons.append("compression + bear trend: breakdown setup")
        else:
            score += 3  # compressed but direction ambiguous

    # Apply direction multiplier to entire score
    score = score * dir_mult

    return min(100.0, max(0.0, score)), reasons


def _component_cfs(abs_delta: float, dte: int,
                   spread_pct: float, rv: float) -> tuple[float, list]:
    """
    Component C — Contract Fit Score (CFS).
    Score 0-100. Weighted ×0.20 in composite.

    DTE is calibrated to the ticker's own realised volatility.
    A high-RV stock (daily move ~2%) needs fewer DTE to develop a
    thesis. A low-RV stock (daily move ~0.3%) needs more runway.
    Calibration: target_dte = (1 / daily_rv) × 5 — this gives roughly
    the number of days needed to see 5 standard deviations of movement,
    which is where most long option profits crystallise.
    """
    score   = 0.0
    reasons = []

    # Delta zone (0-40 pts)
    # Proprietary zones based on expected directional payoff efficiency:
    # 0.30-0.45 is the AVSHUNTER sweet spot: enough delta to profit from
    # directional move, cheap enough to buy in size.
    # Very deep ITM is capital inefficient for long options strategy.
    if 0.30 <= abs_delta <= 0.45:
        score += 40; reasons.append(f"|Δ|={abs_delta:.2f} OLIS sweet spot")
    elif 0.45 < abs_delta <= 0.55:
        score += 32; reasons.append(f"|Δ|={abs_delta:.2f} near ATM")
    elif 0.20 <= abs_delta < 0.30:
        score += 22; reasons.append(f"|Δ|={abs_delta:.2f} OTM leverage play")
    elif 0.55 < abs_delta <= 0.70:
        score += 18; reasons.append(f"|Δ|={abs_delta:.2f} ITM capital heavy")
    elif abs_delta > 0.70:
        score += 8; reasons.append(f"|Δ|={abs_delta:.2f} deep ITM: stock substitute")
    else:
        score += 5

    # DTE calibrated to ticker RV (0-40 pts)
    daily_rv     = rv / np.sqrt(TRADING_DAYS_YEAR)
    target_dte   = int(5 / daily_rv) if daily_rv > 0 else 30  # days for 5σ moves
    target_dte   = max(14, min(target_dte, 55))  # clamp 14-55
    dte_gap      = abs(dte - target_dte)

    if dte_gap <= 5:
        score += 40; reasons.append(f"DTE={dte} optimal for RV={rv:.3f} (target={target_dte})")
    elif dte_gap <= 10:
        score += 30; reasons.append(f"DTE={dte} near optimal (target={target_dte})")
    elif dte_gap <= 18:
        score += 18
    elif dte_gap <= 25:
        score += 8
    else:
        score += 0; reasons.append(f"DTE={dte} far from optimal (target={target_dte})")

    # Spread efficiency (0-20 pts)
    if spread_pct < 2.0:
        score += 20; reasons.append(f"spread={spread_pct:.1f}% tight")
    elif spread_pct < 4.0:
        score += 15
    elif spread_pct < 7.0:
        score += 9
    elif spread_pct < 10.0:
        score += 4
    else:
        score += 0; reasons.append(f"spread={spread_pct:.1f}% wide")

    return min(100.0, max(0.0, score)), reasons


def _component_pg(ask: float, strike: float, spot: float,
                  contract_type: str, rv: float,
                  dte: int) -> tuple[float, list, float, float]:
    """
    Component D — Payoff Geometry (PG).
    Score 0-100. Weighted ×0.15 in composite.

    Core insight: breakeven % means nothing in isolation.
    A 5% required move is trivial for TSLA (daily σ ~2.8%) but
    heroic for KO (daily σ ~0.5%). OLIS expresses breakeven in
    units of the ticker's own expected daily move (σ-normalised),
    giving a universal scale across all tickers.

    Also computes premium-to-expected-move ratio: how many days of
    maximum expected profit are you paying for upfront? Lower is better.
    """
    score   = 0.0
    reasons = []
    ctype   = contract_type.lower() if contract_type else ""

    # Breakeven price and % from spot
    if ctype == "call":
        be_price = strike + ask
        be_pct   = (be_price - spot) / spot * 100
    else:
        be_price = strike - ask
        be_pct   = (spot - be_price) / spot * 100
    be_pct = max(be_pct, 0.0)

    # Daily vol normalisation
    daily_rv      = rv / np.sqrt(TRADING_DAYS_YEAR)
    be_in_sigma   = (be_pct / 100) / daily_rv if daily_rv > 0 else 999.0

    # Score on σ-normalised breakeven (0-55 pts)
    # Interpretation: be_in_sigma = how many daily expected moves to break even
    if be_in_sigma < 1.0:
        score += 55; reasons.append(f"BE={be_pct:.1f}% = {be_in_sigma:.1f}σ <1day move")
    elif be_in_sigma < 2.0:
        score += 42; reasons.append(f"BE={be_pct:.1f}% = {be_in_sigma:.1f}σ ~2day move")
    elif be_in_sigma < 3.5:
        score += 28; reasons.append(f"BE={be_pct:.1f}% = {be_in_sigma:.1f}σ ~3-4day move")
    elif be_in_sigma < 5.0:
        score += 16; reasons.append(f"BE={be_pct:.1f}% = {be_in_sigma:.1f}σ ~week move")
    elif be_in_sigma < 8.0:
        score += 6
    else:
        score += 0; reasons.append(f"BE={be_pct:.1f}% = {be_in_sigma:.1f}σ: unlikely to reach")

    # Premium as % of underlying (0-30 pts) — cost efficiency
    pct_premium = ask / spot * 100 if spot > 0 else 999.0
    if pct_premium < 0.25:
        score += 30; reasons.append(f"prem={pct_premium:.2f}% of stock: very cheap")
    elif pct_premium < 0.6:
        score += 22
    elif pct_premium < 1.2:
        score += 14
    elif pct_premium < 2.5:
        score += 7
    elif pct_premium < 5.0:
        score += 2
    else:
        score += 0; reasons.append(f"prem={pct_premium:.2f}% expensive relative to stock")

    # Time-adjusted R:R (0-15 pts)
    # How much can this contract gain if spot moves 2× its expected DTE range?
    expected_move_to_exp = daily_rv * np.sqrt(dte) * spot
    target_payoff = max(0, expected_move_to_exp - ask * 2)
    # Rough R:R at 1× expected move: payoff / cost
    payoff_1x = max(0, (daily_rv * spot) - ask)
    rr_1x     = payoff_1x / ask if ask > 0 else 0.0
    if rr_1x > 1.5:
        score += 15; reasons.append(f"R:R={rr_1x:.1f}:1 at 1× expected move")
    elif rr_1x > 0.8:
        score += 9
    elif rr_1x > 0.3:
        score += 4

    return min(100.0, max(0.0, score)), reasons, round(be_pct, 3), round(pct_premium, 3)


def _component_mm(oi: int, spread_pct: float) -> tuple[float, list]:
    """
    Component E — Market Microstructure (MM).
    Score 0-100. Weighted ×0.10 in composite.

    Execution quality focus only. Volume deliberately excluded from
    this component — high option volume can be noise, retail crowding,
    or smart money. OI is a more stable liquidity measure for multi-day
    holds. Absolute OI matters more than relative Vol/OI for long trades.
    """
    score   = 0.0
    reasons = []

    # OI depth (0-65 pts)
    if oi >= 10000:
        score += 65; reasons.append(f"OI={oi:,} deep market")
    elif oi >= 5000:
        score += 52
    elif oi >= 2000:
        score += 40; reasons.append(f"OI={oi:,} liquid")
    elif oi >= 1000:
        score += 30
    elif oi >= 500:
        score += 18
    elif oi >= 200:
        score += 10
    else:
        score += 3; reasons.append(f"OI={oi} thin market")

    # Spread tightness (0-35 pts) — direct measure of execution cost
    if spread_pct < 1.5:
        score += 35; reasons.append(f"spread={spread_pct:.1f}% institutional tight")
    elif spread_pct < 3.0:
        score += 28
    elif spread_pct < 5.0:
        score += 20
    elif spread_pct < 8.0:
        score += 12
    elif spread_pct < 12.0:
        score += 5
    else:
        score += 0; reasons.append(f"spread={spread_pct:.1f}% execution drag")

    return min(100.0, max(0.0, score)), reasons


def score_long_contracts(ticker: str, options_df: pd.DataFrame,
                          spot: float, vms: dict) -> list:
    """
    AVSHUNTER OLIS — Options Long Intelligence Score.
    Evaluates every pre-screened contract through 5 proprietary
    components, applies VMS conviction multiplier, assigns verdict.
    Returns top MAX_CONTRACTS_PER_TICKER contracts.
    """
    today          = datetime.today()
    direction      = vms.get("direction",      "NEUTRAL")
    vms_decision   = vms.get("decision",       "BLOCK")
    iv_rank        = vms.get("iv_rank",         0.5)
    iv_rank_source = vms.get("iv_rank_source", "SYNTHETIC")
    rv             = vms.get("rv",              0.0)
    iv             = vms.get("iv",              0.0)
    term_slope     = vms.get("term_slope",      0.0)
    rsi_14         = vms.get("rsi_14",         50.0) or 50.0
    momentum_20d   = vms.get("momentum_20d",    0.0) or 0.0
    above_ma20     = vms.get("above_ma20",     False) or False
    above_ma50     = vms.get("above_ma50",     False) or False
    skew           = vms.get("skew",            0.0)
    compression    = vms.get("compression",    False)
    vms_score      = vms.get("score",            0)

    vms_mult = VMS_MULTIPLIER.get(vms_decision, 0.0)

    # BLOCK: skip contract scoring entirely — save CPU
    if vms_mult == 0.0:
        return []

    scored      = []
    ps_rejected = {}
    filt_rej    = {"no_bid": 0, "dte": 0, "moneyness": 0,
                   "spread": 0, "prem": 0, "no_iv": 0}

    for _, row in options_df.iterrows():
        try:
            ctype  = str(row.get("contract_type", "")).lower()
            bid    = row.get("bid",   np.nan)
            ask    = row.get("ask",   np.nan)

            if pd.isna(bid) or pd.isna(ask) or ask <= 0 or bid < 0:
                filt_rej["no_bid"] += 1; continue

            mid        = (bid + ask) / 2.0
            spread     = (ask - bid) / mid if mid > 0 else 1.0
            spread_pct = spread * 100.0
            strike     = float(row["strike_price"])
            dte        = int((row["expiration_date"] - today).days)
            iv_c       = float(row.get("implied_volatility", np.nan))
            oi         = int(row.get("open_interest", 0) or 0)
            volume     = row.get("volume")
            volume     = int(volume) if volume is not None and not pd.isna(volume) else None
            delta      = row.get("delta")
            delta      = float(delta) if delta is not None and not pd.isna(delta) else None
            vega       = row.get("vega")
            abs_delta  = abs(delta) if delta is not None else 0.0
            moneyness  = abs(strike - spot) / spot

            if pd.isna(iv_c) or iv_c <= 0:
                filt_rej["no_iv"] += 1; continue

            # Layer 1: Pre-screen
            ps_result = _pre_screen(
                iv_rank, oi, dte, mid, spread, moneyness, abs_delta, vms_decision
            )
            if ps_result:
                ps_rejected[ps_result] = ps_rejected.get(ps_result, 0) + 1
                continue

            # Layer 2: Five-component OLIS scoring
            a_score, a_reasons = _component_vmi(
                iv_c, rv, iv_rank, iv_rank_source, term_slope
            )
            b_score, b_reasons = _component_dc(
                ctype, direction, momentum_20d, rsi_14,
                above_ma20, above_ma50, skew, compression
            )
            c_score, c_reasons = _component_cfs(abs_delta, dte, spread_pct, rv)

            d_score, d_reasons, be_pct, pct_prem = _component_pg(
                ask, strike, spot, ctype, rv, dte
            )
            e_score, e_reasons = _component_mm(oi, spread_pct)

            # Weighted composite (0-100)
            raw_olis = (
                a_score * W_VMI +
                b_score * W_DC  +
                c_score * W_CFS +
                d_score * W_PG  +
                e_score * W_MM
            )

            # Layer 3: VMS conviction multiplier
            olis = raw_olis * vms_mult

            # Spread execution penalty (applied after multiplier)
            if spread_pct > 10.0:
                olis = max(0.0, olis - 6.0)

            olis = round(olis, 2)

            # Verdict
            if olis >= PRIME_LONG_THRESHOLD:
                verdict = "PRIME_LONG"
            elif olis >= SETUP_LONG_THRESHOLD:
                verdict = "SETUP_LONG"
            elif olis >= WATCH_LONG_THRESHOLD:
                verdict = "WATCH_LONG"
            else:
                verdict = "PASS"

            if verdict == "PASS":
                continue

            be_price = round(strike + ask, 4) if ctype == "call" else round(strike - ask, 4)

            daily_rv_val = rv / np.sqrt(TRADING_DAYS_YEAR) if rv > 0 else 0.001
            be_sigma     = round((be_pct / 100) / daily_rv_val, 2)

            component_breakdown = {
                "VMI": round(a_score, 1),
                "DC":  round(b_score, 1),
                "CFS": round(c_score, 1),
                "PG":  round(d_score, 1),
                "MM":  round(e_score, 1),
                "raw": round(raw_olis, 2),
                "vms_mult": vms_mult,
            }

            top_reasons = (a_reasons + b_reasons + c_reasons + d_reasons + e_reasons)[:7]

            scored.append({
                # Identity
                "ticker":           ticker,
                "type":             ctype,
                "strike":           strike,
                "expiry":           row["expiration_date"].strftime("%Y-%m-%d"),
                "dte":              dte,
                # OLIS verdict
                "olis_score":       olis,
                "olis_verdict":     verdict,
                "olis_direction":   direction,
                "olis_components":  json.dumps(component_breakdown),
                "olis_reasons":     " | ".join(top_reasons),
                # Price
                "spot":             round(spot, 4),
                "bid":              round(float(bid), 2),
                "ask":              round(float(ask), 2),
                "mid":              round(float(mid), 2),
                # Payoff geometry (key economics)
                "be_price":         be_price,
                "be_pct":           be_pct,           # % move to breakeven
                "be_sigma":         be_sigma,          # breakeven in σ-normalised daily moves
                "pct_premium":      pct_prem,          # ask as % of underlying
                # Greeks
                "delta":            round(delta, 4) if delta is not None else None,
                "vega":             round(float(vega), 4) if vega is not None and not pd.isna(vega) else None,
                # Vol intelligence
                "iv":               round(iv_c, 4),
                "iv_rank":          iv_rank,
                "iv_rank_source":   iv_rank_source,
                "rv":               round(rv, 4),
                "vol_spread":       round(rv - iv_c, 4),
                "term_slope":       round(term_slope, 4),
                # Market microstructure
                "spread_pct":       round(spread_pct, 2),
                "spread_warn":      spread_pct > 10.0,
                "open_interest":    oi,
                "contract_volume":  volume,
                "moneyness_pct":    round(moneyness * 100, 2),
                # VMS context
                "vms_score":        vms_score,
                "vms_gate":         vms_decision,
                "vms_mult":         vms_mult,
                "rsi_14":           round(rsi_14, 1),
                "momentum_20d":     round(momentum_20d, 4),
                "compression":      compression,
                # Tagging (populated by caller)
                "pipeline_tag":     None,
                "tier":             None,
            })

        except Exception as e:
            log.debug(f"  {ticker} OLIS scoring error: {e}")
            continue

    if not scored:
        ps_str = " ".join(f"{k}×{v}" for k, v in ps_rejected.items()) if ps_rejected else "none"
        log.debug(
            f"  {ticker}: 0 OLIS contracts from {len(options_df)} chain rows | "
            f"filt(dte={filt_rej['dte']} mon={filt_rej['moneyness']} "
            f"sprd={filt_rej['spread']} prem={filt_rej['prem']}) | "
            f"prescreen: {ps_str}"
        )
        return []

    # Sort by OLIS score descending
    scored.sort(key=lambda x: x["olis_score"], reverse=True)

    # Selection logic:
    # For PRIME tickers: surface best call + best put if both qualify above WATCH
    prime = [c for c in scored if c["olis_verdict"] == "PRIME_LONG"]
    if len(prime) >= 2:
        prime_calls = [c for c in prime if c["type"] == "call"]
        prime_puts  = [c for c in prime if c["type"] == "put"]
        if prime_calls and prime_puts:
            top = [prime_calls[0], prime_puts[0]][:MAX_CONTRACTS_PER_TICKER]
            return top

    return scored[:MAX_CONTRACTS_PER_TICKER]


# ── Backwards-compat alias ────────────────────────────────────────────────────
def scan_contracts(ticker, options_df, spot, vms):
    """Deprecated alias → score_long_contracts / OLIS engine."""
    return score_long_contracts(ticker, options_df, spot, vms)




# ============================================================
# PER-TICKER PIPELINE
# ============================================================

def process_ticker(ticker: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Full VMS pipeline for one ticker. Uses both Polygon and MarketData.app."""
    time.sleep(CALL_DELAY)

    price_data = fetch_price_data(ticker)
    if not price_data:
        return None

    # ── STEP 1: Fetch a broad chain first pass (both sides) so VMS can compute
    # direction. Then we keep this chain — fetching twice wastes credits.
    # The direction_side credit optimisation is applied on SUBSEQUENT runs
    # via the direction cache in the manifest. For the current run, fetch all.
    chain = fetch_options_chain(ticker, direction_side="all")
    if not chain:
        return None

    records = []
    for item in chain:
        try:
            d = item.get("details", {})
            g = item.get("greeks", {})
            q = item.get("last_quote", {})
            records.append({
                "contract_type":      d.get("contract_type"),
                "strike_price":       d.get("strike_price"),
                "expiration_date":    pd.to_datetime(d.get("expiration_date")),
                "implied_volatility": item.get("implied_volatility"),
                "bid":                q.get("bid"),
                "ask":                q.get("ask"),
                "open_interest":      item.get("open_interest"),
                "volume":             item.get("volume"),
                "delta":              g.get("delta"),
                "vega":               g.get("vega"),
            })
        except Exception:
            continue

    if not records:
        return None

    options_df = pd.DataFrame(records).dropna(
        subset=["implied_volatility", "strike_price", "expiration_date"]
    )
    if options_df.empty:
        return None

    # Fetch real IV history from MarketData.app (or load from cache)
    iv_series = get_iv_series(ticker, price_data["spot"], conn)

    # ── STEP 2: VMS + direction voting (now has real momentum/RSI/MA inputs)
    vms = compute_vms(price_data, options_df, iv_series)
    if not vms:
        return None

    # ── STEP 3: Score contracts using long-options intelligence layer
    contracts = score_long_contracts(ticker, options_df, price_data["spot"], vms)

    chain_source = chain[0].get("_source", "polygon") if chain else "none"
    return {
        "ticker":       ticker,
        "spot":         round(price_data["spot"], 2),
        "vms":          vms,
        "contracts":    contracts,
        "chain_source": chain_source,
    }


# ============================================================
# PIPELINE UNIVERSE OVERLAP TAGGING
# ============================================================

def load_pipeline_universe() -> set:
    for candidate in [
        PIPELINE_UNIVERSE_FILE,
        Path(__file__).parent / "polygon_liquid_universe.csv",
        BASE_DIR / "polygon_liquid_universe.csv",
    ]:
        if candidate.exists():
            df = pd.read_csv(candidate)
            tickers = set(df.iloc[:, 0].dropna().str.strip().tolist())
            log.info(f"Pipeline universe loaded ({len(tickers)} tickers) for overlap tagging")
            return tickers
    log.warning("Pipeline universe file not found — all results tagged NEW")
    return set()


# ============================================================
# CORE SCAN RUNNER
# ============================================================

def run_scan(universe: list, pipeline_universe: set,
             tier_label: str, top_n: int,
             conn: sqlite3.Connection) -> tuple:
    """Parallel VMS scan across universe. Returns (contracts_df, vms_df)."""
    all_contracts = []
    vms_summary   = []
    processed = errors = 0
    real_iv_count = synthetic_iv_count = 0

    log.info(f"{tier_label}: {len(universe)} tickers | {MAX_WORKERS} threads")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_ticker, t, conn): t for t in universe}

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                processed += 1

                if result:
                    v   = result["vms"]
                    tag = "KNOWN" if ticker in pipeline_universe else "NEW"

                    if v["iv_rank_source"] == "REAL":
                        real_iv_count += 1
                    else:
                        synthetic_iv_count += 1

                    vms_summary.append({
                        "ticker":              ticker,
                        "spot":                result["spot"],
                        "iv":                  v["iv"],
                        "rv":                  v["rv"],
                        "vol_spread":          v["vol_spread"],
                        "iv_rank":             v["iv_rank"],
                        "iv_rank_source":      v["iv_rank_source"],
                        "iv_rank_confidence":  v["iv_rank_confidence"],
                        "iv_history_points":   v["iv_history_points"],
                        "compression":         v["compression"],
                        "term_slope":          v["term_slope"],
                        "skew":                v["skew"],
                        "score":               v["score"],
                        "decision":            v["decision"],
                        "direction":           v.get("direction", "UNKNOWN"),
                        "direction_reason":    v.get("direction_reason", ""),
                        "momentum_20d":        v.get("momentum_20d"),
                        "rsi_14":              v.get("rsi_14"),
                        "above_ma20":          v.get("above_ma20"),
                        "n_contracts":         len(result["contracts"]),
                        "pipeline_tag":        tag,
                        "tier":                tier_label,
                    })

                    if result["contracts"]:
                        for c in result["contracts"]:
                            c["pipeline_tag"] = tag
                            c["tier"]         = tier_label
                        all_contracts.extend(result["contracts"])

                    if v["decision"] in ("GO", "PROBE"):
                        _warn_ct   = sum(1 for c in result["contracts"] if c.get("spread_warn"))
                        _warn_str  = f" ⚠️  {_warn_ct} spread>10%" if _warn_ct else ""
                        _dir       = v.get("direction", "?")
                        _chain_src = result.get("chain_source", "?")
                        log.info(
                            f"  ✓ {ticker:<6} [{tag}] {v['decision']:<5} "
                            f"score={v['score']:3d} | "
                            f"RV={v['rv']:.3f} IV={v['iv']:.3f} "
                            f"spread={v['vol_spread']:+.3f} | "
                            f"IVR={v['iv_rank']:.2f}({v['iv_rank_source']}) | "
                            f"{_dir} chain={_chain_src} | "
                            f"contracts={len(result['contracts'])}{_warn_str}"
                        )
                else:
                    log.debug(f"  {ticker:<6} | No data")

            except Exception as e:
                errors += 1
                log.debug(f"  {ticker:<6} | Error: {e}")

    log.info(
        f"{tier_label}: processed={processed} errors={errors} | "
        f"IV rank sources: REAL={real_iv_count} SYNTHETIC={synthetic_iv_count}"
    )
    if synthetic_iv_count > 0:
        log.warning(
            f"  {synthetic_iv_count} tickers used synthetic IV rank (~65% confidence). "
            f"Run --rebuild-iv-cache to build real IV history."
        )

    vms_df = (
        pd.DataFrame(vms_summary).sort_values("score", ascending=False).reset_index(drop=True)
        if vms_summary else pd.DataFrame()
    )
    contracts_df = (
        pd.DataFrame(all_contracts).sort_values("olis_score", ascending=False).reset_index(drop=True)
        if all_contracts else pd.DataFrame()
    )

    return contracts_df, vms_df


# ============================================================
# IV CACHE REBUILD (standalone cold start)
# ============================================================

def rebuild_iv_cache(universe: list, conn: sqlite3.Connection) -> None:
    """
    Standalone cold-start IV cache builder.
    Pulls 52 weeks of weekly ATM IV for every ticker in universe.
    Run once, then warm refreshes handle daily updates automatically.

    Credit cost estimate: len(universe) × 52 × 2 contracts = credits used.
    For 600 tickers: ~62,400 credits (62% of daily Trader plan budget).
    Run during off-hours or split across multiple days.
    """
    log.info(f"IV Cache Rebuild: {len(universe)} tickers | 52 weekly samples each")
    log.info(f"Estimated credit cost: ~{len(universe) * 52 * 2:,} MarketData credits")
    log.info("Run during off-hours. Split across days if near credit limit.")

    price_cache = {}
    built = skipped = errors = 0

    for i, ticker in enumerate(universe, 1):
        try:
            if not needs_cold_start(conn, ticker):
                log.info(f"  [{i}/{len(universe)}] {ticker}: cache fresh — skipping")
                skipped += 1
                continue

            # Need spot price to find ATM strike
            price_data = fetch_price_data(ticker)
            if not price_data:
                log.debug(f"  [{i}/{len(universe)}] {ticker}: no price data")
                errors += 1
                continue

            spot = price_data["spot"]
            log.info(f"  [{i}/{len(universe)}] {ticker}: cold start (spot={spot:.2f})")

            build_iv_history_marketdata(ticker, spot, conn, cold_start=True)
            built += 1
            time.sleep(0.5)  # respectful pacing

        except Exception as e:
            log.warning(f"  [{i}/{len(universe)}] {ticker}: error — {e}")
            errors += 1

    log.info(f"IV Cache Rebuild complete: built={built} skipped={skipped} errors={errors}")


# ============================================================
# OUTPUT WRITER
# ============================================================

def _scanner_route(vms_score: float, vms_decision: str) -> str:
    """
    L1-CHANGE-3: Primary routing gate — mirrors orchestrator _scanner_route().
    Stamped onto vms_scoreboard CSV so orchestrator + discovery can consume it.
    """
    d = str(vms_decision).upper()
    s = float(vms_score) if vms_score else 0.0
    if d == "GO"    or s >= 75: return "FULL_PIPELINE"
    if d == "PROBE" or s >= 60: return "DISCOVERY_ONLY"
    if d == "WAIT"  or s >= 45: return "WATCHLIST_ONLY"
    return "SCANNER_BLOCKED"


def write_outputs(contracts_df: pd.DataFrame, vms_df: pd.DataFrame,
                  run_id: str, tiers_run: list, dry_run: bool) -> dict:
    if dry_run:
        log.info("[DRY RUN] Output writing skipped")
        return {}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not contracts_df.empty:
        contracts_df.to_csv(OUTPUT_DIR / f"contracts_{run_id}.csv",  index=False)
        contracts_df.to_csv(OUTPUT_DIR / "contracts_latest.csv",      index=False)

    if not vms_df.empty:
        # L1-CHANGE-3: Stamp scanner routing fields onto every VMS row before write.
        vms_df = vms_df.copy()
        vms_df["scanner_primary_route"] = vms_df.apply(
            lambda r: _scanner_route(r.get("score", 0), r.get("decision", "BLOCK")), axis=1
        )
        vms_df["route_source"]       = "SCANNER_VMS"
        vms_df["signal_source"]      = "MICROSTRUCTURE"
        vms_df["news_terminal_role"] = "CONFIRMATION_ONLY"
        vms_df["scanner_manifest_at"] = datetime.utcnow().isoformat() + "Z"
        vms_df.to_csv(OUTPUT_DIR / f"vms_scoreboard_{run_id}.csv",   index=False)
        vms_df.to_csv(OUTPUT_DIR / "vms_scoreboard_latest.csv",       index=False)

    def tlist(df, decision, tag):
        if df.empty: return []
        return df[(df["decision"] == decision) & (df["pipeline_tag"] == tag)]["ticker"].tolist()

    # IV rank quality summary for manifest
    real_count      = int((vms_df["iv_rank_source"] == "REAL").sum())    if not vms_df.empty else 0
    synthetic_count = int((vms_df["iv_rank_source"] == "SYNTHETIC").sum()) if not vms_df.empty else 0

    prime_n = setup_n = watch_n = 0
    if not contracts_df.empty and "olis_verdict" in contracts_df.columns:
        prime_n = int((contracts_df["olis_verdict"] == "PRIME_LONG").sum())
        setup_n = int((contracts_df["olis_verdict"] == "SETUP_LONG").sum())
        watch_n = int((contracts_df["olis_verdict"] == "WATCH_LONG").sum())

    manifest = {
        "run_id":            run_id,
        "timestamp":         datetime.now().isoformat(),
        "tiers_run":         tiers_run,
        "universe_scanned":  int(len(vms_df)),
        "go_new":            tlist(vms_df, "GO",    "NEW"),
        "go_known":          tlist(vms_df, "GO",    "KNOWN"),
        "probe_new":         tlist(vms_df, "PROBE", "NEW"),
        "probe_known":       tlist(vms_df, "PROBE", "KNOWN"),
        "contract_count":    int(len(contracts_df)),
        "long_verdicts": {
            "PRIME_LONG": prime_n,
            "SETUP_LONG": setup_n,
            "WATCH_LONG": watch_n,
        },
        "max_age_hours":     MANIFEST_MAX_AGE_HOURS,
        "iv_rank_quality": {
            "real_iv_rank_count":      real_count,
            "synthetic_iv_rank_count": synthetic_count,
            "real_pct":                round(real_count / max(1, real_count + synthetic_count) * 100, 1),
        },
        "files": {
            "contracts":      str(OUTPUT_DIR / "contracts_latest.csv"),
            "vms_scoreboard": str(OUTPUT_DIR / "vms_scoreboard_latest.csv"),
        },
        # L1-CHANGE-3: Routing metadata — downstream reads these to confirm
        # scanner is primary gate and news terminal is confirmation only.
        "route_source":       "SCANNER_VMS",
        "signal_source":      "MICROSTRUCTURE",
        "news_terminal_role": "CONFIRMATION_ONLY",
        "scanner_manifest_at": datetime.utcnow().isoformat() + "Z",
    }

    with open(OUTPUT_DIR / "scanner_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    log.info(f"Outputs → {OUTPUT_DIR}")
    log.info(
        f"GO  new={len(manifest['go_new'])} known={len(manifest['go_known'])} | "
        f"PROBE new={len(manifest['probe_new'])} known={len(manifest['probe_known'])} | "
        f"Contracts={manifest['contract_count']} | "
        f"IV rank: REAL={real_count} SYNTHETIC={synthetic_count}"
    )
    return manifest


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(contracts_df: pd.DataFrame, vms_df: pd.DataFrame,
                  run_id: str, top_n: int) -> None:
    print(f"\n{'='*90}")
    print(f"  AVSHUNTER UNIVERSE SCANNER v6.0 — {run_id}")

    if vms_df.empty:
        print("  No results.")
        print(f"{'='*90}\n")
        return

    go_df    = vms_df[vms_df["decision"] == "GO"]
    probe_df = vms_df[vms_df["decision"] == "PROBE"]
    new_q    = vms_df[(vms_df["pipeline_tag"] == "NEW") & vms_df["decision"].isin(["GO","PROBE"])]
    real_n   = (vms_df["iv_rank_source"] == "REAL").sum()
    syn_n    = (vms_df["iv_rank_source"] == "SYNTHETIC").sum()

    prime_n = setup_n = watch_n = 0
    if not contracts_df.empty and "olis_verdict" in contracts_df.columns:
        prime_n = (contracts_df["olis_verdict"] == "PRIME_LONG").sum()
        setup_n = (contracts_df["olis_verdict"] == "SETUP_LONG").sum()
        watch_n = (contracts_df["olis_verdict"] == "WATCH_LONG").sum()

    print(f"  Scanned={len(vms_df)} | GO={len(go_df)} | PROBE={len(probe_df)} | NEW={len(new_q)}")
    print(f"  IV Rank: REAL={real_n} (~95% conf) | SYNTHETIC={syn_n} (~65% conf)")
    print(f"  Contracts: PRIME_LONG={prime_n} | SETUP_LONG={setup_n} | WATCH_LONG={watch_n}")
    print(f"{'='*90}")

    if not contracts_df.empty and "olis_verdict" in contracts_df.columns:
        top = contracts_df.head(top_n)
        print(f"\n  TOP {top_n} OLIS CONTRACTS — AVSHUNTER LONG OPTIONS INTELLIGENCE\n")
        hdr = (f"  {'#':<3} {'Ticker':<7} {'Tag':<6} {'Verdict':<12} {'Dir':<5} "
               f"{'Type':<5} {'Strike':<8} {'Exp':<12} {'DTE':<4} "
               f"{'Ask':>6} {'Prem%':>6} {'BE%':>5} {'BE-σ':>5} "
               f"{'OI':>7} {'IVR':>5} {'Δ':>6} "
               f"{'OLIS':>6} {'Warn'}")
        print(hdr)
        print(f"  {'-'*125}")
        for i, row in enumerate(top.itertuples(), 1):
            warn_flag  = "⚠️  SPRD" if getattr(row, "spread_warn", False) else ""
            delta_str  = f"{row.delta:.2f}" if row.delta else "   -"
            be_sig_str = f"{row.be_sigma:.1f}" if row.be_sigma else "  -"
            verdict    = getattr(row, "olis_verdict", "?")
            icon       = "🔥" if verdict == "PRIME_LONG" else ("⚡" if verdict == "SETUP_LONG" else "👁")
            print(
                f"  {i:<3} {row.ticker:<7} {row.pipeline_tag:<6} "
                f"{icon} {verdict:<10} {row.olis_direction:<5} "
                f"{row.type:<5} {row.strike:<8.2f} {row.expiry:<12} {row.dte:<4} "
                f"${row.ask:>5.2f} {row.pct_premium:>5.2f}% {row.be_pct:>4.1f}% "
                f"{be_sig_str:>5}σ "
                f"{row.open_interest:>7,} {row.iv_rank:>5.2f} "
                f"{delta_str:>6} "
                f"{row.olis_score:>6.1f} {warn_flag}"
            )
            if getattr(row, "olis_reasons", ""):
                print(f"        ↳ {row.olis_reasons}")

    qualified = vms_df[vms_df["decision"].isin(["GO","PROBE"])]
    if not qualified.empty:
        print(f"\n  VMS SCOREBOARD — GO / PROBE  [NEW = outside pipeline universe]\n")
        cols = [c for c in ["ticker","pipeline_tag","tier","spot","rv","iv","vol_spread",
                "iv_rank","iv_rank_source","compression","score","decision",
                "direction","rsi_14","momentum_20d","n_contracts"] if c in qualified.columns]
        print(qualified[cols].to_string(index=False))

    print(f"{'='*90}\n")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="AVSHUNTER Universe Options Mispricing Scanner v5.0"
    )
    parser.add_argument("--test",             action="store_true",
                        help="Test mode: synthetic data, zero API calls, ~30 seconds. Validates full pipeline logic and writes manifest for orchestrator --validate.")
    parser.add_argument("--tier1",            action="store_true",
                        help="Tier 1: dynamic Polygon-driven universe (run daily)")
    parser.add_argument("--tier2",            action="store_true",
                        help="Tier 2: broad sweep universe (run weekly/on-demand)")
    parser.add_argument("--tickers",          default=None,
                        help="Custom comma-separated tickers (overrides tiers)")
    parser.add_argument("--top-n",            type=int, default=20)
    parser.add_argument("--dry-run",          action="store_true",
                        help="Score and display without writing output files")
    parser.add_argument("--rebuild-iv-cache", action="store_true",
                        help="Cold-start IV history cache for all tickers (uses ~62K MarketData credits)")
    parser.add_argument("--polygon-key",      default=None,
                        help="Polygon API key (overrides POLYGON_API_KEY env var)")
    parser.add_argument("--marketdata-key",   default=None,
                        help="MarketData.app API key (overrides MARKETDATA_API_KEY env var)")
    args = parser.parse_args()

    if not args.tier1 and not args.tier2 and not args.tickers and not args.rebuild_iv_cache and not args.test:
        parser.error("Specify at least one of: --tier1  --tier2  --tickers  --test  --rebuild-iv-cache")

    global POLYGON_API_KEY, MARKETDATA_API_KEY
    if args.polygon_key:
        POLYGON_API_KEY = args.polygon_key
    if args.marketdata_key:
        MARKETDATA_API_KEY = args.marketdata_key

    if POLYGON_API_KEY == "YOUR_POLYGON_API_KEY" and not args.test:
        log.error("No Polygon API key. Use --polygon-key or set POLYGON_API_KEY env var")
        sys.exit(1)

    if MARKETDATA_API_KEY == "YOUR_MARKETDATA_API_KEY":
        log.warning(
            "No MarketData.app API key set. IV Rank will use synthetic RV×1.2 proxy (~65% confidence).\n"
            "Set MARKETDATA_API_KEY env var or use --marketdata-key for real IV rank (~95% confidence)."
        )

    run_id = datetime.now().strftime("%Y%m%d_%H%M")

    print(f"""
    ╔════════════════════════════════════════════════════════════════╗
    ║   AVSHUNTER — UNIVERSE OPTIONS MISPRICING SCANNER v7.0        ║
    ║   OLIS — Options Long Intelligence Score (proprietary)        ║
    ║   Polygon (chain/universe) + MarketData.app (real IV Rank)    ║
    ╚════════════════════════════════════════════════════════════════╝
    run_id        : {run_id}
    test_mode     : {args.test}  (synthetic data — zero API calls)
    tier1         : {args.tier1}   (dynamic, Polygon-driven)
    tier2         : {args.tier2}   (broad sweep, ~{len(TIER2_UNIVERSE)} tickers)
    custom        : {args.tickers or 'None'}
    rebuild_cache : {args.rebuild_iv_cache}
    dry_run       : {args.dry_run}
    marketdata    : {'REAL IV rank' if MARKETDATA_API_KEY != 'YOUR_MARKETDATA_API_KEY' else 'SYNTHETIC fallback (no key)'}
    """)

    conn             = init_iv_cache()
    pipeline_universe = load_pipeline_universe()

    # ── Test mode — synthetic data, zero API calls ────────────────────────────
    if args.test:
        log.info("Starting TEST MODE — no API calls will be made")
        contracts_df, vms_df = run_test_scan(pipeline_universe, top_n=args.top_n)
        conn.close()
        run_id_test = run_id + "_TEST"
        print_summary(contracts_df, vms_df, run_id_test, args.top_n)
        # Always write outputs in test mode (even without --dry-run)
        # so orchestrator Phase 0 handshake can be tested immediately
        write_outputs(contracts_df, vms_df, run_id_test, ["TEST"], dry_run=False)
        log.info("Test complete. To test orchestrator handshake:")
        log.info("  python intelligent_orchestrator.py --validate --run-id <run_id>")
        sys.exit(0)

    # ── Standalone IV cache rebuild ───────────────────────────────────────────
    if args.rebuild_iv_cache:
        custom = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
        if custom:
            rebuild_universe = custom
        elif args.tier1:
            rebuild_universe = build_tier1_universe()
        else:
            rebuild_universe = TIER2_UNIVERSE
        rebuild_iv_cache(rebuild_universe, conn)
        if not args.tier1 and not args.tier2 and not args.tickers:
            conn.close()
            log.info("IV cache rebuild complete. Run scanner normally to score.")
            sys.exit(0)

    all_contracts = pd.DataFrame()
    all_vms       = pd.DataFrame()
    tiers_run     = []

    if args.tickers:
        custom = [t.strip().upper() for t in args.tickers.split(",")]
        c_df, v_df = run_scan(custom, pipeline_universe, "CUSTOM", args.top_n, conn)
        all_contracts = pd.concat([all_contracts, c_df], ignore_index=True)
        all_vms       = pd.concat([all_vms, v_df],       ignore_index=True)
        tiers_run.append("CUSTOM")

    if args.tier1:
        t1 = build_tier1_universe()
        if t1:
            c_df, v_df = run_scan(t1, pipeline_universe, "TIER1", args.top_n, conn)
            all_contracts = pd.concat([all_contracts, c_df], ignore_index=True)
            all_vms       = pd.concat([all_vms, v_df],       ignore_index=True)
            tiers_run.append("TIER1")
        else:
            log.warning("Tier 1: No universe returned — check API access")

    if args.tier2:
        c_df, v_df = run_scan(TIER2_UNIVERSE, pipeline_universe, "TIER2", args.top_n, conn)
        all_contracts = pd.concat([all_contracts, c_df], ignore_index=True)
        all_vms       = pd.concat([all_vms, v_df],       ignore_index=True)
        tiers_run.append("TIER2")

    conn.close()

    # Deduplicate across tiers
    if not all_vms.empty:
        all_vms = (
            all_vms.sort_values("score", ascending=False)
            .drop_duplicates(subset="ticker", keep="first")
            .reset_index(drop=True)
        )
    if not all_contracts.empty:
        all_contracts = (
            all_contracts.sort_values("olis_score", ascending=False)
            .drop_duplicates(subset=["ticker","type","strike","expiry"], keep="first")
            .reset_index(drop=True)
        )

    print_summary(all_contracts, all_vms, run_id, args.top_n)
    write_outputs(all_contracts, all_vms, run_id, tiers_run, args.dry_run)

    log.info(f"Done. Log: {log_file}")


if __name__ == "__main__":
    main()
