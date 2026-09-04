"""AVS-RCA-002 A5b - cache identity forensics. READ ONLY."""
import sqlite3, pandas as pd
con=sqlite3.connect("file:data/canonical/control_plane.sqlite?mode=ro", uri=True)
q=lambda s,*a: pd.read_sql_query(s, con, params=a)
for r in ("20260904_004338","20260902_232526"):
    d=q("select scope_fingerprint, request_fingerprint, count(*) n from api_request_ledger where run_id=? and dataset_type='OPTION_CHAIN' group by scope_fingerprint, request_fingerprint order by n desc",r)
    print(f"\n### {r}: distinct (scope_fingerprint, request_fingerprint) for OPTION_CHAIN: {len(d)}")
    print(d.head(5).to_string(index=False))
    d2=q("select count(distinct scope_fingerprint) sf, count(distinct request_fingerprint) rf, count(distinct dataset_id) di, count(*) n from api_request_ledger where run_id=? and dataset_type='OPTION_CHAIN'",r)
    print(d2.to_string(index=False))
print("\n### dataset_registry OPTION_CHAIN ###")
print(q("select dataset_type, count(*) n, count(distinct scope_fingerprint) sf, count(distinct instrument_id) inst, min(session_date) mn, max(session_date) mx from dataset_registry where dataset_type='OPTION_CHAIN' group by dataset_type").to_string(index=False))
print(q("select source_run_id, count(*) n, count(distinct scope_fingerprint) sf from dataset_registry where dataset_type='OPTION_CHAIN' group by source_run_id order by source_run_id").to_string(index=False))
print("\nsample OPTION_CHAIN registry rows:")
print(q("select dataset_id, instrument_id, session_date, scope_fingerprint, completeness_status, expires_at, as_of, source_run_id from dataset_registry where dataset_type='OPTION_CHAIN' order by registered_at desc limit 6").to_string(index=False))
print("\nscope_json sample:")
for (s,) in con.execute("select scope_json from dataset_registry where dataset_type='OPTION_CHAIN' order by registered_at desc limit 3"):
    print("  ", s[:400])
print("\n### all dataset_types in registry ###")
print(q("select dataset_type, count(*) n, count(distinct scope_fingerprint) sf from dataset_registry group by dataset_type order by n desc").to_string(index=False))
print("\n### how OTHER dataset types got exact hits (which run/type) ###")
print(q("select run_id, dataset_type, reason, count(*) n, sum(physical_request_count) phys from api_request_ledger where reason in ('exact fresh dataset','partial coverage requires gap fetch') group by run_id, dataset_type, reason order by run_id").to_string(index=False))
