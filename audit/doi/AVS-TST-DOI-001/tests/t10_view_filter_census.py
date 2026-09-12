"""AVS-TST-DOI-001 T10 task 3: port of the Lab's client-side view pipeline
(intelligence-lab/static/index.html) applied to the merged+projected governed
book for run 20260909_071646.  Read-only; no server is started.

JS sources ported:
  index.html:589  SHOW_INVALID default
  index.html:599  showAuditRows default (DOI-10 "All Opportunities")
  index.html:706  ALL_SIGS = ALL_SIGS.filter(s => s.sb_schema_ok !== 'N')
  index.html:1328 cleanCategory / 1332 finalLabVerdict / 1337 displayCampaign
  index.html:1377 isActionSignal / 1399 isAuditOnlySignal / 1512 firstSignalValue
  index.html:1897 filteredData
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from canonical_data.dynamic_options_projection import DynamicOptionsProjectionResolver
from contracts.interpreter_handoff import validate_handoff_manifest
from domain.dynamic_options_projection import merge_all_opportunities

RUN = "20260909_071646"
BOOK = ROOT / "data" / "output" / "runs" / RUN / "intelligence_lab" / f"final_opportunity_book_{RUN}.json"
HANDOFF = ROOT / "data" / "output" / "runs" / RUN / "interpreter" / "handoff_manifest.json"
DB = ROOT / "audit" / "doi" / "AVS-TST-DOI-001" / "scratch" / "T10" / "cp_nodoi.sqlite"

MISSING = {"NONE", "N/A", "NA", "UNKNOWN", "NULL", "NAN", "UNROUTED"}


def clean(v) -> str:
    return " ".join(str(v if v is not None else "").strip().upper().split()).replace(" ", "_")


def first_signal_value(s, keys):
    for k in keys:
        v = s.get(k)
        if v is None or str(v).strip() == "":
            continue
        if clean(v) in MISSING:
            continue
        return v
    return ""


def final_lab_verdict(s) -> str:
    return clean(s.get("lab_verdict") or s.get("lab_status") or s.get("display_final_verdict") or "WAIT")


CAMPAIGN_MAP = {
    "GO": "READY_EXECUTE", "EOD_EXEC": "READY_EXECUTE", "GO_LIMIT": "READY_LIMIT",
    "PROBE": "READY_PROBE", "EOD_CAUTION": "EXECUTE_WITH_CAUTION", "ARMED": "ARMED",
    "CONTRACT_REPAIR": "CONTRACT_REPAIR", "WAIT": "WATCHLIST", "WATCHLIST": "WATCHLIST",
    "BLOCKED": "BLOCKED",
}


def display_campaign(s) -> str:
    return s.get("display_campaign") or CAMPAIGN_MAP.get(final_lab_verdict(s)) or s.get("sb_campaign") or "WATCHLIST"


def is_action_signal(s) -> bool:
    return final_lab_verdict(s) in {"GO", "GO_LIMIT", "PROBE", "EOD_EXEC", "EOD_CAUTION"}


def morning_perm(s):
    return clean(first_signal_value(s, ["morning_execution_permission", "mv__morning_execution_permission",
                                        "mv_morning_execution_permission", "mv_execution_permission",
                                        "mv__execution_permission"]))


def morning_route(s):
    return clean(first_signal_value(s, ["morning_execution_route", "mv__morning_execution_route",
                                        "mv_morning_execution_route"]))


def live_state(s):
    return clean(first_signal_value(s, ["live_validation_state", "mv__live_validation_state",
                                        "mv_live_validation_state", "validation_state", "mv__validation_state"]))


def thesis_state(s):
    return clean(first_signal_value(s, ["thesis_validity_state", "mv__thesis_validity_state",
                                        "mv_thesis_validity_state"]))


def is_audit_only(s) -> bool:
    if s.get("lab_hidden_by_default") is True or str(s.get("lab_hidden_by_default")).lower() == "true":
        return True
    flags = clean(first_signal_value(s, ["veto_flags", "conflict_flags", "execution_lock_reason"]))
    return (final_lab_verdict(s) == "BLOCKED"
            or morning_perm(s) == "BLOCKED"
            or morning_route(s) in {"STAND_DOWN", "BLOCKED"}
            or live_state(s) in {"REJECTED", "BLOCKED"}
            or thesis_state(s) in {"BROKEN", "INVALIDATED", "THESIS_BROKEN"}
            or (clean(s.get("conflict_state")) == "HARD_CONFLICT" and "MORNING_VALIDATION_BLOCKED" in flags))


DIR_FIELDS = ("governed_direction", "canonical_direction", "final_direction", "direction")


def split(rows):
    c = collections.Counter()
    for r in rows:
        d = "OTHER"
        for f in DIR_FIELDS:
            v = str(r.get(f) or "").strip().upper()
            if v in {"CALL", "PUT"}:
                d = v
                break
        c[d] += 1
    return f"CALL {c['CALL']:>3} / PUT {c['PUT']:>3} / OTHER {c['OTHER']:>3}  (n={sum(c.values())})"


payload = json.loads(BOOK.read_text(encoding="utf-8"))
full = payload["rows"]
actionable = [dict(r) for r in validate_handoff_manifest(HANDOFF, require_accepted=True).book_rows]
merged, _ = merge_all_opportunities(full, actionable)
signals = DynamicOptionsProjectionResolver(DB).project_rows(merged)

print("=" * 92)
print("T10 TASK 3 - LAB VIEW CENSUS, run", RUN)
print("=" * 92)
print(f"{'GOVERNED BOOK (v2 payload rows)':<58}{split(full)}")
print(f"{'AFTER DOI-10 merge + projection (API result.signals)':<58}{split(signals)}")

# --- index.html:706 - population mutation, not a view filter -----------------
schema_n = [s for s in signals if str(s.get("sb_schema_ok")) == "N"]
all_sigs = [s for s in signals if str(s.get("sb_schema_ok")) != "N"]
print("\n-- index.html:589+706  SHOW_INVALID=false (DEFAULT): ALL_SIGS is REASSIGNED, not filtered --")
print(f"{'  rows with sb_schema_ok == N (dropped from base pop)':<58}{split(schema_n)}")
print(f"{'  ALL_SIGS after the drop (base for EVERY count/view)':<58}{split(all_sigs)}")
print(f"  sb_schema_ok value distribution: "
      f"{dict(collections.Counter(repr(s.get('sb_schema_ok')) for s in signals))}")

# --- index.html:1897 filteredData at documented defaults --------------------
print("\n-- index.html:338/599  DEFAULT VIEW: showAuditRows=true, all filters 'ALL' --")
default_view = list(all_sigs)
print(f"{'  DEFAULT (All Opportunities) rendered rows':<58}{split(default_view)}")
print(f"  retains full governed book? {len(default_view) == len(full)}"
      f"   ({len(default_view)} of {len(full)})")

# --- every offered filter ---------------------------------------------------
print("\n-- EVERY FILTER THE LAB OFFERS (population under each) --")
views = {
    "Actionable Only toggle (showAuditRows=false)": [s for s in all_sigs if not is_audit_only(s)],
    "campaignViewMode (Campaign card)": [s for s in all_sigs if display_campaign(s) == "CORE_CAMPAIGN"],
    "SIGNALS (isActionSignal - drives Top 5 / stats)": [s for s in all_sigs if is_action_signal(s)],
    "quickFilter monetisable": [s for s in all_sigs if clean(first_signal_value(
        s, ["monetisability_state", "monetisability"])) in {"MONETISABLE", "LIMITED"}],
    "filters.dir = CALL": [s for s in all_sigs if "CALL" in str(s.get("direction") or "").upper()],
    "filters.dir = PUT": [s for s in all_sigs if "PUT" in str(s.get("direction") or "").upper()],
}
for verdict in sorted({final_lab_verdict(s) for s in all_sigs}):
    views[f"filters.verdict = {verdict}"] = [s for s in all_sigs if final_lab_verdict(s) == verdict]
for camp in sorted({display_campaign(s) for s in all_sigs}):
    views[f"filters.camp = {camp}"] = [s for s in all_sigs if display_campaign(s) == camp]

for name, rows in views.items():
    delta = len(rows) - len(full)
    mark = "" if delta == 0 else f"   REDUCES BY {abs(delta)}"
    print(f"  {name:<56}{split(rows)}{mark}")

print("\n-- audit-only (hidden when the toggle is switched off) --")
hidden = [s for s in all_sigs if is_audit_only(s)]
print(f"{'  rows hidden by Actionable Only':<58}{split(hidden)}")
print("  verdict distribution of hidden rows: "
      f"{dict(collections.Counter(final_lab_verdict(s) for s in hidden))}")

print("\n-- lab_schema_version after the DOI-10 merge (drives populateGovernedDisplayFields, index.html:672) --")
print("  " + str(dict(collections.Counter(s.get("lab_schema_version") for s in signals))))
print("  populateGovernedDisplayFields returns EARLY unless lab_schema_version == 'lab_signal_book_v2'")
non_v2 = [s for s in signals if s.get("lab_schema_version") != "lab_signal_book_v2"]
print(f"  rows that therefore LOSE governed display aliasing: {[s.get('ticker') for s in non_v2]}")
