"""One bounded writer, immutable records and content-addressed evidence (no retention deletion)."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import uuid


class WriterBusy(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


@contextmanager
def writer(folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    lock = folder / '.writer.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise WriterBusy(f'MACRO_CYCLE_WRITER_BUSY: {lock}') from None
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        yield
    finally:
        lock.unlink()


def atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists(): tmp.unlink()


def immutable(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data: raise ValueError(f'Immutable artifact collision: {path}')
        return
    # Caller owns the enclosing writer lock; no dated file is replaced.
    with path.open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def capture(folder, name, data):
    sha = hashlib.sha256(data).hexdigest()
    path = Path(folder) / 'captures' / sha
    immutable(path, data)
    return {'name': name, 'sha256': sha, 'bytes': len(data), 'capture': str(Path('captures') / sha)}


def publish(folder, narrative):
    from .cycle_narrative import validate, render
    validate(narrative)
    folder = Path(folder)
    nid = narrative['narrative_id']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', nid): raise ValueError('Unsafe narrative ID')
    path = folder / 'narratives' / (nid + '.json')
    md = path.with_suffix('.md')
    data, view = encoded(narrative), render(narrative).encode('utf-8')
    with writer(folder):
        immutable(path, data); immutable(md, view)
        atomic(folder / 'latest.json', encoded({'narrative_id': nid, 'json': str(path), 'markdown': str(md),
            'sha256': hashlib.sha256(data).hexdigest(), 'markdown_sha256': hashlib.sha256(view).hexdigest(),
            'authority': 'ADVISORY_ONLY', 'status': narrative['status']}))
    return path


def read_records(path):
    path = Path(path)
    if not path.exists(): return []
    data = path.read_bytes()
    if data and not data.endswith(b'\n'): raise ValueError(f'Incomplete append-only journal: {path}')
    rows = [json.loads(line) for line in data.splitlines()]
    if len({r['record_id'] for r in rows}) != len(rows): raise ValueError('Duplicate journal identities')
    return rows


def append_records(path, records):
    path = Path(path)
    with writer(path.parent):
        seen = {r['record_id']: r for r in read_records(path)}
        new = []
        for row in records:
            rid = row['record_id']
            if rid in seen:
                if seen[rid] != row: raise ValueError(f'Conflicting append-only identity: {rid}')
            else:
                new.append(row); seen[rid] = row
        if new:
            with path.open('ab') as stream:
                stream.write(b''.join(encoded(r) + b'\n' for r in new)); stream.flush(); os.fsync(stream.fileno())
        return len(new)
