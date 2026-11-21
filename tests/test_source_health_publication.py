"""Exercise the actual builder publication body with an offline synthesis boundary."""
import copy
import json
from pathlib import Path
import shutil
import sys
import build_macro_json as builder

FIXTURES=Path(__file__).parent/'fixtures/macro_delivery_20261022'

def test_source_failure_survives_actual_macro_publication(tmp_path,monkeypatch,capsys):
    drop=tmp_path/'dropbox';macro=drop/'macro';macro.mkdir(parents=True)
    shutil.copyfile(FIXTURES/'usmi.json',macro/'avshunter_us_money_index.json')
    shutil.copyfile(FIXTURES/'news.json',macro/'avshunter_macro_enrichment_delta.json')
    shutil.copyfile(FIXTURES/'events.json',macro/'economic_events_latest.json')
    base=json.loads((FIXTURES/'macro.json').read_text(encoding='utf-8'))
    payload={'data':{'report_json':{'data_quality':{'fred_series_retrieved':0}},
             'overnight_json':{'us_reference_session':'2026-10-21','groups':{'us_futures':[
                 {'symbol':'ES=F','last':100.,'last_bar_utc':'2026-10-21T20:55:00Z','state':'OK','stale':False}]}},
             'macro_module_contract_json':{'dxy_source':'NONE','as_of':'2026-10-21'}},
             'files_found':[], 'files_found_by_key':{},'files_missing':[],
             'input_manifest':{'manifest_id':'OFFLINE_TEST','manifest_sha256':'a'*64}}
    monkeypatch.setattr(builder,'PIPELINE_MACRO_DIR',tmp_path/'canonical')
    monkeypatch.setattr(builder,'load_data_payload',lambda *a,**kw:copy.deepcopy(payload))
    monkeypatch.setattr(builder,'format_data_for_prompt',lambda *a:'OFFLINE FIXTURE')
    monkeypatch.setattr(builder,'call_macro_api',lambda *a,**kw:copy.deepcopy(base))
    monkeypatch.setattr(builder,'build_macro_input_manifest',lambda *a,**kw:payload['input_manifest'])
    monkeypatch.setattr(builder,'publish_macro_input_manifest',lambda *a,**kw:dict(payload['input_manifest']))
    monkeypatch.setattr(builder,'build_macro_prompt_context',lambda *a,**kw:{'sources':{},'input_consumption_ledger':{}})
    monkeypatch.setattr(builder,'apply_macro_input_governance',lambda m,p:m)
    monkeypatch.setattr(builder,'validate_macro_output_coherence',lambda *a:None)
    monkeypatch.setattr(builder,'archive_macro_packet',lambda *a:{'packet_id':'TEST','sha256':'b'*64})
    monkeypatch.setattr(builder,'publish_macro_projections',lambda *a:{'sha256':'c'*64})
    monkeypatch.setattr(sys,'argv',['builder','--force','--health-exit-code','--dropbox',str(drop),'--us-money-index',str(macro/'avshunter_us_money_index.json')])
    assert builder.main()==2
    published=json.loads((macro/'macro_intelligence_latest.json').read_text())
    assert published['_builder_metadata']['validation']=='DEGRADED'
    assert published['_builder_metadata']['schema_validation']=='PASS'
    assert published['_builder_metadata']['input_consumption_status']=='COMPLETE_WITH_DEGRADED_EVIDENCE'
    assert published['extras']['us_money_index']['state']['risk_off_transition'] is None
    assert set(published['extras']['research_source_manifest'])=={'usmi','news','events'}
    assert {'FRED_NO_COVERAGE','FUTURES_STALE','FUTURES_MISSING','DOLLAR_INDEX_MISSING'} <= set(published['macro_health']['issues'])
    assert 'BUILD DEGRADED' in capsys.readouterr().out
