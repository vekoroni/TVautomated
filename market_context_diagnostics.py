#!/usr/bin/env python3
"""
Read-only market context diagnostics for AVSHUNTER.

P10: market breadth context for the current candidate slate.
P11: intraday regime watchdog message for LATEST-mode runs.

These diagnostics are intentionally advisory only. They do not mutate pipeline
artifacts, filter candidates, rank candidates, change sizing, or set capital
permission.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


MISSING_TOKENS = {"", "nan", "none", "null", "na", "n/a", "<na>"}

SECTOR_ETF_TO_NAME = {
    "XLB": "Materials",
    "XLC": "Communication Services",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Information Technology",
    "XLP": "Consumer Staples",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
}

SECTOR_NAME_ALIASES = {
    "TECHNOLOGY": "Information Technology",
    "INFORMATION TECHNOLOGY": "Information Technology",
    "HEALTHCARE": "Health Care",
    "HEALTH CARE": "Health Care",
    "COMMUNICATIONS": "Communication Services",
    "COMMUNICATION SERVICES": "Communication Services",
    "CONSUMER CYCLICAL": "Consumer Discretionary",
    "CONSUMER DISCRETIONARY": "Consumer Discretionary",
    "CONSUMER DEFENSIVE": "Consumer Staples",
    "CONSUMER STAPLES": "Consumer Staples",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text.lower() not in MISSING_TOKENS


def _first_present(row: Dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if _is_present(value):
            return str(value).strip()
    return default


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if not _is_present(value):
        return default
    try:
        return float(str(value).strip().replace("%", "").replace(",", ""))
    except Exception:
        return default


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError:
            continue
    return []


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def _latest_file(folder: Path, pattern: str) -> Optional[Path]:
    files = [p for p in folder.glob(pattern) if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _run_dir(base_dir: Path, run_id: str) -> Path:
    return base_dir / "data" / "output" / "runs" / run_id


def _diagnostics_dir(base_dir: Path, run_id: str) -> Path:
    return _run_dir(base_dir, run_id) / "diagnostics"


def _candidate_file(base_dir: Path, run_id: str) -> Tuple[Optional[Path], str]:
    run_dir = _run_dir(base_dir, run_id)
    morning = run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv"
    if morning.exists():
        return morning, "morning_candidates"
    eil = run_dir / "superbrain" / f"eil_enriched_{run_id}.csv"
    if eil.exists():
        return eil, "eil_enriched_fallback"
    superbrain = run_dir / "superbrain" / f"superbrain_enriched_{run_id}.csv"
    if superbrain.exists():
        return superbrain, "superbrain_enriched_fallback"
    return None, "missing"


def _sector_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in SECTOR_ETF_TO_NAME:
        return SECTOR_ETF_TO_NAME[upper]
    normalised = text.replace("_", " ").replace("-", " ").strip()
    alias = SECTOR_NAME_ALIASES.get(normalised.upper())
    if alias:
        return alias
    return " ".join(part.capitalize() for part in normalised.split())


def _candidate_sector(row: Dict[str, Any]) -> str:
    sector = _first_present(
        row,
        (
            "sector",
            "scanner_sector",
            "gics_sector",
            "sector_name",
            "market_sector",
            "sector_etf",
        ),
    )
    return _sector_name(sector)


def _candidate_direction(row: Dict[str, Any]) -> str:
    direction = _first_present(
        row,
        ("primary_direction", "direction", "options_direction", "selected_contract_side"),
        "UNKNOWN",
    )
    return direction.upper()


def _summarise_sector_breadth(sector_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    usable: List[Dict[str, Any]] = []
    for row in sector_rows:
        daily = _to_float(row.get("daily_pct"))
        weekly = _to_float(row.get("weekly_pct"))
        if daily is None and weekly is None:
            continue
        ticker = _first_present(row, ("ticker",), "")
        name = SECTOR_ETF_TO_NAME.get(ticker.upper()) or _sector_name(
            _first_present(row, ("name", "sector"), ticker)
        )
        usable.append(
            {
                "ticker": ticker,
                "name": name,
                "daily_pct": daily,
                "weekly_pct": weekly,
                "monthly_pct": _to_float(row.get("monthly_pct")),
            }
        )

    if not usable:
        return {
            "status": "DATA_UNAVAILABLE",
            "sector_count": 0,
            "positive_daily_pct": None,
            "positive_weekly_pct": None,
            "avg_daily_pct": None,
            "avg_weekly_pct": None,
            "leaders": [],
            "laggards": [],
        }

    daily_values = [r["daily_pct"] for r in usable if r["daily_pct"] is not None]
    weekly_values = [r["weekly_pct"] for r in usable if r["weekly_pct"] is not None]
    positive_daily = sum(1 for value in daily_values if value > 0)
    positive_weekly = sum(1 for value in weekly_values if value > 0)
    daily_participation = positive_daily / len(daily_values) if daily_values else None
    weekly_participation = positive_weekly / len(weekly_values) if weekly_values else None
    avg_daily = sum(daily_values) / len(daily_values) if daily_values else None
    avg_weekly = sum(weekly_values) / len(weekly_values) if weekly_values else None

    ranked_weekly = sorted(
        usable,
        key=lambda r: (
            r["weekly_pct"] if r["weekly_pct"] is not None else -999.0,
            r["daily_pct"] if r["daily_pct"] is not None else -999.0,
        ),
        reverse=True,
    )
    ranked_daily = sorted(
        usable,
        key=lambda r: (
            r["daily_pct"] if r["daily_pct"] is not None else -999.0,
            r["weekly_pct"] if r["weekly_pct"] is not None else -999.0,
        ),
    )

    status = "MIXED"
    if daily_participation is not None and weekly_participation is not None:
        if daily_participation >= 0.60 and weekly_participation >= 0.55 and (avg_daily or 0.0) >= 0:
            status = "SUPPORTIVE"
        elif daily_participation <= 0.35 or (avg_daily is not None and avg_daily <= -0.50):
            status = "DETERIORATING"

    return {
        "status": status,
        "sector_count": len(usable),
        "positive_daily_count": positive_daily,
        "positive_weekly_count": positive_weekly,
        "positive_daily_pct": round(daily_participation * 100, 1) if daily_participation is not None else None,
        "positive_weekly_pct": round(weekly_participation * 100, 1) if weekly_participation is not None else None,
        "avg_daily_pct": round(avg_daily, 3) if avg_daily is not None else None,
        "avg_weekly_pct": round(avg_weekly, 3) if avg_weekly is not None else None,
        "leaders": ranked_weekly[:3],
        "laggards": ranked_daily[:3],
    }


def _summarise_candidate_slate(candidate_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    sectors: Counter[str] = Counter()
    directions: Counter[str] = Counter()
    for row in candidate_rows:
        sector = _candidate_sector(row)
        if sector:
            sectors[sector] += 1
        directions[_candidate_direction(row)] += 1
    return {
        "candidate_count": len(candidate_rows),
        "sector_known_count": sum(sectors.values()),
        "top_sectors": sectors.most_common(8),
        "direction_counts": dict(directions),
    }


def _alignment_note(
    slate: Dict[str, Any],
    breadth: Dict[str, Any],
) -> Tuple[str, List[str]]:
    if not slate.get("candidate_count"):
        return "NO_CANDIDATE_SLATE", ["Candidate slate not available for breadth comparison."]
    if not breadth.get("sector_count"):
        return "BREADTH_DATA_UNAVAILABLE", ["Sector breadth file has no usable percentage fields."]
    if not slate.get("sector_known_count"):
        return "SLATE_SECTOR_DATA_MISSING", ["Candidate slate has no usable sector labels."]

    leader_names = {_sector_name(item.get("name", "")) for item in breadth.get("leaders", [])}
    laggard_names = {_sector_name(item.get("name", "")) for item in breadth.get("laggards", [])}
    slate_top = [name for name, _ in slate.get("top_sectors", [])[:5]]
    aligned = [name for name in slate_top if name in leader_names]
    conflicting = [name for name in slate_top if name in laggard_names]

    notes: List[str] = []
    if aligned:
        notes.append("Slate has exposure to current breadth leaders: " + ", ".join(aligned) + ".")
    if conflicting:
        notes.append("Slate has exposure to current breadth laggards: " + ", ".join(conflicting) + ".")
    if not notes:
        notes.append("No clear sector leadership conflict detected from available data.")

    if conflicting and not aligned:
        return "BREADTH_CONFLICT_REVIEW", notes
    if aligned and not conflicting:
        return "BREADTH_SUPPORTIVE_REVIEW", notes
    return "BREADTH_MIXED_REVIEW", notes


def build_market_breadth_diagnostic(run_id: str, base_dir: Path) -> Dict[str, Any]:
    base_dir = Path(base_dir)
    market_dir = base_dir / "dropbox" / "market_data"
    diagnostics_dir = _diagnostics_dir(base_dir, run_id)
    sectors_path = _latest_file(market_dir, "sectors_*.csv")
    candidate_path, candidate_source = _candidate_file(base_dir, run_id)
    macro_snapshot_path = _run_dir(base_dir, run_id) / "macro_snapshot.json"

    sector_rows = _read_csv(sectors_path) if sectors_path else []
    candidate_rows = _read_csv(candidate_path) if candidate_path else []
    macro = _read_json(macro_snapshot_path)

    breadth = _summarise_sector_breadth(sector_rows)
    slate = _summarise_candidate_slate(candidate_rows)
    alignment_status, alignment_notes = _alignment_note(slate, breadth)

    status = breadth.get("status", "DATA_UNAVAILABLE")
    message = (
        f"MARKET BREADTH: {status} | "
        f"sectors daily positive={breadth.get('positive_daily_pct')}% | "
        f"weekly positive={breadth.get('positive_weekly_pct')}% | "
        f"slate={slate.get('candidate_count', 0)} candidates | "
        f"{alignment_status}. Advisory only; no candidates changed."
    )

    payload: Dict[str, Any] = {
        "diagnostic": "P10_MARKET_BREADTH_READ_ONLY",
        "run_id": run_id,
        "generated_at_utc": _now_utc(),
        "advisory_only": True,
        "mutates_pipeline_outputs": False,
        "source_files": {
            "sectors": str(sectors_path) if sectors_path else None,
            "candidate_slate": str(candidate_path) if candidate_path else None,
            "candidate_source": candidate_source,
            "macro_snapshot": str(macro_snapshot_path) if macro_snapshot_path.exists() else None,
        },
        "macro_context": {
            "regime_state": macro.get("regime_state") or macro.get("regime_label"),
            "risk_on_off_switch": macro.get("risk_on_off_switch") or macro.get("risk_on_switch"),
            "macro_filter": macro.get("macro_filter"),
            "macro_conviction": macro.get("macro_conviction"),
        },
        "breadth": breadth,
        "candidate_slate": slate,
        "alignment_status": alignment_status,
        "alignment_notes": alignment_notes,
        "operator_message": message,
    }

    _write_json(diagnostics_dir / f"market_breadth_diagnostic_{run_id}.json", payload)
    _write_text(diagnostics_dir / f"market_breadth_message_{run_id}.txt", message)
    return payload


def _latest_intraday_rows(base_dir: Path) -> Tuple[Optional[Path], List[Dict[str, str]]]:
    market_dir = base_dir / "dropbox" / "market_data"
    us_indices = _latest_file(market_dir, "us_indices_cash_*.csv")
    if us_indices:
        rows = _read_csv(us_indices)
        usable = [row for row in rows if _to_float(row.get("daily_pct")) is not None]
        if usable:
            return us_indices, rows
    global_indices = _latest_file(market_dir, "global_indices_*.csv")
    if global_indices:
        return global_indices, _read_csv(global_indices)
    return us_indices or global_indices, _read_csv(us_indices or global_indices) if (us_indices or global_indices) else []


def _build_intraday_label(
    data_mode: str,
    index_rows: List[Dict[str, str]],
    vix_row: Dict[str, str],
    macro: Dict[str, Any],
) -> Tuple[str, str, List[str]]:
    if data_mode != "LATEST":
        return (
            "INACTIVE_EOD",
            "Intraday regime watchdog inactive for EOD run. Completed-bar regime only. Advisory only.",
            ["Run was not started with --data-mode LATEST."],
        )

    reasons: List[str] = []
    index_values = [
        _to_float(row.get("daily_pct"))
        for row in index_rows
        if str(row.get("ticker", "")).upper() in {"SPX", "SPY", "NDX", "QQQ", "RUT", "IWM", "DJI", "DIA"}
    ]
    index_values = [value for value in index_values if value is not None]
    avg_index = sum(index_values) / len(index_values) if index_values else None

    vix_momentum = str(vix_row.get("VIX_Momentum") or macro.get("extras", {}).get("vix_momentum") or "").upper()
    fear_phase = str(vix_row.get("Fear_Phase") or macro.get("extras", {}).get("fear_phase") or "").upper()
    vix_structure = str(vix_row.get("VIX_Structure") or macro.get("vix_structure_label") or "").upper()
    macro_regime = str(macro.get("regime_state") or macro.get("regime_label") or "UNKNOWN").upper()

    if avg_index is None:
        reasons.append("Intraday index percentage fields are unavailable; using macro/VIX context only.")
    else:
        reasons.append(f"Average intraday index move from available rows: {avg_index:.2f}%.")
    if vix_momentum:
        reasons.append(f"VIX momentum: {vix_momentum}.")
    if fear_phase:
        reasons.append(f"Fear phase: {fear_phase}.")

    risk_off = (
        (avg_index is not None and avg_index < -0.35)
        or vix_momentum in {"RISING", "HIGH_RISING"}
        or fear_phase in {"EARLY_FEAR_BUILD", "FEAR_BUILD", "STRESS"}
    )
    risk_on = (
        avg_index is not None
        and avg_index > 0.35
        and vix_momentum not in {"RISING", "HIGH_RISING"}
        and "BACKWARD" not in vix_structure
    )

    if risk_off:
        label = f"{macro_regime}_RISK_OFF_PRESSURE"
        message = (
            f"INTRADAY REGIME WATCH: {label}. Tape/vol context is cautionary; "
            "confirm long exposure live and require trigger quality. Advisory only."
        )
    elif risk_on:
        label = f"{macro_regime}_RISK_ON_CONFIRMATION"
        message = (
            f"INTRADAY REGIME WATCH: {label}. Broad tape is supportive from available data; "
            "still no automatic candidate changes. Advisory only."
        )
    else:
        label = f"{macro_regime}_TRANSITIONAL_MONITOR"
        message = (
            f"INTRADAY REGIME WATCH: {label}. No decisive intraday regime shift from available data. "
            "Advisory only."
        )

    return label, message, reasons


def build_intraday_regime_watchdog(run_id: str, base_dir: Path, data_mode: str = "EOD") -> Dict[str, Any]:
    base_dir = Path(base_dir)
    market_dir = base_dir / "dropbox" / "market_data"
    diagnostics_dir = _diagnostics_dir(base_dir, run_id)
    macro_snapshot_path = _run_dir(base_dir, run_id) / "macro_snapshot.json"
    vix_path = market_dir / "avshunter_vix_engine_v2.csv"
    vix_rows = _read_csv(vix_path)
    vix_row = vix_rows[-1] if vix_rows else {}
    index_path, index_rows = _latest_intraday_rows(base_dir)
    macro = _read_json(macro_snapshot_path)

    mode = str(data_mode or "EOD").upper().strip()
    label, message, reasons = _build_intraday_label(mode, index_rows, vix_row, macro)

    payload: Dict[str, Any] = {
        "diagnostic": "P11_INTRADAY_REGIME_WATCHDOG_READ_ONLY",
        "run_id": run_id,
        "generated_at_utc": _now_utc(),
        "data_mode": mode,
        "advisory_only": True,
        "mutates_pipeline_outputs": False,
        "source_files": {
            "index_snapshot": str(index_path) if index_path else None,
            "vix_engine": str(vix_path) if vix_path.exists() else None,
            "macro_snapshot": str(macro_snapshot_path) if macro_snapshot_path.exists() else None,
        },
        "watchdog_label": label,
        "operator_message": message,
        "reasons": reasons,
        "vix_context": {
            "vix_level": vix_row.get("VIX_Level"),
            "vix_momentum": vix_row.get("VIX_Momentum"),
            "vix_structure": vix_row.get("VIX_Structure"),
            "fear_phase": vix_row.get("Fear_Phase"),
            "usd_vix_signal": vix_row.get("USD_VIX_Signal"),
        },
    }

    _write_json(diagnostics_dir / f"intraday_regime_watchdog_{run_id}.json", payload)
    _write_text(diagnostics_dir / f"intraday_regime_watchdog_message_{run_id}.txt", message)
    return payload


def run_read_only_market_context_diagnostics(
    run_id: str,
    base_dir: Path,
    data_mode: str = "EOD",
) -> Dict[str, Any]:
    """Run P10 and P11 advisory diagnostics and write per-run artifacts."""
    base_dir = Path(base_dir)
    diagnostics_dir = _diagnostics_dir(base_dir, run_id)
    market_breadth = build_market_breadth_diagnostic(run_id, base_dir)
    intraday_watchdog = build_intraday_regime_watchdog(run_id, base_dir, data_mode=data_mode)

    summary = {
        "diagnostic": "READ_ONLY_MARKET_CONTEXT_DIAGNOSTICS",
        "run_id": run_id,
        "generated_at_utc": _now_utc(),
        "advisory_only": True,
        "mutates_pipeline_outputs": False,
        "market_breadth_status": market_breadth.get("breadth", {}).get("status"),
        "market_breadth_message": market_breadth.get("operator_message"),
        "intraday_watchdog_label": intraday_watchdog.get("watchdog_label"),
        "intraday_watchdog_message": intraday_watchdog.get("operator_message"),
    }
    _write_json(diagnostics_dir / f"read_only_market_context_{run_id}.json", summary)
    return {
        "success": True,
        "market_breadth": market_breadth,
        "intraday_watchdog": intraday_watchdog,
        "summary": summary,
    }


__all__ = [
    "build_market_breadth_diagnostic",
    "build_intraday_regime_watchdog",
    "run_read_only_market_context_diagnostics",
]
