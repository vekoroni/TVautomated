"""Small, independently versioned, display-only Macroboard publication for the Lab.

No trade-book reads, providers, direction changes or Worker 3 dependencies.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

SCHEMA = 'lab_macro_desk_v1'


def project(payload):
    session = payload.get('as_of_session')
    datetime.strptime(session, '%Y-%m-%d')
    built = datetime.fromisoformat(payload['built_at_utc'].replace('Z', '+00:00'))
    if built.tzinfo is None:
        raise ValueError('Macro build timestamp must include timezone')
    conditions = payload.get('conditions', {}).get('current', {})
    if not isinstance(conditions, dict) or not conditions:
        raise ValueError('Measured macro conditions required')
    observations = payload.get('conditions', {}).get('observations', {})
    values = payload.get('conditions', {}).get('current_values', {})
    evidence = [{'id': key, 'state': value, 'value': values.get(key),
                 'observation': observations.get(key) if isinstance(observations, dict) else None}
                for key, value in conditions.items()]
    source_issues = []
    for name, receipt in payload.get('external', {}).items():
        if not isinstance(receipt, dict):
            continue
        if receipt.get('status') in {'MISSING', 'UNREADABLE', 'STALE'}:
            source_issues.append(f"{name}: {receipt['status']} at board build")
        try:
            observed = datetime.fromisoformat(str(receipt.get('as_of', '')).replace('Z', '+00:00'))
            if observed.tzinfo and observed > built:
                source_issues.append(f'{name}: timestamp is later than board build; do not assume cutoff validity')
        except ValueError:
            pass
    scenarios = []
    rules = [
        ('credit', 'WIDENING', 'Defensive positioning pressure',
         'Wider credit spreads can indicate greater demand for protection, even while equities remain firm.',
         'Credit continues widening and equity breadth deteriorates.',
         'Credit stabilises or tightens and breadth broadens.',
         'Challenges unconfirmed bullish continuation; does not establish a bearish trade.'),
        ('yields', 'RISING', 'Discount-rate pressure',
         'Rising yields can make investors less willing to pay for distant earnings.',
         'Yields keep rising while rate-sensitive equities weaken.',
         'Yields ease and rate-sensitive equities regain participation.',
         'Stress-test duration-sensitive bullish theses; do not reverse their saved direction.'),
        ('market_breadth', 'LOW', 'Narrow participation / fragile confidence',
         'Low breadth can mean index resilience is not shared widely across stocks.',
         'Indexes hold up but participation remains weak.',
         'Participation improves alongside index strength.',
         'Require ticker-level confirmation rather than assuming index strength supports every stock.'),
        ('market_vol', 'LOW', 'Quiet-market vulnerability',
         'Low realised volatility describes recent calm, not proof that investors are complacent.',
         'Volatility rises and price support fails.',
         'Calm persists with improving participation and stable credit.',
         'Consider gap and volatility-expansion risk in existing setups.'),
    ]
    for key, state, title, interpretation, confirm, invalidate, implication in rules:
        if conditions.get(key) == state:
            scenarios.append({'title': title, 'evidence_ids': [key],
                              'interpretation': interpretation, 'confirmation': confirm,
                              'invalidation': invalidate, 'thesis_implication': implication,
                              'classification': 'CONDITIONAL_INFERENCE_NOT_FORECAST'})
    out = {'schema_version': SCHEMA, 'authority': 'ADVISORY_ONLY',
           'can_grant_capital': False, 'can_reverse_direction': False,
           'board_version': payload.get('board_version'), 'as_of_session': session,
           'built_at_utc': payload['built_at_utc'], 'build_kind': payload.get('build', {}).get('kind'),
           'evidence': evidence, 'source_observations': observations,
           'scenarios': scenarios, 'source_issues': source_issues,
           'limitations': ['Psychology is an inference, not measured investor intent.',
                           'No scenario probabilities or execution permissions are inferred.',
                           'Source observation dates may differ from the board build time.',
                           'Source quality receipts describe the board build, not current freshness.',
                           'Trade review retains its own frozen run and evidence revision.'],
           'source_quality': payload.get('external', {})}
    out['revision'] = hashlib.sha256(json.dumps(out, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return out


def publish(payload, output_dir):
    document = project(payload)
    target = Path(output_dir) / 'lab_macro_latest.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return document


def publish_saved_board(path, output_dir):
    """Manual/offline import of our self-contained board; never execute its JS."""
    raw = Path(path).read_bytes()
    if len(raw) > 30_000_000:
        raise ValueError('Board exceeds 30 MB import limit')
    html = raw.decode('utf-8-sig')
    marker = 'const BOARD='
    if html.count(marker) != 1:
        raise ValueError('Expected exactly one embedded board payload')
    text = html.split(marker, 1)[1]
    payload, end = json.JSONDecoder().raw_decode(text)
    if not text[end:].lstrip().startswith(';') or not isinstance(payload, dict):
        raise ValueError('Invalid embedded board payload')
    if not str(payload.get('board_version', '')).startswith('macro-board-'):
        raise ValueError('Unsupported board identity')
    return publish(payload, output_dir)


def register_routes(app, output_dir):
    from flask import jsonify, send_from_directory

    @app.get('/macro-scenarios')
    def macro_scenarios_page():
        return send_from_directory(app.static_folder, 'macro-desk.html')

    @app.get('/api/lab/macro-context')
    def macro_context():
        try:
            # Short read handle. Never open the full book or scan board snapshots.
            document = json.loads((Path(output_dir) / 'lab_macro_latest.json').read_text(encoding='utf-8'))
            if document.get('schema_version') != SCHEMA or document.get('authority') != 'ADVISORY_ONLY':
                raise ValueError('Unsupported macro publication')
            built = datetime.fromisoformat(document['built_at_utc'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - built).total_seconds()
            document['publication_age_hours'] = round(age / 3600, 1)
            document['freshness'] = 'STALE' if age > 36 * 3600 else 'RECENT_BUILD_NOT_SOURCE_FRESHNESS_PROOF'
            response = jsonify(document)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            response = jsonify({'state': 'UNAVAILABLE', 'reason': str(exc)})
            response.status_code = 503
        response.headers['Cache-Control'] = 'no-store'
        return response


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Publish Lab macro context from saved board, offline')
    parser.add_argument('--from-board', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    result = publish_saved_board(args.from_board, args.output_dir)
    print(json.dumps({key: result[key] for key in ('revision', 'as_of_session', 'built_at_utc')}))
