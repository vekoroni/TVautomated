"""
AVSHUNTER Market Intelligence Extractor
VERSION: 5.4.3 — runs unattended on the AVSHUNTER PC (logic of 5.4.2 unchanged)

===============================================================================
CHANGES FROM v5.4.2  (7 Oct 2026 — Colab notebook "Future Bias" ported)
===============================================================================

L-01  Importing the file does nothing. Output folder, keys and banner moved into
      setup(), run only from __main__. Locally the default output folder is
      dropbox\\market_data (Colab keeps /content/market_data); --output-dir or
      AVSH_MI_OUTPUT_DIR overrides it for testing. Keys: Colab Secrets, else the
      environment, else the repo .env (override=False).
L-02  P0  V-05 purge, run in the SHARED dropbox\\market_data, would have deleted
      other producers' files: the bare prefix 'macro_' matches
      macro_series_threshold_flags.csv, macro_module_contract.json,
      macro_breadth.png ... Now only this module's own <prefix>YYYYMMDD_HHMMSS
      outputs are touched, and they are moved to archive\\, never deleted.
L-03  P0  A requests error message carries the full URL, and Polygon (apiKey=)
      and FRED (api_key=) put the key in the query string. v5.4.2 printed it and
      stored it in collection_errors -> collection_errors_*.txt and
      report_*.json (read by build_macro_json.py). Key values are now redacted
      at the source and again at write time.
L-04  report_*.json and collection_errors_*.txt written as UTF-8 (Windows
      default cp1252 is not what the UTF-8 readers expect). UTF-8 console.
      Local run:  venv\\Scripts\\python.exe Enhancements\\colab\\avshunter_market_intelligence_v5_4_3.py

===============================================================================
CHANGES FROM v5.4.1
===============================================================================

NEW   vix_pct_rank_1y and vix9d_pct_rank_1y — position of the current level in
      its own trailing 252-observation distribution. Computed from closes
      already held in memory; no extra fetch.

      WHY: the 12:13 run scored vix_term at +0.6 (the maximum in the map) on
      STEEP_CONTANGO with VIX at 14.90 against a 52-week low of 13.47. Steep
      contango near a 52-week low is a crowded carry; steep contango mid-range
      is not. The score cannot distinguish them, and neither can a consumer
      unless the percentile is published.

      NOT DONE HERE — deliberately. No event calendar, no score adjustment, no
      threshold interpolation. This module emits facts and mechanical
      computations. Whether a steep curve should be trusted in a week
      containing CPI is a sizing decision, and sizing lives in the macro
      module, which already owns BREADTH_HAIRCUT / VVIX_HAIRCUT /
      VOLGAP_HAIRCUT. The event calendar arrives there from
      bond_macro_intelligence (B-01), so there is one calendar, not two.

      Raw contango_ratio is emitted unrounded so anything downstream can
      re-tier without inheriting this module's 1.25 / 1.10 / 0.95 cut points.

===============================================================================
CHANGES IN v5.4.1  (defects found in the 2026-08-09 11:07 validation run)
===============================================================================

V-01  P0  NO CROSS-SERIES VINTAGE CHECK — the defect that mattered.
          The 11:07 run reported STEEP_CONTANGO_FRONT_END_HUMP with
          contango_ratio 1.3785. It compared:
              VIX    14.90  observed 2026-08-07
              VIX9D  16.85  observed 2026-07-17   <- 23 days stale
              VIX3M  20.54  observed 2026-07-17   <- 23 days stale
          yfinance ^VIX9D and ^VIX3M stopped updating on 17 July while ^VIX and
          ^VVIX stayed current. The "hump" was an artefact of mixed vintages,
          not an observation. The VIX9D "+51% weekly" reading was the 10->17
          July move, not the week before 8 August.
          v5.4 tagged obs_date on every row and then never compared them one
          layer up — the exact failure class this build exists to remove.
          Now: any leg more than TERM_MAX_VINTAGE_SKEW_DAYS from spot forces
          regime UNKNOWN / TERM_STRUCTURE_STALE and a 0.0 layer score.

NEW   P0  CBOE AS PRIMARY VOL SOURCE.
          Cboe calculates and publishes these indices and serves daily closes
          free, with no key and no entitlement. yfinance demoted to fallback
          after demonstrating ticker-specific staleness. Per-leg source is
          recorded, and a mixed-source term structure is flagged.

V-02  P1  RECONCILIATION compared latest-vs-latest, so VIX 14.90 (7 Aug) against
          FRED VIXCLS 15.15 (6 Aug) produced a false DIVERGENT_1.7PCT. A
          cross-date gap is market movement, not a data fault. Now compares on
          the last SHARED date.

V-03  P1  FUTURE-DATED FRED OBSERVATIONS. IORB came back dated 2026-08-10 on a
          9 August run — FRED forward-fills some series past today. Any
          observation dated after today is now dropped.

V-04  P1  MIXED VINTAGE INSIDE THE CURVE BLOCK. v5.4 reported slope_2s10s 0.46
          (T10Y2Y, 7 Aug) alongside yield_10y 4.69 and yield_2y 4.25 (DGS, 6
          Aug), which differ by 0.44 — internally inconsistent output. And
          curve_move ran off the DGS series only, so it missed Friday's move
          entirely and reported BEAR_FLATTENING when 7 Aug was bull steepening.
          Now both slopes are reported with their own as_of, the skew is
          measured, and the discrepancy is explicit.

V-05  P2  DIRECTORY HYGIENE. us_indices_cash_20260809_100152.csv — 100% NaN,
          from the pre-fix 10:01 run — was still sitting in the output folder
          beside the 11:07 files. Downstream globs (forward_bias_*.csv etc.)
          would collide. Prior-run outputs are now purged before writing.

V-06  P2  vix_term layer reported n=? — inputs_used was missing.

NEW   P1  INFLATION TIER now evaluates headline CPI, core CPI and CORE PCE
          separately and takes the most cautious. Core PCE is the Fed's target
          gauge and ran 3.29% y/y in this batch, above core CPI at 2.81%.
          The chosen tier and the gauge behind it are both published.

===============================================================================
CARRIED FROM v5.4 (see that header for full detail)
===============================================================================
  C-01 get_val no longer returns empty rows   C-06 inflation level != trend
  C-02 MarketData indices removed             C-07 copper polarity
  C-03 fail-loud + collection validation      C-08 vix_signal off VXX
  C-04 VIX regime from term structure         C-09 real YTD
  C-05 FRED map 22 -> 31 series + y/y         C-10 keys from Secrets/env
===============================================================================
"""

# -- Cell 1 -------------------------------------------------------------------
# !pip install requests pandas numpy yfinance --quiet

import os
import io
import re
import json
import time
import glob
import warnings
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings('ignore')

# ============================================================================
# CONFIG
# ============================================================================

OUTPUT_DIR = "/content/market_data"      # Colab default; setup() resolves the real one

MAX_NULL_RATE = 0.80
ABORT_ON_COLLECTION_FAILURE = True
VIX_RECONCILE_TOLERANCE_PCT = 1.0
TERM_MAX_VINTAGE_SKEW_DAYS = 3       # V-01
PURGE_PRIOR_RUNS = True              # V-05
USSLIND_MAX_AGE_DAYS = 120

OUTPUT_PREFIXES = ('report_', 'macro_', 'forward_bias_', 'collection_validation_',
                   'collection_errors_', 'equity_etf_', 'sectors_', 'metals_etf_',
                   'energy_etf_', 'bonds_etf_', 'agriculture_etf_', 'vol_dollar_',
                   'fx_spot_', 'vol_complex_', 'global_indices_', 'us_indices_cash_')


def _load_key(names, label):
    try:
        from google.colab import userdata
        for n in names:
            try:
                v = userdata.get(n)
                if v and v.strip():
                    print(f"  {label:14s}: Colab Secret '{n}' ({len(v.strip())} chars)")
                    return v.strip()
            except Exception as e:
                if "NotebookAccess" in type(e).__name__:
                    print(f"  {label:14s}: Secret '{n}' EXISTS but notebook access is OFF")
    except ImportError:
        pass
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            print(f"  {label:14s}: environment '{n}' ({len(v)} chars)")
            return v
    print(f"  {label:14s}: NOT FOUND (tried {', '.join(names)})")
    return None


POLYGON_API_KEY = None      # set by setup()
FRED_API_KEY = None         # set by setup()
REPO_ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"


def setup(argv=None):
    """Everything v5.4.2 did at import time: resolve the output folder, load keys, print the
    banner. Called only when the file is run, so importing it (tests) has no side effects."""
    global OUTPUT_DIR, POLYGON_API_KEY, FRED_API_KEY
    import argparse
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        import google.colab  # noqa: F401
        in_colab = True
    except ImportError:
        in_colab = False
    parser = argparse.ArgumentParser(description="AVSHUNTER market intelligence extractor")
    parser.add_argument("--output-dir", default=os.environ.get("AVSH_MI_OUTPUT_DIR"),
                        help="write here instead of dropbox\\market_data (for testing)")
    args, _ = parser.parse_known_args(argv)     # Colab passes its own kernel arguments
    local_default = os.path.join(REPO_ROOT, "dropbox", "market_data")
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    elif not in_colab and os.path.isdir(local_default):
        OUTPUT_DIR = local_default
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not in_colab:
        try:
            from dotenv import load_dotenv
            env = os.path.join(REPO_ROOT, ".env")
            if os.path.exists(env):
                load_dotenv(env, override=False)    # real environment variables win
        except ImportError:
            pass

    print("=" * 70)
    print("AVSHUNTER MARKET INTELLIGENCE v5.4.3 — Percentile context")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    POLYGON_API_KEY = _load_key(["POLYGON_API_KEY", "POLYGON"], "Polygon")
    FRED_API_KEY = _load_key(["FRED_API_KEY", "FRED"], "FRED")

    if not POLYGON_API_KEY:
        raise SystemExit("POLYGON_API_KEY is required — cannot proceed")
    if not FRED_API_KEY:
        print("  WARNING: no FRED key — macro block and VIX reconciliation degraded")

    print("  Vol complex   : CBOE primary, yfinance fallback (V-01)")
    print(f"  Vintage guard : term structure rejected above {TERM_MAX_VINTAGE_SKEW_DAYS}d skew")
    print(f"  Output dir    : {OUTPUT_DIR}")
    return in_colab


COLLECTION_ERRORS = []
TODAY_ISO = date.today().isoformat()

