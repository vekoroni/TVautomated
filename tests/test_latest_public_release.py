from datetime import datetime,timezone
NOW=datetime(2026,10,24,12,tzinfo=timezone.utc)

def verified(code='THREEFYTP10',observed='2026-10-16'):
 return dict(series=code,frequency='D',last_observation=observed,public_latest_observation=observed,publication_query_end='2026-10-23',publication_verified_at_utc=NOW.isoformat(),publication_evidence_sha256='a'*64,fetched_utc=NOW.isoformat())

def test_latest_public_term_premium_is_accepted_despite_age():
 from contracts.fred_publication import assess_observation,current_summary_value
 r=assess_observation(verified(),NOW)
 assert r['assessed_status']=='LATEST_PUBLIC_RELEASE'
 assert current_summary_value(.9857,dict(status=r['assessed_status']))==.9857
 assert r['last_observation']=='2026-10-16' and r['not_live']

def test_newer_public_observation_missing_locally_is_a_real_failure():
 from contracts.fred_publication import assess_observation
 r=verified();r['public_latest_observation']='2026-10-23'
 assert assess_observation(r,NOW)['assessed_status']=='MISSED_PUBLIC_UPDATE'

def test_old_check_is_dated_last_known_not_an_invented_collection_failure():
 from contracts.fred_publication import assess_observation
 r=verified();r['publication_verified_at_utc']='2026-10-20T12:00:00Z'
 assert assess_observation(r,NOW)['assessed_status']=='LATEST_KNOWN_PUBLIC_RELEASE'

def test_publisher_delay_after_schedule_is_accepted_when_checked():
 from contracts.fred_publication import assess_observation
 now=datetime(2026,10,30,12,tzinfo=timezone.utc);r=verified('M2SL','2026-08-01');r.update(frequency='M',publication_verified_at_utc=now.isoformat(),publication_query_end='2026-10-30',last_scheduled_release_date='2026-10-27',fred_last_updated='2026-09-22')
 assert assess_observation(r,now)['assessed_status']=='LATEST_PUBLIC_RELEASE'
 assert assess_observation(r,now)['release_status']=='AWAITING_PUBLISHER_UPDATE'

def test_source_receipt_is_bound_to_actual_valid_observations_and_asof():
 from contracts.fred_publication import publication_receipt
 obs=[{'date':'2026-10-16','value':'0.9857'},{'date':'2026-10-23','value':'.'},{'date':'2026-10-26','value':'1.0'}]
 r=publication_receipt(obs,'2026-10-23',NOW)
 assert r['public_latest_observation']=='2026-10-16'
 assert r['publication_query_end']=='2026-10-23' and len(r['publication_evidence_sha256'])==64

def test_health_has_no_gap_for_verified_public_term_premium():
 from contracts.macro_health import assess_macro_health
 h=assess_macro_health({'extras':{'fred_series_health':[verified()]}},now=NOW)['source_health']['fred']
 assert h['guidance_gaps']==[]


def test_last_successful_check_age_alone_is_not_a_collection_failure():
 from contracts.macro_health import assess_macro_health
 r=verified();r.update(publication_verified_at_utc='2026-10-20T12:00:00Z',fetched_utc='2026-10-20T12:00:00Z')
 h=assess_macro_health({'extras':{'fred_series_health':[r]}},now=NOW)['source_health']['fred']
 assert h['guidance_gaps']==[]
 assert h['series'][0]['source_refresh_status']=='LAST_SUCCESSFUL_CHECK_OLD'
