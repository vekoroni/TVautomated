"""Typed actuarial hand-off. Descriptive evidence is not an option probability.

No providers, model fits, database writes or implicit outcome/horizon aliases.
Legacy rates are retained for audit without inventing their denominators.
"""
from __future__ import annotations
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'actuarial_evidence_v1'
FIELDS = ('actuarial_evidence_json', 'actuarial_evidence_state',
          'actuarial_evidence_reasons', 'actuarial_evidence_source_run_id',
          'actuarial_evidence_binding')
IDENTITIES = ('behaviour_state_hash', 'behaviour_state_key', 'layer2__matched_state_key')

def number(value):
    try:
        n=float(value)
        return n if not isinstance(value,bool) and math.isfinite(n) else None
    except (ValueError,TypeError,OverflowError):return None

def present(value):
    return value is not None and str(value).strip().lower() not in {'','nan','none','null'}

def integer(value):
    n=number(value)
    return int(n) if n is not None and n>=0 and n==int(n) else None

def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()

def index_cache_outcomes(cache):
    result={}
    for row in cache.to_dict('records'):
        key=str(row.get('state_key',''))
        result[key]=row if key not in result else None
    return result

def cache_outcomes(result, cache):
    """Read the exact matched cache cohort, not its generic 20d sample_size.

    Counts already exist per horizon in the cache but older lookup result
    objects drop them. Missing numerators/cutoffs remain missing. This does
    not reconstruct integer wins from a rounded rate or rebuild the cache.
    """
    get=result.get if isinstance(result,dict) else lambda k,d=None:getattr(result,k,d)
    key=get('matched_key')
    indexed=cache if isinstance(cache,dict) else index_cache_outcomes(cache)
    row=indexed.get(str(key)) or {}
    cohorts=[]
    for h in (5,10,20):
        rate=number(get(f'win_rate_{h}d'))
        cached_rate=number(row.get(f'win_rate_{h}d'))
        same=rate is not None and cached_rate is not None and abs(rate-cached_rate)<1e-12
        cohorts.append({'cohort_id':str(key or ''), 'event_id':'UNDERLYING_RETURN_GT_ZERO',
            'event_basis':'PRODUCER_CONTRACT_ACB02', 'side':'UP', 'horizon':h,'clock':'DAILY_BARS',
            'rate':rate,'rate_unit':'FRACTION',
            'n':integer(row.get(f'sample_size_{h}d')) if same else None,
            'wins':integer(row.get(f'win_count_{h}d')) if same else None,
            'losses':integer(row.get(f'loss_count_{h}d')) if same else None,
            'observation_cutoff_session':row.get('observation_cutoff_session') if present(row.get('observation_cutoff_session')) else None,
            'denominator_source':f'MATCHED_CACHE.sample_size_{h}d' if same else 'UNVERIFIED',
            'source_cache_row_sha256':sha(row) if same else None,
            'maturity_basis':'NON_NULL_HORIZON_OUTCOMES' if same else 'UNVERIFIED'})
    return cohorts

def load_records(run_dir):
    """Resolve exact-run records, retaining each immutable record's metadata."""
    root=Path(run_dir); path=root/'enrichment'/f'actuarial_{root.name}.jsonl'
    if not path.is_file():return {},'MISSING',None
    raw=path.read_bytes();records={}
    try:
        for line in raw.decode('utf-8-sig').splitlines():
            if not line.strip():continue
            r=json.loads(line)
            if r.get('run_id')!=root.name:return {},'RUN_MISMATCH',hashlib.sha256(raw).hexdigest()
            if r.get('stage')!='actuarial':continue
            # NAN is a literal roster identity, not a missing numeric value.
            if not isinstance(r.get('payload'),dict) or r.get('ticker') is None or not str(r['ticker']).strip():
                return {},'INVALID',hashlib.sha256(raw).hexdigest()
            t=str(r['ticker']).strip().upper()
            # Conflicting same-run records cannot be disambiguated by ticker
            # alone. Do not choose whichever state happened to be appended last.
            if t in records and records[t]['payload']!=r['payload']:
                records[t]={'run_id':root.name,'ticker':t,'payload':{},'conflict':True}
            else:records[t]=r
        return records,'PRESENT',hashlib.sha256(raw).hexdigest()
    except (ValueError,UnicodeError):return {},'INVALID',hashlib.sha256(raw).hexdigest()

