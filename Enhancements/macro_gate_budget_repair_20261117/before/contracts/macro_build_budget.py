"""Atomic full-build attempt budget. No provider, pipeline or scheduling calls."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import os
import sqlite3
import uuid

ET = ZoneInfo('America/New_York')


def reserve(root, *, reason, key, now=None, inherited=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Aware clock required')
    root = Path(root)
    policy = json.loads((root/'config/macro_build_schedule_v1.json').read_text())
    limit = policy['max_full_builds_per_et_day']
    if limit != 4:
        raise ValueError('Approved daily cap must remain four')
    day = now.astimezone(ET).date().isoformat()
    path = root/'data/macro/delivery/full_build_attempts.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10, isolation_level=None) as db:
        db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, day TEXT, reason TEXT, fingerprint TEXT, started TEXT, UNIQUE(day, reason, fingerprint))')
        db.execute('CREATE TABLE IF NOT EXISTS stages (id TEXT, stage TEXT, PRIMARY KEY(id,stage))')
        db.execute('BEGIN IMMEDIATE')
        if inherited:
            row = db.execute('SELECT id FROM attempts WHERE id=? AND day=?', (inherited,day)).fetchone()
            if not row:
                raise ValueError('Unknown or previous-day build reservation')
            return inherited
        count = db.execute('SELECT count(*) FROM attempts WHERE day=?',(day,)).fetchone()[0]
        # Preserve a post-close slot; failed attempts still count toward the cap.
        post = db.execute("SELECT count(*) FROM attempts WHERE day=? AND reason='POST_CLOSE'",(day,)).fetchone()[0]
        if count >= limit or (reason != 'POST_CLOSE' and not post and count >= limit-1):
            raise ValueError('DAILY_FULL_BUILD_LIMIT_REACHED')
        if reason in ('MATERIAL_CHANGE','OPEN_CHECK'):
            intraday = db.execute("SELECT count(*) FROM attempts WHERE day=? AND reason IN ('MATERIAL_CHANGE','OPEN_CHECK')",(day,)).fetchone()[0]
            if intraday >= policy['max_intraday_builds']:
                raise ValueError('INTRADAY_BUILD_LIMIT_REACHED')
        token = str(uuid.uuid4())
        try:
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,?)',(token,day,reason,key,now.isoformat()))
        except sqlite3.IntegrityError:
            raise ValueError('BUILD_ALREADY_ATTEMPTED') from None
        db.execute('COMMIT')
        return token


def authorize_stage(root, stage, *, now=None):
    token = reserve(root, reason=os.environ.get('AVSH_BUILD_REASON','MANUAL'),
                    key=os.environ.get('AVSH_BUILD_FINGERPRINT',str(uuid.uuid4())),
                    inherited=os.environ.get('AVSH_FULL_BUILD_ID'), now=now)
    with sqlite3.connect(Path(root)/'data/macro/delivery/full_build_attempts.sqlite',timeout=10) as db:
        try:
            db.execute('INSERT INTO stages VALUES (?,?)',(token,stage))
        except sqlite3.IntegrityError:
            raise ValueError('PAID_STAGE_ALREADY_ATTEMPTED') from None
    os.environ['AVSH_FULL_BUILD_ID'] = token
    return token
