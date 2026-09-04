from pathlib import Path
import sqlite3

import pandas as pd

from scripts.ev3_calibration_report import build_report


def _db(path: Path, ddl: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute(ddl)
    return connection


def test_calibration_report_fails_closed_when_outcomes_are_absent(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    result_dir = runs / "20260828_100000" / "ev3_shadow"
    result_dir.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "TEST", "ev3_status": "EVALUATED_PRODUCTION_EVIDENCE",
        "ev3_absolute_state": "NEGATIVE_EV", "ev3_ev_conservative_return": -0.1,
        "ev3_ev_lower_bound_return": -0.2,
    }]).to_parquet(result_dir / "ev3_stage1_shadow_results.parquet", index=False)
    journal = tmp_path / "journal.db"
    _db(journal, "CREATE TABLE closed_trades (run_id TEXT, ticker TEXT, pnl_pct_premium REAL)").close()
    phantom = tmp_path / "phantom.db"
    _db(phantom, "CREATE TABLE phantom_outcomes (run_id TEXT, ticker TEXT, pnl REAL)").close()

    report = build_report(runs, journal, phantom)

    assert report["status"] == "INSUFFICIENT_OUTCOMES"
    assert report["capital_authority_calibrated"] is False
    assert report["matched_outcome_rows"] == 0


def test_calibration_report_passes_only_with_both_ev_bands(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    result_dir = runs / "20260828_100001" / "ev3_shadow"
    result_dir.mkdir(parents=True)
    rows = [{
        "ticker": f"T{index}", "ev3_status": "EVALUATED_PRODUCTION_EVIDENCE",
        "ev3_absolute_state": "POSITIVE_UNVALIDATED" if index < 10 else "NEGATIVE_EV",
        "ev3_ev_conservative_return": 0.1 if index < 10 else -0.1,
        "ev3_ev_lower_bound_return": 0.05 if index < 10 else -0.2,
    } for index in range(30)]
    pd.DataFrame(rows).to_parquet(result_dir / "ev3_stage1_shadow_results.parquet", index=False)
    journal = tmp_path / "journal.db"
    connection = _db(journal, "CREATE TABLE closed_trades (run_id TEXT, ticker TEXT, pnl_pct_premium REAL)")
    connection.executemany(
        "INSERT INTO closed_trades VALUES (?, ?, ?)",
        [("20260828_100001", f"T{index}", 1.0 if index % 2 == 0 else -1.0) for index in range(30)],
    )
    connection.commit()
    connection.close()
    phantom = tmp_path / "phantom.db"
    _db(phantom, "CREATE TABLE phantom_outcomes (run_id TEXT, ticker TEXT, pnl REAL)").close()

    report = build_report(runs, journal, phantom)

    assert report["status"] == "PASS"
    assert report["capital_authority_calibrated"] is True
    assert report["matched_outcome_rows"] == 30
