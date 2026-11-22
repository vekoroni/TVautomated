"""Additive target names. No new target, arrival clock, price or trading gate."""
from copy import deepcopy
import hashlib
import json
import math

VERSION='evening_target_roles_v1'
FIRST_LABEL='First target (median arrival)'
FULL_LABEL='Full target (original Lab)'

def _positive(value):
    if isinstance(value,bool):return None
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) and value>0 else None

def target_metadata(row):
    first=_positive(row.get('anticipated_level_q50'));full=_positive(row.get('anticipated_level'))
    return {'target_naming_version':VERSION,'target_role':'FIRST_TARGET_MEDIAN_ARRIVAL',
        'target_source_field':'anticipated_level_q50','target_label':FIRST_LABEL,
        'targets':{
            'first_target':{'label':FIRST_LABEL,'source_field':'anticipated_level_q50','price':first,
                'state':'AVAILABLE' if first is not None else 'UNASSESSED_MISSING_OR_INVALID',
                'arrival_clock_field':'anticipated_sessions_q50',
                'meaning':'Conditional underlying level used by existing target scenarios; not observed first option profit.'},
            'full_target':{'label':FULL_LABEL,'source_field':'anticipated_level','price':full,
                'state':'AVAILABLE' if full is not None else 'UNASSESSED_MISSING_OR_INVALID',
                'arrival_clock_field':None,'valuation_state':'REFERENCE_ONLY_NOT_REPRICED',
                'meaning':'Original Lab target reference; no new arrival clock or option payoff inferred.'}},
        'target_alias_policy':'Legacy target remains anticipated_level_q50. Neither level is relabelled as empirical first profit.'}

def scenario_metadata(name):
    labels={'TARGET_IF_REACHED':'First target if reached',
        'TARGET_IV_DOWN':'First target with lower IV','TARGET_IV_UP':'First target with higher IV',
        'TARGET_WIDE_EXIT':'First target with wider exit spread',
        'HALF_MOVE_IF_REACHED':'Half move to first target if reached',
        'INVALIDATION_AT_CHECKPOINT':'Invalidation at checkpoint','STALL':'No underlying move',
        'STALL_IV_DOWN':'No underlying move with lower IV'}
    is_target=name.startswith('TARGET_');half=name=='HALF_MOVE_IF_REACHED'
    return {'scenario_label':labels.get(name,name),'target_role':
        'FIRST_TARGET_MEDIAN_ARRIVAL' if is_target else 'HALF_MOVE_TO_FIRST_TARGET' if half else 'NOT_APPLICABLE',
        'target_source_field':'anticipated_level_q50' if is_target or half else None}

def annotate_payload(payload,row):
    """New saved publication annotation; frozen source packet is never edited."""
    first=_positive(row.get('anticipated_level_q50'));old=_positive(payload.get('target'))
    if first!=old:raise ValueError('TARGET_ANNOTATION_SOURCE_LEVEL_MISMATCH')
    out=deepcopy(payload);metadata=target_metadata(row)
    out.update(metadata)
    for s in out.get('scenarios',[]):s.update(scenario_metadata(s['scenario']))
    parent=payload.get('source_sha256')
    digest=hashlib.sha256(json.dumps({'parent_source_sha256':parent,'metadata':metadata},
        sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    out.update(source_sha256=digest,target_naming_parent_source_sha256=parent,
        target_naming_basis='ADDITIVE_SAVED_ANNOTATION_NO_REPRICING')
    return out
