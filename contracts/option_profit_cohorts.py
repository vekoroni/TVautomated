"""Frozen, saved-entry-state cohort experiment. Never production authority.

No target/contract selection, Lane B policies, expiry changes, live inputs or
unconditional fallback when a match is unavailable. Pooling is a hypothesis.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import date
from functools import lru_cache
import math
from contracts.option_profit_evidence import contract,number,instant,digest,sessions_after

VERSION='option_profit_matched_cohorts_v2_availability_clocks'
POLICY={'version':VERSION,'dte_upper':[14,30,60,120,365],
    'signed_moneyness_upper':[-.05,-.02,.02,.05],
    'spread_fraction_upper':[.10,.25,.50],
    'fee_fraction_upper':[.01,.05], 'size_boundary':10,
    'min_train':20,'min_train_tickers':5,'min_train_dates':3,
    'min_test':50,'min_test_tickers':10,'min_test_dates':5,
    'embargo_sessions':1,'bootstrap_repetitions':500,'bootstrap_seed':20261121,
    'max_unassessed_fraction':.20,'max_calibration_gap':.10,
    'contract_multiplier':100,'authority':'OFFLINE_SHADOW_ONLY',
    'matching':'EXACT_FROZEN_BUCKETS_NO_WIDENING',
    'baseline':'PAST_AVAILABLE_SAME_EVENT_AND_SIDE_UNMATCHED_BETA_1_1',
    'test':'EXPANDING_TIME_LEAVE_TEST_TICKER_OUT_FULL_WINDOW_PURGE_DATE_CLUSTERED'}

def bucket(value,bounds):
    return next((i for i,upper in enumerate(bounds) if value<=upper),len(bounds))

def entry_state(symbol,origin,q,open_fee,close_fee):
    c=contract(symbol);reasons=[]
    if not c:return None,['NONSTANDARD_CONTRACT']
    day=date.fromisoformat(origin);dte=(c['expiry']-day).days
    values={k:number(q.get(k)) for k in ('bid','ask','bid_size','ask_size','underlying_price')}
    b,a,bs,az,s=(values[k] for k in ('bid','ask','bid_size','ask_size','underlying_price'))
    if any(v is None for v in values.values()) or min(a or 0,s or 0,c['strike'])<=0:
        return None,['MISSING_ENTRY_FEATURES']
    if b<=0 or b>a or min(bs,az)<1:return None,['UNUSABLE_ENTRY_QUOTE']
    if dte<7 or dte>365:return None,['ENTRY_DTE_OUTSIDE_FROZEN_MODEL_SUPPORT']
    intrinsic=max(0,s-c['strike']) if c['side']=='CALL' else max(0,c['strike']-s)
    upper=s if c['side']=='CALL' else c['strike']
    if a+.01<intrinsic or b>upper+.01:return None,['ENTRY_PRICE_SPOT_INCONSISTENCY']
    sign=1 if c['side']=='CALL' else -1
    moneyness=sign*(s/c['strike']-1);spread=(a-b)/((a+b)/2)
    fee_fraction=(open_fee+close_fee)/(a*100)
    return {'side':c['side'],'dte_bucket':bucket(dte,POLICY['dte_upper']),
        'signed_moneyness_bucket':bucket(moneyness,POLICY['signed_moneyness_upper']),
        'spread_bucket':bucket(spread,POLICY['spread_fraction_upper']),
        'size_bucket':int(min(bs,az)>=POLICY['size_boundary']),
        'fee_bucket':bucket(fee_fraction,POLICY['fee_fraction_upper'])},reasons

def event_key(row):
    return digest({**{k:row[k] for k in ('event_id','horizon','clock','threshold','open_fee','close_fee','entry','exit','multiplier','side')},
        'entry_clock':row.get('entry_clock','CLOSE_BENCHMARK')})

def decorate(row,ticker,quote,*,universe_known_at=None,eligible_from_session=None,training_available_at=None,assessment_session=None):
    out=dict(row,ticker=ticker,universe_known_at=universe_known_at,eligible_from_session=eligible_from_session,
        training_available_at=training_available_at or universe_known_at)
    if assessment_session:out['assessment_session']=assessment_session
    state,reasons=entry_state(row['contract_symbol'],row['origin'],quote,row['open_fee'],row['close_fee'])
    out.update(entry_state=state,feature_reasons=reasons,
        shared_event_key=event_key(row),outcome_id=digest([ticker,row['contract_symbol'],row['origin'],row['event_key']]))
    out['cohort_key']=digest([out['shared_event_key'],state]) if state else None
    return out

def nonoverlapping(rows):
    """One exposure per ticker/window; selection order is outcome-independent."""
    until={};seen=set();out=[]
    for r in sorted(rows,key=lambda x:(x['origin'],x['ticker'],x['contract_symbol'],x['outcome_id'])):
        if r['outcome_id'] in seen:continue
        seen.add(r['outcome_id'])
        if r['origin']<=until.get(r['ticker'],''):continue
        until[r['ticker']]=r['window_end'];out.append(r)
    return out

def probability(rows):
    wins=sum(r['label']==1 for r in rows);n=len(rows)
    return {'n':n,'wins':wins,'failures':n-wins,'probability':(wins+1)/(n+2),
        'tickers':len({r['ticker'] for r in rows}),'dates':len({r['origin'] for r in rows})}

@lru_cache(maxsize=2048)
def purged_end(day):
    return sessions_after(date.fromisoformat(day),POLICY['embargo_sessions'])[-1].isoformat()

def forecast(target,pool,*,require_receipts=True):
    cutoff=instant(target.get('prediction_cutoff_utc'));reasons=[]
    if target['cohort_key'] is None:return {'reason':'NO_VALID_MATCHED_ENTRY_STATE','probability':None,'training_ids':[]}
    if cutoff is None:return {'reason':'NO_PREDICTION_CUTOFF','probability':None,'training_ids':[]}
    def eligible(r):
        if not r.get('fit_eligible') or r.get('label') not in (0,1):return False
        if r['ticker']==target['ticker'] or r['shared_event_key']!=target['shared_event_key']:return False
        if purged_end(r['window_end'])>=target['origin']:return False
        if require_receipts:
            available=instant(r.get('quote_available_at'))
            if available is None or available>cutoff:return False
            # Training observations may be recovered later than their origin.
            # Their DATA must be known before this forecast; never pretend a
            # historical decision or universe publication existed at origin.
            known=instant(r.get('training_available_at') or r.get('universe_known_at'))
            if known is None or known>cutoff:return False
        return True
    base=[r for r in pool if eligible(r)]
    matched=nonoverlapping([r for r in base if r['cohort_key']==target['cohort_key']])
    baseline=nonoverlapping(base);p=probability(matched)
    if p['n']<POLICY['min_train'] or p['tickers']<POLICY['min_train_tickers'] or p['dates']<POLICY['min_train_dates']:
        reasons.append('INSUFFICIENT_DIVERSE_PRIOR_MATCHED_EVIDENCE')
    if require_receipts:
        entry=instant(target.get('entry_available_at'));known=instant(target.get('universe_known_at'))
        if entry is None or entry>cutoff:reasons.append('ENTRY_NOT_AVAILABLE_AT_PREDICTION')
        if known is None or known>cutoff:reasons.append('UNIVERSE_NOT_KNOWN_AT_PREDICTION')
        if target.get('eligible_from_session') and target['origin']<target['eligible_from_session']:
            reasons.append('ENTRY_SESSION_PRECEDES_RECORDED_PUBLICATION')
    return {'reason':'|'.join(reasons) or None,'probability':p['probability'] if not reasons else None,
        'training':p,'baseline_probability':probability(baseline)['probability'],
        'training_ids':[r['outcome_id'] for r in matched],
        'baseline_ids':[r['outcome_id'] for r in baseline],
        'mode':'POINT_IN_TIME' if require_receipts else 'RETROSPECTIVE_AVAILABILITY_UNPROVEN_NOT_DEPLOYABLE'}

def maturity_coverage(rows):
    eligible=[];pending=0;runway=0
    for r in rows:
        if r.get('expiry_truncated'):runway+=1
        elif r.get('assessment_session') and r['window_end']>r['assessment_session']:pending+=1
        elif r.get('state')=='RIGHT_CENSORED':pending+=1
        else:eligible.append(r)
    missing=sum(not r['fit_eligible'] for r in eligible)
    return {'mature_runway_eligible_n':len(eligible),'mature_unassessed_n':missing,
        'not_matured_n':pending,'expiry_truncated_n':runway,
        'mature_unknown_fraction':missing/len(eligible) if eligible else 0.}

def metrics(predictions):
    valid=[r for r in predictions if r['forecast']['probability'] is not None and r['target']['fit_eligible']]
    unique={}
    for r in valid:
        key=r['target']['outcome_id']
        if key in unique and unique[key]!=r:raise ValueError('Conflicting duplicate forecast identity')
        unique[key]=r
    valid=list(unique.values())
    # Ticker-level overlap is removed separately inside each event experiment.
    picked={r['outcome_id'] for r in nonoverlapping([x['target'] for x in valid])}
    valid=[r for r in valid if r['target']['outcome_id'] in picked]
    if not valid:return {'n':0,'tickers':0,'dates':0,'brier':None,'baseline_brier':None,
                         'date_cluster_brier_difference_ci95':None,'calibration':[],'mean_net_return':None}
    import numpy as np
    daily=defaultdict(list);bins=defaultdict(list);losses=[];base_losses=[]
    for r in valid:
        t=r['target'];p=r['forecast']['probability'];bp=r['forecast']['baseline_probability'];y=t['label']
        loss=(p-y)**2;base=(bp-y)**2;losses.append(loss);base_losses.append(base)
        daily[t['origin']].append(loss-base);bins[min(9,int(p*10))].append((p,y))
    differences=np.array([sum(v)/len(v) for _,v in sorted(daily.items())])
    ci=None
    if len(differences)>=2:
        rng=np.random.default_rng(POLICY['bootstrap_seed'])
        means=rng.choice(differences,size=(POLICY['bootstrap_repetitions'],len(differences)),replace=True).mean(axis=1)
        ci=[float(x) for x in np.quantile(means,[.025,.975])]
    returns=[r['target']['net_return'] for r in valid if r['target']['net_return'] is not None]
    return {'n':len(valid),'tickers':len({r['target']['ticker'] for r in valid}),'dates':len(daily),
        'brier':sum(losses)/len(losses),'baseline_brier':sum(base_losses)/len(base_losses),
        'date_cluster_brier_difference_ci95':ci,
        'calibration':[{'bin':k,'n':len(v),'mean_probability':sum(p for p,y in v)/len(v),
                        'observed_rate':sum(y for p,y in v)/len(v)} for k,v in sorted(bins.items())],
        'mean_net_return':sum(returns)/len(returns) if returns else None,'return_n':len(returns),
        'unpriced_outcomes':len(valid)-len(returns)}

def validation_gates(m,unknown_fraction):
    reasons=[]
    if m['n']<POLICY['min_test'] or m['tickers']<POLICY['min_test_tickers'] or m['dates']<POLICY['min_test_dates']:
        reasons.append('INSUFFICIENT_DIVERSE_CHRONOLOGICAL_TEST')
    ci=m['date_cluster_brier_difference_ci95']
    if ci is None or ci[1]>=0:reasons.append('NO_DATE_CLUSTER_ROBUST_BRIER_IMPROVEMENT')
    if any(abs(b['mean_probability']-b['observed_rate'])>POLICY['max_calibration_gap'] for b in m['calibration']):
        reasons.append('CALIBRATION_GAP_EXCEEDS_FROZEN_LIMIT')
    if unknown_fraction>POLICY['max_unassessed_fraction']:reasons.append('MISSING_OUTCOME_SELECTION_BIAS')
    if m['mean_net_return'] is None or m['mean_net_return']<=0:reasons.append('NO_POSITIVE_NET_SNAPSHOT_RETURN')
    if m.get('unpriced_outcomes',0):reasons.append('UNPRICED_OUTCOMES')
    return reasons

def evaluate(rows):
    if len({r['shared_event_key'] for r in rows})>1:raise ValueError('One side, threshold, horizon and cost convention per experiment')
    feature_rows=[r for r in rows if r['cohort_key'] is not None]
    pool=[r for r in feature_rows if r['fit_eligible']]
    strict=[];retrospective=[]
    for r in rows:
        strict.append({'target':r,'forecast':forecast(r,pool)})
        retrospective.append({'target':r,'forecast':forecast(r,pool,require_receipts=False)})
    m=metrics(strict);diagnostic=metrics(retrospective)
    coverage=maturity_coverage(rows)
    unknown=coverage['mature_unknown_fraction']
    gates=validation_gates(m,unknown)
    gates+=['SHADOW_RELEASE_REVIEW_REQUIRED','ENTRY_SPOT_TIME_ALIGNMENT_NOT_INDEPENDENTLY_VERIFIED',
            'NO_COMPARABLE_CALIBRATED_MARKET_EDGE_REFERENCE']
    return {'policy':POLICY,'policy_sha256':digest(POLICY),'promotion_enabled':False,
        'rows':len(rows),'matched_state_rows':len(feature_rows),
        'feature_exclusions':dict(Counter(x for r in rows for x in r['feature_reasons'])),
        'states':dict(Counter(r['state'] for r in rows)),
        'maturity_coverage':coverage,
        'unknown_fraction':unknown,'point_in_time_oos':m,'retrospective_diagnostic_only':diagnostic,
        'forecast_blockers':dict(Counter(x['forecast']['reason'] for x in strict if x['forecast']['reason'])),
        'validation_passed':not validation_gates(m,unknown),'promotion_blockers':gates,
        'forecasts':[{'outcome_id':x['target']['outcome_id'],'cohort_key':x['target']['cohort_key'],
            'ticker':x['target']['ticker'],'origin':x['target']['origin'],'label':x['target']['label'],
            **x['forecast']} for x in strict]}
