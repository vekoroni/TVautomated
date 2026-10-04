import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "Enhancements" / "phase0" / "actuarial_refresh" / "reconcile_adjusted_history.py"
SPEC = importlib.util.spec_from_file_location("reconcile_adjusted_history", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_source(directory, ticker, dates, closes, *, max_date=None):
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"date": dates, "open": closes, "high": closes,
                          "low": closes, "close": closes, "volume": [100] * len(dates)})
    frame.to_csv(directory / f"{ticker}.csv", index=False)
    manifest = {"status": "COMPLETE", "provider": "Polygon", "adjusted": True,
                "tickers": {ticker: {"status": "PERSISTED", "max_date": max_date or dates[-1],
                                     "sha256": MODULE.sha256(directory / f"{ticker}.csv")}}}
    (directory / "_source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_reconcile_preserves_verified_older_prefix(tmp_path):
    old, fresh = tmp_path / "old", tmp_path / "fresh"
    _write_source(old, "A", ["2021-09-29", "2021-09-30", "2021-10-01"], [10, 11, 12])
    _write_source(fresh, "A", ["2021-10-01", "2026-10-01"], [12, 13])
    result = MODULE.reconcile(old, fresh)
    assert result == {"PREPEND": 1, "CARRY_HISTORICAL": 0, "prefix_rows": 2}
    actual = pd.read_csv(fresh / "A.csv")
    assert actual["date"].tolist() == ["2021-09-29", "2021-09-30", "2021-10-01", "2026-10-01"]
    manifest = json.loads((fresh / "_source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["tickers"]["A"]["sha256"] == MODULE.sha256(fresh / "A.csv")


def test_reconcile_refuses_adjustment_change_without_modifying_stage(tmp_path):
    old, fresh = tmp_path / "old", tmp_path / "fresh"
    _write_source(old, "A", ["2021-09-30", "2021-10-01"], [10, 11])
    _write_source(fresh, "A", ["2021-10-01", "2026-10-01"], [22, 23])
    before = MODULE.sha256(fresh / "A.csv")
    with pytest.raises(ValueError, match="volume does not confirm"):
        MODULE.reconcile(old, fresh)
    assert MODULE.sha256(fresh / "A.csv") == before


def test_reconcile_refuses_missing_recent_ticker(tmp_path):
    old, fresh = tmp_path / "old", tmp_path / "fresh"
    _write_source(old, "A", ["2026-09-15", "2026-09-16"], [10, 11])
    fresh.mkdir()
    (fresh / "_source_manifest.json").write_text(
        json.dumps({"status": "COMPLETE", "provider": "Polygon", "adjusted": True,
                    "tickers": {"A": {"status": "INSUFFICIENT_DATA"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="current source disappeared"):
        MODULE.reconcile(old, fresh)


def test_reconcile_rebases_old_prefix_after_split(tmp_path):
    old, fresh = tmp_path / "old", tmp_path / "fresh"
    _write_source(old, "A", ["2021-09-30", "2021-10-01"], [10, 11])
    _write_source(fresh, "A", ["2021-10-01", "2026-10-01"], [110, 120])
    frame = pd.read_csv(fresh / "A.csv")
    frame.loc[0, "volume"] = 10
    frame.to_csv(fresh / "A.csv", index=False)
    result = MODULE.reconcile(old, fresh)
    assert result["prefix_rows"] == 1
    actual = pd.read_csv(fresh / "A.csv")
    assert actual.loc[0, "close"] == 100
    assert actual.loc[0, "volume"] == 10
    manifest = json.loads((fresh / "_source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["tickers"]["A"]["retained_prefix_adjustment_factor"] == 10


def test_later_provider_correction_does_not_discard_verified_prefix(tmp_path):
    old, fresh = tmp_path / "old", tmp_path / "fresh"
    dates = [f"2021-10-{day:02d}" for day in range(1, 24)]
    _write_source(old, "A", ["2021-09-30", *dates], [9, *([10] * len(dates))])
    _write_source(fresh, "A", [*dates, "2026-10-01"], [*([10] * len(dates)), 11])
    frame = pd.read_csv(fresh / "A.csv")
    frame["open"] = frame["open"].astype(float)
    frame.loc[21, "open"] = 10.05
    frame.to_csv(fresh / "A.csv", index=False)
    MODULE.reconcile(old, fresh)
    actual = pd.read_csv(fresh / "A.csv")
    assert actual.loc[0, "date"] == "2021-09-30"
    assert actual.loc[22, "open"] == 10.05
