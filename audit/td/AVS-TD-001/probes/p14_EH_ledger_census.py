"""p14_EH_ledger_census: read-only census of the ledger COPY (Track H1 / E6).

Writes beside this file:
  p14_EH_ledger_census.csv         long format: run_id,event_type,direction,n
  p14_EH_ledger_census_wide.csv    run_id,event_type,n,n_call,n_put,n_other
  p14_EH_ledger_payload_keys.json  payload key inventory per event_type
  p14_EH_ledger_census_out.json    totals, sub-facets, substring hits, link stats
Direction is taken from payload.direction (fallback governed_direction /
options_direction); anything not CALL/PUT is OTHER.
"""
import sqlite3, json, csv, collections, os
ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(ROOT, "..", "db_copies", "decision_outcome_ledger.sqlite"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = con.execute(
    "SELECT run_id,event_type,payload_json,previous_event_id,occurred_at_utc FROM ledger_events"
).fetchall()
census = collections.Counter()
keys = collections.defaultdict(collections.Counter)
sub = collections.defaultdict(collections.Counter)
prev_link = collections.Counter()
hits = collections.Counter()
occurred = collections.defaultdict(list)
for run_id, et, pj, prev, occ in rows:
    p = json.loads(pj)
    d = str(p.get("direction") or p.get("governed_direction") or p.get("options_direction") or "").upper()
    d = d if d in ("CALL", "PUT") else "OTHER"
    census[(run_id, et, d)] += 1
    for k in p:
        keys[et][k] += 1
    for f in ("decision_stage", "data_status", "is_counterfactual", "record_version",
              "first_passage_state", "outcome_class", "exit_reason", "source",
              "final_action", "execution_eligibility_state", "thesis_state"):
        if f in p:
            sub[et][f"{f}={p[f]}"] += 1
    prev_link[f"{et}|prev_present={bool(prev)}"] += 1
    low = pj.lower()
    for w_ in ("position", "episode", "fill", "mfe", "mae", "attribution", "horizon"):
        if w_ in low:
            hits[f"{et}|{w_}"] += 1
    occurred[(run_id, et)].append(occ)

with open(os.path.join(ROOT, "p14_EH_ledger_census.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["run_id", "event_type", "direction", "n"])
    for (run_id, et, d), n in sorted(census.items()):
        w.writerow([run_id, et, d, n])
wide = collections.defaultdict(collections.Counter)
for (run_id, et, d), n in census.items():
    wide[(run_id, et)][d] += n
with open(os.path.join(ROOT, "p14_EH_ledger_census_wide.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["run_id", "event_type", "n", "n_call", "n_put", "n_other", "first_occurred", "last_occurred"])
    for (run_id, et), ds in sorted(wide.items()):
        occ = sorted(occurred[(run_id, et)])
        w.writerow([run_id, et, sum(ds.values()), ds["CALL"], ds["PUT"], ds["OTHER"], occ[0], occ[-1]])
tot = collections.Counter()
for (r, et, d), n in census.items():
    tot[et] += n
out = {
    "total_rows": len(rows),
    "event_type_totals": dict(tot),
    "event_types_present": sorted(tot),
    "distinct_run_ids": sorted({r for r, _, _ in census}),
    "previous_event_id_link": dict(prev_link),
    "payload_sub_facets": {et: dict(c) for et, c in sub.items()},
    "payload_substring_hits": dict(hits),
}
json.dump(out, open(os.path.join(ROOT, "p14_EH_ledger_census_out.json"), "w"), indent=1)
json.dump({et: dict(c) for et, c in keys.items()}, open(os.path.join(ROOT, "p14_EH_ledger_payload_keys.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
