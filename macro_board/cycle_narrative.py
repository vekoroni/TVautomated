"""MAC-08. Assemble measured evidence and explicitly authored judgements, never invent calls."""
from copy import deepcopy
from datetime import datetime

from .cycle_evidence import driver_readings, number
from .cycle_io import digest

SECTIONS = ('what_changed', 'transmission', 'house_view', 'wrong_worlds', 'central_bank_vs_price',
            'forced_flows', 'confirmation_divergence', 'etf_book', 'what_changes_our_mind')


def validate_author_input(author):
    if not author: return
    if author.get('authority') != 'ADVISORY_ONLY': raise ValueError('Authored input must be advisory')
    if not author.get('author') or not author.get('as_of_utc'): raise ValueError('Authored source identity/clock required')
    clock = datetime.fromisoformat(author['as_of_utc'].replace('Z', '+00:00'))
    if clock.tzinfo is None: raise ValueError('Authored input needs timezone')
    from .cycle_governance import validate_input
    validate_input(author)
    for key in ('house_view', 'central_bank_vs_price'):
        if key in author and not isinstance(author[key], dict): raise ValueError('Authored section must be object')
    calls = []
    for key in ('wrong_worlds', 'event_calls', 'playbook_choices', 'forced_flow_predictions'):
        if not isinstance(author.get(key, []), list): raise ValueError('Authored calls must be arrays')
        calls.extend(author.get(key, []))
    if len({c.get('call_id') for c in calls}) != len(calls) or any(not c.get('call_id') for c in calls):
        raise ValueError('Every authored call requires a unique stable call_id')
    for call in calls:
        for key in ('event', 'due_at_utc', 'resolution_rule'):
            if not call.get(key): raise ValueError(f'Call requires {key}')
        clock = datetime.fromisoformat(call['due_at_utc'].replace('Z', '+00:00'))
        if clock.tzinfo is None: raise ValueError('Call resolution clock needs timezone')
        p = call.get('probability')
        if p is not None and (isinstance(p, bool) or number(p) is None or not 0 <= float(p) <= 1):
            raise ValueError('Probability must be explicit unknown or finite 0..1')
    for world in author.get('wrong_worlds', []):
        trip = world.get('tripwire') or {}
        if not trip.get('series') or number(trip.get('level')) is None or trip.get('operator') not in ('GT', 'GE', 'LT', 'LE', 'EQ'):
            raise ValueError('Wrong world requires measurable series/level/operator tripwire')
    if author.get('worlds_partition') == 'MUTUALLY_EXCLUSIVE_EXHAUSTIVE' and author.get('input_contract_version') != 'macro_research_input_v2':
        probabilities = [author.get('house_view', {}).get('probability')] + [w.get('probability') for w in author.get('wrong_worlds', [])]
        if any(number(p) is None for p in probabilities) or abs(sum(probabilities) - 1) > 1e-8:
            raise ValueError('Explicit world partition must sum to one')


