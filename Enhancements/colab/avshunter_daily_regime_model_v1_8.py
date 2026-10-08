# === AVSHUNTER DAILY REGIME MODEL v1.8 ===
# CHANGES over v1.5 (v1.6):
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
# v1.7 (7 Oct 2026) — runs unattended on the AVSHUNTER PC as well as in Colab: pip install
# only in Colab, keys from the repo .env, error messages never echo a request URL (Polygon
# apiKey / MarketData token ride in it), charts only in Colab, UTF-8 console, --output-dir
# (or AVSH_REGIME_OUTPUT_DIR) for testing, exit code 1 when the CSV was not written.
# Session cut-off (8 Oct 2026): with AVSH_SESSION_CUTOFF set (Run-MacroInputs.ps1), ETF and VIX
# series stop at the last completed US session, so a pre-open run predicts from the previous
# close and never from a partial pre-market bar. Unset (Colab / manual): unchanged.
#
# v1.8 (7 Oct 2026, ACK approved both fixes) — model, features and thresholds unchanged:
# ✅ FIX: a prediction is dated by the session whose close it was computed from. v1.7 dated
#    every row one session late (the label mask dropped the final row, then
#    `features.index[-len(probs):]` re-dated the rest), and the newest session — the one that
#    matters for the next open — never got a prediction. It now gets a LIVE prediction.
# ✅ FIX: avshunter_daily_macro_regime.csv is an append-only record of the LIVE call made on
#    each session. A later run never rewrites an older row (a same-session rerun replaces only
#    its own row). v1.7 retrained and re-predicted the whole history every run.
#    The first v1.8 run moves the old re-predicted file to market_data\archive\ (kept, not
#    deleted, and outside every reader's exact filename).
# ✅ The re-predicted test period (the honest out-of-sample check) is written separately to
#    avshunter_daily_macro_regime_backtest.csv, Prediction_Kind = BACKTEST, rewritten each run.
# ✅ Importing this file does nothing; work happens in main() (tests import the functions).
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_daily_regime_model_v1_8.py

import argparse
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

ENGINE_VERSION = "v1.8_live_append_only"
REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
LOG_NAME = "avshunter_daily_macro_regime.csv"
BACKTEST_NAME = "avshunter_daily_macro_regime_backtest.csv"
LOG_KIND_COLUMN = "Prediction_Kind"

# Minimum fraction of trading days VIX must cover to be admitted to the feature set.
MIN_VIX_COVERAGE = 0.90

MD_BASE = "https://api.marketdata.app/v1"
POLYGON_API_KEY = None          # set by main()
MARKETDATA_API_KEY = None       # set by main()

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


def session_cutoff():
    """Last completed US session from AVSH_SESSION_CUTOFF (set by Run-MacroInputs.ps1), or None
    when unset (Colab / manual runs keep the previous behaviour)."""
    value = os.environ.get("AVSH_SESSION_CUTOFF", "").strip()
    return pd.Timestamp(value).normalize() if value else None


def cut_to_session(data, cutoff):
    """Drop rows dated after the last completed US session, so a pre-open run never treats a
    partial "today" bar (pre-market trades, overnight VIX) as a finished session."""
    if cutoff is None or data is None or len(data) == 0:
        return data
    idx = pd.DatetimeIndex(data.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return data[idx.normalize() <= cutoff]


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
# SECTION 2 — FEATURES AND MODEL (pure: no fetching, no files)
# ══════════════════════════════════════════════════════════════

def build_features(daily_data):
    """Returns and the 3-transform feature frame (unchanged from v1.6)."""
    returns = daily_data.pct_change().dropna()
    if returns.empty:
        raise SystemExit("❌ returns empty after pct_change — insufficient data rows")
    ema_returns = returns.ewm(span=3).mean()
    zscore_returns = (returns - returns.rolling(60).mean()) / returns.rolling(60).std()
    zscore_returns = zscore_returns.clip(lower=-3, upper=3)
    features = pd.concat([returns, ema_returns, zscore_returns],
                         axis=1, keys=["raw", "ema", "z"]).dropna()
    return returns, features


def default_model():
    return CalibratedClassifierCV(
        GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42), cv=3)


