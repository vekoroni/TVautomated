import json
from pathlib import Path
from unittest.mock import patch
import pytest
from flask import Flask
from contracts.lab_macro_desk import project, publish, publish_saved_board, register_routes


def board(**changes):
    return dict({'board_version': 'macro-board-v1.0.0', 'as_of_session': '2026-10-16',
                 'built_at_utc': '2026-10-17T15:41:04+00:00', 'build': {'kind': 'OFF_SESSION'},
                 'conditions': {'current': {'credit': 'WIDENING', 'yields': 'RISING'},
                                'observations': {'credit': {'date': '2026-10-15'}}},
                 'external': {}}, **changes)


def test_advisory_projection_does_not_mutate_or_import_trade_authority():
    data = board(capital_permission=True, direction='CALL', probability=.95)
    before = json.dumps(data, sort_keys=True)
    out = project(data)
    assert json.dumps(data, sort_keys=True) == before
    assert out['authority'] == 'ADVISORY_ONLY'
    assert out['can_grant_capital'] is out['can_reverse_direction'] is False
    assert 'probability' not in out and 'direction' not in out
    assert len(out['scenarios']) == 2
    assert all(s['evidence_ids'] and s['confirmation'] and s['invalidation'] for s in out['scenarios'])
    assert out['evidence'][0]['observation']['date'] == '2026-10-15'


def test_unknown_missing_states_do_not_invent_scenarios():
    assert project(board(conditions={'current': {'credit': 'MISSING'}}))['scenarios'] == []


def test_source_cutoff_and_quality_issues_are_exposed():
    result = project(board(external={'late': {'as_of': '2026-10-18T12:00:00Z'},
                                    'absent': {'status': 'MISSING'}}))
    assert any('later than board build' in item for item in result['source_issues'])
    assert any('MISSING' in item for item in result['source_issues'])


@pytest.mark.parametrize('changes', [{'as_of_session': 'bad'}, {'built_at_utc': '2026-10-17T15:00:00'},
                                      {'conditions': {'current': {}}}])
def test_invalid_publication_rejected(changes, tmp_path):
    with pytest.raises((ValueError, TypeError)):
        publish(board(**changes), tmp_path)
    assert not (tmp_path / 'lab_macro_latest.json').exists()


def test_atomic_publish_idempotence_and_independent_refresh(tmp_path):
    frozen = tmp_path / 'review.sqlite'; frozen.write_bytes(b'frozen review')
    first = publish(board(), tmp_path)
    assert first['revision'] == publish(board(), tmp_path)['revision']
    app = Flask(__name__); register_routes(app, tmp_path); client = app.test_client()
    assert client.get('/api/lab/macro-context').json['revision'] == first['revision']
    second = publish(board(built_at_utc='2026-10-18T10:00:00+00:00'), tmp_path)
    reply = client.get('/api/lab/macro-context')
    assert reply.json['revision'] == second['revision'] != first['revision']
    assert reply.headers['Cache-Control'] == 'no-store'
    assert frozen.read_bytes() == b'frozen review'
    assert not list(tmp_path.glob('*.tmp'))


def test_missing_corrupt_and_stale_are_disclosed(tmp_path):
    app = Flask(__name__); register_routes(app, tmp_path); client = app.test_client()
    assert client.get('/api/lab/macro-context').status_code == 503
    publish(board(built_at_utc='2020-01-01T00:00:00Z'), tmp_path)
    assert client.get('/api/lab/macro-context').json['freshness'] == 'STALE'
    (tmp_path / 'lab_macro_latest.json').write_text('bad')
    assert client.get('/api/lab/macro-context').status_code == 503


def test_manual_import_is_json_only_no_network(tmp_path):
    path = tmp_path / 'board.html'
    path.write_text('<script>const BOARD=' + json.dumps(board()) + ';</script><script>evil()</script>')
    with patch('socket.socket', side_effect=AssertionError('No providers')):
        assert publish_saved_board(path, tmp_path)['as_of_session'] == '2026-10-16'
    path.write_text('<script>const BOARD=evil();</script>')
    with pytest.raises(ValueError): publish_saved_board(path, tmp_path)


def test_worker3_is_retained_but_intake_refuses_and_pipeline_does_not_call_it():
    from worker3.integration.coordinator import _policy
    from worker3.domain import ContractError
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ContractError, match='decommissioned'):
        _policy(root / 'contracts/worker3_integration_v1.json')
    text = (root / 'intelligent_orchestrator.py').read_text(encoding='utf-8')
    assert text.count('materialize_worker3_market_environment(') == 1  # retained definition only
    assert text.index('materialize_lab_macro_evidence(canonical_run_id)') < text.index('_review_publication = republish_saved_review(')
    server = (root / 'intelligence-lab/intelligence_lab.py').read_text(encoding='utf-8')
    assert 'from worker3.' not in server
    assert (root / 'worker3/integration/browser_launch.py').exists()


def test_board_publication_is_after_html_and_not_historical_replay():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'macro_board/build_board.py').read_text(encoding='utf-8')
    assert text.index('target.write_text(html') < text.index('publish_lab_macro(payload, output_dir)')
    assert 'if not as_of:\n        # Independent advisory publication' in text
