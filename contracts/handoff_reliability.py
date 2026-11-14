"""Pure, additive reliability facts shared by exports and Lab; never decisions.

No Lane B selection/entry/exit policy, wall clock, providers or data writes.
Historical source labels are preserved, not reconciled by granting authority.
"""
from __future__ import annotations
import math
from typing import Any, Mapping
from domain.trade_timing import day

RELIABILITY_FIELDS = (
    'handoff_reliability_version', 'handoff_duration_status', 'handoff_duration_n',
    'handoff_duration_quantile_basis', 'handoff_return_kind',
    'contract_repair_current_state', 'contract_repair_current_basis',
    'contract_trading_dte_reference_date', 'contract_calendar_dte_reference_date',
    'quote_exit_state', 'handoff_catalyst_type', 'handoff_catalyst_date',
    'handoff_earnings_state', 'handoff_verified_earnings_date',
    'handoff_target_roles_state', 'handoff_rank_authority',
    'handoff_calculation_state',
)

def _text(v):
    return '' if v is None else str(v).strip()

def _number(v):
    if isinstance(v, bool): return None
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError): return None

def _date(v):
    d=day(v)
    return d.isoformat() if d else None

def reliability_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    status = row.get('anticipated_evidence_status') or row.get('thesis_duration_status') or 'UNASSESSED'
    n = row.get('anticipated_evidence_n')
    if n in (None, ''): n=row.get('thesis_duration_n')
    resolved=_text(row.get('contract_repair_resolved_at_open')).upper()=='TRUE'
    pending=_text(row.get('economics_recompute_required')).upper()=='TRUE'
    if resolved:
        repair='QUOTE_REPAIRED_ECONOMICS_PENDING' if pending else 'RESOLVED_FOR_SELECTED_CONTRACT'
    elif _text(row.get('contract_repair_required')).upper()=='TRUE': repair='REPAIR_REQUIRED'
    elif row.get('contract_repair_status'): repair=_text(row['contract_repair_status'])
    else: repair='UNASSESSED'
    bid,ask=_number(row.get('contract_bid')),_number(row.get('contract_ask'))
    quote=('NOT_RECORDED' if bid is None or ask is None else
           'INVALID_QUOTE' if bid<0 or ask<=0 or bid>ask else
           'NO_OBSERVED_EXECUTABLE_BID' if bid==0 else 'SAVED_TWO_SIDED_QUOTE_NOT_A_FILL')
    catalyst_type=row.get('catalyst_type')
    earnings_source=_text(row.get('earnings_source')).upper()
    generic=('TYPE STRUCTURAL' in earnings_source or
             (_text(catalyst_type).upper()=='STRUCTURAL' and row.get('earnings_date')==row.get('catalyst_date') and
              'CATALYST' in earnings_source))
    edate=row.get('earnings_date')
    estate=('UNVERIFIED_GENERIC_CATALYST' if generic else
            'REPORTED_EARNINGS_WITH_SOURCE' if edate and earnings_source else
            'UNVERIFIED_DATE' if edate else 'NOT_RECORDED')
    target=_number(row.get('exit_target_price')); scenario=_number(row.get('scenario_target_exit_spot'))
    return dict(zip(RELIABILITY_FIELDS, (
        'handoff_reliability_v1', status, n,
        'TARGET_EVENT_CONDITIONAL_QUANTILES_NOT_HIT_PROBABILITY',
        'CONDITIONAL_MODELLED_PAYOFF_NOT_EXPECTED_RETURN',
        repair, 'SELECTED_CONTRACT_ASSESSMENT; original repair flags retained as history',
        _date(row.get('evidence_session_date') or row.get('bar_data_asof')),
        _date(row.get('quote_provider_timestamp_utc') or row.get('anticipated_valued_at_utc') or row.get('selected_quote_timestamp_utc')),
        quote, catalyst_type, _date(row.get('catalyst_date')),
        estate, _date(edate) if estate=='REPORTED_EARNINGS_WITH_SOURCE' and
        _text(row.get('earnings_date_confirmation')).upper() in {'CONFIRMED','AGREED','PROVIDER_CONFIRMED'} else None,
        'DIFFERENT_REFERENCES_NOT_ONE_EXIT_POLICY' if target is not None and scenario is not None and abs(target-scenario)>.01 else 'SAME_REFERENCE' if target is not None and scenario is not None else 'UNASSESSED',
        'LEGACY_CONDITIONAL_HEURISTIC_NOT_CALIBRATED_EXPECTED_RETURN',
        'UNASSESSED_NONFINITE_SOURCE_VALUE' if row.get('scenario_target_return_on_premium') not in (None,'') and _number(row.get('scenario_target_return_on_premium')) is None else
        row.get('valuation_calculation_state') or ('SAVED_CONDITIONAL_SCENARIO' if _number(row.get('scenario_target_return_on_premium')) is not None else 'NOT_COMPUTED'),
    )))
