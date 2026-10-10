"""G3-01 (verification of run 20261008_220129; ACK 9 Oct 2026: fix before the Morning).

Business rule: a row with no selected contract keeps its ticker's duration evidence. The lifecycle fields take the
evidence runway, move time and basis from the selected contract when there is one, and otherwise from the ticker
context, never from an empty contract. No hold is invented: a ticker without evidence stays without it.

Live run: seven no-contract review rows (FBP, BWMN, SFL, CBZ, EFC, ITGR, TECH) had replay evidence of 13-399 sessions,
but the lifecycle copied the empty contract and they read NO_EVIDENCE_HOLD, so later alternatives were rejected on a
misleading horizon.
"""
import scripts.avshunter_options_intelligence as oi

CTX = {"ticker": "FBP", "direction": "CALL", "spot": 20.0, "evidence_runway_sessions": 399,
       "evidence_move_sessions": 210, "evidence_runway_basis": "IN_SAMPLE_REPLAY_NOT_VALIDATED:Q80"}


def test_a_row_without_a_contract_keeps_the_tickers_evidence():
    out = oi._options_liquidity_lifecycle_fields(CTX, {}, {})
    assert out["evidence_runway_sessions"] == 399
    assert out["evidence_move_sessions"] == 210
    assert out["evidence_runway_basis"] == "IN_SAMPLE_REPLAY_NOT_VALIDATED:Q80"


def test_a_selected_contracts_own_values_still_win():
    contract = {"evidence_runway_sessions": 20, "evidence_move_sessions": 10, "evidence_runway_basis": "C"}
    out = oi._options_liquidity_lifecycle_fields(CTX, contract, {})
    assert (out["evidence_runway_sessions"], out["evidence_runway_basis"]) == (20, "C")


def test_no_evidence_is_not_invented():
    out = oi._options_liquidity_lifecycle_fields({"ticker": "X", "direction": "CALL", "spot": 5.0}, {}, {})
    assert out["evidence_runway_sessions"] is None and out["evidence_runway_basis"] is None
