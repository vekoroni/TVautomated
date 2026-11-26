"""MAC-03/07/04/05. Pure advisory evidence, no network or database writers."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import math
import re

import pandas as pd

from avshunter.shared.xnys_calendar import is_xnys_session, is_early_close, session_bounds

DRIVERS = ('policy', 'inflation', 'growth_labour', 'credit', 'liquidity', 'oil',
           'dollar', 'volatility', 'positioning_breadth', 'rates', 'rotation')


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def short_windows(series, sessions, policy):
    """Changes on a complete exchange-session grid; no forward fill or future data.

    Callers align release-lagged FRED observations before calling. Percentiles rank
    signed changes separately from absolute unusualness (not forecast likelihood).
    """
    result = {}
    for name, raw in series.items():
        if name in policy['historical_only']:
            result[name] = {'status': 'EXCLUDED_HISTORICAL_ONLY'}
            continue
        s = raw.reindex(sessions)
        rows = {}
        for window in policy['windows_sessions']:
            change = s.diff(window)
            # Never bridge a missing session in the requested window.
            change = change.where(s.notna().rolling(window + 1).sum() == window + 1)
            if name.startswith('DGS'):
                change = change * 100
                unit = 'bp'
            elif name.startswith('PRICE:'):
                change = ((s / s.shift(window)) - 1) * 100
                change = change.where(s.notna().rolling(window + 1).sum() == window + 1)
                unit = 'percent'
            else:
                unit = policy.get('series_units', {}).get(name, 'native_units')
            current = number(change.iloc[-1]) if len(change) else None
            hist = change.iloc[-policy['percentile_history_sessions']:].dropna()
            enough = current is not None and len(hist) >= policy['percentile_min_samples']
            pct = float((hist <= current).mean()) if enough else None
            unusual = float((hist.abs() <= abs(current)).mean()) if enough else None
            rows[str(window)] = {'change': current, 'unit': unit, 'signed_percentile': pct,
                'unusualness_percentile': unusual, 'evidence_count': len(hist),
                'turning_point': unusual is not None and unusual >= policy['turning_point_percentile'],
                'status': 'OK' if enough else 'INSUFFICIENT_HISTORY',
                'as_of_session': str(sessions[-1].date()) if len(sessions) else None}
        result[name] = rows
    return result


def driver_readings(payload, sources, policy):
    packet, bond, liq = (sources.get(k) or {} for k in ('packet', 'bond', 'liquidity'))
    extras = packet.get('extras') or {}
    conditions = payload.get('conditions') or {}
    out = {k: {'state': 'MISSING', 'status': 'MISSING', 'owner': 'macro_board.cycle_evidence',
               'source_values': [], 'conflicts': [], 'dimensions': {}, 'age_days': None,
               'evidence_status': 'MISSING', 'authority': 'ADVISORY_ONLY'} for k in DRIVERS}

    def reading(key, state, facts, dimensions=None, status='OBSERVED'):
        row = out[key]
        row.update(state=state, status=status if state != 'MISSING' else 'MISSING',
                   source_values=facts, dimensions=dimensions or {},
                   evidence_status='OBSERVED' if facts else 'MISSING')
        row['observation_evidence'] = (conditions.get('observations') or {}).get(key, {})
        return row

    def fact(source, value, unit='label', observation=None):
        return {'source': source, 'value': value, 'unit': unit, 'observation_date': observation,
                'publication_at_utc': None, 'clock_status': 'SOURCE_CLOCK_UNKNOWN' if not observation else 'OBSERVATION_DATE_ONLY'}

    credit = extras.get('credit') or {}
    bc = bond.get('credit_stress') or {}
    hy, z = number(liq.get('HY_OAS')), number(liq.get('HY_Z'))
    wide = (hy is not None and hy > policy['credit_wide_pct']) or liq.get('Credit_Stress') in ('WIDE', 'ELEVATED', 'EXTREME')
    warning = (z is not None and z >= policy['credit_warning_z']) or bc.get('stress_level') in ('ELEVATED', 'EXTREME')
    state = 'WIDE_WARNING' if wide and warning else 'WIDE' if wide else 'WARNING' if warning else str(liq.get('Credit_Stress') or bc.get('stress_level') or 'MISSING')
    facts = [fact('liquidity.HY_OAS', hy, 'percent'), fact('liquidity.HY_Z', z, 'zscore'),
             fact('bond.credit_stress', bc), fact('packet.extras.credit', credit),
             fact('board.conditions.credit', (conditions.get('current') or {}).get('credit'))]
    r = reading('credit', state, [f for f in facts if f['value'] not in (None, {})],
                {'spread_level': liq.get('Credit_Stress'), 'relative_etf_momentum': bc.get('stress_level'),
                 'board_20s_momentum': (conditions.get('current') or {}).get('credit')})
    if credit.get('state') == 'NEUTRAL' and state in ('WIDE_WARNING', 'WIDE', 'WARNING'):
        r['conflicts'].append({'source': 'packet.extras.credit', 'label': 'NEUTRAL',
            'disposition': 'SUPERSEDED_FOR_NARRATIVE_ONLY', 'reason': 'Different fixed-threshold rule; original value preserved'})

    curve = bond.get('yield_curve') or {}
    proxy = bond.get('zn_futures') or {}
    momentum = proxy.get('rate_regime_signal')
    delta = number((curve.get('curve_move_5d_detail') or {}).get('d2y_bp'))
    state = 'EASING' if delta is not None and delta < 0 else 'TIGHTENING' if delta is not None and delta > 0 else 'STABLE' if delta == 0 else 'MISSING'
    r = reading('rates', state, [fact('bond.yield_curve.d2y_5d', delta, 'bp', curve.get('as_of_date')),
                fact('bond.zn_futures.rate_regime_signal', momentum)],
                {'policy_stance': packet.get('rates_impulse'), 'yield_momentum': momentum,
                 'curve_state': curve.get('curve_state'), 'd2y_5d_bp': delta},
                 'STALE' if curve.get('stale_flag') else 'OBSERVED')
    if packet.get('rates_impulse') and state != 'MISSING':
        r['conflicts'].append({'source': 'packet.rates_impulse', 'label': packet['rates_impulse'],
            'disposition': 'SEPARATE_DIMENSION_NOT_OVERRIDDEN', 'reason': 'Policy stance is not yield momentum'})
    # rates_impulse is a combined legacy label, not a verified central-bank policy reading.
    r['dimensions']['policy_stance_evidence_status'] = 'LEGACY_COMPOSITE_LABEL_NOT_VERIFIED_POLICY'

    lv = str(liq.get('Liquidity_Regime') or '')
    age = re.search(r'STALE\s*[-_ ]\s*(\d+)d', lv, re.I)
    lr = reading('liquidity', lv.split(' (')[0].upper() or 'MISSING',
                 [fact('liquidity.Liquidity_Regime', lv), fact('packet.extras.liquidity', extras.get('liquidity'))] if lv else [],
                 {'board_net_liquidity_momentum': (conditions.get('current') or {}).get('liquidity')},
                 'STALE' if age else 'OBSERVED')
    lr['age_days'] = int(age[1]) if age else None
    if lv and lr['dimensions']['board_net_liquidity_momentum']:
        lr['conflicts'].append({'source': 'board.conditions.liquidity', 'label': lr['dimensions']['board_net_liquidity_momentum'],
            'disposition': 'DIFFERENT_MEASUREMENT', 'reason': 'Net liquidity and WALCL/RRP regime are not the same series'})

    strength = {t: number(((payload.get('etfs') or {}).get(t, {}).get('metrics') or {}).get('rs_vs_spy_20d'))
                for t in policy['defensive_etfs']}
    fresh = {t: ((payload.get('etfs') or {}).get(t, {}).get('metrics') or {}).get('status') == 'FRESH' for t in strength}
    leaders = [t for t, v in strength.items() if v is not None and v > policy['defensive_relative_min_pp'] and fresh[t]]
    rotation = 'DEFENSIVE_BROADENING' if len(leaders) >= policy['defensive_min_members'] else 'MIXED' if any(v is not None for v in strength.values()) else 'MISSING'
    rr = reading('rotation', rotation, [fact('board.rs_vs_spy_20d', strength, 'percentage_points', payload.get('as_of_session'))],
                 {'leading_defensive_etfs': leaders, 'relative_not_absolute': True,
                  'rapid_rotation_detector': packet.get('rotation_detail')})
    breadth = ((payload.get('opportunity') or {}).get('leadership') or {}).get('breadth') or {}
    if breadth.get('state') in (None, 'UNKNOWN', 'MISSING'):
        rr['evidence_status'] = 'PARTIAL_PARTICIPATION_UNAVAILABLE'
    if (packet.get('rotation_detail') or {}).get('summary'):
        rr['conflicts'].append({'source': 'packet.rotation_detail', 'label': packet['rotation_detail']['summary'],
            'disposition': 'NARROW_DETECTOR_NOT_GENERAL_ROTATION', 'reason': 'Commodity/paper detector does not measure sector leadership'})
    current = conditions.get('current') or {}
    for key, ck in [('oil', 'oil'), ('dollar', 'dollar'), ('volatility', 'market_vol'), ('positioning_breadth', 'market_breadth')]:
        value = current.get(ck)
        row = reading(key, value or 'MISSING', [fact('board.conditions.' + ck, value, observation=payload.get('as_of_session'))] if value else [],
                      {'measurement': ck})
        row['observation_evidence'] = (conditions.get('observations') or {}).get(ck, {})
    # No inferred inflation/growth/policy label from prose; publish their numeric evidence only.
    for key, cols in [('policy', ['FEDFUNDS', 'EFFR', 'SOFR']), ('inflation', ['CPIAUCSL', 'CPILFESL', 'T10YIE']),
                      ('growth_labour', ['PAYEMS', 'UNRATE', 'ICSA', 'GDPC1'])]:
        out[key]['source_values'] = [fact('fred.' + c, (sources.get('fred_latest') or {}).get(c), policy['series_units'].get(c, 'native_units')) for c in cols
                                     if (sources.get('fred_latest') or {}).get(c) is not None]
        if out[key]['source_values']:
            out[key]['evidence_status'] = 'MEASURED_VALUES_NO_AUTHORED_READING'
    # Carry cadence/observation status at the point of use, including unknown
    # clocks. A producer's file-generation date is never a substitute.
    for key, row in out.items():
        observed = row.get('observation_evidence') or {}
        row['freshness'] = {'oldest_observation_date': observed.get('oldest'),
                            'sessions_old': observed.get('sessions_old'),
                            'status': 'STALE' if row['status'] == 'STALE' else 'MISSING' if row['status'] == 'MISSING' else 'SOURCE_CLOCK_UNVERIFIED'}
        if observed.get('oldest'):
            row['age_days'] = (date.fromisoformat(payload['as_of_session']) - date.fromisoformat(observed['oldest'])).days
            limit = policy['max_age_days']['weekly' if key == 'liquidity' else 'daily']
            row['freshness']['status'] = 'STALE' if row['age_days'] > limit or row['status'] == 'STALE' else 'WITHIN_DECISION_AGE_RULE'
            if row['age_days'] > limit: row['status'] = 'STALE'
        elif row['source_values'] and all(f.get('observation_date') for f in row['source_values']):
            oldest = min(f['observation_date'] for f in row['source_values'])
            row['age_days'] = (date.fromisoformat(payload['as_of_session']) - date.fromisoformat(oldest)).days
            row['freshness'].update(oldest_observation_date=oldest,
                status='WITHIN_DECISION_AGE_RULE' if row['age_days'] <= policy['max_age_days']['daily'] else 'STALE')
            if row['freshness']['status'] == 'STALE': row['status'] = 'STALE'
        for f in row['source_values']:
            f['freshness_status'] = 'SOURCE_CLOCK_UNKNOWN' if not f['observation_date'] else row['freshness']['status']
        if key in ('policy', 'inflation', 'growth_labour'):
            for f in row['source_values']:
                native = f['value']
                if isinstance(native, dict) and native.get('observation_date'):
                    f.update(value=native['value'], observation_date=native['observation_date'],
                             freshness_status=native.get('status', 'UNKNOWN'), clock_status='OBSERVATION_DATE_ONLY')
        if row['freshness']['status'] == 'SOURCE_CLOCK_UNVERIFIED' and row['status'] == 'OBSERVED':
            row['status'] = 'FRESHNESS_UNVERIFIED'
    return out


def forced_calendar(as_of, closes, policy):
    year = as_of.year + (as_of.month == 12)
    month = 1 if as_of.month == 12 else as_of.month + 1
    end = date(year, month, monthrange(year, month)[1])
    events = []
    day = as_of + timedelta(days=1)
    etfs = policy['trend_etfs']
    def add(kind, d, **extra):
        events.append({'event_id': f'{kind}:{d}', 'date': str(d), 'kind': kind, 'etfs': etfs,
                       'source': 'avshunter.shared.xnys_calendar', 'prediction': None,
                       'evidence_type': 'CALENDAR_NOT_DIRECTIONAL_FLOW_FORECAST', **extra})
    while day <= end:
        if day.weekday() < 5 and not is_xnys_session(day): add('MARKET_HOLIDAY', day)
        if is_early_close(day): add('HALF_DAY', day, close_utc=session_bounds(day)[1].isoformat())
        if is_xnys_session(day):
            nxt = day + timedelta(days=1)
            while not is_xnys_session(nxt): nxt += timedelta(days=1)
            if nxt.month != day.month:
                add('MONTH_END', day)
                if day.month in (3, 6, 9, 12): add('QUARTER_END', day)
                if day.month == 12: add('YEAR_END', day)
        third_friday = date(day.year, day.month, 1)
        third_friday += timedelta(days=(4 - third_friday.weekday()) % 7 + 14)
        expiry = third_friday
        while not is_xnys_session(expiry): expiry -= timedelta(days=1)
        if day == expiry: add('MONTHLY_OPTIONS_EXPIRY', day, nominal_third_friday=str(third_friday))
        day += timedelta(days=1)
    for y in range(as_of.year, end.year + 1):
        start, stop = date(y, 11, 1), date(y, 12, policy['tax_loss_end_day_december'])
        if stop >= as_of and start <= end:
            add('TAX_LOSS_WINDOW', max(start, as_of), window_start=str(start), window_end=str(stop),
                limitation='Seasonal review window, not a guaranteed flow')
    grid = pd.DatetimeIndex([d for d in pd.date_range(as_of - timedelta(days=500), as_of) if is_xnys_session(d.date())])
    levels = {}
    for t in etfs:
        s = closes[t].reindex(grid) if t in closes else pd.Series(index=grid, dtype=float)
        spot = number(s.iloc[-1]) if len(s) else None
        levels[t] = {}
        for w in policy['trend_windows_sessions']:
            tail = s.iloc[-w:]
            avg = float(tail.mean()) if len(tail) == w and tail.notna().all() else None
            levels[t][str(w)] = {'average': avg, 'distance_pct': (spot / avg - 1) * 100 if avg and spot else None,
                'status': 'OK' if avg is not None and spot is not None else 'MISSING',
                'reference_session': str(as_of), 'source': 'saved_split_adjusted_price_rows',
                'adjustment': 'SOURCE_STORE_BASIS_NO_NEW_ADJUSTMENTS'}
    return {'as_of_session': str(as_of), 'through': str(end), 'events': events, 'trend_levels': levels}
