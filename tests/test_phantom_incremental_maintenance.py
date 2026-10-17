from pathlib import Path
import sqlite3,sys,json
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.phantom_database import PhantomDatabase
from scripts.phantom_maintenance import complete_greeks_and_queue_iv,drain_pending
from scripts.phantom_maintenance import session_health
import subprocess

def row(ticker='AAA',**kw):
    return dict(ticker=ticker,quote_date='2026-10-02',option_symbol=ticker+'261120C00100000',
      side='call',strike=100.,dte=49.,underlying_price=100.,bid=3.9,ask=4.1,mid=4.,
      source='marketdata.app',iv=None,delta=None,gamma=None,theta=None,vega=None,**kw)

def setup(tmp_path):
    path=tmp_path/'phantom.db'
    db=PhantomDatabase(path,ROOT); db.initialise()
    return db,path

def test_written_missing_greeks_complete_once_and_queue_exact_pair(tmp_path):
    db,path=setup(tmp_path); r=row('NAN')
    db.upsert_chain_rows([r])
    with sqlite3.connect(path) as c:
        values=c.execute('SELECT iv,delta,gamma,theta,vega,greeks_source FROM chain_snapshots').fetchone()
        assert all(v is not None for v in values[:5])
        assert values[5]=='COMPUTED_BS'
        assert c.execute('SELECT ticker,quote_date,status FROM phantom_maintenance_pairs').fetchone()==('NAN','2026-10-02','PENDING_IV')
        assert complete_greeks_and_queue_iv(c,[r])=={'changed':0,'computed':0}
        assert c.execute('SELECT COUNT(*) FROM options_greeks_history').fetchone()[0]==1

def test_vendor_complete_preserved_and_labelled(tmp_path):
    db,path=setup(tmp_path); r=row(); r.update(iv=.3,delta=.51,gamma=.02,theta=-.04,vega=.1)
    db.upsert_chain_rows([r])
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT iv,delta,greeks_source FROM chain_snapshots').fetchone()==(.3,.51,'MARKETDATA_VENDOR')
        assert c.execute('SELECT COUNT(*) FROM options_greeks_history').fetchone()[0]==0
        assert c.execute('SELECT greeks_quality FROM chain_snapshots').fetchone()[0]=='VENDOR_COMPLETE'

def test_provider_name_does_not_override_explicit_computed_field_lineage(tmp_path):
    db,path=setup(tmp_path); r=row()
    r.update(iv=.3,delta=.51,gamma=.02,theta=-.04,vega=.1,
      raw_json=json.dumps({'greeks_source':'COMPUTED_BS'}))
    db.upsert_chain_rows([r])
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT greeks_source FROM chain_snapshots').fetchone()[0]=='COMPUTED_BS'

def test_failure_reason_persists_and_missing_spot_is_not_filled(tmp_path):
    db,path=setup(tmp_path); r=row(); r['underlying_price']=None
    db.upsert_chain_rows([r])
    with sqlite3.connect(path) as c:
        spot,iv,reason=c.execute('SELECT underlying_price,iv,greeks_quality FROM chain_snapshots').fetchone()
        assert spot is None and iv is None
        assert 'missing_underlying_price' in reason
        lineage=c.execute('SELECT underlying_quality FROM phantom_row_lineage').fetchone()[0]
        assert lineage=='MISSING_OR_INVALID_NOT_FILLED'

def test_hook_does_not_commit_raw_ingestion_transaction(tmp_path):
    db,path=setup(tmp_path); r=row()
    c=sqlite3.connect(path)
    fields=','.join(r); marks=','.join('?' for _ in r)
    c.execute(f'INSERT INTO chain_snapshots({fields}) VALUES({marks})',list(r.values()))
    complete_greeks_and_queue_iv(c,[r]); c.rollback(); c.close()
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT COUNT(*) FROM chain_snapshots').fetchone()[0]==0

