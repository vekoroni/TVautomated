"""Offline final-build acceptance. New evidence output only; no live publication."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import html
import json
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence-root', type=Path, default=Path('C:/Users/ACKVerissimo/Documents/Codex/2026-07-24/a'))
parser.add_argument('--output', type=Path)
parser.add_argument('--feed-evidence', type=Path, default=Path('C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/macro_board/output/accepted_feed_evidence'))
args = parser.parse_args()
EVIDENCE = args.evidence_root
sys.path.insert(0, str(ROOT))
def forbidden(*a, **k): raise AssertionError('No network/providers permitted')
socket.socket.connect = forbidden
import pandas as pd
from flask import Flask
from macro_board.operating_cycle import run_cycle, load_policy
from macro_board.cycle_io import encoded, digest, immutable
from macro_board.cycle_publication import publish_saved_cycle, read_bundle
from contracts.lab_macro_desk import register_routes

source = EVIDENCE / 'MACRO_CYCLE_PHASE1_FINAL_20261126'
output = args.output or EVIDENCE / 'MACRO_FINAL_GOVERNANCE_ISOLATED_20261126'
pointer = json.loads((source / 'latest.json').read_bytes())
old_bytes = Path(pointer['json']).read_bytes()
assert hashlib.sha256(old_bytes).hexdigest() == pointer['sha256']
old = json.loads(old_bytes)
def capture(key):
    entry = old['input_manifest'][key]; raw = (source / entry['capture']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry['sha256']
    return raw
def obj(key): return json.loads(capture(key))
def frame(key):
    f = pd.DataFrame(obj(key)); col = 'index' if 'index' in f else 'trading_date'
    f[col] = pd.to_datetime(f[col]); f = f.set_index(col)
    return f.apply(pd.to_numeric, errors='coerce')

draft_path = Path('C:/Users/ACKVerissimo/.codex/attachments/6431c4b0-4dd1-41ac-ae78-a9748f764b7a/Pasted text.txt')
draft_bytes = draft_path.read_bytes()
text = draft_bytes.decode('utf-8-sig')
raw = text[text.index('\n{\\\n'):].strip()
draft = json.loads(html.unescape(raw).replace('\\\n', '\n'))
draft_sha = hashlib.sha256(draft_bytes).hexdigest()
immutable(output / 'research_drafts' / (draft_sha + '.txt'), draft_bytes)
immutable(output / 'research_drafts' / (digest(draft) + '.json'), encoded(draft))
now = datetime.now(timezone.utc).isoformat()
payload = obj('board_payload'); original = json.loads(json.dumps(payload))
payload['cycle_assembly_utc'] = now
# Do not install or silently repair the author's unapproved probabilities/worlds.
# Preserve the original as captured research, expose only its labelled draft thesis.
author = {'input_contract_version': 'macro_research_input_v2', 'input_revision': 1,
          'authority': 'ADVISORY_ONLY', 'author': 'Codex research-envelope assembler; original ACK/Claude draft preserved',
          'as_of_utc': now, 'authored_at_utc': now, 'evidence_cutoff_utc': payload['built_at_utc'],
          'approval': {'state': 'RESEARCH_DRAFT'}, 'research_draft_source_sha256': draft_sha,
          'original_draft_clock_status': 'CLAIMED_IN_ORIGINAL_NOT_AUTHENTICATED_AS_AUTHORSHIP',
          'house_view': {**draft['house_view'], 'status': 'RESEARCH_DRAFT_NOT_APPROVED'},
          'central_bank_vs_price': draft['central_bank_vs_price'],
          'event_forecasts': [], 'market_scenarios': {'partition': 'NOT_ASSERTED'}, 'etf_book': [],
          'withheld_from_structured_calls': ['Overlapping policy/CPI/credit/oil alternatives are not a market partition',
              'Declared hot-CPI complement implies 40%, inconsistent with 20% OR scenario',
              'Credit baseline and direct spread outcome need pinned source; VIX is alert only',
              'Oil benchmark/contract/roll and complete path not supplied',
              'Exact ETF expressions/contracts/quotes/delay/IV/costs absent; no option WIN marks',
              'Fresh scenario probabilities and thresholds require ACK/Claude authorship, not code invention']}
raw_inputs = {k: (v['name'], capture(k)) for k, v in old['input_manifest'].items()
              if k in ('macro_packet', 'bond_state', 'liquidity_monitor', 'us_money_index', 'enrichment', 'enrichment_delta', 'event_payload', 'forward_bias')}
raw_inputs['research_draft_original'] = (draft_path.name, draft_bytes)
result = run_cycle(payload, opens=frame('selected_open_rows'), closes=frame('selected_close_rows'),
                   fred=frame('fred_history'), raw=raw_inputs, board_config=obj('board_config'),
                   output_dir=output / 'cycle', policy=load_policy(), author=author)
n = json.loads(Path(result['narrative']).read_bytes())
assert n['status'] == 'RESEARCH_DRAFT'
assert n['governance']['approval_state'] == 'RESEARCH_DRAFT'
assert n['governance']['valuation_readiness'] == 'OPTION_PAYOFF_UNASSESSED'
assert n['governance']['market_scenarios']['partition'] == 'NOT_ASSERTED'
assert n['clocks']['authored_at_utc'] != n['information_cutoff_utc']
publication = output / 'publication'
packet = obj('macro_packet')
for item in packet['extras']['research_source_manifest'].values():
    sha = item['accepted_raw_sha256']
    data = (args.feed_evidence / (sha + '.json')).read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha
    immutable(publication / 'accepted_feed_evidence' / (sha + '.json'), data)
published = publish_saved_cycle(output / 'cycle', publication)
bundle = read_bundle(publication)
assert bundle['manifest']['feed_chain']['status'] == 'VERIFIED_ALL_THREE_FEEDS'
app = Flask(__name__); register_routes(app, publication); client = app.test_client()
lab, board = client.get('/api/lab/macro-context'), client.get('/api/lab/macro-board')
assert lab.status_code == board.status_code == 200
board_payload, _ = json.JSONDecoder().raw_decode(board.text.split('const BOARD=', 1)[1])
assert board_payload['macro_operating_cycle']['narrative_sha256'] == lab.json['macro_operating_cycle']['narrative_sha256']
assert board_payload['etfs'] == original['etfs']
assert {k: v for k, v in board_payload.items() if k not in ('macro_operating_cycle', 'macro_publication_id', 'cycle_assembly_utc')} == original
assert Path(pointer['json']).read_bytes() == old_bytes
report = {'status': 'PASS', 'publication': published, 'draft_original_sha256': draft_sha,
          'original_revision_1_preserved': True, 'draft_installed_as_live_input': False,
          'research_draft_not_approved': True, 'board_http': board.status_code, 'lab_http': lab.status_code,
          'same_narrative_hash': True, 'all_three_feeds': True, 'unchanged_etf_rows': len(original['etfs']),
          'older_narrative_unchanged': True, 'separate_clocks': n['clocks'],
          'provider_calls': 0, 'paid_builds': 0, 'pipeline_runs': 0, 'live_publication_modified': False}
immutable(output / ('receipt_' + digest(report) + '.json'), encoded(report))
print(json.dumps(report, indent=2))
