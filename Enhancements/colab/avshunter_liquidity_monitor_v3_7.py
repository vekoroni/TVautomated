# === AVSHUNTER: Global Macro + Repo Money Flow Monitor v3.7 ===
# CHANGES over v3.4:
# ✅ yfinance removed — VIX9D/VIX3M/VVIX via Polygon Indices API
# CHANGES over v3.3:
# ✅ OUTPUT_DIR config cell — saves direct to dropbox\market_data
# ✅ VIX9D, VIX3M, VVIX added via Polygon (was yfinance)
# ✅ HY OAS + IG BBB OAS added via FRED (BAMLH0A0HYM2 / BAMLC0A4CBBB) — credit gap closed
# ✅ Yield curve timezone normalisation hardened
# ✅ No files.download() calls
#
# v3.6 (7 Oct 2026) — runs unattended on the AVSHUNTER PC as well as in Colab: pip install
# only in Colab; keys from Colab Secrets, else environment / repo .env; FRED and Polygon read
# through their REST endpoints with requests (no fredapi / polygon-api-client needed); error
# text never echoes a key; charts only in Colab; UTF-8 console; --output-dir (or
# AVSH_LIQ_OUTPUT_DIR) for testing; exit code 1 when the CSV was not written.
#
# v3.7 (7 Oct 2026, ACK approved) — unit fixes, same levels, same CSV schema:
# ✅ FIX: HY/IG OAS are PERCENT on FRED (3.10 = 310 bp). v3.6 compared them with 350/500/800
#    as if bp, so Credit_Stress could never leave NORMAL and printed "3.1bps". The same levels
#    now apply in percent (3.5 / 5.0 / 8.0); printed as "3.10% (310 bp)". CSV values unchanged.
# ✅ FIX: RRPONTSYD is $ BILLIONS. v3.6 compared it with 1.2e12 / 1.5e12 / 2.0e12 as dollars,
#    so the RRP legs of Repo_Stress_Score and the regime never fired and Latest_RRP_Trillions
#    showed 0.00T. The same $1.2T / $1.5T / $2.0T levels now apply in $bn (1200 / 1500 / 2000).
# ✅ FIX: VIX / VIX9D / VIX3M / VVIX from Cboe's published daily history (no key) instead of
#    Polygon index aggregates, which return 403 NOT_AUTHORIZED on this plan (checked 7 Oct).
#    Same source the market intelligence extractor uses.
# ✅ Importing this file does nothing; work happens in main() (tests import the functions).
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_liquidity_monitor_v3_7.py

import argparse
import io
import os
import pathlib
import re
import sys
import time
from datetime import datetime, UTC

import numpy as np
import pandas as pd
import requests

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUTPUT_NAME = "avshunter_liquidity_monitor.csv"

# Levels (unchanged from v3.5), stated in the units FRED publishes.
HY_OAS_EXTREME_PCT  = 8.0      # 800 bp
HY_OAS_ELEVATED_PCT = 5.0      # 500 bp
HY_OAS_WIDE_PCT     = 3.5      # 350 bp
RRP_DRAIN_BN        = 2000.0   # $2.0T: regime Draining, repo stress 90
RRP_STRESS_MID_BN   = 1200.0   # $1.2T: repo stress 60
RRP_FLOOD_MAX_BN    = 1500.0   # $1.5T: Flooded only below this
WALCL_FLOOD_CHANGE  = 0.001
WALCL_DRAIN_CHANGE  = -0.0005

CBOE_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
CBOE_FILES = {"VIX": ["VIX_History.csv"], "VIX9D": ["VIX9D_History.csv"],
              "VIX3M": ["VIX3M_History.csv", "VXV_History.csv"], "VVIX": ["VVIX_History.csv"]}

RESAMPLE_MODE = 'daily'
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

FRED_API_KEY = None       # set by main()
POLYGON_API_KEY = None    # set by main()

_KEY_IN_TEXT = re.compile(r"((?:apiKey|api_key|token)=)[^&\s'\"]+", re.IGNORECASE)


