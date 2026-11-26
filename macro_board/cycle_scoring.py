"""MAC-06/09. Cumulative exchange-session outcomes; missing evidence is not a loss."""
from datetime import date, datetime, timedelta, timezone
import math

import pandas as pd

from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
from .cycle_io import digest
from .cycle_evidence import number


def instant(value):
    ts = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if ts.tzinfo is None: raise ValueError('Timestamp must be timezone-aware; filename is not a clock')
    return ts.astimezone(timezone.utc)


def forward_calls(rows, known_at_utc, source_sha, policy):
    instant(known_at_utc)
    out = []
    for i, row in enumerate(rows):
        if row.get('horizon') not in policy['horizon_map']: raise ValueError('Unknown forward horizon')
        p = number(row.get('bullish_prob_pct'))
        if p is not None and not 0 <= p <= 100: raise ValueError('Invalid source score percentage')
        rid = digest([source_sha, i, row['horizon']])
        out.append({'record_id': rid, 'call_id': rid, 'known_at_utc': known_at_utc,
                    'source_sha256': source_sha, 'source_row': dict(row), 'source_horizon': row['horizon'],
                    'horizon_sessions': policy['horizon_map'][row['horizon']],
                    'evaluation': 'CUMULATIVE_NEXT_OPEN_TO_CLOSE_H', 'direction': row.get('direction'),
                    'source_bullish_score_fraction': None if p is None else p / 100,
                    'probability_status': policy['forward_probability_status'], 'authority': 'ADVISORY_ONLY',
                    'calc_version': policy['calc_version'], 'policy_sha256': digest(policy)})
    return out


def expected_sessions(call_time, horizon):
    day = call_time.date()
    while not is_xnys_session(day) or session_bounds(day)[0] < call_time:
        day += timedelta(days=1)
    days = []
    while len(days) < horizon:
        if is_xnys_session(day): days.append(day)
        day += timedelta(days=1)
    return days


def score_forward(calls, bars, as_of_utc):
    now = instant(as_of_utc)
    result = []
    for call in calls:
        days = expected_sessions(instant(call['known_at_utc']), call['horizon_sessions'])
        row = {'call_id': call['call_id'], 'source_horizon': call['source_horizon'],
               'calc_version': call.get('calc_version', 'macro_cycle_scoring_v1'),
               'horizon_sessions': call['horizon_sessions'], 'assessed_at_utc': as_of_utc,
               'entry_session': str(days[0]), 'exit_session': str(days[-1]),
               'status': 'PENDING', 'return_pct': None, 'hit': None,
               'brier_score_descriptive_only': None, 'probability_status': call['probability_status']}
        if session_bounds(days[-1])[1] <= now:
            grid = pd.DatetimeIndex(days)
            panel = bars.reindex(grid)
            if not {'open', 'close'}.issubset(panel.columns) or panel[['open', 'close']].isna().any().any() or (panel[['open', 'close']] <= 0).any().any():
                row['status'] = 'DATA_GAP'
            else:
                ret = float(panel.close.iloc[-1] / panel.open.iloc[0] - 1)
                direction = str(call.get('direction') or '').upper()
                sign = -1 if 'BEARISH' in direction else 1 if 'BULLISH' in direction else 0
                row.update(status='MATURED' if sign else 'NO_DIRECTIONAL_CALL', return_pct=ret * 100,
                           hit=bool(sign * ret > 0) if sign else None,
                           price_rows_sha256=digest(panel.reset_index().astype(str).to_dict('records')))
                p = call.get('source_bullish_score_fraction')
                if p is not None: row['brier_score_descriptive_only'] = (p - int(ret > 0)) ** 2
        row['record_id'] = digest(row)
        result.append(row)
    return result


def forward_summary(calls, outcomes):
    latest = {r['call_id']: r for r in outcomes}
    out = {}
    for h in sorted({c['horizon_sessions'] for c in calls}):
        eligible = [latest[c['call_id']] for c in calls if c['horizon_sessions'] == h and c['call_id'] in latest]
        mature = [r for r in eligible if r['status'] == 'MATURED']
        ids = {r['call_id'] for r in mature}
        matched = [c for c in calls if c['call_id'] in ids]
        bins = []
        for lo in (0, .2, .4, .6, .8):
            cohort = [c for c in matched if c.get('source_bullish_score_fraction') is not None
                      and lo <= c['source_bullish_score_fraction'] <= lo + .2
                      and (lo == 0 or c['source_bullish_score_fraction'] > lo)]
            if cohort:
                bins.append({'score_bin': [lo, lo + .2], 'n': len(cohort),
                    'mean_source_score': sum(c['source_bullish_score_fraction'] for c in cohort) / len(cohort),
                    'observed_up_fraction': sum(latest[c['call_id']]['return_pct'] > 0 for c in cohort) / len(cohort)})
        # Conservative count of non-overlapping scored windows, not row count.
        end = None; n_eff = 0
        for r in sorted(mature, key=lambda x: x['entry_session']):
            if end is None or r['entry_session'] > end:
                n_eff += 1; end = r['exit_session']
        out[str(h)] = {'calls': len(eligible), 'matured': len(mature),
            'hit_rate': sum(r['hit'] for r in mature) / len(mature) if mature else None,
            'nonoverlapping_windows': n_eff, 'reliability_bins_descriptive_only': bins,
            'descriptive_brier_mean': sum(r['brier_score_descriptive_only'] for r in mature if r['brier_score_descriptive_only'] is not None) / sum(r['brier_score_descriptive_only'] is not None for r in mature)
                if any(r['brier_score_descriptive_only'] is not None for r in mature) else None,
            'always_up_hit_rate_same_calls': sum(r['return_pct'] > 0 for r in mature) / len(mature) if mature else None,
            'status_counts': {s: sum(r['status'] == s for r in eligible) for s in sorted({r['status'] for r in eligible})},
            'validation_status': 'UNCALIBRATED_NOT_VALIDATED_FORECAST_PROBABILITIES'}
    return out


def score_calls(calls, observations, as_of_utc):
    now = instant(as_of_utc)
    by = {}
    for obs in observations:
        if not obs.get('source') or not obs.get('source_sha256') or len(obs['source_sha256']) != 64:
            raise ValueError('Outcome requires saved-source identity and hash')
        if not isinstance(obs.get('outcome'), bool): raise ValueError('Outcome must be an observed boolean, not a text inference')
        if instant(obs['observed_at_utc']) > now: continue
        key = obs['call_id']
        if key in by and by[key] != obs: raise ValueError('Conflicting outcome receipts need explicit new version')
        by[key] = obs
    result = []
    for call in calls:
        row = {'call_id': call['call_id'], 'assessed_at_utc': as_of_utc, 'status': 'PENDING',
               'calc_version': 'macro_authored_call_scoring_v1',
               'outcome': None, 'brier_score': None}
        if instant(call['due_at_utc']) <= now:
            obs = by.get(call['call_id'])
            if obs is None:
                row['status'] = 'UNASSESSED_OUTCOME'
            elif instant(obs['observed_at_utc']) < instant(call.get('known_at_utc', call.get('authored_at_utc', call['due_at_utc']))):
                row['status'] = 'INVALID_OUTCOME_CLOCK'
            else:
                row.update(status='MATURED', outcome=obs['outcome'], evidence=obs)
                if call.get('probability') is not None:
                    row['brier_score'] = (float(call['probability']) - int(obs['outcome'])) ** 2
        row['record_id'] = digest(row); result.append(row)
    return result
