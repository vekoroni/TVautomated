# === AVSHUNTER: Global Macro + Repo Money Flow Monitor v3.5 ===
# CHANGES over v3.4:
# ✅ yfinance removed — VIX9D/VIX3M/VVIX via Polygon Indices API
# CHANGES over v3.3:
# ✅ OUTPUT_DIR config cell — saves direct to dropbox\market_data
# ✅ VIX9D, VIX3M, VVIX added via Polygon (was yfinance)
# ✅ HY OAS + IG BBB OAS added via FRED (BAMLH0A0HYM2 / BAMLC0A4CBBB) — credit gap closed
# ✅ Yield curve timezone normalisation hardened
# ✅ No files.download() calls
#
# v3.6 (7 Oct 2026) — runs unattended on the AVSHUNTER PC as well as in Colab. Thresholds,
# signals and the avshunter_liquidity_monitor.csv schema are unchanged from v3.5:
# ✅ pip install only inside Colab; keys from Colab Secrets, else environment / repo .env.
# ✅ FRED and Polygon read through their REST endpoints with requests (same series and
#    aggregates the fredapi / polygon-api-client wrappers call), so the venv needs no new
#    packages. Error text never echoes a key.
# ✅ Charts only inside Colab (display-only); UTF-8 console; --output-dir (or
#    AVSH_LIQ_OUTPUT_DIR) for testing; exit code 1 when the CSV was not written.
# ✅ `import requests` added: v3.5 never imported it, so fetch_polygon_index() always hit a
#    NameError that its bare except turned into "failed" for every VIX leg.
# ⚠️ KNOWN, NOT FIXED HERE (awaiting ACK) — unit mismatches:
#    • HY/IG OAS are PERCENT on FRED (3.1 = 310 bp) but compared with 350/500/800 as bp, so
#      Credit_Stress can never leave NORMAL (and prints "3.1bps").
#    • RRPONTSYD is $bn but compared with 1.2e12 / 2.0e12 / 1.5e12 as dollars, so the RRP
#      legs of Repo_Stress_Score and the regime never fire; Latest_RRP_Trillions shows 0.00T.
#    • Polygon index aggregates (I:VIX ...) are outside the plan (403), so VIX term / VVIX
#      stay MISSING in this file; the VIX engine and market intelligence files carry them.
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_liquidity_monitor_v3_6.py

# ════════════════════════════════════════════════════════════
# ── CONFIG ──────────────────────────────────────────────────
import argparse
import os
import pathlib
import re
import sys

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
_parser = argparse.ArgumentParser(description="AVSHUNTER global macro + repo money flow monitor")
_parser.add_argument("--output-dir", default=os.environ.get("AVSH_LIQ_OUTPUT_DIR"),
                     help="write here instead of dropbox\\market_data (for testing)")
_args, _ = _parser.parse_known_args()   # Colab passes its own kernel arguments
if _args.output_dir:
    OUTPUT_DIR = pathlib.Path(_args.output_dir)
else:
    OUTPUT_DIR = REPO_ROOT / "dropbox" / "market_data"
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR = pathlib.Path("/content")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
print(f"📁 OUTPUT_DIR: {OUTPUT_DIR}")
# ════════════════════════════════════════════════════════════

if IN_COLAB:
    get_ipython().system('pip -q install -U pip setuptools wheel')  # noqa: F821

import time
from datetime import datetime, timedelta, UTC
import numpy as np
import pandas as pd
import requests

if IN_COLAB:
    import matplotlib.pyplot as plt
else:
    plt = None
    try:
        from dotenv import load_dotenv
        if (REPO_ROOT / ".env").exists():
            load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
    except ImportError:
        pass

_KEY_IN_TEXT = re.compile(r"((?:apiKey|api_key|token)=)[^&\s'\"]+", re.IGNORECASE)


def _safe(e):
    """Exception text with any key value redacted (request URLs carry the key)."""
    text = _KEY_IN_TEXT.sub(r"\1REDACTED", str(e))
    return f"{type(e).__name__}: {text}"

