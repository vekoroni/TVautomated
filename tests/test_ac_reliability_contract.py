"""Reliability disclosures cannot invent evidence or grant trading authority."""
from copy import deepcopy
import math
from datetime import date
import pytest


def test_missing_routing_in_partial_usmi_is_not_neutral():
    from macro_domain.us_money_index import sector_advisory
    p = {'quality_status': 'PARTIAL_UNVERIFIED', 'sector_routing': {'CALL': {}, 'PUT': {}}}
    r = sector_advisory(p, sector='Information Technology', direction='CALL')
    assert r['alignment'] == 'UNAVAILABLE'
    assert r['reason'] == 'USMI_ROUTING_UNASSESSED'


def test_existing_explicit_sector_route_still_works():
    from macro_domain.us_money_index import sector_advisory
    p = {'quality_status': 'PARTIAL_UNVERIFIED', 'sector_routing': {'CALL': {'TECHNOLOGY': {'alignment': 'ALIGNED', 'priority': 2}}}}
    assert sector_advisory(p, sector='Information Technology', direction='CALL')['alignment'] == 'ALIGNED'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1])
def test_nonfinite_or_negative_model_value_is_not_a_return(value):
    from domain.option_valuation import return_on_premium
    assert return_on_premium(value, bid=.9, ask=1) is None


def test_calendar_valuation_uses_exact_holiday_adjusted_exit():
    from domain.anticipated_move import anticipated_move_fields
    r = anticipated_move_fields(direction='CALL', spot=100, outcome_level=110,
        outcome_definition='level', timeframe='1d',
        duration={'status':'IN_SAMPLE_REPLAY_NOT_VALIDATED','q50_bars':2,'q80_bars':3,'n':100},
        vol_annual=.3, contract={'strike':100,'ask':3,'bid':2.8,'iv':.3,
        'expiry':'2026-12-18','as_of':'2026-11-25','underlying':'ABC'},
        governed_window_sessions=3, trade_side_event=True)
    assert r['scenario_exit_date'] == '2026-11-30'
    assert r['valuation_time_basis'] == 'EXACT_XNYS_EXIT_TO_CALENDAR_EXPIRY'


def test_reliability_contract_preserves_decision_and_labels_catalyst_type():
    from contracts.handoff_reliability import reliability_fields
    row={'ticker':'HG','contract_symbol':'HG261218C00035000','verdict':'BLOCK',
         'contract_repair_resolved_at_open':'TRUE','contract_repair_required':'TRUE',
         'execution_viability_state':'EXECUTABLE_QUOTE','anticipated_evidence_status':'IN_SAMPLE_REPLAY_NOT_VALIDATED',
         'anticipated_evidence_n':100,'bar_data_asof':'2026-11-11',
         'anticipated_valued_at_utc':'2026-11-12T14:45:00Z',
         'catalyst_type':'STRUCTURAL','catalyst_date':'2027-02-18',
         'earnings_date':'2027-02-18','earnings_source':'catalyst_truth, type STRUCTURAL'}
    before=deepcopy(row); out=reliability_fields(row)
    assert row==before and 'verdict' not in out
    assert out['contract_repair_current_state']=='RESOLVED_FOR_SELECTED_CONTRACT'
    assert out['handoff_earnings_state']=='UNVERIFIED_GENERIC_CATALYST'
    assert out['handoff_verified_earnings_date'] is None
    assert out['handoff_duration_status']=='IN_SAMPLE_REPLAY_NOT_VALIDATED'
    assert out['contract_trading_dte_reference_date']=='2026-11-11'
    assert out['contract_calendar_dte_reference_date']=='2026-11-12'


def test_zero_bid_is_unavailable_exit_not_total_loss():
    from contracts.handoff_reliability import reliability_fields
    out=reliability_fields({'contract_bid':0,'contract_ask':1.15})
    assert out['quote_exit_state']=='NO_OBSERVED_EXECUTABLE_BID'


def test_remaining_hold_is_saved_not_live_and_no_clock_restart():
    from domain.trade_timing import remaining_hold
    assert remaining_hold(52,'2026-11-11','2026-11-12T14:45:00Z')['remaining_hold_sessions']==52
    assert remaining_hold(52,'2026-11-11','2026-11-12T21:01:00Z')['remaining_hold_sessions']==51


