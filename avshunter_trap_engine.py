#!/usr/bin/env python3
"""
Sprint 3 — Trap-to-Launch Engine (TLE)
Phase 5.5 standalone enrichment layer.

Reads package JSON files written by Phase 5 (build_packages + inject_macro + backfill),
computes trap detection scores for each ticker, and writes tle_ fields back to the
package JSON so Options Intelligence (Phase 7) can read tle_verdict as a CSM modifier.

Architecture decision: standalone enrichment, NOT a phase resequence.
trigger_layer.py at Phase 8.6b is NOT modified — TLE is additive and upstream.

Usage (CLI):
    python avshunter_trap_engine.py --run-id 20260604_003037
    python avshunter_trap_engine.py --test-mode

Orchestrator call (Phase 5.5):
    run_trap_layer(run_id=run_id, runs_dir=cfg.RUNS_DIR)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("avshunter.trap_engine")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [TLE] %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )

BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_RUNS_DIR = BASE_DIR / "data" / "output" / "runs"


# ── Sparse-field guard ──────────────────────────────────────────────────────
# Fields with <80% population must return a safe default, never raise KeyError.

def _s(d: Dict, key: str, default: Any = "") -> Any:
    v = d.get(key)
    if v is None or v == "":
        return default
    return v


def _sf(d: Dict, key: str, default: Optional[float] = None) -> Optional[float]:
    v = d.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ── Per-package TLE computation ─────────────────────────────────────────────

def _compute_tle(pkg: Dict) -> Dict[str, Any]:
    """
    Compute TLE scores and return a tle_ field dict.
    Called once per package; never raises — returns neutral fields on any error.
    """
    try:
        return _compute_tle_inner(pkg)
    except Exception as exc:
        logger.warning("TLE compute error for %s: %s", pkg.get("ticker", "?"), exc)
        return _neutral_tle(pkg)


def _neutral_tle(pkg: Dict) -> Dict[str, Any]:
    ticker = str(pkg.get("ticker") or "?")
    disc = pkg.get("discovery", {}) if isinstance(pkg.get("discovery"), dict) else {}
    stop = _sf(disc, "structural_stop") or _sf(disc, "stop_loss")
    target = _sf(disc, "structural_target")
    return {
        "tle_trap_direction": "NEUTRAL",
        "tle_who_is_trapped": "None confirmed",
        "tle_forced_move_level": None,
        "tle_entry_trigger": "UNAVAILABLE",
        "tle_kill_switch": stop,
        "tle_bullish_score": 0,
        "tle_bearish_score": 0,
        "tle_verdict": "NO_TRADE",
        "tle_crowd_arrival_target": target,
        "_tle_ticker": ticker,
    }


def _compute_tle_inner(pkg: Dict) -> Dict[str, Any]:
    disc = pkg.get("discovery", {})
    trig = pkg.get("triggers", {})
    macro = pkg.get("macro", {})

    if not isinstance(disc, dict):
        disc = {}
    if not isinstance(trig, dict):
        trig = {}
    if not isinstance(macro, dict):
        macro = {}

    macro_payload = macro.get("payload", {}) if isinstance(macro.get("payload"), dict) else {}
    macro_gex = macro_payload.get("gex", {}) if isinstance(macro_payload.get("gex"), dict) else {}

    # ── Read discovery fields ────────────────────────────────────────────────
    ticker = str(pkg.get("ticker") or _s(disc, "ticker", "?"))
    direction = str(_s(disc, "direction", "")).upper()
    phase = str(_s(disc, "phase", "")).upper()
    wyckoff_mode = str(_s(disc, "wyckoff_mode", "")).upper()
    wyckoff_granular = str(_s(disc, "wyckoff_phase_granular", "")).upper()
    dominant_event = str(_s(disc, "dominant_event_norm") or _s(disc, "dominant_event", "")).upper()
    control_state = str(_s(disc, "control_state", "")).upper().replace(" ", "_")
    precor_control = str(_s(disc, "precor_control", "")).upper().replace(" ", "_")
    vwap_bias = str(_s(disc, "vwap_bias", "")).upper()
    dominant_trend = str(_s(disc, "dominant_trend", "")).upper()
    gamma_risk_flag = str(_s(disc, "gamma_risk_flag", "false")).lower() == "true"
    event_evidence = str(_s(disc, "event_evidence_bucket", "")).upper()
    repricing_dir = str(_s(disc, "repricing_direction", "")).upper()
    repricing_state = str(_s(disc, "repricing_state", "NORMAL")).upper()

    # Sparse fields — explicit fallback to empty string / 0 (never raise)
    crabel_state = str(_s(disc, "crabel_state", "")).upper()      # 25% populated
    crabel_bucket = str(_s(disc, "crabel_bucket", "")).upper()
    days_in_range = _sf(disc, "days_in_range", 0.0) or 0.0       # 25% populated

    # Trigger fields (100% populated in packages — primary is always a string)
    trigger_primary = str(trig.get("primary") or "").upper()
    trigger_codes_raw = trig.get("codes", "")
    trigger_codes = str(trigger_codes_raw).upper() if trigger_codes_raw else ""

    # Price levels for output fields
    spot = _sf(disc, "stock_price") or _sf(disc, "entry_price")
    structural_stop = _sf(disc, "structural_stop") or _sf(disc, "stop_loss")
    structural_target = _sf(disc, "structural_target")
    vwap_level = _sf(disc, "VWAP")
    entry_price = _sf(disc, "entry_price") or spot

    # GEX proxy (market-wide, used as 1-weight wall signal)
    gex_score = _sf(macro_gex, "score", 0.0) or 0.0
    gex_regime = str(macro_gex.get("regime", "")).upper()
    gex_stress = str(macro_gex.get("stress", "")).upper()

    # ── BULLISH trap signals ────────────────────────────────────────────────
    bull_score = 0
    bull_signals: list[str] = []

    # T1: Spring / Wyckoff Phase C reclaim (weight 3)
    spring_signal = (
        "SPRING" in wyckoff_granular
        or (phase == "C" and wyckoff_mode == "ACCUMULATION")
        or dominant_event in ("SC", "LPS", "SOS", "SPRING")
    )
    if spring_signal:
        bull_score += 3
        bull_signals.append("SPRING_RECLAIM")

    # T2: VWAP reclaim (price above VWAP — proxy for VWAP_RECLAIM trigger) (weight 2)
    vwap_reclaim = vwap_bias == "ABOVE"
    if vwap_reclaim:
        bull_score += 2
        bull_signals.append("VWAP_RECLAIM")

    # T3: VOL_COMPRESSION trigger (weight 2)
    vol_compression = (
        "VOL_COMPRESSION" in trigger_primary
        or "VOL_COMPRESSION" in trigger_codes
        or "COMPRESSION" in crabel_bucket
        or crabel_state in ("COILING", "COMPRESSED")
    )
    if vol_compression:
        bull_score += 2
        bull_signals.append("VOL_COMPRESSION")

    # T4: Failed breakdown — separate from spring (wick below support, close above) (weight 2)
    failed_breakdown = (
        repricing_dir == "COUNTER_CALL" and repricing_state == "NORMAL"
    )
    if failed_breakdown:
        bull_score += 2
        bull_signals.append("FAILED_BREAKDOWN")

    # T5: Shorts trapped below value area (weight 2)
    shorts_trapped = (
        control_state in ("SHIFTING_BULLISH", "BULLISH")
        or precor_control in ("SHIFTING_BULLISH", "BULLISH")
    )
    if shorts_trapped:
        bull_score += 2
        bull_signals.append("SHORTS_TRAPPED")

    # T6: Call wall runway clear (weight 1) — proxy: non-bearish trend + no gamma risk
    call_wall_clear = not gamma_risk_flag and dominant_trend != "BEARISH"
    if call_wall_clear:
        bull_score += 1
        bull_signals.append("CALL_WALL_CLEAR")

    # ── BEARISH trap signals ────────────────────────────────────────────────
    bear_score = 0
    bear_signals: list[str] = []

    # T1: UTAD / failed breakout (weight 3)
    utad_signal = (
        "UTAD" in wyckoff_granular
        or "LPSY" in wyckoff_granular
        or (wyckoff_mode == "DISTRIBUTION" and phase in ("C", "D"))
        or dominant_event in ("UTAD", "SOW", "LPSY", "PSY")
    )
    if utad_signal:
        bear_score += 3
        bear_signals.append("UTAD_BREAKOUT_FAIL")

    # T2: VWAP loss confirmed (weight 2)
    vwap_below = vwap_bias == "BELOW"
    if vwap_below:
        bear_score += 2
        bear_signals.append("VWAP_LOSS")

    # T3: Buyers trapped above value (weight 2)
    buyers_trapped = (
        control_state in ("SHIFTING_BEARISH", "BEARISH", "ADVERSE")
        or precor_control in ("SHIFTING_BEARISH", "BEARISH")
    )
    if buyers_trapped:
        bear_score += 2
        bear_signals.append("BUYERS_TRAPPED")

    # T4: Rejection at supply zone (weight 2)
    rejection = (
        repricing_dir in ("COUNTER_PUT", "REJECTION")
        or "UTAD" in wyckoff_granular
        or "LPSY" in wyckoff_granular
    )
    if rejection:
        bear_score += 2
        bear_signals.append("SUPPLY_REJECTION")

    # T5: Weak thrust after positive catalyst (weight 1)
    weak_thrust = dominant_trend == "BEARISH" and event_evidence in ("HIGH", "MEDIUM")
    if weak_thrust:
        bear_score += 1
        bear_signals.append("WEAK_THRUST")

    # T6: Put wall acceleration path clear (weight 1) — proxy: negative GEX amplifies downside
    put_wall_clear = gex_regime == "NEGATIVE" or gex_stress in ("HIGH", "EXTREME")
    if put_wall_clear:
        bear_score += 1
        bear_signals.append("PUT_WALL_CLEAR")

    # ── Trap direction ───────────────────────────────────────────────────────
    if bull_score > bear_score:
        tle_trap_direction = "BULLISH"
    elif bear_score > bull_score:
        tle_trap_direction = "BEARISH"
    elif bull_score > 0:
        tle_trap_direction = "CONFLICTED"
    else:
        tle_trap_direction = "NEUTRAL"

    # ── Active score (aligned to signal direction) ──────────────────────────
    if direction == "CALL":
        active_score = bull_score
    elif direction == "PUT":
        active_score = bear_score
    else:
        active_score = max(bull_score, bear_score)

    # ── Verdict ──────────────────────────────────────────────────────────────
    if active_score >= 11:
        tle_verdict = "CHASE"
    elif active_score >= 7:
        tle_verdict = "CONFIRMATION_ENTRY"
    elif active_score >= 4:
        tle_verdict = "EARLY_PROBE"
    else:
        tle_verdict = "NO_TRADE"

    # ── Human-readable fields ────────────────────────────────────────────────
    if tle_trap_direction == "BULLISH":
        _level = structural_stop or entry_price
        tle_who_is_trapped = f"Shorts below ${_level:.2f}" if _level else "Shorts below support"
        tle_forced_move_level = vwap_level or entry_price
        tle_entry_trigger = "VWAP_RECLAIM" if not vwap_reclaim else "HOLD_ABOVE_VWAP"
    elif tle_trap_direction == "BEARISH":
        _level = entry_price or spot
        tle_who_is_trapped = f"Buyers above ${_level:.2f}" if _level else "Buyers above resistance"
        tle_forced_move_level = vwap_level or entry_price
        tle_entry_trigger = "VWAP_LOSS" if not vwap_below else "HOLD_BELOW_VWAP"
    else:
        tle_who_is_trapped = "None confirmed"
        tle_forced_move_level = vwap_level or entry_price
        tle_entry_trigger = "WAIT_FOR_SETUP"

    return {
        "tle_trap_direction": tle_trap_direction,
        "tle_who_is_trapped": tle_who_is_trapped,
        "tle_forced_move_level": tle_forced_move_level,
        "tle_entry_trigger": tle_entry_trigger,
        "tle_kill_switch": structural_stop,
        "tle_bullish_score": bull_score,
        "tle_bearish_score": bear_score,
        "tle_verdict": tle_verdict,
        "tle_crowd_arrival_target": structural_target,
        "_tle_ticker": ticker,
        "_tle_bull_signals": bull_signals,
        "_tle_bear_signals": bear_signals,
    }


# ── Orchestrator entry point ─────────────────────────────────────────────────

def run_trap_layer(run_id: str, runs_dir: Path) -> bool:
    """
    Phase 5.5 — enrich all packages in a run with TLE fields.
    Called by intelligent_orchestrator.py after backfill, before VANGUARD.
    Returns True even on partial failures so the pipeline continues.
    """
    packages_dir = Path(runs_dir) / run_id / "packages"
    if not packages_dir.exists():
        logger.error("TLE: packages dir not found: %s", packages_dir)
        return False

    pkg_files = sorted(packages_dir.glob("*.package.json"))
    if not pkg_files:
        logger.info("TLE: no packages found in %s — skipping", packages_dir)
        return True

    logger.info("TLE: enriching %d packages in run %s", len(pkg_files), run_id)
    ok_count = 0
    err_count = 0
    verdict_counts: Dict[str, int] = {}

    for pkg_path in pkg_files:
        try:
            with open(pkg_path, "r", encoding="utf-8") as fh:
                pkg = json.load(fh)

            tle_fields = _compute_tle(pkg)
            pkg["tle"] = tle_fields

            with open(pkg_path, "w", encoding="utf-8") as fh:
                json.dump(pkg, fh, indent=2, ensure_ascii=False)

            v = tle_fields.get("tle_verdict", "NO_TRADE")
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
            ok_count += 1

        except Exception as exc:
            logger.warning("TLE: failed on %s: %s", pkg_path.name, exc)
            err_count += 1

    logger.info(
        "TLE: complete — OK=%d ERR=%d | verdicts: %s",
        ok_count,
        err_count,
        " | ".join(f"{k}={v}" for k, v in sorted(verdict_counts.items())),
    )
    return True


# ── CLI entry point ──────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(description="AVSHUNTER Trap-to-Launch Engine (Phase 5.5)")
    parser.add_argument("--run-id", help="Run ID to enrich (e.g. 20260604_003037)")
    parser.add_argument(
        "--runs-dir",
        default=str(_DEFAULT_RUNS_DIR),
        help="Path to runs directory",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Test against latest run without writing back to packages",
    )
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)

    if args.test_mode:
        # Find latest run
        run_dirs = sorted(
            [d for d in runs_dir.iterdir() if d.is_dir() and (d / "packages").exists()],
            reverse=True,
        )
        if not run_dirs:
            print("TEST MODE: no runs with packages found")
            sys.exit(1)
        run_id = run_dirs[0].name
        print(f"TEST MODE: using run {run_id}")

        packages_dir = runs_dir / run_id / "packages"
        pkg_files = sorted(packages_dir.glob("*.package.json"))[:10]
        print(f"TEST MODE: sampling {len(pkg_files)} packages (no write-back)")
        for pkg_path in pkg_files:
            with open(pkg_path, "r", encoding="utf-8") as fh:
                pkg = json.load(fh)
            tle = _compute_tle(pkg)
            disc = pkg.get("discovery", {})
            print(
                f"  {tle['_tle_ticker']:8s} | dir={disc.get('direction','?'):4s} | "
                f"bull={tle['tle_bullish_score']:2d} bear={tle['tle_bearish_score']:2d} | "
                f"verdict={tle['tle_verdict']:<22s} | trap={tle['tle_trap_direction']}"
            )
        return

    if not args.run_id:
        parser.error("--run-id is required unless --test-mode is set")

    ok = run_trap_layer(run_id=args.run_id, runs_dir=runs_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _cli()