def cohort_issues(c):
    issues=[]; n=integer(c.get('n')); w=integer(c.get('wins')); l=integer(c.get('losses')); rate=number(c.get('rate'))
    if n is None or n<=0:issues.append('MISSING_HORIZON_DENOMINATOR')
    if w is None or l is None:issues.append('MISSING_SUCCESS_FAILURE_COUNTS')
    elif n is None or w+l!=n:issues.append('COUNT_MISMATCH')
    if rate is None or not 0<=rate<=1 or c.get('rate_unit')!='FRACTION':issues.append('INVALID_RATE_OR_UNIT')
    elif n and w is not None and abs(rate-w/n)>1e-10:issues.append('RATE_COUNT_MISMATCH')
    if not present(c.get('event_id')) or c.get('event_id')=='UNVERIFIED_LEGACY_EVENT':issues.append('OUTCOME_UNVERIFIED')
    if integer(c.get('horizon')) in (None,0) or c.get('clock') not in {'DAILY_BARS','XNYS_SESSIONS','CALENDAR_DAYS'}:issues.append('HORIZON_UNVERIFIED')
    if not present(c.get('cohort_id')) or c.get('side') not in {'UP','DOWN','CALL','PUT'}:issues.append('COHORT_OR_SIDE_UNVERIFIED')
    if c.get('maturity_basis')!='NON_NULL_HORIZON_OUTCOMES':issues.append('MATURITY_UNVERIFIED')
    return issues

def bind_evidence(row, record, run_id, as_of_session, ledger_state='PRESENT', ledger_sha=None):
    p=record.get('payload',{}) if record else {}; blockers=[]
    if ledger_state!='PRESENT':blockers.append('LEDGER_'+ledger_state)
    if not record:blockers.append('NO_ACTUARIAL_RECORD')
    if record and (record.get('run_id')!=run_id or record.get('conflict')):blockers.append('RECORD_IDENTITY_CONFLICT')
    if record and str(record.get('ticker','')).upper()!=str(row.get('ticker','')).upper():blockers.append('TICKER_MISMATCH')
    if present(row.get('run_id')) and str(row['run_id'])!=run_id:blockers.append('CANDIDATE_RUN_MISMATCH')
    shared=[k for k in IDENTITIES if present(row.get(k)) and present(p.get(k))]
    binding='MATCHED' if shared and all(str(row[k])==str(p[k]) for k in shared) else 'UNVERIFIED' if not shared else 'CONFLICTED'
    if binding!='MATCHED':blockers.append('CANDIDATE_STATE_'+binding)
    if p.get('available') is not True or p.get('valid') is not True or p.get('no_match') is not False:
        blockers.append('SOURCE_NOT_VALIDATED')
    if p.get('deferred') is not False: blockers.append('SOURCE_DEFERRED_OR_STATUS_UNVERIFIED')
    if not present(p.get('enriched_by')):blockers.append('PRODUCER_UNVERIFIED')
    if p.get('enrichment_pass_result') not in {'EXACT_MATCH','FALLBACK_MATCH'}:blockers.append('SOURCE_COMPLETION_UNVERIFIED')
    if record and not present(record.get('input_sha256')):blockers.append('SOURCE_INPUT_HASH_UNVERIFIED')
    cohorts=p.get('outcome_evidence')
    if not isinstance(cohorts,list):
        cohorts=[{'event_id':'UNVERIFIED_LEGACY_EVENT','cohort_id':p.get('matched_key'),
            'horizon':h,'clock':'UNVERIFIED_LEGACY_DAYS','side':'UNVERIFIED',
            'rate':number(p.get(f'win_rate_{h}d')),'rate_unit':'UNVERIFIED',
            'n':integer(p.get(f'sample_size_{h}d')),'wins':None,'losses':None,
            'maturity_basis':'UNVERIFIED'} for h in (5,10,20)]
    clean=[]
    for item in cohorts:
        if not isinstance(item,dict):blockers.append('INVALID_COHORT');continue
        c=dict(item);issues=cohort_issues(c)
        cutoff=c.get('observation_cutoff_session')
        try:
            if date.fromisoformat(str(cutoff))>date.fromisoformat(as_of_session):issues.append('FUTURE_OBSERVATIONS')
        except (ValueError,TypeError):issues.append('OBSERVATION_CUTOFF_UNVERIFIED')
        c['issues']=issues;c['state']='QUALIFIED' if not issues else 'UNASSESSED';clean.append(c)
    state='QUALIFIED' if clean and not blockers and all(not c['issues'] for c in clean) else 'PARTIAL' if p else 'MISSING'
    return {'schema':SCHEMA,'source_run_id':run_id,'requested_session':as_of_session,
        'binding':binding,'state':state,'blockers':blockers,'cohorts':clean,
        'source_identity':{k:p.get(k) for k in IDENTITIES},
        'reported_generic_sample_size':p.get('sample_size'),
        'reported_layer2_sample_size':p.get('layer2__sample_size'),
        'source_record_sha256':sha(record) if record else None,'ledger_sha256':ledger_sha,
        'source_input_sha256':record.get('input_sha256') if record else None,
        'producer_version':record.get('calculation_version') if record else None,
        'recorded_at_utc':record.get('recorded_at_utc') if record else None,
        'cache_built_at':p.get('cache_built_at'),'authority':'EVIDENCE_ONLY'}

