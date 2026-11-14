"""Exact missing contracts only; one unchanged cumulative budget and no overwrites."""
import importlib.util
import json
import sqlite3
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[1]
PATH=ROOT/'Enhancements/phase0/phantom_named_contract_supplement_20261113.py'
spec=importlib.util.spec_from_file_location('supplement',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def target(ticker='AAL',day='2026-10-20',symbol='AAL270115P00012000'):
    return {'ticker':ticker,'day':day,'symbol':symbol}

def payload(t=None):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    t=t or target()
    return {'s':'ok','optionSymbol':[t['symbol']],
        'updated':[int(datetime.fromisoformat(t['day']+'T16:00:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp())],
        'bid':[1.0],'ask':[1.2],'mid':[1.1],'underlyingPrice':[12.5]}

def test_only_explicit_missing_entry_dates_not_november_12():
    m.check_target(target())
    with pytest.raises(ValueError):m.check_target(target(day='2026-11-12'))
    with pytest.raises(ValueError):m.check_target(target(day='2026-10-13'))

def test_named_quote_uses_occ_identity_without_inventing_underlying_price():
    p=payload();p['underlyingPrice']=[None]
    row=m.normalize_quote(p,target())
    assert row['option_symbol']=='AAL270115P00012000'
    assert row['side']=='put' and row['strike']==12 and row['dte']==87
    assert row['underlying_price'] is None
    assert json.loads(row['raw_json'])['static_identity_policy']=='EXACT_OCC_DECODE_NOT_PRICE_IMPUTATION'

def test_wrong_contract_mapping_or_quote_date_is_not_ingested():
    p=payload();p['optionSymbol']=['AAL270115P00013000']
    with pytest.raises(m.g.MappingFailure):m.normalize_quote(p,target())
    p=payload();p['underlying']=['OTHER']
    with pytest.raises(m.g.MappingFailure):m.normalize_quote(p,target())
    p=payload();p['updated']=[0]
    with pytest.raises(RuntimeError,match='DATE'):m.normalize_quote(p,target())

def test_quote_reuses_saved_receipt_and_shared_cap_across_old_and_new_dates(tmp_path):
    b=m.g.Budget(tmp_path,2,allowed_days=m.ALLOWED_DAYS)
    b.reserve('old','SPY','2026-11-09',0)
    class R:
        status_code=200;headers={'X-Api-Ratelimit-Consumed':'1'}
        def json(self):return payload()
    class S:
        calls=0
        def get(self,*a,**k):self.calls+=1;return R()
    s=S();m.fetch_quote(s,b,target())
    m.fetch_quote(s,m.g.Budget(tmp_path,2,allowed_days=m.ALLOWED_DAYS),target())
    assert s.calls==1
    with pytest.raises(RuntimeError,match='CAP'):
        m.fetch_quote(s,m.g.Budget(tmp_path,2,allowed_days=m.ALLOWED_DAYS),target('BILI','2026-10-14','BILI270115P00015000'))
    assert s.calls==1

def setup_store(tmp_path):
    from scripts.phantom_database import PhantomDatabase
    from scripts.phantom_maintenance import ensure_schema
    db=tmp_path/'phantom.db';PhantomDatabase(db,ROOT).initialise()
    with sqlite3.connect(db) as c:ensure_schema(c)
    return db

def test_supplement_to_existing_pair_preserves_every_existing_chain_value(tmp_path):
    db=setup_store(tmp_path)
    old=m.normalize_quote(payload(),target())
    old['option_symbol']='AAL261120P00012000';old['iv']=.333;old['delta']=-.25
    with sqlite3.connect(db) as c:
        cols=list(old);c.execute('INSERT INTO chain_snapshots('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',list(old.values()))
    before=m.existing_hash(db,'AAL','2026-10-20',{'AAL270115P00012000'})
    new=m.normalize_quote(payload(),target());assert m.insert_exact(db,[new])==1
    assert m.existing_hash(db,'AAL','2026-10-20',{'AAL270115P00012000'})==before
    assert m.insert_exact(db,[new])==0
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT iv,delta FROM chain_snapshots WHERE option_symbol='AAL261120P00012000'").fetchone()==(.333,-.25)
        assert c.execute("SELECT COUNT(*) FROM chain_snapshots").fetchone()[0]==2

def test_default_old_budget_cannot_silently_accept_expanded_dates(tmp_path):
    b=m.g.Budget(tmp_path,2,allowed_days=m.ALLOWED_DAYS)
    b.reserve('new','BILI','2026-10-14',0)
    with pytest.raises(RuntimeError,match='date outside scope'):m.g.Budget(tmp_path,2)


def test_derived_iv_never_replaces_existing_cache_or_surface_values(tmp_path):
    db=setup_store(tmp_path);m.insert_exact(db,[m.normalize_quote(payload(),target())])
    cache=tmp_path/'iv.db'
    with sqlite3.connect(cache) as c:
        c.execute('CREATE TABLE iv_history(ticker,sample_date,atm_iv,source,updated_at,PRIMARY KEY(ticker,sample_date))')
        c.execute('CREATE TABLE iv_cache_meta(ticker PRIMARY KEY,last_full_build,last_refresh)')
        c.execute("INSERT INTO iv_history VALUES('AAL','2026-10-20',.123,'original','original')")
        c.execute("INSERT INTO iv_cache_meta VALUES('AAL','full','2026-11-12')")
    first=m.derive_preserving(db,cache,'AAL','2026-10-20')
    assert first['cache_preservation_flag']['existing_atm_iv']==.123
    with sqlite3.connect(db) as c:
        before=c.execute("SELECT * FROM iv_surface_history WHERE ticker='AAL'").fetchall()
        assert before
    m.derive_preserving(db,cache,'AAL','2026-10-20')
    with sqlite3.connect(db) as c:assert c.execute("SELECT * FROM iv_surface_history WHERE ticker='AAL'").fetchall()==before
    with sqlite3.connect(cache) as c:
        assert c.execute('SELECT * FROM iv_history').fetchone()==('AAL','2026-10-20',.123,'original','original')
        assert c.execute('SELECT * FROM iv_cache_meta').fetchone()==('AAL','full','2026-11-12')


def test_deferred_day_cannot_be_added_even_to_expanded_budget(tmp_path):
    with pytest.raises(ValueError,match='deferred'):
        m.g.Budget(tmp_path,30000,allowed_days=m.ALLOWED_DAYS|{'2026-11-12'})


def test_explicit_option_symbol_error_is_mapping_skip_not_batch_failure():
    assert m.g.is_symbol_error({'http':400,'data':{'errmsg':'Invalid option symbol'}})
    assert not m.g.is_symbol_error({'http':401,'data':{'errmsg':'Invalid option symbol'}})
