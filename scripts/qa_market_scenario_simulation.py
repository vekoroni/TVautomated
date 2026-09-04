#!/usr/bin/env python
"""Stress-test a completed AVSHUNTER run with simulated live market scenarios.

The test has two jobs:
1. Audit the output artifacts that should exist after a full orchestrator run.
2. Replay morning validation against synthetic live data scenarios built from the
   real morning candidate artifact, without mutating production run output.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "output" / "runs"
QA_DIR = ROOT / "data" / "output" / "qa"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from morning_thesis_validator import build_summary, run_morning_validation  # type: ignore[import-not-found]  # noqa: E402
    _LEGACY_MORNING_VALIDATOR_AVAILABLE = True
except ModuleNotFoundError:
    build_summary = None
    run_morning_validation = None
    _LEGACY_MORNING_VALIDATOR_AVAILABLE = False


SCENARIOS = [
    "clean_breakout_go",
    "spread_caution_armed",
    "wide_spread_block",
    "stale_quote_wait",
    "missing_contract_quote_block",
    "invalidation_break_block",
    "chase_risk_armed",
    "retest_wait",
    "direction_reversal_block",
]

EXPECTED = {
    "clean_breakout_go": {"GO"},
    "spread_caution_armed": {"ARMED"},
    "wide_spread_block": {"BLOCKED"},
    "stale_quote_wait": {"WAIT"},
    "missing_contract_quote_block": {"BLOCKED"},
    "invalidation_break_block": {"BLOCKED"},
    "chase_risk_armed": {"ARMED", "WAIT"},
    "retest_wait": {"WAIT", "ARMED"},
    "direction_reversal_block": {"BLOCKED", "WAIT"},
}

CSV_ARTIFACTS = [
    ("Discovery", "discovery/discovery_candidates_ultimate_{run_id}.csv", ["ticker"], 1),
    ("Vanguard raw", "vanguard/vanguard_signals.csv", ["ticker"], 1),
    ("Vanguard enriched", "options/vanguard_signals_enriched_{run_id}.csv", ["ticker"], 1),
    ("Options intelligence", "options/options_intelligence_{run_id}.csv", ["ticker"], 1),
    ("Horizon 1-5D", "horizon/horizon_1_5d_{run_id}.csv", ["ticker"], 0),
    ("Horizon 6-10D", "horizon/horizon_6_10d_{run_id}.csv", ["ticker"], 0),
    ("Horizon 11-20D", "horizon/horizon_11_20d_{run_id}.csv", ["ticker"], 0),
    ("Horizon blocked", "horizon/horizon_blocked_{run_id}.csv", ["ticker"], 0),
    ("Superbrain", "superbrain/superbrain_enriched_{run_id}.csv", ["ticker"], 1),
    ("EIL enriched", "superbrain/eil_enriched_{run_id}.csv", ["ticker"], 1),
    ("Execution", "execution/execution_v3_5_{run_id}.csv", ["ticker"], 1),
    ("GARCH", "qomega/garch_forecasts_{run_id}.csv", ["ticker"], 1),
    ("Catalyst truth", "catalysts/catalyst_truth_{run_id}.csv", ["ticker", "catalyst_truth_score", "catalyst_trade_class", "event_convexity_score"], 1),
    ("Morning candidates", "morning_validation/morning_candidates_{run_id}.csv", ["ticker"], 1),
    ("Morning validated", "morning_validation/morning_validated_trades_{run_id}.csv", ["ticker"], 1),
    ("Final opportunity book", "intelligence_lab/final_opportunity_book_{run_id}.csv", ["ticker"], 0),
]

JSON_ARTIFACTS = [
    ("Run meta", "run_meta.json"),
    ("Truth packet", "truth_packet_run.json"),
    ("Final run manifest", "final_run_manifest.json"),
    ("Pipeline integrity", "pipeline_integrity_{run_id}.json"),
    ("Horizon summary", "horizon/horizon_summary_{run_id}.json"),
    ("Options summary", "options/options_intelligence_summary_{run_id}.json"),
    ("Vanguard summary", "vanguard/vanguard_run_summary.json"),
    ("Catalyst summary", "catalysts/catalyst_truth_summary_{run_id}.json"),
    ("Morning packet", "morning_validation/morning_validation_packet_{run_id}.json"),
]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _latest_run_id() -> str:
    latest = RUNS_DIR.parent / "latest.json"
    if latest.exists():
        try:
            payload = json.loads(latest.read_text(encoding="utf-8-sig"))
            rid = payload.get("run_id") or payload.get("latest_run_id")
            if rid:
                return str(rid)
        except Exception:
            pass
    runs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
    if not runs:
        raise FileNotFoundError(f"No run folders found under {RUNS_DIR}")
    return runs[-1]


def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, Any]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, rows: List[Dict[str, Any]], fields: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")


def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    try:
        out = float(text)
    except Exception:
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _truthy(value: Any) -> bool:
    return _upper(value) in {"TRUE", "T", "YES", "Y", "1", "1.0"}


def _falsey(value: Any) -> bool:
    return _upper(value) in {"FALSE", "F", "NO", "N", "0", "0.0"}


def _fmt(template: str, run_id: str) -> str:
    return template.format(run_id=run_id)


def _positive_first(row: Dict[str, Any], keys: Iterable[str], default: float = 50.0) -> float:
    for key in keys:
        value = _float(row.get(key), None)
        if value is not None and value > 0:
            return value
    return default


def _artifact_audit(run_id: str, run_dir: Path) -> Dict[str, Any]:
    stages: List[Dict[str, Any]] = []
    rows_by_name: Dict[str, int] = {}
    columns_by_name: Dict[str, List[str]] = {}
    defects: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for name, rel_template, required_cols, min_rows in CSV_ARTIFACTS:
        rel = _fmt(rel_template, run_id)
        path = run_dir / rel
        columns, rows = _read_csv(path)
        missing_cols = [col for col in required_cols if col not in columns]
        row_count = len(rows)
        status = "PASS"
        if not path.exists() or missing_cols or row_count < min_rows:
            status = "FAIL"
            defects.append(
                {
                    "stage": name,
                    "issue": "missing_or_invalid_csv",
                    "path": str(path),
                    "rows": row_count,
                    "missing_columns": missing_cols,
                }
            )
        stages.append(
            {
                "stage": name,
                "kind": "csv",
                "status": status,
                "path": str(path),
                "rows": row_count,
                "columns": len(columns),
                "missing_columns": missing_cols,
            }
        )
        rows_by_name[name] = row_count
        columns_by_name[name] = columns

    for name, rel_template in JSON_ARTIFACTS:
        rel = _fmt(rel_template, run_id)
        path = run_dir / rel
        status = "PASS"
        payload_keys: List[str] = []
        if not path.exists():
            status = "FAIL"
            defects.append({"stage": name, "issue": "missing_json", "path": str(path)})
        else:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(payload, dict):
                    payload_keys = sorted(str(k) for k in payload.keys())
            except Exception as exc:
                status = "FAIL"
                defects.append({"stage": name, "issue": "invalid_json", "path": str(path), "error": str(exc)})
        stages.append(
            {
                "stage": name,
                "kind": "json",
                "status": status,
                "path": str(path),
                "top_level_keys": payload_keys[:20],
            }
        )

    package_dir = run_dir / "packages"
    package_count = len(list(package_dir.glob("*.package.json"))) if package_dir.exists() else 0
    stages.append(
        {
            "stage": "Packages",
            "kind": "dir",
            "status": "PASS" if package_count else "FAIL",
            "path": str(package_dir),
            "files": package_count,
        }
    )
    if package_count == 0:
        defects.append({"stage": "Packages", "issue": "missing_packages", "path": str(package_dir)})

    archive_dir = ROOT / "data" / "archive" / run_id
    archive_count = len(list(archive_dir.rglob("*"))) if archive_dir.exists() else 0
    stages.append(
        {
            "stage": "Archive",
            "kind": "dir",
            "status": "PASS" if archive_count else "WARN",
            "path": str(archive_dir),
            "files": archive_count,
        }
    )
    if archive_count == 0:
        warnings.append({"stage": "Archive", "issue": "archive_not_found_or_empty", "path": str(archive_dir)})

    # Cross-stage row consistency checks.
    expected_equal = [
        ("Options intelligence", "EIL enriched"),
        ("EIL enriched", "Execution"),
        ("EIL enriched", "GARCH"),
    ]
    for left, right in expected_equal:
        if rows_by_name.get(left) != rows_by_name.get(right):
            defects.append(
                {
                    "stage": "Cross-stage row parity",
                    "issue": "row_count_mismatch",
                    "left": left,
                    "left_rows": rows_by_name.get(left),
                    "right": right,
                    "right_rows": rows_by_name.get(right),
                }
            )

    if rows_by_name.get("Vanguard enriched", 0) > package_count:
        warnings.append(
            {
                "stage": "Vanguard/package coverage",
                "issue": "more_vanguard_rows_than_packages",
                "vanguard_rows": rows_by_name.get("Vanguard enriched", 0),
                "package_count": package_count,
            }
        )

    morning_path = run_dir / f"morning_validation/morning_candidates_{run_id}.csv"
    morning_cols, morning_rows = _read_csv(morning_path)
    if morning_rows:
        direction_keys = ["direction", "evening_direction", "option_direction", "options_direction", "signal_type", "instrument"]
        direction_present = 0
        mapped_transition = 0
        tier_counts = Counter()
        for row in morning_rows:
            if any(_upper(row.get(key)) in {"CALL", "PUT", "C", "P", "BULLISH", "BEARISH"} for key in direction_keys):
                direction_present += 1
            label = _upper(row.get("state_transition_label") or row.get("evening_state_transition_label") or row.get("hidden_state_label"))
            if any(
                token in label
                for token in [
                    "BALANCE_TO_",
                    "CONTINUATION_",
                    "HIGH_ENTROPY_CHOP",
                    "CHOP_CONTINUATION",
                    "NO_TRANSITION_EDGE",
                    "LOW_ENERGY_NO_EDGE",
                    "COMPRESSED_BALANCED",
                ]
            ):
                mapped_transition += 1
            tier_counts[_upper(row.get("structural_tier") or row.get("tier") or row.get("tier_label") or "UNKNOWN")] += 1
        direction_rate = direction_present / len(morning_rows) * 100.0
        transition_rate = mapped_transition / len(morning_rows) * 100.0
        if direction_rate < 95:
            defects.append(
                {
                    "stage": "Morning candidates",
                    "issue": "executable_side_not_preserved",
                    "detail": "Morning candidates should carry CALL/PUT side for live validation.",
                    "coverage_pct": round(direction_rate, 2),
                    "rows_with_side": direction_present,
                    "rows": len(morning_rows),
                }
            )
        if transition_rate < 50:
            warnings.append(
                {
                    "stage": "Morning candidates",
                    "issue": "low_mapped_transition_coverage",
                    "detail": "Live physics confirmation needs mapped transition labels.",
                    "coverage_pct": round(transition_rate, 2),
                    "rows_with_mapped_transition": mapped_transition,
                    "rows": len(morning_rows),
                }
            )
        if tier_counts and (tier_counts.get("A", 0) + tier_counts.get("B", 0)) == 0:
            warnings.append(
                {
                    "stage": "Morning candidates",
                    "issue": "no_tier_a_or_b_candidates",
                    "detail": "This output is validation-prep only; capital allocation should wait for live UAT promotion.",
                    "tier_counts": dict(tier_counts),
                }
            )

    packet_path = run_dir / f"morning_validation/morning_validation_packet_{run_id}.json"
    if packet_path.exists():
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8-sig"))
            summary = packet.get("summary", {})
            if summary.get("paper_mode") is True:
                warnings.append(
                    {
                        "stage": "Morning validation",
                        "issue": "paper_mode_validation",
                        "detail": "Paper/sim validation cannot authorize capital allocation.",
                    }
                )
            if int(summary.get("go_count") or 0) == 0:
                warnings.append(
                    {
                        "stage": "Morning validation",
                        "issue": "zero_live_go_signals",
                        "detail": "No GO signals were produced in the saved validation packet.",
                    }
                )
        except Exception:
            pass

    execution_path = run_dir / f"execution/execution_v3_5_{run_id}.csv"
    execution_cols, execution_rows = _read_csv(execution_path)
    if execution_rows:
        buy_now = [row for row in execution_rows if _upper(row.get("execution_verdict")) == "BUY_NOW"]
        capital_leaks = [
            row
            for row in buy_now
            if _float(row.get("pse_final_size"), 0.0) > 0.0
            and _upper(row.get("capital_permission")) not in {"NO", "NO_CAPITAL", "WATCH_ONLY", "EOD_CANDIDATE_ONLY", ""}
            and not _truthy(row.get("execution_authorized"))
        ]
        if capital_leaks:
            defects.append(
                {
                    "stage": "Execution authority",
                    "issue": "buy_now_capital_leak",
                    "detail": "BUY_NOW rows have positive size without explicit execution_authorized=true.",
                    "rows": len(capital_leaks),
                    "sample_tickers": [row.get("ticker") for row in capital_leaks[:10]],
                }
            )

        unauthorized_buy_now = [
            row
            for row in buy_now
            if _upper(row.get("capital_permission")) in {"NO", "NO_CAPITAL", "WATCH_ONLY", ""}
            or (
                _float(row.get("pse_final_size"), 0.0) <= 0.0
                and _upper(row.get("capital_permission")) != "EOD_CANDIDATE_ONLY"
                and not _truthy(row.get("eod_candidate_authorized"))
                and _upper(row.get("sizing_policy")) != "PSE_IGNORED_MANUAL_SIZING"
                and not _truthy(row.get("manual_sizing_required"))
            )
        ]
        if unauthorized_buy_now:
            warnings.append(
                {
                    "stage": "Execution authority",
                    "issue": "buy_now_label_without_capital_authority",
                    "detail": "These are pre-live campaign labels; effective_execution_verdict/capital_permission must govern funding.",
                    "rows": len(unauthorized_buy_now),
                    "eil_blocked_rows": sum(1 for row in unauthorized_buy_now if _upper(row.get("eil_v3_verdict")) == "BLOCKED"),
                    "liquidity_failed_rows": sum(1 for row in unauthorized_buy_now if _falsey(row.get("eil_liquidity_passed"))),
                    "sample_tickers": [row.get("ticker") for row in unauthorized_buy_now[:10]],
                }
            )

        if "effective_execution_verdict" not in execution_cols or "execution_authorized" not in execution_cols:
            warnings.append(
                {
                    "stage": "Execution authority",
                    "issue": "missing_effective_execution_authority_columns",
                    "detail": "Execution output should expose execution_authorized and effective_execution_verdict.",
                }
            )

    horizon_summary_path = run_dir / f"horizon/horizon_summary_{run_id}.json"
    if horizon_summary_path.exists() and execution_rows:
        try:
            horizon_summary = json.loads(horizon_summary_path.read_text(encoding="utf-8-sig"))
            summary_regime = _upper(
                horizon_summary.get("regime_state")
                or horizon_summary.get("macro_regime")
                or horizon_summary.get("regime")
            ).replace(" ", "_")
            csv_regimes = Counter(
                _upper(row.get("horizon_regime_state") or row.get("regime_state") or row.get("macro_regime_label") or row.get("macro_regime")).replace(" ", "_")
                for row in execution_rows
            )
            csv_regimes.pop("", None)
            if summary_regime and csv_regimes and summary_regime not in csv_regimes:
                warnings.append(
                    {
                        "stage": "Macro regime",
                        "issue": "horizon_summary_execution_regime_mismatch",
                        "detail": "Sizing must consume the authoritative horizon regime instead of falling back to a generic label.",
                        "summary_regime": summary_regime,
                        "execution_regimes": dict(csv_regimes.most_common(5)),
                    }
                )
        except Exception as exc:
            warnings.append({"stage": "Macro regime", "issue": "horizon_summary_parse_failed", "error": str(exc)})

    eil_cols = columns_by_name.get("EIL enriched", [])
    if "l3_jump_risk_flag" in eil_cols and "l3_jump_risk_flag" not in execution_cols:
        warnings.append(
            {
                "stage": "GARCH execution propagation",
                "issue": "jump_risk_missing_from_execution",
                "detail": "l3_jump_risk_flag is visible to EIL but absent from execution output.",
            }
        )

    catalyst_path = run_dir / f"catalysts/catalyst_truth_{run_id}.csv"
    catalyst_cols, catalyst_rows = _read_csv(catalyst_path)
    if catalyst_rows:
        detected_rows = [row for row in catalyst_rows if _truthy(row.get("catalyst_detected"))]
        dated_rows = [row for row in catalyst_rows if str(row.get("catalyst_date", "")).strip()]
        inside_rows = [row for row in catalyst_rows if _truthy(row.get("catalyst_inside_dte"))]
        event_convexity_rows = [
            row for row in catalyst_rows
            if (_float(row.get("event_convexity_score"), 0.0) or 0.0) >= 65.0
        ]
        if not detected_rows:
            warnings.append(
                {
                    "stage": "Catalyst truth",
                    "issue": "zero_detected_catalysts",
                    "detail": "The catalyst lens ran, but found no catalyst evidence. This is safe, but not enough for event-convexity capital allocation.",
                    "rows": len(catalyst_rows),
                }
            )
        if detected_rows and not dated_rows:
            warnings.append(
                {
                    "stage": "Catalyst truth",
                    "issue": "detected_without_dated_packets",
                    "detail": "Catalysts are inferred from structure/event fields, but no dated operator catalyst packet is present.",
                    "detected": len(detected_rows),
                }
            )
        if event_convexity_rows and not inside_rows:
            warnings.append(
                {
                    "stage": "Catalyst truth",
                    "issue": "event_convexity_without_dte_confirmation",
                    "detail": "Event-convexity candidates exist, but no catalyst date is confirmed inside contract DTE.",
                    "event_convexity_rows": len(event_convexity_rows),
                }
            )

        missing_from_eil = [
            field for field in ("catalyst_truth_score", "catalyst_trade_class", "event_convexity_score")
            if field not in eil_cols
        ]
        if eil_cols and missing_from_eil:
            warnings.append(
                {
                    "stage": "Catalyst propagation",
                    "issue": "catalyst_fields_missing_from_eil",
                    "detail": "EIL should carry the advisory catalyst fields into candidate creation.",
                    "missing_fields": missing_from_eil,
                }
            )

        manual_path = ROOT / "dropbox" / "inputs" / "manual_ticker_upload_latest.csv"
        if manual_path.exists():
            _, manual_rows = _read_csv(manual_path)
            manual_tickers = {
                _upper(row.get("ticker") or row.get("symbol"))
                for row in manual_rows
                if _upper(row.get("ticker") or row.get("symbol"))
            }
            catalyst_tickers = {_upper(row.get("ticker")) for row in catalyst_rows}
            manual_missing = sorted(ticker for ticker in manual_tickers if ticker not in catalyst_tickers)
            manual_dated = [
                row for row in catalyst_rows
                if _upper(row.get("ticker")) in manual_tickers and str(row.get("catalyst_date", "")).strip()
            ]
            if manual_missing:
                defects.append(
                    {
                        "stage": "Manual ticker catalyst coverage",
                        "issue": "manual_tickers_missing_from_catalyst_layer",
                        "detail": "Manual/new tickers must receive the same catalyst lens as scanner tickers.",
                        "missing": manual_missing,
                    }
                )
            if manual_tickers and not manual_dated:
                warnings.append(
                    {
                        "stage": "Manual ticker catalyst coverage",
                        "issue": "manual_tickers_without_dated_catalysts",
                        "detail": "Manual/new tickers are covered, but still need a dated catalyst packet before event-convexity allocation.",
                        "manual_tickers": sorted(manual_tickers),
                    }
                )

    validated_path = run_dir / f"morning_validation/morning_validated_trades_{run_id}.csv"
    validated_cols, validated_rows = _read_csv(validated_path)
    if validated_rows:
        score_values = {
            str(row.get("validation_score", "")).strip()
            for row in validated_rows
            if str(row.get("validation_score", "")).strip()
        }
        if len(score_values) == 1 and len(validated_rows) > 10:
            warnings.append(
                {
                    "stage": "Morning validation",
                    "issue": "homogeneous_validation_score",
                    "detail": "All validated rows share the same score; confirm this is a deterministic paper-mode score, not a stuck placeholder.",
                    "score": next(iter(score_values)),
                    "rows": len(validated_rows),
                }
            )

        non_paper_missing_greeks = [
            row
            for row in validated_rows
            if _upper(row.get("live_data_mode")) not in {"", "PAPER", "SIM", "SIMULATED"}
            and any(str(row.get(col, "")).strip().lower() in {"", "nan", "none", "null"} for col in ("live_iv", "live_delta", "live_gamma", "live_theta"))
        ]
        if non_paper_missing_greeks:
            defects.append(
                {
                    "stage": "Morning validation",
                    "issue": "live_mode_missing_option_greeks",
                    "detail": "Live validation cannot authorize capital without contract greeks.",
                    "rows": len(non_paper_missing_greeks),
                    "sample_tickers": [row.get("ticker") for row in non_paper_missing_greeks[:10]],
                }
            )

    horizon_1_5_path = run_dir / f"horizon/horizon_1_5d_{run_id}.csv"
    _, horizon_1_5_rows = _read_csv(horizon_1_5_path)
    if horizon_1_5_rows:
        stand_down = [
            row
            for row in horizon_1_5_rows
            if any("STAND_DOWN" in _upper(value) for value in row.values())
        ]
        if stand_down:
            warnings.append(
                {
                    "stage": "Horizon routing",
                    "issue": "stand_down_rows_in_short_horizon",
                    "detail": "Short-horizon STAND_DOWN rows should carry an explicit non-actionable flag.",
                    "rows": len(stand_down),
                    "sample_tickers": [row.get("ticker") for row in stand_down[:10]],
                }
            )

    return {
        "stages": stages,
        "rows_by_stage": rows_by_name,
        "columns_by_stage": {k: len(v) for k, v in columns_by_name.items()},
        "defects": defects,
        "warnings": warnings,
        "package_count": package_count,
        "archive_file_count": archive_count,
    }


def _manual_upload_coverage(run_id: str, run_dir: Path) -> Dict[str, Any]:
    manual_path = ROOT / "dropbox" / "inputs" / "manual_ticker_upload_latest.csv"
    if not manual_path.exists():
        return {"status": "SKIPPED", "reason": "manual upload file not found", "path": str(manual_path)}
    _, manual_rows = _read_csv(manual_path)
    tickers = sorted({_upper(row.get("ticker") or row.get("symbol")) for row in manual_rows if _upper(row.get("ticker") or row.get("symbol"))})
    stages = {
        "discovery": run_dir / f"discovery/discovery_candidates_ultimate_{run_id}.csv",
        "vanguard": run_dir / f"options/vanguard_signals_enriched_{run_id}.csv",
        "options": run_dir / f"options/options_intelligence_{run_id}.csv",
        "catalyst": run_dir / f"catalysts/catalyst_truth_{run_id}.csv",
        "eil": run_dir / f"superbrain/eil_enriched_{run_id}.csv",
        "morning_candidates": run_dir / f"morning_validation/morning_candidates_{run_id}.csv",
    }
    coverage = {}
    for name, path in stages.items():
        _, rows = _read_csv(path)
        present = {_upper(row.get("ticker")) for row in rows if _upper(row.get("ticker"))}
        matched = sorted(t for t in tickers if t in present)
        coverage[name] = {
            "matched": len(matched),
            "total_manual": len(tickers),
            "missing": sorted(t for t in tickers if t not in present),
        }
    return {"status": "PASS", "path": str(manual_path), "tickers": tickers, "coverage": coverage}


def _scenario_candidate(row: Dict[str, Any], idx: int, scenario: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    side = "CALL" if idx % 2 == 0 else "PUT"
    base = _positive_first(
        row,
        [
            "vwap_eod",
            "current_price",
            "spot_price",
            "underlying_price",
            "signal_price",
            "last_price",
            "strike",
            "contract_strike",
        ],
        default=50.0 + idx,
    )
    if base < 1:
        base = 50.0 + idx
    strike = _positive_first(row, ["strike", "contract_strike", "evening_strike"], default=base)
    premium = _positive_first(row, ["premium_eod", "premium_mid", "contract_premium", "entry_premium"], default=max(1.0, base * 0.03))
    target = max(base * 1.08, strike + premium * 1.2) if side == "CALL" else min(base * 0.92, strike - premium * 1.2)
    invalidation = base * 0.965 if side == "CALL" else base * 1.035
    transition = "BALANCE_TO_UPSIDE_EXPANSION" if side == "CALL" else "BALANCE_TO_DOWNSIDE_EXPANSION"

    cand = dict(row)
    cand.update(
        {
            "candidate_status": "READY_FOR_VALIDATION",
            "thesis_decision": row.get("thesis_decision") or "WATCHLIST",
            "direction": side,
            "option_direction": side,
            "signal_type": side,
            "state_transition_label": transition,
            "target_price": round(target, 4),
            "invalidation_level": round(invalidation, 4),
            "signal_price": round(base, 4),
            "current_price": round(base, 4),
            "scenario_name": scenario,
        }
    )

    if side == "CALL":
        vwap = base
        orb_high = base * 1.006
        orb_low = base * 0.994
        price = base * 1.014
        if scenario == "retest_wait":
            price = base * 1.002
            orb_high = base * 1.02
            orb_low = base * 0.99
        elif scenario == "chase_risk_armed":
            price = base * 1.04
            orb_high = base * 1.006
        elif scenario == "invalidation_break_block":
            price = base * 0.955
        elif scenario == "direction_reversal_block":
            price = base * 0.982
            orb_low = base * 0.99
    else:
        vwap = base
        orb_high = base * 1.006
        orb_low = base * 0.994
        price = base * 0.986
        if scenario == "retest_wait":
            price = base * 0.998
            orb_high = base * 1.01
            orb_low = base * 0.98
        elif scenario == "chase_risk_armed":
            price = base * 0.96
            orb_low = base * 0.994
        elif scenario == "invalidation_break_block":
            price = base * 1.045
        elif scenario == "direction_reversal_block":
            price = base * 1.018
            orb_high = base * 1.01

    quote_ts = datetime.now(timezone.utc)
    if scenario == "stale_quote_wait":
        quote_ts = quote_ts - timedelta(minutes=45)

    mid = premium
    bid = mid * 0.98
    ask = mid * 1.02
    if scenario == "spread_caution_armed":
        bid = mid * 0.95
        ask = mid * 1.05
    elif scenario == "wide_spread_block":
        bid = mid * 0.875
        ask = mid * 1.125
    elif scenario == "missing_contract_quote_block":
        bid = ""
        ask = ""
        mid = ""

    live = {
        "ticker": cand.get("ticker"),
        "scenario_name": scenario,
        "live_price": round(price, 4),
        "live_bid": round(price * 0.999, 4),
        "live_ask": round(price * 1.001, 4),
        "live_mid": round(price, 4),
        "live_volume": 250000,
        "live_vwap": round(vwap, 4),
        "live_open": round(base * (0.997 if side == "CALL" else 1.003), 4),
        "live_high": round(max(price, orb_high) * 1.002, 4),
        "live_low": round(min(price, orb_low) * 0.998, 4),
        "live_prev_close": round(base * (0.995 if side == "CALL" else 1.005), 4),
        "live_orb_high": round(orb_high, 4),
        "live_orb_low": round(orb_low, 4),
        "live_contract_bid": round(bid, 4) if isinstance(bid, float) else "",
        "live_contract_ask": round(ask, 4) if isinstance(ask, float) else "",
        "live_contract_mid": round(mid, 4) if isinstance(mid, float) else "",
        "live_contract_volume": 450,
        "live_contract_open_interest": 2200,
        "live_iv": 0.42,
        "live_delta": 0.45 if side == "CALL" else -0.45,
        "live_data_timestamp_utc": quote_ts.isoformat(),
    }
    return cand, live


def _run_scenario_replay(run_id: str, run_dir: Path, qa_dir: Path, stamp: str, max_candidates: int) -> Dict[str, Any]:
    source_path = run_dir / f"morning_validation/morning_candidates_{run_id}.csv"
    fields, rows = _read_csv(source_path)
    if not rows:
        return {
            "status": "FAIL",
            "reason": "morning candidates missing or empty",
            "source_path": str(source_path),
            "defects": [{"stage": "Scenario replay", "issue": "no_candidates"}],
        }

    selected = rows[: max_candidates or len(rows)]
    scenario_candidates: List[Dict[str, Any]] = []
    live_rows: List[Dict[str, Any]] = []
    ticker_to_scenario: Dict[str, str] = {}
    for idx, row in enumerate(selected):
        scenario = SCENARIOS[idx % len(SCENARIOS)]
        cand, live = _scenario_candidate(row, idx, scenario)
        ticker = _upper(cand.get("ticker"))
        ticker_to_scenario[ticker] = scenario
        scenario_candidates.append(cand)
        live_rows.append(live)

    candidate_fields = list(fields)
    for extra in [
        "scenario_name",
        "direction",
        "option_direction",
        "signal_type",
        "state_transition_label",
        "target_price",
        "invalidation_level",
        "signal_price",
        "current_price",
    ]:
        if extra not in candidate_fields:
            candidate_fields.append(extra)
    scenario_candidates_path = qa_dir / f"market_scenario_candidates_{run_id}_{stamp}.csv"
    live_path = qa_dir / f"market_scenario_live_overrides_{run_id}_{stamp}.csv"
    validated_path = qa_dir / f"market_scenario_validated_{run_id}_{stamp}.csv"
    _write_csv(scenario_candidates_path, scenario_candidates, candidate_fields)
    _write_csv(live_path, live_rows)

    validated = run_morning_validation(
        candidates_path=scenario_candidates_path,
        output_path=validated_path,
        run_id=run_id,
        max_signals=len(scenario_candidates),
        tier_filter=None,
        live_mode=True,
        runs_dir=RUNS_DIR,
        live_data_path=live_path,
        paper_mode=False,
        pipeline_mode="MORNING_VALIDATION",
        include_high_priority_wait=True,
    )
    summary = build_summary(run_id, validated, len(scenario_candidates))

    scenario_counts = Counter()
    permission_counts = Counter()
    failures: List[Dict[str, Any]] = []
    by_scenario: Dict[str, Counter] = defaultdict(Counter)
    for row in validated:
        ticker = _upper(row.get("ticker"))
        scenario = ticker_to_scenario.get(ticker) or str(row.get("scenario_name") or "")
        permission = _upper(row.get("execution_permission"))
        scenario_counts[scenario] += 1
        permission_counts[permission] += 1
        by_scenario[scenario][permission] += 1
        if permission not in EXPECTED.get(scenario, set()):
            failures.append(
                {
                    "ticker": ticker,
                    "scenario": scenario,
                    "expected": sorted(EXPECTED.get(scenario, set())),
                    "actual": permission,
                    "state": row.get("live_validation_state"),
                    "score": row.get("validation_score"),
                    "reason": row.get("rejection_reason") or row.get("wait_reason") or row.get("morning_notes"),
                }
            )

    return {
        "status": "PASS" if not failures else "FAIL",
        "source_candidates": str(source_path),
        "scenario_candidates": str(scenario_candidates_path),
        "live_overrides": str(live_path),
        "validated_output": str(validated_path),
        "summary": summary,
        "scenario_counts": dict(scenario_counts),
        "permission_counts": dict(permission_counts),
        "by_scenario": {k: dict(v) for k, v in sorted(by_scenario.items())},
        "expectation_failures": failures,
    }


def _status(artifact_audit: Dict[str, Any], scenario_replay: Dict[str, Any]) -> str:
    if artifact_audit["defects"] or scenario_replay.get("status") == "FAIL":
        return "FAIL"
    if artifact_audit["warnings"]:
        return "PASS_WITH_WARNINGS"
    return "PASS"


def _write_markdown(path: Path, report: Dict[str, Any]) -> None:
    audit = report["artifact_audit"]
    replay = report["scenario_replay"]
    lines = [
        f"# Market Scenario Stress Test - {report['run_id']}",
        "",
        f"Status: **{report['status']}**",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        "## Artifact Audit",
        "",
        "| Stage | Status | Rows/Files | Path |",
        "|---|---:|---:|---|",
    ]
    for stage in audit["stages"]:
        count = stage.get("rows", stage.get("files", ""))
        lines.append(f"| {stage['stage']} | {stage['status']} | {count} | `{stage['path']}` |")

    lines.extend(["", "## Scenario Replay", ""])
    lines.append(f"Replay status: **{replay.get('status')}**")
    if replay.get("summary"):
        summary = replay["summary"]
        lines.append(
            f"Validated {summary.get('validated_count')} candidates: "
            f"GO={summary.get('go_count')} ARMED={summary.get('armed_count')} "
            f"WAIT={summary.get('wait_count')} BLOCKED={summary.get('blocked_count')}."
        )
    if replay.get("by_scenario"):
        lines.extend(["", "| Scenario | Outcomes |", "|---|---|"])
        for scenario, outcomes in replay["by_scenario"].items():
            outcome_text = ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items()))
            lines.append(f"| {scenario} | {outcome_text} |")

    lines.extend(["", "## Findings", ""])
    if audit["defects"] or replay.get("expectation_failures"):
        for defect in audit["defects"]:
            lines.append(f"- DEFECT: {defect.get('stage')}: {defect.get('issue')} - {defect.get('detail', '')}")
        for failure in replay.get("expectation_failures", []):
            lines.append(
                "- DEFECT: Scenario "
                f"{failure['scenario']} for {failure['ticker']} expected {failure['expected']} "
                f"but got {failure['actual']} ({failure.get('reason') or 'no reason captured'})."
            )
    else:
        lines.append("- No blocking defects in artifact presence or scenario expectations.")
    for warning in audit["warnings"]:
        lines.append(f"- WARNING: {warning.get('stage')}: {warning.get('issue')} - {warning.get('detail', '')}")

    manual = report.get("manual_upload_coverage", {})
    if manual.get("status") == "PASS":
        lines.extend(["", "## Manual Upload Coverage", ""])
        for stage, payload in manual.get("coverage", {}).items():
            lines.append(f"- {stage}: {payload['matched']}/{payload['total_manual']} matched; missing={payload['missing']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(run_id: str, max_candidates: int) -> Dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run folder not found: {run_dir}")
    stamp = _now_stamp()
    qa_dir = QA_DIR / "market_scenarios"
    qa_dir.mkdir(parents=True, exist_ok=True)

    audit = _artifact_audit(run_id, run_dir)
    replay = _run_scenario_replay(run_id, run_dir, qa_dir, stamp, max_candidates)
    manual = _manual_upload_coverage(run_id, run_dir)
    report = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": _status(audit, replay),
        "artifact_audit": audit,
        "scenario_replay": replay,
        "manual_upload_coverage": manual,
    }

    json_path = qa_dir / f"market_scenario_stress_report_{run_id}_{stamp}.json"
    md_path = qa_dir / f"market_scenario_stress_report_{run_id}_{stamp}.md"
    report["report_json"] = str(json_path)
    report["report_markdown"] = str(md_path)
    _write_json(json_path, report)
    _write_markdown(md_path, report)
    return report


def main() -> int:
    if not _LEGACY_MORNING_VALIDATOR_AVAILABLE:
        print(
            "RETIRED: this scenario replayer targeted morning_thesis_validator.py. "
            "Production uses morning_gate.py; run the current morning-gate tests instead."
        )
        return 2
    parser = argparse.ArgumentParser(description="Stress-test completed AVSHUNTER output with synthetic live scenarios.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-candidates", type=int, default=60)
    parser.add_argument("--strict", action="store_true", help="Return non-zero on warnings as well as defects.")
    args = parser.parse_args()

    run_id = args.run_id or _latest_run_id()
    report = run(run_id, args.max_candidates)
    compact = {
        "run_id": report["run_id"],
        "status": report["status"],
        "artifact_defects": len(report["artifact_audit"]["defects"]),
        "artifact_warnings": len(report["artifact_audit"]["warnings"]),
        "scenario_status": report["scenario_replay"].get("status"),
        "scenario_failures": len(report["scenario_replay"].get("expectation_failures", [])),
        "scenario_permissions": report["scenario_replay"].get("permission_counts"),
        "report_markdown": report["report_markdown"],
        "report_json": report["report_json"],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=True))
    if report["status"] == "FAIL":
        return 1
    if args.strict and report["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
