"""Build the governed EV3 outcome-calibration readiness report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
import uuid

import pandas as pd


SCHEMA_VERSION = "ev3-calibration-readiness-v1"
MIN_MATCHED_OUTCOMES = 30
MIN_OUTCOMES_PER_EV_BAND = 10
EVALUATED_STATUSES = {"EVALUATED_PRODUCTION_EVIDENCE", "EVALUATED_SHADOW"}


def _read_sqlite(path: Path, table: str) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro&immutable=1", uri=True
    )
    try:
        return pd.read_sql_query(f"SELECT * FROM {table}", connection)
    except Exception:
        return pd.DataFrame()
    finally:
        connection.close()


def _prediction_rows(runs_dir: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in sorted(runs_dir.glob("*/ev3_shadow/ev3_stage1_shadow_results.parquet")):
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        if "ev3_status" not in frame.columns:
            continue
        frame = frame[frame["ev3_status"].astype(str).isin(EVALUATED_STATUSES)].copy()
        if frame.empty:
            continue
        frame["run_id"] = path.parents[1].name
        frame["ticker"] = frame.get("ticker", "").astype(str).str.upper().str.strip()
        keep = [column for column in (
            "run_id", "ticker", "ev3_contract_symbol", "ev3_absolute_state",
            "ev3_ev_conservative_return", "ev3_ev_lower_bound_return",
        ) if column in frame.columns]
        rows.append(frame[keep])
    if not rows:
        return pd.DataFrame(columns=["run_id", "ticker"])
    return pd.concat(rows, ignore_index=True).drop_duplicates(
        ["run_id", "ticker"], keep="last"
    )


def build_report(runs_dir: Path, trade_journal: Path, phantom_db: Path) -> dict[str, Any]:
    predictions = _prediction_rows(runs_dir)
    closed = _read_sqlite(trade_journal, "closed_trades")
    phantom = _read_sqlite(phantom_db, "phantom_outcomes")
    outcomes: list[pd.DataFrame] = []
    if not closed.empty and {"run_id", "ticker"}.issubset(closed.columns):
        journal = closed.copy()
        journal["realised_pnl"] = pd.to_numeric(
            journal.get("pnl_pct_premium", journal.get("pnl_usd")), errors="coerce"
        )
        journal["outcome_source"] = "TRADE_JOURNAL"
        outcomes.append(journal[["run_id", "ticker", "realised_pnl", "outcome_source"]])
    if not phantom.empty and {"run_id", "ticker"}.issubset(phantom.columns):
        observed = phantom.copy()
        observed["realised_pnl"] = pd.to_numeric(observed.get("pnl"), errors="coerce")
        observed["outcome_source"] = "PHANTOM"
        outcomes.append(observed[["run_id", "ticker", "realised_pnl", "outcome_source"]])
    outcome_frame = (
        pd.concat(outcomes, ignore_index=True)
        if outcomes else pd.DataFrame(columns=["run_id", "ticker", "realised_pnl", "outcome_source"])
    )
    for frame in (predictions, outcome_frame):
        if not frame.empty:
            frame["run_id"] = frame["run_id"].astype(str)
            frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    outcome_frame = outcome_frame.dropna(subset=["realised_pnl"]).drop_duplicates(
        ["run_id", "ticker"], keep="last"
    )
    matched = predictions.merge(outcome_frame, on=["run_id", "ticker"], how="inner")
    absolute = matched.get("ev3_absolute_state", pd.Series(index=matched.index, dtype=str)).astype(str)
    positive_band = matched[absolute == "POSITIVE_UNVALIDATED"]
    nonpositive_band = matched[absolute.isin({"NEGATIVE_EV", "INDETERMINATE"})]
    reasons: list[str] = []
    if len(matched) < MIN_MATCHED_OUTCOMES:
        reasons.append("MATCHED_OUTCOMES_BELOW_MINIMUM")
    if len(positive_band) < MIN_OUTCOMES_PER_EV_BAND:
        reasons.append("POSITIVE_EV_BAND_OUTCOMES_BELOW_MINIMUM")
    if len(nonpositive_band) < MIN_OUTCOMES_PER_EV_BAND:
        reasons.append("NONPOSITIVE_EV_BAND_OUTCOMES_BELOW_MINIMUM")
    status = "PASS" if not reasons else "INSUFFICIENT_OUTCOMES"
    realised = matched.get("realised_pnl", pd.Series(dtype=float))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "capital_authority_calibrated": status == "PASS",
        "activation_reasons": reasons,
        "minimum_matched_outcomes": MIN_MATCHED_OUTCOMES,
        "minimum_outcomes_per_ev_band": MIN_OUTCOMES_PER_EV_BAND,
        "prediction_rows": int(len(predictions)),
        "journal_outcome_rows": int(len(closed)),
        "phantom_outcome_rows": int(len(phantom)),
        "matched_outcome_rows": int(len(matched)),
        "matched_positive_ev_rows": int(len(positive_band)),
        "matched_nonpositive_ev_rows": int(len(nonpositive_band)),
        "matched_profitable_rows": int((realised > 0).sum()),
        "matched_win_rate": round(float((realised > 0).mean()), 6) if len(matched) else None,
        "runs_dir": str(runs_dir.resolve()),
        "trade_journal": str(trade_journal.resolve()),
        "phantom_db": str(phantom_db.resolve()),
    }


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--trade-journal", type=Path, required=True)
    parser.add_argument("--phantom-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.runs_dir, args.trade_journal, args.phantom_db)
    write_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
