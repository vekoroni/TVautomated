"""Saved-only exact-session timing; no provider/pipeline imports or wall-clock estimates."""
from copy import deepcopy
import json
from datetime import date
import pytest
from domain.trade_timing import after_sessions, day, remaining_hold, sessions_between, timing_for_row
from domain.option_contract_liquidity import calculate_dte_requirement, evaluate_options_liquidity_lifecycle


@pytest.mark.parametrize('hold',[1,2,3,4,5,7,21,61,252,666])
def test_any_positive_session_hold_is_preserved(hold):
    result=timing_for_row(dict(planned_hold_sessions=hold,expiry='2030-01-18'),
                          planned_at='2026-11-11',as_of='2026-11-12T15:00:00Z')
    assert result['planned_hold_sessions']==hold
    assert result['remaining_hold_sessions']==hold  # current session not complete
    assert result['minimum_required_sessions']==hold+8
    assert result['planned_short_1_5'] is (1<=hold<=5)


def test_holidays_and_early_close_are_sessions_not_calendar_days():
    assert sessions_between(day('2026-09-04'),day('2026-09-08'))==1  # Labor Day
    assert sessions_between(day('2026-11-25'),day('2026-11-27'))==1  # Thanksgiving, early close
    assert after_sessions(day('2026-11-25'),1)==date(2026,11,27)
    assert sessions_between(day('2026-12-24'),day('2027-01-04'))==5


def test_azz_saved_calendar_conversion_was_not_enough():
    exact=calculate_dte_requirement(61,evidence_hold=True,as_of_date='2026-11-12')
    assert exact['minimum_required_sessions']==69
    assert exact['minimum_required_expiry_date']=='2027-02-24'
    assert exact['minimum_required_dte']==104
    result=timing_for_row(dict(planned_hold_sessions=61,contract_symbol='AZZ270219C00120000'),
                         planned_at='2026-11-11',as_of='2026-11-12T15:43:36Z')
    assert result['expiry_sessions_remaining']==66
    assert result['expiry_calendar_days_remaining']==99
    assert result['expiry_session_check_state']=='INSUFFICIENT_XNYS_RUNWAY'


def test_lifecycle_refuses_execution_on_exact_short_runway():
    result=evaluate_options_liquidity_lifecycle(dict(side='CALL',spot=100,strike=100,delta=.5,
        bid=3,ask=3.1,dte=99,remaining_hold_sessions=61,forecast_vol_annual=.25,
        thesis_spot=100,current_spot=101,structural_target=110,invalidation_spot=95,
        quote_age_seconds=0,as_of_date='2026-11-12',expiry_date='2027-02-19'))
    assert result['expiry_sessions_remaining']==66
    assert result['expiry_session_check_state']=='INSUFFICIENT_XNYS_RUNWAY'
    assert result['executable_now'] is False


def test_remaining_hold_ages_only_completed_sessions_not_partial_day_or_weekend():
    assert remaining_hold(3,'2026-11-25','2026-11-27T17:59:00Z')['remaining_hold_sessions']==3
    assert remaining_hold(3,'2026-11-25','2026-11-27T18:01:00Z')['remaining_hold_sessions']==2
    assert remaining_hold(3,'2026-11-25','2026-11-29')['remaining_hold_sessions']==2
    assert remaining_hold(1,'2026-11-25','2026-11-27T18:01:00Z')['hold_clock_state']=='EXHAUSTED'
    assert day('2026-11-13T00:30:00Z')==date(2026,11,12)


def test_four_clocks_never_substitute_for_each_other():
    row=dict(planned_hold_sessions=52,anticipated_sessions_q50=22,anticipated_sessions_q80=52,
             scenario_exit_sessions=22,ev3_planned_hold_sessions=20,dte=99)
    original=deepcopy(row)
    result=timing_for_row(row,planned_at='2026-11-11',as_of='2026-11-12T21:01:00Z')
    assert [result[k] for k in ('arrival_median_sessions','planned_hold_sessions','remaining_hold_sessions','valuation_horizon_sessions')]==[22,52,51,22]
    assert result['empirical_horizon_state']=='DIFFERS_FROM_PLANNED_HOLD'
    assert row==original


def test_missing_dates_and_holds_stay_explicit_not_five_or_twenty():
    result=timing_for_row(dict(dte=99,contract_dte=67))
    assert result['planned_hold_sessions'] is None
    assert result['remaining_hold_sessions'] is None
    assert result['valuation_horizon_sessions'] is None
    assert result['expiry_session_check_state']=='UNASSESSED_MISSING_DATES'


def test_morning_expired_budget_cannot_be_renewed_by_a_contract_refresh():
    import morning_gate
    row=dict(ticker='TEST',final_direction='CALL',signal_price=100,contract_strike=100,
        target_price=110,invalidation_price=95,contract_symbol='TEST261218C00100000',
        expiry='2026-12-18',dte=36,contract_dte=26,planned_hold_sessions=1,
        planned_hold_source='DURATION_EVIDENCE_Q80:1d:n=100',
        planned_hold_reference_at_utc='2026-11-10',hv_30d=.25)
    live=dict(live_price=101,live_contract_bid=3,live_contract_ask=3.1,live_contract_delta=.5,
        live_options_fetched_at='2026-11-12T21:01:00Z')
    original=deepcopy(row)
    result=morning_gate._morning_liquidity_lifecycle(row,live,contract_changed=False,economics_recompute_complete=False)
    assert result['remaining_hold_sessions']==0 and not result['executable_now']
    assert result['liquidity_lifecycle_reason']=='HOLD_BUDGET_EXHAUSTED_REQUIRES_NEW_THESIS_ASSESSMENT'
    assert row==original


def test_saved_publication_downgrades_only_display_preserving_source_and_old_generation(tmp_path):
    from contracts.lab_review_sources import prepare_review_publication
    from contracts.lab_review_projection import publish_review_projection,read_review_rows,read_review_card
    run=tmp_path/'TIMING'; run.mkdir()
    (run/'run_meta.json').write_text(json.dumps({'dynamic_plan':{'evidence_cutoff_utc':'2026-11-11T23:19:51Z'}}))
    book={'run_id':'TIMING','created_at_utc':'2026-11-12T15:43:36Z','candidate_count':1,'rows':[
        dict(ticker='AZZ',contract_symbol='AZZ270219C00120000',planned_hold_sessions=61,
             planned_hold_source='DURATION_EVIDENCE_Q80:1d:n=261',anticipated_sessions_q50=3,
             lab_verdict='GO_LIMIT',scenario_exit_sessions=3)]}
    original=deepcopy(book)
    old=publish_review_projection(book,tmp_path)
    prepared,context,receipt=prepare_review_publication(book,run)
    assert book==original
    assert prepared['rows'][0]['lab_verdict']=='MANUAL_REVIEW'
    assert prepared['rows'][0]['timing_details']['published_lab_verdict']=='GO_LIMIT'
    new=publish_review_projection(prepared,tmp_path,context=context,source_receipt=receipt)
    assert new['row_count']==1 and new['timing_summary']['arrival_1_5_count']==1
    assert (run/'intelligence_lab/review_projection'/old['database_file']).exists()
    home=read_review_rows(tmp_path,'TIMING')['rows'][0]
    card=read_review_card(tmp_path,'TIMING',home['row_key'])
    assert card['timing_details']['expiry_sessions_remaining']==66
    assert home['lab_verdict']=='MANUAL_REVIEW'
