from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PATH = Path(__file__).with_name("contract_execution_tournament.py")
SPEC = importlib.util.spec_from_file_location("contract_execution_tournament", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample() -> pd.DataFrame:
    return pd.DataFrame([
        {"expression": "E0_RECORDED", "entry_spread": .40, "entry_ask": 1.0, "iv_over_forecast": 1.0, "moneyness_abs": .05, "contract_dte": 30},
        {"expression": "E1_CORE", "entry_spread": .10, "entry_ask": .50, "iv_over_forecast": 1.1, "moneyness_abs": .02, "contract_dte": 35},
    ])


def test_recorded_control_preserves_recorded_contract() -> None:
    assert MODULE.deterministic_choice(sample(), "CEX-0").expression == "E0_RECORDED"


def test_minimum_spread_chooses_current_alternative() -> None:
    assert MODULE.deterministic_choice(sample(), "CEX-1").expression == "E1_CORE"


def test_premium_floor_retains_ticker_as_monitor_when_no_contract() -> None:
    assert MODULE.deterministic_choice(sample(), "CEX-2-2.0") is None


def test_delayed_expression_is_not_used_by_current_deterministic_selector() -> None:
    frame = pd.concat([sample(), pd.DataFrame([{
        "expression": "E4_MATURED_CORE", "entry_spread": .01, "entry_ask": 1.0,
        "iv_over_forecast": 1.0, "moneyness_abs": .01, "contract_dte": 30,
    }])], ignore_index=True)
    assert MODULE.deterministic_choice(frame, "CEX-1").expression == "E1_CORE"


def test_missing_spread_keeps_ticker_in_monitoring_instead_of_crashing() -> None:
    frame = sample().copy()
    frame["entry_spread"] = float("nan")
    assert MODULE.deterministic_choice(frame, "CEX-1") is None


def test_empty_selection_is_reported_as_monitoring_not_failure() -> None:
    result = MODULE.summary(pd.DataFrame(), pd.DataFrame(), 17)
    assert result["monitor_no_contract"] == 17
    assert result["coverage"] == 0.0


def test_training_pool_is_not_restricted_to_evaluation_sessions(monkeypatch) -> None:
    seen_sessions = []

    class FakeModel:
        def fit(self, frame, target):
            seen_sessions.append(len(frame))
            return self

        def predict_proba(self, frame):
            import numpy as np
            return np.tile([0.5, 0.5], (len(frame), 1))

    monkeypatch.setattr(MODULE, "model", lambda kind: FakeModel())
    rows = []
    sessions = ["2026-01-01", "2026-01-05", "2026-01-10", "2026-01-15"]
    for sidx, session in enumerate(sessions):
        for index in range(60):
            rows.append({
                "candidate_id": f"{session}-{index}", "horizon": 1, "session": session,
                "end_session": sessions[min(sidx + 1, 3)], "base_return": .5 if index % 2 else -.5,
                "expression": "E0_RECORDED", "side": "CALL", "activity_agreement": "AGREE",
                **{name: float(index + 1) for name in MODULE.NUMERIC},
            })
    chosen = MODULE.trained_choices(pd.DataFrame(rows), "LOGISTIC", delayed=False)
    assert not chosen.empty
    assert seen_sessions and max(seen_sessions) >= 120
