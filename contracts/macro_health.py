"""Research-feed health: evidence completeness is separate from JSON validity.

Pure assessment; no score, rank, gate, capital or execution authority.
"""
from datetime import datetime, timezone, timedelta
from typing import Mapping

def timestamp_health(value, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return 'TIMEZONE_MISSING'
        return 'FUTURE_TIMESTAMP' if stamp > now else 'DATED'
    except (ValueError, TypeError):
        return 'TIMESTAMP_MISSING'

def assess_macro_health(macro, *, report=None, now=None):
    now = now or datetime.now(timezone.utc)
    extras = macro.get('extras') or {}
    quality = (report or {}).get('data_quality') or {}
    issues = []
    source_health = {}
    overnight = (extras.get('overnight') or {}).get('document') or {}
    groups = overnight.get('groups') or {}
    from contracts.futures_freshness import classify_futures_quote, CONFIG
    for group in ('us_futures', 'rates_commodities', 'fx', 'volatility', 'us_premarket', 'asia', 'europe'):
        rows = groups.get(group) or []
        details = []
        for row in rows:
            state = row.get('state', 'MISSING')
            stale = bool(row.get('stale'))
            stamp_value = row.get('last_bar_utc')
            if stamp_value:
                try:
                    stamp_dt = datetime.fromisoformat(stamp_value.replace('Z', '+00:00'))
                    if stamp_dt.tzinfo is None: raise ValueError('timezone')
                    age = (now-stamp_dt).total_seconds()/60
                    live_clock = group in ('us_futures','rates_commodities','fx','volatility','us_premarket') or state=='INTRADAY'
                    stale = stale or (live_clock and age > CONFIG['stale_after_minutes']) or age < 0
                    if group in ('us_futures', 'rates_commodities') and state not in ('MISSING_REFERENCE','MISSING','FUTURE_QUOTE'):
                        assessed = classify_futures_quote(now, stamp_dt, CONFIG['stale_after_minutes'])
                        state, stale = assessed['state'], assessed['stale']
                    elif age < 0: state = 'FUTURE_QUOTE'
                    elif state == 'CLOSED':
                        from zoneinfo import ZoneInfo
                        expected=now.astimezone(ZoneInfo(row.get('exchange_tz') or 'UTC')).date()
                        # A completed Friday session remains Friday after local midnight on Saturday.
                        # This is a weekend correction; unknown exchange holidays are not inferred.
                        while expected.weekday()>=5: expected-=timedelta(days=1)
                        if row.get('session_date') != expected.isoformat():
                            state, stale = 'STALE_SESSION', True
                except (ValueError, TypeError):
                    state, stale = 'INVALID_TIMESTAMP', True
            elif group in ('us_futures', 'rates_commodities', 'fx', 'volatility'):
                state, stale = 'TIMESTAMP_MISSING', True
            from zoneinfo import ZoneInfo
            et=now.astimezone(ZoneInfo('America/New_York'))
            # A closed Saturday has no live quote obligation. Require an actual
            # late Friday bar; Thursday/early Friday bars remain stale.
            not_live=False
            if et.weekday()==5 and stamp_value and row.get('last') is not None and group in ('us_futures','rates_commodities','fx','volatility','us_premarket'):
                try:
                    quote=datetime.fromisoformat(stamp_value.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York'))
                    close_hour=20 if group=='us_premarket' else 16 if group=='volatility' else 17
                    expected=et.date()-timedelta(days=1)
                    cutoff=quote.replace(hour=close_hour,minute=0,second=0,microsecond=0)-timedelta(minutes=CONFIG['stale_after_minutes'])
                    if quote.date()==expected and quote>=cutoff and quote<=et:
                        state,stale,not_live='MARKET_CLOSED_LAST_SESSION',False,True
                except (ValueError,TypeError): pass
            missing = row.get('last') is None or state.startswith('MISSING')
            details.append({'symbol':row.get('symbol'), 'state':state, 'stale':stale,
                            'missing':missing, 'last_bar_utc':stamp_value,'not_live':not_live})
        expected = {'us_futures':4, 'rates_commodities':3}.get(group, 1)
        symbols={x.get('symbol') for x in rows}
        required={'us_futures':{'ES=F','NQ=F','YM=F','RTY=F'},'rates_commodities':{'ZN=F','CL=F','GC=F'}}.get(group,set())
        incomplete = len(rows)<expected or not required<=symbols or any(x['missing'] for x in details)
        degraded = incomplete or any(x['stale'] for x in details)
        source_health[group] = {'status':'MISSING' if not rows else 'DEGRADED' if degraded else 'AVAILABLE',
                               'expected_minimum':expected, 'received':len(rows), 'instruments':details}
        prefix = 'FUTURES' if group=='us_futures' else group.upper()
        if incomplete: issues.append(prefix+'_MISSING')
        if any(x['stale'] for x in details): issues.append(prefix+'_STALE')
        if any(x['state']=='REOPEN_PENDING' for x in details): issues.append(prefix+'_REOPEN_PENDING')
    module_source = extras.get('macro_module_source_health') or {}
    dxy = module_source.get('dxy_source')
    source_health['dollar_index'] = {'source':dxy, 'as_of':module_source.get('as_of'),
        'status':'MISSING' if not dxy or dxy=='NONE' else 'PROXY' if 'PROXY' in dxy else 'AVAILABLE'}
    if not dxy or dxy=='NONE': issues.append('DOLLAR_INDEX_MISSING')
    elif 'PROXY' in dxy: issues.append('DOLLAR_INDEX_PROXY')
    needed_session=overnight.get('us_reference_session')
    gex=dict(extras.get('gex_source_health') or {})
    gex['authority']='ADVISORY_ONLY_OI_GAMMA_PROXY_NOT_DEALER_INVENTORY'
    if not gex or gex.get('validation_status')!='VALIDATED':
        gex['status']='UNAVAILABLE';issues.append('GEX_UNAVAILABLE')
    elif needed_session and gex.get('session_date')!=needed_session:
        gex['status']='STALE_SESSION';issues.append('GEX_STALE_SESSION')
    else: gex['status']='AVAILABLE'
    source_health['gex']=gex
    dxy_date=module_source.get('dxy_observation_date')
    source_health['dollar_index']['observation_date']=dxy_date
    if dxy and dxy!='NONE':
        if not dxy_date:
            issues.append('DOLLAR_INDEX_DATE_UNVERIFIED')
            source_health['dollar_index']['status']='DATE_UNVERIFIED'
        elif str(dxy_date)>now.date().isoformat():
            issues.append('DOLLAR_INDEX_FUTURE_OBSERVATION')
            source_health['dollar_index']['status']='FUTURE_OBSERVATION'
        elif needed_session and dxy_date<needed_session:
            issues.append('DOLLAR_INDEX_STALE')
            source_health['dollar_index']['status']='STALE'
    if any('FRED' in str(x) for x in module_source.get('errors',[])):
        issues.append('MACRO_MODULE_FRED_ERRORS')
    if macro.get('_builder_metadata', {}).get('schema_validation') == 'FAIL':
        issues.append('SCHEMA_INVALID')
    if quality.get('fred_series_retrieved') == 0:
        issues.append('FRED_NO_COVERAGE')
    elif quality.get('fred_series_retrieved') is None:
        issues.append('FRED_COVERAGE_UNASSESSED')
    elif any(str(item).startswith('FRED ') for item in (report or {}).get('collection_errors', [])):
        issues.append('FRED_PARTIAL_COVERAGE')
    source_health['fred']={'series_retrieved':quality.get('fred_series_retrieved'),
        'status':'MISSING' if quality.get('fred_series_retrieved')==0 else 'UNASSESSED' if quality.get('fred_series_retrieved') is None else 'PARTIAL' if 'FRED_PARTIAL_COVERAGE' in issues else 'AVAILABLE',
        'errors':[x for x in (report or {}).get('collection_errors',[]) if str(x).startswith('FRED ')]}
    from contracts.source_transport import CONFIG as FRED_CONFIG
    series_health=[]
    frequency_aliases={'DAILY':'D','WEEKLY':'W','BIWEEKLY':'BW','MONTHLY':'M','QUARTERLY':'Q','ANNUAL':'A'}
    for item in extras.get('fred_series_health') or []:
        from contracts.fred_publication import assess_observation, GOOD, resolve_guidance
        row=assess_observation(item,now)
        try:
            captured=datetime.fromisoformat(str(row.get('fetched_utc')).replace('Z','+00:00'))
            if captured.tzinfo is None: raise ValueError('timezone')
            row['source_refresh_status']='RECENT_FETCH'
            if captured>now:
                row['source_refresh_status']='INVALID_FETCH_TIMESTAMP'
                issues.append('FRED_MANIFEST_STALE_OR_INVALID')
            elif (now-captured).total_seconds()>FRED_CONFIG['manifest_max_age_hours']*3600:
                row['source_refresh_status']='LAST_SUCCESSFUL_CHECK_OLD'
        except (ValueError,TypeError):
            row['source_refresh_status']='FETCH_TIMESTAMP_MISSING'
            issues.append('FRED_MANIFEST_TIMESTAMP_MISSING')
        if row['source_refresh_status'] in {'INVALID_FETCH_TIMESTAMP','FETCH_TIMESTAMP_MISSING'}: row['assessed_status']='COLLECTION_FAILURE'
        row['freshness_cause']='OBSERVATION_LAG' if row['assessed_status']=='STALE' and row['source_refresh_status']=='RECENT_FETCH' else 'COLLECTION_LAG' if row['source_refresh_status']!='RECENT_FETCH' else 'NONE'
        series_health.append(row)
    coverage_count=quality.get('fred_series_retrieved')
    source_health['fred']['producer_reported_series_retrieved']=coverage_count
    if series_health:
        coverage_count=sum(bool(row.get('last_observation')) and (row.get('provider') or 'FRED')=='FRED' for row in series_health)
        source_health['fred']['series_retrieved']=coverage_count
        source_health['fred']['coverage_basis']='CURRENT_SERIES_MANIFEST'
        if 'FRED_NO_COVERAGE' in issues and coverage_count:
            issues.remove('FRED_NO_COVERAGE');issues.append('FRED_PRODUCER_NO_COVERAGE')
    source_health['fred']['series']=series_health
    if not series_health: issues.append('FRED_SERIES_FRESHNESS_UNASSESSED')
    else:
        from contracts.fred_publication import resolve_guidance
        gaps=resolve_guidance(series_health)
        source_health['fred']['guidance_gaps']=gaps
        source_health['fred']['accepted_latest_public']=[r['series'] for r in series_health if r['assessed_status']=='LATEST_PUBLIC_RELEASE']
        source_health['fred']['publication_lags']=[r['series'] for r in series_health if r['assessed_status']=='EXPECTED_PUBLICATION_LAG']
        source_health['fred']['status']='DEGRADED' if gaps else 'AVAILABLE_WITH_PUBLICATION_LAGS'
        for gap in gaps: issues.append('FRED_SERIES_'+gap['status'])
    rejection = extras.get('us_money_index_status') or {}
    usmi = extras.get('us_money_index') or {}
    if rejection.get('status') == 'INVALID_UNAVAILABLE' and not usmi:
        issues.append('USMI_REJECTED')
    if usmi.get('quality_issues'):
        issues.append('USMI_PARTIAL_EVIDENCE')
    if not usmi:
        issues.append('USMI_UNAVAILABLE')
    if not extras.get('macro_enrichment_delta'):
        issues.append('NEWS_UNAVAILABLE')
    if not extras.get('economic_events'):
        issues.append('EVENTS_UNAVAILABLE')
    stamp = timestamp_health(macro.get('as_of_utc'), now)
    if stamp != 'DATED':
        issues.append(stamp)
    return {'contract_version': 'macro_health_v1', 'authority': 'ADVISORY_ONLY',
            'status': 'DEGRADED' if issues else 'AVAILABLE',
            'schema_status': macro.get('_builder_metadata', {}).get('schema_validation', 'NOT_ASSESSED'),
            'fred_series_retrieved': coverage_count,
            'issues': list(dict.fromkeys(issues)),
            'source_health': source_health,
            'feeds': {'usmi': 'PARTIAL' if usmi and usmi.get('quality_issues') else 'AVAILABLE' if usmi else 'UNAVAILABLE',
                      'news': 'AVAILABLE' if extras.get('macro_enrichment_delta') else 'UNAVAILABLE',
                      'events': 'AVAILABLE' if extras.get('economic_events') else 'UNAVAILABLE'}}

def capture_research_context(macro_dir):
    """Freeze validated research bytes once, before paid synthesis starts."""
    import json, hashlib
    from pathlib import Path
    from contracts.macro_feed_delivery import validate_feed
    result={}
    for feed,name in {'news':'avshunter_macro_enrichment_delta.json','events':'economic_events_latest.json'}.items():
        path=Path(macro_dir)/name
        if not path.is_file():
            result[feed]={'status':'MISSING'}
            continue
        try:
            raw=path.read_bytes();packet=json.loads(raw.decode('utf-8-sig'))
            validate_feed(feed,packet)
            result[feed]={'status':'AVAILABLE','packet':packet,'sha256':hashlib.sha256(raw).hexdigest(),'source_path':str(path)}
            if feed=='events' and packet.get('delivery_source_manifest'):
                result[feed]['accepted_source_sha256']=packet['delivery_source_manifest']['current_export_sha256']
        except (ValueError,OSError) as error:
            result[feed]={'status':'INVALID_UNAVAILABLE','error':str(error)}
    return result

def attach_research_context(macro, macro_dir, *, bound=None):
    """Attach validated News and event view without replacing any core fact."""
    import json
    from pathlib import Path
    from contracts.macro_enrichment_delta import load_macro_enrichment_delta, merge_macro_enrichment_delta
    if bound is not None:
        for feed,entry in bound.items():
            if entry['status']!='AVAILABLE':
                macro.setdefault('extras',{})[feed+'_status']={k:v for k,v in entry.items() if k!='packet'}
                continue
            if feed=='news': macro=merge_macro_enrichment_delta(macro,entry['packet'])
            else: macro.setdefault('extras',{})['economic_events']=entry['packet']
            macro['extras'].setdefault('research_source_manifest',{})[feed]={
                'sha256':entry['sha256'],'source_path':entry['source_path'],
                'as_of_utc':entry['packet'].get('as_of_utc'),
                'generated_from_report_date':entry['packet'].get('generated_from_report_date')}
            if entry.get('accepted_source_sha256'):
                macro['extras']['research_source_manifest'][feed]['accepted_source_sha256']=entry['accepted_source_sha256']
        return macro
    result = macro
    import hashlib
    root = Path(macro_dir)
    receipts = result.setdefault('extras', {}).setdefault('research_source_manifest', {})
    news = root / 'avshunter_macro_enrichment_delta.json'
    if news.is_file():
        try:
            raw = news.read_bytes()
            result = merge_macro_enrichment_delta(result, json.loads(raw.decode('utf-8-sig')))
            receipts = result['extras'].setdefault('research_source_manifest', {})
            receipts['news'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'source_path': str(news),
                                'as_of_utc': result['extras']['macro_enrichment_delta'].get('as_of_utc')}
        except (ValueError, OSError) as error:
            result.setdefault('extras', {})['news_status'] = {'status': 'INVALID_UNAVAILABLE', 'error': str(error)}
    events = root / 'economic_events_latest.json'
    if events.is_file():
        try:
            from contracts.macro_feed_delivery import validate_event_packet
            raw = events.read_bytes()
            packet = json.loads(raw.decode('utf-8-sig'))
            validate_event_packet(packet)
            result.setdefault('extras', {})['economic_events'] = packet
            receipts['events'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'source_path': str(events),
                                  'generated_from_report_date': packet.get('generated_from_report_date')}
            if packet.get('delivery_source_manifest'):
                receipts['events']['accepted_source_sha256']=packet['delivery_source_manifest']['current_export_sha256']
        except (ValueError, OSError) as error:
            result.setdefault('extras', {})['event_status'] = {'status': 'INVALID_UNAVAILABLE', 'error': str(error)}
    return result