_KEY_IN_TEXT = re.compile(r"((?:apiKey|api_key|apikey|token)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text):
    """Remove API key values from any text (a requests error message carries the full URL,
    and Polygon/FRED put the key in the query string)."""
    return _KEY_IN_TEXT.sub(r"\1REDACTED", str(text))


def safe_error(e):
    """Error description for the console and the error record: type, HTTP status, message
    with key values redacted."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__}" + (f" (HTTP {status})" if status else "") + f" — {redact(e)}"


# ============================================================================
# TECHNICAL HELPERS
# ============================================================================

def safe_series(closes):
    if closes is None or len(closes) == 0:
        return np.array([])
    return np.array([c for c in closes if c is not None and not np.isnan(float(c))])


def calculate_rsi(closes, period=14):
    s = safe_series(closes)
    if len(s) < period + 1:
        return None
    deltas = np.diff(s)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain, avg_loss = np.mean(gains[:period]), np.mean(losses[:period])
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def calculate_bollinger_position(closes, period=20, std_dev=2):
    s = safe_series(closes)
    if len(s) < period:
        return None
    recent = s[-period:]
    mid, std = np.mean(recent), np.std(recent, ddof=1)
    if std == 0:
        return 0.5
    bw = (mid + std_dev * std) - (mid - std_dev * std)
    return round((s[-1] - (mid - std_dev * std)) / bw, 3) if bw != 0 else 0.5


def calculate_momentum(closes, period):
    s = safe_series(closes)
    if len(s) < period + 1:
        return None
    return round((s[-1] - s[-period - 1]) / s[-period - 1] * 100, 3)


def calculate_adx_proxy(closes, highs, lows, period=14):
    c, h, l = safe_series(closes), safe_series(highs), safe_series(lows)
    if len(c) < period + 2 or len(h) != len(c) or len(l) != len(c):
        return None
    dm_plus, dm_minus, tr = [], [], []
    for i in range(1, len(c)):
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        dm_plus.append(up if up > down and up > 0 else 0)
        dm_minus.append(down if down > up and down > 0 else 0)
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))

    def wilder(data, n):
        r = [np.mean(data[:n])]
        for v in data[n:]:
            r.append(r[-1] - r[-1] / n + v)
        return r

    atr, dip, dim = wilder(tr, period), wilder(dm_plus, period), wilder(dm_minus, period)
    dx = []
    for a, p, m in zip(atr[-period:], dip[-period:], dim[-period:]):
        if a == 0:
            continue
        _p, _m = 100 * p / a, 100 * m / a
        if (_p + _m) != 0:
            dx.append(100 * abs(_p - _m) / (_p + _m))
    return round(np.mean(dx), 2) if dx else None


def _days_between(a, b):
    try:
        return abs((pd.Timestamp(a) - pd.Timestamp(b)).days)
    except Exception:
        return 999


# ============================================================================
# BUILD METRICS
# ============================================================================

def build_metrics(ticker, name, closes, highs=None, lows=None, volumes=None,
                  dates=None, source="UNKNOWN", status="OK", note=""):
    empty = {
        'ticker': ticker, 'name': name, 'current_price': None, 'daily_pct': None,
        'weekly_pct': None, 'monthly_pct': None, 'ytd_pct': None, 'volume': None,
        'high_52w': None, 'low_52w': None, 'pct_from_52w_high': None,
        'source': source, 'obs_date': None,
        'data_status': status if status != "OK" else "NO_DATA",
        'data_flag': 'FAILED', 'note': note,
        'closes': [], 'highs': [], 'lows': [], 'volumes': [], 'dates': [],
    }
    if closes is None or len(closes) < 2:
        return empty

    c = [x for x in closes if x is not None and not (isinstance(x, float) and np.isnan(x))]
    if len(c) < 2:
        return empty

    h = list(highs) if highs is not None else list(c)
    l = list(lows) if lows is not None else list(c)
    v = list(volumes) if volumes is not None else [0] * len(c)
    d = list(dates) if dates is not None else []

    current, previous = c[-1], c[-2]
    week, month = c[max(0, len(c) - 6)], c[max(0, len(c) - 22)]

    ytd_base = None
    if d and len(d) == len(c):
        yr = pd.Timestamp(d[-1]).year
        for i, dt in enumerate(d):
            if pd.Timestamp(dt).year == yr:
                ytd_base = c[i]
                break
    h52 = max(h[-252:]) if len(h) >= 252 else max(h)
    l52 = min(l[-252:]) if len(l) >= 252 else min(l)

    def pct(a, b):
        return round((a - b) / b * 100, 3) if b else None

    obs = str(pd.Timestamp(d[-1]).date()) if d else None
    # A row can be populated and simultaneously stale. Flag it here so the
    # consumer does not have to infer it (V-01 root cause).
    stale_days = _days_between(obs, TODAY_ISO) if obs else None
    return {
        'ticker': ticker, 'name': name,
        'current_price': round(current, 4),
        'daily_pct': pct(current, previous),
        'weekly_pct': pct(current, week),
        'monthly_pct': pct(current, month),
        'ytd_pct': pct(current, ytd_base) if ytd_base else None,
        'volume': int(v[-1]) if v and v[-1] is not None else None,
        'high_52w': round(h52, 4), 'low_52w': round(l52, 4),
        'pct_from_52w_high': round((current - h52) / h52 * 100, 2) if h52 else None,
        'source': source, 'obs_date': obs, 'age_days': stale_days,
        'data_status': 'OK',
        'data_flag': 'STALE' if (stale_days or 0) > 5 else 'DIRECT',
        'note': note,
        'closes': c[-500:], 'highs': h[-500:], 'lows': l[-500:],
        'volumes': v[-60:],
        'dates': [str(pd.Timestamp(x).date()) for x in d[-500:]] if d else [],
    }


# ============================================================================
# SOURCE 1 — POLYGON
# ============================================================================

class PolygonExtractor:
    def __init__(self, api_key):
        self.api_key, self.base_url, self._cache = api_key, "https://api.polygon.io", {}

    def get_data(self, ticker, days_back=550):
        if ticker in self._cache:
            return self._cache[ticker]
        end = datetime.now()
        start = end - timedelta(days=days_back)
        url = (f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day"
               f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}")
        try:
            r = requests.get(url, params={'apiKey': self.api_key, 'adjusted': 'true',
                                          'sort': 'asc', 'limit': 50000}, timeout=15)
            r.raise_for_status()
            time.sleep(0.05)
            self._cache[ticker] = r.json()
            return self._cache[ticker]
        except Exception as e:
            COLLECTION_ERRORS.append(f"Polygon {ticker}: {safe_error(e)}")
            print(f"    FAIL {ticker}: {safe_error(e)}")
            return {}

    def fetch(self, ticker, name):
        res = (self.get_data(ticker) or {}).get('results')
        if not res:
            COLLECTION_ERRORS.append(f"Polygon {ticker}: empty results")
            return build_metrics(ticker, name, [], source="POLYGON",
                                 status="NO_DATA", note="empty results")
        return build_metrics(ticker, name,
                             closes=[r['c'] for r in res], highs=[r['h'] for r in res],
                             lows=[r['l'] for r in res], volumes=[r.get('v', 0) for r in res],
                             dates=[pd.to_datetime(r['t'], unit='ms') for r in res],
                             source="POLYGON")

    def extract(self):
        print("\n" + "-" * 70)
        print("SOURCE 1 — POLYGON (ETFs, sectors, FX spot, commodity proxies)")
        print("-" * 70)
        assets = {
            'Equity_ETF': {'SPY': 'S&P500 ETF (SPY)       [proxy: ES=F]',
                           'QQQ': 'NASDAQ ETF (QQQ)        [proxy: NQ=F]',
                           'DIA': 'Dow ETF (DIA)           [proxy: YM=F]',
                           'IWM': 'Russell ETF (IWM)       [proxy: RTY=F]',
                           'RSP': 'S&P500 Equal Weight (RSP)',
                           'ARKK': 'ARK Innovation (ARKK)'},
            'Sectors': {'XLF': 'Financials (XLF)', 'XLE': 'Energy (XLE)',
                        'XLK': 'Technology (XLK)', 'XLV': 'Healthcare (XLV)',
                        'XLI': 'Industrials (XLI)', 'XLY': 'Consumer Disc (XLY)',
                        'XLP': 'Consumer Staples (XLP)', 'XLU': 'Utilities (XLU)',
                        'XLB': 'Materials (XLB)', 'XLRE': 'Real Estate (XLRE)',
                        'XLC': 'Comm Services (XLC)'},
            'Metals_ETF': {'GLD': 'Gold ETF (GLD)          [proxy: GC=F]',
                           'SLV': 'Silver ETF (SLV)        [proxy: SI=F]',
                           'GDX': 'Gold Miners (GDX)', 'GDXJ': 'Jr Gold Miners (GDXJ)',
                           'CPER': 'Copper ETF (CPER)       [proxy: HG=F]',
                           'PPLT': 'Platinum ETF (PPLT)     [proxy: PL=F]'},
            'Energy_ETF': {'USO': 'Oil ETF (USO)           [proxy: CL=F]',
                           'UNG': 'NatGas ETF (UNG)        [proxy: NG=F]',
                           'XOP': 'Oil & Gas E&P (XOP)', 'OIH': 'Oil Services (OIH)',
                           'PDBC': 'Commodity Basket (PDBC)'},
            'Bonds_ETF': {'TLT': '20Y Treasury (TLT)      [proxy: ZB=F]',
                          'IEF': '10Y Treasury (IEF)      [proxy: ZN=F]',
                          'SHY': '2Y Treasury (SHY)       [proxy: ZT=F]',
                          'HYG': 'High Yield Corp (HYG)', 'LQD': 'Investment Grade (LQD)'},
            'Agriculture_ETF': {'DBA': 'Agriculture Basket (DBA)',
                                'CORN': 'Corn ETF (CORN)         [proxy: ZC=F]',
                                'SOYB': 'Soybean ETF (SOYB)      [proxy: ZS=F]',
                                'WEAT': 'Wheat ETF (WEAT)        [proxy: ZW=F]'},
            'Vol_Dollar': {'VXX': 'VIX Short-Term (VXX)', 'UVXY': 'Ultra VIX (UVXY)',
                           'SVXY': 'Short VIX (SVXY)',
                           'UUP': 'Dollar ETF (UUP)        [proxy: DX=F]'},
            'FX_Spot': {'C:EURUSD': 'EUR/USD              [proxy: 6E=F]',
                        'C:GBPUSD': 'GBP/USD              [proxy: 6B=F]',
                        'C:USDJPY': 'USD/JPY              [proxy: 6J=F]',
                        'C:USDCNH': 'USD/CNH', 'C:AUDUSD': 'AUD/USD'},
        }
        out = {}
        for cat, tickers in assets.items():
            rows = [self.fetch(t, n) for t, n in tickers.items()]
            ok = sum(1 for r in rows if r['data_status'] == 'OK')
            print(f"  [{cat:16s}] {ok}/{len(rows)} populated")
            out[cat] = pd.DataFrame(rows)
        return out


# ============================================================================
# SOURCE 2 — VOL COMPLEX  (Cboe primary, yfinance fallback)
# ============================================================================

class VolComplexExtractor:
    """
    Cboe calculates and publishes the VIX complex and serves daily closes free,
    with no key and no entitlement. That makes it strictly better than any
    vendor for an EOD pipeline — and after ^VIX9D / ^VIX3M silently froze on
    17 July while ^VIX kept updating, it is also the only source we can rely on.

    Per-leg source is recorded so a mixed-source term structure is visible.
    """
    CBOE_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"

    CBOE_CANDIDATES = {
        'VIX':   [f"{CBOE_BASE}/VIX_History.csv"],
        'VIX9D': [f"{CBOE_BASE}/VIX9D_History.csv"],
        'VIX3M': [f"{CBOE_BASE}/VIX3M_History.csv", f"{CBOE_BASE}/VXV_History.csv"],
        'VVIX':  [f"{CBOE_BASE}/VVIX_History.csv"],
    }
    YF_TICKERS = {'VIX': '^VIX', 'VIX9D': '^VIX9D', 'VIX3M': '^VIX3M', 'VVIX': '^VVIX'}
    NAMES = {'VIX': 'VIX (CBOE Volatility)', 'VIX9D': 'VIX9D (9-Day VIX)',
             'VIX3M': 'VIX3M (3-Month VIX)', 'VVIX': 'VVIX (Vol of Vol)'}

    # ---- Cboe -------------------------------------------------------------
    @staticmethod
    def _parse_cboe(text, key):
        """
        Cboe files vary: VIX_History has OPEN/HIGH/LOW/CLOSE; the single-value
        files sometimes name the column after the index. Locate a date column
        and a close-like column rather than assuming a fixed schema.
        """
        df = pd.read_csv(io.StringIO(text))
        if df.empty:
            return None
        cols = {c.strip().upper(): c for c in df.columns}
        date_col = next((cols[c] for c in cols if 'DATE' in c), None)
        if date_col is None:
            return None
        close_col = None
        for want in ('CLOSE', f'{key} CLOSE', key, 'VALUE', 'INDEX'):
            if want in cols:
                close_col = cols[want]
                break
        if close_col is None:
            numeric = [c for c in df.columns
                       if c != date_col and pd.to_numeric(df[c], errors='coerce').notna().any()]
            if not numeric:
                return None
            close_col = numeric[-1]

        out = df[[date_col, close_col]].copy()
        out.columns = ['date', 'close']
        out['date'] = pd.to_datetime(out['date'], errors='coerce')
        out['close'] = pd.to_numeric(out['close'], errors='coerce')
        out = out.dropna().sort_values('date')
        out = out[out['date'] <= pd.Timestamp(TODAY_ISO)]      # V-03 pattern
        return out.tail(600) if not out.empty else None

    def fetch_cboe(self, key):
        for url in self.CBOE_CANDIDATES.get(key, []):
            try:
                r = requests.get(url, timeout=25,
                                 headers={'User-Agent': 'AVSHUNTER/5.4.1'})
                if r.status_code != 200 or not r.text.strip():
                    continue
                parsed = self._parse_cboe(r.text, key)
                if parsed is None or len(parsed) < 2:
                    continue
                closes = parsed['close'].tolist()
                return build_metrics(key, self.NAMES[key], closes=closes,
                                     highs=closes, lows=closes,
                                     volumes=[0] * len(closes),
                                     dates=list(parsed['date']),
                                     source="CBOE",
                                     note=url.rsplit('/', 1)[-1])
            except Exception as e:
                COLLECTION_ERRORS.append(f"Cboe {key} ({url.rsplit('/',1)[-1]}): "
                                         f"{type(e).__name__} — {e}")
        return None

    # ---- yfinance fallback -------------------------------------------------
    def fetch_yf(self, key):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            hist = yf.Ticker(self.YF_TICKERS[key]).history(period="2y", auto_adjust=False)
        except Exception as e:
            COLLECTION_ERRORS.append(f"yfinance {key}: {type(e).__name__} — {e}")
            return None
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return None
        df = hist[['Close', 'High', 'Low', 'Volume']].dropna(subset=['Close'])
        if df.empty:
            return None
        idx = pd.to_datetime(df.index)
        try:
            if idx.tz is not None:
                idx = idx.tz_convert(None)
        except (AttributeError, TypeError):
            pass
        return build_metrics(key, self.NAMES[key],
                             closes=df['Close'].astype(float).tolist(),
                             highs=df['High'].astype(float).tolist(),
                             lows=df['Low'].astype(float).tolist(),
                             volumes=df['Volume'].fillna(0).astype(float).tolist(),
                             dates=list(idx.normalize()), source="YFINANCE")

    def extract(self):
        print("\n" + "-" * 70)
        print("SOURCE 2a — VOL COMPLEX (Cboe primary, yfinance fallback)")
        print("-" * 70)
        rows = []
        for key in ('VIX', 'VIX9D', 'VIX3M', 'VVIX'):
            row = self.fetch_cboe(key)
            if row is None or row['data_status'] != 'OK':
                if row is None:
                    COLLECTION_ERRORS.append(f"Cboe {key}: unavailable — falling back to yfinance")
                alt = self.fetch_yf(key)
                if alt is not None:
                    alt['data_flag'] = 'FALLBACK' if alt['data_flag'] == 'DIRECT' else alt['data_flag']
                    row = alt
            if row is None:
                row = build_metrics(key, self.NAMES[key], [], source="NONE",
                                    status="NO_DATA", note="Cboe and yfinance both failed")
                COLLECTION_ERRORS.append(f"{key}: no source available")
            rows.append(row)
            px = f"{row['current_price']:.2f}" if row['current_price'] else "n/a"
            age = f"{row.get('age_days')}d" if row.get('age_days') is not None else "?"
            mark = "OK  " if row['data_status'] == 'OK' else "FAIL"
            print(f"    {mark} {key:6s} {px:>8s}  {row['obs_date'] or '':10s}  "
                  f"age {age:>4s}  src {row['source']}")
        ok = sum(1 for r in rows if r['data_status'] == 'OK')
        print(f"  [Vol_Complex     ] {ok}/{len(rows)} populated")
        return {'Vol_Complex': pd.DataFrame(rows)}


class GlobalIndicesExtractor:
    SYMBOLS = {'^GDAXI': 'DAX (Germany)', '^FTSE': 'FTSE 100 (UK)',
               '^N225': 'Nikkei 225 (Japan)', '^HSI': 'Hang Seng (HK)',
               '^FCHI': 'CAC 40 (France)'}

    def extract(self):
        print("\n" + "-" * 70)
        print("SOURCE 2b — GLOBAL INDICES (yfinance)")
        print("-" * 70)
        try:
            import yfinance as yf
        except ImportError:
            COLLECTION_ERRORS.append("yfinance not installed — global indices unavailable")
            return {'Global_Indices': pd.DataFrame(
                [build_metrics(s.lstrip('^'), n, [], source="YFINANCE",
                               status="NO_LIBRARY") for s, n in self.SYMBOLS.items()])}
        rows = []
        for sym, name in self.SYMBOLS.items():
            try:
                hist = yf.Ticker(sym).history(period="2y", auto_adjust=False)
                df = hist[['Close', 'High', 'Low', 'Volume']].dropna(subset=['Close'])
                idx = pd.to_datetime(df.index)
                try:
                    if idx.tz is not None:
                        idx = idx.tz_convert(None)
                except (AttributeError, TypeError):
                    pass
                row = build_metrics(sym.lstrip('^'), name,
                                    closes=df['Close'].astype(float).tolist(),
                                    highs=df['High'].astype(float).tolist(),
                                    lows=df['Low'].astype(float).tolist(),
                                    volumes=df['Volume'].fillna(0).astype(float).tolist(),
                                    dates=list(idx.normalize()), source="YFINANCE")
            except Exception as e:
                COLLECTION_ERRORS.append(f"yfinance {sym}: {type(e).__name__} — {e}")
                row = build_metrics(sym.lstrip('^'), name, [], source="YFINANCE",
                                    status="EXCEPTION", note=str(e)[:120])
            rows.append(row)
            px = f"{row['current_price']:,.2f}" if row['current_price'] else "n/a"
            print(f"    {'OK  ' if row['data_status']=='OK' else 'FAIL'} "
                  f"{row['ticker']:8s} {px:>12s}  {row['obs_date'] or ''}")
        ok = sum(1 for r in rows if r['data_status'] == 'OK')
        print(f"  [Global_Indices  ] {ok}/{len(rows)} populated")
        return {'Global_Indices': pd.DataFrame(rows)}


# ============================================================================
# SOURCE 3 — FRED
# ============================================================================

class FREDExtractor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.stlouisfed.org/fred"
        self.indicators = {
            'PAYEMS': ('Nonfarm Payrolls', 'Employment', False),
            'UNRATE': ('Unemployment Rate', 'Employment', False),
            'ICSA': ('Initial Jobless Claims', 'Employment', False),
            'CPIAUCSL': ('CPI (Headline)', 'Inflation', True),
            'CPILFESL': ('CPI (Core)', 'Inflation', True),
            'PPIACO': ('PPI (Producer Prices)', 'Inflation', True),
            'PCEPILFE': ('PCE Core Inflation', 'Inflation', True),
            'FEDFUNDS': ('Fed Funds Rate', 'Policy', False),
            'SOFR': ('SOFR (Overnight Funding)', 'Policy', False),
            'IORB': ('Interest on Reserve Balances', 'Policy', False),
            'DGS3MO': ('3M Treasury Yield', 'Policy', False),
            'DGS2': ('2Y Treasury Yield', 'Policy', False),
            'DGS10': ('10Y Treasury Yield', 'Policy', False),
            'DGS30': ('30Y Treasury Yield', 'Policy', False),
            'T10Y2Y': ('Yield Curve (10Y-2Y)', 'Policy', False),
            'T10Y3M': ('Yield Curve (10Y-3M)', 'Policy', False),
            'INDPRO': ('Industrial Production', 'Activity', True),
            'RSXFS': ('Retail Sales', 'Activity', True),
            'NEWORDER': ('Durable Goods / Mfg Orders', 'Activity', True),
            'UMCSENT': ('Consumer Sentiment', 'Sentiment', False),
            'USSLIND': ('Leading Economic Index (LEI)', 'Leading', False),
            'M1SL': ('M1 Money Supply', 'Liquidity', True),
            'M2SL': ('M2 Money Supply', 'Liquidity', True),
            'WALCL': ('Fed Balance Sheet (WALCL)', 'Liquidity', False),
            'WTREGEN': ('Treasury General Account', 'Liquidity', False),
            'WRESBAL': ('Reserve Balances', 'Liquidity', False),
            'RRPONTSYD': ('Overnight Reverse Repo', 'Liquidity', False),
            'TOTLL': ('Total Loans & Leases', 'Liquidity', False),
            'DTWEXBGS': ('Dollar Index (Trade-Wtd)', 'Currency', False),
            'DEXJPUS': ('USD/JPY', 'Currency', False),
            'VIXCLS': ('VIX (FRED Daily)', 'Volatility', False),
        }

    def get_series(self, series_id, limit=400):
        params = {'series_id': series_id, 'api_key': self.api_key,
                  'file_type': 'json', 'sort_order': 'desc', 'limit': limit}
        try:
            r = requests.get(f"{self.base_url}/series/observations", params=params, timeout=15)
            r.raise_for_status()
            time.sleep(0.10)
            obs = [(o['date'], float(o['value'])) for o in r.json().get('observations', [])
                   if o['value'] not in ('.', '')]
            # V-03: FRED forward-fills some series past today. IORB came back
            # dated 2026-08-10 on a 9 August run.
            future = [d for d, _ in obs if d > TODAY_ISO]
            if future:
                COLLECTION_ERRORS.append(
                    f"FRED {series_id}: dropped {len(future)} future-dated obs (latest {max(future)})")
                obs = [(d, v) for d, v in obs if d <= TODAY_ISO]
            return obs
        except Exception as e:
            COLLECTION_ERRORS.append(f"FRED {series_id}: {safe_error(e)}")
            return []

    def extract(self):
        print("\n" + "-" * 70)
        print(f"SOURCE 3 — FRED ({len(self.indicators)} macro series)")
        print("-" * 70)
        if not self.api_key:
            COLLECTION_ERRORS.append("FRED: no API key — block skipped")
            return {}
        macro = {}
        for sid, (name, cat, wants_yoy) in self.indicators.items():
            obs = self.get_series(sid)
            if not obs:
                print(f"    FAIL {sid}")
                continue
            latest_d, latest_v = obs[0]
            prev_v = obs[1][1] if len(obs) > 1 else None
            chg = ((latest_v - prev_v) / abs(prev_v) * 100) if prev_v else None
            yoy = None
            if wants_yoy and len(obs) >= 13 and obs[12][1]:
                yoy = round((latest_v / obs[12][1] - 1) * 100, 3)
            macro[sid] = {
                'name': name, 'category': cat, 'value': latest_v, 'date': latest_d,
                'change_pct': chg, 'prev_value': prev_v,
                'abs_change': round(latest_v - prev_v, 3) if prev_v is not None else None,
                'yoy_pct': yoy, 'obs_count': len(obs),
                'age_days': _days_between(latest_d, TODAY_ISO),
                'history': obs[:60], 'source': 'FRED',
            }
            extra = f"  y/y {yoy:+.2f}%" if yoy is not None else ""
            print(f"    OK   {sid:10s} {latest_v:>13,.3f}  {latest_d}{extra}")
        print(f"  {len(macro)}/{len(self.indicators)} series retrieved")
        return macro


# ============================================================================
# INFLATION — tier across all three gauges, take the most cautious
# ============================================================================

def _tier(y):
    if y is None:
        return None
    return 'LOW' if y < 2.5 else 'MODERATE' if y <= 3.5 else 'HIGH'


def calculate_inflation_pressure(macro_data):
    p = {'level': 'UNKNOWN', 'trend': 'UNKNOWN', 'regime': 'UNKNOWN',
         'level_basis': None, 'tiers': {},
         'headline_yoy': None, 'core_cpi_yoy': None, 'core_pce_yoy': None,
         'real_fed_funds': None, 'energy_driven_flag': False, 'components': {}}

    for ind in ('CPIAUCSL', 'CPILFESL', 'PPIACO', 'PCEPILFE'):
        if ind in macro_data:
            p['components'][ind] = {'value': macro_data[ind]['value'],
                                    'mom_pct': macro_data[ind]['change_pct'],
                                    'yoy_pct': macro_data[ind]['yoy_pct'],
                                    'date': macro_data[ind]['date']}

    head = macro_data.get('CPIAUCSL', {})
    core = macro_data.get('CPILFESL', {})
    pce = macro_data.get('PCEPILFE', {})
    p['headline_yoy'] = head.get('yoy_pct')
    p['core_cpi_yoy'] = core.get('yoy_pct')
    p['core_pce_yoy'] = pce.get('yoy_pct')

    # Three gauges, three tiers. Core PCE is the Fed's target measure and ran
    # ABOVE core CPI in this batch (3.29 vs 2.81), so picking one silently would
    # change the regime. Publish all and take the most cautious.
    p['tiers'] = {'headline_cpi': _tier(p['headline_yoy']),
                  'core_cpi': _tier(p['core_cpi_yoy']),
                  'core_pce': _tier(p['core_pce_yoy'])}
    rank = {'LOW': 0, 'MODERATE': 1, 'HIGH': 2}
    live = {k: v for k, v in p['tiers'].items() if v}
    if live:
        basis = max(live, key=lambda k: rank[live[k]])
        p['level'], p['level_basis'] = live[basis], basis
        p['level_selection'] = 'most cautious of headline CPI / core CPI / core PCE'

    moms = [v['mom_pct'] for v in p['components'].values() if v['mom_pct'] is not None]
    if moms:
        avg = sum(moms) / len(moms)
        p['mom_avg'] = round(avg, 4)
        p['trend'] = 'RISING' if avg > 0.15 else 'FALLING' if avg < -0.15 else 'STABLE'

    if p['level'] != 'UNKNOWN' and p['trend'] != 'UNKNOWN':
        p['regime'] = f"{p['level']}_{p['trend']}"

    hm, cm = head.get('change_pct'), core.get('change_pct')
    if hm is not None and cm is not None and abs(hm - cm) > 0.15:
        p['energy_driven_flag'] = True
        p['energy_divergence_pp'] = round(hm - cm, 3)

    ff = macro_data.get('FEDFUNDS', {}).get('value')
    gauge = p['core_pce_yoy'] if p['core_pce_yoy'] is not None else p['core_cpi_yoy']
    if ff is not None and gauge is not None:
        p['real_fed_funds'] = round(ff - gauge, 3)
        p['real_fed_funds_basis'] = 'core_pce' if p['core_pce_yoy'] is not None else 'core_cpi'
    return p


def calculate_economic_momentum(macro_data):
    m = {'score': 0.5, 'direction': 'STABLE', 'strength': 'MODERATE', 'signals': []}
    sigs = []
    pay = macro_data.get('PAYEMS')
    if pay and pay.get('abs_change') is not None:
        k = pay['abs_change']
        m['payrolls_change_k'] = k
        sigs.append(1 if k > 100 else -1 if k < 0 else 0)
        m['signals'].append(f'Payrolls {k:+.0f}k — '
                            f'{"expanding" if k > 100 else "CONTRACTING" if k < 0 else "soft"}')
    for ind, thr, label in [('INDPRO', 0.3, 'Industrial production'),
                            ('RSXFS', 0.5, 'Retail sales')]:
        c = macro_data.get(ind, {}).get('change_pct')
        if c is not None:
            sigs.append(1 if c > thr else -1 if c < -thr else 0)
            if abs(c) > thr:
                m['signals'].append(f'{label} {"expanding" if c > 0 else "contracting"}')
    um = macro_data.get('UMCSENT')
    if um and um.get('change_pct') is not None:
        lvl, c = um['value'], um['change_pct']
        tier = 'DEPRESSED' if lvl < 60 else 'SOFT' if lvl < 80 else 'HEALTHY'
        m.update({'sentiment_level': lvl, 'sentiment_tier': tier})
        sigs.append(1 if c > 2 else -1 if c < -2 else 0)
        m['signals'].append(f'Consumer sentiment {lvl:.1f} [{tier}], {c:+.1f}% m/m')
    c = macro_data.get('ICSA', {}).get('change_pct')
    if c is not None:
        sigs.append(1 if c < -2 else -1 if c > 2 else 0)
    if sigs:
        avg = sum(sigs) / len(sigs)
        m['score'] = (avg + 1) / 2
        m['direction'] = 'EXPANDING' if avg > 0.3 else 'CONTRACTING' if avg < -0.3 else 'STABLE'
        m['strength'] = 'STRONG' if abs(avg) > 0.6 else 'MODERATE'
    return m


def calculate_market_regime(macro_data, inflation):
    r = {'growth': 'UNKNOWN', 'inflation': inflation.get('regime', 'UNKNOWN'),
         'policy': 'UNKNOWN', 'overall': 'UNKNOWN', 'confidence': 0.5}
    cf = []
    u = macro_data.get('UNRATE', {}).get('value')
    if u is not None:
        for thr, lbl, c in [(4.0, 'STRONG', 0.9), (5.0, 'MODERATE', 0.7),
                            (6.5, 'WEAK', 0.7), (999, 'CONTRACTION', 0.9)]:
            if u < thr:
                r['growth'] = lbl; cf.append(c); break
    rfr = inflation.get('real_fed_funds')
    if rfr is not None:
        for thr, lbl, c in [(-1.0, 'VERY_EASY', 0.9), (0.0, 'EASY', 0.8),
                            (1.5, 'NEUTRAL', 0.7), (3.0, 'TIGHT', 0.8),
                            (999, 'VERY_TIGHT', 0.9)]:
            if rfr < thr:
                r['policy'] = lbl; cf.append(c); break
        r['real_fed_funds'] = rfr
        r['real_fed_funds_basis'] = inflation.get('real_fed_funds_basis')
    g, p, i = r['growth'], r['policy'], r['inflation']
    if g == 'STRONG' and p in ('NEUTRAL', 'EASY') and i.startswith('LOW'):
        r['overall'] = 'GOLDILOCKS'
    elif g in ('WEAK', 'CONTRACTION') and p in ('EASY', 'VERY_EASY'):
        r['overall'] = 'RECOVERY'
    elif g == 'STRONG' and i.startswith('HIGH'):
        r['overall'] = 'OVERHEATING'
    elif g in ('WEAK', 'CONTRACTION') and p in ('TIGHT', 'VERY_TIGHT'):
        r['overall'] = 'STAGFLATION_RISK'
    else:
        r['overall'] = 'TRANSITIONAL'
    r['confidence'] = sum(cf) / len(cf) if cf else 0.5
    return r


# ============================================================================
# V-04 — YIELD CURVE with explicit vintages
# ============================================================================

def _fred_chg(macro_data, sid, n):
    h = macro_data.get(sid, {}).get('history') or []
    return round(h[0][1] - h[n][1], 4) if len(h) > n else None


def analyze_yield_curve(macro_data):
    """
    v5.4 reported slope_2s10s 0.46 (T10Y2Y, 7 Aug) beside yield_10y 4.69 and
    yield_2y 4.25 (DGS, 6 Aug) — which differ by 0.44. The output contradicted
    itself, and curve_move ran off the DGS series alone so it missed Friday.
    Both slopes are now reported with their own as_of and the skew is measured.
    """
    a = {'yield_2y': None, 'yield_10y': None, 'yield_30y': None,
         'slope_2s10s_derived': None, 'slope_2s10s_published': None,
         'slope_2s10s': None, 'slope_source': None, 'slope_as_of': None,
         'slope_vintage_skew_days': None, 'slope_consistent': None,
         'slope_3m10s': None, 'slope_10s30s': None,
         'inverted': False, 'signal': 'NEUTRAL', 'recession_probability': 0.0,
         'curve_move_1d': 'UNKNOWN', 'curve_move_5d': 'UNKNOWN',
         'dgs_as_of': None, 'published_as_of': None}

    for key, sid in (('yield_2y', 'DGS2'), ('yield_10y', 'DGS10'), ('yield_30y', 'DGS30')):
        a[key] = macro_data.get(sid, {}).get('value')
    a['dgs_as_of'] = macro_data.get('DGS10', {}).get('date')
    a['published_as_of'] = macro_data.get('T10Y2Y', {}).get('date')

    if a['yield_10y'] is not None and a['yield_2y'] is not None:
        a['slope_2s10s_derived'] = round(a['yield_10y'] - a['yield_2y'], 3)
    a['slope_2s10s_published'] = macro_data.get('T10Y2Y', {}).get('value')

    d, pub = a['slope_2s10s_derived'], a['slope_2s10s_published']
    if pub is not None and a['published_as_of'] and a['dgs_as_of']:
        skew = _days_between(a['published_as_of'], a['dgs_as_of'])
        a['slope_vintage_skew_days'] = skew
        a['slope_consistent'] = (d is not None and abs(d - pub) < 0.005)
        if skew > 0 and not a['slope_consistent']:
            COLLECTION_ERRORS.append(
                f"Curve vintage skew: T10Y2Y {pub} @{a['published_as_of']} vs "
                f"DGS-derived {d} @{a['dgs_as_of']} ({skew}d apart)")
    # Prefer the fresher published series, but say so.
    if pub is not None:
        a['slope_2s10s'], a['slope_source'], a['slope_as_of'] = pub, 'T10Y2Y', a['published_as_of']
    elif d is not None:
        a['slope_2s10s'], a['slope_source'], a['slope_as_of'] = d, 'DGS10-DGS2', a['dgs_as_of']

    a['slope_3m10s'] = macro_data.get('T10Y3M', {}).get('value')
    if a['yield_30y'] and a['yield_10y']:
        a['slope_10s30s'] = round(a['yield_30y'] - a['yield_10y'], 3)

    s = a['slope_2s10s']
    if s is not None:
        for thr, inv, sig, prob in [(-0.5, True, 'SEVERE_INVERSION', 0.75),
                                    (0.0, True, 'RECESSION_WARNING', 0.50),
                                    (0.25, False, 'FLATTENING', 0.25),
                                    (1.5, False, 'NORMAL', 0.10),
                                    (999, False, 'STEEPENING', 0.05)]:
            if s < thr:
                a['inverted'], a['signal'], a['recession_probability'] = inv, sig, prob
                break

    for label, n in (('curve_move_1d', 1), ('curve_move_5d', 5)):
        d2, d10 = _fred_chg(macro_data, 'DGS2', n), _fred_chg(macro_data, 'DGS10', n)
        if d2 is None or d10 is None:
            continue
        if d2 < 0 and d10 < 0:
            a[label] = 'BULL_STEEPENING' if abs(d2) > abs(d10) else 'BULL_FLATTENING'
        elif d2 > 0 and d10 > 0:
            a[label] = 'BEAR_FLATTENING' if abs(d2) > abs(d10) else 'BEAR_STEEPENING'
        else:
            a[label] = 'TWIST'
        a[f'{label}_detail'] = {'d2y_bp': round(d2 * 100, 1), 'd10y_bp': round(d10 * 100, 1),
                                'as_of': a['dgs_as_of']}
    return a


def calculate_liquidity_conditions(macro_data):
    liq = {'level': 'MODERATE', 'trend': 'STABLE', 'signals': []}
    c = macro_data.get('WALCL', {}).get('change_pct')
    if c is not None:
        liq['walcl_change_pct'] = round(c, 4)
        liq['signals'].append(f'Fed balance sheet '
                              f'{"expanding" if c > 0.5 else "contracting (QT)" if c < -0.5 else "flat"} ({c:+.2f}%)')
    rrp = macro_data.get('RRPONTSYD', {}).get('value')
    if rrp is not None:
        liq['rrp_usd_bn'] = rrp
        liq['rrp_exhausted'] = rrp < 50
        if liq['rrp_exhausted']:
            liq['signals'].append(f'RRP exhausted (${rrp:,.1f}bn) — settlement drains reserves directly')
    res = macro_data.get('WRESBAL', {}).get('value')
    if res is not None:
        liq['reserves_usd_mn'] = res
    c = macro_data.get('M2SL', {}).get('change_pct')
    if c is not None:
        if c > 1.0:
            liq.update({'trend': 'EXPANDING', 'level': 'HIGH'})
        elif c < -1.0:
            liq.update({'trend': 'CONTRACTING', 'level': 'LOW'})
    m1, m2 = macro_data.get('M1SL', {}).get('value'), macro_data.get('M2SL', {}).get('value')
    if m1 and m2:
        liq['m1_m2_velocity_ratio'] = round(m1 / m2, 4)
    c = macro_data.get('WTREGEN', {}).get('change_pct')
    if c is not None:
        if c < -5:
            liq['signals'].append('TGA draining -> net liquidity injection')
        elif c > 5:
            liq['signals'].append('TGA building -> absorbing liquidity')
    sofr, ff = macro_data.get('SOFR', {}).get('value'), macro_data.get('FEDFUNDS', {}).get('value')
    if sofr is not None and ff is not None:
        sp = round(sofr - ff, 4)
        liq['sofr_ff_spread'] = sp
        liq['signals'].append(f'SOFR-FF spread {sp:+.3f}% — '
                              f'{"funding stress elevated" if abs(sp) > 0.10 else "overnight funding stable"}')
    return liq


# ============================================================================
# get_val  (C-01)
# ============================================================================

def get_val(market_data, category_hints, name_hint=None, ticker=None):
    hints = category_hints if isinstance(category_hints, list) else [category_hints]
    for cat_hint in hints:
        for cat, df in market_data.items():
            if cat_hint.lower() not in cat.lower():
                continue
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            if ticker is not None and 'ticker' in df.columns:
                rows = df[df['ticker'].astype(str).str.upper() == ticker.upper()]
            elif name_hint is not None and 'name' in df.columns:
                rows = df[df['name'].str.contains(name_hint, case=False, na=False)]
            else:
                continue
            for _, cand in rows.iterrows():
                if cand.get('current_price') is not None:
                    return cand
    return None


def analyze_risk_signals(market_data):
    signals = {k: 'NEUTRAL' for k in
               ('gold_signal', 'credit_signal', 'treasury_signal', 'vix_signal',
                'dollar_signal', 'copper_signal', 'crude_signal')}
    signals.update({'risk_off_count': 0, 'risk_on_count': 0})

    def chk(cats, hi, lo, hi_lbl, lo_lbl, key, ticker):
        row = get_val(market_data, cats, ticker=ticker)
        if row is None or row.get('daily_pct') is None or pd.isna(row['daily_pct']):
            signals[key] = 'MISSING'
            return
        d = row['daily_pct']
        if d > hi:
            signals[key] = hi_lbl
            signals['risk_off_count' if any(x in hi_lbl for x in
                    ('OFF', 'FEAR', 'STRESS', 'NEG')) else 'risk_on_count'] += 1
        elif d < lo:
            signals[key] = lo_lbl
            signals['risk_on_count' if any(x in lo_lbl for x in
                    ('ON', 'HEALTHY', 'POS')) else 'risk_off_count'] += 1

    chk(['Metals_ETF'], 1.0, -1.0, 'RISK_OFF', 'RISK_ON', 'gold_signal', 'GLD')
    chk(['Bonds_ETF'], -0.5, -999, 'NEUTRAL', 'STRESS', 'credit_signal', 'HYG')
    chk(['Bonds_ETF'], 0.5, -0.5, 'FLIGHT_SAFETY', 'RISK_ON', 'treasury_signal', 'TLT')
    chk(['Vol_Complex'], 5.0, -5.0, 'FEAR_SPIKE', 'COMPLACENCY', 'vix_signal', 'VIX')
    chk(['Vol_Dollar'], 0.5, -0.5, 'STRENGTH', 'WEAKNESS', 'dollar_signal', 'UUP')
    chk(['Metals_ETF'], 1.5, -1.5, 'GROWTH_POS', 'GROWTH_NEG', 'copper_signal', 'CPER')
    chk(['Energy_ETF'], 2.0, -2.0, 'DEMAND_STR', 'DEMAND_WEAK', 'crude_signal', 'USO')
    return signals


def calculate_risk_score(market_data, macro_regime, yield_curve, risk_signals, liquidity):
    mkt = 0.5
    for cat, df in market_data.items():
        if 'Sector' in cat and isinstance(df, pd.DataFrame) and 'daily_pct' in df:
            valid = df['daily_pct'].dropna()
            if len(valid):
                mkt = (valid > 0).sum() / len(valid)
            break
    macro = {'GOLDILOCKS': 0.9, 'RECOVERY': 0.7, 'OVERHEATING': 0.4,
             'STAGFLATION_RISK': 0.2, 'TRANSITIONAL': 0.5}.get(macro_regime['overall'], 0.5)
    curve = 1.0 - yield_curve['recession_probability']
    tot = risk_signals['risk_off_count'] + risk_signals['risk_on_count']
    sig = (risk_signals['risk_on_count'] / tot) if tot else 0.5
    liq = {'HIGH': 0.8, 'MODERATE': 0.6, 'LOW': 0.3}.get(liquidity['level'], 0.5)
    combined = mkt * .25 + macro * .25 + curve * .15 + sig * .20 + liq * .15
    return {'market_favourability': round(mkt, 4), 'macro_favourability': round(macro, 4),
            'curve_favourability': round(curve, 4), 'signal_favourability': round(sig, 4),
            'liquidity_favourability': round(liq, 4), 'combined_score': round(combined, 4),
            'polarity_note': 'higher = more favourable, not more risky',
            'recommendation': 'RISK_ON' if combined > 0.7 else 'RISK_OFF' if combined < 0.4 else 'NEUTRAL',
            'confidence': 'HIGH' if abs(combined - 0.55) > 0.25 else 'MODERATE'}


# ============================================================================
# V-01 / V-02 — VIX TERM STRUCTURE with vintage and reconciliation guards
# ============================================================================

def calculate_vix_term_structure(market_data, macro_data):
    out = {'regime': 'UNKNOWN', 'signal': 'NEUTRAL', 'vix_spot': None,
           'vix9d': None, 'vix3m': None, 'vvix': None,
           'contango_ratio': None, 'contango_pts': None,
           'front_end_slope': None, 'front_end_inverted': None,
           'source': 'NONE', 'obs_date': None, 'leg_sources': {}, 'leg_dates': {},
           'term_vintage_skew_days': None, 'mixed_source': None,
           'vix_pct_rank_1y': None, 'vix9d_pct_rank_1y': None,
           'reconcile_pct': None, 'reconcile_status': 'NOT_RUN'}

    legs = {}
    for t in ('VIX', 'VIX9D', 'VIX3M', 'VVIX'):
        r = get_val(market_data, ['Vol_Complex'], ticker=t)
        legs[t] = r
        if r is not None:
            out['leg_sources'][t] = r.get('source')
            out['leg_dates'][t] = r.get('obs_date')

    def val(t):
        return legs[t]['current_price'] if legs[t] is not None else None

    spot, v9, v3, vv = val('VIX'), val('VIX9D'), val('VIX3M'), val('VVIX')
    out.update({'vix_spot': spot, 'vix9d': v9, 'vix3m': v3, 'vvix': vv,
                'obs_date': out['leg_dates'].get('VIX')})
    out['source'] = out['leg_sources'].get('VIX', 'NONE')
    srcs = {s for s in out['leg_sources'].values() if s}
    out['mixed_source'] = len(srcs) > 1

    # ---- Percentile context ----------------------------------------------
    # Where the current level sits in its own trailing 252 observations.
    # A fact, not a judgement: this module does not know what is in the
    # calendar this week, so it does not adjust any score on the back of it.
    # Computed BEFORE the vintage guard so the percentile survives even when
    # the term structure itself is rejected.
    for key, tk in (('vix_pct_rank_1y', 'VIX'), ('vix9d_pct_rank_1y', 'VIX9D')):
        row = legs.get(tk)
        if row is not None and row.get('closes') and row.get('current_price') is not None:
            s = pd.Series(row['closes'][-252:], dtype='float64').dropna()
            if len(s) >= 30:
                out[key] = round(float((s < row['current_price']).mean() * 100), 1)

    # ---- V-02: reconcile on the last SHARED date -------------------------
    fred_v = macro_data.get('VIXCLS', {}).get('value')
    fred_d = macro_data.get('VIXCLS', {}).get('date')
    vix_row = legs['VIX']
    if fred_v and vix_row is not None and vix_row.get('dates'):
        dts, cls = list(vix_row['dates']), list(vix_row['closes'])
        if fred_d in dts:
            yv = cls[dts.index(fred_d)]
            diff = abs(yv - fred_v) / fred_v * 100
            out.update({'reconcile_pct': round(diff, 3),
                        'reconcile_date': fred_d,
                        'reconcile_source_value': round(yv, 4),
                        'fred_vixcls': fred_v, 'fred_vixcls_date': fred_d,
                        'reconcile_status': 'MATCH' if diff <= VIX_RECONCILE_TOLERANCE_PCT
                        else f'DIVERGENT_{diff:.1f}PCT'})
        else:
            out.update({'reconcile_status': 'NO_OVERLAP', 'fred_vixcls': fred_v,
                        'fred_vixcls_date': fred_d})

    if spot is None and fred_v:
        spot = fred_v
        out.update({'vix_spot': spot, 'source': 'FRED_VIXCLS_LAGGED', 'obs_date': fred_d})
    if spot is None:
        out['note'] = 'no VIX from any source'
        return out

    if v3 is None or v9 is None:
        out.update({'regime': 'UNKNOWN', 'signal': 'TERM_STRUCTURE_UNAVAILABLE',
                    'note': 'VIX9D/VIX3M unavailable — regime NOT inferred'})
        return out

    # ---- V-01: vintage guard ---------------------------------------------
    # The 11:07 run computed a 1.3785 contango ratio from a 7 August spot and a
    # 17 July 9D/3M. Populated is not the same as current.
    base_d = out['leg_dates'].get('VIX')
    skew = max(_days_between(base_d, out['leg_dates'].get('VIX9D')),
               _days_between(base_d, out['leg_dates'].get('VIX3M'))) if base_d else 999
    out['term_vintage_skew_days'] = skew
    if skew > TERM_MAX_VINTAGE_SKEW_DAYS:
        out.update({
            'regime': 'UNKNOWN', 'signal': 'TERM_STRUCTURE_STALE',
            'note': (f"VIX {base_d} vs 9D {out['leg_dates'].get('VIX9D')} / "
                     f"3M {out['leg_dates'].get('VIX3M')} — {skew}d apart. "
                     f"Term structure NOT computed across mixed vintages.")})
        COLLECTION_ERRORS.append(
            f"VIX term structure rejected: {skew}d vintage skew "
            f"(spot {base_d}, 9D {out['leg_dates'].get('VIX9D')}, "
            f"3M {out['leg_dates'].get('VIX3M')})")
        return out

    out['contango_ratio'] = round(v3 / spot, 4)
    out['contango_pts'] = round(v3 - spot, 3)
    out['front_end_slope'] = round(v9 - spot, 3)
    out['front_end_inverted'] = v9 > spot

    ratio = out['contango_ratio']
    if ratio > 1.25:
        regime, signal = 'STEEP_CONTANGO', 'CALM_LOW_VOL'
    elif ratio > 1.10:
        regime, signal = 'CONTANGO', 'NORMAL_MARKET'
    elif ratio > 0.95:
        regime, signal = 'FLAT', 'ELEVATED_CAUTION'
    else:
        regime, signal = 'BACKWARDATION', 'HIGH_STRESS'
    if out['front_end_inverted']:
        regime += '_FRONT_END_HUMP'
        signal = 'EVENT_PREMIUM_PRICED'
    out['regime'], out['signal'] = regime, signal
    return out


# ============================================================================
# FORWARD BIAS ENGINE
# ============================================================================

class ForwardBiasEngine:
    EQUITY_TARGETS = [('Equity_ETF', 'SPY'), ('Equity_ETF', 'QQQ')]

    def __init__(self, market_data, macro_data, vix_ts):
        self.md, self.mac, self.vts = market_data, macro_data, vix_ts

    def _closes(self, cat, ticker):
        row = get_val(self.md, [cat], ticker=ticker)
        if row is None:
            return []
        v = row.get('closes', [])
        return v if isinstance(v, list) else []

    def layer_tech_momentum(self):
        scores = []
        for cat, tk in self.EQUITY_TARGETS:
            closes = self._closes(cat, tk)
            if not closes:
                continue
            rsi = calculate_rsi(closes)
            if rsi is None:
                continue
            bb = calculate_bollinger_position(closes)
            r5, r10, r20 = (calculate_momentum(closes, n) for n in (5, 10, 20))
            score = (((rsi - 50) / 50) * .15 + ((bb - 0.5) * 2 if bb else 0) * .15
                     + np.tanh((r5 or 0) / 2) * .35 + np.tanh((r10 or 0) / 3) * .20
                     + np.tanh((r20 or 0) / 5) * .15)
            scores.append({'ticker': tk, 'rsi': rsi, 'bb': bb, 'roc5': r5,
                           'roc10': r10, 'roc20': r20, 'score': round(score, 4)})
        avg = float(np.mean([s['score'] for s in scores])) if scores else 0.0
        return {'layer': 'Technical_Momentum', 'score': round(avg, 4),
                'inputs_used': len(scores),
                'direction': 'BULLISH' if avg > 0.1 else 'BEARISH' if avg < -0.1 else 'NEUTRAL',
                'details': scores, 'weight': 0.25}

    def layer_vix_term(self):
        regime = self.vts.get('regime', 'UNKNOWN')
        base = regime.replace('_FRONT_END_HUMP', '')
        score = {'STEEP_CONTANGO': .6, 'CONTANGO': .3, 'FLAT': -.3,
                 'BACKWARDATION': -.6, 'UNKNOWN': 0.0}.get(base, 0.0)
        if self.vts.get('front_end_inverted'):
            score = min(score, 0.0)
        # V-06: report how many legs actually contributed.
        n = sum(1 for k in ('vix_spot', 'vix9d', 'vix3m')
                if self.vts.get(k) is not None) if regime != 'UNKNOWN' else 0
        return {'layer': 'VIX_Term_Structure', 'regime': regime,
                'vix_spot': self.vts.get('vix_spot'), 'vix9d': self.vts.get('vix9d'),
                'vix3m': self.vts.get('vix3m'),
                'contango_ratio': self.vts.get('contango_ratio'),
                'front_end_inverted': self.vts.get('front_end_inverted'),
                'vintage_skew_days': self.vts.get('term_vintage_skew_days'),
                'score': score, 'inputs_used': n,
                'direction': 'BULLISH' if score > 0 else 'BEARISH' if score < 0 else 'NEUTRAL',
                'weight': 0.15}

    def layer_cross_asset(self):
        series = {}
        for key, cat, tk in [('spy', 'Equity_ETF', 'SPY'), ('gold', 'Metals_ETF', 'GLD'),
                             ('tlt', 'Bonds_ETF', 'TLT'), ('dollar', 'Vol_Dollar', 'UUP')]:
            c = self._closes(cat, tk)
            if len(c) >= 20:
                series[key] = np.array(c[-20:])
        if len(series) < 2:
            return {'layer': 'Cross_Asset_Regime', 'score': 0.0, 'inputs_used': len(series),
                    'direction': 'NEUTRAL', 'weight': 0.15}

        def ret(a):
            return np.diff(a) / a[:-1]

        scores = []
        if 'spy' in series and 'gold' in series:
            rs, rg = ret(series['spy']), ret(series['gold'])
            if len(rs) == len(rg) > 3:
                corr, up = np.corrcoef(rs, rg)[0, 1], np.mean(rs[-5:]) > 0
                scores.append(.4 if (up and corr < 0) else -.3 if (not up and corr < 0) else 0.0)
        if 'spy' in series and 'tlt' in series:
            rs, rt = ret(series['spy']), ret(series['tlt'])
            if len(rs) == len(rt) > 3:
                eq_up, tlt_up = np.mean(rs[-5:]) > 0, np.mean(rt[-5:]) > 0
                scores.append(.5 if (eq_up and not tlt_up) else -.5 if (not eq_up and tlt_up) else 0.0)
        avg = float(np.mean(scores)) if scores else 0.0
        return {'layer': 'Cross_Asset_Regime', 'score': round(avg, 4),
                'inputs_used': len(series),
                'direction': 'RISK_ON' if avg > 0.1 else 'RISK_OFF' if avg < -0.1 else 'NEUTRAL',
                'weight': 0.15}

    def layer_vol_regime(self):
        s = safe_series(self._closes('Equity_ETF', 'SPY'))
        if len(s) < 25:
            return {'layer': 'Volatility_Regime', 'score': 0.0, 'inputs_used': 0,
                    'direction': 'NEUTRAL', 'weight': 0.10}
        rets = np.diff(s) / s[:-1]
        rv5 = np.std(rets[-5:], ddof=1) * np.sqrt(252) * 100
        rv20 = np.std(rets[-20:], ddof=1) * np.sqrt(252) * 100
        ratio = rv5 / rv20 if rv20 > 0 else 1.0
        vix = self.vts.get('vix_spot')
        if vix is None:
            return {'layer': 'Volatility_Regime', 'score': 0.0, 'inputs_used': 1,
                    'rv5': round(rv5, 2), 'rv20': round(rv20, 2),
                    'direction': 'NEUTRAL', 'note': 'VIX unavailable', 'weight': 0.10}
        score = (.4 if (ratio < 0.8 and vix < 20) else -.5 if (ratio > 1.5 or vix > 30)
                 else -.3 if vix > 25 else 0.0)
        if self.vts.get('front_end_inverted'):
            score = min(score, 0.0)
        return {'layer': 'Volatility_Regime', 'rv5': round(rv5, 2), 'rv20': round(rv20, 2),
                'ratio': round(ratio, 3), 'vix': vix, 'score': round(score, 4),
                'inputs_used': 2,
                'direction': 'BULLISH' if score > 0 else 'BEARISH' if score < 0 else 'NEUTRAL',
                'weight': 0.10}

    def layer_mean_reversion(self):
        results, sigs = {}, []
        for cat, tk in self.EQUITY_TARGETS:
            closes = self._closes(cat, tk)
            if not closes:
                continue
            rsi, bb = calculate_rsi(closes), calculate_bollinger_position(closes)
            if rsi is None:
                continue
            if rsi > 70 and bb and bb > 0.85:
                sigs.append(-.6); results[tk] = 'OVERBOUGHT_REVERSION'
            elif rsi < 30 and bb and bb < 0.15:
                sigs.append(.6); results[tk] = 'OVERSOLD_BOUNCE'
            elif rsi > 65:
                sigs.append(-.3); results[tk] = 'MILDLY_OVERBOUGHT'
            elif rsi < 35:
                sigs.append(.3); results[tk] = 'MILDLY_OVERSOLD'
            else:
                sigs.append(0.0); results[tk] = 'NEUTRAL'
        avg = float(np.mean(sigs)) if sigs else 0.0
        return {'layer': 'Mean_Reversion', 'score': round(avg, 4), 'inputs_used': len(sigs),
                'direction': 'BULLISH' if avg > 0 else 'BEARISH' if avg < 0 else 'NEUTRAL',
                'details': results, 'weight': 0.15}

    def layer_trend_persistence(self):
        scores = []
        for cat, tk in self.EQUITY_TARGETS:
            row = get_val(self.md, [cat], ticker=tk)
            if row is None:
                continue
            adx = calculate_adx_proxy(row.get('closes', []), row.get('highs', []), row.get('lows', []))
            if adx is None:
                continue
            up = (calculate_momentum(row.get('closes', []), 20) or 0) > 0
            if adx > 35:
                scores.append(.7 if up else -.7)
            elif adx > 25:
                scores.append(.4 if up else -.4)
            elif adx < 20:
                scores.append(0.0)
            else:
                scores.append(.1 if up else -.1)
        avg = float(np.mean(scores)) if scores else 0.0
        return {'layer': 'Trend_Persistence', 'score': round(avg, 4), 'inputs_used': len(scores),
                'direction': ('TRENDING_BULLISH' if avg > 0.3 else
                              'TRENDING_BEARISH' if avg < -0.3 else 'CONSOLIDATING'),
                'weight': 0.10}

    def layer_macro_pulse(self):
        mac, sigs, used = self.mac, [], []
        u = mac.get('USSLIND')
        if u and u.get('change_pct') is not None:
            if (u.get('age_days') or 999) > USSLIND_MAX_AGE_DAYS:
                COLLECTION_ERRORS.append(
                    f"USSLIND quarantined: observation {u['date']} is {u.get('age_days')} days old")
            else:
                c = u['change_pct']
                sigs.append(.6 if c > .3 else -.6 if c < -.3 else .1); used.append('USSLIND')
        p = mac.get('PAYEMS')
        if p and p.get('abs_change') is not None:
            k = p['abs_change']
            sigs.append(.5 if k > 150 else .2 if k > 50 else -.5 if k < 0 else 0.0)
            used.append('PAYEMS')
        c = mac.get('ICSA', {}).get('change_pct')
        if c is not None:
            sigs.append(-.4 if c > 5 else .4 if c < -5 else 0.0); used.append('ICSA')
        um = mac.get('UMCSENT')
        if um and um.get('change_pct') is not None:
            lvl, c = um['value'], um['change_pct']
            base = .3 if c > 2 else -.3 if c < -2 else 0.0
            if lvl < 60:
                base = min(base, 0.0)
            sigs.append(base); used.append('UMCSENT')
        s = mac.get('T10Y2Y', {}).get('value')
        if s is not None:
            sigs.append(.4 if s > .5 else -.5 if s < -.25 else 0.0); used.append('T10Y2Y')
        c = mac.get('WALCL', {}).get('change_pct')
        if c is not None:
            sigs.append(.3 if c > .5 else -.3 if c < -.5 else 0.0); used.append('WALCL')
        avg = float(np.mean(sigs)) if sigs else 0.0
        return {'layer': 'Macro_Pulse', 'score': round(avg, 4), 'inputs_used': len(sigs),
                'inputs': used,
                'direction': 'POSITIVE' if avg > 0.2 else 'NEGATIVE' if avg < -0.2 else 'NEUTRAL',
                'weight': 0.10}

    def compute(self):
        print("\n" + "-" * 70)
        print("FORWARD BIAS ENGINE (1-20 day)")
        print("-" * 70)
        layers = {}
        for fn, key in [(self.layer_tech_momentum, 'tech'), (self.layer_vix_term, 'vix_term'),
                        (self.layer_cross_asset, 'cross_asset'), (self.layer_vol_regime, 'vol_regime'),
                        (self.layer_mean_reversion, 'mean_rev'),
                        (self.layer_trend_persistence, 'trend'), (self.layer_macro_pulse, 'macro')]:
            layers[key] = fn()
        live = sum(1 for l in layers.values() if l.get('inputs_used', 0) > 0)
        coverage = round(live / len(layers), 3)
        print(f"  layers with live inputs: {live}/{len(layers)}  (coverage {coverage:.0%})")
        if coverage < 0.7:
            COLLECTION_ERRORS.append(f"Forward bias coverage {coverage:.0%} — below 70%")

        short_w = {'tech': .35, 'vix_term': .20, 'mean_rev': .25, 'vol_regime': .15, 'cross_asset': .05}
        med_w = {'tech': .20, 'vix_term': .15, 'cross_asset': .20, 'vol_regime': .15, 'trend': .15, 'macro': .15}
        long_w = {'trend': .25, 'macro': .30, 'cross_asset': .20, 'vix_term': .10, 'vol_regime': .15}

        def wscore(w):
            t = sum(w.values())
            return sum(layers[k]['score'] * v for k, v in w.items() if k in layers) / t if t else 0.0

        def to_bias(s):
            p = (s + 1) / 2 * 100
            d = ('BULLISH' if p > 65 else 'MILDLY_BULLISH' if p > 55 else
                 'BEARISH' if p < 35 else 'MILDLY_BEARISH' if p < 45 else 'NEUTRAL')
            return d, round(p, 1)

        out = {'layers': layers, 'layer_coverage': coverage, 'horizons': {}}
        for key, w, drv in [('short_1_5d', short_w, ['tech', 'mean_rev', 'vix_term']),
                            ('medium_6_10d', med_w, ['cross_asset', 'vol_regime', 'trend']),
                            ('long_11_20d', long_w, ['macro', 'trend', 'cross_asset'])]:
            s = wscore(w)
            d, p = to_bias(s)
            out['horizons'][key] = {'score': round(s, 4), 'direction': d,
                                    'bullish_prob_pct': p, 'drivers': drv,
                                    'layer_coverage': coverage}
        return out


# ============================================================================
# VALIDATION + V-05 DIRECTORY HYGIENE
# ============================================================================

class CollectionFailed(Exception):
    pass


_OWN_OUTPUT = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in OUTPUT_PREFIXES) + r")\d{8}_\d{6}\.(?:csv|json|txt)$")


def purge_prior_runs(output_dir, current_ts):
    """
    V-05: us_indices_cash_20260809_100152.csv — 100% NaN, from the pre-fix run —
    was still in the folder beside the 11:07 outputs. Downstream globs
    (forward_bias_*.csv etc.) would pick up whichever sorted first.

    v5.4.3: in the shared dropbox\\market_data folder a bare prefix match also hit other
    producers' files (macro_series_threshold_flags.csv, macro_module_contract.json, ...).
    Only this module's own <prefix>YYYYMMDD_HHMMSS outputs are touched, and they are MOVED to
    archive\\ (point-in-time history kept), never deleted.
    """
    moved = []
    archive = os.path.join(output_dir, "archive")
    for f in os.listdir(output_dir):
        if _OWN_OUTPUT.match(f) and current_ts not in f:
            try:
                os.makedirs(archive, exist_ok=True)
                os.replace(os.path.join(output_dir, f), os.path.join(archive, f))
                moved.append(f)
            except OSError:
                pass
    if moved:
        print(f"\n  Archived {len(moved)} file(s) from prior runs to archive/ "
              f"(e.g. {moved[0]})")
    return moved


def validate_collection(market_data):
    rows, failed = [], []
    for cat, df in market_data.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            rows.append({'category': cat, 'total': 0, 'populated': 0, 'stale': 0,
                         'null_rate': 1.0, 'status': 'FAILED'})
            failed.append(cat)
            continue
        total = len(df)
        pop = int(df['current_price'].notna().sum()) if 'current_price' in df else 0
        stale = int((df['data_flag'] == 'STALE').sum()) if 'data_flag' in df else 0
        nr = round(1 - pop / total, 3) if total else 1.0
        status = ('FAILED' if nr > MAX_NULL_RATE else
                  'STALE' if stale else 'DEGRADED' if nr > 0 else 'OK')
        if status == 'FAILED':
            failed.append(cat)
        rows.append({'category': cat, 'total': total, 'populated': pop, 'stale': stale,
                     'null_rate': nr, 'status': status})
    print("\n" + "=" * 70)
    print("COLLECTION VALIDATION")
    print("=" * 70)
    for r in rows:
        extra = f"  {r['stale']} STALE" if r['stale'] else ""
        print(f"  {r['status']:9s} {r['category']:18s} {r['populated']:>3d}/{r['total']:<3d} "
              f"null_rate {r['null_rate']:.0%}{extra}")
    return rows, failed


# ============================================================================
# DISPLAY
# ============================================================================

def print_report(risk, regime, inflation, momentum, liquidity, curve, signals, vts, fb):
    print("\n" + "=" * 70)
    print("AVSHUNTER INTELLIGENCE REPORT v5.4.3")
    print("=" * 70)
    print(f"\n  RECOMMENDATION : {risk['recommendation']} ({risk['confidence']})")
    print(f"  Combined score : {risk['combined_score']:.1%}  [{risk['polarity_note']}]")

    print(f"\n  MACRO REGIME   : {regime['overall']} (conf {regime['confidence']:.0%})")
    print(f"    Growth       : {regime['growth']}")
    print(f"    Inflation    : {regime['inflation']}")
    pol = f"    Policy       : {regime['policy']}"
    if regime.get('real_fed_funds') is not None:
        pol += f"  (real FF {regime['real_fed_funds']:+.2f}% vs {regime.get('real_fed_funds_basis')})"
    print(pol)

    print(f"\n  INFLATION      : level {inflation['level']} "
          f"(basis: {inflation.get('level_basis')})  trend {inflation['trend']}")
    for lbl, key in [('Headline CPI', 'headline_yoy'), ('Core CPI', 'core_cpi_yoy'),
                     ('Core PCE', 'core_pce_yoy')]:
        if inflation.get(key) is not None:
            print(f"    {lbl:13s}: {inflation[key]:+.2f}% y/y  "
                  f"[{inflation['tiers'].get(key.lower().replace(' ', '_').replace('headline_cpi','headline_cpi'))or ''}]")
    if inflation['energy_driven_flag']:
        print(f"    ENERGY-DRIVEN: headline vs core diverged "
              f"{inflation.get('energy_divergence_pp'):+.2f}pp")

    print(f"\n  YIELD CURVE    : {curve['signal']}")
    print(f"    2s10s {curve['slope_2s10s']} (src {curve['slope_source']} @{curve['slope_as_of']})")
    if curve.get('slope_consistent') is False:
        print(f"    VINTAGE SKEW : DGS-derived {curve['slope_2s10s_derived']} "
              f"@{curve['dgs_as_of']} vs published {curve['slope_2s10s_published']} "
              f"@{curve['published_as_of']} ({curve['slope_vintage_skew_days']}d)")
    print(f"    3m10s {curve['slope_3m10s']}  |  10s30s {curve['slope_10s30s']}")
    print(f"    2Y {curve['yield_2y']}  10Y {curve['yield_10y']}  30Y {curve['yield_30y']}  "
          f"@{curve['dgs_as_of']}")
    print(f"    Move 1d      : {curve['curve_move_1d']}   5d: {curve['curve_move_5d']}"
          f"   (from DGS @{curve['dgs_as_of']})")

    print(f"\n  VIX            : {vts.get('vix_spot')} [{vts.get('source')}] {vts.get('obs_date') or ''}")
    print(f"    9D {vts.get('vix9d')}  30D {vts.get('vix_spot')}  3M {vts.get('vix3m')}  "
          f"VVIX {vts.get('vvix')}")
    print(f"    Leg dates    : {vts.get('leg_dates')}")
    print(f"    Leg sources  : {vts.get('leg_sources')}")
    print(f"    Regime       : {vts.get('regime')}  ratio {vts.get('contango_ratio')}  "
          f"skew {vts.get('term_vintage_skew_days')}d")
    if vts.get('vix_pct_rank_1y') is not None:
        print(f"    1y pct rank  : VIX {vts['vix_pct_rank_1y']}th"
              + (f"   VIX9D {vts['vix9d_pct_rank_1y']}th" if vts.get('vix9d_pct_rank_1y') is not None else "")
              + "   (context only — no score adjustment applied here)")
    if vts.get('signal') == 'TERM_STRUCTURE_STALE':
        print(f"    REJECTED     : {vts.get('note')}")
    elif vts.get('front_end_inverted'):
        print("    FRONT-END HUMP — 9D above spot. Event premium priced in the front end.")
    print(f"    Reconcile    : {vts.get('reconcile_status')} "
          f"({vts.get('reconcile_pct')}% on {vts.get('reconcile_date', 'n/a')})")

    print(f"\n  LIQUIDITY      : {liquidity['level']} ({liquidity['trend']})")
    for s in liquidity['signals'][:5]:
        print(f"    - {s}")
    print(f"\n  MOMENTUM       : {momentum['direction']} ({momentum['strength']})")
    for s in momentum['signals'][:5]:
        print(f"    - {s}")
    print("\n  RISK SIGNALS:")
    for k, v in signals.items():
        if not k.endswith('_count'):
            print(f"    {k.replace('_', ' ').title():25s}: {v}")

    print("\n" + "=" * 70)
    print(f"FORWARD BIAS  (layer coverage {fb['layer_coverage']:.0%})")
    print("=" * 70)
    for label, key in [('SHORT  [ 1- 5d]', 'short_1_5d'),
                       ('MEDIUM [ 6-10d]', 'medium_6_10d'),
                       ('LONG   [11-20d]', 'long_11_20d')]:
        h = fb['horizons'][key]
        bar = '#' * int(h['bullish_prob_pct'] / 5) + '.' * (20 - int(h['bullish_prob_pct'] / 5))
        print(f"  {label}  {h['direction']:16s} [{bar}] {h['bullish_prob_pct']}%")
    print("\n  LAYER SCORES (n = inputs actually used):")
    for key, l in fb['layers'].items():
        print(f"    {l['layer']:26s} {l['score']:+.4f}  n={l.get('inputs_used', 0)}  "
              f"{l.get('direction', '')}")


def colab_auto_download(output_dir, ts):
    try:
        from google.colab import files as colab_files
    except ImportError:
        print(f"\n  Not in Colab — files in {output_dir}/")
        return
    print("\n  Move CSVs to: dropbox/market_data/")
    for fn in sorted(f for f in os.listdir(output_dir) if ts in f and f.endswith(('.json', '.csv'))):
        try:
            colab_files.download(os.path.join(output_dir, fn))
            time.sleep(0.3)
            print(f"  downloaded {fn}")
        except Exception as e:
            print(f"  FAILED {fn}: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if PURGE_PRIOR_RUNS:
        purge_prior_runs(OUTPUT_DIR, ts)

    market_data = {}
    market_data.update(PolygonExtractor(POLYGON_API_KEY).extract())
    market_data.update(VolComplexExtractor().extract())
    market_data.update(GlobalIndicesExtractor().extract())
    fred_data = FREDExtractor(FRED_API_KEY).extract()

    val_rows, failed_cats = validate_collection(market_data)
    if failed_cats:
        msg = f"Categories with >{MAX_NULL_RATE:.0%} nulls: {', '.join(failed_cats)}"
        COLLECTION_ERRORS.append(msg)
        print(f"\n  COLLECTION FAILURE: {msg}")
        if ABORT_ON_COLLECTION_FAILURE:
            raise CollectionFailed(msg)
        print("  ABORT_ON_COLLECTION_FAILURE=False — continuing degraded")

    inflation = calculate_inflation_pressure(fred_data)
    regime = calculate_market_regime(fred_data, inflation)
    curve = analyze_yield_curve(fred_data)
    momentum = calculate_economic_momentum(fred_data)
    liquidity = calculate_liquidity_conditions(fred_data)
    signals = analyze_risk_signals(market_data)
    risk = calculate_risk_score(market_data, regime, curve, signals, liquidity)
    vts = calculate_vix_term_structure(market_data, fred_data)
    fb = ForwardBiasEngine(market_data, fred_data, vts).compute()

    print_report(risk, regime, inflation, momentum, liquidity, curve, signals, vts, fb)

    print("\n" + "-" * 70)
    print("SAVING OUTPUTS")
    print("-" * 70)

    report = {
        'version': '5.4.3', 'run_id': ts, 'timestamp': datetime.now().isoformat(),
        'sources': ['Polygon', 'Cboe', 'yfinance', 'FRED'],
        'collection_validation': val_rows,
        'collection_errors': [redact(x) for x in COLLECTION_ERRORS],   # second line of defence
        'data_quality': {
            'layer_coverage': fb['layer_coverage'],
            'vix_source': vts.get('source'),
            'vix_leg_sources': vts.get('leg_sources'),
            'vix_leg_dates': vts.get('leg_dates'),
            'vix_term_vintage_skew_days': vts.get('term_vintage_skew_days'),
            'vix_term_accepted': vts.get('signal') != 'TERM_STRUCTURE_STALE',
            'vix_reconcile_status': vts.get('reconcile_status'),
            'vix_pct_rank_1y': vts.get('vix_pct_rank_1y'),
            'vix9d_pct_rank_1y': vts.get('vix9d_pct_rank_1y'),
            'curve_slope_consistent': curve.get('slope_consistent'),
            'curve_vintage_skew_days': curve.get('slope_vintage_skew_days'),
            'categories_failed': failed_cats,
            'fred_series_retrieved': len(fred_data),
        },
        'risk_assessment': risk, 'risk_signals': signals, 'macro_regime': regime,
        'inflation': inflation, 'momentum': momentum, 'liquidity': liquidity,
        'yield_curve': curve, 'vix_term_structure': vts,
        'forward_bias': {'horizons': fb['horizons'], 'layer_coverage': fb['layer_coverage'],
                         'layers': {k: {'score': v['score'], 'direction': v.get('direction', ''),
                                        'inputs_used': v.get('inputs_used')}
                                    for k, v in fb['layers'].items()}},
        'fred_indicators': {k: {kk: vv for kk, vv in v.items() if kk != 'history'}
                            for k, v in fred_data.items()},
    }
    with open(f"{OUTPUT_DIR}/report_{ts}.json", 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  report_{ts}.json")

    pd.DataFrame([{'indicator': s, 'name': d['name'], 'category': d['category'],
                   'value': d['value'], 'date': d['date'], 'age_days': d['age_days'],
                   'change_pct': d['change_pct'], 'abs_change': d['abs_change'],
                   'yoy_pct': d['yoy_pct'], 'source': d['source']}
                  for s, d in fred_data.items()]).to_csv(f"{OUTPUT_DIR}/macro_{ts}.csv", index=False)
    print(f"  macro_{ts}.csv")

    pd.DataFrame([{'horizon': k, 'direction': v['direction'],
                   'bullish_prob_pct': v['bullish_prob_pct'], 'score': v['score'],
                   'layer_coverage': v['layer_coverage'], 'run_id': ts}
                  for k, v in fb['horizons'].items()]).to_csv(
        f"{OUTPUT_DIR}/forward_bias_{ts}.csv", index=False)
    print(f"  forward_bias_{ts}.csv")

    pd.DataFrame(val_rows).to_csv(f"{OUTPUT_DIR}/collection_validation_{ts}.csv", index=False)
    print(f"  collection_validation_{ts}.csv")

    csv_cols = ['ticker', 'name', 'current_price', 'daily_pct', 'weekly_pct', 'monthly_pct',
                'ytd_pct', 'volume', 'high_52w', 'low_52w', 'pct_from_52w_high',
                'source', 'obs_date', 'age_days', 'data_status', 'data_flag']
    for cat, df in market_data.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            df[[c for c in csv_cols if c in df.columns]].to_csv(
                f"{OUTPUT_DIR}/{cat.lower()}_{ts}.csv", index=False)
    print(f"  category CSVs ({len(market_data)})")

    if COLLECTION_ERRORS:
        with open(f"{OUTPUT_DIR}/collection_errors_{ts}.txt", 'w', encoding='utf-8') as f:
            f.write("\n".join(redact(x) for x in COLLECTION_ERRORS))
        print(f"  collection_errors_{ts}.txt ({len(COLLECTION_ERRORS)} entries)")

    colab_auto_download(OUTPUT_DIR, ts)

    populated = sum(int(df['current_price'].notna().sum()) for df in market_data.values()
                    if isinstance(df, pd.DataFrame) and 'current_price' in df)
    total = sum(len(df) for df in market_data.values() if isinstance(df, pd.DataFrame))
    print("\n" + "=" * 70)
    print("AVSHUNTER v5.4.3 COMPLETE")
    print("=" * 70)
    print(f"  Run id                : {ts}")
    print(f"  Instruments POPULATED : {populated}/{total}")
    print(f"  FRED series           : {len(fred_data)}")
    print(f"  Forward bias coverage : {fb['layer_coverage']:.0%}")
    print(f"  VIX legs              : {vts.get('leg_sources')}")
    print(f"  Term structure        : {vts.get('regime')} "
          f"(skew {vts.get('term_vintage_skew_days')}d)")
    print(f"  Errors logged         : {len(COLLECTION_ERRORS)}")
    return report


if __name__ == "__main__":
    import sys
    IN_COLAB = setup()
    failed = True
    try:
        result = main()
        failed = False
    except CollectionFailed as e:
        print(f"\n  ABORTED — {redact(e)}")
        print("  No outputs written. Set ABORT_ON_COLLECTION_FAILURE=False to override.")
    except KeyboardInterrupt:
        print("\n  Interrupted")
    except Exception as e:
        import traceback
        print(f"\n  Error: {safe_error(e)}")
        print(redact(traceback.format_exc()))
    if failed and not IN_COLAB:     # a scheduler must see the failure; Colab shows it inline
        sys.exit(1)
