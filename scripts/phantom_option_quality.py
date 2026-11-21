"""US-options historical mark qualification; never mutates archived values.

Numerical IV range and benchmark eligibility are deliberately separate. The
1%-500% benchmark range is retained, not widened to make coverage look better.
"""
from datetime import datetime
from functools import lru_cache
import math
from zoneinfo import ZoneInfo

IV_BENCHMARK_MIN = .01
IV_BENCHMARK_MAX = 5.0

@lru_cache(maxsize=65536)
def _new_york_session(epoch):
    """Pure timestamp conversion, not a freshness or eligibility cache."""
    return datetime.fromtimestamp(epoch,ZoneInfo('America/New_York')).date().isoformat()

def benchmark_record_eligible(row):
    """Production scoring uses the same mark/quality contract as IV derivation."""
    iv=row.get('iv')
    if not finite(iv) or not IV_BENCHMARK_MIN<=float(iv)<=IV_BENCHMARK_MAX:
        return False
    for key in ('strike','underlying_price','dte'):
        if not finite(row.get(key)) or float(row[key])<=0:
            return False
    if str(row.get('greeks_quality') or '').split(';')[0] not in {
            'OK','VENDOR_COMPLETE','COMPLETE_COMPUTED_EXISTING'}:
        return False
    return quote_assessment(row)[0] is not None

def finite(value):
    try:
        return value is not None and not isinstance(value, bool) and math.isfinite(float(value))
    except (ValueError, TypeError, OverflowError):
        return False

def quote_assessment(row):
    """Only an internally consistent two-sided mark is a point-solve input.

    No un-timestamped last fallback; no ask substitution. Shared EOD updated
    dates establish session identity, not quote/underlying leg synchronisation.
    Missing leg clocks remain explicit; no fake timestamps are generated.
    """
    flags=[]
    bid,ask,mid=(row.get(k) for k in ('bid','ask','mid'))
    if not finite(bid) or not finite(ask):return None,'none',['MISSING_BID_ASK']
    bid,ask=float(bid),float(ask)
    if bid<0 or ask<0:return None,'none',['NEGATIVE_QUOTE']
    if ask<bid:return None,'none',['CROSSED_QUOTE']
    if bid<=0 or ask<=0:return None,'none',['ONE_SIDED_OR_EMPTY_QUOTE']
    if finite(mid) and float(mid)>0:
        mid=float(mid)
        if not bid-1e-8<=mid<=ask+1e-8:return None,'none',['MID_OUTSIDE_SPREAD']
        source='mid'
    else:
        mid=(bid+ask)/2;source='bid_ask_mid';flags.append('mid_rebuilt_from_bid_ask')
    day=row.get('quote_date')
    updated=row.get('updated_ts')
    missing_clock = updated is None or (isinstance(updated, float) and math.isnan(updated))
    if day and not missing_clock:
        try:
            if _new_york_session(float(updated))!=str(day):return None,'none',['QUOTE_SESSION_MISMATCH']
        except (ValueError,TypeError,OverflowError,OSError):return None,'none',['INVALID_QUOTE_TIMESTAMP']
    else:flags.append('QUOTE_SESSION_CLOCK_UNVERIFIED')
    if row.get('underlying_updated_ts') is None:
        flags.append('QUOTE_UNDERLYING_ALIGNMENT_UNVERIFIED')
    elif day:
        try:
            if _new_york_session(float(row['underlying_updated_ts']))!=str(day):return None,'none',['UNDERLYING_SESSION_MISMATCH']
        except (ValueError,TypeError,OverflowError,OSError):return None,'none',['INVALID_UNDERLYING_TIMESTAMP']
    return mid,source,flags

def benchmark_mask(frame):
    """One eligibility mask for every IV statistic; raw population stays intact.

    Compact analytical frames without quote/quality columns remain supported.
    Production derivation always supplies those columns and therefore checks
    them. Quality-unknown stored rows are not promoted to approved benchmarks.
    """
    import pandas as pd
    iv=pd.to_numeric(frame['iv'],errors='coerce')
    mask=iv.between(IV_BENCHMARK_MIN,IV_BENCHMARK_MAX)&iv.map(finite)
    for column in ('strike','underlying_price'):
        values=pd.to_numeric(frame[column],errors='coerce')
        mask &= values.gt(0)&values.map(finite)
    if 'dte' in frame:
        values=pd.to_numeric(frame['dte'],errors='coerce')
        mask &= values.gt(0)&values.map(finite)
    if 'greeks_quality' in frame:
        quality=frame['greeks_quality'].fillna('').astype(str).str.split(';').str[0]
        mask &= quality.isin(['OK','VENDOR_COMPLETE','COMPLETE_COMPUTED_EXISTING'])
    if {'bid','ask','mid'}<=set(frame.columns):
        mask &= frame.apply(lambda row:quote_assessment(row)[0] is not None,axis=1).astype(bool)
    return mask
