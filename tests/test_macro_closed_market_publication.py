"""Closed-market limitations stay visible without excusing genuine failures."""
from pathlib import Path
import pytest
from contracts.macro_health import health_exit_code

@pytest.mark.parametrize('health,schema,expected',[
    ({'status':'AVAILABLE_WITH_LIMITATIONS','warnings':['CLOSED_MARKET_INPUT_LIMITATIONS'],'blocking_issues':[]},True,0),
    ({'status':'DEGRADED','blocking_issues':['FUTURES_MISSING']},True,2),
    ({'status':'AVAILABLE_WITH_LIMITATIONS','blocking_issues':['MARKET_REFRESH_COLLECTION_ERRORS']},True,2),
    ({'status':'AVAILABLE_WITH_LIMITATIONS','blocking_issues':[]},False,1),
    ({'status':'UNASSESSED'},True,2),
])
def test_publication_never_confuses_limitations_with_failed_safeguards(health,schema,expected):
    assert health_exit_code(health,schema_valid=schema)==expected

def test_builder_uses_health_exit_code_and_preserves_explicit_consumption_state():
    text=(Path(__file__).resolve().parents[1]/'build_macro_json.py').read_text(encoding='utf-8')
    assert "return health_exit_code(macro_json['macro_health'], schema_valid=all_pass)" in text
    assert '"COMPLETE_WITH_LIMITATIONS" if macro_json["macro_health"].get("warnings")' in text
