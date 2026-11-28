"""Versioned US-option assessment. Raw/vendor chain values are never updated.

The shared American CRR owner supplies every model price. Point, interval and
excluded results are distinct; a successful inverse is not a vendor Greek set.
"""
from __future__ import annotations
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
import hashlib,json,math,sqlite3
from pathlib import Path

FIELDS=('ticker','quote_date','option_symbol','side','strike','dte','bid','mid','ask',
        'underlying_price','iv','delta','gamma','theta','vega','updated_ts','greeks_source','greeks_quality')
GREEKS=('iv','delta','gamma','theta','vega')
RATE=.045
DIVIDEND=0.
STEPS=300
MAX_VOL=12.
ELIGIBLE={'VENDOR_POINT_QUALIFIED','MODEL_POINT_QUALIFIED'}

def finite(v):
    try:return v is not None and not isinstance(v,bool) and math.isfinite(float(v))
    except (TypeError,ValueError):return False

def canonical(v):
    if isinstance(v,float):return (0. if v==0 else v) if math.isfinite(v) else str(v)
    return v

@lru_cache(maxsize=1)
def calc_version():
    root=Path(__file__).resolve().parents[1]
    paths=[Path(__file__),root/'domain/option_valuation.py',root/'config/governed_constants_v1.json',root/'scripts/phantom_option_quality.py']
    h=hashlib.sha256()
    for p in paths:h.update(p.read_bytes().replace(b'\r\n',b'\n'))
    return 'PHANTOM_AMERICAN_ASSESSMENT_V1_'+h.hexdigest()[:20]

def input_hash(row):
    return hashlib.sha256(json.dumps([canonical(row.get(k)) for k in FIELDS],separators=(',',':'),sort_keys=True).encode()).hexdigest()

def has_table(c):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='phantom_greek_assessments'").fetchone())

def ensure_schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_greek_assessments(
       ticker TEXT,quote_date TEXT,option_symbol TEXT,input_hash TEXT NOT NULL,
       calc_version TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL,
       assessed_at_utc TEXT NOT NULL,PRIMARY KEY(ticker,quote_date,option_symbol))''')
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_greek_assessment_audit(
       id INTEGER PRIMARY KEY,ticker TEXT,quote_date TEXT,option_symbol TEXT,
       prior_payload_json TEXT,new_payload_json TEXT NOT NULL,assessed_at_utc TEXT NOT NULL)''')

def _price(rows, vols, steps=STEPS, spot_scale=1., time_days=0.):
    import numpy as np
    from domain.option_valuation import american_crr_values
    from domain.option_valuation import european_bsm_value
    s=np.array([r['underlying_price']*spot_scale for r in rows],float)
    k=np.array([r['strike'] for r in rows],float)
    t=np.maximum(np.array([r['dte'] for r in rows],float)+time_days,0.)/365.
    call=np.array([str(r['side']).lower()=='call' for r in rows])
    out=american_crr_values(s,k,t,RATE,DIVIDEND,vols,call,steps=steps)
    for i,r in enumerate(rows):
        if r['_style']=='EUROPEAN':out[i]=european_bsm_value(str(r['side']).upper(),s[i],k[i],t[i],float(vols[i]),rate=RATE,dividend_yield=DIVIDEND)
    return out

def _inverse(rows, targets):
    """Vector bisection only within a finite bracket; no mark clamping."""
    import numpy as np
    # Stay above the CRR probability-clamping region at very small sigma.
    lo=np.array([max(1e-4,abs(RATE-DIVIDEND)*math.sqrt(r['dte']/365./STEPS)*1.001) for r in rows])
    hi=np.full(len(rows),MAX_VOL)
    target=np.array(targets,float);floor=_price(rows,lo);ceiling=_price(rows,hi)
    tol=np.maximum(1e-5,abs(target)*1e-5)
    ok=(target>floor+tol)&(target<ceiling-tol)
    boundary=abs(target-floor)<=tol
    active=np.flatnonzero(ok)
    active_rows=[rows[i] for i in active]
    # Invalid/boundary targets never use a point root. Do not repeatedly price
    # them, and batch only the valid inversions (identical bisection arithmetic).
    for _ in range(28 if len(active) else 0):
        mid=(lo[active]+hi[active])/2;price=_price(active_rows,mid)
        below=price<target[active]
        lo[active]=np.where(below,mid,lo[active]);hi[active]=np.where(below,hi[active],mid)
    return (lo+hi)/2,ok,boundary,floor,ceiling

