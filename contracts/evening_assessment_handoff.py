"""Append-only Evening packets and exact-thesis carry-forward; no providers."""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
from domain.evening_assessment import FIELDS, dump

def freeze_assessments(rows,root):
    root=Path(root)
    meta=root/'run_meta.json'
    metadata=json.loads(meta.read_text(encoding='utf-8-sig')) if meta.is_file() else {}
    if str(metadata.get('run_status') or metadata.get('status')).upper() not in {'RUNNING','IN_PROGRESS'}:
        return {'state':'PRESERVED_NON_RUNNING_SNAPSHOT'}
    packet={'schema':'evening_assessment_packet_v1','run_id':root.name,'rows':[
        {k:r.get(k) for k in ('ticker','thesis_id','trade_lane_candidate_id','contract_symbol',*FIELDS)} for r in rows]}
    raw=dump(packet).encode();digest=hashlib.sha256(raw).hexdigest()
    folder=root/'intelligence_lab'/'evening_assessments';folder.mkdir(parents=True,exist_ok=True)
    dest=folder/f'{digest}.json'
    if not dest.exists():
        with dest.open('xb') as stream:stream.write(raw)
    elif dest.read_bytes()!=raw:raise ValueError('EVENING_PACKET_CONTENT_MISMATCH')
    pointer={'schema':packet['schema'],'run_id':root.name,'sha256':digest,'file':dest.name,'rows':len(rows)}
    temp=folder/f'pointer-{uuid4().hex}.tmp'
    try:
        with temp.open('x',encoding='utf-8') as stream:json.dump(pointer,stream)
        os.replace(temp,folder/'latest.json')
    finally:
        if temp.exists():temp.unlink()
    return {'state':'FROZEN','sha256':digest,'rows':len(rows)}

def carry_frozen_assessments(rows,root):
    root=Path(root);folder=root/'intelligence_lab'/'evening_assessments';pointer=folder/'latest.json'
    if not pointer.is_file():return rows,{'state':'UNASSESSED_NO_FROZEN_EVENING_PACKET'}
    p=json.loads(pointer.read_text())
    digest=p.get('sha256','')
    if len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest) or p.get('file')!=digest+'.json':
        raise ValueError('INVALID_EVENING_PACKET_POINTER')
    raw=(folder/p['file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('EVENING_PACKET_HASH_MISMATCH')
    packet=json.loads(raw)
    if packet.get('run_id')!=root.name or p.get('run_id')!=root.name:raise ValueError('EVENING_PACKET_RUN_MISMATCH')
    index=defaultdict(list)
    for row in packet['rows']:index[(row.get('ticker'),row.get('thesis_id'),row.get('trade_lane_candidate_id'))].append(row)
    out=[];matched=0
    for row in rows:
        key=(row.get('ticker'),row.get('thesis_id'),row.get('trade_lane_candidate_id'))
        found=index.get(key,[]) if key[0] and key[1] else []
        # No ticker-only fallback; Morning may legitimately change the contract,
        # but the Evening packet continues to name its ORIGINAL contract.
        if len(found)==1:
            row={**row,**{f:found[0].get(f) for f in FIELDS}};matched+=1
        else:
            row={**row,**{f:None for f in FIELDS},'evening_assessment_route':'EVENING_NOT_ASSESSED',
                'evening_assessment_reasons':'NO_UNIQUE_FROZEN_THESIS_MATCH'}
        out.append(row)
    return out,{'state':'CARRIED_FROZEN_EVENING','matched_rows':matched,'unassessed_rows':len(out)-matched,'sha256':digest}
