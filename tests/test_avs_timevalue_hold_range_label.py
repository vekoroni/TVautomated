"""Time-value check labels holds beyond its tested range (ACK 5 Oct 2026, change 5; open item O8).

Its volatility budget is tested for holds of 1-20 sessions. Since step 3 the hold is the evidence runway, often
longer (run 20261005_072245: 4 of the 12 handoff rows), and such rows were reported PLANNED_HOLD_SESSIONS_INVALID -
a label claiming bad data where the hold is valid and only beyond the check's range.
Business rules:
- A valid hold beyond 20 sessions is NOT_EVALUATED with reason PLANNED_HOLD_BEYOND_TESTED_RANGE_20.
- A non-integer hold is still PLANNED_HOLD_SESSIONS_INVALID.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_avs_fix_001_w34_timevalue_monetisability import evaluate   # existing complete fixture


def _reason(hold):
    return evaluate(direction="CALL", target=110.0, ask=0.85, strike=100.0, iv=0.30, dte=60,
                    hold=hold)[1]["monetisability_timevalue_reason"]


def test_a_long_evidence_hold_is_labelled_beyond_range_not_invalid():
    assert _reason(27) == "PLANNED_HOLD_BEYOND_TESTED_RANGE_20"


def test_a_fractional_hold_is_still_invalid():
    assert _reason(12.5) == "PLANNED_HOLD_SESSIONS_INVALID"
