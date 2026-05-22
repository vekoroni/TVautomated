#!/usr/bin/env python3
"""
AVSHUNTER â€” Sector Alignment Utility
=====================================
Single source of truth for per-ticker sector bias classification.

All pipeline modules (superbrain, options intelligence, EIL, FinalDecisionEngine,
monetisation policy) call this module to derive the 9 required sector alignment
fields from the macro JSON sector_rotation block and the ticker's GICS sector.

DEPLOY
------
  Copy to: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\scripts\\sector_alignment.py

USAGE
-----
  from scripts.sector_alignment import classify_sector_alignment, load_sector_bias_map

  # Once â€” in orchestrator after macro JSON load
  sector_bias_map = load_sector_bias_map(macro_json)

  # Per ticker â€” in any downstream module
  alignment = classify_sector_alignment(ticker, gics_sector, sector_bias_map)
  # alignment is a dict with 9 fields ready to merge into any output row

CHANGE LOG
----------
  v1.0  2026-05  Initial build â€” full sector_rotation block parsing,
                 9-field output schema, GICS normalisation, TAILWIND sizing.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

log = logging.getLogger("SECTOR-ALIGN")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# GICS SECTOR â†’ ETF MAP (canonical GICS sector name â†’ primary sector ETF)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

GICS_TO_ETF: Dict[str, str] = {
    "Information Technology":     "XLK",
    "Technology":                 "XLK",
    "Health Care":                "XLV",
    "Healthcare":                 "XLV",
    "Financials":                 "XLF",
    "Financial Services":         "XLF",
    "Consumer Discretionary":     "XLY",
    "Consumer Staples":           "XLP",
    "Industrials":                "XLI",
    "Energy":                     "XLE",
    "Materials":                  "XLB",
    "Real Estate":                "XLRE",
    "Communication Services":     "XLC",
    "Communications":             "XLC",
    "Utilities":                  "XLU",
}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SECTOR ALIGNMENT SCORE MULTIPLIERS
# Applied as a 4th multiplier in FinalDecisionEngine.decide() sizing chain
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SECTOR_SIZE_MULTIPLIERS: Dict[str, float] = {
    "TAILWIND":  1.10,   # Macro explicitly favours this sector â€” boost allocation
    "NEUTRAL":   1.00,   # No macro opinion â€” standard sizing
    "MIXED":     0.80,   # Conflicting signals â€” reduce with warning flag
    "HEADWIND":  0.55,   # Macro explicitly opposes this sector â€” significant cut
    "UNKNOWN":   0.80,   # No sector data â€” treat conservatively
}

# At this macro_conviction threshold and above, HEADWIND â†’ BLOCK rather than
# just a size penalty. Reflects high-confidence macro call.
HEADWIND_BLOCK_CONVICTION_THRESHOLD = 0.80

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# FIELD NAMES â€” 9 required output fields (sector alignment contract)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#
# macro_sector_bias          TAILWIND | NEUTRAL | MIXED | HEADWIND | UNKNOWN
# sector_alignment_label     Human-readable label e.g. "Tech HEADWIND (XLK avoid)"
# sector_alignment_score     float multiplier 0.55â€“1.10 from SECTOR_SIZE_MULTIPLIERS
# sector_alignment_flag      BLOCK | REDUCE | NEUTRAL | BOOST â€” execution guidance
# sector_etf_mapped          ETF ticker mapped from GICS sector e.g. "XLK"
# gics_sector_norm           Normalised GICS sector string
# sector_bias_source         macro_json | inferred | unknown â€” traceability
# sector_conviction_context  float â€” macro_conviction at time of classification
# sector_alignment_note      one-line rationale string

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MACRO JSON SECTOR_ROTATION BLOCK LOADER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_sector_bias_map(macro_json: dict) -> Dict[str, str]:
    """
    Extract the sector_bias_map from the macro JSON sector_rotation block.

    Returns a dict keyed by GICS sector name (upper-cased, stripped) with
    values: TAILWIND | NEUTRAL | HEADWIND | MIXED

    Falls back gracefully:
      - If sector_rotation block absent  â†’ derives from sector_lead/sector_avoid
      - If neither present               â†’ returns empty dict (all UNKNOWN)

    Parameters
    ----------
    macro_json : dict
        Parsed macro_intelligence_latest.json

    Returns
    -------
    dict  e.g. {"INFORMATION TECHNOLOGY": "HEADWIND", "ENERGY": "TAILWIND", ...}
    """
    bias_map: Dict[str, str] = {}

    # â”€â”€ Primary path: sector_rotation.sector_bias_map (Step 1 schema) â”€â”€â”€â”€â”€â”€â”€â”€
    sector_rotation = macro_json.get("sector_rotation", {})
    if isinstance(sector_rotation, dict):
        raw_map = sector_rotation.get("sector_bias_map", {})
        if isinstance(raw_map, dict) and raw_map:
            for sector, bias in raw_map.items():
                key = str(sector).strip().upper()
                val = str(bias).strip().upper()
                if val in ("TAILWIND", "NEUTRAL", "HEADWIND", "MIXED"):
                    bias_map[key] = val
                else:
                    bias_map[key] = "NEUTRAL"
            log.debug("Loaded sector_bias_map from sector_rotation block: %d entries", len(bias_map))
            return bias_map

    # â”€â”€ Fallback: derive from sector_lead / sector_avoid arrays â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # These are ETF tickers (e.g. "XLK", "XLY") â€” map back to GICS sector names
    ETF_TO_GICS: Dict[str, str] = {v: k for k, v in GICS_TO_ETF.items()}
    # Deduplicate (multiple GICS map to same ETF â€” keep longest name)
    ETF_TO_GICS = {
        etf: max(
            (gics for gics, e in GICS_TO_ETF.items() if e == etf),
            key=len,
            default=etf
        )
        for etf in set(GICS_TO_ETF.values())
    }

    sector_lead  = macro_json.get("sector_lead",  []) or []
    sector_avoid = macro_json.get("sector_avoid", []) or []

    # Also check extras.sector_tilt if present
    extras = macro_json.get("extras", {})
    if isinstance(extras, dict):
        extras_st = extras.get("sector_tilt", {})
        if isinstance(extras_st, dict):
            sector_lead  = sector_lead  or extras_st.get("lead_long", []) or extras_st.get("long", [])
            sector_avoid = sector_avoid or extras_st.get("avoid",    [])

    for etf in sector_lead:
        etf_upper = str(etf).strip().upper()
        gics = ETF_TO_GICS.get(etf_upper, etf_upper)
        bias_map[gics.upper()] = "TAILWIND"

    for etf in sector_avoid:
        etf_upper = str(etf).strip().upper()
        gics = ETF_TO_GICS.get(etf_upper, etf_upper)
        key = gics.upper()
        if key not in bias_map:  # lead overrides avoid
            bias_map[key] = "HEADWIND"

    if bias_map:
        log.debug(
            "Derived sector_bias_map from sector_lead/avoid: %d entries", len(bias_map)
        )
    else:
        log.warning(
            "No sector_rotation block and no sector_lead/avoid â€” sector alignment will be UNKNOWN for all tickers"
        )

    return bias_map


def load_macro_conviction(macro_json: dict) -> float:
    """Extract macro_conviction float from macro JSON (searches top-level + extras)."""
    for key in ("macro_conviction", "conviction_score"):
        val = macro_json.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    extras = macro_json.get("extras", {})
    if isinstance(extras, dict):
        for key in ("conviction_score", "macro_conviction"):
            val = extras.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
    return 0.60  # default moderate conviction


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PER-TICKER CLASSIFIER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def classify_sector_alignment(
    ticker: str,
    gics_sector: Optional[str],
    sector_bias_map: Dict[str, str],
    macro_conviction: float = 0.60,
    macro_regime_state: str = "",
) -> Dict:
    """
    Classify a ticker's sector alignment against the current macro regime.

    Parameters
    ----------
    ticker          : str   Ticker symbol (e.g. "AAPL")
    gics_sector     : str   GICS sector name (e.g. "Information Technology")
                            Can be None or empty â€” returns UNKNOWN alignment
    sector_bias_map : dict  From load_sector_bias_map() â€” keyed by upper-cased GICS
    macro_conviction: float From macro JSON (0.0â€“1.0)

    Returns
    -------
    dict  9 required fields ready to merge into any pipeline output row:
        macro_sector_bias
        sector_alignment_label
        sector_alignment_score
        sector_alignment_flag
        sector_etf_mapped
        gics_sector_norm
        sector_bias_source
        sector_conviction_context
        sector_alignment_note
    """
    import os as _os
    _regime_state = (
        macro_regime_state.strip().upper()
        or _os.environ.get("AVSHUNTER_MACRO_REGIME_STATE", "").strip().upper()
    )
    ticker_upper = str(ticker).strip().upper()

    # â”€â”€ Normalise GICS sector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    gics_norm = ""
    if gics_sector:
        gics_norm = str(gics_sector).strip()
    gics_key  = gics_norm.upper()

    # â”€â”€ Map to ETF â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sector_etf = GICS_TO_ETF.get(gics_norm, GICS_TO_ETF.get(gics_key, ""))

    # â”€â”€ Look up bias â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    bias_source = "unknown"

    if not gics_key:
        macro_bias = "UNKNOWN"
        bias_source = "unknown"
    elif sector_bias_map:
        # Try exact match, then partial match (for variant sector names)
        macro_bias = sector_bias_map.get(gics_key)
        if macro_bias is None:
            # Partial: e.g. "TECH" found in "INFORMATION TECHNOLOGY"
            for map_key, map_val in sector_bias_map.items():
                if gics_key in map_key or map_key in gics_key:
                    macro_bias = map_val
                    break
        macro_bias  = macro_bias or "NEUTRAL"
        bias_source = "macro_json"
    else:
        macro_bias  = "UNKNOWN"
        bias_source = "inferred"

    # â”€â”€ Determine flag and check high-conviction HEADWIND block â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if macro_bias == "TAILWIND":
        flag  = "BOOST"
        note  = (
            f"{ticker_upper} sector ({gics_norm or 'N/A'}) is a macro TAILWIND"
            f" â€” allocation boosted (macro_conviction={macro_conviction:.2f})"
        )
    elif macro_bias == "HEADWIND":
        # Approach warning: log only, no block
        if 0.65 <= macro_conviction < 0.80:
            log.warning(
                "[SECTOR] %s in HEADWIND sector %s. Conviction %.2f approaching floor. "
                "No block applied. Size modifier: %.0f%%.",
                ticker_upper, gics_norm or "N/A", macro_conviction,
                SECTOR_SIZE_MULTIPLIERS["HEADWIND"] * 100,
            )
        # MACRO REDESIGN: hard BLOCK only on RISK_OFF regime, not conviction alone
        if _regime_state == "RISK_OFF":
            flag = "SECTOR_RISK_OFF_BLOCK"
            log.warning(
                "[SECTOR] %s BLOCKED: HEADWIND sector + RISK_OFF regime confirmed.",
                ticker_upper,
            )
            note = (
                f"{ticker_upper} sector ({gics_norm or 'N/A'}) is a HEADWIND"
                f" in confirmed RISK_OFF regime -- SECTOR_RISK_OFF_BLOCK"
            )
        else:
            flag = "HEADWIND_REDUCE"
            note = (
                f"{ticker_upper} sector ({gics_norm or 'N/A'}) is a HEADWIND"
                f" -- size reduced to {SECTOR_SIZE_MULTIPLIERS['HEADWIND']:.0%}"
                f" (macro_conviction={macro_conviction:.2f})"
            )
    elif macro_bias == "MIXED":
        flag  = "REDUCE"
        note  = (
            f"{ticker_upper} sector ({gics_norm or 'N/A'}) has MIXED macro signals"
            f" â€” size reduced to {SECTOR_SIZE_MULTIPLIERS['MIXED']:.0%}"
        )
    elif macro_bias == "UNKNOWN":
        flag  = "REDUCE"
        note  = (
            f"{ticker_upper} has no GICS sector data â€” treated conservatively"
            f" (size {SECTOR_SIZE_MULTIPLIERS['UNKNOWN']:.0%})"
        )
    else:  # NEUTRAL
        flag  = "NEUTRAL"
        note  = (
            f"{ticker_upper} sector ({gics_norm or 'N/A'}) is NEUTRAL"
            f" â€” standard sizing"
        )

    # â”€â”€ Build label â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    etf_suffix = f" ({sector_etf})" if sector_etf else ""
    label = f"{gics_norm or ticker_upper}{etf_suffix} {macro_bias}"
    if flag == "SECTOR_RISK_OFF_BLOCK":
        label += " RISK_OFF_BLOCK"

    alignment_score = SECTOR_SIZE_MULTIPLIERS.get(macro_bias, SECTOR_SIZE_MULTIPLIERS["UNKNOWN"])

    return {
        "macro_sector_bias":         macro_bias,
        "sector_alignment_label":    label,
        "sector_alignment_score":    round(alignment_score, 4),
        "sector_alignment_flag":     flag,
        "sector_etf_mapped":         sector_etf or "",
        "gics_sector_norm":          gics_norm,
        "sector_bias_source":        bias_source,
        "sector_conviction_context": round(macro_conviction, 4),
        "sector_alignment_note":     note,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CONVENIENCE: classify directly from a signal row dict
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def classify_from_row(
    row: Dict,
    sector_bias_map: Dict[str, str],
    macro_conviction: float = 0.60,
) -> Dict:
    """
    Convenience wrapper â€” extract ticker and sector from a signal row dict,
    then call classify_sector_alignment().

    Production-safe lookup order:
      1. gics_sector
      2. gics_sector_norm
      3. sector
      4. gics_industry
      5. sector_etf / sector_etf_mapped â€” ETF reverse-mapped to GICS sector name

    The ETF fallback (step 4) is critical for Options Intelligence rows which carry
    sector_etf=XLK but no gics_sector field. Without it, AAPL+XLK would silently
    return macro_sector_bias=UNKNOWN instead of the correct HEADWIND/TAILWIND.
    D-MACRO-SEC-002 fix.
    """
    ticker = str(row.get("ticker", row.get("symbol", ""))).strip().upper()

    gics_sector = (
        row.get("gics_sector")
        or row.get("gics_sector_norm")
        or row.get("sector")
        or row.get("scanner_sector")
        or row.get("gics_industry")
        or ""
    )

    # â”€â”€ ETF fallback: reverse-map XLK/XLE/etc â†’ GICS sector name â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Required for OI rows that carry sector_etf but not gics_sector
    if not gics_sector:
        etf = (
            row.get("sector_etf")
            or row.get("sector_etf_mapped")
            or row.get("macro_sector_etf")
            or ""
        )
        etf = str(etf).strip().upper()

        _ETF_TO_GICS: Dict[str, str] = {
            "XLK":  "Information Technology",
            "XLV":  "Health Care",
            "XLF":  "Financials",
            "XLY":  "Consumer Discretionary",
            "XLP":  "Consumer Staples",
            "XLI":  "Industrials",
            "XLE":  "Energy",
            "XLB":  "Materials",
            "XLRE": "Real Estate",
            "XLC":  "Communication Services",
            "XLU":  "Utilities",
        }
        gics_sector = _ETF_TO_GICS.get(etf, "")

    return classify_sector_alignment(
        ticker=ticker,
        gics_sector=gics_sector,
        sector_bias_map=sector_bias_map,
        macro_conviction=macro_conviction,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SELF-TEST
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    _sample_macro = {
        "macro_conviction": 0.72,
        "sector_rotation": {
            "sector_bias_map": {
                "Information Technology": "HEADWIND",
                "Energy":                 "TAILWIND",
                "Materials":              "TAILWIND",
                "Financials":             "NEUTRAL",
                "Health Care":            "MIXED",
            },
            "strongest_sectors": ["Energy", "Materials"],
            "weakest_sectors":   ["Information Technology"],
            "rotation_signal":   "RISK_OFF_GROWTH_TO_VALUE",
        },
    }

    _sbm = load_sector_bias_map(_sample_macro)
    print(f"sector_bias_map loaded: {_sbm}\n")

    _mc = load_macro_conviction(_sample_macro)

    _test_cases = [
        ("AAPL", "Information Technology"),
        ("XOM",  "Energy"),
        ("NEM",  "Materials"),
        ("JPM",  "Financials"),
        ("ABT",  "Health Care"),
        ("UNKN", ""),
    ]

    for t, s in _test_cases:
        result = classify_sector_alignment(t, s, _sbm, _mc)
        print(f"  {t:6s} | {result['macro_sector_bias']:10s} | flag={result['sector_alignment_flag']:7s} | score={result['sector_alignment_score']:.2f} | {result['sector_alignment_note']}")

    # Test fallback (no sector_rotation block)
    print("\n--- fallback test (sector_lead/avoid only) ---")
    _fallback_macro = {
        "macro_conviction": 0.55,
        "sector_lead":  ["XLE", "XLB"],
        "sector_avoid": ["XLK", "XLC"],
    }
    _sbm2 = load_sector_bias_map(_fallback_macro)
    print(f"fallback bias_map: {_sbm2}")
    result2 = classify_sector_alignment("MSFT", "Information Technology", _sbm2, 0.55)
    print(f"  MSFT | {result2['macro_sector_bias']} | flag={result2['sector_alignment_flag']} | score={result2['sector_alignment_score']:.2f}")

    # â”€â”€ D-MACRO-SEC-002 regression test: ETF fallback in classify_from_row â”€â”€â”€â”€â”€
    print("\n--- ETF fallback test (D-MACRO-SEC-002: OI rows carry sector_etf not gics_sector) ---")
    _sbm3 = {
        "INFORMATION TECHNOLOGY": "HEADWIND",
        "ENERGY":                 "TAILWIND",
    }
    # Simulate an OI output row: has sector_etf but no gics_sector/sector field
    _oi_row_aapl = {"ticker": "AAPL", "sector_etf": "XLK", "sector_5d_return": 1.2}
    _oi_row_xom  = {"ticker": "XOM",  "sector_etf": "XLE", "sector_5d_return": 2.1}
    _oi_row_unkn = {"ticker": "ZZZ",  "sector_5d_return": 0.0}  # no ETF at all
    for _r in [_oi_row_aapl, _oi_row_xom, _oi_row_unkn]:
        _res = classify_from_row(_r, _sbm3, 0.72)
        _t = _r["ticker"]
        _etf = _r.get("sector_etf", "N/A")
        print(f"  {_t:6s} ETF={_etf:6s} â†’ {_res['macro_sector_bias']:10s} | flag={_res['sector_alignment_flag']:7s} | gics={_res['gics_sector_norm']}")
    # Validate D-MACRO-SEC-002 is fixed: AAPL+XLK must NOT return UNKNOWN
    _aapl_res = classify_from_row(_oi_row_aapl, _sbm3, 0.72)
    assert _aapl_res["macro_sector_bias"] != "UNKNOWN", f"D-MACRO-SEC-002 STILL PRESENT: AAPL+XLK returned UNKNOWN"
    print("  D-MACRO-SEC-002 regression: PASSED âœ… (AAPL+XLK correctly classified, not UNKNOWN)")

