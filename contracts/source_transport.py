"""Bounded FRED transport. Validate the body inside the retry boundary.

No response body, request URL or credentials enter errors. XML from FRED is
accepted only for recognised API roots; HTML is never data. No cached values
are relabelled as current and no alternate economic series is substituted.
"""
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree
import requests
import json
from pathlib import Path
CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/source_recovery_v1.json').read_text(encoding='utf-8'))['fred']

class FredSourceError(RuntimeError):
    pass

def filter_observation_window(observations, end_date):
    """Preserve native rows while excluding observations beyond the requested as-of."""
    from datetime import date
    end=date.fromisoformat(str(end_date))
    return [row for row in observations if date.fromisoformat(str(row['date']))<=end]

class FredResponse:
    def __init__(self, response, payload, diagnostics):
        self.status_code=response.status_code
        self.headers=getattr(response,'headers',{})
        self.source_diagnostics=diagnostics
        self._payload=payload
    def raise_for_status(self): return None
    def json(self): return self._payload

def _decode(response, path):
    roots={'observations':'observation','seriess':'series','release_dates':'release_date',
           'releases':'release'}
    expected=('observations' if path.endswith('/observations') else
              'release_dates' if path.endswith('/dates') else
              'seriess' if path.endswith('/series') else
              'releases' if path.endswith('/releases') else None)
    try:
        payload=response.json()
        fmt='JSON'
    except ValueError:
        text=getattr(response,'text','')
        if len(text)>16_000_000 or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise FredSourceError('INVALID_PAYLOAD') from None
        if not text.strip(): raise FredSourceError('INVALID_PAYLOAD_EMPTY_BODY')
        try: root=ElementTree.fromstring(text)
        except ElementTree.ParseError: raise FredSourceError('INVALID_PAYLOAD_NON_JSON_XML') from None
        if str(root.tag).lower()=='html': raise FredSourceError('INVALID_PAYLOAD_HTML')
        if root.tag not in roots: raise FredSourceError('INVALID_PAYLOAD_UNRECOGNISED_XML')
        payload={root.tag:[dict(x.attrib) for x in root if x.tag==roots[root.tag]]}
        fmt='XML'
    if not isinstance(payload,dict) or 'error_code' in payload:
        raise FredSourceError('INVALID_PAYLOAD')
    if expected and not isinstance(payload.get(expected),list):
        raise FredSourceError('INVALID_PAYLOAD')
    if expected=='observations' and any(not isinstance(x,dict) or not {'date','value'}<=x.keys()
                                         for x in payload[expected]):
        raise FredSourceError('INVALID_PAYLOAD')
    return payload,fmt

def get_fred_response(url, params, *, get=None, sleep=None, attempts=None, timeout=None):
    get=get or requests.get; sleep=sleep or time.sleep
    attempts=attempts or CONFIG['attempts'];timeout=timeout or CONFIG['timeout_seconds']
    path=urlsplit(url).path
    last='UNAVAILABLE'
    for attempt in range(1,attempts+1):
        try:
            response=get(url,params={**(params or {}),'file_type':'json'},timeout=timeout)
            status=response.status_code
            if status>=400:
                last=f'HTTP_{status}'
                if status!=429 and status<500:
                    raise requests.exceptions.HTTPError(f'FRED {path}: {last}; attempts={attempt}', response=response) from None
            else:
                try:
                    payload,fmt=_decode(response,path)
                    return FredResponse(response,payload,{'attempts':attempt,'format':fmt,
                                        'status':status,'recovered':attempt>1 or fmt!='JSON'})
                except FredSourceError as error: last=str(error)
        except (requests.exceptions.Timeout,requests.exceptions.ConnectionError):
            last='TRANSPORT_UNAVAILABLE'
        if attempt<attempts: sleep(2*attempt)
    raise FredSourceError(f'FRED {path}: {last}; attempts={attempts}') from None
