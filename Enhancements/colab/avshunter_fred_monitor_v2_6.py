# === AVSHUNTER: FRED Economic Monitor v2.5 ===
# Review of v2.4 against its real outputs (Claude, 6 Oct 2026). Every fix below was confirmed
# on the files v2.4 actually produced in dropbox\market_data.
#
# FIXES over v2.4
# ✅ HY/BBB OAS units. BAMLH0A0HYM2 / BAMLC0A4CBBB are PERCENT (3.10 = 310 bp). v2.4 printed
#    "3.10bps" and classify_regime() compared them with 400 / 600 as if they were bp, so STRESS
#    could never fire and GOLDILOCKS fired on the curve alone. Thresholds are now in percent
#    (HY_STRESS_PCT = 6.0, HY_CALM_PCT = 4.0) and labels print "% (… bp)".
# ✅ USSLIND is discontinued on FRED (last observation 2020-02-01, 2 points). v2.4 reported
#    "NORMAL (z=0.00)" because the 24-month z on 2 points is NaN and fell back to 0.
#    Stale is now STALE, never NORMAL; an undefined z is reported as undefined. The OECD
#    composite leading indicator for the US (USALOLITONOSTSAM) is fetched as the replacement
#    and goes through the same anomaly check.
# ✅ SOFR spread used monthly FEDFUNDS (35 days old on 6 Oct; the cause of the packet's
#    SOFR_FF_SPREAD_CONFLICT). It now uses daily EFFR: SOFR_EFFR_SPREAD. SOFR_FF_SPREAD is kept
#    for continuity.
# ✅ avsh_macro_master.csv was never consolidated in Colab. OUTPUT_DIR falls back to /content
#    where the other CSVs do not exist, so all seven merges were skipped (the delivered file
#    has 12 columns, no LIQ_/REGIME_/VIX_/FH_/FLAGS_/VTERM_/GEX_). The script now reports the
#    skips loudly and records merge coverage in the master row. It also points at
#    avshunter_vix_engine_v3.csv (v2.4 still looked for v2).
# ✅ Merged rows keep their own date as <PREFIX>_SOURCE_DATE (v2.4 dropped "Date", hiding that
#    e.g. GEX was two sessions older than the master row).
# ✅ Master row values are numbers (NaN when missing), not formatted strings or "N/A".
# ✅ BACKWARD COMPATIBLE: build_macro_json.py reads avsh_macro_master.csv by the v2.4 names
#    HY_OAS, IG_BBB_OAS, USSLIND_Quarantined, XLC_30d (and tests pin that header). Those columns
#    keep their names and units (percent); new columns are added beside them. The regime JSON
#    keeps its v2.4 keys too.
# ✅ avshunter_fred_errors.txt is always written (empty when clean); a stale error file from
#    an earlier run no longer survives a clean run.
# ✅ Labels: NEWORDER is core capital goods orders (not "Durable Goods"); DEXUSEU / DEXUSAL are
#    USD per EUR / AUD.
# ✅ Header honesty: v2.1 said "no files.download()", but v2.4 downloads everything. Download is
#    now an explicit AUTO_DOWNLOAD flag (default True, same behaviour as v2.4).
#
# ADDITIONS (board gap G10: split rising yields into their drivers; VIX history; broad dollar)
# ➕ DFII10 (10Y TIPS real yield), T10YIE (10Y breakeven), T5YIFR (5y5y forward inflation),
#    THREEFYTP10 (Kim-Wright 10Y term premium), BAMLH0A2HYB (single-B OAS), VIXCLS (VIX close),
#    DTWEXBGS (broad trade-weighted dollar), EFFR, NFCI (Chicago Fed financial conditions),
#    ICSA (initial claims), USALOLITONOSTSAM (OECD CLI, US).
# ➕ avshunter_fred_series_manifest.csv: one row per series with label, units, frequency,
#    last observation, age in days and FRESH / STALE / MISSING. A wrong or dead series ID shows
#    up here on the first run instead of silently disappearing.
# ➕ Dated archive copy of the FRED master (avshunter_fred_master_YYYYMMDD.csv) so a board
#    built today can be reproduced later (point-in-time inputs).
#
# NOT CHANGED: FRED history for ICE BofA series (HY/BBB/single-B OAS) is limited by licence to
# about three years (HY OAS starts 2023-10 in the master). The board uses HYG vs LQD for
# credit history for that reason.
#
# PIPELINE WARNING (unchanged): avshunter_regime.json uses GOLDILOCKS/INVERTED_CURVE vocabulary,
# NOT compatible with macro_contract_v1_0. SUPPLEMENTARY GPT context only.
#
# v2.6 (8 Oct 2026) — the Colab notebook "FRED Data- Input" (identical to v2.5) made runnable on
# the AVSHUNTER PC. Series, thresholds, derived indicators and every output schema unchanged:
# ✅ `!pip install` was notebook-only syntax, so v2.5 could not start as a .py file; pip now
#    runs only inside Colab.
# ✅ Keys: Colab Secrets in Colab; locally the environment, else the repo .env (override=False).
#    v2.5 read the environment only, so a key kept in .env was never found.
# ✅ Session cut-off (8 Oct 2026): with AVSH_SESSION_CUTOFF set (Run-MacroInputs.ps1), the Polygon
#    sector series stop at the last completed US session. FRED series are not cut.
# ✅ FRED via its REST endpoints (series/observations, series) — the calls fredapi wraps;
#    fredapi is not in the venv. Error text is redacted before it is printed or written.
# ✅ Merges for avsh_macro_master.csv read the other producers' files from
#    dropbox\market_data even when --output-dir (or AVSH_FRED_OUTPUT_DIR) redirects output.
# ✅ Plots only in Colab (display-only); JSON / errors written as UTF-8; UTF-8 console.
#    Local run:  venv\Scripts\python.exe Enhancements\colab\avshunter_fred_monitor_v2_6.py

