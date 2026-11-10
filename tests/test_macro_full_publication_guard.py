import json
import sys
import pytest
from scripts import publish_macro_data_only as publisher

def configure(root, mode):
    (root/'config').mkdir(exist_ok=True)
    (root/'config/macro_delivery_v1.json').write_text(json.dumps({'publication_mode':mode}))

def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

@pytest.mark.parametrize('existing',[False,True])
def test_full_cli_exits_zero_before_seed_lock_recovery_or_board(tmp_path,monkeypatch,capsys,existing):
    configure(tmp_path,'FULL')
    if existing:
        target=tmp_path/'dropbox/macro/macro_intelligence_latest.json';target.parent.mkdir(parents=True)
        target.write_text('{"full_build":"must not be replaced"}')
    before=snapshot(tmp_path)
    monkeypatch.setattr(publisher,'R',tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('FULL must not enter data-only work')
    monkeypatch.setattr(publisher,'load_publication_seed',forbidden)
    monkeypatch.setattr(publisher,'publish',forbidden)
    monkeypatch.setattr(sys,'argv',['publish_macro_data_only.py','--board','--if-changed'])
    assert publisher.main()==0
    assert 'SKIPPED' in capsys.readouterr().out
    assert snapshot(tmp_path)==before
    assert not (tmp_path/'data').exists()

@pytest.mark.parametrize('entry',['load_publication_seed','publish','resolve_analysis_base'])
def test_full_direct_entries_cannot_read_recovery_base_or_write(tmp_path,monkeypatch,entry):
    configure(tmp_path,'FULL');before=snapshot(tmp_path)
    monkeypatch.setattr(publisher,'R',tmp_path)
    with pytest.raises(publisher.DataOnlyPublicationDisabled):
        if entry=='publish':publisher.publish()
        elif entry=='resolve_analysis_base':publisher.resolve_analysis_base({},tmp_path)
        else:publisher.load_publication_seed(tmp_path)
    assert snapshot(tmp_path)==before

def test_data_only_mode_still_runs_explicit_publisher(tmp_path,monkeypatch):
    configure(tmp_path,'DATA_ONLY')
    monkeypatch.setattr(publisher,'R',tmp_path)
    monkeypatch.setattr(publisher,'load_publication_seed',lambda root:{})
    called=[];monkeypatch.setattr(publisher,'publish',lambda:called.append(True))
    monkeypatch.setattr(sys,'argv',['publisher'])
    assert publisher.main()==0 and called==[True]
    assert not (tmp_path/'data/macro/delivery/data_only_publication.lock').exists()

@pytest.mark.parametrize('mode',[None,'UNKNOWN','data_only'])
def test_unknown_mode_fails_closed(tmp_path,mode):
    configure(tmp_path,mode)
    with pytest.raises(ValueError):publisher.load_publication_seed(tmp_path)
    assert not (tmp_path/'dropbox').exists()
