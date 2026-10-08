# === AVSHUNTER VIX FEAR ENGINE v4.0 (ACCURATE VIX) ===
# CHANGES over v3.0:
# ✅ VIX SOURCE FIXED — real CBOE VIX via yfinance (^VIX/^VIX9D/^VIX3M/^VVIX)
#    MarketData indices confirmed unavailable: /v1/indices/* returns 404 {"s":"no_data"}
#    for every symbol, every path variant, WITH AND WITHOUT auth. Their own docs example
#    fails anonymously. Product is listed "Coming Soon". Not fixable from our side.
# ✅ FRED VIXCLS added as an INDEPENDENT auditor — official CBOE series via the Fed.
#    Verified: FRED 17.05 == yfinance 17.049999 on 2026-07-21 (exact match).
#    Divergence >1% raises a flag rather than silently passing.
# ✅ REAL VVIX replaces the fabricated `np.clip(iv_std * 400, 60, 200)` — that formula
#    measured cross-sectional IV dispersion, not vol-of-vol, and swung 88.12 → 69.56
#    between two runs purely because the chain size changed.
# ✅ REAL VIX percentile rank over 1y of actual VIX history.
#    Old IV_Pct_Rank compared implied vs REALISED vol — a variance-premium measure,
#    not an IV rank. Kept, but renamed and sat alongside the real one.
# ✅ VIX_Momentum now measures VIX. It previously carried the realised-vol trend.
#    Realised-vol trend retained separately as RealisedVol_Trend.
# ✅ ATM IV values RENAMED honestly: SPY_ATM_IV_9d / _30d / _3M.
#    atm_band=0.05 spans only ±0.66 SD at 83 DTE, so these are ATM IV, not VIX.
#    Retained deliberately — ATM_vs_VIX_Gap_Pct is a genuine skew-premium measure.
# ✅ TERMINAL NaN GUARD — yfinance returned "latest nan" on 2026-07-24. Every series is
#    dropna()'d before .iloc[-1] and the true observation date is recorded.
# ✅ HARDCODED TOKEN REMOVED. It was your real key with base64 padding stripped
#    (59 chars vs 60). ROTATE IT at https://app.marketdata.app/ — it has been in plaintext.
# ✅ _validate_api_key() now probes /v1/stocks/quotes/SPY/ (live) instead of the dead
#    indices endpoint, and no longer returns True on arbitrary failures.
# ✅ MarketData retained for the SPY options chain only — that part works (1906 contracts).
#
# CSV SCHEMA: every v3.0 column preserved. New columns appended, none removed.
#
# v4.1 (7 Oct 2026) — runs unattended on the AVSHUNTER PC as well as in Colab. Logic,
# thresholds and CSV schema are unchanged from v4.0; only how it runs:
# ✅ pip install only inside Colab (a local run never modifies the venv).
# ✅ Keys from the repo .env when not already in the environment (override=False).
# ✅ FRED VIXCLS through the FRED REST API when fredapi is not installed (same series).
# ✅ Chart is optional: no matplotlib → no PNG, the CSV is unaffected.
# ✅ UTF-8 console so a scheduled run cannot die printing an emoji.
# ✅ --output-dir (or AVSH_VIX_OUTPUT_DIR) to test without touching dropbox\market_data.
# ✅ Exit code 1 when the CSV was not written, so a scheduler sees the failure.
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_vix_engine_v4_1.py

# ════════════════════════════════════════════════════════════
# STEP 0 — DEPENDENCIES
# ════════════════════════════════════════════════════════════
import subprocess, sys
try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
if IN_COLAB:
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "requests", "pandas", "numpy", "matplotlib", "yfinance", "fredapi",
                    "--quiet"], check=False)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ════════════════════════════════════════════════════════════
# STEP 1 — IMPORTS
# ════════════════════════════════════════════════════════════
import os
import time
import argparse
import pathlib
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
    print("ℹ️  matplotlib not installed — dashboard PNG will be skipped (CSV unaffected)")

print("✅ Imports OK")

