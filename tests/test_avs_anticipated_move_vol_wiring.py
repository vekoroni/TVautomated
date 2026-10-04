"""Anticipated move D-A (ACK 3 Oct 2026): the structural level is capped at the volatility reach.

Found on the first production run (20261003_213716): every estimated row had anticipated_level_basis
STRUCTURAL_REACH_UNKNOWN (846 of 846), and moves reached +175%. Options intelligence computes
target_reachable_vol_annual in its context, but its output row published only target_reachable,
target_reachable_state and target_reach_ratio. The EOD engine therefore always received None, and the cap never ran.
Business rule: the volatility the reach was computed from is published beside the reach, so the anticipated
move can apply the approved cap.
"""
import inspect

import scripts.avshunter_options_intelligence as oi


def test_options_output_publishes_the_reach_volatility():
    src = inspect.getsource(oi.process_ticker)
    for field in ("target_reachable_vol_annual", "target_reachable_sigma_multiple", "target_reachable_hold_sessions"):
        assert f"'{field}'" in src and f"ctx.get('{field}')" in src, field


def test_reach_volatility_is_in_the_context():
    out = oi.reachable_target_fields("CALL", 10.0, 12.0, 0.03, hold_sessions=20)
    assert out["target_reachable_vol_annual"] and out["target_reachable_vol_annual"] > 0
