"""Offline regression tests for reported failures; never calls providers or builds."""
import importlib.util,json,sys,sqlite3,os,subprocess,shutil
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
STAGE=Path(os.environ.get('MACRO_REPAIR_STAGE',str(R)))
if STAGE!=R:
 import contracts
 contracts.__path__=[str(STAGE/'contracts'),*contracts.__path__]
from contracts.macro_market_refresh_gate import verify_refresh
from contracts.macro_source_sessions import classify_source_session
from contracts import macro_build_budget as budget
spec=importlib.util.spec_from_file_location('fixture_gate',R/'tests/test_macro_market_refresh_gate.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)

@pytest.mark.parametrize('stamp',[None,''])
def test_missing_regional_clock_reports_group_failure_not_iso_crash(tmp_path,stamp):
 path,doc=fixtures.saved_snapshot(tmp_path)
 doc['groups']['asia'].append(dict(symbol='^AXJO',state='NO_SESSION_TODAY',last=100,last_bar_utc=stamp))
 path.write_text(json.dumps(doc));raw=path.read_bytes()
 with pytest.raises(ValueError,match='MARKET_SOURCE_NOT_READY:asia'):
  verify_refresh(tmp_path,not_before=fixtures.START,now=fixtures.NOW)
 assert path.read_bytes()==raw

def dt(s):return datetime.fromisoformat(s.replace('Z','+00:00'))

def test_cme_break_accepts_dated_postclose_reference_without_calling_it_live():
 row=dict(symbol='ES=F',last=7000,last_bar_utc='2026-11-17T21:50:00Z',state='SESSION_BREAK',stale=True)
 before=deepcopy(row)
 result=classify_source_session('us_futures',row,dt('2026-11-17T22:10:00Z'))
 assert result and result['state']=='POST_CLOSE_SESSION_BREAK_REFERENCE'
 assert result['not_live'] and not result['stale']
 assert row==before

@pytest.mark.parametrize('stamp,now',[
 ('2026-11-17T20:55:00Z','2026-11-17T22:10:00Z'),
 ('2026-11-16T21:50:00Z','2026-11-17T22:10:00Z'),
 ('2026-11-17T22:11:00Z','2026-11-17T22:10:00Z'),
 ('2026-11-17T21:50:00Z','2026-11-17T23:10:00Z'),
])
def test_break_exception_never_excuses_preclose_old_future_or_prereopen_quotes(stamp,now):
 from contracts.macro_health import assess_macro_health
 r=dict(symbol='ES=F',last=7000,last_bar_utc=stamp,state='SESSION_BREAK',stale=True)
 h=assess_macro_health({'extras':{'overnight':{'document':{'groups':{'us_futures':[r]}}}}},now=dt(now))
 assert h['source_health']['us_futures']['instruments'][0]['stale']

def configured(tmp):
 (tmp/'config').mkdir()
 p=json.loads((R/'config/macro_build_schedule_v1.json').read_text())
 (tmp/'config/macro_build_schedule_v1.json').write_text(json.dumps(p));return tmp

def test_gate_only_failures_do_not_exhaust_paid_build_cap(tmp_path,monkeypatch):
 root=configured(tmp_path);now=dt('2026-11-17T23:30:00Z')
 for i in range(5):budget.reserve(root,reason='POST_CLOSE',key='gate-only-'+str(i),now=now)
 monkeypatch.delenv('AVSH_FULL_BUILD_ID',raising=False)
 monkeypatch.setenv('AVSH_BUILD_REASON','POST_CLOSE')
 for i in range(4):
  token=budget.reserve(root,reason='POST_CLOSE',key='paid-'+str(i),now=now)
  monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
  budget.authorize_stage(root,'MACRO_SYNTHESIS',now=now)
 with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):
  budget.reserve(root,reason='POST_CLOSE',key='paid-fifth',now=now)

def test_unchanged_gate_fingerprint_cannot_loop_but_corrected_inputs_can_retry(tmp_path):
 root=configured(tmp_path);now=dt('2026-11-17T23:30:00Z')
 budget.reserve(root,reason='POST_CLOSE',key='same-inputs',now=now)
 with pytest.raises(ValueError,match='BUILD_ALREADY_ATTEMPTED'):
  budget.reserve(root,reason='POST_CLOSE',key='same-inputs',now=now)
 assert budget.reserve(root,reason='POST_CLOSE',key='fixed-gate-new-inputs',now=now)

def test_concurrent_preflights_cannot_overcommit_the_paid_stage(tmp_path,monkeypatch):
 root=configured(tmp_path);now=dt('2026-11-17T23:30:00Z')
 tokens=[budget.reserve(root,reason='POST_CLOSE',key=str(i),now=now) for i in range(5)]
 for token in tokens[:4]:
  monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
  budget.authorize_stage(root,'MACRO_SYNTHESIS',now=now)
 monkeypatch.setenv('AVSH_FULL_BUILD_ID',tokens[4])
 with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):
  budget.authorize_stage(root,'MACRO_SYNTHESIS',now=now)

