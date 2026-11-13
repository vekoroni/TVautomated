"""ACK 13 Nov: hard cumulative cap, saved reuse, immutable captured chains."""
import importlib.util
from pathlib import Path
import sqlite3
import json
import pytest

PATH=Path(__file__).parents[1]/'Enhancements/phase0/guarded_phantom_backfill.py'
spec=importlib.util.spec_from_file_location('guarded_phantom_backfill',PATH)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

def test_only_the_two_approved_sessions_can_execute():
    assert g.checked_days('2026-10-20,2026-11-09')==list(g.DAYS)
    with pytest.raises(ValueError):g.checked_days('2026-11-12')

def test_complete_roster_keeps_literal_nan_and_sym(tmp_path):
    p=tmp_path/'roster.csv';p.write_text('ticker\nNAN\nSYM\nAAPL\n')
    assert g.roster(p)==['AAPL','NAN','SYM']

def test_budget_is_shared_across_sessions_and_never_renews(tmp_path):
    budget=g.Budget(tmp_path,2)
    budget.reserve('a','AAPL',g.DAYS[0],0)
    budget.reserve('b','AAPL',g.DAYS[1],0)
    with pytest.raises(RuntimeError,match='CAP'):budget.reserve('c','SPY',g.DAYS[1],0)
    with pytest.raises(RuntimeError,match='UNCERTAIN'):g.Budget(tmp_path,2).reserve('a','AAPL',g.DAYS[0],0)
    with pytest.raises(RuntimeError,match='CAP_CHANGED'):g.Budget(tmp_path,3)

def test_saved_response_is_reused_without_a_network_call(tmp_path):
    b=g.Budget(tmp_path,2)
    class Response:
        status_code=200;headers={'X-Api-Ratelimit-Consumed':'1'}
        def json(self):return {'s':'no_data'}
    class Session:
        calls=0
        def get(self,*args,**kwargs):self.calls+=1;return Response()
    session=Session()
    assert g.get_page(session,b,'AAPL',g.DAYS[0],0)['s']=='no_data'
    assert g.get_page(session,g.Budget(tmp_path,2),'AAPL',g.DAYS[0],0)['s']=='no_data'
    assert session.calls==1 and len(b.records)==1


def test_summary_lock_retries_only_local_replace_without_repeating_paid_request(tmp_path,monkeypatch):
    original=g.os.replace;calls=[]
    def locked_once(source,target):
        calls.append(str(target))
        if len(calls)==2:
            error=PermissionError('Windows sharing lock');error.winerror=5;raise error
        return original(source,target)
    monkeypatch.setattr(g.os,'replace',locked_once)
    monkeypatch.setattr(g.time,'sleep',lambda seconds:None)
    class Response:
        status_code=200;headers={'X-Api-Ratelimit-Consumed':'1'}
        def json(self):return {'s':'no_data'}
    class Session:
        calls=0
        def get(self,*a,**k):self.calls+=1;return Response()
    session=Session();budget=g.Budget(tmp_path,2)
    g.get_page(session,budget,'AAPL',g.DAYS[0],0)
    g.get_page(session,g.Budget(tmp_path,2),'AAPL',g.DAYS[0],0)
    assert session.calls==1
    assert json.loads((tmp_path/'BUDGET.json').read_text())['unresolved_reservations']==0


def test_persistent_windows_lock_stops_with_old_summary_intact(tmp_path,monkeypatch):
    path=tmp_path/'summary.json';g.save(path,{'original':True})
    attempts=[]
    def locked(source,target):
        attempts.append(1);error=PermissionError('persistent lock');error.winerror=32;raise error
    monkeypatch.setattr(g.os,'replace',locked)
    monkeypatch.setattr(g.time,'sleep',lambda seconds:None)
    with pytest.raises(PermissionError):g.save(path,{'new':True})
    assert len(attempts)==6
    assert json.loads(path.read_text())=={'original':True}


def test_non_sharing_filesystem_error_is_not_retried(tmp_path,monkeypatch):
    calls=[]
    def failed(source,target):
        calls.append(1);raise OSError('disk I/O failure')
    monkeypatch.setattr(g.os,'replace',failed)
    with pytest.raises(OSError):g.save(tmp_path/'summary.json',{})
    assert len(calls)==1


