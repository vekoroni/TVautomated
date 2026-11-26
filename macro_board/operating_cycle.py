"""Saved-only macro operating cycle and automatic board-publication adapter.

No provider/client imports. Writes only its own cycle directory. CLI reads the
saved board and a short mode=ro SQLite snapshot; never runs a board or pipeline.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

from . import conditions
from .cycle_evidence import short_windows, forced_calendar
from .cycle_io import encoded, digest, capture, writer, publish, read_records, append_records, atomic
from .cycle_narrative import assemble, validate_author_input, tripwires
from .cycle_scoring import forward_calls, score_forward, forward_summary, score_calls, instant

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'config/macro_operating_cycle_v1.json'


def load_policy(path=POLICY):
    policy = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if policy['authority'] != 'ADVISORY_ONLY': raise ValueError('Macro cycle must remain advisory')
    return policy


def _safe(value):
    # Pandas frames become selected logical rows, not a physical DB/WAL fingerprint.
    if isinstance(value, pd.DataFrame): return value.reset_index().astype(str).to_dict('records')
    return value


def make_windows(fred, closes, board_config, policy):
    sessions = closes.index
    series = {}
    for name in ('DGS2', 'DGS10', 'WALCL', 'WTREGEN', 'RRPONTSYD', 'VIXCLS', 'DEXUSEU', 'SPREAD_2Y10Y'):
        series[name] = conditions.fred_point_in_time(fred, name, 'weekly' if name in ('WALCL', 'WTREGEN') else 'daily', sessions, board_config)
    for name in ('SPY', 'QQQ', 'IWM', 'HYG', 'LQD', 'USO', 'UUP'):
        if name in closes: series['PRICE:' + name] = closes[name]
    result = short_windows(series, sessions, policy)
    for name, rows in result.items():
        for row in rows.values():
            if isinstance(row, dict):
                row['source'] = 'saved FRED release-lag aligned' if not name.startswith('PRICE:') else 'saved split-adjusted ETF prices'
    return result


def _documents(raw):
    out = {}
    mapping = {'macro_packet': 'packet', 'bond_state': 'bond', 'liquidity_monitor': 'liquidity',
               'us_money_index': 'usmi', 'enrichment': 'news', 'enrichment_delta': 'news', 'event_payload': 'events'}
    import io
    for key, (name, data) in raw.items():
        if key not in mapping: continue
        if name.lower().endswith('.csv'):
            frame = pd.read_csv(io.BytesIO(data)); obj = json.loads(frame.tail(1).to_json(orient='records'))
            out[mapping[key]] = obj[0] if obj else {}
        else:
            out[mapping[key]] = json.loads(data.decode('utf-8-sig'))
    return out


def _authored(path, cutoff):
    if not path.exists(): return None
    author = json.loads(path.read_text(encoding='utf-8-sig')); validate_author_input(author)
    if instant(author['as_of_utc']) > instant(cutoff): raise ValueError('Authored input is newer than the cycle cutoff')
    return author


def run_cycle(payload, *, output_dir, **kwargs):
    # Serialize the whole transaction; lower-level journals also guard direct callers.
    with writer(Path(output_dir) / 'cycle_writer'):
        return _run_cycle(payload, output_dir=output_dir, **kwargs)


def _run_cycle(payload, *, opens, closes, fred, raw, board_config, output_dir, policy=None,
              author=None, observations=None, archive_calls=None):
    policy = policy or load_policy()
    output_dir = Path(output_dir)
    # Every operation below uses an explicit clock. No hidden current-time scoring.
    cutoff = payload['built_at_utc']; instant(cutoff)
    if author:
        validate_author_input(author)
        if instant(author['as_of_utc']) > instant(cutoff): raise ValueError('Future authored input')
    raw = dict(raw)
    for observation in observations or []:
        source = observation.get('source_path')
        if not source or str(source).startswith(('http:', 'https:', '\\\\')):
            raise ValueError('Authored outcome needs a local saved source_path; no fetch permitted')
        data = Path(source).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != observation.get('source_sha256'):
            raise ValueError('Authored outcome saved-source hash mismatch')
        raw['outcome_evidence_' + sha] = (Path(source).name, data)
    as_of = date.fromisoformat(payload['as_of_session'])
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    if not is_xnys_session(as_of) or session_bounds(as_of)[1] > instant(cutoff):
        raise ValueError('Reference close must be completed at the knowledge cutoff')
    opens, closes = opens.loc[:str(as_of)], closes.loc[:str(as_of)]
    # Histories are evidence-as-read, not asserted point-in-time release vintages.
    windows = make_windows(fred, closes, board_config, policy)
    calendar = forced_calendar(as_of, closes, policy)
    sources = _documents(raw)
    sources['fred_latest'] = {k: {'value': float(v.dropna().iloc[-1]),
                                'observation_date': str(v.dropna().index[-1].date()),
                                'status': 'AS_READ_REVISED_HISTORY_NOT_VINTAGE_CERTIFIED'}
                               for k, v in fred.loc[:str(as_of)].items() if len(v.dropna())}
    manifest = {}
    with writer(output_dir):
        for key, (name, data) in raw.items(): manifest[key] = capture(output_dir, name, data)
        for key, obj in [('board_payload', payload), ('selected_open_rows', _safe(opens)),
                         ('selected_close_rows', _safe(closes)), ('fred_history', _safe(fred)),
                         ('policy', policy), ('board_config', board_config), ('authored_input', author),
                         ('authored_outcomes', observations or [])]:
            manifest[key] = capture(output_dir, key, encoded(obj))
        # Runtime evidence is bound even when calc_version has not changed.
        runtime = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('cycle_*.py'))}
        runtime[Path(__file__).name] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        manifest['runtime'] = capture(output_dir, 'runtime_hashes', encoded(runtime))
    previous = None
    pointer = output_dir / 'latest.json'
    if pointer.exists():
        p = json.loads(pointer.read_text()); blob = Path(p['json']).read_bytes()
        if hashlib.sha256(blob).hexdigest() != p['sha256']: raise ValueError('Previous narrative hash mismatch')
        previous = json.loads(blob)
        # A retry of the identical capture should not create an endless version chain.
        if previous.get('input_manifest') == manifest:
            report = json.loads((output_dir / 'runs' / (previous['narrative_id'] + '.json')).read_text())
            return {**report, 'idempotent': True}
    narrative = assemble(payload, sources, windows, calendar, policy, manifest, author, previous)
    measurements = {}
    for series in ('DGS2', 'DGS10', 'WALCL', 'WTREGEN', 'RRPONTSYD', 'VIXCLS', 'DEXUSEU', 'SPREAD_2Y10Y'):
        aligned = conditions.fred_point_in_time(fred, series, 'weekly' if series in ('WALCL', 'WTREGEN') else 'daily', closes.index, board_config)
        value = aligned.iloc[-1] if len(aligned) else None
        from .cycle_evidence import number
        measurements[series] = {'value': number(value), 'status': 'OK' if number(value) is not None else 'MISSING_OR_STALE',
                                'source': 'release_lag_aligned_saved_FRED', 'as_of_session': str(as_of)}
    for t in policy['trend_etfs']:
        value = closes[t].iloc[-1] if t in closes and len(closes) else None
        measurements[t + '.close'] = {'value': number(value), 'status': 'OK' if number(value) is not None else 'MISSING',
                                     'source': 'saved_price_rows', 'as_of_session': str(as_of)}
    narrative['tripwire_observations'] = tripwires(author, measurements, (previous or {}).get('tripwire_observations'))
    # The ID covers the alert observations too, not only prose and driver states.
    narrative.pop('narrative_id')
    narrative['narrative_id'] = 'macro_' + str(as_of) + '_' + digest(narrative)[:24]
    calendar_record = {'contract_version': 'macro_forced_flow_calendar_v1', 'calc_version': policy['calc_version'],
                       'authority': 'ADVISORY_ONLY', 'input_hashes': {k: v['sha256'] for k, v in manifest.items()}, **calendar}
    calendar_path = output_dir / 'calendars' / ('forced_flow_calendar_' + str(as_of) + '_' + digest(calendar_record)[:24] + '.json')
    with writer(output_dir):
        from .cycle_io import immutable
        immutable(calendar_path, encoded(calendar_record))
    current_calls = []
    if 'forward_bias' in raw:
        import io
        name, data = raw['forward_bias']
        rows = pd.read_csv(io.BytesIO(data)).fillna('').to_dict('records')
        current_calls = forward_calls(rows, cutoff, hashlib.sha256(data).hexdigest(), policy)
    calls_path = output_dir / 'forward_calls.jsonl'
    existing_calls = {r['record_id']: r for r in read_records(calls_path)}
    candidates = {}
    for call in list(archive_calls or []) + current_calls:
        rid = call['record_id']
        if rid in existing_calls:
            old = existing_calls[rid]
            if {k: v for k, v in old.items() if k != 'known_at_utc'} != {k: v for k, v in call.items() if k != 'known_at_utc'}:
                raise ValueError('Forward call identity conflict')
            if instant(call['known_at_utc']) < instant(old['known_at_utc']):
                raise ValueError('Earlier publication evidence found; explicit clock correction required')
            continue  # Same bytes are the same call, not a fresh forecast on each board refresh.
        if rid not in candidates or instant(call['known_at_utc']) < instant(candidates[rid]['known_at_utc']):
            candidates[rid] = call
    append_records(calls_path, list(candidates.values()))
    calls = read_records(calls_path)
    bars = pd.DataFrame({'open': opens['SPY'], 'close': closes['SPY']}) if 'SPY' in opens and 'SPY' in closes else pd.DataFrame()
    outcomes = score_forward(calls, bars, cutoff)
    append_records(output_dir / 'forward_scores.jsonl', outcomes)
    authored_calls = []
    for kind in ('wrong_worlds', 'event_calls', 'playbook_choices', 'forced_flow_predictions'):
        for call in (author or {}).get(kind, []):
            authored_calls.append({**call, 'record_id': digest([manifest['authored_input']['sha256'], call['call_id']]),
                                   'kind': kind, 'known_at_utc': author['as_of_utc'],
                                   'authored_input_sha256': manifest['authored_input']['sha256'],
                                   'authority': 'ADVISORY_ONLY'})
    existing_authored = read_records(output_dir / 'authored_calls.jsonl')
    previous_calls = {c['call_id']: c for c in existing_authored}
    for call in authored_calls:
        if call['call_id'] in previous_calls and call != previous_calls[call['call_id']]:
            raise ValueError('Changed authored call requires a new call_id/correction lineage')
    append_records(output_dir / 'authored_calls.jsonl', authored_calls)
    all_authored = read_records(output_dir / 'authored_calls.jsonl')
    authored_scores = score_calls(all_authored, observations or [], cutoff)
    append_records(output_dir / 'daily_scores.jsonl', authored_scores)
    # Advance the narrative pointer only after all required journals succeeded.
    target = publish(output_dir, narrative)
    report = {'status': narrative['status'], 'narrative_id': narrative['narrative_id'], 'narrative': str(target),
              'authority': 'ADVISORY_ONLY', 'source_captures': len(manifest), 'provider_calls': 0,
              'forward': forward_summary(calls, outcomes), 'authored_calls': len(all_authored),
              'authored_status_counts': {s: sum(r['status'] == s for r in authored_scores) for s in sorted({r['status'] for r in authored_scores})},
              'driver_states': {k: {'state': v['state'], 'status': v['status']} for k, v in narrative['driver_readings'].items()},
              'knowledge_cutoff_utc': cutoff, 'reference_session': str(as_of)}
    report['forced_flow_calendar'] = str(calendar_path)
    report['tripwires'] = narrative['tripwire_observations']
    with writer(output_dir):
        from .cycle_io import immutable
        immutable(output_dir / 'runs' / (narrative['narrative_id'] + '.json'), encoded(report))
        atomic(output_dir / 'run_latest.json', encoded(report))
    return report


def archive_inventory(folder, policy):
    """Use board capture clocks, never infer a timezone from file names."""
    folder = Path(folder); by_sha = {}; skipped = []; clock_evidence = []
    for path in sorted((folder / 'snapshots').glob('board_*.json')):
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
        entry = (doc.get('inputs') or {}).get('forward_bias') or {}
        if not entry.get('archived_as'): continue
        saved = folder / 'inputs' / entry['archived_as']
        if not saved.is_file():
            skipped.append({'snapshot': str(path), 'reason': 'ARCHIVED_CALL_BYTES_MISSING'}); continue
        data = saved.read_bytes(); sha = hashlib.sha256(data).hexdigest()
        if sha != entry.get('sha256'): raise ValueError('Archived forward-call hash mismatch')
        clock = doc.get('built_at_utc')
        if not clock:
            skipped.append({'snapshot': str(path), 'reason': 'PUBLICATION_CLOCK_UNKNOWN'}); continue
        instant(clock)
        clock_evidence.append({'snapshot': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'forward_source_sha256': sha, 'built_at_utc': clock})
        if sha not in by_sha or instant(clock) < instant(by_sha[sha][0]): by_sha[sha] = (clock, data)
    calls = []
    import io
    for sha, (clock, data) in sorted(by_sha.items()):
        calls.extend(forward_calls(pd.read_csv(io.BytesIO(data)).fillna('').to_dict('records'), clock, sha, policy))
    artifacts = list((folder / 'inputs').glob('*forward_bias*.csv'))
    orphaned = [{'artifact': str(p), 'reason': 'NO_VERIFIED_PUBLICATION_CLOCK_LINK'} for p in artifacts
                if hashlib.sha256(p.read_bytes()).hexdigest() not in by_sha]
    return calls, {'distinct_archived_artifacts': len(by_sha), 'call_rows': len(calls), 'exclusions': skipped,
                   'archived_csv_files': len(artifacts), 'unlinked_artifacts': orphaned,
                   'publication_clock_evidence': clock_evidence,
                   'clock_convention': 'EARLIEST_SAVED_BOARD_PUBLICATION_REFERENCING_BYTES'}


def board_adapter(payload, *, opens, closes, fred, external, board_config, output_dir, replay=False):
    raw = {name: (read.file.name, read.file.read_bytes()) for name, read in external.items()
           if read.file and read.file.is_file() and name in ('macro_packet', 'bond_state', 'liquidity_monitor',
                                                          'us_money_index', 'enrichment', 'enrichment_delta', 'event_payload', 'forward_bias')}
    policy = load_policy()
    author = _authored(ROOT / policy['author_input'], payload['built_at_utc'])
    obs_path = ROOT / policy['outcome_input']
    observations = json.loads(obs_path.read_text(encoding='utf-8-sig')) if obs_path.exists() else []
    folder = Path(output_dir) / 'operating_cycle'
    return run_cycle(payload, opens=opens, closes=closes, fred=fred, raw=raw, board_config=board_config,
                     output_dir=folder, policy=policy, author=author, observations=observations)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--backfill-forward', action='store_true')
    args = p.parse_args()
    html = args.board.read_text(encoding='utf-8'); marker = 'const BOARD='
    start = html.index(marker) + len(marker)
    payload, _ = json.JSONDecoder().raw_decode(html[start:])
    config = json.loads((ROOT / 'macro_board/config/macro_board_config_v1.json').read_text())
    from . import sources as src
    tickers = sorted(set(load_policy()['trend_etfs']) | {'HYG', 'LQD', 'USO', 'UUP'})
    # Existing loader is mode=ro; promptly closes its connection after the bounded query.
    opens, closes, _ = src.load_prices(ROOT / config['sources']['price_db'], tickers, config['history_start'])
    fred = src.load_fred(ROOT / config['sources']['fred_master'])
    kind = (payload.get('build') or {}).get('kind', 'EVENING')
    suffix = '' if kind == 'EVENING' else '_' + kind.lower()
    snapshot = args.board.parent / 'snapshots' / f"board_{payload['as_of_session']}{suffix}.json"
    doc = json.loads(snapshot.read_text())
    if doc['built_at_utc'] != payload['built_at_utc']: raise ValueError('Board/snapshot revision mismatch')
    raw = {'saved_board': (args.board.name, args.board.read_bytes())}
    for key, entry in doc.get('inputs', {}).items():
        if key not in ('macro_packet', 'bond_state', 'liquidity_monitor', 'us_money_index', 'enrichment', 'enrichment_delta', 'event_payload', 'forward_bias'): continue
        if entry.get('archived_as'):
            path = args.board.parent / 'inputs' / entry['archived_as']; data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != entry['sha256']: raise ValueError('Saved input hash mismatch')
            raw[key] = (path.name, data)
    policy = load_policy(); author = _authored(ROOT / policy['author_input'], payload['built_at_utc'])
    calls, inventory = archive_inventory(args.board.parent, policy) if args.backfill_forward else ([], {})
    # Never backfill a future publication into an earlier cutoff.
    calls = [c for c in calls if instant(c['known_at_utc']) <= instant(payload['built_at_utc'])]
    # Preserve the verified historical CSV bytes before existing rolling retention
    # can remove them. Unlinked artifacts stay unassessed; copying grants no clock.
    if args.backfill_forward:
        with writer(args.output):
            for path in (args.board.parent / 'inputs').glob('*forward_bias*.csv'):
                capture(args.output, path.name, path.read_bytes())
            for path in (args.board.parent / 'snapshots').glob('board_*.json'):
                capture(args.output, path.name, path.read_bytes())
    report = run_cycle(payload, opens=opens, closes=closes, fred=fred, raw=raw, board_config=config,
                       output_dir=args.output, author=author, archive_calls=calls)
    report['archive_inventory'] = inventory
    with writer(args.output):
        from .cycle_io import immutable
        immutable(args.output / 'archive_inventories' / (digest(inventory) + '.json'), encoded(inventory))
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__': main()
