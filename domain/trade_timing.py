"""1–n session timing, without providers, a wall clock, pricing or fixed hold buckets."""
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import math
import re
from avshunter.shared.xnys_calendar import NEW_YORK, is_xnys_session, session_bounds, xnys_sessions_between


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None


def day(value):
    try:
        if 'T' in str(value):
            instant = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if instant.tzinfo is None:
                return None
            return instant.astimezone(NEW_YORK).date()
        return date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


@lru_cache(maxsize=4096)
def sessions_between(start, end):
    return xnys_sessions_between(start, end)


@lru_cache(maxsize=4096)
def after_sessions(start, count):
    current = start
    for _ in range(count):
        current += timedelta(days=1)
        while not is_xnys_session(current):
            current += timedelta(days=1)
    return current


def expiry_requirement(hold, reference, *, monitor=3, exit_buffer=5):
    """Exact required expiry dates, excluding the reference session itself."""
    reference = day(reference)
    if reference is None:
        return None
    if number(monitor) is None or number(exit_buffer) is None:
        raise ValueError('session buffers must be finite nonnegative numbers')
    hold = number(hold)
    minimum_date = after_sessions(reference, math.ceil(exit_buffer + 1))
    required = math.ceil(hold + monitor + exit_buffer) if hold is not None else None
    required_date = after_sessions(reference, required) if required is not None else None
    return {'expiry_session_basis': 'XNYS_STRICTLY_AFTER_REFERENCE_THROUGH_EXPIRY',
            'expiry_reference_date': reference.isoformat(),
            'minimum_required_sessions': required,
            'minimum_required_expiry_date': required_date.isoformat() if required_date else None,
            'minimum_required_dte': (required_date-reference).days if required_date else None,
            'minimum_holdable_dte': (minimum_date-reference).days}


def remaining_hold(planned, planned_at, as_of):
    """Age a planning budget by completed sessions, not calendar days or partial sessions."""
    planned = number(planned)
    start, end = day(planned_at), day(as_of)
    if planned is None:
        return {'remaining_hold_sessions': None, 'hold_clock_state': 'NO_EVIDENCE_HOLD'}
    if start is None or end is None or end < start:
        return {'remaining_hold_sessions': None, 'hold_clock_state': 'REFERENCE_NOT_RECORDED_OR_INVALID'}
    # A timestamp before today's close has not spent today's full session.
    if 'T' in str(as_of):
        try:
            instant = datetime.fromisoformat(str(as_of).replace('Z', '+00:00'))
            if instant.tzinfo is None:
                raise ValueError('timestamp requires timezone')
            if is_xnys_session(end) and instant < session_bounds(end)[1]:
                end -= timedelta(days=1)
        except ValueError:
            return {'remaining_hold_sessions': None, 'hold_clock_state': 'REFERENCE_NOT_RECORDED_OR_INVALID'}
    elapsed = sessions_between(start, end)
    left = max(0, planned-elapsed)
    return {'remaining_hold_sessions': left, 'elapsed_hold_sessions': elapsed,
            'hold_clock_state': 'EXHAUSTED' if left == 0 else 'SAVED_PLANNING_BUDGET',
            'planned_hold_reference_date': start.isoformat(), 'timing_as_of': str(as_of),
            'hold_clock_basis': 'COMPLETED_XNYS_SESSIONS_SINCE_PLANNING_NOT_POSITION_ENTRY'}


def timing_for_row(row, *, planned_at=None, as_of=None):
    """A saved assessment. Original numeric fields and decisions are never overwritten."""
    planned = number(row.get('planned_hold_sessions'))
    anchor = row.get('planned_hold_reference_at_utc') or planned_at or row.get('evidence_session_date') or row.get('bar_data_asof')
    stamp = as_of or row.get('validation_evidence_cutoff_utc') or row.get('selected_quote_timestamp_utc') or row.get('quote_provider_timestamp_utc') or row.get('anticipated_valued_at_utc')
    budget = remaining_hold(planned, anchor, stamp)
    expiry = day(row.get('expiry') or row.get('contract_expiry'))
    symbol = str(row.get('contract_symbol') or row.get('selected_contract_symbol') or '')
    match = re.fullmatch(r'.+?(\d{6})[CP]\d{8}', symbol)
    if expiry is None and match:
        text = match[1]
        expiry = day(f'20{text[:2]}-{text[2:4]}-{text[4:]}')
    reference = day(stamp)
    requirement = expiry_requirement(budget['remaining_hold_sessions'], reference) or {}
    available = sessions_between(reference, expiry) if reference and expiry else None
    required = requirement.get('minimum_required_sessions')
    state = ('UNASSESSED_MISSING_DATES' if available is None else
             'NO_EVIDENCE_HOLD' if planned is None else
             'UNASSESSED_MISSING_HOLD_REFERENCE' if required is None else
             'HOLD_BUDGET_EXHAUSTED' if budget['remaining_hold_sessions'] == 0 else
             'INSUFFICIENT_XNYS_RUNWAY' if available < required else 'SUFFICIENT_XNYS_RUNWAY')
    q50, q80 = number(row.get('anticipated_sessions_q50')), number(row.get('anticipated_sessions_q80'))
    valuation = number(row.get('scenario_exit_sessions'))
    empirical = number(row.get('ev3_planned_hold_sessions'))
    return {'version': 'trade_timing_sessions_v1', 'planned_hold_sessions': planned,
            'arrival_median_sessions': q50, 'arrival_q80_sessions': q80,
            'valuation_horizon_sessions': valuation,
            'valuation_horizon_basis': 'SAVED_SCENARIO_EXIT' if valuation is not None else 'NOT_RECORDED',
            'valuation_reference_utc': row.get('anticipated_valued_at_utc'),
            'empirical_valuation_horizon_sessions': empirical,
            'empirical_horizon_state': 'NOT_RECORDED' if empirical is None else
                'DIFFERS_FROM_PLANNED_HOLD' if empirical != planned else 'MATCHES_PLANNED_HOLD',
            'planned_short_1_5': planned is not None and 1 <= planned <= 5,
            'arrival_short_1_5': q50 is not None and 1 <= q50 <= 5,
            'expiry_sessions_remaining': available, 'expiry_session_check_state': state,
            'expiry_calendar_days_remaining': max(0,(expiry-reference).days) if expiry and reference else None,
            'expiry_date': expiry.isoformat() if expiry else None,
            'timing_as_of': str(stamp) if stamp else None,
            **budget, **requirement}
