from copy import deepcopy
from datetime import date,timedelta
import pytest
from contracts.option_profit_evidence import outcome,sessions_after
from contracts.option_profit_cohorts import (POLICY,entry_state,decorate,forecast,nonoverlapping,
    evaluate,metrics,validation_gates)
from avshunter.shared.xnys_calendar import session_bounds

def quote(day,bid=.9,ask=1):
    return {'bid':bid,'ask':ask,'bid_size':10,'ask_size':10,'underlying_price':100,
        'available_at':(session_bounds(day)[1]+timedelta(minutes=1)).isoformat()}

def window(ticker='ABC',origin=date(2026,1,5),hit=True,level=.2,horizon=5):
    sym=ticker+'261218C00100000';days=sessions_after(origin,horizon)
    h={str(origin):quote(origin),**{str(d):quote(d,1.5 if hit else .8,1.6 if hit else 1) for d in days}}
    row=outcome(sym,origin,h,as_of=days[-1],horizon=horizon,threshold=level,open_fee=1.1,close_fee=.1)
    return decorate(row,ticker,h[str(origin)],universe_known_at='2025-12-01T00:00:00+00:00')

def training():
    days=sessions_after(date(2026,1,2),50)
    return [window(chr(65+j)*2,days[i*10],hit=(j%2==0)) for i in range(5) for j in range(6)]

def target():return window('TEST',date(2026,4,20))

def test_matching_uses_only_entry_features_not_outcomes_or_current_thesis():
    a=window(hit=True);b=window(hit=False)
    assert a['cohort_key']==b['cohort_key'] and a['shared_event_key']==b['shared_event_key']
    q=quote(date(2026,1,5));q['current_macro']='BEAR';q['future_return']=999
    assert entry_state('ABC261218C00100000','2026-01-05',q,1.1,.1)[0]==a['entry_state']

@pytest.mark.parametrize('field,value',[('underlying_price',None),('ask_size',0),('bid',0),('bid',2),('underlying_price',200)])
def test_missing_or_inconsistent_entry_is_excluded_without_a_broad_fallback(field,value):
    q=quote(date(2026,1,5));q[field]=value
    state,reasons=entry_state('ABC261218C00100000','2026-01-05',q,1.1,.1)
    assert state is None and reasons

def test_distinct_dte_moneyness_spread_size_fee_states():
    q=quote(date(2026,1,5));a=entry_state('ABC261218C00100000','2026-01-05',q,1.1,.1)[0]
    assert entry_state('ABC260123C00100000','2026-01-05',q,1.1,.1)[0]!=a
    for mutation in ({'underlying_price':95},{'bid':.5},{'bid_size':1},{'bid':.09,'ask':.1}):
        assert entry_state('ABC261218C00100000','2026-01-05',{**q,**mutation},1.1,.1)[0]!=a

def test_cross_contract_matching_uses_real_failures_and_past_only():
    t=target();pool=training();f=forecast(t,pool)
    assert f['probability'] is not None and f['training']['n']==30
    assert f['training']['wins']==15 and f['training']['failures']==15
    assert f['training']['tickers']==6 and f['training']['dates']==5
    assert f['probability']==.5

def test_same_ticker_and_overlaps_are_not_new_independent_evidence():
    t=target();pool=training()
    same=window('TEST',date(2026,1,5));overlap=deepcopy(pool[0]);overlap['outcome_id']='other-strike'
    overlap['contract_symbol']='AA261218C00105000'
    f=forecast(t,pool+[same,overlap])
    assert f['training']['n']==30
    assert same['outcome_id'] not in f['training_ids']

def test_late_receipt_or_later_universe_never_enters_point_in_time_training():
    t=target();pool=training()
    for r in pool:r['quote_available_at']='2026-05-01T00:00:00+00:00'
    assert forecast(t,pool)['probability'] is None
    for r in pool:r['quote_available_at']='2026-04-01T00:00:00+00:00';r['universe_known_at']=None;r['training_available_at']=None
    assert forecast(t,pool)['probability'] is None
    assert forecast(t,pool,require_receipts=False)['probability']==.5

