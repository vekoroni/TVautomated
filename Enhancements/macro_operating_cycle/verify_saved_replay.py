"""Independent saved-artifact check; no production assembly/scoring code imported."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--folder', type=Path, required=True)
args = parser.parse_args()
folder = args.folder
pointer = json.loads((folder / 'latest.json').read_bytes())
blob = Path(pointer['json']).read_bytes()
assert hashlib.sha256(blob).hexdigest() == pointer['sha256']
assert hashlib.sha256(Path(pointer['markdown']).read_bytes()).hexdigest() == pointer['markdown_sha256']
n = json.loads(blob)
assert n['authority'] == 'ADVISORY_ONLY'
assert [s['key'] for s in n['sections']] == ['what_changed', 'transmission', 'house_view', 'wrong_worlds',
    'central_bank_vs_price', 'forced_flows', 'confirmation_divergence', 'etf_book', 'what_changes_our_mind']
manifest = n['input_manifest']
for entry in manifest.values():
    raw = (folder / entry['capture']).read_bytes()
    assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
assert {'us_money_index', 'enrichment', 'event_payload'} <= set(manifest)
def captured(key):
    return json.loads((folder / manifest[key]['capture']).read_bytes())
prices = pd.DataFrame(captured('selected_close_rows'))
prices.index = pd.to_datetime(prices.pop('trading_date'))
prices = prices.apply(pd.to_numeric, errors='coerce')
fred = pd.DataFrame(captured('fred_history'))
fred.index = pd.to_datetime(fred.pop('index'))
fred = fred.apply(pd.to_numeric, errors='coerce')
# Independent DGS2 alignment from documented observation + one-day lag.
observed = fred.DGS2.dropna()
aligned = []
for day in prices.index:
    history = observed[observed.index <= day - pd.Timedelta(days=1)]
    aligned.append(float(history.iloc[-1]) if len(history) and (day - history.index[-1]).days <= 6 else float('nan'))
s = pd.Series(aligned, index=prices.index)
changes = s.diff(5) * 100
changes = changes.where(s.notna().rolling(6).sum() == 6)
value = float(changes.iloc[-1]); tail = changes.iloc[-252:].dropna()
pct = float((tail.abs() <= abs(value)).mean())
reported = n['sections'][0]['data']['short_windows']['DGS2']['5']
assert abs(reported['change'] - value) < 1e-8
assert abs(reported['unusualness_percentile'] - pct) < 1e-8
assert abs(value + 17) < 1e-8 and reported['turning_point']
run = json.loads((folder / 'run_latest.json').read_bytes())
calendar = json.loads(Path(run['forced_flow_calendar']).read_bytes())
seen = {(e['date'], e['kind']) for e in calendar['events']}
assert {('2026-11-27', 'HALF_DAY'), ('2026-11-30', 'MONTH_END'), ('2026-12-18', 'MONTHLY_OPTIONS_EXPIRY'),
        ('2026-12-31', 'QUARTER_END'), ('2026-12-31', 'YEAR_END')} <= seen
for t in ('SPY', 'QQQ', 'IWM'):
    for w in (20, 50, 100, 200):
        assert abs(calendar['trend_levels'][t][str(w)]['average'] - prices[t].iloc[-w:].mean()) < 1e-8
assert n['driver_readings']['credit']['state'] == 'WIDE_WARNING'
assert n['driver_readings']['rates']['state'] == 'EASING'
assert n['driver_readings']['rotation']['state'] == 'DEFENSIVE_BROADENING'
assert n['driver_readings']['liquidity']['status'] == 'STALE'
assert n['series_eligibility']['USSLIND']['status'] == 'EXCLUDED_HISTORICAL_ONLY'
calls = [json.loads(line) for line in (folder / 'forward_calls.jsonl').read_bytes().splitlines()]
assert len(calls) == len({r['record_id'] for r in calls}) == 81
assert all(r['probability_status'] == 'UNCALIBRATED_SCORE_TRANSFORM' for r in calls)
inventory = json.loads(next((folder / 'archive_inventories').glob('*.json')).read_bytes())
assert inventory['archived_csv_files'] == 34 and inventory['distinct_archived_artifacts'] == 27
assert len(inventory['unlinked_artifacts']) == 7
print(json.dumps({'status': 'PASS', 'narrative_id': n['narrative_id'], 'capture_hashes_checked': len(manifest),
    'independent_dgs2_5s_bp': value, 'independent_unusualness_percentile': pct,
    'trend_averages_checked': 12, 'forward_call_rows': len(calls), 'provider_calls': 0,
    'content_status': n['status'], 'clock_certification': 'AS_READ_NOT_VINTAGE_BACKTEST'}, indent=2))
