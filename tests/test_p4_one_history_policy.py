"""Phase 4 / RC04: one declared history policy, with precise reasons.

Business rules:
- History must reach the evidence session (point-in-time: Vanguard analyses AS OF the completed session).
  The manifest and the runtime package factory apply the SAME function, so they cannot disagree
  (Phase 0: QRVO was manifest VALID but rejected at runtime).
- A rejection states its reason: NO_BARS / INSUFFICIENT_HISTORY / HISTORY_BEHIND_EVIDENCE_SESSION - never
  "NO_OHLCV" when bars exist.
"""
import ast
from datetime import date
from pathlib import Path

import pandas as pd

from avshunter.c0_run.canonical_manifest import evidence_history_policy

ROOT = Path(__file__).resolve().parents[1]
SESSION = date(2026, 10, 5)


def _frame(n, last="2026-10-05"):
    d = pd.bdate_range(end=last, periods=n)
    return pd.DataFrame({"date": d.strftime("%Y-%m-%d"), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                         "volume": 1.0})


def test_history_reaching_the_session_is_valid():
    v = evidence_history_policy(_frame(300), evidence_session=SESSION, min_bars=60)
    assert v["ok"] and v["reason"] == "VALID"


def test_history_behind_the_session_says_so():
    v = evidence_history_policy(_frame(1284, last="2026-10-02"), evidence_session=SESSION, min_bars=60)
    assert not v["ok"] and v["reason"].startswith("HISTORY_BEHIND_EVIDENCE_SESSION")
    assert "2026-10-02" in v["reason"]


def test_short_and_missing_history_say_so():
    assert evidence_history_policy(_frame(10), evidence_session=SESSION, min_bars=60)["reason"].startswith(
        "INSUFFICIENT_HISTORY")
    assert evidence_history_policy(pd.DataFrame(), evidence_session=SESSION, min_bars=60)["reason"] == "NO_BARS"


def _calls(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8-sig"))
    return {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            for n in ast.walk(tree) if isinstance(n, ast.Call)}


def test_manifest_and_factory_use_the_same_policy():
    assert "evidence_history_policy" in _calls("avshunter/c0_run/canonical_manifest.py")
    assert "evidence_history_policy" in _calls("avshunter/c0_run/thin_package.py")


def test_adapter_reports_the_factory_reason_not_no_ohlcv():
    from vanguard.integration.orchestrator_adapter import _bar_rejection_code
    assert _bar_rejection_code({"data_failure_reason": "HISTORY_BEHIND_EVIDENCE_SESSION (last 2026-10-02, "
                                                       "session 2026-10-05)"}) == "HISTORY_BEHIND_EVIDENCE_SESSION"
    assert _bar_rejection_code({}) == "NO_OHLCV_DATA"
