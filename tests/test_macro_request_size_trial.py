"""Dated payload trial preserves next-day limits and separately approved spending."""
import json
from pathlib import Path
import pytest
from contracts import macro_api_cost as cost

@pytest.fixture
def root(tmp_path):
    (tmp_path/'config').mkdir()
    policy=json.loads((Path(__file__).resolve().parents[1]/'config/macro_api_cost_v1.json').read_text())
    policy['one_off_daily_caps']={'2026-11-26':{'daily_cap_usd':10,'authority':'explicit daily grant'}}
    policy['one_off_request_limits']={'2026-11-26':{'max_request_bytes':900000,'authority':'explicit payload trial'}}
    (tmp_path/'config/macro_api_cost_v1.json').write_text(json.dumps(policy))
    return tmp_path

def test_trial_expires_without_changing_standing_limit_or_money(root):
    before=(root/'config/macro_api_cost_v1.json').read_bytes()
    today=cost.policy(root,'2026-11-26')
    assert today['max_request_bytes']==900000 and today['standing_max_request_bytes']==750000
    assert today['daily_cap_usd']==10 and today['max_output_tokens']==16000
    assert cost.policy(root,'2026-11-27')['max_request_bytes']==750000
    assert cost.policy(root,'2026-11-27')['daily_cap_usd']==4
    assert (root/'config/macro_api_cost_v1.json').read_bytes()==before

def test_request_limit_and_next_day_fail_closed(root):
    request={'model':'claude-sonnet-4-6','max_tokens':16000,'system':'rules','messages':[{'role':'user','content':'x'*800000}]}
    assert len(cost._quote(root,request,day='2026-11-26')[1])<900000
    with pytest.raises(cost.ApiCostLimit,match='INPUT_TOO_LARGE'):cost._quote(root,request,day='2026-11-27')
    request['messages'][0]['content']='x'*900000
    with pytest.raises(cost.ApiCostLimit,match='INPUT_TOO_LARGE'):cost._quote(root,request,day='2026-11-26')
    assert not (root/'data').exists()

@pytest.mark.parametrize('grant',[{}, {'authority':'test','max_request_bytes':True},{'authority':'test','max_request_bytes':-1}])
def test_invalid_trial_grant_is_rejected(root,grant):
    path=root/'config/macro_api_cost_v1.json';p=json.loads(path.read_text());p['one_off_request_limits']['2026-11-26']=grant;path.write_text(json.dumps(p))
    with pytest.raises(cost.ApiCostLimit):cost.policy(root,'2026-11-26')

def test_production_config_has_unique_keys_and_dated_approval():
    def unique(pairs):
        result={}
        for key,value in pairs:
            assert key not in result,key
            result[key]=value
        return result
    path=Path(__file__).resolve().parents[1]/'config/macro_api_cost_v1.json'
    p=json.loads(path.read_text(),object_pairs_hook=unique)
    assert p['daily_cap_usd']==4 and p['max_request_bytes']==750000
    assert p['one_off_daily_caps']['2026-11-26']['daily_cap_usd']==10
