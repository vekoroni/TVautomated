"""Dossier field-integrity gate (Fix Spec, Data Integrity Remediation, 24 Sep 2026).

Packages the four audit checks used across the 17-run audit (rr_options, ivp_label vs
iv_percentile, call_wall == put_wall, gamma_flip / strike) so they run against every
pipeline run, split by long call and long put, plus the flagged-state consistency check
that Fix 1b introduces (rr_options None <=> rr_options_state non-null).

Pure check functions live here so tests import them; the CLI reads one run's
options_intelligence CSV read-only and prints the per-direction clean rate.

  venv\\Scripts\\python.exe Enhancements\\assessment\\dossier_field_integrity_gate.py RUN_ID [--min-clean 0.95]

Exit code 1 when the clean rate is below --min-clean (default 0.95 per the spec's baseline).
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "data" / "output" / "runs"

IVP_CHEAP_MAX = 0.40
IVP_EXPENSIVE = 0.65
RR_IMPLAUSIBLE_ABOVE = 20.0
GF_RATIO_LOW, GF_RATIO_HIGH = 0.1, 3.0
PRICED_STATES = {"PRICED_TARGET_ABOVE_BREAKEVEN", "PRICED_TARGET_INSIDE_BREAKEVEN", "STRIKE_BEYOND_TARGET"}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _get(row: Mapping[str, Any], name: str) -> Any:
    """Read a field by its dossier name or its opt__ prefixed alias."""
    for key in (name, f"opt__{name}"):
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def direction_of(row: Mapping[str, Any]) -> str:
    for key in ("options_direction", "governed_direction", "canonical_direction", "direction"):
        value = str(row.get(key) or "").upper()
        if value in {"CALL", "PUT"}:
            return value
    return "OTHER"


def rr_bad(row: Mapping[str, Any]) -> bool:
    """Numeric rr_options outside [-1, 20], or a negative rr without the state that explains it."""
    rr = _num(_get(row, "rr_options"))
    if rr is None:
        return False
    if rr < -1.0 or rr > RR_IMPLAUSIBLE_ABOVE:
        return True
    state = _get(row, "rr_options_state")
    if rr < 0 and state is not None and state not in {"PRICED_TARGET_INSIDE_BREAKEVEN", "STRIKE_BEYOND_TARGET"}:
        return True
    return False


def rr_state_inconsistent(row: Mapping[str, Any]) -> bool:
    """Fix 1b flagged-state check: rr None <=> state names why; a priced state carries a number."""
    if "rr_options_state" not in row and "opt__rr_options_state" not in row:
        return False   # pre-fix dossier: the check does not apply
    rr = _num(_get(row, "rr_options"))
    state = _get(row, "rr_options_state")
    if rr is None:
        return state is None or state in PRICED_STATES
    return state not in PRICED_STATES


def ivp_bad(row: Mapping[str, Any]) -> bool:
    ivp = _num(_get(row, "iv_percentile"))
    label = _get(row, "ivp_label")
    if ivp is None or label is None:
        return False
    expected = "CHEAP" if ivp <= IVP_CHEAP_MAX else ("EXPENSIVE" if ivp > IVP_EXPENSIVE else "FAIR")
    return expected != str(label).upper()


def wall_bad(row: Mapping[str, Any]) -> bool:
    cw, pw = _num(_get(row, "call_wall")), _num(_get(row, "put_wall"))
    return cw is not None and pw is not None and cw == pw


def wall_side_bad(row: Mapping[str, Any]) -> bool:
    """Fix 3: a call wall at or below spot, or a put wall at or above spot, is on the wrong side."""
    spot = _num(_get(row, "entry_spot")) or _num(_get(row, "underlying_price")) or _num(_get(row, "spot"))
    if not spot:
        return False
    cw, pw = _num(_get(row, "call_wall")), _num(_get(row, "put_wall"))
    return (cw is not None and cw <= spot) or (pw is not None and pw >= spot)


def gf_bad(row: Mapping[str, Any]) -> bool:
    gf = _num(_get(row, "gamma_flip"))
    strike = _num(_get(row, "strike")) or _num(_get(row, "contract_strike"))
    if gf is None or not strike:
        return False
    ratio = gf / strike
    return ratio < GF_RATIO_LOW or ratio > GF_RATIO_HIGH


CHECKS = {"rr_bad": rr_bad, "rr_state_inconsistent": rr_state_inconsistent,
          "ivp_bad": ivp_bad, "wall_bad": wall_bad, "wall_side_bad": wall_side_bad, "gf_bad": gf_bad}


def audit_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-direction counts and clean rate. A row is clean when no check fires."""
    out: dict[str, Any] = {}
    for direction in ("CALL", "PUT", "OTHER", "ALL"):
        subset = rows if direction == "ALL" else [r for r in rows if direction_of(r) == direction]
        if not subset:
            continue
        counts = Counter()
        clean = 0
        for row in subset:
            fired = [name for name, check in CHECKS.items() if check(row)]
            for name in fired:
                counts[name] += 1
            if not fired:
                clean += 1
        out[direction] = {"rows": len(subset), "clean": clean, "clean_rate": round(clean / len(subset), 4),
                          **{name: counts.get(name, 0) for name in CHECKS}}
    return out


def load_run(run_id: str) -> list[dict[str, Any]]:
    csv.field_size_limit(1 << 30)
    path = RUNS / run_id / "options" / f"options_intelligence_{run_id}.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    min_clean = 0.95
    if "--min-clean" in argv:
        min_clean = float(argv[argv.index("--min-clean") + 1])
        args = [a for a in args if a != argv[argv.index("--min-clean") + 1]]
    run_id = args[0]
    report = {"run_id": run_id, "min_clean": min_clean, "by_direction": audit_rows(load_run(run_id))}
    report["pass"] = report["by_direction"]["ALL"]["clean_rate"] >= min_clean
    print(json.dumps(report, indent=1))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
