"""Offline reconciliation: preserve protected facts, expose partial commits."""
import json
import socket
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.phantom_database import PhantomDatabase
from scripts.phantom_maintenance import drain_pending, session_health
from scripts import finalize_phantom_weekly_snapshot as finalizer

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-11-25'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Network forbidden in saved-data tests')
    monkeypatch.setattr(socket, 'create_connection', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)


def fixture(tmp_path, names=('AAA', 'BBB'), missing_spot=False):
    db = PhantomDatabase(tmp_path/'phantom.db', ROOT)
    db.initialise()
    db.upsert_chain_rows([dict(ticker=t,quote_date=DAY,option_symbol=t+'261225C00100000',
        side='call',strike=100.,dte=30.,underlying_price=None if missing_spot else 100.,
        bid=3.,mid=3.1,ask=3.2,iv=.3,delta=.5,gamma=.02,theta=-.04,vega=.1,
        open_interest=10,volume=2,source='marketdata.app') for t in names])
    cache=tmp_path/'iv.db'
    with sqlite3.connect(cache) as c:
        c.execute('CREATE TABLE iv_history(ticker TEXT,sample_date TEXT,atm_iv REAL,source TEXT,updated_at TEXT,PRIMARY KEY(ticker,sample_date))')
        c.execute('CREATE TABLE iv_cache_meta(ticker TEXT PRIMARY KEY,last_full_build TEXT,last_refresh TEXT)')
    return db.db_path,cache


@pytest.mark.parametrize('source',['marketdata','UNKNOWN',None])
@pytest.mark.parametrize('prior',[.3,.4])
def test_preserves_full_vendor_row_and_metadata_continues_other_pair(tmp_path,source,prior):
    path,cache=fixture(tmp_path)
    with sqlite3.connect(cache) as c:
        c.execute('INSERT INTO iv_history VALUES(?,?,?,?,?)',('AAA',DAY,prior,source,'original'))
        c.execute("INSERT INTO iv_cache_meta VALUES('AAA','original-full','original-refresh')")
        before=c.execute("SELECT * FROM iv_history WHERE ticker='AAA'").fetchone()
    result=drain_pending(path,cache,min_free_gib=0)
    with sqlite3.connect(cache) as c:
        assert c.execute("SELECT * FROM iv_history WHERE ticker='AAA'").fetchone()==before
        assert c.execute("SELECT * FROM iv_cache_meta WHERE ticker='AAA'").fetchone()==('AAA','original-full','original-refresh')
        assert c.execute("SELECT atm_iv,source FROM iv_history WHERE ticker='BBB'").fetchone()==(.3,'phantom_history')
    with sqlite3.connect(path) as c:
        states=dict(c.execute('SELECT ticker,status FROM phantom_maintenance_pairs'))
        assert states=={'AAA':'COMPLETE' if prior==.3 else 'IV_CONFLICT','BBB':'COMPLETE'}
        if prior!=.3:
            conflict=json.loads(c.execute("SELECT last_error FROM phantom_maintenance_pairs WHERE ticker='AAA'").fetchone()[0])
            assert conflict['preserved_iv']==prior and conflict['derived_iv']==.3
    assert len(result['conflicts'])==int(prior!=.3)
    assert drain_pending(path,cache,min_free_gib=0)['status']=='NO_PENDING_WORK'
    if prior!=.3:
        assert session_health(path,DAY,['AAA','BBB'])['unresolved_iv_conflict_pairs']==1


def test_missing_derived_iv_preserves_vendor_and_flags_unresolved(tmp_path):
    path,cache=fixture(tmp_path,('AAA',),missing_spot=True)
    with sqlite3.connect(cache) as c:
        c.execute("INSERT INTO iv_history VALUES('AAA',?,.4673,'marketdata','original')",(DAY,))
    result=drain_pending(path,cache,min_free_gib=0)
    assert result['conflicts'][0]['reason']=='NO_QUALIFIED_DERIVED_IV'
    assert result['reports'][0]['queue_unavailable']==0
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT underlying_price FROM chain_snapshots').fetchone()[0] is None
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0]=='IV_CONFLICT'
    with sqlite3.connect(cache) as c:
        assert c.execute('SELECT atm_iv,source FROM iv_history').fetchone()==(.4673,'marketdata')


def test_cache_failure_reports_surface_commit_keeps_queue_pending(tmp_path,monkeypatch):
    path,cache=fixture(tmp_path)
    def fail(*a,**k):raise RuntimeError('injected cache failure')
    monkeypatch.setattr(finalizer,'_write_iv_cache',fail)
    with pytest.raises(RuntimeError) as caught:drain_pending(path,cache,min_free_gib=0)
    report=caught.value.drain_report
    assert report['failed_batch']['surface_committed'] is True
    assert report['failed_batch']['cache_committed'] is False
    assert report['failed_batch']['queue_acknowledged'] is False
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT count(*) FROM iv_surface_history').fetchone()[0]>0
        assert c.execute("SELECT count(*) FROM phantom_maintenance_pairs WHERE status='PENDING_IV'").fetchone()[0]==2