def assess_rows(records):
    import numpy as np
    from domain.option_valuation import exercise_style
    from scripts.phantom_option_quality import quote_assessment,benchmark_record_eligible
    rows=[dict(x) for x in records];out=[];work=[];work_indices=[]
    for i,r in enumerate(rows):
        style=exercise_style(r.get('ticker'));r['_style']=style
        rec=dict(input_hash=input_hash(r),calc_version=calc_version(),status='EXCLUDED_UNSUPPORTED_INPUT',
          reason='UNSUPPORTED_INPUT',model='AMERICAN_CRR' if style=='AMERICAN' else 'BSM_EUROPEAN',
          authority='ADVISORY_ONLY',promotion_eligible=False,risk_free_rate=RATE,rate_basis='ASSUMED_FIXED_NOT_OBSERVED',
          dividend_yield=DIVIDEND,dividend_basis='ASSUMED_ZERO_NOT_OBSERVED',clock_basis='SAVED_CALENDAR_DTE_365',
          quote_underlying_alignment='UNVERIFIED',greeks=None,iv_interval=None)
        out.append(rec)
        if str(r.get('side')).lower() not in ('call','put'):
            rec.update(status='EXCLUDED_INVALID_SIDE',reason='INVALID_SIDE');continue
        if any(not finite(r.get(k)) or r[k]<=0 for k in ('underlying_price','strike','dte')):
            reason='MISSING_UNDERLYING' if not finite(r.get('underlying_price')) or r['underlying_price']<=0 else 'INVALID_STRIKE_OR_DTE'
            rec.update(status='EXCLUDED_'+reason,reason=reason);continue
        mark,_,flags=quote_assessment(r);rec['quote_flags']=flags
        if mark is None:
            rec.update(status='EXCLUDED_INVALID_QUOTE',reason=';'.join(flags));continue
        rec['market_price']=mark
        source=str(r.get('greeks_source') or '').upper()
        if all(finite(r.get(g)) for g in GREEKS) and ('VENDOR' in source or source.startswith('MARKETDATA')):
            if benchmark_record_eligible(r):
                rec.update(status='VENDOR_POINT_QUALIFIED',reason='PRESERVED_MEASURED_VECTOR',model='VENDOR',
                           greeks={g:float(r[g]) for g in GREEKS},rate_basis='VENDOR_METHOD_UNDISCLOSED',dividend_basis='VENDOR_METHOD_UNDISCLOSED')
            else:rec.update(status='EXCLUDED_VENDOR_BENCHMARK_POLICY',reason='VENDOR_VECTOR_OUTSIDE_QUALIFICATION')
            continue
        # Unknown-origin numerics cannot silently become verified vendor data.
        if source and not any(s in source for s in ('VENDOR','MARKETDATA','COMPUTED','UNAVAILABLE','MIXED')):
            rec.update(status='EXCLUDED_UNVERIFIED_ORIGIN',reason='NUMERIC_ORIGIN_UNVERIFIED');continue
        intrinsic=max(0.,r['underlying_price']-r['strike']) if r['side']=='call' else max(0.,r['strike']-r['underlying_price'])
        rec['intrinsic']=intrinsic
        cap=r['underlying_price'] if r['side']=='call' else r['strike']
        if r['ask']<intrinsic-1e-8:
            rec.update(status='EXCLUDED_SPREAD_BELOW_INTRINSIC',reason='ASK_BELOW_SAVED_INTRINSIC_ALIGNMENT_UNVERIFIED');continue
        if r['bid']>cap+1e-8:
            rec.update(status='EXCLUDED_SPREAD_ABOVE_UPPER_BOUND',reason='BID_ABOVE_MODEL_UPPER_BOUND');continue
        work.append(r);work_indices.append(i)
    if not work:return out
    marks=[out[i]['market_price'] for i in work_indices]
    mids,valid,boundary,floor,ceiling=_inverse(work,marks)
    bids,bid_ok,_,_,_=_inverse(work,[r['bid'] for r in work])
    asks,ask_ok,_,_,_=_inverse(work,[r['ask'] for r in work])
    good=[];gi=[];vol=[]
    for j,i in enumerate(work_indices):
        rec=out[i];r=work[j]
        # The entire feasible bid/ask interval lies in the model domain, or
        # extends to a non-identifiable boundary. Never invent a point there.
        if r['ask']<floor[j]-1e-5 or r['bid']>ceiling[j]+1e-5:
            rec.update(status='EXCLUDED_MODEL_SPREAD_INCOMPATIBLE',reason='SPREAD_DOES_NOT_INTERSECT_CURRENT_ASSUMED_MODEL');continue
        rec['iv_interval']={'lower':float(bids[j]) if bid_ok[j] else 0.,
                            'upper':float(asks[j]) if ask_ok[j] else None,
                            'upper_unbounded':bool(r['ask']>=ceiling[j]),'basis':'BID_ASK_MODEL_COMPATIBLE_SET_NOT_CONFIDENCE_INTERVAL'}
        if not valid[j]:
            rec.update(status='INTERVAL_ONLY',reason='MIDPOINT_BOUNDARY_OR_OUTSIDE_MODEL_RANGE');continue
        if not .01<=mids[j]<=5.:
            rec.update(status='EXCLUDED_MODEL_IV_RANGE',reason='POINT_OUTSIDE_RETAINED_1_TO_500_PERCENT_RANGE',candidate_iv=float(mids[j]));continue
        good.append(r);gi.append(i);vol.append(mids[j])
    if not good:return out
    v=np.array(vol);fine=_price(good,v,steps=STEPS*2)
    coarse=_price(good,v);up=_price(good,v,steps=STEPS*2,spot_scale=1.005)
    down=_price(good,v,steps=STEPS*2,spot_scale=.995)
    vp=_price(good,v+.001,steps=STEPS*2);vm=_price(good,np.maximum(v-.001,1e-5),steps=STEPS*2)
    tomorrow=_price(good,v,steps=STEPS*2,time_days=-1.)
    for j,i in enumerate(gi):
        rec=out[i];r=good[j];h=.005*r['underlying_price']
        delta=(up[j]-down[j])/(2*h);gamma=(up[j]-2*fine[j]+down[j])/(h*h)
        vega=(vp[j]-vm[j])/.002/100.;theta=tomorrow[j]-fine[j]
        g=dict(iv=float(v[j]),delta=float(delta),gamma=float(gamma),theta=float(theta),vega=float(vega))
        rec['candidate_greeks']=g;rec['tree_steps']=STEPS
        rec['reprice_error']=float(abs(fine[j]-rec['market_price']))
        rec['tree_price_difference']=float(abs(fine[j]-coarse[j]))
        tol=max(.01,.005*rec['market_price'])
        if abs(fine[j]-rec['market_price'])>tol or abs(fine[j]-coarse[j])>tol:
            rec.update(status='EXCLUDED_MODEL_CONVERGENCE',reason='300_600_TREE_PRICE_NOT_CONVERGED');continue
        if not all(math.isfinite(x) for x in g.values()) or gamma< -1e-6 or vega<=1e-6 or not (-1.001<=delta<=1.001):
            rec.update(status='EXCLUDED_MODEL_GREEK_STABILITY',reason='NONFINITE_OR_DEGENERATE_NUMERICAL_GREEKS');continue
        rec.update(status='MODEL_POINT_QUALIFIED',reason='COHERENT_SHARED_MODEL_VECTOR_NOT_VENDOR_RECONSTRUCTION',greeks=g,
                   numerical_greeks='600_STEP_CENTRAL_SPOT_0_5_PERCENT_VOL_0_001_THETA_ONE_CALENDAR_DAY')
    return out

