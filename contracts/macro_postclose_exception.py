"""Dated, single-use user-authorised PostClose exception; never resets budgets."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo


def authorization(root, *, now=None, reason=None, fingerprint=None):
    now = now or datetime.now(timezone.utc)
    path = Path(root)/'config/macro_postclose_exception_v1.json'
    if not path.exists():
        return None
    p = json.loads(path.read_text(encoding='utf-8'))
    if p.get('authority') != 'USER_REQUEST_REMOVE_BLOCK_FOR_ONE_POST_CLOSE':
        return None
    day = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if p.get('day') != day or not datetime.fromisoformat(p['issued_at_utc']) <= now < datetime.fromisoformat(p['expires_at_utc']):
        return None
    if reason is not None and reason != 'POST_CLOSE':
        return None
    if fingerprint is not None and fingerprint != p['fingerprint']:
        return None
    if p.get('max_extra_full_attempts') != 1 or p.get('additional_request_cap_usd') != 1:
        return None
    return p


def build_authorization(root, build_id, *, now=None):
    p = authorization(root, now=now)
    if not p or not build_id:
        return None
    path = Path(root)/'data/macro/delivery/full_build_attempts.sqlite'
    if not path.exists():
        return None
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='postclose_exception_claims'").fetchone():
            return None
        row = db.execute('''SELECT 1 FROM postclose_exception_claims c JOIN attempts a ON a.id=c.build_id
            WHERE c.day=? AND c.fingerprint=? AND c.build_id=? AND a.reason='POST_CLOSE'
            AND a.fingerprint=c.fingerprint AND a.day=c.day''', (p['day'], p['fingerprint'], build_id)).fetchone()
        finished = db.execute('SELECT 1 FROM attempt_outcomes WHERE id=?', (build_id,)).fetchone()
    return p if row and not finished else None
