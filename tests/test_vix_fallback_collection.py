"""Saved failure shape and injected responses only; no providers or builds."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import pytest
from contracts.macro_collection_health import assess_collection, CBOE_VIX
from contracts.macro_market_refresh_gate import verify_refresh, GROUPS
from contracts.macro_health import assess_macro_health

NOW=datetime(2026,11,19,23,18,27,tzinfo=timezone.utc)
ERROR=CBOE_VIX+': HTTP 403'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('No providers'))


def saved_document():
    def row(symbol):return dict(symbol=symbol,last=100.,last_bar_utc='2026-11-19T23:15:00Z',state='OK',stale=False)
    groups={
        'us_futures':[row(s) for s in ('ES=F','NQ=F','YM=F','RTY=F')],
        'rates_commodities':[row(s) for s in ('ZN=F','CL=F','GC=F')],
        'fx':[row('EURUSD=X')], 'us_premarket':[row('SPY')],
        'asia':[dict(row('^N225'),state='NOT_YET_OPEN',last_bar_utc='2026-11-19T06:30:00Z')],
        'europe':[dict(row('^FTSE'),state='CLOSED',last_bar_utc='2026-11-19T16:30:00Z',session_date='2026-11-19',exchange_tz='Europe/London')],
        'volatility':[dict(symbol='VIX',source='YFINANCE',last=28.440000534057617,
            reference=28.440000534057617,reference_label='VIX close 2026-11-19',
            last_bar_utc='2026-11-19T21:15:00Z',change_pct=0.,state='STALE',stale=True)],
    }
    return dict(as_of_utc='2026-11-19T23:18:26Z',us_reference_session='2026-11-19',groups=groups,
                market_refresh=dict(as_of_utc='2026-11-19T23:18:26Z',groups_refetched=list(GROUPS),errors=[ERROR]),
                futures_refresh=dict(errors=[ERROR]))


def write_fixture(tmp_path,doc):
    parent=tmp_path/'source_parent.json';parent.write_bytes(b'{"original":true}')
    doc['futures_refresh'].update(parent_file=parent.name,parent_sha256=hashlib.sha256(parent.read_bytes()).hexdigest())
    target=tmp_path/'overnight_20261119_231826.json';target.write_text(json.dumps(doc))
    return target


def test_saved_403_is_warning_only_after_independent_fallback_validation(tmp_path):
    doc=saved_document();frozen=deepcopy(doc)
    c=assess_collection(doc,NOW)
    assert doc==frozen
    assert c['status']=='WARNING' and not c['fatal_errors']
    assert c['raw_errors']==[ERROR] and len(c['warnings'])==1
    assert c['warnings'][0]['primary_error']==ERROR
    assert c['warnings'][0]['not_live']
    path=write_fixture(tmp_path,doc);before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    r=verify_refresh(tmp_path,not_before=NOW-timedelta(minutes=1),now=NOW)
    assert r['status']=='READY_FOR_FULL' and all(s=='AVAILABLE' for s in r['groups'].values())
    assert r['warnings']==c['warnings']
    assert r['source_assessments']['volatility'][0]['state']=='MARKET_CLOSED_LAST_SESSION'
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


@pytest.mark.parametrize('patch',[
    {'last':None},{'last':0},{'last':float('nan')},{'last':float('inf')},
    {'reference':None},{'reference':-1},{'reference':False},
    {'last_bar_utc':None},{'last_bar_utc':'2026-11-19T21:15:00'},
    {'last_bar_utc':'2026-11-19T23:19:00Z'},
    {'last_bar_utc':'2026-11-18T21:15:00Z'},
    {'last_bar_utc':'2026-11-19T20:00:00Z'},
    {'reference_label':'VIX close 2026-11-18'}, {'reference_label':None},
    {'state':'COLLECTION_ERROR'},{'source':'CBOE_DELAYED'},
    {'change_pct':None},{'change_pct':float('nan')},{'change_pct':30},
])
def test_invalid_fallback_cannot_suppress_primary_failure(tmp_path,patch):
    doc=saved_document();doc['groups']['volatility'][0].update(patch)
    original=deepcopy(doc)
    c=assess_collection(doc,NOW)
    assert c['status']=='FAILED' and c['fatal_errors'] and not c['warnings']
    assert c['vix_fallback']['status']=='INVALID'
    # Even a forged producer recovery claim cannot bypass independent validation.
    doc['market_refresh']['collection_assessment']={'status':'AVAILABLE','fatal_errors':[]}
    path=write_fixture(tmp_path,doc);before=path.read_bytes()
    with pytest.raises(ValueError,match='MARKET_REFRESH_COLLECTION_ERRORS'):
        verify_refresh(tmp_path,not_before=NOW-timedelta(minutes=1),now=NOW)
    assert path.read_bytes()==before


@pytest.mark.parametrize('other',[
    'https://api.marketdata.app/stocks/candles/5/SPY/: HTTP 429',
    'https://api.stlouisfed.org/fred/series: HTTP 403',
    'https://cdn.cboe.com/api/global/delayed_quotes/quotes/OTHER.json: HTTP 403',
    'https://cdn.cboe.com.evil.invalid/api/global/delayed_quotes/quotes/_VIX.json: HTTP 403',
    ERROR+' plus an unrelated failure','provider unavailable',
])
def test_only_exact_primary_vix_errors_can_be_recovered(tmp_path,other):
    doc=saved_document();doc['futures_refresh']['errors'].append(other)
    c=assess_collection(doc,NOW)
    assert c['status']=='FAILED' and other in c['fatal_errors']
    assert c['warnings'][0]['primary_error']==ERROR
    write_fixture(tmp_path,doc)
    with pytest.raises(ValueError,match='MARKET_REFRESH_COLLECTION_ERRORS'):
        verify_refresh(tmp_path,not_before=NOW-timedelta(minutes=1),now=NOW)


@pytest.mark.parametrize('now,stamp,reference,valid',[
    ('2026-11-20T07:54:00Z','2026-11-19T21:15:00Z','2026-11-19',True),
    ('2026-11-19T13:35:00Z','2026-11-19T13:20:00Z','2026-11-18',True),
    ('2026-11-19T13:35:00Z','2026-11-18T21:15:00Z','2026-11-18',False),
    ('2026-11-19T23:18:27Z','2026-11-19T21:15:00Z','2026-11-18',False),
])
def test_fallback_must_fit_the_actual_assessment_session(now,stamp,reference,valid):
    doc=saved_document();doc['us_reference_session']=reference
    doc['groups']['volatility'][0].update(last_bar_utc=stamp,reference_label='VIX close '+reference,stale=False,state='OK')
    c=assess_collection(doc,datetime.fromisoformat(now.replace('Z','+00:00')))
    assert (c['vix_fallback']['status']=='VALIDATED')==valid


def test_missing_fallback_and_invalid_silent_fallback_still_fail(tmp_path):
    doc=saved_document();doc['groups']['volatility']=[]
    assert assess_collection(doc,NOW)['fatal_errors']
    doc=saved_document();doc['market_refresh']['errors']=[];doc['futures_refresh']['errors']=[]
    c=assess_collection(doc,NOW)
    assert c['warnings'][0]['code']=='VIX_FALLBACK_USED'
    doc['groups']['volatility'][0]['reference']=None
    assert assess_collection(doc,NOW)['fatal_errors']


@pytest.mark.parametrize('failure,marker',[
    ('parent','PARENT_HASH'),('expired','CAPTURE_EXPIRED'),('old_fx','MARKET_SOURCE_NOT_READY'),
])
def test_recovered_vix_cannot_bypass_unrelated_guards(tmp_path,failure,marker):
    doc=saved_document();path=write_fixture(tmp_path,doc)
    if failure=='parent':doc['futures_refresh']['parent_sha256']='0'*64
    elif failure=='expired':doc['as_of_utc']=doc['market_refresh']['as_of_utc']=(NOW-timedelta(minutes=11)).isoformat()
    else:doc['groups']['fx'][0]['last_bar_utc']='2026-11-19T20:00:00Z'
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match=marker):verify_refresh(tmp_path,not_before=NOW-timedelta(minutes=15),now=NOW)


def test_warning_survives_macro_health():
    doc=saved_document();original=deepcopy(doc)
    health=assess_macro_health({'extras':{'overnight':{'document':doc}}},now=NOW)
    assert doc==original
    assert health['source_health']['volatility']['status']=='AVAILABLE'
    assert 'VIX_PRIMARY_SOURCE_FAILED_FALLBACK_VALIDATED' in health['issues']
    assert health['source_health']['volatility']['warnings'][0]['primary_error']==ERROR


def test_injected_collector_403_records_warning_without_erasing_errors():
    import pandas as pd
    from scripts import refresh_futures_snapshot as refresh
    def history(symbol,period,interval):
        if symbol=='^VIX':
            stamps=['2026-11-19T00:00:00Z'] if interval=='1d' else ['2026-11-19T20:55:00Z','2026-11-19T21:15:00Z']
            return pd.DataFrame({'Close':[28.44]*len(stamps)},index=pd.to_datetime(stamps))
        return pd.DataFrame({'Close':[100.,101.]},index=pd.to_datetime(['2026-11-19T20:55:00Z','2026-11-19T23:15:00Z']))
    class Response:
        def __init__(self,code):self.status_code=code
        def json(self):return {'s':'ok','t':[1795121700,1795130100],'c':[100.,101.],'v':[1,1]}
    calls=[]
    def get(url,**kwargs):calls.append(url);return Response(403 if url==CBOE_VIX else 200)
    source={'us_reference_session':'2026-11-19','us_reference_close_utc':'2026-11-19T21:00:00Z','groups':{}}
    before=deepcopy(source)
    result=refresh.refresh_document(source,history=history,http_get=get,marketdata_key='offline',now=NOW,all_market_data=True)
    assert source==before and CBOE_VIX in calls
    assert ERROR in result['market_refresh']['errors'] and ERROR in result['futures_refresh']['errors']
    assert result['market_refresh']['collection_assessment']['status']=='WARNING'
    assert result['market_refresh']['collection_assessment']['warnings'][0]['primary_error']==ERROR
