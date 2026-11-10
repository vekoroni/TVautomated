"""Exact-byte intake for the three advisory producers. No research or trading authority."""
from __future__ import annotations
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler

FILES = {'usmi': 'avshunter_us_money_index.json', 'news': 'avshunter_macro_enrichment_delta.json',
         'events': 'economic_events_latest.json'}

def _reject_constant(value):
    raise ValueError('non-finite JSON constant is not allowed')

def _decode(raw):
    return json.loads(raw.decode('utf-8-sig'), parse_constant=_reject_constant)

def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def _stamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('timezone missing')
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError) as error:
        raise ValueError('generated_at_utc must be a timezone-aware ISO timestamp') from error

def validate_event_packet(packet):
    if packet.get('schema_version') != 'avshunter_us_economic_event_impact_v1_0':
        raise ValueError('unsupported event schema')
    context = packet.get('run_context') or {}
    if context.get('automatic_execution_enabled') is not False or context.get('manual_review_required') is not True:
        raise ValueError('events must remain manual-review advisory only')
    events = packet.get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('event packet must contain events')
    identities = []
    for event in events:
        if not isinstance(event, dict) or not event.get('event_id') or not event.get('event_name'):
            raise ValueError('every event needs event_id and event_name')
        identities.append(event['event_id'])
    if len(set(identities)) != len(identities):
        raise ValueError('duplicate event identity in packet')

def validate_feed(feed, packet):
    if not isinstance(packet, dict):
        raise ValueError('packet must be a JSON object')
    if feed == 'usmi':
        from contracts.us_money_index_contract import validate_us_money_index_packet
        report = validate_us_money_index_packet(packet)
        if not report['valid']:
            raise ValueError('; '.join(report['errors']))
        return report['packet']
    if feed == 'news':
        from contracts.macro_enrichment_delta import validate_macro_enrichment_delta
        result = validate_macro_enrichment_delta(packet, {'contract_version': 'macro_contract_v1_0'})
        if not result.valid:
            raise ValueError('; '.join(result.errors))
        return packet
    if feed == 'events':
        validate_event_packet(packet)
        return packet
    raise ValueError('unknown feed')

def source_observation_time(feed, packet):
    if feed=='usmi':
        window=packet.get('analysis_window') or {}
        return window.get('as_of_utc') or window.get('generated_utc')
    if feed=='news': return packet.get('as_of_utc')
    context=packet.get('run_context') or {}
    # Recognised native event-producer alias; keep the source clock, never mtime.
    stamp=context.get('information_cutoff_utc') or context.get('information_cutoff') or context.get('generated_utc')
    if stamp:return stamp
    event_times=[event.get('information_cutoff_utc') for event in packet.get('events',[]) if isinstance(event,dict)]
    return max(event_times,key=_stamp) if event_times and all(event_times) else None

