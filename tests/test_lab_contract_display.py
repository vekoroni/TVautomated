"""Contract identity and DTE are exact saved references, never a wall-clock countdown."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contracts.lab_contract_display import saved_contract_details
from contracts.lab_review_projection import publish_review_projection,read_review_rows,read_review_card


def test_saved_exact_put_and_reference():
    fields=dict(contract_symbol='IONQ270115P00035000',expiry='2027-01-15',dte=87,
                contract_dte=61,selected_quote_timestamp_utc='2026-10-20T14:03:29Z')
    original=fields.copy(); d=saved_contract_details(fields)
    assert fields==original
    assert d['strike']==35 and d['call_put']=='Put' and d['expiry']=='2027-01-15'
    assert d['calendar_dte']==87 and d['trading_sessions_remaining']==60
    assert d['saved_trading_sessions_remaining']==61
    assert d['saved_reference_date']=='2026-10-20'
    assert d['issues']==['SAVED_TRADING_DTE_DIFFERS_FROM_EXACT_XNYS_COUNT'] and not d['live_countdown']


def test_exact_fractional_strike_and_zero_dte():
    d=saved_contract_details(dict(contract_symbol='BRK.B261020C00422500',dte=0,contract_dte=0))
    assert d['strike']==422.5 and d['call_put']=='Call'
    assert d['calendar_dte']==0 and d['trading_sessions_remaining']==0
    assert d['saved_reference_date']=='2026-10-20'
    assert d['reference_basis'].startswith('Derived from saved')


def test_quote_date_cannot_silently_relabel_an_older_dte():
    d=saved_contract_details(dict(contract_symbol='AAA270115C00100000',dte=88,
                                 selected_quote_timestamp_utc='2026-10-20T14:00:00Z'))
    assert d['saved_reference_date']=='2026-10-19'
    assert 'DTE_REFERENCE_DIFFERS_FROM_QUOTE_DATE' in d['issues']
    assert d['saved_quote_timestamp']=='2026-10-20T14:00:00Z'


@pytest.mark.parametrize('value',[None,'',True,'nan','bad',-1])
def test_missing_invalid_dte_not_invented(value):
    d=saved_contract_details(dict(contract_symbol='AAA270115C00100000',dte=value,contract_dte=value))
    assert d['calendar_dte'] is None and d['trading_sessions_remaining'] is None
    assert d['saved_reference_date'] is None


def test_saved_identity_conflicts_explicit():
    d=saved_contract_details(dict(contract_symbol='AAA270115C00100000',expiry='2027-01-16',strike=101))
    assert d['state']=='IDENTITY_CONFLICT'
    assert set(d['issues'])=={'SAVED_EXPIRY_CONFLICTS_WITH_OCC','SAVED_STRIKE_CONFLICTS_WITH_OCC'}


def test_malformed_symbol_not_guessed():
    d=saved_contract_details(dict(contract_symbol='unknown'))
    assert d['strike'] is None and d['call_put'] is None and d['expiry'] is None
    assert d['state']=='INCOMPLETE'


def test_card_read_adds_display_without_republishing_source(tmp_path):
    row=dict(ticker='BILI',contract_symbol='BILI270115P00015000',expiry='2027-01-15',dte=87,
             contract_dte=61,selected_quote_timestamp_utc='2026-10-20T14:00:00Z')
    m=publish_review_projection(dict(run_id='TEST',candidate_count=1,rows=[row]),tmp_path)
    manifest=tmp_path/'TEST/intelligence_lab/review_projection/manifest.json'
    before=manifest.read_bytes()
    key=read_review_rows(tmp_path,'TEST')['rows'][0]['row_key']
    c=read_review_card(tmp_path,'TEST',key,m['revision'])
    assert c['contract_details']['strike']==15
    assert c['contract_details']['trading_sessions_remaining']==60
    assert c['fields']['contract_dte']==61  # original saved numeric fact is preserved
    assert c['fields']['dte']==87 and manifest.read_bytes()==before
