"""Versioned current-analysis projection. Archives are not erased or called resolved."""
from copy import deepcopy
from datetime import datetime
import hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='macro_prompt_projection_v2'

class ProjectionBudgetExceeded(ValueError):
    pass

def canonical(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True,default=str).encode('utf-8')

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def policy():
    p=json.loads((ROOT/'config/macro_prompt_projection_v2.json').read_text(encoding='utf-8'))
    if p.get('contract_version')!=VERSION or p.get('completed_session_lookback')!=5:
        raise ValueError('PROMPT_PROJECTION_POLICY_INVALID')
    if type(p.get('max_synthesis_request_bytes')) is not int or not 0<p['max_synthesis_request_bytes']<=700000:
        raise ValueError('PROMPT_PROJECTION_BYTE_BUDGET_INVALID')
    if p.get('max_inline_omission_paths')!=8:raise ValueError('PROMPT_PROJECTION_RECEIPT_LIMIT_INVALID')
    return p

def stamp(value):
    if not isinstance(value,str):return None
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        return d if d.tzinfo is not None and d.utcoffset() is not None else None
    except ValueError:return None

def receipt(records,**metadata):
    return {'policy_version':VERSION,'omitted_count':len(records),'omission_manifest_sha256':digest(records),
        'omission_manifest_hash_basis':'CANONICAL_JSON_OF_FEED_OMISSION_RECORDS',
        'omitted_path_examples':[r['path'] for r in records[:8] if len(r['path'])<=160],
        'archive_policy':'FULL_SOURCE_AND_COMPLETE_OMISSION_MANIFEST_RETAINED; NOT_PROOF_OF_RESOLUTION',**metadata}

def _record(feed,path,value,reason,**extra):
    return dict(feed=feed,path=path,reason=reason,content_sha256=digest(value),**extra)

def usmi_view(packet,*,audit=None):
    revision=(packet.get('source_payload') or {}).get('packet_revision')
    omissions=[]
    def walk(value,path=''):
        if isinstance(value,dict):
            out={}
            for key,item in value.items():
                pointer=path+'/'+key.replace('~','~0').replace('/','~1')
                reason=None
                if key in {'source_payload','timeline_since_monday','revision_history','historical_revisions'}:
                    reason='ARCHIVED_SOURCE_MIRROR_OR_REVISION_HISTORY'
                match=re.match(r'^rev[_ ]?(\d+)(?:_|$)',key,re.I)
                if match and revision is not None and int(match.group(1))<revision:
                    reason='EXPLICIT_SUPERSEDED_REVISION'
                archive=re.match(r'^(?:archived_.*?rev(?:ision)?[_ ]?(\d+)|historical_rev(?:ision)?[_ ]?(\d+))',key,re.I)
                if archive and isinstance(item,(dict,list)) and revision is not None:
                    if int(next(v for v in archive.groups() if v is not None))<revision:
                        reason='EXPLICIT_SUPERSEDED_REVISION'
                if reason:
                    omissions.append(_record('usmi',pointer,item,reason));continue
                out[key]=walk(item,pointer)
            return out
        if isinstance(value,list):return [walk(v,path+'/'+str(i)) for i,v in enumerate(value)]
        return value
    view=walk(packet)
    view.update(source_revision=revision,projection_policy=VERSION,
        projection_omitted_paths=[r['path'] for r in omissions[:8] if len(r['path'])<=160],
        projection_receipt=receipt(omissions))
    if audit is not None:audit.extend(omissions)
    return view

def event_window(packet,*,as_of_utc=None,audit=None):
    """Use explicit source clocks only. Unknown dates/active risks are never aged out."""
    out=deepcopy(packet);rows=packet.get('events',[])
    anchor=stamp(as_of_utc)
    if anchor is None:
        # No inferred wall clock, filename, ID date, mtime or container receipt time.
        out['event_projection']={'policy_version':VERSION,'status':'CLOCK_UNASSESSED_ALL_RETAINED'}
        return out
    from canonical_data.session_clock import previous_xnys_session,session_snapshot
    start=session_snapshot(anchor).last_completed_session
    for _ in range(policy()['completed_session_lookback']-1):start=previous_xnys_session(start)
    kept_indices=set();omissions=[];undated=0;active_count=0;row_clocks={}
    for index,row in enumerate(rows):
        values=[row.get(k) for k in ('information_cutoff_utc','as_of_utc','market_observation_time_utc','observation_time_utc','release_time_utc','original_report_release_time_utc')]
        for key in ('release_time','market_observation_time'):
            if isinstance(row.get(key),dict):values.append(row[key].get('utc'))
        clocks=[d for value in values if (d:=stamp(value)) is not None]
        row_clocks[index]=clocks
        active=any(row.get(k) is True for k in ('active','ongoing','unresolved')) or row.get('lifecycle_status') in {'ACTIVE','ONGOING','PENDING','UPCOMING'}
        undated+=not clocks;active_count+=active
        if active or not clocks or max(clocks).date()>=start:kept_indices.add(index)
    # A current revision/counterargument may require an older event. Preserve
    # exact-ID dependencies transitively; never infer relationships from prose.
    by_id={r.get('event_id'):i for i,r in enumerate(rows) if isinstance(r.get('event_id'),str)}
    def references(value):
        if isinstance(value,str):return {by_id[value]} if value in by_id else set()
        if isinstance(value,dict):return set().union(*(references(v) for v in value.values())) if value else set()
        if isinstance(value,list):return set().union(*(references(v) for v in value)) if value else set()
        return set()
    pending=list(kept_indices)
    while pending:
        for index in references(rows[pending.pop()])-kept_indices:
            kept_indices.add(index);pending.append(index)
    kept=[]
    for index,row in enumerate(rows):
        if index in kept_indices:kept.append(deepcopy(row));continue
        omissions.append(_record('events','/events/'+str(index),row,'DATED_HISTORICAL_CONTEXT_OUTSIDE_ANALYSIS_WINDOW',
            event_id=row.get('event_id'),latest_explicit_clock=max(row_clocks[index]).isoformat()))
    out['events']=kept;out['event_count']=len(kept)
    out['event_projection']=receipt(omissions,source_event_count=len(rows),retained_event_count=len(kept),
        retained_undated_count=undated,retained_explicitly_active_count=active_count,
        window_start_session=start.isoformat(),analysis_as_of_utc=anchor.isoformat(),
        status='CURRENT_WINDOW_WITH_ARCHIVED_HISTORY')
    if audit is not None:audit.extend(omissions)
    return out

def enforce_request_budget(request):
    maximum=policy()['max_synthesis_request_bytes']
    actual=len(json.dumps(request,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    if actual>maximum:
        raise ProjectionBudgetExceeded(f'CURRENT_EVIDENCE_EXCEEDS_PROMPT_BUDGET:{actual}>{maximum}; no current or undated evidence was truncated; inspect projection audit before retry')
    return {'policy_version':VERSION,'request_bytes':actual,'max_request_bytes':maximum}

def persist_audit(directory,audit):
    from contracts.macro_feed_delivery import atomic_json
    name=digest(audit)+'.json';path=Path(directory)/name
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=audit:raise ValueError('PROMPT_AUDIT_COLLISION')
    else:atomic_json(path,audit)
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'canonical_sha256':digest(audit),'omitted_count':len(audit.get('omissions',[])),'policy_version':VERSION}
