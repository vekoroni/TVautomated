"""Only explicitly bound replacement producers may deliver a feed."""
from pathlib import Path
import pytest
from contracts.macro_export_receipt import receive_export

FIXTURE=Path(__file__).parent/'fixtures/macro_delivery_20261022/news.json'


def config():
    return {'expected_feeds':['news'],'max_packet_bytes':10485760,'timeout_seconds':1,
            'max_attempts':1,'https_hosts':[],'state_directory':'state','macro_directory':'macro',
            'default_manifest':'incoming/manifest.json','producer_chat_ids':{'news':'current-news'},
            'producer_chat_aliases':{'news':['legacy-news','asia-news']}}


@pytest.mark.parametrize('source',['current-news','legacy-news','asia-news'])
def test_only_declared_primary_and_alias_producers_are_accepted(tmp_path,source):
    receipt=receive_export(FIXTURE,root=tmp_path,config=config(),source_chat=source,source_message='saved-message')
    assert receipt['delivery']['feeds']['news']['status']=='ACCEPTED'
    assert receipt['source_chat']==source


@pytest.mark.parametrize('source',['usmi-source','unknown-news','legacy-news-lookalike'])
def test_unbound_or_other_feed_sources_are_still_rejected_without_writes(tmp_path,source):
    with pytest.raises(ValueError,match='SOURCE_CHAT_FEED_MISMATCH'):
        receive_export(FIXTURE,root=tmp_path,config=config(),source_chat=source,source_message='saved-message')
    assert not (tmp_path/'state/accepted.json').exists()
