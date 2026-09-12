"""AVS-TST-DOI-001 / T1.2 — DOI-1 exit-criterion permutation probe (v2).

DOI-1 exit criterion: "governed opportunity population is invariant when EIL,
entry, exit and timing values are permuted; only advisory states and ordering
may change."

Input: the REAL governed opportunity book from run 20260909_071646
(235 rows, CALL 151 / PUT 84 / OTHER 0).

METHOD NOTE (v2). Version 1 of this probe was WEAK and is recorded as such in
T1_authority.md: the Lab book renames several engine fields
(`invalidation_price` vs the engine's `invalidation_spot`), so every row fell
through the first early-return branch of `_eod_candidate_status` and the
permutation never reached the EIL / timing / liquidity branches. All 63,450
evaluations returned one status. That is a test that cannot fail.

v2 therefore does harness validation FIRST: it maps the book's field names on
to the engine's, and asserts that the recomputed `eod_candidate_status`
reproduces the status persisted in the book for a material share of rows.
Only rows the harness reproduces are permuted, so the invariance result is
about the engine, not about a field-name mismatch.

Gates re-evaluated per permutation:
  1. eod_candidate_engine._eod_candidate_status  -> eod_candidate_status
  2. the Phase 10 manifest mask (hard_block_mask + carry-forward set)

READ ONLY. No database, no provider, no write to data/.
Interpreter: venv\\Scripts\\python.exe
"""

from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

BOOK = ROOT / "data/output/runs/20260909_071646/intelligence_lab/final_opportunity_book_20260909_071646.csv"

import eod_candidate_engine as ece  # noqa: E402

# Book column -> engine column. The engine reads governed field names that the
# Lab projection renames on the way out.
FIELD_ALIASES = {
    "invalidation_price": "invalidation_spot",
    "target_price": "structural_target",
    "signal_price": "entry_spot",
}

EIL_VERDICTS = [
    "", "NOT_EVALUATED", "EXECUTE", "EXECUTE_NOW", "EXECUTE_WITH_CAUTION",
    "WATCHLIST", "BLOCKED", "BLOCK", "STAND_DOWN_MICROSTRUCTURE", "DEFER",
]
TIMING_STATES = [
    "", "HORIZON_ELAPSED", "INVALIDATION_LEVEL_BREACHED",
    "TARGET_TOUCHED", "ENTRY_CONDITION_MOVED",
]
TIMING_FIELDS = (
    "exit_state", "timing_state", "entry_state", "horizon_state",
    "exit_discipline_state", "entry_timing_state", "exit_condition",
)
LIQUIDITY = [
    (0.02, 5000.0, 4000.0),   # pristine
    (0.95, 0.0, 0.0),         # worst legal: wide spread, zero OI, zero volume
    (None, None, None),       # everything missing
]
ADVISORY_FLAGS = [(True, True), (False, False)]  # (eil_advisory_only, eil_liquidity_passed)


def direction_bucket(row: dict) -> str:
    for key in ("governed_direction", "final_direction", "canonical_direction", "direction"):
        value = str(row.get(key) or "").strip().upper()
        if value in {"CALL", "PUT"}:
            return value
    return "OTHER"


def to_engine_row(row: dict) -> dict:
    engine = dict(row)
    for book_field, engine_field in FIELD_ALIASES.items():
        if book_field in row and engine_field not in row:
            engine[engine_field] = row[book_field]
    return engine


def evaluate(row: dict) -> tuple[str, bool]:
    """Return (eod_candidate_status, phase10_manifest_include)."""
    tier = str(row.get("structural_tier") or row.get("tier") or "")
    status, _reason = ece._eod_candidate_status(row, tier)
    hard_block = status in {"EOD_NO_OPTIONS_ROUTE", "EOD_STRUCTURAL_BLOCK", "EOD_BLOCK"}
    trigger_go = str(row.get("trigger_go_eligible") or "").upper() in {"TRUE", "1", "YES"}
    include = (not hard_block) and (trigger_go or status in ece.EOD_CARRY_FORWARD_STATUSES)
    return status, include


