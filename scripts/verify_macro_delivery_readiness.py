"""Read-only audit of delivery, publication and ETF quote clocks. No providers/builds."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def clock(value):
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Aware source observation required')
    return stamp


def quote_checks(board, now, max_age):
    """Recompute age at inspection; never trust a cached stale=false flag."""
    rows = board.get('latest', {}).get('rows', {})
    focus = list(dict.fromkeys(['QQQ'] + list(board.get('focus') or ['SPY', 'IWM', 'DIA'])))
    checks = {}
    for symbol in focus:
        row = rows.get(symbol, {})
        result = {'observation_at_utc': row.get('time_utc'), 'current': False}
        try:
            age = (now - clock(row.get('time_utc'))).total_seconds() / 60
            price = row.get('price')
            valid = type(price) in (int, float) and math.isfinite(price) and price > 0
            result.update(age_minutes=round(age, 2), current=valid and 0 <= age <= max_age,
                          reason='CURRENT_DELAYED_OBSERVATION' if valid and 0 <= age <= max_age
                          else 'EXPIRED_FUTURE_OR_INVALID_QUOTE')
        except (ValueError, TypeError, OverflowError):
            result['reason'] = 'MISSING_OR_INVALID_OBSERVATION_CLOCK'
        checks[symbol] = result
    return checks


def audit(root, *, pending_path, now, validate_feed):
    report = {'checked_at_utc': now.isoformat(), 'authority': 'READ_ONLY_AUDIT_NO_EXECUTION_PERMISSION',
              'feeds': {}, 'errors': [], 'pending_exact_exports': [],
              'publication_verified': False, 'ready_for_current_market_use': False,
              'pipeline_consumption_verified': False,
              'pipeline_note': 'Board publication is not proof of pipeline consumption.',
              'paid_build_launched': False, 'pipeline_launched': False}
    try:
        policy = json.loads((root / 'config/macro_build_schedule_v1.json').read_text())
        accepted = json.loads((root / 'data/macro/delivery/accepted.json').read_text())
        macro_raw = (root / 'dropbox/macro/macro_intelligence_latest.json').read_bytes()
        macro = json.loads(macro_raw)
        manifest = macro['extras']['research_source_manifest']
        html = (root / 'macro_board/output/etf_macro_board.html').read_text(encoding='utf-8')
        start = re.search(r'(?:const|let|var) BOARD\s*=\s*', html)
        if start is None:
            raise ValueError('BOARD_PAYLOAD_MISSING')
        board, _ = json.JSONDecoder().raw_decode(html[start.end():])
        snapshot = json.loads((root / 'macro_board/output/snapshots' / board['build']['snapshot']).read_text())
        link = snapshot['inputs']['macro_packet']
        archived = (root / 'macro_board/output/inputs' / link['archived_as']).read_bytes()
        report.update(board_built_at_utc=board.get('built_at_utc'),
                      macro_packet_built_at_utc=macro.get('_builder_metadata', {}).get('built_at'),
                      ai_analysis_built_at_utc=board.get('intel', {}).get('synthesis', {}).get('analysis_built_at'),
                      historical_price_session=board.get('as_of_session'),
                      board_packet_matches=link['sha256'] == digest(macro_raw) == digest(archived))
        report['focus_etf_quotes'] = quote_checks(board, now, policy['quote_max_age_minutes'])
        report['current_quotes_verified'] = all(r['current'] for r in report['focus_etf_quotes'].values())
        for feed in ('usmi', 'news', 'events'):
            result = {'valid': False}
            report['feeds'][feed] = result
            try:
                entry = accepted[feed]
                path = Path(entry['published_path'])
                if not path.is_absolute():
                    path = root / path
                raw = path.read_bytes()
                validate_feed(feed, json.loads(raw))
                receipt = json.loads((root / 'data/macro/delivery/transport_receipts' / (entry['sha256'] + '.json')).read_text())
                archive = (root / 'data/macro/delivery/archive' / (entry['sha256'] + '.json')).read_bytes()
                result.update(valid=True, revision=entry['revision'], materialized_sha256=digest(raw),
                              source_observation_at_utc=entry.get('source_observation_at_utc'),
                              receipt_complete=receipt['delivery']['status'] == 'COMPLETE',
                              raw_archive_matches=digest(archive) == entry['sha256'],
                              accepted_consumed_match=digest(raw) == manifest[feed]['sha256'])
                if feed == 'usmi':
                    result['board_snapshot_matches'] = snapshot['inputs']['us_money_index']['sha256'] == digest(raw)
                if feed == 'news':
                    result['board_batch_matches'] = board['intel']['enrichment']['batch_id'] == json.loads(raw)['batch_id']
            except (OSError, ValueError, KeyError, TypeError) as exc:
                result['error'] = str(exc)
        # A monitor backlog must be provided explicitly. An absent backlog is UNKNOWN, not empty.
        if pending_path is None:
            report['errors'].append('PENDING_EXPORT_REGISTRY_NOT_PROVIDED')
        else:
            pending = json.loads(pending_path.read_text())
            report['pending_exact_exports'] = [r['source_message'] for r in pending
                if not r.get('accepted_revision') and
                ('PENDING' in r.get('status', '') or 'BLOCKED' in r.get('status', ''))]
        report['publication_verified'] = report['board_packet_matches'] and all(
            r.get('valid') and all(r.get(k, False) for k in
                ('receipt_complete', 'raw_archive_matches', 'accepted_consumed_match'))
            and r.get('board_snapshot_matches', True) and r.get('board_batch_matches', True)
            for r in report['feeds'].values())
        report['delivery_complete'] = report['publication_verified'] and not report['errors'] and not report['pending_exact_exports']
        report['ready_for_current_market_use'] = report['delivery_complete'] and report['current_quotes_verified']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report['errors'].append(str(exc))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--pending', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.root))
    from contracts.macro_feed_delivery import validate_feed
    result = audit(args.root, pending_path=args.pending, now=datetime.now(timezone.utc), validate_feed=validate_feed)
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        temporary = args.output.with_suffix(args.output.suffix + '.tmp')
        temporary.write_text(rendered, encoding='utf-8')
        temporary.replace(args.output)
    print(rendered)
    return 0 if result['ready_for_current_market_use'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
