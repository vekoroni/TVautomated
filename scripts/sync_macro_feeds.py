"""Receive completed producer JSONs, then publish a dated advisory-only view.

No research generation, paid API/model calls or pipeline execution.
Exit 0: complete; 2: missing/rejected delivery; 3: writer busy/deferred;
1: configuration/transport error.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.macro_feed_delivery import deliver, atomic_json, validate_feed, FILES

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--manifest')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--receive-file',type=Path,help='Validate and receive a downloaded or checksum-verified original export')
    parser.add_argument('--receive-preview-lines',type=Path,help='Complete numbered source lines with producer SHA-256 verification')
    parser.add_argument('--expected-bytes',type=int)
    parser.add_argument('--source-chat')
    parser.add_argument('--source-message')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--transport',default='DOWNLOAD')
    args = parser.parse_args(argv)
    config_path = args.config or args.root / 'config/macro_delivery_v1.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    if config.get('contract_version') != 'macro_delivery_config_v1':
        raise ValueError('unsupported delivery config')
    manifest = args.manifest or str(args.root / config['default_manifest'])
    from contracts.macro_export_receipt import receive_export,receive_queue,assemble_preview_source
    if args.receive_preview_lines:
        if args.receive_file:raise ValueError('preview cannot have a competing input')
        capture=json.loads(args.receive_preview_lines.read_text(encoding='utf-8-sig'))
        raw=assemble_preview_source(capture['lines'],last_line=capture['last_line'],expected_sha256=args.expected_sha256,expected_bytes=args.expected_bytes,verification_lines=capture.get('verification_lines'))
        if len(raw)>config['max_packet_bytes']:raise ValueError('EXPORT_EXCEEDS_SIZE_LIMIT')
        import hashlib
        producer_checksum=bool(args.expected_sha256)
        args.expected_sha256=hashlib.sha256(raw).hexdigest()
        queue=args.root/config.get('export_queue_directory','dropbox/macro/exports');queue.mkdir(parents=True,exist_ok=True)
        args.receive_file=queue/(args.expected_sha256+'.json')
        if args.receive_file.exists() and args.receive_file.read_bytes()!=raw:raise ValueError('RAW_ARCHIVE_COLLISION')
        args.receive_file.write_bytes(raw)
        args.transport='FILE_PREVIEW_SOURCE_EXACT_PRODUCER_SHA256' if producer_checksum else 'FILE_PREVIEW_SOURCE_TWO_COMPLETE_PASSES'

    if args.receive_file:
        record=receive_export(args.receive_file,root=args.root,config=config,source_chat=args.source_chat,
            source_message=args.source_message,expected_sha256=args.expected_sha256,transport=args.transport)
        receipt=record['delivery']
    else:
        queued=receive_queue(args.root,config)
        failed=[record['delivery'] for record in queued if record['delivery'].get('status')=='FAILED' or any(feed.get('status')=='REJECTED' for feed in record['delivery'].get('feeds',{}).values())]
        receipt=failed[-1] if failed else queued[-1]['delivery'] if queued else deliver(manifest, root=args.root, config=config)

    feeds = {}
    for feed, name in FILES.items():
        path = args.root / config['macro_directory'] / name
        if path.is_file():
            try:
                packet = json.loads(path.read_text(encoding='utf-8-sig'))
                feeds[feed] = validate_feed(feed, packet)
            except (ValueError, OSError):
                continue
    atomic_json(args.root / config['macro_directory'] / 'macro_advisory_latest.json',
                {'contract_version': 'macro_advisory_overlay_v1', 'authority': 'ADVISORY_ONLY',
                 'execution_permission': 'NONE_INTELLIGENCE_ONLY',
                 'as_of_utc': receipt['checked_at_utc'], 'observation_time_policy': 'PER_FEED_NOT_REFRESHED_BY_DELIVERY',
                 'delivery': receipt, 'feeds': feeds})
    print(json.dumps({'status': receipt['status'], 'material_change': receipt['material_change'], 'feeds': receipt['feeds']}))
    return 0 if receipt['status'] == 'COMPLETE' else 2

if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, OSError, KeyError) as error:
        if isinstance(error,ValueError) and any(marker in str(error).lower() for marker in ('delivery_writer_busy','writer already locked')):
            print('DEFERRED: DELIVERY_WRITER_BUSY; retain accepted files and retry delivery on the next pickup',file=sys.stderr)
            sys.exit(3)
        print('Macro delivery failed; check configuration, manifest and transport. No automatic research rebuild.', file=sys.stderr)
        sys.exit(1)