def assess_and_store(c, records):
    ensure_schema(c)
    changed=[];outcomes=[];all_rows=[dict(r) for r in records]
    for r in all_rows:
        key=(r['ticker'],r['quote_date'],r['option_symbol'])
        prior=c.execute('SELECT input_hash,calc_version,payload_json FROM phantom_greek_assessments WHERE ticker=? AND quote_date=? AND option_symbol=?',key).fetchone()
        if prior and prior[0]==input_hash(r) and prior[1]==calc_version():continue
        changed.append((r,prior[2] if prior else None))
    # Compact model work together instead of paying a tree solve per tiny
    # ticker batch interspersed with already measured vendor vectors.
    def requires_model(item):
        r=item[0]
        return not (all(finite(r.get(g)) for g in GREEKS) and
                    ('VENDOR' in str(r.get('greeks_source','')).upper() or str(r.get('greeks_source','')).upper().startswith('MARKETDATA')))
    changed.sort(key=requires_model)
    for start in range(0,len(changed),128):
        batch=changed[start:start+128];assessments=assess_rows([r for r,_ in batch]);now=datetime.now(timezone.utc).isoformat()
        for (r,prior),a in zip(batch,assessments):
            key=(r['ticker'],r['quote_date'],r['option_symbol']);payload=json.dumps(a,sort_keys=True,allow_nan=False)
            c.execute('INSERT INTO phantom_greek_assessment_audit(ticker,quote_date,option_symbol,prior_payload_json,new_payload_json,assessed_at_utc) VALUES(?,?,?,?,?,?)',(*key,prior,payload,now))
            c.execute('''INSERT INTO phantom_greek_assessments VALUES(?,?,?,?,?,?,?,?)
              ON CONFLICT(ticker,quote_date,option_symbol) DO UPDATE SET input_hash=excluded.input_hash,
              calc_version=excluded.calc_version,status=excluded.status,payload_json=excluded.payload_json,assessed_at_utc=excluded.assessed_at_utc''',
              (*key,a['input_hash'],a['calc_version'],a['status'],payload,now))
            outcomes.append(a['status'])
    return {'changed':len(outcomes),'statuses':dict(Counter(outcomes))}