def assemble(payload, sources, changes, calendar, policy, manifest, author=None, previous=None):
    validate_author_input(author)
    author = deepcopy(author or {})
    readings = driver_readings(payload, sources, policy)
    from .cycle_governance import governance
    governed = governance(author, readings, policy)
    bank_section = deepcopy(author.get('central_bank_vs_price') or {})
    if bank_section:
        bank_section['authored_status'] = bank_section.get('status')
        bank_section['status'] = governed['central_bank_comparison']
    old = (previous or {}).get('driver_readings') or {}
    differences = [{'driver': key, 'previous_state': old.get(key, {}).get('state'),
                    'previous_source_values': old.get(key, {}).get('source_values'),
                    'state': row['state'], 'source_values': row['source_values'],
                    'status': 'FIRST_RECORDED_CYCLE' if not previous else 'CHANGED' if old.get(key, {}).get('state') != row['state'] or old.get(key, {}).get('source_values') != row['source_values'] else 'UNCHANGED'}
                   for key, row in readings.items()]
    missing = {'status': 'MISSING', 'reason': 'ACK/Claude authored input not supplied; no inferred judgement'}
    house = {'statement': None, 'probability': None, 'status': 'MISSING', **author.get('house_view', {})}
    if house['statement'] is not None and house['probability'] is not None:
        house['status'] = 'ACK_APPROVED_ADVISORY' if governed['approval_state'] == 'ACK_APPROVED_ADVISORY' else 'RESEARCH_DRAFT_NOT_APPROVED'
    expressions = governed['expressions']
    world_ids = ({w['world_id'] for w in governed['market_scenarios'].get('worlds', [])}
                 if author.get('input_contract_version') == 'macro_research_input_v2' else {'HOUSE'} | {w['call_id'] for w in author.get('wrong_worlds', [])})
    for expression in expressions:
        marks = expression.get('world_marks') or {}
        if set(marks) != world_ids: raise ValueError('ETF expression must mark every declared world, using UNASSESSED where unknown')
        expression['worlds_count'] = len(marks)
        expression['winning_worlds_count'] = sum(v == 'WIN' for v in marks.values())
    worlds = deepcopy(author.get('wrong_worlds', []))
    previous_worlds = {w['call_id']: w for w in ((previous or {}).get('authored_input') or {}).get('wrong_worlds', [])}
    for world in worlds:
        prior = previous_worlds.get(world.get('supersedes_call_id') or world['call_id'], {})
        before, now = number(prior.get('probability')), number(world.get('probability'))
        world['previous_probability'] = before
        world['probability_change'] = now - before if before is not None and now is not None else None
    sections = [
        {'key': 'what_changed', 'data': {'drivers': differences, 'short_windows': changes}},
        {'key': 'transmission', 'data': author.get('transmission') or missing},
        {'key': 'house_view', 'data': house},
        {'key': 'wrong_worlds', 'data': {'worlds': worlds, 'market_scenarios': governed['market_scenarios'],
            'event_forecasts': governed['event_forecasts'], 'status': 'AUTHORED' if worlds or governed['event_forecasts'] or governed['market_scenarios'].get('worlds') else 'MISSING'}},
        {'key': 'central_bank_vs_price', 'data': bank_section or missing},
        {'key': 'forced_flows', 'data': {'calendar': calendar, 'predictions': author.get('forced_flow_predictions', [])}},
        {'key': 'confirmation_divergence', 'data': {'readings': readings,
            'authored_interpretation': author.get('confirmation_divergence') or missing}},
        {'key': 'etf_book', 'data': {'expressions': expressions, 'status': 'AUTHORED' if expressions else 'MISSING'}},
        {'key': 'what_changes_our_mind', 'data': author.get('what_changes_our_mind') or missing}]
    n = {'contract_version': 'macro_narrative_v1', 'calc_version': policy['calc_version'],
         'authority': 'ADVISORY_ONLY', 'as_of_session': payload['as_of_session'],
         'information_cutoff_utc': payload['built_at_utc'], 'cycle_kind': (payload.get('build') or {}).get('kind', 'REPLAY'),
         'policy_sha256': digest(policy), 'input_manifest': manifest, 'driver_readings': readings,
         'sections': sections, 'authored_input': author or None,
         'governance': governed, 'etf_universe': policy.get('etf_registry'),
         'clocks': {'market_publication_utc': payload['built_at_utc'],
                    'evidence_cutoff_utc': author.get('evidence_cutoff_utc', payload['built_at_utc']),
                    'authored_at_utc': author.get('authored_at_utc', author.get('as_of_utc')),
                    'approved_at_utc': (author.get('approval') or {}).get('approved_at_utc'),
                    'assembly_utc': payload.get('cycle_assembly_utc', payload['built_at_utc'])},
         'series_eligibility': {s: {'status': 'EXCLUDED_HISTORICAL_ONLY',
             'disposition': 'Original observations preserved in raw evidence; never used as current driver evidence',
             'replacement_context': 'OECD_CLI_US_NORMALIZED is separately identified, not a renamed USSLIND'}
             for s in policy['historical_only']},
         'previous_narrative_id': (previous or {}).get('narrative_id'),
         'supersedes': author.get('supersedes'), 'correction_reason': author.get('correction_reason'),
         'status': 'INCOMPLETE_AUTHORED_INPUT',
         'limitations': ['Advisory only; no ticker score/rank/gate/contract authority',
                        'A scheduled calendar date does not predict flow direction or size',
                        'Current saved histories can contain later revisions; not a vintage-certified historical backtest']}
    required = ('transmission', 'house_view', 'wrong_worlds', 'central_bank_vs_price', 'etf_book', 'what_changes_our_mind')
    if all(author.get(k) for k in required) and house.get('probability') is not None and house.get('statement') and 2 <= len(author.get('wrong_worlds', [])) <= 3:
        n['status'] = 'COMPLETE_WITH_EVIDENCE_LIMITATIONS' if any(r['status'] in ('MISSING', 'STALE') for r in readings.values()) else 'COMPLETE'
    if author and governed['approval_state'] != 'ACK_APPROVED_ADVISORY': n['status'] = 'RESEARCH_DRAFT'
    elif author.get('input_contract_version') == 'macro_research_input_v2':
        complete = all(author.get(k) for k in ('transmission', 'house_view', 'central_bank_vs_price', 'etf_book', 'what_changes_our_mind'))
        complete = complete and house.get('probability') is not None and bool(author.get('event_forecasts')) and governed['market_scenarios'].get('partition') == 'ORDERED_EXHAUSTIVE'
        n['status'] = 'COMPLETE_WITH_EVIDENCE_LIMITATIONS' if complete else 'INCOMPLETE_AUTHORED_INPUT'
    n['narrative_id'] = 'macro_' + payload['as_of_session'] + '_' + digest(n)[:24]
    validate(n)
    return n


