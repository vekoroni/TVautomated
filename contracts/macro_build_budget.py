"""Atomic paid-FULL budget; preflight history is preserved without buying a slot.

The first attempted paid stage charges one FULL, even if that stage fails.
No providers or pipelines are called here. Legacy historical FULL rows still count.
"""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import hashlib,json,os,sqlite3,uuid

ET=ZoneInfo('America/New_York')
CHARGED="(a.reason='HISTORICAL_FULL' OR EXISTS (SELECT 1 FROM stages s WHERE s.id=a.id))"

def _path(root):return Path(root)/'data/macro/delivery/full_build_attempts.sqlite'

def _init(db):
    db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, day TEXT, reason TEXT, fingerprint TEXT, started TEXT, UNIQUE(day,reason,fingerprint))')
    db.execute('CREATE TABLE IF NOT EXISTS stages (id TEXT, stage TEXT, PRIMARY KEY(id,stage))')
    db.execute('CREATE TABLE IF NOT EXISTS attempt_outcomes (id TEXT PRIMARY KEY, finished TEXT, exit_code INTEGER, status TEXT)')

def _policy(root):
    policy=json.loads((Path(root)/'config/macro_build_schedule_v1.json').read_text())
    if policy['max_full_builds_per_et_day']!=4:raise ValueError('Approved daily cap must remain four')
    return policy

def _check(db,day,reason,policy):
    paid=db.execute('SELECT a.reason FROM attempts a WHERE a.day=? AND '+CHARGED,(day,)).fetchall()
    post=any(r[0]=='POST_CLOSE' for r in paid)
    if len(paid)>=4 or (reason!='POST_CLOSE' and not post and len(paid)>=3):
        raise ValueError('DAILY_FULL_BUILD_LIMIT_REACHED')
    if reason in ('OPEN_CHECK','MATERIAL_CHANGE') and sum(r[0] in ('OPEN_CHECK','MATERIAL_CHANGE') for r in paid)>=policy['max_intraday_builds']:
        raise ValueError('INTRADAY_BUILD_LIMIT_REACHED')

def reserve(root,*,reason,key,now=None,inherited=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:raise ValueError('Aware clock required')
    policy=_policy(root);day=now.astimezone(ET).date().isoformat()
    path=_path(root);path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path,timeout=10,isolation_level=None) as db:
        _init(db);db.execute('BEGIN IMMEDIATE')
        if inherited:
            if not db.execute('SELECT id FROM attempts WHERE id=? AND day=?',(inherited,day)).fetchone():
                raise ValueError('Unknown or previous-day build reservation')
            return inherited
        _check(db,day,reason,policy)
        token=str(uuid.uuid4())
        try:db.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',(token,day,reason,key,now.isoformat()))
        except sqlite3.IntegrityError:raise ValueError('BUILD_ALREADY_ATTEMPTED') from None
        db.execute('COMMIT');return token

def authorize_stage(root,stage,*,now=None):
    if stage not in ('MACRO_SYNTHESIS','BOARD_NARRATIVE'):raise ValueError('Unknown paid build stage')
    now=now or datetime.now(timezone.utc)
    token=reserve(root,reason=os.environ.get('AVSH_BUILD_REASON','MANUAL'),
                  key=os.environ.get('AVSH_BUILD_FINGERPRINT',str(uuid.uuid4())),
                  inherited=os.environ.get('AVSH_FULL_BUILD_ID'),now=now)
    with sqlite3.connect(_path(root),timeout=10,isolation_level=None) as db:
        _init(db);db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT day,reason FROM attempts WHERE id=?',(token,)).fetchone()
        already=db.execute('SELECT 1 FROM stages WHERE id=? LIMIT 1',(token,)).fetchone()
        if not already:_check(db,row[0],row[1],_policy(root))
        if db.execute('SELECT 1 FROM attempt_outcomes WHERE id=?',(token,)).fetchone():
            raise ValueError('BUILD_ATTEMPT_ALREADY_FINISHED')
        try:db.execute('INSERT INTO stages VALUES (?,?)',(token,stage))
        except sqlite3.IntegrityError:raise ValueError('PAID_STAGE_ALREADY_ATTEMPTED') from None
        db.execute('COMMIT')
    os.environ['AVSH_FULL_BUILD_ID']=token
    return token

def finish_attempt(root,token,exit_code,*,now=None):
    """Append one outcome; never delete, redate or refund a paid attempt."""
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('Aware clock required')
    with sqlite3.connect(_path(root),timeout=10,isolation_level=None) as db:
        _init(db);db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT reason FROM attempts WHERE id=?',(token,)).fetchone()
        if not row:raise ValueError('Unknown build reservation')
        paid=row[0]=='HISTORICAL_FULL' or db.execute('SELECT 1 FROM stages WHERE id=? LIMIT 1',(token,)).fetchone() is not None
        status=('COMPLETE' if exit_code in (0,2) else 'FAILED_PAID_STAGE') if paid else 'PREFLIGHT_ONLY'
        db.execute('INSERT OR IGNORE INTO attempt_outcomes VALUES (?,?,?,?)',(token,now.isoformat(),int(exit_code),status))
        db.execute('COMMIT')
    return status

def budget_status(root,day):
    """Read-only accounting. Legacy reservations with no paid stage cost no FULL."""
    path=_path(root)
    empty={'paid_attempts':0,'preflight_only_reservations':0,'last_paid_started':None,'completed_reasons':[]}
    if not path.exists():return empty
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True) as db:
        rows=db.execute('SELECT a.reason,a.started FROM attempts a WHERE a.day=? AND '+CHARGED+' ORDER BY a.started',(day,)).fetchall()
        total=db.execute('SELECT count(*) FROM attempts WHERE day=?',(day,)).fetchone()[0]
        outcomes=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attempt_outcomes'").fetchone()
        completed=db.execute("SELECT a.reason FROM attempts a JOIN attempt_outcomes o ON a.id=o.id WHERE a.day=? AND o.status='COMPLETE'",(day,)).fetchall() if outcomes else []
    return {'paid_attempts':len(rows),'preflight_only_reservations':total-len(rows),
            'last_paid_started':rows[-1][1] if rows else None,'completed_reasons':[r[0] for r in completed]}

def build_fingerprint(root,reason,day):
    """Stable input/code identity: capture-time-only changes do not buy retries."""
    root=Path(root);identity={'reason':reason,'day':day,'files':{},'market_groups':{}}
    for name in ('config/macro_build_schedule_v1.json','contracts/macro_market_refresh_gate.py',
                 'contracts/macro_health.py','contracts/macro_source_sessions.py',
                 'contracts/macro_build_budget.py','scripts/scheduled_macro_builds.py',
                 'contracts/macro_prompt_projection.py','contracts/macro_prompt_policy.py',
                 'config/macro_prompt_projection_v2.json','domain/macro_input_governance.py','build_macro_json.py',
                 'Enhancements/colab/avshunter_market_intelligence_v5_4_3.py',
                 'dropbox/macro/avshunter_us_money_index.json',
                 'dropbox/macro/avshunter_macro_enrichment_delta.json',
                 'dropbox/macro/economic_events_latest.json'):
        p=root/name;identity['files'][name]=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else 'MISSING'
    candidates=list((root/'dropbox/market_data').glob('overnight_????????_??????.json'))
    if candidates:
        latest=max(candidates,key=lambda p:p.stat().st_mtime)
        identity['market_groups']=json.loads(latest.read_text(encoding='utf-8-sig')).get('groups',{})
    return hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
