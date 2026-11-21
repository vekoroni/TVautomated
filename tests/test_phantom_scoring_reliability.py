"""Offline regressions: no providers, pipeline, live DB writes or snapshots."""
from pathlib import Path
import json
import sqlite3
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from phantom_database import PhantomDatabase
from phantom_engine import score_row, _composite, resolve_evidence_session
from phantom_gamma_field import compute_gamma_trajectory
from phantom_iv_surface import compute_iv_surface
from phantom_option_quality import benchmark_record_eligible


def contract(**kw):
    r=dict(ticker='NAN',quote_date='2026-11-19',option_symbol='NAN270115C00100000',
           side='call',strike=100.,dte=57.,underlying_price=100.,bid=3.,ask=3.2,mid=3.1,
           iv=.3,delta=.5,gamma=.02,theta=-.03,vega=.1,open_interest=100,
           greeks_quality='VENDOR_COMPLETE',greeks_source='MARKETDATA_VENDOR')
    r.update(kw);return r


def stored(tmp_path, rows):
    db=PhantomDatabase(tmp_path/'p.db',ROOT);db.initialise()
    with db.connect() as c:
        from phantom_maintenance import ensure_schema
        ensure_schema(c)
        for r in rows:
            c.execute('INSERT INTO chain_snapshots('+','.join(r)+') VALUES('+','.join('?' for _ in r)+')',list(r.values()))
    return db


@pytest.mark.parametrize('kw',[{'bid':0},{'iv':12.},{'greeks_quality':'NO_VALID_PRICE'},
    {'underlying_price':None},{'dte':0},{'mid':9.},{'greeks_quality':None}])
def test_qualification_excludes_bad_rows(kw):
    assert not benchmark_record_eligible(contract(**kw))


def test_preload_filters_history_and_latest_without_fallback_or_future(tmp_path):
    db=stored(tmp_path,[contract(),contract(quote_date='2026-11-20',bid=0),contract(quote_date='2026-11-23')])
    db.preload_tickers(['NAN'],as_of='2026-11-20')
    assert db.historical_iv_values('NAN')==[.3]
    assert db.latest_chain_rows('NAN')==[]
    assert db.scoring_coverage('NAN')['latest_stored_session']=='2026-11-20'
    assert db.scoring_coverage('NAN')['state']=='UNAVAILABLE'
    db.preload_tickers(['NAN'],as_of='2026-11-19')
    assert len(db.latest_chain_rows('NAN'))==1
    assert db.scoring_coverage('NAN')['state']=='QUALIFIED'
    # read helpers must not use the writable connection path.
    db.connect=lambda:pytest.fail('scoring attempted writable connection')
    db.preload_tickers(['NAN'],as_of='2026-11-20')


def test_missing_evidence_has_no_fabricated_points_or_promotion(tmp_path):
    db=stored(tmp_path,[]);db.preload_tickers(['NAN'],as_of='2026-11-20')
    row={'ticker':'NAN','direction':'CALL','options_score':62,'options_verdict':'WATCH'}
    payload=score_row(row,db,'20261120_220000')
    assert payload['phantom_score'] is None and payload['phantom_decision']=='UNASSESSED'
    assert payload['phantom_promoted_verdict']=='NONE'
    assert payload['phantom_ois_adjustment']==0
    assert payload['phantom_gamma_direction_aligned'] is None
    assert set(payload['phantom_missing_components'])=={'iv','gamma','bayes','info','critical'}
    assert payload['options_score_phantom_adjusted']==62
    assert _composite({'iv':None},{'iv':.22})==0


def test_zero_gex_is_not_alignment_and_stale_not_current(tmp_path):
    db=stored(tmp_path,[contract(open_interest=0)])
    db.preload_tickers(['NAN'],as_of='2026-11-19')
    out=compute_gamma_trajectory({'ticker':'NAN','direction':'CALL'},db)
    assert out['gamma_direction_aligned'] is False
    assert out['gamma_score']==0
    db.preload_tickers(['NAN'],as_of='2026-11-20')
    assert compute_gamma_trajectory({'ticker':'NAN'},db)['gamma_score'] is None
    assert compute_iv_surface({'ticker':'NAN'},db)['iv_entropy_score'] is None


def test_unqualified_selected_row_inputs_cannot_inflate_components(tmp_path):
    db=stored(tmp_path,[contract()]);db.preload_tickers(['NAN'],as_of='2026-11-19')
    out=compute_iv_surface({'ticker':'NAN','contract_iv':12.,'contract_symbol':'absent'},db)
    assert out['iv_kl_divergence']==0
    assert out['iv_current_basis']=='QUALIFIED_SURFACE_MEDIAN_PROXY'


def test_run_session_authority_not_start_clock(tmp_path):
    p=tmp_path/'data/output/runs/20261120_010000/run_meta.json';p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'session_date':'2026-11-19'}))
    assert resolve_evidence_session(tmp_path,'20261120_010000')==('2026-11-19','RUN_META_SESSION_DATE')
    p.write_text(json.dumps({'session_date':'bad'}))
    with pytest.raises(ValueError):resolve_evidence_session(tmp_path,'20261120_010000')


def test_covering_index_is_guarded_and_changes_no_chain_values(tmp_path):
    from phantom_database import SCORING_HISTORY_COLUMNS, SCORING_QUALIFICATION_SQL
    db=stored(tmp_path,[contract(),contract(option_symbol='BAD',bid=0)])
    with db.read_connection() as c:before=[tuple(r) for r in c.execute('SELECT * FROM chain_snapshots ORDER BY option_symbol')]
    with pytest.raises(RuntimeError,match='disk reserve'):db.ensure_scoring_index(min_free_gib=10**9)
    assert db.ensure_scoring_index(min_free_gib=0)
    assert not db.ensure_scoring_index(min_free_gib=0)
    with db.read_connection() as c:
        after=[tuple(r) for r in c.execute('SELECT * FROM chain_snapshots ORDER BY option_symbol')]
        plan=c.execute('EXPLAIN QUERY PLAN SELECT '+SCORING_HISTORY_COLUMNS+
            ' FROM chain_snapshots WHERE ticker=? AND '+SCORING_QUALIFICATION_SQL+
            ' AND dte BETWEEN 7 AND 60 ORDER BY quote_date,option_symbol',('NAN',)).fetchall()
        assert any('COVERING INDEX idx_chain_scoring_qualified_v2' in r[3] for r in plan)
    assert before==after


def test_timestamp_memoization_has_exact_calendar_and_dst_parity():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from phantom_option_quality import _new_york_session
    _new_york_session.cache_clear()
    # Summer/winter and DST transition boundaries, never wall-clock freshness.
    for day in ('2026-03-08','2026-11-01','2026-06-15','2026-11-20'):
        start=datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
        for minute in range(0,1440,3):
            epoch=start+minute*60
            expected=datetime.fromtimestamp(epoch,ZoneInfo('America/New_York')).date().isoformat()
            assert _new_york_session(epoch)==expected
            assert _new_york_session(epoch)==expected
    assert _new_york_session.cache_info().hits>=1920


def test_missing_bayesian_input_is_not_misreported_as_bad_iv_or_gamma(tmp_path):
    db=stored(tmp_path,[contract()]);db.preload_tickers(['NAN'],as_of='2026-11-19')
    p=score_row({'ticker':'NAN','direction':'CALL','contract_symbol':'NAN270115C00100000',
        'pcr_oi':1.,'phase_transition_probability':.1},db,'20261119_test')
    assert p['phantom_missing_components']==['bayes']
    assert p['phantom_promotion_reason'].startswith('Missing/unqualified components: bayes;')
