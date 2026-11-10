"""Publication-aware economic evidence assessment. Display authority only.

Native observation dates are never rewritten. Period labels, release cadence,
collection time and market currency are separate facts.
"""
import calendar,csv,io,json,math
from datetime import date,timedelta,datetime
from pathlib import Path
from pandas.tseries.holiday import USFederalHolidayCalendar
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config/fred_publication_v1.json').read_text(encoding='utf-8'))
GOOD={'FRESH','EXPECTED_PUBLICATION_LAG','LATEST_PUBLIC_RELEASE','LATEST_KNOWN_PUBLIC_RELEASE'}

def publication_receipt(observations,end_date,now):
 import hashlib
 end=date.fromisoformat(str(end_date));valid=[]
 for row in observations:
  try:
   d=date.fromisoformat(str(row['date']));v=float(row['value'])
   if d<=end and math.isfinite(v):valid.append(d)
  except (ValueError,TypeError,KeyError):pass
 if not valid:raise ValueError('No eligible public observation')
 digest=hashlib.sha256(json.dumps(observations,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return dict(public_latest_observation=max(valid).isoformat(),publication_query_end=end.isoformat(),publication_verified_at_utc=now.isoformat(),publication_evidence_sha256=digest)

def current_summary_value(value,row):
 return value if row.get('status') in GOOD else None

def assess_observation(item,now):
 from contracts.source_transport import CONFIG as source_config
 r=dict(item);code=r.get('series');p=CONFIG['series'].get(code,{})
 r.update({k:v for k,v in p.items() if k in {'label','guidance_effect','reason','release_cadence','replacement','equivalence'}})
 freq=str(r.get('frequency') or '').upper().split(',')[0]
 freq={'DAILY':'D','WEEKLY':'W','MONTHLY':'M','QUARTERLY':'Q','ANNUAL':'A'}.get(freq,freq)
 r['not_live']=True
 try:
  observed=date.fromisoformat(str(r.get('last_observation')));end=observed
  if freq in {'M','Q','A'}:
   month=observed.month if freq=='M' else ((observed.month-1)//3+1)*3 if freq=='Q' else 12
   end=observed.replace(month=month,day=calendar.monthrange(observed.year,month)[1])
  raw_age=(now.date()-observed).days;age=(now.date()-end).days
  r.update(observation_period_end=end.isoformat(),age_since_period_end_days=age,native_observation_age_days=raw_age,assessed_age_days=age,date_basis='PERIOD_END_FOR_M_Q_A; NATIVE_DATE_FOR_D_W')
  limit=p.get('max_period_age_days',source_config['max_observation_age_days'].get(freq))
  status='FUTURE_OBSERVATION' if raw_age<0 else 'UNASSESSED_FREQUENCY' if limit is None else 'STALE' if age>limit else 'FRESH'
  if p.get('release_cadence')=='WEEKLY_H10' and raw_age>=0:
   # Latest completed H.10 observation week published by this timestamp.
   from zoneinfo import ZoneInfo
   et=now.astimezone(ZoneInfo('America/New_York'));monday=et.date()-timedelta(days=et.weekday())
   holidays={x.date() for x in USFederalHolidayCalendar().holidays(start=monday,end=monday+timedelta(days=5))}
   release=monday
   while release in holidays:release+=timedelta(days=1)
   released=et.date()>release or (et.date()==release and (et.hour,et.minute)>=(16,15))
   expected=monday-timedelta(days=3 if released else 10)
   r['expected_latest_observation']=expected.isoformat()
   status='EXPECTED_PUBLICATION_LAG' if observed>=expected and raw_age<=limit else 'STALE'
  elif p.get('release_cadence')=='MONTHLY_H6_WEEKLY_OBSERVATIONS' and status=='FRESH':
   status='EXPECTED_PUBLICATION_LAG'
  if status in GOOD and p.get('release_cadence')!='WEEKLY_H10':
   try:
    scheduled=date.fromisoformat(str(r.get('last_scheduled_release_date')))
    updated=date.fromisoformat(str(r.get('fred_last_updated'))[:10])
    if scheduled>updated and (now.date()-scheduled).days>CONFIG['calendar_grace_days']:
     status='OVERDUE_RELEASE'
   except (ValueError,TypeError):pass
  # A publication schedule is diagnostic, not proof of an available update.
  # A recent successful source query takes precedence over an age threshold.
  r['release_status']='AWAITING_PUBLISHER_UPDATE' if status in {'STALE','OVERDUE_RELEASE'} else 'WITHIN_PUBLICATION_POLICY'
  verified=r.get('publication_verified_at_utc')
  if verified:
   try:
    import re
    stamp=datetime.fromisoformat(str(verified).replace('Z','+00:00'))
    latest=date.fromisoformat(str(r.get('public_latest_observation')))
    end=date.fromisoformat(str(r.get('publication_query_end')))
    if stamp.tzinfo is None or stamp>now or latest>end or end>now.date() or not re.fullmatch('[0-9a-f]{64}',str(r.get('publication_evidence_sha256'))):raise ValueError('receipt')
    if raw_age<0:status='FUTURE_OBSERVATION'
    elif latest>observed:status='MISSED_PUBLIC_UPDATE'
    elif latest<observed:status='PUBLICATION_VERIFICATION_INVALID'
    elif not p.get('historical_only') and not p.get('replacement'):
     status='LATEST_KNOWN_PUBLIC_RELEASE' if (now-stamp).total_seconds()>source_config['manifest_max_age_hours']*3600 else 'LATEST_PUBLIC_RELEASE'
   except (ValueError,TypeError):status='PUBLICATION_VERIFICATION_INVALID'
  elif status in {'STALE','OVERDUE_RELEASE'} and not (p.get('historical_only') or p.get('replacement')):
   status='PUBLICATION_UNVERIFIED'
  r['assessed_status']=status
 except (ValueError,TypeError):r['assessed_status']='MISSING'
 r.setdefault('guidance_effect','Economic context only; no execution, ranking or capital authority.')
 return r

def resolve_guidance(rows):
 by={r.get('series'):r for r in rows}
 for r in rows:
  p=CONFIG['series'].get(r.get('series'),{});replacement=by.get(p.get('replacement'),{})
  r['gap_disposition']='NO_GAP' if r['assessed_status'] in GOOD else 'ACTIVE_GUIDANCE_GAP'
  if p.get('historical_only'):
   r['gap_disposition']='HISTORICAL_ONLY_RELATED_COVERAGE' if replacement.get('assessed_status') in GOOD else 'HISTORICAL_ONLY_NO_CURRENT_LEADING_CONFIRMATION'
  elif replacement.get('assessed_status') in GOOD:
   r['gap_disposition']='REPLACED_SAME_MEASURE'
 return [dict(series=r['series'],status=r['assessed_status'],last_observation=r.get('last_observation'),guidance_effect=r['guidance_effect']) for r in rows if r['gap_disposition'] in {'ACTIVE_GUIDANCE_GAP','HISTORICAL_ONLY_NO_CURRENT_LEADING_CONFIRMATION'}]

def parse_oecd_cli(text,end_date):
 expected=CONFIG['oecd']['dimensions'];rows=list(csv.DictReader(io.StringIO(text)));out=[]
 if not rows:raise ValueError('OECD empty response')
 for r in rows:
  if any(r.get(k)!=v for k,v in expected.items()):raise ValueError('OECD dimension mismatch')
  d=date.fromisoformat(r['TIME_PERIOD']+'-01');v=float(r['OBS_VALUE'])
  if not math.isfinite(v):raise ValueError('OECD non-finite value')
  if d<=date.fromisoformat(str(end_date)):out.append((d.isoformat(),v))
 if len({d for d,v in out})!=len(out) or not out:raise ValueError('OECD duplicate or missing observations')
 return sorted(out)
