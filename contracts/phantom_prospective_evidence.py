"""Immutable local candidate/quote and advisory-publication receipts.

Actual UTC recording times, never historical entry-time reconstruction. No
providers, database writes, Lane B journal, decision authority or fill claims.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from contextlib import closing
import hashlib,json,math,os,sqlite3,tempfile
from datetime import timedelta
from zoneinfo import ZoneInfo
from avshunter.shared.xnys_calendar import is_xnys_session,session_bounds

SCHEMA='phantom_prospective_evidence_v1'
ENTRY_FIELDS=('ticker','thesis_id','trade_idea_id','trade_lane_candidate_id','contract_symbol',
    'contract_occ_symbol','option_symbol','options_direction','primary_direction','direction',
    'options_verdict','options_route_verdict','options_score','contract_strike','contract_dte',
    'contract_bid','contract_ask','contract_iv','contract_delta','planned_hold_sessions',
    'remaining_hold_sessions','anticipated_sessions_q50','anticipated_sessions_q80',
    'scenario_exit_sessions','bar_data_asof','selected_quote_timestamp_utc',
    'quote_provider_timestamp_utc','behaviour_state_hash','behaviour_state_key',
    'layer2__matched_state_key','macro_regime_label','regime','actuarial_evidence_json',
    'actuarial_evidence_state','execution_permission','contract_alternatives_json')
QUOTE_FIELDS=('ticker','quote_date','option_symbol','side','strike','dte','bid','ask',
    'bid_size','ask_size','underlying_price','updated_ts','created_at_utc','source',
    'iv','delta','gamma','theta','vega','greeks_source','greeks_quality')

def _utc_now():return datetime.now(timezone.utc)
def _instant(s):
    try:
        t=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError,TypeError):return None
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [clean(x) for x in v]
    if isinstance(v,float) and not math.isfinite(v):return None
    if v is None or isinstance(v,(str,int,float,bool)):return v
    return str(v)
def blob(value):return json.dumps(clean(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(blob(value)).hexdigest()
def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def db_fingerprint(path):
    result={}
    for p in (Path(path),Path(str(path)+'-wal')):
        if not p.exists():result[str(p)]=None;continue
        stat=p.stat()
        with p.open('rb') as f:head=hashlib.sha256(f.read(65536)).hexdigest()
        result[str(p)]={'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'header_sha256':head}
    return result

SNAPSHOT_METHOD='SQLITE_READ_TRANSACTION_EXACT_KEYS_V1'

def _row_key(row):
    ticker=str(row.get('ticker') or '').strip()
    symbol=next((row.get(k) for k in ('contract_symbol','contract_occ_symbol','option_symbol')
        if isinstance(row.get(k),str) and row[k].strip()),None)
    return ticker,symbol

def _fetch_quote(conn,ticker,session,symbol):
    values=conn.execute('SELECT '+','.join(QUOTE_FIELDS)+' FROM chain_snapshots '
        'WHERE ticker=? AND quote_date=? AND option_symbol=?',(ticker,session,symbol)).fetchall() if symbol else []
    if len(values)>1:raise ValueError('Ambiguous exact-session quote rows')
    return dict(values[0]) if values else None

def _quotes_hash(quotes):
    return digest([{'ticker':t,'option_symbol':s,'quote':clean(quotes[(t,s)])}
        for t,s in sorted(quotes,key=lambda k:(k[0],k[1] or ''))])

def _verify_selected_snapshot(packet):
    """Compare logical selected rows, including absences, not mutable WAL files.

    Each comparison uses one SQLite read transaction. Checkpoints, read-only
    WAL/SHM housekeeping and unrelated writes do not change these observations.
    Relevant row changes still block publication; no historical hash is guessed.
    """
    proof=packet.get('source_snapshot')
    if proof is None:
        # Preserve the original contract for historical v1 receipts.
        if db_fingerprint(packet['source_database'])!=packet['source_database_fingerprint']:
            raise ValueError('Quote store changed between candidate capture and publication')
        return
    if proof.get('method')!=SNAPSHOT_METHOD:raise ValueError('Unknown quote snapshot method')
    frozen={}
    for row in packet['rows']:
        key=(row['ticker'],row['contract_symbol']);quote=row['quote']
        if row['quote_sha256']!=(digest(quote) if quote is not None else None):
            raise ValueError('Captured quote hash mismatch')
        if key in frozen and frozen[key]!=quote:raise ValueError('Conflicting duplicate quote identity')
        frozen[key]=quote
    if len(frozen)!=proof['unique_keys'] or _quotes_hash(frozen)!=proof['selected_rows_sha256']:
        raise ValueError('Captured selected-quote snapshot mismatch')
    with closing(sqlite3.connect(Path(packet['source_database']).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as conn:
        conn.execute('PRAGMA query_only=ON');conn.row_factory=sqlite3.Row
        conn.execute('BEGIN')
        current={key:_fetch_quote(conn,key[0],packet['evidence_session'],key[1]) for key in frozen}
        conn.rollback()
    if _quotes_hash(current)!=proof['selected_rows_sha256']:
        raise ValueError('Selected quote rows changed between candidate capture and publication')

def first_entry_session(recorded):
    """After-close publication cannot claim an entry at that closing quote."""
    day=recorded.astimezone(ZoneInfo('America/New_York')).date()
    while not is_xnys_session(day) or recorded>=session_bounds(day)[1]:day+=timedelta(days=1)
    return day.isoformat()

def _write(root,packet):
    root=Path(root).resolve()
    if root.name!=packet['run_id']:raise ValueError('Capture run-directory mismatch')
    folder=root/'evidence'/'phantom_prospective'
    if not folder.resolve().is_relative_to(root):raise ValueError('Capture escapes run directory')
    folder.mkdir(parents=True,exist_ok=True)
    sha=digest(packet);packet={**packet,'content_sha256':sha};raw=blob(packet)
    dest=folder/(packet['kind'].lower()+'-'+sha+'.json')
    # Durable temp + exclusive link: readers never observe a partially written
    # record and existing evidence is never replaced, even on retries/races.
    fd,name=tempfile.mkstemp(prefix='.capture-',suffix='.tmp',dir=folder)
    temp=Path(name)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        try:os.link(temp,dest)
        except FileExistsError:
            if dest.read_bytes()!=raw:raise ValueError('Capture hash collision or corrupt prior record')
    finally:temp.unlink(missing_ok=True)
    return {'status':'CAPTURED','path':str(dest),'content_sha256':sha,'rows':len(packet['rows']),
            'recorded_at_utc':packet['recorded_at_utc'],'kind':packet['kind']}

def read_packet(path,*,run_id=None,kind=None):
    p=Path(path);packet=json.loads(p.read_text(encoding='utf-8'))
    sha=packet.get('content_sha256');body={k:v for k,v in packet.items() if k!='content_sha256'}
    if packet.get('schema')!=SCHEMA or sha!=digest(body) or p.name!=packet['kind'].lower()+'-'+sha+'.json':
        raise ValueError('Invalid prospective packet/hash')
    if run_id is not None and packet['run_id']!=run_id:raise ValueError('Capture run mismatch')
    if kind is not None and packet['kind']!=kind:raise ValueError('Capture kind mismatch')
    if _instant(packet.get('recorded_at_utc')) is None:raise ValueError('Capture clock missing')
    return packet

def capture_candidates(run_dir,source,rows,*,run_id,session,database,score_version,replay_only=False):
    source=Path(source).resolve();database=Path(database).resolve()
    before=file_hash(source);db_before=db_fingerprint(database);started=_utc_now();records=[];quotes={}
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)) as conn:
        conn.execute('PRAGMA query_only=ON');conn.row_factory=sqlite3.Row
        # A real read transaction pins one logical database snapshot across ALL
        # candidates. Autocommit SELECTs can otherwise observe different commits.
        conn.execute('BEGIN')
        for ordinal,row in enumerate(rows):
            ticker,symbol=_row_key(row)
            key=(ticker,symbol)
            if key not in quotes:
                quotes[key]=_fetch_quote(conn,ticker,session,symbol)
            q=quotes[key];reasons=[]
            if not symbol:reasons.append('NO_SELECTED_CONTRACT')
            elif q is None:reasons.append('NO_UNIQUE_EXACT_SESSION_QUOTE')
            if q is not None:
                received=_instant(q.get('created_at_utc'))
                if received is None:reasons.append('SOURCE_RECEIPT_CLOCK_UNVERIFIED')
                elif received>started:reasons.append('SOURCE_RECEIPT_AFTER_CAPTURE_STARTED')
                try:
                    quoted=datetime.fromtimestamp(float(q['updated_ts']),timezone.utc)
                    if quoted>started:reasons.append('QUOTE_CLOCK_AFTER_CAPTURE_STARTED')
                except (ValueError,TypeError,OverflowError,OSError):reasons.append('SOURCE_QUOTE_CLOCK_UNVERIFIED')
            source_sha=digest(row)
            records.append({'candidate_id':digest([run_id,ordinal,source_sha]),'source_row_ordinal':ordinal,
                'source_row_sha256':source_sha,'ticker':ticker,'contract_symbol':symbol,
                'entry_state':{k:clean(v) for k,v in row.items() if k in ENTRY_FIELDS
                    or ('contract' in k and ('alternative' in k or 'candidates' in k))},
                'quote':clean(q),'quote_sha256':digest(q) if q is not None else None,
                'quote_evidence_state':'CAPTURED_NOT_FILL_PROOF' if not reasons else 'UNASSESSED',
                'limitations':reasons,'execution_authority':'NONE'})
        conn.rollback()
    if file_hash(source)!=before:raise ValueError('Candidate input changed during capture')
    db_after=db_fingerprint(database)
    repo=Path(__file__).resolve().parents[1]
    code={str(p.relative_to(repo)):file_hash(p) for p in (Path(__file__),
        repo/'contracts/phantom_advisory_policy.py',repo/'scripts/phantom_engine.py')}
    meta_path=Path(run_dir)/'run_meta.json';context={}
    if meta_path.exists():
        meta=json.loads(meta_path.read_text(encoding='utf-8-sig'))
        context={'run_meta_sha256':file_hash(meta_path),'recorded_fields':{k:meta.get(k) for k in
            ('release_id','baseline_commit_hash','code_identity','config_identity','run_mode','session_date','canonical_run_id')}}
    recorded=_utc_now()
    return _write(run_dir,{'schema':SCHEMA,'kind':'CANDIDATES','run_id':run_id,
        'evidence_session':session,'recorded_at_utc':recorded.isoformat(),
        'capture_started_at_utc':started.isoformat(),'score_version':score_version,
        'authority':'ADVISORY_NO_PROMOTION','scope':'ALL_PHANTOM_INPUT_ROWS_NOT_FINAL_TRADE_OR_FILL_SET',
        'capture_purpose':'OFFLINE_REPLAY_NOT_ACTUAL_PUBLICATION' if replay_only else 'RUNTIME_PROSPECTIVE',
        'source_path':str(source),'source_sha256':before,'source_database':str(database),
        'source_database_fingerprint':db_before,
        'source_database_fingerprint_after':db_after,
        'source_snapshot':{'method':SNAPSHOT_METHOD,'unique_keys':len(quotes),
            'selected_rows_sha256':_quotes_hash(quotes),'physical_metadata_changed':db_before!=db_after,
            'scope':'FROZEN_EXACT_SESSION_SELECTED_QUOTES_NOT_FULL_SCORING_HISTORY',
            'physical_fingerprint_role':'DIAGNOSTIC_ONLY_NOT_QUOTE_VALUE_PROOF'},
        'run_context':context,'code_sha256':code,'actioned':False,
        'actioned_basis':'NO_EXECUTION_OR_FILL_AUTHORITY',
        'clock_basis':'ACTUAL_CAPTURE_UTC_NEVER_BACKDATED_TO_EVIDENCE_SESSION',
        'rows':records,'universe_count':len(records),'fill_proof':False})

def capture_predictions(run_dir,candidates,payloads,*,run_id):
    packet=read_packet(candidates['path'],run_id=run_id,kind='CANDIDATES')
    if candidates['content_sha256']!=packet['content_sha256']:raise ValueError('Candidate reference mismatch')
    if file_hash(packet['source_path'])!=packet['source_sha256']:raise ValueError('Candidate source changed before publication')
    _verify_selected_snapshot(packet)
    if len(payloads)!=len(packet['rows']):raise ValueError('Prospective population mismatch')
    rows=[]
    for candidate,payload in zip(packet['rows'],payloads):
        if str(payload.get('ticker') or '')!=candidate['ticker'] or payload.get('run_id')!=run_id:
            raise ValueError('Prospective candidate/prediction identity mismatch')
        if payload.get('phantom_promoted_verdict')!='NONE' or payload.get('phantom_ois_adjustment')!=0:
            raise ValueError('Prospective capture requires blocked promotions')
        rows.append({'candidate_id':candidate['candidate_id'],'source_row_ordinal':candidate['source_row_ordinal'],
            'ticker':candidate['ticker'],'contract_symbol':candidate['contract_symbol'],'payload':clean(payload)})
    recorded=_utc_now()
    if recorded<_instant(packet['recorded_at_utc']):raise ValueError('Publication clock precedes candidate capture')
    return _write(run_dir,{'schema':SCHEMA,'kind':'PREDICTIONS','run_id':run_id,
        'recorded_at_utc':recorded.isoformat(),'evidence_session':packet['evidence_session'],
        'score_version':packet['score_version'],'authority':'ADVISORY_NO_PROMOTION',
        'capture_purpose':packet['capture_purpose'],
        'earliest_entry_session':first_entry_session(recorded),
        'candidate_packet_path':str(Path(candidates['path']).resolve()),
        'candidate_packet_sha256':packet['content_sha256'],'rows':rows,'promotion_enabled':False})

def availability_index(paths):
    """Only paired, hash-checked publications establish selection availability.

    Hash conflict, orphan, partial population or ambiguous identity fails
    closed. The actual publication time never becomes a historical timestamp.
    """
    index={}
    for path in paths:
        p=read_packet(path,kind='PREDICTIONS')
        if p.get('promotion_enabled') is not False or p.get('authority')!='ADVISORY_NO_PROMOTION':
            raise ValueError('Prospective publication authority mismatch')
        if p.get('capture_purpose')!='RUNTIME_PROSPECTIVE':raise ValueError('Replay capture cannot establish prospective availability')
        c=read_packet(p['candidate_packet_path'],run_id=p['run_id'],kind='CANDIDATES')
        if c['content_sha256']!=p['candidate_packet_sha256'] or len(c['rows'])!=len(p['rows']):
            raise ValueError('Unpaired prospective publication')
        known=_instant(p['recorded_at_utc'])
        if known<_instant(c['recorded_at_utc']):raise ValueError('Publication precedes capture')
        if p.get('earliest_entry_session')!=first_entry_session(known):raise ValueError('Entry clock was backdated')
        for candidate,prediction in zip(c['rows'],p['rows']):
            if candidate['candidate_id']!=prediction['candidate_id'] or candidate['ticker']!=prediction['ticker'] or candidate['contract_symbol']!=prediction['contract_symbol']:
                raise ValueError('Publication row identity mismatch')
            if not candidate['contract_symbol']:continue
            if prediction['payload'].get('phantom_promoted_verdict')!='NONE' or prediction['payload'].get('phantom_ois_adjustment')!=0:
                raise ValueError('Unexpected decision authority in prospective publication')
            key=(candidate['ticker'],candidate['contract_symbol'])
            if key not in index or known<_instant(index[key]['known_at']):
                index[key]={'known_at':known.isoformat(),'source_run_id':p['run_id'],
                    'earliest_entry_session':p['earliest_entry_session'],
                    'publication_path':str(Path(path).resolve()),'content_sha256':p['content_sha256'],
                    'candidate_id':candidate['candidate_id'],'quote_evidence_state':candidate['quote_evidence_state']}
    return index
