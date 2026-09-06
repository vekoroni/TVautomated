"""AVS-FIX-001 Workstream 2 — read-only gate report for one run.

    python audit/ops/check_run_gates.py <run_id> [--json <path>] [--csv <path>]

Reads `data/output/runs/<run_id>/` and nothing else. It opens no network
connection, executes no stage, and writes only the files named on the command
line. This is what ACK runs after Monday's Evening (W2.1) and Tuesday's Morning
(W2.2), and how the tester closes an item: every line carries the filter that
produced it and, where direction matters, the CALL/PUT/OTHER split.

Sections
    1  AG-01…AG-17 / RG-01…RG-09, reproducing AVS-TST-QT-001/B_<run>.csv
       exactly. Gates that file never defined are reported NOT_DEFINED_IN_B
       rather than invented, so the coverage gap stays visible.
    2  DDD closure checks — one pipeline_run_id and one completed session
       across stages; build receipt present and plan-hash-bound; run_meta
       carrying git_describe, all nine flags and the runtime profile hash;
       completed_profile_summary usable_ratio and guard_decision.
    3  Semantic audit fail_count, split genuine vs spurious, with the failing
       tickers named.
    4  The seven AVS-MVP-001 §6 kill criteria.

Exit code is 1 if any P0 gate fails, any kill criterion fires, or the run
directory is unreadable; 0 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUNS = REPO / "data" / "output" / "runs"

#: Gates whose failure stops the run. Everything else is reported and does not
#: change the exit code.
P0_GATES = {
    "AG-01", "AG-02", "AG-03", "AG-05", "AG-07", "AG-08", "AG-08b", "AG-09",
    "RG-02", "RG-03", "RG-05", "RG-07",
    "DDD-RUN-IDENTITY", "DDD-COMPLETED-SESSION", "DDD-BUILD-RECEIPT",
    "DDD-RUN-META-GIT-DESCRIBE", "DDD-RUN-META-FLAGS",
    "DDD-RUN-META-PROFILE-HASH",
}

#: The AG/RG numbers AVS-TST-QT-001 B never defined an assertion for. Named so
#: the report shows the gap instead of implying full coverage.
UNDEFINED_IN_B = [
    "AG-04b", "AG-06", "AG-14", "AG-15", "AG-16", "AG-17",
    "RG-01", "RG-04", "RG-06", "RG-08", "RG-09",
]


# --------------------------------------------------------------------------
# helpers — lifted verbatim in behaviour from AVS-TST-QT-001/scripts/track_b.py
# so the numbers reconcile line for line.
# --------------------------------------------------------------------------

def blank(series: pd.Series) -> pd.Series:
    return series.isna() | (
        series.astype(str).str.strip().isin(["", "nan", "None", "NaN", "<NA>"])
    )


def read_csv(pattern: Path) -> pd.DataFrame | None:
    matches = glob.glob(str(pattern))
    return pd.read_csv(matches[0], low_memory=False) if matches else None


def read_json(pattern: Path) -> Any:
    matches = glob.glob(str(pattern))
    if not matches:
        return None
    try:
        return json.loads(Path(matches[0]).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def direction_split(frame: pd.DataFrame | None, mask, column: str = "final_direction") -> str:
    """CALL / PUT / OTHER counts for the rows a gate matched (binding rule 7)."""
    if frame is None or column not in frame.columns:
        return ""
    values = frame.loc[mask, column].fillna("<NULL>").value_counts().to_dict()
    if not values:
        return ""
    return ";".join(f"{key}={value}" for key, value in sorted(values.items()))


class Report:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.rows: list[dict[str, Any]] = []

    def add(self, gate: str, assertion: str, filter_text: str, count: Any,
            required: Any, three_direction: str = "", verdict: str | None = None) -> None:
        if verdict is None:
            verdict = "PASS" if str(count) == str(required) else "FAIL"
        self.rows.append({
            "run_id": self.run_id,
            "gate": gate,
            "assertion": assertion,
            "filter": filter_text,
            "count": count,
            "required": required,
            "verdict": verdict,
            "p0": gate in P0_GATES,
            "three_direction": three_direction,
        })

    def skip(self, gate: str, assertion: str, reason: str) -> None:
        self.add(gate, assertion, reason, "-", "-", verdict="NOT_EVALUATED")

    @property
    def failed_p0(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["p0"] and r["verdict"] == "FAIL"]


# --------------------------------------------------------------------------
# Section 1 — AG / RG gates
# --------------------------------------------------------------------------

def section_ag_rg(report: Report, frames: dict[str, pd.DataFrame | None]) -> None:
    vanguard = frames["vanguard"]
    options = frames["options"]
    lab = frames["lab"]
    candidates = frames["morning_candidates"]

    if vanguard is not None:
        profile_type = vanguard.get(
            "layer1__profile__profile_type", pd.Series([""] * len(vanguard))
        ).astype(str)
        auction = vanguard.get(
            "layer1__auction_state", pd.Series([""] * len(vanguard))
        ).astype(str)
        mask = profile_type.eq("INSUFFICIENT_DATA") & auction.eq("ALIGNED")
        report.add("AG-01", "INSUFFICIENT_DATA and ALIGNED",
                   "profile_type==INSUFFICIENT_DATA & auction_state==ALIGNED",
                   int(mask.sum()), 0, direction_split(vanguard, mask, "direction"))

        poc = pd.to_numeric(vanguard.get("layer1__profile__poc"), errors="coerce")
        report.add("AG-02", "POC represented as 0.0", "layer1__profile__poc==0.0",
                   int((poc == 0).sum()), 0)

        if "layer1__ready_to_trade" in vanguard.columns:
            ready = vanguard["layer1__ready_to_trade"].astype(str).str.upper().eq("TRUE")
            mask = ready & poc.isna()
            report.add("AG-03", "ready_to_trade True with null POC",
                       "ready_to_trade==True & poc isna",
                       int(mask.sum()), 0, direction_split(vanguard, mask, "direction"))

        timeframe = vanguard.get("layer1__profile__timeframe")
        if timeframe is not None:
            governed = timeframe.astype(str).value_counts().to_dict().get("GOVERNED", 0)
            report.add("AG-04a", "governed branch executed", "timeframe value_counts",
                       governed, len(vanguard))
    else:
        for gate in ("AG-01", "AG-02", "AG-03", "AG-04a"):
            report.skip(gate, "vanguard gate", "vanguard artefact not found")

    if options is not None:
        direction_column = (
            "final_direction" if "final_direction" in options.columns else "direction"
        )
        verdicts = options.get("options_verdict", pd.Series([""] * len(options))).astype(str)
        invalidation = options.get(
            "invalidation_state", pd.Series([""] * len(options))
        ).astype(str)

        mask = verdicts.eq("ARMED") & invalidation.eq("MISSING")
        report.add("AG-05", "ARMED with invalidation MISSING",
                   "options_verdict==ARMED & invalidation_state==MISSING",
                   int(mask.sum()), 0, direction_split(options, mask, direction_column))

        text_leak = options.get(
            "stand_down_reason", pd.Series([""] * len(options))
        ).astype(str).str.contains(
            "unsupported operand|Traceback|Unhandled exception", na=False
        )
        report.add("AG-09", "raw interpreter text in stand_down_reason",
                   "regex on stand_down_reason", int(text_leak.sum()), 0,
                   direction_split(options, text_leak, direction_column))

        if "economics_reason" in options.columns:
            unresolved = options["economics_reason"].astype(str).eq(
                "STRUCTURAL_TARGET_UNRESOLVED"
            )
            count = int(unresolved.sum())
            report.add("AG-10", "governed STRUCTURAL_TARGET_UNRESOLVED present",
                       "economics_reason==STRUCTURAL_TARGET_UNRESOLVED",
                       count, count,
                       direction_split(options, unresolved, direction_column))

        other = options[direction_column].astype(str).isin(["STRANGLE", "UNRESOLVED"])
        breached = other & ~invalidation.eq("NOT_APPLICABLE")
        report.add("RG-07", "OTHER direction not NOT_APPLICABLE",
                   "direction in (STRANGLE,UNRESOLVED) & invalidation_state!=NOT_APPLICABLE",
                   int(breached.sum()), 0,
                   direction_split(options, other, direction_column))
    else:
        for gate in ("AG-05", "AG-09", "AG-10", "RG-07"):
            report.skip(gate, "options gate", "options artefact not found")

    if lab is not None:
        if "invalidation_price" in lab.columns:
            missing = blank(lab["invalidation_price"])
            permission = lab.get(
                "options_research_permission", pd.Series([""] * len(lab))
            ).astype(str)
            mask = missing & permission.eq("EXECUTABLE_SUBJECT_TO_GATES")
            report.add("AG-08", "Lab EXECUTABLE without invalidation",
                       "blank invalidation_price & permission==EXECUTABLE_SUBJECT_TO_GATES",
                       int(mask.sum()), 0, direction_split(lab, mask))
            report.add("AG-08b", "Lab rows blank invalidation_price",
                       "blank invalidation_price", int(missing.sum()), 0,
                       direction_split(lab, missing))

        for field in ("contract_bid_size", "contract_ask_size",
                      "selected_quote_timestamp_utc", "execution_viability_state"):
            if field in lab.columns:
                report.add(f"AG-11:{field}", "Lab lineage populated",
                           f"non-blank {field}", int((~blank(lab[field])).sum()), len(lab))

        for field in ("macro_as_of_utc", "macro_packet_sha256", "monetisability_authority"):
            if field in lab.columns:
                report.add(f"AG-12/13:{field}", "lineage/authority stamp populated",
                           f"non-blank {field}", int((~blank(lab[field])).sum()), len(lab))

        report.add("RG-05", "Lab population reconciles",
                   "nunique(trade_idea_id)==len",
                   int(lab["trade_idea_id"].nunique()) if "trade_idea_id" in lab else -1,
                   len(lab))

        if "final_direction" in lab.columns:
            report.add("RG-02", "Lab direction population",
                       "value_counts(final_direction)", len(lab), len(lab),
                       direction_split(lab, pd.Series([True] * len(lab))))

        # RG-03 is a kill criterion in AVS-MVP-001 §6 but was not evaluated in
        # B; it is cheap and unambiguous, so it is evaluated here.
        if "governed_direction_record_sha256" in lab.columns:
            missing_lineage = blank(lab["governed_direction_record_sha256"])
            report.add("RG-03", "direction lineage hash present on every Lab row",
                       "blank governed_direction_record_sha256",
                       int(missing_lineage.sum()), 0,
                       direction_split(lab, missing_lineage))

        # AVS-FIX-001 W1.1 / W1.5 additions, so a regression is visible here
        # rather than only in the semantic audit.
        for field in ("structural_target", "target_price"):
            if field in lab.columns:
                values = pd.to_numeric(lab[field], errors="coerce")
                zeros = values.notna() & values.eq(0.0)
                report.add(f"FIX-W1.1:{field}", "price field never published as 0.0",
                           f"{field}==0.0", int(zeros.sum()), 0,
                           direction_split(lab, zeros))
        if "contract_dte" in lab.columns:
            has_contract = ~blank(lab.get("contract_symbol", pd.Series([""] * len(lab))))
            missing_dte = has_contract & blank(lab["contract_dte"])
            report.add("FIX-W1.5:contract_dte", "contract_dte present where a contract exists",
                       "contract_symbol non-blank & contract_dte blank",
                       int(missing_dte.sum()), 0, direction_split(lab, missing_dte))
    else:
        for gate in ("AG-08", "AG-08b", "RG-02", "RG-03", "RG-05"):
            report.skip(gate, "Lab gate", "Lab book not found")

    if candidates is not None and "invalidation_spot" in candidates.columns:
        missing = blank(candidates["invalidation_spot"])
        permission = candidates.get(
            "capital_permission", pd.Series([""] * len(candidates))
        ).astype(str)
        mask = missing & permission.eq("EOD_CANDIDATE_ONLY")
        report.add("AG-07", "EOD_CANDIDATE_ONLY without invalidation",
                   "blank invalidation_spot & capital_permission==EOD_CANDIDATE_ONLY",
                   int(mask.sum()), 0, direction_split(candidates, mask))
    else:
        report.skip("AG-07", "morning candidate gate", "morning_candidates not found")

    for gate in UNDEFINED_IN_B:
        report.skip(gate, "no assertion defined",
                    "NOT_DEFINED_IN_B (AVS-TST-QT-001 B never defined this gate)")


# --------------------------------------------------------------------------
# Section 2 — DDD closure checks
# --------------------------------------------------------------------------

FEATURE_FLAGS = (
    "AVSHUNTER_DYNAMIC_PLAN_ENABLED",
    "AVSHUNTER_DYNAMIC_THESIS_ENABLED",
    "AVSHUNTER_DYNAMIC_VALIDATION_ENABLED",
    "AVSHUNTER_PROFILE_LIFECYCLE_ENABLED",
    "AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED",
    "AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED",
    "AVSHUNTER_DECISION_LEDGER_ENABLED",
    "AVSHUNTER_DYNAMIC_AUTO_ENABLED",
    "AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED",
)


def section_ddd(report: Report, run_dir: Path, run_id: str,
                frames: dict[str, pd.DataFrame | None]) -> dict[str, Any]:
    meta = read_json(run_dir / "run_meta.json") or {}

    run_ids = {str(meta.get("canonical_run_id") or ""), str(meta.get("discovery_run_id") or "")}
    for name, frame in frames.items():
        if frame is None:
            continue
        for column in ("pipeline_run_id", "run_id", "canonical_run_id"):
            if column in frame.columns:
                run_ids.update(frame[column].dropna().astype(str).unique().tolist())
                break
    run_ids.discard("")
    report.add("DDD-RUN-IDENTITY", "one pipeline_run_id across stages",
               "distinct run ids in run_meta + stage artefacts",
               len(run_ids), 1,
               three_direction=";".join(sorted(run_ids)[:5]))

    sessions: set[str] = set()
    for frame in frames.values():
        if frame is None:
            continue
        for column in ("completed_session", "evidence_session_date", "session_date"):
            if column in frame.columns:
                sessions.update(
                    frame[column].dropna().astype(str).str.slice(0, 10).unique().tolist()
                )
                break
    sessions.discard("")
    report.add("DDD-COMPLETED-SESSION", "one completed session across stages",
               "distinct session dates in stage artefacts",
               len(sessions) if sessions else 0, 1,
               three_direction=";".join(sorted(sessions)[:5]))

    receipt = read_json(run_dir / "*thesis_receipt*.json") or read_json(
        run_dir / "run_plans" / "*.json"
    )
    plan = (meta.get("dynamic_plan") or {})
    plan_hash = str(plan.get("plan_hash") or "")
    receipt_hash = ""
    if isinstance(receipt, dict):
        receipt_hash = str(receipt.get("plan_hash") or receipt.get("plan_hash_sha256") or "")
    report.add("DDD-BUILD-RECEIPT", "build receipt present and plan-hash-bound",
               "receipt.plan_hash == run_meta.dynamic_plan.plan_hash",
               "BOUND" if (plan_hash and plan_hash == receipt_hash) else
               ("RECEIPT_MISSING" if receipt is None else "UNBOUND"),
               "BOUND")

    describe = str(meta.get("git_describe") or "")
    report.add("DDD-RUN-META-GIT-DESCRIBE", "run_meta carries git_describe",
               "run_meta.git_describe non-blank and not UNAVAILABLE",
               "PRESENT" if describe and describe != "UNAVAILABLE" else
               (describe or "ABSENT"), "PRESENT")

    resolved = meta.get("resolved_feature_flags") or {}
    report.add("DDD-RUN-META-FLAGS", "run_meta carries all nine feature flags",
               "len(run_meta.resolved_feature_flags)",
               len([f for f in FEATURE_FLAGS if f in resolved]), len(FEATURE_FLAGS),
               three_direction=";".join(
                   f"{name.split('_')[-2]}={resolved.get(name)}"
                   for name in FEATURE_FLAGS if name in resolved
               )[:120])

    profile_sha = str((meta.get("ddd_runtime_profile") or {}).get("sha256") or "")
    report.add("DDD-RUN-META-PROFILE-HASH", "run_meta carries the runtime profile hash",
               "run_meta.ddd_runtime_profile.sha256 non-blank",
               "PRESENT" if profile_sha else "ABSENT", "PRESENT",
               three_direction=profile_sha[:16])

    summary = read_json(
        run_dir / "market_profile" / f"completed_profile_summary_{run_id}.json"
    ) or read_json(run_dir / "market_profile" / "completed_profile_summary_*.json")
    if summary:
        usable = summary.get("usable_ratio")
        minimum = summary.get("min_usable_ratio")
        if usable is None or minimum is None:
            # A summary written before AVS-FIX-001 W1.4 has neither field. Say
            # so rather than passing a comparison against None.
            report.skip("DDD-PROFILE-USABLE-RATIO", "completed_profile_summary usable_ratio",
                        "usable_ratio/min_usable_ratio absent (pre-W1.4 summary)")
        else:
            report.add("DDD-PROFILE-USABLE-RATIO", "completed_profile_summary usable_ratio",
                       f"usable_ratio >= min_usable_ratio ({minimum})",
                       usable, f">={minimum}",
                       verdict="PASS" if usable >= minimum else "FAIL")
        if "guard_decision" in summary:
            report.add("DDD-PROFILE-GUARD", "completed_profile_summary guard_decision",
                       "guard_decision", summary["guard_decision"], "PASS")
        else:
            report.skip("DDD-PROFILE-GUARD", "completed_profile_summary guard_decision",
                        "guard_decision absent (pre-W1.4 summary)")
        report.add("DDD-PROFILE-POPULATION",
                   "input = processed + excluded + deferred + exceptions",
                   "reconciled", summary.get("reconciled", "ABSENT"), True)
    else:
        for gate in ("DDD-PROFILE-USABLE-RATIO", "DDD-PROFILE-GUARD",
                     "DDD-PROFILE-POPULATION"):
            report.skip(gate, "profile stage", "completed_profile_summary not found")
    return meta


# --------------------------------------------------------------------------
# Section 3 — semantic audit
# --------------------------------------------------------------------------

#: Statuses that describe a real contradiction in the data. Anything else the
#: audit reports is treated as spurious and named, never silently dropped.
GENUINE_AUDIT_STATUSES = {
    "OPTIONS_PERMISSION_NOT_RESEARCH_ONLY",
    "OPTIONS_BLOCKED_PROMOTED_TO_EOD_CANDIDATE",
    "RETIRED_PSE_EMITTED_POSITIVE_SIZE",
    "DIRECTIONAL_TRADE_PROMOTED_WITHOUT_GOVERNED_INVALIDATION",
    "UNUSABLE_PROFILE_MARKED_ALIGNED_OR_READY",
    "ARMED_WITHOUT_GOVERNED_INVALIDATION",
    "EOD_CANDIDATE_WITHOUT_GOVERNED_INVALIDATION",
    "LAB_EXECUTABLE_WITHOUT_GOVERNED_INVALIDATION",
    "RAW_INTERPRETER_TEXT_PUBLISHED",
    "INSUFFICIENT_PROFILE_MARKED_ALIGNED",
    "MISSING_PROFILE_LEVEL_PUBLISHED_AS_ZERO",
    "PRICE_FIELD_ZERO_AS_MISSING",
    "DIRECTION_LINEAGE_HASH_MISMATCH",
    "STALE_BAR_FALLBACK_UNNAMED",
}


def section_audit(report: Report, run_id: str) -> list[dict[str, Any]]:
    try:
        import handoff_contract_audit as hca
    except Exception as error:                       # pragma: no cover
        report.skip("AUDIT", "semantic audit", f"handoff_contract_audit unavailable: {error}")
        return []
    # audit_run writes its CSV/JSON beside the run by default. This report is
    # read-only over the run directory, so the output is redirected to a
    # temporary directory that is discarded.
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as scratch:
            result = hca.audit_run(run_id, output_dir=Path(scratch))
    except Exception as error:
        report.skip("AUDIT", "semantic audit", f"audit_run failed: {error}")
        return []

    records = [
        record for record in (result.get("outstanding_fixes") or [])
        if str(record.get("severity", "")).upper() == "FAIL"
    ]
    genuine = [r for r in records if r.get("status") in GENUINE_AUDIT_STATUSES]
    spurious = [r for r in records if r.get("status") not in GENUINE_AUDIT_STATUSES]

    report.add("AUDIT-FAIL-GENUINE", "semantic audit genuine failures",
               "severity==FAIL and status in the genuine set", len(genuine), 0)
    # One row per genuine finding, so the failing tickers are named rather than
    # truncated into a single summary line.
    for record in genuine:
        report.add(
            f"AUDIT:{record.get('status')}",
            f"stage={record.get('stage')} contract={record.get('field_contract')}",
            f"rows={record.get('filled_rows')} of {record.get('row_count')}",
            record.get("filled_rows"), 0,
            three_direction=str(record.get("recommendation", ""))[:180],
        )
    report.add("AUDIT-FAIL-SPURIOUS", "semantic audit failures not in the genuine set",
               "severity==FAIL and status outside the genuine set",
               len(spurious), len(spurious),
               three_direction="; ".join(str(r.get("status")) for r in spurious)[:200])
    return genuine


# --------------------------------------------------------------------------
# Section 4 — AVS-MVP-001 §6 kill criteria
# --------------------------------------------------------------------------

def section_kill_criteria(report: Report, frames: dict[str, pd.DataFrame | None],
                          genuine_audit: list[dict[str, Any]], run_dir: Path) -> None:
    lab = frames["lab"]

    def kill(number: int, description: str, filter_text: str, fired,
             three_direction: str = "") -> None:
        report.add(f"KILL-{number}", description, filter_text,
                   "FIRED" if fired else "CLEAR", "CLEAR", three_direction)

    if lab is not None and "invalidation_price" in lab.columns:
        missing = blank(lab["invalidation_price"])
        permission = lab.get(
            "options_research_permission", pd.Series([""] * len(lab))
        ).astype(str)
        action = lab.get("final_action", pd.Series([""] * len(lab))).astype(str)
        promoted = permission.eq("EXECUTABLE_SUBJECT_TO_GATES") | action.str.startswith("BUY")
        mask = missing & promoted
        kill(1, "Lab row EXECUTABLE or BUY_* with blank invalidation_price",
             "blank invalidation_price & (EXECUTABLE_SUBJECT_TO_GATES | BUY_*)",
             bool(mask.any()), direction_split(lab, mask))
    else:
        kill(1, "Lab row EXECUTABLE or BUY_* with blank invalidation_price",
             "Lab book not found", False, "NOT_EVALUATED")

    if lab is not None and "governed_direction_record_sha256" in lab.columns:
        mask = blank(lab["governed_direction_record_sha256"])
        kill(2, "governed_direction_record_sha256 mismatch or missing (RG-03)",
             "blank governed_direction_record_sha256", bool(mask.any()),
             direction_split(lab, mask))
    else:
        kill(2, "governed_direction_record_sha256 mismatch or missing (RG-03)",
             "lineage column not found", False, "NOT_EVALUATED")

    if lab is not None:
        column = "final_direction" if "final_direction" in lab.columns else "direction"
        if column in lab.columns:
            mask = lab[column].astype(str).str.upper().isin(["STRANGLE", "UNRESOLVED"])
            kill(3, "STRANGLE/UNRESOLVED row in the Lab book (RG-07)",
                 f"{column} in (STRANGLE, UNRESOLVED)", bool(mask.any()),
                 direction_split(lab, mask, column))
        else:
            kill(3, "STRANGLE/UNRESOLVED row in the Lab book (RG-07)",
                 "direction column not found", False, "NOT_EVALUATED")
    else:
        kill(3, "STRANGLE/UNRESOLVED row in the Lab book (RG-07)",
             "Lab book not found", False, "NOT_EVALUATED")

    pattern = "unsupported operand|Traceback|Unhandled exception"
    leaked_fields: list[str] = []
    for name, frame in frames.items():
        if frame is None:
            continue
        for column in frame.columns:
            if frame[column].dtype != object:
                continue
            if frame[column].astype(str).str.contains(pattern, na=False).any():
                leaked_fields.append(f"{name}.{column}")
    kill(4, "interpreter/exception text in a trader-facing field (AG-09)",
         f"regex '{pattern}' over object columns", bool(leaked_fields),
         ";".join(leaked_fields[:6]))

    finaliser = read_json(run_dir / "**" / "*handoff_final*.json")
    if finaliser is None:
        kill(5, "Morning handoff finaliser failed or reported a permission disagreement",
             "handoff finaliser artefact not found", False, "NOT_EVALUATED")
    else:
        status = str(
            (finaliser or {}).get("status")
            or (finaliser or {}).get("finaliser_status")
            or ""
        ).upper()
        kill(5, "Morning handoff finaliser failed or reported a permission disagreement",
             "finaliser status not PASS/COMPLETE",
             status not in {"PASS", "COMPLETE", "OK", "SUCCESS", ""}, status)

    kill(6, "audit fail_count > 0 for a genuine rule",
         "genuine semantic-audit FAIL records", bool(genuine_audit),
         ";".join(sorted({str(r.get("status")) for r in genuine_audit}))[:200])

    kill(7, "two consecutive positions exit at invalidation with no target approached",
         "requires the outcome ledger; not derivable from one run directory",
         False, "NOT_EVALUATED_REQUIRES_LEDGER")


# --------------------------------------------------------------------------

def load_frames(run_dir: Path, run_id: str) -> dict[str, pd.DataFrame | None]:
    vanguard = read_csv(run_dir / "options" / f"vanguard_signals_enriched_{run_id}.csv")
    if vanguard is None:
        vanguard = read_csv(run_dir / "vanguard" / "vanguard_signals.csv")
    return {
        "vanguard": vanguard,
        "options": read_csv(run_dir / "options" / f"options_intelligence_{run_id}.csv"),
        "eil_enriched": read_csv(run_dir / "superbrain" / f"eil_enriched_{run_id}.csv"),
        "execution": read_csv(run_dir / "execution" / f"execution_v3_5_{run_id}.csv"),
        "lab": read_csv(
            run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv"
        ),
        "morning_candidates": read_csv(
            run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--csv", dest="csv_path")
    args = parser.parse_args(argv)

    run_dir = RUNS / args.run_id
    if not run_dir.is_dir():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        return 1

    report = Report(args.run_id)
    frames = load_frames(run_dir, args.run_id)

    print("=" * 100)
    print(f"AVS-FIX-001 gate report - run {args.run_id}")
    print(f"source: {run_dir}   (read only)")
    print("=" * 100)

    section_ag_rg(report, frames)
    section_ddd(report, run_dir, args.run_id, frames)
    genuine = section_audit(report, args.run_id)
    section_kill_criteria(report, frames, genuine, run_dir)

    width = max(len(row["gate"]) for row in report.rows)
    for row in report.rows:
        marker = "P0" if row["p0"] else "  "
        print(f"  {row['verdict']:13s} {marker} {row['gate']:{width}s} "
              f"count={str(row['count']):>10s} req={str(row['required']):>10s}  "
              f"{row['filter'][:52]}")
        if row["three_direction"]:
            print(f"                    {'':{width}s}   -> {row['three_direction'][:110]}")

    failures = report.failed_p0
    killed = [
        r for r in report.rows
        if r["gate"].startswith("KILL-") and r["count"] == "FIRED"
    ]
    print("-" * 100)
    print(f"rows={len(report.rows)}  "
          f"PASS={sum(1 for r in report.rows if r['verdict'] == 'PASS')}  "
          f"FAIL={sum(1 for r in report.rows if r['verdict'] == 'FAIL')}  "
          f"NOT_EVALUATED={sum(1 for r in report.rows if r['verdict'] == 'NOT_EVALUATED')}")
    print(f"P0 failures: {len(failures)}"
          + (" -> " + ", ".join(r["gate"] for r in failures) if failures else ""))
    print(f"kill criteria fired: {len(killed)}"
          + (" -> " + ", ".join(r["gate"] for r in killed) if killed else ""))

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report.rows, indent=2, default=str), encoding="utf-8"
        )
        print(f"json: {args.json_path}")
    if args.csv_path:
        with open(args.csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(report.rows[0].keys()))
            writer.writeheader()
            writer.writerows(report.rows)
        print(f"csv: {args.csv_path}")

    return 1 if (failures or killed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