def predict_by_session(features, spy_returns, make_model=default_model):
    """Fit on the first 80% of labelled sessions, predict the remaining 20% (BACKTEST) and the
    newest, still-unlabelled session (LIVE). Every prediction is indexed by the session whose
    features produced it, i.e. the close it was computed from."""
    fwd = spy_returns.shift(-1)
    labels = (fwd > 0).astype(float).where(fwd.notna()).reindex(features.index)

    X = features.values
    y = labels.values
    mask = ~np.isnan(y)
    X_clean, y_clean = X[mask], y[mask].astype(int)
    if len(X_clean) < 50:
        raise SystemExit(f"❌ Only {len(X_clean)} labelled rows — insufficient to train")
    if mask.all():
        raise SystemExit("❌ No unlabelled newest session — nothing to predict live")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_clean)
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y_clean, test_size=0.2, shuffle=False)

    model = make_model()
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

    # FIX v1.8: date by the labelled sessions actually used, not the tail of the full index.
    test_sessions = features.index[mask][-len(probs):]
    live_session = features.index[~mask][-1]
    live_row = X[~mask][-1:]
    live_probability = float(model.predict_proba(scaler.transform(live_row))[:, 1][0])

    return {
        "backtest": pd.DataFrame({"Regime_Probability": probs}, index=test_sessions),
        "live_session": live_session,
        "live_probability": live_probability,
        "acc_at_060": acc_at_060,
        "best_t": best_t,
        "best_acc": best_acc,
    }


def confidence_level(prob):
    if prob > 0.7 or prob < 0.3:
        return "HIGH"
    if prob > 0.6 or prob < 0.4:
        return "MODERATE"
    return "LOW"


def regime_rows(dates, probs, *, best_t, best_acc, hyg, vix, vix_source, vix_flag, kind,
                generated_at_utc):
    """Output rows in the v1.6 schema, then the v1.8 provenance columns appended."""
    probs = np.asarray(probs, dtype=float)
    return pd.DataFrame({
        "Date":               pd.DatetimeIndex(dates).strftime("%Y-%m-%d"),
        "Regime_Probability": probs,
        "Regime":             ["Risk-On" if p > best_t else "Risk-Off" for p in probs],
        "Model_Accuracy":     best_acc,
        "Best_Threshold":     best_t,
        "Confidence_Level":   [confidence_level(p) for p in probs],
        "HYG_Return_Proxy":   np.asarray(hyg, dtype=float),
        "VIX_Level":          np.asarray(vix, dtype=float),
        "VIX_Source":         vix_source,
        "VIX_Data_Flag":      vix_flag,
        LOG_KIND_COLUMN:      kind,
        "Generated_At_UTC":   generated_at_utc,
        "Engine_Version":     ENGINE_VERSION,
    })


def append_live_row(log_path, live_row, archive_dir):
    """Add one session's LIVE call to the append-only log. Older rows are never rewritten; a
    rerun for the same session replaces only that session's row. A pre-v1.8 file (whole
    history re-predicted each run, no Prediction_Kind column) is moved to archive_dir first."""
    log_path, archive_dir = pathlib.Path(log_path), pathlib.Path(archive_dir)
    existing = pd.DataFrame()
    if log_path.exists():
        existing = pd.read_csv(log_path, dtype={"Date": str})
        if LOG_KIND_COLUMN not in existing.columns:
            archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            target = archive_dir / f"{log_path.stem}_pre_v1_8_{stamp}.csv"
            log_path.replace(target)
            print(f"📦 Archived pre-v1.8 re-predicted history → {target}")
            existing = pd.DataFrame()
    sessions = set(live_row["Date"])
    kept = existing[~existing["Date"].isin(sessions)] if not existing.empty else existing
    combined = pd.concat([kept, live_row], ignore_index=True) if not kept.empty else live_row.copy()
    combined = combined.sort_values("Date", kind="stable").reset_index(drop=True)
    combined.to_csv(log_path, index=False)
    return combined


