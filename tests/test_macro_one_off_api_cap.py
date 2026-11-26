import json
from datetime import datetime,timezone
from pathlib import Path
import pytest
from contracts import macro_api_cost as cost


@pytest.fixture
def root(tmp_path):
    original=Path(__file__).resolve().parents[1]
    (tmp_path/'config').mkdir()
    for name in ('macro_api_cost_v1.json','macro_build_schedule_v1.json'):
        (tmp_path/'config'/name).write_bytes((original/'config'/name).read_bytes())
    return tmp_path


def test_one_off_cap_expires_and_does_not_change_standing_policy(root):
    raw=(root/'config/macro_api_cost_v1.json').read_bytes()
    assert cost.policy(root,'2026-11-25')['daily_cap_usd']==6
    assert cost.policy(root,'2026-11-25')['standing_daily_cap_usd']==4
    assert cost.policy(root,'2026-11-26')['daily_cap_usd']==4
    assert cost.policy(root,'2026-11-24')['daily_cap_usd']==4
    assert cost.usage_status(root,'2026-11-25')['daily_cap_usd']==6
    assert cost.usage_status(root,'2026-11-26')['daily_cap_usd']==4
    assert (root/'config/macro_api_cost_v1.json').read_bytes()==raw
    assert not (root/'data/macro/delivery/api_usage.sqlite').exists()


def test_reservation_uses_its_actual_et_day(root):
    request={'model':'claude-sonnet-4-6','max_tokens':16000,'system':'contract',
             'messages':[{'role':'user','content':'evidence'}]}
    # 04:59 UTC is still 25 November in New York. The next minute is 26th.
    before=datetime(2026,11,26,4,59,tzinfo=timezone.utc)
    after=datetime(2026,11,26,5,0,tzinfo=timezone.utc)
    for _ in range(15):cost.reserve_request(root,'MACRO_SYNTHESIS',request,now=before)
    assert cost.usage_status(root,'2026-11-25')['accounted_usd']>4
    assert cost.usage_status(root,'2026-11-25')['accounted_usd']<=6
    for _ in range(30):
        try:cost.reserve_request(root,'MACRO_SYNTHESIS',request,now=after)
        except cost.ApiCostLimit:break
    assert cost.usage_status(root,'2026-11-26')['accounted_usd']<=4
    with pytest.raises(cost.ApiCostLimit,match='DOLLAR_CAP'):
        cost.reserve_request(root,'MACRO_SYNTHESIS',request,now=after)


def test_missing_authority_fails_closed(root):
    path=root/'config/macro_api_cost_v1.json'
    policy=json.loads(path.read_text());policy['one_off_daily_caps']['2026-11-25'].pop('authority')
    path.write_text(json.dumps(policy))
    with pytest.raises(cost.ApiCostLimit,match='authority'):
        cost.policy(root,'2026-11-25')
