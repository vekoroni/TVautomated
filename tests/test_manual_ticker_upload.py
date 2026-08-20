from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import intelligent_orchestrator as orch  # noqa: E402


def test_manual_ticker_upload_is_retired_and_ignored() -> None:
    old_universe = orch.cfg.UNIVERSE_FILE
    old_upload = orch.cfg.MANUAL_TICKER_UPLOAD_FILE
    old_age = orch.cfg.MANUAL_TICKER_MAX_AGE_HOURS

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        universe = tmp_path / "polygon_liquid_universe.csv"
        upload = tmp_path / "manual_ticker_upload_latest.csv"
        universe.write_text("ticker\nINTC\nNVDA\n", encoding="utf-8")
        upload.write_text("ticker\nINTC\nXOM\nXOM\nCVX\nBAD.A\n", encoding="utf-8")

        orch.cfg.UNIVERSE_FILE = universe
        orch.cfg.MANUAL_TICKER_UPLOAD_FILE = upload
        orch.cfg.MANUAL_TICKER_MAX_AGE_HOURS = 24

        payload = orch.load_manual_ticker_upload()

    orch.cfg.UNIVERSE_FILE = old_universe
    orch.cfg.MANUAL_TICKER_UPLOAD_FILE = old_upload
    orch.cfg.MANUAL_TICKER_MAX_AGE_HOURS = old_age

    assert payload["available"] is False
    assert payload["go_new"] == []
    assert payload["go_known"] == []
    assert payload["probe_known"] == []
    assert payload["probe_new"] == []
    assert payload["all_new"] == []
    assert payload["vms_df"] is None


def test_manual_merge_preserves_real_scanner_context() -> None:
    scanner = {
        "available": True,
        "go_new": ["INTC"],
        "go_known": [],
        "probe_new": [],
        "probe_known": [],
        "all_new": ["INTC"],
        "run_id": "scanner",
        "age_hrs": 1.0,
        "tiers_run": ["TIER1"],
        "vms_df": pd.DataFrame(
            [{"ticker": "INTC", "decision": "GO", "score": 80, "pipeline_tag": "NEW"}]
        ),
    }
    manual = {
        "available": True,
        "go_new": [],
        "go_known": [],
        "probe_new": [],
        "probe_known": [],
        "all_new": ["INTC", "CVX"],
        "manual_new": ["INTC", "CVX"],
        "manual_known": [],
        "run_id": "manual",
        "age_hrs": 0.5,
        "tiers_run": ["MANUAL_UPLOAD"],
        "vms_df": None,
    }

    merged = orch.merge_scanner_inputs(scanner, manual)
    rows = {row["ticker"]: row for row in merged["vms_df"].to_dict("records")}

    assert merged["all_new"] == ["INTC", "CVX"]
    assert rows["INTC"]["decision"] == "GO"
    assert rows["INTC"]["score"] == 80
    assert "CVX" not in rows


if __name__ == "__main__":
    test_manual_ticker_upload_is_retired_and_ignored()
    test_manual_merge_preserves_real_scanner_context()
    print("manual_ticker_upload tests passed")
