# === AVSHUNTER DAILY REGIME MODEL v1.6 ===
# CHANGES over v1.5:
# ✅ VIX source migrated: Polygon I:VIX (403 Forbidden) → MarketData.app indices candles
# ✅ Multi-source VIX fallback chain: MarketData → yfinance → Polygon → excluded
#    — no single source failure can leave the model without a fear signal
# ✅ VIX_Source + VIX_Data_Flag columns added — provenance is now recorded in output
# ✅ FIX: VIX_Level / HYG_Return_Proxy were scalars broadcast to every row
#    — now written as the true per-date series (was a lookahead hazard in backtests)
# ✅ FIX: VIX can no longer reduce row count — ETF frame built first, VIX joined by reindex
# ✅ FIX: label shift(-1) artifact — final row was silently labelled 0 instead of NaN
# ✅ Typed exception handling — no bare `except Exception: return None`
# ✅ Coverage guard — VIX excluded (not silently forward-filled) if history is too sparse
#
# NOTE: restoring VIX changes the feature set from 8 tickers to 9 (24 → 27 features).
#       Accuracy figures will NOT match v1.5 runs. That is expected, not a regression.
#
# v1.7 (7 Oct 2026) — runs unattended on the AVSHUNTER PC as well as in Colab. Model, features,
# thresholds and the avshunter_daily_macro_regime.csv schema are unchanged from v1.6; only how
# it runs:
# ✅ pip install only inside Colab (a local run never modifies the venv).
# ✅ Keys from the repo .env when not already in the environment (override=False).
# ✅ Error messages never echo a request URL (Polygon apiKey / MarketData token ride in it).
# ✅ Charts only inside Colab (they were display-only; no file was ever saved).
# ✅ UTF-8 console so a scheduled run cannot die printing an emoji.
# ✅ --output-dir (or AVSH_REGIME_OUTPUT_DIR) to test without touching dropbox\market_data.
# ✅ Exit code 1 when the CSV was not written, so a scheduler sees the failure.
# ⚠️ KNOWN, NOT FIXED HERE (awaiting ACK): each output row is dated one session AFTER the
#    features it was predicted from, and the latest session gets no prediction — the label
#    mask drops the final row, then `dates = features.index[-len(probs):]` re-dates the rest.
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_daily_regime_model_v1_7.py

