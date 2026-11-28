"""Data-only provenance exclusions must never conceal executable source."""
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('family,prefix',[('cycles','cycle'),('forecasts','forecasts'),('outcomes','outcomes')])
def test_only_typed_runtime_json_is_ignored(family,prefix):
    def ignored(path):
        p=subprocess.run(['git','-C',str(ROOT),'check-ignore','--no-index','--',path],capture_output=True,text=True)
        assert p.returncode in (0,1),p.stderr
        return p.returncode==0
    assert ignored(f'data/phantom/shadow_profit/{family}/{prefix}-abcdef.json')
    assert not ignored(f'data/phantom/shadow_profit/{family}/{prefix}-abcdef.py')
    assert not ignored(f'data/phantom/shadow_profit/{family}/{prefix}-abcdef.ps1')
    assert not ignored(f'data/phantom/shadow_profit/{family}/{prefix}-abcdef.js')