@pytest.mark.skipif(g.os.name!='nt',reason='Real Windows sharing semantics')
def test_real_windows_reader_lock_releases_and_atomic_save_succeeds(tmp_path):
    import ctypes
    import threading
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
        ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    path=tmp_path/'locked.json';g.save(path,{'original':True})
    handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
    assert handle!=ctypes.c_void_p(-1).value
    timer=threading.Timer(.15,lambda:kernel.CloseHandle(handle));timer.start()
    try:g.save(path,{'new':True})
    finally:timer.join()
    assert json.loads(path.read_text())=={'new':True}

@pytest.mark.parametrize('status',[401,429,500])
def test_provider_systemic_errors_stop_without_retry(tmp_path,status):
    b=g.Budget(tmp_path,5)
    class R:
        status_code=status;headers={'X-Api-Ratelimit-Consumed':'1'}
        def json(self):return {'s':'error','errmsg':'test failure'}
    class S:
        calls=0
        def get(self,*a,**k):self.calls+=1;return R()
    s=S()
    with pytest.raises(RuntimeError):g.get_page(s,b,'AAPL',g.DAYS[0],0)
    assert s.calls==1 and list(b.records.values())[0]['status']=='RECEIVED'

def test_explicit_mapping_failure_is_local_but_auth_is_not():
    assert g.is_symbol_error({'http':404,'data':{'errmsg':'Unknown symbol'}})
    assert not g.is_symbol_error({'http':401,'data':{'errmsg':'Unknown symbol'}})
    with pytest.raises(g.MappingFailure):g.check_identity('BH.A','BHA','BHA261120C00010000')
    g.check_identity('BRK.B','BRKB','BRKB261120C00010000')

def test_insert_only_guard_protects_existing_rows_and_other_dates(tmp_path):
    p=tmp_path/'db.sqlite';c=sqlite3.connect(p)
    c.execute('CREATE TABLE chain_snapshots(ticker,quote_date,option_symbol,iv,PRIMARY KEY(ticker,quote_date,option_symbol))')
    c.execute("INSERT INTO chain_snapshots VALUES('OLD','2026-11-12','OLD261218C00010000',.2)")
    c.commit()
    g.install_chain_guard(c,[('NEW',g.DAYS[0],'NEW261218C00010000')])
    with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE chain_snapshots SET iv=.9 WHERE ticker='OLD'")
    with pytest.raises(sqlite3.IntegrityError):c.execute("DELETE FROM chain_snapshots WHERE ticker='OLD'")
    with pytest.raises(sqlite3.IntegrityError):c.execute("INSERT INTO chain_snapshots VALUES('BAD','2026-11-12','BAD',.1)")
    assert c.execute("SELECT iv FROM chain_snapshots WHERE ticker='OLD'").fetchone()==(.2,)
    c.close()

def test_header_charge_cannot_be_ignored(tmp_path):
    b=g.Budget(tmp_path,3)
    class R:
        status_code=200;headers={'X-Api-Ratelimit-Consumed':'2'}
        def json(self):return {'s':'no_data'}
    class S:
        def get(self,*a,**k):return R()
    with pytest.raises(RuntimeError,match='CHARGE'):g.get_page(S(),b,'AAPL',g.DAYS[0],0)
    assert len(b.records)==1

def test_legacy_runbook_delegates_instead_of_resetting_a_cap():
    import ast
    tree=ast.parse((PATH.parent/'backfill_runbook.py').read_text(encoding='utf-8-sig'))
    main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main')
    assert 'guarded_phantom_backfill' in ast.unparse(main)

def test_no_data_and_scope_are_preserved():
    p=g.params(g.DAYS[0],0)
    assert p['from']=='2026-10-27' and p['to']=='2026-12-19'
    assert p['limit']==1000 and p['nonstandard']=='false'

def setup_store(tmp_path):
    from scripts.phantom_database import PhantomDatabase
    from scripts.phantom_maintenance import ensure_schema
    db=tmp_path/'phantom.db';PhantomDatabase(db,PATH.parents[2]).initialise()
    with sqlite3.connect(db) as c:ensure_schema(c)
    cache=tmp_path/'cache.db'
    with sqlite3.connect(cache) as c:
        c.execute('CREATE TABLE iv_history(ticker,sample_date,atm_iv,source,updated_at,PRIMARY KEY(ticker,sample_date))')
        c.execute('CREATE TABLE iv_cache_meta(ticker PRIMARY KEY,last_full_build,last_refresh)')
        c.execute("INSERT INTO iv_cache_meta VALUES('NAN','old-full','2026-11-12')")
    return db,cache