def effective_rows(c, records):
    """A full, current analytical vector or the unchanged raw observation.

    Explicit exclusions block analytical use. Raw values remain available as
    raw_* fields on an overlaid model row, never overwritten in the database.
    """
    rows=[dict(r) for r in records]
    if not rows or not has_table(c):return rows
    by_pair={}
    for r in rows:
        pair=(r['ticker'],r['quote_date'])
        if pair not in by_pair:
            by_pair[pair]={x[0]:(x[1],x[2],x[3]) for x in c.execute('SELECT option_symbol,input_hash,calc_version,payload_json FROM phantom_greek_assessments WHERE ticker=? AND quote_date=?',pair)}
        prior=by_pair[pair].get(r['option_symbol'])
        if not prior:continue
        if prior[0]!=input_hash(r) or prior[1]!=calc_version():
            if 'COMPUTED' in str(r.get('greeks_source','')):r['greeks_quality']='ASSESSMENT_STALE'
            r['assessment_status']='STALE';continue
        a=json.loads(prior[2]);r['assessment_status']=a['status'];r['assessment_calc_version']=a['calc_version']
        if a['status']=='MODEL_POINT_QUALIFIED':
            r.update({'raw_'+g:r.get(g) for g in GREEKS});r.update(a['greeks'])
            r['greeks_source']='COMPUTED_AMERICAN_ASSESSMENT' if a['model']=='AMERICAN_CRR' else 'COMPUTED_EUROPEAN_ASSESSMENT'
            r['greeks_quality']='OK;ADVISORY_MODEL_ASSUMPTIONS;'+a['reason']
        elif a['status'] not in ELIGIBLE:
            r['greeks_quality']='ASSESSED_EXCLUDED;'+a['status']+';'+a['reason']
    return rows

def session_assessment(c, day, tickers):
    if not has_table(c):return None
    counts=Counter();total=unassessed=0
    for t in sorted(set(tickers)):
        cur=c.execute('SELECT '+','.join(FIELDS)+' FROM chain_snapshots WHERE ticker=? AND quote_date=?',(t,day))
        names=[x[0] for x in cur.description];rows=[dict(zip(names,x)) for x in cur]
        saved={x[0]:(x[1],x[2],x[3]) for x in c.execute('SELECT option_symbol,input_hash,calc_version,status FROM phantom_greek_assessments WHERE ticker=? AND quote_date=?',(t,day))}
        for r in rows:
            total+=1;a=saved.get(r['option_symbol'])
            if a is None or a[0]!=input_hash(r) or a[1]!=calc_version():unassessed+=1
            else:counts[a[2]]+=1
    return dict(rows=total,unassessed_rows=unassessed,statuses=dict(counts),
                eligible_rows=sum(counts[s] for s in ELIGIBLE),
                excluded_rows=sum(n for s,n in counts.items() if s not in ELIGIBLE),calc_version=calc_version())