def evidence_fields(e):
    def clean(v):
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list):return [clean(x) for x in v]
        return None if isinstance(v,float) and not math.isfinite(v) else v
    return dict(zip(FIELDS,(json.dumps(clean(e),sort_keys=True,allow_nan=False,default=str),e['state'],
        '|'.join(e['blockers']+sorted({x for c in e['cohorts'] for x in c['issues']})),e['source_run_id'],e['binding'])))

def carry_fields(row):
    # An explicit empty reasons string means no blockers, not a missing owner.
    return {k:row[k] if k in row else row.get('vg__'+k) for k in FIELDS}

def wire_frame(frame, run_dir, as_of_session):
    records,status,digest=load_records(run_dir); out=frame.copy(); fields=[]
    for row in frame.to_dict('records'):
        e=bind_evidence(row,records.get(str(row.get('ticker','')).upper()),Path(run_dir).name,
                        as_of_session,status,digest)
        fields.append(evidence_fields(e))
    for k in FIELDS:out[k]=[f[k] for f in fields]
    return out,{'rows':len(out),'ledger_state':status,'ledger_sha256':digest,
                'states':dict(Counter(f['actuarial_evidence_state'] for f in fields)),
                'bindings':dict(Counter(f['actuarial_evidence_binding'] for f in fields))}

