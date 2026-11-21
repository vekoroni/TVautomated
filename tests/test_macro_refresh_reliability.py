import copy,importlib.util,json,hashlib
from datetime import datetime,timezone
from pathlib import Path
import pytest
from contracts.macro_health import assess_macro_health

ROOT=Path(__file__).resolve().parents[1]

def test_sydney_friday_close_remains_valid_during_saturday_local_time():
 row={'symbol':'^AXJO','last':8000,'state':'CLOSED','session_date':'2026-10-23','exchange_tz':'Australia/Sydney','last_bar_utc':'2026-10-23T05:10:00Z','stale':False}
 macro={'extras':{'overnight':{'document':{'groups':{'asia':[row]}}}}}
 health=assess_macro_health(macro,now=datetime(2026,10,23,15,tzinfo=timezone.utc))
 assert health['source_health']['asia']['status']=='AVAILABLE'
 row['session_date']='2026-10-22'
 assert assess_macro_health(macro,now=datetime(2026,10,23,15,tzinfo=timezone.utc))['source_health']['asia']['status']=='DEGRADED'

def test_full_refresh_updates_every_live_group_without_redating_old_observations(monkeypatch):
 from scripts import refresh_futures_snapshot as refresh
 now=datetime(2026,10,23,15,tzinfo=timezone.utc)
 class Extractor:
  def __init__(self,**kwargs):self.errors=[]
  def _closes(self,*args):return []
  def _volatility(self,*args):return [{'symbol':'VIX','last_bar_utc':'2026-10-23T14:45:00Z'}]
  def _premarket(self,*args):return [{'symbol':'QQQ','last_bar_utc':'2026-10-23T14:45:00Z'}]
 class Collector:
  OvernightExtractor=Extractor
  OVERNIGHT_SINCE_US_CLOSE={'us_futures':[('ES=F','ES')],'rates_commodities':[('CL=F','CL')],'fx':[('EURUSD=X','EUR')]}
  OVERNIGHT_SESSIONS={'asia':[('^AXJO','ASX','Australia/Sydney','10:00','16:10')],'europe':[('^FTSE','FTSE','Europe/London','08:00','16:30')]}
  @staticmethod
  def measure_since_us_close(symbol,*args):return {'symbol':symbol,'last_bar_utc':'2026-10-23T14:45:00Z'}
  @staticmethod
  def local_session_reading(symbol,*args,**kwargs):return {'symbol':symbol,'last_bar_utc':'2026-10-23T05:10:00Z' if symbol=='^AXJO' else '2026-10-23T14:45:00Z'}
  @staticmethod
  def summarise_group(rows):return {'of':len(rows)}
 monkeypatch.setattr(refresh,'collector',lambda:Collector)
 doc={'as_of_utc':'2026-10-23T10:55:00Z','us_reference_session':'2026-10-22','us_reference_close_utc':'2026-10-22T20:00:00Z','groups':{'fx':[{'last_bar_utc':'2026-10-23T10:40:00Z'}]},'releases_today':[{'observation_date':'2026-09-01'}]}
 original=copy.deepcopy(doc)
 result=refresh.refresh_document(doc,now=now,all_market_data=True)
 assert set(result['groups'])=={'us_futures','rates_commodities','fx','volatility','us_premarket','asia','europe'}
 assert result['groups']['fx'][0]['last_bar_utc']=='2026-10-23T14:45:00Z'
 assert result['groups']['asia'][0]['last_bar_utc']=='2026-10-23T05:10:00Z'
 assert result['as_of_utc']=='2026-10-23T15:00:00Z'
 assert result['releases_today']==original['releases_today'] and doc==original

