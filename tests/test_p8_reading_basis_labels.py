"""Step 2 of the behavioural-stage design (ACK approved 12 Oct 2026): every claim in the reading says how it is known.

Business rules (generic, any ticker and timeframe; from ACK's Soul of the Chart teaching format):
- OBSERVED: read directly from completed bars - recorded structure and levels, compression measures, an event whose
  response the later bars settled (activated / confirmed / failed / outcome level reached).
- INFERRED: an interpretation of observed bars - who controls the campaign, the phase, a transition, an event
  candidate whose response is not yet decisive.
- UNRESOLVED: not decidable from the bars yet - two-sided or shifting control, a low-confidence phase, a monitored
  contraction without a direction, and always the right edge (the last bar's outcome).
- A timeframe whose bars are stale, incomplete or disagree with the daily bar cannot carry OBSERVED: its claims are
  capped at INFERRED and the cap names the reason.
"""
from __future__ import annotations

from domain.structure_behaviour.basis import INFERRED, OBSERVED, UNRESOLVED, label_reading


def _reading(**kw):
    base = {"Status": "EVALUATED", "As_Of": "2026-10-09", "Controller": "SELLERS", "Phase_Confidence": "MEDIUM",
            "Wyckoff_Phase": "E", "Phase_Transition": "STABLE", "Compression_State": "CONTRACTING",
            "candidates": [{"Signal_State": "ACTIVATED"}, {"Signal_State": "DETECTED"}, {"Signal_State": "MONITOR"},
                           {"Signal_State": "FAILED"}, {"Signal_State": "OUTCOME_REACHED"}]}
    base.update(kw)
    return base


def test_claims_carry_how_they_are_known():
    r = label_reading(_reading())
    assert (r["Controller_Basis"], r["Phase_Basis"], r["Transition_Basis"], r["Compression_Basis"]) == \
        (INFERRED, INFERRED, INFERRED, OBSERVED)
    assert r["Right_Edge_Basis"] == UNRESOLVED and r["Basis_As_Of"] == "2026-10-09" and r["Basis_Cap"] == ""
    assert [c["Event_Basis"] for c in r["candidates"]] == [OBSERVED, INFERRED, UNRESOLVED, OBSERVED, OBSERVED]
    assert all(c["Levels_Basis"] == OBSERVED for c in r["candidates"])


def test_undecided_control_and_low_confidence_phase_are_unresolved():
    for controller in ("TWO-SIDED", "CONTROL SHIFTING"):
        assert label_reading(_reading(Controller=controller))["Controller_Basis"] == UNRESOLVED
    assert label_reading(_reading(Phase_Confidence="LOW"))["Phase_Basis"] == UNRESOLVED
    assert label_reading(_reading(Compression_State="NONE"))["Compression_Basis"] == OBSERVED   # no contraction, measured


def test_imperfect_bars_cap_every_observed_claim_at_inferred():
    r = label_reading(_reading(Data_Status="STALE_INTRADAY"))
    assert r["Compression_Basis"] == INFERRED and r["Basis_Cap"] == "STALE_INTRADAY"
    assert [c["Event_Basis"] for c in r["candidates"]][:2] == [INFERRED, INFERRED]
    assert all(c["Levels_Basis"] == INFERRED for c in r["candidates"])
    assert r["Controller_Basis"] == INFERRED and r["Right_Edge_Basis"] == UNRESOLVED


def test_a_timeframe_not_evaluated_says_so():
    r = label_reading({"Status": "NOT_EVALUATED_INSUFFICIENT_BARS", "Controller": "NOT_EVALUATED", "candidates": []})
    assert r["Controller_Basis"] == r["Phase_Basis"] == "NOT_EVALUATED"


def test_the_engine_labels_every_timeframe_and_discovery_publishes_the_labels():
    import inspect
    import avshunter_discovery_ULTIMATE as disc
    from domain.structure_behaviour import engine
    assert "label_reading(" in inspect.getsource(engine.analyse_ticker)
    src = inspect.getsource(disc._beh001_summary_fields)
    for f in ("_controller_basis", "_phase_basis", "_compression_basis", "_basis_cap"):
        assert f in src
