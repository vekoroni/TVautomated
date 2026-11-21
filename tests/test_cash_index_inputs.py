import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('cash_repair_mi', ROOT/'Enhancements/colab/avshunter_market_intelligence_v5_4_3.py')
mi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mi)

def frame(last='2026-11-17'):
    dates = pd.date_range('2026-11-12', last, freq='B', tz='America/New_York')
    return pd.DataFrame({'Close': range(100,100+len(dates)), 'High': range(101,101+len(dates)),
                         'Low': range(99,99+len(dates)), 'Volume': 0}, index=dates)

def extract(hist):
    ticker = types.SimpleNamespace(history=lambda **kwargs: hist)
    with patch.dict(sys.modules, {'yfinance': types.SimpleNamespace(Ticker=lambda s:ticker)}), \
         patch('macro_board.market_prices.last_eligible_session', return_value=pd.Timestamp('2026-11-16').date()), \
         patch.dict('os.environ', {'AVSH_SESSION_CUTOFF':'2026-11-13'}):
        mi.TODAY_ISO='2026-11-16'
        return mi.USCashIndicesExtractor().extract()['US_Indices_Cash']

def test_excludes_partial_and_future_sessions_without_using_etf_proxies():
    result=extract(frame())
    assert set(result.ticker)=={'GSPC','NDX','RUT','DJI'}
    assert set(result.obs_date)=={'2026-11-13'}
    assert set(result.current_price)=={101}
    assert set(result.source)=={'YFINANCE'}
    assert set(result.data_status)=={'OK'}

def test_stale_history_is_explicit_failure():
    result=extract(frame('2026-11-12'))
    assert result.current_price.isna().all()
    assert set(result.data_status)=={'EXCEPTION'}

def test_duplicate_labels_are_rejected():
    hist=frame()
    result=extract(pd.concat([hist,hist.iloc[[0]]]))
    assert result.current_price.isna().all()