def test_iv_drain_is_bounded_and_idempotent(tmp_path):
    db,path=setup(tmp_path); db.upsert_chain_rows([row('AAA'),row('BBB')])
    cache=tmp_path/'iv.db'
    first=drain_pending(path,cache,max_pairs=1,min_free_gib=0)
    assert first['pairs']==1
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM phantom_maintenance_pairs WHERE status='PENDING_IV'").fetchone()[0]==1
    assert drain_pending(path,cache,max_pairs=1,min_free_gib=0)['pairs']==1
    assert drain_pending(path,cache,max_pairs=1,min_free_gib=0)['status']=='NO_PENDING_WORK'
    with sqlite3.connect(cache) as c:
        assert c.execute('SELECT COUNT(*) FROM iv_history').fetchone()[0]==2

def test_disk_guard_keeps_pending_receipt(tmp_path):
    db,path=setup(tmp_path); db.upsert_chain_rows([row()])
    with pytest.raises(RuntimeError,match='disk reserve'):
        drain_pending(path,tmp_path/'iv.db',min_free_gib=10**9)
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0]=='PENDING_IV'

def test_unknown_legacy_health_is_not_reported_as_zero_needs(tmp_path):
    db,path=setup(tmp_path); r=row()
    with sqlite3.connect(path) as c:
        c.execute('INSERT INTO chain_snapshots(ticker,quote_date,option_symbol) VALUES(?,?,?)',tuple(r[k] for k in ('ticker','quote_date','option_symbol')))
    health=session_health(path,'2026-10-02',['AAA'])
    assert health['state']=='NEEDS_AUDIT'
    assert health['needs_greeks_rows'] is None

def test_weekly_command_read_only_plan_then_bounded_local_execution(tmp_path):
    db,path=setup(tmp_path); r=row('NAN')
    with sqlite3.connect(path) as c:
        c.execute('INSERT INTO chain_snapshots('+','.join(r)+') VALUES('+','.join('?' for _ in r)+')',list(r.values()))
    roster=tmp_path/'roster.csv'; roster.write_text('ticker\nNAN\nSYM\n',encoding='utf-8')
    report=tmp_path/'report.json'; cache=tmp_path/'cache.db'
    command=[sys.executable,'-B',str(ROOT/'scripts/phantom_weekly_maintenance.py'),'--db-path',str(path),
      '--iv-cache-path',str(cache),'--universe-path',str(roster),'--sessions','2026-10-02','--report',str(report)]
    plan=subprocess.run(command,capture_output=True,text=True)
    assert plan.returncode==0,plan.stderr
    evidence=json.loads(report.read_text())
    assert evidence['provider_calls']==0
    assert evidence['sessions'][0]['missing_tickers']==['SYM']
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT iv FROM chain_snapshots').fetchone()[0] is None
    run=subprocess.run(command+['--execute-local','--max-local-pairs','1'],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    evidence=json.loads(report.read_text())
    assert evidence['provider_calls']==0
    assert evidence['health'][0]['known_needs_greeks_rows']==0
    assert sum(r['pairs'] for r in evidence['local_reports'])==1
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT iv,greeks_source FROM chain_snapshots').fetchone()[1]=='COMPUTED_BS'

@pytest.mark.parametrize('module_name',['run_phantom_backfill_parallel','phantom_greek_rehydrate'])
def test_other_write_helpers_complete_only_their_written_rows(tmp_path,module_name):
    import importlib
    helper=importlib.import_module('scripts.'+module_name)
    db,path=setup(tmp_path)
    with sqlite3.connect(path) as c:
        helper.upsert_chain_rows_conn(c,[row()])
        assert c.execute('SELECT COUNT(*) FROM options_greeks_history').fetchone()[0]==1
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0]=='PENDING_IV'

def test_quote_rehydration_does_not_invent_missing_chain_identity(tmp_path):
    from scripts.phantom_marketdata_quote_greek_rehydrate import update_row,init_schema
    db,path=setup(tmp_path)
    with sqlite3.connect(path) as c:
        init_schema(c)
        # Prior writes must not make a zero-row UPDATE look successful.
        c.execute("INSERT OR REPLACE INTO schema_meta VALUES('test','write')")
        r=row(); r.update(status='OK_FULL_GREEKS',values={'iv':.3,'delta':.5,'gamma':.02,'theta':-.03,'vega':.1},audit_key='TEST')
        assert update_row(c,r,False)==0
        assert c.execute('SELECT COUNT(*) FROM chain_snapshots').fetchone()[0]==0