# ════════════════════════════════════════════════════════════
# STEP 2 — OUTPUT DIRECTORY
# ════════════════════════════════════════════════════════════
REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
_parser = argparse.ArgumentParser(description="AVSHUNTER VIX + USD engine")
_parser.add_argument("--output-dir", default=os.environ.get("AVSH_VIX_OUTPUT_DIR"),
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

if not IN_COLAB:
    try:
        from dotenv import load_dotenv
        if (REPO_ROOT / ".env").exists():
            load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
    except ImportError:
        pass

# Reconciliation tolerance: yfinance vs FRED VIXCLS on a shared date.
VIX_RECONCILE_TOLERANCE_PCT = 1.0

# ════════════════════════════════════════════════════════════
# STEP 3 — API KEYS  (no hardcoded fallbacks)
# ════════════════════════════════════════════════════════════
MD_SECRET_NAMES = ["MARKETDATA_API_KEY", "MARKETDATA_KEY",
                   "MARKET_DATA_API_KEY", "MARKETDATA_APP_KEY", "MD_API_KEY"]
FRED_SECRET_NAMES = ["FRED_API_KEY", "FRED_KEY", "FREDAPI_KEY", "FRED_API_TOKEN"]

MARKETDATA_API_KEY = None
FRED_API_KEY = None
MD_KEY_SOURCE = "NONE"
FRED_KEY_SOURCE = "NONE"

if IN_COLAB:
    from google.colab import userdata
else:
    userdata = None
    print("ℹ️  Not in Colab — reading keys from environment variables / repo .env")


def _load_colab_secret(candidate_names, label):
    """
    Try each candidate name in turn. Colab raises SecretNotFoundError when the name
    does not exist and NotebookAccessError when it exists but the notebook toggle is
    off — those need different remedies, so they are reported separately rather than
    collapsed into one silent failure.
    """
    if not IN_COLAB:
        return None, "NONE"
    for name in candidate_names:
        try:
            v = userdata.get(name)
            if v and v.strip():
                print(f"✅ {label} key from Colab Secret '{name}' ({len(v.strip())} chars)")
                return v.strip(), f"COLAB:{name}"
            print(f"⚪ Secret '{name}': exists but EMPTY")
        except Exception as e:
            etype = type(e).__name__
            if "NotebookAccess" in etype:
                print(f"🔒 Secret '{name}': EXISTS but notebook access is OFF ← toggle it on")
            elif "SecretNotFound" not in etype:
                print(f"⚠️  Secret '{name}': {etype} — {e}")
            # SecretNotFoundError is the normal miss — stay quiet and try the next name.
    return None, "NONE"


MARKETDATA_API_KEY, MD_KEY_SOURCE = _load_colab_secret(MD_SECRET_NAMES, "MarketData")
FRED_API_KEY, FRED_KEY_SOURCE = _load_colab_secret(FRED_SECRET_NAMES, "FRED")

# Environment fallback — runs in Colab too, not only outside it.
if not MARKETDATA_API_KEY:
    v = os.environ.get("MARKETDATA_API_KEY", "").strip()
    if v:
        MARKETDATA_API_KEY, MD_KEY_SOURCE = v, "ENV"
        print(f"✅ MarketData key from environment ({len(v)} chars)")
if not FRED_API_KEY:
    v = os.environ.get("FRED_API_KEY", "").strip()
    if v:
        FRED_API_KEY, FRED_KEY_SOURCE = v, "ENV"
        print(f"✅ FRED key from environment ({len(v)} chars)")

if not MARKETDATA_API_KEY:
    print(f"⚠️  No MarketData key found under: {', '.join(MD_SECRET_NAMES)}")
    print("   → SPY options chain will be unavailable; real VIX is unaffected.")
if not FRED_API_KEY:
    print(f"⚠️  No FRED key found under: {', '.join(FRED_SECRET_NAMES)}")
    print("   → VIX reconciliation will be skipped; yfinance VIX is unaffected.")

MD_BASE   = "https://api.marketdata.app/v1"
TODAY     = date.today().isoformat()
START_90D = (date.today() - timedelta(days=90)).isoformat()
START_1Y  = (date.today() - timedelta(days=400)).isoformat()
START_5D  = (date.today() - timedelta(days=7)).isoformat()


def _md_headers():
    return {"Authorization": f"Token {MARKETDATA_API_KEY}", "Accept": "application/json"}


def _validate_api_key():
    """
    Probe a LIVE endpoint. v3.0 probed /v1/indices/quotes/VIX/ — which is dead — and
    returned True on any status except 401, so it could never fail meaningfully.
    """
    if not MARKETDATA_API_KEY:
        print("⚠️  No MarketData key — options chain will be skipped")
        return False
    try:
        r = requests.get(f"{MD_BASE}/stocks/quotes/SPY/", headers=_md_headers(), timeout=20)
    except requests.exceptions.Timeout:
        print("⚠️  MarketData validation timed out — options chain may be unavailable")
        return False
    except requests.exceptions.RequestException as e:
        print(f"⚠️  MarketData connectivity failed: {e}")
        return False

    if r.status_code in (200, 203):
        tag = "cached/delayed" if r.status_code == 203 else "live"
        print(f"✅ MarketData token valid ({tag} tier)")
        return True
    if r.status_code == 401:
        print("❌ MarketData 401 — token rejected. Check https://app.marketdata.app/")
        return False
    print(f"⚠️  MarketData probe HTTP {r.status_code} — options chain may be unavailable")
    return False


def _clean_last(series):
    """
    Return (value, observation_date) using the last NON-NaN point.
    yfinance returned a NaN terminal bar on 2026-07-24; taking .iloc[-1] blindly
    propagates that, or silently forward-fills it into today's decision.
    """
    if series is None or len(series) == 0:
        return None, None
    s = series.dropna()
    if s.empty:
        return None, None
    return float(s.iloc[-1]), pd.Timestamp(s.index[-1]).date()


def _normalise_index(series):
    """tz-naive, date-only index so yfinance and FRED align exactly."""
    idx = pd.to_datetime(series.index)
    try:
        if idx.tz is not None:
            idx = idx.tz_convert(None)
    except (AttributeError, TypeError):
        pass
    series.index = idx.normalize()
    return series[~series.index.duplicated(keep="last")].sort_index()


# ══════════════════════════════════════════════════════════════
# SECTION 1 — REAL VIX  (yfinance primary)
# ══════════════════════════════════════════════════════════════

def fetch_real_vix_suite():
    """
    Real CBOE volatility indices from yfinance.
    Returns dict of {name: pd.Series} — empty dict on total failure.

    Why yfinance rather than MarketData or Polygon:
      MarketData /v1/indices/*  → 404 no_data (product unreleased)
      Polygon    I:VIX          → 403 (plan does not include indices)
      yfinance   ^VIX           → works, and matches FRED VIXCLS exactly.
    VIX is an index: no splits, dividends or adjustments, so the usual Yahoo
    corporate-action problems do not apply to this ticker class.
    """
    print("\n" + "─" * 50)
    print("REAL VIX SUITE  (yfinance)")
    print("─" * 50)

    out = {}
    try:
        import yfinance as yf
    except ImportError:
        print("  ❌ yfinance not installed — real VIX unavailable")
        return out

    for name, sym in [("VIX", "^VIX"), ("VIX9D", "^VIX9D"),
                      ("VIX3M", "^VIX3M"), ("VVIX", "^VVIX")]:
        try:
            hist = yf.Ticker(sym).history(period="2y", auto_adjust=False)
        except Exception as e:
            print(f"  ⚠  {sym}: {type(e).__name__} — {e}")
            continue

        if hist is None or hist.empty or "Close" not in hist.columns:
            print(f"  ⚠  {sym}: empty response")
            continue

        s = _normalise_index(hist["Close"].astype("float64"))
        val, obs = _clean_last(s)
        if val is None:
            print(f"  ⚠  {sym}: all values NaN")
            continue

        out[name] = s
        nan_tail = int(s.iloc[::-1].isna().cumprod().sum())
        tail_note = f"  ⚠ {nan_tail} trailing NaN(s)" if nan_tail else ""
        print(f"  ✅ {sym}: {s.dropna().shape[0]} obs, latest {val:.2f} on {obs}{tail_note}")

    if not out:
        print("  ❌ No real VIX data retrieved from yfinance")
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 2 — FRED VIXCLS  (independent auditor)
# ══════════════════════════════════════════════════════════════

def fetch_fred_vix():
    """
    Official CBOE VIX published via FRED. Roughly one day behind, headline index only —
    so not a primary source, but a completely independent check on yfinance.
    """
    if not FRED_API_KEY:
        print("\n⚠️  No FRED key — VIX reconciliation skipped")
        return None
    try:
        try:
            from fredapi import Fred
            s = Fred(api_key=FRED_API_KEY).get_series("VIXCLS").dropna()
        except ImportError:
            # Same series through the FRED REST API (fredapi is a wrapper around it).
            # Retried on timeout / connection error / 429 / 5xx (fredapi waited without a limit;
            # FRED answered in 8-11 s per request on 8 Oct 2026). A 4xx is not retried.
            resp, last = None, None
            for attempt in range(1, 4):
                try:
                    resp = requests.get("https://api.stlouisfed.org/fred/series/observations",
                                        params={"series_id": "VIXCLS", "api_key": FRED_API_KEY,
                                                "file_type": "json"}, timeout=60)
                    if resp.status_code != 429 and resp.status_code < 500:
                        break
                    last, resp = requests.exceptions.HTTPError(f"HTTP {resp.status_code}", response=resp), None
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    last = e
                if attempt < 3:
                    time.sleep(2 * attempt)
            if resp is None:
                raise last
            resp.raise_for_status()
            obs = resp.json()["observations"]
            s = pd.Series(pd.to_numeric([o["value"] for o in obs], errors="coerce"),
                          index=pd.to_datetime([o["date"] for o in obs])).dropna()
        s = _normalise_index(pd.Series(s.values, index=pd.to_datetime(s.index), dtype="float64"))
        val, obs = _clean_last(s)
        print(f"\n✅ FRED VIXCLS: {len(s)} obs, latest {val:.2f} on {obs}")
        return s
    except Exception as e:
        # Never echo the exception text: a REST error message carries the URL and the key.
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"\n⚠️  FRED VIXCLS fetch failed: {type(e).__name__}"
              + (f" (HTTP {status})" if status else ""))
        return None