def test_exit_rules_use_saved_clock_not_today():
    from scripts.exit_rules_engine import compute_exit_rules
    row={'canonical_direction':'CALL','expiry':'2026-12-18','anticipated_level':110,
         'anticipated_valued_at_utc':'2026-11-12T14:45:00Z','contract_theta':-.1,'contract_mid':2}
    r=compute_exit_rules(row)
    assert r['exit_clock_as_of']=='2026-11-12'
    assert r['exit_theta_date']=='2026-11-22'
    assert r['exit_target_basis']=='ANTICIPATED_LEVEL_REFERENCE_NOT_Q50_SCENARIO'


def test_exit_rules_missing_clock_is_explicit_unknown():
    from scripts.exit_rules_engine import compute_exit_rules
    r=compute_exit_rules({'canonical_direction':'CALL','expiry':'2026-12-18','contract_theta':-.1,'contract_mid':2})
    assert r['exit_theta_date'] is None
    assert r['exit_clock_state']=='REFERENCE_NOT_RECORDED'


def test_export_preserves_duration_status_and_catalyst_type(tmp_path):
    import csv, json
    from scripts.export_claude_evidence_handoff import build_saved_handoff
    run=tmp_path/'20261111_231951'; run.mkdir()
    p=run/'forecast/behavioural_candidate_packet_v1/candidates.csv';p.parent.mkdir(parents=True)
    with p.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['Ticker','Thesis_ID','Duration_Level_Status','Duration_Level_N','Timeframe'])
        writer.writeheader();writer.writerow({'Ticker':'NAN','Thesis_ID':'TH1','Duration_Level_Status':'NO_COMPARABLE_EVIDENCE','Duration_Level_N':0,'Timeframe':'60m'})
    p=run/'catalysts/catalyst_truth_20261111_231951.csv';p.parent.mkdir()
    p.write_text('ticker,catalyst_type,catalyst_date\nNAN,STRUCTURAL,2027-02-18\n')
    first=build_saved_handoff(run);second=build_saved_handoff(run)
    assert first==second
    assert first['pre_option_candidates'][0]['values']['Ticker']=='NAN'
    assert first['pre_option_candidates'][0]['values']['Duration_Level_Status']=='NO_COMPARABLE_EVIDENCE'
    assert first['typed_catalysts'][0]['catalyst_type']=='STRUCTURAL'
    assert first['state']=='PARTIAL_MISSING_SOURCES'
    assert all('sha256' in r for r in first['source_receipts'] if r['state']=='SAVED')


def test_projection_exposes_reliability_without_changing_verdict(tmp_path):
    # API is verified separately in projection tests; new fields must be part
    # of the immutable schema, not an on-GET recalculation.
    from contracts.lab_review_projection import CARD_FIELDS
    assert 'handoff_duration_status' in CARD_FIELDS
    assert 'contract_repair_current_state' in CARD_FIELDS
    assert 'scenario_exit_date' in CARD_FIELDS


def test_previous_publication_schema_remains_readable(tmp_path, monkeypatch):
    import contracts.lab_review_projection as p
    current=p.CARD_FIELDS
    with monkeypatch.context() as old:
        old.setattr(p,'CARD_FIELDS',('ticker','lab_verdict','contract_symbol'))
        manifest=p.publish_review_projection({'run_id':'OLD','candidate_count':1,'rows':[{'ticker':'ABC','lab_verdict':'BLOCKED','contract_symbol':'ABC261218C00100000'}]},tmp_path)
    assert p.CARD_FIELDS==current
    summary=p.read_review_rows(tmp_path,'OLD')
    key=summary['rows'][0]['row_key']
    card=p.read_review_card(tmp_path,'OLD',key)
    assert card['fields']['lab_verdict']=='BLOCKED'
    assert 'handoff_duration_status' not in card['fields']


def test_nonphysical_source_reach_is_not_shown_as_a_price(tmp_path):
    import contracts.lab_review_projection as p
    row={'ticker':'ABC','lab_verdict':'BLOCKED','anticipated_reachable_level':-5}
    manifest=p.publish_review_projection({'run_id':'BAD_REACH','candidate_count':1,'rows':[row]},tmp_path)
    key=p.read_review_rows(tmp_path,'BAD_REACH')['rows'][0]['row_key']
    fields=p.read_review_card(tmp_path,'BAD_REACH',key)['fields']
    assert fields['anticipated_reachable_level'] is None
    assert fields['anticipated_reach_state']=='UNASSESSED_NONPHYSICAL_SOURCE_REFERENCE'
    assert row['anticipated_reachable_level']==-5