class _Redirect(HTTPRedirectHandler):
    def __init__(self, hosts): self.hosts = hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl, self.hosts)
        if urlsplit(req.full_url).hostname != urlsplit(newurl).hostname:
            raise ValueError('cross-host redirect refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def _check_url(url, hosts):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in hosts or parts.username or parts.password:
        raise ValueError('download URL must use HTTPS and a configured host, without embedded credentials')

def _read(source, *, base, config):
    limit = config['max_packet_bytes']
    if str(base).startswith('https://') or str(source).startswith('https://'):
        url = urljoin(str(base), str(source)); hosts = set(config['https_hosts'])
        _check_url(url, hosts)
        headers = {'Accept': 'application/json'}
        token = os.environ.get('AVSH_MACRO_DELIVERY_TOKEN')
        if token: headers['Authorization'] = 'Bearer ' + token
        for attempt in range(config['max_attempts']):
            try:
                with build_opener(_Redirect(hosts)).open(Request(url, headers=headers), timeout=config['timeout_seconds']) as response:
                    raw = response.read(limit + 1)
                break
            except Exception:
                if attempt + 1 == config['max_attempts']:
                    raise ValueError('HTTPS download failed; check endpoint/authentication (URL and credentials redacted)') from None
                time.sleep(2 ** attempt)
    else:
        root = Path(base).resolve().parent
        candidate = (root / source).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError('local source must stay inside manifest directory')
        with candidate.open('rb') as stream: raw = stream.read(limit + 1)
    if len(raw) > limit: raise ValueError('download exceeds configured size limit')
    return raw

@contextmanager
def _lock(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'writer.lock'
    try: fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError: raise ValueError('delivery writer already locked; verify crashed writer before clearing lock') from None
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        yield
    finally: path.unlink(missing_ok=True)

def _deliver(manifest, *, root, config, now=None):
    """Import producer envelopes. Rejected/newer packets cannot overwrite last accepted bytes."""
    root = Path(root); now = now or datetime.now(timezone.utc)
    state_root = root / config['state_directory']; macro = root / config['macro_directory']
    manifest = str(manifest)
    receipt = {'contract_version': 'macro_delivery_receipt_v1', 'authority': 'ADVISORY_ONLY',
               'checked_at_utc': now.isoformat(), 'feeds': {}, 'material_change': False}
    with _lock(state_root):
        if not manifest.startswith('https://') and not Path(manifest).is_file():
            receipt['status'] = 'WAITING_FOR_MANIFEST'
            receipt['feeds'] = {feed: {'status': 'NOT_DELIVERED'} for feed in config['expected_feeds']}
            atomic_json(state_root / 'latest_receipt.json', receipt)
            return receipt
        if manifest.startswith('https://'):
            raw = _read(manifest, base=manifest, config=config)
        else:
            with Path(manifest).open('rb') as stream: raw = stream.read(config['max_packet_bytes'] + 1)
        if len(raw) > config['max_packet_bytes']: raise ValueError('manifest size limit exceeded')
        document = _decode(raw)
        if not isinstance(document, dict) or document.get('contract_version') != 'macro_delivery_manifest_v1' or not isinstance(document.get('packets'), list):
            raise ValueError('unsupported delivery manifest')
        if len(document['packets']) > len(config['expected_feeds']) or any(not isinstance(item, dict) for item in document['packets']):
            raise ValueError('one typed envelope per feed is required')
        registry_path = state_root / 'accepted.json'
        registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
        for envelope in document['packets']:
            feed = envelope.get('feed'); data = None
            try:
                if feed not in config['expected_feeds']: raise ValueError('unknown feed')
                if feed in receipt['feeds']: raise ValueError('multiple envelopes per feed; events must be batched')
                generated = _stamp(envelope.get('generated_at_utc'))
                if generated > now: raise ValueError('FUTURE_TIMESTAMP')
                previous = registry.get(feed)
                if envelope.get('no_material_change') is True:
                    if not previous or envelope.get('sha256') != previous['sha256']:
                        raise ValueError('retained packet does not match accepted identity')
                    if generated < _stamp(previous['generated_at_utc']) or envelope.get('revision') != previous['revision']:
                        raise ValueError('retained packet revision/time does not match accepted identity')
                    receipt['feeds'][feed] = {'status': 'RETAINED', 'sha256': previous['sha256']}
                    continue
                if type(envelope.get('material_change')) is not bool: raise ValueError('material_change must be boolean')
                if not isinstance(envelope.get('revision'), int) or isinstance(envelope.get('revision'), bool) or envelope['revision'] < 0:
                    raise ValueError('revision must be integer')
                data = _read(envelope['source'], base=manifest, config=config)
                digest = hashlib.sha256(data).hexdigest()
                if digest != envelope.get('sha256'): raise ValueError('checksum mismatch')
                packet = _decode(data)
                validate_feed(feed, packet)
                if previous and (generated < _stamp(previous['generated_at_utc']) or envelope['revision'] < previous['revision']):
                    raise ValueError('OUT_OF_ORDER')
                if previous and envelope['revision'] == previous['revision'] and digest != previous['sha256']:
                    raise ValueError('REVISION_COLLISION')
                if feed == 'usmi' and packet.get('packet_revision') is not None and packet['packet_revision'] != envelope['revision']:
                    raise ValueError('USMI_REVISION_MISMATCH')
                source_time = source_observation_time(feed, packet)
                previous_source_time = (previous or {}).get('source_observation_at_utc')
                if previous and not previous_source_time:
                    previous_blob=state_root/'archive'/(previous['sha256']+'.json')
                    if previous_blob.is_file(): previous_source_time=source_observation_time(feed,_decode(previous_blob.read_bytes()))
                if previous and not source_time: raise ValueError('SOURCE_OBSERVATION_TIMESTAMP_MISSING')
                if source_time and previous_source_time and _stamp(source_time)<_stamp(previous_source_time):
                    raise ValueError('SOURCE_OBSERVATION_OUT_OF_ORDER')
                if source_time and _stamp(source_time) > generated:
                    raise ValueError('source generation cannot be after export generation')
                blob = state_root / 'archive' / (digest + '.json')
                blob.parent.mkdir(parents=True, exist_ok=True)
                if not blob.exists(): blob.write_bytes(data)
                # Keep each event version and materialise all accepted event identities, not the last filename.
                published = packet
                if feed == 'events':
                    ledger_path = state_root / 'events.json'
                    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
                    for event in packet['events']:
                        ledger[event['event_id']] = {'event': event, 'source_sha256': digest,
                                                    'generated_at_utc': generated.isoformat()}
                    atomic_json(ledger_path, ledger)
                    published = dict(packet, events=[item['event'] for item in ledger.values()],
                                     delivery_source_manifest={'current_export_sha256':digest,
                                         'event_source_sha256':sorted({item['source_sha256'] for item in ledger.values()})})
                # Event view is intentionally materialised; raw exact bytes remain in archive.
                if feed == 'events': atomic_json(macro / FILES[feed], published)
                else:
                    destination = macro / FILES[feed]; destination.parent.mkdir(parents=True, exist_ok=True)
                    tmp = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
                    try: tmp.write_bytes(data); os.replace(tmp, destination)
                    finally: tmp.unlink(missing_ok=True)
                registry[feed] = {k: envelope[k] for k in ('revision', 'generated_at_utc', 'sha256')}
                registry[feed]['published_path'] = str(macro / FILES[feed])
                if source_time: registry[feed]['source_observation_at_utc']=source_time
                atomic_json(registry_path, registry)
                changed = not previous or digest != previous['sha256']
                receipt['material_change'] |= changed and envelope['material_change']
                receipt['feeds'][feed] = {'status': 'ACCEPTED' if changed else 'DUPLICATE', 'sha256': digest,
                                         'revision': envelope['revision'], 'published_path': str(macro / FILES[feed])}
            except (ValueError, KeyError, OSError) as error:
                safe_error = str(error) if isinstance(error, (ValueError, KeyError)) else type(error).__name__
                identity = hashlib.sha256(data or json.dumps(envelope).encode()).hexdigest()
                atomic_json(state_root / 'quarantine' / (identity + '.receipt.json'),
                            {'feed': feed, 'error': safe_error, 'checked_at_utc': now.isoformat()})
                if data: (state_root / 'quarantine' / (identity + '.json')).write_bytes(data)
                receipt['feeds'][str(feed)] = {'status': 'REJECTED', 'error': safe_error}
        for feed in config['expected_feeds']:
            receipt['feeds'].setdefault(feed, {'status': 'NOT_DELIVERED'})
        receipt['status'] = 'DEGRADED' if any(x['status'] in {'NOT_DELIVERED', 'REJECTED'} for x in receipt['feeds'].values()) else 'COMPLETE'
        atomic_json(state_root / 'latest_receipt.json', receipt)
    return receipt


def deliver(manifest, *, root, config, now=None):
    try:
        return _deliver(manifest, root=root, config=config, now=now)
    except (ValueError, KeyError, OSError) as error:
        if isinstance(error, ValueError) and 'writer already locked' in str(error):
            raise
        receipt = {'contract_version': 'macro_delivery_receipt_v1', 'authority': 'ADVISORY_ONLY',
                   'checked_at_utc': (now or datetime.now(timezone.utc)).isoformat(),
                   'status': 'FAILED', 'material_change': False,
                   'error': 'MANIFEST_OR_TRANSPORT_INVALID',
                   'feeds': {feed: {'status': 'NOT_DELIVERED'} for feed in config['expected_feeds']}}
        atomic_json(Path(root) / config['state_directory'] / 'latest_receipt.json', receipt)
        return receipt
