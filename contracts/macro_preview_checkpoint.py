"""Pure, bounded merges of visible numbered source frames; no browser or network."""
from copy import deepcopy
from contracts.macro_export_receipt import assemble_preview_source

IDENTITY=('source_chat','source_message','expected_sha256','expected_bytes')

def merge_preview_frame(checkpoint, frame, *, max_bytes=10485760, max_no_progress=3):
    for key in IDENTITY:
        if key not in frame or (checkpoint and checkpoint.get(key)!=frame[key]):
            raise ValueError('SOURCE_IDENTITY_CHANGED_OR_MISSING')
    if not all(isinstance(frame[k],str) and frame[k] for k in IDENTITY[:3]):
        raise ValueError('SOURCE_IDENTITY_INVALID')
    digest=frame['expected_sha256']
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('SOURCE_CHECKSUM_INVALID')
    size=frame['expected_bytes']
    if type(size) is not int or not 0<size<=max_bytes:
        raise ValueError('SOURCE_BYTE_LENGTH_INVALID')
    previous=deepcopy(checkpoint or {})
    rows={}
    for number,value in list(previous.get('lines',[]))+list(frame.get('lines',[])):
        if type(number) is not int or not 1<=number<=size+1 or not isinstance(value,str):
            raise ValueError('INVALID_SOURCE_LINE')
        if number in rows and rows[number]!=value:
            raise ValueError('CONFLICTING_SOURCE_LINE')
        rows[number]=value
    if sum(len(v.encode('utf-8')) for v in rows.values())>size:
        raise ValueError('SOURCE_CAPTURE_EXCEEDS_EXPECTED_BYTES')
    terminal=frame.get('last_line') or previous.get('last_line')
    if previous.get('last_line') and frame.get('last_line') and previous['last_line']!=frame['last_line']:
        raise ValueError('SOURCE_TERMINAL_CHANGED')
    if terminal is not None and (type(terminal) is not int or not 1<=terminal<=size+1 or any(n>terminal for n in rows)):
        raise ValueError('INVALID_SOURCE_TERMINAL')
    added=len(rows)-len(dict(previous.get('lines',[])))
    stagnant=0 if added else previous.get('no_progress_runs',0)+1
    result={k:frame[k] for k in IDENTITY}
    result.update(last_line=terminal,lines=sorted(rows.items()),captured_lines=len(rows),
                  added_lines=added,no_progress_runs=stagnant,status='INCOMPLETE')
    if terminal and len(rows)==terminal:
        assemble_preview_source(result['lines'],last_line=terminal,expected_sha256=digest,expected_bytes=size)
        result.update(status='COMPLETE',missing_ranges=[])
    else:
        missing=[];start=None
        for number in range(1,(terminal or max(rows,default=0))+1):
            if number not in rows and start is None:start=number
            if number in rows and start is not None:missing.append([start,number-1]);start=None
        if start is not None:missing.append([start,terminal or max(rows)])
        result['missing_ranges']=missing
        if stagnant>=max_no_progress:result['status']='STOPPED_NO_PROGRESS'
    return result