# ════════════════════════════════════════════════════════════
# ── CONFIG ──────────────────────────────────────────────────
import argparse, os, pathlib, re, sys
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
LOCAL_MARKET_DATA = REPO_ROOT / "dropbox" / "market_data"
_parser = argparse.ArgumentParser(description="AVSHUNTER FRED economic monitor")
_parser.add_argument("--output-dir", default=os.environ.get("AVSH_FRED_OUTPUT_DIR"),
                     help="write here instead of dropbox\\market_data (for testing)")
_args, _ = _parser.parse_known_args()          # Colab passes its own kernel arguments
RUNNING_LOCAL = (not IN_COLAB) and LOCAL_MARKET_DATA.exists()
OUTPUT_DIR = LOCAL_MARKET_DATA if RUNNING_LOCAL else pathlib.Path("/content")
INPUT_DIR = OUTPUT_DIR                         # other producers' files (merge step)
if _args.output_dir:
    OUTPUT_DIR = pathlib.Path(_args.output_dir)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = OUTPUT_DIR / "fred_archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
AUTO_DOWNLOAD = True          # Colab only: download outputs after the run (v2.4 behaviour)
HY_CALM_PCT, HY_STRESS_PCT = 4.0, 6.0     # HY OAS in PERCENT (4.0% = 400 bp)
CURVE_STEEP_PCT = 1.0                      # 10Y-2Y in percentage points
MAX_AGE_DAYS = {"D": 7, "W": 14, "BW": 21, "M": 75, "Q": 140, "A": 400}   # by FRED frequency
print(f"📁 OUTPUT_DIR: {OUTPUT_DIR}  ({'local Windows' if RUNNING_LOCAL else 'Colab /content'})"
      + (f"   inputs: {INPUT_DIR}" if INPUT_DIR != OUTPUT_DIR else ""))
# ════════════════════════════════════════════════════════════

if IN_COLAB:
    get_ipython().system('pip -q install pandas numpy matplotlib requests')  # noqa: F821

import json, datetime, time
import pandas as pd
import numpy as np
import requests
if IN_COLAB:
    import matplotlib.pyplot as plt
else:
    plt = None

if IN_COLAB:
    from google.colab import userdata
    FRED_API_KEY    = userdata.get("FRED_API_KEY")
    POLYGON_API_KEY = userdata.get("POLYGON_API_KEY")
else:                                               # local run: environment, else repo .env
    try:
        from dotenv import load_dotenv
        if (REPO_ROOT / ".env").exists():
            load_dotenv(REPO_ROOT / ".env", override=False)   # real environment variables win
    except ImportError:
        pass
    FRED_API_KEY    = (os.environ.get("FRED_API_KEY") or "").strip() or None
    POLYGON_API_KEY = (os.environ.get("POLYGON_API_KEY") or "").strip() or None
