"""
AVSHUNTER — Rapid Rotation Flag (RRF) v2.0
==========================================
v2.0 changes:
  - Uses CL=F (WTI crude futures) and GC=F (gold futures) from Colab output CSVs
    when available. Futures move before ETFs — earlier, cleaner signal.
  - Falls back to USO/GLD Polygon ETF calls when Colab CSVs are not present.
  - Added SI=F (silver futures) and HG=F (copper futures) as commodity signals.
  - Paper side updated: SPY replaces QQQ as primary equity proxy (broader signal).

Run AFTER uploading macro JSON and BEFORE running the pipeline.
"""

import json
import os
import sys
import csv
import glob
import requests
from pathlib import Path
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

from canonical_data.macro_publication import (
    macro_projection_paths,
    write_authoritative_macro,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent
MACRO_JSON_PATH = REPOSITORY_ROOT / "dropbox" / "macro" / "macro_intelligence_latest.json"

# Colab output drop folder — where Colab CSVs land after download
COLAB_DROP_DIR = REPOSITORY_ROOT / "dropbox" / "market_data"

# ─────────────────────────────────────────────
# COMMODITY TICKERS
# Futures preferred (from Colab CSV), ETF fallback (Polygon)
# ─────────────────────────────────────────────

COMMODITY_FUTURES = {
    "CL=F":  {"desc": "WTI Crude Futures",   "spike_pct": 2.0, "etf_fallback": "USO"},
    "GC=F":  {"desc": "Gold Futures",         "spike_pct": 1.2, "etf_fallback": "GLD"},
    "SI=F":  {"desc": "Silver Futures",       "spike_pct": 1.5, "etf_fallback": "SLV"},
    "HG=F":  {"desc": "Copper Futures",       "spike_pct": 1.5, "etf_fallback": "CPER"},
    "GDX":   {"desc": "Gold Miners ETF",      "spike_pct": 1.8, "etf_fallback": "GDX"},
}

PAPER_TICKERS = {
    "SPY":  {"desc": "S&P500 ETF",   "drop_pct": -0.8},
    "QQQ":  {"desc": "Nasdaq ETF",   "drop_pct": -0.8},
    "NVDA": {"desc": "Nvidia",       "drop_pct": -1.5},
}

ACTIVE_THRESHOLD   = 2
BUILDING_THRESHOLD = 1


# ─────────────────────────────────────────────
# COLAB CSV READER
# Looks for the most recent energy_futures or metal_futures CSV
# in the Colab drop directory and reads daily_pct for each ticker.
# ─────────────────────────────────────────────

def read_colab_pct(ticker: str) -> float | None:
    """
    Reads daily_pct for a futures ticker from the most recent Colab output CSV.
    Looks in COLAB_DROP_DIR for energy_futures_*.csv and metal_futures_*.csv.
    Returns float pct_change or None if not found.
    """
    if not COLAB_DROP_DIR.exists():
        return None

    # Map ticker to expected CSV category prefix
    category_map = {
        "CL=F": "energy_futures",
        "NG=F": "energy_futures",
        "HO=F": "energy_futures",
        "GC=F": "metal_futures",
        "SI=F": "metal_futures",
        "HG=F": "metal_futures",
        "PL=F": "metal_futures",
        "ES=F": "equity_futures",
        "NQ=F": "equity_futures",
        "SPY":  "indices_etf",
        "QQQ":  "indices_etf",
    }

    prefix = category_map.get(ticker)
    if not prefix:
        return None

    # Find the most recent matching CSV
    pattern = str(COLAB_DROP_DIR / f"{prefix}_*.csv")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return None

    latest = files[0]
    try:
        with open(latest, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = row.get("ticker", "").strip()
                if t == ticker:
                    val = row.get("daily_pct")
                    if val not in (None, "", "None", "nan"):
                        return float(val)
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# OVERNIGHT CAPTURE (Run-MacroInputs pre-open step)
# Live futures and pre-market ETFs measured since the last US close. Used first when the capture is
# fresh and the instrument's line is live; the Colab futures CSVs it replaced no longer exist.
# ─────────────────────────────────────────────

OVERNIGHT_MAX_AGE_HOURS = 12.0      # same limit as the macro board's overnight freshness


def read_overnight(ticker: str) -> dict | None:
    files = sorted(COLAB_DROP_DIR.glob("overnight_*.json")) if COLAB_DROP_DIR.exists() else []
    if not files:
        return None
    try:
        doc = json.loads(files[-1].read_text(encoding="utf-8"))
        made = datetime.fromisoformat(str(doc["as_of_utc"]).replace("Z", "+00:00"))
    except Exception:
        return None
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - made).total_seconds() / 3600.0 > OVERNIGHT_MAX_AGE_HOURS:
        return None
    if str(doc.get("run_session") or "").lower() != "preopen":
        return None                 # an evening capture measures from today's close: almost no move yet
    for rows in (doc.get("groups") or {}).values():
        for row in rows or []:
            if row.get("symbol") != ticker:
                continue
            pct = row.get("change_pct")
            if row.get("state") != "OK" or row.get("stale") or pct is None:
                return None
            return {"ticker": ticker, "pct_change": round(float(pct), 3), "status": "OK", "source": "overnight_capture",
                    "window": f"since the {doc.get('us_reference_session')} close (overnight capture {files[-1].name})"}
    return None


# ─────────────────────────────────────────────
# POLYGON FALLBACK FETCH
# ─────────────────────────────────────────────

def get_polygon_change(ticker: str) -> dict:
    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not api_key:
        return {
            "ticker": ticker,
            "pct_change": None,
            "status": "CREDENTIAL_UNAVAILABLE",
            "source": "polygon",
        }
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
    params = {"adjusted": "true", "apiKey": api_key}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("resultsCount", 0) == 0:
            return {"ticker": ticker, "pct_change": None, "status": "NO_DATA", "source": "polygon"}
        bar = data["results"][0]
        o, c = bar["o"], bar["c"]
        pct = round(((c - o) / o) * 100, 3) if o else None
        return {"ticker": ticker, "open": o, "close": c, "pct_change": pct,
                "status": "OK", "source": "polygon"}
    except Exception as e:
        return {
            "ticker": ticker,
            "pct_change": None,
            "status": f"ERROR:{type(e).__name__}",
            "source": "polygon",
        }


# ─────────────────────────────────────────────
# UNIFIED FETCH — futures CSV first, then Polygon ETF fallback
# ─────────────────────────────────────────────

POLYGON_WINDOW = "previous session, open to close"


def fetch_commodity(futures_ticker: str, cfg: dict) -> dict:
    """Fresh overnight capture first, then the Colab futures CSV, then the ETF via Polygon."""
    live = read_overnight(futures_ticker)
    if live is not None:
        return live
    pct = read_colab_pct(futures_ticker)
    if pct is not None:
        return {"ticker": futures_ticker, "pct_change": pct,
                "status": "OK", "source": "colab_csv", "window": "Colab daily change"}

    # Fallback: use ETF via Polygon
    etf = cfg.get("etf_fallback", futures_ticker)
    result = get_polygon_change(etf)
    result["ticker"] = futures_ticker  # keep futures label for reporting
    result["etf_used"] = etf
    result["window"] = POLYGON_WINDOW
    return result


def fetch_paper(ticker: str) -> dict:
    """Paper assets: live pre-market line from the overnight capture, then the Colab CSV, then Polygon."""
    live = read_overnight(ticker)
    if live is not None:
        return live
    pct = read_colab_pct(ticker)
    if pct is not None:
        return {"ticker": ticker, "pct_change": pct, "status": "OK", "source": "colab_csv", "window": "Colab daily change"}
    result = get_polygon_change(ticker)
    result["window"] = POLYGON_WINDOW
    return result


# ─────────────────────────────────────────────
# ROTATION DETECTION LOGIC (unchanged from v1.0)
# ─────────────────────────────────────────────

def assess_rotation(commodity_results: dict, paper_results: dict, *, commodities: dict | None = None,
                    paper: dict | None = None, active_threshold: int | None = None) -> dict:
    """The flag rule. Settings default to this module's; the macro board replays the same rule on history."""
    commodities = COMMODITY_FUTURES if commodities is None else commodities
    paper = PAPER_TICKERS if paper is None else paper
    active_threshold = ACTIVE_THRESHOLD if active_threshold is None else active_threshold
    commodity_spikes = []
    for ticker, cfg in commodities.items():
        r = commodity_results.get(ticker, {})
        pct = r.get("pct_change")
        if pct is not None and pct >= cfg["spike_pct"]:
            commodity_spikes.append({
                "ticker": ticker, "desc": cfg.get("desc", ticker),
                "pct": pct, "threshold": cfg["spike_pct"],
                "source": r.get("source", "?"), "window": r.get("window")
            })

    paper_drops, paper_mixed = [], []
    for ticker, cfg in paper.items():
        r = paper_results.get(ticker, {})
        pct = r.get("pct_change")
        if pct is not None and pct <= cfg["drop_pct"]:
            paper_drops.append({"ticker": ticker, "desc": cfg.get("desc", ticker),
                                 "pct": pct, "threshold": cfg["drop_pct"],
                                 "source": r.get("source", "?"), "window": r.get("window")})
        elif pct is not None:
            paper_mixed.append({"ticker": ticker, "pct": pct})

    commodity_firing = len(commodity_spikes) >= active_threshold
    paper_confirming = len(paper_drops) >= len(paper)
    paper_partial    = len(paper_drops) >= 1

    if commodity_firing and paper_confirming:
        flag    = "SPECULATOR_ROTATION_ACTIVE"
        summary = (f"{len(commodity_spikes)} commodities spiking, "
                   f"all {len(paper_drops)} paper assets dropping. "
                   "Classic rotation mechanic confirmed.")
    elif commodity_firing and paper_partial:
        flag    = "ROTATION_BUILDING"
        summary = (f"{len(commodity_spikes)} commodities spiking, "
                   f"partial paper pressure ({len(paper_drops)}/{len(paper)}). "
                   "Monitor — rotation may be developing.")
    elif len(commodity_spikes) == 1 and paper_confirming:
        flag    = "ROTATION_BUILDING"
        summary = "Single commodity spike with broad paper selling. Possible early-stage rotation."
    else:
        flag    = "NORMAL"
        summary = "No rotation signal detected."

    return {
        "rotation_override": flag,
        "summary": summary,
        "commodity_spikes": commodity_spikes,
        "paper_drops": paper_drops,
        "paper_mixed": paper_mixed,
        "commodities_assessed": len(commodity_results),
        "paper_assessed": len(paper_results),
    }


# ─────────────────────────────────────────────
# JSON PATCHER
# ─────────────────────────────────────────────

def patch_macro_json(rotation_detail: dict) -> bool:
    if not MACRO_JSON_PATH.exists():
        print(f"[RRF] ❌ Macro JSON not found at: {MACRO_JSON_PATH}")
        return False
    try:
        with open(MACRO_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["rotation_override"]       = rotation_detail["rotation_override"]
        data["rotation_flag_as_of_utc"] = datetime.now(timezone.utc).isoformat()
        data["rotation_detail"]         = rotation_detail
        receipt = write_authoritative_macro(
            MACRO_JSON_PATH,
            data,
            macro_projection_paths(REPOSITORY_ROOT),
        )
        print(
            "[RRF] ✅ Published rotation patch to all macro projections "
            f"({receipt['sha256'][:16]})"
        )

        return True
    except Exception as e:
        print(f"[RRF] ❌ Failed to patch macro JSON: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run():
    print("=" * 60)
    print("  AVSHUNTER — Rapid Rotation Flag (RRF) v2.0")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)

    colab_available = COLAB_DROP_DIR.exists() and any(COLAB_DROP_DIR.glob("*.csv"))
    print(f"\n  Colab CSVs: {'✅ Found — using futures data' if colab_available else '⚠️  Not found — using Polygon ETF fallback'}")

    print("\n[1/3] Fetching commodity signals...")
    commodity_results = {}
    for ticker, cfg in COMMODITY_FUTURES.items():
        r = fetch_commodity(ticker, cfg)
        commodity_results[ticker] = r
        pct_str = f"{r['pct_change']:+.2f}%" if r["pct_change"] is not None else "N/A"
        src     = f"[{r.get('source','?')}]"
        icon    = "✅" if r["status"] == "OK" else "⚠️ "
        print(f"  {icon} {ticker:8s}  {pct_str:>8s}   {cfg['desc']:25s} {src}")

    print("\n[2/3] Fetching paper asset signals...")
    paper_results = {}
    for ticker, cfg in PAPER_TICKERS.items():
        r = fetch_paper(ticker)
        paper_results[ticker] = r
        pct_str = f"{r['pct_change']:+.2f}%" if r["pct_change"] is not None else "N/A"
        src     = f"[{r.get('source','?')}]"
        icon    = "✅" if r["status"] == "OK" else "⚠️ "
        print(f"  {icon} {ticker:8s}  {pct_str:>8s}   {cfg['desc']:25s} {src}")

    print("\n[3/3] Assessing rotation signal...")
    result = assess_rotation(commodity_results, paper_results)

    flag  = result["rotation_override"]
    icons = {"SPECULATOR_ROTATION_ACTIVE": "🔴", "ROTATION_BUILDING": "🟡", "NORMAL": "🟢"}
    icon  = icons.get(flag, "⚪")

    print(f"\n  {icon} ROTATION FLAG: {flag}")
    print(f"  📋 {result['summary']}")

    if result["commodity_spikes"]:
        print("\n  COMMODITY SPIKES:")
        for s in result["commodity_spikes"]:
            print(f"    → {s['ticker']} ({s['desc']}): {s['pct']:+.2f}%  "
                  f"[threshold: +{s['threshold']}%]  source={s['source']}")

    if result["paper_drops"]:
        print("\n  PAPER DROPS:")
        for d in result["paper_drops"]:
            print(f"    → {d['ticker']} ({d['desc']}): {d['pct']:+.2f}%  "
                  f"[threshold: {d['threshold']}%]")

    print(f"\n  Patching: {MACRO_JSON_PATH}")
    success = patch_macro_json(result)
    print("  ✅ Macro JSON updated." if success else "  ❌ Patch failed.")

    print("\n" + "=" * 60)
    return flag


if __name__ == "__main__":
    flag = run()
    exit_codes = {"SPECULATOR_ROTATION_ACTIVE": 2, "ROTATION_BUILDING": 1, "NORMAL": 0}
    sys.exit(exit_codes.get(flag, 0))