def sample_row(ticker='NAN',day=g.DAYS[0],spot=100):
    return dict(ticker=ticker,quote_date=day,option_symbol=ticker+'261120C00100000',
        side='call',strike=100.,dte=31.,underlying_price=spot,bid=3.9,ask=4.1,mid=4.,
        open_interest=10,volume=2,source='marketdata.app',iv=None,delta=None,gamma=None,theta=None,vega=None,
        raw_json=json.dumps({'backfill_job':g.JOB}))

def test_exact_new_pair_gets_greeks_and_iv_without_draining_other_dates(tmp_path):
    db,cache=setup_store(tmp_path)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO phantom_maintenance_pairs(ticker,quote_date,status,updated_at_utc) VALUES('OLD','2026-10-02','PENDING_IV','original')")
    r=sample_row();assert g.insert_pair(db,[r])==1
    out=g.derive_pair(db,cache,'NAN',g.DAYS[0]);assert out['state']=='COMPLETE'
    receipt={'ticker':'NAN','session':g.DAYS[0],'status':'OK','rows':1,'chain_sha256':g.pair_hash(db,'NAN',g.DAYS[0])}
    assert g.verify_quality(db,cache,[receipt])['incomplete_without_quality']==0
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT status,updated_at_utc FROM phantom_maintenance_pairs WHERE ticker='OLD'").fetchone()==('PENDING_IV','original')
        assert all(x is not None for x in c.execute("SELECT iv,delta,gamma,theta,vega FROM chain_snapshots WHERE ticker='NAN'").fetchone())
    with sqlite3.connect(cache) as c:
        assert c.execute("SELECT * FROM iv_cache_meta WHERE ticker='NAN'").fetchone()==('NAN','old-full','2026-11-12')
    before=g.pair_hash(db,'NAN',g.DAYS[0])
    with pytest.raises(RuntimeError,match='existing captures preserved'):g.insert_pair(db,[{**r,'mid':999}])
    assert g.pair_hash(db,'NAN',g.DAYS[0])==before

def test_unavailable_underlying_is_flagged_not_invented(tmp_path):
    db,cache=setup_store(tmp_path);r=sample_row('SYM',spot=None)
    g.insert_pair(db,[r]);assert g.derive_pair(db,cache,'SYM',g.DAYS[0])['state']=='IV_UNAVAILABLE'
    with sqlite3.connect(db) as c:
        spot,iv,quality=c.execute("SELECT underlying_price,iv,greeks_quality FROM chain_snapshots WHERE ticker='SYM'").fetchone()
        assert spot is None and iv is None and 'missing_underlying_price' in quality

def test_plan_does_not_modify_a_store_or_create_receipts(tmp_path):
    db,cache=setup_store(tmp_path);before=db.read_bytes()
    result=g.make_plan(db,['NAN','SYM'])
    assert [len(r['missing']) for r in result]==[2,2]
    assert db.read_bytes()==before
    assert not list(tmp_path.glob('*BUDGET*'))


def test_approved_vici_conflict_preserves_cache_and_exposes_discrepancy(tmp_path):
    db,cache=setup_store(tmp_path)
    g.insert_pair(db,[sample_row('VICI')])
    saved=.22746940176152292
    with sqlite3.connect(cache) as c:
        c.execute("INSERT INTO iv_history VALUES('VICI',?,?, 'marketdata','original')",(g.DAYS[0],saved))
    result=g.derive_pair(db,cache,'VICI',g.DAYS[0])
    assert result['state']=='COMPLETE'
    with sqlite3.connect(cache) as c:
        assert c.execute("SELECT atm_iv,source,updated_at FROM iv_history WHERE ticker='VICI'").fetchone()==(saved,'marketdata','original')
    receipt={'ticker':'VICI','session':g.DAYS[0],'status':'OK','rows':1,'chain_sha256':g.pair_hash(db,'VICI',g.DAYS[0])}
    quality=g.verify_quality(db,cache,[receipt])
    assert quality['pending_iv']==0
    assert quality['iv_cache_discrepancies'][0]['existing_atm_iv']==saved
    assert quality['iv_cache_discrepancies'][0]['ticker']=='VICI'


def test_unapproved_cache_conflict_still_stops(tmp_path):
    db,cache=setup_store(tmp_path)
    g.insert_pair(db,[sample_row('NAN')])
    with sqlite3.connect(cache) as c:
        c.execute("INSERT INTO iv_history VALUES('NAN',?,.01,'marketdata','original')",(g.DAYS[0],))
    with pytest.raises(RuntimeError,match='PRE_EXISTING_IV_CACHE_CONFLICT_PRESERVED'):
        g.derive_pair(db,cache,'NAN',g.DAYS[0])