# ════════════════════════════════════════════════════════════
# ── CONFIG ──────────────────────────────────────────────────
import argparse
import os
import pathlib
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
_parser = argparse.ArgumentParser(description="AVSHUNTER daily regime model")
_parser.add_argument("--output-dir", default=os.environ.get("AVSH_REGIME_OUTPUT_DIR"),
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

# Minimum fraction of trading days VIX must cover to be admitted to the feature set.
MIN_VIX_COVERAGE = 0.90
# ════════════════════════════════════════════════════════════

if IN_COLAB:
    get_ipython().system('pip install pandas numpy scikit-learn matplotlib requests yfinance --quiet')

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

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

# ── API keys ──────────────────────────────────────────────────────────────────
POLYGON_API_KEY = None
MARKETDATA_API_KEY = None

try:
    from google.colab import userdata

    try:
        POLYGON_API_KEY = userdata.get("POLYGON_API_KEY")
        print("✅ POLYGON_API_KEY loaded from Colab Secrets")
    except Exception as e:
        print(f"❌ POLYGON_API_KEY unavailable: {e}")

    try:
        MARKETDATA_API_KEY = userdata.get("MARKETDATA_API_KEY")
        if MARKETDATA_API_KEY:
            MARKETDATA_API_KEY = MARKETDATA_API_KEY.strip()
            print(f"✅ MARKETDATA_API_KEY loaded from Colab Secrets ({len(MARKETDATA_API_KEY)} chars)")
        else:
            print("⚠️  MARKETDATA_API_KEY is empty — check Secrets → Notebook access toggle")
    except Exception as e:
        print(f"⚠️  MARKETDATA_API_KEY unavailable: {e}")

except ImportError:
    POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
    MARKETDATA_API_KEY = os.environ.get("MARKETDATA_API_KEY")
    print("ℹ️  Not in Colab — keys read from environment variables")

if not POLYGON_API_KEY:
    raise SystemExit("❌ POLYGON_API_KEY is required for ETF price data — cannot proceed")

MD_BASE = "https://api.marketdata.app/v1"

end_date = datetime.today().strftime("%Y-%m-%d")
start_date = (datetime.today() - timedelta(days=730)).strftime("%Y-%m-%d")

ETF_TICKERS = {
    "SPY": "SPY",
    "IWM": "IWM",
    "UUP": "UUP",
    "TLT": "TLT",
    "IEF": "IEF",
    "GLD": "GLD",
    "USO": "USO",
    "HYG": "HYG",   # credit proxy
}


# ══════════════════════════════════════════════════════════════
# SECTION 1 — FETCH HELPERS
# ══════════════════════════════════════════════════════════════

def _normalise_index(series):
    """Force a tz-naive, date-only index so every source aligns identically."""
    idx = pd.to_datetime(series.index)
    try:
        if idx.tz is not None:
            idx = idx.tz_convert(None)
    except (AttributeError, TypeError):
        pass
    series.index = idx.normalize()
    return series[~series.index.duplicated(keep="last")].sort_index()


def fetch_polygon_daily(ticker, start, end):
    """Daily closes from Polygon v2 aggs. Returns pd.Series or None."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": POLYGON_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=30)
    except requests.exceptions.Timeout:
        print(f"❌ {ticker}: Polygon request timed out")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ {ticker}: Polygon network error — {type(e).__name__}")   # message carries apiKey
        return None

    if r.status_code == 403:
        print(f"❌ {ticker}: HTTP 403 Forbidden — plan does not include this ticker class")
        return None
    if r.status_code == 429:
        print(f"❌ {ticker}: HTTP 429 — rate limited")
        return None
    if r.status_code != 200:
        print(f"❌ {ticker}: HTTP {r.status_code}")
        return None

    try:
        results = r.json().get("results", [])
    except ValueError as e:
        print(f"❌ {ticker}: Polygon returned non-JSON — {e}")
        return None

    if not results:
        print(f"⚠️  {ticker}: empty results")
        return None

    df = pd.DataFrame(results)
    if "t" not in df.columns or "c" not in df.columns:
        print(f"❌ {ticker}: unexpected Polygon schema — {list(df.columns)}")
        return None

    df["t"] = pd.to_datetime(df["t"], unit="ms")
    return _normalise_index(df.set_index("t")["c"])


def _md_headers():
    return {"Authorization": f"Token {MARKETDATA_API_KEY}", "Accept": "application/json"}


def _md_parse_candles(payload, label):
    """Parse a MarketData.app candles response into a pd.Series."""
    if payload.get("s") == "no_data":
        print(f"  ⚠  {label}: s=no_data for requested range")
        return None
    if payload.get("s") != "ok":
        print(f"  ⚠  {label}: s={payload.get('s')} errmsg={payload.get('errmsg', '')}")
        return None

    closes, stamps = payload.get("c"), payload.get("t")
    if not closes or not stamps or len(closes) != len(stamps):
        print(f"  ⚠  {label}: malformed arrays (c={len(closes or [])} t={len(stamps or [])})")
        return None

    # MarketData returns unix seconds; some endpoints return milliseconds.
    unit = "ms" if stamps[0] > 1e10 else "s"
    idx = pd.to_datetime(stamps, unit=unit)
    return _normalise_index(pd.Series(closes, index=idx, dtype="float64"))


def fetch_marketdata_vix(start, end):
    """
    Daily VIX closes from MarketData.app indices candles.
    Endpoint: /v1/indices/candles/D/{symbol}/?from=&to=
    Tries header auth first, then query-param auth. Returns pd.Series or None.
    """
    if not MARKETDATA_API_KEY:
        print("  ⚠  MarketData: no API key — skipping")
        return None

    for symbol in ["VIX", "^VIX"]:
        url = f"{MD_BASE}/indices/candles/D/{symbol}/"
        base_params = {"from": start, "to": end}

        for auth_mode in ["header", "param"]:
            try:
                if auth_mode == "header":
                    r = requests.get(url, headers=_md_headers(), params=base_params, timeout=30)
                else:
                    r = requests.get(url, params={**base_params, "token": MARKETDATA_API_KEY}, timeout=30)
            except requests.exceptions.Timeout:
                print(f"  ⚠  MarketData {symbol} ({auth_mode}): timed out")
                continue
            except requests.exceptions.RequestException as e:
                print(f"  ⚠  MarketData {symbol} ({auth_mode}): network error — {type(e).__name__}")
                continue

            # 203 = cached / delayed data, still usable
            if r.status_code in (200, 203):
                try:
                    payload = r.json()
                except ValueError as e:
                    print(f"  ⚠  MarketData {symbol}: non-JSON response — {e}")
                    continue
                series = _md_parse_candles(payload, f"MarketData {symbol}")
                if series is not None and not series.empty:
                    tag = "delayed" if r.status_code == 203 else "live"
                    print(f"  ✅ MarketData {symbol} ({auth_mode}, {tag}): "
                          f"{len(series)} closes "
                          f"({series.index[0].date()} → {series.index[-1].date()}) "
                          f"latest {series.iloc[-1]:.2f}")
                    return series
            elif r.status_code == 401:
                print(f"  ⚠  MarketData {symbol} ({auth_mode}): 401 Unauthorized — token rejected")
            elif r.status_code == 402:
                print(f"  ⚠  MarketData {symbol}: 402 — plan does not cover indices")
                return None
            elif r.status_code == 404:
                print(f"  ⚠  MarketData {symbol} ({auth_mode}): 404 — symbol/endpoint not found")
                break   # try next symbol format
            elif r.status_code == 429:
                print(f"  ⚠  MarketData {symbol}: 429 — rate limited")
                return None
            else:
                print(f"  ⚠  MarketData {symbol} ({auth_mode}): HTTP {r.status_code} "
                      f"— {r.text[:100]}")

    return None


def fetch_yfinance_vix():
    """Fallback: ^VIX from yfinance. Returns pd.Series or None."""
    try:
        import yfinance as yf
    except ImportError:
        print("  ⚠  yfinance not installed — skipping fallback")
        return None

    try:
        hist = yf.Ticker("^VIX").history(period="2y", auto_adjust=False)
    except Exception as e:                      # yfinance raises a wide variety
        print(f"  ⚠  yfinance ^VIX error: {e}")
        return None

    if hist is None or hist.empty or "Close" not in hist.columns:
        print("  ⚠  yfinance ^VIX: empty response")
        return None

    series = _normalise_index(hist["Close"].astype("float64"))
    print(f"  ✅ yfinance ^VIX: {len(series)} closes "
          f"({series.index[0].date()} → {series.index[-1].date()}) "
          f"latest {series.iloc[-1]:.2f}")
    return series


def fetch_vix_with_fallback(start, end):
    """
    Ordered VIX acquisition. Returns (series, source_label, data_flag).
    Never raises. Returns (None, 'NONE', 'MISSING') if every source fails.
    """
    print("\n" + "─" * 50)
    print("VIX ACQUISITION (ordered fallback)")
    print("─" * 50)

    print("  → Tier 1: MarketData.app indices candles")
    series = fetch_marketdata_vix(start, end)
    if series is not None and not series.empty:
        return series, "MARKETDATA_INDICES", "DIRECT"

    print("  → Tier 2: yfinance ^VIX")
    series = fetch_yfinance_vix()
    if series is not None and not series.empty:
        return series, "YFINANCE", "DIRECT"

    print("  → Tier 3: Polygon I:VIX")
    series = fetch_polygon_daily("I:VIX", start, end)
    if series is not None and not series.empty:
        print(f"  ✅ Polygon I:VIX: {len(series)} bars, latest {series.iloc[-1]:.2f}")
        return series, "POLYGON_INDEX", "DIRECT"

    print("  ❌ All VIX sources failed — model will run without a fear signal")
    return None, "NONE", "MISSING"


# ══════════════════════════════════════════════════════════════
# SECTION 2 — DATA ACQUISITION
# ══════════════════════════════════════════════════════════════

print(f"\nFetching {start_date} to {end_date} (730 days)...\n")

etf_data = {}
for name, ticker in ETF_TICKERS.items():
    s = fetch_polygon_daily(ticker, start_date, end_date)
    if s is not None and not s.empty:
        etf_data[name] = s
        print(f"  ✅ {name} ({ticker})  — {len(s)} bars")
    else:
        print(f"  ⚠️  {name} ({ticker}) failed — excluded from feature set")

if "SPY" not in etf_data:
    raise SystemExit("❌ SPY unavailable — SPY is the prediction target, cannot proceed")

# FIX v1.6: build the ETF frame FIRST. VIX is joined afterwards by reindex,
# so a short or gappy VIX history can never truncate the training set.
daily_data = pd.DataFrame(etf_data).ffill().dropna()
print(f"\n📊 ETF frame: {daily_data.shape[0]} rows × {daily_data.shape[1]} cols")

if daily_data.empty:
    raise SystemExit("❌ ETF frame is empty after alignment — check fetch logs above")

vix_series, vix_source, vix_flag = fetch_vix_with_fallback(start_date, end_date)

vix_aligned = None
if vix_series is not None:
    aligned = vix_series.reindex(daily_data.index).ffill()
    coverage = float(aligned.notna().mean())
    print(f"\n📊 VIX coverage over ETF calendar: {coverage:.1%}")

    if coverage >= MIN_VIX_COVERAGE:
        aligned = aligned.bfill()               # fill any leading gap
        daily_data["VIX"] = aligned
        vix_aligned = aligned
        print(f"📊 VIX latest level : {aligned.iloc[-1]:.2f}  "
              f"(fear signal ACTIVE — source: {vix_source})")
    else:
        vix_flag = f"REJECTED_COVERAGE_{coverage:.0%}"
        vix_source = f"{vix_source}_REJECTED"
        print(f"⚠️  VIX coverage below {MIN_VIX_COVERAGE:.0%} — EXCLUDED rather than "
              f"forward-filled across large gaps")
else:
    print("⚠️  VIX MISSING — fear signal absent from feature set")

print(f"\n📊 daily_data: {daily_data.shape[0]} rows × {daily_data.shape[1]} cols")
print(f"   Tickers: {list(daily_data.columns)}")
print(f"   Range  : {daily_data.index[0].date()} → {daily_data.index[-1].date()}")

returns = daily_data.pct_change().dropna()
if returns.empty:
    raise SystemExit("❌ returns empty after pct_change — insufficient data rows")

if "HYG" in returns.columns:
    print(f"\n💳 HYG latest return: {returns['HYG'].iloc[-1] * 100:.2f}%  (credit proxy ACTIVE)")
else:
    print("\n⚠️  HYG MISSING — credit risk carried neutral in regime model")

if "TLT" in daily_data.columns and "IEF" in daily_data.columns:
    tlt_ief_spread = (daily_data["TLT"] - daily_data["IEF"]).pct_change().dropna()
    print(f"📊 TLT-IEF spread   : {tlt_ief_spread.iloc[-1] * 100:.3f}%  (duration proxy ACTIVE)")


# ══════════════════════════════════════════════════════════════
# SECTION 3 — FEATURES
# ══════════════════════════════════════════════════════════════

ema_returns = returns.ewm(span=3).mean()
zscore_returns = (returns - returns.rolling(60).mean()) / returns.rolling(60).std()
zscore_returns = zscore_returns.clip(lower=-3, upper=3)

features = pd.concat([returns, ema_returns, zscore_returns],
                     axis=1, keys=["raw", "ema", "z"]).dropna()

print("\n=== DATA QUALITY ===")
print(f"Rows     : {len(features)}")
print(f"Features : {features.shape[1]}  ({daily_data.shape[1]} tickers × 3 transforms)")
print(f"Range    : {features.index[0].date()} → {features.index[-1].date()}")
print(f"Missing  : {features.isna().sum().sum()}")
print(f"Extreme (>5σ): {(features.abs() > 5).any(axis=1).sum()}")
print(f"VIX in set: {'YES — ' + vix_source if 'VIX' in daily_data.columns else 'NO'}")

if len(features) < 100:
    print("⚠️  WARNING: fewer than 100 rows — model may be unreliable")


# ══════════════════════════════════════════════════════════════
# SECTION 4 — MODEL
# ══════════════════════════════════════════════════════════════

# FIX v1.6: shift(-1) leaves the final row undefined. v1.5 ran `.astype(int)`
# before reindexing, which turned that NaN into a spurious label of 0.
fwd = returns["SPY"].shift(-1)
labels = (fwd > 0).astype(float).where(fwd.notna()).reindex(features.index)

X = features.values
y = labels.values
mask = ~np.isnan(y)
X_clean, y_clean = X[mask], y[mask].astype(int)

if len(X_clean) < 50:
    raise SystemExit(f"❌ Only {len(X_clean)} labelled rows — insufficient to train")

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_clean)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y_clean, test_size=0.2, shuffle=False)

base_model = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
model = CalibratedClassifierCV(base_model, cv=3)
model.fit(X_train, y_train)

probs = model.predict_proba(X_test)[:, 1]
acc_at_060 = accuracy_score(y_test, (probs > 0.6).astype(int))
print(f"\n✅ Test Accuracy (fixed threshold=0.60): {acc_at_060:.2%}")

print("\n=== THRESHOLD ANALYSIS ===")
best_t, best_acc = 0.6, 0.0
for t in [0.50, 0.55, 0.60, 0.65, 0.70]:
    a = accuracy_score(y_test, (probs > t).astype(int))
    marker = " ← BEST" if a > best_acc else ""
    print(f"  {t:.2f}: {a:.2%}{marker}")
    if a > best_acc:
        best_acc, best_t = a, t

print(f"\nUsing threshold: {best_t:.2f}  (accuracy: {best_acc:.2%})")
print("⚠️  NOTE: this threshold was selected ON the test set, so the accuracy above is")
print(f"    optimistic. The honest out-of-sample figure is {acc_at_060:.2%} at the fixed 0.60.")

final_preds = (probs > best_t).astype(int)
dates = features.index[-len(probs):]


def confidence_level(prob):
    if prob > 0.7 or prob < 0.3:
        return "HIGH"
    if prob > 0.6 or prob < 0.4:
        return "MODERATE"
    return "LOW"


# FIX v1.6: v1.5 wrote `.iloc[-1]` scalars here, which pandas broadcast to every row.
# The columns looked like time series and contained a single snapshot — a lookahead
# hazard for anything backtesting against this file. Now aligned per-date.
hyg_col = returns["HYG"].reindex(dates) if "HYG" in returns.columns else pd.Series(index=dates, dtype="float64")

if vix_aligned is not None:
    vix_col = vix_aligned.reindex(dates)
else:
    vix_col = pd.Series(index=dates, dtype="float64")

regime_output = pd.DataFrame({
    "Date":               dates,
    "Regime_Probability": probs,
    "Regime":             ["Risk-On" if p == 1 else "Risk-Off" for p in final_preds],
    "Model_Accuracy":     best_acc,
    "Best_Threshold":     best_t,
    "Confidence_Level":   [confidence_level(p) for p in probs],
    "HYG_Return_Proxy":   hyg_col.values,
    "VIX_Level":          vix_col.values,
    "VIX_Source":         vix_source,
    "VIX_Data_Flag":      vix_flag,
}).set_index("Date")

out_path = OUTPUT_DIR / "avshunter_daily_macro_regime.csv"
try:
    regime_output.to_csv(out_path)
    print(f"\n✅ Saved: {out_path}  ({os.path.getsize(out_path)} bytes)")
except OSError as e:
    print(f"\n❌ CSV save failed: {e}")
    if not IN_COLAB:
        raise SystemExit(1)

print(f"   HYG credit proxy : {'ACTIVE' if hyg_col.notna().any() else 'MISSING — neutral'}")
if vix_col.notna().any():
    print(f"   VIX fear signal  : ACTIVE — {vix_col.dropna().iloc[-1]:.2f}  [{vix_source}]")
else:
    print(f"   VIX fear signal  : MISSING  [{vix_flag}]")
print(regime_output.tail(10))


# ══════════════════════════════════════════════════════════════
# SECTION 5 — VISUALISATION
# ══════════════════════════════════════════════════════════════

try:
    if plt is None:
        raise RuntimeError("charts are shown only in Colab")
    plt.figure(figsize=(12, 5))
    plt.plot(regime_output.index[-30:], regime_output["Regime_Probability"].iloc[-30:],
             marker="o", linewidth=2)
    plt.axhline(best_t, color="green", linestyle="--", alpha=0.5, label=f"Threshold ({best_t:.2f})")
    plt.axhline(1 - best_t, color="red", linestyle="--", alpha=0.5)
    plt.title(f"Daily Regime (Last 30 Days) — threshold {best_t:.2f}, accuracy {best_acc:.2%}")
    plt.ylabel("Probability (Risk-On)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

    if vix_col.notna().any():
        plt.figure(figsize=(12, 4))
        plt.plot(vix_col.index, vix_col.values, linewidth=2, color="crimson")
        plt.title(f"VIX — {vix_source} (fear signal in feature set)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    cum_cols = [c for c in ["SPY", "TLT", "HYG", "GLD"] if c in returns.columns]
    if cum_cols:
        returns[cum_cols].cumsum().plot(figsize=(14, 6),
                                        title="Cumulative Returns — SPY/TLT/HYG/GLD")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
except RuntimeError as e:
    print(f"ℹ️  Charts skipped: {e}")
except Exception as e:
    print(f"⚠️  Charting failed (data outputs are unaffected): {e}")

print(f"\n✅ v1.7 COMPLETE — outputs → {OUTPUT_DIR}")
print(f"   • VIX source      : {vix_source}  [{vix_flag}]")
print(f"   • Feature tickers : {list(daily_data.columns)}")
print(f"   • OOS accuracy    : {acc_at_060:.2%} at fixed 0.60 threshold")
