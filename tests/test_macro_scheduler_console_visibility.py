"""Console-only repair: mocked scheduler execution; real harmless local probes."""
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from scripts import scheduled_macro_builds as scheduler

ROOT = Path(__file__).resolve().parents[1]


def test_windows_flag_does_not_change_non_windows_launches(monkeypatch):
    monkeypatch.setattr(scheduler, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    assert scheduler.console_creation_options() == {'creationflags': 0x08000000}
    monkeypatch.setattr(scheduler, 'os', SimpleNamespace(name='posix'))
    assert scheduler.console_creation_options() == {}


def test_all_three_console_children_use_visibility_option():
    tree=ast.parse((ROOT/'scripts/scheduled_macro_builds.py').read_text(encoding='utf-8-sig'))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
           and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='run']
    assert len(calls)==3
    assert all(any(k.arg is None and isinstance(k.value,ast.Call)
                   and isinstance(k.value.func,ast.Name) and k.value.func.id=='console_creation_options'
                   for k in call.keywords) for call in calls)


@pytest.fixture
def offline_scheduler(tmp_path,monkeypatch):
    policy=json.loads((ROOT/'config/macro_build_schedule_v1.json').read_bytes())
    (tmp_path/'config').mkdir()
    (tmp_path/'config/macro_build_schedule_v1.json').write_text(json.dumps(policy))
    (tmp_path/'config/macro_delivery_v1.json').write_text(json.dumps({'publication_mode':'FULL'}))
    monkeypatch.setattr(scheduler,'ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['scheduled_macro_builds.py','--execute'])
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,18,10,tzinfo=timezone.utc)
    monkeypatch.setattr(scheduler,'datetime',Clock)
    monkeypatch.setattr(scheduler,'observations',lambda *a,**k:(False,0,None,{}))
    def forbidden(*a,**k):pytest.fail('No actual provider, paid stage or budget write')
    for name in ('reserve','budget_status','build_fingerprint','finish_attempt'):
        monkeypatch.setattr(scheduler,name,forbidden)
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)
    return tmp_path,policy


@pytest.mark.parametrize('code,output',[(0,'12345\n'),(1,''),(5,'CIM unavailable')])
def test_writer_or_inspection_failure_still_defers(offline_scheduler,monkeypatch,capsys,code,output):
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=code,stdout=output)
    monkeypatch.setattr(subprocess,'run',run)
    monkeypatch.setattr(scheduler,'decide',lambda *a,**k:('PRE_OPEN','fixture'))
    assert scheduler.main()==0
    assert len(calls)==1
    command,options=calls[0]
    assert command[:3]==['powershell.exe','-NoProfile','-Command']
    assert 'Get-CimInstance Win32_Process' in command[-1]
    for writer in ('Run-MacroInputs.ps1','build_macro_json.py','intelligent_orchestrator.py','backfill','macro_board'):
        assert writer in command[-1]
    assert options['capture_output'] and options['text']
    assert all(options[k]==v for k,v in scheduler.console_creation_options().items())
    assert 'DEFERRED: writer active or process inspection unavailable' in capsys.readouterr().out


def test_skip_still_checks_writers_without_building(offline_scheduler,monkeypatch,capsys):
    calls=[]
    monkeypatch.setattr(subprocess,'run',lambda cmd,**kw:(calls.append((cmd,kw)) or SimpleNamespace(returncode=0,stdout='')))
    monkeypatch.setattr(scheduler,'decide',lambda *a,**k:('SKIP','Outside build windows'))
    assert scheduler.main()==0 and len(calls)==1
    assert 'Outside build windows' in capsys.readouterr().out


