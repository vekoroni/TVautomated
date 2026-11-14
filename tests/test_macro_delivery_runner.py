"""Runner wiring and its real offline delivery CLI; no provider/model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(shutil.which('powershell.exe') is None,reason='Windows PowerShell required')
def test_research_only_plan_contains_no_paid_producers():
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Run-MacroInputs.ps1'),
        '-PlanOnly','-Session','PreOpen','-ResearchDeliveryOnly','-NowET','2026-10-22 07:00'],capture_output=True,text=True,timeout=90,cwd=ROOT)
    assert result.returncode==0,result.stderr
    assert 'Macro research JSON delivery' in result.stdout
    assert 'VIX engine v4.1' not in result.stdout
    assert 'Macro packet (build_macro_json)' not in result.stdout
    assert 'ETF macro board' not in result.stdout

def test_cli_reports_missing_source_as_degraded_and_writes_no_model_output(tmp_path):
    (tmp_path/'config').mkdir()
    shutil.copyfile(ROOT/'config/macro_delivery_v1.json',tmp_path/'config/macro_delivery_v1.json')
    result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/sync_macro_feeds.py'),'--root',str(tmp_path)],
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==2,result.stderr
    receipt=json.loads((tmp_path/'data/macro/delivery/latest_receipt.json').read_text())
    assert receipt['status']=='WAITING_FOR_MANIFEST'
    overlay=json.loads((tmp_path/'dropbox/macro/macro_advisory_latest.json').read_text())
    assert overlay['authority']=='ADVISORY_ONLY'
    assert not (tmp_path/'dropbox/macro/macro_intelligence_latest.json').exists()
