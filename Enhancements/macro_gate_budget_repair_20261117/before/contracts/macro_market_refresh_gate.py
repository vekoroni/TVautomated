"""Read-only prerequisite for paid FULL analysis; never refresh or redate data."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GROUPS = ('us_futures', 'rates_commodities', 'fx', 'volatility',
          'us_premarket', 'asia', 'europe')


def verify_refresh(directory, *, not_before, now=None):
    from contracts.macro_health import assess_macro_health
    now = now or datetime.now(timezone.utc)
    if any(t.tzinfo is None or t.utcoffset() is None for t in (now, not_before)):
        raise ValueError('REFRESH_GATE_AWARE_CLOCK_REQUIRED')
    paths = list(Path(directory).glob('overnight_????????_??????.json'))
    if not paths:
        raise ValueError('CURRENT_RUN_MARKET_SNAPSHOT_MISSING')
    path = max(paths, key=lambda p: p.stat().st_mtime)
    doc = json.loads(path.read_text(encoding='utf-8-sig'))
    refresh = doc.get('market_refresh') or {}
    captured = datetime.fromisoformat(str(refresh.get('as_of_utc')).replace('Z', '+00:00'))
    if captured.tzinfo is None or not not_before <= captured <= now:
        raise ValueError('CURRENT_RUN_MARKET_REFRESH_NOT_PROVEN')
    if (now-captured).total_seconds() > 600:
        raise ValueError('MARKET_REFRESH_CAPTURE_EXPIRED')
    if doc.get('as_of_utc') != refresh.get('as_of_utc'):
        raise ValueError('MARKET_REFRESH_CLOCK_MISMATCH')
    if refresh.get('errors') or (doc.get('futures_refresh') or {}).get('errors'):
        raise ValueError('MARKET_REFRESH_COLLECTION_ERRORS')
    if not set(GROUPS) <= set(refresh.get('groups_refetched') or []):
        raise ValueError('MARKET_REFRESH_GROUPS_INCOMPLETE')
    for group in GROUPS:
        for row in (doc.get('groups') or {}).get(group, []):
            stamp = datetime.fromisoformat(str(row.get('last_bar_utc')).replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp > now:
                raise ValueError('MARKET_SOURCE_TIMESTAMP_INVALID:' + group)
    lineage = doc.get('futures_refresh') or {}
    parent_name = lineage.get('parent_file')
    if not isinstance(parent_name, str) or Path(parent_name).name != parent_name:
        raise ValueError('MARKET_REFRESH_PARENT_INVALID')
    parent = Path(directory)/parent_name
    if not parent.is_file() or hashlib.sha256(parent.read_bytes()).hexdigest() != lineage.get('parent_sha256'):
        raise ValueError('MARKET_REFRESH_PARENT_HASH_MISMATCH')
    health = assess_macro_health({'extras': {'overnight': {'document': doc}}}, now=now)
    groups = {g: health['source_health'][g] for g in GROUPS}
    unavailable = [g for g, item in groups.items() if item['status'] != 'AVAILABLE']
    if unavailable:
        raise ValueError('MARKET_SOURCE_NOT_READY:' + ','.join(unavailable))
    return {'status': 'READY_FOR_FULL', 'snapshot': str(path),
            'snapshot_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'captured_at_utc': captured.isoformat(), 'checked_at_utc': now.isoformat(),
            'groups': {g: item['status'] for g, item in groups.items()},
            'source_assessments': {g: item['instruments'] for g, item in groups.items()},
            'policy': 'SOURCE_TIMESTAMPS_UNCHANGED; USMI_ASSESSED_SEPARATELY'}
