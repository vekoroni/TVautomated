"""Missing gamma-flip crossings must not abort a valid macro refresh."""
import importlib.util
from pathlib import Path

import pytest

PATH=Path(__file__).resolve().parents[1]/'Enhancements/colab/avshunter_macro_module_v2_8.py'
spec=importlib.util.spec_from_file_location('macro_module_null_gex_test',PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_no_crossing_loads_and_formats_without_imputing_a_flip(tmp_path):
    path=tmp_path/'gex.csv'
    path.write_text('Ticker,As_Of,Data_Status,Regime,Spot,Net_GEX_Bn,Gamma_Flip,Quality_Flags\n'
      f'SPY,{module.END_DATE}T20:00:00Z,OK,NEGATIVE,763.25,-4.665631,,NO_ZERO_GAMMA_CROSSING_IN_GRID\n')
    gex=module.load_gex(path)
    assert gex['state']=='OK'
    assert gex['gamma_flip'] is None and gex['flip_vs_spot_pct'] is None
    before=dict(gex)
    text=module.format_gex_summary(gex)
    assert 'no zero-gamma crossing in grid' in text and 'net -4.666B' in text
    assert gex==before


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),'unavailable'])
def test_optional_numbers_are_null_safe(value):
    text=module.format_gex_summary(dict(gamma_flip=value,flip_vs_spot_pct=value,net_gex_bn=value,spot=value))
    assert 'N/A' in text and 'nan' not in text and 'inf' not in text


def test_real_crossing_keeps_signed_distance():
    text=module.format_gex_summary(dict(gamma_flip=760,flip_vs_spot_pct=0.43,net_gex_bn=-4.66,spot=763.25))
    assert 'flip 760.00' in text and '(+0.43%)' in text
