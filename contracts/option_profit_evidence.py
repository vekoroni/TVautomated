"""Offline exact-contract profit-event research. No execution/promotion authority.

The event is first OBSERVED net profit at saved close bids, not an intraday
first passage, expiry ITM probability, actual fill, or Lane B exit policy.
"""
from __future__ import annotations
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds

VERSION='option_profit_evidence_v1'
HORIZONS=(5,10,20)
LEVELS=(.2,.3)
MIN_TRAIN=20
MIN_VALIDATION=20

def number(v):
    try:
        n=float(v)
        return n if not isinstance(v,bool) and math.isfinite(n) else None
    except (ValueError,TypeError,OverflowError):return None

def instant(v):
    try:
        t=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError,TypeError):return None

def digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def contract(symbol):
    m=re.fullmatch(r'([A-Z.]+)(\d{6})([CP])(\d{8})',str(symbol))
    if not m:return None
    try:expiry=datetime.strptime(m[2],'%y%m%d').date()
    except ValueError:return None
    return {'root':m[1],'expiry':expiry,'side':'CALL' if m[3]=='C' else 'PUT','strike':int(m[4])/1000}

def sessions_after(origin,n):
    days=[]
    while len(days)<n:
        origin+=timedelta(days=1)
        if is_xnys_session(origin):days.append(origin)
    return days

def valid_quote(q,entry=False):
    if not isinstance(q,dict):return False
    b,a=number(q.get('bid')),number(q.get('ask'))
    if b is None or a is None or b<0 or a<=0 or b>a:return False
    if entry and b<=0:return False
    size=number(q.get('ask_size' if entry else 'bid_size'))
    return (not entry and b==0) or (size is not None and size>=1)

def outcome(symbol,origin,history,*,as_of,horizon,threshold,open_fee,close_fee):
    if horizon not in HORIZONS or threshold not in LEVELS:raise ValueError('Unregistered event')
    if any(number(x) is None or x<0 for x in (open_fee,close_fee)):raise ValueError('Invalid costs')
    c=contract(symbol);days=sessions_after(origin,horizon)
    key={'version':VERSION,'contract_symbol':symbol,'horizon':horizon,'clock':'XNYS_SESSIONS',
         'threshold':threshold,'open_fee':open_fee,'close_fee':close_fee,
         'entry':'SAVED_ASK','exit':'SAVED_BID','multiplier':100}
    r={**key,'event_id':f'OPTION_NET_PROFIT_GE_{round(threshold*100)}_OBSERVED_CLOSE',
       'event_key':digest(key),'origin':origin.isoformat(),'window_end':days[-1].isoformat(),
       'state':'UNASSESSED','label':None,'fit_eligible':False,'known_hit':False,
       'first_hit_session':None,'first_hit_date':None,'net_return':None,'net_dollars':None,
       'maximum_observed_net_return':None,'quote_available_at':None,'missing_sessions':[],
       'expiry_truncated':bool(c and c['expiry']<days[-1]),'side':c['side'] if c else None}
    if not c or not is_xnys_session(origin):r['state']='UNASSESSED_CONTRACT_OR_ORIGIN';return r
    entry=history.get(origin.isoformat())
    if not valid_quote(entry,True):r['state']='UNASSESSED_ENTRY';return r
    r['entry_ask']=float(entry['ask']);r['entry_cost_dollars']=r['entry_ask']*100+open_fee
    r['prediction_cutoff_utc']=(session_bounds(origin)[1]+timedelta(minutes=30)).isoformat()
    r['entry_available_at']=entry.get('available_at')
    available=[instant(entry.get('available_at'))];marks=[];exit_quote=None
    for n,day in enumerate(days,1):
        if day>as_of or day>c['expiry']:break
        q=history.get(day.isoformat())
        if not valid_quote(q):r['missing_sessions'].append(day.isoformat());continue
        available.append(instant(q.get('available_at')))
        if float(q['bid'])>0:
            pnl=float(q['bid'])*100-close_fee-r['entry_cost_dollars']
            ret=pnl/r['entry_cost_dollars'];marks.append(ret)
            if not r['known_hit'] and ret+1e-12>=threshold:
                r.update(known_hit=True,first_hit_session=n,first_hit_date=day.isoformat(),
                         net_return=ret,net_dollars=pnl)
        if n==horizon:exit_quote=q
    r['maximum_observed_net_return']=max(marks) if marks else None
    mature=days[-1]<=as_of and days[-1]<=c['expiry']
    if not mature:r['state']='EXPIRY_TRUNCATED' if r['expiry_truncated'] and c['expiry']<=as_of else 'RIGHT_CENSORED'
    elif r['missing_sessions']:r['state']='UNASSESSED_PATH_GAPS'
    else:
        r.update(state='HIT' if r['known_hit'] else 'FAILURE_NO_THRESHOLD',label=int(r['known_hit']),fit_eligible=True)
        if not r['known_hit'] and exit_quote and float(exit_quote['bid'])>0:
            pnl=float(exit_quote['bid'])*100-close_fee-r['entry_cost_dollars']
            r.update(net_dollars=pnl,net_return=pnl/r['entry_cost_dollars'])
        r['terminal_zero_bid']=bool(exit_quote and float(exit_quote['bid'])==0)
    # Even a known early hit reserves its full window before training can use it.
    if mature and not r['missing_sessions'] and all(t is not None for t in available):
        r['quote_available_at']=max([session_bounds(days[-1])[1],*available]).isoformat()
    return r