def test_preview_capture_requires_all_numbered_source_lines_and_matches_producer_bytes():
 from contracts.macro_export_receipt import assemble_preview_source
 raw=b'{\n  "packet_revision": 61\n}\n'
 digest=hashlib.sha256(raw).hexdigest()
 lines=[[1,'{'],[2,'  "packet_revision": 61'],[3,'}'],[4,'\n']]
 assert assemble_preview_source(lines,last_line=4,expected_sha256=digest,expected_bytes=len(raw))==raw
 with pytest.raises(ValueError,match='INCOMPLETE'):assemble_preview_source(lines[1:],last_line=4,expected_sha256=digest)
 with pytest.raises(ValueError,match='CHECKSUM'):assemble_preview_source(lines,last_line=4,expected_sha256='0'*64)
 assert assemble_preview_source(lines,last_line=4,verification_lines=lines)==raw
 with pytest.raises(ValueError,match='SECOND_COMPLETE'):assemble_preview_source(lines,last_line=4)

def test_source_observation_rollback_is_rejected_even_with_newer_local_receipt(tmp_path):
 from contracts.macro_feed_delivery import deliver
 fixture=ROOT/'tests/fixtures/macro_delivery_20261022'
 config={'expected_feeds':['news'],'max_packet_bytes':10485760,'timeout_seconds':1,'max_attempts':1,'https_hosts':[],'state_directory':'state','macro_directory':'macro'}
 inbox=tmp_path/'in';inbox.mkdir();packet=json.loads((fixture/'news.json').read_text());packet['as_of_utc']='2026-10-22T11:00:00Z'
 def send(revision):
  raw=json.dumps(packet).encode();(inbox/'news.json').write_bytes(raw)
  m={'contract_version':'macro_delivery_manifest_v1','packets':[{'feed':'news','revision':revision,'generated_at_utc':'2026-10-23T12:00:00Z','sha256':hashlib.sha256(raw).hexdigest(),'source':'news.json','material_change':True}]}
  (inbox/'manifest.json').write_text(json.dumps(m));return deliver(inbox/'manifest.json',root=tmp_path,config=config,now=datetime(2026,10,23,13,tzinfo=timezone.utc))
 assert send(1)['status']=='COMPLETE'
 before=(tmp_path/'macro/avshunter_macro_enrichment_delta.json').read_bytes()
 packet['as_of_utc']='2026-10-21T11:00:00Z'
 result=send(2)
 assert result['feeds']['news']['error']=='SOURCE_OBSERVATION_OUT_OF_ORDER'
 assert (tmp_path/'macro/avshunter_macro_enrichment_delta.json').read_bytes()==before

def test_durable_queue_is_automatic_idempotent_and_retains_original_source_bytes(tmp_path):
 from contracts.macro_export_receipt import receive_queue
 fixture=ROOT/'tests/fixtures/macro_delivery_20261022'
 config={'expected_feeds':['usmi','news','events'],'max_packet_bytes':10485760,'timeout_seconds':1,'max_attempts':1,'https_hosts':[],'state_directory':'state','macro_directory':'macro','default_manifest':'incoming/manifest.json','export_queue_directory':'exports'}
 queue=tmp_path/'exports';queue.mkdir()
 source_bytes={}
 for feed in config['expected_feeds']:
  raw=(fixture/(feed+'.json')).read_bytes();digest=hashlib.sha256(raw).hexdigest();source_bytes[feed]=(raw,digest)
  (queue/(digest+'.json')).write_bytes(raw)
  (queue/(digest+'.export.json')).write_text(json.dumps({'sha256':digest,'source':digest+'.json','source_chat':feed+'-producer','source_message':'original-message'}))
 results=receive_queue(tmp_path,config)
 assert len(results)==3 and results[-1]['delivery']['status']=='COMPLETE'
 assert receive_queue(tmp_path,config)==[]
 registry=json.loads((tmp_path/'state/accepted.json').read_text())
 for feed,(raw,digest) in source_bytes.items():
  assert registry[feed]['sha256']==digest
  assert (tmp_path/'state/archive'/(digest+'.json')).read_bytes()==raw
 assert (tmp_path/'incoming/manifest.json').exists()

