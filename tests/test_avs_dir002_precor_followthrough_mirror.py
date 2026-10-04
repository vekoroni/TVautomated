"""DIR-002 DSC-24: Phase-C follow-through has equal bullish/bearish treatment."""

import pandas as pd

from wyckoff_crabel_precor_logic_v2 import WyckoffCrabelStateMachine


def _bars(step: int) -> pd.DataFrame:
    return pd.DataFrame({
        "high": [102.0] * 45,
        "low": [98.0] * 45,
        "close": [100.0] * 45,
        "dir": [0] * 40 + [step] * 5,
    })


def test_phase_c_followthrough_confidence_is_mirrored() -> None:
    engine = WyckoffCrabelStateMachine()
    bull = engine._infer_transition(_bars(1), "C", "ACCUMULATION", None, "BUYERS")
    bear = engine._infer_transition(_bars(-1), "C", "DISTRIBUTION", None, "SELLERS")
    assert bull[:2] == bear[:2] == ("D", 78.0)


def test_opposing_control_does_not_get_confirmed_followthrough() -> None:
    engine = WyckoffCrabelStateMachine()
    direction, confidence, _ = engine._infer_transition(
        _bars(1), "C", "DISTRIBUTION", None, "SELLERS"
    )
    assert (direction, confidence) == ("D", 70.0)
