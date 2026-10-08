# === AVSHUNTER Macro Module v2.6 ===
#
# ============================================================================
# CHANGES over v2.5
# ============================================================================
#
# P0-1  VIX VINTAGE GUARD + CBOE PRIMARY.
#       v2.5 read ^VIX9D / ^VIX3M from yfinance with no date check. Those two
#       tickers FROZE on 2026-07-17 while ^VIX kept updating — confirmed in the
#       collector's 11:07 run, which computed a "front-end hump" from a 7 August
#       spot against 17 July wings. Here the consequence is worse than a wrong
#       label: vix_shape feeds compute_sizing directly, and
#
#           if vix_shape == "BACKWARDATION" or r >= 4:  mult = 0.50
#
#       so a stale-mix inversion halves the book on data that does not exist.
#       v2.6 sources the complex from Cboe (the calculating exchange, free, no
#       entitlement), falls back to yfinance, and REJECTS the term structure
#       when leg observation dates skew more than VIX_MAX_VINTAGE_SKEW_DAYS.
#       A rejected structure resolves to UNKNOWN -> VOLGAP_HAIRCUT, never to
#       BACKWARDATION. Unmeasurable is not the same as dangerous.
#
# P0-2  GEX IS NO LONGER A MANUAL INPUT.
#       v2.5 listed GEX under MANUAL INPUTS STILL REQUIRED as the "primary
#       splitting-factor gap". avshunter_gex_proxy.csv now supplies Regime,
#       Net_GEX_Bn, Gamma_Flip, Data_Status and As_Of. Consumed in the conflict
#       matrix. Data_Status != OK propagates as null with a warning — never as
#       an imputed neutral.
#
# P1-1  classify_vix_shape had no HUMP state. Both ordering tests required a
#       monotonic curve, so a humped structure (9D above spot, 3M above 9D —
#       exactly what event premium looks like) matched neither and fell through
#       to slope > 0.5 -> CONTANGO. Third state added.
#
# P1-2  Slope was VIX3M - VIX9D, which never touches spot. Now spot-relative,
#       matching the Fear Engine (which had it right while this module did not,
#       in the same batch).
#
# P1-3  No FRED VIXCLS in FRED_SERIES, so no reconciliation. The Fear Engine
#       audits yfinance against FRED and degrades on divergence; this module
#       took it on faith and fed it into sizing. VIXCLS added, compared on the
#       last SHARED date (a cross-date gap is market movement, not a fault).
#
# P1-4  5-DAY ESCALATION. Bands tested only the 30-day change, so VIX9D's
#       +51.12% five-day move scored GREY because its 30-day was +8.15%. A
#       5-day move at or beyond the band's own RED threshold now escalates the
#       flag one level and is recorded in escalated_5d.
#
# NEW   EVENT_HAIRCUT — wired, calibrated OFF. compute_sizing already owns
#       BREADTH / VVIX / VOLGAP haircuts, so the event haircut belongs here and
#       not in the collector: this is where sizing decisions live and where a
#       calendar can be read once and used by every rule. Calendar comes from
#       the bond module (B-01 TreasuryDirect) or a local CSV — one calendar,
#       two consumers. EVENT_HAIRCUT_ACTIVE stays False until backtested,
#       following the REGIME_CONTEST_AFFECTS_SIZING precedent.
#
# P2    VVIX tiers aligned to the Fear Engine (>110 ELEVATED, >95 HIGH).
#       yfinance auto_adjust/period aligned. as_of on every flag row. Errors
#       file written unconditionally so "no errors" and "did not run" differ.
#
# ============================================================================
# CARRIED FROM v2.5 — deliberately unchanged
# ============================================================================
#   Direction-aware sizing (RISK_WHEN); asset-class bands; breadth log-spread
#   with z-score; EOD vs intraday breadth divergence; regime-contest diagnostic
#   advisory-only; DXY UUP fallback with substitution recorded; sizing counts
#   the ETF universe only. This module has the best risk discipline in the
#   stack and none of it was touched.
#
# CALIBRATION STUBS — replace with values derived from the actuarial DB:
#   BREADTH_HAIRCUT (0.75), BREADTH_Z_TRIGGER (1.0), VVIX_HAIRCUT (0.85),
#   VOLGAP_HAIRCUT (0.90), REGIME_CONTEST_MIN (2.0), EVENT_HAIRCUT (0.85),
#   GEX_NEGATIVE_HAIRCUT (0.85)
#
# STILL OUTSTANDING (different file): Fung-Hsieh v1.2 uses
#   train_test_split(random_state=42, stratify=y) with no shuffle=False on a
#   time series -> future weeks leak into training. Its accuracy is inflated,
#   and GO/NO-GO gates on accuracy >= 0.70.

#
# ============================================================================
# v2.7 (7 Oct 2026) — Colab notebook "AVSHUNTER_Polygon_Macro_Loader" ported
# ============================================================================
#   Analytics, thresholds, sizing and every output schema are unchanged.
#   L-01  Importing the file does nothing: keys, banner and folder creation
#         moved to setup(), called only from __main__.
#   L-02  Locally the default output is dropbox\market_data (Colab keeps
#         /content); --output-dir / AVSH_MACRO_OUTPUT_DIR for testing. Inputs
#         (avshunter_gex_proxy.csv, event calendars) are read from
#         dropbox\market_data even when the output is redirected. In Colab the
#         GEX handoff was always MISSING (the file is never in /content).
#   L-03  FRED via its REST endpoint (fredapi is not in the venv); same series,
#         same observation_start.
#   L-04  requests error text carries the URL with the Polygon apiKey; it reached
#         the errors list -> macro_module_contract.json and macro_v26_errors_*.txt.
#         Key values are redacted at the source and again at write time.
#   L-05  Charts only when matplotlib is installed (not in the venv; no code
#         reads the PNGs). JSON / errors written as UTF-8; UTF-8 console.
#   v2.8 (7 Oct 2026, ACK approved)
#   F-01  GEX age: As_Of is an ISO UTC timestamp; v2.7 subtracted it from a naive date,
#         raised, and _days_between returned 999, so GEX was STALE on every run. Both
#         sides are now compared as UTC calendar dates.
#   F-02  Event calendar: bond_macro_intelligence writes auction_calendar.csv to
#         dropbox\macro; v2.7 looked only in market_data, so the event window was never
#         active. dropbox\macro\auction_calendar.csv is now read after the market_data
#         candidates (first existing file wins, as before).
#   Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_macro_module_v2_8.py
#   Session cut-off (8 Oct 2026): with AVSH_SESSION_CUTOFF set (Run-MacroInputs.ps1), Polygon,
#         vol-complex and DXY series stop at the last completed US session; a PreOpen run
#         (AVSH_RUN_SESSION) skips the same-day RSP vs SPY breadth (state SKIPPED).

# ════════════════════════════════════════════════════════════
# ── CONFIG ──────────────────────────────────────────────────
import pathlib, datetime, io, os, re, sys, time

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

REPO_ROOT = pathlib.Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
LOCAL_MARKET_DATA = REPO_ROOT / "dropbox" / "market_data"
OUTPUT_DIR = LOCAL_MARKET_DATA if (not IN_COLAB and LOCAL_MARKET_DATA.exists()) else pathlib.Path("/content")
INPUT_DIR = OUTPUT_DIR          # setup() keeps inputs on dropbox\market_data when output is redirected

BREADTH_LOOKBACK  = 20     # trading days for the RSP/SPY spread
BREADTH_ZWINDOW   = 252    # trading days for the z-score baseline
BREADTH_MIN_ROWS  = 60     # minimum z-window before breadth is admitted
BREADTH_Z_TRIGGER = 1.0    # |z| at which state leaves NEUTRAL   [STUB]
BREADTH_HAIRCUT   = 0.75   # sizing multiplier when narrow/missing [STUB]
VVIX_HAIRCUT      = 0.85   # [STUB]
VOLGAP_HAIRCUT    = 0.90   # vol complex unavailable              [STUB]
SIZE_FLOOR        = 0.25

INTRADAY_BREADTH  = True   # Polygon snapshot call for same-day RSP vs SPY
REGIME_CONTEST_LOOKBACK = 5
REGIME_CONTEST_MIN      = 2.0    # min |5d %| to call a contest    [STUB]
REGIME_CONTEST_AFFECTS_SIZING = False   # keep False until backtested

# ── v2.6: VIX sourcing and vintage integrity ────────────────────────────────
VIX_MAX_VINTAGE_SKEW_DAYS = 3     # reject the term structure beyond this
VIX_RECONCILE_TOLERANCE_PCT = 1.0 # yfinance/Cboe vs FRED VIXCLS, shared date
CBOE_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
CBOE_CANDIDATES = {
    "VIX":   [f"{CBOE_BASE}/VIX_History.csv"],
    "VIX9D": [f"{CBOE_BASE}/VIX9D_History.csv"],
    "VIX3M": [f"{CBOE_BASE}/VIX3M_History.csv", f"{CBOE_BASE}/VXV_History.csv"],
    "VVIX":  [f"{CBOE_BASE}/VVIX_History.csv"],
}
YF_VOL_TICKERS = {"VIX": "^VIX", "VIX9D": "^VIX9D", "VIX3M": "^VIX3M", "VVIX": "^VVIX"}