def test_paid_failure_still_counts_and_completion_prevents_token_reuse(tmp_path,monkeypatch):
 root=configured(tmp_path);now=dt('2026-11-17T23:30:00Z')
 token=budget.reserve(root,reason='POST_CLOSE',key='failed',now=now)
 monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
 budget.authorize_stage(root,'MACRO_SYNTHESIS',now=now)
 assert budget.finish_attempt(root,token,1,now=now)=='FAILED_PAID_STAGE'
 assert budget.budget_status(root,'2026-11-17')['paid_attempts']==1
 with pytest.raises(ValueError,match='ALREADY_FINISHED'):
  budget.authorize_stage(root,'BOARD_NARRATIVE',now=now)

def test_reference_requires_actual_break_and_known_value():
 r=dict(symbol='CL=F',last=85,last_bar_utc='2026-11-17T21:50:00Z',state='SESSION_BREAK',stale=True)
 assert classify_source_session('rates_commodities',r,dt('2026-11-17T22:55:00Z'))['not_live']
 for patch in ({'last':None},{'last':float('nan')},{'state':'COLLECTION_ERROR'},{'last_bar_utc':None}):
  assert classify_source_session('rates_commodities',{**r,**patch},dt('2026-11-17T22:10:00Z')) is None
 assert classify_source_session('rates_commodities',r,dt('2026-11-20T22:10:00Z')) is None

def test_stable_fingerprint_changes_for_corrected_code_or_observations_not_fetch_clock(tmp_path):
 root=configured(tmp_path);m=root/'dropbox/market_data';m.mkdir(parents=True)
 p=m/'overnight_20261117_230000.json'
 p.write_text(json.dumps({'as_of_utc':'first','groups':{'fx':[{'last':1.1}]}}))
 a=budget.build_fingerprint(root,'POST_CLOSE','2026-11-17')
 p.write_text(json.dumps({'as_of_utc':'second','groups':{'fx':[{'last':1.1}]}}))
 assert budget.build_fingerprint(root,'POST_CLOSE','2026-11-17')==a
 p.write_text(json.dumps({'as_of_utc':'second','groups':{'fx':[{'last':1.2}]}}))
 b=budget.build_fingerprint(root,'POST_CLOSE','2026-11-17');assert b!=a
 (root/'contracts').mkdir();(root/'contracts/macro_market_refresh_gate.py').write_text('corrected')
 assert budget.build_fingerprint(root,'POST_CLOSE','2026-11-17')!=b

@pytest.mark.skipif(not shutil.which('powershell.exe'),reason='PowerShell required')
def test_actual_runner_budget_refusal_exits_nonzero_before_start(tmp_path):
 runner=STAGE/'Run-MacroInputs.ps1'
 harness=tmp_path/'budget-refusal.ps1'
 harness.write_text(r'''
param($Runner)
$text=Get-Content -LiteralPath $Runner -Raw
$start=$text.IndexOf('    # Reserve an auditable preflight identity.')
$end=$text.IndexOf('    $runStarted = Get-Date',$start)
if($start -lt 0 -or $end -lt 0){throw 'Budget block missing'}
function MockBudgetPython {$global:LASTEXITCODE=1}
$venvPython='MockBudgetPython';$runLabel='PostClose';$exitCode=0
$dataOnlyPublication=$false;$ResearchDeliveryOnly=$false;$SkipMacroJson=$false
$body=$text.Substring($start,$end-$start)
$program=':run do {'+[Environment]::NewLine+$body+[Environment]::NewLine+'} while ($false)'
Invoke-Expression $program
Write-Output ('EXIT_CODE='+$exitCode)
exit $exitCode
''')
 result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(harness),str(runner)],capture_output=True,text=True,timeout=30)
 assert result.returncode==7,result.stdout+result.stderr
 assert 'EXIT_CODE=7' in result.stdout

def test_runner_restores_the_callers_build_identity():
 text=(STAGE/'Run-MacroInputs.ps1').read_text()
 declaration=next(x for x in text.splitlines() if 'foreach ($name in ' in x and 'PYTHONIOENCODING' in x)
 for name in ('AVSH_FULL_BUILD_ID','AVSH_BUILD_REASON','AVSH_BUILD_FINGERPRINT','AVSH_BUILD_OWNER'):
  assert name in declaration

def test_complete_postclose_gate_accepts_only_dated_break_references(tmp_path):
 path,doc=fixtures.saved_snapshot(tmp_path)
 now=dt('2026-11-17T22:10:00Z')
 doc['as_of_utc']=doc['market_refresh']['as_of_utc']='2026-11-17T22:09:00Z'
 for g,rows in doc['groups'].items():
  for r in rows:
   r.update(last_bar_utc='2026-11-17T22:05:00Z')
   if g in ('us_futures','rates_commodities'):
    r.update(last_bar_utc='2026-11-17T21:50:00Z',state='SESSION_BREAK',stale=True)
   elif g=='volatility':r.update(last_bar_utc='2026-11-17T21:15:00Z')
   elif g=='asia':r.update(last_bar_utc='2026-11-17T06:30:00Z',state='NOT_YET_OPEN',session_date='2026-11-17')
 path.write_text(json.dumps(doc));before=path.read_bytes()
 result=verify_refresh(tmp_path,not_before=now-timedelta(minutes=2),now=now)
 assert result['status']=='READY_FOR_FULL'
 assert all(x['not_live'] for x in result['source_assessments']['us_futures'])
 assert all(x['state']=='POST_CLOSE_SESSION_BREAK_REFERENCE' for x in result['source_assessments']['rates_commodities'])
 assert path.read_bytes()==before
