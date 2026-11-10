import hashlib
import json
import pytest
from scripts import publish_macro_data_only as publisher


def setup_seed(root, monkeypatch, value=None):
    (root/'config').mkdir(exist_ok=True)
    (root/'config/macro_delivery_v1.json').write_text(json.dumps({'publication_mode':'DATA_ONLY'}))
    value=value or {'_builder_metadata': {'built_at': '2026-10-23T14:54:03+00:00'}, 'dir_bias': 'NEUTRAL'}
    raw=json.dumps(value).encode()
    digest=hashlib.sha256(raw).hexdigest()
    archive=root/'data/macro/publication_bases';archive.mkdir(parents=True)
    (archive/(digest+'.json')).write_bytes(raw)
    receipt=root/'data/macro/delivery';receipt.mkdir(parents=True)
    (receipt/'data_only_publication_receipt.json').write_text(json.dumps({'prior_ai_packet_sha256':digest}))
    monkeypatch.setattr(publisher.builder,'validate_macro_json',lambda x:(True,[]))
    return archive/(digest+'.json')


def test_missing_live_packet_recovers_only_receipted_base(tmp_path,monkeypatch):
    setup_seed(tmp_path,monkeypatch)
    result=publisher.load_publication_seed(tmp_path)
    assert result['_builder_metadata']['built_at']=='2026-10-23T14:54:03+00:00'
    assert result['dir_bias']=='NEUTRAL'
    assert not (tmp_path/'dropbox/macro/macro_intelligence_latest.json').exists()


def test_corrupt_archive_fails_closed(tmp_path,monkeypatch):
    archive=setup_seed(tmp_path,monkeypatch)
    archive.write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):
        publisher.load_publication_seed(tmp_path)


def test_never_chain_data_only_as_original_ai(tmp_path,monkeypatch):
    setup_seed(tmp_path,monkeypatch,{'_builder_metadata':{'build_mode':'DATA_ONLY'}})
    with pytest.raises(ValueError,match='original analysis'):
        publisher.load_publication_seed(tmp_path)
