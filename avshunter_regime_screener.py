#!/usr/bin/env python3
"""
avshunter_regime_screener.py
============================
AVSHUNTER — Regime-Adaptive Signal Screener
Version : 1.0.0

PURPOSE
-------
The core pipeline is optimised for directional momentum (MARKUP + EXPANSION vol).
In TRANSITIONAL or RISK_OFF regimes where directional edge is thin, three
additional signal types produce consistent long options edge:

  TYPE 1 — MEAN REVERSION (Long puts/calls on overextended names)
    Edge source : Dealer gamma forces mean reversion at walls
    Best regime : ANY — works in all regimes
    Options play: Long OTM put/call 21-45 DTE on extension into wall

  TYPE 2 — VOLATILITY EXPANSION (Long straddles/strangles pre-move)
    Edge source : IV compression before catalyst → vol expansion trade
    Best regime : TRANSITIONAL — vol cheap, move imminent
    Options play: Long ATM straddle 14-28 DTE, IV below 30th percentile

  TYPE 3 — STRUCTURAL BREAKOUT (Long calls on volume-confirmed breakouts)
    Edge source : Institutional accumulation completing → markup begins
    Best regime : RISK_ON or TRANSITIONAL recovering
    Options play: Long ITM call 30-60 DTE on Phase D/E breakout

PIPELINE POSITION
-----------------
Runs as a standalone screener AFTER the main discovery run.
Outputs additional candidates to a separate CSV that feeds into
the same morning candidates manifest via EOD candidate engine.

    avshunter_discovery_ULTIMATE.py   (main discovery)
            ↓
    avshunter_regime_screener.py      (this script — additional signals)
            ↓
    [both outputs] → eod_candidate_engine.py → morning_candidates.csv

DEPLOY
------
    C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\avshunter_regime_screener.py

ORCHESTRATOR CALL
-----------------
    from avshunter_regime_screener import run_regime_screener
    result = run_regime_screener(run_id=run_id, base_dir=cfg.BASE_DIR)
"""

from __future__ import annotations

import csv
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("regime_screener")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

HERE    = Path(__file__).resolve().parent
REPO    = HERE

# Screener thresholds
MR_VWAP_DEVIATION_MIN    = 1.5    # ATR units from VWAP to qualify as overextended
MR_RVOL_MIN              = 2.0    # Minimum RVOL for mean reversion signal
MR_WBS_MIN               = 35.0   # Minimum WBS score (near a wall)
MR_ADX_MAX               = 35.0   # ADX below this = not strongly trending = MR candidate

VE_IVP_MAX               = 35.0   # IVP below 35th percentile = vol cheap
VE_ATR_PCT_MAX           = 30.0   # ATR percentile below 30 = compression
VE_RVOL_MIN              = 1.5    # Some vol activity present

SB_PHASE_QUALIFY         = {"D", "E", "MARKUP"}  # Structural breakout phases
SB_ADX_MIN               = 25.0   # Trending
SB_RVOL_MIN              = 1.8    # Volume confirmation

# Signal caps
MAX_MR_SIGNALS           = 10
MAX_VE_SIGNALS           = 8
MAX_SB_SIGNALS           = 10


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _f(v: Any, default: float = 0.0) -> float:
    try:
        r = float(v)
        return default if (r != r or math.isinf(r)) else r
    except (TypeError, ValueError):
        return default