def reconcile_vix(yf_series, fred_series):
    """
    Compare yfinance against FRED on the most recent SHARED date.
    Same-date comparison only — a cross-date gap is market movement, not a data fault.
    Returns (fred_value, fred_date, diff_pct, status).
    """
    if yf_series is None or fred_series is None:
        return None, None, None, "NO_FRED"

    y = yf_series.dropna()
    f = fred_series.dropna()
    overlap = y.index.intersection(f.index)
    if len(overlap) == 0:
        print("  ⚠️  No overlapping date between yfinance and FRED — cannot reconcile")
        return None, None, None, "NO_OVERLAP"

    d = overlap.max()
    yv, fv = float(y.loc[d]), float(f.loc[d])
    diff = abs(yv - fv) / fv * 100 if fv else None

    print(f"\n🔍 VIX RECONCILIATION on {d.date()}")
    print(f"     yfinance ^VIX : {yv:.4f}")
    print(f"     FRED VIXCLS   : {fv:.4f}")
    print(f"     divergence    : {diff:.3f}%")

    if diff is None:
        status = "UNKNOWN"
    elif diff <= VIX_RECONCILE_TOLERANCE_PCT:
        status = "MATCH"
        print(f"     ✅ MATCH (within {VIX_RECONCILE_TOLERANCE_PCT}%)")
    else:
        status = f"DIVERGENT_{diff:.1f}PCT"
        print(f"     ⚠️  DIVERGENCE above {VIX_RECONCILE_TOLERANCE_PCT}% — yfinance may be")
        print(f"         stale or scraping a changed page. Treat VIX with caution.")
    return fv, d.date(), (round(diff, 3) if diff is not None else None), status


# ══════════════════════════════════════════════════════════════
# SECTION 3 — MARKETDATA FETCH UTILITIES  (stocks + options only)
# ══════════════════════════════════════════════════════════════

def fetch_daily_close(ticker, start, end):
    """Daily closes via MarketData /v1/stocks/candles/D/{symbol}/."""
    if not MARKETDATA_API_KEY:
        return pd.Series(dtype="float64")

    url, params = f"{MD_BASE}/stocks/candles/D/{ticker}/", {"from": start, "to": end}
    try:
        r = requests.get(url, headers=_md_headers(), params=params, timeout=30)
    except requests.exceptions.Timeout:
        print(f"  ⚠  {ticker}: timed out")
        return pd.Series(dtype="float64")
    except requests.exceptions.RequestException as e:
        print(f"  ⚠  {ticker}: network error — {e}")
        return pd.Series(dtype="float64")

    if r.status_code in (200, 203):
        try:
            data = r.json()
        except ValueError:
            print(f"  ⚠  {ticker}: non-JSON response")
            return pd.Series(dtype="float64")
        if data.get("s") != "ok" or not data.get("c"):
            print(f"  ⚠  {ticker}: s={data.get('s')} errmsg={data.get('errmsg','')}")
            return pd.Series(dtype="float64")
        raw_t = data["t"]
        unit = "ms" if (raw_t and raw_t[0] > 1e10) else "s"
        dates = pd.to_datetime(raw_t, unit=unit).tz_localize(None).normalize()
        s = pd.Series(data["c"], index=dates, name=ticker, dtype="float64").sort_index()
        print(f"  ✅ {ticker}: {len(s)} closes ({s.index[0].date()} → {s.index[-1].date()})")
        return s
    if r.status_code == 429:
        print(f"  ⚠  {ticker}: 429 rate limited")
    elif r.status_code == 404:
        print(f"  ⚠  {ticker}: 404 — no data for range")
    else:
        print(f"  ⚠  {ticker}: HTTP {r.status_code} — {r.text[:120]}")
    return pd.Series(dtype="float64")


