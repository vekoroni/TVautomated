"""Offline regression: a dated exception never erases history or opens an unlimited budget."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import pytest
from contracts import macro_build_budget as budget
from contracts import macro_api_cost as cost
from contracts.macro_postclose_exception import authorization, build_authorization

R=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,18,23,30,tzinfo=timezone.utc)
OLD=datetime(2026,11,18,20,tzinfo=timezone.utc)
KEY='user-approved-single-postclose-fingerprint'


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    for name in ('macro_build_schedule_v1.json','macro_api_cost_v1.json'):
        (tmp_path/'config'/name).write_bytes((R/'config'/name).read_bytes())
    p={'day':'2026-11-18','issued_at_utc':'2026-11-18T22:00:00+00:00',
       'expires_at_utc':'2026-11-19T05:00:00+00:00','fingerprint':KEY,
       'authority':'USER_REQUEST_REMOVE_BLOCK_FOR_ONE_POST_CLOSE',
       'max_extra_full_attempts':1,'additional_request_cap_usd':1}
    (tmp_path/'config/macro_postclose_exception_v1.json').write_text(json.dumps(p))
    for i in range(4):
        token=budget.reserve(tmp_path,reason='POST_CLOSE',key='original-'+str(i),now=OLD)
        monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
        budget.authorize_stage(tmp_path,'MACRO_SYNTHESIS',now=OLD)
    monkeypatch.delenv('AVSH_FULL_BUILD_ID')
    return tmp_path


def test_exact_exception_allows_one_fifth_attempt_and_preserves_all_old_rows(root,monkeypatch):
    with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):
        budget.reserve(root,reason='POST_CLOSE',key='not-authorized',now=NOW)
    token=budget.reserve(root,reason='POST_CLOSE',key=KEY,now=NOW)
    assert build_authorization(root,token,now=NOW)
    monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
    budget.authorize_stage(root,'MACRO_SYNTHESIS',now=NOW)
    assert budget.budget_status(root,'2026-11-18')['paid_attempts']==5
    with pytest.raises(ValueError,match='ALREADY_CLAIMED'):
        budget.reserve(root,reason='POST_CLOSE',key=KEY,now=NOW)
    with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):
        budget.reserve(root,reason='POST_CLOSE',key='sixth',now=NOW)
    with sqlite3.connect(budget._path(root)) as db:
        assert db.execute("SELECT count(*) FROM attempts WHERE fingerprint LIKE 'original-%'").fetchone()[0]==4
    budget.finish_attempt(root,token,1,now=NOW)
    assert build_authorization(root,token,now=NOW) is None


def test_exception_does_not_apply_to_other_reason_day_or_fingerprint(root):
    assert authorization(root,now=NOW,reason='PRE_OPEN',fingerprint=KEY) is None
    assert authorization(root,now=NOW,reason='POST_CLOSE',fingerprint='different') is None
    assert authorization(root,now=datetime(2026,11,19,5,tzinfo=timezone.utc)) is None
    with pytest.raises(ValueError,match='DAILY_FULL_BUILD_LIMIT'):
        budget.reserve(root,reason='MATERIAL_CHANGE',key=KEY,now=NOW)


def test_unknown_legacy_spend_remains_unknown_but_scoped_request_can_reserve_under_one_dollar(root,monkeypatch):
    request={'model':'claude-sonnet-4-6','max_tokens':16000,'system':'contract',
             'messages':[{'role':'user','content':'fresh evidence'}]}
    with pytest.raises(cost.ApiCostLimit,match='UNTRACKED_PRIOR_SPEND'):
        cost.reserve_request(root,'MACRO_SYNTHESIS',request,now=NOW,input_token_estimate=100000)
    token=budget.reserve(root,reason='POST_CLOSE',key=KEY,now=NOW)
    monkeypatch.setenv('AVSH_FULL_BUILD_ID',token)
    assert cost.reserve_request(root,'MACRO_SYNTHESIS',request,now=NOW,input_token_estimate=100000)
    assert cost.usage_status(root,'2026-11-18')['legacy_usage_unknown'] is True
    with pytest.raises(cost.ApiCostLimit,match='EXCEPTION_DOLLAR_CAP'):
        cost.reserve_request(root,'MACRO_SYNTHESIS',request,now=NOW,input_token_estimate=100000)
    with pytest.raises(cost.ApiCostLimit,match='SYNTHESIS_ONLY'):
        cost.reserve_request(root,'BOARD_NARRATIVE',request,now=NOW,input_token_estimate=1000)


def test_preflight_failure_consumes_only_exception_not_paid_slot(root):
    token=budget.reserve(root,reason='POST_CLOSE',key=KEY,now=NOW)
    assert budget.finish_attempt(root,token,1,now=NOW)=='PREFLIGHT_ONLY'
    assert budget.budget_status(root,'2026-11-18')['paid_attempts']==4
    with pytest.raises(ValueError,match='ALREADY_CLAIMED'):
        budget.reserve(root,reason='POST_CLOSE',key=KEY,now=NOW)
