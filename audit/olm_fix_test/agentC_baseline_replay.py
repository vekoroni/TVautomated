"""Agent C - SS11.1 frozen-baseline differential replay.

READ-ONLY. Loads the pre-change execution_gate.py / contracts/lab_control.py
from backups/olm_blocker_remediation_prechange_20260829_2035/ via importlib
(so shared unmodified dependencies such as contracts.direction_governance
still resolve to the current, real modules) and replays the same source rows
through both the BEFORE and AFTER execution_gate() to diff every business
field. Does not modify any production file; writes only under
audit/olm_fix_test/.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

BACKUP_DIR = REPO_ROOT / "backups" / "olm_blocker_remediation_prechange_20260829_2035"
RUN_ID = "20260828_094349"
SOURCE_CSV = (
    REPO_ROOT / "data" / "output" / "runs" / RUN_ID / "morning_validation"
    / f"morning_validated_trades_{RUN_ID}.csv"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    backup_execution_gate = _load_module(
        "backup_execution_gate", BACKUP_DIR / "execution_gate.py"
    )
    import execution_gate as current_execution_gate

    with SOURCE_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = [dict(r) for r in csv.DictReader(fh)]
    print(f"Loaded {len(rows)} source rows from {SOURCE_CSV}")

    # Confirm the stated limitation before proceeding: does this frozen
    # baseline carry any OLM lifecycle-contract fields at all?
    contract_fields = (
        "lifecycle_contract_version", "thesis_state", "liquidity_state",
        "morning_transition_state", "remaining_runway_state", "executable_now",
    )
    has_any = 0
    for r in rows:
        if any(str(r.get(f) or "").strip() for f in contract_fields if f in r):
            has_any += 1
    print(f"Rows carrying ANY OLM lifecycle-contract field: {has_any}/{len(rows)}")
    present_cols = [f for f in contract_fields if f in (rows[0].keys() if rows else [])]
    print(f"OLM lifecycle-contract columns present in this CSV at all: {present_cols}")

    before_rows = [backup_execution_gate.execution_gate(dict(r)) for r in rows]
    after_rows_prod = [current_execution_gate.execution_gate(dict(r), require_olm=True) for r in rows]
    after_rows_compat = [current_execution_gate.execution_gate(dict(r), require_olm=False) for r in rows]

    def action_counts(gated):
        from collections import Counter
        return dict(Counter(g.get("final_action", "MISSING") for g in gated))

    print("BEFORE (pre-change execution_gate, GATE_VERSION="
          f"{backup_execution_gate.GATE_VERSION}) final_action counts:",
          action_counts(before_rows))
    print("AFTER, require_olm=True (production run_execution_gate path, "
          f"GATE_VERSION={current_execution_gate.GATE_VERSION}) final_action counts:",
          action_counts(after_rows_prod))
    print("AFTER, require_olm=False (direct-call compatibility mode, "
          f"GATE_VERSION={current_execution_gate.GATE_VERSION}) final_action counts:",
          action_counts(after_rows_compat))

    # Exclude fields that are explicitly allowed to change per design SS11.1:
    # gate version/reason/telemetry, OLM guard lineage, and volatile timestamps.
    ALLOWED_CHANGE_FIELDS = {
        "final_action", "gate_reason", "gate_version", "gate_timestamp_utc",
        "gate_warnings", "gate_size_penalty", "gate_conviction_override",
        "preservation_gate",
        "olm_guard_version", "olm_guard_disposition", "olm_guard_reason",
        "olm_guard_pass", "olm_guard_state_consistent",
        "check_direction_integrity_pass", "check_direction_integrity_reason",
        "direction_integrity_status",
    }

    def diff_row(before, after, ticker_label):
        all_keys = set(before.keys()) | set(after.keys())
        diffs = []
        for k in sorted(all_keys):
            if k in ALLOWED_CHANGE_FIELDS:
                continue
            bv = before.get(k, "<MISSING>")
            av = after.get(k, "<MISSING>")
            if str(bv) != str(av):
                diffs.append((k, bv, av))
        return diffs

    unexpected_diffs = {}
    for idx, (b, a) in enumerate(zip(before_rows, after_rows_prod)):
        ticker = rows[idx].get("ticker", f"ROW{idx}")
        d = diff_row(b, a, ticker)
        if d:
            unexpected_diffs[ticker] = d

    action_flip_summary = {}
    for idx, (b, a) in enumerate(zip(before_rows, after_rows_prod)):
        ticker = rows[idx].get("ticker", f"ROW{idx}")
        ba, aa = b.get("final_action"), a.get("final_action")
        if ba != aa:
            action_flip_summary.setdefault((ba, aa), []).append(ticker)

    print(f"\nTotal rows with final_action flip (before -> after, require_olm=True): "
          f"{sum(len(v) for v in action_flip_summary.values())}")
    for (ba, aa), tickers in sorted(action_flip_summary.items(), key=lambda kv: -len(kv[1])):
        sample = tickers[:5]
        print(f"  {ba} -> {aa}: {len(tickers)} rows (sample: {sample})")

    print(f"\nRows with a NON-allowed-category business-field difference: {len(unexpected_diffs)}")
    shown = 0
    for ticker, diffs in unexpected_diffs.items():
        if shown >= 15:
            print(f"  ... ({len(unexpected_diffs) - shown} more rows with diffs not shown)")
            break
        print(f"  {ticker}: {diffs[:5]}{' ...' if len(diffs) > 5 else ''}")
        shown += 1

    out = {
        "run_id": RUN_ID,
        "source_rows": len(rows),
        "rows_with_any_olm_field": has_any,
        "olm_columns_present_in_csv": present_cols,
        "before_action_counts": action_counts(before_rows),
        "after_prod_action_counts": action_counts(after_rows_prod),
        "after_compat_action_counts": action_counts(after_rows_compat),
        "action_flip_summary": {
            f"{ba}->{aa}": len(tickers) for (ba, aa), tickers in action_flip_summary.items()
        },
        "rows_with_unexpected_business_field_diff": len(unexpected_diffs),
        "unexpected_diff_sample": {
            k: v for k, v in list(unexpected_diffs.items())[:25]
        },
    }
    out_path = REPO_ROOT / "audit" / "olm_fix_test" / "agentC_baseline_replay_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
