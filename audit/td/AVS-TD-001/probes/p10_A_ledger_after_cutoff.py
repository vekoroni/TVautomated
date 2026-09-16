"""p10_A_ledger_after_cutoff.py -- Track A / A1: api_request_ledger (control_plane copy, read-only) per run_id:
requests, physical requests, and requests/physical started after the evidence cutoff. Cutoff = run_plans first-row
evidence_cutoff_utc when present, else the UTC run_id stamp; also the ledger's own evidence_cutoff_utc column.
Output: probes/p10_A_ledger_after_cutoff_out.json"""
import json, os, sqlite3
from datetime import datetime, timezone
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; DB = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "db_copies")
RUNS = os.path.join(ROOT, "data", "output", "runs")
def p(s):
    if not s: return None
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00")); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
plans = {}
pc = sqlite3.connect(f"file:{os.path.join(DB, 'run_plans.sqlite')}?mode=ro", uri=True)
for rid, cut in pc.execute("select pipeline_run_id, evidence_cutoff_utc from run_plans order by persisted_at_utc"):
    plans.setdefault(rid, cut)
c = sqlite3.connect(f"file:{os.path.join(DB, 'control_plane.sqlite')}?mode=ro", uri=True)
out = {"runs": {}}
for (rid,) in c.execute("select distinct run_id from api_request_ledger order by 1").fetchall():
    try: stamp = datetime.strptime(str(rid)[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError: stamp = None
    cut = p(plans.get(rid)) or stamp
    rows = c.execute("select started_at, physical_request_count, evidence_cutoff_utc, stage, dataset_type from api_request_ledger where run_id=?", (rid,)).fetchall()
    after = [r for r in rows if cut and p(r[0]) and p(r[0]) > cut]
    ledger_cuts = sorted({r[2] for r in rows if r[2]})
    out["runs"][rid] = {"cutoff_used": cut.isoformat() if cut else None, "cutoff_src": "run_plans" if rid in plans else "run_id_stamp",
                        "has_run_meta": os.path.isfile(os.path.join(RUNS, rid, "run_meta.json")),
                        "n": len(rows), "physical": sum(int(r[1] or 0) for r in rows),
                        "n_after_cutoff": len(after), "physical_after_cutoff": sum(int(r[1] or 0) for r in after),
                        "min_started": min((r[0] for r in rows), default=None), "max_started": max((r[0] for r in rows), default=None),
                        "ledger_evidence_cutoff_values": ledger_cuts[:5], "n_distinct_ledger_cutoffs": len(ledger_cuts)}
R = out["runs"]
out["summary"] = {"runs_in_ledger": len(R), "runs_with_any_after_cutoff": sum(1 for v in R.values() if v["n_after_cutoff"] > 0),
                  "runs_with_physical_after_cutoff": sum(1 for v in R.values() if v["physical_after_cutoff"] > 0),
                  "run_meta_runs_in_ledger": sum(1 for v in R.values() if v["has_run_meta"]),
                  "run_meta_runs_with_any_after_cutoff": sum(1 for v in R.values() if v["has_run_meta"] and v["n_after_cutoff"] > 0)}
json.dump(out, open(os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_ledger_after_cutoff_out.json"), "w", encoding="utf-8"), indent=1)
for k, v in R.items(): print(k, {x: v[x] for x in ("cutoff_src", "has_run_meta", "n", "physical", "n_after_cutoff", "physical_after_cutoff", "min_started", "max_started", "n_distinct_ledger_cutoffs")})
print(out["summary"])
