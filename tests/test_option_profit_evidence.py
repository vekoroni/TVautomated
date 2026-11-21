from copy import deepcopy
from datetime import date,timedelta
import pytest
from contracts.option_profit_evidence import (outcome,sessions_after,build_windows,posterior,evaluate,walk_forward)
from avshunter.shared.xnys_calendar import session_bounds

SYMBOL='NAN271217C00010000'
ORIGIN=date(2026,10,1)

def quote(bid=1,ask=1.1,day=ORIGIN):
    return dict(bid=bid,ask=ask,bid_size=10,ask_size=10,
                available_at=(session_bounds(day)[1]+timedelta(minutes=1)).isoformat())

def fixture(horizon=5,bid=1):
    days=sessions_after(ORIGIN,horizon)
    return {ORIGIN.isoformat():quote(.9,1),**{d.isoformat():quote(bid,max(bid,1.1),d) for d in days}}

def measure(history=None,**kw):
    args=dict(as_of=sessions_after(ORIGIN,5)[-1],horizon=5,threshold=.2,open_fee=1.1,close_fee=.1)
    args.update(kw)
    return outcome(SYMBOL,ORIGIN,history if history is not None else fixture(),**args)

def test_threshold_is_on_ask_plus_open_and_bid_less_close_fee():
    r=measure(fixture(bid=1.2))
    assert r['state']=='FAILURE_NO_THRESHOLD'
    r=measure(fixture(bid=1.2142))
    assert r['state']=='HIT' and r['net_return']==pytest.approx(.2)
    assert r['net_dollars']==pytest.approx(20.22)

@pytest.mark.parametrize('level,bid,hit',[(.2,1.25,1),(.3,1.25,0),(.3,1.32,1)])
def test_distinct_20_30_outcomes(level,bid,hit):
    assert measure(fixture(bid=bid),threshold=level)['label']==hit

def test_failures_and_costs_in_posterior_not_winners_only():
    hit=measure(fixture(bid=1.5));fail=measure()
    p=posterior([hit,fail,fail])
    assert p['n']==3 and p['wins']==1 and p['failures']==2 and p['probability']==.4
    assert posterior([fail])['probability']==pytest.approx(1/3)

@pytest.mark.parametrize('mutation', ['missing','crossed','nan','size'])
def test_bad_path_is_unknown_not_false_failure(mutation):
    h=fixture();day=sessions_after(ORIGIN,5)[1].isoformat()
    if mutation=='missing':h.pop(day)
    elif mutation=='crossed':h[day]['bid']=9
    elif mutation=='nan':h[day]['bid']=float('nan')
    else:h[day]['bid_size']=0
    r=measure(h)
    assert r['state']=='UNASSESSED_PATH_GAPS' and r['label'] is None and not r['fit_eligible']

def test_known_hit_with_missing_later_sessions_does_not_bias_complete_cohort():
    h=fixture(bid=1.5);h.pop(sessions_after(ORIGIN,5)[-1].isoformat())
    r=measure(h)
    assert r['known_hit'] and r['label'] is None and not r['fit_eligible']

def test_censored_hit_is_not_used_before_full_maturity():
    r=measure(fixture(bid=1.5),as_of=sessions_after(ORIGIN,5)[1])
    assert r['known_hit'] and r['state']=='RIGHT_CENSORED' and r['label'] is None

def test_expiry_runway_does_not_manufacture_a_full_horizon_failure():
    r=outcome('NAN261002C00010000',ORIGIN,fixture(),as_of=date(2026,10,12),horizon=5,threshold=.2,open_fee=1.1,close_fee=.1)
    assert r['state']=='EXPIRY_TRUNCATED' and r['label'] is None

def test_zero_bid_threshold_failure_is_not_an_executed_total_loss():
    r=measure(fixture(bid=0))
    assert r['label']==0 and r['terminal_zero_bid'] and r['net_return'] is None

def test_nonoverlap_is_frozen_and_sources_unchanged():
    h=fixture();days=sessions_after(ORIGIN,20)
    h.update({d.isoformat():quote(1.5,1.6,d) for d in days});old=deepcopy(h)
    rows=build_windows(SYMBOL,h,as_of=days[-1],horizon=5,threshold=.2,open_fee=1.1,close_fee=.1)
    assert all(a['window_end']<b['origin'] for a,b in zip(rows,rows[1:]))
    assert h==old


def test_no_impossible_post_expiry_origins_are_counted_as_missing_evidence():
    rows=build_windows('NAN261002C00010000',fixture(),as_of=date(2026,11,20),
        horizon=5,threshold=.2,open_fee=1.1,close_fee=.1)
    assert len(rows)==1 and rows[0]['origin']=='2026-10-01'
    assert rows[0]['state']=='EXPIRY_TRUNCATED'

@pytest.mark.parametrize('different', ['threshold','horizon','contract','cost'])
def test_pooling_outcome_horizon_contract_or_cost_mismatches_is_forbidden(different):
    a=measure();b=deepcopy(a);b['event_key']=different
    with pytest.raises(ValueError):posterior([a,b])
    with pytest.raises(ValueError):evaluate([a,b])

def test_future_and_late_receipt_training_excluded():
    a=measure();b=deepcopy(a);b['origin']='2026-11-02';b['window_end']='2026-11-09'
    b['prediction_cutoff_utc']='2026-11-02T21:30:00+00:00';b['entry_available_at']='2026-11-02T21:01:00+00:00'
    a['quote_available_at']='2026-11-03T00:00:00+00:00'
    assert walk_forward([a,b])[1]['training']['n']==0
    a['quote_available_at']='2026-10-15T20:01:00+00:00'
    assert walk_forward([a,b])[1]['training']['n']==1
    assert walk_forward([a,b])[0]['training']['n']==0