@pytest.mark.parametrize('reason,session,code',[('PRE_OPEN','PreOpen',0),('POST_CLOSE','PostClose',7)])
def test_mocked_build_keeps_arguments_environment_exit_and_log_handles(offline_scheduler,monkeypatch,reason,session,code):
    root,_=offline_scheduler;calls=[];finished=[]
    monkeypatch.setattr(scheduler,'decide',lambda *a,**k:(reason,'fixture'))
    monkeypatch.setattr(scheduler,'budget_status',lambda *a,**k:{'completed_reasons':[],'last_paid_started':None})
    monkeypatch.setattr(scheduler,'build_fingerprint',lambda *a,**k:'fixture-hash')
    monkeypatch.setattr(scheduler,'reserve',lambda *a,**k:'fixture-token')
    monkeypatch.setattr(scheduler,'finish_attempt',lambda *a:finished.append(a))
    def run(cmd,**kw):
        calls.append((cmd,kw));return SimpleNamespace(returncode=0 if len(calls)==1 else code,stdout='')
    monkeypatch.setattr(subprocess,'run',run)
    assert scheduler.main()==code and len(calls)==2
    cmd,kw=calls[1]
    assert cmd==['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'Run-MacroInputs.ps1'),'-Session',session,'-Force']
    assert kw['cwd']==root and kw['env']['AVSH_FULL_BUILD_ID']=='fixture-token'
    assert kw['env']['AVSH_BUILD_REASON']==reason
    assert not any(k in kw for k in ('capture_output','stdout','stderr')),'Retain inherited logging handles'
    assert all(kw[k]==v for k,v in scheduler.console_creation_options().items())
    assert finished==[(root,'fixture-token',code)]


def test_mocked_opening_refresh_remains_bounded_and_once(offline_scheduler,monkeypatch):
    root,_=offline_scheduler;calls=[]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,18,15,tzinfo=timezone.utc)
    monkeypatch.setattr(scheduler,'datetime',Clock)
    monkeypatch.setattr(scheduler,'decide',lambda *a,**k:('SKIP','fixture'))
    monkeypatch.setattr(subprocess,'run',lambda cmd,**kw:(calls.append((cmd,kw)) or SimpleNamespace(returncode=0,stdout='')))
    assert scheduler.main()==0
    assert len(calls)==2
    assert calls[1][0][-1]=='--all-market-data' and calls[1][1]['timeout']==180
    assert not any(k in calls[1][1] for k in ('capture_output','stdout','stderr'))
    assert all(calls[1][1][k]==v for k,v in scheduler.console_creation_options().items())
    assert scheduler.main()==0 and len(calls)==3,'Second check probes writers but does not refresh again'
    assert (root/'data/macro/delivery/opening_quote_check_2026-11-18.json').is_file()


# ACK 20 Nov 2026: "We want to change 12pm UK" - the pre-open full build runs at 07:00 ET (12:00 UK in winter),
# 150 minutes before the open, so the board and the triage macro context are ready for the triage and deep dives.
# 09:05 ET (the previous slot) is no longer a pre-open window.
@pytest.mark.parametrize('stamp,expected',[
    ('2026-11-18T12:00:00Z','PRE_OPEN'),('2026-11-18T12:09:00Z','PRE_OPEN'),('2026-11-18T12:10:00Z','SKIP'),
    ('2026-11-18T14:05:00Z','SKIP'),('2026-11-18T21:30:00Z','POST_CLOSE'),
    ('2026-11-18T10:00:00Z','SKIP'),('2026-11-26T12:00:00Z','SKIP'),
    ('2026-11-27T18:30:00Z','POST_CLOSE'),
])
def test_schedule_decisions_unchanged(stamp,expected):
    policy=json.loads((ROOT/'config/macro_build_schedule_v1.json').read_bytes())
    assert scheduler.decide(datetime.fromisoformat(stamp.replace('Z','+00:00')),policy)[0]==expected


@pytest.mark.skipif(os.name!='nt',reason='Windows console creation probe')
def test_real_hidden_powershell_has_no_console_and_keeps_output_and_exit():
    command='''Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class ConsoleProbe { [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); }'; [Console]::Out.WriteLine('WINDOW=' + [ConsoleProbe]::GetConsoleWindow().ToInt64()); [Console]::Error.WriteLine('offline-probe-stderr'); exit 7'''
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                          capture_output=True,text=True,timeout=30,**scheduler.console_creation_options())
    assert result.returncode==7
    assert 'WINDOW=0' in result.stdout and 'offline-probe-stderr' in result.stderr


def test_real_harmless_child_preserves_file_log_stream(tmp_path):
    log=tmp_path/'scheduler-probe.log'
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-B','-c',"import sys; print('offline-stdout'); print('offline-stderr',file=sys.stderr); sys.exit(3)"],
                              stdout=stream,stderr=subprocess.STDOUT,timeout=30,**scheduler.console_creation_options())
    assert result.returncode==3
    assert 'offline-stdout' in log.read_text() and 'offline-stderr' in log.read_text()
