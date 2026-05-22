#!/usr/bin/env python3
"""
AVSHUNTER — Macro Exposure Resolver
=====================================
Resolves per-ticker macro exposure role and reason from the enrichment delta
ticker_role_map and base macro context.

OUTPUT COLUMNS (display only — NEVER read by scoring, EIL, Vanguard, OI, or execution):
  macro_exposure_role    BENEFICIARY | VULNERABLE | NEUTRAL
  macro_exposure_reason  One-line human-readable string

This module is DISPLAY ONLY. Its outputs must never feed into any execution
verdict, execution_permission, EIL scoring, Vanguard StateVector, or OI bonus.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("AVSHUNTER.MACRO_EXPOSURE")

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MACRO_PATH      = REPO / "dropbox" / "macro" / "macro_intelligence_latest.json"
DEFAULT_ENRICHMENT_PATH = REPO / "dropbox" / "macro" / "avshunter_macro_enrichment_delta.json"

NEUTRAL_ROLE   = "NEUTRAL"
NEUTRAL_REASON = "No macro theme exposure identified"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        log.warning("[EXPOSURE] Could not load %s: %s", path.name, exc)
        return None


def _extract_ticker_role_map(enrichment: Dict[str, Any]) -> Dict[str, str]:
    """Build {ticker_upper: role} from the enrichment delta exposure index hint."""
    role_map: Dict[str, str] = {}
    try:
        hint = enrichment.get("macro_exposure_index_build") or {}
        ticker_hint = hint.get("ticker_role_map_hint") or {}
        for role, tickers in ticker_hint.items():
            role_upper = str(role).strip().upper()
            if role_upper not in {"BENEFICIARY", "VULNERABLE", "CONTEXT_ONLY"}:
                continue
            output_role = "NEUTRAL" if role_upper == "CONTEXT_ONLY" else role_upper
            for t in (tickers or []):
                key = str(t).strip().upper()
                if key:
                    role_map[key] = output_role
    except Exception as exc:
        log.debug("[EXPOSURE] Role map extraction failed: %s", exc)
    return role_map


def _build_theme_reasons(enrichment: Dict[str, Any]) -> Dict[str, List[str]]:
    """Map ticker_upper → list of theme names it appears in, keyed by role."""
    reasons: Dict[str, List[str]] = {}
    try:
        for theme in (enrichment.get("theme_deltas") or []):
            theme_name = str(theme.get("theme_name") or theme.get("theme_id") or "")
            if not theme_name:
                continue
            for role_key, tickers in [
                ("BENEFICIARY", theme.get("beneficiary_universe") or []),
                ("VULNERABLE",  theme.get("vulnerable_universe") or []),
            ]:
                for t in tickers:
                    key = str(t).strip().upper()
                    if key:
                        reasons.setdefault(key, [])
                        if theme_name not in reasons[key]:
                            reasons[key].append(theme_name)
    except Exception as exc:
        log.debug("[EXPOSURE] Theme reason extraction failed: %s", exc)
    return reasons


def _macro_narrative_summary(macro: Dict[str, Any]) -> str:
    """One-line macro context label from base macro fields."""
    try:
        regime   = str(macro.get("regime_state") or "").replace("_", " ").title()
        dir_bias = str(macro.get("dir_bias") or "").replace("_", " ").title()
        sector_lead = ", ".join(
            str(s) for s in (macro.get("sector_lead") or [])[:3]
        )
        if sector_lead:
            return f"{regime} / {dir_bias} — sector_lead: {sector_lead}"
        return f"{regime} / {dir_bias}"
    except Exception:
        return "Macro context"


def resolve(
    tickers: List[str],
    macro_path: Optional[Path] = None,
    enrichment_path: Optional[Path] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Resolve macro_exposure_role and macro_exposure_reason for each ticker.

    Parameters
    ----------
    tickers          : list of ticker strings
    macro_path       : path to macro_intelligence_latest.json (default: dropbox/macro/)
    enrichment_path  : path to enrichment delta JSON (default: dropbox/macro/)

    Returns
    -------
    dict keyed by ticker_upper:
        {"macro_exposure_role": str, "macro_exposure_reason": str}
    """
    macro_path      = Path(macro_path) if macro_path else DEFAULT_MACRO_PATH
    enrichment_path = Path(enrichment_path) if enrichment_path else DEFAULT_ENRICHMENT_PATH

    macro      = _load_json(macro_path) or {}
    enrichment = _load_json(enrichment_path) or {}

    role_map      = _extract_ticker_role_map(enrichment)
    theme_reasons = _build_theme_reasons(enrichment)
    macro_summary = _macro_narrative_summary(macro)

    result: Dict[str, Dict[str, str]] = {}
    for ticker in tickers:
        key  = str(ticker).strip().upper()
        role = role_map.get(key, NEUTRAL_ROLE)
        if role == NEUTRAL_ROLE:
            reason = NEUTRAL_REASON
        else:
            themes = theme_reasons.get(key, [])
            if themes:
                reason = f"{role}: {'; '.join(themes[:2])}"
            else:
                reason = f"{role} ({macro_summary})"
        result[key] = {
            "macro_exposure_role":   role,
            "macro_exposure_reason": reason,
        }

    log.info(
        "[EXPOSURE] Resolved %d tickers: BENEFICIARY=%d VULNERABLE=%d NEUTRAL=%d",
        len(result),
        sum(1 for v in result.values() if v["macro_exposure_role"] == "BENEFICIARY"),
        sum(1 for v in result.values() if v["macro_exposure_role"] == "VULNERABLE"),
        sum(1 for v in result.values() if v["macro_exposure_role"] == NEUTRAL_ROLE),
    )
    return result


def enrich_dataframe(df: Any, macro_path: Optional[Path] = None,
                     enrichment_path: Optional[Path] = None) -> Any:
    """
    Add macro_exposure_role and macro_exposure_reason columns to a pandas DataFrame.
    Missing tickers default to NEUTRAL / "No macro theme exposure identified".
    DISPLAY ONLY — these columns must never be read by scoring or execution code.
    """
    if "ticker" not in df.columns:
        log.warning("[EXPOSURE] DataFrame has no 'ticker' column — skipping enrichment")
        return df

    tickers = list(df["ticker"].dropna().astype(str).str.strip().str.upper().unique())
    lookup  = resolve(tickers, macro_path=macro_path, enrichment_path=enrichment_path)

    df = df.copy()
    df["macro_exposure_role"]   = df["ticker"].apply(
        lambda t: lookup.get(str(t).strip().upper(), {}).get("macro_exposure_role",   NEUTRAL_ROLE)
    )
    df["macro_exposure_reason"] = df["ticker"].apply(
        lambda t: lookup.get(str(t).strip().upper(), {}).get("macro_exposure_reason", NEUTRAL_REASON)
    )
    return df
