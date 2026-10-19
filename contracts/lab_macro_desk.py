"""Versioned Market Mentality publication; local, display-only, no providers."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from contracts.lab_market_mentality import VERSION, assessment, compare_previous, evidence_from_board, trade_context

SCHEMA = 'lab_market_mentality_v2'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def project(payload, previous=None):
    session = payload.get('as_of_session')
    datetime.strptime(session, '%Y-%m-%d')
    built = datetime.fromisoformat(payload['built_at_utc'].replace('Z', '+00:00'))
    if built.tzinfo is None:
        raise ValueError('Macro build timestamp must include timezone')
    if built.date().isoformat() < session:
        raise ValueError('Board build precedes its market session')
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    session_date = datetime.strptime(session, '%Y-%m-%d').date()
    if not is_xnys_session(session_date) or built < session_bounds(session_date)[1]:
        raise ValueError('Completed-session mentality requires a closed XNYS session')
    if not isinstance(payload.get('conditions', {}).get('current'), dict) or not payload['conditions']['current']:
        raise ValueError('Measured macro conditions required')
    evidence, issues = evidence_from_board(payload, session, built)
    out = {'schema_version': SCHEMA, 'calculation_version': VERSION,
           'authority': 'ADVISORY_ONLY', 'can_grant_capital': False, 'can_reverse_direction': False,
           'board_version': payload.get('board_version'), 'as_of_session': session,
           'built_at_utc': payload['built_at_utc'], 'build_kind': payload.get('build', {}).get('kind'),
           'evidence': evidence, 'mentality': assessment(evidence), 'source_issues': issues,
           'methodology': {'status': 'PROVISIONAL_DESCRIPTIVE_NOT_PREDICTIVE',
                           'broad_progress_min_indices': 3, 'index_universe': ['SPY', 'QQQ', 'IWM', 'DIA'],
                           'daily_return_floor_pct': 0.25, 'five_session_return_floor_pct': 0.50,
                           'explanation': 'Progress requires at least three of four dated index returns beyond the applicable positive or negative floor. These are descriptive noise floors, not calibrated forecasts.'},
           'source_quality': payload.get('external', {}),
           'limitations': [
               'Crowd mentality is inferred from proxies, not a measurement of investor intentions.',
               'Actual positioning, crowdedness, forced exits and institutional activity remain unverified.',
               'Daily gap/close behaviour does not establish intraday value acceptance or order-book absorption.',
               'Trading urgency requires intraday speed, spread and executable-liquidity evidence.',
               'No crowd probabilities, fear score, trade direction, rank or execution permission is generated.',
               'Observation dates, board build and interpretation publication are separate clocks.',
               'Latest post-run mentality was not used to create the frozen trade decisions.',
           ]}
    out['source_revision'] = digest({key: out[key] for key in ('calculation_version', 'methodology', 'board_version', 'as_of_session', 'built_at_utc', 'evidence', 'source_quality')})
    out['changes'] = compare_previous(out, previous)
    out['revision'] = digest(out)
    return out


def verify(document):
    if (not isinstance(document, dict) or document.get('schema_version') != SCHEMA
            or document.get('calculation_version') != VERSION or document.get('authority') != 'ADVISORY_ONLY'
            or document.get('can_grant_capital') is not False or document.get('can_reverse_direction') is not False):
        raise ValueError('Unsupported Market Mentality publication; republish the saved board')
    identity = {key: value for key, value in document.items() if key not in ('revision', 'published_at_utc')}
    if document.get('revision') != digest(identity):
        raise ValueError('Market Mentality revision integrity check failed')
    return document


def _atomic(path, document):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(canonical(document), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def publish(payload, output_dir):
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    target, lock = root / 'lab_macro_latest.json', root / 'lab_mentality_publish.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    try:
        previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else None
        compatible = previous if previous and previous.get('schema_version') == SCHEMA else None
        if compatible:
            verify(compatible)
        document = project(payload, compatible)
        if compatible:
            if document['source_revision'] == compatible['source_revision']:
                return compatible
            old_time = datetime.fromisoformat(compatible['built_at_utc'].replace('Z', '+00:00'))
            new_time = datetime.fromisoformat(document['built_at_utc'].replace('Z', '+00:00'))
            if document['as_of_session'] < compatible['as_of_session'] or new_time < old_time:
                raise ValueError('Older board cannot replace the latest mentality assessment')
        document['published_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        history = root / 'mentality_history'
        history.mkdir(exist_ok=True)
        archive = history / (document['revision'] + '.json')
        if not archive.exists():
            _atomic(archive, document)
        else:
            verify(json.loads(archive.read_text(encoding='utf-8')))
        _atomic(target, document)
        return document
    finally:
        lock.unlink(missing_ok=True)


def publish_saved_board(path, output_dir):
    """Offline manual import, JSON only: never execute embedded JavaScript."""
    file = Path(path)
    if file.stat().st_size > 30_000_000:
        raise ValueError('Board exceeds 30 MB import limit')
    html = file.read_text(encoding='utf-8-sig')
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


def read_publication(output_dir, revision=None):
    root = Path(output_dir)
    if revision:
        if not re.fullmatch('[0-9a-f]{64}', revision):
            raise ValueError('Invalid mentality revision')
        path = root / 'mentality_history' / (revision + '.json')
    else:
        path = root / 'lab_macro_latest.json'
    return verify(json.loads(path.read_text(encoding='utf-8')))


def register_routes(app, output_dir, runs_dir=None):
    from flask import jsonify, request, send_from_directory

    @app.get('/market-mentality')
    @app.get('/macro-scenarios')
    def macro_scenarios_page():
        return send_from_directory(app.static_folder, 'macro-desk.html')

    def response_for(document):
        response = jsonify(document)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/lab/macro-context')
    def macro_context():
        try:
            document = read_publication(output_dir, request.args.get('revision'))
            built = datetime.fromisoformat(document['built_at_utc'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - built).total_seconds()
            return response_for({**document, 'publication_age_hours': round(age / 3600, 1),
                                 'freshness': 'STALE_BUILD' if age > 36 * 3600 else 'RECENT_BUILD_NOT_SOURCE_FRESHNESS_PROOF'})
        except (OSError, ValueError, KeyError, TypeError):
            response = response_for({'state': 'UNAVAILABLE', 'reason': 'Market Mentality publication is missing, incompatible or failed verification; republish the saved board.'})
            response.status_code = 503
            return response

    if runs_dir is not None:
        @app.get('/api/lab/<run_id>/rows/<row_key>/mentality')
        def mentality_for_trade(run_id, row_key):
            from contracts.lab_review_projection import read_review_card, ReviewRevisionConflict, ReviewIntegrityError
            try:
                if not request.args.get('revision'):
                    raise ValueError('Frozen review revision required')
                root = runs_dir() if callable(runs_dir) else runs_dir
                card = read_review_card(root, run_id, row_key, request.args['revision'])
                context = trade_context(read_publication(output_dir), card['fields'], card['revision'])
                return response_for(context)
            except (ReviewRevisionConflict, ReviewIntegrityError):
                response = response_for({'state': 'REVISION_CONFLICT', 'reason': 'Frozen review changed; reload the trade review.'})
                response.status_code = 409
            except (OSError, ValueError, KeyError, sqlite3.DatabaseError):
                response = response_for({'state': 'CONTEXT_UNAVAILABLE', 'reason': 'Latest mentality context unavailable; frozen trade card is unchanged.'})
                response.status_code = 503
            return response


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Publish Market Mentality from a saved board, offline')
    parser.add_argument('--from-board', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    result = publish_saved_board(args.from_board, args.output_dir)
    print(json.dumps({key: result[key] for key in ('revision', 'as_of_session', 'built_at_utc', 'published_at_utc')}))
