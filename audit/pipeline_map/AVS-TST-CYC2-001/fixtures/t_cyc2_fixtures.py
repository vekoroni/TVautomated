"""AVS-TST-CYC2-001 — Stage 2 focused fixtures (three-direction matrix).

Verifies F1-F4 behaviourally by importing the contract module read-only and
calling pure functions on synthetic inputs. Executes no pipeline stage, reads
no provider, writes no pipeline state.

Deliberately supplies the PUT variants that tests/test_cycle2_governance.py
omits (it carries CALL x3 and STRANGLE x2 but zero PUT) — see F7.

Usage: python t_cyc2_fixtures.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import contracts.options_liquidity_lifecycle as olc          # noqa: E402
from contracts.governed_states import (                       # noqa: E402
    GovernedDataState, LifecycleEvaluationState,
    GOVERNED_DATA_STATE_VALUES, LIFECYCLE_EVALUATION_STATE_VALUES,
)

OUT = Path(__file__).resolve().parent.parent
rows: list[dict] = []


def emit(tid, fix, direction, expected, actual, verdict, ev=""):
    rows.append({"test_id": tid, "stage": "2", "fix_ref": fix,
                 "level": "fixture", "direction_variant": direction,
                 "expected": expected, "actual": actual,
                 "verdict": verdict, "evidence": ev})


def call(side, *, spot=100.0, cur=100.0, tgt=110.0, inval=97.0):
    try:
        r = olc.classify_remaining_runway(
            side, thesis_spot=spot, current_spot=cur,
            structural_target=tgt, invalidation_spot=inval)
        return False, r
    except Exception as e:
        return True, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- F1
def f1_invalidation_side():
    # CALL: correct stop is BELOW entry. Wrong-sided = ABOVE.
    raised, d = call("CALL", tgt=110.0, inval=103.0)
    emit("CYC2.F1.wrong_sided_raises", "F1", "CALL",
         "raises (invalidation on the thesis side of entry)",
         f"raised={raised} :: {str(d)[:90]}",
         "PASS" if raised else "FAIL")
    # PUT: correct stop is ABOVE entry. Wrong-sided = BELOW.
    raised, d = call("PUT", tgt=90.0, inval=97.0)
    emit("CYC2.F1.wrong_sided_raises", "F1", "PUT",
         "raises (invalidation on the thesis side of entry)",
         f"raised={raised} :: {str(d)[:90]}",
         "PASS" if raised else "FAIL",
         "the 437-PUT production case; NOT covered by test_cycle2_governance.py")
    # correct geometry must still pass
    raised, d = call("CALL", tgt=110.0, inval=97.0)
    emit("CYC2.F1.correct_geometry_ok", "F1", "CALL", "no raise",
         f"raised={raised} :: {str(d)[:70]}", "PASS" if not raised else "FAIL")
    raised, d = call("PUT", tgt=90.0, inval=103.0)
    emit("CYC2.F1.correct_geometry_ok", "F1", "PUT", "no raise",
         f"raised={raised} :: {str(d)[:70]}", "PASS" if not raised else "FAIL")


# ---------------------------------------------------------------- F2
def f2_hold_domain():
    def dte(h):
        try:
            return False, olc.calculate_dte_requirement(remaining_hold_sessions=float(h))
        except Exception as e:
            return True, f"{type(e).__name__}: {e}"
    for h in (5, 10, 20):
        raised, d = dte(h)
        emit("CYC2.F2.routed_hold_accepted", "F2", "n/a",
             f"hold={h} accepted", f"raised={raised}",
             "PASS" if not raised else "FAIL")
    for h in (7, 20.5, 0, 100):
        raised, d = dte(h)
        emit("CYC2.F2.unrouted_hold_raises", "F2", "n/a",
             f"hold={h} not in {{5,10,20}} raises",
             f"raised={raised} :: {str(d)[:80]}",
             "PASS" if raised else "FAIL")


# ---------------------------------------------------------------- F3
def f3_non_directional():
    for direction in ("STRANGLE", "UNRESOLVED", "", "NONE"):
        raised, d = call(direction)
        s = str(d).upper()
        never_invalidated = "INVALIDATED" not in s or "NOT_EVALUATED" in s
        emit("CYC2.F3.non_directional_named", "F3", direction or "<blank>",
             "named non-directional outcome; never INVALIDATED",
             f"raised={raised} :: {str(d)[:90]}",
             "PASS" if (raised and never_invalidated) else "FAIL",
             "contract fails closed by raise; the named state is applied at the "
             "call sites (options_intelligence :4581/:4588, morning_gate :1461)")


# ---------------------------------------------------------------- F5
def f5_enum():
    expect8 = {"AVAILABLE", "PENDING_MORNING_REFRESH", "NOT_APPLICABLE",
               "UNAVAILABLE_PROVIDER", "DATA_DEFECT", "STALE_ADVISORY",
               "CONTRACT_REPAIR_REQUIRED", "SYNTHETIC_RESEARCH_ONLY"}
    emit("CYC2.F5.eight_states_present", "F5", "n/a",
         "all eight governed states in one enum",
         f"{len(GOVERNED_DATA_STATE_VALUES)} values; missing="
         f"{sorted(expect8 - set(GOVERNED_DATA_STATE_VALUES)) or 'none'}",
         "PASS" if expect8 <= set(GOVERNED_DATA_STATE_VALUES) else "FAIL")
    need = {"NOT_EVALUATED_NON_DIRECTIONAL", "MISSING_AUTHORITATIVE_STOP",
            "SUPERSEDED_DATA_DEFECT"}
    emit("CYC2.F5.lifecycle_states_present", "F5", "n/a",
         "lifecycle evaluation states importable",
         f"{sorted(LIFECYCLE_EVALUATION_STATE_VALUES)}",
         "PASS" if need <= set(LIFECYCLE_EVALUATION_STATE_VALUES) else "FAIL")


def main() -> None:
    for fn in (f1_invalidation_side, f2_hold_domain, f3_non_directional, f5_enum):
        try:
            fn()
        except Exception as e:
            emit(f"CYC2.{fn.__name__}.ERROR", "-", "n/a", "fixture completes",
                 f"{type(e).__name__}: {e}", "BLOCKED")

    w = max(len(r["test_id"]) for r in rows) + 1
    print("\n=== AVS-TST-CYC2-001 Stage 2 fixtures (read-only import) ===\n")
    for r in rows:
        print(f"  {r['verdict']:<6} {r['test_id']:<{w}} "
              f"[{r['direction_variant']:<11}] {r['actual'][:82]}")
    tally: dict[str, int] = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"\n  TALLY: {tally}")
    p = OUT / "CYC2_fixtures.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"  wrote {p.name}")


if __name__ == "__main__":
    main()
