"""Advisory research contracts. No selection, market fetching or trading authority."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import re
import hashlib
import json
from pathlib import Path

from .cycle_io import digest
from .cycle_evidence import number

OPS = {'GT': lambda a, b: a > b, 'GE': lambda a, b: a >= b,
       'LT': lambda a, b: a < b, 'LE': lambda a, b: a <= b, 'EQ': lambda a, b: a == b}


def clock(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None: raise ValueError('Explicit timezone required')
    return t


def probability(value):
    if value is not None and (isinstance(value, bool) or number(value) is None or not 0 <= value <= 1):
        raise ValueError('Probability must be null or finite 0..1')


def validate_rule(rule):
    for key in ('series', 'unit', 'source', 'window_start_utc', 'window_end_utc', 'sampling', 'vintage'):
        if not rule.get(key): raise ValueError('Resolution rule requires ' + key)
    if clock(rule['window_start_utc']) > clock(rule['window_end_utc']): raise ValueError('Invalid outcome window')
    if rule['sampling'] not in ('AT_DEADLINE', 'ANY_CROSSING'): raise ValueError('Unknown sampling policy')
    if rule['vintage'] not in ('FIRST_PUBLISHED', 'AS_READ'): raise ValueError('Unknown vintage policy')
    if rule.get('operator') not in OPS or number(rule.get('level')) is None: raise ValueError('Invalid threshold')
    if rule.get('change_from_baseline'):
        b = rule.get('baseline') or {}
        if number(b.get('value')) is None or not re.fullmatch('[0-9a-f]{64}', b.get('source_sha256', '')) or not b.get('observed_at_utc'):
            raise ValueError('Change rule needs pinned baseline')
        if clock(b['observed_at_utc']) > clock(rule['window_start_utc']): raise ValueError('Future baseline')
    if rule.get('asset_class') == 'OIL' and not all(rule.get(k) for k in ('benchmark', 'contract', 'roll_rule', 'settlement')):
        raise ValueError('Oil requires exact benchmark/contract/settlement/roll rule')


def validate_input(a):
    """Version 2 is explicit; legacy inputs remain readable but never implicitly approved."""
    if a.get('input_contract_version') != 'macro_research_input_v2': return
    for key in ('authority', 'author', 'as_of_utc', 'authored_at_utc', 'evidence_cutoff_utc', 'approval', 'event_forecasts', 'market_scenarios', 'etf_book'):
        if key not in a: raise ValueError('Research contract requires ' + key)
    if a['authority'] != 'ADVISORY_ONLY' or not a['author']: raise ValueError('Research must remain identified and advisory')
    clock(a['as_of_utc'])
    for key in ('authored_at_utc', 'evidence_cutoff_utc'):
        clock(a[key])
    if clock(a['evidence_cutoff_utc']) > clock(a['authored_at_utc']): raise ValueError('Evidence cannot postdate authorship')
    approval = a.get('approval') or {}
    if approval.get('state') not in ('RESEARCH_DRAFT', 'ACK_APPROVED_ADVISORY'): raise ValueError('Explicit approval state required')
    if approval['state'] == 'ACK_APPROVED_ADVISORY':
        content = deepcopy(a); content.pop('approval', None)
        if approval.get('approved_by') != 'ACK' or approval.get('content_sha256') != digest(content):
            raise ValueError('ACK approval must bind exact input contents')
        if clock(approval['approved_at_utc']) < clock(a['authored_at_utc']): raise ValueError('Approval predates authorship')
    events = a.get('event_forecasts', [])
    ids = [c['call_id'] for c in events]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate event ID')
    for c in events:
        probability(c.get('probability')); validate_rule(c['resolution'])
        if clock(c['resolution']['window_start_utc']) < clock(a['authored_at_utc']):
            raise ValueError('Prospective outcome window predates authorship')
    by = {c['call_id']: c for c in events}
    for r in a.get('probability_constraints', []):
        left, right = by[r['left']], by[r['right']]
        # Constraints are declared relationships, not NLP assertions about prose.
        if left['resolution']['window_end_utc'] != right['resolution']['window_end_utc']:
            raise ValueError('Probability constraints require a common horizon')
        p, q = left.get('probability'), right.get('probability')
        if p is None or q is None: continue
        kind = r['relationship']
        if kind == 'IMPLIES' and p > q + 1e-8: raise ValueError('Implied event cannot have smaller probability')
        if kind == 'COMPLEMENT' and abs(p + q - 1) > 1e-8: raise ValueError('Complement probabilities must sum to one')
        if kind not in ('IMPLIES', 'COMPLEMENT'): raise ValueError('Unknown probability relationship')
    s = a.get('market_scenarios') or {}
    if s.get('partition', 'NOT_ASSERTED') not in ('NOT_ASSERTED', 'ORDERED_EXHAUSTIVE'): raise ValueError('Unknown scenario partition')
    if s.get('partition') == 'ORDERED_EXHAUSTIVE':
        clock(s['horizon_utc']); worlds = s['worlds']
        if not worlds or worlds[-1].get('residual') is not True: raise ValueError('Final residual world required')
        if len({w['world_id'] for w in worlds}) != len(worlds): raise ValueError('Duplicate market world')
        for w in worlds:
            probability(w.get('probability'))
            if not w.get('residual') and not w.get('conditions'): raise ValueError('Observable scenario conditions required')
            for c in w.get('conditions', []):
                if c.get('operator') not in OPS or number(c.get('level')) is None or not c.get('metric'):
                    raise ValueError('Invalid market boundary')
        if any(w.get('residual') for w in worlds[:-1]): raise ValueError('Residual must be last only')
        definitions = s.get('metric_definitions') or {}
        for metric in {c['metric'] for w in worlds for c in w.get('conditions', [])}:
            d = definitions.get(metric) or {}
            if d.get('kind') not in ('ABSOLUTE_RETURN', 'RELATIVE_RETURN') or not d.get('etf') or not d.get('baseline_session'):
                raise ValueError('Market metric requires ETF, kind and baseline session')
            if d['kind'] == 'RELATIVE_RETURN' and not d.get('benchmark'): raise ValueError('Relative metric needs benchmark')
        ps = [w.get('probability') for w in worlds]
        if any(p is None for p in ps) or abs(sum(ps) - 1) > 1e-8: raise ValueError('Exhaustive probabilities must sum to one')
    for e in a.get('etf_book', []):
        for k in ('expression_id', 'etf', 'forecast_basis', 'deadline_utc', 'invalidation', 'killer_event', 'covering_position'):
            if k not in e: raise ValueError('ETF expression requires ' + k)
        if e['forecast_basis'] not in ('ABSOLUTE', 'RELATIVE'): raise ValueError('Explicit forecast basis required')
        if e['forecast_basis'] == 'RELATIVE' and not e.get('benchmark'): raise ValueError('Relative forecast needs benchmark')
        clock(e['deadline_utc'])
    expression_ids = [e['expression_id'] for e in a.get('etf_book', [])]
    if len(set(expression_ids)) != len(expression_ids): raise ValueError('Duplicate ETF expression ID')
    if any(e.get('covering_position') is not None and e['covering_position'] not in expression_ids for e in a.get('etf_book', [])):
        raise ValueError('Cover must reference an exact expression; null means no cover')


def resolve(rule, rows, now):
    """Only matching, source-hashed observations resolve a call. Alerts never do."""
    validate_rule(rule)
    end = clock(rule['window_end_utc'])
    if clock(now) < end: return {'status': 'PENDING', 'outcome': None}
    eligible = []
    for r in rows:
        if any(r.get(k) != rule[k] for k in ('series', 'unit', 'source')): continue
        if r.get('status') != 'OK' or not re.fullmatch('[0-9a-f]{64}', r.get('source_sha256', '')): continue
        if rule['vintage'] == 'FIRST_PUBLISHED' and r.get('vintage') != 'FIRST_PUBLISHED': continue
        if rule.get('asset_class') == 'OIL' and any(r.get(k) != rule[k] for k in ('benchmark', 'contract', 'roll_rule', 'settlement')): continue
        t = clock(r['observed_at_utc'])
        if not clock(rule['window_start_utc']) <= t <= end or clock(r['published_at_utc']) > clock(now): continue
        if rule['sampling'] == 'AT_DEADLINE' and t != end: continue
        if number(r.get('value')) is not None: eligible.append(r)
    if not eligible: return {'status': 'UNASSESSED_OUTCOME', 'outcome': None}
    values = {}
    for r in eligible:
        if r['observed_at_utc'] in values and values[r['observed_at_utc']] != r['value']:
            return {'status': 'UNASSESSED_CONFLICTING_OBSERVATIONS', 'outcome': None}
        values[r['observed_at_utc']] = r['value']
    baseline = Decimal(str(rule['baseline']['value'])) if rule.get('change_from_baseline') else Decimal(0)
    hits = [OPS[rule['operator']](Decimal(str(r['value'])) - baseline, Decimal(str(rule['level']))) for r in eligible]
    # A missing interval must never manufacture a false negative.
    if rule['sampling'] == 'ANY_CROSSING' and not any(hits):
        expected = rule.get('expected_observations_utc')
        if not expected or set(expected) != set(values): return {'status': 'UNASSESSED_INCOMPLETE_PATH', 'outcome': None}
    return {'status': 'MATURED', 'outcome': any(hits), 'evidence': eligible}


def classify(scenarios, metrics, now):
    if scenarios.get('partition') != 'ORDERED_EXHAUSTIVE': return {'status': 'NOT_ASSERTED', 'world_id': None}
    if clock(now) < clock(scenarios['horizon_utc']): return {'status': 'PENDING', 'world_id': None}
    needed = {c['metric'] for w in scenarios['worlds'] for c in w.get('conditions', [])}
    if any(number(metrics.get(k)) is None for k in needed): return {'status': 'UNASSESSED_MISSING_BENCHMARK', 'world_id': None}
    for w in scenarios['worlds']:
        if w.get('residual') or all(OPS[c['operator']](metrics[c['metric']], c['level']) for c in w['conditions']):
            return {'status': 'CLASSIFIED', 'world_id': w['world_id'], 'precedence': 'FIRST_MATCH_THEN_RESIDUAL'}


def classify_saved(scenarios, closes, now, source_hash):
    """Exact saved closing observations, no fill-forward and no proxy substitution."""
    if scenarios.get('partition') != 'ORDERED_EXHAUSTIVE': return {'status': 'NOT_ASSERTED', 'world_id': None}
    if clock(now) < clock(scenarios['horizon_utc']): return {'status': 'PENDING', 'world_id': None}
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    end = clock(scenarios['horizon_utc']); day = end.date()
    if not is_xnys_session(day) or session_bounds(day)[1] != end:
        return {'status': 'UNASSESSED_NOT_EXACT_SESSION_CLOSE', 'world_id': None}
    metrics, evidence = {}, {}
    for name, d in scenarios.get('metric_definitions', {}).items():
        try:
            base, final = closes.loc[d['baseline_session']], closes.loc[day.isoformat()]
            names = [d['etf']] + ([d['benchmark']] if d['kind'] == 'RELATIVE_RETURN' else [])
            if any(number(base[t]) is None or base[t] <= 0 or number(final[t]) is None or final[t] <= 0 for t in names): continue
            returns = {t: float(final[t] / base[t] - 1) for t in names}
            metrics[name] = returns[d['etf']] - (returns[d['benchmark']] if d['kind'] == 'RELATIVE_RETURN' else 0)
            evidence[name] = {'baseline_session': d['baseline_session'], 'final_session': str(day), 'returns': returns, 'source_sha256': source_hash}
        except (KeyError, TypeError, ValueError): continue
    return {**classify(scenarios, metrics, now), 'metrics': metrics, 'evidence': evidence,
            'limitations': ['Saved closing price returns, not total returns or realised option outcomes']}


def option_payoff(e):
    """Conditional model disclosure only. Never a realised result or an entry recommendation."""
    q, s = e.get('saved_option_quote') or {}, e.get('option_scenario') or {}
    missing = {'status': 'OPTION_PAYOFF_UNASSESSED', 'reason': 'Exact saved contract, quote, source hash, clock and scenario inputs required'}
    required = ('occ_symbol', 'underlying', 'right', 'strike', 'expiry', 'bid', 'ask', 'quote_at_utc', 'source_sha256')
    if any(q.get(k) is None for k in required) or any(s.get(k) is None for k in ('at_utc', 'spot', 'iv', 'rate', 'rate_basis', 'dividend_yield', 'dividend_basis', 'iv_basis', 'exit_spread_multiple')): return missing
    if q['underlying'] != e['etf'] or not re.fullmatch('[0-9a-f]{64}', q['source_sha256']): return missing
    source = q.get('source_path')
    if not source or str(source).startswith(('http:', 'https:', '\\\\')):
        return {**missing, 'reason': 'Local archived quote source required; no fetch permitted'}
    try:
        raw = Path(source).read_bytes()
        if hashlib.sha256(raw).hexdigest() != q['source_sha256']: return {**missing, 'reason': 'Archived quote hash mismatch'}
        saved = json.loads(raw.decode('utf-8-sig'))
        rows = saved if isinstance(saved, list) else saved.get('quotes', [saved])
        identity = ('occ_symbol', 'underlying', 'right', 'strike', 'expiry', 'bid', 'ask', 'quote_at_utc', 'expiry_close_utc')
        if not any(all(r.get(k) == q.get(k) for k in identity) for r in rows):
            return {**missing, 'reason': 'Quote values disagree with archived source'}
    except (OSError, ValueError, TypeError, AttributeError): return {**missing, 'reason': 'Archived quote unreadable or unsupported; JSON rows required'}
    symbol = re.fullmatch(r'([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})', q['occ_symbol'])
    if not symbol or symbol[1] != q['underlying'] or symbol[3] != q['right'] or int(symbol[4]) / 1000 != q['strike'] or datetime.strptime(symbol[2], '%y%m%d').date().isoformat() != q['expiry']:
        return {**missing, 'reason': 'Exact OCC identity disagrees with contract fields'}
    vals = [number(q[k]) for k in ('strike', 'bid', 'ask')] + [number(s[k]) for k in ('spot', 'iv', 'rate', 'dividend_yield', 'exit_spread_multiple')]
    if any(v is None for v in vals) or not 0 <= q['bid'] <= q['ask'] or q['ask'] <= 0 or s['spot'] <= 0 or s['iv'] <= 0 or s['dividend_yield'] < 0 or s['exit_spread_multiple'] < 0: return missing
    at, quoted = clock(s['at_utc']), clock(q['quote_at_utc'])
    if e.get('deadline_utc') and at > clock(e['deadline_utc']):
        return {**missing, 'reason': 'Option valuation occurs after ETF forecast deadline'}
    # Caller supplies exact expiry close (including half-days); no inferred expiry session.
    if not q.get('expiry_close_utc'): return {**missing, 'reason': 'Exact expiry-session close required'}
    expiry = clock(q['expiry_close_utc'])
    if expiry.date().isoformat() != q['expiry'] or not quoted <= at <= expiry: return missing
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    if not is_xnys_session(expiry.date()) or session_bounds(expiry.date())[1] != expiry:
        return {**missing, 'reason': 'Expiry close disagrees with XNYS calendar'}
    from domain.option_valuation import option_value, cost_basis
    from .cycle_option_compat import net_return_on_premium_raw
    model = option_value('CALL' if q['right'] == 'C' else 'PUT', s['spot'], q['strike'], (expiry - at).total_seconds() / (365 * 86400), s['iv'], rate=s['rate'], dividend_yield=s['dividend_yield'], style='AMERICAN')
    net = net_return_on_premium_raw(model['value'], bid=q['bid'], ask=q['ask'], exit_spread_multiple=s['exit_spread_multiple'])
    if net is None: return {**missing, 'reason': 'Invalid shared model value or governed cost basis'}
    return {'status': 'CONDITIONAL_MODEL_NOT_REALISED', 'net_return_on_premium': net,
            'conditional_mark': 'WIN' if net > 0 else 'LOSE' if net < 0 else 'FLAT', **model,
            'cost_basis': cost_basis(q['bid']) + '|exit_spread_multiple=' + str(s['exit_spread_multiple']),
            'valuation_adapter': 'macro_option_cost_compat_v1', 'inputs': {'quote': q, 'scenario': s},
            'limitations': ['American CRR conditional estimate, not an executable exit bid', 'Saved quote is not a live entry quote', 'ETF relative correctness is not option profit']}


def governance(a, readings, policy):
    a = a or {}; validate_input(a)
    approval = (a.get('approval', {}).get('state') if a.get('input_contract_version') == 'macro_research_input_v2' else None) or ('RESEARCH_DRAFT' if a else 'MISSING')
    registry = set(policy.get('etf_registry', []))
    expressions = []
    for original in a.get('etf_book', []):
        e = deepcopy(original)
        if e.get('etf') not in registry: raise ValueError('ETF outside governed registry')
        e['option_payoff'] = option_payoff(e)
        world_ids = [w['world_id'] for w in (a.get('market_scenarios') or {}).get('worlds', [])]
        supplied = e.get('option_scenarios_by_world') or {}
        if set(supplied) - set(world_ids): raise ValueError('Option scenario references an undeclared market world')
        e['option_payoff_by_world'] = {wid: option_payoff({**e, 'option_scenario': supplied.get(wid)}) for wid in world_ids}
        stresses = e.get('option_stress_scenarios') or {}
        if len(stresses) > policy.get('max_option_stress_scenarios', 16): raise ValueError('Too many option stress scenarios')
        e['option_stress_comparisons'] = {name: option_payoff({**e, 'option_scenario': scenario}) for name, scenario in stresses.items()}
        e['stress_status'] = 'AUTHORED_CONDITIONAL_STRESSES' if stresses else 'UNASSESSED_STRESSES_NOT_SUPPLIED'
        e['world_marks_basis'] = 'AUTHORED_ETF_THESIS_ONLY_NOT_OPTION_PNL'
        e['realised_option_outcome'] = 'UNASSESSED_NO_OBSERVED_EXIT'
        expressions.append(e)
    bank = a.get('central_bank_vs_price') or {}
    return {'approval_state': approval, 'publication_integrity': 'HASH_BOUND_ON_PUBLICATION',
            'central_bank_comparison': 'AUTHORED_CALL_PRESENT_PRICED_PATH_MISSING' if bank.get('our_call') and bank.get('priced_call') is None else 'AUTHORED_NOT_MEASURED' if bank.get('our_call') else 'MISSING_AUTHORED_CALL',
            'evidence_completeness': 'LIMITED' if any(r.get('status') != 'OK' for r in readings.values()) else 'PRESENT_NOT_INDEPENDENTLY_VERIFIED',
            'valuation_readiness': 'CONDITIONAL_ONLY' if expressions and all(e['option_payoff_by_world'] and all(v['status'] == 'CONDITIONAL_MODEL_NOT_REALISED' for v in e['option_payoff_by_world'].values()) for e in expressions) else 'OPTION_PAYOFF_UNASSESSED',
            'semantic_validation': 'DECLARED_RELATIONSHIPS_ONLY_NOT_PROSE_CERTIFICATION',
            'market_scenarios': a.get('market_scenarios') or {'partition': 'NOT_ASSERTED'},
            'event_forecasts': a.get('event_forecasts', []), 'expressions': expressions}
