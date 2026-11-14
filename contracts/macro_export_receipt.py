"""Exact source-byte receipts for browser previews and downloaded producer files.

No research construction, schema repair, model calls or trading authority.
"""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from contracts.macro_feed_delivery import atomic_json,deliver,FILES,_decode,source_observation_time,_stamp

def assemble_preview_source(lines, *, last_line, expected_sha256=None, expected_bytes=None, verification_lines=None):
    """Recover a complete numbered file preview, accepting only producer-matching bytes."""
    rows={}
    for number,value in lines:
        if type(number) is not int or not isinstance(value,str):raise ValueError('INVALID_SOURCE_LINE')
        if number in rows and rows[number]!=value:raise ValueError('CONFLICTING_SOURCE_LINE')
        rows[number]=value
    if type(last_line) is not int or last_line<1 or set(rows)!=set(range(1,last_line+1)):
        raise ValueError('INCOMPLETE_SOURCE_PREVIEW')
    values=[rows[i] for i in range(1,last_line+1)]
    # Viewer represents a trailing empty source line as a newline text node.
    if values[-1]=='\n':values[-1]=''
    body='\n'.join(values).encode('utf-8')
    if expected_bytes is not None and len(body)!=expected_bytes:raise ValueError('SOURCE_BYTE_LENGTH_MISMATCH')
    digest=hashlib.sha256(body).hexdigest()
    if expected_sha256:
        if digest!=expected_sha256:raise ValueError('SOURCE_CHECKSUM_MISMATCH')
    elif verification_lines is None:raise ValueError('SECOND_COMPLETE_SOURCE_PASS_REQUIRED')
    else:assemble_preview_source(verification_lines,last_line=last_line,expected_sha256=digest,expected_bytes=len(body))
    _decode(body)
    return body

def identify_feed(packet):
    if packet.get('packet_type')=='US_MONEY_INDEX_CONSOLIDATED':return 'usmi'
    if packet.get('schema_version')=='avshunter_us_economic_event_impact_v1_0':return 'events'
    if packet.get('batch_id') and packet.get('target_macro_contract_version'):return 'news'
    raise ValueError('UNKNOWN_PRODUCER_EXPORT')

def receive_export(path, *, root, config, source_chat, source_message, expected_sha256=None, transport='DOWNLOAD', now=None):
    """Assign receipt sequences and retain other accepted raw packets automatically."""
    root=Path(root);state=root/config['state_directory']
    if (state/'writer.lock').exists():raise ValueError('DELIVERY_WRITER_BUSY')
    with Path(path).open('rb') as stream:raw=stream.read(config['max_packet_bytes']+1)
    if len(raw)>config['max_packet_bytes']:raise ValueError('EXPORT_EXCEEDS_SIZE_LIMIT')
    digest=hashlib.sha256(raw).hexdigest()
    if expected_sha256 and digest!=expected_sha256:raise ValueError('SOURCE_CHECKSUM_MISMATCH')
    packet=_decode(raw);feed=identify_feed(packet)
    if not source_chat or not source_message:raise ValueError('SOURCE_PROVENANCE_REQUIRED')
    expected_chat=config.get('producer_chat_ids',{}).get(feed)
    if expected_chat and source_chat!=expected_chat:raise ValueError('SOURCE_CHAT_FEED_MISMATCH')
    registry_path=state/'accepted.json';registry=_decode(registry_path.read_bytes()) if registry_path.exists() else {}
    previous=registry.get(feed,{})
    now=now or datetime.now(timezone.utc);stamp=now.isoformat()
    incoming=(root/config['default_manifest']).parent;incoming.mkdir(parents=True,exist_ok=True)
    target=incoming/(digest+'.json')
    if target.exists():
        if target.read_bytes()!=raw:raise ValueError('RAW_ARCHIVE_COLLISION')
    else:target.write_bytes(raw)
    revision=packet.get('packet_revision') if feed=='usmi' else previous.get('revision',0)+(digest!=previous.get('sha256'))
    packets=[{'feed':feed,'revision':revision,'generated_at_utc':stamp,'sha256':digest,'source':target.name,'material_change':True,
              'source_chat':source_chat,'source_message':source_message,'transport':transport,
              'generation_time_basis':'TRANSPORT_RECEIPT_NOT_SOURCE_OBSERVATION'}]
    for other in config['expected_feeds']:
        if other==feed or other not in registry:continue
        old=registry[other]
        packets.append({'feed':other,'revision':old['revision'],'generated_at_utc':stamp,'sha256':old['sha256'],'no_material_change':True})
    manifest={'contract_version':'macro_delivery_manifest_v1','packets':packets}
    manifest_path=incoming/(digest+'.manifest.json');atomic_json(manifest_path,manifest)
    receipt=deliver(str(manifest_path),root=root,config=config,now=now)
    receipt_path=state/'transport_receipts'/(digest+'.json')
    record={'source_chat':source_chat,'source_message':source_message,'transport':transport,'received_at_utc':stamp,
            'feed':feed,'sha256':digest,'bytes':len(raw),'manifest':str(manifest_path),'delivery':receipt}
    if receipt_path.exists():
        previous_bytes=receipt_path.read_bytes();previous_hash=hashlib.sha256(previous_bytes).hexdigest()
        history_path=receipt_path.parent/'history'/(previous_hash[:32]+'.json')
        if history_path.exists():
            if hashlib.sha256(history_path.read_bytes()).hexdigest()!=previous_hash:raise ValueError('TRANSPORT_RECEIPT_HISTORY_COLLISION')
        else:atomic_json(history_path,_decode(previous_bytes))
        record['previous_transport_receipt_sha256']=previous_hash
    atomic_json(receipt_path,record)
    if receipt['feeds'].get(feed,{}).get('status') in {'ACCEPTED','DUPLICATE'}:
        atomic_json(root/config['default_manifest'],manifest)
    return record

def receive_queue(root,config):
    """Runner processes durable metadata receipts, never guesses at repeated filenames."""
    root=Path(root);queue=root/config.get('export_queue_directory','dropbox/macro/exports')
    state=root/config['state_directory'];results=[];pending=[]
    for meta_path in sorted(queue.glob('*.export.json')):
        meta=_decode(meta_path.read_bytes());digest=meta.get('sha256','')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('INVALID_QUEUE_CHECKSUM')
        if (state/'transport_receipts'/(digest+'.json')).exists():continue
        path=(queue/meta['source']).resolve()
        if not path.is_relative_to(queue.resolve()):raise ValueError('EXPORT_QUEUE_PATH_ESCAPE')
        with path.open('rb') as stream:raw=stream.read(config['max_packet_bytes']+1)
        if len(raw)>config['max_packet_bytes']:raise ValueError('EXPORT_EXCEEDS_SIZE_LIMIT')
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('SOURCE_CHECKSUM_MISMATCH')
        packet=_decode(raw);feed=identify_feed(packet);observed=source_observation_time(feed,packet)
        if not observed:raise ValueError('SOURCE_OBSERVATION_TIMESTAMP_MISSING')
        pending.append((_stamp(observed),path,meta))
    for _,path,meta in sorted(pending,key=lambda item:(item[0],item[1].name)):
        results.append(receive_export(path,root=root,config=config,source_chat=meta['source_chat'],source_message=meta['source_message'],expected_sha256=meta['sha256'],transport=meta.get('transport','DOWNLOAD')))
    return results