def build_windows(symbol,history,*,as_of,horizon,threshold,open_fee,close_fee):
    """Origin grid fixed by quote dates, never by subsequent success or failure."""
    parsed=contract(symbol)
    if parsed is None:return []
    last_origin=min(as_of,parsed['expiry'])
    dates=sorted(date.fromisoformat(k) for k in history if date.fromisoformat(k)<=last_origin)
    if not dates:return []
    origin=dates[0];out=[]
    while origin<=last_origin:
        out.append(outcome(symbol,origin,history,as_of=as_of,horizon=horizon,
                           threshold=threshold,open_fee=open_fee,close_fee=close_fee))
        origin=sessions_after(sessions_after(origin,horizon)[-1],1)[0]
    return out

def posterior(rows):
    """Explicit weak Beta(1,1) prior; failures are in the denominator."""
    if len({r['event_key'] for r in rows})>1:raise ValueError('Incompatible exact events cannot be pooled')
    known=[r for r in rows if r.get('fit_eligible')]
    wins=sum(r['label']==1 for r in known);losses=len(known)-wins
    if not known:return {'n':0,'wins':0,'failures':0,'probability':None,'ci90':None}
    from scipy.stats import beta
    return {'n':len(known),'wins':wins,'failures':losses,'probability':(wins+1)/(len(known)+2),
            'ci90':[float(beta.ppf(.05,wins+1,losses+1)),float(beta.ppf(.95,wins+1,losses+1))]}

def walk_forward(rows):
    """Exact event key only; full-window purge and actual receipt availability."""
    forecasts=[]
    for row in sorted(rows,key=lambda x:x['origin']):
        cutoff=instant(row.get('prediction_cutoff_utc'))
        entry_known=instant(row.get('entry_available_at'))
        training=[r for r in rows if r['event_key']==row['event_key']
            and r['window_end']<row['origin'] and r.get('fit_eligible')
            and instant(r.get('quote_available_at')) is not None
            and cutoff is not None and instant(r['quote_available_at'])<=cutoff]
        p=posterior(training)
        reason='INSUFFICIENT_PRIOR_MATURED_EXACT_EVENT_HISTORY' if p['n']<MIN_TRAIN else None
        if cutoff is None or entry_known is None or entry_known>cutoff:reason='ENTRY_NOT_AVAILABLE_AT_PREDICTION'
        forecasts.append({'origin':row['origin'],'event_key':row['event_key'],'training':p,
            'forecast_probability':p['probability'] if reason is None else None,
            'reason':reason,'test_label':row['label'],'test_eligible':row.get('fit_eligible',False),
            'training_origins':[r['origin'] for r in training]})
    return forecasts

def evaluate(rows):
    if len({r['event_key'] for r in rows})>1:raise ValueError('Evaluate one exact event at a time')
    forecasts=walk_forward(rows)
    test=[f for f in forecasts if f['forecast_probability'] is not None and f['test_eligible']]
    brier=sum((f['forecast_probability']-f['test_label'])**2 for f in test)/len(test) if test else None
    baseline=sum((.5-f['test_label'])**2 for f in test)/len(test) if test else None
    complete=[r for r in rows if r.get('fit_eligible')]
    hits=[r for r in complete if r['label']==1];unknown=len(rows)-len(complete)
    returns=[r['net_return'] for r in complete if r['net_return'] is not None]
    model=posterior(rows)
    reasons=[]
    if model['n']<MIN_TRAIN:reasons.append('INSUFFICIENT_EXACT_EVENT_TRAINING')
    if len(test)<MIN_VALIDATION:reasons.append('INSUFFICIENT_CHRONOLOGICAL_VALIDATION')
    if brier is None or brier>=baseline:reasons.append('NO_OUT_OF_SAMPLE_BRIER_IMPROVEMENT')
    if unknown:reasons.append('INCOMPLETE_PATH_SELECTION_BIAS_UNRESOLVED')
    reasons+=['ACTUAL_FILL_AND_INTRADAY_PATH_UNVERIFIED','SHADOW_ONLY_NOT_AUTHORISED_FOR_PROMOTION',
              'NO_COMPARABLE_INDEPENDENT_MARKET_PROBABILITY','ENTRY_STATE_MATCHING_NOT_VALIDATED']
    return {'version':VERSION,'authority':'OFFLINE_SHADOW_ONLY','promotion_enabled':False,
        'posterior_basis':'BETA_1_1_EXACT_CONTRACT_COMPLETE_WINDOWS_NOT_MARKET_EDGE',
        'counts':dict(Counter(r['state'] for r in rows)),'total_windows':len(rows),
        'complete_n':len(complete),'hit_n':len(hits),'failure_n':len(complete)-len(hits),'unassessed_or_censored_n':unknown,
        'observed_hit_rate':len(hits)/len(complete) if complete else None,
        'missing_outcome_bounds':[len(hits)/len(rows),(len(hits)+unknown)/len(rows)] if rows else None,
        'mean_executable_snapshot_return':sum(returns)/len(returns) if returns else None,
        'return_denominator':len(returns),'unpriced_terminal_zero_bids':sum(r.get('terminal_zero_bid',False) for r in complete),
        'posterior':model,'validation':{'out_of_sample_n':len(test),'brier':brier,'fixed_half_baseline_brier':baseline,
             'forecast_blockers':dict(Counter(f['reason'] for f in forecasts if f['reason']))},
        'promotion_blockers':reasons,'forecasts':forecasts}