def test_even_positive_validation_never_authorises_promotion():
    rows=[]
    for i in range(45):
        d=date(2020,1,1)+timedelta(days=15*i)
        r=measure();r.update(origin=d.isoformat(),window_end=(d+timedelta(days=7)).isoformat(),
            prediction_cutoff_utc=d.isoformat()+'T21:30:00+00:00',entry_available_at=d.isoformat()+'T21:00:00+00:00',
            quote_available_at=(d+timedelta(days=8)).isoformat()+'T21:00:00+00:00',label=1)
        rows.append(r)
    result=evaluate(rows)
    assert result['validation']['out_of_sample_n']==25
    assert result['validation']['brier']<result['validation']['fixed_half_baseline_brier']
    assert not result['promotion_enabled']
    assert 'SHADOW_ONLY_NOT_AUTHORISED_FOR_PROMOTION' in result['promotion_blockers']

def test_invalid_costs_and_invalid_contract_stay_explicit():
    with pytest.raises(ValueError):measure(open_fee=-1)
    with pytest.raises(ValueError):measure(close_fee=float('nan'))
    assert outcome('BAD',ORIGIN,{},as_of=ORIGIN,horizon=5,threshold=.2,open_fee=1,close_fee=0)['state']=='UNASSESSED_CONTRACT_OR_ORIGIN'


def test_reader_enforces_ro_and_rejects_late_or_nonclose_quotes(tmp_path):
    import sqlite3
    from scripts.research_option_profit_evidence import read_history
    p=tmp_path/'fixture.db';c=sqlite3.connect(p)
    c.execute('CREATE TABLE chain_snapshots(ticker,quote_date,option_symbol,bid,ask,bid_size,ask_size,updated_ts,created_at_utc)')
    days=[ORIGIN,*sessions_after(ORIGIN,2)]
    for i,d in enumerate(days):
        close=session_bounds(d)[1]
        c.execute('INSERT INTO chain_snapshots VALUES(?,?,?,?,?,?,?,?,?)',('NAN',str(d),SYMBOL,1,1.1,10,10,
            int((close-timedelta(hours=2 if i==1 else 0)).timestamp()),
            (close+timedelta(days=30 if i==2 else 0)).isoformat()))
    c.commit();c.close()
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):c.execute('DELETE FROM chain_snapshots')
        hist,receipt=read_history(c,'NAN',SYMBOL,ORIGIN,days[-1],session_bounds(days[-1])[1])
        assert hist[str(days[0])] and hist[str(days[1])] is None and hist[str(days[2])] is None
        assert receipt['quarantine_counts']=={'NOT_NEAR_SESSION_CLOSE':1,'RECEIPT_AFTER_RESEARCH_CUTOFF':1}
    finally:c.close()


def test_input_universe_keeps_literal_nan_but_does_not_read_lane_b_records(tmp_path):
    import json
    from scripts.research_option_profit_evidence import identities,guard
    source=tmp_path/'source.csv';source.write_text('ticker,contract_occ_symbol\nNAN,'+SYMBOL+'\nSYM,\n')
    archived=tmp_path/'history.json'
    archived.write_text(json.dumps([dict(cohort='LANE_B_HANDOFF',ticker='SECRET'),
        dict(cohort='HISTORICAL_TICKETS',ticker='NAN',symbol=SYMBOL,id='T',decision='2026-10-01')]))
    index,counts,missing=identities(source,archived)
    assert set(index)=={('NAN',SYMBOL)} and counts=={'saved_pipeline_rows':1,'historical_tickets':1}
    assert missing==[{'ticker':'SYM','reason':'NO_SELECTED_EXACT_CONTRACT'}]
    with pytest.raises(RuntimeError):guard('socket.connect',())
    with pytest.raises(RuntimeError):guard('sqlite3.connect',('write.db',))


def test_existing_pk_fast_read_has_identical_rows_to_unhinted_read(tmp_path):
    import sqlite3
    from scripts.research_option_profit_evidence import read_history
    p=tmp_path/'fixture.db';c=sqlite3.connect(p)
    c.execute('CREATE TABLE chain_snapshots(ticker TEXT,quote_date TEXT,option_symbol TEXT,bid,ask,bid_size,ask_size,updated_ts,created_at_utc,PRIMARY KEY(ticker,quote_date,option_symbol))')
    stamp=session_bounds(ORIGIN)[1]
    for sym,bid in [(SYMBOL,1),('NAN271217P00010000',7)]:
        c.execute('INSERT INTO chain_snapshots VALUES(?,?,?,?,?,?,?,?,?)',('NAN',str(ORIGIN),sym,bid,bid+.1,10,10,int(stamp.timestamp()),stamp.isoformat()))
    c.commit()
    fast,receipt=read_history(c,'NAN',SYMBOL,ORIGIN,ORIGIN,stamp)
    c.execute('ALTER TABLE chain_snapshots RENAME TO indexed')
    c.execute('CREATE TABLE chain_snapshots AS SELECT * FROM indexed')
    plain,other=read_history(c,'NAN',SYMBOL,ORIGIN,ORIGIN,stamp)
    assert fast==plain and receipt==other and receipt['saved_exact_rows']==1
    c.close()
