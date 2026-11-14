"""A12 exact-contract first-observed-profit measurement, not a trade policy.

Daily snapshots cannot establish an intraday first passage or actual fills.
No models, providers, expiry choice, pooled expiries or production authority.
"""
from __future__ import annotations
from datetime import date, timedelta
import math
from typing import Mapping
from .expression import contract_expiry
from avshunter.shared.xnys_calendar import is_xnys_session

VERSION='monetisation_clock_v1'
LEVELS=(.2,.3)

def _number(v):
    if isinstance(v,bool):return None
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def _valid(q, *, entry=False):
    if not isinstance(q,Mapping):return False
    b,a=_number(q.get('bid')),_number(q.get('ask'))
    if b is None or a is None or b<0 or a<=0 or b>a:return False
    size=_number(q.get('ask_size' if entry else 'bid_size'))
    if entry:return b>0 and size is not None and size>=1
    return b==0 or (size is not None and size>=1)

def _sessions(start,count):
    out=[]
    while len(out)<count:
        start+=timedelta(days=1)
        if is_xnys_session(start):out.append(start)
    return out

def measure_origin(origin,entry,path,*,threshold,open_fee,close_fee,as_of=None):
    """Measure an exact observation path. Fees are dollars per 100-share contract.

    Profit is (observed bid - close fee/share)/(ask + open fee/share)-1.
    No hit by a complete window is an observed threshold failure, never P&L.
    """
    if threshold not in LEVELS:raise ValueError('Only registered +20%/+30% thresholds')
    if any(_number(f) is None or f<0 for f in (open_fee,close_fee)):raise ValueError('Fees must be finite and nonnegative')
    base={'origin':str(origin),'threshold':threshold,'n_sessions':None}
    if not _valid(entry,entry=True):return {**base,'state':'UNASSESSED_ENTRY'}
    if not path:return {**base,'state':'UNASSESSED_NO_POST_ENTRY_SESSION'}
    cost=float(entry['ask'])+open_fee/100
    gaps=[]; zero=False; observed=0
    for n,(day,q) in enumerate(path,1):
        d=date.fromisoformat(str(day)[:10])
        if as_of is not None and d>as_of:
            return {**base,'state':'UNASSESSED_GAPS_AND_CENSORING' if gaps else 'RIGHT_CENSORED',
                    'observed_sessions':observed,'missing_sessions':gaps}
        if not _valid(q):gaps.append(n);continue
        observed+=1;bid=float(q['bid']);zero=bid==0
        # A zero bid is an observation of no buyer, not an executed sale at zero.
        if bid>0 and (bid-close_fee/100)/cost-1+1e-12>=threshold:
            return {**base,'state':'UNASSESSED_GAP_BEFORE_HIT' if gaps else 'HIT',
                    'n_sessions':None if gaps else n,'first_observed_hit_session':n,
                    'hit_date':d.isoformat(),'missing_sessions':gaps}
    return {**base,'state':'UNASSESSED_MISSING_QUOTES' if gaps else 'NO_OBSERVED_HIT',
            'observed_sessions':observed,'missing_sessions':gaps,'terminal_zero_bid':zero}

def summarise_origins(origins):
    hit=[x['n_sessions'] for x in origins if x['state']=='HIT']
    failure=sum(x['state']=='NO_OBSERVED_HIT' for x in origins)
    censored=sum(x['state']=='RIGHT_CENSORED' for x in origins)
    unknown=len(origins)-len(hit)-failure-censored
    ordered=sorted(hit)
    quantile=lambda p:ordered[max(0,math.ceil(p*len(ordered))-1)] if ordered else None
    return {'n_q50':quantile(.5),'n_q80':quantile(.8),'unit':'XNYS_SESSIONS',
            'evidence_n':len(origins),'hit_n':len(hit),'failure_n':failure,'censored_n':censored,
            'unassessed_n':unknown,'complete_outcome_n':len(hit)+failure,
            'quantile_basis':'CONDITIONAL_ON_OBSERVED_HITS_NOT_SUCCESS_PROBABILITY',
            'failure_basis':'THRESHOLD_NOT_OBSERVED_AT_SAVED_SNAPSHOTS_NOT_TRADE_LOSS',
            'state':'DESCRIPTIVE_NOT_CALIBRATED' if hit else 'UNASSESSED_NO_OBSERVED_HIT_QUANTILE'}

def measure_contract_history(symbol,history,*,as_of,observation_sessions,open_fee,close_fee):
    """Deterministic non-overlapping origin windows in this exact contract.

    Origins are selected without reference to outcomes. Each reserves the whole
    configured window even if profit was observed early. No statistical pooling
    across expiries, strikes, ticker aliases or missing option paths.
    """
    if type(observation_sessions) is not int or observation_sessions<1:
        raise ValueError('Observation sessions must be a positive integer, not a hold policy')
    try:expiry=contract_expiry(symbol)
    except (ValueError,TypeError):expiry=None
    out={'version':VERSION,'contract_symbol':symbol,'as_of_session':as_of.isoformat(),
         'observation_sessions':observation_sessions,'origins':[],
         'authority':'DESCRIPTIVE_MEASUREMENT_ONLY','expiry_selection_owner':'CLAUDE_LANE_B',
         'conditioning':'EXACT_CONTRACT_HISTORY_NOT_A_ROW_SPECIFIC_FORECAST',
         'origin_basis':'NON_OVERLAPPING_FULL_WINDOWS_NOT_INDEPENDENCE_PROOF',
         'levels':{}}
    if expiry is None:
        out['state']='UNASSESSED_NONSTANDARD_OR_INVALID_CONTRACT'
    else:
        days=sorted(date.fromisoformat(str(d)[:10]) for d in history if date.fromisoformat(str(d)[:10])<=min(as_of,expiry))
        if not days:out['state']='UNASSESSED_NO_EXACT_CONTRACT_HISTORY'
        else:
            origin=days[0]
            while origin<=min(as_of,expiry):
                future=_sessions(origin,observation_sessions)
                path=[(d.isoformat(),history.get(d.isoformat())) for d in future if d<=expiry]
                entry=history.get(origin.isoformat())
                levels={str(round(t*100)):measure_origin(origin,entry,path,threshold=t,open_fee=open_fee,close_fee=close_fee,as_of=as_of) for t in LEVELS}
                out['origins'].append({'date':origin.isoformat(),'expiry_truncated':len(path)<observation_sessions,'levels':levels})
                origin=_sessions(future[-1],1)[0]
            out['state']='DESCRIPTIVE_CONTRACT_HISTORY'
    for t in LEVELS:
        key=str(round(t*100))
        out['levels'][key]=summarise_origins([x['levels'][key] for x in out['origins']])
    return out