def _safe(e):
    """Exception text with any key value redacted (request URLs carry the key)."""
    text = _KEY_IN_TEXT.sub(r"\1REDACTED", str(e))
    return f"{type(e).__name__}: {text}"


# ══════════════════════════════════════════════════════════════
# Classification (pure; unit-tested)
# ══════════════════════════════════════════════════════════════

def _present(x):
    return x is not None and not (isinstance(x, float) and np.isnan(x))


def credit_stress_label(hy_oas_pct):
    """HY OAS in percent (FRED BAMLH0A0HYM2) against the 350 / 500 / 800 bp levels."""
    if not _present(hy_oas_pct):
        return "MISSING"
    if hy_oas_pct > HY_OAS_EXTREME_PCT:
        return "EXTREME"
    if hy_oas_pct > HY_OAS_ELEVATED_PCT:
        return "ELEVATED"
    if hy_oas_pct > HY_OAS_WIDE_PCT:
        return "WIDE"
    return "NORMAL"


def repo_stress_score(rrp_bn, rrp_z):
    """90 / 60 / 20 from the RRP level ($bn) or its z-score; no RRP print -> 20 (as v3.5)."""
    if not _present(rrp_bn):
        return 20
    z = rrp_z if _present(rrp_z) else None
    if rrp_bn > RRP_DRAIN_BN or (z is not None and z > 2):
        return 90
    if rrp_bn > RRP_STRESS_MID_BN or (z is not None and z > 1):
        return 60
    return 20


def liquidity_regime(change_walcl, latest_rrp_bn, days_since):
    """Flooded / Draining / Neutral from the WALCL change and the RRP level ($bn), with age."""
    rrp_known = _present(latest_rrp_bn)
    if change_walcl > WALCL_FLOOD_CHANGE and (rrp_known and latest_rrp_bn < RRP_FLOOD_MAX_BN):
        regime = "Flooded"
    elif change_walcl < WALCL_DRAIN_CHANGE or (rrp_known and latest_rrp_bn > RRP_DRAIN_BN):
        regime = "Draining"
    else:
        regime = "Neutral"
    if days_since > 7:
        regime += f" (STALE - {days_since}d old)"
    elif days_since > 0:
        regime += f" ({days_since}d old)"
    return regime


def rrp_trillions_label(rrp_bn):
    return f"{rrp_bn / 1000.0:.2f}T" if _present(rrp_bn) else "N/A"


def oas_text(pct):
    return f"{pct:.2f}% ({pct * 100:.0f} bp)"


def parse_cboe_history(text, key):
    """Cboe daily history CSV -> close series by date. VIX_History has OPEN/HIGH/LOW/CLOSE;
    single-value files name the column after the index (e.g. DATE,VVIX)."""
    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        return None
    cols = {c.strip().upper(): c for c in df.columns}
    date_col = next((cols[c] for c in cols if "DATE" in c), None)
    if date_col is None:
        return None
    close_col = next((cols[w] for w in ("CLOSE", f"{key} CLOSE", key, "VALUE", "INDEX") if w in cols), None)
    if close_col is None:
        numeric = [c for c in df.columns
                   if c != date_col and pd.to_numeric(df[c], errors="coerce").notna().any()]
        if not numeric:
            return None
        close_col = numeric[-1]
    out = pd.Series(pd.to_numeric(df[close_col], errors="coerce").values,
                    index=pd.to_datetime(df[date_col], errors="coerce"), dtype="float64")
    out = out[out.index.notna()].dropna().sort_index()
    out = out[out.index <= pd.Timestamp(datetime.now(UTC).date())]
    out.name = key
    return out if not out.empty else None


# ══════════════════════════════════════════════════════════════
# Fetching
# ══════════════════════════════════════════════════════════════

def fetch_cboe_index(key):
    for name in CBOE_FILES[key]:
        try:
            r = requests.get(f"{CBOE_BASE}/{name}", timeout=25, headers={"User-Agent": "AVSHUNTER/3.7"})
            if r.status_code != 200 or not r.text.strip():
                continue
            s = parse_cboe_history(r.text, key)
            if s is not None and len(s) >= 2:
                return s
        except Exception as e:
            print(f"  ⚠  Cboe {key} ({name}): {_safe(e)}")
    return None


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