def test_later_batch_failure_retains_earlier_success(tmp_path,monkeypatch):
    path,cache=fixture(tmp_path,tuple(f'T{i:03}' for i in range(51)))
    original=finalizer._write_iv_cache
    calls=[]
    def fail_second(*a,**k):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('second batch failure')
        return original(*a,**k)
    monkeypatch.setattr(finalizer,'_write_iv_cache',fail_second)
    with pytest.raises(RuntimeError) as caught:drain_pending(path,cache,min_free_gib=0)
    assert caught.value.drain_report['reports'][0]['queue_complete']==50
    with sqlite3.connect(path) as c:
        assert dict(c.execute('SELECT status,count(*) FROM phantom_maintenance_pairs GROUP BY status'))=={'COMPLETE':50,'PENDING_IV':1}


def test_surface_failure_reports_no_commit(tmp_path):
    path,cache=fixture(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("CREATE TRIGGER stop_surface BEFORE INSERT ON iv_surface_history BEGIN SELECT RAISE(ABORT,'surface fail'); END")
    with pytest.raises(sqlite3.IntegrityError) as caught:drain_pending(path,cache,min_free_gib=0)
    partial=caught.value.drain_report['failed_batch']
    assert partial['surface_committed'] is False and partial['cache_committed'] is False
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT count(*) FROM iv_surface_history').fetchone()[0]==0


def test_queue_failure_reports_both_store_commits_and_retry_is_idempotent(tmp_path):
    path,cache=fixture(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("CREATE TRIGGER stop_queue BEFORE UPDATE ON phantom_maintenance_pairs BEGIN SELECT RAISE(ABORT,'queue fail'); END")
    with pytest.raises(sqlite3.IntegrityError) as caught:drain_pending(path,cache,min_free_gib=0)
    partial=caught.value.drain_report['failed_batch']
    assert partial['surface_committed'] is True and partial['cache_committed'] is True
    assert partial['queue_acknowledged'] is False
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT count(*) FROM phantom_maintenance_pairs WHERE status='PENDING_IV'").fetchone()[0]==2
        c.execute('DROP TRIGGER stop_queue')
    assert drain_pending(path,cache,min_free_gib=0)['reports'][0]['queue_complete']==2
    assert drain_pending(path,cache,min_free_gib=0)['status']=='NO_PENDING_WORK'
    with sqlite3.connect(cache) as c:assert c.execute('SELECT count(*) FROM iv_history').fetchone()[0]==2


def test_weekly_failure_writes_partial_report(tmp_path,monkeypatch):
    from scripts import phantom_weekly_maintenance as weekly
    path,cache=fixture(tmp_path)
    roster=tmp_path/'roster.csv';roster.write_text('ticker\nAAA\nBBB\n')
    report=tmp_path/'report.json'
    def fail(*a,**k):raise RuntimeError('injected cache failure')
    monkeypatch.setattr(finalizer,'_write_iv_cache',fail)
    with pytest.raises(RuntimeError):
        weekly.main(['--db-path',str(path),'--iv-cache-path',str(cache),'--universe-path',str(roster),
                     '--sessions',DAY,'--report',str(report),'--execute-local','--max-local-pairs','2'])
    saved=json.loads(report.read_text())
    assert saved['status']=='STOPPED_PARTIAL' and saved['provider_calls']==0
    assert saved['local_reports'][0]['failed_batch']['surface_committed'] is True


def test_weekly_success_exposes_conflict_not_complete(tmp_path):
    from scripts import phantom_weekly_maintenance as weekly
    path,cache=fixture(tmp_path)
    with sqlite3.connect(cache) as c:c.execute("INSERT INTO iv_history VALUES('AAA',?,.4,'marketdata','original')",(DAY,))
    roster=tmp_path/'roster.csv';roster.write_text('ticker\nAAA\nBBB\n')
    report=tmp_path/'report.json'
    assert weekly.main(['--db-path',str(path),'--iv-cache-path',str(cache),'--universe-path',str(roster),
                       '--sessions',DAY,'--report',str(report),'--execute-local','--max-local-pairs','2'])==0
    saved=json.loads(report.read_text())
    assert saved['status']=='COMPLETE_WITH_EXCLUSIONS'
    assert saved['iv_queue_statuses']['IV_CONFLICT']==1
    assert saved['iv_conflicts'][0]['ticker']=='AAA'