def test_failed_queue_checksum_cannot_publish_a_packet(tmp_path):
 from contracts.macro_export_receipt import receive_queue
 queue=tmp_path/'exports';queue.mkdir();(queue/'bad.json').write_text('{"wrong":true}')
 (queue/'bad.export.json').write_text(json.dumps({'sha256':'0'*64,'source':'bad.json','source_chat':'producer','source_message':'original'}))
 config={'max_packet_bytes':1024,'state_directory':'state','export_queue_directory':'exports'}
 with pytest.raises(ValueError,match='CHECKSUM'):receive_queue(tmp_path,config)
 assert not (tmp_path/'state/accepted.json').exists()

def test_fred_health_distinguishes_fetched_series_count_and_measurement_period():
 now=datetime(2026,10,23,15,tzinfo=timezone.utc)
 macro={'extras':{'fred_series_health':[
  {'series':'GDPC1','frequency':'Q','last_observation':'2026-04-01','fetched_utc':'2026-10-23T14:30:00Z'},
  {'series':'PCE','frequency':'M','last_observation':'2026-08-01','fetched_utc':'2026-10-23T14:30:00Z'}]}}
 h=assess_macro_health(macro,report={'data_quality':{'fred_series_retrieved':1}},now=now)
 assert h['fred_series_retrieved']==2
 assert h['source_health']['fred']['producer_reported_series_retrieved']==1
 rows=h['source_health']['fred']['series']
 assert rows[0]['observation_period_end']=='2026-06-30'
 assert rows[1]['observation_period_end']=='2026-08-31'
 assert all(r['source_refresh_status']=='RECENT_FETCH' for r in rows)
 # Publication policy ages monthly/quarterly observations from period end,
 # not their native period-start labels or their retrieval timestamps.
 assert [r['assessed_age_days'] for r in rows]==[115,53]
 assert [r['native_observation_age_days'] for r in rows]==[205,83]
 assert [r['last_observation'] for r in rows]==['2026-04-01','2026-08-01']
 assert all(r['assessed_status']=='FRESH' and r['not_live'] for r in rows)
 assert not h['source_health']['fred']['accepted_latest_public'], 'Age-policy acceptance is not latest-public verification'


@pytest.mark.parametrize('code,freq,observed,period_end,limit',[
 ('GDPC1','Q','2026-04-01','2026-06-30',140),
 ('PCE','M','2026-08-01','2026-08-31',75),
])
def test_fred_period_age_boundary_is_independent_of_recent_fetch(code,freq,observed,period_end,limit):
 from datetime import timedelta
 end=datetime.fromisoformat(period_end).replace(hour=15,tzinfo=timezone.utc)
 for days,expected in [(limit,'FRESH'),(limit+1,'PUBLICATION_UNVERIFIED')]:
  now=end+timedelta(days=days)
  item=dict(series=code,frequency=freq,last_observation=observed,fetched_utc=now.isoformat())
  original=copy.deepcopy(item)
  h=assess_macro_health({'extras':{'fred_series_health':[item]}},now=now)
  row=h['source_health']['fred']['series'][0]
  assert item==original
  assert row['source_refresh_status']=='RECENT_FETCH'
  assert row['assessed_age_days']==days and row['observation_period_end']==period_end
  assert row['last_observation']==observed and row['assessed_status']==expected
  assert row['gap_disposition']==('NO_GAP' if expected=='FRESH' else 'ACTIVE_GUIDANCE_GAP')
  assert not h['source_health']['fred']['accepted_latest_public']


