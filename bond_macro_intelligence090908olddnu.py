"""
bond_macro_intelligence.py
==========================
AVSHUNTER - Bond & Fixed Income Macro Intelligence Layer
Location: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\bond_macro_intelligence.py

Implements four fixed income signals derived from the institutional fixed income
curriculum (Days 1-6) mapped against AVSHUNTER pipeline gaps:

  Signal 1 — Treasury Auction Calendar
    Flags known US Treasury auction days (2Y/5Y/7Y/10Y/30Y).
    On auction days, option spreads widen — breakeven must be adjusted.

  Signal 2 — Yield Curve State (2Y/10Y spread)
    Classifies curve as STEEP / NORMAL / FLAT / INVERTED / DISINVERTING.
    DISINVERTING = earliest signal of rate-cut cycle = Russell/small-cap tailwind.
    Source: FRED API (free, no key required).

  Signal 3 — ZN Futures Direction (10Y Treasury Note Futures)
    Real-time rate regime proxy. ZN rising = yields falling = easing bias.
    ZN falling = yields rising = tightening = headwind for growth/tech.
    Source: Polygon API (existing AVSHUNTER key).

  Signal 4 — HYG/LQD Credit Stress (rolling z-score)
    HYG (high yield) / LQD (investment grade) ratio on 20-day z-score.
    Widening ratio precedes equity drawdowns by 3-10 days.
    Source: Polygon API (existing AVSHUNTER key).

Output JSON schema:
{
  "generated_at": "2026-05-20T09:45:00",
  "as_of_date": "2026-05-20",
  "auction": {
    "auction_today": false,
    "auction_window": false,
    "tenors_today": [],
    "spread_risk_flag": false,
    "breakeven_adjustment_pct": 0.0,
    "note": ""
  },
  "yield_curve": {
    "yield_2y": 4.85,
    "yield_10y": 4.42,
    "spread_bps": -43.0,
    "curve_state": "INVERTED",
    "curve_delta_7d_bps": 12.0,
    "disinverting": false,
    "regime_implication": "Recession risk elevated. Favour defensive, domestic-revenue names.",
    "russell_tailwind": false,
    "data_source": "FRED"
  },
  "zn_futures": {
    "zn_close": 109.25,
    "zn_sma5": 108.90,
    "zn_sma20": 108.10,
    "zn_direction": "BULLISH",
    "zn_5d_trend": "RISING",
    "rate_regime_signal": "EASING_BIAS",
    "regime_implication": "Yields falling. Tailwind for growth/tech calls.",
    "data_source": "Polygon"
  },
  "credit_stress": {
    "hyg_close": 79.10,
    "lqd_close": 108.30,
    "hyg_lqd_ratio": 0.7304,
    "ratio_zscore_20d": 1.2,
    "stress_level": "ELEVATED",
    "credit_warning": false,
    "credit_alert": false,
    "regime_implication": "Credit spreads within normal range.",
    "data_source": "Polygon"
  },
  "composite": {
    "macro_bond_score": 62,
    "trade_go": true,
    "primary_warning": "",
    "breakeven_adjustment_pct": 0.0,
    "morning_manifest_flag": "BOND_MACRO_OK",
    "summary": "Curve inverted but stabilising. ZN bullish. Credit normal. No auction today."
  }
}

Usage:
  python bond_macro_intelligence.py
  python bond_macro_intelligence.py --verbose
  python bond_macro_intelligence.py --dry-run
  python bond_macro_intelligence.py --output-path /custom/path/bond_macro_state.json
  python bond_macro_intelligence.py --date 2026-05-15

Integration with pipeline:
  - Run after build_macro_json.py, before rapid_rotation_flag.py
  - Output file: market_data/bond_macro_state.json
  - Morning validator reads bond_macro_state.json and applies:
      * spread_risk_flag  -> widens breakeven by breakeven_adjustment_pct
      * credit_alert      -> suppresses EXECUTE verdicts (EXECUTE_WITH_CAUTION only)
      * macro_bond_score  -> feeds into morning manifest header

Dependencies:
  pip install requests pandas numpy  (all already in AVSHUNTER environment)

FRED API:   Free. No key required for CSV endpoint used here.
Polygon:    Uses POLYGON_API_KEY env var (already configured in AVSHUNTER).
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
import numpy as np
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta, date
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bond_macro_intelligence")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POLYGON_API_KEY = os.environ.get(
    "POLYGON_API_KEY",
    "***REDACTED_POLYGON_API_KEY***"
)

FRED_CSV_URL    = "https://fred.stlouisfed.org/graph/fredgraph.csv"
POLYGON_AGG_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"

DEFAULT_OUTPUT_PATH = os.path.join(
    os.path.expanduser("~"),
    "AVSHUNTER-Intelligence", "dropbox", "macro", "bond_macro_state.json"
)

# FRED series identifiers
FRED_YIELD_2Y  = "DGS2"    # 2-Year Treasury Constant Maturity Rate
FRED_YIELD_10Y = "DGS10"   # 10-Year Treasury Constant Maturity Rate

# Yield curve classification (basis points)
CURVE_STEEP_THRESHOLD    = 150   # > 150bps = steep (recovery/expansion)
CURVE_NORMAL_HIGH        = 150
CURVE_NORMAL_LOW         =  50   # 50-150bps = normal
CURVE_FLAT_THRESHOLD     =  50   # 0-50bps = flat
CURVE_INVERTED_THRESHOLD =   0   # < 0bps = inverted

# Disinversion trigger: was inverted, now improving by at least this much in 7 days
DISINVERT_DELTA_THRESHOLD = 10   # bps improvement over 7 days

# Credit stress thresholds (z-score of HYG/LQD ratio, 20-day window)
CREDIT_WARN_ZSCORE  = 1.5
CREDIT_ALERT_ZSCORE = 2.5

# Breakeven adjustments triggered by spread risk
BREAKEVEN_ADJ_AUCTION     = 12.0   # % wider on auction day
BREAKEVEN_ADJ_AUCTION_WIN =  6.0   # % wider in auction window (day before/after)
BREAKEVEN_ADJ_CREDIT_WARN =  8.0   # % wider on credit warning
BREAKEVEN_ADJ_CREDIT_ALERT = 15.0  # % wider on credit alert

# ZN lookback for SMA calculations
ZN_SMA_SHORT  =  5
ZN_SMA_LONG   = 20
ZN_LOOKBACK   = 30   # calendar days to fetch

# HYG/LQD lookback for z-score
CREDIT_LOOKBACK = 40  # calendar days (need >20 trading days)

# ---------------------------------------------------------------------------
# Treasury Auction Calendar
# ---------------------------------------------------------------------------
# US Treasury publishes its auction schedule quarterly.
# Pattern: 2Y, 5Y, 7Y auction in the last full week of each month (Tue/Wed/Thu).
# 10Y auctions: monthly reopenings, new issue in Feb/May/Aug/Nov (second week).
# 30Y auctions: Feb/May/Aug/Nov (second week, day after 10Y).
# This implementation uses known weekday patterns as a reliable approximation.
# For production accuracy, fetch from: https://home.treasurydirect.gov/TA_WS/securities/upcoming

# B-01 (P0): the weekday heuristic below had THREE faults, all confirmed on the
# 2026-08-08 run:
#   1. The 3Y note is not in it at all — Tuesday 11 Aug ($58bn) was invisible.
#   2. The window is +/- ONE CALENDAR DAY, so auctions on 11/12/13 Aug were
#      unreachable from an 8 Aug run. auction_window can never warn in advance.
#   3. long_end_auction reads tenors_today only, so it cannot flag a long-end
#      auction that is IN the window.
# Net effect: the packet asserted "No auction activity today" for a week
# carrying $125bn of refunding including a $25bn 30Y.
#
# The module's own comment already named the fix. It is now implemented.
AUCTION_WINDOW_DAYS   = 5          # forward-looking, configurable
TREASURY_UPCOMING_URL = "https://home.treasurydirect.gov/TA_WS/securities/upcoming"
TREASURY_TIMEOUT      = 20
AUCTION_CALENDAR_CSV  = "auction_calendar.csv"   # consumed by macro_module v2.6
LONG_END_TENORS       = ("10Y", "20Y", "30Y")

# Retained ONLY as a last-resort fallback when TreasuryDirect is unreachable.
# Marked in the output as schedule_source=HEURISTIC_FALLBACK so a consumer can
# tell a real calendar from a pattern guess.
AUCTION_SCHEDULE = [
    {"tenor": "2Y",  "months": "all",         "week_of_month": 4, "weekday": 1},
    {"tenor": "3Y",  "months": "all",         "week_of_month": 2, "weekday": 1},  # was MISSING
    {"tenor": "5Y",  "months": "all",         "week_of_month": 4, "weekday": 2},
    {"tenor": "7Y",  "months": "all",         "week_of_month": 4, "weekday": 3},
    {"tenor": "10Y", "months": "all",         "week_of_month": 2, "weekday": 2},
    {"tenor": "30Y", "months": [2, 5, 8, 11], "week_of_month": 2, "weekday": 3},
]


def _normalise_tenor(term: str) -> Optional[str]:
    """TreasuryDirect returns e.g. '10-Year', '30-Year', '4-Week'. Map to tenor."""
    if not term:
        return None
    t = str(term).upper().replace(" ", "")
    for n in ("2", "3", "5", "7", "10", "20", "30"):
        if t.startswith(f"{n}-YEAR") or t.startswith(f"{n}YEAR"):
            return f"{n}Y"
    return None


def fetch_treasury_calendar(timeout: int = TREASURY_TIMEOUT) -> Tuple[list, str]:
    """
    Upcoming auctions from TreasuryDirect. Returns (rows, source).

    rows: [{"date": date, "tenor": "10Y", "type": "Note", "offering_usd_bn": float|None}]
    source: TREASURYDIRECT | HEURISTIC_FALLBACK
    """
    try:
        r = requests.get(TREASURY_UPCOMING_URL, timeout=timeout,
                         headers={"User-Agent": "AVSHUNTER/bond-macro-2.0"})
        if r.status_code != 200:
            log.warning(f"TreasuryDirect HTTP {r.status_code} — heuristic fallback")
            return [], "HEURISTIC_FALLBACK"
        payload = r.json()
    except Exception as e:
        # Retry once: TreasuryDirect intermittently refuses the first TLS
        # handshake from some networks. Report the concrete reason rather than
        # just the exception class, so a proxy/DNS issue is distinguishable
        # from the endpoint being down.
        try:
            time.sleep(2)
            r = requests.get(TREASURY_UPCOMING_URL, timeout=timeout,
                             headers={"User-Agent": "Mozilla/5.0 (AVSHUNTER bond-macro/2.0)"})
            if r.status_code == 200:
                payload = r.json()
            else:
                raise RuntimeError(f"HTTP {r.status_code}")
        except Exception as e2:
            log.warning(f"TreasuryDirect unreachable ({type(e).__name__}: {e}) — "
                        f"retry also failed ({type(e2).__name__}) — heuristic fallback")
            log.warning(f"  Check reachability: curl -I {TREASURY_UPCOMING_URL}")
            return [], "HEURISTIC_FALLBACK"

    rows = []
    for item in payload if isinstance(payload, list) else []:
        tenor = _normalise_tenor(item.get("securityTerm"))
        if tenor is None:
            continue          # bills and TIPS are not the supply risk we gate on
        raw = item.get("auctionDate") or item.get("issueDate")
        if not raw:
            continue
        try:
            adate = pd.to_datetime(raw).date()
        except Exception:
            continue
        amt = item.get("offeringAmount")
        try:
            amt = float(amt) / 1e9 if amt not in (None, "") else None
        except (TypeError, ValueError):
            amt = None
        rows.append({"date": adate, "tenor": tenor,
                     "type": item.get("securityType"), "offering_usd_bn": amt})
    if not rows:
        log.warning("TreasuryDirect returned no coupon auctions — heuristic fallback")
        return [], "HEURISTIC_FALLBACK"
    return sorted(rows, key=lambda x: x["date"]), "TREASURYDIRECT"

def _staleness(as_of: Optional[str]) -> Optional[int]:
    """Sessions between an observation date and today (weekend-aware, holiday-blind)."""
    if not as_of:
        return None
    try:
        d0, d1 = pd.to_datetime(as_of).date(), date.today()
        return int(np.busday_count(d0, d1)) if d1 > d0 else 0
    except Exception:
        return None


def _quality(as_of: Optional[str]) -> str:
    n = _staleness(as_of)
    if n is None:
        return "UNKNOWN"
    return "FRESH" if n <= 1 else "STALE_1D" if n == 2 else "STALE_MULTI"


def get_week_of_month(d: date) -> int:
    """Return the week number within the month (1 = first week)."""
    first_weekday = d.replace(day=1).weekday()
    return (d.day + first_weekday - 1) // 7 + 1


def check_treasury_auction(target_date: Optional[date] = None) -> dict:
    """
    Determine whether target_date is a Treasury auction day or auction window.
    Returns auction metadata dict for inclusion in bond_macro_state.json.

    An 'auction window' is the day before or after an auction day — spreads
    are still elevated as dealers position ahead of / unwind after supply.
    """
    if target_date is None:
        target_date = date.today()

    rows, source = fetch_treasury_calendar()
    horizon = target_date + timedelta(days=AUCTION_WINDOW_DAYS)

    if source == "TREASURYDIRECT":
        today_rows  = [r for r in rows if r["date"] == target_date]
        window_rows = [r for r in rows if target_date < r["date"] <= horizon]
    else:
        # Fallback: same weekday pattern, but scanned across the FORWARD window
        # rather than +/- one day, and including the 3Y.
        today_rows, window_rows = [], []
        for offset in range(0, AUCTION_WINDOW_DAYS + 1):
            d = target_date + timedelta(days=offset)
            for a in AUCTION_SCHEDULE:
                months = a["months"]
                if months != "all" and d.month not in months:
                    continue
                if (get_week_of_month(d) == a["week_of_month"]
                        and d.weekday() == a["weekday"]):
                    row = {"date": d, "tenor": a["tenor"], "type": "Note/Bond",
                           "offering_usd_bn": None}
                    (today_rows if offset == 0 else window_rows).append(row)

    tenors_today  = [r["tenor"] for r in today_rows]
    tenors_window = [f"{r['tenor']}@{r['date'].isoformat()}" for r in window_rows]

    auction_today  = len(today_rows) > 0
    auction_window = len(window_rows) > 0

    # B-01 fault 3: long-end status must consider the WINDOW, not just today.
    long_end_today  = any(r["tenor"] in LONG_END_TENORS for r in today_rows)
    long_end_window = any(r["tenor"] in LONG_END_TENORS for r in window_rows)
    next_long_end   = next((r["date"] for r in (today_rows + window_rows)
                            if r["tenor"] in LONG_END_TENORS), None)

    total_bn = sum(r["offering_usd_bn"] or 0.0 for r in (today_rows + window_rows))

    if auction_today:
        adjustment = BREAKEVEN_ADJ_AUCTION + (5.0 if long_end_today else 0.0)
        note = f"AUCTION DAY: {', '.join(tenors_today)}. Spreads elevated. Breakeven +{adjustment:.0f}%."
    elif auction_window:
        adjustment = BREAKEVEN_ADJ_AUCTION_WIN
        note = (f"AUCTION WINDOW ({AUCTION_WINDOW_DAYS}d): {', '.join(tenors_window)}. "
                f"Breakeven +{adjustment:.0f}%.")
    else:
        adjustment = 0.0
        note = f"No coupon auction within {AUCTION_WINDOW_DAYS} days."

    if source == "HEURISTIC_FALLBACK":
        note += " [schedule from weekday heuristic, not TreasuryDirect]"

    return {
        "auction_today":             auction_today,
        "auction_window":            auction_window,
        "auction_window_days":       AUCTION_WINDOW_DAYS,
        "tenors_today":              tenors_today,
        "tenors_window":             tenors_window,
        "long_end_auction":          long_end_today or long_end_window,
        "long_end_today":            long_end_today,
        "long_end_in_window":        long_end_window,
        "days_to_next_long_end":     (next_long_end - target_date).days if next_long_end else None,
        "total_offering_usd_bn":     round(total_bn, 1) if total_bn else None,
        "schedule_source":           source,
        "spread_risk_flag":          auction_today or auction_window,
        "breakeven_adjustment_pct":  adjustment,
        "calendar_rows":             [{"date": r["date"].isoformat(), "tenor": r["tenor"],
                                       "type": r["type"], "offering_usd_bn": r["offering_usd_bn"]}
                                      for r in (today_rows + window_rows)],
        "note":                      note,
    }


# ---------------------------------------------------------------------------
# Yield Curve State (FRED)
# ---------------------------------------------------------------------------

def fetch_fred_series(series_id: str, lookback_days: int = 30) -> Optional[pd.Series]:
    """
    Fetch a FRED time series as a pandas Series (date index, float values).
    Uses FRED's free CSV endpoint — no API key required.
    Returns None on any fetch or parse failure.
    """
    start = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end   = date.today().strftime("%Y-%m-%d")
    url   = f"{FRED_CSV_URL}?id={series_id}&vintage_date={end}"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        # Read without assuming column names — FRED occasionally changes header casing
        df = pd.read_csv(StringIO(resp.text), na_values=[".", ""])
        # Normalise column names to upper
        df.columns = [c.strip().upper() for c in df.columns]
        # Find date column (DATE, Unnamed, or first string-like column)
        date_col = None
        for c in df.columns:
            if "DATE" in c or c == df.columns[0]:
                date_col = c
                break
        if date_col is None:
            raise ValueError("Cannot identify date column in FRED response")
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).set_index(date_col)
        series = df.iloc[:, 0].dropna().astype(float)
        # Return only recent window
        cutoff = pd.Timestamp(date.today() - timedelta(days=lookback_days))
        return series[series.index >= cutoff]
    except Exception as exc:
        log.warning(f"FRED fetch failed for {series_id}: {exc}")
        return None


def classify_curve(spread_bps: float, delta_7d_bps: float) -> tuple:
    """
    Classify yield curve shape and return (state_str, disinverting_bool, implication_str).

    spread_bps   : current 10Y - 2Y spread in basis points
    delta_7d_bps : change in spread over last 7 trading days (positive = steepening)
    """
    was_inverted    = (spread_bps - delta_7d_bps) < 0
    disinverting    = was_inverted and spread_bps > (spread_bps - delta_7d_bps) + DISINVERT_DELTA_THRESHOLD

    if spread_bps > CURVE_STEEP_THRESHOLD:
        state = "STEEP"
        impl  = "Steep curve: recovery/expansion bias. Cyclicals, small caps, financials favoured."
    elif spread_bps > CURVE_FLAT_THRESHOLD:
        state = "NORMAL"
        impl  = "Normal curve: balanced regime. Standard signal scoring applies."
    elif spread_bps >= CURVE_INVERTED_THRESHOLD:
        state = "FLAT"
        impl  = "Flat curve: late-cycle signal. Reduce risk-on exposure. Prefer defensives."
    else:
        state = "INVERTED"
        impl  = "Inverted curve: recession risk elevated. Favour defensive, domestic-revenue names. Suppress growth/tech longs."

    if disinverting:
        state = "DISINVERTING"
        impl  = ("Curve disinverting: earliest signal of rate-cut cycle beginning. "
                 "Russell 2000 / small cap CALL setups gaining tailwind. Monitor closely.")

    russell_tailwind = state in ("STEEP", "DISINVERTING")

    return state, disinverting, impl, russell_tailwind


def get_yield_curve_state(verbose: bool = False) -> dict:
    """
    Fetch 2Y and 10Y yields from FRED, compute spread, classify curve state.
    Returns yield curve dict for bond_macro_state.json.
    """
    log.info("Fetching yield curve data from FRED...")
    s_2y  = fetch_fred_series(FRED_YIELD_2Y,  lookback_days=30)
    s_10y = fetch_fred_series(FRED_YIELD_10Y, lookback_days=30)

    if s_2y is None or s_10y is None or s_2y.empty or s_10y.empty:
        # Attempt fallback: read t2y/t10y from macro_intelligence_latest.json
        try:
            macro_path = os.path.join(os.path.dirname(DEFAULT_OUTPUT_PATH), "macro_intelligence_latest.json")
            if os.path.exists(macro_path):
                with open(macro_path, "r", encoding="utf-8") as _f:
                    _macro = json.load(_f)
                _t2y  = _macro.get("extras", {}).get("rates", {}).get("t2y")
                _t10y = _macro.get("extras", {}).get("rates", {}).get("t10y")
                if _t2y is not None and _t10y is not None:
                    _spread_bps = (float(_t10y) - float(_t2y)) * 100
                    _state, _disinv, _impl, _rtw = classify_curve(_spread_bps, 0.0)
                    log.warning(
                        f"FRED unavailable — falling back to macro JSON yields "
                        f"(2Y={_t2y}, 10Y={_t10y}, spread={_spread_bps:+.1f}bps)"
                    )
                    return {
                        "yield_2y":           float(_t2y),
                        "yield_10y":          float(_t10y),
                        "spread_bps":         round(_spread_bps, 1),
                        "curve_state":        _state,
                        "curve_delta_7d_bps": None,
                        "disinverting":       _disinv,
                        "russell_tailwind":   _rtw,
                        "regime_implication": _impl,
                        "as_of_date":         _macro.get("report_date", "unknown"),
                        "data_source":        "MACRO_JSON_FALLBACK",
                        "fetch_error":        True,
                    }
        except Exception as _fb_exc:
            log.warning(f"Macro JSON fallback also failed: {_fb_exc}")

        log.error("Yield curve fetch failed — returning UNKNOWN state.")
        return {
            "yield_2y":          None,
            "yield_10y":         None,
            "spread_bps":        None,
            "curve_state":       "UNKNOWN",
            "curve_delta_7d_bps": None,
            "disinverting":      False,
            "russell_tailwind":  False,
            "regime_implication": "Yield curve data unavailable. Manual check required.",
            "data_source":       "FRED",
            "fetch_error":       True,
        }

    # Align on common dates
    common = s_2y.index.intersection(s_10y.index)
    s_2y   = s_2y.reindex(common).ffill()
    s_10y  = s_10y.reindex(common).ffill()

    yield_2y_now  = float(s_2y.iloc[-1])
    yield_10y_now = float(s_10y.iloc[-1])
    spread_now    = (yield_10y_now - yield_2y_now) * 100  # convert to bps

    # 7-day delta (approximately 5 trading days back)
    idx_7d = max(0, len(common) - 6)
    yield_2y_7d   = float(s_2y.iloc[idx_7d])
    yield_10y_7d  = float(s_10y.iloc[idx_7d])
    spread_7d     = (yield_10y_7d - yield_2y_7d) * 100
    delta_7d      = spread_now - spread_7d

    curve_state, disinverting, impl, russell_tw = classify_curve(spread_now, delta_7d)

    # B-07 (P1): the packet carried only 2s10s. The 30Y — the tenor Thursday's
    # auction hits — was absent entirely, and so was the DIRECTION of travel.
    # Level cannot distinguish "policy easing priced" (bull steepening) from
    # "term premium / supply shock" (bear steepening). They imply opposite trades.
    yield_30y_now, spread_10s30s = None, None
    try:
        s_30y = fetch_fred_series("DGS30", lookback_days=30)
        if s_30y is not None and len(s_30y):
            yield_30y_now = round(float(s_30y.reindex(common).ffill().iloc[-1]), 3)
            spread_10s30s = round((yield_30y_now - yield_10y_now) * 100, 1)
    except Exception as e:
        log.warning(f"DGS30 unavailable ({type(e).__name__}) — long end not measured")

    def _move(n):
        if len(common) <= n:
            return "UNKNOWN", None
        d2 = (float(s_2y.iloc[-1]) - float(s_2y.iloc[-1 - n])) * 100
        d10 = (float(s_10y.iloc[-1]) - float(s_10y.iloc[-1 - n])) * 100
        if d2 < 0 and d10 < 0:
            lbl = "BULL_STEEPENING" if abs(d2) > abs(d10) else "BULL_FLATTENING"
        elif d2 > 0 and d10 > 0:
            lbl = "BEAR_FLATTENING" if abs(d2) > abs(d10) else "BEAR_STEEPENING"
        else:
            lbl = "TWIST"
        return lbl, {"d2y_bp": round(d2, 1), "d10y_bp": round(d10, 1)}

    move_1d, detail_1d = _move(1)
    move_5d, detail_5d = _move(5)

    as_of = common[-1].strftime("%Y-%m-%d")

    if verbose:
        log.info(f"  2Y yield:        {yield_2y_now:.3f}%")
        log.info(f"  10Y yield:       {yield_10y_now:.3f}%")
        log.info(f"  Spread:          {spread_now:+.1f} bps")
        log.info(f"  7d delta:        {delta_7d:+.1f} bps")
        log.info(f"  Curve state:     {curve_state}")
        log.info(f"  Russell tw:      {russell_tw}")

    return {
        "yield_2y":           round(yield_2y_now, 3),
        "yield_10y":          round(yield_10y_now, 3),
        "spread_bps":         round(spread_now, 1),
        "yield_30y":          yield_30y_now,
        "spread_10s30s_bps":  spread_10s30s,
        "curve_move_1d":      move_1d,
        "curve_move_1d_detail": detail_1d,
        "curve_move_5d":      move_5d,
        "curve_move_5d_detail": detail_5d,
        "curve_state":        curve_state,
        "curve_delta_7d_bps": round(delta_7d, 1),
        "disinverting":       disinverting,
        "russell_tailwind":   russell_tw,
        "regime_implication": impl,
        "as_of_date":         as_of,
        "staleness_sessions": _staleness(as_of),
        "stale_flag":         (_staleness(as_of) or 0) > 1,
        "data_quality":       _quality(as_of),
        "data_source":        "FRED",
        "fetch_error":        False,      # call succeeded; see stale_flag for freshness
    }


# ---------------------------------------------------------------------------
# ZN Futures Direction (Polygon)
# ---------------------------------------------------------------------------

def fetch_polygon_ohlcv(ticker: str, lookback_days: int = 35) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV bars from Polygon for a given ticker.
    Returns DataFrame with columns [open, high, low, close, volume] indexed by date.
    Returns None on failure.

    Note: Futures tickers on Polygon use format I:ZNc1 (continuous front month).
    Equities use standard ticker (HYG, LQD).
    """
    end_date   = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    url = POLYGON_AGG_URL.format(
        ticker    = ticker,
        from_date = start_date.strftime("%Y-%m-%d"),
        to_date   = end_date.strftime("%Y-%m-%d"),
    )

    try:
        resp = requests.get(
            url,
            params={"adjusted": "true", "sort": "asc", "limit": 50,
                    "apiKey": POLYGON_API_KEY},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("resultsCount", 0) == 0 or "results" not in data:
            log.warning(f"No Polygon data for {ticker}: {data.get('message', 'empty results')}")
            return None

        df = pd.DataFrame(data["results"])
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date
        df = df.set_index("date").rename(columns={
            "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
        })[["open", "high", "low", "close", "volume"]]
        return df

    except Exception as exc:
        log.warning(f"Polygon fetch failed for {ticker}: {exc}")
        return None


def _yields_rising_recent(lookback: int = 5) -> Optional[bool]:
    """
    True when DGS10 has RISEN over the lookback. Returns None when unavailable —
    unknown must not be read as 'not rising'.
    """
    try:
        s = fetch_fred_series("DGS10", lookback_days=lookback * 6)
        if s is None or len(s) <= lookback:
            return None
        return bool(float(s.iloc[-1]) > float(s.iloc[-1 - lookback]))
    except Exception as e:
        log.warning(f"DGS10 gate unavailable ({type(e).__name__}) — regime label ungated")
        return None


def get_zn_direction(verbose: bool = False) -> dict:
    """
    Fetch ZN (10Y Treasury Note Futures) daily bars from Polygon.
    Compute SMA5 and SMA20, classify direction and rate regime signal.

    Polygon continuous futures ticker: I:ZNc1
    """
    log.info("Fetching ZN futures data from Polygon...")

    # Try continuous contract first, fall back to the ZN equity proxy (IEF)
    df = fetch_polygon_ohlcv("I:ZNc1", lookback_days=ZN_LOOKBACK)
    ticker_used = "I:ZNc1"

    if df is None or len(df) < ZN_SMA_SHORT:
        log.warning("ZN continuous contract unavailable — falling back to IEF (ZN proxy).")
        df = fetch_polygon_ohlcv("IEF", lookback_days=ZN_LOOKBACK)
        # B-03 (P0): TLT is the ZB (30Y bond) proxy, not ZN. The module's own
        # bonds_etf mapping says so: TLT [proxy: ZB=F], IEF [proxy: ZN=F].
        # TLT carries ~17y duration standing in for a ~6.5y note future.
        ticker_used = "IEF (ZN proxy)"

    if df is None or len(df) < ZN_SMA_SHORT:
        log.error("ZN/IEF fetch failed — returning UNKNOWN state.")
        return {
            "ticker_used":        "UNAVAILABLE",
            "zn_close":           None,
            "zn_sma5":            None,
            "zn_sma20":           None,
            "zn_direction":       "UNKNOWN",
            "sma_agreement":      "UNAVAILABLE",
            "zn_5d_trend":        "UNKNOWN",
            "rate_regime_signal": "UNKNOWN",
            "regime_implication": "ZN data unavailable. Manual rate check required.",
            "data_source":        "Polygon",
            "fetch_error":        True,
        }

    closes = df["close"]
    zn_now = float(closes.iloc[-1])

    sma5  = float(closes.tail(ZN_SMA_SHORT).mean())
    sma20 = float(closes.tail(min(ZN_SMA_LONG, len(closes))).mean()) if len(closes) >= ZN_SMA_LONG else None

    # B-02 (P0): sma20 was computed here, emitted to JSON, and NEVER USED in the
    # decision. On 2026-08-08 close 82.76 was above sma5 82.658 but 0.75% BELOW
    # sma20 83.3805 — a counter-trend bounce beneath a falling 20-day, labelled
    # BULLISH. Requiring agreement is a one-line change to an already-computed
    # value. Note also that sma5 is the mean of the last five closes INCLUDING
    # the current bar, so `close > sma5` is true on almost any up day.
    if sma20 is None:
        direction = "BULLISH" if zn_now > sma5 else "BEARISH" if zn_now < sma5 * 0.998 else "NEUTRAL"
        sma_agreement = "SMA20_UNAVAILABLE"
    elif zn_now > sma5 and zn_now > sma20:
        direction, sma_agreement = "BULLISH", "BOTH_ABOVE"
    elif zn_now < sma5 and zn_now < sma20:
        direction, sma_agreement = "BEARISH", "BOTH_BELOW"
    elif zn_now > sma5 and zn_now < sma20:
        direction, sma_agreement = "COUNTERTREND_BOUNCE", "ABOVE_SMA5_BELOW_SMA20"
    else:
        direction, sma_agreement = "PULLBACK", "BELOW_SMA5_ABOVE_SMA20"

    # 5-day trend (restored — the v2.0 patch block spanned this computation
    # and removed it, leaving `trend` referenced but never assigned).
    if len(closes) >= 6:
        trend_delta = float(closes.iloc[-1]) - float(closes.iloc[-6])
        trend = "RISING" if trend_delta > 0.05 else ("FALLING" if trend_delta < -0.05 else "FLAT")
    else:
        trend = "INSUFFICIENT_DATA"

    # B-04 (P0): gate the regime label on the ACTUAL yield series. On the
    # 2026-08-08 batch the module asserted "yields falling" while FRED showed
    # DGS2 +7bp, DGS10 +6bp and DGS30 +5bp into the 6 Aug close. An ETF proxy
    # trend may not contradict the observed curve.
    yields_rising = _yields_rising_recent()

    if direction == "BULLISH" and trend == "RISING" and not yields_rising:
        rate_signal = "EASING_BIAS"
        impl = "ZN bullish and rising: yields falling. Tailwind for growth/tech CALL setups."
    elif direction == "BEARISH" and trend == "FALLING":
        rate_signal = "TIGHTENING_BIAS"
        impl = "ZN bearish and falling: yields rising. Headwind for growth/tech. Favour financials, energy, domestic-revenue names."
    elif direction == "BULLISH":
        rate_signal = "MILD_EASING"
        impl = "ZN mildly bullish: modest easing signal. Neutral impact on candidate scoring."
    elif direction == "BEARISH":
        rate_signal = "MILD_TIGHTENING"
        impl = "ZN mildly bearish: modest tightening signal. Slight headwind for high-beta longs."
    else:
        rate_signal = "NEUTRAL"
        impl = "ZN neutral: no clear rate regime signal. Standard scoring applies."

    if verbose:
        log.info(f"  ZN ticker:       {ticker_used}")
        log.info(f"  ZN close:        {zn_now:.4f}")
        log.info(f"  ZN SMA5:         {sma5:.4f}")
        log.info(f"  ZN SMA20:        {sma20:.4f}" if sma20 else "  ZN SMA20:        insufficient data")
        log.info(f"  Direction:       {direction}")
        log.info(f"  5d trend:        {trend}")
        log.info(f"  Rate signal:     {rate_signal}")

    result = {
        "ticker_used":        ticker_used,
        "zn_close":           round(zn_now, 4),
        "zn_sma5":            round(sma5, 4),
        "zn_sma20":           round(sma20, 4) if sma20 else None,
        "zn_direction":       direction,
        "sma_agreement":      sma_agreement,
        "yields_rising_5d":   yields_rising,
        "zn_5d_trend":        trend,
        "rate_regime_signal": rate_signal,
        "regime_implication": impl,
        "data_source":        "Polygon",
        "fetch_error":        False,
    }
    return result


# ---------------------------------------------------------------------------
# HYG/LQD Credit Stress (Polygon)
# ---------------------------------------------------------------------------

def get_credit_stress(verbose: bool = False) -> dict:
    """
    Compute HYG/LQD ratio z-score over a 20-day rolling window.
    A rising ratio (HY underperforming IG) signals credit stress.
    Z-score > 1.5 = WARNING. Z-score > 2.5 = ALERT.
    """
    log.info("Fetching HYG and LQD data from Polygon for credit stress...")

    df_hyg = fetch_polygon_ohlcv("HYG", lookback_days=CREDIT_LOOKBACK)
    df_lqd = fetch_polygon_ohlcv("LQD", lookback_days=CREDIT_LOOKBACK)

    if df_hyg is None or df_lqd is None or df_hyg.empty or df_lqd.empty:
        log.error("HYG/LQD fetch failed — returning UNKNOWN credit state.")
        return {
            "hyg_close":          None,
            "lqd_close":          None,
            "hyg_lqd_ratio":      None,
            "ratio_zscore_20d":   None,
            "stress_level":       "UNKNOWN",
            "credit_warning":     False,
            "credit_alert":       False,
            "regime_implication": "Credit stress data unavailable. Manual check required.",
            "breakeven_adjustment_pct": 0.0,
            "data_source":        "Polygon",
            "fetch_error":        True,
        }

    # Align on common trading days
    common_idx = df_hyg.index.intersection(df_lqd.index)
    if len(common_idx) < 10:
        log.warning("Insufficient overlapping data for HYG/LQD z-score.")
        return {
            "hyg_close":          None,
            "lqd_close":          None,
            "hyg_lqd_ratio":      None,
            "ratio_zscore_20d":   None,
            "stress_level":       "INSUFFICIENT_DATA",
            "credit_warning":     False,
            "credit_alert":       False,
            "regime_implication": "Insufficient history for credit stress z-score.",
            "breakeven_adjustment_pct": 0.0,
            "data_source":        "Polygon",
            "fetch_error":        False,
        }

    hyg_closes = df_hyg.loc[common_idx, "close"]
    lqd_closes = df_lqd.loc[common_idx, "close"]
    ratio      = hyg_closes / lqd_closes

    # Z-score: how many std devs is current ratio from its 20-day mean?
    window     = min(20, len(ratio))
    ratio_mean = float(ratio.tail(window).mean())
    ratio_std  = float(ratio.tail(window).std())

    if ratio_std == 0 or np.isnan(ratio_std):
        zscore = 0.0
    else:
        # Note: HYG/LQD FALLING = stress (HY underperforming). Invert for intuitive sign.
        # A LOWER ratio = more stress. We report as positive zscore for widening credit spread.
        zscore = float((ratio_mean - ratio.iloc[-1]) / ratio_std)

    hyg_now = float(hyg_closes.iloc[-1])
    lqd_now = float(lqd_closes.iloc[-1])
    ratio_now = float(ratio.iloc[-1])

    # Classify
    if zscore > CREDIT_ALERT_ZSCORE:
        stress_level = "CRITICAL"
        credit_warn  = True
        credit_alert = True
        adjustment   = BREAKEVEN_ADJ_CREDIT_ALERT
        impl = (f"CREDIT ALERT (z={zscore:.2f}): HY spreads significantly wider than IG. "
                "Institutional risk-off in credit markets. Suppress EXECUTE verdicts. "
                "Only PROBE or EXECUTE_WITH_CAUTION on highest-conviction signals.")
    elif zscore > CREDIT_WARN_ZSCORE:
        stress_level = "ELEVATED"
        credit_warn  = True
        credit_alert = False
        adjustment   = BREAKEVEN_ADJ_CREDIT_WARN
        impl = (f"CREDIT WARNING (z={zscore:.2f}): HY spreads widening relative to IG. "
                f"Widen breakeven by {adjustment:.0f}%. Favour domestic/defensive names.")
    elif zscore > 0.5:
        stress_level = "MILD"
        credit_warn  = False
        credit_alert = False
        adjustment   = 0.0
        impl = f"Credit spreads mildly elevated (z={zscore:.2f}). Monitor. No adjustment required."
    else:
        stress_level = "NORMAL"
        credit_warn  = False
        credit_alert = False
        adjustment   = 0.0
        impl = f"Credit spreads normal (z={zscore:.2f}). No credit headwind detected."

    if verbose:
        log.info(f"  HYG close:       {hyg_now:.4f}")
        log.info(f"  LQD close:       {lqd_now:.4f}")
        log.info(f"  HYG/LQD ratio:   {ratio_now:.6f}")
        log.info(f"  Z-score (20d):   {zscore:.3f}")
        log.info(f"  Stress level:    {stress_level}")

    return {
        "hyg_close":               round(hyg_now, 4),
        "lqd_close":               round(lqd_now, 4),
        "hyg_lqd_ratio":           round(ratio_now, 6),
        "ratio_zscore_20d":        round(zscore, 3),
        "stress_level":            stress_level,
        "credit_warning":          credit_warn,
        "credit_alert":            credit_alert,
        "regime_implication":      impl,
        "breakeven_adjustment_pct": adjustment,
        "data_source":             "Polygon",
        "fetch_error":             False,
    }


# ---------------------------------------------------------------------------
# Composite Score & Morning Manifest Flag
# ---------------------------------------------------------------------------

def build_composite(auction: dict, yield_curve: dict,
                    zn: dict, credit: dict) -> dict:
    """
    Combine all four signals into a composite bond macro score (0-100)
    and a single morning manifest flag.

    Score interpretation:
      80-100 : Bond macro tailwind — favourable conditions for long options
      60-79  : Neutral — standard scoring applies
      40-59  : Mild headwind — tighten breakeven, prefer domestic/defensive
      20-39  : Significant headwind — execute only highest-conviction signals
      0-19   : Adverse — stand down from new longs, reassess

    Flag values (for morning_manifest header):
      BOND_MACRO_TAILWIND
      BOND_MACRO_OK
      BOND_MACRO_CAUTION
      BOND_MACRO_WARNING
      BOND_MACRO_ADVERSE
    """
    score = 70  # baseline neutral

    warnings = []
    adjustments = []

    # --- Auction impact ---
    if auction["auction_today"]:
        score -= 15
        adj = auction["breakeven_adjustment_pct"]
        warnings.append(f"Auction day ({', '.join(auction['tenors_today'])})")
        adjustments.append(adj)
    elif auction["auction_window"]:
        score -= 7
        adjustments.append(auction["breakeven_adjustment_pct"])

    # --- Yield curve impact ---
    curve_state = yield_curve.get("curve_state", "UNKNOWN")
    curve_adjustments = {
        "STEEP":        +15,
        "DISINVERTING": +10,
        "NORMAL":       +5,
        "FLAT":         -5,
        "INVERTED":     -15,
        "UNKNOWN":       0,
    }
    _curve_delta = curve_adjustments.get(curve_state, 0)
    score += _curve_delta
    # B-06 (P1): FLAT applied -5 and appended NOTHING, which is why the
    # 2026-08-08 packet reported all_warnings: [] beside a regime_implication
    # reading "Flat curve: late-cycle signal. Reduce risk-on exposure."
    # Any block applying a negative score delta must now emit a warning.
    if curve_state == "INVERTED":
        warnings.append("Yield curve inverted")
    if curve_state == "DISINVERTING":
        warnings.append("Curve disinverting — Russell/small cap tailwind building")
    if _curve_delta < 0 and not any("curve" in w.lower() for w in warnings):
        warnings.append(f"Curve {curve_state} — score {_curve_delta:+d}: "
                        f"{yield_curve.get('regime_implication', '')}".strip())
    if yield_curve.get("russell_tailwind") is False:
        warnings.append("No Russell/small-cap tailwind from the curve")

    # --- ZN direction impact ---
    rate_signal = zn.get("rate_regime_signal", "UNKNOWN")
    zn_adjustments = {
        "EASING_BIAS":      +10,
        "MILD_EASING":      +5,
        "NEUTRAL":           0,
        "MILD_TIGHTENING":  -5,
        "TIGHTENING_BIAS":  -12,
        "UNKNOWN":           0,
    }
    _zn_delta = zn_adjustments.get(rate_signal, 0)
    score += _zn_delta
    if rate_signal == "TIGHTENING_BIAS":
        warnings.append("ZN tightening bias (rising yields)")
    if _zn_delta < 0 and not any("ZN" in w for w in warnings):
        warnings.append(f"ZN {rate_signal} — score {_zn_delta:+d}")
    if zn.get("sma_agreement") == "ABOVE_SMA5_BELOW_SMA20":
        warnings.append("ZN counter-trend bounce — above SMA5 but below SMA20")
    if zn.get("yields_rising_5d") is True and "EASING" in str(rate_signal):
        warnings.append("CONTRADICTION: easing label while DGS10 rose over 5d")

    # --- Credit stress impact ---
    stress = credit.get("stress_level", "UNKNOWN")
    credit_adjustments = {
        "NORMAL":           +5,
        "MILD":              0,
        "ELEVATED":         -12,
        "CRITICAL":         -25,
        "UNKNOWN":           0,
        "INSUFFICIENT_DATA": 0,
    }
    score += credit_adjustments.get(stress, 0)
    if credit.get("credit_alert"):
        warnings.append("CREDIT ALERT — HY spreads critically elevated")
        adjustments.append(credit["breakeven_adjustment_pct"])
    elif credit.get("credit_warning"):
        warnings.append("Credit warning — HY spreads elevated")
        adjustments.append(credit["breakeven_adjustment_pct"])

    # Clamp score
    # B-05: a successful fetch of old data is not a clean read. On 2026-08-08
    # yield_curve.as_of_date was 2026-08-06 with fetch_error False, so the
    # packet reported a clean curve computed from pre-payrolls values.
    if yield_curve.get("stale_flag"):
        score -= 10
        warnings.append(f"Yield curve data STALE — as_of {yield_curve.get('as_of_date')} "
                        f"({yield_curve.get('staleness_sessions')} sessions)")
    if auction.get("schedule_source") == "HEURISTIC_FALLBACK":
        warnings.append("Auction calendar from weekday heuristic — TreasuryDirect unreachable")
    if auction.get("long_end_in_window"):
        warnings.append(f"Long-end auction within {auction.get('auction_window_days')}d "
                        f"(next in {auction.get('days_to_next_long_end')}d) — "
                        f"a benign CPI can still lift long yields on weak demand")

    score = max(0, min(100, score))

    # Max breakeven adjustment (don't stack multiplicatively)
    max_adj = max(adjustments) if adjustments else 0.0

    # Determine trade go / flag
    if score >= 80:
        flag    = "BOND_MACRO_TAILWIND"
        trade_go = True
    elif score >= 60:
        flag    = "BOND_MACRO_OK"
        trade_go = True
    elif score >= 40:
        flag    = "BOND_MACRO_CAUTION"
        trade_go = True   # proceed with caution, not a hard stop
    elif score >= 20:
        flag    = "BOND_MACRO_WARNING"
        trade_go = False  # suppress new longs
    else:
        flag    = "BOND_MACRO_ADVERSE"
        trade_go = False

    # Build summary sentence
    if not warnings:
        summary = f"Bond macro clean. Score {score}/100. No fixed income headwinds detected."
    else:
        summary = f"Score {score}/100. Flags: {'; '.join(warnings)}."
        if max_adj > 0:
            summary += f" Breakeven +{max_adj:.0f}%."

    primary_warning = warnings[0] if warnings else ""

    return {
        "macro_bond_score":          score,
        "trade_go":                  trade_go,
        "primary_warning":           primary_warning,
        "all_warnings":              warnings,
        "breakeven_adjustment_pct":  max_adj,
        "morning_manifest_flag":     flag,
        "summary":                   summary,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(target_date: Optional[date] = None,
        output_path: str = DEFAULT_OUTPUT_PATH,
        verbose: bool = False,
        dry_run: bool = False) -> dict:
    """
    Run all four bond macro intelligence signals and write output JSON.
    Returns the full state dict.
    """
    if target_date is None:
        target_date = date.today()

    log.info(f"=== Bond Macro Intelligence — {target_date} ===")

    # --- Run all four signals ---
    auction     = check_treasury_auction(target_date)
    yield_curve = get_yield_curve_state(verbose=verbose)
    zn          = get_zn_direction(verbose=verbose)
    credit      = get_credit_stress(verbose=verbose)
    composite   = build_composite(auction, yield_curve, zn, credit)

    state = {
        "generated_at":  datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "as_of_date":    target_date.strftime("%Y-%m-%d"),
        "schema_version": "2.0.0",
        "auction":       auction,
        "yield_curve":   yield_curve,
        "zn_futures":    zn,
        "credit_stress": credit,
        "composite":     composite,
    }

    # --- Output ---
    if dry_run:
        log.info("DRY RUN — output not written to disk.")
        print(json.dumps(state, indent=2))
    else:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            log.info(f"Output directory confirmed: {output_dir}")
        else:
            log.warning("Output path has no directory component — writing to current directory.")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            log.info(f"Bond macro state written: {output_path}")

            # Publish the auction calendar as a flat CSV so macro_module v2.6
            # can read the SAME calendar. One calendar, two consumers — a
            # second hardcoded copy is how two components end up disagreeing
            # about what week it is.
            try:
                rows = (state.get("auction") or {}).get("calendar_rows") or []
                cal_path = os.path.join(output_dir or ".", AUCTION_CALENDAR_CSV)
                pd.DataFrame(rows or [{"date": None, "tenor": None,
                                       "type": None, "offering_usd_bn": None}]
                             ).to_csv(cal_path, index=False)
                log.info(f"Auction calendar written: {cal_path} ({len(rows)} rows, "
                         f"source={(state.get('auction') or {}).get('schedule_source')})")
            except Exception as exc:
                log.error(f"Failed to write {AUCTION_CALENDAR_CSV}: {exc}")
        except Exception as exc:
            log.error(f"Failed to write bond_macro_state.json: {exc}")
            log.error(f"Resolved path was: {os.path.abspath(output_path)}")
            log.error("Check that the market_data folder exists at the AVSHUNTER-Intelligence root.")


    # Always print composite summary to console
    c = composite
    log.info(f"")
    log.info(f"  COMPOSITE SCORE:   {c['macro_bond_score']}/100")
    log.info(f"  FLAG:              {c['morning_manifest_flag']}")
    log.info(f"  TRADE GO:          {c['trade_go']}")
    log.info(f"  BREAKEVEN ADJ:     +{c['breakeven_adjustment_pct']:.0f}%")
    log.info(f"  SUMMARY:           {c['summary']}")
    log.info(f"")

    return state


# ---------------------------------------------------------------------------
# CLI entry point
def parse_args():
    p = argparse.ArgumentParser(
        description="AVSHUNTER Bond Macro Intelligence Layer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bond_macro_intelligence.py
  python bond_macro_intelligence.py --verbose
  python bond_macro_intelligence.py --dry-run
  python bond_macro_intelligence.py --date 2026-05-15
  python bond_macro_intelligence.py --output-path C:/custom/path/bond_macro_state.json
        """
    )
    p.add_argument(
        "--date", type=str, default=None,
        help="Target date in YYYY-MM-DD format (default: today)"
    )
    p.add_argument(
        "--output-path", type=str, default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})"
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="Print detailed signal values during fetch"
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Compute and print output without writing to disk"
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    target = None
    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            log.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)

    run(
        target_date = target,
        output_path = args.output_path,
        verbose     = args.verbose,
        dry_run     = args.dry_run,
    )