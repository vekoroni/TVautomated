#!/usr/bin/env python3
"""
Attach governed catalyst/macro context without changing Discovery membership.

Discovery is the authority for the macro-agnostic core candidate set. Existing
Discovery survivors may receive additive external-intelligence annotations,
but catalyst or macro-only tickers are written to a separate advisory artifact.
They cannot be appended to the core CSV, create Packages/Vanguard work, or
reactivate a ticker that Discovery dropped.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from contracts.macro_enrichment_delta import (  # noqa: E402
    candidate_macro_enrichment_audit,
    find_macro_enrichment_delta,
    load_macro_enrichment_delta,
    merge_macro_enrichment_delta,
)


EXTERNAL_INTEL_FIELDS = [
    "external_intel_lane",
    "external_intel_force_review",
    "external_intel_source",
    "external_intel_stage_status",
    "external_intel_reason",
    "external_intel_direction_bias",
    "external_intel_catalyst_status",
    "external_intel_catalyst_type",
    "external_intel_catalyst_date",
    "external_intel_source_tier",
    "external_intel_macro_theme_count",
    "external_intel_macro_theme_ids",
    "external_intel_macro_roles",
    "external_intel_macro_pressure_label",
    "external_intel_macro_confirmation_required",
    "external_intel_macro_conflict_flags",
    "external_intel_data_quality",
]

_US_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,4}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_plain_us_ticker(value: str) -> bool:
    symbol = _ticker(value)
    return bool(symbol and _US_TICKER_RE.match(symbol))


def _json_cell(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(list(value) if isinstance(value, set) else value, sort_keys=True, ensure_ascii=True)
    if value is None:
        return ""
    return str(value)


def _safe_float(value: Any) -> float:
    try:
        if value is None or str(value).strip() == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(row) for row in reader]
        fields = list(reader.fieldnames or [])
    return rows, fields


def _write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _ordered_fields(existing: Iterable[str]) -> List[str]:
    fields = list(existing)
    for field in EXTERNAL_INTEL_FIELDS:
        if field not in fields:
            fields.append(field)
    for field in ("ticker", "symbol", "precor_intent", "external_intel_created_utc"):
        if field not in fields:
            fields.append(field)
    return fields


def _direction_from_catalyst(row: Mapping[str, Any]) -> str:
    raw = " ".join(
        str(row.get(key) or "")
        for key in ("catalyst_direction_bias", "trade_bias", "tradability_route", "expected_impact")
    ).upper()
    if any(token in raw for token in ("PUT", "BEAR", "SHORT", "NEGATIVE", "LOSER", "VULNERABLE")):
        return "PUT"
    if any(token in raw for token in ("CALL", "BULL", "LONG", "POSITIVE", "BENEFICIARY")):
        return "CALL"
    return ""


def _read_catalyst_calendar(path: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return out

    rows, _ = _read_csv(path)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = _ticker(row.get("ticker") or row.get("symbol"))
        if symbol:
            grouped[symbol].append(row)

    for symbol, items in grouped.items():
        best = sorted(
            items,
            key=lambda r: _safe_float(r.get("catalyst_source_confidence") or r.get("source_confidence")),
            reverse=True,
        )[0]
        out[symbol] = {
            "source": "CATALYST_CALENDAR",
            "direction_bias": _direction_from_catalyst(best),
            "catalyst_status": str(best.get("catalyst_status") or best.get("event_status") or ""),
            "catalyst_type": str(best.get("catalyst_type") or ""),
            "catalyst_date": str(best.get("catalyst_date") or best.get("event_window_start") or ""),
            "source_tier": str(best.get("source_tier") or ""),
            "data_quality": str(best.get("date_quality") or best.get("data_quality") or ""),
            "reason": "Ticker present in governed catalyst calendar",
        }
    return out


def _load_macro_context(macro_path: Path, enrichment_path: Optional[Path] = None) -> Tuple[Dict[str, Any], str]:
    with macro_path.open("r", encoding="utf-8") as fh:
        macro = json.load(fh)
    selected = find_macro_enrichment_delta(macro_path, enrichment_path)
    if selected is None:
        return macro, ""
    enrichment = load_macro_enrichment_delta(selected)
    merged = merge_macro_enrichment_delta(macro, enrichment)
    return merged, str(selected)


def _macro_external_info(macro: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    extras = macro.get("extras") if isinstance(macro, Mapping) else {}
    index = extras.get("macro_exposure_index") if isinstance(extras, Mapping) else {}
    if not isinstance(index, Mapping):
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for symbol in sorted(index.keys()):
        ticker = _ticker(symbol)
        if not ticker:
            continue
        audit = candidate_macro_enrichment_audit(macro, ticker)
        out[ticker] = {
            "source": "MACRO_ENRICHMENT",
            "direction_bias": "",
            "macro_theme_count": str(audit.get("macro_enrichment_theme_count") or 0),
            "macro_theme_ids": _json_cell(audit.get("macro_enrichment_theme_ids") or []),
            "macro_roles": _json_cell(audit.get("macro_enrichment_roles") or []),
            "macro_pressure_label": str(audit.get("macro_enrichment_pressure_label") or ""),
            "macro_confirmation_required": _json_cell(audit.get("macro_enrichment_confirmation_required") or []),
            "macro_conflict_flags": _json_cell(audit.get("macro_enrichment_conflict_flags") or []),
            "reason": "Ticker present in macro enrichment exposure index",
        }
    return out


def _merge_info(catalyst: Dict[str, Dict[str, Any]], macro: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for symbol in sorted(set(catalyst) | set(macro)):
        c = catalyst.get(symbol, {})
        m = macro.get(symbol, {})
        sources = []
        if c:
            sources.append("CATALYST")
        if m:
            sources.append("MACRO_ENRICHMENT")
        merged[symbol] = {
            **m,
            **c,
            "source": "+".join(sources),
            "reason": "; ".join(part for part in [c.get("reason"), m.get("reason")] if part),
            "macro_theme_count": m.get("macro_theme_count", ""),
            "macro_theme_ids": m.get("macro_theme_ids", ""),
            "macro_roles": m.get("macro_roles", ""),
            "macro_pressure_label": m.get("macro_pressure_label", ""),
            "macro_confirmation_required": m.get("macro_confirmation_required", ""),
            "macro_conflict_flags": m.get("macro_conflict_flags", ""),
        }
    return merged


def apply_external_intel_review_lane(
    discovery_csv: Path,
    macro_path: Path,
    catalyst_calendar: Optional[Path] = None,
    enrichment_path: Optional[Path] = None,
    review_output: Optional[Path] = None,
) -> Dict[str, Any]:
    rows, original_fields = _read_csv(discovery_csv)
    output_fields = _ordered_fields(original_fields)

    catalyst_path = catalyst_calendar or (REPO / "dropbox" / "inputs" / "catalyst_calendar_latest.csv")
    catalyst_info = _read_catalyst_calendar(catalyst_path)
    macro_context, selected_enrichment = _load_macro_context(macro_path, enrichment_path)
    macro_info = _macro_external_info(macro_context)
    external = _merge_info(catalyst_info, macro_info)

    invalid_tickers = sorted(symbol for symbol in external if not _is_plain_us_ticker(symbol))
    valid_external = {symbol: info for symbol, info in external.items() if _is_plain_us_ticker(symbol)}

    existing = {_ticker(row.get("ticker") or row.get("symbol")) for row in rows}
    matched_existing = 0
    advisory_rows: List[Dict[str, Any]] = []
    for row in rows:
        symbol = _ticker(row.get("ticker") or row.get("symbol"))
        info = valid_external.get(symbol)
        if not info:
            continue
        matched_existing += 1
        _stamp_row(row, info, appended=False)
        advisory_rows.append(dict(row))

    advisory_only = 0
    for symbol, info in sorted(valid_external.items()):
        if symbol in existing:
            continue
        row = {field: "" for field in output_fields}
        row["ticker"] = symbol
        if "symbol" in output_fields:
            row["symbol"] = symbol
        row["precor_intent"] = "WAIT"
        row["external_intel_created_utc"] = _utc_now()
        _stamp_row(row, info, appended=True)
        advisory_rows.append(row)
        advisory_only += 1

    if review_output is not None:
        review_path = review_output
    elif "discovery_candidates_ultimate_" in discovery_csv.name:
        review_path = discovery_csv.with_name(
            discovery_csv.name.replace(
                "discovery_candidates_ultimate_", "external_intel_review_candidates_"
            )
        )
    else:
        review_path = discovery_csv.with_name(
            f"{discovery_csv.stem}_external_intel_review.csv"
        )
    _write_csv(discovery_csv, rows, output_fields)
    _write_csv(review_path, advisory_rows, output_fields)
    return {
        "status": "PASS",
        "discovery_csv": str(discovery_csv),
        "macro_path": str(macro_path),
        "macro_enrichment_path": selected_enrichment,
        "catalyst_calendar": str(catalyst_path),
        "input_rows": len(rows),
        "output_rows": len(rows),
        "external_tickers": len(external),
        "valid_external_tickers": len(valid_external),
        "invalid_external_tickers": invalid_tickers,
        "matched_existing_rows": matched_existing,
        "appended_forced_review_rows": 0,
        "advisory_review_rows": len(advisory_rows),
        "advisory_only_rows": advisory_only,
        "review_output": str(review_path),
        "core_membership_changed": False,
        "generated_utc": _utc_now(),
    }


def _stamp_row(row: Dict[str, Any], info: Mapping[str, Any], appended: bool) -> None:
    row["external_intel_lane"] = "TRUE"
    row["external_intel_force_review"] = "TRUE"
    row["external_intel_source"] = str(info.get("source") or "")
    row["external_intel_stage_status"] = (
        "ADVISORY_ONLY_NOT_DISCOVERY" if appended else "ALREADY_IN_DISCOVERY"
    )
    row["external_intel_reason"] = str(info.get("reason") or "")
    row["external_intel_direction_bias"] = str(info.get("direction_bias") or "")
    row["external_intel_catalyst_status"] = str(info.get("catalyst_status") or "")
    row["external_intel_catalyst_type"] = str(info.get("catalyst_type") or "")
    row["external_intel_catalyst_date"] = str(info.get("catalyst_date") or "")
    row["external_intel_source_tier"] = str(info.get("source_tier") or "")
    row["external_intel_macro_theme_count"] = str(info.get("macro_theme_count") or "")
    row["external_intel_macro_theme_ids"] = str(info.get("macro_theme_ids") or "")
    row["external_intel_macro_roles"] = str(info.get("macro_roles") or "")
    row["external_intel_macro_pressure_label"] = str(info.get("macro_pressure_label") or "")
    row["external_intel_macro_confirmation_required"] = str(info.get("macro_confirmation_required") or "")
    row["external_intel_macro_conflict_flags"] = str(info.get("macro_conflict_flags") or "")
    row["external_intel_data_quality"] = str(info.get("data_quality") or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery-csv", required=True)
    parser.add_argument("--macro-path", required=True)
    parser.add_argument("--catalyst-calendar", default="")
    parser.add_argument("--enrichment-path", default="")
    parser.add_argument("--review-output", default="")
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()

    result = apply_external_intel_review_lane(
        discovery_csv=Path(args.discovery_csv),
        macro_path=Path(args.macro_path),
        catalyst_calendar=Path(args.catalyst_calendar) if args.catalyst_calendar else None,
        enrichment_path=Path(args.enrichment_path) if args.enrichment_path else None,
        review_output=Path(args.review_output) if args.review_output else None,
    )
    if args.report_path:
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(
        "[OK] External intel review lane: "
        f"{result['matched_existing_rows']} existing stamped, "
        f"{result['advisory_only_rows']} advisory-only, "
        f"{len(result['invalid_external_tickers'])} invalid skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
