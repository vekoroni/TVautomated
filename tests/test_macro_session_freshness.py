"""Offline session-boundary and complete FULL prerequisite tests; no builds."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import pytest
from contracts.macro_source_sessions import classify_source_session
from contracts.macro_market_refresh_gate import verify_refresh, GROUPS


def clock(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def row(symbol, stamp, **values):
    return dict(symbol=symbol, last=100., last_bar_utc=stamp, state='OK', stale=False, **values)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **k: pytest.fail('No provider calls'))


@pytest.mark.parametrize('now,vix,etf,closed', [
    ('2026-11-17T07:54:54Z','2026-11-16T21:15:00Z','2026-11-17T00:55:00Z',(True,True)),
    ('2026-11-17T13:35:00Z','2026-11-17T13:20:00Z','2026-11-17T13:20:00Z',(False,False)),
    ('2026-11-17T21:30:00Z','2026-11-17T21:15:00Z','2026-11-17T21:25:00Z',(True,False)),
    ('2026-11-18T04:30:00Z','2026-11-17T21:15:00Z','2026-11-18T00:55:00Z',(True,True)),
    ('2026-11-16T07:54:00Z','2026-11-13T21:15:00Z','2026-11-14T00:55:00Z',(True,True)),
    ('2026-11-26T13:35:00Z','2026-11-25T21:15:00Z','2026-11-26T00:55:00Z',(True,True)),
    ('2026-11-27T19:00:00Z','2026-11-27T18:15:00Z','2026-11-27T18:55:00Z',(True,False)),
    ('2026-11-28T07:54:00Z','2026-11-27T18:15:00Z','2026-11-27T21:55:00Z',(True,True)),
    ('2026-10-30T06:54:00Z','2026-10-29T20:15:00Z','2026-10-29T23:55:00Z',(True,True)),
    ('2026-11-17T08:14:59Z','2026-11-16T21:15:00Z','2026-11-17T00:55:00Z',(True,True)),
    ('2026-11-17T08:30:00Z','2026-11-17T08:20:00Z','2026-11-17T00:55:00Z',(False,True)),
])
def test_feed_sessions_last_reference_and_live_obligations(now,vix,etf,closed):
    for index,(group,symbol,stamp) in enumerate([('volatility','VIX',vix),('us_premarket','SPY',etf)]):
        source=row(symbol,stamp); original=deepcopy(source)
        result=classify_source_session(group,source,clock(now))
        assert not result['stale'],result
        assert result['not_live']==closed[index]
        assert source==original
        assert result['state']==('MARKET_CLOSED_LAST_SESSION' if closed[index] else 'OK')


@pytest.mark.parametrize('group,symbol,now,stamp',[
    ('volatility','VIX','2026-11-17T08:15:00Z','2026-11-16T21:15:00Z'),
    ('us_premarket','SPY','2026-11-17T09:00:00Z','2026-11-17T00:55:00Z'),
    ('us_premarket','SPY','2026-11-17T09:10:00Z','2026-11-17T08:55:00Z'),
    ('volatility','VIX','2026-11-17T13:35:00Z','2026-11-17T12:30:00Z'),
    ('us_premarket','QQQ','2026-11-17T21:30:00Z','2026-11-17T20:00:00Z'),
    ('volatility','VIX','2026-11-17T21:30:00Z','2026-11-17T20:00:00Z'),
    ('volatility','VIX','2026-11-17T07:54:54Z','2026-11-13T21:15:00Z'),
    ('us_premarket','DIA','2026-11-17T07:54:54Z','2026-11-16T20:55:00Z'),
    ('volatility','VIX','2026-11-17T07:54:54Z','2026-11-17T07:55:00Z'),
])
def test_stale_wrong_session_and_future_observations_still_fail(group,symbol,now,stamp):
    assert classify_source_session(group,row(symbol,stamp),clock(now))['stale']


@pytest.mark.parametrize('patch',[
    {'last_bar_utc':None},{'last_bar_utc':'2026-11-16T21:15:00'},
    {'last':None},{'last':0},{'last':float('nan')},{'last':True},
    {'state':'MISSING_REFERENCE'},{'state':'COLLECTION_ERROR'},
])
def test_bad_evidence_cannot_be_excused_by_market_closure(patch):
    r=row('VIX','2026-11-16T21:15:00Z');r.update(patch)
    assert classify_source_session('volatility',r,clock('2026-11-17T07:54:54Z'))['stale']


def test_no_blanket_exemption_for_other_feeds():
    for group,symbol in [('fx','EURUSD=X'),('us_futures','ES=F'),('volatility','UNKNOWN'),('us_premarket','UNKNOWN')]:
        assert classify_source_session(group,row(symbol,'2026-11-16T21:15:00Z'),clock('2026-11-17T07:54:54Z')) is None


def test_live_source_degradation_is_not_cleared_by_a_recent_timestamp():
    r=row('SPY','2026-11-17T13:30:00Z');r['stale']=True
    assert classify_source_session('us_premarket',r,clock('2026-11-17T13:35:00Z'))['stale']


def fixture(directory,now,vix,etf):
    now=clock(now)
    recent=(now-timedelta(minutes=10)).isoformat()
    groups={
        'us_futures':[row(s,recent) for s in ('ES=F','NQ=F','YM=F','RTY=F')],
        'rates_commodities':[row(s,recent) for s in ('ZN=F','CL=F','GC=F')],
        'fx':[row('EURUSD=X',recent)], 'asia':[row('^N225',recent)],
        'europe':[row('^FTSE',recent)], 'volatility':[row('VIX',vix)],
        'us_premarket':[row(s,etf) for s in ('SPY','QQQ','IWM','DIA')],
    }
    for group in ('volatility','us_premarket'):
        for r in groups[group]:
            r['stale']=(now-clock(r['last_bar_utc'])).total_seconds()>3600
    parent=directory/'source_parent.json';parent.write_bytes(b'{}')
    stamp=(now-timedelta(seconds=1)).isoformat()
    doc=dict(as_of_utc=stamp,groups=groups,market_refresh=dict(as_of_utc=stamp,errors=[],groups_refetched=list(GROUPS)),
             futures_refresh=dict(errors=[],parent_file=parent.name,parent_sha256=hashlib.sha256(parent.read_bytes()).hexdigest()))
    target=directory/'overnight_20261117_075453.json';target.write_text(json.dumps(doc))
    return target,doc,now


@pytest.mark.parametrize('now,vix,etf',[
    ('2026-11-17T07:54:54Z','2026-11-16T21:15:00Z','2026-11-17T00:55:00Z'),
    ('2026-11-17T13:35:00Z','2026-11-17T13:20:00Z','2026-11-17T13:20:00Z'),
    ('2026-11-17T21:30:00Z','2026-11-17T21:15:00Z','2026-11-17T21:25:00Z'),
])
def test_complete_gate_early_normal_preopen_and_postclose_is_read_only(tmp_path,now,vix,etf):
    path,doc,now=fixture(tmp_path,now,vix,etf)
    original={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result=verify_refresh(tmp_path,not_before=now-timedelta(minutes=5),now=now)
    assert result['status']=='READY_FOR_FULL'
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==original
    assert result['source_assessments']['volatility'][0]['last_bar_utc']==vix
    assert result['source_assessments']['us_premarket'][0]['last_bar_utc']==etf


@pytest.mark.parametrize('damage',['old_vix','old_etf','errors','parent','expired_capture'])
def test_early_session_exception_does_not_bypass_other_guards(tmp_path,damage):
    path,doc,now=fixture(tmp_path,'2026-11-17T07:54:54Z','2026-11-16T21:15:00Z','2026-11-17T00:55:00Z')
    if damage=='old_vix':doc['groups']['volatility'][0]['last_bar_utc']='2026-11-13T21:15:00Z'
    elif damage=='old_etf':doc['groups']['us_premarket'][0]['last_bar_utc']='2026-11-16T20:55:00Z'
    elif damage=='errors':doc['market_refresh']['errors']=['provider failure']
    elif damage=='parent':doc['futures_refresh']['parent_sha256']='0'*64
    else:doc['as_of_utc']=doc['market_refresh']['as_of_utc']=(now-timedelta(minutes=11)).isoformat()
    path.write_text(json.dumps(doc));before=path.read_bytes()
    with pytest.raises(ValueError):verify_refresh(tmp_path,not_before=now-timedelta(minutes=15),now=now)
    assert path.read_bytes()==before
