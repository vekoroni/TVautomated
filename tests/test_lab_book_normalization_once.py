"""Book materialisation must normalize once with byte-equivalent field values."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contracts import lab_control

def test_normalization_is_once_and_preserves_all_published_fields(monkeypatch):
    original=lab_control.csv_safe_row;seen=[]
    def capture(row):
        seen.append(dict(row));return original(row)
    monkeypatch.setattr(lab_control,'csv_safe_row',capture)
    result=lab_control.opportunity_book_row({'ticker':'ABC','direction':'CALL',
        'anticipated_contract_basis':'MORNING_REPRICED:ABC','anticipated_value_multiple_q50':1.2,
        'valuation_cost_basis':'TEST','contract_ask':float('nan')},'TEST',1)
    assert len(seen)==1
    expected={k:original(seen[0]).get(k,'') for k in lab_control.FINAL_BOOK_FIELDS}
    assert result==expected