def validate(n):
    required = ('contract_version', 'calc_version', 'narrative_id', 'authority', 'as_of_session',
                'information_cutoff_utc', 'policy_sha256', 'input_manifest', 'driver_readings',
                'sections', 'status', 'limitations')
    if any(k not in n for k in required): raise ValueError('Missing narrative schema field')
    if n.get('contract_version') != 'macro_narrative_v1' or n.get('authority') != 'ADVISORY_ONLY':
        raise ValueError('Invalid narrative authority/contract')
    if [s.get('key') for s in n.get('sections', [])] != list(SECTIONS): raise ValueError('Nine sections required in order')
    if not n.get('calc_version') or not n.get('input_manifest') or not n.get('narrative_id'):
        raise ValueError('Version/lineage/identity required')
    from .cycle_evidence import DRIVERS
    if not set(DRIVERS).issubset(n['driver_readings']): raise ValueError('All driver readings required, including explicit missing')
    if n['status'] not in ('COMPLETE', 'COMPLETE_WITH_EVIDENCE_LIMITATIONS', 'INCOMPLETE_AUTHORED_INPUT', 'RESEARCH_DRAFT'):
        raise ValueError('Invalid narrative status')
    ts = datetime.fromisoformat(n['information_cutoff_utc'].replace('Z', '+00:00'))
    if ts.tzinfo is None: raise ValueError('Information cutoff must carry timezone')
    if n.get('supersedes') and not n.get('correction_reason'): raise ValueError('Corrections require reason')
    if n.get('clocks'):
        from .cycle_governance import clock
        c = n['clocks']; assembly = clock(c['assembly_utc'])
        if clock(c['market_publication_utc']) != ts or clock(c['evidence_cutoff_utc']) > ts or ts > assembly:
            raise ValueError('Research and market clocks disagree')
        if c.get('authored_at_utc') and clock(c['authored_at_utc']) > assembly: raise ValueError('Authorship cannot follow assembly')
        if c.get('approved_at_utc') and not clock(c['authored_at_utc']) <= clock(c['approved_at_utc']) <= assembly:
            raise ValueError('Approval clock outside authorship/assembly')
    def forbidden(value):
        if isinstance(value, dict):
            if any(k in value for k in ('ticker_score', 'ticker_rank', 'ticker_veto', 'execution_permission', 'order_request')):
                raise ValueError('Ticker/execution authority field forbidden in macro narrative')
            for v in value.values(): forbidden(v)
        elif isinstance(value, list):
            for v in value: forbidden(v)
    # Raw captured input manifests may reference legacy contracts, but the new
    # assembled decisions cannot acquire their authority fields.
    forbidden(n.get('authored_input'))
    p = n['sections'][2]['data'].get('probability')
    if p is not None and (isinstance(p, bool) or number(p) is None or not 0 <= float(p) <= 1): raise ValueError('Invalid house probability')
    allowed = set(n.get('etf_universe') or ['SPY', 'QQQ', 'IWM', 'DIA', 'RSP', 'TLT', 'IEF', 'HYG', 'LQD', 'GLD', 'USO', 'UUP',
                   'XLP', 'XLV', 'XLU', 'XLRE', 'XLK', 'XLF', 'XLE', 'XLI', 'XLY', 'XLB', 'XLC', 'SMH'])
    for e in n['sections'][7]['data'].get('expressions', []):
        if e.get('etf') not in allowed: raise ValueError('ETF book accepts governed ETFs only')
        if not e.get('killer_event') or 'covering_position' not in e: raise ValueError('ETF killer event/covering position required, explicit null allowed')
        marks = e.get('world_marks') or {}
        if any(v not in ('WIN', 'FLAT', 'LOSE', 'UNASSESSED') for v in marks.values()): raise ValueError('Invalid world mark')
    validate_author_input(n.get('authored_input'))
    if n['status'].startswith('COMPLETE'):
        if n.get('governance') and n['governance']['approval_state'] != 'ACK_APPROVED_ADVISORY':
            raise ValueError('Draft cannot be complete/approved')
        a = n.get('authored_input') or {}
        if a.get('input_contract_version') == 'macro_research_input_v2':
            if not all(a.get(k) for k in ('transmission', 'house_view', 'event_forecasts', 'central_bank_vs_price', 'etf_book', 'what_changes_our_mind')) or not a['house_view'].get('statement') or a['house_view'].get('probability') is None or a.get('market_scenarios', {}).get('partition') != 'ORDERED_EXHAUSTIVE':
                raise ValueError('Incomplete v2 authored narrative')
            return
        if not all(a.get(k) for k in ('transmission', 'house_view', 'wrong_worlds', 'central_bank_vs_price', 'etf_book', 'what_changes_our_mind')):
            raise ValueError('Cannot mark missing authored sections complete')
        if not a['house_view'].get('statement') or a['house_view'].get('probability') is None or not 2 <= len(a['wrong_worlds']) <= 3:
            raise ValueError('Complete narrative requires house probability and two/three wrong worlds')


