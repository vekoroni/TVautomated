"""Source-bound Evening opportunity assessment. No selection, execution or I/O.

The research route is independent of legacy execution verdicts. Historical
clock quantiles, assumed-path crossings and checkpoint payoffs are different
evidence types. No probability, fill or future price path is manufactured.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from collections import Counter
from domain.trade_timing import day, after_sessions, sessions_between, expiry_requirement
from domain.option_valuation import (american_crr_values, european_bsm_value, exercise_style,
    valuation_policy, resolve_rate, resolve_dividend, entry_cost_usd_per_share,
    exit_proceeds_usd_per_share, cost_basis)
from domain.crossing_scenario import crossing_config
from domain.long_option_execution import SPREAD_POLICY
from domain.evening_target_roles import VERSION as TARGET_NAMING_VERSION, target_metadata, scenario_metadata

VERSION = 'evening_opportunity_assessment_v1'
FIELDS = ('evening_assessment_version', 'evening_assessment_route', 'evening_assessment_label',
    'evening_assessment_reasons', 'evening_assessment_warnings', 'evening_assessment_id',
    'evening_assessment_source_sha256', 'evening_assessment_json')
HOME_FIELDS = FIELDS[:-1]
LABELS = {
 'EVENING_QUALIFIED': 'Evening qualified — entry validation pending',
 'WAITING_FOR_TRIGGER': 'Waiting for trigger',
 'HUMAN_REVIEW_LONGER_HORIZON': 'Human review — longer horizon',
 'CONTRACT_UNSUITABLE': 'Contract unsuitable',
 'ASSESSMENT_INCOMPLETE': 'Assessment incomplete',
 'THESIS_INVALIDATED': 'Thesis invalidated',
 'OPPORTUNITY_CLOSED': 'Opportunity closed — no new-entry qualification',
 'EVENING_NOT_ASSESSED': 'Evening assessment not published',
}

def num(value):
    if isinstance(value, bool): return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError): return None

def text(value):
    s = str(value or '').strip()
    return '' if s.upper() in {'NAN','NULL','NONE','N/A'} else s

def instant(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo is not None else None
    except (ValueError, TypeError): return None

def dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def source_inputs(row, run_id):
    keys = ('ticker','thesis_id','trade_lane_candidate_id','direction','canonical_direction',
        'pipeline_mode','signal_price','invalidation_price','anticipated_level_q50','anticipated_level',
        'anticipated_sessions_q50','anticipated_sessions_q80','planned_hold_sessions',
        'contract_symbol','anticipated_contract_symbol','contract_bid','contract_ask','contract_iv',
        'contract_oi','contract_volume','contract_delta','selected_quote_timestamp_utc',
        'quote_provider_timestamp_utc','anticipated_valued_at_utc','bar_data_asof',
        'crossing_quote_spot','crossing_contract_symbol','crossing_quote_timestamp_utc',
        'thesis__readiness','thesis__event_status','thesis_structure_alignment',
        'direction_conflict_status','contract_repair_required','contract_repair_resolved_at_open',
        'valuation_rate_annual','valuation_rate_basis','valuation_dividend_yield_annual',
        'valuation_dividend_basis','earnings_disclosure')
    keys += ('quote_tier','veto_flags','atm_iv','iv_rank','iv_percentile','iv_history_state','iv_vs_hv')
    # Invalid/nonfinite input must not become a valid zero in a source receipt.
    return {'run_id':run_id, 'assessment_version':VERSION, 'target_naming_version':TARGET_NAMING_VERSION, 'valuation_policy':dict(valuation_policy()),
        'scenario_policy':dict(crossing_config()),
        **{k: (None if isinstance(row.get(k),float) and
        not math.isfinite(row[k]) else row.get(k)) for k in keys}}

def assess_evening(row, *, run_id):
    """Return additive fields; never alter rank, selection, verdict or authority."""
    frozen = text(row.get('evening_assessment_json'))
    mode = text(row.get('pipeline_mode')).upper()
    morning = text(row.get('morning_data_state')).upper() == 'AVAILABLE'
    if morning or mode in {'MORNING','MORNING_VALIDATION','LIVE'}:
        # Morning carries the frozen Evening assessment; it cannot rewrite it.
        return {k:row.get(k) for k in FIELDS} if frozen else {}
    inputs = source_inputs(row, run_id)
    digest = hashlib.sha256(dump(inputs).encode()).hexdigest()
    identity = {k:inputs.get(k) for k in ('run_id','ticker','thesis_id','trade_lane_candidate_id','contract_symbol')}
    assessment_id = hashlib.sha256(dump(identity).encode()).hexdigest()
    errors, warnings, unsuitable = [], [], []
    side = text(row.get('canonical_direction') or row.get('direction')).upper()
    hold = num(row.get('planned_hold_sessions'))
    arrival = num(row.get('anticipated_sessions_q50'))
    target = num(row.get('anticipated_level_q50'))
    stop = num(row.get('invalidation_price'))
    symbol = text(row.get('contract_symbol')).upper().removeprefix('O:')
    match = re.fullmatch(r'([A-Z0-9.]+)(\d{6})([CP])(\d{8})', symbol)
    quote = instant(row.get('selected_quote_timestamp_utc') or row.get('quote_provider_timestamp_utc'))
    valued = instant(row.get('anticipated_valued_at_utc'))
    reference = day(row.get('bar_data_asof'))
    bid,ask,iv,oi = (num(row.get(k)) for k in ('contract_bid','contract_ask','contract_iv','contract_oi'))
    spot = num(row.get('signal_price'))
    cross_spot = num(row.get('crossing_quote_spot'))
    if cross_spot is not None:
        if text(row.get('crossing_contract_symbol')).upper().removeprefix('O:') != symbol:
            errors.append('QUOTE_SPOT_CONTRACT_IDENTITY_MISMATCH')
        elif instant(row.get('crossing_quote_timestamp_utc')) != quote:
            errors.append('QUOTE_SPOT_TIMESTAMP_MISMATCH')
        else: spot = cross_spot
    if side not in {'CALL','PUT'}: errors.append('DIRECTION_UNASSESSED')
    if not text(row.get('thesis_id')): errors.append('THESIS_IDENTITY_MISSING')
    if not text(run_id): errors.append('RUN_IDENTITY_MISSING')
    if hold is None or hold < 1: errors.append('PLANNED_TRADING_HOLD_MISSING_OR_INVALID')
    if reference is None or quote is None: errors.append('SAVED_QUOTE_OR_SESSION_CLOCK_MISSING')
    elif day(quote.isoformat()) != reference: errors.append('QUOTE_SESSION_MISMATCH')
    if valued is not None and quote is not None and valued != quote:
        errors.append('SOURCE_VALUATION_QUOTE_MISMATCH')
    if text(row.get('anticipated_contract_symbol')) and text(row['anticipated_contract_symbol']).upper().removeprefix('O:') != symbol:
        errors.append('SOURCE_VALUATION_CONTRACT_MISMATCH')
    if any(x is None or x <= 0 for x in (spot,target,stop)):
        errors.append('THESIS_PRICE_GEOMETRY_MISSING')
    invalidated = (spot is not None and stop is not None and side in {'CALL','PUT'} and
        (spot <= stop if side == 'CALL' else spot >= stop))
    if spot and target and side in {'CALL','PUT'} and (target <= spot if side == 'CALL' else target >= spot):
        errors.append('TARGET_NOT_AHEAD_OF_REFERENCE')
    status = text(row.get('thesis__readiness')).upper()
    invalidated = invalidated or status == 'CLOSED_INVALIDATED'
    if status.startswith('CLOSED_') and status != 'CLOSED_INVALIDATED':
        warnings.append('THESIS_ALREADY_CLOSED_OR_OUTCOME_REACHED')
    if not status: errors.append('TRIGGER_READINESS_MISSING')
    if text(row.get('thesis_structure_alignment')).upper() != 'ALIGNED':
        errors.append('TRADE_SIDE_STRUCTURE_NOT_ALIGNED')
    if text(row.get('direction_conflict_status')).upper() != 'NO_CONFLICT':
        errors.append('DIRECTION_CONFLICT_REQUIRES_REVIEW')
    if text(row.get('lab_verdict')).upper() == 'BLOCKED' or text(row.get('veto_flags')) not in {'','[]'}:
        errors.append('UPSTREAM_SAFETY_BLOCK_RETAINED')
    expiry = strike = None
    if not match: errors.append('EXACT_OCC_CONTRACT_MISSING_OR_INVALID')
    else:
        try: expiry = datetime.strptime(match[2],'%y%m%d').date()
        except ValueError: errors.append('INVALID_OCC_EXPIRY')
        strike = int(match[4])/1000
        root = text(row.get('ticker')).upper()
        aliases = {'BF.B':'BFB','BRK.B':'BRKB','MOG.A':'MOGA'}
        if match[1] not in {root,aliases.get(root,root)}: errors.append('OCC_UNDERLYING_MISMATCH')
        if match[3] != ('C' if side == 'CALL' else 'P'): errors.append('OCC_THESIS_SIDE_MISMATCH')
        if strike <= 0: errors.append('INVALID_OCC_STRIKE')
    if bid is None or ask is None or iv is None: errors.append('QUOTE_OR_IV_MISSING')
    elif bid < 0 or ask <= 0 or bid > ask or iv <= 0: errors.append('INVALID_QUOTE_OR_IV')
    elif bid == 0: unsuitable.append('NO_OBSERVED_EXECUTABLE_BID')
    spread = (ask-bid)/((ask+bid)/2) if bid is not None and ask and bid >= 0 and bid <= ask else None
    if spread is not None and spread > float(SPREAD_POLICY['executable_max']):
        unsuitable.append('SPREAD_EXCEEDS_GOVERNED_EXECUTABLE_CEILING')
    if oi is None: errors.append('CONTRACT_OI_UNASSESSED')
    elif oi < 100: unsuitable.append('LIQUIDITY_TIER_C_OI_BELOW_100')
    elif ask and ask < 1.5 and bid is not None and ask-bid > .10+1e-9:
        unsuitable.append('SMALL_PREMIUM_ABSOLUTE_SPREAD_OVER_010')
    if text(row.get('contract_repair_required')).upper()=='TRUE':
        warnings.append('HISTORICAL_REPAIR_FLAG_RETAINED_SELECTED_FACTS_ASSESSED_SEPARATELY')
    if text(row.get('quote_tier'))=='C': unsuitable.append('SAVED_LIQUIDITY_TIER_C')
    cfg = crossing_config()
    required = expiry_requirement(hold, reference, monitor=cfg['monitor_buffer_sessions'],
        exit_buffer=cfg['exit_buffer_sessions']) if reference else None
    runway = sessions_between(reference,expiry) if reference and expiry and expiry>=reference else None
    if expiry and reference and expiry <= reference: unsuitable.append('CONTRACT_EXPIRED_AT_REFERENCE')
    if required and required['minimum_required_sessions'] is not None and runway is not None and runway < required['minimum_required_sessions']:
        unsuitable.append('INSUFFICIENT_TRADING_HOLD_PLUS_BUFFER_RUNWAY')
    if arrival is None or arrival <= 0: errors.append('TARGET_ARRIVAL_UNASSESSED')
    elif hold and hold <= 20 and arrival > hold: errors.append('TARGET_ARRIVAL_OUTSIDE_TRADING_WINDOW')
    scenarios=[]
    can_value = not errors and reference and expiry and runway is not None
    if can_value:
        # A long thesis stays in human review, with economics on its actual
        # arrival/hold clocks. Do not misleadingly revalue a distant target at
        # every 1–20 checkpoint or impose a 20-session hold cap on it.
        checkpoints = sorted({math.ceil(arrival),math.ceil(hold),math.ceil(hold)+5} if hold>20 else
            {1,5,10,20,math.ceil(hold),math.ceil(arrival),math.ceil(hold)+5})
        rate,rb = resolve_rate(row.get('valuation_rate_annual'),row.get('valuation_rate_basis'))
        div,db = resolve_dividend(row.get('valuation_dividend_yield_annual'),row.get('valuation_dividend_basis'))
        jobs=[]
        for n in checkpoints:
            at=after_sessions(reference,n)
            for name,level,iv_mult,spread_mult in (
                ('TARGET_IF_REACHED',target,1.,1.),('INVALIDATION_AT_CHECKPOINT',stop,1.,1.),
                ('HALF_MOVE_IF_REACHED',spot+(target-spot)/2,1.,1.),
                ('STALL',spot,1.,1.),('TARGET_IV_DOWN',target,cfg['iv_down_multiple'],1.),
                ('STALL_IV_DOWN',spot,cfg['iv_down_multiple'],1.),
                ('TARGET_IV_UP',target,1/cfg['iv_down_multiple'],1.),
                ('TARGET_WIDE_EXIT',target,1.,cfg['exit_spread_stress_multiple'])):
                record={'checkpoint_sessions':n,'exit_date':at.isoformat(),'scenario':name,
                    **scenario_metadata(name),
                    'spot':level,'iv':iv*iv_mult,'exit_spread_multiple':spread_mult,
                    'state':'BEYOND_EXPIRY' if at>expiry else 'CONDITIONAL_NOT_FORECAST'}
                scenarios.append(record)
                if at<=expiry: jobs.append((record,max((expiry-at).days,0)/365))
        if jobs:
            if exercise_style(row.get('ticker'))=='AMERICAN':
                values=american_crr_values([r['spot'] for r,_ in jobs],strike,[t for _,t in jobs],rate,div,
                    [r['iv'] for r,_ in jobs],side=='CALL',steps=int(valuation_policy()['crr_steps']))
                model='AMERICAN_CRR'
            else:
                values=[european_bsm_value(side,r['spot'],strike,t,r['iv'],rate=rate,dividend_yield=div) for r,t in jobs]
                model='BSM_EUROPEAN'
            entry=entry_cost_usd_per_share(ask)
            for (record,_),value in zip(jobs,values):
                if not math.isfinite(float(value)) or float(value)<0:
                    record['state']='UNASSESSED_NUMERIC_MODEL_RESULT'
                    errors.append('UNASSESSED_NUMERIC_MODEL_RESULT')
                    continue
                proceeds=exit_proceeds_usd_per_share(float(value),bid=bid,ask=ask,
                    exit_spread_multiple=record['exit_spread_multiple'])
                record.update(model=model,model_value_per_share=float(value),entry_cost_per_contract=entry*100,
                    exit_proceeds_per_contract=proceeds*100,net_pnl_per_contract=(proceeds-entry)*100,
                    net_return_fraction=proceeds/entry-1,rate=rate,rate_basis=rb,dividend_yield=div,dividend_basis=db)
        central = next((r for r in scenarios if r['scenario']=='TARGET_IF_REACHED' and r['checkpoint_sessions']==math.ceil(arrival)),None)
        if hold<=20 and central and central.get('net_return_fraction',-1)<float(cfg['threshold_floor']):
            unsuitable.append('TARGET_PAYOFF_BELOW_GOVERNED_MONETISATION_FLOOR')
    if invalidated: route='THESIS_INVALIDATED'
    elif status.startswith('CLOSED_'): route='OPPORTUNITY_CLOSED'
    elif hold is not None and hold>20: route='HUMAN_REVIEW_LONGER_HORIZON'
    elif errors: route='ASSESSMENT_INCOMPLETE'
    elif unsuitable: route='CONTRACT_UNSUITABLE'
    elif status!='READY_FOR_HUMAN_REVIEW': route='WAITING_FOR_TRIGGER'
    else: route='EVENING_QUALIFIED'
    empirical={k:row.get(k) for k in row if k.startswith('monetisation_')}
    payload={'version':VERSION,'run_id':run_id,'assessment_id':assessment_id,'source_sha256':digest,
        'route':route,'label':LABELS[route],'authority':'RESEARCH_ONLY_NO_ENTRY_PERMISSION',
        'execution_validation':'ENTRY_VALIDATION_PENDING','planned_trading_hold_sessions':hold,
        'routing_clock':'ORIGINAL_GOVERNED_PLANNED_HOLD_NOT_DTE_OR_ASSUMED_CROSSING',
        'reference_session':reference.isoformat() if reference else None,
        'quote_timestamp_utc':quote.isoformat() if quote else None,'contract_symbol':symbol,
        'spot':spot,'target':target,'invalidation':stop,'arrival_q50_sessions':arrival,
        'move_from_bound_spot_pct':abs(target/spot-1)*100 if spot and target else None,
        'contract_state':'UNASSESSED' if errors else 'UNSUITABLE' if unsuitable else 'SUITABLE_SAVED_REFERENCE',
        'expiry_sessions':runway,'runway_requirement':required,'spread_fraction_mid':spread,
        'iv_intelligence':{'selected_contract_iv':iv,'iv_units':'DECIMAL_ANNUAL',
            'iv_down_multiple':cfg['iv_down_multiple'],'iv_up_multiple':1/cfg['iv_down_multiple'],
            'atm_iv':row.get('atm_iv'),'iv_rank':row.get('iv_rank'),'iv_percentile':row.get('iv_percentile'),
            'iv_history_state':row.get('iv_history_state'),'iv_vs_hv':row.get('iv_vs_hv'),
            'basis':'SAVED_DESCRIPTIVE_CONTEXT_NOT_CHEAPNESS_OR_PROFIT_PROOF',
            'warning':'IV can reprice premium independently of the underlying move; historical context may be unavailable.'},
        'errors':list(dict.fromkeys(errors)),'contract_limitations':list(dict.fromkeys(unsuitable)),
        'warnings':warnings,'cost_basis':cost_basis(bid),'scenarios':scenarios,
        'empirical_clock':empirical,'empirical_clock_state':row.get('monetisation_clock_state') or 'UNASSESSED_NOT_PUBLISHED',
        'crossing_scenario_state':row.get('crossing_state') or 'NOT_PUBLISHED',
        'crossing_authority':'ASSUMED_PATH_NOT_EMPIRICAL_OR_FORECAST',
        'limitations':['Conditional checkpoint prices are assumptions, not a predicted path or expected return.',
            'Invalidation is valued at the checkpoint; stop fills, gaps and first-barrier order are not established.',
            'Ask entry plus fees; model exit less half spread plus close fee, not observed fills.',
            'No additional impact/slippage estimate beyond spread; live broker validation required.',
            'Saved historical hit quantiles do not establish the chance of future profit.'],
        'earnings_disclosure':row.get('earnings_disclosure'),'legacy_verdict':row.get('lab_verdict'),
        'ranking_basis':'LEGACY_CONDITIONAL_PROXY_NOT_CALIBRATED_EXPECTED_PROFIT',
        'selection_owner':'CLAUDE_UNCHANGED'}
    payload.update(target_metadata(row))
    reasons=list(dict.fromkeys(errors+unsuitable))
    return dict(zip(FIELDS,(VERSION,route,LABELS[route],'; '.join(reasons),'; '.join(warnings),
        assessment_id,digest,dump(payload))))

def attach_assessments(rows, *, run_id):
    output=[{**r,**assess_evening(r,run_id=run_id)} for r in rows]
    return output,dict(Counter(r.get('evening_assessment_route','EVENING_NOT_ASSESSED') for r in output))
