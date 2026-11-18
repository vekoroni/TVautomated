"""Offline scheduler foundation: no providers, live budget writes or builds."""
import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import pytest
from scripts import scheduled_macro_builds as scheduler
from contracts import macro_build_budget as budget

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,18,14,5,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('No providers'))
    for name in ('AVSH_FULL_BUILD_ID','AVSH_BUILD_REASON','AVSH_BUILD_FINGERPRINT','AVSH_BUILD_OWNER'):
        monkeypatch.delenv(name,raising=False)


@pytest.fixture
def root(tmp_path):
    (tmp_path/'config').mkdir()
    policy=json.loads((ROOT/'config/macro_build_schedule_v1.json').read_bytes())
    (tmp_path/'config/macro_build_schedule_v1.json').write_text(json.dumps(policy))
    (tmp_path/'config/macro_delivery_v1.json').write_text(json.dumps({'publication_mode':'FULL'}))
    return tmp_path


@pytest.mark.parametrize('stamp,reason',[
    ('2026-11-18T14:05:00Z','PRE_OPEN'),('2026-11-18T14:15:00Z','SKIP'),
    ('2026-11-18T21:30:00Z','POST_CLOSE'),('2026-11-18T22:30:00Z','SKIP'),
    ('2026-11-27T18:30:00Z','POST_CLOSE'),('2026-11-26T14:05:00Z','SKIP'),
    ('2026-11-21T14:05:00Z','SKIP'),('2026-11-16T14:05:00Z','SKIP'),
])
def test_current_schedule_and_calendar(stamp,reason):
    policy=json.loads((ROOT/'config/macro_build_schedule_v1.json').read_bytes())
    assert scheduler.decide(datetime.fromisoformat(stamp.replace('Z','+00:00')),policy)[0]==reason


def test_intraday_requires_real_fresh_observations_or_changed_research():
    p=json.loads((ROOT/'config/macro_build_schedule_v1.json').read_bytes())
    now=datetime(2026,11,18,15,tzinfo=timezone.utc)
    assert scheduler.decide(now,p,moved_etfs=2,cash_observed_at=now-timedelta(minutes=10))[0]=='OPEN_CHECK'
    assert scheduler.decide(now,p,moved_etfs=2,cash_observed_at=now-timedelta(hours=2))[0]=='SKIP'
    assert scheduler.decide(now,p,changed_sources=True)[0]=='MATERIAL_CHANGE'


@pytest.mark.parametrize('code,stdout,blocked',[(0,'',False),(0,'123\n',True),(1,'',True)])
def test_writer_probe_keeps_fail_closed_behaviour(root,monkeypatch,capsys,code,stdout,blocked):
    monkeypatch.setattr(scheduler,'ROOT',root)
    monkeypatch.setattr(sys,'argv',['scheduler','--execute'])
    monkeypatch.setattr(scheduler,'observations',lambda *a,**k:(False,0,None,{}))
    monkeypatch.setattr(scheduler,'decide',lambda *a,**k:('SKIP','fixture'))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,18,10,tzinfo=timezone.utc)
    monkeypatch.setattr(scheduler,'datetime',Clock)
    calls=[]
    monkeypatch.setattr(subprocess,'run',lambda cmd,**kw:(calls.append((cmd,kw)) or SimpleNamespace(returncode=code,stdout=stdout)))
    for name in ('reserve','budget_status','build_fingerprint','finish_attempt'):
        monkeypatch.setattr(scheduler,name,lambda *a,**k:pytest.fail('SKIP/defer must not reserve or build'))
    assert scheduler.main()==0 and len(calls)==1
    cmd,kw=calls[0]
    assert cmd[:3]==['powershell.exe','-NoProfile','-Command']
    assert kw['capture_output'] and kw['text']
    assert ('DEFERRED' in capsys.readouterr().out)==blocked


def test_preflight_is_not_a_paid_build_and_status_is_read_only(root):
    assert budget.budget_status(root,'2026-11-18')['paid_attempts']==0
    assert not budget._path(root).exists()
    for i in range(6):budget.reserve(root,reason='POST_CLOSE',key=str(i),now=NOW)
    status=budget.budget_status(root,'2026-11-18')
    assert status['paid_attempts']==0 and status['preflight_only_reservations']==6


def test_paid_stages_share_one_attempt_and_preserve_failed_charges(root,monkeypatch):
    token=budget.reserve(root,reason='POST_CLOSE',key='first',now=NOW)
    monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
    budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)
    budget.authorize_stage(root,'BOARD_NARRATIVE',now=NOW)
    assert budget.budget_status(root,'2026-11-18')['paid_attempts']==1
    assert budget.finish_attempt(root,token,1,now=NOW)=='FAILED_PAID_STAGE'
    assert budget.budget_status(root,'2026-11-18')['paid_attempts']==1
    with pytest.raises(ValueError,match='ALREADY_FINISHED'):budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)


def test_five_preflights_cannot_overcommit_four_paid_builds(root,monkeypatch):
    tokens=[budget.reserve(root,reason='POST_CLOSE',key=str(i),now=NOW) for i in range(5)]
    for token in tokens[:4]:
        monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
        budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)
    monkeypatch.setenv('AVSH_FULL_BUILD_ID',tokens[4])
    with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)


