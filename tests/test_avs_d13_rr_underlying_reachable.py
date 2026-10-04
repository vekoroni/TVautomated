"""XLU-D13 completion (ACK 2 Oct 2026): the underlying R:R that scores and gates is measured
to the volatility-reachable target, never to a distant structural level, and never falls
through to a structural R:R when the reachable one is missing.

- Options publishes rr_underlying_reachable = signed move from entry to target_reachable
  divided by the signed risk from entry to the stop; rr_underlying stays as disclosure.
- EOD structural conviction (both scorers) and the SuperBrain R:R gate read it explicitly.
Evidence: eod_candidate_engine.py:1818/1932 and avshunter_superbrain_layer.py:1335 read
`rr_underlying or rr` (structural target), awarding up to 20 points on unreachable levels.
"""
import pytest

from scripts.avshunter_options_intelligence import rr_underlying_reachable


def test_reachable_underlying_rr_is_signed_move_over_risk():
    assert rr_underlying_reachable("PUT", 39.71, 44.6501, 37.20) == pytest.approx((39.71 - 37.20) / (44.6501 - 39.71), abs=1e-4)
    assert rr_underlying_reachable("CALL", 100.0, 95.0, 106.0) == pytest.approx(1.2)


def test_missing_or_wrong_side_inputs_give_none():
    assert rr_underlying_reachable("PUT", 39.71, None, 37.20) is None
    assert rr_underlying_reachable("PUT", 39.71, 44.65, None) is None
    assert rr_underlying_reachable("CALL", 100.0, 105.0, 106.0) is None      # stop on the wrong side
    assert rr_underlying_reachable("STRANGLE", 100.0, 95.0, 106.0) is None


def _conviction_rows():
    base = {"options_score": 0, "sb_conv_score": 0, "composite": 0, "rr": 8.0, "rr_underlying": 8.0}
    return base, {**base, "rr_underlying_reachable": 0.5}


@pytest.mark.parametrize("scorer", ["structural_conviction_score", "_structural_conviction_score_legacy"])
def test_eod_conviction_gives_no_rr_points(scorer):
    # ACK 3 Oct 2026 (step 6/D-C): R:R retired from every score - no ranking information on the holdout replay.
    import eod_candidate_engine as eod
    fn = getattr(eod, scorer)
    structural_only, reachable = _conviction_rows()
    s_struct, _ = fn(structural_only)
    s_reach, _ = fn(reachable)
    s_none, _ = fn({**structural_only, "rr_underlying": 0.0, "rr": 0.0})
    assert s_struct == s_none
    assert s_reach == s_none
    s_good, _ = fn({**structural_only, "rr_underlying_reachable": 2.6})
    assert s_good == s_none


def test_superbrain_rr_gate_reads_the_reachable_underlying_rr():
    from pathlib import Path
    source = Path("scripts/avshunter_superbrain_layer.py").read_text(encoding="utf-8")
    assert "rr_val        = float(_f(signal, 'rr_underlying_reachable') or 0)" in source
