import importlib.util
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
 import requests
 monkeypatch.setattr(requests,'get',lambda *a,**k:pytest.fail('offline test attempted network'))
def module(rel):
 if rel.endswith(('avshunter_fred_monitor_v2_6.py','avshunter_vix_engine_v4_1.py')):
  # These legacy scripts execute their jobs at import. Load only function
  # definitions so an offline transport test cannot launch their producers.
  import ast,types,requests,time,os
  from contracts.source_transport import get_fred_response
  tree=ast.parse((ROOT/rel).read_text(encoding='utf-8'))
  selected={'_fred_get','fetch_fred_vix','_normalise_index','_clean_last','session_cutoff','cut_to_session'}
  tree.body=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in selected]
  m=types.ModuleType('legacy_source_functions')
  m.__dict__.update(requests=requests,time=time,os=os,pd=pd,get_fred_response=get_fred_response,FRED_BASE='https://api.stlouisfed.org/fred',FRED_API_KEY=None,FRED_ATTEMPTS=3,FRED_TIMEOUT_S=60)
  exec(compile(tree,str(ROOT/rel),'exec'),m.__dict__)
  return m
 s=importlib.util.spec_from_file_location('source_test_'+Path(rel).stem,ROOT/rel)
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def transport(): return module('contracts/source_transport.py')
class Response:
 status_code=200
 def __init__(self,payload=None,text=''):
  self.payload=payload;self.text=text;self.headers={'Content-Type':'text/html'}
 def json(self):
  if self.payload is None: raise ValueError('invalid')
  return self.payload
 def raise_for_status(self): pass
def test_decode_failure_is_retried_inside_request_boundary():
 m=transport();responses=iter([Response(text='<html>unavailable</html>'),Response({'observations':[{'date':'2026-10-21','value':'4.2'}]})])
 r=m.get_fred_response('https://api.stlouisfed.org/fred/series/observations',{'api_key':'secret'},get=lambda *a,**k:next(responses),sleep=lambda _:None)
 assert r.json()['observations'][0]['value']=='4.2'
 assert r.source_diagnostics['attempts']==2
def test_xml_fred_observations_are_decoded_without_inventing_dates():
 m=transport();r=m.get_fred_response('https://api.stlouisfed.org/fred/series/observations',{},get=lambda *a,**k:Response(text='<observations><observation date="2026-10-20" value="3.33"/></observations>'),sleep=lambda _:None)
 assert r.json()['observations']==[{'date':'2026-10-20','value':'3.33'}]
 assert r.source_diagnostics['format']=='XML'
def test_permanent_bad_body_fails_closed_and_redacts():
 m=transport();calls=[]
 def get(*a,**k): calls.append(1);return Response(text='secret')
 with pytest.raises(m.FredSourceError) as e: m.get_fred_response('https://api.stlouisfed.org/fred/series/observations',{'api_key':'secret'},get=get,sleep=lambda _:None)
 assert len(calls)==3 and 'secret' not in str(e.value) and 'INVALID_PAYLOAD' in str(e.value)
def future_row(now,last):
 m=module('Enhancements/colab/avshunter_market_intelligence_v5_4_3.py')
 bars=pd.Series([100.,101.],index=pd.to_datetime(['2026-10-21T19:55Z',last]))
 return m.measure_since_us_close('ES=F','ES',bars,datetime(2026,10,21,20,tzinfo=timezone.utc),datetime.fromisoformat(now))
def test_reopening_needs_a_post_reopen_bar_even_within_age_limit():
 row=future_row('2026-10-21T22:01:00+00:00','2026-10-21T20:55Z')
 assert row['state']=='REOPEN_PENDING' and row['stale'] is True
 assert row['next_refresh_utc']=='2026-10-21T22:20:00Z'
def test_after_reopening_grace_old_quote_is_stale():
 assert future_row('2026-10-21T22:25:00+00:00','2026-10-21T20:55Z')['state']=='STALE_AFTER_REOPEN'
def test_fresh_post_reopen_quote_is_ok():
 assert future_row('2026-10-21T22:20:00+00:00','2026-10-21T22:05Z')['state']=='OK'
def test_future_quote_rejected():
 assert future_row('2026-10-21T22:20:00+00:00','2026-10-21T22:25Z')['state']=='FUTURE_QUOTE'
def test_health_recomputes_quote_age_at_build_time():
 m=module('contracts/macro_health.py')
 macro={'as_of_utc':'2026-10-22T12:00:00Z','extras':{'overnight':{'document':{'groups':{'us_futures':[{'symbol':'ES=F','state':'OK','stale':False,'last_bar_utc':'2026-10-21T22:05:00Z'}]}}}}}
 h=m.assess_macro_health(macro,report={'data_quality':{'fred_series_retrieved':0}},now=datetime(2026,10,22,12,tzinfo=timezone.utc))
 assert 'FUTURES_STALE' in h['issues'] and 'FRED_NO_COVERAGE' in h['issues']

