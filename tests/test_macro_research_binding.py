"""Latest research reaches synthesis and publication from the same frozen bytes."""
import json
from pathlib import Path
import build_macro_json as builder
from contracts.macro_health import capture_research_context, attach_research_context
ROOT=Path(__file__).resolve().parents[1]

def test_latest_usmi_revision_is_not_lost_behind_historical_character_limit():
    packet={'source_payload':{'packet_revision':57},'state':{'rev1_old':'OLD_HISTORY'*4000,'rev57_current':{'routing':'LATEST_META_IBM_PAUSED'}},'sector_routing':{'late':'LATEST_SECTOR_ROUTE'}}
    text=builder.format_data_for_prompt({'data':{'us_money_index_advisory':packet}})
    assert 'LATEST_META_IBM_PAUSED' in text and 'LATEST_SECTOR_ROUTE' in text
    assert 'OLD_HISTORY' not in text

def test_bound_news_and_events_survive_live_file_replacement(tmp_path):
    import shutil
    for src,dst in [('news.json','avshunter_macro_enrichment_delta.json'),('events.json','economic_events_latest.json')]:
        shutil.copyfile(ROOT/'tests/fixtures/macro_delivery_20261022'/src,tmp_path/dst)
    bound=capture_research_context(tmp_path)
    (tmp_path/'avshunter_macro_enrichment_delta.json').write_text('{}')
    (tmp_path/'economic_events_latest.json').write_text('{}')
    macro={'contract_version':'macro_contract_v1_0'}
    result=attach_research_context(macro,tmp_path,bound=bound)
    assert result['extras']['macro_enrichment_delta']['as_of_utc']==bound['news']['packet']['as_of_utc']
    assert result['extras']['economic_events']==bound['events']['packet']
    assert result['extras']['research_source_manifest']['news']['sha256']==bound['news']['sha256']