def close_col(df):
    return df["close"] if ("close" in df.columns and not df.empty) else pd.Series(dtype="float64")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main(argv=None):
    global FRED_API_KEY, POLYGON_API_KEY
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="AVSHUNTER global macro + repo money flow monitor")
    parser.add_argument("--output-dir", default=os.environ.get("AVSH_LIQ_OUTPUT_DIR"),
                        help="write here instead of dropbox\\market_data (for testing)")
    args, _ = parser.parse_known_args(argv)   # Colab passes its own kernel arguments
    if args.output_dir:
        output_dir = pathlib.Path(args.output_dir)
    else:
        output_dir = REPO_ROOT / "dropbox" / "market_data"
        if not output_dir.exists():
            output_dir = pathlib.Path("/content")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 OUTPUT_DIR: {output_dir}")

    plt = None
    if IN_COLAB:
        get_ipython().system('pip -q install -U pip setuptools wheel')  # noqa: F821
        import matplotlib.pyplot as plt
        from google.colab import userdata
        try:
            FRED_API_KEY    = userdata.get("FRED_API_KEY")
            POLYGON_API_KEY = userdata.get("POLYGON_API_KEY")
            print("✅ API keys loaded from Colab Secrets")
        except Exception as e:
            print("❌ ERROR: Could not load API keys"); raise
    else:
        try:
            from dotenv import load_dotenv
            if (REPO_ROOT / ".env").exists():
                load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
        except ImportError:
            pass
        FRED_API_KEY    = os.environ.get("FRED_API_KEY", "").strip() or None
        POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "").strip() or None
        print(f"ℹ️  Keys from environment / repo .env — FRED {'found' if FRED_API_KEY else 'MISSING'}, "
              f"Polygon {'found' if POLYGON_API_KEY else 'MISSING'}")
        if not POLYGON_API_KEY:
            raise SystemExit("❌ POLYGON_API_KEY is required — cannot proceed")

    end_date = datetime.now(UTC).strftime('%Y-%m-%d')

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
        etfs[symbol] = get_polygon_aggs(symbol, START_DATE, end_date)
        print(f"  {'✅' if not etfs[symbol].empty else '⚠ '} {symbol}")
    btc = get_polygon_aggs(CRYPTO_TICKER, START_DATE, end_date)

    # FIX v3.7: Cboe daily history (Polygon index aggregates are 403 on this plan)
    vix_liq = {}
    print("\nFetching Cboe indices (VIX/VIX9D/VIX3M/VVIX)...")
    for name in CBOE_FILES:
        s = fetch_cboe_index(name)
        if s is not None and not s.empty:
            s = s[s.index >= pd.Timestamp(START_DATE)]
            s.index = s.index.tz_localize("UTC")      # consistent with the FRED series
            vix_liq[name] = s
            print(f"  ✅ {name} (Cboe): {s.iloc[-1]:.2f} on {s.index[-1].date()}")
        else:
            print(f"  ⚠  {name} (Cboe): failed")

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

    # ── VIX term structure ────────────────────────────────────────────────────
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

    # ── Credit stress (FIX v3.7: OAS in percent) ─────────────────────────────
    hy_oas_val = float(hy_oas.iloc[-1]) if not hy_oas.empty else None
    ig_oas_val = float(ig_oas.iloc[-1]) if not ig_oas.empty else None
    credit_stress = credit_stress_label(hy_oas_val)
    if hy_oas_val is not None:
        print(f"\n💳 HY OAS: {oas_text(hy_oas_val)} [{credit_stress}]"
              + (f"  IG BBB: {oas_text(ig_oas_val)}" if ig_oas_val else ""))
    else:
        print("\n⚠️  HY/IG OAS MISSING — credit risk carried neutral")

    # ── WALCL regime (FIX v3.7: RRP in $bn) ──────────────────────────────────
    latest_rrp = float(rrp.iloc[-1]) if not rrp.empty else np.nan
    change_walcl = None
    regime = "No Data"
    if not walcl.empty and walcl.size > 1:
        change_walcl = walcl.pct_change().iloc[-1]
        days_since   = (datetime.now(UTC) - walcl.index[-1]).days
        regime = liquidity_regime(change_walcl, latest_rrp, days_since)

    repo_score = repo_stress_score(latest_rrp if not rrp.empty else None,
                                   float(rrp_z.iloc[-1]) if not rrp_z.empty else None)

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

    print("\n" + "="*60 + "\n=== AVSHUNTER LIQUIDITY MONITOR v3.7 ===\n" + "="*60)
    print(f"Date             : {end_date}")
    print(f"Liquidity Regime : {regime}")
    print(f"Repo Stress Score: {repo_score}/100   (RRP {rrp_trillions_label(latest_rrp)})")
    print(f"Credit Stress    : {credit_stress}  HY={oas_text(hy_oas_val)}" if hy_oas_val else f"Credit Stress    : {credit_stress}")
    print(f"SOFR Z-Score     : {last_val(sofr_z)}")
    print(f"HY OAS Z-Score   : {last_val(hy_z)}")
    print(f"2Y/10Y Spread    : {latest_spread:.3f}% ({spread_signal})" if latest_spread else "2Y/10Y Spread    : N/A")
    print(f"VIX Term Shape   : {vix_shape_liq}")
    print(f"VVIX             : {vvix_liq_val:.2f} [{vvix_liq_stress}]" if vvix_liq_val else "VVIX             : MISSING")
    print("="*60)

    # ── Export (schema unchanged) ─────────────────────────────────────────────
    liquidity_summary = pd.DataFrame([{
        'Date': end_date, 'Liquidity_Regime': regime, 'Repo_Stress_Score': repo_score,
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
        'WALCL_Change_Pct': f"{change_walcl*100:.3f}%" if change_walcl is not None else "N/A",
        'Latest_RRP_Trillions': rrp_trillions_label(latest_rrp),
    }])

    try:
        liquidity_summary.to_csv(output_dir / OUTPUT_NAME, index=False)
    except OSError as e:
        print(f"\n❌ CSV save failed: {e}")
        if not IN_COLAB:
            return 1
        raise
    print(f"\n📁 {output_dir / OUTPUT_NAME}")

    # ── Visuals (Colab only — display-only, nothing is saved) ─────────────────
    if plt is not None:
        plt.figure(figsize=(20,6))
        if not rc_arkk.empty: rc_arkk.plot(label='WALCL vs ARKK',linewidth=2)
        if not rc_qqq.empty:  rc_qqq.plot(label='WALCL vs QQQ',linewidth=2)
        if not rc_btc.empty:  rc_btc.plot(label='WALCL vs BTC',linewidth=2)
        plt.axhline(0,linestyle='--',color='gray',alpha=0.5)
        plt.title("Rolling Correlations: Fed Liquidity vs Risk Assets (v3.7)")
        plt.legend(); plt.grid(True,alpha=0.3); plt.tight_layout(); plt.show()
        if not spread.empty:
            plt.figure(figsize=(20,4)); spread.plot(linewidth=2,color='steelblue')
            plt.axhline(0,linestyle='--',color='red',alpha=0.7)
            plt.title(f"10Y-2Y Yield Spread — [{spread_signal}]"); plt.grid(True,alpha=0.3); plt.tight_layout(); plt.show()
        if not hy_oas.empty:
            plt.figure(figsize=(20,4)); hy_oas.plot(linewidth=2,color='crimson',label='HY OAS (%)')
            if not ig_oas.empty: ig_oas.plot(linewidth=2,color='steelblue',label='IG BBB OAS (%)')
            plt.title(f"Credit Spreads — HY [{credit_stress}]")
            plt.legend(); plt.grid(True,alpha=0.3); plt.tight_layout(); plt.show()

    print(f"\n✅ v3.7 COMPLETE — outputs → {output_dir}")
    return 0


if __name__ == "__main__":
    _code = main()
    if not IN_COLAB:          # in a notebook cell SystemExit would print a traceback
        sys.exit(_code)