def fetch_spy_chain():
    """SPY options chain via MarketData. This part of MarketData works — 1906 contracts."""
    if not MARKETDATA_API_KEY:
        return pd.DataFrame(), None

    print("\n" + "─" * 50)
    print("SPY OPTIONS CHAIN  (MarketData.app)")
    print("─" * 50)

    spot = None
    try:
        qr = requests.get(f"{MD_BASE}/stocks/quotes/SPY/", headers=_md_headers(), timeout=30)
        if qr.status_code in (200, 203):
            qd = qr.json()
            if qd.get("s") == "ok" and qd.get("last"):
                spot = float(qd["last"][0])
                print(f"  💵 SPY spot (live quote): {spot:.2f}")
            elif qd.get("s") == "ok" and qd.get("mid"):
                spot = float(qd["mid"][0])
                print(f"  💵 SPY spot (mid quote): {spot:.2f}")
    except requests.exceptions.RequestException as e:
        print(f"  ⚠  SPY quote error: {e}")

    if spot is None:
        recent = fetch_daily_close("SPY", START_5D, TODAY)
        v, _ = _clean_last(recent)
        if v is not None:
            spot = v
            print(f"  💵 SPY spot (last candle close): {spot:.2f}")

    if spot is None:
        print("  ❌ SPY spot unavailable — cannot build chain")
        return pd.DataFrame(), None

    today_d = date.today()
    real_expiries = []
    try:
        er = requests.get(f"{MD_BASE}/options/expirations/SPY/", headers=_md_headers(), timeout=30)
        if er.status_code in (200, 203):
            ed = er.json()
            if ed.get("s") == "ok" and ed.get("expirations"):
                all_exp = [date.fromisoformat(e) for e in ed["expirations"]]
                preview = [e.isoformat() for e in all_exp[:10]]
                suffix = "..." if len(all_exp) > 10 else ""
                print(f"  📅 Available expirations ({len(all_exp)}): {preview}{suffix}")
                for near in [today_d, today_d + timedelta(days=1)]:
                    if near in all_exp and near.isoformat() not in real_expiries:
                        real_expiries.append(near.isoformat())
                for target_dte in [9, 30, 60, 90]:
                    target = today_d + timedelta(days=target_dte)
                    closest = min(all_exp, key=lambda d: abs((d - target).days))
                    if closest.isoformat() not in real_expiries:
                        real_expiries.append(closest.isoformat())
                real_expiries.sort()
                print(f"  📅 Real expiries selected: {real_expiries}")
    except requests.exceptions.RequestException as e:
        print(f"  ⚠  Expiry fetch error: {e}")

    if not real_expiries:
        real_expiries = [(today_d + timedelta(days=n)).isoformat() for n in (9, 30, 60, 90)]
        print(f"  ⚠  Using calculated expiries: {real_expiries}")

    url = f"{MD_BASE}/options/chain/SPY/"
    all_contracts = []
    for expiry in real_expiries:
        try:
            r = requests.get(url, headers=_md_headers(),
                             params={"expiration": expiry}, timeout=30)
            if r.status_code == 429:
                time.sleep(5)
                r = requests.get(url, headers=_md_headers(),
                                 params={"expiration": expiry}, timeout=30)
            if r.status_code not in (200, 203):
                print(f"  ⚠  Expiry {expiry}: HTTP {r.status_code}")
                continue
            data = r.json()
            if data.get("s") != "ok":
                print(f"  ⚠  Expiry {expiry}: s={data.get('s')}")
                continue
            n = len(data.get("optionSymbol", []))
            if n > 0:
                all_contracts.append(data)
                print(f"  ✅ Expiry {expiry}: {n} contracts "
                      f"(DTE {(date.fromisoformat(expiry) - today_d).days})")
        except requests.exceptions.RequestException as e:
            print(f"  ⚠  Expiry {expiry}: {e}")
            continue

    if not all_contracts:
        print("  ❌ No contracts returned")
        return pd.DataFrame(), None

    rows = []
    for data in all_contracts:
        for i in range(len(data.get("optionSymbol", []))):
            rows.append({
                "strike": data["strike"][i] if "strike" in data else None,
                "dte":    data["dte"][i] if "dte" in data else None,
                "ctype":  str(data["side"][i]).upper() if "side" in data else "?",
                "iv":     data["iv"][i] if "iv" in data else None,
                "oi":     data["openInterest"][i] if "openInterest" in data else 0,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(), None
    df = df.dropna(subset=["iv", "strike", "dte"])
    df = df[df["dte"] > 0].copy()
    df["iv"] = df["iv"].astype(float)
    df["strike"] = df["strike"].astype(float)
    df["dte"] = df["dte"].astype(int)
    df["oi"] = df["oi"].fillna(0).astype(float)
    print(f"  ✅ {len(df)} total contracts | DTE {df['dte'].min()}–{df['dte'].max()}")
    return df, spot


def atm_iv_for_dte(df, dte_lo, dte_hi, spot, atm_band=0.05):
    """
    OI-weighted ATM implied volatility over a DTE window.

    THIS IS NOT VIX. CBOE's VIX is a variance-swap replication across the full strike
    chain out to zero-bid; the OTM put wing carries most of the weight. A ±5% band
    excludes that wing entirely, and covers progressively less of the distribution
    as tenor extends (±2.31 SD at 9 DTE, ±1.16 SD at 27, ±0.66 SD at 83).
    Retained as SPY_ATM_IV_* because the gap versus real VIX is a useful skew measure.
    """
    if df.empty:
        return None
    sub = df[(df["dte"] >= dte_lo) & (df["dte"] <= dte_hi)]
    if sub.empty:
        return None
    atm = sub[(sub["strike"] >= spot * (1 - atm_band)) & (sub["strike"] <= spot * (1 + atm_band))]
    if len(atm) < 3:
        atm = sub
    w = atm["oi"].clip(lower=1)
    return round(float((atm["iv"] * w).sum() / w.sum()) * 100, 2)


# ══════════════════════════════════════════════════════════════
# SECTION 4 — USD STRENGTH MONITOR  (unchanged logic)
# ══════════════════════════════════════════════════════════════

def fetch_usd_strength():
    print("\n" + "─" * 50)
    print("USD STRENGTH MONITOR")
    print("─" * 50)

    result = {"USD_Proxy": "UUP", "USD_Latest": None,
              "USD_5d_Pct": None, "USD_20d_Pct": None, "USD_60d_Pct": None,
              "USD_Trend": "MISSING", "USD_Strength": "MISSING",
              "EURUSD_Proxy_5d": None, "JPYUSD_Proxy_5d": None}

    uup = fetch_daily_close("UUP", START_90D, TODAY)
    latest, _ = _clean_last(uup)
    if latest is None:
        print("  ⚠  UUP unavailable")
        return result
    result["USD_Latest"] = round(latest, 3)

    def pct_chg(s, n):
        s = s.dropna()
        if len(s) < 2:
            return None
        lb = min(n, len(s) - 1)
        return round(float((s.iloc[-1] - s.iloc[-lb]) / s.iloc[-lb] * 100), 2)

    result["USD_5d_Pct"], result["USD_20d_Pct"], result["USD_60d_Pct"] = \
        pct_chg(uup, 5), pct_chg(uup, 20), pct_chg(uup, 60)
    c5, c20, c60 = (result["USD_5d_Pct"] or 0, result["USD_20d_Pct"] or 0,
                    result["USD_60d_Pct"] or 0)

    if   c5 > 0.5 and c20 > 0:  trend = "STRENGTHENING"
    elif c5 < -0.5 and c20 < 0: trend = "WEAKENING"
    elif c5 > 0.5 and c20 < 0:  trend = "BOUNCING"
    elif c5 < -0.5 and c20 > 0: trend = "FADING"
    else:                       trend = "STABLE"
    result["USD_Trend"] = trend

    if   c60 > 3:  strength = "STRONG"
    elif c60 > 1:  strength = "FIRM"
    elif c60 < -3: strength = "WEAK"
    elif c60 < -1: strength = "SOFTENING"
    else:          strength = "NEUTRAL"
    result["USD_Strength"] = strength

    print(f"  💵 UUP: {latest:.3f}  |  5d:{c5:+.2f}%  20d:{c20:+.2f}%  60d:{c60:+.2f}%")
    print(f"     Trend: {trend}  |  Strength: {strength}  (60d window)")

    for etf, label, key in [("FXE", "EUR/USD", "EURUSD_Proxy_5d"),
                            ("FXY", "JPY/USD", "JPYUSD_Proxy_5d")]:
        s = fetch_daily_close(etf, START_5D, TODAY)
        if not s.dropna().empty:
            chg = pct_chg(s, 5)
            result[key] = chg
            confirms = "✅ CONFIRMS" if (chg is not None and (
                (trend == "STRENGTHENING" and chg < 0) or
                (trend == "WEAKENING" and chg > 0))) else "⚠️  DIVERGES"
            print(f"     {label} 5d: {chg:+.2f}%  {confirms}")
        else:
            print(f"     {label}: unavailable")
    return result


# ══════════════════════════════════════════════════════════════
# SECTION 5 — VIX ANALYTICS
# ══════════════════════════════════════════════════════════════

def build_vix_analytics():
    print("\n" + "─" * 50)
    print("VIX ANALYTICS")
    print("─" * 50)

    r = {
        # v3.0 schema — preserved
        "VIX_Proxy": None, "VIX_Direct": None, "VIX9D_Proxy": None, "VIX3M_Proxy": None,
        "VVIX_Proxy": None, "VVIX_Stress": "MISSING", "VIX_Level": "MISSING",
        "VIX_Momentum": "UNKNOWN", "VIX_Structure": "UNKNOWN", "Term_Slope": None,
        "IV_Pct_Rank": None, "IV_Trend": "UNKNOWN",
        "Fear_Phase": "UNKNOWN", "Vol_Edge": "NEUTRAL", "VIX_Data_Flag": "MISSING",
        # v4.0 additions
        "VIX_Source": "NONE", "VIX_Obs_Date": None,
        "FRED_VIXCLS": None, "FRED_VIXCLS_Date": None,
        "VIX_Reconcile_Pct": None, "VIX_Reconcile_Status": "NOT_RUN",
        "VIX_Pct_Rank_1y": None, "VVIX_Source": "NONE",
        "SPY_ATM_IV_9d": None, "SPY_ATM_IV_30d": None, "SPY_ATM_IV_3M": None,
        "ATM_vs_VIX_Gap_Pct": None,
        "RealisedVol_20d": None, "RealisedVol_Trend": "UNKNOWN",
        "IV_vs_RealisedVol_Pct": None,
    }

    # ── 1. Real VIX ───────────────────────────────────────────────────────────
    vix_data = fetch_real_vix_suite()
    vix_series = vix_data.get("VIX")
    vix_val, vix_obs = _clean_last(vix_series)

    fred_series = fetch_fred_vix()

    # ── 2. Fallback ladder if yfinance fails entirely ─────────────────────────
    if vix_val is None and fred_series is not None:
        vix_val, vix_obs = _clean_last(fred_series)
        if vix_val is not None:
            r["VIX_Source"], r["VIX_Data_Flag"] = "FRED_VIXCLS", "DIRECT_LAGGED"
            print(f"  ℹ️  yfinance unavailable — using FRED VIXCLS {vix_val:.2f} ({vix_obs})")
    elif vix_val is not None:
        r["VIX_Source"], r["VIX_Data_Flag"] = "YFINANCE", "DIRECT"

    r["VIX_Direct"], r["VIX_Proxy"] = vix_val, vix_val
    r["VIX_Obs_Date"] = str(vix_obs) if vix_obs else None

    # ── 3. Reconciliation ─────────────────────────────────────────────────────
    fv, fd, diff, status = reconcile_vix(vix_series, fred_series)
    r["FRED_VIXCLS"], r["FRED_VIXCLS_Date"] = fv, (str(fd) if fd else None)
    r["VIX_Reconcile_Pct"], r["VIX_Reconcile_Status"] = diff, status
    if status.startswith("DIVERGENT"):
        r["VIX_Data_Flag"] = "DIRECT_DIVERGENT"

    # ── 4. Term structure from REAL indices ───────────────────────────────────
    v9, _  = _clean_last(vix_data.get("VIX9D"))
    v3m, _ = _clean_last(vix_data.get("VIX3M"))
    vvix, _ = _clean_last(vix_data.get("VVIX"))
    r["VIX9D_Proxy"], r["VIX3M_Proxy"] = v9, v3m

    if vvix is not None:
        r["VVIX_Proxy"], r["VVIX_Source"] = vvix, "YFINANCE_REAL"
        r["VVIX_Stress"] = ("ELEVATED" if vvix > 110 else
                            "HIGH" if vvix > 95 else "NORMAL")
        print(f"\n  📊 VVIX (real): {vvix:.2f}  [{r['VVIX_Stress']}]")

    if vix_val is not None and v3m is not None:
        r["VIX_Structure"] = ("CONTANGO" if v3m > vix_val else
                              "BACKWARDATION" if v3m < vix_val else "FLAT")
        r["Term_Slope"] = round((v3m - vix_val) / vix_val * 100, 2)
        print(f"  📊 Term structure: {r['VIX_Structure']}  slope={r['Term_Slope']:+.2f}%")
        if v9 is not None:
            print(f"     VIX9D {v9:.2f}  →  VIX {vix_val:.2f}  →  VIX3M {v3m:.2f}")

    # ── 5. Level, momentum, real percentile rank ──────────────────────────────
    if vix_val is not None:
        r["VIX_Level"] = ("COMPLACENCY" if vix_val < 12 else "NORMAL" if vix_val < 20 else
                          "ELEVATED" if vix_val < 30 else "FEAR" if vix_val < 45 else
                          "EXTREME_PANIC")

        if vix_series is not None:
            hist = vix_series.dropna()
            # Real IV rank: current VIX against 1y of its OWN history.
            one_yr = hist[hist.index >= (hist.index.max() - pd.Timedelta(days=365))]
            if len(one_yr) >= 30:
                r["VIX_Pct_Rank_1y"] = round(float((one_yr < vix_val).mean() * 100), 1)
                lbl = ("HIGH" if r["VIX_Pct_Rank_1y"] > 75 else
                       "MEDIUM" if r["VIX_Pct_Rank_1y"] > 40 else "LOW")
                print(f"  📊 VIX 1y percentile rank: {r['VIX_Pct_Rank_1y']:.0f}th [{lbl}]  "
                      f"(n={len(one_yr)})")

            # VIX momentum — measures VIX. v3.0 put realised-vol trend in this field.
            if len(hist) >= 5:
                ma5, cur = float(hist.rolling(5).mean().iloc[-1]), float(hist.iloc[-1])
                r["VIX_Momentum"] = ("RISING" if cur > ma5 * 1.03 else
                                     "FALLING" if cur < ma5 * 0.97 else "STABLE")
                print(f"  📊 VIX momentum: {r['VIX_Momentum']}  "
                      f"(cur={cur:.2f} MA5={ma5:.2f})")

    # ── 6. SPY options chain — ATM IV, honestly labelled ──────────────────────
    chain, spot = fetch_spy_chain()
    iv_history = None

    if not chain.empty and spot is not None:
        r["SPY_ATM_IV_9d"]  = atm_iv_for_dte(chain, 5, 13, spot)
        r["SPY_ATM_IV_30d"] = atm_iv_for_dte(chain, 25, 35, spot)
        r["SPY_ATM_IV_3M"]  = atm_iv_for_dte(chain, 75, 105, spot)
        if r["SPY_ATM_IV_3M"] is None:
            mx = int(chain["dte"].max())
            if mx >= 20:
                r["SPY_ATM_IV_3M"] = atm_iv_for_dte(chain, int(mx * 0.65), mx, spot)

        print(f"\n  📐 SPY ATM IV (NOT VIX — ±5% strike band):")
        for lbl, key in [("9d", "SPY_ATM_IV_9d"), ("30d", "SPY_ATM_IV_30d"),
                         ("3M", "SPY_ATM_IV_3M")]:
            v = r[key]
            print(f"     {lbl:4s}: {v:.2f}" if v is not None else f"     {lbl:4s}: N/A")

        # Gap between ATM IV and real VIX ≈ the skew premium. A genuine signal.
        if vix_val and r["SPY_ATM_IV_30d"]:
            r["ATM_vs_VIX_Gap_Pct"] = round(
                (r["SPY_ATM_IV_30d"] - vix_val) / vix_val * 100, 2)
            print(f"     ATM(30d) vs VIX gap: {r['ATM_vs_VIX_Gap_Pct']:+.2f}%  "
                  f"(negative = VIX carries skew premium ATM IV misses)")

    # ── 7. Realised vol — kept, correctly named ───────────────────────────────
    spy_hist = fetch_daily_close("SPY", START_90D, TODAY)
    if not spy_hist.dropna().empty and len(spy_hist.dropna()) >= 22:
        rets = spy_hist.dropna().pct_change().dropna()
        realised = (rets.rolling(20).std() * (252 ** 0.5) * 100).dropna()
        if not realised.empty:
            iv_history = realised
            r["RealisedVol_20d"] = round(float(realised.iloc[-1]), 2)
            print(f"\n  📈 Realised vol (20d): {r['RealisedVol_20d']:.2f}  "
                  f"[90d range {realised.min():.1f}–{realised.max():.1f}]")

            if vix_val is not None:
                # v3.0 called this IV_Pct_Rank. It is implied-vs-realised — a variance
                # premium measure, not an IV rank. Preserved under both names.
                pct = round(float((realised < vix_val).mean() * 100), 1)
                r["IV_vs_RealisedVol_Pct"] = pct
                r["IV_Pct_Rank"] = pct
                print(f"     VIX vs realised distribution: {pct:.0f}th pct "
                      f"(variance premium measure — NOT IV rank)")

            if len(realised) >= 5:
                ma5, cur = float(realised.rolling(5).mean().iloc[-1]), float(realised.iloc[-1])
                rv_trend = ("RISING" if cur > ma5 * 1.03 else
                            "FALLING" if cur < ma5 * 0.97 else "STABLE")
                r["RealisedVol_Trend"] = rv_trend
                r["IV_Trend"] = rv_trend        # legacy field, same value as v3.0
                print(f"     Realised vol trend: {rv_trend}")

    # ── 8. Fear phase — now driven by REAL VIX momentum ───────────────────────
    level, momentum = r["VIX_Level"], r["VIX_Momentum"]
    structure, vvix_st = r["VIX_Structure"], r["VVIX_Stress"]

    if   level in ("COMPLACENCY", "NORMAL") and momentum == "RISING":
        phase, edge = "EARLY_FEAR_BUILD", "BUY_VOL"
    elif level == "ELEVATED" and momentum == "RISING":
        phase, edge = "MID_FEAR_EXPANSION", "BUY_VOL"
    elif level in ("FEAR", "EXTREME_PANIC") and momentum == "RISING":
        phase, edge = "PANIC_PEAK", "NEUTRAL"
    elif level in ("FEAR", "EXTREME_PANIC") and momentum == "FALLING":
        phase, edge = "FEAR_UNWIND", "SELL_VOL"
    elif structure == "CONTANGO":
        phase, edge = "CALM_CARRY", "SELL_VOL"
    else:
        phase, edge = "TRANSITION", "NEUTRAL"

    if vvix_st == "ELEVATED" and edge == "SELL_VOL":
        edge, phase = "NEUTRAL", phase + "_VVIX_OVERRIDE"

    # Degrade the verdict when VIX itself is not trustworthy.
    if r["VIX_Data_Flag"] in ("MISSING", "DIRECT_DIVERGENT") or vix_val is None:
        edge, phase = "NEUTRAL", phase + "_DATA_SUSPECT"
        print(f"\n  ⚠️  VIX flag = {r['VIX_Data_Flag']} — Vol_Edge suppressed to NEUTRAL")

    r["Fear_Phase"], r["Vol_Edge"] = phase, edge

    # NOTE: CALM_CARRY/SELL_VOL is the fall-through branch of this cascade — it fires
    # whenever the curve is in normal contango and momentum is not RISING. Treat it as
    # "no other condition matched", not as a positive finding.
    if phase.startswith("CALM_CARRY"):
        print("\n  ℹ️  CALM_CARRY is this cascade's fall-through branch "
              "(contango + momentum not RISING). Not a positive signal.")

    return r, iv_history, vix_series, fred_series


# ══════════════════════════════════════════════════════════════
# SECTION 6 — USD / VIX CONFLICT  (unchanged)
# ══════════════════════════════════════════════════════════════

def compute_usd_vix_conflict(usd, vix_res):
    usd_trend = usd.get("USD_Trend", "STABLE")
    vix_level = vix_res.get("VIX_Level", "NORMAL")
    vix_trend = vix_res.get("VIX_Momentum", "STABLE")   # now real VIX momentum

    usd_up   = usd_trend in ("STRENGTHENING", "BOUNCING", "FIRM")
    usd_down = usd_trend in ("WEAKENING", "FADING")
    vix_hi   = vix_level in ("ELEVATED", "FEAR", "EXTREME_PANIC")
    vix_lo   = vix_level in ("COMPLACENCY", "NORMAL")

    if   usd_up and vix_hi and vix_trend == "RISING":
        return "RISK-OFF FLIGHT — USD+VIX both rising. Consistent crisis signal."
    elif usd_down and vix_hi:
        return "DOLLAR STRESS — VIX elevated but USD losing safe-haven bid."
    elif usd_up and vix_lo and vix_trend == "FALLING":
        return "RISK-ON STRONG DOLLAR — Growth/rate-differential driven. Bullish equities."
    elif usd_down and vix_lo:
        return "RISK-ON WEAK DOLLAR — Reflation/EM rotation. Positive for commodities."
    elif usd_up and vix_hi and vix_trend == "FALLING":
        return "FEAR UNWIND — VIX falling but still elevated. USD strength may moderate."
    return "NEUTRAL/TRANSITIONAL — No clear USD/VIX regime signal."


# ══════════════════════════════════════════════════════════════
# SECTION 7 — DASHBOARD
# ══════════════════════════════════════════════════════════════

def plot_dashboard(usd_series, iv_history, vix_res, usd_res, vix_series, fred_series):
    if plt is None:
        print("ℹ️  Dashboard PNG skipped (matplotlib not installed)")
        return None
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.patch.set_facecolor("#0d0d1a")
    for ax in axes.flat:
        ax.set_facecolor("#0d0d1a")
        ax.tick_params(colors="white")
        for sp in ax.spines.values():
            sp.set_edgecolor("#333366")

    def style(ax, title):
        ax.set_title(title, color="white", fontsize=10, pad=6)
        ax.grid(True, alpha=0.2, color="#444466")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")

    # 1 — VIX history with FRED overlay
    ax = axes[0, 0]
    if vix_series is not None and not vix_series.dropna().empty:
        s = vix_series.dropna().tail(180)
        ax.plot(s.index, s.values, color="#e74c3c", linewidth=2, label="VIX (yfinance)")
        if fred_series is not None and not fred_series.dropna().empty:
            f = fred_series.dropna()
            f = f[f.index >= s.index.min()]
            if not f.empty:
                ax.plot(f.index, f.values, color="#f1c40f", linewidth=1,
                        linestyle=":", label="FRED VIXCLS")
        style(ax, f"VIX — {vix_res.get('VIX_Source','')} "
                  f"[{vix_res.get('VIX_Reconcile_Status','')}]")
        ax.set_ylabel("VIX", color="white")
        ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=8)
    else:
        ax.text(0.5, 0.5, "VIX unavailable", transform=ax.transAxes,
                color="white", ha="center")
        style(ax, "VIX")

    # 2 — realised vol vs VIX
    ax = axes[0, 1]
    if iv_history is not None and len(iv_history) > 0:
        ax.plot(iv_history.index, iv_history.values, color="#3498db",
                linewidth=2, label="Realised Vol (20d)")
        v = vix_res.get("VIX_Proxy")
        if v:
            ax.axhline(v, color="#e74c3c", linestyle="--", linewidth=1.5,
                       label=f"VIX {v:.1f}")
        a = vix_res.get("SPY_ATM_IV_30d")
        if a:
            ax.axhline(a, color="#2ecc71", linestyle=":", linewidth=1.5,
                       label=f"SPY ATM IV 30d {a:.1f}")
        style(ax, "Realised Vol vs VIX vs ATM IV")
        ax.set_ylabel("Annualised Vol %", color="white")
        ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=8)
    else:
        ax.text(0.5, 0.5, "Realised vol unavailable", transform=ax.transAxes,
                color="white", ha="center")
        style(ax, "Realised Vol")

    # 3 — term structure, real vs ATM proxy
    ax = axes[1, 0]
    labels = ["9D", "30D", "3M"]
    real = [vix_res.get("VIX9D_Proxy"), vix_res.get("VIX_Proxy"), vix_res.get("VIX3M_Proxy")]
    atm  = [vix_res.get("SPY_ATM_IV_9d"), vix_res.get("SPY_ATM_IV_30d"),
            vix_res.get("SPY_ATM_IV_3M")]
    if any(v is not None for v in real):
        x = np.arange(len(labels))
        ax.bar(x - 0.2, [v or 0 for v in real], 0.4, color="#e74c3c",
               alpha=0.9, label="Real VIX")
        ax.bar(x + 0.2, [v or 0 for v in atm], 0.4, color="#2ecc71",
               alpha=0.7, label="SPY ATM IV")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        for i, v in enumerate(real):
            if v:
                ax.text(i - 0.2, v + 0.3, f"{v:.1f}", ha="center",
                        color="white", fontsize=8)
        for i, v in enumerate(atm):
            if v:
                ax.text(i + 0.2, v + 0.3, f"{v:.1f}", ha="center",
                        color="white", fontsize=8)
        sl = vix_res.get("Term_Slope")
        style(ax, f"Term Structure [{vix_res.get('VIX_Structure','')}"
                  + (f"  slope={sl:+.1f}%" if sl is not None else "") + "]")
        ax.set_ylabel("Vol %", color="white")
        ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=8)
    else:
        ax.text(0.5, 0.5, "Term data unavailable", transform=ax.transAxes,
                color="white", ha="center")
        style(ax, "Term Structure")

    # 4 — summary
    ax = axes[1, 1]
    ax.axis("off")
    lines = [
        f"DATE:           {TODAY}",
        f"VIX SOURCE:     {vix_res.get('VIX_Source','N/A')}  [{vix_res.get('VIX_Data_Flag','')}]",
        f"VIX OBS DATE:   {vix_res.get('VIX_Obs_Date','N/A')}",
        "",
        f"VIX:            {vix_res.get('VIX_Proxy','N/A')}",
        f"FRED VIXCLS:    {vix_res.get('FRED_VIXCLS','N/A')} ({vix_res.get('FRED_VIXCLS_Date','')})",
        f"RECONCILE:      {vix_res.get('VIX_Reconcile_Status','')} "
        f"({vix_res.get('VIX_Reconcile_Pct','N/A')}%)",
        "",
        f"VIX LEVEL:      {vix_res.get('VIX_Level','N/A')}",
        f"VIX MOMENTUM:   {vix_res.get('VIX_Momentum','N/A')}",
        f"VIX 1Y RANK:    {vix_res.get('VIX_Pct_Rank_1y','N/A')}th pct",
        f"VVIX:           {vix_res.get('VVIX_Proxy','N/A')} [{vix_res.get('VVIX_Stress','')}]",
        "",
        f"FEAR PHASE:     {vix_res.get('Fear_Phase','N/A')}",
        f"VOL EDGE:       {vix_res.get('Vol_Edge','N/A')}",
        "",
        f"SPY ATM 30d:    {vix_res.get('SPY_ATM_IV_30d','N/A')}  "
        f"(gap {vix_res.get('ATM_vs_VIX_Gap_Pct','N/A')}%)",
        f"REALISED 20d:   {vix_res.get('RealisedVol_20d','N/A')}",
        "",
        f"USD (UUP):      {usd_res.get('USD_Latest','N/A')}  "
        f"{usd_res.get('USD_Trend','')} / {usd_res.get('USD_Strength','')}",
    ]
    ax.text(0.02, 0.98, "\n".join(lines), transform=ax.transAxes, color="white",
            fontsize=8.5, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="#1a1a2e", alpha=0.85))
    style(ax, "Summary")

    plt.suptitle(f"AVSHUNTER VIX + USD MONITOR  |  {TODAY}  |  v4.0 REAL VIX",
                 color="white", fontsize=13, y=1.01)
    plt.tight_layout()
    path = OUTPUT_DIR / "avshunter_vix_usd_dashboard.png"
    plt.savefig(str(path), dpi=150, bbox_inches="tight", facecolor="#0d0d1a")
    if IN_COLAB:
        plt.show()
    plt.close(fig)
    print(f"📊 Chart saved: {path}")
    return path


