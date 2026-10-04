"""Step 4e (ACK 3 Oct 2026): the Morning runway measures progress toward the anticipated level.

Business rules: the anticipated level (evidence-based, step 2) is the runway target when present, basis
ANTICIPATED_LEVEL; without it the D01 chain applies (structural target, else the volatility-reachable target),
and no target is invented.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import morning_gate
from test_avs_d11_morning_confirmation import LIVE, _row


def _run(**over):
    return morning_gate._morning_liquidity_lifecycle(_row(**over), dict(LIVE), contract_changed=False,
                                                     economics_recompute_complete=False)


def test_runway_is_measured_to_the_anticipated_level():
    out = _run(anticipated_level=104.0)
    assert out["runway_target_basis"] == "ANTICIPATED_LEVEL"
    assert out["thesis_move_total"] == 4.0                       # 104 - 100, not the 110 structural target


def test_without_an_anticipated_level_the_d01_chain_applies():
    assert _run()["runway_target_basis"] == "STRUCTURAL"
    assert _run(target_price=None, target_reachable=106.0)["runway_target_basis"] == "REACHABLE"
