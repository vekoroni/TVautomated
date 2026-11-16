"""Saved-data FRED freshness regressions extracted without unrelated refresh tests."""
import copy
from datetime import datetime, timezone
import pytest
from contracts.macro_health import assess_macro_health

def test_fred_health_distinguishes_fetched_series_count_and_measurement_period():
 now=datetime(2026,10,23,15,tzinfo=timezone.utc)
 macro={'extras':{'fred_series_health':[
  {'series':'GDPC1','frequency':'Q','last_observation':'2026-04-01','fetched_utc':'2026-10-23T14:30:00Z'},
  {'series':'PCE','frequency':'M','last_observation':'2026-08-01','fetched_utc':'2026-10-23T14:30:00Z'}]}}
 h=assess_macro_health(macro,report={'data_quality':{'fred_series_retrieved':1}},now=now)
 assert h['fred_series_retrieved']==2
 assert h['source_health']['fred']['producer_reported_series_retrieved']==1
 rows=h['source_health']['fred']['series']
 assert rows[0]['observation_period_end']=='2026-06-30'
 assert rows[1]['observation_period_end']=='2026-08-31'
 assert all(r['source_refresh_status']=='RECENT_FETCH' for r in rows)
 # Publication policy ages monthly/quarterly observations from period end,
 # not their native period-start labels or their retrieval timestamps.
 assert [r['assessed_age_days'] for r in rows]==[115,53]
 assert [r['native_observation_age_days'] for r in rows]==[205,83]
 assert [r['last_observation'] for r in rows]==['2026-04-01','2026-08-01']
 assert all(r['assessed_status']=='FRESH' and r['not_live'] for r in rows)
 assert not h['source_health']['fred']['accepted_latest_public'], 'Age-policy acceptance is not latest-public verification'


@pytest.mark.parametrize('code,freq,observed,period_end,limit',[
 ('GDPC1','Q','2026-04-01','2026-06-30',140),
 ('PCE','M','2026-08-01','2026-08-31',75),
])
def test_fred_period_age_boundary_is_independent_of_recent_fetch(code,freq,observed,period_end,limit):
 from datetime import timedelta
 end=datetime.fromisoformat(period_end).replace(hour=15,tzinfo=timezone.utc)
 for days,expected in [(limit,'FRESH'),(limit+1,'PUBLICATION_UNVERIFIED')]:
  now=end+timedelta(days=days)
  item=dict(series=code,frequency=freq,last_observation=observed,fetched_utc=now.isoformat())
  original=copy.deepcopy(item)
  h=assess_macro_health({'extras':{'fred_series_health':[item]}},now=now)
  row=h['source_health']['fred']['series'][0]
  assert item==original
  assert row['source_refresh_status']=='RECENT_FETCH'
  assert row['assessed_age_days']==days and row['observation_period_end']==period_end
  assert row['last_observation']==observed and row['assessed_status']==expected
  assert row['gap_disposition']==('NO_GAP' if expected=='FRESH' else 'ACTIVE_GUIDANCE_GAP')
  assert not h['source_health']['fred']['accepted_latest_public']


@pytest.mark.parametrize('code,freq,observed,newer',[
 ('GDPC1','Q','2026-04-01','2026-07-01'),
 ('PCE','M','2026-08-01','2026-09-01'),
])
def test_fred_known_newer_release_overrides_age_policy_and_recent_fetch(code,freq,observed,newer):
 from contracts.fred_publication import publication_receipt
 now=datetime(2026,10,23,15,tzinfo=timezone.utc)
 item=dict(series=code,frequency=freq,last_observation=observed,fetched_utc=now.isoformat())
 # Saved in-memory provider-response fixture; no network or live source writes.
 item.update(publication_receipt([{'date':observed,'value':'100'},
                                  {'date':newer,'value':'101'}],now.date(),now))
 h=assess_macro_health({'extras':{'fred_series_health':[item]}},now=now)
 row=h['source_health']['fred']['series'][0]
 assert row['source_refresh_status']=='RECENT_FETCH'
 assert row['assessed_status']=='MISSED_PUBLIC_UPDATE'
 assert row['last_observation']==observed and row['public_latest_observation']==newer
 assert row['gap_disposition']=='ACTIVE_GUIDANCE_GAP'
 assert 'FRED_SERIES_MISSED_PUBLIC_UPDATE' in h['issues']
