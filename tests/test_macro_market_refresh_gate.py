"""Saved synthetic source fixtures and AST-only runner mocks: no external calls."""
import copy
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from contracts.macro_market_refresh_gate import GROUPS, verify_refresh

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 16, 9, 20, tzinfo=timezone.utc)
START = NOW - timedelta(minutes=2)


def saved_snapshot(directory):
    parent = directory/'overnight_20261116_080000.json'
    parent.write_bytes(b'{"original":"preserved"}')
    def row(symbol):
        return dict(symbol=symbol, state='OK', last=100., stale=False,
                    last_bar_utc='2026-11-16T09:15:00Z')
    groups = {
        'us_futures': [row(s) for s in ('ES=F','NQ=F','YM=F','RTY=F')],
        'rates_commodities': [row(s) for s in ('ZN=F','CL=F','GC=F')],
        'fx': [row('EURUSD=X')], 'volatility': [row('VIX')],
        'us_premarket': [row('SPY')], 'asia': [row('^N225')],
        'europe': [row('^FTSE')],
    }
    # A current completed regional session is valid, not a pretend live quote.
    groups['asia'][0].update(state='CLOSED', session_date='2026-11-16',
        exchange_tz='Asia/Tokyo', last_bar_utc='2026-11-16T06:30:00Z')
    stamp = (NOW-timedelta(minutes=1)).isoformat()
    doc = dict(as_of_utc=stamp, groups=groups,
        market_refresh=dict(as_of_utc=stamp, errors=[], groups_refetched=list(GROUPS)),
        futures_refresh=dict(errors=[], parent_file=parent.name,
                             parent_sha256=hashlib.sha256(parent.read_bytes()).hexdigest()))
    path = directory/'overnight_20261116_091900.json'
    path.write_text(json.dumps(doc))
    return path, doc


