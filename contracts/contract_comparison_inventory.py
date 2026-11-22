"""Versioned observed-quote comparison schema. No selection or provider I/O."""
from copy import deepcopy
from datetime import datetime,timezone
import math
import re

SCHEMA='contract_comparison_inventory_v1'
FIELDS=('symbol','right','strike','expiry','dte','bid','ask','iv','delta','mid','spread_pct',
        'open_interest','volume','quote_timestamp_utc','gate_failed')
_UNSET=object()

def _number(value):
    if isinstance(value,bool):return None
    try:v=float(value)
    except (TypeError,ValueError):return None
    return v if math.isfinite(v) else None

def _raw(value):
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite_float':repr(value)}
    if isinstance(value,dict):return {k:_raw(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [_raw(v) for v in value]
    return deepcopy(value)

def normalize_quote(row,*,gate_failed=_UNSET):
    reasons={};bases={};out={k:None for k in FIELDS}
    symbol=str(row.get('symbol') or row.get('option_symbol') or '').strip().upper().removeprefix('O:')
    out['symbol']=symbol
    occ=re.fullmatch(r'([A-Z0-9.]+)(\d{6})([CP])(\d{8})',symbol)
    side=str(row.get('right') or row.get('side') or '').strip().upper()
    out['right']={'C':'CALL','CALL':'CALL','P':'PUT','PUT':'PUT'}.get(side)
    occ_side=('CALL' if occ[3]=='C' else 'PUT') if occ else None
    if out['right'] is None and not side and occ_side:
        out['right']=occ_side;bases['right']='EXACT_OCC_ENCODING'
    elif occ_side and out['right']!=occ_side:reasons['right']='OCC_SIDE_CONFLICT'
    elif out['right'] is None:reasons['right']='MISSING_OR_INVALID_SIDE'
    occ_expiry=None
    if occ:
        try:occ_expiry=datetime.strptime(occ[2],'%y%m%d').date().isoformat()
        except ValueError:reasons['symbol']='INVALID_OCC_EXPIRY'
    else:reasons['symbol']='MISSING_OR_INVALID_EXACT_OCC'
    expiry=row.get('expiration_date') or row.get('expiry')
    if expiry:
        try:out['expiry']=datetime.fromisoformat(str(expiry).replace('Z','+00:00')).date().isoformat()
        except (ValueError,TypeError):reasons['expiry']='INVALID_RECORDED_EXPIRY'
        if out['expiry'] and occ_expiry and out['expiry']!=occ_expiry:reasons['expiry']='OCC_EXPIRY_CONFLICT'
        bases['expiry']='RECORDED'
    elif occ_expiry:out['expiry']=occ_expiry;bases['expiry']='EXACT_OCC_ENCODING'
    else:reasons['expiry']='NOT_RECORDED_AND_OCC_UNAVAILABLE'
    for field in ('strike','dte','bid','ask','delta','mid','spread_pct','open_interest','volume'):
        value=row.get(field)
        if field=='mid' and value is None and row.get('mark') is not None:
            value=row['mark'];bases['mid']='RECORDED_MARK_NOT_RECONSTRUCTED'
        out[field]=_number(value)
        if out[field] is None:reasons[field]='NOT_RECORDED_IN_SAVED_SCOPE' if value is None else 'NONFINITE_OR_INVALID_NUMBER'
    if out['strike'] is None and row.get('strike') is None and occ:
        out['strike']=int(occ[4])/1000;bases['strike']='EXACT_OCC_ENCODING';reasons.pop('strike',None)
    if occ and out['strike'] is not None and out['strike']!=int(occ[4])/1000:reasons['strike']='OCC_STRIKE_CONFLICT'
    for field in ('strike','ask'):
        if out[field] is not None and out[field]<=0:out[field]=None;reasons[field]='NONPOSITIVE_RECORDED_VALUE'
    for field in ('bid','dte','open_interest','volume','spread_pct'):
        if out[field] is not None and out[field]<0:out[field]=None;reasons[field]='NEGATIVE_RECORDED_VALUE'
    if out['bid']==0:reasons['bid']='NO_OBSERVED_EXECUTABLE_BID'
    iv=row.get('iv') if row.get('iv') is not None else row.get('implied_vol')
    out['iv']=_number(iv)
    if out['iv'] is None:reasons['iv']='NOT_RECORDED_IN_SAVED_SCOPE' if iv is None else 'NONFINITE_OR_INVALID_IV'
    elif out['iv']<=0:out['iv']=None;reasons['iv']='NONPOSITIVE_RECORDED_IV'
    stamp=row.get('quote_timestamp_utc')
    if stamp is not None:
        try:
            t=datetime.fromisoformat(str(stamp).replace('Z','+00:00'))
            if t.tzinfo is None:raise ValueError('Unzoned time')
            out['quote_timestamp_utc']=t.astimezone(timezone.utc).isoformat()
            bases['quote_timestamp_utc']='RECORDED_TIMEZONE_AWARE'
        except (ValueError,TypeError):reasons['quote_timestamp_utc']='INVALID_OR_UNZONED_RECORDED_TIMESTAMP'
    elif row.get('updated_ts') is not None:
        epoch=_number(row['updated_ts'])
        try:
            if epoch is None:raise ValueError('Invalid epoch')
            out['quote_timestamp_utc']=datetime.fromtimestamp(epoch,timezone.utc).isoformat()
            bases['quote_timestamp_utc']='RECORDED_UPDATED_TS_EPOCH_SECONDS'
        except (ValueError,OverflowError,OSError):reasons['quote_timestamp_utc']='INVALID_RECORDED_EPOCH_SECONDS'
    else:reasons['quote_timestamp_utc']='NOT_RECORDED_IN_SAVED_SCOPE'
    if gate_failed is _UNSET:
        out['gate_failed']=row.get('gate_failed')
        gate_state='RECORDED' if 'gate_failed' in row else 'NOT_RECORDED_IN_SAVED_SCOPE'
    else:out['gate_failed']=gate_failed;gate_state='CLASSIFIED_PASS' if gate_failed is None else 'CLASSIFIED_REJECTION'
    if gate_state=='NOT_RECORDED_IN_SAVED_SCOPE':reasons['gate_failed']=gate_state
    invalid=bool(any('CONFLICT' in v for v in reasons.values())) or (
        out['bid'] is not None and out['ask'] is not None and out['bid']>out['ask'])
    if invalid:reasons['quote']='CROSSED_OR_IDENTITY_CONFLICT'
    out.update(schema=SCHEMA,raw_observation=_raw(dict(row)),field_reasons=reasons,field_basis=bases,
        iv_state='AVAILABLE_SAVED_VALUE' if out['iv'] is not None else 'UNAVAILABLE',gate_evidence_state=gate_state,
        quote_state='INVALID_OR_IDENTITY_CONFLICT' if invalid else 'NO_OBSERVED_EXECUTABLE_BID' if out['bid']==0 else
            'SAVED_TWO_SIDED_REFERENCE' if out['bid'] is not None and out['ask'] is not None else 'INCOMPLETE_SAVED_QUOTE',
        authority='COMPARISON_ONLY_NO_SELECTION_OR_EXECUTION_PERMISSION')
    return out

def normalize_inventory(record):
    """Whole saved artifact view; does not claim complete provider chains."""
    out={k:deepcopy(v) for k,v in record.items() if k!='available_contracts_both_sides'}
    out.update(schema=SCHEMA,source_schema='SAVED_PHANTOM_RAW_SESSION_INVENTORY',
               raw_observations_preserved=True,provider_chain_completeness='NOT_ESTABLISHED')
    sides={}
    for side in ('CALL','PUT'):
        original=record.get('available_contracts_both_sides',{}).get(side,{})
        raw=original.get('contracts',[])
        if not isinstance(raw,list):raise ValueError('INVALID_SAVED_CONTRACT_LIST')
        sides[side]={**{k:deepcopy(v) for k,v in original.items() if k!='contracts'},
            'state':original.get('state') or ('AVAILABLE' if raw else 'NOT_PRESENT_IN_SAVED_SCOPE'),
            'total_contracts':original.get('total_contracts',len(raw)),'recorded_contracts':len(raw),
            'truncated':bool(original.get('truncated',False)),
            'truncation_basis':'AS_RECORDED' if 'truncated' in original else 'COMPLETE_RECORDED_ARTIFACT_NOT_PROVIDER_CHAIN',
            'contracts':[normalize_quote(q) for q in raw]}
    out['available_contracts_both_sides']=sides
    return out
