"""Read-only S0 inventory for AVS-SD-TEV-001.

This is a coverage *proxy*, not a C4 training set: actuarial v7 has fixed
5/10/20-day labels but not the frozen, per-geometry first-passage trajectories
required by the signed-off design. It prints JSON to stdout and writes nothing.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
ACTUARIAL = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet")
PHANTOM = ROOT / "data" / "phantom" / "phantom_history.db"
CANONICAL_PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"
RUN_STATUS = (
    ROOT / "data" / "output" / "runs" / "20260926_173730"
    / "ev3_shadow" / "ev3_shadow_phase_status_20260926_173730.json"
)


def _bucket(value: object) -> str:
    if value is None:
        return "MISSING"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "INVALID"
    if not 0 <= number <= 100:
        return "INVALID"
    return "LOW" if number < 20 else "MID" if number <= 80 else "HIGH"


def _actuarial_inventory(path: Path) -> dict:
    file = pq.ParquetFile(path)
    cols = [
        "ticker", "date", "wyckoff_phase_bucket", "bb_percentile",
        "vol_regime", "mature_20d",
    ]
    counts = Counter()
    dates: set[str] = set()
    mature_dates: set[str] = set()
    tickers: set[str] = set()
    combo_counts: Counter[tuple[str, str, str]] = Counter()
    combo_dates: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for batch in file.iter_batches(batch_size=65536, columns=cols):
        arrays = [batch.column(i).to_pylist() for i in range(len(cols))]
        for ticker, day, wyckoff, bb, vol, mature in zip(*arrays):
            counts["rows"] += 1
            if day:
                dates.add(str(day))
            if ticker:
                tickers.add(str(ticker))
            if mature is not True:
                continue
            counts["mature_20d_rows"] += 1
            if not day:
                counts["mature_missing_date"] += 1
                continue
            day_text = str(day)
            mature_dates.add(day_text)
            key = (str(wyckoff or "MISSING"), _bucket(bb), str(vol or "MISSING"))
            combo_counts[key] += 1
            combo_dates[key].add(day_text)
    ordered_dates = sorted(dates)
    block_by_date = {day: index // 20 for index, day in enumerate(ordered_dates)}
    combos = [
        {
            "wyckoff": key[0], "compression_proxy": key[1], "vol_regime": key[2],
            "raw_mature_rows": count,
            "distinct_20_session_date_blocks": len({block_by_date[day] for day in combo_dates[key]}),
        }
        for key, count in combo_counts.most_common()
    ]
    return {
        "path": str(path), "parquet_rows": file.metadata.num_rows,
        "scanned_rows": counts["rows"], "mature_20d_rows": counts["mature_20d_rows"],
        "unique_tickers": len(tickers), "distinct_dates": len(dates),
        "mature_distinct_dates": len(mature_dates),
        "mature_distinct_20_session_date_blocks": len({block_by_date[day] for day in mature_dates}),
        "diagnostic_combo_count": len(combos),
        "diagnostic_combos_with_40_rows_and_12_blocks": sum(
            item["raw_mature_rows"] >= 40
            and item["distinct_20_session_date_blocks"] >= 12 for item in combos
        ),
        "top_diagnostic_combos": combos[:15],
        "limitations": [
            "Fixed-horizon labels are not C4 candidate-geometry first-passage paths.",
            "Raw rows are not independent ticker-starts; adjacent 20-session labels overlap.",
            "The parquet does not provide a governed sector join or run-frozen macro release lineage.",
            "The diagnostic three-way grid is not the proposed forecasting estimator.",
        ],
    }


def _phantom_inventory(path: Path) -> dict:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        wanted = ["phantom_outcomes", "phantom_scores", "chain_snapshots", "options_greeks_history"]
        schemas = {}
        for name in wanted:
            schemas[name] = [row[1] for row in connection.execute(f"PRAGMA table_info({name})")]
        return {
            "path": str(path), "read_only_open": True,
            "relevant_table_columns": schemas,
            "limitations": [
                "Chain snapshots are market quotes, not demonstrated fills.",
                "Phantom outcome rows do not alone supply C4 first-passage labels or sector lineage.",
                "No live database tables or WAL were modified.",
            ],
        }
    finally:
        connection.close()


def _canonical_price_inventory(path: Path) -> dict:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        row = connection.execute(
            """SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(trading_date),
                      MAX(trading_date),
                      SUM(CASE WHEN bar_status='COMPLETE' THEN 1 ELSE 0 END)
               FROM ohlcv_daily"""
        ).fetchone()
        revisions = connection.execute(
            "SELECT COUNT(*) FROM ohlcv_daily_revisions"
        ).fetchone()[0]
        columns = [item[1] for item in connection.execute("PRAGMA table_info(ohlcv_daily)")]
        return {
            "path": str(path), "read_only_open": True,
            "bars": row[0], "tickers": row[1],
            "first_session": row[2], "last_session": row[3],
            "complete_bars": row[4], "revisions": revisions,
            "columns": columns,
            "limitations": [
                "Current canonical rows and revision history require an as-of reconstruction before historical feature use.",
                "A complete bar is not proof the exact ticker/geometry start has an uninterrupted 20-session future path.",
                "Session-calendar alignment and corporate-action convention must reconcile with actuarial v7 before a label is certified.",
                "No live database tables or WAL were modified.",
            ],
        }
    finally:
        connection.close()


def main() -> None:
    status = json.loads(RUN_STATUS.read_text(encoding="utf-8"))
    report = {
        "audit": "AVS-SD-TEV-001/S0",
        "read_only": True,
        "actuarial": _actuarial_inventory(ACTUARIAL),
        "phantom": _phantom_inventory(PHANTOM),
        "canonical_prices": _canonical_price_inventory(CANONICAL_PRICES),
        "ev3_baseline": {
            key: status.get(key) for key in (
                "run_id", "rows_received", "rows_applicable", "rows_evaluated",
                "rows_rejected", "rows_not_applicable", "reason_counts",
                "contract_evaluation_reason_counts", "ev_functional_health",
            )
        },
        "s0_decision": "PROXY_ONLY_C4_FEASIBILITY_NOT_YET_CERTIFIED",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
