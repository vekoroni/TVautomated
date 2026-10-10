"""G2-06 (verification of run 20261008_220129; ACK 9 Oct 2026: fix before the Morning).

Business rule: the governing setup - the one that supplies the trigger, target and invalidation of the ticker's thesis
- must be a thesis the thesis step ADOPTED on the ticker's side. A REFUSED candidate (its levels are on the wrong side:
the move happened or its invalidation was crossed) never governs.

Live run: BRO, FA and ISRG had their side set by an adopted thesis, but select_governing ran before the thesis
decisions and picked a refused candidate; the handoff then had no governed invalidation (INCOMPLETE_GEOMETRY) and the
Lab blocked them (INVALIDATION_MISSING).
"""
from pathlib import Path

from domain.structure_behaviour.trade_lane import select_governing

ROOT = Path(__file__).resolve().parents[1]
PX = 100.0


def cand(tf, kind, state, direction, outcome, invalidation, n=100):
    return {"Timeframe": tf, "Signal_Type": kind, "Signal_State": state, "Direction": direction,
            "Outcome_Level": outcome, "Invalidation_Level": invalidation, "Age_Bars": 5,
            "Candidate_ID": f"T|{tf}|CAMPAIGN|{kind}|2026-09-01", "Duration_Level_N": n,
            "Duration_Level_Q50_Bars": 2, "Duration_Level_Q80_Bars": 4,
            "Duration_Level_Status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "Outcome_Definition": "measured move",
            "Structure_Scope": "CAMPAIGN"}


# A refused daily candidate whose invalidation (99) is already crossed (price 100, BEAR), which would otherwise rank
# first (ACTIVATED, daily), and the adopted weekly thesis that set the side.
REFUSED_1D = cand("1d", "Hinge / Apex Expansion", "ACTIVATED", "BEAR", 90.0, 99.0)
ADOPTED_1W = cand("1w", "SOW -> LPSY continuation", "DETECTED", "BEAR", 85.0, 120.0)


def test_only_an_adopted_thesis_can_govern():
    _, governing = select_governing([REFUSED_1D, ADOPTED_1W], price=PX, atr_daily=2.0, side="BEAR",
                                    adopted_ids={ADOPTED_1W["Candidate_ID"]})
    assert governing is not None and governing["Candidate_ID"] == ADOPTED_1W["Candidate_ID"]


def test_no_adopted_thesis_on_the_side_means_no_governing_setup():
    fields, governing = select_governing([REFUSED_1D], price=PX, atr_daily=2.0, side="BEAR", adopted_ids=set())
    assert governing is None and fields["trade_lane"] == "C"


def test_callers_without_thesis_decisions_keep_todays_behaviour():
    _, governing = select_governing([REFUSED_1D, ADOPTED_1W], price=PX, atr_daily=2.0, side="BEAR")
    assert governing is not None                      # adopted_ids=None: no thesis filter (legacy callers)


def test_discovery_passes_the_adopted_theses():
    src = (ROOT / "avshunter_discovery_ULTIMATE.py").read_text(encoding="utf-8-sig")
    call = src.split("_lane_fields, _governing = select_governing(", 1)[1].split(")\n", 1)[0]
    assert "adopted_ids=" in call