def tripwires(author, measurements, previous=None):
    """Evaluate only explicitly identified saved series. Alerts are not trade vetoes."""
    old = {r['call_id']: r for r in (previous or [])}
    out = []
    ops = {'GT': lambda a, b: a > b, 'GE': lambda a, b: a >= b,
           'LT': lambda a, b: a < b, 'LE': lambda a, b: a <= b, 'EQ': lambda a, b: a == b}
    for call in (author or {}).get('wrong_worlds', []):
        t = call['tripwire']; m = measurements.get(t['series']) or {}
        value = number(m.get('value'))
        assessed = value is not None and m.get('status') == 'OK'
        fired = ops[t['operator']](value, float(t['level'])) if assessed else None
        out.append({'call_id': call['call_id'], 'tripwire': t, 'measurement': m,
                    'fired': fired, 'newly_fired': fired is True and old.get(call['call_id'], {}).get('fired') is not True,
                    'status': 'TRIGGERED' if fired else 'NOT_TRIGGERED' if assessed else 'UNASSESSED_SOURCE',
                    'authority': 'ADVISORY_ONLY'})
    return out


def render(n):
    import json
    lines = [f"# Macro operating cycle — {n['as_of_session']}", '',
             f"{n['narrative_id']} · ADVISORY_ONLY · {n['status']}",
             f"Information cutoff: {n['information_cutoff_utc']} · calculation: {n['calc_version']}", '']
    if n.get('governance'):
        g = n['governance']
        lines += [f"Approval: {g['approval_state']} · evidence: {g['evidence_completeness']} · valuation: {g['valuation_readiness']}",
                  'Separate clocks: ' + json.dumps(n.get('clocks'), sort_keys=True), '']
    for i, section in enumerate(n['sections'], 1):
        lines.extend([f"## {i}. {section['key'].replace('_', ' ').title()}", ''])
        data = section['data']
        if section['key'] == 'house_view':
            lines += [data.get('statement') or 'MISSING — authored house view not supplied.',
                      'Probability: ' + ('MISSING' if data.get('probability') is None else f"{data['probability']:.1%} (AUTHORED, not measured)"), '']
        elif section['key'] == 'what_changed':
            lines += ['| Driver | Previous | Current | Status |', '|---|---|---|---|']
            for r in data['drivers']:
                evidence = n['driver_readings'][r['driver']]['status']
                lines.append(f"| {r['driver']} | {r['previous_state'] or 'No prior cycle'} | {r['state']} ({evidence}) | {r['status']} |")
            lines += ['', 'Full source values, clocks and short-window readings:', '', '```json',
                      json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), '```', '']
        elif isinstance(data, dict) and data.get('status') == 'MISSING':
            lines += ['MISSING — ' + str(data.get('reason') or 'Awaiting authored input.'), '']
        else:
            lines += ['```json', json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), '```', '']
    lines += ['## Limitations', ''] + ['- ' + s for s in n['limitations']]
    return '\n'.join(lines) + '\n'