def fetch_polygon_index(index_ticker, start_date, end_date, api_key):
    """Fetch daily close for a Polygon index ticker (e.g. I:VIX, I:VIX9D, I:DXY)."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{index_ticker}/range/1/day/{start_date}/{end_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": api_key}
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        df = pd.DataFrame(results)
        df["t"] = pd.to_datetime(df["t"], unit="ms").dt.tz_localize(None)
        s = df.set_index("t")["c"]
        s.name = index_ticker
        return s
    except Exception as e:
        return None


if IN_COLAB:
    from google.colab import userdata
    try:
        FRED_API_KEY    = userdata.get("FRED_API_KEY")
        POLYGON_API_KEY = userdata.get("POLYGON_API_KEY")
        print("✅ API keys loaded from Colab Secrets")
    except Exception as e:
        print("❌ ERROR: Could not load API keys"); raise
else:
    FRED_API_KEY    = os.environ.get("FRED_API_KEY", "").strip() or None
    POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "").strip() or None
    print(f"ℹ️  Keys from environment / repo .env — FRED {'found' if FRED_API_KEY else 'MISSING'}, "
          f"Polygon {'found' if POLYGON_API_KEY else 'MISSING'}")
    if not POLYGON_API_KEY:
        raise SystemExit("❌ POLYGON_API_KEY is required — cannot proceed")

RESAMPLE_MODE = 'daily'
END_DATE      = datetime.now(UTC).strftime('%Y-%m-%d')
START_DATE    = "2023-01-01"

FRED_SERIES = {
    "walcl":  "WALCL",
    "rrp":    "RRPONTSYD",
    "sofr":   "SOFR",
    "y10":    "DGS10",
    "y2":     "DGS2",
    "hy_oas": "BAMLH0A0HYM2",   # FIX v3.4: HY OAS — gap closed
    "ig_oas": "BAMLC0A4CBBB",   # FIX v3.4: IG BBB OAS — gap closed
}

ETF_TICKERS   = ["BIL", "TLT", "ARKK", "HYG", "QQQ"]
CRYPTO_TICKER = "X:BTCUSD"

def _fred_series(series: str, start: str) -> pd.Series:
    """FRED series/observations (the endpoint fredapi.get_series calls); '.' = missing."""
    if not FRED_API_KEY:
        raise RuntimeError("no FRED_API_KEY")
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": series, "api_key": FRED_API_KEY, "file_type": "json",
                             "observation_start": start}, timeout=30)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    return pd.Series(pd.to_numeric([o["value"] for o in obs], errors="coerce"),
                     index=pd.to_datetime([o["date"] for o in obs]), dtype="float64")


class _TooManyRequests(Exception):
    pass


def _polygon_aggs(ticker, multiplier, timespan, from_, to, limit):
    """Polygon /v2/aggs (the endpoint RESTClient.get_aggs calls), following next_url pages."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_}/{to}"
    params = {"adjusted": "true", "sort": "asc", "limit": limit, "apiKey": POLYGON_API_KEY}
    rows = []
    while url:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:
            raise _TooManyRequests(ticker)
        r.raise_for_status()
        payload = r.json()
        rows.extend(payload.get("results") or [])
        url, params = payload.get("next_url"), {"apiKey": POLYGON_API_KEY}
    return rows

def safe_fred_get(series: str, start: str) -> pd.Series:
    try:
        s = _fred_series(series, start).dropna()
        s.index = pd.to_datetime(s.index)
        # FIX v3.4: consistent UTC normalisation
        s.index = s.index.tz_localize("UTC") if s.index.tz is None else s.index.tz_convert("UTC")
        s.name = series
        return s
    except Exception as e:
        print(f"[WARN] FRED fetch failed for {series}: {_safe(e)}")
        return pd.Series(dtype="float64")

def get_polygon_aggs(ticker, start, end, multiplier=1, timespan="day",
                     limit=50000, max_retries=3, backoff=1.5):
    for attempt in range(1, max_retries+1):
        try:
            aggs = _polygon_aggs(ticker=ticker, multiplier=multiplier,
                timespan=timespan, from_=start, to=end, limit=limit)
            rows = [{"timestamp": pd.to_datetime(a["t"], unit="ms", utc=True), "close": a["c"]} for a in aggs]
            if not rows:
                return pd.DataFrame(columns=["close"], index=pd.DatetimeIndex([], tz="UTC"))
            return pd.DataFrame(rows).set_index("timestamp").sort_index()
        except _TooManyRequests:
            time.sleep(backoff ** attempt)
        except Exception as e:
            if attempt == max_retries:
                print(f"[ERROR] Polygon {ticker}: {_safe(e)}")
                return pd.DataFrame(columns=["close"], index=pd.DatetimeIndex([], tz="UTC"))
            time.sleep(backoff ** attempt)

