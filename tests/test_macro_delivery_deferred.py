"""Exercise only extracted runner functions and a fake producer, never the pipeline."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
SHELL=shutil.which('pwsh') or shutil.which('powershell.exe')

@pytest.mark.skipif(not SHELL,reason='PowerShell required')
@pytest.mark.parametrize('marker,code,key,status',[
    ('DELIVERY_WRITER_BUSY',1,'research_delivery','DEFERRED'),
    ('writer already locked',1,'research_delivery','DEFERRED'),
    ('DEFERRED: DELIVERY_WRITER_BUSY',3,'research_delivery','DEFERRED'),
    ('provider auth failed',1,'research_delivery','FAILED'),
    ('writer already locked',1,'other_producer','FAILED'),
])
def test_delivery_lock_defers_and_next_step_continues(tmp_path,marker,code,key,status):
    dummy=tmp_path/'fake.py';dummy.write_text('# never executed')
    # AST extraction loads function definitions only, not runner setup or main.
    script=r'''
param($Runner,$Dummy,$Marker,[int]$Code,$Key)
$errors=$null;$tokens=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Runner,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Runner syntax error'}
foreach($name in @('Write-Header','Add-Result','Invoke-StepInline')){
 $f=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true) | Where-Object Name -eq $name
 Invoke-Expression $f.Extent.Text
}
$script:results=@();$script:calls=0
function Invoke-FakePython { $script:calls++;if($script:calls -eq 1){Write-Output $Marker;$global:LASTEXITCODE=$Code}else{Write-Output 'accepted inputs used';$global:LASTEXITCODE=0} }
$venvPython='Invoke-FakePython'
$step=@{Key=$Key;Name='Macro research JSON delivery';Script=$Dummy;Args=@();OkCodes=@(0,2,3)}
Invoke-StepInline $step
Invoke-StepInline @{Key='packet';Name='Fake next build';Script=$Dummy;Args=@();OkCodes=@(0)}
$failedAst=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$failed'},$true) | Select-Object -Last 1
Invoke-Expression $failedAst.Extent.Text
Write-Output ('RESULT_JSON='+(@{statuses=@($script:results.Status);failed=$failed.Count;calls=$script:calls}|ConvertTo-Json -Compress))
'''
    harness=tmp_path/'harness.ps1';harness.write_text(script)
    result=subprocess.run([SHELL,'-NoProfile','-File',str(harness),str(ROOT/'Run-MacroInputs.ps1'),str(dummy),marker,str(code),key],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    data=json.loads(next(x.split('=',1)[1] for x in result.stdout.splitlines() if x.startswith('RESULT_JSON=')))
    assert data['statuses']==[status,'OK']
    assert data['calls']==2
    assert data['failed']==(0 if status=='DEFERRED' else 1)

@pytest.mark.parametrize('receive_file',[False,True])
def test_real_delivery_cli_busy_is_deferred_without_touching_accepted_files(tmp_path,receive_file):
    (tmp_path/'config').mkdir()
    shutil.copyfile(ROOT/'config/macro_delivery_v1.json',tmp_path/'config/macro_delivery_v1.json')
    state=tmp_path/'data/macro/delivery';state.mkdir(parents=True)
    (state/'writer.lock').write_text('test owner')
    accepted=state/'accepted.json';accepted.write_text('{"sentinel":"untouched"}')
    args=[sys.executable,'-B',str(ROOT/'scripts/sync_macro_feeds.py'),'--root',str(tmp_path)]
    if receive_file:
        source=tmp_path/'original.json';source.write_text('{}')
        args+=['--receive-file',str(source),'--source-chat','producer','--source-message','message']
    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
    assert result.returncode==3,result.stdout+result.stderr
    assert 'DEFERRED' in result.stderr and 'DELIVERY_WRITER_BUSY' in result.stderr
    assert accepted.read_text()=='{"sentinel":"untouched"}'
    assert not (tmp_path/'dropbox/macro/macro_advisory_latest.json').exists()
