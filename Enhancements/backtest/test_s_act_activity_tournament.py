from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).with_name("s_act_activity_tournament.py")
SPEC = importlib.util.spec_from_file_location("s_act_activity_tournament", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_ratio_respects_denominator_floor() -> None:
    assert MODULE.ratio(20.0, 10.0, 10.0) == 2.0
    assert MODULE.ratio(20.0, 9.0, 10.0) is None


def test_pcr_bucket_is_non_directional_vocabulary() -> None:
    assert MODULE.pcr_bucket(0.5) == "CALL_HEAVY"
    assert MODULE.pcr_bucket(0.8) == "BALANCED"
    assert MODULE.pcr_bucket(1.2) == "PUT_HEAVY"
    assert all(term not in MODULE.pcr_bucket(2.0) for term in ("BULL", "BEAR", "BUY", "SELL"))


def test_feature_frame_keeps_oi_and_volume_separate() -> None:
    row = {
        "put_oi": 200.0, "call_oi": 100.0, "put_dw_oi": 80.0, "call_dw_oi": 40.0,
        "put_volume": 10.0, "call_volume": 100.0,
        "expiry_put_oi": 100.0, "expiry_call_oi": 100.0,
        "expiry_put_volume": 20.0, "expiry_call_volume": 20.0,
        "near_put_oi": 100.0, "near_call_oi": 100.0,
        "near_put_volume": 20.0, "near_call_volume": 20.0,
        "delta_put_oi": 100.0, "delta_call_oi": 100.0,
        "delta_put_volume": 20.0, "delta_call_volume": 20.0,
        "prior_put_oi": 100.0, "prior_call_oi": 100.0,
        "prior_put_dw_oi": 50.0, "prior_call_dw_oi": 50.0,
    }
    result = MODULE.feature_frame(pd.DataFrame([row]), floor=1.0).iloc[0]
    assert result.total_oi_pcr == 2.0
    assert result.total_volume_pcr == 0.1
    assert result.activity_agreement == "MIXED"


def test_future_oi_is_not_in_any_model_feature_set() -> None:
    used = {name for columns in MODULE.SCENARIOS.values() for name in columns}
    assert "next_oi_change_selected" not in used


def test_stable_fraction_is_reproducible_and_bounded() -> None:
    first = MODULE.stable_fraction("ABC|1|0.1")
    assert first == MODULE.stable_fraction("ABC|1|0.1")
    assert 0.0 <= first < 1.0


def test_walk_forward_purges_training_outcomes_that_overlap_test_session(monkeypatch) -> None:
    seen = []

    class FakeModel:
        def fit(self, frame, target):
            seen.append(set(frame.index))
            return self

        def predict_proba(self, frame):
            import numpy as np
            return np.tile([0.5, 0.5], (len(frame), 1))

    monkeypatch.setattr(MODULE, "make_model", lambda columns: FakeModel())
    rows = []
    sessions = ["2026-01-01", "2026-01-05", "2026-01-10", "2026-01-15"]
    for session_index, session in enumerate(sessions):
        for row_index in range(50):
            rows.append({
                "candidate_id": f"{session}-{row_index}", "session": session,
                "end_session": sessions[min(session_index + 1, len(sessions) - 1)],
                "base_return": 0.5 if row_index % 2 else -0.5,
                "log_total_oi_pcr": float(row_index),
                "horizon": 1,
            })
    frame = pd.DataFrame(rows)
    scored = MODULE.walk_forward_scores(frame, "S-ACT-1", ("log_total_oi_pcr",))
    assert not scored.empty
    # The first eligible test session is 2026-01-15; only outcomes ending before it can train.
    assert set(scored.held_out_session) == {"2026-01-15"}
    assert seen


def test_monetisation_status_requires_positive_stressed_mean() -> None:
    rows = []
    for session in ("A", "B"):
        for index in range(50):
            rows.append({
                "session": session, "candidate_id": f"{session}-{index}", "horizon": 1,
                "score": float(index) / 50.0, "target": int(index >= 40),
                "base_return": -0.1 if index >= 40 else -0.5,
                "stress_spread_25": -0.2 if index >= 40 else -0.6,
                "stress_spread_50": -0.3 if index >= 40 else -0.7,
                "spy_bull": False, "spy_vol_high": False,
            })
    summary = MODULE.summarise_scores(pd.DataFrame(rows))
    assert summary["status"] != "MONETISATION_CANDIDATE"