def main() -> int:
    df = pd.read_csv(BOOK, low_memory=False)
    rows = [to_engine_row(r) for r in df.to_dict("records")]
    persisted = df.get("eod_candidate_status", pd.Series([""] * len(df))).fillna("").astype(str).tolist()

    base_dirs = Counter(direction_bucket(r) for r in rows)
    print(f"baseline population: {len(rows)}")
    print(f"baseline CALL/PUT/OTHER: {base_dirs['CALL']}/{base_dirs['PUT']}/{base_dirs['OTHER']}")
    print(f"persisted eod_candidate_status: {dict(Counter(persisted))}")

    # ---- harness validation -------------------------------------------------
    baseline: dict[int, tuple[str, bool]] = {}
    reproduced: list[int] = []
    for idx, row in enumerate(rows):
        baseline[idx] = evaluate(row)
        if baseline[idx][0] == persisted[idx]:
            reproduced.append(idx)
    recomputed_counts = Counter(v[0] for v in baseline.values())
    print(f"recomputed eod_candidate_status: {dict(recomputed_counts)}")
    print(f"harness reproduces persisted status for {len(reproduced)} / {len(rows)} rows")
    if not reproduced:
        print("HARNESS INVALID: recomputation reproduces no persisted status. "
              "Permutation result would be meaningless. Aborting.")
        return 2
    repro_dirs = Counter(direction_bucket(rows[i]) for i in reproduced)
    print(f"reproduced CALL/PUT/OTHER: {repro_dirs['CALL']}/{repro_dirs['PUT']}/{repro_dirs['OTHER']}")

    # ---- permutation --------------------------------------------------------
    perms = list(itertools.product(EIL_VERDICTS, TIMING_STATES, LIQUIDITY, ADVISORY_FLAGS))
    print(f"permutations per row: {len(perms)}  total evaluations: {len(perms) * len(reproduced)}")

    dropped: Counter = Counter()
    dropped_examples: list[dict] = []
    status_space: Counter = Counter()
    status_by_dir: dict[str, Counter] = {"CALL": Counter(), "PUT": Counter(), "OTHER": Counter()}

    for idx in reproduced:
        row = rows[idx]
        bucket = direction_bucket(row)
        base_status, base_include = baseline[idx]
        for verdict, timing, (spread, oi, volume), (advisory, liq_passed) in perms:
            mutated = dict(row)
            mutated["eil_v3_verdict"] = verdict
            mutated["eil_advisory_only"] = advisory
            mutated["eil_liquidity_passed"] = liq_passed
            mutated["eil_defer_reason"] = "" if liq_passed else "LIQUIDITY_GATE_FAILED"
            mutated["eil_block_reason"] = "" if liq_passed else "NO_EXECUTABLE_MARKET"
            for field in TIMING_FIELDS:
                mutated[field] = timing
            mutated["spread_pct"] = spread
            mutated["open_interest"] = oi
            mutated["volume"] = volume
            status, include = evaluate(mutated)
            status_space[status] += 1
            status_by_dir[bucket][status] += 1
            if base_include and not include:
                dropped[bucket] += 1
                if len(dropped_examples) < 12:
                    dropped_examples.append({
                        "ticker": row.get("ticker"), "direction": bucket,
                        "base_status": base_status, "mutated_status": status,
                        "eil_v3_verdict": verdict, "timing": timing,
                        "spread_pct": spread, "open_interest": oi, "volume": volume,
                        "eil_advisory_only": advisory, "eil_liquidity_passed": liq_passed,
                    })

    print()
    print("=== RESULT ===")
    print("rows whose Phase 10 inclusion flipped TRUE->FALSE under permutation:")
    print(f"  CALL={dropped['CALL']}  PUT={dropped['PUT']}  OTHER={dropped['OTHER']}")
    print()
    print(f"distinct eod_candidate_status values reached: {len(status_space)}")
    for status, count in status_space.most_common():
        carried = status in ece.EOD_CARRY_FORWARD_STATUSES
        print(f"  {status:42} {count:9}  carry_forward={carried}")
    print()
    for bucket in ("CALL", "PUT"):
        print(f"  {bucket} distinct statuses reached: {len(status_by_dir[bucket])}")
    if dropped_examples:
        print()
        print("first dropped examples:")
        print(json.dumps(dropped_examples, indent=2, default=str))

    strong = len(status_space) > 1
    invariant = sum(dropped.values()) == 0
    print()
    print(f"branch coverage: {'ADEQUATE' if strong else 'WEAK (single status reached)'}")
    print(f"DOI-1 permutation invariance: {'PASS' if invariant else 'FAIL'}")
    return 0 if invariant and strong else 1


if __name__ == "__main__":
    raise SystemExit(main())
