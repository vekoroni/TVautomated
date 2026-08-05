"""
normalise_macro_contract.py
============================
AVSHUNTER — Macro Contract Normaliser  [FIX-04]

Purpose:
    Reads the raw GPT-generated macro_intelligence_latest.json and writes
    the four structured score fields that RegimeConsensus (regime_consensus.py)
    needs to run in "structured" mode instead of "legacy_fallback".

    Without these four fields the RCS computes using hardcoded fallback
    defaults (net_liquidity=0.5, vix=0.8, gex=0.5, momentum=0.5) regardless
    of actual macro conditions — producing a meaningless neutral RCS=57.5.

    This script ADDS fields to the existing JSON — it does NOT replace it.
    All existing fields are preserved. Safe to run multiple times.

Four fields written (all 0.0–1.0):
    net_liquidity_score   — 0=contracting, 1=expanding
    vix_regime_score      — 0=fearful (high VIX), 1=complacent (low VIX)
    gex_regime_score      — 0=amplifying (neg GEX), 1=dampening (pos GEX)
    macro_momentum_score  — 0=contracting, 1=expanding (= conviction score)

Also writes:
    normalised_at_utc     — timestamp of this normalisation run

Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/
Run:       python scripts/normalise_macro_contract.py

Called by: intelligent_orchestrator.py (add to pre-Phase-1 sequence)
           Can also be run manually before an evening run.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.macro_quant_packet import build_macro_quant_packet
except Exception:
    from macro_quant_packet import build_macro_quant_packet

try:
    from contracts.macro_regime_safety import normalise_macro_regime_fields
except Exception:
    from macro_regime_safety import normalise_macro_regime_fields  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("normalise_macro")

# ─── DEFAULT MACRO PATH ────────────────────────────────────────────────────────
DEFAULT_MACRO_PATH = Path(
    r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\dropbox\macro\macro_intelligence_latest.json"
)

# ─── VIX NORMALISATION ────────────────────────────────────────────────────────
# vix_regime_score = 1 - (vix - VIX_LOW) / (VIX_HIGH - VIX_LOW)
# VIX=12 → score=1.0 (very complacent)
# VIX=40 → score=0.0 (very fearful)
VIX_LOW  = 12.0
VIX_HIGH = 40.0


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _find_field(node: Any, key: str) -> Optional[Any]:
    """Recursively search nested dict for first occurrence of key."""
    if not isinstance(node, dict):
        return None
    if key in node:
        return node[key]
    for v in node.values():
        if isinstance(v, dict):
            result = _find_field(v, key)
            if result is not None:
                return result
    return None


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _clip(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


# ─── SCORE DERIVATIONS ────────────────────────────────────────────────────────

def derive_net_liquidity_score(macro: dict) -> Optional[float]:
    """
    Derive net_liquidity_score (0–1) from available macro fields.

    Priority:
      1. liquidity_pulse or liquidity_status (string label)
      2. net_liquidity_delta_4w (raw $ billions — from FRED)
    """
    # String label path
    label = str(
        _find_field(macro, "liquidity_pulse") or
        _find_field(macro, "liquidity_status") or ""
    ).upper()

    if label:
        if any(x in label for x in ("STRONG_IMPROV", "EXPANDING", "ACCELERAT")):
            return 0.80
        if any(x in label for x in ("MODEST_IMPROV", "IMPROVING", "STABLE_MODEST")):
            return 0.62
        if any(x in label for x in ("STABLE", "FLAT", "NEUTRAL")):
            return 0.50
        if any(x in label for x in ("MODEST_DET", "SLIGHT_CONTR", "WEAKENING")):
            return 0.38
        if any(x in label for x in ("CONTRACTING", "DETERIORATING", "TIGHTENING")):
            return 0.22

    # Raw delta path (WALCL - TGA - RRP change over 4 weeks, $ billions)
    delta = _safe_float(_find_field(macro, "net_liquidity_delta_4w"))
    if delta is not None:
        # Map ±$200bn range to 0–1
        return _clip((delta + 200) / 400)

    return None


def derive_vix_regime_score(macro: dict) -> Optional[float]:
    """
    Derive vix_regime_score (0–1) from vix_spot or vix_5d_avg.
    0 = fearful (high VIX), 1 = complacent (low VIX).
    """
    vix = (
        _safe_float(_find_field(macro, "vix_spot")) or
        _safe_float(_find_field(macro, "vix_5d_avg")) or
        _safe_float(_find_field(macro, "vix_level"))
    )
    if vix is None:
        return None

    score = 1.0 - (vix - VIX_LOW) / (VIX_HIGH - VIX_LOW)
    return _clip(score)


def derive_gex_regime_score(macro: dict) -> Optional[float]:
    """
    Derive gex_regime_score (0–1).
    0 = amplifying (negative GEX, dealers short gamma)
    1 = dampening  (positive GEX, dealers long gamma)

    Currently returns 0.50 (neutral) when no GEX aggregate is available.
    The GEX pipeline (Polygon options chain → aggregate) is not yet connected
    to the macro JSON. This placeholder will be replaced when that feed is live.
    """
    # Try to find any GEX aggregate field
    gex = (
        _safe_float(_find_field(macro, "gex_net_aggregate")) or
        _safe_float(_find_field(macro, "gex_aggregate")) or
        _safe_float(_find_field(macro, "net_gex"))
    )
    if gex is not None:
        # Map $ range: +$5bn (strong dampening) → 1.0; -$5bn (amplifying) → 0.0
        return _clip((gex + 5_000_000_000) / 10_000_000_000)

    # Fallback: GEX string label from macro narrative
    gex_label = str(_find_field(macro, "gex_regime") or "").upper()
    if "DAMPENING" in gex_label or "POSITIVE" in gex_label:
        return 0.70
    if "AMPLIFYING" in gex_label or "NEGATIVE" in gex_label:
        return 0.30

    # No GEX data — neutral placeholder
    log.debug("GEX: no data found — using neutral placeholder 0.50")
    return 0.50


def derive_macro_momentum_score(macro: dict) -> Optional[float]:
    """
    Derive macro_momentum_score (0–1) from conviction_score or macro_conviction.
    These are already normalised 0–1 by GPT synthesis.
    """
    conv = (
        _safe_float(_find_field(macro, "macro_conviction")) or
        _safe_float(_find_field(macro, "conviction_score")) or
        _safe_float(_find_field(macro, "predictability_score"))
    )
    if conv is None:
        return None

    # conviction_score from GPT may be on 0–100 scale — normalise
    if conv > 1.0:
        conv = conv / 100.0

    return _clip(conv)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def normalise(macro_path: Path) -> bool:
    """
    Read macro JSON, derive 4 score fields, write them back.
    Returns True on success.
    """
    if not macro_path.exists():
        log.error(f"Macro JSON not found: {macro_path}")
        return False

    try:
        with open(macro_path, encoding="utf-8") as f:
            macro = json.load(f)
    except Exception as e:
        log.error(f"Failed to read macro JSON: {e}")
        return False

    log.info(f"Loaded: {macro_path}")
    log.info(f"  source_file:         {macro.get('source_file', '?')}")
    log.info(f"  normalised_at_utc:   {macro.get('normalised_at_utc', 'never')}")
    log.info(f"  regime_state:        {_find_field(macro, 'regime_state') or '?'}")
    macro = normalise_macro_regime_fields(macro)
    log.info(f"  regime_sub_state:    {macro.get('regime_sub_state', '?')}")
    log.info(f"  regime_distribution: {macro.get('regime_distribution', '?')}")
    log.info("")

    # ── Derive scores ────────────────────────────────────────────────────────
    scores = {
        "net_liquidity_score":  derive_net_liquidity_score(macro),
        "vix_regime_score":     derive_vix_regime_score(macro),
        "gex_regime_score":     derive_gex_regime_score(macro),
        "macro_momentum_score": derive_macro_momentum_score(macro),
    }

    any_failed = False
    for field, val in scores.items():
        if val is None:
            log.warning(f"  {field}: COULD NOT DERIVE — field will remain absent")
            any_failed = True
        else:
            existing = macro.get(field)
            macro[field] = round(val, 4)
            log.info(f"  {field}: {existing} -> {macro[field]}")

    # ── Timestamp + Phase 3 macro quant baton ────────────────────────────────
    macro["normalised_at_utc"] = datetime.now(timezone.utc).isoformat()
    macro["macro_quant_packet"] = build_macro_quant_packet(macro, macro_path)
    macro["macro_quant_contract_version"] = macro["macro_quant_packet"]["macro_quant_contract_version"]
    log.info(
        "  macro_quant_packet: %s | freshness=%s | quality=%s",
        macro["macro_quant_packet"]["macro_quant_contract_version"],
        macro["macro_quant_packet"]["macro_freshness_status"],
        macro["macro_quant_packet"]["macro_data_quality"],
    )

    # ── Write back ────────────────────────────────────────────────────────────
    try:
        with open(macro_path, "w", encoding="utf-8") as f:
            json.dump(macro, f, indent=2)
        log.info(f"\nWritten: {macro_path}")
        log.info(f"normalised_at_utc: {macro['normalised_at_utc']}")
    except Exception as e:
        log.error(f"Failed to write macro JSON: {e}")
        return False

    if any_failed:
        log.warning(
            "\nSome scores could not be derived — RCS will use legacy fallback "
            "for those components. Run macro rebuild first to populate raw fields."
        )

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AVSHUNTER — Macro Contract Normaliser (FIX-04)"
    )
    parser.add_argument(
        "--macro-path",
        type=Path,
        default=DEFAULT_MACRO_PATH,
        help=f"Path to macro_intelligence_latest.json (default: {DEFAULT_MACRO_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and log scores without writing to file",
    )
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY RUN — no file will be written")
        path = args.macro_path
        if not path.exists():
            log.error(f"File not found: {path}")
            return 2
        with open(path, encoding="utf-8") as f:
            macro = json.load(f)
        log.info(f"net_liquidity_score:  {derive_net_liquidity_score(macro)}")
        log.info(f"vix_regime_score:     {derive_vix_regime_score(macro)}")
        log.info(f"gex_regime_score:     {derive_gex_regime_score(macro)}")
        log.info(f"macro_momentum_score: {derive_macro_momentum_score(macro)}")
        return 0

    ok = normalise(args.macro_path)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
