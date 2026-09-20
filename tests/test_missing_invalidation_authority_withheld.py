"""Item F (AVS-SD-MON-003 Phase 0/1 fix spec, 20 Sep 2026) - regression lock, not a fix.

The fix spec originally proposed making eod_candidate_engine.py withhold candidate/capital
authority when a governed invalidation level is missing, per the handoff-contract audit's own
recommendation on run 20260919_205844 (162 rows, fill_rate 0.1049). Verified against that run's
real output before writing any code: this already happens correctly (_candidate_permission_fields
and the EOD status classifier both withhold authority - capital_permission=NO,
eod_status=EOD_DATA_INSUFFICIENT_REVIEW - whenever a governed-directional row has no invalidation
level). There is no code defect here.

The upstream question - why do rows end up without invalidation at all - has a confirmed answer:
cross-referencing tonight's 162 missing-invalidation rows against thesis_geometry_review_state
(scripts/avshunter_options_intelligence.py) shows 160/162 are DIRECTION_CONTRADICTS_STRUCTURE (the
exact population S-DIR-3 already measured - register, Round 2 findings, 20 Sep) and 2/162 are
MISSING_STOP. thesis_geometry_review() is working as documented: a CALL in Wyckoff DISTRIBUTION or
a PUT in ACCUMULATION has no valid stop because the structural invalidation lies on the wrong side,
and it correctly refuses to fabricate one. This is not a bug - it is the same finding as D1, not a
separate defect, and any further action (e.g. computing a structure-consistent invalidation for the
structure-implied direction) is gated on ACK's D1 decision, not a standalone repair.

This test locks the current, verified-correct behaviour against regression, since it was previously
assumed rather than proven.
"""
from __future__ import annotations

from eod_candidate_engine import _candidate_permission_fields, _invalidation_level


def _row(direction="CALL", invalidation_spot=None, invalidation_state="MISSING_GOVERNED_INVALIDATION",
        entry_spot=100.0):
    return {
        "direction": direction,
        "entry_spot": entry_spot,
        "invalidation_spot": invalidation_spot,
        "invalidation_state": invalidation_state,
    }


def test_missing_invalidation_returns_none_not_zero():
    # Mirrors the real DIRECTION_CONTRADICTS_STRUCTURE case: no stop exists, must stay missing.
    assert _invalidation_level(_row(invalidation_spot=None)) is None


def test_directional_row_without_invalidation_loses_capital_authority():
    row = _row(direction="CALL", invalidation_spot=None, invalidation_state="MISSING_GOVERNED_INVALIDATION")
    result = _candidate_permission_fields(row, eod_status="EOD_DATA_INSUFFICIENT_REVIEW")
    assert result["live_capital_permission"] == "NO"
    assert result["eod_candidate_permission"] == "STRUCTURAL_REVIEW_ONLY"
    assert result["capital_permission"] == "NO"
    assert result["capital_authorization_state"] == "NOT_AUTHORIZED_INVALIDATION_MISSING"
    assert result["eod_candidate_authorized"] is False
    assert result["execution_authorized"] is False


def test_directional_row_with_valid_invalidation_is_not_blocked_by_this_rule():
    # A CALL with a stop below entry (correct side) must not be caught by the missing-invalidation path.
    row = _row(direction="CALL", invalidation_spot=95.0, invalidation_state="AVAILABLE", entry_spot=100.0)
    result = _candidate_permission_fields(row, eod_status="COMPLETE")
    assert result["capital_authorization_state"] != "NOT_AUTHORIZED_INVALIDATION_MISSING"


def test_non_directional_row_is_not_penalised_for_missing_invalidation():
    row = _row(direction="NON_DIRECTIONAL", invalidation_spot=None, invalidation_state="MISSING_GOVERNED_INVALIDATION")
    result = _candidate_permission_fields(row, eod_status="COMPLETE")
    # Non-directional theses have no invalidation requirement in the first place.
    assert result["capital_authorization_state"] != "NOT_AUTHORIZED_INVALIDATION_MISSING"
