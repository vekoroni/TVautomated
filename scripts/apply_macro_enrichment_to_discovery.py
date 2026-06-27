#!/usr/bin/env python3
"""
Apply additive macro enrichment context to discovery CSV rows.

This keeps ticker intake plain while making narrative/event macro context
available to the Options layer through the discovery baton. It never changes
existing discovery columns and never changes protected macro gates.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from contracts.macro_enrichment_delta import (  # noqa: E402
    candidate_macro_enrichment_audit,
    find_macro_enrichment_delta,
    load_macro_enrichment_delta,
    merge_macro_enrichment_delta,
)
from scripts.macro_quant_packet import build_macro_quant_packet  # noqa: E402


# L1-CHANGE-1: Route demotion guard.
# Scanner VMS is now the primary routing gate. News terminal enrichment delta
# CANNOT assign pipeline routes. Any tradability_route value from the enrichment
# delta is explicitly demoted to CONTEXT_ONLY at this consumption point.
DEMOTED_ROUTES = frozenset({
    "FULL_PIPELINE", "DISCOVERY_ONLY", "WATCHLIST_ONLY",
    "MACRO_ONLY", "NEWS_WATCH_ONLY", "CATALYST_ONLY",
})


def _read_enrichment_route(route_value: str) -> str:
    """Demote any news terminal route recommendation to CONTEXT_ONLY."""
    return "CONTEXT_ONLY"


ENRICHMENT_DISCOVERY_FIELDS = [
    "macro_enrichment_theme_count",
    "macro_enrichment_theme_ids",
    "macro_enrichment_roles",
    "macro_enrichment_event_guards",
    "macro_enrichment_confirmation_required",
    "macro_enrichment_conflict_flags",
    "macro_enrichment_pressure_label",
    "macro_enrichment_options_bonus_hint",
    "macro_enrichment_gate_preserved",
    "macro_enrichment_macro_filter",
    "macro_enrichment_trigger_required",
    "macro_enrichment_put_gate_permission",
    "macro_enrichment_audit_note",
    "macro_alignment_state",
    "macro_applicability",
    "macro_direction_authority",
    "macro_direction_vote",
    "macro_raw_direction_hint",
    "macro_can_invert_direction",
    "structure_first_required",
    "trade_type_classification",
    "macro_interpretation_reason",
]

# Bias fields stamped from binary options analysis policy bias map
BIAS_DISCOVERY_FIELDS = ["macro_bias", "macro_abstain", "macro_bias_source"]

# Tickers exempt from sector headwind — power generation exception
MACRO_ABSTAIN_TICKERS = {"VST", "NEE", "CEG"}


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def json_cell(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    if value is None:
        return ""
    return str(value)


def as_bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def ordered_fields(existing: Iterable[str]) -> List[str]:
    fields = list(existing)
    for field in ENRICHMENT_DISCOVERY_FIELDS + BIAS_DISCOVERY_FIELDS:
        if field not in fields:
            fields.append(field)
    return fields


def bonus_hint_from_audit(macro: Dict[str, Any], audit: Dict[str, Any]) -> float:
    macro_filter = str(macro.get("macro_filter") or "").upper()
    trigger_required = bool(macro.get("trigger_required"))
    conflicts = audit.get("macro_enrichment_conflict_flags") or []
    confirmations = audit.get("macro_enrichment_confirmation_required") or []
    theme_count = int(audit.get("macro_enrichment_theme_count") or 0)
    if theme_count <= 0:
        return 0.0
    if "NO_GO" in macro_filter or trigger_required or conflicts:
        return 0.0
    if confirmations:
        return 1.0
    return 3.0


def _extract_bias_maps(macro: Dict[str, Any]) -> tuple:
    """Return (call_tickers, put_tickers, context_tickers) sets from bias map."""
    try:
        extras   = macro.get("extras") or {}
        delta    = extras.get("macro_enrichment_delta") or {}
        policy   = delta.get("binary_options_analysis_policy") or {}
        bias_map = policy.get("current_macro_bias_map") or {}
        call_t   = set(t.upper() for t in (bias_map.get("CALL_CONTEXT_OR_TAILWIND") or []))
        put_t    = set(t.upper() for t in (bias_map.get("PUT_CONTEXT_OR_HEADWIND") or []))
        ctx_t    = set(t.upper() for t in (bias_map.get("CONTEXT_ONLY_OR_REASSESSMENT") or []))
        return call_t, put_t, ctx_t
    except Exception:
        return set(), set(), set()


def _resolve_macro_bias(ticker: str, call_tickers: set, put_tickers: set, context_tickers: set) -> tuple:
    """Return (macro_bias, macro_abstain str, macro_bias_source) for a ticker."""
    t = str(ticker).strip().upper()
    if t in MACRO_ABSTAIN_TICKERS:
        return "NEUTRAL", "true", "POWER_GEN_EXCEPTION"
    if t in call_tickers:
        return "CALL_TAILWIND", "false", "ENRICHMENT_DELTA"
    if t in put_tickers:
        return "PUT_HEADWIND", "false", "ENRICHMENT_DELTA"
    if t in context_tickers:
        return "CONTEXT_ONLY", "false", "ENRICHMENT_DELTA"
    return "NEUTRAL", "false", "NO_ENRICHMENT_MATCH"


def _load_macro_bias_map_from_macro_json(macro: Dict[str, Any]) -> Dict[str, str]:
    """
    Build sector_etf → macro_bias map from macro JSON extras.sectors block.
    Handles both string values ("LEAD_LONG") and dict values ({"signal": "LEAD_LONG"}).
    """
    _signal_to_bias = {
        "LEAD_LONG":         "CALL_TAILWIND",
        "LONG":              "CALL_TAILWIND",
        "NEUTRAL":           "NEUTRAL",
        "NEUTRAL_DEFENSIVE": "NEUTRAL",
        "REDUCE_TACTICAL":   "PUT_HEADWIND",
        "AVOID":             "PUT_HEADWIND",
    }
    try:
        extras      = macro.get("extras") or {}
        sectors_raw = extras.get("sectors") or {}
        result: Dict[str, str] = {}
        for etf, info in sectors_raw.items():
            if isinstance(info, dict):
                signal = str(info.get("signal") or info.get("macro_signal") or "").upper()
            else:
                signal = str(info or "").upper()
            result[str(etf).upper().strip()] = _signal_to_bias.get(signal, "NEUTRAL")
        return result
    except Exception:
        return {}


def _bias_from_sector_etf(sector_etf: str, macro_bias_map: Dict[str, str]) -> str:
    """Map a sector ETF ticker to macro_bias using the loaded bias map."""
    etf = str(sector_etf).strip().upper()
    if not etf or etf in ("NAN", "NONE", "UNKNOWN"):
        return ""
    return macro_bias_map.get(etf, "NEUTRAL")


def enrich_discovery_csv(discovery_csv: Path, macro_path: Path, enrichment_path: Path | None = None) -> Dict[str, Any]:
    macro = read_json(macro_path)
    macro["macro_quant_packet"] = build_macro_quant_packet(macro, macro_path)

    # Always read the discovery CSV so bias stamping can run even when no theme delta exists
    with discovery_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        original_fields = reader.fieldnames or []

    output_fields = ordered_fields(original_fields)

    # ── Phase A: Theme enrichment (conditional on enrichment delta) ───────────
    selected_enrichment = find_macro_enrichment_delta(macro_path, str(enrichment_path) if enrichment_path else None)
    matched = 0
    theme_status = "SKIPPED"
    if selected_enrichment is not None:
        enrichment = load_macro_enrichment_delta(selected_enrichment)
        macro = merge_macro_enrichment_delta(macro, enrichment)
        put_gate = macro.get("put_gate") if isinstance(macro.get("put_gate"), dict) else {}
        for row in rows:
            ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
            audit = candidate_macro_enrichment_audit(macro, ticker)
            theme_count = int(audit.get("macro_enrichment_theme_count") or 0)
            if theme_count > 0:
                matched += 1
            row.update({
                "macro_enrichment_theme_count": theme_count,
                "macro_enrichment_theme_ids": json_cell(audit.get("macro_enrichment_theme_ids") or []),
                "macro_enrichment_roles": json_cell(audit.get("macro_enrichment_roles") or []),
                "macro_enrichment_event_guards": json_cell(audit.get("macro_enrichment_event_guards") or []),
                "macro_enrichment_confirmation_required": json_cell(audit.get("macro_enrichment_confirmation_required") or []),
                "macro_enrichment_conflict_flags": json_cell(audit.get("macro_enrichment_conflict_flags") or []),
                "macro_enrichment_pressure_label": str(audit.get("macro_enrichment_pressure_label") or ""),
                "macro_enrichment_options_bonus_hint": bonus_hint_from_audit(macro, audit),
                "macro_enrichment_gate_preserved": as_bool_text(audit.get("macro_enrichment_gate_preserved", True)),
                "macro_enrichment_macro_filter": str(macro.get("macro_filter") or ""),
                "macro_enrichment_trigger_required": as_bool_text(macro.get("trigger_required")),
                "macro_enrichment_put_gate_permission": str(put_gate.get("current_permission") or ""),
                "macro_enrichment_audit_note": str(audit.get("macro_enrichment_audit_note") or ""),
                "macro_alignment_state": str(audit.get("macro_alignment_state") or ""),
                "macro_applicability": str(audit.get("macro_applicability") or ""),
                "macro_direction_authority": str(audit.get("macro_direction_authority") or ""),
                "macro_direction_vote": str(audit.get("macro_direction_vote") or ""),
                "macro_raw_direction_hint": str(audit.get("macro_raw_direction_hint") or ""),
                "macro_can_invert_direction": as_bool_text(audit.get("macro_can_invert_direction")),
                "structure_first_required": as_bool_text(audit.get("structure_first_required")),
                "trade_type_classification": str(audit.get("trade_type_classification") or ""),
                "macro_interpretation_reason": str(audit.get("macro_interpretation_reason") or ""),
            })
        theme_status = "PASS"

    # ── Phase B: Bias map stamping (always runs) ──────────────────────────────
    call_tickers, put_tickers, context_tickers = _extract_bias_maps(macro)
    macro_bias_map = _load_macro_bias_map_from_macro_json(macro)
    bias_counts: Dict[str, int] = {"CALL_TAILWIND": 0, "PUT_HEADWIND": 0, "CONTEXT_ONLY": 0, "NEUTRAL": 0, "ABSTAIN": 0}
    for row in rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()

        # Priority 0: sector_etf in discovery row (from enriched universe via Step 3)
        _disc_etf     = str(row.get("sector_etf") or "").strip().upper()
        _disc_abstain = str(row.get("macro_abstain") or "False").upper() == "TRUE"
        if _disc_etf and _disc_etf not in ("NAN", "NONE", "UNKNOWN"):
            bias        = _bias_from_sector_etf(_disc_etf, macro_bias_map) or "NEUTRAL"
            abstain     = "true" if _disc_abstain else "false"
            source      = "UNIVERSE_SECTOR_ETF"
        else:
            # Priority 1: ticker-level bias map from macro JSON
            bias, abstain, source = _resolve_macro_bias(ticker, call_tickers, put_tickers, context_tickers)

        # Augment only — do not overwrite columns already populated
        if not row.get("macro_bias"):
            row["macro_bias"] = bias
        if not row.get("macro_abstain"):
            row["macro_abstain"] = abstain
        if not row.get("macro_bias_source"):
            row["macro_bias_source"] = source
        bias_counts[bias] = bias_counts.get(bias, 0) + 1
        if abstain == "true":
            bias_counts["ABSTAIN"] += 1

    # ── Write combined result ─────────────────────────────────────────────────
    with discovery_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return {
        "status": "PASS" if theme_status == "PASS" else "BIAS_ONLY",
        "discovery_csv": str(discovery_csv),
        "macro_path": str(macro_path),
        "enrichment_path": str(selected_enrichment) if selected_enrichment else None,
        "rows": len(rows),
        "matched_rows": matched,
        "bias_call_tailwind": bias_counts["CALL_TAILWIND"],
        "bias_put_headwind": bias_counts["PUT_HEADWIND"],
        "bias_context_only": bias_counts["CONTEXT_ONLY"],
        "bias_neutral": bias_counts["NEUTRAL"],
        "bias_abstain": bias_counts["ABSTAIN"],
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery-csv", required=True)
    parser.add_argument("--macro-path", required=True)
    parser.add_argument("--enrichment-path", default="")
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()

    discovery_csv = Path(args.discovery_csv)
    macro_path = Path(args.macro_path)
    enrichment_path = Path(args.enrichment_path) if args.enrichment_path else None

    result = enrich_discovery_csv(discovery_csv, macro_path, enrichment_path)
    if args.report_path:
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, sort_keys=True)

    status = result.get("status")
    if status == "PASS":
        print(
            f"[OK] Macro enrichment stamped onto discovery: "
            f"{result.get('matched_rows')}/{result.get('rows')} theme-matched | "
            f"bias: CALL={result.get('bias_call_tailwind')} PUT={result.get('bias_put_headwind')} "
            f"ABSTAIN={result.get('bias_abstain')}"
        )
    elif status == "BIAS_ONLY":
        print(
            f"[OK] Macro bias stamped (no enrichment delta): "
            f"CALL={result.get('bias_call_tailwind')} PUT={result.get('bias_put_headwind')} "
            f"ABSTAIN={result.get('bias_abstain')} rows={result.get('rows')}"
        )
    else:
        print(f"[SKIP] Macro enrichment discovery stamp: {result.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