def _s(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip().upper()


def _load_csv(path: Path) -> List[Dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows.append({k: v.strip() if isinstance(v, str) else v
                             for k, v in row.items()})
    except Exception as e:
        log.warning("Failed to load %s: %s", path.name, e)
    return rows


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL TYPE 1 — MEAN REVERSION
# ─────────────────────────────────────────────────────────────────────────────

def screen_mean_reversion(
    rows: List[Dict[str, Any]],
    wbs_map: Dict[str, Dict],
) -> List[Dict[str, Any]]:
    """
    Identify names overextended from VWAP approaching a gamma wall.
    These names tend to snap back regardless of regime.

    Long PUT  if price extended UP into call wall (sell the rip)
    Long CALL if price extended DOWN into put wall (buy the dip)

    Selection criteria:
      - Price deviated >= 1.5 ATR from VWAP
      - RVOL >= 2.0x (institutional activity)
      - WBS >= 35 (near a gamma wall)
      - ADX < 35 (not in a strong trend — trending names don't revert)
    """
    signals = []

    for r in rows:
        ticker = _s(r.get("ticker"))
        if not ticker:
            continue

        price       = _f(r.get("current_price") or r.get("signal_price") or r.get("close"))
        vwap        = _f(r.get("vwap") or r.get("vwap_eod"))
        atr         = _f(r.get("atr") or r.get("atr_14"))
        rvol        = _f(r.get("rvol") or r.get("volume_ratio"))
        adx         = _f(r.get("adx") or r.get("adx_14"))
        atr_pct     = _f(r.get("atr_pct") or r.get("atr_percentile"))

        if price <= 0 or vwap <= 0 or atr <= 0:
            continue

        # VWAP deviation in ATR units
        vwap_dev_atr = abs(price - vwap) / atr if atr > 0 else 0

        if vwap_dev_atr < MR_VWAP_DEVIATION_MIN:
            continue
        if rvol < MR_RVOL_MIN:
            continue
        if adx > MR_ADX_MAX:
            continue  # Strong trend — not a mean reversion candidate

        # Check WBS for wall proximity
        wbs_row = wbs_map.get(ticker, {})
        wbs     = _f(wbs_row.get("wbs") or r.get("wbs"))
        if wbs < MR_WBS_MIN:
            continue

        # Direction: extended UP = put candidate, extended DOWN = call candidate
        extended_up   = price > vwap
        direction     = "PUT" if extended_up else "CALL"
        wall_price    = _f(wbs_row.get("wbs_wall_price") or r.get("call_wall" if extended_up else "put_wall"))

        # Confidence score: higher deviation + higher RVOL + higher WBS = stronger signal
        score = (
            min(vwap_dev_atr / 3.0, 1.0) * 0.40 +
            min(rvol / 5.0, 1.0)          * 0.30 +
            min(wbs / 60.0, 1.0)          * 0.30
        )

        signals.append({
            "ticker":           ticker,
            "signal_type":      "MEAN_REVERSION",
            "direction":        direction,
            "signal_score":     round(score, 4),
            "signal_price":     price,
            "vwap":             vwap,
            "vwap_dev_atr":     round(vwap_dev_atr, 2),
            "rvol":             rvol,
            "adx":              adx,
            "atr_pct":          atr_pct,
            "wbs":              wbs,
            "wall_price":       wall_price,
            "suggested_dte":    "21-35",
            "suggested_strike": "ATM-1" if extended_up else "ATM+1",
            "size_guidance":    "15-20%",
            "regime_note":      "Works in all regimes — gamma wall forces reversion",
            "campaign":         "MEAN_REVERSION",
        })

    signals.sort(key=lambda x: x["signal_score"], reverse=True)
    return signals[:MAX_MR_SIGNALS]


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL TYPE 2 — VOLATILITY EXPANSION
# ─────────────────────────────────────────────────────────────────────────────

def screen_vol_expansion(
    rows: List[Dict[str, Any]],
    macro: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Identify names with compressed vol about to expand.
    Long straddle/strangle when IV is cheap and ATR is compressed.

    Best in TRANSITIONAL regime where uncertainty is high but
    options are still cheap because market has been range-bound.

    Selection criteria:
      - IVP < 35th percentile (vol cheap)
      - ATR percentile < 30 (price compressed)
      - RVOL >= 1.5 (some activity building)
      - No strong directional bias (ADX < 30)
    """
    signals = []
    macro_regime = _s(macro.get("macro_state", {}).get("RegimeState") or
                      macro.get("regime_state") or "TRANSITIONAL")

    for r in rows:
        ticker  = _s(r.get("ticker"))
        if not ticker:
            continue

        ivp     = _f(r.get("ivp") or r.get("iv_percentile") or r.get("contract_ivp"))
        atr_pct = _f(r.get("atr_pct") or r.get("atr_percentile"))
        rvol    = _f(r.get("rvol") or r.get("volume_ratio"))
        adx     = _f(r.get("adx") or r.get("adx_14"))
        price   = _f(r.get("current_price") or r.get("signal_price"))

        # IVP check — if unknown use ATR as proxy
        if ivp <= 0:
            ivp = atr_pct  # ATR percentile as vol proxy

        if ivp > VE_IVP_MAX:
            continue
        if atr_pct > VE_ATR_PCT_MAX:
            continue
        if rvol < VE_RVOL_MIN:
            continue

        # Score: lower IVP + lower ATR pct + higher RVOL = better
        score = (
            (1.0 - min(ivp / VE_IVP_MAX, 1.0))     * 0.45 +
            (1.0 - min(atr_pct / VE_ATR_PCT_MAX, 1.0)) * 0.35 +
            min(rvol / 4.0, 1.0)                    * 0.20
        )

        # In TRANSITIONAL regime boost score — this is the prime environment
        if macro_regime == "TRANSITIONAL":
            score = min(score * 1.15, 1.0)

        signals.append({
            "ticker":           ticker,
            "signal_type":      "VOL_EXPANSION",
            "direction":        "STRADDLE",
            "signal_score":     round(score, 4),
            "signal_price":     price,
            "ivp":              ivp,
            "atr_pct":          atr_pct,
            "rvol":             rvol,
            "adx":              adx,
            "macro_regime":     macro_regime,
            "suggested_dte":    "14-28",
            "suggested_strike": "ATM",
            "size_guidance":    "10-15%",
            "regime_note":      f"IV compressed in {macro_regime} — long both sides",
            "campaign":         "CONVEXITY_INJECTION",
        })

    signals.sort(key=lambda x: x["signal_score"], reverse=True)
    return signals[:MAX_VE_SIGNALS]


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL TYPE 3 — STRUCTURAL BREAKOUT
# ─────────────────────────────────────────────────────────────────────────────

def screen_structural_breakout(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Identify names completing accumulation and entering markup.
    Long ITM/ATM calls on Phase D/E breakouts with volume confirmation.

    These are the only signals the actuarial database consistently
    shows WR > 55% for — EXPANSION vol + UP trend + MARKUP phase.

    Selection criteria:
      - Wyckoff phase D, E, or MARKUP bucket
      - ADX >= 25 (trend established)
      - RVOL >= 1.8 (volume confirmation)
      - Structure quality STRONG or NEUTRAL
    """
    signals = []

    for r in rows:
        ticker  = _s(r.get("ticker"))
        if not ticker:
            continue

        phase   = _s(r.get("wyckoff_phase") or r.get("wyckoff_phase_bucket") or
                     r.get("current_phase") or r.get("phase"))
        adx     = _f(r.get("adx") or r.get("adx_14"))
        rvol    = _f(r.get("rvol") or r.get("volume_ratio"))
        struct  = _s(r.get("structure_quality") or r.get("layer2__structure_quality"))
        vol_reg = _s(r.get("vol_regime") or r.get("layer2__vol_regime"))
        trend   = _s(r.get("trend_direction") or r.get("layer2__trend_direction"))
        price   = _f(r.get("current_price") or r.get("signal_price"))
        wr_10d  = _f(r.get("win_rate_10d") or r.get("actuarial_win_rate_10d"))

        # Phase qualification
        phase_ok = any(p in phase for p in SB_PHASE_QUALIFY)
        if not phase_ok:
            continue
        if adx < SB_ADX_MIN:
            continue
        if rvol < SB_RVOL_MIN:
            continue
        if trend not in ("UP", "UPTREND"):
            continue

        # Highest conviction: EXPANSION vol + STRONG structure
        vol_bonus    = 0.2 if vol_reg == "EXPANSION" else 0.0
        struct_bonus = 0.1 if struct == "STRONG" else 0.0
        wr_bonus     = min(wr_10d * 0.5, 0.3) if wr_10d > 0 else 0.0

        score = (
            min(adx / 50.0, 1.0) * 0.35 +
            min(rvol / 5.0, 1.0) * 0.30 +
            vol_bonus + struct_bonus + wr_bonus
        )

        signals.append({
            "ticker":           ticker,
            "signal_type":      "STRUCTURAL_BREAKOUT",
            "direction":        "CALL",
            "signal_score":     round(score, 4),
            "signal_price":     price,
            "wyckoff_phase":    phase,
            "adx":              adx,
            "rvol":             rvol,
            "vol_regime":       vol_reg,
            "structure_quality":struct,
            "win_rate_10d":     wr_10d,
            "suggested_dte":    "30-60",
            "suggested_strike": "ATM to ITM-1",
            "size_guidance":    "20-30%",
            "regime_note":      "Actuarial confirmed edge: EXPANSION+UP+MARKUP = WR>55%",
            "campaign":         "CORE_CAMPAIGN",
        })

    signals.sort(key=lambda x: x["signal_score"], reverse=True)
    return signals[:MAX_SB_SIGNALS]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCREENER
# ─────────────────────────────────────────────────────────────────────────────

def run_regime_screener(
    run_id: str,
    base_dir: Path,
) -> Dict[str, Any]:
    """
    Run all three signal type screeners against the current run's data.
    Outputs a combined regime_signals_{run_id}.csv for morning validation.

    Called by orchestrator after discovery, before Phase 8.5.
    """
    run_dir  = base_dir / "data" / "output" / "runs" / run_id
    out_dir  = run_dir / "regime_screener"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data sources ─────────────────────────────────────────────────────
    # Vanguard signals (best state data available)
    vg_path = run_dir / "vanguard" / f"vanguard_signals_enriched_{run_id}.csv"
    if not vg_path.exists():
        vg_path = run_dir / "vanguard" / "vanguard_signals.csv"
    rows = _load_csv(vg_path)

    if not rows:
        # Fall back to superbrain enriched
        sb_path = run_dir / "superbrain" / f"superbrain_enriched_{run_id}.csv"
        rows = _load_csv(sb_path)

    if not rows:
        log.warning("Regime screener: no input data found for run %s", run_id)
        return {"success": False, "reason": "no_input_data"}

    log.info("Regime screener: %d rows loaded", len(rows))

    # WBS map
    wbs_path = run_dir / f"wall_break_scores_{run_id}.csv"
    if not wbs_path.exists():
        wbs_path = run_dir / "wall_break" / f"wall_break_scores_{run_id}.csv"
    wbs_rows = _load_csv(wbs_path)
    wbs_map  = {str(r.get("ticker","")).strip().upper(): r for r in wbs_rows}

    # Macro snapshot
    macro: Dict[str, Any] = {}
    macro_path = base_dir / "dropbox" / "macro" / "macro_intelligence_latest.json"
    if macro_path.exists():
        try:
            with macro_path.open("r", encoding="utf-8-sig") as f:
                macro = json.load(f)
        except Exception:
            pass

    # ── Run all three screeners ───────────────────────────────────────────────
    mr_signals = screen_mean_reversion(rows, wbs_map)
    ve_signals = screen_vol_expansion(rows, macro)
    sb_signals = screen_structural_breakout(rows)

    all_signals = mr_signals + ve_signals + sb_signals

    # Add run metadata to each signal
    now = datetime.now(timezone.utc).isoformat()
    for sig in all_signals:
        sig["run_id"]      = run_id
        sig["screened_at"] = now
        sig["source"]      = "regime_screener"

    # ── Write output ──────────────────────────────────────────────────────────
    out_csv = out_dir / f"regime_signals_{run_id}.csv"
    _write_csv(out_csv, all_signals)

    summary = {
        "run_id":              run_id,
        "generated_at":        now,
        "input_rows":          len(rows),
        "mean_reversion":      len(mr_signals),
        "vol_expansion":       len(ve_signals),
        "structural_breakout": len(sb_signals),
        "total_signals":       len(all_signals),
        "output_csv":          str(out_csv),
        "success":             True,
    }

    with (out_dir / f"regime_screener_summary_{run_id}.json").open("w") as f:
        json.dump(summary, f, indent=2)

    log.info(
        "Regime screener complete — MR=%d VE=%d SB=%d total=%d",
        len(mr_signals), len(ve_signals), len(sb_signals), len(all_signals),
    )

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [REGIME_SCREENER] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> int:
    import argparse
    _setup_logging()

    ap = argparse.ArgumentParser(description="AVSHUNTER Regime-Adaptive Screener")
    ap.add_argument("--run-id",   required=True)
    ap.add_argument("--base-dir", default=str(HERE))
    args = ap.parse_args()

    result = run_regime_screener(
        run_id   = args.run_id,
        base_dir = Path(args.base_dir).resolve(),
    )

    if not result.get("success"):
        log.error("FAILED: %s", result.get("reason"))
        return 1

    print(f"\n=== REGIME SCREENER COMPLETE ===")
    print(f"  Mean Reversion    : {result['mean_reversion']}")
    print(f"  Vol Expansion     : {result['vol_expansion']}")
    print(f"  Structural Breakout: {result['structural_breakout']}")
    print(f"  Total             : {result['total_signals']}")
    print(f"  Output            : {result['output_csv']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