@pytest.mark.parametrize('name,call',[
 ('macro_module_v2_8','macro'),('liquidity_monitor_v3_7','liquidity'),
 ('market_intelligence_v5_4_3','market'),('fred_monitor_v2_6','monitor'),('vix_engine_v4_1','vix')])
def test_each_fred_consumer_recovers_a_bad_body(monkeypatch,name,call):
 m=module('Enhancements/colab/avshunter_'+name+'.py')
 responses=iter([Response(text='unavailable'),Response({'observations':[{'date':'2026-10-20','value':'5.12'}]})])
 monkeypatch.setattr(m.requests,'get',lambda *a,**k:next(responses))
 monkeypatch.setattr(m.time,'sleep',lambda _:None)
 monkeypatch.setattr(m,'FRED_API_KEY','test-key',raising=False)
 if call=='macro': assert m.fetch_fred_all({'DGS10':'10Y'},'2026-10-01','test-key')['DGS10'].iloc[-1]==5.12
 elif call=='liquidity': assert m._fred_series('DGS10','2026-10-01').iloc[-1]==5.12
 elif call=='market': assert m.FREDExtractor('test-key').get_series('DGS10')==[('2026-10-20',5.12)]
 elif call=='monitor': assert m._fred_get('series/observations',series_id='DGS10')['observations'][0]['value']=='5.12'
 else: assert m.fetch_fred_vix().iloc[-1]==5.12

def test_fred_permanent_rejection_does_not_retry():
 import requests
 m=transport();calls=[]
 def get(*a,**k):
  calls.append(1);r=Response();r.status_code=400;return r
 with pytest.raises(requests.exceptions.HTTPError): m.get_fred_response('https://api.stlouisfed.org/fred/series/observations',{},get=get,sleep=lambda _:None)
 assert len(calls)==1

@pytest.mark.parametrize('payload',[{},[],{'observations':'bad'},{'observations':[{'value':'1'}]}])
def test_wrong_json_shape_is_unavailable_not_empty_success(payload):
 m=transport()
 with pytest.raises(m.FredSourceError):m.get_fred_response('https://api.stlouisfed.org/fred/series/observations',{},get=lambda *a,**k:Response(payload),sleep=lambda _:None)

def test_dollar_index_uses_working_symbol_and_session_cutoff(monkeypatch):
 m=module('Enhancements/colab/avshunter_macro_module_v2_8.py');calls=[]
 monkeypatch.setenv('AVSH_SESSION_CUTOFF','2026-10-21')
 frame=pd.DataFrame({'Close':[101.,102.]},index=pd.to_datetime(['2026-10-21','2026-10-22']))
 def history(symbol):calls.append(symbol);return frame
 series,source=m.fetch_dollar_index(history=history,proxy_loader=lambda:pytest.fail('proxy called'))
 assert calls==['DX-Y.NYB'] and source=='YFINANCE_DX_Y_NYB'
 assert series.iloc[-1]==101. and str(series.index[-1].date())=='2026-10-21'

def test_unavailable_index_explicit_proxy_then_missing():
 m=module('Enhancements/colab/avshunter_macro_module_v2_8.py')
 series,source=m.fetch_dollar_index(history=lambda _:pd.DataFrame(),proxy_loader=lambda:pd.Series([25.],index=pd.to_datetime(['2026-10-20'])))
 assert source=='POLYGON_UUP_PROXY' and series.iloc[-1]==25.
 series,source=m.fetch_dollar_index(history=lambda _:pd.DataFrame())
 assert source=='NONE' and series.empty

@pytest.mark.parametrize('at,last,state',[
 ('2026-10-21T21:30:00+00:00','2026-10-21T20:55:00+00:00','SESSION_BREAK'),
 ('2026-10-24T12:00:00+00:00','2026-10-23T20:55:00+00:00','WEEKEND_CLOSED'),
 ('2026-11-02T23:01:00+00:00','2026-11-02T21:55:00+00:00','REOPEN_PENDING')])
def test_maintenance_weekend_and_dst_are_explicit(at,last,state):
 m=module('contracts/futures_freshness.py')
 result=m.classify_futures_quote(datetime.fromisoformat(at),datetime.fromisoformat(last))
 assert result['state']==state and result['stale']

def test_reopening_poll_recovers_and_preserves_other_source_timestamps():
 m=module('scripts/refresh_futures_snapshot.py')
 times=iter([datetime.fromisoformat(t) for t in ['2026-10-21T22:01:00+00:00','2026-10-21T22:01:00+00:00','2026-10-21T22:01:00+00:00','2026-10-21T22:20:00+00:00','2026-10-21T22:20:00+00:00']])
 calls=[];sleeps=[]
 def history(*args):
  calls.append(1);last='2026-10-21T20:55Z' if len(calls)<=7 else '2026-10-21T22:05Z'
  return pd.DataFrame({'Close':[100.,101.]},index=pd.to_datetime(['2026-10-21T19:55Z',last]))
 doc={'as_of_utc':'2026-10-21T22:00:00Z','us_reference_close_utc':'2026-10-21T20:00:00Z','groups':{'fx':[{'last_bar_utc':'2026-10-21T21:50:00Z'}]}}
 result=m.refresh_until_ready(doc,history=history,clock=lambda:next(times),sleep=sleeps.append,max_wait_seconds=1200)
 assert result['futures_refresh']['attempts']==2 and result['futures_refresh']['status']=='AVAILABLE'
 assert sleeps==[30] and result['as_of_utc']==doc['as_of_utc'] and result['groups']['fx']==doc['groups']['fx']
 assert 'us_futures' not in doc['groups']

