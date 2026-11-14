"""Business acceptance for the delivered three-feed incident, isolated from live writers."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.us_money_index_contract import normalise_us_money_index_sidecar

def test_delivered_usmi_keeps_uncertain_flag_unknown_and_preserves_source():
    raw = json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/usmi.json').read_text(encoding='utf-8'))
    before = copy.deepcopy(raw)
    packet = normalise_us_money_index_sidecar(raw)
    assert packet['state']['risk_off_transition'] is None
    assert packet['state']['risk_off_transition_basis'] == 'UNRESOLVED_PRODUCER_DESCRIPTION'
    assert packet['source_payload'] == before == raw
    assert packet['execution_permission'] == 'NONE_INTELLIGENCE_ONLY'
    assert packet['quality_issues']
    assert packet['scenarios'] == raw['forward_triggers']['scenarios']

def test_historical_contradictions_cannot_strengthen_active_leadership():
    from contracts.macro_enrichment_delta import validate_macro_enrichment_delta
    news = json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/news.json').read_text(encoding='utf-8'))
    base = json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/macro.json').read_text(encoding='utf-8'))
    result = validate_macro_enrichment_delta(news, base)
    assert result.valid
    assert 'STRENGTHENS_EXISTING_TECH_LEADERSHIP' not in result.theme_relationships.values()

def test_zero_fred_and_rejected_usmi_are_degraded_even_with_valid_schema():
    from contracts.macro_health import assess_macro_health
    health = assess_macro_health({'extras': {'us_money_index_status': {'status': 'INVALID_UNAVAILABLE'}}},
                                report={'data_quality': {'fred_series_retrieved': 0}})
    assert health['status'] == 'DEGRADED'
    assert {'FRED_NO_COVERAGE', 'USMI_REJECTED'} <= set(health['issues'])

def test_future_observation_is_not_fresh():
    from contracts.macro_health import timestamp_health
    from datetime import datetime, timezone
    assert timestamp_health('2099-01-01T00:00:00Z', datetime(2026,10,22,tzinfo=timezone.utc)) == 'FUTURE_TIMESTAMP'

def test_bond_fallback_cannot_relabel_old_curve_as_new(tmp_path, monkeypatch):
    import bond_macro_intelligence as bond
    monkeypatch.setattr(bond, 'fetch_fred_series', lambda *args, **kwargs: None)
    monkeypatch.setattr(bond, 'DEFAULT_OUTPUT_PATH', str(tmp_path/'bond_macro_state.json'))
    (tmp_path/'macro_intelligence_latest.json').write_text(json.dumps({
        'report_date':'2026-10-21','extras':{'rates':{'t2y':4.74,'t10y':5.09}}}))
    result=bond.get_yield_curve_state()
    assert result['as_of_date'] is None
    assert result['stale_flag'] is True
    assert result['data_quality']=='FALLBACK_OBSERVATION_DATE_UNVERIFIED'
    assert result['fallback_report_date']=='2026-10-21'

def test_board_rejects_future_dated_freshness():
    from macro_board.sources import freshness
    from datetime import datetime, timezone
    assert freshness('2099-01-01T00:00:00Z', datetime(2026,10,22,tzinfo=timezone.utc),30)[0]=='FUTURE_TIMESTAMP'

def test_current_contradictions_survive_compact_reader_without_old_active_themes():
    from pipeline_interpreter.news_macro_readers import read_enrichment_delta
    text=read_enrichment_delta(str(ROOT/'tests/fixtures/macro_delivery_20261022/news.json'))
    assert 'credit_transmission:' in text
    assert 'confirmation_dashboard:' in text
    assert 'historical_theme_count: 16' in text
    assert 'WEEKEND_THEME_1_2026_10_17' not in text

def test_independent_schema_errors_are_reported_together():
    from contracts.us_money_index_contract import validate_us_money_index_packet
    raw=json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/usmi.json').read_text(encoding='utf-8'))
    raw['current_state']['risk_off_transition']='MAYBE_LATER'
    raw['cross_asset']['equities']['current_global_session']=[]
    result=validate_us_money_index_packet(raw)
    assert result['valid'] is False
    assert len(result['errors'])>=2
    assert any('risk_off_transition' in e for e in result['errors'])
    assert any('current_global_session' in e for e in result['errors'])

def test_rev57_descriptive_risk_state_is_preserved_without_boolean_promotion():
    raw=json.loads((ROOT/'tests/fixtures/macro_delivery_20261022/usmi.json').read_text(encoding='utf-8'))
    raw['current_state']['risk_off_transition']='RISK_OFF_TRANSITION_ELEVATED_84OF100_VOLATILITY_18_SECOND_GATE'
    packet=normalise_us_money_index_sidecar(raw)
    assert packet['state']['risk_off_transition'] is None
    assert packet['state']['risk_off_transition_basis']=='UNRESOLVED_PRODUCER_DESCRIPTION'
    assert packet['source_payload']['current_state']==raw['current_state']

def test_usmi_exact_download_identity_survives_attachment(tmp_path):
    import hashlib
    from contracts.us_money_index_contract import load_us_money_index_sidecar, attach_us_money_index
    original=(ROOT/'tests/fixtures/macro_delivery_20261022/usmi.json').read_bytes()
    path=tmp_path/'usmi.json';path.write_bytes(original)
    packet=load_us_money_index_sidecar(path)
    macro=attach_us_money_index({},packet)
    receipt=macro['extras']['research_source_manifest']['usmi']
    assert receipt['sha256']==hashlib.sha256(original).hexdigest()
    assert receipt['packet_revision']==51

