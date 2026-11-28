"""US-options mark/boundary/benchmark regressions; no network or live writes."""
from copy import deepcopy
from datetime import datetime, timezone
import json, math, sqlite3, subprocess, sys
from pathlib import Path
import pandas as pd
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from scripts.compute_greeks_bs import choose_market_price,compute_greeks_from_row
from scripts.phantom_option_quality import benchmark_mask
from scripts.finalize_phantom_weekly_snapshot import _surface_and_atm,derive_iv_history,entropy
from scripts.finalize_phantom_weekly_snapshot import _write_iv_cache
from scripts.phantom_database import PhantomDatabase

def row(**updates):
    value=dict(ticker='AAA',quote_date='2026-11-20',option_symbol='AAA261218C00100000',side='call',
        expiration_ts=1797627600,strike=100.,underlying_price=100.,dte=28.,bid=2.9,ask=3.1,mid=3.,last=3.,
        updated_ts=1795208400,iv=.3,delta=.5,gamma=.02,theta=-.03,vega=.1,
        source='marketdata.app',greeks_quality='VENDOR_COMPLETE',open_interest=3,volume=1)
    value.update(updates);return value

@pytest.mark.parametrize('change,reason',[
    ({'bid':4.,'ask':2.},'CROSSED_QUOTE'),({'mid':9.},'MID_OUTSIDE_SPREAD'),
    ({'bid':0.},'ONE_SIDED_OR_EMPTY_QUOTE'),({'bid':-1.},'NEGATIVE_QUOTE'),
    ({'bid':None},'MISSING_BID_ASK'),({'ask':float('inf')},'MISSING_BID_ASK'),
    ({'updated_ts':1795122000},'QUOTE_SESSION_MISMATCH'),({'updated_ts':'bad'},'INVALID_QUOTE_TIMESTAMP'),
    ({'underlying_updated_ts':1795122000},'UNDERLYING_SESSION_MISMATCH')])
def test_invalid_quote_never_replaced_with_last_or_ask(change,reason):
    record=row(**change);before=deepcopy(record)
    price,source,flags=choose_market_price(record)
    assert price is None and source=='none' and reason in flags
    assert record==before
    assert compute_greeks_from_row(record).iv is None

def test_missing_leg_clock_remains_unverified_not_fabricated():
    price,_,flags=choose_market_price(row())
    assert price==3. and 'QUOTE_UNDERLYING_ALIGNMENT_UNVERIFIED' in flags

def test_mid_rebuild_requires_two_sided_quote_and_preserves_raw():
    record=row(mid=None);before=deepcopy(record)
    assert choose_market_price(record)[:2]==(3.,'bid_ask_mid')
    assert record==before
    assert choose_market_price(row(mid=0,bid=0,ask=0,last=99))[0] is None

@pytest.mark.parametrize('record,status',[
    (row(underlying_price=105,bid=5.1,ask=5.3,mid=5.2),'PRICE_BELOW_NO_ARB'),
    (row(bid=99.9,ask=100.3,mid=100.1),'PRICE_ABOVE_NO_ARB'),
    (row(side='put',option_symbol='AAA261218P00100000',bid=.000001,ask=.000001,mid=.000001),'BOUNDARY_IV_NON_IDENTIFIABLE')])
def test_observed_price_is_not_clipped_to_create_iv(record,status):
    before=deepcopy(record);answer=compute_greeks_from_row(record)
    assert answer.quality_status==status
    assert all(getattr(answer,g) is None for g in ('iv','delta','gamma','theta','vega'))
    assert answer.market_price==record['mid'] and record==before

def test_iv_mask_rejects_extremes_boundary_and_invalid_quotes_without_mutation():
    frame=pd.DataFrame([row(),row(iv=0),row(iv=6),row(iv=float('inf')),
        row(iv=.4,greeks_quality='OK_ADJUSTED_NO_ARB'),row(bid=0),row(mid=7),row(underlying_price=None)])
    before=frame.copy(deep=True)
    assert benchmark_mask(frame).tolist()==[True,False,False,False,False,False,False,False]
    pd.testing.assert_frame_equal(before,frame)

def sample():
    return [row(option_symbol='AAA261218C0010000'+str(i),iv=iv,greeks_quality=quality)
        for i,(iv,quality) in enumerate([(.2,'VENDOR_COMPLETE'),(.4,'OK'),(9,'VENDOR_COMPLETE'),(0,'OK_ADJUSTED_NO_ARB'),(.25,'OK_ADJUSTED_NO_ARB')])]

def test_surface_statistics_and_cache_share_eligibility_preserve_raw_population():
    frame=pd.DataFrame(sample());before=frame.copy(deep=True)
    surface,atm=_surface_and_atm(frame,'2026-11-20','fixture')
    assert surface[0][4]==5 and surface[0][6]==pytest.approx(.3)
    assert surface[0][7]==pytest.approx(entropy(pd.Series([.2,.4])))
    assert surface[0][5]==.2 and atm.iloc[0]['iv']==.2
    pd.testing.assert_frame_equal(before,frame)

