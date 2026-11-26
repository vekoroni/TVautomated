"""Coordinated advisory board/Lab publication. One commit pointer, no model/provider calls."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .cycle_io import atomic, encoded, digest, immutable, writer
from .cycle_narrative import validate
from .cycle_scoring import instant

ROOT = Path(__file__).resolve().parents[1]
POINTER = 'macro_publication_latest.json'


def verify_binding(binding, session, built):
    if not isinstance(binding, dict) or binding.get('authority') != 'ADVISORY_ONLY':
        raise ValueError('Advisory operating-cycle binding required')
    narrative = binding.get('narrative')
    if not isinstance(narrative, dict): raise ValueError('Full narrative required, not a latest-file reference')
    validate(narrative)
    if binding.get('narrative_id') != narrative['narrative_id'] or binding.get('narrative_sha256') != digest(narrative):
        raise ValueError('Narrative binding hash/identity mismatch')
    if narrative['as_of_session'] != session or instant(narrative['information_cutoff_utc']) != instant(built):
        raise ValueError('Board/narrative snapshot clock mismatch')
    if binding.get('status') != narrative['status']: raise ValueError('Narrative status mismatch')
    return binding


def bind_cycle(payload, narrative):
    bound = deepcopy(payload)
    bound['macro_operating_cycle'] = {'authority': 'ADVISORY_ONLY', 'narrative_id': narrative['narrative_id'],
        'narrative_sha256': digest(narrative), 'status': narrative['status'], 'narrative': deepcopy(narrative)}
    verify_binding(bound['macro_operating_cycle'], bound['as_of_session'], bound['built_at_utc'])
    return bound


def render_board(payload, template=None):
    template = template if template is not None else (ROOT / 'macro_board/board_template.html').read_text(encoding='utf-8')
    if template.count('/*__BOARD_PAYLOAD__*/null') != 1: raise ValueError('Board template payload marker mismatch')
    code = (ROOT / 'intelligence-lab/static/macro-cycle.js').read_text(encoding='utf-8')
    if '</script' in code.lower(): raise ValueError('Unsafe inline cycle renderer')
    template = template.replace('/*__MACRO_CYCLE_RENDERER__*/', code)
    return template.replace('/*__BOARD_PAYLOAD__*/null', json.dumps(payload, separators=(',', ':'), ensure_ascii=False, allow_nan=False).replace('</', '<\\/'))


def feed_chain(narrative, root):
    """Bind accepted raw bytes -> analysis-consumed view -> cycle capture.

    The Events union legitimately differs from its last raw export; both hashes
    are checked independently. No source identity is inferred or rewritten.
    """
    inputs = narrative['input_manifest']
    if 'macro_packet' not in inputs:
        return {'status': 'UNASSESSED_NO_FEED_MANIFEST', 'feeds': {}}, {}
    def captured(name):
        entry = inputs[name]
        path = Path(root) / 'operating_cycle' / 'captures' / entry['sha256']
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']: raise ValueError('Captured macro feed hash mismatch')
        return data
    packet = json.loads(captured('macro_packet'))
    source_manifest = packet.get('extras', {}).get('research_source_manifest') or {}
    if not source_manifest:
        return {'status': 'UNASSESSED_NO_FEED_MANIFEST', 'feeds': {}}, {}
    records, originals = {}, {}
    policy = json.loads((ROOT / 'config/macro_delivery_v1.json').read_text(encoding='utf-8-sig'))
    archive = ROOT / policy['state_directory'] / 'archive'
    for feed, key in [('usmi', 'us_money_index'), ('news', 'enrichment'), ('events', 'event_payload')]:
        expected = source_manifest.get(feed) or {}
        if key not in inputs or not expected.get('sha256') or not expected.get('accepted_raw_sha256'):
            raise ValueError('Incomplete accepted-to-analysis feed binding: ' + feed)
        actual = hashlib.sha256(captured(key)).hexdigest()
        if actual != expected['sha256']: raise ValueError('Analysis/cycle feed revision mismatch: ' + feed)
        raw_sha = expected['accepted_raw_sha256']
        if not re.fullmatch('[a-f0-9]{64}', raw_sha): raise ValueError('Invalid accepted raw identity')
        # Read a previously retained bundle copy first, so later retention cannot
        # break an otherwise reproducible saved publication.
        retained = Path(root) / 'accepted_feed_evidence' / (raw_sha + '.json')
        raw = (retained if retained.exists() else archive / (raw_sha + '.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != raw_sha: raise ValueError('Accepted raw feed receipt mismatch: ' + feed)
        originals[raw_sha] = raw
        records[feed] = {'status': 'VERIFIED', 'accepted_revision': expected.get('accepted_revision'),
                          'accepted_raw_sha256': raw_sha, 'analysis_consumed_sha256': actual,
                          'cycle_capture_sha256': inputs[key]['sha256'],
                          'view_kind': 'MATERIALIZED_EVENT_UNION' if feed == 'events' else 'EXACT_ACCEPTED_EXPORT'}
    return {'status': 'VERIFIED_ALL_THREE_FEEDS', 'feeds': records}, originals


def read_bundle(output_dir, publication_id=None):
    root = Path(output_dir)
    if publication_id is None:
        pointer = json.loads((root / POINTER).read_bytes())
        publication_id = pointer['publication_id']
    else:
        pointer = None
    if not re.fullmatch('[a-f0-9]{64}', publication_id): raise ValueError('Invalid macro publication ID')
    folder = root / 'macro_publications' / publication_id
    raw = (folder / 'manifest.json').read_bytes()
    if pointer and hashlib.sha256(raw).hexdigest() != pointer['manifest_sha256']: raise ValueError('Macro commit manifest hash mismatch')
    manifest = json.loads(raw)
    if manifest.get('publication_id') != publication_id or manifest.get('authority') != 'ADVISORY_ONLY':
        raise ValueError('Invalid macro publication manifest')
    files = {}
    for key, expected in [('board', 'board.html'), ('lab', 'lab.json')]:
        entry = manifest['artifacts'][key]
        if entry['file'] != expected: raise ValueError('Unsafe macro artifact path')
        path = folder / expected
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']: raise ValueError('Macro artifact hash mismatch: ' + key)
        files[key] = path
    doc = json.loads(files['lab'].read_bytes())
    binding = verify_binding(doc['macro_operating_cycle'], manifest['as_of_session'], manifest['built_at_utc'])
    if doc.get('macro_publication_id') != publication_id or binding['narrative_id'] != manifest['narrative_id']:
        raise ValueError('Cross-publication narrative mismatch')
    return {'manifest': manifest, 'lab_document': doc, **files}


def publish_bundle(payload, output_dir):
    """Canonical consumers follow POINTER only after both immutable views exist.

    Old direct-file names are compatibility copies, repaired after the canonical
    commit. They are not a multi-file atomic transaction. The Lab board endpoint
    and macro-context endpoint always follow the same verified commit marker.
    """
    root = Path(output_dir)
    verify_binding(payload.get('macro_operating_cycle'), payload['as_of_session'], payload['built_at_utc'])
    from contracts.lab_macro_desk import project, verify
    runtime = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        ROOT / 'macro_board/board_template.html', ROOT / 'intelligence-lab/static/macro-cycle.js',
        Path(__file__), ROOT / 'contracts/lab_macro_desk.py')}
    clean = deepcopy({k: v for k, v in payload.items() if k != 'macro_publication_id'})
    chain, originals = feed_chain(clean['macro_operating_cycle']['narrative'], root)
    clean['macro_operating_cycle']['feed_chain'] = chain
    pid = digest({'payload': clean, 'render_runtime': runtime})
    bound = dict(clean, macro_publication_id=pid)
    with writer(root / 'macro_publication_writer'):
        for sha, data in originals.items(): immutable(root / 'accepted_feed_evidence' / (sha + '.json'), data)
        previous = read_bundle(root) if (root / POINTER).exists() else None
        if previous and previous['manifest']['publication_id'] == pid:
            result = previous
        else:
            old = previous['lab_document'] if previous else None
            legacy = root / 'lab_macro_latest.json'
            if old is None and legacy.exists():
                old = verify(json.loads(legacy.read_bytes()))
            if old and (bound['as_of_session'] < old['as_of_session'] or instant(bound['built_at_utc']) < instant(old['built_at_utc'])):
                raise ValueError('Older cycle cannot replace latest macro publication')
            document = project(bound, old)
            document['macro_publication_id'] = pid
            document.pop('revision', None)
            document['revision'] = digest(document)
            document['published_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            verify(document)
            folder = root / 'macro_publications' / pid
            if (folder / 'lab.json').exists():
                staged = verify(json.loads((folder / 'lab.json').read_bytes()))
                if {k: v for k, v in staged.items() if k != 'published_at_utc'} != {k: v for k, v in document.items() if k != 'published_at_utc'}:
                    raise ValueError('Staged macro publication identity conflict')
                document = staged  # Retry preserves the first staging clock/bytes.
            html = render_board(bound).encode('utf-8')
            lab = encoded(document)
            immutable(folder / 'board.html', html)
            immutable(folder / 'lab.json', lab)
            immutable(root / 'mentality_history' / (document['revision'] + '.json'), lab)
            manifest = {'contract_version': 'macro_publication_v1', 'publication_id': pid,
                        'authority': 'ADVISORY_ONLY', 'as_of_session': bound['as_of_session'],
                        'built_at_utc': bound['built_at_utc'],
                        'narrative_id': bound['macro_operating_cycle']['narrative_id'],
                        'narrative_sha256': bound['macro_operating_cycle']['narrative_sha256'],
                        'content_status': bound['macro_operating_cycle']['status'], 'runtime_hashes': runtime,
                        'lab_revision': document['revision'],
                        'feed_chain': chain,
                        'artifacts': {'board': {'file': 'board.html', 'sha256': hashlib.sha256(html).hexdigest()},
                                      'lab': {'file': 'lab.json', 'sha256': hashlib.sha256(lab).hexdigest()}}}
            raw = encoded(manifest)
            immutable(folder / 'manifest.json', raw)
            atomic(root / POINTER, encoded({'publication_id': pid, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                                           'authority': 'ADVISORY_ONLY'}))
            result = read_bundle(root)
        repairs = []
        for name, source in [('etf_macro_board.html', result['board']), ('lab_macro_latest.json', result['lab'])]:
            try:
                atomic(root / name, source.read_bytes())
            except OSError as exc:
                repairs.append({'view': name, 'status': 'COMPATIBILITY_VIEW_WRITE_FAILED', 'reason': str(exc)})
        return {'status': 'COMMITTED_WITH_COMPATIBILITY_WARNINGS' if repairs else 'COMMITTED',
                'publication_id': pid, 'narrative_id': payload['macro_operating_cycle']['narrative_id'],
                'content_status': payload['macro_operating_cycle']['status'], 'compatibility_warnings': repairs}


def publish_saved_cycle(cycle_folder, output_dir):
    """Import a verified saved cycle into real consumers. No recalculation/acquisition.

    Preserves original clocks and narrative, and archives replaced compatibility
    files before installing the committed bundle. Existing dated artifacts stay.
    """
    source, root = Path(cycle_folder), Path(output_dir)
    pointer = json.loads((source / 'latest.json').read_bytes())
    raw = Path(pointer['json']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer['sha256']: raise ValueError('Saved cycle hash mismatch')
    narrative = json.loads(raw); validate(narrative)
    captured = {}
    for name, entry in narrative['input_manifest'].items():
        expected = Path('captures') / entry['sha256']
        if Path(entry['capture']) != expected: raise ValueError('Unsafe capture identity')
        data = (source / expected).read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('Saved evidence hash mismatch')
        captured[name] = data
    payload = json.loads(captured['board_payload'])
    bound = bind_cycle(payload, narrative)
    with writer(root / 'macro_publication_writer'):
        for name in ('etf_macro_board.html', 'lab_macro_latest.json'):
            path = root / name
            if path.exists():
                data = path.read_bytes()
                immutable(root / 'macro_publications' / 'legacy_captures' / (hashlib.sha256(data).hexdigest() + Path(name).suffix), data)
        for name, data in captured.items():
            entry = narrative['input_manifest'][name]
            immutable(root / 'operating_cycle' / entry['capture'], data)
    from .cycle_io import publish
    publish(root / 'operating_cycle', narrative)
    return publish_bundle(bound, root)
