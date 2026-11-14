"""Versioned A12 presentation/handoff adapter. No pricing, selection or writes."""
from __future__ import annotations
from copy import deepcopy
from collections import defaultdict
import hashlib
import json

COUNT_FIELDS=('evidence_n','hit_n','failure_n','censored_n','unassessed_n')
MONETISATION_FIELDS=tuple(['monetisation_clock_state','monetisation_clock_basis','monetisation_source_sha256',
    'monetisation_as_of_session','monetisation_observation_sessions']+
    [f'monetisation_{level}_{field}' for level in ('20','30') for field in ('n_q50','n_q80','state',*COUNT_FIELDS)])

def clock_fields(measurement=None,*,source_sha256=None,state=None):
    out={f:None for f in MONETISATION_FIELDS}
    out.update(monetisation_clock_state=state or (measurement.get('state') if measurement else 'UNASSESSED_NOT_PUBLISHED'),
        monetisation_clock_basis='FIRST_OBSERVED_NET_PROFIT; CONDITIONAL_HIT_QUANTILES; NOT_FORECAST_OR_EXPIRY_RULE',
        monetisation_source_sha256=source_sha256)
    if measurement:
        out['monetisation_as_of_session']=measurement.get('as_of_session')
        out['monetisation_observation_sessions']=measurement.get('observation_sessions')
        for level in ('20','30'):
            stats=measurement['levels'][level]
            for field in ('n_q50','n_q80','state',*COUNT_FIELDS):out[f'monetisation_{level}_{field}']=stats[field]
    return out

def validate_packet(packet,run_id):
    if packet.get('schema')!='monetisation_clock_packet_v1' or packet.get('run_id')!=run_id:
        raise ValueError('MONETISATION_PACKET_IDENTITY_MISMATCH')
    if packet.get('authority')!='DESCRIPTIVE_MEASUREMENT_ONLY':raise ValueError('MONETISATION_AUTHORITY_INVALID')
    body={k:v for k,v in packet.items() if k!='content_sha256'}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if digest!=packet.get('content_sha256'):raise ValueError('MONETISATION_PACKET_HASH_MISMATCH')
    return digest

def attach_clock(rows,packet,*,run_id):
    """Match ticker + thesis + exact OCC; never ticker-only or row-position joins."""
    digest=validate_packet(packet,run_id);index=defaultdict(list)
    for r in packet['records']:index[(r['ticker'],r.get('thesis_id'),r['contract_symbol'])].append(r)
    output=[];matched=0
    for row in rows:
        out=deepcopy(row)
        key=(row.get('ticker'),row.get('thesis_id'),row.get('contract_symbol'))
        hit=index.get(key,[]) if all(key) else []
        if len(hit)==1 and (not row.get('trade_idea_id') or not hit[0].get('trade_idea_id') or row['trade_idea_id']==hit[0]['trade_idea_id']):
            out.update(clock_fields(hit[0]['measurement'],source_sha256=digest));matched+=1
        else:out.update(clock_fields(state='UNASSESSED_NO_UNIQUE_EXACT_IDENTITY',source_sha256=digest))
        output.append(out)
    return output,{'matched_rows':matched,'unassessed_identity_rows':len(output)-matched,'source_sha256':digest,'authority':'DISPLAY_ONLY'}