def test_bounded_and_cli_derivation_match_and_leave_vendor_numbers_unchanged(tmp_path):
    path=tmp_path/'phantom.db';db=PhantomDatabase(path,ROOT);db.initialise()
    # Insert archived fixtures directly; this is a benchmark derivation test,
    # not an ingestion test that relabels supplied Greeks as vendor complete.
    with sqlite3.connect(path) as c:
        from scripts.options_db_writer import ensure_computed_greeks_schema
        ensure_computed_greeks_schema(c)
        for record in sample():
            c.execute('INSERT INTO chain_snapshots('+','.join(record)+') VALUES('+','.join('?' for _ in record)+')',list(record.values()))
        before=c.execute('SELECT * FROM chain_snapshots ORDER BY option_symbol').fetchall()
    direct=derive_iv_history(path,tmp_path/'iv.db','2026-11-20',['AAA'],execute=False)
    report=tmp_path/'report.json'
    run=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/finalize_phantom_weekly_snapshot.py'),
        '--db-path',str(path),'--iv-cache-path',str(tmp_path/'iv.db'),'--quote-date','2026-11-20',
        '--expected-rows','5','--report',str(report)],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    other=json.loads(report.read_text())
    assert direct['surface_rows']==other['surface_rows'] and direct['iv_cache_rows']==other['iv_cache_rows']==1
    with sqlite3.connect(tmp_path/'iv.db') as c:
        c.execute('CREATE TABLE iv_history(ticker TEXT,sample_date TEXT,atm_iv REAL,source TEXT,updated_at TEXT,PRIMARY KEY(ticker,sample_date))')
        c.execute('CREATE TABLE iv_cache_meta(ticker TEXT PRIMARY KEY,last_full_build TEXT,last_refresh TEXT)')
    derive_iv_history(path,tmp_path/'iv.db','2026-11-20',['AAA'],execute=True)
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT * FROM chain_snapshots ORDER BY option_symbol').fetchall()==before
        assert c.execute('SELECT median_iv FROM iv_surface_history').fetchone()[0]==pytest.approx(.3)
    with sqlite3.connect(tmp_path/'iv.db') as c:
        assert c.execute('SELECT atm_iv FROM iv_history').fetchone()[0]==.2
        c.execute("UPDATE iv_history SET source='MARKETDATA_VENDOR',updated_at='original'")
    execute=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/finalize_phantom_weekly_snapshot.py'),
        '--db-path',str(path),'--iv-cache-path',str(tmp_path/'iv.db'),'--quote-date','2026-11-20',
        '--expected-rows','5','--report',str(report),'--execute'],capture_output=True,text=True)
    assert execute.returncode==0,execute.stderr
    with sqlite3.connect(tmp_path/'iv.db') as c:
        assert c.execute('SELECT atm_iv,source,updated_at FROM iv_history').fetchone()==(.2,'MARKETDATA_VENDOR','original')
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT * FROM chain_snapshots ORDER BY option_symbol').fetchall()==before

def test_failed_solve_preserves_partial_vendor_greeks(tmp_path):
    path=tmp_path/'phantom.db';db=PhantomDatabase(path,ROOT);db.initialise()
    record=row(bid=0,iv=.33,delta=None,gamma=None,theta=None,vega=None)
    record.pop('greeks_quality')
    db.upsert_chain_rows([record])
    with sqlite3.connect(path) as c:
        found=c.execute('SELECT iv,delta,bid,mid,greeks_quality FROM chain_snapshots').fetchone()
        assert found[:4]==(.33,None,0,3.)
        assert 'ONE_SIDED_OR_EMPTY_QUOTE' in found[4]

def test_all_ineligible_bucket_remains_visible_with_no_iv_statistics():
    frame=pd.DataFrame([row(iv=0,greeks_quality='OK_ADJUSTED_NO_ARB')])
    surface,atm=_surface_and_atm(frame,'2026-11-20','fixture')
    assert surface[0][4]==1 and surface[0][5] is None and surface[0][6] is None
    assert atm.empty

def test_exact_contract_ties_are_independent_of_database_read_order():
    frame=pd.DataFrame(sample())
    a,ai=_surface_and_atm(frame,'2026-11-20','fixture')
    b,bi=_surface_and_atm(frame.iloc[::-1],'2026-11-20','fixture')
    assert a==b
    pd.testing.assert_frame_equal(ai.reset_index(drop=True),bi.reset_index(drop=True))

def test_successful_computed_labels_retain_model_and_timing_qualifications(tmp_path):
    path=tmp_path/'phantom.db';db=PhantomDatabase(path,ROOT);db.initialise()
    record=row(iv=None,delta=None,gamma=None,theta=None,vega=None)
    record.pop('greeks_quality')
    db.upsert_chain_rows([record])
    with sqlite3.connect(path) as c:
        quality=c.execute('SELECT greeks_quality FROM chain_snapshots').fetchone()[0]
        assert quality.startswith('OK;') and 'ALIGNMENT_UNVERIFIED' in quality
        assert 'FIXED_MODEL_ASSUMPTION' in quality

@pytest.mark.parametrize('candidate',[.3,.4,None])
def test_existing_non_derived_cache_value_is_not_overwritten(tmp_path,candidate):
    path=tmp_path/'cache.db'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE iv_history(ticker TEXT,sample_date TEXT,atm_iv REAL,source TEXT,updated_at TEXT,PRIMARY KEY(ticker,sample_date))')
        c.execute('CREATE TABLE iv_cache_meta(ticker TEXT PRIMARY KEY,last_full_build TEXT,last_refresh TEXT)')
        c.execute("INSERT INTO iv_history VALUES('AAA','2026-11-20',.3,'MARKETDATA_VENDOR','original')")
    frame=pd.DataFrame([{'ticker':'AAA','iv':candidate}]) if candidate is not None else pd.DataFrame(columns=['ticker','iv'])
    if candidate==.3:
        _write_iv_cache(path,'2026-11-20',frame,'new',replace_tickers=['AAA'])
    else:
        with pytest.raises(RuntimeError,match='NON_DERIVED_VALUE_CONFLICT'):
            _write_iv_cache(path,'2026-11-20',frame,'new',replace_tickers=['AAA'])
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT * FROM iv_history').fetchone()==('AAA','2026-11-20',.3,'MARKETDATA_VENDOR','original')
