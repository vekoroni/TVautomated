"""End-to-end macro publication contract, no pipeline or network."""
from copy import deepcopy
import json
from pathlib import Path

from flask import Flask
import pytest

from macro_board.cycle_narrative import assemble
from macro_board.cycle_io import digest, encoded
from macro_board.operating_cycle import load_policy
from macro_board.cycle_publication import bind_cycle, publish_bundle, read_bundle, render_board
from contracts.lab_macro_desk import project, read_publication, register_routes


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket
    def forbidden(*args, **kwargs): raise AssertionError('No network/provider calls')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def fixture():
    payload = {'board_version': 'macro-board-v1.0.0', 'as_of_session': '2026-11-25',
               'built_at_utc': '2026-11-26T11:35:33Z', 'build': {'kind': 'OFF_SESSION'},
               'conditions': {'current': {'credit': 'WIDENING'}}, 'external': {},
               'etfs': {'SPY': {'metrics': {'status': 'FRESH', 'close': 100}}}}
    n = assemble(payload, {}, {}, {}, load_policy(), {'fixture': {'sha256': 'a' * 64}})
    return payload, n


def test_binding_pure_exact_advisory_and_cross_clock_rejected():
    p, n = fixture(); before = deepcopy(p)
    b = bind_cycle(p, n)
    assert p == before
    assert {k: v for k, v in b.items() if k != 'macro_operating_cycle'} == before
    assert b['macro_operating_cycle']['narrative_sha256'] == digest(n)
    assert b['macro_operating_cycle']['narrative_id'] == n['narrative_id']
    bad = deepcopy(n); bad['as_of_session'] = '2026-11-24'
    with pytest.raises(ValueError): bind_cycle(p, bad)
    bad = deepcopy(n); bad['information_cutoff_utc'] = '2026-11-26T12:00:00Z'
    with pytest.raises(ValueError): bind_cycle(p, bad)


def test_lab_carries_same_narrative_and_same_clock_new_cycle_changes_revision():
    p, n = fixture(); a = project(bind_cycle(p, n))
    assert a['macro_operating_cycle']['narrative'] == n
    other = deepcopy(n); other['correction_reason'] = 'fixture correction'; other['narrative_id'] += '_v2'
    b = project(bind_cycle(p, other), a)
    assert a['source_revision'] != b['source_revision']
    bad = bind_cycle(p, n); bad['macro_operating_cycle']['narrative']['status'] = 'COMPLETE'
    with pytest.raises(ValueError): project(bad)


def test_bundle_one_commit_marker_serves_both_consumers_and_preserves_review(tmp_path):
    p, n = fixture(); bound = bind_cycle(p, n)
    frozen = tmp_path / 'review.sqlite'; frozen.write_bytes(b'unchanged ticker verdicts')
    receipt = publish_bundle(bound, tmp_path)
    bundle = read_bundle(tmp_path)
    assert bundle['manifest']['narrative_id'] == n['narrative_id']
    assert read_publication(tmp_path)['macro_operating_cycle']['narrative_id'] == n['narrative_id']
    html = bundle['board'].read_text(encoding='utf-8')
    assert n['narrative_id'] in html and 'macro-operating-cycle' in html
    assert 'MacroCycleView' in html and '<script src="/static/macro-cycle.js"' not in html
    assert frozen.read_bytes() == b'unchanged ticker verdicts'
    app = Flask(__name__); register_routes(app, tmp_path); client = app.test_client()
    data = client.get('/api/lab/macro-context').json
    assert data['macro_operating_cycle']['narrative_sha256'] == digest(n)
    board = client.get('/api/lab/macro-board')
    assert board.status_code == 200 and n['narrative_id'] in board.text
    assert board.headers['Cache-Control'] == 'no-store'
    assert receipt['publication_id'] == data['macro_publication_id']


def test_failed_commit_leaves_last_committed_publication_readable(tmp_path, monkeypatch):
    import macro_board.cycle_publication as pub
    p, n = fixture(); first = publish_bundle(bind_cycle(p, n), tmp_path)
    original = pub.atomic
    def fail_pointer(path, data):
        if Path(path).name == 'macro_publication_latest.json': raise OSError('fixture power loss')
        return original(path, data)
    monkeypatch.setattr(pub, 'atomic', fail_pointer)
    other = deepcopy(n); other['narrative_id'] += '_next'
    with pytest.raises(OSError): publish_bundle(bind_cycle(p, other), tmp_path)
    assert read_bundle(tmp_path)['manifest']['publication_id'] == first['publication_id']
    assert read_publication(tmp_path)['macro_operating_cycle']['narrative_id'] == n['narrative_id']
    monkeypatch.setattr(pub, 'atomic', original)
    retried = publish_bundle(bind_cycle(p, other), tmp_path)
    assert retried['status'] == 'COMMITTED'
    assert read_publication(tmp_path)['macro_operating_cycle']['narrative_id'] == other['narrative_id']


def test_corrupt_committed_artifact_fails_closed_without_old_fallback(tmp_path):
    p, n = fixture(); publish_bundle(bind_cycle(p, n), tmp_path)
    b = read_bundle(tmp_path); b['board'].write_text('corrupted', encoding='utf-8')
    with pytest.raises(ValueError): read_publication(tmp_path)


def test_pinned_old_publication_survives_new_cycle(tmp_path):
    p, n = fixture(); first = publish_bundle(bind_cycle(p, n), tmp_path)
    old = read_publication(tmp_path)
    n2 = deepcopy(n); n2['narrative_id'] += '_v2'
    publish_bundle(bind_cycle(p, n2), tmp_path)
    assert read_publication(tmp_path, old['revision'])['macro_operating_cycle']['narrative_id'] == n['narrative_id']
    assert read_bundle(tmp_path, first['publication_id'])['manifest']['narrative_id'] == n['narrative_id']


def test_normal_adapter_accepts_real_source_read_paths_and_never_runs_a_producer(tmp_path, monkeypatch):
    import pandas as pd
    import macro_board.operating_cycle as cycle
    from macro_board.sources import SourceRead
    p, _ = fixture()
    path = tmp_path / 'source.json'; path.write_text('{}')
    external = {'macro_packet': SourceRead('fixture', str(path), 'FRESH', data={})}
    assert isinstance(external['macro_packet'].file, Path)
    prices = pd.DataFrame({'SPY': [100., 101.]}, index=pd.to_datetime(['2026-11-24', '2026-11-25']))
    config = json.loads((Path(__file__).parents[1] / 'macro_board/config/macro_board_config_v1.json').read_text())
    monkeypatch.setattr(cycle, 'ROOT', tmp_path)
    report = cycle.board_adapter(p, opens=prices, closes=prices, fred=pd.DataFrame(index=prices.index),
                                 external=external, board_config=config, output_dir=tmp_path)
    n = json.loads(Path(report['narrative']).read_bytes())
    receipt = publish_bundle(bind_cycle(p, n), tmp_path)
    assert receipt['status'] == 'COMMITTED'
    assert read_publication(tmp_path)['macro_operating_cycle']['narrative_id'] == n['narrative_id']
