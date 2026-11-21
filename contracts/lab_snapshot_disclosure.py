"""Lab-only snapshot scoping. No repricing, decisions, wall clock or providers."""
from copy import deepcopy
from datetime import datetime
import json
import math
from pathlib import Path
from functools import lru_cache
from contracts.lab_review_display import valuation_disclosure


@lru_cache(maxsize=1)
def feed_policy():
    return json.loads((Path(__file__).resolve().parents[1]/'config/governed_constants_v1.json').read_text(encoding='utf-8-sig'))['option_quote_feed']


def num(value):
    if isinstance(value,bool): return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError): return None


def date_part(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z','+00:00')).date().isoformat()
    except (ValueError,TypeError): return None


def scope_snapshot(row):
    """Copy display fields; preserve incompatible historical values separately."""
    out=dict(row)
    reference=row.get('snapshot_reference_inputs') or {}
    if reference.get('match_basis')=='EXACT_TICKER_CONTRACT_THESIS_VALUATION_INSTANT':
        row={**reference,**{k:v for k,v in row.items() if v not in (None,'')}}
    selected=str(row.get('contract_symbol') or '').upper().removeprefix('O:')
    current=valuation_disclosure(row)
    current_state=current['state']
    legacy={k:deepcopy(v) for k,v in row.items()
            if k.startswith('monetisability_timevalue_') or k=='monetisability_state_timevalue'}
    previous=(row.get('reference_snapshots') or {}).get('historical_timevalue') or {}
    if row.get('monetisability_state_timevalue')=='HISTORICAL_REFERENCE_ONLY' and previous.get('fields'):
        legacy=deepcopy(previous['fields'])
    has_legacy=any(legacy.get(k) not in (None,'') for k in (
        'monetisability_timevalue_value_per_share','monetisability_timevalue_profit_pct',
        'monetisability_timevalue_as_of_session'))
    mismatches=[]
    if has_legacy:
        comparisons=(('AS_OF_SESSION',date_part(legacy.get('monetisability_timevalue_as_of_session')),
                      date_part(row.get('anticipated_valued_at_utc'))),
                     ('EXPIRY',date_part(legacy.get('monetisability_timevalue_expiry_date')),
                      date_part(row.get('expiry') or row.get('contract_expiry'))),
                     ('IV',num(legacy.get('monetisability_timevalue_iv_used')),num(row.get('contract_iv'))))
        for name,old,new in comparisons:
            if old is None or new is None: mismatches.append(name+'_UNVERIFIED')
            elif old!=new: mismatches.append(name+'_MISMATCH')
        ask=num(row.get('contract_ask')); value=num(legacy.get('monetisability_timevalue_value_per_share'))
        ret=num(legacy.get('monetisability_timevalue_profit_pct'))
        implied=value/(1+ret/100) if value is not None and ret is not None and ret>-100 else None
        if ask is None or implied is None: mismatches.append('ENTRY_ASK_UNVERIFIED')
        elif abs(implied-ask)>max(.001,abs(ask)*.00001): mismatches.append('ENTRY_ASK_MISMATCH')
        if str(row.get('monetisability_evaluation_phase') or '').upper().startswith('EOD'):
            mismatches.append('EOD_REFERENCE_PHASE')
        if not selected or current_state not in {'MORNING_REFERENCE','DOCUMENTED_REFERENCE'}:
            mismatches.append('CURRENT_VALUATION_LINEAGE_UNVERIFIED')
    if mismatches:
        references=deepcopy(row.get('reference_snapshots') or {})
        references['historical_timevalue']={'fields':legacy,'mismatch_reasons':mismatches,
            'authority':'HISTORICAL_REFERENCE_ONLY_NOT_CURRENT_CONTRACT',
            'evaluation_phase':row.get('monetisability_evaluation_phase'),
            'original_contract_symbol_claim':row.get('monetisability_contract_symbol'),
            'warning':'Original symbol may have been overlaid; expiry, clock, IV and entry inputs govern compatibility.'}
        out['reference_snapshots']=references
        for key in legacy: out[key]=None
        out['monetisability_state_timevalue']='HISTORICAL_REFERENCE_ONLY'
        out['monetisability_timevalue_reason']='NOT_RECOMPUTED_FOR_CURRENT_SNAPSHOT'
    feed=feed_policy()
    observation=row.get('quote_provider_timestamp_utc') or row.get('selected_quote_timestamp_utc')
    source=row.get('selected_quote_source') or row.get('quote_provider')
    matching_feed=str(source or '').upper()==str(feed.get('provider') or '').upper()
    fallback=str(row.get('planned_hold_source') or '').startswith('VOLATILITY_')
    arrival=num(row.get('anticipated_sessions_q50'))
    disclosure={'version':'lab_snapshot_disclosure_v1','authority':'DISPLAY_ONLY',
        'current_scenario':{'state':current_state,'family':'ANTICIPATED_MOVE_CONDITIONAL_NET_PAYOFF',
            'contract_symbol':row.get('anticipated_contract_symbol'),
            'valued_at_utc':row.get('anticipated_valued_at_utc'),
            'exit_sessions':row.get('scenario_exit_sessions'),'exit_date':row.get('scenario_exit_date'),
            'model':row.get('valuation_model'),'cost_basis':row.get('valuation_cost_basis'),
            'return_kind':'CONDITIONAL_MODEL_SCENARIO_NOT_EXPECTED_OR_REALISED_RETURN'},
        'doi_scenario':{'state':row.get('scenario_state'),'reason':row.get('scenario_reason'),
                        'contract_symbol':row.get('scenario_contract_symbol'),
                        'scope':'SEPARATE_DOI_FAMILY_NOT_STATUS_OF_CURRENT_CONDITIONAL_PAYOFF'},
        'historical_timevalue':{'state':'REFERENCE_ONLY' if mismatches else 'MATCHING_SAVED_INPUTS' if has_legacy else 'NOT_RECORDED',
            'mismatch_reasons':mismatches,'as_of_session':legacy.get('monetisability_timevalue_as_of_session'),
            'expiry':legacy.get('monetisability_timevalue_expiry_date'),
            'return_pct':legacy.get('monetisability_timevalue_profit_pct')},
        'timing':{'hold_basis':'VOLATILITY_PLANNING_FALLBACK' if fallback else row.get('planned_hold_source') or 'NOT_RECORDED',
            'arrival_state':'HISTORICAL_ARRIVAL_ESTIMATE' if arrival is not None else 'NO_HISTORICAL_ARRIVAL_ESTIMATE',
            'evidence_status':row.get('anticipated_evidence_status'),'evidence_n':row.get('anticipated_evidence_n'),
            'ev3_status':row.get('ev3_status'),'ev3_reason':row.get('ev3_reason_detail') or row.get('ev3_reason_code'),
            'warning':'Planned hold and target arrival are not time to +20%/+30% option profit.'},
        'quote':{'state':'SAVED_QUOTE_REFERENCE_NOT_LIVE' if observation else 'QUOTE_OBSERVATION_TIME_NOT_RECORDED',
            'observation_at_utc':observation,'provider':source or 'NOT_RECORDED',
            'configured_delay_seconds':feed['disclosed_delay_seconds'] if matching_feed else None,
            'configured_effective_window_seconds':feed['freshness_max_seconds'] if matching_feed else None,
            'saved_assessment_state':row.get('execution_viability_quote_age_state') or row.get('quote_age_state') or row.get('quote_freshness'),
            'saved_raw_age_minutes':row.get('execution_viability_quote_age_minutes'),
            'saved_effective_age_seconds':row.get('execution_viability_quote_age_seconds') if row.get('execution_viability_quote_age_seconds') not in (None,'') else row.get('quote_age_seconds'),
            'entry_quote_verified':False,'instruction':'Live broker re-quote required before entry; saved feed-window status is not entry freshness.'}}
    out['snapshot_disclosure']=disclosure
    return out
