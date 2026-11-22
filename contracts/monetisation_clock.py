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


def complete_evening_history(rows, run_root, database):
    """Bounded reuse-only exact-contract measurement for a NEW running Evening.

    Existing completed runs never acquire files through this function. Source
    and packet are create-only; a changed source is an error, not a replacement.
    Missing stores/clocks are explicit, not a fabricated n or provider fallback.
    """
    from pathlib import Path
    from datetime import date
    from avshunter.c12_outcome.adapters.monetisation_history import instant
    root=Path(run_root);rid=root.name;db=Path(database)
    meta_path=root/'run_meta.json'
    if not meta_path.is_file():return rows,{'state':'UNASSESSED_NO_RUNNING_RUN_RECEIPT'}
    meta=json.loads(meta_path.read_text(encoding='utf-8-sig'))
    if str(meta.get('run_status') or meta.get('status','')).upper() not in {'RUNNING','IN_PROGRESS'}:
        return rows,{'state':'PRESERVED_NON_RUNNING_SNAPSHOT'}
    if not db.is_file():return rows,{'state':'UNASSESSED_SAVED_HISTORY_STORE_UNAVAILABLE'}
    if len(rows)>5000:return rows,{'state':'UNASSESSED_EVENING_HISTORY_BATCH_LIMIT','rows':len(rows),'limit':5000}
    keys=('ticker','thesis_id','trade_idea_id','contract_symbol','bar_data_asof',
          'anticipated_valued_at_utc','quote_provider_timestamp_utc')
    source={'run_id':rid,'source_kind':'evening','rows':[{k:r.get(k) for k in keys} for r in rows]}
    cutoff=instant(meta.get('evidence_cutoff_utc'))
    if cutoff is None:return rows,{'state':'UNASSESSED_EVENING_DECISION_CUTOFF_MISSING'}
    try:as_of=date.fromisoformat(str(meta.get('session_date')))
    except ValueError:return rows,{'state':'UNASSESSED_EVENING_REFERENCE_SESSION_MISSING'}
    folder=root/'intelligence_lab';folder.mkdir(parents=True,exist_ok=True)
    src=folder/f'evening_clock_source_{rid}.json'
    raw=json.dumps(source,sort_keys=True,separators=(',',':'),allow_nan=False)
    if src.exists():
        if src.read_text(encoding='utf-8')!=raw:raise ValueError('FROZEN_EVENING_CLOCK_SOURCE_CHANGED')
    else:
        with src.open('x',encoding='utf-8') as stream:stream.write(raw)
    dest=folder/f'evening_monetisation_clock_{rid}.json'
    if dest.is_file():packet=json.loads(dest.read_text(encoding='utf-8'))
    else:
        from scripts.publish_monetisation_clock import publish_saved_clock
        packet=publish_saved_clock(root,db,as_of=as_of,decision_cutoff=cutoff,
                                   source_kind='evening',source_path=src)
        with dest.open('x',encoding='utf-8') as stream:json.dump(packet,stream,allow_nan=False)
    if (packet.get('source_rows_sha256')!=hashlib.sha256(src.read_bytes()).hexdigest()
            or packet.get('source_kind')!='evening'):
        raise ValueError('EVENING_MEASUREMENT_SOURCE_MISMATCH')
    output,receipt=attach_clock(rows,packet,run_id=rid)
    return output,{'state':'COMPLETE_DESCRIPTIVE_MEASUREMENT',**receipt,'summary':packet['summary']}
