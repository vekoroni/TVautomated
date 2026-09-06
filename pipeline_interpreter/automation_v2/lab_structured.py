"""Structured Intelligence Lab adapter for the automated ticker workflow."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .veto import evaluate_sovereign_veto


SECTION_FIELDS = {
    "overview": (
        "lab_rank", "lab_verdict", "lab_tradeable", "lab_status",
        "lab_execution_status", "execution_category", "display_execution_mode",
        "position_size_display", "direction", "instrument", "macro_regime",
        "priority_score", "eil_composite_eod",
    ),
    "trade_setup": (
        "strike", "expiry", "dte", "premium_mid", "entry_plan",
        "invalidation_price", "target_price", "structural_target",
        "underlying_price", "breakeven_price", "breakeven_pct",
        "rr_predicted", "ev_predicted", "hold_window", "time_horizon",
        "hold_period", "trigger_price", "trigger_primary", "trigger_quality",
        "trigger_score", "trigger_codes",
    ),
    "options": (
        "contract_symbol", "contract_delta", "contract_gamma",
        "contract_theta", "contract_iv", "contract_bid", "contract_ask",
        "contract_mid", "contract_oi", "contract_volume", "call_wall",
        "put_wall", "gamma_flip", "max_pain", "pcr_signal",
        "gamma_island_on_path", "gamma_island_level",
        "gamma_island_distance_pct",
    ),
    "convexity": (
        "wbs", "wbs_grade", "wbs_wall_price", "wbs_wall_dist_pct",
        "wbs_f5_momentum", "wbs_phase_b_trigger", "wbs_phase_c_trigger",
        "wbs_entry_guidance", "wbs_size_guidance", "wbs_wall_stall_rule",
        "wbs_notes", "option_gain_at_target", "runway_to_target",
        "runway_to_wall_pct", "target_in_play",
    ),
    "qomega": (
        "expected_move_5d", "expected_move_10d", "expected_move_20d",
        "ivp_30d", "ivp_252d", "hv_30d", "iv_vs_hv", "term_structure",
        "vol_of_vol", "iv_accel_detected", "risk_reversal",
    ),
}


@dataclass(frozen=True, slots=True)
class LabStructuredResult:
    manifest: Path
    ticker: str
    run_id: str
    findings: tuple[str, ...]


def _read_ticker_row(path: Path, ticker: str) -> dict[str, str] | None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("ticker") or row.get("Ticker") or "").strip().upper() == ticker:
                return dict(row)
    return None


def _run_suffix(path: Path, prefix: str) -> str:
    return path.stem.removeprefix(prefix)


def discover_lab_sources(
    root: Path, ticker: str
) -> tuple[Path, Path | None, dict[str, str], dict[str, str]]:
    """Find the newest Lab run containing the exact ticker."""
    symbol = ticker.strip().upper()
    lab_export = root.parent / "lab_export"
    signal_candidates = (
        list(lab_export.glob("avshunter_signals_*.csv"))
        if lab_export.exists() else []
    )
    signal_candidates.extend(root.glob("avshunter_signals_*.csv"))
    candidates = sorted(
        signal_candidates or list(root.glob("lab_triage_view_*.csv")),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for triage_path in candidates:
        triage_row = _read_ticker_row(triage_path, symbol)
        if triage_row is None:
            continue
        suffix = _run_suffix(triage_path, "lab_triage_view_")
        enriched_path = root / f"eil_enriched_{suffix}.csv"
        enriched_row = (
            _read_ticker_row(enriched_path, symbol)
            if enriched_path.is_file()
            else {}
        ) or {}
        return (
            triage_path,
            enriched_path if enriched_path.is_file() else None,
            triage_row,
            enriched_row,
        )
    raise LookupError(f"LAB_TICKER_NOT_FOUND:{symbol}")


def _present_fields(
    row: Mapping[str, Any], names: Iterable[str]
) -> dict[str, Any]:
    return {
        name: row[name]
        for name in names
        if row.get(name) not in (None, "")
    }


def _normalise_row(row: Mapping[str, Any]) -> dict[str, Any]:
    normalised = {str(key).strip().lower(): value for key, value in row.items()}
    aliases = {
        "ticker": "Ticker", "run_id": "Run_ID", "lab_rank": "Priority_Rank",
        "lab_verdict": "Verdict", "rr_predicted": "RR", "ev_predicted": "EV",
        "direction": "Direction", "instrument": "Instrument", "strike": "Strike",
        "expiry": "Expiry", "dte": "DTE", "priority_score": "Priority_Score",
        "trigger_price": "Trigger_Price", "trigger_primary": "Trigger_Primary",
        "trigger_quality": "Trigger_Quality", "trigger_score": "Trigger_Score",
        "trigger_codes": "Trigger_Codes", "premium_mid": "Premium_Mid",
    }
    for target, source in aliases.items():
        if normalised.get(target) in (None, "") and row.get(source) not in (None, ""):
            normalised[target] = row[source]
    return normalised


def build_structured_lab_manifest(
    *,
    ticker: str,
    pipeline_outputs: Path,
    output_file: Path,
) -> LabStructuredResult:
    symbol = ticker.strip().upper()
    triage_path, enriched_path, triage, enriched = discover_lab_sources(
        pipeline_outputs.resolve(), symbol
    )
    # Enriched EIL supplies missing detail; Lab triage remains authoritative.
    merged = {**_normalise_row(enriched), **_normalise_row(triage)}
    run_id = str(triage.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("LAB_RUN_ID_MISSING")

    rr = (
        triage.get("rr_predicted")
        or enriched.get("rr_options")
        or enriched.get("rr_premium_expected")
        or ""
    )
    sovereign = evaluate_sovereign_veto(
        pipeline_row={**merged, "rr": rr},
        live_validation=None,
    )
    sections = {
        section: _present_fields(merged, fields)
        for section, fields in SECTION_FIELDS.items()
    }
    findings = [
        f"SECTION_EMPTY:{section}"
        for section, values in sections.items()
        if not values
    ]
    payload = {
        "schema_version": "automation_v2.lab_structured.1",
        "ticker": symbol,
        "run_id": run_id,
        "status": "staged",
        "source_precedence": [
            "lab_triage_view",
            "eil_enriched_fill_only",
        ],
        "sources": {
            "lab_triage_view": str(triage_path),
            "eil_enriched": str(enriched_path) if enriched_path else None,
        },
        "sections": sections,
        "sovereign": {
            "rr": rr,
            "veto_codes": list(sovereign.veto_codes),
            "effective_verdict": sovereign.effective_verdict,
            "eil_action": sovereign.eil_action,
            "execution_permission": sovereign.execution_permission,
            "capital_permission": sovereign.capital_permission,
        },
        "findings": findings,
        "published": False,
    }
    target = output_file.resolve()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return LabStructuredResult(
        manifest=target,
        ticker=symbol,
        run_id=run_id,
        findings=tuple(findings),
    )

