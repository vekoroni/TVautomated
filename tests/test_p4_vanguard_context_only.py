"""Phase 4: Vanguard adds context and never changes the thesis (design §8, D-A revised).

Business rules:
- Vanguard publishes contradiction flags against the THESIS's side as display context only:
  HISTORY_AGAINST_THESIS_SIDE (side evidence unfavourable at the configured horizon), THIN_HISTORY,
  SIDE_EVIDENCE_NOT_EVALUATED; with authority CONTEXT_ONLY (no gate, rank, scope or trade-ready label).
- No thesis side -> no side flag (Vanguard never picks a side).
- Vanguard's output never writes a thesis field (side, direction, trigger, target, invalidation).
"""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import vanguard.main as vm

ROOT = Path(__file__).resolve().parents[1]


def _blocks(p20, mean20, status="EVALUATED", n=120):
    return {"side_block_status": status, "side_block_sample_size": n,
            "side_bull__p_close_favourable_20d": p20, "side_bull__signed_mean_return_close_20d": mean20,
            "side_bear__p_close_favourable_20d": 1 - p20, "side_bear__signed_mean_return_close_20d": -mean20}


def _fields(blocks, side):
    outcomes = NS(side_evidence_blocks=blocks)
    vi = NS(thesis_context=NS(side=side))
    return vm._side_block_fields(outcomes, vi)


def test_history_against_the_thesis_side_is_flagged_as_context():
    f = _fields(_blocks(0.40, -0.01), "BULL")
    assert "HISTORY_AGAINST_THESIS_SIDE" in f["vanguard_context_flags"]
    assert f["vanguard_context_authority"] == "CONTEXT_ONLY"


def test_supportive_history_raises_no_flag():
    f = _fields(_blocks(0.60, 0.02), "BULL")
    assert "HISTORY_AGAINST_THESIS_SIDE" not in f["vanguard_context_flags"]


def test_thin_and_unevaluated_history_are_flagged():
    assert "THIN_HISTORY" in _fields(_blocks(0.5, 0.0, status="NOT_EVALUATED", n=12) | {"side_block_reason": "THIN_SAMPLE"},
                                     "BEAR")["vanguard_context_flags"]
    assert "SIDE_EVIDENCE_NOT_EVALUATED" in _fields({"side_block_status": "NOT_EVALUATED",
                                                     "side_block_reason": "NO_MATCH"}, "BULL")["vanguard_context_flags"]


def test_no_thesis_side_gives_no_side_flag():
    f = _fields(_blocks(0.40, -0.01), None)
    assert "HISTORY_AGAINST_THESIS_SIDE" not in f["vanguard_context_flags"]


def test_vanguard_never_writes_a_thesis_field():
    forbidden = {"thesis__side", "direction", "final_direction", "trigger_price", "structural_target",
                 "target_price", "invalidation_spot", "governed_invalidation_spot", "thesis_trigger_level"}
    tree = ast.parse((ROOT / "vanguard/main.py").read_text(encoding="utf-8-sig"))
    written = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            written |= {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and isinstance(n.slice, ast.Constant):
            written.add(n.slice.value)
    assert written & forbidden == set()