# ══════════════════════════════════════════════════════════════
# SECTION 3 — MAIN
# ══════════════════════════════════════════════════════════════

def _load_keys():
    global POLYGON_API_KEY, MARKETDATA_API_KEY
    if IN_COLAB:
        from google.colab import userdata
        try:
            POLYGON_API_KEY = userdata.get("POLYGON_API_KEY")
            print("✅ POLYGON_API_KEY loaded from Colab Secrets")
        except Exception as e:
            print(f"❌ POLYGON_API_KEY unavailable: {type(e).__name__}")
        try:
            MARKETDATA_API_KEY = (userdata.get("MARKETDATA_API_KEY") or "").strip() or None
            if MARKETDATA_API_KEY:
                print(f"✅ MARKETDATA_API_KEY loaded from Colab Secrets ({len(MARKETDATA_API_KEY)} chars)")
            else:
                print("⚠️  MARKETDATA_API_KEY is empty — check Secrets → Notebook access toggle")
        except Exception as e:
            print(f"⚠️  MARKETDATA_API_KEY unavailable: {type(e).__name__}")
    else:
        try:
            from dotenv import load_dotenv
            if (REPO_ROOT / ".env").exists():
                load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
        except ImportError:
            pass
        POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
        MARKETDATA_API_KEY = os.environ.get("MARKETDATA_API_KEY")
        print("ℹ️  Not in Colab — keys read from environment variables / repo .env")
    if not POLYGON_API_KEY:
        raise SystemExit("❌ POLYGON_API_KEY is required for ETF price data — cannot proceed")