# ── v2.6: GEX handoff ───────────────────────────────────────────────────────
GEX_FILE = INPUT_DIR / "avshunter_gex_proxy.csv"
GEX_PRIMARY_TICKER = "SPY"
GEX_MAX_AGE_DAYS = 3               # positioning decays; stale GEX is advisory only
GEX_NEGATIVE_HAIRCUT = 0.85        # [STUB]
GEX_AFFECTS_SIZING = False         # keep False until backtested

# ── v2.6: event calendar (shared with bond_macro_intelligence B-01) ─────────
def event_calendar_files(input_dir):
    """Calendars in priority order. v2.8: bond_macro_intelligence (B-01) writes
    auction_calendar.csv to dropbox\\macro, the sibling of market_data, so v2.7 never found it."""
    return [
        input_dir / "macro_event_calendar.csv",            # columns: date,event,importance
        input_dir / "auction_calendar.csv",
        input_dir.parent / "macro" / "auction_calendar.csv",   # where the bond module writes it
    ]


EVENT_CALENDAR_FILES = event_calendar_files(INPUT_DIR)
EVENT_WINDOW_DAYS   = 3            # look-ahead for a scheduled binary
EVENT_HAIRCUT       = 0.85         # [STUB]
EVENT_HAIRCUT_ACTIVE = False       # keep False until backtested

EXTREME_5D_ESCALATION = True       # P1-4

RUN_ID = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
# ════════════════════════════════════════════════════════════

import json
import pandas as pd
import numpy as np
import requests

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:          # not in the AVSHUNTER venv; charts are skipped, data unaffected
    plt = None

POLYGON_API_KEY = FRED_API_KEY = None     # set by setup()

