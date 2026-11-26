"""Read-only plans exercise holiday opt-in without providers or builds."""
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'Run-MacroInputs.ps1'
pytestmark=pytest.mark.skipif(not shutil.which('powershell.exe') or not (ROOT/'venv/Scripts/python.exe').exists(),reason='Windows runner and calendar required')

def plan(day,*args):
    return subprocess.run(['powershell.exe','-NoProfile','-File',str(RUNNER),'-PlanOnly','-NowET',day,*args],cwd=ROOT,capture_output=True,text=True,timeout=180)

def test_holiday_opt_in_uses_completed_session_and_non_scored_label():
    out=plan('2026-11-26 12:00','-Session','PostClose','-AllowHolidayOffSession')
    assert out.returncode==0,out.stdout+out.stderr
    for expected in ('session        : OffSession','explicitly authorised holiday','session cut-off: 2026-11-25','close 2026-11-25T21:00:00Z','off-session (not the scored evening record)','none (explicit holiday off-session - starts immediately)'):
        assert expected in out.stdout

def test_default_holiday_scheduled_run_still_skips():
    out=plan('2026-11-26 12:00','-Session','PostClose')
    assert out.returncode==0
    assert 'NO - the run would be skipped' in out.stdout
    assert 'session        : OffSession' not in out.stdout

def test_opt_in_cannot_relabel_an_open_early_close_session():
    out=plan('2026-11-27 12:00','-AllowHolidayOffSession')
    assert out.returncode==6
    assert 'calendar-confirmed XNYS non-session' in out.stdout

def test_next_day_preopen_uses_wednesday_close_without_holiday_override():
    out=plan('2026-11-27 07:00','-Session','PreOpen')
    assert out.returncode==0
    assert 'session        : PreOpen' in out.stdout
    assert 'session cut-off: 2026-11-25' in out.stdout

def test_early_close_completed_cutoff_is_actual_thirteen_et_close():
    out=plan('2026-11-27 14:00','-Session','PostClose','-Force')
    assert out.returncode==0
    assert 'session cut-off: 2026-11-27' in out.stdout
    assert 'close 2026-11-27T18:00:00Z' in out.stdout

def test_opt_in_does_not_modify_guard_or_budget_paths():
    text=RUNNER.read_text(encoding='utf-8-sig')
    assert '$waitsPastGuard = (-not $forced) -and ($startAt.TimeOfDay -ge $RegularGuard) -and ($etNow -lt $startAt)' in text
    assert 'elseif ($Session -eq "PreOpen" -or $offSession)' in text
    assert 'Get-PipelineProcesses' in text and 'reserve,build_fingerprint' in text
    assert 'Current-run market freshness gate' in text