def zscore(series, window):
    if series.empty: return series
    roll = series.rolling(window=window, min_periods=max(5, min(20, window//3)))
    return (series - roll.mean()) / roll.std(ddof=0).replace(0, np.nan)

def last_val(s, fmt="{:.2f}", fallback="N/A"):
    return fmt.format(s.iloc[-1]) if (isinstance(s, pd.Series) and not s.empty) else fallback

def resample_series(s, freq):
    if s.empty: return s
    s2 = s.copy()
    if s2.index.tz is None: s2.index = s2.index.tz_localize("UTC")
    return s2.resample(freq).last().ffill()

print("Fetching FRED data...")
walcl  = safe_fred_get(FRED_SERIES["walcl"],  START_DATE)
rrp    = safe_fred_get(FRED_SERIES["rrp"],    START_DATE)
sofr   = safe_fred_get(FRED_SERIES["sofr"],   START_DATE)
y10    = safe_fred_get(FRED_SERIES["y10"],    START_DATE)
y2     = safe_fred_get(FRED_SERIES["y2"],     START_DATE)
hy_oas = safe_fred_get(FRED_SERIES["hy_oas"], START_DATE)
ig_oas = safe_fred_get(FRED_SERIES["ig_oas"], START_DATE)
for k, s in {"walcl":walcl,"rrp":rrp,"sofr":sofr,"y10":y10,"y2":y2,"hy_oas":hy_oas,"ig_oas":ig_oas}.items():
    print(f"  {'✅' if not s.empty else '⚠ '} {k}")

print("\nFetching Polygon ETFs...")
etfs = {}
for symbol in ETF_TICKERS:
    etfs[symbol] = get_polygon_aggs(symbol, START_DATE, END_DATE)
    print(f"  {'✅' if not etfs[symbol].empty else '⚠ '} {symbol}")
btc = get_polygon_aggs(CRYPTO_TICKER, START_DATE, END_DATE)

# FIX v3.5: VIX9D / VIX3M / VVIX via Polygon Indices — yfinance removed
POLYGON_VIX_MAP = {"VIX":"I:VIX","VIX9D":"I:VIX9D","VIX3M":"I:VIX3M","VVIX":"I:VVIX"}
vix_liq = {}
print("\nFetching Polygon Indices (VIX/VIX9D/VIX3M/VVIX)...")
for name, idx_ticker in POLYGON_VIX_MAP.items():
    s = fetch_polygon_index(idx_ticker, START_DATE, END_DATE, POLYGON_API_KEY)
    if s is not None and not s.empty:
        # normalise to UTC for consistency with FRED series
        s.index = pd.to_datetime(s.index)
        s.index = s.index.tz_localize("UTC") if s.index.tz is None else s.index.tz_convert("UTC")
        vix_liq[name] = s; print(f"  ✅ {name} ({idx_ticker}): {s.iloc[-1]:.2f}")
    else:
        print(f"  ⚠  {name} ({idx_ticker}): failed")

freq = 'W-WED' if RESAMPLE_MODE == 'weekly' else 'D'
walcl  = resample_series(walcl,  freq)
rrp    = resample_series(rrp,    freq)
sofr   = resample_series(sofr,   freq)
y10    = resample_series(y10,    freq)
y2     = resample_series(y2,     freq)
hy_oas = resample_series(hy_oas, freq)
ig_oas = resample_series(ig_oas, freq)
for k, df in etfs.items():
    if not df.empty: etfs[k] = df.resample(freq).last().ffill()
if not btc.empty: btc = btc.resample(freq).last().ffill()
for k, s in vix_liq.items():
    if not s.empty: vix_liq[k] = s.resample(freq).last().ffill()

spread   = (y10 - y2).dropna()
win = 60 if RESAMPLE_MODE == 'daily' else 12
spread_z = zscore(spread,  win)
sofr_z   = zscore(sofr,    win)
rrp_z    = zscore(rrp,     win)
hy_z     = zscore(hy_oas,  win)
ig_z     = zscore(ig_oas,  win)

# ── VIX term structure ────────────────────────────────────────────────────────
vix_shape_liq = "UNKNOWN"
if "VIX9D" in vix_liq and "VIX3M" in vix_liq:
    v9 = float(vix_liq["VIX9D"].iloc[-1]); v3m = float(vix_liq["VIX3M"].iloc[-1])
    vix_shape_liq = "BACKWARDATION" if v9>v3m else "CONTANGO" if v9<v3m else "FLAT"
    print(f"\n📊 VIX Term: VIX9D={v9:.2f}  VIX3M={v3m:.2f}  → {vix_shape_liq}")
else:
    print("\n⚠️  VIX9D/VIX3M MISSING — term structure inferred neutral")

vvix_liq_val, vvix_liq_stress = None, "MISSING"
if "VVIX" in vix_liq and not vix_liq["VVIX"].empty:
    vvix_liq_val = float(vix_liq["VVIX"].iloc[-1])
    vvix_liq_stress = "ELEVATED" if vvix_liq_val > 110 else "NORMAL"
    print(f"📊 VVIX: {vvix_liq_val:.2f}  [{vvix_liq_stress}]")
else:
    print("⚠️  VVIX MISSING — options premium stress cannot be validated")

# ── Credit stress ─────────────────────────────────────────────────────────────
hy_oas_val = float(hy_oas.iloc[-1]) if not hy_oas.empty else None
ig_oas_val = float(ig_oas.iloc[-1]) if not ig_oas.empty else None
credit_stress = "MISSING"
if hy_oas_val is not None:
    credit_stress = "EXTREME" if hy_oas_val>800 else "ELEVATED" if hy_oas_val>500 else "WIDE" if hy_oas_val>350 else "NORMAL"
    print(f"\n💳 HY OAS: {hy_oas_val:.1f}bps [{credit_stress}]  IG BBB: {ig_oas_val:.1f}bps" if ig_oas_val else f"\n💳 HY OAS: {hy_oas_val:.1f}bps [{credit_stress}]")
else:
    print("\n⚠️  HY/IG OAS MISSING — credit risk carried neutral")

# ── WALCL regime ──────────────────────────────────────────────────────────────
regime = "No Data"
if not walcl.empty and walcl.size > 1:
    change_walcl = walcl.pct_change().iloc[-1]
    latest_rrp   = rrp.iloc[-1] if not rrp.empty else np.nan
    days_since   = (datetime.now(UTC) - walcl.index[-1]).days
    if change_walcl>0.001 and (not np.isnan(latest_rrp) and latest_rrp<1.5e12): regime="Flooded"
    elif change_walcl<-0.0005 or (not np.isnan(latest_rrp) and latest_rrp>2.0e12): regime="Draining"
    else: regime="Neutral"
    if days_since>7: regime+=f" (STALE - {days_since}d old)"
    elif days_since>0: regime+=f" ({days_since}d old)"

repo_stress_score = 90 if (not rrp.empty and (rrp.iloc[-1]>2.0e12 or (not rrp_z.empty and rrp_z.iloc[-1]>2))) \
               else 60 if (not rrp.empty and (rrp.iloc[-1]>1.2e12 or (not rrp_z.empty and rrp_z.iloc[-1]>1))) \
               else 20

def close_col(df): return df["close"] if ("close" in df.columns and not df.empty) else pd.Series(dtype="float64")
merged = pd.concat([walcl.rename("walcl"),
    close_col(etfs.get("ARKK",pd.DataFrame())).rename("arkk"),
    close_col(etfs.get("QQQ",pd.DataFrame())).rename("qqq"),
    close_col(btc).rename("btc")], axis=1).dropna()

if not merged.empty and len(merged)>=win:
    rc_arkk = merged["walcl"].rolling(win,min_periods=max(10,win//3)).corr(merged["arkk"]).ewm(span=10).mean()
    rc_qqq  = merged["walcl"].rolling(win,min_periods=max(10,win//3)).corr(merged["qqq"]).ewm(span=10).mean()
    rc_btc  = merged["walcl"].rolling(win,min_periods=max(10,win//3)).corr(merged["btc"]).ewm(span=10).mean()
else:
    rc_arkk = rc_qqq = rc_btc = pd.Series(dtype="float64")

latest_spread = float(spread.iloc[-1]) if not spread.empty else None
spread_signal = "NORMAL" if (latest_spread and latest_spread>0.25) else \
                "FLAT"   if (latest_spread and latest_spread>0)    else \
                "INVERTED" if latest_spread is not None else "UNKNOWN"

print("\n" + "="*60 + "\n=== AVSHUNTER LIQUIDITY MONITOR v3.6 ===\n" + "="*60)
print(f"Date             : {END_DATE}")
print(f"Liquidity Regime : {regime}")
print(f"Repo Stress Score: {repo_stress_score}/100")
print(f"Credit Stress    : {credit_stress}  HY={hy_oas_val:.1f}bps" if hy_oas_val else f"Credit Stress    : {credit_stress}")
print(f"SOFR Z-Score     : {last_val(sofr_z)}")
print(f"HY OAS Z-Score   : {last_val(hy_z)}")
print(f"2Y/10Y Spread    : {latest_spread:.3f}% ({spread_signal})" if latest_spread else "2Y/10Y Spread    : N/A")
print(f"VIX Term Shape   : {vix_shape_liq}")
print(f"VVIX             : {vvix_liq_val:.2f} [{vvix_liq_stress}]" if vvix_liq_val else "VVIX             : MISSING")
print("="*60)

# ── Export ────────────────────────────────────────────────────────────────────
liquidity_summary = pd.DataFrame([{
    'Date': END_DATE, 'Liquidity_Regime': regime, 'Repo_Stress_Score': repo_stress_score,
    'Credit_Stress': credit_stress,
    'HY_OAS': f"{hy_oas_val:.1f}" if hy_oas_val else "N/A",
    'IG_BBB_OAS': f"{ig_oas_val:.1f}" if ig_oas_val else "N/A",
    'HY_Z': last_val(hy_z,"{:.2f}","N/A"), 'SOFR_Z': last_val(sofr_z,"{:.2f}","N/A"),
    'Spread_Z': last_val(spread_z,"{:.2f}","N/A"), 'RRP_Z': last_val(rrp_z,"{:.2f}","N/A"),
    'DGS10_daily': last_val(y10,"{:.3f}","N/A"), 'DGS2_daily': last_val(y2,"{:.3f}","N/A"),
    'Spread_10y2y': f"{latest_spread:.3f}" if latest_spread else "N/A",
    'Spread_Signal': spread_signal, 'VIX_Term_Shape': vix_shape_liq,
    'VVIX': f"{vvix_liq_val:.2f}" if vvix_liq_val else "MISSING", 'VVIX_Stress': vvix_liq_stress,
    'Corr_WALCL_QQQ': last_val(rc_qqq,"{:.3f}","N/A"),
    'Corr_WALCL_ARKK': last_val(rc_arkk,"{:.3f}","N/A"),
    'Corr_WALCL_BTC': last_val(rc_btc,"{:.3f}","N/A"),
    'WALCL_Change_Pct': f"{change_walcl*100:.3f}%" if 'change_walcl' in dir() else "N/A",
    'Latest_RRP_Trillions': f"{latest_rrp/1e12:.2f}T" if 'latest_rrp' in dir() and not np.isnan(latest_rrp) else "N/A"
}])

try:
    liquidity_summary.to_csv(OUTPUT_DIR / "avshunter_liquidity_monitor.csv", index=False)
except OSError as e:
    print(f"\n❌ CSV save failed: {e}")
    if not IN_COLAB:
        sys.exit(1)
    raise
print(f"\n📁 {OUTPUT_DIR / 'avshunter_liquidity_monitor.csv'}")

# ── Visuals (Colab only — display-only, nothing is saved) ─────────────────────
if plt is None:
    print(f"\n✅ v3.6 COMPLETE — outputs → {OUTPUT_DIR}")
    sys.exit(0)
plt.figure(figsize=(20,6))
if not rc_arkk.empty: rc_arkk.plot(label='WALCL vs ARKK',linewidth=2)
if not rc_qqq.empty:  rc_qqq.plot(label='WALCL vs QQQ',linewidth=2)
if not rc_btc.empty:  rc_btc.plot(label='WALCL vs BTC',linewidth=2)
plt.axhline(0,linestyle='--',color='gray',alpha=0.5)
plt.title("Rolling Correlations: Fed Liquidity vs Risk Assets (v3.4)")
plt.legend(); plt.grid(True,alpha=0.3); plt.tight_layout(); plt.show()

if not spread.empty:
    plt.figure(figsize=(20,4)); spread.plot(linewidth=2,color='steelblue')
    plt.axhline(0,linestyle='--',color='red',alpha=0.7)
    plt.title(f"10Y-2Y Yield Spread — [{spread_signal}]"); plt.grid(True,alpha=0.3); plt.tight_layout(); plt.show()

if not hy_oas.empty:
    plt.figure(figsize=(20,4)); hy_oas.plot(linewidth=2,color='crimson',label='HY OAS')
    if not ig_oas.empty: ig_oas.plot(linewidth=2,color='steelblue',label='IG BBB OAS')
    plt.title(f"Credit Spreads — HY [{credit_stress}]")
    plt.legend(); plt.grid(True,alpha=0.3); plt.tight_layout(); plt.show()

print(f"\n✅ v3.6 COMPLETE — outputs → {OUTPUT_DIR}")
