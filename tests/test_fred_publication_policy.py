from datetime import datetime, timezone
import pytest
NOW=datetime(2026,10,24,12,tzinfo=timezone.utc)

def row(code,freq,date):
 return dict(series=code,frequency=freq,last_observation=date,fetched_utc=NOW.isoformat())

@pytest.mark.parametrize('code,freq,date',[('M2SL','M','2026-08-01'),('PCE','M','2026-08-01'),('NEWORDER','M','2026-08-01'),('GDPC1','Q','2026-04-01'),('FDHBFRBN','Q','2026-04-01')])
def test_period_start_is_not_the_publication_age(code,freq,date):
 from contracts.fred_publication import assess_observation
 r=assess_observation(row(code,freq,date),NOW)
 assert r['assessed_status']=='FRESH'
 assert r['assessed_age_days']==r['age_since_period_end_days']

@pytest.mark.parametrize('code,freq,date',[('DEXUSEU','D','2026-10-16'),('DTWEXBGS','D','2026-10-16'),('WM2NS','W','2026-08-31')])
def test_observation_frequency_is_not_release_frequency(code,freq,date):
 from contracts.fred_publication import assess_observation
 r=assess_observation(row(code,freq,date),NOW)
 assert r['assessed_status']=='EXPECTED_PUBLICATION_LAG'
 assert r['not_live'] and r['guidance_effect']

def test_release_calendar_cannot_excuse_a_missed_week_or_future_value():
 from contracts.fred_publication import assess_observation
 assert assess_observation(row('DEXUSEU','D','2026-10-09'),NOW)['assessed_status']=='PUBLICATION_UNVERIFIED'
 assert assess_observation(row('IORB','D','2026-10-26'),NOW)['assessed_status']=='FUTURE_OBSERVATION'

def test_oecd_parser_rejects_a_different_measure_and_keeps_native_month():
 from contracts.fred_publication import parse_oecd_cli
 head='REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ACTIVITY,ADJUSTMENT,TRANSFORMATION,TIME_HORIZ,METHODOLOGY,TIME_PERIOD,OBS_VALUE\n'
 raw=head+'USA,M,LI,IX,_Z,NOR,IX,_Z,H,2026-09,101.0\n'
 assert parse_oecd_cli(raw,'2026-10-23')==[('2026-09-01',101.0)]
 with pytest.raises(ValueError):parse_oecd_cli(raw.replace(',NOR,',',AA,'),'2026-10-23')
 with pytest.raises(ValueError):parse_oecd_cli(raw+raw.splitlines()[1]+'\n','2026-10-23')

def test_health_distinguishes_replaced_history_from_an_active_guidance_gap():
 from contracts.macro_health import assess_macro_health
 rows=[row('USSLIND','M','2020-02-01'),row('USALOLITONOSTSAM','M','2024-01-01'),row('OECD_CLI_US_NORMALIZED','M','2026-09-01'),row('THREEFYTP10','D','2026-10-16')]
 rows[2]['provider']='OECD'
 h=assess_macro_health({'extras':{'fred_series_health':rows}},now=NOW)['source_health']['fred']
 assert h['guidance_gaps'][0]['series']=='THREEFYTP10' and len(h['guidance_gaps'])==1
 assert h['series'][1]['gap_disposition']=='REPLACED_SAME_MEASURE'
 assert h['series'][0]['gap_disposition']=='HISTORICAL_ONLY_RELATED_COVERAGE'

def test_stale_model_value_is_not_promoted_to_current_summary():
 from contracts.fred_publication import current_summary_value
 assert current_summary_value(0.9857,{'status':'STALE'}) is None
 assert current_summary_value(0.9857,{'status':'MISSING'}) is None
 assert current_summary_value(1.1,{'status':'FRESH'})==1.1

def test_weekly_fx_turns_overdue_after_the_actual_release_time():
 from contracts.fred_publication import assess_observation
 r=row('DEXUSEU','D','2026-10-16')
 assert assess_observation(r,datetime(2026,10,26,20,14,tzinfo=timezone.utc))['assessed_status']=='EXPECTED_PUBLICATION_LAG'
 assert assess_observation(r,datetime(2026,10,26,20,16,tzinfo=timezone.utc))['assessed_status']=='PUBLICATION_UNVERIFIED'

def test_next_release_does_not_hide_a_missed_monthly_publication():
 from contracts.fred_publication import assess_observation
 r=row('M2SL','M','2026-08-01');r.update(fred_last_updated='2026-09-22 12:01:00-05',last_scheduled_release_date='2026-10-27',next_release_date='2026-11-24')
 assert assess_observation(r,datetime(2026,10,30,12,tzinfo=timezone.utc))['assessed_status']=='PUBLICATION_UNVERIFIED'
