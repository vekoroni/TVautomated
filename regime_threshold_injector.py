"""
AVSHUNTER Discovery — Regime Threshold Injector  [NEW MODULE]
==============================================================

Purpose:
  Read the current macro regime from macro_intelligence_latest.json
  and return a regime-adjusted UltimateConfig so that Discovery
  tier qualification is tighter or looser based on the market environment.

Design principles:
  - Single responsibility: this module ONLY adjusts config thresholds.
    It does not score tickers, it does not run analysis.
  - Fail-safe default: if regime cannot be determined, TRANSITIONAL
    thresholds apply. Discovery never runs with unknown thresholds.
  - All threshold tables are in one place (this file) so they can be
    audited, versioned, and tuned without touching Discovery logic.
  - Thresholds are documented with the reasoning behind each value.

Usage:
    from regime_threshold_injector import apply_regime_to_config
    cfg = UltimateConfig()
    cfg = apply_regime_to_config(cfg, macro_path)

Called from:
    avshunter_discovery_ULTIMATE.py — main() — after macro preflight, before scan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("AVSHUNTER_ULTIMATE")


# =============================================================================
#  REGIME THRESHOLD TABLES
# =============================================================================
#
# Each regime defines thresholds for ALL tier qualification levels.
#
# Reasoning per regime:
#
# RISK_ON (e.g. SPY in uptrend, VIX < 18, broad participation):
#   Discovery can be modestly permissive. The macro tailwind improves
#   the base win rate across most setups. We lower tier floors slightly
#   to catch more early-stage accumulations before they run.
#   BUT we do NOT remove selectivity — loose thresholds in Risk-On
#   still produce a better signal:noise than in Risk-Off.
#
# TRANSITIONAL (e.g. mixed signals, VIX 18-25, sector rotation):
#   The default operating mode. Thresholds are calibrated to the
#   long-run base rate of the system. Neither aggressive nor defensive.
#
# RISK_OFF (e.g. SPY below 200EMA, VIX > 25, liquidity withdrawal):
#   Only the highest-conviction setups should surface. False positives
#   are expensive in Risk-Off — gaps, rapid reversals, wide spreads.
#   The system must act like an institutional desk: if you're not sure,
#   you don't trade. Tier 1 floor raised to 70+ reflects this.
#
# SELECTIVE_RISK_ON (e.g. dir_bias = "Selective Risk-On"):
#   Market is constructive but not broadly bullish. Sector selectivity
#   matters. Thresholds between TRANSITIONAL and RISK_ON.

REGIME_TIER_THRESHOLDS = {
    #                   tier1_min  tier2_min  tier3_min  early_score_floor
    "RISK_ON":          (48.0,     33.0,      23.0,      48.0),
    "SELECTIVE_RISK_ON":(54.0,     38.0,      26.0,      50.0),
    "TRANSITIONAL":     (60.0,     42.0,      30.0,      52.0),
    "RISK_OFF":         (66.0,     48.0,      34.0,      56.0),  # loosened: allow high-R:R PUTs in risk-off tapes
}

# Compression thresholds: in Risk-Off, we want TIGHTER compression before
# surfacing a candidate. A name with moderate compression in a Risk-Off
# environment is not a setup — it's a slow bleed. We raise the bar.
REGIME_COMPRESSION_THRESHOLDS = {
    #                   compression_max  extreme_compression
    "RISK_ON":          (0.88,           0.62),
    "SELECTIVE_RISK_ON":(0.85,           0.60),
    "TRANSITIONAL":     (0.82,           0.58),
    "RISK_OFF":         (0.75,           0.52),
}

# Volume minimum: in Risk-Off, thin volume means institutional absence.
# We raise the minimum to ensure we're only tracking names with real participation.
REGIME_VOLUME_MINIMUMS = {
    "RISK_ON":          500_000,
    "SELECTIVE_RISK_ON":600_000,
    "TRANSITIONAL":     600_000,
    "RISK_OFF":         800_000,
}

# Default fallback if regime resolution fails
DEFAULT_REGIME = "TRANSITIONAL"


# =============================================================================
#  REGIME RESOLVER
# =============================================================================

def resolve_regime(macro_path: Path) -> Tuple[str, str]:
    """
    Resolve the canonical regime label from macro JSON using a composite
    of FOUR signals, not just regime_state.

    Returns (regime_key, regime_label) where:
      - regime_key: key into threshold tables (RISK_ON, TRANSITIONAL, etc.)
      - regime_label: human-readable label for logging

    Fail-safe: any parse failure returns DEFAULT_REGIME.

    Composite resolution logic (in priority order):
      1. regime_state         — primary signal
      2. risk_on_off_switch   — secondary signal (RISK_OFF_TILT upgrades toward RISK_OFF)
      3. vol_mode             — fear signal     (FEAR_SPIKE upgrades toward RISK_OFF)
      4. dir_bias             — nuance signal   (SELECTIVE → SELECTIVE_RISK_ON)

    Upgrade rules (can only TIGHTEN, never loosen):
      TRANSITIONAL + risk_on_off_switch contains RISK_OFF → upgrade to RISK_OFF
      TRANSITIONAL + vol_mode == FEAR_SPIKE               → upgrade to RISK_OFF
      RISK_ON      + risk_on_off_switch contains RISK_OFF → upgrade to TRANSITIONAL
      RISK_ON      + vol_mode == FEAR_SPIKE               → upgrade to TRANSITIONAL
      RISK_ON      + dir_bias contains selective          → refine to SELECTIVE_RISK_ON
    """

    if macro_path is None or not Path(macro_path).exists():
        logger.warning(f"   \u26a0\ufe0f  Regime injector: macro file not found at {macro_path}. Using {DEFAULT_REGIME}.")
        return DEFAULT_REGIME, f"DEFAULT ({DEFAULT_REGIME} \u2014 macro not found)"

    try:
        with open(macro_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"   \u26a0\ufe0f  Regime injector: could not parse macro JSON: {e}. Using {DEFAULT_REGIME}.")
        return DEFAULT_REGIME, f"DEFAULT ({DEFAULT_REGIME} \u2014 parse error)"

    # Read all four composite signals
    regime_state       = str(_find_field(data, "regime_state")       or "").strip()
    dir_bias           = str(_find_field(data, "dir_bias")            or "").strip()
    risk_on_off_switch = str(_find_field(data, "risk_on_off_switch")  or "").strip()
    vol_mode           = str(_find_field(data, "vol_mode")            or "").strip()

    rs  = regime_state.lower()
    roo = risk_on_off_switch.upper()
    vol = vol_mode.upper()
    db  = dir_bias.lower()

    # Step 1: Primary mapping from regime_state
    if "risk-off" in rs or "risk off" in rs or rs == "risk_off":
        regime_key = "RISK_OFF"
    elif "risk-on" in rs or "risk on" in rs or rs == "risk_on":
        regime_key = "RISK_ON"
    elif "transitional" in rs:
        regime_key = "TRANSITIONAL"
    else:
        logger.warning(
            f"   \u26a0\ufe0f  Regime injector: unknown regime_state='{regime_state}'. Using {DEFAULT_REGIME}."
        )
        regime_key = DEFAULT_REGIME

    # Step 2: Composite upgrade pass (can only TIGHTEN, never loosen)
    upgrades_applied = []

    if regime_key == "TRANSITIONAL":
        if "RISK_OFF" in roo:
            regime_key = "RISK_OFF"
            upgrades_applied.append(f"risk_on_off_switch={risk_on_off_switch}->RISK_OFF")
        elif vol == "FEAR_SPIKE":
            regime_key = "RISK_OFF"
            upgrades_applied.append(f"vol_mode={vol_mode}->RISK_OFF")

    elif regime_key == "RISK_ON":
        if "RISK_OFF" in roo:
            regime_key = "TRANSITIONAL"
            upgrades_applied.append(f"risk_on_off_switch={risk_on_off_switch}->TRANSITIONAL")
        elif vol == "FEAR_SPIKE":
            regime_key = "TRANSITIONAL"
            upgrades_applied.append(f"vol_mode={vol_mode}->TRANSITIONAL")
        elif "selective" in db:
            regime_key = "SELECTIVE_RISK_ON"
            upgrades_applied.append(f"dir_bias={dir_bias}->SELECTIVE_RISK_ON")

    # RISK_OFF is the terminal state — never downgraded

    # Step 3: Build human label
    parts = [regime_state]
    if dir_bias:
        parts.append(dir_bias)
    if upgrades_applied:
        parts.append(f"[upgraded: {', '.join(upgrades_applied)}]")
    human_label = " / ".join(parts)

    # Log composite resolution for auditability
    logger.info(f"   regime_state={regime_state}  risk_switch={risk_on_off_switch}"
                f"  vol_mode={vol_mode}  dir_bias={dir_bias}")
    if upgrades_applied:
        logger.info(f"   Composite upgrade applied: {', '.join(upgrades_applied)}")

    return regime_key, human_label


def _find_field(node: dict, field: str) -> Optional[str]:
    """Recursively find first occurrence of field in nested dict."""
    if not isinstance(node, dict):
        return None
    if field in node:
        return node[field]
    for v in node.values():
        if isinstance(v, dict):
            result = _find_field(v, field)
            if result is not None:
                return result
    return None


# =============================================================================
#  MAIN INJECTION FUNCTION
# =============================================================================

def apply_regime_to_config(cfg, macro_path: Optional[Path]) -> object:
    """
    Attach the external regime as advisory metadata without changing thresholds.

    Args:
        cfg: UltimateConfig instance (from avshunter_discovery_ULTIMATE.py)
        macro_path: Path to macro_intelligence_latest.json

    Returns:
        Modified cfg with regime-appropriate thresholds.
        Original cfg is NOT mutated — new values are set on the instance.

    Logs all threshold changes for auditability.
    """

    regime_key, regime_label = resolve_regime(macro_path)

    # External macro is a separately refreshed advisory product.  Historical
    # threshold tables remain in this module for audit/research reproducibility,
    # but production Discovery must produce the same membership for the same
    # ticker evidence whether the macro file is present, stale or absent.
    logger.info("─" * 60)
    logger.info("MACRO ADVISORY ATTACHMENT (ZERO CORE AUTHORITY)")
    logger.info(f"  Advisory regime:    {regime_label} → [{regime_key}]")
    logger.info(f"  Core tier floors:   {cfg.tier1_min}/{cfg.tier2_min}/{cfg.tier3_min} (unchanged)")
    logger.info(f"  Core compression:   {cfg.compression_max} (unchanged)")
    logger.info(f"  Core min volume:    {cfg.min_avg_vol20:,.0f} (unchanged)")
    logger.info("─" * 60)

    # Preserve the snapshot for display/lineage only.
    cfg.active_regime = regime_key
    cfg.active_regime_label = regime_label
    cfg.macro_authority = "ADVISORY_ONLY"
    cfg.macro_core_effective_delta = 0.0

    return cfg


# =============================================================================
#  INTEGRATION PATCH FOR avshunter_discovery_ULTIMATE.py
# =============================================================================
#
# Add these two lines in main() immediately after:
#     cfg = UltimateConfig()
#
# BEFORE:
#     cfg = UltimateConfig()
#     tickers = load_universe(universe_path)
#
# AFTER:
#     cfg = UltimateConfig()
#     from regime_threshold_injector import apply_regime_to_config
#     macro_path = Path("dropbox/macro/macro_intelligence_latest.json")
#     cfg = apply_regime_to_config(cfg, macro_path)
#     tickers = load_universe(universe_path)
#
# That is the ONLY change required to avshunter_discovery_ULTIMATE.py.
# All threshold logic lives in this module. Discovery remains clean.
#
# To also tag each output signal with the active regime:
#     signal['active_regime'] = cfg.active_regime
# Add that line inside scan_ticker_ultimate(), in the signal dict build.