def test_source_health_reaches_macro_override_quant_packet_and_desk(tmp_path):
 import json
 import build_macro_json as builder
 from contracts.macro_health import assess_macro_health
 from contracts.interpreter_macro_context import materialize_interpreter_macro_context
 from scripts.macro_quant_packet import build_macro_quant_packet
 macro=json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/macro.json').read_text(encoding='utf-8'))
 payload={'data':{'report_json':{'data_quality':{'fred_series_retrieved':0}},'overnight_json':{'us_reference_session':'2026-10-21','groups':{'us_futures':[{'symbol':'ES=F','last':100.,'last_bar_utc':'2026-10-21T20:55:00Z','state':'OK','stale':False}]}},'macro_module_contract_json':{'dxy_source':'POLYGON_UUP_PROXY','dxy_observation_date':'2026-10-20','as_of':'2026-10-21'}},'files_found_by_key':{}}
 macro=builder.apply_market_data_overrides(macro,payload)
 macro['macro_health']=assess_macro_health(macro,report=payload['data']['report_json'],now=datetime(2026,10,22,12,tzinfo=timezone.utc))
 assert {'FUTURES_MISSING','FUTURES_STALE','DOLLAR_INDEX_PROXY','DOLLAR_INDEX_STALE','FRED_NO_COVERAGE'}<=set(macro['macro_health']['issues'])
 assert build_macro_quant_packet(macro)['macro_health']==macro['macro_health']
 run=tmp_path/'run';run.mkdir();(run/'macro_snapshot.json').write_text(json.dumps(macro),encoding='utf-8')
 packet=materialize_interpreter_macro_context(run_dir=run,session_date='2026-10-21',macro_dir=tmp_path/'macro',prefer_run_snapshot=True)['packet']
 assert packet['macro_health']==macro['macro_health']
 assert packet['macro_health']['source_health']['us_futures']['status']=='DEGRADED'

def test_fred_daily_observation_staleness_is_reported_by_series():
 m=module('contracts/macro_health.py')
 macro={'as_of_utc':'2026-10-22T12:00:00Z','extras':{'fred_series_health':[
  {'series':'DGS10','frequency':'Daily','last_observation':'2026-10-01','fetched_utc':'2026-10-22T11:00:00Z'},
  {'series':'CPIAUCSL','frequency':'M','last_observation':'2026-09-01','fetched_utc':'2026-10-22T11:00:00Z'}]}}
 health=m.assess_macro_health(macro,report={'data_quality':{'fred_series_retrieved':2}},now=datetime(2026,10,22,12,tzinfo=timezone.utc))
 rows=health['source_health']['fred']['series']
 assert rows[0]['assessed_status']=='PUBLICATION_UNVERIFIED' and rows[1]['assessed_status']=='FRESH'
 assert 'FRED_SERIES_PUBLICATION_UNVERIFIED' in health['issues']

def test_refresh_command_appends_source_lineage_and_returns_degraded(tmp_path,monkeypatch):
 import json
 m=module('scripts/refresh_futures_snapshot.py')
 original=tmp_path/'overnight_20261021_220100.json';original.write_text('{"us_reference_close_utc":"2026-10-21T20:00:00Z"}',encoding='utf-8')
 raw=original.read_bytes()
 monkeypatch.setattr(m,'refresh_until_ready',lambda *a,**k:{'futures_refresh':{'status':'DEGRADED'}})
 assert m.main(['--input-dir',str(tmp_path),'--max-wait-seconds','0'])==2
 assert original.read_bytes()==raw
 appended=[p for p in tmp_path.glob('overnight_*.json') if p!=original]
 assert len(appended)==1
 result=json.loads(appended[0].read_text(encoding='utf-8'))
 assert result['futures_refresh']['parent_file']==original.name
 assert len(result['futures_refresh']['parent_sha256'])==64

def test_completed_asian_session_does_not_use_intraday_staleness_limit():
 m=module('contracts/macro_health.py')
 macro={'as_of_utc':'2026-10-22T12:00:00Z','extras':{'overnight':{'document':{'groups':{'asia':[
  {'symbol':'N225','last':100.,'state':'CLOSED','session_date':'2026-10-22','exchange_tz':'Asia/Tokyo','last_bar_utc':'2026-10-22T06:00:00Z','stale':False}]}}}}}
 h=m.assess_macro_health(macro,now=datetime(2026,10,22,12,tzinfo=timezone.utc))
 assert h['source_health']['asia']['status']=='AVAILABLE'
 assert 'ASIA_STALE' not in h['issues']
