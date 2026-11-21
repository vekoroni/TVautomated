from datetime import datetime,timezone
import pytest

def test_data_only_base_requires_exact_archived_ai_and_never_chains_data_only(tmp_path,monkeypatch):
 from scripts.publish_macro_data_only import resolve_analysis_base
 import json,hashlib
 monkeypatch.setattr("scripts.publish_macro_data_only.builder.validate_macro_json",lambda p:(True,[]))
 raw=json.dumps({'_builder_metadata':{'built_at':'2026-10-23T14:54:00Z'}}).encode();h=hashlib.sha256(raw).hexdigest(); d=tmp_path/'data/macro/publication_bases';d.mkdir(parents=True);(d/(h+'.json')).write_bytes(raw)
 current={'_builder_metadata':{'build_mode':'DATA_ONLY','prior_ai_packet_sha256':h}}
 assert resolve_analysis_base(current,tmp_path)[1]==h
 (d/(h+'.json')).write_bytes(b'{}')
 with pytest.raises(ValueError,match='hash'):resolve_analysis_base(current,tmp_path)

def test_gex_health_must_not_hide_old_or_missing_chain_sessions():
 from contracts.macro_health import assess_macro_health
 now=datetime(2026,10,24,12,tzinfo=timezone.utc)
 m={'extras':{'overnight':{'document':{'us_reference_session':'2026-10-23'}},'gex_source_health':{'status':'COMPLETE','session_date':'2026-10-21','fallback_used':True,'validation_status':'VALIDATED'}}}
 h=assess_macro_health(m,now=now)
 assert h['source_health']['gex']['status']=='STALE_SESSION' and 'GEX_STALE_SESSION' in h['issues']
 m['extras']['gex_source_health'].update(session_date='2026-10-23',fallback_used=False)
 assert assess_macro_health(m,now=now)['source_health']['gex']['status']=='AVAILABLE'

def test_all_market_refresh_advances_reference_to_latest_completed_session():
 from scripts import refresh_futures_snapshot as refresh
 import pandas as pd
 now=datetime(2026,10,24,12,tzinfo=timezone.utc)
 def history(*a):return pd.DataFrame({'Close':[100.,101.]},index=pd.to_datetime(['2026-10-23T19:55:00Z','2026-10-23T20:55:00Z']))
 class Response:
  status_code=200
  def json(self):return {'data':{}}
 result=refresh.refresh_document({'us_reference_session':'2026-10-22','us_reference_close_utc':'2026-10-22T20:00:00Z','groups':{}},history=history,now=now,all_market_data=True,http_get=lambda *a,**k:Response())
 assert result['us_reference_session']=='2026-10-23'
 assert result['us_reference_close_utc']=='2026-10-23T20:00:00Z'


def test_saturday_closed_quotes_are_last_session_evidence_not_live_or_broken():
 from contracts.macro_health import assess_macro_health
 now=datetime(2026,10,24,12,tzinfo=timezone.utc)
 row={'symbol':'USDJPY=X','last':156.8,'last_bar_utc':'2026-10-23T20:55:00Z','state':'STALE','stale':True}
 m={'extras':{'overnight':{'document':{'us_reference_session':'2026-10-23','groups':{'fx':[row]}}}}}
 x=assess_macro_health(m,now=now)['source_health']['fx']['instruments'][0]
 assert x['state']=='MARKET_CLOSED_LAST_SESSION' and not x['stale'] and x['not_live']
 row['last_bar_utc']='2026-10-22T20:55:00Z'
 assert assess_macro_health(m,now=now)['source_health']['fx']['instruments'][0]['stale']

def test_failed_board_publication_is_retried_despite_macro_packet_having_new_hashes(tmp_path):
 from scripts.publish_macro_data_only import publication_is_current
 import json
 d=tmp_path/'data/macro/delivery';d.mkdir(parents=True);(d/'accepted.json').write_text(json.dumps({'usmi':{'sha256':'abc'}}))
 current={'_builder_metadata':{'delivery_accepted_hashes':{'usmi':'abc'}}}
 assert not publication_is_current(current,tmp_path,'new-macro',require_board=True)
 (d/'data_only_board_receipt.json').write_text(json.dumps({'macro_sha256':'old-macro'}))
 assert not publication_is_current(current,tmp_path,'new-macro',require_board=True)
 (d/'data_only_board_receipt.json').write_text(json.dumps({'macro_sha256':'new-macro'}))
 assert publication_is_current(current,tmp_path,'new-macro',require_board=True)

def test_future_fred_rows_are_excluded_without_redating_valid_observations():
 from contracts.source_transport import filter_observation_window
 obs=[{'date':'2026-10-23','value':'4.65'},{'date':'2026-10-26','value':'4.65'}]
 assert filter_observation_window(obs,'2026-10-23')==obs[:1]
 assert obs[1]['date']=='2026-10-26'