if not FRED_API_KEY:
    raise SystemExit("❌ FRED_API_KEY empty")
print("✅ API keys loaded")

_KEY_IN_TEXT = re.compile(r"((?:apiKey|api_key|token)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text):
    """Remove key values from error text (request URLs carry the key)."""
    return _KEY_IN_TEXT.sub(r"\1REDACTED", str(text))


FRED_BASE = "https://api.stlouisfed.org/fred"


FRED_TIMEOUT_S, FRED_ATTEMPTS = 60, 3


def _fred_get(path, **params):
    """One FRED REST call, retried on timeout / connection error / 429 / 5xx. fredapi waited
    without a time limit; a bare 30 s timeout lost WTREGEN on 8 Oct when FRED was answering
    in 8-11 s per request, so slowness is retried rather than turned into a MISSING series."""
    last = None
    for attempt in range(1, FRED_ATTEMPTS + 1):
        try:
            r = requests.get(f"{FRED_BASE}/{path}",
                             params={**params, "api_key": FRED_API_KEY, "file_type": "json"},
                             timeout=FRED_TIMEOUT_S)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.exceptions.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if isinstance(e, requests.exceptions.HTTPError) and status is not None and status < 500 and status != 429:
                raise                                   # 4xx (bad series id, bad key) is not transient
            last = e
            if attempt < FRED_ATTEMPTS:
                time.sleep(2 * attempt)
    raise last


today      = datetime.date.today()
start_date = "2020-01-01"
end_date   = today.isoformat()
errors     = []

FRED_SERIES = {
    # liquidity
    "WALCL":"Fed balance sheet ($m)","WRESBAL":"Bank reserves ($m)","RRPONTSYD":"Overnight RRP ($bn)",
    "WTREGEN":"Treasury General Account ($m)",
    # curve
    "DGS1MO":"1M yield","DGS3MO":"3M yield","DGS6MO":"6M yield",
    "DGS1":"1Y yield","DGS2":"2Y yield","DGS5":"5Y yield","DGS10":"10Y yield","DGS30":"30Y yield",
    # yield drivers (NEW v2.5)
    "DFII10":"10Y TIPS real yield","T10YIE":"10Y breakeven inflation","T5YIFR":"5y5y forward inflation",
    "THREEFYTP10":"10Y term premium (Kim-Wright)",
    # credit (ICE BofA: ~3y history on FRED)
    "BAMLH0A0HYM2":"HY OAS (%)","BAMLC0A4CBBB":"BBB OAS (%)","BAMLH0A2HYB":"Single-B OAS (%)",
    # policy / funding
    "SOFR":"SOFR","EFFR":"Effective Fed Funds (daily)","FEDFUNDS":"Fed Funds (monthly avg)","IORB":"IORB",
    "NFCI":"Chicago Fed financial conditions",
    # balance sheets / money
    "WSHOMCB":"Fed MBS holdings","FDHBFRBN":"Foreign holdings of Treasuries","TOTLL":"Total loans",
    "DPSACBW027SBOG":"Bank deposits","M2SL":"M2","M1SL":"M1","WM2NS":"Weekly M2",
    # activity / prices
    "INDPRO":"Industrial production","PAYEMS":"Payrolls","UNRATE":"Unemployment","ICSA":"Initial claims",
    "CPIAUCSL":"CPI","CPILFESL":"Core CPI","PCE":"PCE","GDPC1":"Real GDP",
    "NEWORDER":"Core capital goods new orders (nondefense ex aircraft)",
    "USSLIND":"LEI (Conference Board) — discontinued on FRED, kept for staleness check",
    "USALOLITONOSTSAM":"OECD composite leading indicator, US",
    "UMCSENT":"UMich sentiment",
    # volatility / dollar
    "VIXCLS":"VIX close","DTWEXBGS":"Broad trade-weighted dollar",
    "DEXJPUS":"JPY per USD","DEXUSEU":"USD per EUR","DEXCHUS":"CNY per USD","DEXUSAL":"USD per AUD",
}

POLYGON_SECTORS = {t: t for t in ["XLF","XLE","XLK","XLV","XLI","XLY","XLP","XLU","XLB","XLRE","XLC"]}


def safe_fred_get(series_id, start):
    try:
        obs = _fred_get("series/observations", series_id=series_id, observation_start=start).get("observations", [])
        s = pd.Series(pd.to_numeric([o["value"] for o in obs], errors="coerce"),     # "." = missing
                      index=pd.to_datetime([o["date"] for o in obs]), dtype="float64").dropna()
        s.index = pd.to_datetime(s.index)
        return s
    except Exception as e:
        errors.append(f"{series_id}: {type(e).__name__}: {redact(e)}")
        return pd.Series(dtype="float64")


def safe_fred_info(series_id):
    try:
        info = (_fred_get("series", series_id=series_id).get("seriess") or [{}])[0]
        return {"units": info.get("units_short") or info.get("units"),
                "frequency": info.get("frequency_short") or info.get("frequency"),
                "last_updated": info.get("last_updated")}
    except Exception as e:
        errors.append(f"{series_id} info: {type(e).__name__}: {redact(e)}")
        return {"units": None, "frequency": None, "last_updated": None}


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


def fetch_polygon_daily(ticker, start, end, api_key):
    if not api_key:
        errors.append(f"Polygon {ticker}: no key"); return pd.Series(dtype="float64")
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
    r = requests.get(url, params={"adjusted":"true","sort":"asc","apiKey":api_key}, timeout=30)
    if r.status_code != 200: errors.append(f"Polygon {ticker} {r.status_code}"); return pd.Series(dtype="float64")
    res = r.json().get("results",[])
    if not res: errors.append(f"Polygon {ticker} empty"); return pd.Series(dtype="float64")
    df = pd.DataFrame(res); df["t"] = pd.to_datetime(df["t"],unit="ms")
    return cut_to_session(df.set_index("t")["c"].sort_index(), session_cutoff())


print(f"Fetching {len(FRED_SERIES)} FRED series...")
data, manifest = {}, []
for code, label in FRED_SERIES.items():
    s = safe_fred_get(code, start_date)
    info = safe_fred_info(code)
    freq = str(info.get("frequency") or "").upper().split(",")[0].strip()
    if not s.empty:
        data[code] = s
        last_obs = s.index.max().date()
        age = (today - last_obs).days
        limit = MAX_AGE_DAYS.get(freq, 75)
        status = "FRESH" if age <= limit else "STALE"
        print(f"  {'✅' if status=='FRESH' else '⏳'} {code:18s} | {label} | last {last_obs} ({age}d, {status})")
    else:
        last_obs, age, status = None, None, "MISSING"
        print(f"  ⚠  {code:18s} | FAILED")
    manifest.append({"series": code, "label": label, "units": info.get("units"), "frequency": freq or None,
                     "observations": int(len(s)), "first_observation": None if s.empty else str(s.index.min().date()),
                     "last_observation": None if last_obs is None else str(last_obs), "age_days": age,
                     "status": status, "fred_last_updated": info.get("last_updated"), "fetched_utc":
                     datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"})
pd.DataFrame(manifest).to_csv(OUTPUT_DIR/"avshunter_fred_series_manifest.csv", index=False)
print(f"📁 {OUTPUT_DIR/'avshunter_fred_series_manifest.csv'}")

print(f"\nFetching Polygon sector ETFs...")
sector_data = {}
for name, ticker in POLYGON_SECTORS.items():
    s = fetch_polygon_daily(ticker, start_date, end_date, POLYGON_API_KEY)
    if not s.empty: sector_data[name] = s; print(f"  ✅ {name}")
    else: print(f"  ⚠  {name}: MISSING")
print(f"\nFetched {len(data)}/{len(FRED_SERIES)} FRED series. Errors so far: {len(errors)}")


# ── Leading-indicator anomaly / staleness check (FIX v2.5) ───────────────────
def lei_status(code, max_age_days=75):
    """FRESH value with z vs trailing 24 months, or STALE / MISSING. Never NORMAL from old data,
    never z = 0 when z is undefined."""
    if code not in data or data[code].empty:
        return "MISSING (excluded)", True, None
    lei = data[code].dropna()
    last_obs = lei.index.max().date()
    if (today - last_obs).days > max_age_days:
        return f"STALE (last observation {last_obs}; excluded)", True, None
    z = (lei - lei.rolling(24).mean()) / lei.rolling(24).std()
    z_latest = float(z.iloc[-1]) if pd.notna(z.iloc[-1]) else None
    mom = float(lei.diff().iloc[-1]) if len(lei) > 1 else None
    if z_latest is None:
        return f"FRESH, z undefined (< 24 observations), latest={float(lei.iloc[-1]):.2f}", False, float(lei.iloc[-1])
    if abs(z_latest) > 3 or (mom is not None and abs(mom) > 3):
        return f"QUARANTINED (z={z_latest:.2f}, MoM={mom:.2f})", True, float(lei.iloc[-1])
    return f"NORMAL (z={z_latest:.2f}, latest={float(lei.iloc[-1]):.2f}, as of {last_obs})", False, float(lei.iloc[-1])

usslind_status, usslind_quarantined, _ = lei_status("USSLIND")
cli_status, cli_quarantined, cli_latest = lei_status("USALOLITONOSTSAM")
print(f"\n📊 USSLIND : {usslind_status}")
print(f"📊 OECD CLI: {cli_status}")

# ── Derived indicators ────────────────────────────────────────────────────────
derived = {}
if "DGS10" in data and "DGS2"   in data: derived["SPREAD_2Y10Y"] = (data["DGS10"]-data["DGS2"]).dropna()
if "DGS10" in data and "DGS3MO" in data: derived["SPREAD_3M10Y"] = (data["DGS10"]-data["DGS3MO"]).dropna()
if "SOFR" in data and "EFFR" in data:                                    # daily vs daily (FIX v2.5)
    derived["SOFR_EFFR_SPREAD"] = (data["SOFR"] - data["EFFR"]).dropna()
if "SOFR" in data and "FEDFUNDS" in data:                                # kept for continuity (monthly)
    derived["SOFR_FF_SPREAD"] = (data["SOFR"].reindex(data["FEDFUNDS"].index).ffill()-data["FEDFUNDS"]).dropna()
if "DGS10" in data and "DFII10" in data:                                 # nominal = real + breakeven (check)
    derived["BREAKEVEN_10Y_IMPLIED"] = (data["DGS10"] - data["DFII10"]).dropna()
if "M1SL" in data and "M2SL" in data:
    al = pd.concat([data["M1SL"],data["M2SL"]],axis=1).dropna()
    if not al.empty: derived["M1_M2_RATIO"] = (al.iloc[:,0]/al.iloc[:,1]).dropna()
if "WTREGEN" in data and len(data["WTREGEN"])>4:
    derived["TGA_4WK_CHANGE"] = data["WTREGEN"].diff(4).dropna()
if "DPSACBW027SBOG" in data:
    derived["BANK_DEPOSITS_YOY"] = data["DPSACBW027SBOG"].pct_change(52).dropna()*100
if "M2SL" in data:
    derived["M2_YOY"] = data["M2SL"].pct_change(12).dropna()*100

sector_1m = {}
for name, s in sector_data.items():
    if not s.empty and len(s) >= 22:
        sector_1m[name] = round(float(s.pct_change(22).iloc[-1])*100, 2)          # 22 sessions ≈ 1 month
print(f"\nDerived {len(derived)} computed series.")


# ── Snapshot ──────────────────────────────────────────────────────────────────
def last_value(sd, key):
    s = sd.get(key)
    return float(s.dropna().iloc[-1]) if isinstance(s, pd.Series) and not s.dropna().empty else np.nan

def last_date(sd, key):
    s = sd.get(key)
    return str(s.dropna().index[-1].date()) if isinstance(s, pd.Series) and not s.dropna().empty else None

def fmt(v, pattern):
    return "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else pattern.format(v)

hy, bbb, b = last_value(data,"BAMLH0A0HYM2"), last_value(data,"BAMLC0A4CBBB"), last_value(data,"BAMLH0A2HYB")
print("\n" + "="*65 + "\n=== AVSHUNTER FRED MONITOR v2.6 ===\n" + "="*65)
print(f"Date            : {end_date}")
print(f"DGS10 / DGS2    : {fmt(last_value(data,'DGS10'),'{:.3f}%')} / {fmt(last_value(data,'DGS2'),'{:.3f}%')}  (as of {last_date(data,'DGS10')})")
print(f"2Y-10Y spread   : {fmt(last_value(derived,'SPREAD_2Y10Y'),'{:.3f} pp')}")
print(f"10Y real / BE   : {fmt(last_value(data,'DFII10'),'{:.2f}%')} / {fmt(last_value(data,'T10YIE'),'{:.2f}%')}  term premium {fmt(last_value(data,'THREEFYTP10'),'{:.2f}%')}")
print(f"HY OAS          : {fmt(hy,'{:.2f}%')} ({fmt(hy*100 if not np.isnan(hy) else np.nan,'{:.0f} bp')})  as of {last_date(data,'BAMLH0A0HYM2')}")
print(f"BBB / Single-B  : {fmt(bbb,'{:.2f}%')} / {fmt(b,'{:.2f}%')}")
print(f"SOFR − EFFR     : {fmt(last_value(derived,'SOFR_EFFR_SPREAD'),'{:+.3f} pp')}  (daily)")
print(f"VIX (FRED)      : {fmt(last_value(data,'VIXCLS'),'{:.2f}')}  as of {last_date(data,'VIXCLS')}")
print(f"Broad dollar    : {fmt(last_value(data,'DTWEXBGS'),'{:.2f}')}  NFCI {fmt(last_value(data,'NFCI'),'{:+.3f}')}")
print(f"M2 YoY          : {fmt(last_value(derived,'M2_YOY'),'{:.1f}%')}")
print(f"USSLIND         : {usslind_status}")
print(f"OECD CLI        : {cli_status}")
print(f"XLC 1m          : {sector_1m.get('XLC','MISSING')}")
print("="*65)


# ── Regime JSON (supplementary only) — thresholds in PERCENT (FIX v2.5) ───────
spread = last_value(derived, "SPREAD_2Y10Y")

def classify_regime(spread_pp, hy_pct):
    if np.isnan(spread_pp): return "UNKNOWN"
    if not np.isnan(hy_pct) and hy_pct > HY_STRESS_PCT: return "STRESS"
    if spread_pp < 0: return "INVERTED_CURVE"
    if spread_pp > CURVE_STEEP_PCT and (np.isnan(hy_pct) or hy_pct < HY_CALM_PCT): return "GOLDILOCKS"
    return "NEUTRAL"

regime_label = classify_regime(spread, hy)
regime_json = {
    "_WARNING": "DO NOT feed to inject_macro_into_packages.py — vocabulary incompatible with macro_contract_v1_0",
    "_USE": "Supplementary GPT context only",
    "_UNITS": "spread_2y10y in percentage points; hy_oas in percent (3.10 = 310 bp)",
    "avshunter_regime": regime_label, "as_of": end_date,
    "spread_2y10y": None if np.isnan(spread) else round(spread, 3), "spread_as_of": last_date(derived, "SPREAD_2Y10Y"),
    "hy_oas": None if np.isnan(hy) else hy, "hy_oas_as_of": last_date(data, "BAMLH0A0HYM2"),
    "usslind_status": usslind_status, "usslind_quarantined": usslind_quarantined,
    "oecd_cli_status": cli_status, "oecd_cli_quarantined": cli_quarantined,
    "xlc_30d": sector_1m.get("XLC"),
}
with open(OUTPUT_DIR/"avshunter_regime.json","w",encoding="utf-8") as f: json.dump(regime_json, f, indent=2)
print(f"\n📁 {OUTPUT_DIR/'avshunter_regime.json'}  ⚠️  SUPPLEMENTARY ONLY")


# ── FRED master CSV + dated archive copy (NEW v2.5) ───────────────────────────
all_series = {**data, **derived}
master_df = pd.DataFrame({k: v for k, v in all_series.items() if isinstance(v, pd.Series) and not v.empty})
master_df.index = pd.to_datetime(master_df.index); master_df = master_df.sort_index()
master_df.to_csv(OUTPUT_DIR/"avshunter_fred_master.csv")
master_df.to_csv(ARCHIVE_DIR/f"avshunter_fred_master_{today:%Y%m%d}.csv")
print(f"📁 {OUTPUT_DIR/'avshunter_fred_master.csv'}  (+ archive copy in {ARCHIVE_DIR.name}/)")


# ── avsh_macro_master.csv — consolidated single row ───────────────────────────
print("\n🔄 Building avsh_macro_master.csv...")
master_row = {
    # v2.4 columns, same names and units (read by build_macro_json.py)
    "Date": end_date,
    "DGS10": last_value(data,"DGS10"), "DGS2": last_value(data,"DGS2"), "Spread_2Y10Y": spread,
    "HY_OAS": hy, "IG_BBB_OAS": bbb, "SOFR": last_value(data,"SOFR"), "M2_YOY": last_value(derived,"M2_YOY"),
    "USSLIND_Status": usslind_status, "USSLIND_Quarantined": usslind_quarantined,
    "Regime_FRED": regime_label, "XLC_30d": sector_1m.get("XLC", np.nan),
    # v2.5 additions
    "DFII10": last_value(data,"DFII10"), "T10YIE": last_value(data,"T10YIE"), "TERM_PREMIUM_10Y": last_value(data,"THREEFYTP10"),
    "SINGLE_B_OAS": b, "HY_OAS_AS_OF": last_date(data, "BAMLH0A0HYM2"),
    "SOFR_EFFR_SPREAD": last_value(derived,"SOFR_EFFR_SPREAD"),
    "VIXCLS": last_value(data,"VIXCLS"), "BROAD_USD": last_value(data,"DTWEXBGS"), "NFCI": last_value(data,"NFCI"),
    "OECD_CLI_Status": cli_status, "OECD_CLI_Quarantined": cli_quarantined,
    "UNITS": "yields/spreads/OAS in percent (HY_OAS 3.10 = 310 bp); XLC_30d = 22-session % change",
}
merge_report = []

def merge_csv_latest(filename, prefix, row, filter_col=None, filter_val=None):
    """Merge one row of ``filename`` into ``row`` under ``prefix``; keeps the row's own date as
    <prefix>_SOURCE_DATE. Multi-row files (one row per ticker) MUST pass filter_col/filter_val."""
    fp = INPUT_DIR / filename          # v2.6: inputs stay on dropbox\market_data when output is redirected
    if not fp.exists():
        merge_report.append((filename, prefix, "NOT_FOUND"))
        print(f"  ⚠  Not found (skipped): {filename}")
        return row
    try:
        df = pd.read_csv(fp)
        if df.empty:
            merge_report.append((filename, prefix, "EMPTY")); return row
        if filter_col:
            if filter_col not in df.columns:
                merge_report.append((filename, prefix, f"NO_COLUMN_{filter_col}"))
                print(f"  ⚠  {filename}: column '{filter_col}' not found — skipped (no silent fallback)")
                return row
            sel = df[df[filter_col] == filter_val]
            if sel.empty:
                merge_report.append((filename, prefix, f"NO_ROW_{filter_val}"))
                print(f"  ⚠  {filename}: no row where {filter_col}=={filter_val} — skipped")
                return row
            src = sel.iloc[-1]
        else:
            src = df.iloc[-1]
        for col in df.columns:
            key = f"{prefix}_SOURCE_DATE" if col.lower() == "date" else f"{prefix}_{col}"
            row[key] = src[col]
        merge_report.append((filename, prefix, "MERGED"))
        print(f"  ✅ Merged: {filename}{f' [{filter_col}={filter_val}]' if filter_col else ''}")
    except Exception as e:
        merge_report.append((filename, prefix, f"ERROR {type(e).__name__}"))
        print(f"  ⚠  {filename}: {e}")
    return row

master_row = merge_csv_latest("avshunter_liquidity_monitor.csv",   "LIQ",    master_row)
master_row = merge_csv_latest("avshunter_daily_macro_regime.csv",  "REGIME", master_row)
master_row = merge_csv_latest("avshunter_vix_engine_v3.csv",       "VIX",    master_row)   # FIX v2.5: was v2
master_row = merge_csv_latest("avshunter_macro_filter_summary.csv","FH",     master_row)
master_row = merge_csv_latest("macro_series_threshold_flags.csv",  "FLAGS",  master_row)
master_row = merge_csv_latest("vix_term_dxy_snapshot.csv",         "VTERM",  master_row)
master_row = merge_csv_latest("avshunter_gex_proxy.csv", "GEX",    master_row, filter_col="Ticker", filter_val="SPY")
master_row = merge_csv_latest("avshunter_gex_proxy.csv", "GEXQQQ", master_row, filter_col="Ticker", filter_val="QQQ")

merged = sum(1 for _, _, status in merge_report if status == "MERGED")
master_row["MERGE_COVERAGE"] = f"{merged}/{len(merge_report)}"
master_row["MERGE_REPORT"] = "; ".join(f"{prefix}:{status}" for _, prefix, status in merge_report)
if merged < len(merge_report):
    print(f"\n⚠️  CONSOLIDATION INCOMPLETE: {merged}/{len(merge_report)} sources merged."
          + ("" if RUNNING_LOCAL else " Running in Colab: the other producers' CSVs are not in /content. "
             "Upload them to /content first, or run this cell locally, for a consolidated row."))
pd.DataFrame([master_row]).to_csv(OUTPUT_DIR/"avsh_macro_master.csv", index=False)
print(f"\n📁 {OUTPUT_DIR/'avsh_macro_master.csv'}  ← master row, merge coverage {master_row['MERGE_COVERAGE']}")

# always written, so an earlier run's errors never survive a clean run (FIX v2.5)
with open(OUTPUT_DIR/"avshunter_fred_errors.txt","w",encoding="utf-8") as f: f.write("\n".join(redact(e) for e in errors))
print(f"📁 {OUTPUT_DIR/'avshunter_fred_errors.txt'} ({len(errors)} errors)")


# ── Plots ─────────────────────────────────────────────────────────────────────
def safe_plot(sd, keys, title):
    if plt is None: return                                    # v2.6: plots are Colab-only
    frames = [(k, sd[k]) for k in keys if k in sd and not sd[k].empty]
    if not frames: return
    plt.figure(figsize=(14, 4))
    for k, s in frames: plt.plot(s.index, s.values, label=k)
    plt.title(title); plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout(); plt.show()

safe_plot(derived, ["SPREAD_2Y10Y","SPREAD_3M10Y"], "Yield curve spreads (pp)")
safe_plot(data, ["DGS10","DFII10","T10YIE"], "10Y nominal = real + breakeven (%)")
safe_plot(data, ["THREEFYTP10"], "10Y term premium (%)")
safe_plot(data, ["BAMLH0A0HYM2","BAMLC0A4CBBB","BAMLH0A2HYB"], "Credit spreads: HY, BBB, single-B OAS (%)")
safe_plot(data, ["WALCL","RRPONTSYD","WTREGEN","WRESBAL"], "Fed liquidity block (mixed units: $m and $bn)")
safe_plot(derived, ["SOFR_EFFR_SPREAD"], "SOFR − EFFR (pp, daily)")
safe_plot(data, ["VIXCLS"], "VIX close")
if sector_1m and plt is not None:
    plt.figure(figsize=(13, 5))
    sl, sv = list(sector_1m.keys()), list(sector_1m.values())
    plt.bar(sl, sv, color=["green" if v >= 0 else "red" for v in sv], alpha=0.7)
    plt.axhline(0, color="black", linewidth=0.8)
    plt.title("Sector 1-month (22-session) % change"); plt.xticks(rotation=30, ha="right")
    plt.grid(True, alpha=0.3); plt.tight_layout(); plt.show()


# ── Download (Colab only, explicit flag) ──────────────────────────────────────
if AUTO_DOWNLOAD and not RUNNING_LOCAL:
    try:
        from google.colab import files as _colab_files
        for _f in sorted(list(OUTPUT_DIR.glob("*.csv")) + list(OUTPUT_DIR.glob("*.json")) + list(OUTPUT_DIR.glob("*.txt"))):
            try:
                _colab_files.download(str(_f)); print(f"⬇️  Downloaded: {_f.name}")
            except Exception as _e:
                print(f"⚠️  Could not download {_f.name}: {_e}")
    except Exception:
        pass
print(f"\n✅ v2.6 COMPLETE — outputs → {OUTPUT_DIR}")
print("   • HY/BBB OAS handled in percent; regime STRESS reachable again")
print("   • USSLIND staleness reported honestly; OECD CLI added as the live leading indicator")
print("   • SOFR spread now daily (SOFR − EFFR)")
print("   • Real yield, breakeven, term premium, single-B, VIX, broad dollar, NFCI, claims added")
print("   • Series manifest + dated archive copy written; merge coverage reported in the master row")
