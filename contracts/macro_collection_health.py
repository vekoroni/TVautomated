"""Pure classification of raw collection errors and an evidenced VIX fallback.

Keep raw error receipts intact. Only an exact Cboe VIX HTTP failure can be
recovered, and only by a separately dated, finite, session-valid yfinance row.
All other collection errors remain fatal. Stored claims of recovery are ignored.
"""
from datetime import datetime
import math
import re
from canonical_data.session_clock import session_snapshot
from contracts.macro_source_sessions import classify_source_session
from contracts.futures_freshness import CONFIG

CBOE_VIX = 'https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json'
PRIMARY_HTTP_ERROR = re.compile(re.escape(CBOE_VIX) + r': HTTP [45]\d{2}\Z')


def _positive(value):
    try:
        return not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError, OverflowError):
        return False


def validate_vix_fallback(document, now):
    rows=(document.get('groups') or {}).get('volatility') or []
    if len(rows)!=1 or rows[0].get('symbol') not in {'VIX','^VIX'}:
        return {'status':'INVALID','reason':'VIX_IDENTITY_OR_POPULATION_UNVERIFIED'}
    row=rows[0]
    if row.get('source')!='YFINANCE':
        return {'status':'INVALID','reason':'YFINANCE_FALLBACK_NOT_PRESENT'}
    if not _positive(row.get('last')) or not _positive(row.get('reference')):
        return {'status':'INVALID','reason':'FALLBACK_VALUE_OR_REFERENCE_INVALID'}
    try:
        expected=session_snapshot(now).last_completed_session.isoformat()
        if document.get('us_reference_session')!=expected or row.get('reference_label')!=f'VIX close {expected}':
            return {'status':'INVALID','reason':'FALLBACK_REFERENCE_SESSION_UNVERIFIED'}
        stamp=datetime.fromisoformat(str(row.get('last_bar_utc')).replace('Z','+00:00'))
        if stamp.tzinfo is None or stamp>now:
            return {'status':'INVALID','reason':'FALLBACK_TIMESTAMP_INVALID'}
        change=row.get('change_pct')
        calculated=(float(row['last'])/float(row['reference'])-1)*100
        if (isinstance(change,bool) or not math.isfinite(float(change))
                or abs(float(change)-calculated)>0.00001):
            return {'status':'INVALID','reason':'FALLBACK_CHANGE_INCONSISTENT'}
        assessed=classify_source_session('volatility',row,now,CONFIG['stale_after_minutes'])
        if not assessed or assessed['stale']:
            return {'status':'INVALID','reason':'FALLBACK_SESSION_NOT_READY','session_assessment':assessed}
    except (ValueError,TypeError,OverflowError):
        return {'status':'INVALID','reason':'FALLBACK_TIMESTAMP_OR_REFERENCE_INVALID'}
    return {'status':'VALIDATED','source':'YFINANCE','reference_session':expected,
            'last_bar_utc':row['last_bar_utc'],'not_live':assessed['not_live'],
            'session_assessment':assessed}


def assess_collection(document, now):
    raw=[]
    for name in ('market_refresh','futures_refresh'):
        errors=(document.get(name) or {}).get('errors') or []
        if not isinstance(errors,list):
            errors=[f'{name}: COLLECTION_ERROR_LIST_INVALID']
        for error in errors:
            if error not in raw: raw.append(error)
    primary=[e for e in raw if isinstance(e,str) and PRIMARY_HTTP_ERROR.fullmatch(e)]
    fallback_rows=[r for r in (document.get('groups') or {}).get('volatility') or []
                   if r.get('source')=='YFINANCE']
    fallback=validate_vix_fallback(document,now) if primary or fallback_rows else {'status':'NOT_USED'}
    recovered=primary if fallback['status']=='VALIDATED' else []
    fatal=[e for e in raw if e not in recovered]
    if fallback['status']=='INVALID':
        fatal.append('VIX_FALLBACK_INVALID:'+fallback['reason'])
    warnings=[{'code':'VIX_PRIMARY_SOURCE_FAILED_FALLBACK_VALIDATED','primary_error':e,
               'fallback_source':'YFINANCE','fallback_last_bar_utc':fallback['last_bar_utc'],
               'not_live':fallback['not_live']} for e in recovered]
    if fallback['status']=='VALIDATED' and not primary:
        warnings.append({'code':'VIX_FALLBACK_USED','fallback_source':'YFINANCE',
                         'fallback_last_bar_utc':fallback['last_bar_utc'],'not_live':fallback['not_live']})
    return {'version':'macro_collection_health_v1',
            'status':'FAILED' if fatal else 'WARNING' if warnings else 'AVAILABLE',
            'raw_errors':raw,'fatal_errors':fatal,'warnings':warnings,'vix_fallback':fallback}