@pytest.mark.parametrize('code,freq,observed,newer',[
 ('GDPC1','Q','2026-04-01','2026-07-01'),
 ('PCE','M','2026-08-01','2026-09-01'),
])
def test_fred_known_newer_release_overrides_age_policy_and_recent_fetch(code,freq,observed,newer):
 from contracts.fred_publication import publication_receipt
 now=datetime(2026,10,23,15,tzinfo=timezone.utc)
 item=dict(series=code,frequency=freq,last_observation=observed,fetched_utc=now.isoformat())
 # Saved in-memory provider-response fixture; no network or live source writes.
 item.update(publication_receipt([{'date':observed,'value':'100'},
                                  {'date':newer,'value':'101'}],now.date(),now))
 h=assess_macro_health({'extras':{'fred_series_health':[item]}},now=now)
 row=h['source_health']['fred']['series'][0]
 assert row['source_refresh_status']=='RECENT_FETCH'
 assert row['assessed_status']=='MISSED_PUBLIC_UPDATE'
 assert row['last_observation']==observed and row['public_latest_observation']==newer
 assert row['gap_disposition']=='ACTIVE_GUIDANCE_GAP'
 assert 'FRED_SERIES_MISSED_PUBLIC_UPDATE' in h['issues']

def test_native_usmi_timestamp_windows_are_lossless_and_chronologically_validated():
 from contracts.us_money_index_contract import validate_us_money_index_packet
 raw=json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/usmi.json').read_text())
 original=copy.deepcopy(raw)
 assert validate_us_money_index_packet(raw)['valid'],'Existing date-only packets remain valid'
 raw['analysis_window']['start']='2026-10-21T20:00:00Z'
 raw['analysis_window']['end']='2026-10-21T21:01:23Z'
 before=copy.deepcopy(raw);report=validate_us_money_index_packet(raw)
 assert report['valid'],report['errors']
 assert report['packet']['source_payload']==before and raw==before
 assert report['packet']['market_as_of_session']=='2026-10-21'
 assert report['packet']['state']==validate_us_money_index_packet(original)['packet']['state']
 for start,end in [('2026-10-21T21:00:00Z','2026-10-21T20:00:00Z'),('2026-10-21T20:00:00','2026-10-21T21:01:23Z'),('2026-10-21T20:00:00Z','2026-10-21T22:00:00Z')]:
  bad=copy.deepcopy(raw);bad['analysis_window'].update(start=start,end=end)
  assert not validate_us_money_index_packet(bad)['valid'],(start,end)

def test_usmi_score_description_stays_unknown_boolean_without_rejecting_raw_intelligence():
 from contracts.us_money_index_contract import validate_us_money_index_packet
 raw=json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/usmi.json').read_text())
 raw['current_state']['risk_off_transition']='RISK_OFF_TRANSITION_SCORE82OF100__QUALIFIED_OBSERVATION_NOT_SYSTEMIC'
 report=validate_us_money_index_packet(raw)
 assert report['valid'],report['errors']
 assert report['packet']['state']['risk_off_transition'] is None
 assert report['packet']['source_payload']==raw
 assert report['packet']['quality_issues']
 raw['current_state']['risk_off_transition']='RISK_OFF_TRANSITION_SCORE101OF100__INVALID'
 assert not validate_us_money_index_packet(raw)['valid']

def test_source_chat_must_match_the_declared_producer_before_any_publication(tmp_path):
 from contracts.macro_export_receipt import receive_export
 fixture=ROOT/'tests/fixtures/macro_delivery_20261022/news.json'
 config={'expected_feeds':['news'],'max_packet_bytes':10485760,'state_directory':'state','macro_directory':'macro','default_manifest':'incoming/manifest.json','producer_chat_ids':{'news':'expected-news-chat'}}
 with pytest.raises(ValueError,match='SOURCE_CHAT_FEED_MISMATCH'):
  receive_export(fixture,root=tmp_path,config=config,source_chat='incorrect-chat-id',source_message='source-message')
 assert not (tmp_path/'state/accepted.json').exists()

