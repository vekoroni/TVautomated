"""Business rule for the two top-level producers (VIX engine v4.1, FRED monitor v2.6).

A pre-open run (AVSH_SESSION_CUTOFF set by Run-MacroInputs.ps1) never treats a partial "today" bar
as a finished US session; without the variable (Colab / manual runs) nothing is cut.
Both scripts fetch and write when imported, so the helpers are taken from the source and run alone.
No network, no live data.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
SCRIPTS = ["avshunter_vix_engine_v4_1.py", "avshunter_fred_monitor_v2_6.py"]


def _helpers(script):
    tree = ast.parse((HERE / script).read_text(encoding="utf-8"))
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name in ("session_cutoff", "cut_to_session")]
    assert len(wanted) == 2, f"{script} must define session_cutoff and cut_to_session"
    namespace = {"os": os, "pd": pd}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), script, "exec"), namespace)
    return namespace


@pytest.mark.parametrize("script", SCRIPTS)
def test_a_bar_dated_after_the_last_completed_us_session_is_not_used(script, monkeypatch):
    h = _helpers(script)
    monkeypatch.setenv("AVSH_SESSION_CUTOFF", "2026-10-07")
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-10-06", "2026-10-07", "2026-10-08"]))
    assert h["cut_to_session"](s, h["session_cutoff"]()).index.max() == pd.Timestamp("2026-10-07")


@pytest.mark.parametrize("script", SCRIPTS)
def test_without_a_cut_off_the_series_is_unchanged(script, monkeypatch):
    h = _helpers(script)
    monkeypatch.delenv("AVSH_SESSION_CUTOFF", raising=False)
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-10-07", "2026-10-08"]))
    assert h["cut_to_session"](s, h["session_cutoff"]()).equals(s)


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_fetch_that_can_carry_a_partial_bar_is_cut(script):
    # The cut must be applied where the series is fetched, not left to the caller.
    source = (HERE / script).read_text(encoding="utf-8")
    expected = {"avshunter_vix_engine_v4_1.py": 3, "avshunter_fred_monitor_v2_6.py": 1}[script]
    assert source.count("cut_to_session(") - 1 == expected     # minus the definition
