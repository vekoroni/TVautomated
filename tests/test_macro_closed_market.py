"""Saved/synthetic closed-market tests: no providers or pipeline."""
import copy,hashlib,json,os
from datetime import datetime,timezone,timedelta
import pytest
from contracts.macro_closed_market import VERSION,assess
from contracts.macro_market_refresh_gate import verify_refresh,GROUPS
from contracts.macro_collection_health import assess_collection,CBOE_VIX
from contracts.macro_health import assess_macro_health
NOW=datetime(2026,11,26,11,10,tzinfo=timezone.utc)

def document(now=NOW,session='2026-11-25'):
    def row(s,t=None):return dict(symbol=s,last=100.,reference=100.,change_pct=0.,stale=False,state='OK',last_bar_utc=t or now.isoformat())
    old=session+'T21:10:00Z'
    groups={'us_futures':[row(s,old) for s in ('ES=F','NQ=F','YM=F','RTY=F')],
        'rates_commodities':[row(s,old) for s in ('ZN=F','CL=F','GC=F')],
        'fx':[row('EURUSD=X'),row('DX-Y.NYB',old)],'volatility':[row('VIX')],
        'us_premarket':[row('SPY','2026-11-26T00:55:00Z' if session=='2026-11-25' else session+'T21:55:00Z')],
        'asia':[row('REGIONAL')],'europe':[row('REGIONAL')]}
    groups['volatility'][0].update(source='YFINANCE',reference_label='VIX close '+session)
    csv='VIX_Direct,VIX_Source,VIX_Obs_Date\n28.29,YFINANCE,'+session+'\n'
    return dict(as_of_utc=now.isoformat(),us_reference_session=session,groups=groups,
        market_refresh=dict(as_of_utc=now.isoformat(),errors=[CBOE_VIX+': HTTP 403'],groups_refetched=list(GROUPS)),
        futures_refresh=dict(errors=[]),closed_market=dict(version=VERSION,run_mode='OffSession',
            vix_source_file='avshunter_vix_engine_v3.csv',vix_source_csv=csv,vix_source_sha256=hashlib.sha256(csv.encode()).hexdigest()))

def write(directory,doc):
    parent=directory/'overnight_20261126_100000.json';parent.write_bytes(b'{}')
    os.utime(parent,(NOW.timestamp()-3600,NOW.timestamp()-3600))
    doc['futures_refresh'].update(parent_file=parent.name,parent_sha256=hashlib.sha256(b'{}').hexdigest())
    target=directory/'overnight_20261126_111000.json';target.write_text(json.dumps(doc));return target

def test_holiday_disclosures_do_not_make_stale_observations_fresh(tmp_path):
    doc=document();write(tmp_path,doc);before=copy.deepcopy(doc)
    result=verify_refresh(tmp_path,not_before=NOW-timedelta(minutes=1),now=NOW)
    assert result['status']=='READY_FOR_FULL_WITH_LIMITATIONS'
    assert result['groups']['us_futures']=='AVAILABLE_WITH_LIMITATIONS'
    assert result['closed_market']['vix_reference']['observed_session']=='2026-11-25'
    assert result['closed_market']['vix_reference']['observation_precision']=='SESSION_DATE_ONLY'
    assert result['source_assessments']['us_futures'][0]['stale'] is True
    assert doc==before
    assert assess_collection(doc,NOW)['status']=='WARNING'

@pytest.mark.parametrize('mutation',[
    lambda d:d['closed_market'].update(vix_source_sha256='0'*64),
    lambda d:d['closed_market'].update(run_mode='PostClose'),
    lambda d:d.update(us_reference_session='2026-11-24'),
    lambda d:d['groups']['us_futures'][0].update(last=-1),
    lambda d:d['groups']['us_futures'][0].update(last_bar_utc='2026-11-24T21:00:00Z'),
    lambda d:d['groups']['us_futures'][0].update(last_bar_utc='2026-11-27T21:00:00Z'),
    lambda d:d['groups']['fx'][0].update(last_bar_utc='2026-11-25T21:00:00Z'),
    lambda d:d['market_refresh']['errors'].append('provider authentication HTTP 401'),
])
def test_bad_reference_live_fx_invalid_values_and_provider_errors_still_stop(tmp_path,mutation):
    doc=document();mutation(doc);write(tmp_path,doc)
    with pytest.raises(ValueError):verify_refresh(tmp_path,not_before=NOW-timedelta(minutes=1),now=NOW)

def test_policy_inactive_on_next_open_day():
    assert not assess(document(),datetime(2026,11,27,11,tzinfo=timezone.utc))['active']

@pytest.mark.parametrize('day',[28,29])
def test_weekend_uses_friday_reference_and_actual_fx_close(day):
    now=datetime(2026,11,day,12,tzinfo=timezone.utc);doc=document(now,'2026-11-27')
    for row in doc['groups']['fx']:row['last_bar_utc']='2026-11-27T21:55:00Z'
    out=assess(doc,now)
    assert out['active'] and out['vix_reference']['observed_session']=='2026-11-27'
    assert 'fx' in out['limited_groups']
    health=assess_macro_health({'extras':{'overnight':{'document':doc}}},now=now)
    assert health['source_health']['fx']['status'] in {'AVAILABLE','AVAILABLE_WITH_LIMITATIONS'}
    assert health['source_health']['fx']['closed_market_limitations']
    assert all(row['not_live'] for row in health['source_health']['fx']['instruments'])

def test_sunday_reopening_does_not_accept_friday_futures():
    now=datetime(2026,11,29,23,30,tzinfo=timezone.utc)
    assert 'us_futures' not in assess(document(now,'2026-11-27'),now)['limited_groups']