def publish_handoff(input_path, run_dir, output_path, as_of_session):
    """New artifact only. Never patch an existing historical input or snapshot."""
    import pandas as pd
    source=Path(input_path);dest=Path(output_path)
    if dest.exists() or source.resolve()==dest.resolve():raise FileExistsError('Actuarial hand-off is immutable; use a fresh output')
    # Copy original cell text verbatim; enrichment must not round numeric inputs.
    frame=pd.read_csv(source,low_memory=False,keep_default_na=False,dtype=str)
    out,receipt=wire_frame(frame,run_dir,as_of_session)
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x',encoding='utf-8',newline='') as f:out.to_csv(f,index=False)
    receipt.update(input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),schema=SCHEMA,
                   source_run_id=Path(run_dir).name,as_of_session=as_of_session)
    with dest.with_suffix('.receipt.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
    return receipt

def prepare_phantom_handoff(run_dir, input_path):
    root=Path(run_dir);meta=json.loads((root/'run_meta.json').read_text(encoding='utf-8-sig'))
    session=date.fromisoformat(meta['session_date']).isoformat()
    dest=root/'options'/f'options_intelligence_actuarial_{root.name}.csv'
    if dest.exists():
        if not valid_handoff(root,dest,input_path,session):raise FileExistsError('Existing actuarial hand-off does not match current inputs')
        return dest,{'status':'REUSED_VALIDATED'}
    return dest,publish_handoff(input_path,root,dest,session)

def valid_handoff(root, dest, source, session=None):
    try:
        if session is None:
            session=date.fromisoformat(json.loads((Path(root)/'run_meta.json').read_text(encoding='utf-8-sig'))['session_date']).isoformat()
        receipt=json.loads(Path(dest).with_suffix('.receipt.json').read_text(encoding='utf-8'))
        _,state,digest=load_records(root)
        return (receipt['schema']==SCHEMA and receipt['source_run_id']==Path(root).name
            and (session is None or receipt['as_of_session']==session)
            and receipt['input_sha256']==hashlib.sha256(Path(source).read_bytes()).hexdigest()
            and receipt['output_sha256']==hashlib.sha256(Path(dest).read_bytes()).hexdigest()
            and receipt['ledger_sha256']==digest)
    except (OSError,ValueError,KeyError,TypeError):return False

def preferred_options_input(run_dir):
    root=Path(run_dir);folder=root/'options';run=root.name
    original=folder/f'options_intelligence_{run}.csv'
    phantom=folder/f'options_intelligence_phantom_{run}.csv'
    actuarial=folder/f'options_intelligence_actuarial_{run}.csv'
    if phantom.is_file():return phantom
    if actuarial.is_file() and valid_handoff(root,actuarial,original):return actuarial
    return original

def comparison(row, market):
    """Only identical events, sides, horizons, clocks and measured populations."""
    try:
        e=json.loads(row.get('actuarial_evidence_json') or '{}')
        if e.get('schema')!=SCHEMA:return None,None,['MISSING_TYPED_ACTUARIAL_EVIDENCE']
        reasons=list(e.get('blockers',[]))
        if e.get('source_run_id')!=row.get('run_id',e.get('source_run_id')):reasons.append('RUN_MISMATCH')
        if not all(present(e.get(k)) for k in ('source_record_sha256','source_input_sha256','ledger_sha256','producer_version')):
            reasons.append('PROVENANCE_UNVERIFIED')
        if e.get('binding')!='MATCHED':reasons.append('CANDIDATE_BINDING_UNVERIFIED')
        candidates=e.get('cohorts',[])
        event_matches=[c for c in candidates if c.get('event_id')==market.get('event_id')]
        same_event=[c for c in event_matches if c.get('side')==market.get('side')]
        if not event_matches:reasons.append('OUTCOME_MISMATCH')
        elif not same_event:reasons.append('SIDE_MISMATCH')
        aligned=[c for c in same_event if c.get('horizon')==market.get('horizon') and c.get('clock')==market.get('clock')]
        if same_event and not aligned:reasons.append('HORIZON_OR_CLOCK_MISMATCH')
        if len(aligned)>1:reasons.append('AMBIGUOUS_COHORT')
        c=aligned[0] if len(aligned)==1 else None
        if c:
            reasons.extend(cohort_issues(c));reasons.extend(c.get('issues',[]))
            try:
                cutoff=date.fromisoformat(str(c.get('observation_cutoff_session')))
                if cutoff>date.fromisoformat(str(e.get('requested_session'))):reasons.append('FUTURE_OBSERVATIONS')
            except (ValueError,TypeError):reasons.append('OBSERVATION_CUTOFF_UNVERIFIED')
        probability=number(market.get('probability'))
        if market.get('measure')!='CALIBRATED_EVENT_PROBABILITY' or not present(market.get('calibration_version')):
            reasons.append('MARKET_PROBABILITY_UNVERIFIED')
        if probability is None or not 0<=probability<=1:reasons.append('INVALID_MARKET_PROBABILITY')
        if c and c.get('observation_cutoff_session')!=market.get('observation_cutoff_session'):
            reasons.append('EVIDENCE_CUTOFF_MISMATCH')
        return c,probability,sorted(set(reasons))
    except (ValueError,TypeError,AttributeError):return None,None,['INVALID_TYPED_ACTUARIAL_EVIDENCE']
