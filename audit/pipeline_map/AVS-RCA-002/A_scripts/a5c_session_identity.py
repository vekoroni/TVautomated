"""AVS-RCA-002 A5c - session-date identity: is zero reuse EXPECTED_COLD? READ ONLY."""
import sqlite3, pandas as pd
con=sqlite3.connect("file:data/canonical/control_plane.sqlite?mode=ro", uri=True)
q=lambda s,*a: pd.read_sql_query(s, con, params=a)
print("### OPTION_CHAIN registry: source_run_id x session_date ###")
print(q("select source_run_id, session_date, count(*) n, count(distinct instrument_id) inst, scope_fingerprint from dataset_registry where dataset_type='OPTION_CHAIN' group by source_run_id, session_date order by source_run_id").to_string(index=False))
print("\n### run_registry ###")
print(q("select run_id, run_type, session_date, started_at from run_registry order by run_id").to_string(index=False))
print("\n### same-session cross-run reuse opportunity ###")
a=q("select distinct instrument_id from dataset_registry where dataset_type='OPTION_CHAIN' and source_run_id='20260904_004338'")
b=q("select distinct instrument_id from dataset_registry where dataset_type='OPTION_CHAIN' and session_date='2026-09-03' and source_run_id<>'20260904_004338'")
print("904 instruments:", len(a), " other runs same session 2026-09-03:", len(b), " overlap:", len(set(a.instrument_id)&set(b.instrument_id)))
print("\n### the run that DID get exact hits: 20260829_222259 vs 20260829_100803 ###")
print(q("select source_run_id, session_date, count(*) n from dataset_registry where dataset_type='OPTION_CHAIN' and source_run_id in ('20260829_100803','20260829_222259','20260828_054947','20260828_094349') group by source_run_id, session_date").to_string(index=False))
print("\n### expires_at population ###")
print(q("select dataset_type, sum(case when expires_at is null then 1 else 0 end) null_exp, count(*) n from dataset_registry group by dataset_type").to_string(index=False))
print("\n### ledger reconciliation for 20260904_004338 ###")
print(q("""select
   (select count(*) from api_request_ledger where run_id='20260904_004338') total_rows,
   (select sum(physical_request_count) from api_request_ledger where run_id='20260904_004338') physical,
   (select count(*) from api_request_ledger where run_id='20260904_004338' and physical_request_count>0) fetch_rows,
   (select count(*) from api_request_ledger where run_id='20260904_004338' and reason='no fresh canonical coverage') resolve_rows,
   (select count(*) from dataset_registry where source_run_id='20260904_004338') registered
""").to_string(index=False))
