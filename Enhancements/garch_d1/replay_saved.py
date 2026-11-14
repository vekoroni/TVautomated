"""Read-only D1 arithmetic/model-preservation replay; never runs a pipeline.

Replays saved forecasts without refitting, then compares the unchanged model
against the pre-D1 arithmetic on point-in-time COMPLETE canonical price bars.
Only the explicitly supplied evidence report is written.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import socket
import sqlite3
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def blocked(*args, **kwargs):
    raise AssertionError("Saved-only replay: network forbidden")


socket.socket.connect = blocked
socket.create_connection = blocked

import pandas as pd
import layer3_forward_variance as l3
from tools.avs_verify import avs_verify as verifier


def fingerprint(path):
    if not path.exists():
        return None
    stat = path.stat()
    with path.open("rb") as handle:
        header = hashlib.sha256(handle.read(4096)).hexdigest()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "header_sha256": header}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    db = ROOT / "data/canonical/historical_prices.sqlite"
    saved = ROOT / "data/output/runs/20261111_231951/qomega/garch_forecasts_20261111_231951.csv"
    paths = [db, Path(str(db) + "-wal"), saved]
    before = {str(p): fingerprint(p) for p in paths}

    saved_rows = list(csv.DictReader(saved.open(encoding="utf-8-sig", newline="")))
    checked = old_bad = new_bad = missing = 0
    corrected_rows = []
    for row in saved_rows:
        try:
            vol = float(row["l3_forward_realised_vol"])
            old = [float(row[f"l3_expected_move_{key}"]) for key in ("1_5d", "6_10d", "11_20d")]
            assert math.isfinite(vol) and vol > 0 and all(math.isfinite(x) for x in old)
        except (ValueError, TypeError, AssertionError):
            missing += 1
            continue
        checked += 1
        old_bad += not (old[0] <= old[1] <= old[2])
        new = [l3._expected_move(vol, n) for n in (5, 10, 20)]
        new_bad += not (new[0] <= new[1] <= new[2])
        corrected_rows.append({**row, **{f"l3_expected_move_{key}": value
            for key, value in zip(("1_5d", "6_10d", "11_20d"), new)}})

    cfg = json.loads((ROOT / "tools/avs_verify/avs_verify_rules.json").read_text(encoding="utf-8-sig"))
    cm = {key: None for key in cfg["columns"]}
    cm.update(dict(zip(("garch_1_5", "garch_6_10", "garch_11_20"),
                       ("l3_expected_move_1_5d", "l3_expected_move_6_10d", "l3_expected_move_11_20d"))))
    findings = verifier.F({})
    verifier.r_rows(corrected_rows, list(range(len(corrected_rows))), cm, cfg, "evening", None, findings)
    r17 = next(item for item in findings.book if item["rule"] == "R17_GARCH_MONOTONIC")
    assert r17["status"] == "PASS", r17

    # Pre-D1 public API reconstructed in memory, with exactly the old arithmetic.
    # Model fitting, quality checks and volatility bounds are byte-for-byte the
    # same source as the corrected module. No source file is edited for replay.
    source = Path(l3.__file__).read_text(encoding="utf-8-sig")
    old_source = source.replace("em_6_10  = _expected_move(ann_vol, 10)",
        "em_6_10  = _expected_move(ann_vol, 10) - _expected_move(ann_vol, 5)")
    old_source = old_source.replace("em_11_20 = _expected_move(ann_vol, 20)",
        "em_11_20 = _expected_move(ann_vol, 20) - _expected_move(ann_vol, 10)")
    assert old_source != source
    baseline = types.ModuleType("_garch_d1_pre_fix")
    baseline.__file__ = l3.__file__
    sys.modules[baseline.__name__] = baseline
    exec(compile(old_source, l3.__file__, "exec"), baseline.__dict__)
    baseline._expected_move = lambda vol, days: vol * math.sqrt(days * 5 / 7 / 252) * 100

    details = []
    ignored = {"expected_move_1_5d", "expected_move_6_10d", "expected_move_11_20d"}
    connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        for ticker in ("SPY", "QQQ", "AAPL", "NVDA", "PH", "BILI", "LWLG", "CBRL", "VICI"):
            for asof in ("2026-10-20", "2026-11-06", "2026-11-12"):
                rows = connection.execute("""SELECT trading_date AS date, open, high, low, close, volume
                    FROM ohlcv_daily WHERE ticker=? AND trading_date<=? AND bar_status='COMPLETE'
                    ORDER BY trading_date DESC LIMIT 261""", (ticker, asof)).fetchall()
                assert rows, (ticker, asof)
                frame = pd.DataFrame(rows[::-1], columns=["date", "open", "high", "low", "close", "volume"])
                for length in (261, 41, 16):
                    history = frame.tail(length)
                    old = baseline.compute_forward_variance(ticker, history)
                    new = l3.compute_forward_variance(ticker, history)
                    differences = [key for key in vars(new) if key not in ignored and getattr(old, key) != getattr(new, key)]
                    assert not differences, (ticker, asof, length, differences)
                    vol = new.forward_realised_vol
                    assert vol is not None, (ticker, asof, new.error)
                    moves = [new.expected_move_1_5d, new.expected_move_6_10d, new.expected_move_11_20d]
                    assert all(math.isclose(actual, vol * math.sqrt(n / 252) * 100, rel_tol=1e-12)
                               for actual, n in zip(moves, (5, 10, 20)))
                    assert 0 < moves[0] <= moves[1] <= moves[2]
                    details.append({"ticker": ticker, "asof": asof, "last_bar": str(frame.iloc[-1]["date"]),
                        "bars": len(history), "method": new.method, "forecast_state": new.forecast_state,
                        "annual_vol": vol, "before_percent": [old.expected_move_1_5d, old.expected_move_6_10d, old.expected_move_11_20d],
                        "after_percent": moves, "other_result_fields_unchanged": True})
    finally:
        connection.close()
    after = {str(p): fingerprint(p) for p in paths}
    assert before == after, "Source changed during replay; do not claim source preservation"
    report = {"status": "PASS", "network": "BLOCKED", "source_files_unchanged": True,
        "scope": "D1 calculation integrity, not predictive accuracy or profitability validation",
        "saved_forecast_rows": len(saved_rows), "finite_forecasts_tested": checked,
        "unassessed_missing_forecasts": missing, "old_non_cumulative_rows": old_bad,
        "corrected_non_cumulative_rows": new_bad, "r17_arithmetic_pass_rate": (checked-new_bad)/checked,
        "r17_existing_verifier_on_replay_rows": r17,
        "point_in_time_replays": len(details), "methods": dict(Counter(r["method"] for r in details)),
        "all_non_move_result_fields_unchanged": True, "source_before": before, "source_after": after,
        "code_sha256": hashlib.sha256(source.encode()).hexdigest(), "replays": details,
        "limitations": ["No live files republished; historical run left unchanged",
            "Scaled existing annual forecast, not separately fitted horizon term structure",
            "No forecast calibration, target-hit probability or option profitability claim"]}
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("source_before", "source_after", "replays")}, indent=2))


if __name__ == "__main__":
    main()