def assessed_history_rows(c,ticker,as_of=None):
    if not has_table(c):return []
    columns=','.join('c.'+k for k in FIELDS)
    sql='SELECT '+columns+''' FROM phantom_greek_assessments a JOIN chain_snapshots c
       ON c.ticker=a.ticker AND c.quote_date=a.quote_date AND c.option_symbol=a.option_symbol WHERE a.ticker=?'''
    args=[ticker]
    if as_of:sql+=' AND a.quote_date<=?';args.append(as_of)
    cur=c.execute(sql,args);names=[x[0] for x in cur.description]
    return effective_rows(c,[dict(zip(names,x)) for x in cur])

def assess_session(db_path, day, tickers, *, max_rows=20000, min_free_gib=15):
    """Bounded, exact-session assessment. Commit audit before deriving outputs."""
    import shutil
    import pandas as pd
    from scripts.finalize_phantom_weekly_snapshot import CHAIN_SELECT,_surface_and_atm
    report={'session':day,'rows_checked':0,'rows_changed':0,'affected_pairs':[],
            'provider_calls':0,'calc_version':calc_version()}
    deferred=[];before_digests={};reserved=0
    def digest(value):
        surfaces,atm=value
        return hashlib.sha256(json.dumps([surfaces,atm.to_dict('records')],sort_keys=True,default=str,allow_nan=True).encode()).hexdigest()
    with closing(sqlite3.connect(str(db_path),timeout=60)) as c:
        c.row_factory=sqlite3.Row;ensure_schema(c);c.commit()
        for t in sorted(set(tickers)):
            if shutil.disk_usage(Path(db_path).parent).free<min_free_gib*1024**3:
                raise RuntimeError('ASSESSMENT_DISK_RESERVE')
            records=[dict(x) for x in c.execute(CHAIN_SELECT+' WHERE ticker=? AND quote_date=? ORDER BY option_symbol',(t,day))]
            if not records:continue
            # Existing rows are cheap to validate; only new/stale work uses the cap.
            saved={x[0]:(x[1],x[2]) for x in c.execute('SELECT option_symbol,input_hash,calc_version FROM phantom_greek_assessments WHERE ticker=? AND quote_date=?',(t,day))}
            needed=[r for r in records if saved.get(r['option_symbol'])!=(input_hash(r),calc_version())]
            allowance=max_rows-reserved
            if allowance<=0 and needed:break
            selected=needed[:allowance]
            reserved+=len(selected)
            if selected:
                before_digests[t]=digest(_surface_and_atm(pd.DataFrame(effective_rows(c,records)),day,'SAME_CLOCK'))
            cheap=[]
            for r in selected:
                source=str(r.get('greeks_source','')).upper()
                if all(finite(r.get(g)) for g in GREEKS) and ('VENDOR' in source or source.startswith('MARKETDATA')):cheap.append(r)
                else:deferred.append(r)
            with c:change=assess_and_store(c,cheap)
            report['rows_checked']+=len(records);report['rows_changed']+=change['changed']
            if len(selected)<len(needed):break
        # Across-ticker compact batches make the bounded weekly path practical.
        for start in range(0,len(deferred),512):
            if shutil.disk_usage(Path(db_path).parent).free<min_free_gib*1024**3:raise RuntimeError('ASSESSMENT_DISK_RESERVE')
            with c:change=assess_and_store(c,deferred[start:start+512])
            report['rows_changed']+=change['changed']
        for t,before in before_digests.items():
            records=[dict(x) for x in c.execute(CHAIN_SELECT+' WHERE ticker=? AND quote_date=? ORDER BY option_symbol',(t,day))]
            after=digest(_surface_and_atm(pd.DataFrame(effective_rows(c,records)),day,'SAME_CLOCK'))
            if before!=after:
                report['affected_pairs'].append([t,day])
                with c:
                    c.execute('''INSERT INTO phantom_maintenance_pairs(ticker,quote_date,status,updated_at_utc)
                       VALUES(?,?,'PENDING_IV',?) ON CONFLICT(ticker,quote_date) DO UPDATE SET
                       status='PENDING_IV',updated_at_utc=excluded.updated_at_utc,last_error=NULL
                       WHERE phantom_maintenance_pairs.status!='IV_CONFLICT' ''',(t,day,datetime.now(timezone.utc).isoformat()))
        report['coverage']=session_assessment(c,day,tickers)
    report['status']='COMPLETE_ASSESSED_WITH_EXCLUSIONS' if not report['coverage']['unassessed_rows'] else 'ASSESSMENT_BATCH_LIMIT_REMAINDER'
    return report