def test_one_daily_slot_is_preserved_for_postclose(root,monkeypatch):
    for i in range(3):
        monkeypatch.delenv('AVSH_FULL_BUILD_ID',raising=False)
        token=budget.reserve(root,reason='PRE_OPEN',key=str(i),now=NOW)
        monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
        budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)
    with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):budget.reserve(root,reason='PRE_OPEN',key='fourth',now=NOW)
    assert budget.reserve(root,reason='POST_CLOSE',key='protected',now=NOW)


def test_two_intraday_cap_same_input_and_wrong_day_guards(root,monkeypatch):
    for i in range(2):
        token=budget.reserve(root,reason='MATERIAL_CHANGE',key=str(i),now=NOW)
        monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
        budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)
    with pytest.raises(ValueError,match='INTRADAY_BUILD_LIMIT'):budget.reserve(root,reason='OPEN_CHECK',key='third',now=NOW)
    token=budget.reserve(root,reason='POST_CLOSE',key='same',now=NOW)
    with pytest.raises(ValueError,match='BUILD_ALREADY_ATTEMPTED'):budget.reserve(root,reason='POST_CLOSE',key='same',now=NOW)
    with pytest.raises(ValueError,match='previous-day'):budget.reserve(root,reason='POST_CLOSE',key='next',inherited=token,now=NOW+timedelta(days=1))


def test_fingerprint_does_not_change_for_capture_clock_alone(root):
    folder=root/'dropbox/market_data';folder.mkdir(parents=True)
    p=folder/'overnight_20261118_090000.json'
    p.write_text(json.dumps({'as_of_utc':'first','groups':{'fx':[{'last':1.1}]}}))
    first=budget.build_fingerprint(root,'PRE_OPEN','2026-11-18')
    p.write_text(json.dumps({'as_of_utc':'second','groups':{'fx':[{'last':1.1}]}}))
    assert budget.build_fingerprint(root,'PRE_OPEN','2026-11-18')==first
    p.write_text(json.dumps({'as_of_utc':'second','groups':{'fx':[{'last':1.2}]}}))
    assert budget.build_fingerprint(root,'PRE_OPEN','2026-11-18')!=first


def test_packet_refuses_budget_before_any_api_request(root,monkeypatch):
    monkeypatch.setattr(budget,'authorize_stage',lambda *a,**k:(_ for _ in ()).throw(ValueError('DAILY_FULL_BUILD_LIMIT_REACHED')))
    tree=ast.parse((ROOT/'build_macro_json.py').read_text(encoding='utf-8-sig'))
    guard=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=='not args.dry_run' and any(isinstance(x,ast.Name) and x.id=='authorize_stage' for x in ast.walk(n)))
    program=ast.fix_missing_locations(ast.Module(body=[guard],type_ignores=[]))
    with pytest.raises(SystemExit) as error:
        exec(compile(program,'offline_budget_guard','exec'),{'args':SimpleNamespace(dry_run=False),'BASE_DIR':root,'sys':sys,'log':SimpleNamespace(error=lambda *a:None)})
    assert error.value.code==7


def test_board_refuses_budget_before_client_creation(tmp_path,monkeypatch):
    from macro_board.day_story import ai_narrative
    monkeypatch.setattr(budget,'authorize_stage',lambda *a,**k:(_ for _ in ()).throw(ValueError('DAILY_FULL_BUILD_LIMIT_REACHED')))
    cfg=dict(enabled=True,model='offline',prompt_version='budget',call_on_build_kinds=['EVENING'])
    with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT_REACHED'):
        ai_narrative({},cfg,cache_dir=tmp_path,session='2026-11-18',kind='EVENING',client_factory=lambda:pytest.fail('No paid client'))


def test_full_postclose_timing_current_schedule_and_logging_contract():
    assert json.loads((ROOT/'config/macro_delivery_v1.json').read_bytes())['publication_mode']=='FULL'
    runner=(ROOT/'Run-MacroInputs.ps1').read_text(encoding='utf-8-sig')
    assert '$waitsPastGuard = (-not $forced) -and ($startAt.TimeOfDay -ge $RegularGuard) -and ($etNow -lt $startAt)' in runner
    assert 'PostClose = @{ Start = "16:30"; Latest = "23:30" }' in runner
    assert 'PreOpen   = @{ Start = "09:05"; Latest = "09:15" }' in runner
    assert 'Get-XnysSessionHours' in runner
    declaration=next(l for l in runner.splitlines() if 'foreach ($name in ' in l and 'PYTHONIOENCODING' in l)
    for n in ('AVSH_FULL_BUILD_ID','AVSH_BUILD_REASON','AVSH_BUILD_FINGERPRINT','AVSH_BUILD_OWNER'):assert n in declaration
    wrapper=(ROOT/'Run-MacroSchedule.ps1').read_text()
    assert '--execute 2>&1' in wrapper and 'Out-File -LiteralPath $logFile -Append -Encoding utf8' in wrapper


@pytest.mark.skipif(not shutil.which('powershell.exe'),reason='PowerShell AST harness required')
def test_runner_budget_refusal_stops_before_producers(tmp_path):
    harness=tmp_path/'budget-refusal.ps1'
    harness.write_text('''param($Runner)
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
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
    result=subprocess.run(['powershell.exe','-NoProfile','-File',str(harness),str(ROOT/'Run-MacroInputs.ps1')],capture_output=True,text=True,timeout=30,**options)
    assert result.returncode==7,result.stdout+result.stderr
    assert 'EXIT_CODE=7' in result.stdout
