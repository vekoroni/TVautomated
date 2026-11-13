"""Elapsed time alone is not complete quote evidence; saved-only fixtures."""
from pathlib import Path
import importlib.util
import sys
import pytest

SCRIPTS=Path(__file__).parents[1]/'dropbox/macro/coaching/model/scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('research_path_complete_test',SCRIPTS/'score_decisions.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
CAL=['2026-10-12','2026-10-13','2026-10-14','2026-10-15','2026-10-16','2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23','2026-10-26']

def quote():
    return dict(bid=1.,ask=1.2,oi=100,volume=10,iv=.2,delta=.4,updated_date=None,source='chain_snapshots')

@pytest.mark.parametrize('case,complete',[('all_valid',1),('missing_day',0),('zero_bid',0),('missing_ask',0),('crossed',0),('nonfinite',0),('rounded_zero',0),('missing_entry',0),('invalid_entry',0),('not_mature',0)])
def test_complete_requires_entry_and_ten_valid_post_entry_session_quotes(monkeypatch,case,complete):
    quotes={day:quote() for day in CAL};calendar=CAL
    if case=='missing_day':quotes.pop(CAL[4])
    if case=='zero_bid':quotes[CAL[4]]['bid']=0
    if case=='missing_ask':quotes[CAL[4]]['ask']=None
    if case=='crossed':quotes[CAL[4]]['bid']=2
    if case=='nonfinite':quotes[CAL[4]]['ask']=float('inf')
    if case=='rounded_zero':quotes[CAL[4]].update(bid=.000001,ask=.000002)
    if case=='missing_entry':quotes.pop(CAL[0])
    if case=='invalid_entry':quotes[CAL[0]]['bid']=0
    if case=='not_mature':calendar=CAL[:6]
    monkeypatch.setattr(s,'quotes_for',lambda *a:(quotes,set(quotes)))
    ev={'event_id':'fixture','ticker':'AAL','decision_session':CAL[0],'contract_scored':'AAL270115C00012000'}
    _,entry=s.score_option(ev,None,calendar,{d:i for i,d in enumerate(calendar)})
    assert entry['path_complete']==complete
    assert entry['path_sessions_elapsed']==len(calendar)-1
    if case in ('missing_day','zero_bid','missing_ask','crossed','nonfinite','rounded_zero'):assert entry['path_sessions_quoted']==9


def test_exit_payoffs_are_unchanged_by_completeness_flag(monkeypatch):
    quotes={d:quote() for d in CAL};quotes[CAL[4]]['bid']=0
    monkeypatch.setattr(s,'quotes_for',lambda *a:(quotes,set(quotes)))
    ev={'event_id':'fixture','ticker':'AAL','decision_session':CAL[0],'contract_scored':'AAL270115C00012000'}
    rows,entry=s.score_option(ev,None,CAL,{d:i for i,d in enumerate(CAL)})
    assert entry['path_complete']==0
    assert all(r['opt_status']=='SCORED' for r in rows)
    assert all(r['opt_ret_mid']==0 for r in rows)
    assert all(r['opt_ret_ask_bid']==-16.67 for r in rows)