def test_repeated_receipt_keeps_provenance_history_without_advancing_local_sequence(tmp_path):
 from contracts.macro_export_receipt import receive_export
 fixture=ROOT/'tests/fixtures/macro_delivery_20261022/news.json'
 config={'expected_feeds':['news'],'max_packet_bytes':10485760,'timeout_seconds':1,'max_attempts':1,'https_hosts':[],'state_directory':'state','macro_directory':'macro','default_manifest':'in/manifest.json'}
 first=receive_export(fixture,root=tmp_path,config=config,source_chat='news-chat',source_message='source-one')
 before=json.loads((tmp_path/'state/accepted.json').read_text())['news']['revision']
 second=receive_export(fixture,root=tmp_path,config=config,source_chat='news-chat',source_message='source-two')
 assert second['delivery']['feeds']['news']['status']=='DUPLICATE'
 assert json.loads((tmp_path/'state/accepted.json').read_text())['news']['revision']==before
 history=list((tmp_path/'state/transport_receipts/history').glob('*.json'))
 assert len(history)==1 and json.loads(history[0].read_text())['source_message']=='source-one'
 assert len(history[0].name)<50

def test_board_bounded_event_display_keeps_new_intelligence_instead_of_oldest_ledger_rows():
 from types import SimpleNamespace
 from macro_board.build_board import build_intel
 rows=[{'event_id':f'event-{i}','event_name':f'event-{i}','information_cutoff_utc':f'2026-10-{10+i:02d}T12:00:00Z'} for i in range(10)]
 packet={'events':rows}
 external={'event_payload':SimpleNamespace(status='OK',data=packet)}
 result=build_intel(external,None,max_events=8)['events']
 assert [event['event_id'] for event in result['events']]==[f'event-{i}' for i in range(9,1,-1)]
 assert result['coverage']=={'total_events':10,'displayed_events':8,'omitted_historical_events':2,'ordering':'LATEST_SOURCE_OBSERVATION_FIRST'}
 assert packet['events']==rows and len(packet['events'])==10

def test_board_exposes_data_health_and_prior_analysis_age_for_data_only_publications():
 from macro_board.build_board import build_intel
 packet={'macro_health':{'status':'DEGRADED','issues':['AI_SYNTHESIS_NOT_REFRESHED']},'_builder_metadata':{'build_mode':'DATA_ONLY','analysis_built_at':'2026-10-23T14:54:03Z','built_at':'2026-10-23T15:10:00Z','model_called':False}}
 intel=build_intel({},packet)
 assert intel['macro_health']==packet['macro_health']
 assert intel['synthesis']['build_mode']=='DATA_ONLY'
 assert intel['synthesis']['analysis_built_at']=='2026-10-23T14:54:03Z'
 assert intel['synthesis']['model_called'] is False

def test_snapshot_uses_collection_completion_clock_without_admitting_truly_future_quotes():
 import pandas as pd
 from scripts import refresh_futures_snapshot as refresh
 start=datetime(2026,10,23,15,13,57,tzinfo=timezone.utc)
 finish=datetime(2026,10,23,15,14,13,tzinfo=timezone.utc)
 def history(symbol,period,interval):
  return pd.DataFrame({'Close':[100.,101.]},index=pd.to_datetime(['2026-10-22T19:55:00Z','2026-10-23T15:14:00Z']))
 class Response:
  status_code=200
  def json(self):return {'data':{}}
 doc={'us_reference_session':'2026-10-22','us_reference_close_utc':'2026-10-22T20:00:00Z','groups':{}}
 result=refresh.refresh_document(doc,history=history,now=start,all_market_data=True,http_get=lambda *a,**k:Response(),completion_clock=lambda:finish)
 fx=next(row for row in result['groups']['fx'] if row['symbol']=='USDJPY=X')
 assert fx['last']==101 and fx['state']=='OK' and fx['last_bar_utc']=='2026-10-23T15:14:00Z'
 assert result['as_of_utc']=='2026-10-23T15:14:13Z'
 result=refresh.refresh_document(doc,history=history,now=start,all_market_data=True,http_get=lambda *a,**k:Response(),completion_clock=lambda:start)
 fx=next(row for row in result['groups']['fx'] if row['symbol']=='USDJPY=X')
 assert fx['state']=='FUTURE_QUOTE' and fx['last'] is None