def test_verified_current_refresh_is_read_only_and_keeps_closed_session_dates(tmp_path):
    path, doc = saved_snapshot(tmp_path)
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result = verify_refresh(tmp_path, not_before=START, now=NOW)
    assert result['status']=='READY_FOR_FULL'
    assert all(v=='AVAILABLE' for v in result['groups'].values())
    assert result['snapshot_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before
    assert doc['groups']['asia'][0]['last_bar_utc']=='2026-11-16T06:30:00Z'


@pytest.mark.parametrize('case,marker',[
    ('prior_run','CURRENT_RUN_MARKET_REFRESH_NOT_PROVEN'),
    ('future_capture','CURRENT_RUN_MARKET_REFRESH_NOT_PROVEN'),
    ('capture_expired','MARKET_REFRESH_CAPTURE_EXPIRED'),
    ('clock_mismatch','MARKET_REFRESH_CLOCK_MISMATCH'),
    ('collection_error','MARKET_REFRESH_COLLECTION_ERRORS'),
    ('missing_group','MARKET_REFRESH_GROUPS_INCOMPLETE'),
    ('parent_hash','MARKET_REFRESH_PARENT_HASH_MISMATCH'),
    ('old_quote','MARKET_SOURCE_NOT_READY'),
    ('missing_quote','MARKET_SOURCE_NOT_READY'),
    ('future_quote','MARKET_SOURCE_TIMESTAMP_INVALID'),
    ('no_quote_clock','MARKET_SOURCE_NOT_READY'),
])
def test_recent_fetch_cannot_hide_failed_old_incomplete_or_future_evidence(tmp_path,case,marker):
    path, doc = saved_snapshot(tmp_path)
    start = START
    if case=='prior_run': start=NOW
    elif case=='future_capture': doc['market_refresh']['as_of_utc']=(NOW+timedelta(minutes=1)).isoformat()
    elif case=='capture_expired':
        start=NOW-timedelta(hours=1)
        doc['as_of_utc']=doc['market_refresh']['as_of_utc']=(NOW-timedelta(minutes=11)).isoformat()
    elif case=='clock_mismatch': doc['as_of_utc']=START.isoformat()
    elif case=='collection_error': doc['market_refresh']['errors']=['provider unavailable']
    elif case=='missing_group': doc['market_refresh']['groups_refetched'].remove('fx')
    elif case=='parent_hash': doc['futures_refresh']['parent_sha256']='0'*64
    elif case=='old_quote': doc['groups']['fx'][0]['last_bar_utc']='2026-11-16T08:00:00Z'
    elif case=='missing_quote': doc['groups']['volatility'][0]['last']=None
    elif case=='future_quote': doc['groups']['europe'][0]['last_bar_utc']='2026-11-16T09:21:00Z'
    elif case=='no_quote_clock': doc['groups']['us_premarket'][0]['last_bar_utc']=None
    path.write_text(json.dumps(doc))
    before=path.read_bytes()
    with pytest.raises(ValueError,match=marker): verify_refresh(tmp_path,not_before=start,now=NOW)
    assert path.read_bytes()==before


def test_no_snapshot_and_naive_clock_fail_closed(tmp_path):
    with pytest.raises(ValueError,match='MISSING'): verify_refresh(tmp_path,not_before=START,now=NOW)
    with pytest.raises(ValueError,match='AWARE_CLOCK'): verify_refresh(tmp_path,not_before=START.replace(tzinfo=None),now=NOW)


SHELL = shutil.which('pwsh') or shutil.which('powershell.exe')
@pytest.mark.skipif(not SHELL,reason='PowerShell required')
@pytest.mark.parametrize('failed_key,code,calls',[
    ('none',0,['futures_refresh','market_guard','packet','board']),
    ('futures_refresh',1,['futures_refresh']),
    ('futures_refresh',127,['futures_refresh']),
    ('market_guard',1,['futures_refresh','market_guard']),
    ('packet',1,['futures_refresh','market_guard','packet']),
    ('packet',2,['futures_refresh','market_guard','packet','board']),
])
def test_real_runner_publish_control_flow_never_builds_after_failed_prerequisite(tmp_path,failed_key,code,calls):
    harness=tmp_path/'harness.ps1'
    harness.write_text(r'''
param($Runner,$FailedKey,[int]$FailureCode)
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Runner,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Runner syntax error'}
foreach($name in @('New-Step','Add-Result','Invoke-PublishSteps')){
 $f=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object Name -eq $name
 Invoke-Expression $f.Extent.Text
}
$script:results=@();$script:calls=@();$script:guardArgs=@()
function Invoke-StepInline($step){
 $script:calls+=$step.Key
 if($step.Key -eq 'market_guard'){$script:guardArgs=$step.Args}
 $exit=if($step.Key -eq $FailedKey){$FailureCode}else{0}
 Add-Result $step $exit ([TimeSpan]::Zero) 'mocked'
}
$steps=@((New-Step 'futures_refresh' 'Market snapshot + reopening refresh' 'never.py'),
 (New-Step 'market_guard' 'Current-run market freshness gate' 'never.py'),
 (New-Step 'packet' 'Macro packet' 'never.py' @() @(0,2)),
 (New-Step 'board' 'ETF board' 'never.py'))
Invoke-PublishSteps $steps $true
Write-Output ('RESULT_JSON='+(@{calls=$script:calls;guardArgs=$script:guardArgs;statuses=@($script:results.Status)}|ConvertTo-Json -Compress))
''')
    result=subprocess.run([SHELL,'-NoProfile','-File',str(harness),str(ROOT/'Run-MacroInputs.ps1'),failed_key,str(code)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    payload=json.loads(next(s.split('=',1)[1] for s in result.stdout.splitlines() if s.startswith('RESULT_JSON=')))
    assert payload['calls']==calls
    if 'market_guard' in calls:
        assert payload['guardArgs'][0]=='--not-before-utc'
        assert datetime.fromisoformat(payload['guardArgs'][1].replace('Z','+00:00')).tzinfo is not None


def test_full_and_postclose_timing_guard_are_not_changed():
    config=json.loads((ROOT/'config/macro_delivery_v1.json').read_text())
    assert config['publication_mode']=='FULL'
    runner=(ROOT/'Run-MacroInputs.ps1').read_text(encoding='utf-8-sig')
    assert '$waitsPastGuard = (-not $forced) -and ($startAt.TimeOfDay -ge $RegularGuard) -and ($etNow -lt $startAt)' in runner
    assert '-and -not $waitsPastGuard)' in runner


@pytest.mark.skipif(not SHELL,reason='PowerShell required')
@pytest.mark.parametrize('mode,expected_guard,packet',[
    ('FULL',True,'build_macro_json.py'),
    ('DATA_ONLY',False,'publish_macro_data_only.py'),
])
def test_actual_runner_step_definitions_wire_refresh_before_full_only(tmp_path,mode,expected_guard,packet):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/macro_delivery_v1.json').write_text(json.dumps({'publication_mode':mode}))
    harness=tmp_path/'plan.ps1'
    harness.write_text(r'''
param($Runner,$Root)
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Runner,[ref]$tokens,[ref]$errors)
$f=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object Name -eq 'New-Step'
Invoke-Expression $f.Extent.Text
$repoRoot=$Root;$colab=$Root
$text=Get-Content -LiteralPath $Runner -Raw
$begin=$text.IndexOf('# -- Steps ');$end=$text.IndexOf('# -- Plan ')
Invoke-Expression $text.Substring($begin,$end-$begin)
Write-Output ('RESULT_JSON='+(@{keys=@($publish|ForEach-Object{$_.Key});scripts=@($publish|ForEach-Object{Split-Path $_.Script -Leaf});refreshArgs=@(($publish|Where-Object Key -eq 'futures_refresh').Args)}|ConvertTo-Json -Compress))
''')
    result=subprocess.run([SHELL,'-NoProfile','-File',str(harness),str(ROOT/'Run-MacroInputs.ps1'),str(tmp_path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    payload=json.loads(next(s.split('=',1)[1] for s in result.stdout.splitlines() if s.startswith('RESULT_JSON=')))
    keys=payload['keys']
    assert keys.index('futures_refresh')<keys.index('packet')<keys.index('board')
    assert ('market_guard' in keys)==expected_guard
    if expected_guard: assert keys.index('futures_refresh')<keys.index('market_guard')<keys.index('packet')
    assert payload['scripts'][keys.index('packet')]==packet
    assert payload['refreshArgs']==['--all-market-data']


@pytest.mark.skipif(not SHELL or not (ROOT/'venv/Scripts/python.exe').exists(),reason='Windows runner environment required')
@pytest.mark.parametrize('session,clock,start',[
    ('PreOpen','2026-11-16 07:30','09:05'),
    ('PostClose','2026-11-16 16:20','16:30'),
])
def test_scheduled_preopen_and_postclose_dry_plans_include_guard_in_order(session,clock,start):
    result=subprocess.run([SHELL,'-NoProfile','-File',str(ROOT/'Run-MacroInputs.ps1'),
        '-PlanOnly','-Session',session,'-NowET',clock],capture_output=True,text=True,timeout=180,cwd=ROOT)
    assert result.returncode==0,result.stdout+result.stderr
    text=result.stdout
    assert 'nothing is run' in text and start in text
    names=['Market snapshot + reopening refresh','Current-run market freshness gate',
           'Macro packet (build_macro_json)','ETF macro board']
    positions=[text.index(name) for name in names]
    assert positions==sorted(positions)
    assert '--all-market-data' in text