# ══════════════════════════════════════════════════════════════
# SECTION 8 — MAIN
# ══════════════════════════════════════════════════════════════

def run_engine():
    print("\n" + "=" * 60)
    print(f"=== AVSHUNTER VIX + USD ENGINE v4.1  |  {TODAY} ===")
    print("=== VIX: yfinance (real CBOE) + FRED VIXCLS audit ===")
    print("=== Options chain: MarketData.app ===")
    print("=" * 60)

    md_ok = _validate_api_key()
    if not md_ok:
        print("ℹ️  Proceeding without MarketData — real VIX does not depend on it.")

    usd_result = fetch_usd_strength() if md_ok else {
        "USD_Proxy": "UUP", "USD_Latest": None, "USD_5d_Pct": None,
        "USD_20d_Pct": None, "USD_60d_Pct": None, "USD_Trend": "MISSING",
        "USD_Strength": "MISSING", "EURUSD_Proxy_5d": None, "JPYUSD_Proxy_5d": None}
    usd_series = fetch_daily_close("UUP", START_90D, TODAY) if md_ok else pd.Series(dtype="float64")

    vix_result, iv_history, vix_series, fred_series = build_vix_analytics()

    conflict = compute_usd_vix_conflict(usd_result, vix_result)
    vix_result["USD_VIX_Conflict"] = conflict

    print("\n" + "=" * 60)
    print("=== FINAL SUMMARY ===")
    print("=" * 60)
    for label, val in [
        ("VIX (real)",       vix_result.get("VIX_Proxy", "N/A")),
        ("VIX source",       f"{vix_result.get('VIX_Source')} [{vix_result.get('VIX_Data_Flag')}]"),
        ("VIX obs date",     vix_result.get("VIX_Obs_Date", "N/A")),
        ("FRED VIXCLS",      f"{vix_result.get('FRED_VIXCLS','N/A')} "
                             f"({vix_result.get('FRED_VIXCLS_Date','')})"),
        ("Reconciliation",   f"{vix_result.get('VIX_Reconcile_Status')} "
                             f"({vix_result.get('VIX_Reconcile_Pct','N/A')}%)"),
        ("VIX Level",        vix_result.get("VIX_Level", "N/A")),
        ("VIX Momentum",     vix_result.get("VIX_Momentum", "N/A")),
        ("VIX 1y pct rank",  f"{vix_result.get('VIX_Pct_Rank_1y','N/A')}th"),
        ("VIX Structure",    f"{vix_result.get('VIX_Structure')} "
                             f"slope={vix_result.get('Term_Slope','N/A')}%"),
        ("VVIX (real)",      f"{vix_result.get('VVIX_Proxy','N/A')} "
                             f"[{vix_result.get('VVIX_Stress')}]"),
        ("Fear Phase",       vix_result.get("Fear_Phase", "N/A")),
        ("Vol Edge",         vix_result.get("Vol_Edge", "N/A")),
        ("SPY ATM IV 30d",   f"{vix_result.get('SPY_ATM_IV_30d','N/A')} "
                             f"(gap {vix_result.get('ATM_vs_VIX_Gap_Pct','N/A')}%)"),
        ("Realised vol 20d", vix_result.get("RealisedVol_20d", "N/A")),
        ("USD (UUP)",        usd_result.get("USD_Latest", "N/A")),
        ("USD Trend",        usd_result.get("USD_Trend", "N/A")),
        ("USD/VIX Signal",   conflict),
    ]:
        print(f"  {label:<20}: {val}")

    output_row = {
        "Date": TODAY, "Engine_Version": "v4.1_yfinance_vix_fred_audit",
        # v3.0 schema
        "VIX_Proxy":      vix_result.get("VIX_Proxy"),
        "VIX_Direct":     vix_result.get("VIX_Direct"),
        "VIX9D_Proxy":    vix_result.get("VIX9D_Proxy"),
        "VIX3M_Proxy":    vix_result.get("VIX3M_Proxy"),
        "VVIX_Proxy":     vix_result.get("VVIX_Proxy"),
        "VVIX_Stress":    vix_result.get("VVIX_Stress"),
        "VIX_Level":      vix_result.get("VIX_Level"),
        "VIX_Momentum":   vix_result.get("VIX_Momentum"),
        "VIX_Structure":  vix_result.get("VIX_Structure"),
        "VIX_Term_Slope": vix_result.get("Term_Slope"),
        "IV_Pct_Rank":    vix_result.get("IV_Pct_Rank"),
        "IV_Trend":       vix_result.get("IV_Trend"),
        "Fear_Phase":     vix_result.get("Fear_Phase"),
        "Vol_Edge":       vix_result.get("Vol_Edge"),
        "VIX_Data_Flag":  vix_result.get("VIX_Data_Flag"),
        # v4.0 additions
        "VIX_Source":            vix_result.get("VIX_Source"),
        "VIX_Obs_Date":          vix_result.get("VIX_Obs_Date"),
        "FRED_VIXCLS":           vix_result.get("FRED_VIXCLS"),
        "FRED_VIXCLS_Date":      vix_result.get("FRED_VIXCLS_Date"),
        "VIX_Reconcile_Pct":     vix_result.get("VIX_Reconcile_Pct"),
        "VIX_Reconcile_Status":  vix_result.get("VIX_Reconcile_Status"),
        "VIX_Pct_Rank_1y":       vix_result.get("VIX_Pct_Rank_1y"),
        "VVIX_Source":           vix_result.get("VVIX_Source"),
        "SPY_ATM_IV_9d":         vix_result.get("SPY_ATM_IV_9d"),
        "SPY_ATM_IV_30d":        vix_result.get("SPY_ATM_IV_30d"),
        "SPY_ATM_IV_3M":         vix_result.get("SPY_ATM_IV_3M"),
        "ATM_vs_VIX_Gap_Pct":    vix_result.get("ATM_vs_VIX_Gap_Pct"),
        "RealisedVol_20d":       vix_result.get("RealisedVol_20d"),
        "RealisedVol_Trend":     vix_result.get("RealisedVol_Trend"),
        "IV_vs_RealisedVol_Pct": vix_result.get("IV_vs_RealisedVol_Pct"),
        # USD block
        "USD_Proxy": "UUP",
        "USD_Latest":     usd_result.get("USD_Latest"),
        "USD_5d_Pct":     usd_result.get("USD_5d_Pct"),
        "USD_20d_Pct":    usd_result.get("USD_20d_Pct"),
        "USD_60d_Pct":    usd_result.get("USD_60d_Pct"),
        "USD_Trend":      usd_result.get("USD_Trend"),
        "USD_Strength":   usd_result.get("USD_Strength"),
        "EURUSD_5d_Pct":  usd_result.get("EURUSD_Proxy_5d"),
        "JPYUSD_5d_Pct":  usd_result.get("JPYUSD_Proxy_5d"),
        "USD_VIX_Signal": conflict,
    }
    df_out = pd.DataFrame([output_row])

    file_path = OUTPUT_DIR / "avshunter_vix_engine_v3.csv"   # filename kept for pipeline
    try:
        df_out.to_csv(str(file_path), index=False)
        print(f"\n✅ CSV saved: {file_path}  ({os.path.getsize(str(file_path))} bytes)")
    except OSError as e:
        print(f"\n❌ CSV save error: {e}")
        return None

    try:
        chart_path = plot_dashboard(usd_series, iv_history, vix_result,
                                    usd_result, vix_series, fred_series)
    except Exception as e:
        print(f"⚠️  Chart failed (CSV unaffected): {e}")
        chart_path = None

    if IN_COLAB:
        try:
            from google.colab import files as _cf
            for _f in [file_path, chart_path]:
                if _f and os.path.exists(str(_f)):
                    _cf.download(str(_f))
                    print(f"⬇️  Downloaded: {pathlib.Path(str(_f)).name}")
        except Exception:
            pass

    return df_out


result_df = run_engine()

if result_df is not None:
    print(f"\n✅ v4.1 COMPLETE — outputs in {OUTPUT_DIR}")
    print("   • VIX from yfinance (real CBOE index), audited against FRED VIXCLS")
    print("   • VVIX is the real index, not iv_std * 400")
    print("   • ATM IV retained but labelled SPY_ATM_IV_* — it is not VIX")
    print("   • ⚠️  ROTATE the MarketData token — it was hardcoded in v3.0 in plaintext")
else:
    print("\n❌ Engine did not complete — check errors above")
    if not IN_COLAB:
        sys.exit(1)
