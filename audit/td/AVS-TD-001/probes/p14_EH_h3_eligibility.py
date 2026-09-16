"""p14_EH_h3_eligibility: apply the production maturation eligibility rule
(canonical_data/outcome_maturation.py:107-131) to every CANDIDATE_DECISION in the
ledger COPY and count why candidates are ineligible. Read-only. Also records the
raw value classes of reference_price/target_price/invalidation_price and the
decision_stage filter (line 77-81). Output: p14_EH_h3_eligibility_out.json
"""
import sqlite3, json, collections, os, math
ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(ROOT, "..", "db_copies", "decision_outcome_ledger.sqlite"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

def _number(value):  # verbatim copy of outcome_maturation._number
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None

def vclass(v):
    if v is None: return "None"
    if isinstance(v, bool): return f"bool:{v}"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v): return "nan"
        return "num>0" if v > 0 else "num<=0"
    s = str(v).strip()
    if s == "": return "empty_str"
    try:
        f = float(s); return "str_num>0" if f > 0 else "str_num<=0"
    except ValueError:
        return f"str:{s[:20]}"

rows = con.execute("SELECT run_id,payload_json FROM ledger_events WHERE event_type='CANDIDATE_DECISION'").fetchall()
stage = collections.Counter(); reasons = collections.Counter(); per_run = collections.defaultdict(collections.Counter)
classes = collections.defaultdict(collections.Counter); by_dir = collections.defaultdict(collections.Counter)
eod = 0; eligible = 0; sample = []
for run_id, pj in rows:
    p = json.loads(pj)
    stage[str(p.get("decision_stage"))] += 1
    if str(p.get("decision_stage") or "").upper() != "EOD_THESIS":
        continue
    eod += 1
    direction = str(p.get("direction") or "").strip().upper()
    completed_session = str(p.get("completed_session") or "").strip()[:10]
    reference = _number(p.get("reference_price")); target = _number(p.get("target_price")); inval = _number(p.get("invalidation_price"))
    for f in ("reference_price", "target_price", "invalidation_price", "completed_session", "planned_hold_sessions"):
        classes[f][vclass(p.get(f))] += 1
    missing = []
    if direction not in {"CALL", "PUT"}: missing.append("DIRECTION_UNAVAILABLE")
    if not completed_session: missing.append("COMPLETED_SESSION_UNAVAILABLE")
    if reference is None: missing.append("REFERENCE_PRICE_UNAVAILABLE")
    if target is None: missing.append("TARGET_PRICE_UNAVAILABLE")
    if inval is None: missing.append("INVALIDATION_PRICE_UNAVAILABLE")
    key = "|".join(missing) or "ELIGIBLE"
    reasons[key] += 1; per_run[run_id][key] += 1
    by_dir[direction if direction in ("CALL", "PUT") else "OTHER"][key] += 1
    if not missing:
        eligible += 1
        if len(sample) < 5:
            sample.append({k: p.get(k) for k in ("direction", "completed_session", "reference_price", "target_price", "invalidation_price", "planned_hold_sessions")})
out = {
    "candidate_decision_rows": len(rows),
    "decision_stage_counts": dict(stage),
    "eod_thesis_candidates": eod,
    "eligible_by_production_rule": eligible,
    "ineligibility_reason_counts": dict(reasons),
    "per_run": {r: dict(c) for r, c in per_run.items()},
    "by_direction": {d: dict(c) for d, c in by_dir.items()},
    "value_classes": {f: dict(c) for f, c in classes.items()},
    "eligible_sample": sample,
}
json.dump(out, open(os.path.join(ROOT, "p14_EH_h3_eligibility_out.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
