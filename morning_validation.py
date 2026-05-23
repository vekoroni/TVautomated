from __future__ import annotations

"""
AVSHUNTER — Morning Validation Engine v2.0
==========================================

Purpose
-------
This engine replaces the original Morning Validation proxy-only flow with an
end-to-end, event-aware validator.

It answers one practical question:

    "Is this structurally primed setup actually tradeable right now,
     and has the chart shifted state enough to justify entry?"

Important design clarification
------------------------------
The live pipeline does NOT have access to manually uploaded chart screenshots.
Those screenshots are useful for:
- human review,
- pipeline backtesting,
- thesis validation,
- post-mortem learning.

But an automated pipeline must validate the thesis from machine-readable data.
Therefore this validator uses live intraday bars as the chart surrogate:
- 1-minute bars
- 5-minute bars
- 15-minute bars
- live snapshot price / VWAP / volume
- live options quote

This means the pipeline can determine whether:
- support has broken,
- the break has held,
- reclaim has failed,
- price is below/above VWAP,
- volume is expanding,
- the options contract is still executable.

Architecture
------------
EOD Candidate Engine (structure only)
    -> Morning Validation Score (tradeability / economics)
    -> Trigger Confirmation Engine (event confirmation)
    -> Final decision fusion
    -> CSV + JSON outputs

Final states
------------
EXECUTE : strong tradeability + confirmed event
PROBE   : acceptable tradeability + partial/confirmed event
WATCH   : setup valid but trigger not yet live
REJECT  : hard reject, invalidated setup, or failed trigger

Notes
-----
1. This module does not reconsider EOD structure. It assumes the EOD manifest
   already identified structurally primed candidates.
2. This module does not use uploaded screenshots. If you want screenshot-driven
   validation for research, keep that in a separate backtest / lab process.
3. Trigger confirmation is sovereign over Morning Validation Score. A candidate
   can be tradeable but still not triggered.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from trigger_confirmation_engine import (
    TriggerConfirmationEngine,
    build_trigger_input_from_candidate,
    trigger_result_to_row,
)


# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MV_ENGINE_V2] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("morning_validation_v2")


# =============================================================================
# API KEYS / CONSTANTS
# =============================================================================

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "").strip()
MARKETDATA_API_KEY = os.getenv("MARKETDATA_API_KEY", "").strip()

# Morning Validation thresholds
EXECUTE_THRESHOLD = 75.0
PROBE_THRESHOLD = 50.0
WATCH_THRESHOLD = 30.0

# Trigger thresholds
TCE_EXECUTE_MIN = 75.0
TCE_PROBE_MIN = 50.0

# Drift / spread hard guards
HARD_DRIFT_REJECT = 5.0
SOFT_DRIFT_WARN = 2.5
HARD_SPREAD_REJECT = 15.0
SOFT_SPREAD_WARN = 8.0

# Fetch pacing
POLYGON_SLEEP_SNAPSHOT = 0.50
POLYGON_SLEEP_BARS = 0.35
MARKETDATA_SLEEP_QUOTE = 0.80

# Intraday bar limits
BARS_1M_LIMIT = 25
BARS_5M_LIMIT = 20
BARS_15M_LIMIT = 12


# =============================================================================
# HELPERS
# =============================================================================

def _flt(row: dict[str, Any], key: str, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        v = row.get(key, default)
        if v is None:
            return default
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _str(row: dict[str, Any], key: str, default: str = "") -> str:
    v = row.get(key, default)
    if v is None or str(v).lower() in ("nan", "none", ""):
        return default
    return str(v).strip()


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        f = float(value)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _load_dotenv_fallback(base_dir: Path) -> None:
    """Load .env if API keys are not already present in environment."""
    global POLYGON_API_KEY, MARKETDATA_API_KEY
    if POLYGON_API_KEY and MARKETDATA_API_KEY:
        return

    dotenv_paths = [
        base_dir / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in dotenv_paths:
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "POLYGON_API_KEY" and not POLYGON_API_KEY:
                    POLYGON_API_KEY = v
                elif k == "MARKETDATA_API_KEY" and not MARKETDATA_API_KEY:
                    MARKETDATA_API_KEY = v
        except Exception:
            pass
        if POLYGON_API_KEY and MARKETDATA_API_KEY:
            break


# =============================================================================
# POLYGON / MARKETDATA FETCHERS
# =============================================================================

def _marketdata_stock_quote(ticker: str) -> Optional[dict[str, Any]]:
    """
    Fetch live equity price, bid, ask, mid from MarketData.app (15-min delay).
    This is the primary price source for morning validation.
    MarketData.app supports equity quotes — do not use Polygon snapshot
    (requires higher plan tier than Stock Screener Standard).
    """
    url = f"https://api.marketdata.app/v1/stocks/quotes/{ticker}/"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {MARKETDATA_API_KEY}"},
            timeout=8,
        )
        if r.status_code not in (200, 203):
            log.info(f"  {ticker}: MarketData equity quote HTTP {r.status_code} — response: {r.text[:200]}")
            return None
        data = r.json()
        if data.get("s") != "ok":
            log.info(f"  {ticker}: MarketData equity quote status not OK: {data.get('s')} — {str(data)[:200]}")
            return None

        def _take(x: Any) -> Any:
            return x[0] if isinstance(x, list) else x

        bid    = _take(data.get("bid"))
        ask    = _take(data.get("ask"))
        mid    = _take(data.get("mid"))
        last   = _take(data.get("last"))
        volume = _take(data.get("volume"))
        change_pct = _take(data.get("changepct"))

        # Use mid as price if last not available
        price = last or mid or (((bid or 0) + (ask or 0)) / 2 if bid and ask else None)

        return {
            "price":      price,
            "bid":        bid,
            "ask":        ask,
            "mid":        mid,
            "vwap":       None,   # populated from MarketData candles downstream
            "volume":     volume,
            "prev_vol":   None,
            "open":       None,
            "high":       None,
            "low":        None,
            "change_pct": change_pct,
            "freshness":  (
                "REALTIME_IEX" if r.status_code == 200
                else ("DELAYED_15M" if r.status_code == 203 else "UNKNOWN")
            ),
        }
    except Exception as e:
        log.info(f"  {ticker}: MarketData equity quote exception — {type(e).__name__}: {e}")
        return None


def _polygon_snapshot(ticker: str) -> Optional[dict[str, Any]]:
    """
    Fetch previous-session close and volume from MarketData.app daily candles.
    Replaces Polygon /v2/aggs/ticker/{ticker}/prev endpoint.
    prev_vwap is not available from daily candles — computed from intraday bars downstream.
    """
    try:
        url = f"https://api.marketdata.app/v1/stocks/candles/D/{ticker}/"
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {MARKETDATA_API_KEY}"},
            params={"countback": "5"},
            timeout=8,
        )
        if r.status_code not in (200, 203):
            return None
        data = r.json()
        if data.get("s") != "ok" or not data.get("c"):
            return None
        closes  = data["c"]
        volumes = data.get("v", [])
        return {
            "prev_close":   float(closes[-1])  if closes  else None,
            "prev_vol":     int(volumes[-1])   if volumes else None,
            "prev_vwap":    None,
            # Raw daily arrays for B2 SOT + gap computation
            "daily_opens":  [float(v) for v in data.get("o", []) if v is not None],
            "daily_highs":  [float(v) for v in data.get("h", []) if v is not None],
            "daily_lows":   [float(v) for v in data.get("l", []) if v is not None],
            "daily_closes": [float(v) for v in closes if v is not None],
        }
    except Exception as e:
        log.debug(f"MarketData prev candle failed for {ticker}: {e}")
        return None


def _polygon_intraday_bars(ticker: str, multiplier: int = 5, limit: int = 20) -> list[dict[str, Any]]:
    """
    Fetch recent intraday OHLCV bars from MarketData.app.
    Replaces Polygon /v2/aggs/ticker/{ticker}/range/{N}/minute endpoint.
    Returns at most `limit` most recent bars in chronological order.
    """
    try:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        url = f"https://api.marketdata.app/v1/stocks/candles/{multiplier}/{ticker}/"
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {MARKETDATA_API_KEY}"},
            params={"from": today, "to": today},
            timeout=8,
        )
        if r.status_code not in (200, 203):
            return []
        payload = r.json()
        if payload.get("s") != "ok" or not payload.get("t"):
            return []
        timestamps = payload.get("t", [])
        opens      = payload.get("o", [])
        highs      = payload.get("h", [])
        lows       = payload.get("l", [])
        closes     = payload.get("c", [])
        volumes    = payload.get("v", [])
        n = len(timestamps)
        out: list[dict[str, Any]] = []
        for i in range(n):
            out.append({
                "open":      opens[i]      if i < len(opens)      else None,
                "high":      highs[i]      if i < len(highs)      else None,
                "low":       lows[i]       if i < len(lows)       else None,
                "close":     closes[i]     if i < len(closes)     else None,
                "volume":    volumes[i]    if i < len(volumes)    else None,
                "timestamp": timestamps[i] if i < len(timestamps) else None,
            })
        return out[-limit:]
    except Exception as e:
        log.debug(f"MarketData {multiplier}m bars failed for {ticker}: {e}")
        return []


def _marketdata_quote(occ_symbol: str) -> Optional[dict[str, Any]]:
    url = f"https://api.marketdata.app/v1/options/quotes/{occ_symbol}/"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {MARKETDATA_API_KEY}"},
            timeout=8,
        )
        # MarketData.app returns 203 for delayed quotes — accept both 200 and 203
        if r.status_code not in (200, 203):
            log.info(f"  {occ_symbol}: MarketData options HTTP {r.status_code} — {r.text[:200]}")
            return None
        data = r.json()
        if data.get("s") != "ok" or not data.get("bid"):
            log.info(f"  {occ_symbol}: Options quote not usable — s={data.get('s')} bid={data.get('bid')} — {str(data)[:200]}")
            return None
        def _take(x: Any) -> Any:
            return x[0] if isinstance(x, list) else x
        return {
            "bid":    _take(data.get("bid")),
            "ask":    _take(data.get("ask")),
            "iv":     _take(data.get("iv")),
            "delta":  _take(data.get("delta")),
            "gamma":  _take(data.get("gamma")),
            "theta":  _take(data.get("theta")),
            "vega":   _take(data.get("vega")),
            "mid":    _take(data.get("mid")),
            "volume": _take(data.get("volume")),
            "open_interest": _take(data.get("openInterest") or data.get("open_interest")),
            "updated": _take(data.get("updated")),
            "source": "MARKETDATA_OPTIONS_QUOTE",
            "http_status": r.status_code,
            "freshness": (
                "REALTIME_OPRA" if r.status_code == 200
                else ("DELAYED_15M" if r.status_code == 203 else "UNKNOWN")
            ),
        }
    except Exception as e:
        log.info(f"  {occ_symbol}: MarketData options exception — {type(e).__name__}: {e}")
        return None


def _build_occ_symbol(row: dict[str, Any]) -> Optional[str]:
    ticker = _str(row, "ticker").upper()
    expiry = _str(row, "expiry")
    direction = _str(row, "direction").upper()
    strike = row.get("strike")

    if not all([ticker, expiry, direction, strike]):
        return None

    try:
        dt = datetime.strptime(expiry, "%Y-%m-%d")
        exp_str = dt.strftime("%y%m%d")
        strike_int = int(float(strike) * 1000)
        strike_str = f"{strike_int:08d}"
        cp = "C" if "CALL" in direction else "P"
        return f"{ticker}{exp_str}{cp}{strike_str}"
    except Exception:
        return None


def compute_exit_plan(candidate: dict[str, Any]) -> dict[str, Any]:
    """
    Build a machine-readable three-scenario exit plan.

    exit_invalidation_price is a plan re-evaluation trigger, not a stop loss.
    If reached, live data should be reclassified before any exit decision.
    """
    direction = _str(candidate, "options_direction") or _str(candidate, "direction")
    direction = direction.upper()
    side = "PUT" if "PUT" in direction else "CALL"
    spot = (
        _flt(candidate, "underlying_price", None)
        or _flt(candidate, "signal_price", None)
        or _flt(candidate, "live_price", None)
    )
    wall = (
        _flt(candidate, "wbs_wall_price", None)
        or _flt(candidate, "wall_price", None)
        or _flt(candidate, "call_wall" if side == "CALL" else "put_wall", None)
    )
    phase_b = _flt(candidate, "wbs_phase_b_trigger", None) or _flt(candidate, "phase_b_trigger", None)
    phase_c = _flt(candidate, "wbs_phase_c_trigger", None) or _flt(candidate, "phase_c_trigger", None)
    garch_5d = (
        _flt(candidate, "l3_expected_move_1_5d", None)
        or _flt(candidate, "expected_move_price", None)
        or _flt(candidate, "expected_move_pct", None)
    )
    garch_10d = _flt(candidate, "l3_expected_move_6_10d", None) or garch_5d
    grade = _str(candidate, "wbs_grade").upper()
    vanna = _flt(candidate, "wbs_f1_vanna", 0.0) or 0.0

    if spot and garch_5d and garch_5d < 1.0:
        garch_5d = spot * garch_5d
    if spot and garch_10d and garch_10d < 1.0:
        garch_10d = spot * garch_10d

    if not spot:
        spot = 0.0
    if not wall or wall <= 0:
        wall = spot
    wall_dist = abs(wall - spot) if spot and wall else 0.0
    garch_covers_pct = round(((garch_5d or 0.0) / wall_dist * 100.0), 2) if wall_dist > 0 else 0.0
    sign = -1.0 if side == "PUT" else 1.0

    if not phase_b:
        phase_b = spot + sign * max(wall_dist * 0.55, (garch_5d or 0.0) * 0.55)
    if not phase_c:
        phase_c = spot + sign * max(wall_dist * 0.85, (garch_5d or 0.0) * 0.85)

    if grade == "PROBABLE" and vanna >= 10:
        mode = "RIDE_THROUGH_WALL"
        t1, p1 = phase_b, 40
        t2, p2 = phase_c, 35
        t3, p3 = wall + sign * (garch_10d or wall_dist * 0.25), 25
        rationale = "WBS probable with vanna support; scale but allow wall continuation."
    elif garch_covers_pct >= 40:
        mode = "SCALE_AT_WALL"
        t1, p1 = phase_b, 60
        t2, p2 = phase_c, 25
        t3, p3 = wall + sign * max(wall_dist * 0.15, (garch_10d or 0.0) * 0.15), 15
        rationale = "GARCH covers at least 40% of wall distance; scale into wall and hold a runner."
    else:
        mode = "EXIT_BEFORE_WALL"
        move = garch_5d or wall_dist or max(spot * 0.02, 0.01)
        t1, p1 = spot + sign * move * 0.55, 50
        t2, p2 = spot + sign * move * 0.85, 35
        t3, p3 = spot + sign * move * 1.05, 15
        rationale = "Expected move does not cover enough wall distance; harvest before the wall."

    invalidation = _flt(candidate, "exit_invalidation_price", None) or _flt(candidate, "invalidation_level", None)
    if invalidation is None:
        invalidation = spot - sign * max((garch_5d or wall_dist or max(spot * 0.02, 0.01)) * 0.35, 0.01)

    return {
        "exit_mode": mode,
        "exit_t1_price": round(float(t1), 4) if t1 is not None else "",
        "exit_t1_pct": p1,
        "exit_t2_price": round(float(t2), 4) if t2 is not None else "",
        "exit_t2_pct": p2,
        "exit_t3_price": round(float(t3), 4) if t3 is not None else "",
        "exit_t3_pct": p3,
        "exit_garch_covers_pct": garch_covers_pct,
        "exit_rationale": rationale,
        "exit_invalidation_price": round(float(invalidation), 4) if invalidation is not None else "",
        "exit_invalidation_label": "PLAN_REEVALUATION_TRIGGER_NOT_STOP_LOSS",
    }


# =============================================================================
# MORNING VALIDATION SCORE (MVS)
# =============================================================================

def morning_validation_score(
    candidate: dict[str, Any],
    live_stock: Optional[dict[str, Any]],
    live_option: Optional[dict[str, Any]],
) -> tuple[float, dict[str, str], list[str]]:
    """
    Tradeability / economics score only.
    This does NOT confirm the event. Trigger confirmation is handled separately.
    """
    score = 0.0
    breakdown: dict[str, str] = {}
    hard_rejects: list[str] = []

    signal_price = _flt(candidate, "signal_price")
    direction = _str(candidate, "direction").upper()
    tier = _str(candidate, "structural_tier")

    current_price = _safe_float((live_stock or {}).get("price"))
    live_vwap = _safe_float((live_stock or {}).get("vwap"))

    # 1. Price drift
    if current_price and signal_price:
        drift_pct = abs((current_price - signal_price) / signal_price * 100)
        if drift_pct > HARD_DRIFT_REJECT:
            hard_rejects.append(f"DRIFT_HARD_REJECT: {drift_pct:.1f}% > {HARD_DRIFT_REJECT}%")
            breakdown["drift"] = f"HARD_REJECT ({drift_pct:.1f}%)"
        elif drift_pct <= 1.0:
            score += 25
            breakdown["drift"] = f"STRONG ({drift_pct:.1f}%) → 25pts"
        elif drift_pct <= SOFT_DRIFT_WARN:
            score += 15
            breakdown["drift"] = f"OK ({drift_pct:.1f}%) → 15pts"
        else:
            score += 5
            breakdown["drift"] = f"WARN ({drift_pct:.1f}%) → 5pts"
    else:
        breakdown["drift"] = "NO_PRICE_DATA"

    # 2. VWAP positioning
    if current_price and live_vwap:
        above_vwap = current_price > live_vwap
        if direction == "PUT":
            if not above_vwap:
                score += 20
                breakdown["vwap"] = f"BELOW VWAP ({current_price:.2f} < {live_vwap:.2f}) → 20pts"
            elif (current_price - live_vwap) / live_vwap < 0.005:
                score += 10
                breakdown["vwap"] = f"AT VWAP → 10pts"
            else:
                breakdown["vwap"] = f"ABOVE VWAP → 0pts"
        else:
            if above_vwap:
                score += 20
                breakdown["vwap"] = "ABOVE VWAP → 20pts"
            elif (live_vwap - current_price) / live_vwap < 0.005:
                score += 10
                breakdown["vwap"] = "AT VWAP → 10pts"
            else:
                breakdown["vwap"] = "BELOW VWAP → 0pts"
    else:
        eod_vwap_bias = _str(candidate, "vwap_bias_eod")
        if direction == "PUT" and eod_vwap_bias == "BELOW":
            score += 10
            breakdown["vwap"] = "EOD_BELOW → 10pts"
        elif direction == "CALL" and eod_vwap_bias == "ABOVE":
            score += 10
            breakdown["vwap"] = "EOD_ABOVE → 10pts"
        else:
            breakdown["vwap"] = "NO_VWAP_DATA"

    # 3. Options spread quality
    live_spread_pct = None
    spread_source = _str(candidate, "spread_source") or _str(candidate, "options_spread_source") or _str(candidate, "contract_spread_source")
    spread_source = spread_source.upper().strip()
    if live_option and live_option.get("bid") is not None and live_option.get("ask") is not None:
        bid = _safe_float(live_option.get("bid"))
        ask = _safe_float(live_option.get("ask"))
        if bid and ask and ask > bid > 0:
            mid = (bid + ask) / 2.0
            live_spread_pct = (ask - bid) / mid * 100 if mid > 0 else None
            spread_source = "LIVE_QUOTE"
    if live_spread_pct is not None:
        if live_spread_pct > HARD_SPREAD_REJECT:
            hard_rejects.append(f"SPREAD_HARD_REJECT: {live_spread_pct:.1f}% > {HARD_SPREAD_REJECT}%")
            breakdown["spread"] = f"HARD_REJECT ({live_spread_pct:.1f}%)"
        elif live_spread_pct <= 4.0:
            score += 20
            breakdown["spread"] = f"TIGHT ({live_spread_pct:.1f}%) → 20pts"
        elif live_spread_pct <= SOFT_SPREAD_WARN:
            score += 12
            breakdown["spread"] = f"ACCEPTABLE ({live_spread_pct:.1f}%) → 12pts"
        elif live_spread_pct <= 12.0:
            score += 5
            breakdown["spread"] = f"WIDE ({live_spread_pct:.1f}%) → 5pts"
        else:
            breakdown["spread"] = f"VERY_WIDE ({live_spread_pct:.1f}%) → 0pts"
    else:
        if spread_source in {"UNAVAILABLE", "MISSING", "NO_QUOTE"}:
            hard_rejects.append("SPREAD_SOURCE_UNAVAILABLE: no live/usable contract spread")
            breakdown["spread"] = "NO_QUOTE_SOURCE_UNAVAILABLE -> HARD_REJECT"
        elif spread_source in {"OI_DERIVED", "SYNTHETIC", "BSM_SYNTHETIC"}:
            score = max(0.0, score - 2.5)
            breakdown["spread"] = f"NO_LIVE_QUOTE_{spread_source} -> -2.5pts, verify at open"
        else:
            breakdown["spread"] = "NO_QUOTE"
    breakdown["spread_source"] = spread_source or "UNKNOWN"

    # 4. IV sanity
    live_iv = _safe_float((live_option or {}).get("iv"))
    if live_iv:
        if live_iv < 0.25:
            score += 15
            breakdown["iv_sanity"] = f"CHEAP ({live_iv:.0%}) → 15pts"
        elif live_iv < 0.40:
            score += 12
            breakdown["iv_sanity"] = f"FAIR ({live_iv:.0%}) → 12pts"
        elif live_iv < 0.60:
            score += 7
            breakdown["iv_sanity"] = f"ELEVATED ({live_iv:.0%}) → 7pts"
        elif live_iv < 0.80:
            score += 3
            breakdown["iv_sanity"] = f"RICH ({live_iv:.0%}) → 3pts"
        else:
            breakdown["iv_sanity"] = f"EXTREME ({live_iv:.0%}) → 0pts"
    else:
        eil_iv = _flt(candidate, "eil_iv_score") or 0.0
        if eil_iv > 0:
            pts = round(eil_iv / 100 * 10, 1)
            score += pts
            breakdown["iv_sanity"] = f"EIL_PROXY ({eil_iv:.0f}) → {pts:.0f}pts"
        else:
            breakdown["iv_sanity"] = "NO_IV_DATA"

    # 5. Volume / RVOL
    if live_stock and live_stock.get("volume") and live_stock.get("prev_vol"):
        vol_today = _safe_float(live_stock.get("volume"), 0.0) or 0.0
        vol_prev = _safe_float(live_stock.get("prev_vol"), 0.0) or 0.0
        rvol_est = (vol_today * 20) / vol_prev if vol_prev > 0 else 1.0
        if rvol_est >= 1.5:
            score += 10
            breakdown["volume"] = f"RVOL {rvol_est:.1f}x (HIGH) → 10pts"
        elif rvol_est >= 1.0:
            score += 6
            breakdown["volume"] = f"RVOL {rvol_est:.1f}x (NORMAL) → 6pts"
        elif rvol_est >= 0.7:
            score += 3
            breakdown["volume"] = f"RVOL {rvol_est:.1f}x (LOW) → 3pts"
        else:
            breakdown["volume"] = f"RVOL {rvol_est:.1f}x (DEAD) → 0pts"
    else:
        breakdown["volume"] = "NO_VOLUME_DATA"

    # 6. Structural carry
    scs = _flt(candidate, "scs_score") or 0.0
    if tier == "A":
        score += 10
        pts = 10
    elif tier == "B":
        score += 7
        pts = 7
    elif tier == "C":
        score += 4
        pts = 4
    else:
        pts = 0
    breakdown["structural_carry"] = f"Tier {tier} SCS={scs:.0f} → {pts}pts"

    return round(min(100.0, score), 1), breakdown, hard_rejects


# =============================================================================
# FINAL DECISION FUSION
# =============================================================================

def execution_decision_with_trigger(
    mvs: float,
    trigger_state: str,
    trigger_score: float,
    hard_rejects: list[str],
    candidate: dict[str, Any],
) -> tuple[str, float]:
    """
    Decision fusion:
    - hard rejects remain sovereign,
    - confirmed event required for EXECUTE,
    - partial/confirmed event allowed for PROBE,
    - not-ready event becomes WATCH if tradeability is still acceptable.
    """
    eod_size = _flt(candidate, "sb_position_size_pct", 15.0) or 15.0

    if hard_rejects:
        return "REJECT", 0.0

    if trigger_state in ("INVALIDATED", "FAILED"):
        return "REJECT", 0.0

    if mvs >= EXECUTE_THRESHOLD and trigger_state == "CONFIRMED" and trigger_score >= TCE_EXECUTE_MIN:
        return "EXECUTE", eod_size

    if mvs >= PROBE_THRESHOLD and trigger_state in ("CONFIRMED", "PARTIAL") and trigger_score >= TCE_PROBE_MIN:
        return "PROBE", round(eod_size * 0.50, 1)

    if mvs >= WATCH_THRESHOLD and trigger_state in ("PARTIAL", "NOT_READY", "DATA_WEAK"):
        return "WATCH", 0.0

    return "REJECT", 0.0


# =============================================================================
# PRESENTATION
# =============================================================================

def print_signal_card(
    candidate: dict[str, Any],
    idx: int,
    live_stock: Optional[dict[str, Any]],
    live_option: Optional[dict[str, Any]],
    mvs: float,
    trigger_result: Any,
    decision: str,
    breakdown: dict[str, str],
    hard_rejects: list[str],
    position_size: float,
    occ_symbol: Optional[str],
) -> None:
    tier = _str(candidate, "structural_tier")
    ticker = _str(candidate, "ticker")
    direction = _str(candidate, "direction")
    strike = _flt(candidate, "strike") or 0.0
    expiry = _str(candidate, "expiry")
    dte = _flt(candidate, "dte") or 0.0
    rr = _flt(candidate, "rr") or 0.0
    scs = _flt(candidate, "scs_score") or 0.0
    setup = _str(candidate, "setup_type")
    campaign = _str(candidate, "sb_campaign")
    time_stop = _str(candidate, "sb_time_stop_date")
    ladder = _str(candidate, "sb_ladder_summary")

    current_price = (live_stock or {}).get("price")
    live_bid = (live_option or {}).get("bid")
    live_ask = (live_option or {}).get("ask")
    live_iv = (live_option or {}).get("iv")

    decision_icons = {"EXECUTE": "🟢", "PROBE": "🟡", "WATCH": "🔵", "REJECT": "🔴"}
    tier_icons = {"A": "⭐", "B": "●", "C": "○", "WATCH": "△"}

    print()
    print(f"  {'─' * 64}")
    print(f"  {idx:>3}. {tier_icons.get(tier, '○')} {ticker:<6} [{tier}] {direction} ${strike:.0f} exp:{expiry} {dte:.0f}DTE")
    print(f"       Setup:   {setup} | {campaign}")
    _wbs_score = _flt(candidate, "wbs_score") or _flt(candidate, "wbs") or 0.0
    _wbs_grade = _str(candidate, "wbs_grade") or ("IMMINENT" if _wbs_score >= 80 else "BUILDING" if _wbs_score >= 50 else "N/A")
    print(f"       EOD:     OIS={_flt(candidate, 'options_score') or 0:.0f}  RR={rr:.2f}x  SCS={scs:.0f}/100  WBS={_wbs_grade} ({_wbs_score:.0f})")
    print(f"       Signal:  ${_flt(candidate, 'signal_price') or 0:.2f}  Wall:${_flt(candidate, 'wall_price') or 0:.2f} ({_flt(candidate, 'wall_dist_pct') or 0:.1f}% away)")
    print(f"       Stop:    ${_flt(candidate, 'invalidation_level') or 0:.2f}  |  TimeStop:{time_stop}")

    if current_price:
        rv = ((live_stock.get('volume', 0) or 0) * 20 / max(live_stock.get('prev_vol', 1) or 1, 1)) if live_stock else 0
        print(f"       Live:    ${current_price:.2f}  VWAP:{live_stock.get('vwap', '?')}  RVOL:~{rv:.1f}x")
    else:
        print("       Live:    [No price data]")

    if live_bid and live_ask:
        mid = (float(live_bid) + float(live_ask)) / 2
        spread_pct = (float(live_ask) - float(live_bid)) / mid * 100 if mid > 0 else 0
        iv_str = f"IV:{float(live_iv):.0%}" if live_iv is not None else "IV:?"
        print(f"       Quote:   {occ_symbol or '?'}  Bid:${float(live_bid):.2f} Ask:${float(live_ask):.2f} Mid:${mid:.2f}  Spread:{spread_pct:.1f}%  {iv_str}")
    else:
        print(f"       Quote:   [No live quote] OCC:{occ_symbol or 'unknown'}")

    print()
    print(f"       {'─' * 56}")
    print(
        f"       🧠 MVS: {mvs:.0f}/100  |  TCE: {trigger_result.trigger_score:.0f}/100 "
        f"({trigger_result.trigger_state})  |  {decision_icons.get(decision, '?')} {decision}",
        end="",
    )
    if position_size > 0:
        print(f"  ({position_size:.0f}% size)")
    else:
        print()

    print("       Breakdown:")
    for component, detail in breakdown.items():
        icon = "✓" if "REJECT" not in detail and "FAIL" not in detail and "NO_" not in detail else "✗"
        print(f"         {icon}  {component:<20} {detail}")

    print(f"         ⚙  trigger_entry         {trigger_result.entry_type}")
    print(f"         ⚙  trigger_reason        {trigger_result.trigger_reason}")

    if hard_rejects:
        for r in hard_rejects:
            print(f"         ⛔  {r}")

    if ladder:
        print(f"\n       Campaign: {ladder}")


# =============================================================================
# MAIN ENGINE
# =============================================================================

def run_morning_validation(
    candidates_path: str | Path,
    output_path: str | Path,
    run_id: str = "manual",
    max_signals: int = 30,
    tier_filter: Optional[str] = None,
    live_mode: bool = True,
) -> list[dict[str, Any]]:
    log.info(f"Morning Validation Engine v2.0 — {run_id}")
    log.info(f"Loading candidates: {candidates_path}")

    candidates: list[dict[str, Any]] = []
    with open(candidates_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append(row)

    log.info(f"  {len(candidates)} candidates loaded")

    # ── STALE MANIFEST CHECK ──────────────────────────────────────────────────
    # Warn if the candidate manifest was generated during market hours.
    # A mid-session EOD run produces incomplete bars and a corrupted VWAP
    # anchor — TCE will INVALIDATE everything in morning validation as a result.
    try:
        _run_ts = datetime.strptime(run_id, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        _et_offset = -4  # EDT (UTC-4); adjust to -5 in winter (EST)
        _run_et_minutes = ((_run_ts.hour + _et_offset) % 24) * 60 + _run_ts.minute
        _market_open  = 9 * 60 + 30   # 09:30 ET
        _market_close = 16 * 60 + 15  # 16:15 ET
        if _market_open <= _run_et_minutes < _market_close:
            _run_et_h = ((_run_ts.hour + _et_offset) % 24)
            _run_et_m = _run_ts.minute
            log.warning("=" * 68)
            log.warning("⚠️  STALE MANIFEST WARNING")
            log.warning(f"   Candidate manifest run_id={run_id} was generated at")
            log.warning(f"   {_run_et_h:02d}:{_run_et_m:02d} ET — during market hours (09:30–16:15 ET).")
            log.warning("   EOD bars were INCOMPLETE at time of run. TCE confirmation")
            log.warning("   is likely to INVALIDATE all signals. Results should NOT")
            log.warning("   be used for live trading decisions.")
            log.warning("   ACTION: Re-run evening pipeline after 16:15 ET tonight.")
            log.warning("=" * 68)
    except Exception:
        pass
    # ── END STALE MANIFEST CHECK ──────────────────────────────────────────────

    if tier_filter:
        allowed_tiers = {t.strip().upper() for t in tier_filter.split(",")}
    else:
        allowed_tiers = {"A", "B", "C"}

    filtered = [
        c for c in candidates
        if c.get("structural_tier", "") in allowed_tiers
        and c.get("candidate_status", "") == "READY_FOR_VALIDATION"
    ]
    filtered = filtered[:max_signals]
    log.info(f"  Processing {len(filtered)} candidates (tiers: {allowed_tiers})")

    tce = TriggerConfirmationEngine()

    results: list[dict[str, Any]] = []
    execute_out: list[dict[str, Any]] = []
    probe_out: list[dict[str, Any]] = []

    print()
    print("═" * 68)
    print("  AVSHUNTER — MORNING VALIDATION ENGINE v2.0")
    print(f"  {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  Run: {run_id}")
    print("═" * 68)

    # ── v4.1: Track horizon distribution for summary reporting ──────────────
    _horizon_counts = {"1_5d": 0, "6_10d": 0, "11_20d": 0, "unrouted": 0, "monitor_only": 0}

    for idx, candidate in enumerate(filtered, 1):
        ticker = _str(candidate, "ticker").upper()
        direction = _str(candidate, "direction").upper()
        log.info(f"Processing [{idx:>3}/{len(filtered)}] {ticker} {direction}")

        # ── v4.1 HORIZON GATE ─────────────────────────────────────────────────
        # Candidates tagged MONITOR_ONLY must not receive live execution scoring.
        # They are logged for awareness but output with decision=MONITOR_ONLY.
        # 6-10D candidates require a higher MVS threshold for EXECUTE verdict.
        _hb = str(candidate.get("horizon_bucket","")).strip().lower()
        _ha = str(candidate.get("horizon_action","")).strip().upper()
        _hsm = float(candidate.get("horizon_size_multiplier") or (
            1.0 if _hb == "1_5d" else 0.70 if _hb == "6_10d" else 0.0
        ))

        # Count for summary
        if _hb in _horizon_counts:
            _horizon_counts[_hb] = _horizon_counts.get(_hb, 0) + 1
        else:
            _horizon_counts["unrouted"] = _horizon_counts.get("unrouted", 0) + 1

        if _ha == "MONITOR_ONLY":
            # Log awareness but do not score — not executable proactively
            _horizon_counts["monitor_only"] = _horizon_counts.get("monitor_only", 0) + 1
            log.info(
                f"  [{ticker}] HORIZON GATE: 11-20D MONITOR_ONLY — "
                f"skipping live execution scoring. Re-evaluate if VIX>22 or "
                f"tech layer drops or 6-10D prob falls below 55%."
            )
            results.append({
                "ticker":         ticker,
                "direction":      direction,
                "decision":       "MONITOR_ONLY",
                "position_size":  0.0,
                "mvs":            0.0,
                "horizon_bucket": _hb,
                "horizon_action": _ha,
                "mv_notes":       "HORIZON_GATE: 11-20D MONITOR_ONLY — no proactive execution",
            })
            continue
        # ── End horizon gate ──────────────────────────────────────────────────

        live_stock = None
        live_option = None
        occ_symbol = None
        bars_1m: list[dict[str, Any]] = []
        bars_5m: list[dict[str, Any]] = []
        bars_15m: list[dict[str, Any]] = []

        if live_mode:
            # ── PRIMARY: MarketData.app equity quote (15-min delay) ───────────
            # Provides: price, bid, ask, mid, volume, change_pct
            live_stock = _marketdata_stock_quote(ticker)
            time.sleep(MARKETDATA_SLEEP_QUOTE)

            # ── SUPPLEMENT: Polygon prev-day for VWAP context ─────────────────
            poly_ctx = _polygon_snapshot(ticker)
            time.sleep(POLYGON_SLEEP_SNAPSHOT)
            if live_stock and poly_ctx:
                live_stock["prev_vol"]  = poly_ctx.get("prev_vol")
                live_stock["prev_vwap"] = poly_ctx.get("prev_vwap")
                # Use prev VWAP as VWAP proxy if no intraday VWAP available
                if not live_stock.get("vwap"):
                    live_stock["vwap"] = poly_ctx.get("prev_vwap")
            elif not live_stock and poly_ctx:
                # MarketData failed — use Polygon prev close as fallback price
                live_stock = {
                    "price":      poly_ctx.get("prev_close"),
                    "bid":        None,
                    "ask":        None,
                    "mid":        None,
                    "vwap":       poly_ctx.get("prev_vwap"),
                    "volume":     poly_ctx.get("prev_vol"),
                    "prev_vol":   poly_ctx.get("prev_vol"),
                    "change_pct": None,
                }

            # ── Polygon intraday bars for trigger confirmation ─────────────────
            # These are used by the trigger confirmation engine for bar structure,
            # support break confirmation, VWAP re-test etc. — not for price/quote.
            bars_1m  = _polygon_intraday_bars(ticker, multiplier=1,  limit=BARS_1M_LIMIT)
            time.sleep(POLYGON_SLEEP_BARS)
            bars_5m  = _polygon_intraday_bars(ticker, multiplier=5,  limit=BARS_5M_LIMIT)
            time.sleep(POLYGON_SLEEP_BARS)
            bars_15m = _polygon_intraday_bars(ticker, multiplier=15, limit=BARS_15M_LIMIT)
            time.sleep(POLYGON_SLEEP_BARS)

            # ── MarketData.app options quote ───────────────────────────────────
            occ_symbol = _build_occ_symbol(candidate)
            if occ_symbol:
                live_option = _marketdata_quote(occ_symbol)
                time.sleep(MARKETDATA_SLEEP_QUOTE)

            if not live_stock:
                log.warning(f"  {ticker}: No live stock data")
            if not live_option:
                log.warning(f"  {ticker}: No live options quote ({occ_symbol})")

        # 1) Tradeability / economics
        mvs, breakdown, hard_rejects = morning_validation_score(candidate, live_stock, live_option)

        # 2) Event confirmation from live bars
        trigger_input = build_trigger_input_from_candidate(
            candidate,
            live_stock=live_stock,
            bars_1m=bars_1m,
            bars_5m=bars_5m,
            bars_15m=bars_15m,
        )

        # Best-effort OR fallback from snapshot when not supplied in candidate
        if live_stock:
            trigger_input.opening_range_high = trigger_input.opening_range_high or _safe_float(live_stock.get("high"))
            trigger_input.opening_range_low = trigger_input.opening_range_low or _safe_float(live_stock.get("low"))

        trigger_result = tce.evaluate(trigger_input)
        tce_row = trigger_result_to_row(trigger_result)

        breakdown["trigger_state"] = f"{trigger_result.trigger_state} → {trigger_result.trigger_score:.1f}pts"
        breakdown["trigger_entry"] = trigger_result.entry_type
        breakdown["trigger_reason"] = trigger_result.trigger_reason

        # 3) Final decision fusion
        decision, position_size = execution_decision_with_trigger(
            mvs=mvs,
            trigger_state=trigger_result.trigger_state,
            trigger_score=trigger_result.trigger_score,
            hard_rejects=hard_rejects,
            candidate=candidate,
        )

        # ── v4.1: Apply horizon_size_multiplier to final position size ────────
        if _hsm < 1.0 and _hsm > 0.0 and position_size > 0:
            _pre_horizon_size = position_size
            position_size = round(position_size * _hsm, 1)
            log.info(
                f"  [{ticker}] Horizon size: {_pre_horizon_size:.1f}% x {_hsm:.2f} "
                f"({_hb}) = {position_size:.1f}%"
            )
        # ── End horizon_size_multiplier ───────────────────────────────────────

        # 4) Operator card
        print_signal_card(
            candidate,
            idx,
            live_stock,
            live_option,
            mvs,
            trigger_result,
            decision,
            breakdown,
            hard_rejects,
            position_size,
            occ_symbol,
        )

        # 5) Output row
        exit_plan = compute_exit_plan({
            **candidate,
            "live_price": (live_stock or {}).get("price", ""),
            "direction": direction,
        })
        result: dict[str, Any] = {
            "run_id": run_id,
            "ticker": ticker,
            "direction": direction,
            "structural_tier": candidate.get("structural_tier", ""),
            "scs_score": candidate.get("scs_score", 0),
            "setup_type": candidate.get("setup_type", ""),
            "mv_score": mvs,
            "mv_verdict": decision,
            "mv_position_size": position_size,
            "horizon_bucket": _hb,
            "horizon_action": _ha,
            "horizon_size_multiplier": _hsm,
            "mv_hard_rejects": "; ".join(hard_rejects),
            "mv_breakdown": json.dumps(breakdown, ensure_ascii=False),
            "strike": candidate.get("strike", ""),
            "expiry": candidate.get("expiry", ""),
            "dte": candidate.get("dte", ""),
            "occ_symbol": occ_symbol or "",
            "live_price": (live_stock or {}).get("price", ""),
            "live_vwap": (live_stock or {}).get("vwap", ""),
            "live_bid": (live_option or {}).get("bid", ""),
            "live_ask": (live_option or {}).get("ask", ""),
            "live_iv": (live_option or {}).get("iv", ""),
            "live_delta": (live_option or {}).get("delta", ""),
            "live_gamma": (live_option or {}).get("gamma", ""),
            "spread_source": candidate.get("spread_source", candidate.get("options_spread_source", candidate.get("contract_spread_source", ""))),
            "signal_price": candidate.get("signal_price", ""),
            "rr": candidate.get("rr", ""),
            "options_score": candidate.get("options_score", ""),
            "sb_campaign": candidate.get("sb_campaign", ""),
            "sb_time_stop_date": candidate.get("sb_time_stop_date", ""),
            "sb_checkpoint_date": candidate.get("sb_checkpoint_date", ""),
            "sb_ladder_summary": candidate.get("sb_ladder_summary", ""),
            "invalidation_level": candidate.get("invalidation_level", ""),
            "wall_price": candidate.get("wall_price", ""),
            "wbs_score": _flt(candidate, "wbs_score") or _flt(candidate, "wbs") or "",
            "wbs_grade": _str(candidate, "wbs_grade") or "",
            "bars_1m_count": len(bars_1m),
            "bars_5m_count": len(bars_5m),
            "bars_15m_count": len(bars_15m),
            "tce_trigger_state": trigger_result.trigger_state,
            "tce_trigger_score": trigger_result.trigger_score,
            "tce_entry_type": trigger_result.entry_type,
            "tce_confirmed_components": trigger_result.confirmed_components,
            "tce_possible_components": trigger_result.possible_components,
            "tce_data_quality_score": trigger_result.data_quality_score,
            "tce_trigger_reason": trigger_result.trigger_reason,
            "tce_summary_line": trigger_result.summary_line,
            "manual_review_required": "TRUE",
            "reviewer_approval": "",
            "reviewer_notes": "",
            "review_timestamp": "",
            "approved_size_contracts": "",
            "execution_lifecycle_state": "MANUAL_REVIEW_REQUIRED",
            "automated_execution_eligible": "FALSE",
        }
        result.update(exit_plan)
        result.update(tce_row)
        results.append(result)

        if decision == "EXECUTE":
            execute_out.append(result)
        elif decision == "PROBE":
            probe_out.append(result)

    # Summary
    print()
    print("═" * 68)
    print("  MORNING VALIDATION SUMMARY")
    print("═" * 68)

    all_decisions: dict[str, int] = {}
    for r in results:
        d = str(r["mv_verdict"])
        all_decisions[d] = all_decisions.get(d, 0) + 1

    for state in ["EXECUTE", "PROBE", "WATCH", "REJECT"]:
        count = all_decisions.get(state, 0)
        icon = {"EXECUTE": "🟢", "PROBE": "🟡", "WATCH": "🔵", "REJECT": "🔴"}.get(state, "  ")
        print(f"  {icon}  {state:<10} : {count}")

    print()
    if execute_out:
        print("  🟢 EXECUTE LIST (Full size):")
        for r in execute_out:
            print(
                f"     {r['ticker']:<6} {r['direction']}  ${r['strike']}  exp:{r['expiry']}  "
                f"MVS:{float(r['mv_score']):.0f}  TCE:{float(r['tce_trigger_score']):.0f}  "
                f"Size:{float(r['mv_position_size']):.0f}%  Stop:${r['invalidation_level']}"
            )

    if probe_out:
        print()
        print("  🟡 PROBE LIST (Half size):")
        for r in probe_out:
            print(
                f"     {r['ticker']:<6} {r['direction']}  ${r['strike']}  exp:{r['expiry']}  "
                f"MVS:{float(r['mv_score']):.0f}  TCE:{float(r['tce_trigger_score']):.0f}  "
                f"Size:{float(r['mv_position_size']):.0f}%"
            )

    # Equity lane
    equity_signals = [r for r in results if r.get("mv_verdict") == "EXECUTE"]
    if equity_signals:
        print()
        print("  ─" * 34)
        print("  📈 EQUITY LANE — DIRECT STOCK TRADES (same signals, no theta drag)")
        print("  ─" * 34)
        for r in equity_signals:
            invalidation = r.get("invalidation_level", "?")
            wall = r.get("wall_price", "?")
            live_price = r.get("live_price", "?")
            direction = r.get("direction", "")
            entry_note = "BUY STOCK" if direction == "CALL" else "SHORT/PUT STOCK"
            size_pct = r.get("mv_position_size", 0)
            print(f"\n     {r['ticker']:<6} | {entry_note}")
            print(f"       Live: ${live_price}  |  Invalidation: ${invalidation}  |  Wall: ${wall}")
            print(f"       Size: {float(size_pct):.0f}% of position | Stop: ${invalidation}")
            print(f"       Note: Enter equity alongside {direction} option OR as standalone if options spread wide")

    print()

    # Write outputs
    if results:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        log.info(f"Validated trades → {output_path}")
        try:
            import sys as _ma_sys
            _ma_sys.path.insert(0, r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter")
            from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
            _ma_on_pipeline_complete(str(output_path), output_dir=str(Path(output_path).parent))
        except Exception as _ma_sync_err:
            log.warning("MA_Inputs sync skipped for morning validation output: %s", _ma_sync_err)

        summary_path = str(output_path).replace(".csv", "_summary.json")
        summary = {
            "run_id": run_id,
            "generated_utc": datetime.now(tz=timezone.utc).isoformat(),
            "total_processed": len(results),
            "decision_counts": all_decisions,
            "execute": [r["ticker"] for r in execute_out],
            "probe": [r["ticker"] for r in probe_out],
            "notes": [
                "This engine validates event confirmation from live intraday bars, not uploaded screenshots.",
                "Use screenshot-based review as a separate research / backtest lane.",
            ],
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        log.info(f"Summary → {summary_path}")

    return results


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AVSHUNTER Morning Validation Engine v2.0")
    parser.add_argument("--run_id", default=None, help="Run ID to validate")
    parser.add_argument("--base_dir", default=r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
    parser.add_argument("--max_signals", type=int, default=20)
    parser.add_argument("--tiers", default="A,B,C", help="Tier filter: A | A,B | A,B,C")
    parser.add_argument("--test_mode", action="store_true", help="Skip live fetch")
    args = parser.parse_args()

    base_path = Path(args.base_dir)
    _load_dotenv_fallback(base_path)

    run_id = args.run_id
    if not run_id:
        latest_json = base_path / "data" / "output" / "latest.json"
        if not latest_json.exists():
            log.error("Cannot find latest.json at: %s", latest_json)
            log.error("Fix: run [System.IO.File]::WriteAllText('...latest.json', '{\"run_id\": \"YYYYMMDD_HHMMSS\"}') in PowerShell")
            log.error("Or pass --run_id YYYYMMDD_HHMMSS directly.")
            raise SystemExit(1)
        try:
            # utf-8-sig handles BOM from PowerShell Out-File
            with open(latest_json, encoding="utf-8-sig") as f:
                run_id = str(json.load(f).get("run_id", "")).strip()
            if not run_id:
                raise ValueError("run_id empty in latest.json")
            log.info("Auto-resolved run_id: %s (from %s)", run_id, latest_json)
        except Exception as e:
            log.error("Cannot resolve run_id: %s", e)
            log.error("Either pass --run_id YYYYMMDD_HHMMSS or run the evening pipeline first.")
            raise SystemExit(1)

    runs_dir = base_path / "data" / "output" / "runs"
    mv_dir = runs_dir / run_id / "morning_validation"
    mv_dir.mkdir(parents=True, exist_ok=True)

    run_morning_validation(
        candidates_path=mv_dir / f"morning_candidates_{run_id}.csv",
        output_path=mv_dir / f"morning_validated_trades_{run_id}.csv",
        run_id=run_id,
        max_signals=args.max_signals,
        tier_filter=args.tiers,
        live_mode=not args.test_mode,
    )