def test_unknown_entry_or_selection_time_cannot_be_a_qualified_oos_forecast():
    t=target();pool=training();t['entry_available_at']=None
    assert 'ENTRY_NOT_AVAILABLE' in forecast(t,pool)['reason']
    t=target();t['universe_known_at']='2026-05-01T00:00:00+00:00'
    assert 'UNIVERSE_NOT_KNOWN' in forecast(t,pool)['reason']

def test_full_window_embargo_and_outcome_clock_cost_mismatch():
    t=target();pool=training()
    for r in pool:r['window_end']=sessions_after(date(2026,4,16),1)[0].isoformat()
    assert forecast(t,pool)['probability'] is None
    for r in pool:r['window_end']='2026-03-01';r['shared_event_key']='different-cost-or-horizon'
    assert forecast(t,pool)['probability'] is None
    with pytest.raises(ValueError):evaluate([t,window(level=.3)])

def test_sparse_cohort_does_not_widen_and_new_inputs_unchanged():
    t=target();pool=training()[:10];frozen=deepcopy(pool)
    assert forecast(t,pool)['probability'] is None and pool==frozen
    t['cohort_key']=None
    assert forecast(t,training())['reason']=='NO_VALID_MATCHED_ENTRY_STATE'

def test_metric_date_clustering_reproducible_and_duplicates_do_not_add_trades():
    predictions=[]
    for i in range(12):
        t=window(chr(65+i)*3,sessions_after(date(2026,4,1),12)[i],hit=True)
        predictions.append({'target':t,'forecast':{'probability':.9,'baseline_probability':.5}})
    one=metrics(predictions);two=metrics(predictions)
    assert one==two and one['n']==12 and one['dates']==12
    assert one['date_cluster_brier_difference_ci95'][1]<0
    # Exact duplicate outputs do not count as independent forecasts.
    assert len(nonoverlapping([p['target'] for p in predictions]*2))==12
    assert metrics(predictions*2)==one

def test_zero_test_evidence_cannot_validate_or_enable_promotions():
    r=evaluate([target()])
    assert r['point_in_time_oos']['n']==0 and not r['validation_passed'] and not r['promotion_enabled']
    assert 'INSUFFICIENT_DIVERSE_CHRONOLOGICAL_TEST' in r['promotion_blockers']

def test_net_losses_missing_outcomes_and_bad_calibration_block_validation():
    m={'n':100,'tickers':20,'dates':10,'date_cluster_brier_difference_ci95':[-.1,-.01],
       'calibration':[{'mean_probability':.9,'observed_rate':.2}],'mean_net_return':-.1,'unpriced_outcomes':1}
    reasons=validation_gates(m,.5)
    assert {'CALIBRATION_GAP_EXCEEDS_FROZEN_LIMIT','MISSING_OUTCOME_SELECTION_BIAS',
            'NO_POSITIVE_NET_SNAPSHOT_RETURN','UNPRICED_OUTCOMES'}<=set(reasons)

def test_existing_production_guard_continues_even_with_shadow_probability_fields():
    from scripts.phantom_bayesian import compute_bayesian_edge
    p=compute_bayesian_edge({'ticker':'ABC','option_profit_probability':.99,'matched_cohort_validated':True})
    assert p['bayesian_score'] is None and not p['bayesian_evidence_available']


def test_prospective_after_close_publication_cannot_price_an_earlier_closing_entry():
    t=target();t['eligible_from_session']='2026-04-21'
    assert 'ENTRY_SESSION_PRECEDES' in forecast(t,training())['reason']
    pool=training()
    for r in pool:r['eligible_from_session']='2026-04-21'
    t=target()
    # Old training observations need not have been traded/selected at origin.
    # Their recovered data must instead have existed before this NEW forecast.
    assert forecast(t,pool)['training']['n']==30
    for r in pool:r['training_available_at']='2026-04-21T00:00:00+00:00'
    assert forecast(t,pool)['training']['n']==0
