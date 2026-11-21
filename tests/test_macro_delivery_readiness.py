import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

script = Path(__file__).with_name('verify_macro_delivery_readiness.py')
if not script.exists():
    script = Path(__file__).resolve().parents[1] / 'scripts/verify_macro_delivery_readiness.py'
spec = importlib.util.spec_from_file_location('delivery_readiness', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NOW = datetime(2026, 11, 18, 18, 0, tzinfo=timezone.utc)


class ReadinessTests(unittest.TestCase):
    def board(self, stamp):
        return {'focus': ['QQQ'], 'latest': {'rows': {'QQQ': {
            'price': 100, 'time_utc': stamp, 'stale': False, 'age_minutes': 0}}}}

    def test_cached_fresh_flag_expires_using_actual_clock(self):
        result = module.quote_checks(self.board((NOW-timedelta(hours=4)).isoformat()), NOW, 20)
        self.assertFalse(result['QQQ']['current'])
        self.assertEqual(result['QQQ']['age_minutes'], 240)

    def test_future_missing_and_naive_clocks_are_not_current(self):
        for stamp in ((NOW+timedelta(minutes=1)).isoformat(), None, '2026-11-18T18:00:00'):
            self.assertFalse(module.quote_checks(self.board(stamp), NOW, 20)['QQQ']['current'])

    def test_delayed_quote_within_policy_is_current(self):
        result = module.quote_checks(self.board((NOW-timedelta(minutes=15)).isoformat()), NOW, 20)
        self.assertTrue(result['QQQ']['current'])

    def test_missing_packet_yields_explicit_failed_report(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            report = module.audit(Path(folder), pending_path=None, now=NOW, validate_feed=lambda *_: None)
        self.assertFalse(report['ready_for_current_market_use'])
        self.assertTrue(report['errors'])

    def fixture(self, root):
        def write(name, value):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
            return path.read_bytes()
        write('config/macro_build_schedule_v1.json', {'quote_max_age_minutes': 20})
        accepted, manifest = {}, {}
        for feed in ('usmi', 'news', 'events'):
            raw = write('dropbox/macro/' + feed + '.json', {'feed': feed, 'batch_id': 'test-batch'})
            sha = module.digest(raw)
            accepted[feed] = {'published_path': 'dropbox/macro/' + feed + '.json', 'sha256': sha, 'revision': 1}
            manifest[feed] = {'sha256': sha}
            write('data/macro/delivery/archive/' + sha + '.json', json.loads(raw))
            write('data/macro/delivery/transport_receipts/' + sha + '.json', {'delivery': {'status': 'COMPLETE'}})
        write('data/macro/delivery/accepted.json', accepted)
        raw = write('dropbox/macro/macro_intelligence_latest.json', {'extras': {'research_source_manifest': manifest}})
        write('macro_board/output/inputs/packet.json', json.loads(raw))
        snapshot = {'inputs': {'macro_packet': {'sha256': module.digest(raw), 'archived_as': 'packet.json'},
                               'us_money_index': {'sha256': accepted['usmi']['sha256']}}}
        write('macro_board/output/snapshots/test.json', snapshot)
        board = self.board((NOW-timedelta(minutes=15)).isoformat())
        board.update(build={'snapshot': 'test.json'}, intel={'enrichment': {'batch_id': 'test-batch'}})
        (root/'macro_board/output/etf_macro_board.html').write_text('const BOARD = ' + json.dumps(board) + ';')
        write('pending.json', [])

    def test_accepted_registry_does_not_hide_missing_materialized_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            self.fixture(root)
            good = module.audit(root, pending_path=root/'pending.json', now=NOW, validate_feed=lambda *_: None)
            self.assertTrue(good['ready_for_current_market_use'])
            (root/'dropbox/macro/events.json').unlink()
            bad = module.audit(root, pending_path=root/'pending.json', now=NOW, validate_feed=lambda *_: None)
            self.assertFalse(bad['ready_for_current_market_use'])
            self.assertIn('error', bad['feeds']['events'])

    def test_pending_or_unknown_backlog_and_hash_mismatch_never_pass(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            self.fixture(root)
            unknown = module.audit(root, pending_path=None, now=NOW, validate_feed=lambda *_: None)
            self.assertFalse(unknown['ready_for_current_market_use'])
            (root/'pending.json').write_text(json.dumps([{'source_message': 'test-message', 'status': 'EXACT_ORIGINAL_PENDING'}]))
            pending = module.audit(root, pending_path=root/'pending.json', now=NOW, validate_feed=lambda *_: None)
            self.assertEqual(pending['pending_exact_exports'], ['test-message'])
            self.assertFalse(pending['ready_for_current_market_use'])
            (root/'dropbox/macro/news.json').write_text('{"batch_id":"changed"}')
            mismatch = module.audit(root, pending_path=root/'pending.json', now=NOW, validate_feed=lambda *_: None)
            self.assertFalse(mismatch['publication_verified'])


if __name__ == '__main__':
    unittest.main()