def main(argv=None):
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if IN_COLAB:
        get_ipython().system('pip install pandas numpy scikit-learn matplotlib requests yfinance --quiet')  # noqa: F821

    parser = argparse.ArgumentParser(description="AVSHUNTER daily regime model")
    parser.add_argument("--output-dir", default=os.environ.get("AVSH_REGIME_OUTPUT_DIR"),
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

    _load_keys()
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=730)).strftime("%Y-%m-%d")

    # ── data acquisition (unchanged from v1.6; v1.8 cuts at the last completed session) ──
    cutoff = session_cutoff()
    print(f"\nFetching {start_date} to {end_date} (730 days)..."
          + (f"  session cut-off {cutoff.date()} ({os.environ.get('AVSH_RUN_SESSION', 'manual')})" if cutoff is not None else "")
          + "\n")
    etf_data = {}
    for name, ticker in ETF_TICKERS.items():
        s = cut_to_session(fetch_polygon_daily(ticker, start_date, end_date), cutoff)
        if s is not None and not s.empty:
            etf_data[name] = s
            print(f"  ✅ {name} ({ticker})  — {len(s)} bars")
        else:
            print(f"  ⚠️  {name} ({ticker}) failed — excluded from feature set")
    if "SPY" not in etf_data:
        raise SystemExit("❌ SPY unavailable — SPY is the prediction target, cannot proceed")

    daily_data = pd.DataFrame(etf_data).ffill().dropna()
    print(f"\n📊 ETF frame: {daily_data.shape[0]} rows × {daily_data.shape[1]} cols")
    if daily_data.empty:
        raise SystemExit("❌ ETF frame is empty after alignment — check fetch logs above")

    vix_series, vix_source, vix_flag = fetch_vix_with_fallback(start_date, end_date)
    vix_series = cut_to_session(vix_series, cutoff)
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

    returns, features = build_features(daily_data)
    if "HYG" in returns.columns:
        print(f"\n💳 HYG latest return: {returns['HYG'].iloc[-1] * 100:.2f}%  (credit proxy ACTIVE)")
    else:
        print("\n⚠️  HYG MISSING — credit risk carried neutral in regime model")

    print("\n=== DATA QUALITY ===")
    print(f"Rows     : {len(features)}")
    print(f"Features : {features.shape[1]}  ({daily_data.shape[1]} tickers × 3 transforms)")
    print(f"Range    : {features.index[0].date()} → {features.index[-1].date()}")
    print(f"Missing  : {features.isna().sum().sum()}")
    print(f"Extreme (>5σ): {(features.abs() > 5).any(axis=1).sum()}")
    print(f"VIX in set: {'YES — ' + vix_source if 'VIX' in daily_data.columns else 'NO'}")
    if len(features) < 100:
        print("⚠️  WARNING: fewer than 100 rows — model may be unreliable")

    out = predict_by_session(features, returns["SPY"])
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def per_date(series, dates):
        if series is None:
            return np.full(len(dates), np.nan)
        return series.reindex(dates).values

    hyg = returns["HYG"] if "HYG" in returns.columns else None
    common = dict(best_t=out["best_t"], best_acc=out["best_acc"], vix_source=vix_source,
                  vix_flag=vix_flag, generated_at_utc=generated)

    backtest_dates = out["backtest"].index
    backtest = regime_rows(backtest_dates, out["backtest"]["Regime_Probability"].values,
                           hyg=per_date(hyg, backtest_dates), vix=per_date(vix_aligned, backtest_dates),
                           kind="BACKTEST", **common)
    live_dates = pd.DatetimeIndex([out["live_session"]])
    live = regime_rows(live_dates, [out["live_probability"]], hyg=per_date(hyg, live_dates),
                       vix=per_date(vix_aligned, live_dates), kind="LIVE", **common)

    log_path = output_dir / LOG_NAME
    try:
        backtest.to_csv(output_dir / BACKTEST_NAME, index=False)
        log = append_live_row(log_path, live, output_dir / "archive")
        print(f"\n✅ Saved LIVE call for {live['Date'].iloc[0]} → {log_path}  ({len(log)} logged sessions)")
        print(f"✅ Saved BACKTEST ({len(backtest)} sessions) → {output_dir / BACKTEST_NAME}")
    except OSError as e:
        print(f"\n❌ CSV save failed: {e}")
        if not IN_COLAB:
            raise SystemExit(1)

    row = live.iloc[0]
    print(f"   LIVE: session {row['Date']} close → next open: P(SPY up) = {row['Regime_Probability']:.3f} "
          f"→ {row['Regime']} [{row['Confidence_Level']}]")
    print(f"   HYG credit proxy : {'ACTIVE' if hyg is not None else 'MISSING — neutral'}")
    if vix_aligned is not None:
        print(f"   VIX fear signal  : ACTIVE — {vix_aligned.dropna().iloc[-1]:.2f}  [{vix_source}]")
    else:
        print(f"   VIX fear signal  : MISSING  [{vix_flag}]")

    if IN_COLAB:
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(12, 5))
            plt.plot(pd.to_datetime(backtest["Date"].iloc[-30:]), backtest["Regime_Probability"].iloc[-30:],
                     marker="o", linewidth=2)
            plt.axhline(out["best_t"], color="green", linestyle="--", alpha=0.5,
                        label=f"Threshold ({out['best_t']:.2f})")
            plt.axhline(1 - out["best_t"], color="red", linestyle="--", alpha=0.5)
            plt.title(f"Daily Regime backtest (last 30) — threshold {out['best_t']:.2f}, "
                      f"accuracy {out['best_acc']:.2%}")
            plt.ylabel("Probability (Risk-On)")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.show()
        except Exception as e:
            print(f"⚠️  Charting failed (data outputs are unaffected): {e}")

    print(f"\n✅ v1.8 COMPLETE — outputs → {output_dir}")
    print(f"   • VIX source      : {vix_source}  [{vix_flag}]")
    print(f"   • Feature tickers : {list(daily_data.columns)}")
    print(f"   • OOS accuracy    : {out['acc_at_060']:.2%} at fixed 0.60 threshold")
    return 0


if __name__ == "__main__":
    _code = main()
    if not IN_COLAB:          # in a notebook cell SystemExit would print a traceback
        sys.exit(_code)