_KEY_IN_TEXT = re.compile(r"((?:apiKey|api_key|token)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text):
    """Remove API key values from any text (request error messages carry the full URL)."""
    return _KEY_IN_TEXT.sub(r"\1REDACTED", str(text))


def setup(argv=None):
    """Everything v2.6 did at import time: pip (Colab only), output folder, keys, banner."""
    global OUTPUT_DIR, POLYGON_API_KEY, FRED_API_KEY
    import argparse
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if IN_COLAB:
        get_ipython().system('pip install fredapi pandas numpy matplotlib requests yfinance --quiet')  # noqa: F821
    parser = argparse.ArgumentParser(description="AVSHUNTER macro module")
    parser.add_argument("--output-dir", default=os.environ.get("AVSH_MACRO_OUTPUT_DIR"),
                        help="write here instead of dropbox\\market_data (for testing)")
    args, _ = parser.parse_known_args(argv)        # Colab passes its own kernel arguments
    if args.output_dir:
        OUTPUT_DIR = pathlib.Path(args.output_dir)   # inputs stay on INPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"OUTPUT_DIR: {OUTPUT_DIR}   (inputs: {INPUT_DIR})")

    if IN_COLAB:
        from google.colab import userdata
        for _n in ("POLYGON_API_KEY", "POLYGON"):
            try:
                _v = userdata.get(_n)
                if _v and _v.strip():
                    POLYGON_API_KEY = _v.strip(); break
            except Exception:
                continue
        for _n in ("FRED_API_KEY", "FRED"):
            try:
                _v = userdata.get(_n)
                if _v and _v.strip():
                    FRED_API_KEY = _v.strip(); break
            except Exception:
                continue
    else:
        print("Not in Colab — reading keys from environment / repo .env")
        try:
            from dotenv import load_dotenv
            if (REPO_ROOT / ".env").exists():
                load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
        except ImportError:
            pass

    POLYGON_API_KEY = POLYGON_API_KEY or os.environ.get("POLYGON_API_KEY")
    FRED_API_KEY    = FRED_API_KEY    or os.environ.get("FRED_API_KEY")

    if not POLYGON_API_KEY:
        raise SystemExit("POLYGON_API_KEY is required — cannot proceed")
    if not FRED_API_KEY:
        print("  WARNING: FRED_API_KEY missing — FRED block and VIX reconciliation skipped")
    print("API keys resolved")

TODAY         = datetime.date.today()
START_DATE    = (TODAY - datetime.timedelta(days=365)).isoformat()
BREADTH_START = (TODAY - datetime.timedelta(days=550)).isoformat()
END_DATE      = TODAY.isoformat()

FRED_SERIES = {
    "DGS10": "10Y Yield (daily)", "DGS2": "2Y Yield (daily)", "DGS3MO": "3M Yield (daily)",
    "FEDFUNDS": "Fed Funds Rate", "SOFR": "SOFR", "CPIAUCSL": "CPI",
    "M2SL": "M2 Money Supply", "UNRATE": "Unemployment Rate", "WALCL": "Fed Balance Sheet",
    "VIXCLS": "VIX (FRED daily) — reconciliation auditor",   # P1-3
}

POLYGON_TICKERS = {
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "TLT": "TLT", "HYG": "HYG",
    "GLD": "GLD", "USO": "USO",
    "XLF": "XLF", "XLE": "XLE", "XLK": "XLK", "XLV": "XLV", "XLI": "XLI",
    "XLY": "XLY", "XLP": "XLP", "XLU": "XLU", "XLB": "XLB", "XLRE": "XLRE",
    "XLC": "XLC",
}
# RSP is deliberately NOT here. Adding it would push a near-duplicate of SPY
# into threshold_results and double-count equity beta in the sizing verdict.
# It is fetched separately, on a longer window, purely to build the spread.

VOL_SERIES = {"VIX", "VIX9D", "VIX3M", "VVIX"}
FX_SERIES  = {"DXY"}
THRESHOLD_BANDS = {
    "EQUITY": {"green": 0.02, "yellow": 0.05, "red": 0.10},
    "VOL":    {"green": 0.10, "yellow": 0.25, "red": 0.50},
    "FX":     {"green": 0.01, "yellow": 0.025, "red": 0.05},
}

# The direction in which each series constitutes RISK to the book. Default is
# DOWN. A large UP move in a series whose risk direction is DOWN is a rally.
RISK_WHEN = {
    "USO": "UP",    # oil rising = cost shock
    "DXY": "UP",    # dollar rising = funding tightness
}
RISK_NEUTRAL = {"GLD"}   # safe haven, ambiguous in both directions

errors = []


def session_cutoff():
    """Last completed US session from AVSH_SESSION_CUTOFF (set by Run-MacroInputs.ps1), or None
    when unset (Colab / manual runs keep the previous behaviour)."""
    value = os.environ.get("AVSH_SESSION_CUTOFF", "").strip()
    return pd.Timestamp(value).normalize() if value else None


def cut_to_session(data, cutoff):
    """Drop rows dated after the last completed US session, so a pre-open run never treats a
    partial "today" bar (pre-market trades, overnight VIX / dollar) as a finished session."""
    if cutoff is None or data is None or len(data) == 0:
        return data
    idx = pd.DatetimeIndex(data.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return data[idx.normalize() <= cutoff]


# ══════════════════════════════════════════════════════════════
# SECTION 1 — FETCH HELPERS
# ══════════════════════════════════════════════════════════════

def _normalise(series):
    idx = pd.to_datetime(series.index)
    try:
        if idx.tz is not None:
            idx = idx.tz_convert(None)
    except (AttributeError, TypeError):
        pass
    series.index = idx.normalize()
    return series[~series.index.duplicated(keep="last")].sort_index()


def _days_between(a, b):
    """Calendar days between two dates or timestamps. v2.8: a tz-aware ISO timestamp (the GEX
    proxy's As_Of, e.g. 2026-10-05T20:00:00Z) is converted to its UTC date first — v2.7
    subtracted it from a naive date, raised, and returned 999, so GEX was always STALE."""
    try:
        def day(x):
            ts = pd.Timestamp(x)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            return ts.normalize()
        return abs((day(a) - day(b)).days)
    except Exception:
        return 999


def fetch_polygon(ticker, start, end, api_key):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    try:
        r = requests.get(url, params=params, timeout=30)
    except requests.exceptions.Timeout:
        errors.append(f"Polygon {ticker}: timeout"); return pd.Series(dtype="float64")
    except requests.exceptions.RequestException as e:
        errors.append(f"Polygon {ticker}: network — {type(e).__name__}: {redact(e)}"); return pd.Series(dtype="float64")

    if r.status_code == 429:
        errors.append(f"Polygon {ticker}: 429 rate limited"); return pd.Series(dtype="float64")
    if r.status_code != 200:
        errors.append(f"Polygon {ticker}: HTTP {r.status_code}"); return pd.Series(dtype="float64")
    try:
        results = r.json().get("results", [])
    except ValueError as e:
        errors.append(f"Polygon {ticker}: non-JSON — {e}"); return pd.Series(dtype="float64")
    if not results:
        errors.append(f"Polygon {ticker}: empty results"); return pd.Series(dtype="float64")

    df = pd.DataFrame(results)
    if "t" not in df.columns or "c" not in df.columns:
        errors.append(f"Polygon {ticker}: unexpected schema {list(df.columns)}")
        return pd.Series(dtype="float64")
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    return cut_to_session(_normalise(df.set_index("t")["c"].astype("float64")), session_cutoff())


def fetch_polygon_snapshot(ticker, api_key):
    """Same-day snapshot. Returns dict or None. Used for intraday breadth."""
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
    try:
        r = requests.get(url, params={"apiKey": api_key}, timeout=20)
    except requests.exceptions.RequestException as e:
        errors.append(f"Snapshot {ticker}: {type(e).__name__}: {redact(e)}"); return None
    if r.status_code != 200:
        errors.append(f"Snapshot {ticker}: HTTP {r.status_code}"); return None
    try:
        payload = r.json()
    except ValueError as e:
        errors.append(f"Snapshot {ticker}: non-JSON — {e}"); return None

    t = payload.get("ticker") or {}
    if not t:
        errors.append(f"Snapshot {ticker}: no ticker block"); return None
    chg = t.get("todaysChangePerc")
    if chg is None:
        day, prev = t.get("day") or {}, t.get("prevDay") or {}
        if day.get("c") and prev.get("c"):
            chg = (day["c"] / prev["c"] - 1) * 100
    if chg is None:
        errors.append(f"Snapshot {ticker}: no change data"); return None
    return {"ticker": ticker, "chg_pct": float(chg),
            "last": (t.get("day") or {}).get("c"),
            "prev_close": (t.get("prevDay") or {}).get("c")}


FRED_TIMEOUT_S, FRED_ATTEMPTS = 60, 3


def _get_retried(url, params):
    """GET retried on timeout / connection error / 429 / 5xx; a 4xx is returned at once.
    fredapi waited without a time limit; on 8 Oct 2026 FRED answered in 8-11 s per request and
    a single 30 s attempt lost series, so slowness is retried, not turned into MISSING."""
    last = None
    for attempt in range(1, FRED_ATTEMPTS + 1):
        try:
            r = requests.get(url, params=params, timeout=FRED_TIMEOUT_S)
            if r.status_code != 429 and r.status_code < 500:
                return r
            last = requests.exceptions.HTTPError(f"HTTP {r.status_code}", response=r)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = e
        if attempt < FRED_ATTEMPTS:
            time.sleep(2 * attempt)
    raise last


def fetch_fred_all(series_map, start, fred_key):
    if not fred_key:
        errors.append("FRED: no API key — block skipped")
        return {}
    out = {}
    for code, label in series_map.items():
        try:
            # v2.7: FRED series/observations directly (the endpoint fredapi.get_series calls).
            r = _get_retried("https://api.stlouisfed.org/fred/series/observations",
                             {"series_id": code, "api_key": fred_key, "file_type": "json",
                              "observation_start": start})
            r.raise_for_status()
            obs = r.json().get("observations", [])
            s = pd.Series(pd.to_numeric([o["value"] for o in obs], errors="coerce"),
                          index=pd.to_datetime([o["date"] for o in obs]), dtype="float64").dropna()
            s.index = pd.to_datetime(s.index)
            # Drop future-dated observations (FRED forward-fills some series).
            s = s[s.index <= pd.Timestamp(TODAY)]
            out[code] = s
            print(f"  OK   FRED {code:10s} {label}")
        except Exception as e:
            errors.append(f"FRED {code}: {type(e).__name__}: {redact(e)}")
            print(f"  WARN FRED {code}: {type(e).__name__}: {redact(e)}")
    return out


# ── P0-1: Cboe primary for the vol complex ──────────────────────────────────

def _parse_cboe(text, key):
    """
    Cboe files vary: VIX_History carries OPEN/HIGH/LOW/CLOSE, the single-value
    files sometimes name the column after the index. Locate a date column and a
    close-like column rather than assuming a fixed schema.
    """
    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        return None
    cols = {c.strip().upper(): c for c in df.columns}
    date_col = next((cols[c] for c in cols if "DATE" in c), None)
    if date_col is None:
        return None
    close_col = None
    for want in ("CLOSE", f"{key} CLOSE", key, "VALUE", "INDEX"):
        if want in cols:
            close_col = cols[want]; break
    if close_col is None:
        numeric = [c for c in df.columns
                   if c != date_col and pd.to_numeric(df[c], errors="coerce").notna().any()]
        if not numeric:
            return None
        close_col = numeric[-1]
    out = df[[date_col, close_col]].copy()
    out.columns = ["date", "close"]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna().sort_values("date")
    out = out[out["date"] <= pd.Timestamp(TODAY)]
    if out.empty:
        return None
    return _normalise(pd.Series(out["close"].values, index=out["date"], dtype="float64")).tail(600)


def fetch_vol_complex():
    """
    Cboe primary, yfinance fallback. Returns (data, meta).

    yfinance ^VIX9D and ^VIX3M froze on 2026-07-17 while ^VIX kept updating.
    Because vix_shape drives compute_sizing, a stale-mix inversion here would
    cut the book to 0.50x on values three weeks old. Cboe is the calculating
    exchange, free and unentitled, so it is the correct primary.
    """
    data, meta = {}, {}
    for key in ("VIX", "VIX9D", "VIX3M", "VVIX"):
        got = None
        for url in CBOE_CANDIDATES.get(key, []):
            try:
                r = requests.get(url, timeout=25, headers={"User-Agent": "AVSHUNTER/2.6"})
                if r.status_code == 200 and r.text.strip():
                    got = _parse_cboe(r.text, key)
                    if got is not None and len(got) >= 2:
                        meta[key] = {"source": "CBOE", "file": url.rsplit("/", 1)[-1]}
                        break
                    got = None
            except Exception as e:
                errors.append(f"Cboe {key}: {type(e).__name__} — {e}")
        if got is None:
            try:
                import yfinance as yf
                hist = yf.Ticker(YF_VOL_TICKERS[key]).history(period="2y", auto_adjust=False)
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    got = _normalise(hist["Close"].astype("float64").dropna())
                    meta[key] = {"source": "YFINANCE", "file": YF_VOL_TICKERS[key]}
                    errors.append(f"Cboe {key} unavailable — yfinance fallback")
            except Exception as e:
                errors.append(f"yfinance {key}: {type(e).__name__} — {e}")
        got = cut_to_session(got, session_cutoff())
        if got is None or got.empty:
            errors.append(f"{key}: no source available")
            print(f"  FAIL {key:6s} no source")
            continue
        data[key] = got
        obs = got.index[-1].date().isoformat()
        age = _days_between(obs, END_DATE)
        meta[key].update({"obs_date": obs, "age_days": age, "latest": float(got.iloc[-1])})
        print(f"  OK   {key:6s} {got.iloc[-1]:8.2f}  {obs}  age {age}d  "
              f"[{meta[key]['source']}]")
    return data, meta


# ── P0-2: GEX handoff ───────────────────────────────────────────────────────

def load_gex(path=GEX_FILE, ticker=GEX_PRIMARY_TICKER):
    """
    Read the canonical GEX summary. v2.5 listed GEX as a manual input; it is now
    produced by avshunter_gex_proxy v3.4.

    Data_Status != OK propagates as MISSING with a warning. It is never imputed
    to a neutral score — an absent input must reduce conviction, not contribute
    a median value.
    """
    out = {"state": "MISSING", "regime": None, "net_gex_bn": None, "gamma_flip": None,
           "spot": None, "as_of": None, "age_days": None, "data_mode": None,
           "coverage_pct": None, "flip_vs_spot_pct": None, "note": ""}
    try:
        if not path.exists():
            out["note"] = f"{path.name} not found — run avshunter_gex_proxy first"
            errors.append(f"GEX: {out['note']}")
            return out
        df = pd.read_csv(path)
        row = df[df["Ticker"].astype(str).str.upper() == ticker.upper()]
        if row.empty:
            out["note"] = f"no {ticker} row in {path.name}"
            errors.append(f"GEX: {out['note']}"); return out
        r = row.iloc[0]
        if str(r.get("Data_Status", "")).upper() != "OK":
            out["note"] = f"Data_Status={r.get('Data_Status')} — {r.get('Note', '')}"
            errors.append(f"GEX: {ticker} {out['note']}"); return out

        as_of = r.get("As_Of")
        age = _days_between(as_of, END_DATE) if pd.notna(as_of) else None
        out.update({
            "state": "OK", "regime": str(r.get("Regime")),
            "net_gex_bn": float(r["Net_GEX_Bn"]) if pd.notna(r.get("Net_GEX_Bn")) else None,
            "gamma_flip": float(r["Gamma_Flip"]) if pd.notna(r.get("Gamma_Flip")) else None,
            "spot": float(r["Spot"]) if pd.notna(r.get("Spot")) else None,
            "as_of": str(as_of) if pd.notna(as_of) else None, "age_days": age,
            "data_mode": r.get("Data_Mode"), "coverage_pct": r.get("Coverage_Pct"),
        })
        if out["gamma_flip"] and out["spot"]:
            out["flip_vs_spot_pct"] = round((out["spot"] / out["gamma_flip"] - 1) * 100, 3)
        if age is not None and age > GEX_MAX_AGE_DAYS:
            out["state"] = "STALE"
            out["note"] = f"as_of {as_of} is {age}d old — gamma positioning decays"
            errors.append(f"GEX: {ticker} {out['note']}")
    except Exception as e:
        out["note"] = f"{type(e).__name__} — {e}"
        errors.append(f"GEX read failed: {out['note']}")
    return out


# ── EVENT CALENDAR (shared with bond_macro_intelligence B-01) ───────────────

def load_event_window(days=EVENT_WINDOW_DAYS, files=None):
    """
    Scheduled binaries inside the look-ahead window.

    The calendar lives OUTSIDE this module deliberately: bond_macro_intelligence
    builds it from TreasuryDirect for B-01, and this module reads the same file.
    One calendar, two consumers — a second hardcoded copy is how two components
    end up disagreeing about what week it is.
    """
    out = {"active": False, "events": [], "source": None,
           "note": "no calendar file found — event awareness INACTIVE"}
    for path in (EVENT_CALENDAR_FILES if files is None else files):
        try:
            if not path.exists():
                continue
            df = pd.read_csv(path)
            dcol = next((c for c in df.columns if "date" in c.lower()), None)
            if dcol is None:
                continue
            # v2.8: drop undated rows first — an all-blank column (the bond module's "no auctions"
            # file) stays datetime64 after .dt.date and cannot be compared with a date.
            df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
            df = df.dropna(subset=[dcol])
            lo, hi = pd.Timestamp(TODAY), pd.Timestamp(TODAY + datetime.timedelta(days=days))
            hit = df[(df[dcol] >= lo) & (df[dcol] <= hi)].copy()
            hit[dcol] = hit[dcol].dt.date
            ecol = next((c for c in df.columns if "event" in c.lower()
                         or "tenor" in c.lower()), None)
            out.update({
                "active": len(hit) > 0, "source": path.name,
                "events": [f"{r[dcol]} {r[ecol] if ecol else ''}".strip()
                           for _, r in hit.iterrows()],
                "note": "OK",
            })
            return out
        except Exception as e:
            errors.append(f"Event calendar {path.name}: {type(e).__name__} — {e}")
    errors.append("Event calendar: " + out["note"])
    return out


# ══════════════════════════════════════════════════════════════
# SECTION 2 — ANALYTICS
# ══════════════════════════════════════════════════════════════

def asset_class(name):
    if name in VOL_SERIES: return "VOL"
    if name in FX_SERIES:  return "FX"
    return "EQUITY"


def flag_thresholds(series, name=""):
    """
    Magnitude flag, signed direction, asset-class bands, 5-day change.

    P1-4: a 5-day move at or beyond the band's own RED threshold escalates the
    flag one level. v2.5 tested only the 30-day change, so VIX9D's +51.12%
    five-day move scored GREY on an +8.15% 30-day reading. Using the band's own
    red level keeps the rule self-calibrating across EQUITY/VOL/FX.
    """
    band = asset_class(name)
    blank = {"flag": "INSUFFICIENT_DATA", "direction": "UNKNOWN", "chg_30d": None,
             "chg_5d": None, "latest": None, "band": band, "regime": "UNKNOWN",
             "escalated_5d": False, "as_of": None}
    if series is None or series.empty or len(series) < 23:
        return blank
    chg = series.pct_change(22).iloc[-1]
    if pd.isna(chg):
        return blank
    chg = float(chg)

    chg5 = None
    if len(series) > REGIME_CONTEST_LOOKBACK:
        v = series.pct_change(REGIME_CONTEST_LOOKBACK).iloc[-1]
        chg5 = None if pd.isna(v) else float(v)

    b, a = THRESHOLD_BANDS[band], abs(chg)
    flag = ("RED" if a >= b["red"] else "YELLOW" if a >= b["yellow"]
            else "GREEN" if a >= b["green"] else "GREY")

    escalated = False
    if EXTREME_5D_ESCALATION and chg5 is not None and abs(chg5) >= b["red"]:
        bump = {"GREY": "GREEN", "GREEN": "YELLOW", "YELLOW": "RED", "RED": "RED"}
        if bump[flag] != flag:
            flag, escalated = bump[flag], True

    return {"flag": flag,
            "direction": "UP" if chg > 0 else "DOWN" if chg < 0 else "FLAT",
            "chg_30d": round(chg * 100, 2),
            "chg_5d": None if chg5 is None else round(chg5 * 100, 2),
            "latest": round(float(series.iloc[-1]), 4),
            "band": band,
            "regime": "PENDING",
            "escalated_5d": escalated,
            "as_of": series.index[-1].date().isoformat()}


def detect_regime_contest(v):
    """A 30-day momentum flag on a headline-switched variable keeps describing
    the old regime for weeks. If the 5-day move opposes the 30-day sign with
    real magnitude, the flag is contested rather than confirmed.
    ADVISORY — does not affect sizing unless REGIME_CONTEST_AFFECTS_SIZING."""
    c30, c5 = v.get("chg_30d"), v.get("chg_5d")
    if c30 is None or c5 is None:
        return "UNKNOWN"
    if c30 == 0 or c5 == 0:
        return "CONFIRMED"
    if (c30 > 0) != (c5 > 0) and abs(c5) >= REGIME_CONTEST_MIN:
        return "CONTESTED"
    return "CONFIRMED"


def compute_breadth(rsp, spy, lookback=BREADTH_LOOKBACK,
                    zwindow=BREADTH_ZWINDOW, min_z=BREADTH_MIN_ROWS):
    """Equal-weight vs cap-weight participation.

    spread = log(RSP_t / RSP_t-n) - log(SPY_t / SPY_t-n)
    Negative -> cap-weight beating equal-weight -> index carried by its largest
    members -> narrow rally. Log form so it is additive and symmetric.
    """
    out = {"spread_pct": None, "z": None, "zwindow": None,
           "state": "MISSING", "note": ""}
    if rsp is None or spy is None or rsp.empty or spy.empty:
        out["note"] = "RSP or SPY unavailable"; return out
    df = pd.concat([rsp.rename("RSP"), spy.rename("SPY")], axis=1).dropna()
    if len(df) < lookback + min_z:
        out["note"] = f"only {len(df)} aligned rows, need {lookback + min_z}"; return out

    spread = (np.log(df["RSP"]).diff(lookback)
              - np.log(df["SPY"]).diff(lookback)).dropna()
    if spread.empty:
        out["note"] = "spread empty"; return out

    latest = float(spread.iloc[-1])
    win = int(min(zwindow, len(spread)))
    tail = spread.tail(win)
    mu, sd = float(tail.mean()), float(tail.std())
    if not np.isfinite(sd) or sd <= 0:
        out["note"] = "zero/invalid variance in z-window"; return out

    z = (latest - mu) / sd
    out.update({
        "spread_pct": round(latest * 100, 2),
        "z": round(float(z), 2),
        "zwindow": win,
        "state": ("NARROWING"  if z <= -BREADTH_Z_TRIGGER else
                  "BROADENING" if z >=  BREADTH_Z_TRIGGER else "NEUTRAL"),
        "note": "OK" if win >= zwindow else f"z-window truncated to {win} rows",
    })
    return out


def compute_intraday_breadth(api_key):
    """Same-day RSP vs SPY. The EOD spread answers 'was yesterday broad?';
    this answers 'is today's gap broad?'."""
    out = {"spread_pct": None, "rsp_pct": None, "spy_pct": None,
           "state": "MISSING", "note": ""}
    if os.environ.get("AVSH_RUN_SESSION", "").strip().lower() == "preopen":
        # Before the open there is no US session yet; a snapshot would only reflect pre-market prints.
        out.update({"state": "SKIPPED", "note": "pre-open run: no US session yet"})
        return out
    rsp = fetch_polygon_snapshot("RSP", api_key)
    spy = fetch_polygon_snapshot("SPY", api_key)
    if not rsp or not spy:
        out["note"] = "snapshot unavailable for RSP or SPY"; return out
    spread = rsp["chg_pct"] - spy["chg_pct"]
    out.update({
        "spread_pct": round(spread, 3),
        "rsp_pct": round(rsp["chg_pct"], 3),
        "spy_pct": round(spy["chg_pct"], 3),
        "state": ("NARROW" if spread <= -0.25 else
                  "BROAD"  if spread >=  0.25 else "EVEN"),
        "note": "OK",
    })
    if abs(rsp["chg_pct"]) < 1e-9 and abs(spy["chg_pct"]) < 1e-9:
        out["state"] = "MISSING"
        out["note"] = "both changes zero — market likely closed, snapshot stale"
    return out


def classify_vix_shape(snap, meta=None):
    """
    P0-1 vintage guard + P1-1 hump state + P1-2 spot-relative slope.

    v2.5 compared whatever numbers it held, with no date check, and its two
    ordering tests both required a MONOTONIC curve — so a humped structure
    (9D above spot, 3M above 9D, which is what event premium looks like)
    matched neither and fell through to slope > 0.5 -> CONTANGO.

    Returns (shape, slope_pct, detail). A rejected or unmeasurable structure
    returns UNKNOWN, which compute_sizing treats with VOLGAP_HAIRCUT — never
    with the 0.50x BACKWARDATION branch.
    """
    detail = {"skew_days": None, "leg_dates": {}, "sources": {},
              "slope_basis": None, "rejected": False, "note": ""}
    if meta:
        detail["leg_dates"] = {k: meta.get(k, {}).get("obs_date") for k in snap}
        detail["sources"] = {k: meta.get(k, {}).get("source") for k in snap}

    have = [k for k in ("VIX9D", "VIX", "VIX3M") if k in snap]
    if len(have) < 3:
        detail["note"] = f"only {have} available — term structure not computed"
        return "UNKNOWN", None, detail

    if meta:
        base = meta.get("VIX", {}).get("obs_date")
        skew = max(_days_between(base, meta.get("VIX9D", {}).get("obs_date")),
                   _days_between(base, meta.get("VIX3M", {}).get("obs_date"))) if base else 999
        detail["skew_days"] = skew
        if skew > VIX_MAX_VINTAGE_SKEW_DAYS:
            detail["rejected"] = True
            detail["note"] = (f"leg vintages {detail['leg_dates']} skew {skew}d — "
                              f"term structure NOT computed across mixed dates")
            errors.append(f"VIX term structure rejected: {skew}d vintage skew "
                          f"{detail['leg_dates']}")
            return "UNKNOWN", None, detail

    v9, v, v3 = snap["VIX9D"], snap["VIX"], snap["VIX3M"]
    slope = round((v3 - v) / v * 100, 2) if v else None      # P1-2 spot-relative
    detail["slope_basis"] = "(VIX3M - VIX) / VIX * 100"

    if v9 > v > v3:
        shape = "BACKWARDATION"
    elif v9 < v < v3:
        shape = "CONTANGO"
    elif v9 > v and v3 > v9:
        shape = "CONTANGO_FRONT_END_HUMP"                     # P1-1
        detail["note"] = "9D above spot with 3M above 9D — event premium in the front end"
    elif slope is not None and slope < -2.0:
        shape = "BACKWARDATION"
    elif slope is not None and slope > 2.0:
        shape = "CONTANGO"
    else:
        shape = "FLAT_MIXED"
    return shape, slope, detail


def reconcile_vix(vol_series, fred_vixcls):
    """
    P1-3: compare on the last SHARED date. A cross-date gap is market movement,
    not a data fault — comparing latest-to-latest manufactures false divergence.
    """
    out = {"status": "NOT_RUN", "pct": None, "date": None,
           "source_value": None, "fred_value": None}
    if vol_series is None or vol_series.empty or fred_vixcls is None or fred_vixcls.empty:
        out["status"] = "NO_FRED"; return out
    overlap = vol_series.index.intersection(fred_vixcls.index)
    if len(overlap) == 0:
        out["status"] = "NO_OVERLAP"; return out
    d = overlap.max()
    sv, fv = float(vol_series.loc[d]), float(fred_vixcls.loc[d])
    diff = abs(sv - fv) / fv * 100 if fv else None
    out.update({"date": d.date().isoformat(), "source_value": round(sv, 4),
                "fred_value": round(fv, 4),
                "pct": round(diff, 3) if diff is not None else None,
                "status": ("MATCH" if diff is not None and diff <= VIX_RECONCILE_TOLERANCE_PCT
                           else f"DIVERGENT_{diff:.1f}PCT" if diff is not None else "UNKNOWN")})
    if out["status"].startswith("DIVERGENT"):
        errors.append(f"VIX reconciliation {out['status']} on {out['date']}: "
                      f"source {sv} vs FRED {fv}")
    return out


def is_risk(name, v):
    """Does this move constitute risk to the book, or is it a rally?"""
    if name in RISK_NEUTRAL:
        return False
    return v.get("direction") == RISK_WHEN.get(name, "DOWN")


def compute_sizing(results, universe, breadth, vix_shape, vvix_stress,
                   event_window=None, gex=None):
    """
    Base verdict from the ETF universe only, counting RED/YELLOW moves in their
    risk-negative direction. Then explicit multiplicative adjustments.

    v2.6 additions are BOTH gated off pending backtest, following the
    REGIME_CONTEST_AFFECTS_SIZING precedent. An uncalibrated haircut that moves
    real money is worse than no haircut.
    """
    reds, yellows, ignored = [], [], []
    for k in universe:
        v = results.get(k, {})
        f = v.get("flag")
        if f not in ("RED", "YELLOW"):
            continue
        if not is_risk(k, v):
            ignored.append(f"{k}({f}/{v.get('direction')})")
            continue
        (reds if f == "RED" else yellows).append(k)
    r, y = len(reds), len(yellows)

    # Only a MEASURED backwardation may trigger the 0.50x branch. A rejected or
    # unavailable term structure resolves to UNKNOWN and takes VOLGAP_HAIRCUT.
    if vix_shape == "BACKWARDATION" or r >= 4:
        mult, base = 0.50, "REDUCE: max 50% normal size, no new longs"
    elif r >= 2 or y >= 4:
        mult, base = 0.75, "CAUTION: 75% normal size, tighten stops"
    elif r == 1 or y >= 2:
        mult, base = 0.90, "MODEST CAUTION: 90% normal size"
    else:
        mult, base = 1.00, "NORMAL: full size within risk parameters"

    adj, advisory = [], []
    if breadth["state"] in ("NARROWING", "MISSING"):
        mult *= BREADTH_HAIRCUT
        adj.append(f"breadth {breadth['state']} x{BREADTH_HAIRCUT}")
    if vvix_stress == "ELEVATED":
        mult *= VVIX_HAIRCUT
        adj.append(f"VVIX elevated x{VVIX_HAIRCUT}")
    # Unmeasurable is not the same as safe. Without the vol complex we cannot
    # classify the term structure, so we cannot rule out backwardation.
    if vix_shape == "UNKNOWN" or vvix_stress == "MISSING":
        mult *= VOLGAP_HAIRCUT
        adj.append(f"vol complex unavailable x{VOLGAP_HAIRCUT}")

    if event_window and event_window.get("active"):
        msg = (f"scheduled event in {EVENT_WINDOW_DAYS}d window "
               f"({'; '.join(event_window['events'][:3])})")
        if EVENT_HAIRCUT_ACTIVE:
            mult *= EVENT_HAIRCUT
            adj.append(f"{msg} x{EVENT_HAIRCUT}")
        else:
            advisory.append(f"{msg} [EVENT_HAIRCUT_ACTIVE=False — no sizing impact]")

    if gex and gex.get("state") == "OK" and gex.get("regime") == "NEGATIVE":
        msg = f"GEX NEGATIVE ({gex.get('net_gex_bn')}B) — dealer hedging amplifies moves"
        if GEX_AFFECTS_SIZING:
            mult *= GEX_NEGATIVE_HAIRCUT
            adj.append(f"{msg} x{GEX_NEGATIVE_HAIRCUT}")
        else:
            advisory.append(f"{msg} [GEX_AFFECTS_SIZING=False — no sizing impact]")

    if REGIME_CONTEST_AFFECTS_SIZING:
        contested_now = [k for k in universe
                         if results.get(k, {}).get("regime") == "CONTESTED"
                         and results.get(k, {}).get("flag") in ("RED", "YELLOW")]
        if contested_now:
            adj.append(f"regime contested: {', '.join(contested_now)} (sizing impact ON)")

    return {"multiplier": round(max(mult, SIZE_FLOOR), 3), "base": base,
            "adjustments": adj, "advisory_only": advisory,
            "red_count": r, "yellow_count": y,
            "red_series": reds, "yellow_series": yellows,
            "ignored_wrong_direction": ignored}


# ══════════════════════════════════════════════════════════════
# SECTION 3 — DATA ACQUISITION
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":

    setup()
    print("\nFetching FRED...")
    fred_data = fetch_fred_all(FRED_SERIES, START_DATE, FRED_API_KEY)

    print("\nFetching Polygon ETFs...")
    poly_data = {}
    for name, ticker in POLYGON_TICKERS.items():
        s = fetch_polygon(ticker, START_DATE, END_DATE, POLYGON_API_KEY)
        if not s.empty:
            poly_data[name] = s
            print(f"  OK   {name}")
        else:
            print(f"  WARN {name} failed — carried neutral")

    print(f"\nFetching breadth pair (RSP/SPY from {BREADTH_START})...")
    rsp_b = fetch_polygon("RSP", BREADTH_START, END_DATE, POLYGON_API_KEY)
    spy_b = fetch_polygon("SPY", BREADTH_START, END_DATE, POLYGON_API_KEY)
    print(f"  RSP: {len(rsp_b)} bars   SPY: {len(spy_b)} bars")

    print("\nFetching vol complex (Cboe primary, yfinance fallback)...")
    vol_data, vol_meta = fetch_vol_complex()
    vix_data = dict(vol_data)

    # DXY: DX=F came back empty on 2026-08-04, silently disabling the
    # dollar/credit conflict rule. UUP is a proxy — only the % change is
    # comparable, not the level.
    dxy_source = "YFINANCE_DXF"
    try:
        import yfinance as yf
        h = yf.Ticker("DX=F").history(period="2y", auto_adjust=False)
        if h is not None and not h.empty and "Close" in h.columns:
            vix_data["DXY"] = cut_to_session(_normalise(h["Close"].astype("float64").dropna()), session_cutoff())
    except Exception as e:
        errors.append(f"yfinance DX=F: {type(e).__name__} — {e}")
    if "DXY" not in vix_data or vix_data["DXY"].empty:
        uup = fetch_polygon("UUP", START_DATE, END_DATE, POLYGON_API_KEY)
        if not uup.empty:
            vix_data["DXY"] = uup
            dxy_source = "POLYGON_UUP_PROXY"
            errors.append("DXY: DX=F unavailable, substituted UUP ETF proxy")
            print("  FALLBACK DXY -> UUP (proxy; level not comparable to DXY index)")
        else:
            dxy_source = "NONE"
            print("  WARN DXY unavailable from both sources — dollar rules disabled")

    print("\nLoading GEX handoff...")
    gex = load_gex()
    if gex["state"] == "OK":
        print(f"  OK   {GEX_PRIMARY_TICKER} {gex['regime']} net {gex['net_gex_bn']:+.3f}B  "
              f"flip {gex['gamma_flip']} vs spot {gex['spot']} "
              f"({gex['flip_vs_spot_pct']:+.2f}%)  as_of {gex['as_of']} "
              f"[{gex['data_mode']}, cov {gex['coverage_pct']}%]")
    else:
        print(f"  {gex['state']}: {gex['note']}")

    print("\nLoading event calendar...")
    event_window = load_event_window()
    print(f"  {'ACTIVE' if event_window['active'] else 'none'} "
          f"({event_window.get('source') or event_window['note']})")
    for e in event_window["events"][:5]:
        print(f"    - {e}")

    # ══════════════════════════════════════════════════════════════
    # SECTION 4 — THRESHOLD FLAGS + REGIME CONTEST
    # ══════════════════════════════════════════════════════════════

    print("\n" + "=" * 78)
    print("THRESHOLD FLAGS — 30d change, direction-aware, asset-class bands")
    print("=" * 78)
    threshold_results = {}
    for name, series in {**poly_data, **vix_data}.items():
        v = flag_thresholds(series, name)
        v["regime"] = detect_regime_contest(v)
        threshold_results[name] = v

    print(f"  {'series':8s} {'30d':>8s} {'5d':>8s}  {'flag':<6s} {'dir':<5s} "
          f"{'regime':<10s} {'as_of':<11s} risk?")
    for name in sorted(threshold_results, key=lambda k: (asset_class(k), k)):
        v = threshold_results[name]
        c30 = f"{v['chg_30d']:+.1f}%" if v["chg_30d"] is not None else "   N/A"
        c5 = f"{v['chg_5d']:+.1f}%" if v["chg_5d"] is not None else "   N/A"
        rk = "RISK" if (v["flag"] in ("RED", "YELLOW") and is_risk(name, v)) else "-"
        esc = "^" if v.get("escalated_5d") else " "
        print(f"  {name:8s} {c30:>8s} {c5:>8s}  {v['flag']:<5s}{esc} {v['direction']:<5s} "
              f"{v['regime']:<10s} {str(v.get('as_of') or ''):<11s} {rk}")

    escalated = [k for k, v in threshold_results.items() if v.get("escalated_5d")]
    if escalated:
        print("\n  ^ ESCALATED on the 5-day move (v2.5 would have scored these on 30d alone):")
        for k in escalated:
            v = threshold_results[k]
            print(f"    {k}: 5d {v['chg_5d']:+.1f}% vs 30d {v['chg_30d']:+.1f}% "
                  f"-> flag {v['flag']}")

    contested = [k for k, v in threshold_results.items()
                 if v["regime"] == "CONTESTED" and v["flag"] in ("RED", "YELLOW")]
    if contested:
        print("\n  REGIME CONTESTED (5d move opposes 30d sign) — ADVISORY, not gating:")
        for k in contested:
            v = threshold_results[k]
            print(f"    {k}: 30d {v['chg_30d']:+.1f}% vs 5d {v['chg_5d']:+.1f}% "
                  f"— the 30d flag may describe a regime whose driver has reversed")

    # ══════════════════════════════════════════════════════════════
    # SECTION 5 — BREADTH (EOD + INTRADAY)
    # ══════════════════════════════════════════════════════════════

    breadth = compute_breadth(rsp_b, spy_b)

    print("\n" + "=" * 78)
    print(f"BREADTH — equal-weight vs cap-weight ({BREADTH_LOOKBACK}d spread, EOD)")
    print("=" * 78)
    if breadth["state"] == "MISSING":
        print(f"  MISSING — {breadth['note']}")
        print("  Concentration risk CANNOT be assessed. Sizing treats this as narrowing.")
        errors.append(f"Breadth MISSING: {breadth['note']}")
    else:
        print(f"  RSP-SPY spread : {breadth['spread_pct']:+.2f}%")
        print(f"  z-score        : {breadth['z']:+.2f}  (window {breadth['zwindow']} rows)")
        print(f"  State          : {breadth['state']}")
        if breadth["state"] == "NARROWING":
            print("  -> index gains carried by the largest members; participation thin")
        elif breadth["state"] == "BROADENING":
            print("  -> participation widening; rally better supported")
        if breadth["note"] != "OK":
            print(f"  NOTE: {breadth['note']}")
        print("  NOTE: EOD series. Describes the LAST COMPLETE SESSION, not today's gap.")

    breadth_intraday = {"state": "SKIPPED", "spread_pct": None,
                        "rsp_pct": None, "spy_pct": None, "note": "INTRADAY_BREADTH=False"}
    if INTRADAY_BREADTH:
        print("\nBREADTH — same-day snapshot (is TODAY's gap broad?)")
        breadth_intraday = compute_intraday_breadth(POLYGON_API_KEY)
        if breadth_intraday["state"] in ("MISSING", "SKIPPED"):
            print(f"  {breadth_intraday['state']} — {breadth_intraday['note']}")
        else:
            print(f"  RSP {breadth_intraday['rsp_pct']:+.2f}%   "
                  f"SPY {breadth_intraday['spy_pct']:+.2f}%   "
                  f"spread {breadth_intraday['spread_pct']:+.2f}pp  "
                  f"[{breadth_intraday['state']}]")
            if breadth_intraday["state"] == "NARROW":
                print("  -> today's move is mega-cap led; gap not confirmed by participation")
            elif breadth_intraday["state"] == "BROAD":
                print("  -> today's move has genuine participation behind it")

    # ══════════════════════════════════════════════════════════════
    # SECTION 6 — VIX TERM STRUCTURE / VVIX / DXY
    # ══════════════════════════════════════════════════════════════

    vix_snap = {k: float(vix_data[k].iloc[-1])
                for k in ("VIX9D", "VIX", "VIX3M")
                if k in vix_data and not vix_data[k].empty}
    vix_shape, vix_slope, vix_detail = classify_vix_shape(vix_snap, vol_meta)
    vix_recon = reconcile_vix(vol_data.get("VIX"), fred_data.get("VIXCLS"))

    print("\n" + "=" * 78)
    print("VIX TERM STRUCTURE")
    print("=" * 78)
    if vix_snap:
        for k in ("VIX9D", "VIX", "VIX3M"):
            if k in vix_snap:
                m = vol_meta.get(k, {})
                print(f"  {k:6s}: {vix_snap[k]:8.2f}   {m.get('obs_date','?')}  "
                      f"age {m.get('age_days','?')}d  [{m.get('source','?')}]")
        print(f"  Shape : {vix_shape}"
              + (f"   slope {vix_slope:+.2f}%  {vix_detail['slope_basis']}"
                 if vix_slope is not None else ""))
        print(f"  Vintage skew : {vix_detail.get('skew_days')}d "
              f"(reject above {VIX_MAX_VINTAGE_SKEW_DAYS}d)")
        if vix_detail.get("rejected"):
            print(f"  REJECTED — {vix_detail['note']}")
            print("  -> shape UNKNOWN, VOLGAP_HAIRCUT applies. The 0.50x "
                  "BACKWARDATION branch CANNOT fire on mixed-vintage legs.")
        elif vix_detail.get("note"):
            print(f"  NOTE: {vix_detail['note']}")
        print(f"  Reconcile    : {vix_recon['status']} "
              f"({vix_recon['pct']}% on {vix_recon['date']})")
    else:
        print("  MISSING — term structure not computed; VOLGAP_HAIRCUT applies")

    vvix_val, vvix_stress = None, "MISSING"
    if "VVIX" in vix_data and not vix_data["VVIX"].empty:
        vvix_val = float(vix_data["VVIX"].iloc[-1])
        # P2: three tiers, aligned with the Fear Engine.
        vvix_stress = ("ELEVATED" if vvix_val > 110 else
                       "HIGH" if vvix_val > 95 else "NORMAL")
        print(f"\nVVIX  : {vvix_val:.2f}  [{vvix_stress}]  "
              f"{vol_meta.get('VVIX', {}).get('obs_date','?')} "
              f"[{vol_meta.get('VVIX', {}).get('source','?')}]")
    else:
        print("\nVVIX  : MISSING — options premium stress cannot be validated")

    if "DXY" in vix_data and not vix_data["DXY"].empty:
        d = threshold_results.get("DXY", {})
        print(f"DXY   : {float(vix_data['DXY'].iloc[-1]):.3f}  ({d.get('chg_30d')}% 30d)  "
              f"[{d.get('flag')}]  source={dxy_source}")

    # ══════════════════════════════════════════════════════════════
    # SECTION 7 — CONFLICT MATRIX (direction-aware)
    # ══════════════════════════════════════════════════════════════

    def sig(name):
        v = threshold_results.get(name, {})
        return v.get("flag", "N/A"), v.get("direction", "UNKNOWN"), v.get("chg_30d")

    spy_f, spy_d, spy_c = sig("SPY")
    tlt_f, tlt_d, _ = sig("TLT")
    uso_f, uso_d, _ = sig("USO")
    gld_f, gld_d, _ = sig("GLD")
    hyg_f, hyg_d, _ = sig("HYG")
    dxy_f, dxy_d, _ = sig("DXY")

    print("\n" + "=" * 78)
    print("SIGNAL CONFLICT MATRIX")
    print("=" * 78)
    conflicts = []

    if spy_f == "RED" and spy_d == "DOWN" and tlt_f == "RED" and tlt_d == "DOWN":
        conflicts.append("SPY and TLT both falling hard — no safe haven, crisis signal")
    if uso_f in ("RED", "YELLOW") and uso_d == "UP" and spy_d == "DOWN":
        conflicts.append("Oil rising into falling equities — stagflation risk")
    if vix_shape == "BACKWARDATION":
        conflicts.append("VIX backwardation — near-term fear exceeds forward expectation")
    if vix_shape == "CONTANGO_FRONT_END_HUMP":
        conflicts.append("VIX front-end hump — 9D above spot with 3M above 9D; event "
                         "premium priced into the front end, not a calm-carry curve")
    if vix_detail.get("rejected"):
        conflicts.append(f"VIX term structure REJECTED on {vix_detail['skew_days']}d "
                         f"vintage skew — vol regime unmeasurable, sized as unavailable")
    if vix_recon["status"].startswith("DIVERGENT"):
        conflicts.append(f"VIX source diverges from FRED VIXCLS by {vix_recon['pct']}% "
                         f"on {vix_recon['date']} — treat the vol block with caution")
    if gld_f in ("RED", "YELLOW") and gld_d == "DOWN" and tlt_d == "DOWN":
        conflicts.append("Gold and TLT falling together — real yield spike")
    if dxy_f in ("RED", "YELLOW") and dxy_d == "UP" and hyg_d == "DOWN":
        conflicts.append("Dollar rising while credit falls — funding stress combo")
    if vvix_stress == "ELEVATED":
        conflicts.append("VVIX elevated — vol-of-vol stress, reduce size")

    if breadth["state"] == "NARROWING" and spy_c is not None and spy_c > 0:
        conflicts.append("SPY advancing on NARROWING breadth — index gain not confirmed "
                         "by participation; concentration risk")
    if breadth["state"] == "BROADENING" and spy_c is not None and spy_c < 0:
        conflicts.append("Breadth BROADENING while SPY falls — mega-cap-led weakness, "
                         "possible rotation rather than de-risking")
    if breadth["state"] == "MISSING":
        conflicts.append("Breadth UNAVAILABLE — participation unmeasurable, size as if narrowing")

    if (breadth["state"] in ("NEUTRAL", "BROADENING")
            and breadth_intraday.get("state") == "NARROW"):
        conflicts.append("Today's gap is NARROW against a healthy 20d breadth — "
                         "mega-cap-led move inside a participating tape, treat as counter-trend")
    if breadth["state"] == "NARROWING" and breadth_intraday.get("state") == "BROAD":
        conflicts.append("Today broadening against a NARROWING 20d trend — "
                         "possible participation turn, not yet confirmed")

    # ── v2.6: GEX conflicts ─────────────────────────────────────────────────
    if gex["state"] in ("OK", "STALE"):
        tag = " [STALE]" if gex["state"] == "STALE" else ""
        if gex["regime"] == "NEGATIVE":
            conflicts.append(f"GEX NEGATIVE ({gex['net_gex_bn']:+.2f}B){tag} — dealers short "
                             f"gamma, hedging AMPLIFIES moves; short-vol and mean-reversion "
                             f"assumptions do not hold")
        fvs = gex.get("flip_vs_spot_pct")
        if fvs is not None and abs(fvs) <= 0.5:
            conflicts.append(f"Spot within {abs(fvs):.2f}% of the gamma flip "
                             f"({gex['spot']} vs {gex['gamma_flip']}){tag} — dealer gamma "
                             f"turns over at current levels; regime label is knife-edge")
        if gex["regime"] == "POSITIVE" and fvs is not None and fvs < 0:
            conflicts.append(f"GEX POSITIVE but spot BELOW the flip{tag} — headline regime "
                             f"and local positioning disagree; a move down enters short gamma")
    elif gex["state"] == "MISSING":
        conflicts.append("GEX UNAVAILABLE — dealer positioning unmeasurable; "
                         "no gamma inference permitted")

    if event_window.get("active"):
        conflicts.append(f"Scheduled event inside {EVENT_WINDOW_DAYS}d "
                         f"({'; '.join(event_window['events'][:3])}) — vol-carry and "
                         f"mean-reversion signals are least reliable across a known binary")
    if escalated:
        conflicts.append(f"5-day escalation on {', '.join(escalated)} — a move at the band's "
                         f"RED threshold inside 5 sessions that the 30d flag did not capture")
    if contested:
        conflicts.append(f"Regime contested on {', '.join(contested)} — 30d flag(s) may "
                         f"describe a reversed driver [ADVISORY, not gating]")
    if dxy_source == "NONE":
        conflicts.append("DXY unavailable from all sources — dollar/funding rules cannot fire")

    for c in conflicts:
        print(f"  ! {c}")
    if not conflicts:
        print("  No major conflicts detected")

    # ══════════════════════════════════════════════════════════════
    # SECTION 8 — POSITION SIZING
    # ══════════════════════════════════════════════════════════════

    SIZING_UNIVERSE = list(POLYGON_TICKERS.keys())   # ETFs only — no vol, no FX
    sizing = compute_sizing(threshold_results, SIZING_UNIVERSE, breadth,
                            vix_shape, vvix_stress, event_window, gex)

    print("\n" + "=" * 78)
    print("POSITION SIZING GUIDANCE")
    print("=" * 78)
    print(f"  Base            : {sizing['base']}")
    print(f"  RISK RED  ({sizing['red_count']})    : {', '.join(sizing['red_series']) or 'none'}")
    print(f"  RISK YELW ({sizing['yellow_count']})    : {', '.join(sizing['yellow_series']) or 'none'}")
    if sizing["ignored_wrong_direction"]:
        print(f"  Ignored (rally, not risk): {', '.join(sizing['ignored_wrong_direction'])}")
    for a in sizing["adjustments"]:
        print(f"  Adjustment      : {a}")
    for a in sizing["advisory_only"]:
        print(f"  Advisory        : {a}")
    print(f"  MULTIPLIER      : {sizing['multiplier']:.2f} x normal size")
    print("\n  ADVISORY ONLY — PSE retired, final sizing is a manual trader decision.")
    print("  Haircut magnitudes are calibration stubs, not backtested values.")

    # ══════════════════════════════════════════════════════════════
    # SECTION 9 — SECTOR TILT
    # ══════════════════════════════════════════════════════════════

    sector_map = {
        "XLE": "Energy", "XLF": "Financials", "XLK": "Technology", "XLV": "Healthcare",
        "XLI": "Industrials", "XLY": "Consumer Disc", "XLP": "Consumer Staples",
        "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Comm Services",
    }
    valid_sectors = {k: threshold_results.get(k, {}).get("chg_30d")
                     for k in sector_map
                     if threshold_results.get(k, {}).get("chg_30d") is not None}
    ranked = []
    if valid_sectors:
        ranked = sorted(valid_sectors.items(), key=lambda kv: kv[1], reverse=True)
        print(f"\nSECTOR 30d RANK")
        for k, v in ranked:
            tag = " [CONTESTED]" if threshold_results.get(k, {}).get("regime") == "CONTESTED" else ""
            print(f"  {sector_map[k]:16s} {v:+6.2f}%{tag}")
        missing = [k for k in sector_map if k not in valid_sectors]
        if missing:
            print(f"  missing (neutral): {', '.join(missing)}")

    # ══════════════════════════════════════════════════════════════
    # SECTION 10 — MANUAL INPUTS STILL REQUIRED
    # ══════════════════════════════════════════════════════════════

    manual_gaps = {
        "DSPX":  "Cboe S&P 500 Dispersion Index — Cboe entitlement, not on Polygon equities.",
        "COR1M": "Cboe 1-Month Implied Correlation — same entitlement gap as DSPX.",
        "COR3M": "Cboe 3-Month Implied Correlation — same entitlement gap as DSPX.",
        "MOVE":  "ICE BofA MOVE bond vol index — no free source.",
        "BTC.D": "Bitcoin dominance — no free API.",
    }
    if gex["state"] != "OK":
        manual_gaps["GEX"] = f"avshunter_gex_proxy handoff {gex['state']} — {gex['note']}"

    print("\n" + "=" * 78)
    print("MANUAL INPUTS STILL REQUIRED")
    print("=" * 78)
    for k, v in manual_gaps.items():
        print(f"  {k:7s} {v}")
    if gex["state"] == "OK":
        print("  GEX     RESOLVED — supplied by avshunter_gex_proxy "
              f"(as_of {gex['as_of']}, {gex['data_mode']})")

    # ══════════════════════════════════════════════════════════════
    # SECTION 11 — EXPORT
    # ══════════════════════════════════════════════════════════════

    flag_rows = [{"series": k, "flag": v.get("flag"), "direction": v.get("direction"),
                  "regime": v.get("regime"), "band": v.get("band"),
                  "chg_30d_pct": v.get("chg_30d"), "chg_5d_pct": v.get("chg_5d"),
                  "latest": v.get("latest"), "as_of": v.get("as_of"),
                  "escalated_5d": bool(v.get("escalated_5d")),
                  "source": vol_meta.get(k, {}).get("source"),
                  "counts_as_risk": bool(v.get("flag") in ("RED", "YELLOW") and is_risk(k, v))}
                 for k, v in threshold_results.items()]
    pd.DataFrame(flag_rows).to_csv(OUTPUT_DIR / "macro_series_threshold_flags.csv", index=False)
    print(f"\nSaved: {OUTPUT_DIR / 'macro_series_threshold_flags.csv'}")

    snap_rows = [{"series": k, "value": v, "shape": vix_shape,
                  "as_of": vol_meta.get(k, {}).get("obs_date"),
                  "source": vol_meta.get(k, {}).get("source")}
                 for k, v in vix_snap.items()]
    if "DXY" in vix_data and not vix_data["DXY"].empty:
        snap_rows.append({"series": "DXY", "value": float(vix_data["DXY"].iloc[-1]),
                          "shape": dxy_source, "as_of": None, "source": dxy_source})
    if vvix_val is not None:
        snap_rows.append({"series": "VVIX", "value": vvix_val, "shape": vvix_stress,
                          "as_of": vol_meta.get("VVIX", {}).get("obs_date"),
                          "source": vol_meta.get("VVIX", {}).get("source")})
    for lbl, val in (("BREADTH_RSP_SPY_Z", breadth["z"]),
                     ("BREADTH_RSP_SPY_SPREAD_PCT", breadth["spread_pct"])):
        snap_rows.append({"series": lbl, "value": val, "shape": breadth["state"],
                          "as_of": END_DATE, "source": "POLYGON"})
    snap_rows.append({"series": "BREADTH_INTRADAY_SPREAD_PP",
                      "value": breadth_intraday.get("spread_pct"),
                      "shape": breadth_intraday.get("state"),
                      "as_of": END_DATE, "source": "POLYGON_SNAPSHOT"})
    pd.DataFrame(snap_rows).to_csv(OUTPUT_DIR / "vix_term_dxy_snapshot.csv", index=False)
    print(f"Saved: {OUTPUT_DIR / 'vix_term_dxy_snapshot.csv'}")

    pd.DataFrame([{
        "run_id": RUN_ID, "as_of": END_DATE,
        "eod_spread_pct": breadth["spread_pct"], "eod_z": breadth["z"],
        "eod_zwindow": breadth["zwindow"], "eod_state": breadth["state"],
        "eod_note": breadth["note"], "lookback": BREADTH_LOOKBACK,
        "intraday_spread_pp": breadth_intraday.get("spread_pct"),
        "intraday_rsp_pct": breadth_intraday.get("rsp_pct"),
        "intraday_spy_pct": breadth_intraday.get("spy_pct"),
        "intraday_state": breadth_intraday.get("state"),
    }]).to_csv(OUTPUT_DIR / "breadth_rsp_spy.csv", index=False)
    print(f"Saved: {OUTPUT_DIR / 'breadth_rsp_spy.csv'}")

    contract = {
        "module": "macro_module", "version": "2.8", "run_id": RUN_ID, "as_of": END_DATE,
        "breadth_eod": breadth,
        "breadth_intraday": breadth_intraday,
        "vix": {"snapshot": vix_snap, "shape": vix_shape, "slope_pct_vs_spot": vix_slope,
                "slope_basis": vix_detail.get("slope_basis"),
                "leg_dates": vix_detail.get("leg_dates"),
                "leg_sources": vix_detail.get("sources"),
                "vintage_skew_days": vix_detail.get("skew_days"),
                "term_structure_rejected": bool(vix_detail.get("rejected")),
                "reconciliation": vix_recon,
                "vvix": vvix_val, "vvix_stress": vvix_stress},
        "gex": gex,
        "event_window": event_window,
        "dxy_source": dxy_source,
        "sizing": sizing,
        "escalated_5d": escalated,
        "regime_contested": contested,
        "regime_contest_affects_sizing": REGIME_CONTEST_AFFECTS_SIZING,
        "event_haircut_active": EVENT_HAIRCUT_ACTIVE,
        "gex_affects_sizing": GEX_AFFECTS_SIZING,
        "conflicts": conflicts,
        "flags": threshold_results,
        "data_gaps": sorted(manual_gaps.keys()),
        "calibration_stubs": {
            "breadth_haircut": BREADTH_HAIRCUT, "breadth_z_trigger": BREADTH_Z_TRIGGER,
            "vvix_haircut": VVIX_HAIRCUT, "volgap_haircut": VOLGAP_HAIRCUT,
            "regime_contest_min": REGIME_CONTEST_MIN,
            "event_haircut": EVENT_HAIRCUT, "gex_negative_haircut": GEX_NEGATIVE_HAIRCUT,
        },
        "errors": [redact(x) for x in errors],      # v2.7: second line of defence
        "advisory_only": True,
    }
    with open(OUTPUT_DIR / "macro_module_contract.json", "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=2, default=str)
    print(f"Saved: {OUTPUT_DIR / 'macro_module_contract.json'}")

    # P2: written unconditionally, so "no errors" and "did not run" differ.
    err_path = OUTPUT_DIR / f"macro_v26_errors_{RUN_ID}.txt"
    with open(err_path, "w", encoding="utf-8") as f:
        f.write("\n".join(redact(x) for x in errors) if errors else f"{RUN_ID}: no errors")
    print(f"Saved: {err_path.name} ({len(errors)} entries)")

    # ══════════════════════════════════════════════════════════════
    # SECTION 12 — VISUALISATION
    # ══════════════════════════════════════════════════════════════

    try:
        if plt is None:
            raise RuntimeError("matplotlib not installed — PNG charts skipped (data outputs unaffected)")
        if valid_sectors:
            plt.figure(figsize=(13, 4.5))
            names = [sector_map[k] for k, _ in ranked]
            vals = [v for _, v in ranked]
            cols = ["#1D9E75" if v >= 0 else "#D85A30" for v in vals]
            plt.bar(names, vals, color=cols, alpha=0.85)
            plt.axhline(0, color="black", linewidth=0.8)
            plt.title("Sector 30-day % change (ranked)")
            plt.xticks(rotation=30, ha="right"); plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(str(OUTPUT_DIR / "macro_sector_rank.png"), dpi=140,
                        bbox_inches="tight")
            plt.close()

        if vix_snap:
            plt.figure(figsize=(5.5, 3))
            plt.bar(list(vix_snap.keys()), list(vix_snap.values()), color="#378ADD", alpha=0.85)
            plt.title(f"VIX term structure — {vix_shape}")
            plt.grid(True, alpha=0.3); plt.tight_layout()
            plt.savefig(str(OUTPUT_DIR / "macro_vix_term.png"), dpi=140, bbox_inches="tight")
            plt.close()

        if breadth["state"] != "MISSING" and not rsp_b.empty and not spy_b.empty:
            df = pd.concat([rsp_b.rename("RSP"), spy_b.rename("SPY")], axis=1).dropna()
            sp = (np.log(df["RSP"]).diff(BREADTH_LOOKBACK)
                  - np.log(df["SPY"]).diff(BREADTH_LOOKBACK)).dropna() * 100
            plt.figure(figsize=(13, 4))
            plt.plot(sp.index, sp.values, linewidth=1.4, color="#534AB7")
            plt.axhline(0, color="black", linewidth=0.8)
            plt.fill_between(sp.index, sp.values, 0, where=(sp.values < 0), alpha=0.15, color="#D85A30")
            plt.fill_between(sp.index, sp.values, 0, where=(sp.values >= 0), alpha=0.15, color="#1D9E75")
            plt.title(f"Breadth: RSP minus SPY, {BREADTH_LOOKBACK}d log spread (%) "
                      f"— latest {breadth['spread_pct']:+.2f}%, z={breadth['z']:+.2f} "
                      f"[{breadth['state']}]")
            plt.ylabel("% (negative = narrowing)")
            plt.grid(True, alpha=0.3); plt.tight_layout()
            plt.savefig(str(OUTPUT_DIR / "macro_breadth.png"), dpi=140, bbox_inches="tight")
            plt.close()
    except Exception as e:
        print(f"Charting failed (data outputs unaffected): {e}")

    if IN_COLAB:
      try:
        from google.colab import files as _cf
        for _f in sorted(list(OUTPUT_DIR.glob("macro_*.csv"))
                         + list(OUTPUT_DIR.glob("macro_*.json"))
                         + list(OUTPUT_DIR.glob(f"macro_v26_errors_{RUN_ID}.txt"))
                         + list(OUTPUT_DIR.glob("macro_*.png"))
                         + [OUTPUT_DIR / "breadth_rsp_spy.csv",
                            OUTPUT_DIR / "vix_term_dxy_snapshot.csv"]):
            try:
                _cf.download(str(_f))
            except Exception:
                pass
      except ImportError:
        pass

    print("\n" + "=" * 78)
    print(f"v2.6 COMPLETE — run_id {RUN_ID} — outputs -> {OUTPUT_DIR}")
    print(f"  Breadth EOD      : {breadth['state']}  (z={breadth['z']})")
    _isp = breadth_intraday.get("spread_pct")
    print(f"  Breadth intraday : {breadth_intraday.get('state')}"
          + (f"  ({_isp:+.2f}pp)" if _isp is not None else "  (no reading)"))
    print(f"  VIX shape        : {vix_shape}"
          + (f"  [REJECTED {vix_detail['skew_days']}d skew]" if vix_detail.get("rejected") else "")
          + f"   legs {vix_detail.get('sources')}")
    print(f"  VIX reconcile    : {vix_recon['status']}")
    print(f"  GEX              : {gex['state']}"
          + (f"  {gex['regime']} {gex['net_gex_bn']:+.2f}B flip {gex['gamma_flip']}"
             if gex['state'] in ('OK', 'STALE') else f"  {gex['note']}"))
    print(f"  Event window     : {'ACTIVE' if event_window['active'] else 'none'}"
          f"  (haircut {'ON' if EVENT_HAIRCUT_ACTIVE else 'OFF'})")
    print(f"  DXY source       : {dxy_source}")
    print(f"  5d escalated     : {', '.join(escalated) if escalated else 'none'}")
    print(f"  Regime contested : {', '.join(contested) if contested else 'none'}")
    print(f"  Size multiplier  : {sizing['multiplier']:.2f}x  [ADVISORY]")
    print(f"  Errors logged    : {len(errors)}")
    print("=" * 78)
