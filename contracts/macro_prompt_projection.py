"""Deterministic current-evidence projection, with explicit omission provenance.

Original files and publication evidence remain complete. This is not a new
producer packet and does not claim omitted details were read by the model.
"""
import hashlib
import json
from collections import Counter


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def _receipt(value, omitted):
    return {'projection_input_canonical_sha256': hashlib.sha256(encode(value).encode()).hexdigest(),
            'omitted_fields': sorted(omitted), 'policy': 'CURRENT_EVIDENCE_PROJECTION_FULL_SOURCE_ARCHIVED'}


def select(value, fields):
    if not isinstance(value, dict):
        return value
    out = {k: v for k, v in value.items() if k in fields}
    omitted = set(value) - set(out)
    if omitted:
        out['_projection'] = _receipt(value, omitted)
    return out


def research_view(feed, packet):
    if feed == 'events':
        out = {k: v for k, v in packet.items() if k != 'events'}
        # Raw-byte transport proof belongs in the immutable archive, not in an
        # analysis prompt. Keep its checksum, length, clocks and limitations.
        for key in ('source_export_lineage', 'latest_source_export_lineage'):
            if isinstance(out.get(key), dict):
                out[key] = select(out[key], set(out[key]) - {'original_base64'})
        # Keep heterogeneous release clocks, revised values, qualitative results,
        # transmission, limitations and every unknown/new substantive field.
        # A whitelist would silently lose later producers' alternate field names.
        background = {'sources', 'definition', 'event_definition'}
        out['events'] = [select(row, set(row) - background) for row in packet.get('events', [])]
        out['event_count'] = len(out['events'])
        return out
    if feed == 'news':
        # Keep index models, merge deltas, source clocks and every substantive
        # field. Exact repeated research is shared by lossless references below.
        mirrors = {'schema_hygiene', 'validation_rules', 'audit'}
        return select(packet, set(packet) - mirrors)
    return packet


def compact_context(context):
    """Replace only named research mirrors; preserve all governed market records."""
    out = dict(context)
    out['sources'] = dict(context['sources'])
    out['input_consumption_ledger'] = {k: dict(v) for k, v in context['input_consumption_ledger'].items()}
    for feed in ('news', 'events'):
        key = feed + '_research_advisory'
        if key in out['sources']:
            out['sources'][key] = research_view(feed, out['sources'][key])
            if key in out['input_consumption_ledger']:
                out['input_consumption_ledger'][key]['mode'] = 'CURRENT_EVIDENCE_PROJECTION'
    out['projection_policy'] = 'Research details omitted by name, never character-truncated; all market records retained'
    return out


def _backward_references(value):
    """Lossless exact subtree references; all unique values remain in this document.

    Only sizeable containers/strings are referenced. References always point
    backwards to the first complete occurrence using RFC6901 JSON pointers.
    """
    seen = {}
    def walk(item, path):
        raw = encode(item)
        if len(raw) >= 200 and isinstance(item, (dict, list, str)):
            if raw in seen:
                return {'$ref': '#' + seen[raw]}
            seen[raw] = path
        if isinstance(item, dict):
            return {k: walk(v, path + '/' + str(k).replace('~', '~0').replace('/', '~1')) for k, v in item.items()}
        if isinstance(item, list):
            return [walk(v, path + '/' + str(i)) for i, v in enumerate(item)]
        return item
    return walk(value, '')


def deduplicate(value):
    """Choose the smaller lossless reference layout, never truncate evidence.

    Deep provenance paths made the old references almost as long as repeated
    values. A shared-definition table uses the same RFC6901 reference protocol
    with short addresses. Definitions refer only to earlier definitions.
    """
    baseline = _backward_references(value)
    if len(encode(baseline)) < 100000:
        return baseline
    counts = Counter()
    def eligible(item, raw):
        return isinstance(item, (dict, list, str)) and len(raw) >= 64
    def count(item):
        raw = encode(item)
        if eligible(item, raw):counts[raw] += 1
        if isinstance(item, dict):
            for child in item.values():count(child)
        elif isinstance(item, list):
            for child in item:count(child)
    count(value)
    definitions, indices = [], {}
    def children(item):
        if isinstance(item, dict):return {k:pack(v) for k,v in item.items()}
        if isinstance(item, list):return [pack(v) for v in item]
        return item
    def pack(item):
        raw = encode(item)
        if eligible(item, raw) and counts[raw] > 1:
            if raw not in indices:
                body = children(item)
                indices[raw] = len(definitions)
                definitions.append(body)
            return {'$ref':'#/defs/'+str(indices[raw])}
        return children(item)
    document = pack(value)
    pooled = {'defs':definitions, 'document':document}
    return pooled if len(encode(pooled)) < len(encode(baseline)) * .98 else baseline

def columnar_records(value):
    """Lossless column/row encoding for uniform record arrays; nulls stay explicit."""
    if isinstance(value, list):
        if len(value) >= 3 and all(isinstance(v, dict) for v in value):
            columns = list(value[0])
            if all(list(v) == columns for v in value):
                return {'_encoding': 'columns_and_rows', 'columns': columns,
                        'rows': [[columnar_records(v[k]) for k in columns] for v in value]}
            columns = list(dict.fromkeys(k for row in value for k in row))
            indices = {k: str(i) for i, k in enumerate(columns)}
            packed = {'_encoding': 'indexed_records', 'columns': columns,
                      'rows': [{indices[k]: columnar_records(v) for k, v in row.items()} for row in value]}
            if len(encode(packed)) < len(encode(value)) * .9:
                return packed
        return [columnar_records(v) for v in value]
    if isinstance(value, dict):
        return {k: columnar_records(v) for k, v in value.items()}
    return value


