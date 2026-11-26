"""Bounded off-session disclosures; never make stale quotes fresh or alter raw rows."""
import csv
import hashlib
import io
import math
from datetime import datetime, timedelta
from canonical_data.session_clock import NEW_YORK, is_xnys_session, previous_xnys_session, session_bounds

VERSION='macro_closed_market_v1'

def _positive(value):
    try:return not isinstance(value,bool) and math.isfinite(float(value)) and float(value)>0
    except (ValueError,TypeError,OverflowError):return False

def capture(directory,now):
    """Archive the actual daily VIX input bytes; do not invent an intraday clock."""
    if is_xnys_session(now.astimezone(NEW_YORK).date()):return None
    path=directory/'avshunter_vix_engine_v3.csv'
    if not path.is_file():return None
    raw=path.read_bytes()
    return {'version':VERSION,'run_mode':'OffSession','vix_source_file':path.name,
        'vix_source_sha256':hashlib.sha256(raw).hexdigest(),'vix_source_csv':raw.decode('utf-8'),
        'instructions':'US cash market closed. Use validated completed-session VIX only as a dated reference, not live. Any stale futures/DXY observations remain unavailable for current direction or gap assessment; venue closure is UNVERIFIED. Use fresh FX/regional evidence when available. Never infer a holiday US cash return or executable trade.'}

def assess(document,now):
    result={'active':False,'limited_groups':[],'observations':[],'vix_reference':None}
    block=document.get('closed_market') or {}
    if block.get('version')!=VERSION or block.get('run_mode')!='OffSession':return result
    if now.tzinfo is None or is_xnys_session(now.astimezone(NEW_YORK).date()):return result
    expected=previous_xnys_session(now.astimezone(NEW_YORK).date())
    if document.get('us_reference_session')!=expected.isoformat():return result
    text=block.get('vix_source_csv')
    # UTF-8 BOM is removed only for parsing; hash the exact producer bytes.
    if not isinstance(text,str) or block.get('vix_source_file')!='avshunter_vix_engine_v3.csv':return result
    if hashlib.sha256(text.encode('utf-8')).hexdigest()!=block.get('vix_source_sha256'):return result
    try:
        rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
        if len(rows)!=1:return result
        v=rows[0]
        if v.get('VIX_Obs_Date')!=expected.isoformat() or v.get('VIX_Source') not in {'YFINANCE','CBOE'} or not _positive(v.get('VIX_Direct')):return result
    except (ValueError,TypeError,csv.Error):return result
    reference={'value':float(v['VIX_Direct']),'observed_session':v['VIX_Obs_Date'],
        'observation_precision':'SESSION_DATE_ONLY','source':v['VIX_Source'],
        'source_sha256':block['vix_source_sha256'],'status':'VALIDATED_COMPLETED_SESSION_REFERENCE','not_live':True}
    result.update(active=True,reference_session=expected.isoformat(),vix_reference=reference)
    earliest=session_bounds(expected)[1]-timedelta(hours=1)
    et=now.astimezone(NEW_YORK)
    fx_weekend=et.weekday()==5 or (et.weekday()==6 and et.hour<17)
    for group in ('us_futures','rates_commodities','fx','volatility'):
        if group in ('us_futures','rates_commodities') and et.weekday()==6 and et.hour>=18:continue
        rows=document.get('groups',{}).get(group) or []
        limited=[];invalid=False
        for row in rows:
            if group=='fx' and row.get('symbol')!='DX-Y.NYB' and not fx_weekend:continue
            try:
                stamp=datetime.fromisoformat(str(row.get('last_bar_utc')).replace('Z','+00:00'))
                if stamp.tzinfo is None or stamp>now or not _positive(row.get('last')):invalid=True;continue
                if row.get('reference') is not None and not _positive(row['reference']):invalid=True;continue
                if stamp<earliest:invalid=True;continue
                if group=='fx' and row.get('symbol')!='DX-Y.NYB':
                    friday=et.date()-timedelta(days=1 if et.weekday()==5 else 2)
                    quote=stamp.astimezone(NEW_YORK)
                    close=quote.replace(hour=17,minute=0,second=0,microsecond=0)
                    if quote.date()!=friday or not close-timedelta(hours=1)<=quote<=close+timedelta(minutes=5):invalid=True;continue
            except (ValueError,TypeError):invalid=True;continue
            limited.append({'group':group,'symbol':row.get('symbol'),'original_last_bar_utc':row.get('last_bar_utc'),
                'availability':'COMPLETED_SESSION_REFERENCE' if group=='volatility' else 'CURRENT_OBSERVATION_UNAVAILABLE_IF_STALE',
                'not_live':True,'venue_closure':'US_CASH_CONFIRMED_CLOSED' if group=='volatility' else 'UNVERIFIED_NOT_INFERRED_FROM_XNYS'})
        if limited and not invalid:
            result['limited_groups'].append(group);result['observations'].extend(limited)
    return result
