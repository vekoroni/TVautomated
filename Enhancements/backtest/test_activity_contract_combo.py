from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PATH = Path(__file__).with_name("activity_contract_combo.py")
SPEC = importlib.util.spec_from_file_location("activity_contract_combo", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_priority_band_is_session_local() -> None:
    frame = pd.DataFrame([
        {"session": session, "candidate_id": f"{session}-{index}", "score": index / 10}
        for session in ("A", "B") for index in range(10)
    ])
    selected = MODULE.priority_band(frame, 0.20)
    assert selected.groupby("session").size().to_dict() == {"A": 2, "B": 2}


def test_priority_band_does_not_mutate_source() -> None:
    frame = pd.DataFrame([{"session": "A", "candidate_id": str(i), "score": i} for i in range(10)])
    before = frame.copy(deep=True)
    MODULE.priority_band(frame, .10)
    pd.testing.assert_frame_equal(frame, before)
