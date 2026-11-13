import importlib.util
from pathlib import Path
import pytest
import json
PATH=Path(__file__).parents[1]/'Enhancements/phase0/phantom_path_supplement_20261113.py'
spec=importlib.util.spec_from_file_location('path_supplement_test',PATH)
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


@pytest.fixture(autouse=True)
def synthetic_approved_worklist(tmp_path,monkeypatch):
    # No live worklist, receipts or market data are needed by the release tests.
    targets=[{'ticker':'AAL','day':'2026-10-20' if i%2 else '2026-10-13',
              'symbol':f'AAL270115P{10000+i*1000:08d}'} for i in range(508)]
    (tmp_path/'OPTION_PATH_GAP_WORKLIST_20261113.json').write_text(json.dumps({'request_keys':targets}))
    monkeypatch.setattr(p.m.g,'EXTERNAL',tmp_path)
    monkeypatch.setattr(p.PathScope,'target_hash',p.m.g.digest(p.m.g.encoded(targets)))

def test_only_frozen_508_keys_are_allowed_and_never_november_12():
    scope=p.PathScope()
    assert len(scope.manifest['targets'])==508
    assert '2026-11-12' not in scope.allowed_days
    t=scope.manifest['targets'][0];scope.check_target(t)
    with pytest.raises(ValueError):scope.check_target({**t,'day':'2026-11-12'})
    with pytest.raises(ValueError):scope.check_target({**t,'symbol':'FAKE270115C00010000'})

def test_request_identity_and_saved_reuse_do_not_change_between_supplements():
    scope=p.PathScope();eligible=[]
    for item in scope.manifest['targets']:
        try:p.m.check_target(item);eligible.append(item)
        except ValueError:pass
    t=eligible[0]
    assert p.m.quote_key(t,scope=scope)==p.m.quote_key(t)

def test_path_scope_cannot_renew_the_existing_cap(tmp_path):
    scope=p.PathScope();b=p.m.g.Budget(tmp_path,1,allowed_days=scope.allowed_days)
    t=scope.manifest['targets'][0];b.reserve('one',t['ticker'],t['day'],0)
    with pytest.raises(RuntimeError,match='CAP'):p.m.g.Budget(tmp_path,2,allowed_days=scope.allowed_days)

def test_path_scope_reuses_exact_request_without_a_second_paid_call(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    scope=p.PathScope();t=scope.manifest['targets'][0]
    data={'s':'ok','optionSymbol':[t['symbol']],'bid':[1.],'ask':[1.2],
          'underlyingPrice':[20.], 'updated':[int(datetime.fromisoformat(t['day']+'T16:00:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp())]}
    class R:
        status_code=200;headers={'X-Api-Ratelimit-Consumed':'1'}
        def json(self):return data
    class S:
        calls=0
        def get(self,*a,**k):self.calls+=1;return R()
    session=S();b=p.m.g.Budget(tmp_path,2,allowed_days=scope.allowed_days)
    b.reserve('old-entry','AAL','2026-10-20',0)
    p.m.fetch_quote(session,b,t,scope)
    p.m.fetch_quote(session,p.m.g.Budget(tmp_path,2,allowed_days=scope.allowed_days),t,scope)
    assert session.calls==1
    row=p.m.normalize_quote(data,t,scope)
    assert row['ticker']==t['ticker'] and row['quote_date']==t['day']
    import json
    assert json.loads(row['raw_json'])['backfill_job']==scope.job
    with pytest.raises(RuntimeError,match='CAP'):
        p.m.fetch_quote(session,b,scope.manifest['targets'][1],scope)
    assert session.calls==1
