import sys,json,sqlite3
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from scripts import phantom_provenance_labels as m

def row(**kw):
    d=dict(_rowid=1,ticker='ABC',quote_date='2026-10-16',option_symbol='ABC261120C00100000',
      source='MARKETDATA',greeks_source=None,greeks_quality=None,underlying_price=100,
      iv=.3,delta=.5,gamma=.02,theta=-.01,vega=.1)
    d['raw_json']=json.dumps({g:d[g] for g in m.GREEKS});d.update(kw);return d

def db_fixture(path,rows):
    c=sqlite3.connect(path)
    c.execute('CREATE TABLE chain_snapshots(ticker TEXT,quote_date TEXT,option_symbol TEXT,source TEXT,greeks_source TEXT,greeks_quality TEXT,raw_json TEXT,'+','.join(k+' REAL' for k in m.NUMERIC)+')')
    c.execute('CREATE TABLE options_greeks_history(ticker TEXT,snapshot_date TEXT,contract_symbol TEXT,quality_status TEXT)')
    for r in rows:
        r={k:v for k,v in r.items() if k!='_rowid'}
        c.execute('INSERT INTO chain_snapshots('+','.join(r)+') VALUES('+','.join('?' for _ in r)+')',list(r.values()))
    c.commit();return c

def test_vendor_requires_raw_matches():
    assert m.labels(row())[0]=='MARKETDATA_VENDOR'
    assert m.labels(row(raw_json='{}'))[0]=='EXISTING_UNVERIFIED'
    assert m.labels(row(raw_json='{invalid'))[0]=='EXISTING_UNVERIFIED'

def test_explicit_computed_hint_wins():
    r=row();raw=json.loads(r['raw_json']);raw['greeks_source']='COMPUTED_BS';r['raw_json']=json.dumps(raw)
    assert m.labels(r)[0]!='MARKETDATA_VENDOR'

def test_untried_is_not_unsolvable_and_no_spot_fill():
    r=row(iv=None,underlying_price=None)
    s,q,u=m.labels(r)
    assert q=='INCOMPLETE_UNASSESSED_NO_SOLVER_RECORD' and u=='MISSING_OR_INVALID_NOT_FILLED'
    assert r['underlying_price'] is None
    assert m.labels(r,{'quality_status':'BELOW_NO_ARB'})[1]=='HISTORY_BELOW_NO_ARB'
    assert m.labels(r,{'quality_status':'OK'})[1]=='HISTORY_OK_CHAIN_INCOMPLETE'

def test_existing_labels_preserved():
    assert m.labels(row(greeks_source='COMPUTED_BS',greeks_quality='KNOWN'))[:2]==('COMPUTED_BS','KNOWN')

def test_dry_run_no_database_mutation(tmp_path):
    p=tmp_path/'db.sqlite';c=db_fixture(p,[row()]);c.close();before=p.read_bytes()
    result=m.correct(p,execute=False,max_rows=3)
    assert result['provider_calls']==0 and p.read_bytes()==before

def test_execute_preserves_numbers_and_journals_preimage(tmp_path):
    p=tmp_path/'db.sqlite';c=db_fixture(p,[row()]);c.close()
    result=m.correct(p,execute=True,max_rows=3)
    c=sqlite3.connect(p);labels=c.execute('SELECT greeks_source,greeks_quality FROM chain_snapshots').fetchone()
    assert labels==('MARKETDATA_VENDOR','VENDOR_COMPLETE') and result['status']=='COMPLETE'
    assert c.execute('SELECT iv,underlying_price FROM chain_snapshots').fetchone()==(.3,100)
    assert c.execute('SELECT old_source,old_quality FROM phantom_provenance_label_audit').fetchone()==(None,None)

def test_bounded_resume_idempotent(tmp_path):
    p=tmp_path/'db.sqlite';c=db_fixture(p,[row(),row(ticker='DEF',option_symbol='DEF')]);c.close()
    assert m.correct(p,execute=True,max_rows=1)['status']=='BATCH_LIMIT'
    r=m.correct(p,execute=True,max_rows=5)
    assert r['scanned']==2 and r['vendor_labelled']==2
    assert m.correct(p,execute=True,max_rows=5)['vendor_labelled']==2

def test_transaction_rollback_keeps_labels_and_audit_atomic(tmp_path):
    p=tmp_path/'db.sqlite';c=db_fixture(p,[row()]);m.ensure_schema(c);c.commit()
    c.execute('BEGIN');m.apply_batch(c,[row()]);c.rollback()
    assert c.execute('SELECT greeks_source FROM chain_snapshots').fetchone()[0] is None
    assert c.execute('SELECT COUNT(*) FROM phantom_provenance_label_audit').fetchone()[0]==0

def test_disk_guard_no_label_changes(tmp_path):
    p=tmp_path/'db.sqlite';c=db_fixture(p,[row()]);c.close()
    with pytest.raises(RuntimeError,match='DISK'):m.correct(p,execute=True,max_rows=3,min_free_gib=1000000)
    assert sqlite3.connect(p).execute('SELECT greeks_source FROM chain_snapshots').fetchone()[0] is None

def test_weekly_scope_and_limit(tmp_path):
    p=tmp_path/'db.sqlite';c=db_fixture(p,[row(),row(ticker='DEF',option_symbol='DEF'),row(ticker='OLD',quote_date='2025-01-02')]);c.close()
    result=m.repair_sessions(p,['2026-10-16'],['ABC','DEF'],max_rows=1)
    assert result['status']=='BATCH_LIMIT_REMAINDER_UNASSESSED' and result['scanned']==1
    c=sqlite3.connect(p)
    assert c.execute("SELECT greeks_source FROM chain_snapshots WHERE ticker='OLD'").fetchone()[0] is None

def test_weekly_provenance_health_is_scoped(tmp_path):
    from phantom_weekly_maintenance import provenance_health
    p=tmp_path/'health.sqlite'
    c=db_fixture(p,[row(),row(ticker='OLD',quote_date='2025-01-02')])
    health=provenance_health(c,'2026-10-16',['ABC','NAN','SYM'])
    assert health['rows']==1 and health['blank_source']==1 and not health['labels_complete']
    c.execute("UPDATE chain_snapshots SET greeks_source='MARKETDATA_VENDOR',greeks_quality='VENDOR_COMPLETE' WHERE ticker='ABC'")
    assert provenance_health(c,'2026-10-16',['ABC'])['labels_complete']

def test_weekly_remainder_survives_into_next_week(tmp_path):
    p=tmp_path/'queue.sqlite';c=db_fixture(p,[row(),row(ticker='DEF',option_symbol='DEF')]);c.close()
    first=m.repair_sessions(p,['2026-10-16'],['ABC','DEF'],max_rows=1)
    assert first['pending_sessions']==['2026-10-16']
    next_week=m.repair_sessions(p,['2026-10-23'],['ABC','DEF'],max_rows=10)
    assert next_week['pending_sessions']==[]
    c=sqlite3.connect(p)
    assert c.execute("SELECT COUNT(*) FROM chain_snapshots WHERE greeks_source IS NULL").fetchone()[0]==0
