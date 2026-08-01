"""
tests/lab_qa_audit.py is the sprint's acceptance harness (BASELINE.md /
LAB_FIX_SPRINT_REPORT.md track its P0/P1 counts). Its own EXPECTED_MISSING
check compared column names with exact-case equality against snake_case
names ("trade_idea_id"), while every export column uses TitleCase
("Trade_Idea_Id") — so a genuinely-exported field still read as "absent".
This test locks in the case-insensitive fix.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_audit_module():
    path = ROOT / "tests" / "lab_qa_audit.py"
    spec = importlib.util.spec_from_file_location("lab_qa_audit_for_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _base_df(extra_cols=None):
    audit = _load_audit_module()
    row = {c: "x" for c in audit.REQUIRED}
    row.update(extra_cols or {})
    return audit, pd.DataFrame([row])


def test_expected_missing_recognises_titlecase_export_column():
    audit, df = _base_df({"Trade_Idea_Id": "20260731_083130:T:PUT:23.0:2026-08-21"})
    reg = audit.Register()
    audit.chk_schema(df, reg, raw=None)

    eligibility = [f for f in reg.items if f["title"] == "Eligibility fields not present in export"]
    assert eligibility, "chk_schema should still report on eligibility fields"
    assert "trade_idea_id" not in eligibility[0]["evidence"]["absent"], (
        "Trade_Idea_Id is present in the export (case-insensitively) and must not be listed as absent"
    )
    assert "live_data_mode" in eligibility[0]["evidence"]["absent"], (
        "live_data_mode is genuinely absent (item 13, not fixed this sprint) and must still be flagged"
    )


def test_expected_missing_still_fires_when_genuinely_absent():
    audit, df = _base_df()
    reg = audit.Register()
    audit.chk_schema(df, reg, raw=None)

    eligibility = [f for f in reg.items if f["title"] == "Eligibility fields not present in export"]
    assert eligibility
    assert set(eligibility[0]["evidence"]["absent"]) == {"live_data_mode", "trade_idea_id"}
