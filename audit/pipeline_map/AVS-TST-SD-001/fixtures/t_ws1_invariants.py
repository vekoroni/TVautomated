"""AVS-TST-SD-001 — WS1 fixture suite: lifecycle geometry invariants.

Design AVS-SD-001 v0.2 §3 exit gate requires:
  §3.3 classify_remaining_runway raises on a wrong-sided invalidation
       (symmetric to the existing target-side check)
  §3.4 calculate_dte_requirement domain-asserts remaining_hold_sessions
       in {5, 10, 20}
  §3.5 direction not in {CALL, PUT} -> NOT_EVALUATED_NON_DIRECTIONAL,
       never INVALIDATED
  §3.6 a missing/non-authoritative stop -> MISSING_AUTHORITATIVE_STOP named
       state, never a fabricated entry*0.97 default

These fixtures IMPORT the contract module read-only and call pure functions on
synthetic inputs. They execute no pipeline stage, read no provider, and write
no artefact. Full three-direction matrix: CALL, PUT, OTHER.

Usage: python t_ws1_invariants.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import contracts.options_liquidity_lifecycle as olc  # noqa: E402  read-only

OUT = Path(__file__).resolve().parent.parent
rows: list[dict] = []


def emit(tid, direction, expected, actual, verdict, note=""):
    rows.append({"test_id": tid, "workstream": "WS1", "level": "fixture",
                 "direction_variant": direction, "expected": expected,
                 "actual": actual, "verdict": verdict, "evidence": note})


def raises(fn, *a, **kw):
    """Return (raised: bool, detail)."""
    try:
        r = fn(*a, **kw)
        return False, repr(r)[:120]
    except Exception as e:
        return True, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------------
# §3.3 — wrong-sided invalidation must raise. Geometry per prior §7.12:
#   CALL: target > entry, invalidation < entry
#   PUT : target < entry, invalidation > entry
# A wrong-sided stop is: CALL with invalidation ABOVE entry; PUT with
# invalidation BELOW entry.
# --------------------------------------------------------------------------
def test_invalidation_side_invariant():
    sig = None
    try:
        import inspect
        sig = inspect.signature(olc.classify_remaining_runway)
    except Exception:
        pass
    params = list(sig.parameters) if sig else []

    cases = [
        # direction, thesis_spot, current, target, invalidation, wrong_sided?
        ("CALL", 100.0, 100.0, 110.0, 103.0, True),   # stop ABOVE entry: wrong
        ("PUT",  100.0, 100.0,  90.0,  97.0, True),   # stop BELOW entry: wrong
        ("CALL", 100.0, 100.0, 110.0,  97.0, False),  # correct geometry
        ("PUT",  100.0, 100.0,  90.0, 103.0, False),  # correct geometry
    ]
    for direction, spot, cur, tgt, inval, wrong in cases:
        kw = {}
        for name, val in (("side", direction), ("direction", direction),
                          ("thesis_spot", spot), ("current_spot", cur),
                          ("structural_target", tgt),
                          ("invalidation_spot", inval)):
            if not params or name in params:
                kw[name] = val
        did_raise, detail = raises(olc.classify_remaining_runway, **kw)
        if wrong:
            emit("WS1.fx.invalidation_side_raises", direction,
                 "design §3.3: wrong-sided invalidation raises",
                 f"raised={did_raise} :: {detail}",
                 "PASS" if did_raise else "FAIL",
                 f"invalidation={inval} vs entry={spot}")
        else:
            emit("WS1.fx.correct_geometry_ok", direction,
                 "correctly-sided geometry does not raise",
                 f"raised={did_raise} :: {detail}",
                 "PASS" if not did_raise else "FAIL", "")


# --------------------------------------------------------------------------
# §3.4 — hold domain assertion
# --------------------------------------------------------------------------
def test_dte_domain_assert():
    import inspect
    try:
        sig = inspect.signature(olc.calculate_dte_requirement)
        params = list(sig.parameters)
    except Exception:
        params = []

    def call(hold):
        kw = {}
        for name, val in (("remaining_hold_sessions", float(hold)),
                          ("monitor_sessions", 3.0),
                          ("exit_buffer_sessions", 5.0)):
            if not params or name in params:
                kw[name] = val
        return olc.calculate_dte_requirement(**kw)

    for hold in (5, 10, 20):
        did_raise, detail = raises(call, hold)
        emit("WS1.fx.dte_routed_hold_ok", "n/a",
             f"routed hold {hold} accepted", f"raised={did_raise} :: {detail}",
             "PASS" if not did_raise else "FAIL", "")

    for hold in (7, 15, 0, 100):
        did_raise, detail = raises(call, hold)
        emit("WS1.fx.dte_domain_assert_raises", "n/a",
             f"design §3.4: hold={hold} not in {{5,10,20}} must raise",
             f"raised={did_raise} :: {detail}",
             "PASS" if did_raise else "FAIL",
             "domain assertion absent if not raised")


# --------------------------------------------------------------------------
# §3.5 — non-directional third arm
# --------------------------------------------------------------------------
def test_non_directional_third_arm():
    import inspect
    try:
        params = list(inspect.signature(olc.classify_remaining_runway).parameters)
    except Exception:
        params = []
    for direction in ("STRANGLE", "UNRESOLVED", "", "NONE"):
        kw = {}
        for name, val in (("side", direction), ("direction", direction),
                          ("thesis_spot", 100.0), ("current_spot", 100.0),
                          ("structural_target", 110.0),
                          ("invalidation_spot", 97.0)):
            if not params or name in params:
                kw[name] = val
        did_raise, detail = raises(olc.classify_remaining_runway, **kw)
        got = detail.upper()
        ok = ("NOT_EVALUATED_NON_DIRECTIONAL" in got) or did_raise
        never_inval = "INVALIDATED" not in got or \
                      "NOT_EVALUATED" in got
        emit("WS1.fx.non_directional_named_state", direction or "<blank>",
             "design §3.5: NOT_EVALUATED_NON_DIRECTIONAL, never INVALIDATED",
             f"raised={did_raise} :: {detail}",
             "PASS" if (ok and never_inval) else "FAIL",
             "third arm absent if a directional verdict is returned")


def main() -> None:
    for fn in (test_invalidation_side_invariant, test_dte_domain_assert,
               test_non_directional_third_arm):
        try:
            fn()
        except Exception as e:
            emit(f"{fn.__name__}.ERROR", "n/a", "fixture completes",
                 f"{type(e).__name__}: {e}", "BLOCKED")

    w = max(len(r["test_id"]) for r in rows) + 1
    print("\n=== WS1 fixture suite :: contracts/options_liquidity_lifecycle.py "
          "(read-only import) ===\n")
    for r in rows:
        print(f"  {r['verdict']:<7} {r['test_id']:<{w}} "
              f"[{r['direction_variant']:<11}] {r['actual'][:88]}")
    tally: dict[str, int] = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"\n  TALLY: {tally}")

    p = OUT / "TST_ws1_fixtures.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"  wrote {p.name}")


if __name__ == "__main__":
    main()
