"""Offline E1/E17 inventory. Reads saved CSV/JSON only, writes a new audit receipt.

Does not import provider clients, run the pipeline, open trading databases,
rewrite the security master or republish historical Lab artefacts.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.instrument_identity import MASTER, attach_identities, load_registry, reconcile_membership


def inventory(book_path, board_path, *, as_of, master_path=MASTER, coverage=None):
    source = Path(book_path).read_bytes()
    reader = csv.DictReader(io.StringIO(source.decode('utf-8-sig')))
    header = reader.fieldnames or []
    if len(header) != len(set(header)):
        raise ValueError('SAVED_BOOK_DUPLICATE_HEADERS_AMBIGUOUS')
    rows = list(reader)
    if not rows or 'ticker' not in rows[0]:
        raise ValueError('SAVED_BOOK_REQUIRES_LITERAL_TICKER_COLUMN')
    board_bytes = Path(board_path).read_bytes()
    board = json.loads(board_bytes.decode('utf-8-sig'))
    board_tickers = [ticker for group in board['universe'] for ticker in group['tickers']]
    registry = load_registry(master_path, board_path=board_path)
    if registry.error:
        raise ValueError(registry.error)
    receipt = reconcile_membership(registry, [r['ticker'] for r in rows], board_tickers,
                                   as_of=as_of, coverage=coverage)
    enriched = attach_identities(rows, registry, as_of=as_of)
    # Every pre-existing field must survive this offline disclosure projection.
    unchanged = all(all(after.get(k) == value for k, value in before.items())
                    for before, after in zip(rows, enriched))
    if not unchanged or len(rows) != len(enriched):
        raise ValueError('IDENTITY_DISCLOSURE_CHANGED_SAVED_BOOK_FACTS')
    receipt.update(saved_book_path=str(Path(book_path).resolve()),
                   saved_book_sha256=hashlib.sha256(source).hexdigest(),
                   board_path=str(Path(board_path).resolve()),
                   board_sha256=hashlib.sha256(board_bytes).hexdigest(),
                   saved_book_rows=len(rows), existing_fields_unchanged=unchanged,
                   row_order_unchanged=[r['ticker'] for r in rows] == [r['ticker'] for r in enriched],
                   source_master_edited=False, providers_called=0, pipeline_run=False,
                   book_identity_states=dict(Counter(r['instrument_identity_state'] for r in enriched)),
                   book_policy_counts=dict(Counter(r['instrument_review_policy'] for r in enriched)),
                   limitations=['Source-reported identities are not independently issuer-verified.',
                       'No legal wrapper or alias is guessed for missing/ambiguous master rows.',
                       'No matching dated chain scope means NOT_ASSESSED, not NO_CHAIN.',
                       'Current review policy is disclosure, not a historical trading decision.',
                       'Existing historical Lab publications have not been changed.'])
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book', type=Path, required=True)
    parser.add_argument('--board', type=Path, default=ROOT / 'macro_board/config/macro_board_config_v1.json')
    parser.add_argument('--master', type=Path, default=MASTER)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--coverage', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.book, args.board, as_of=args.as_of, master_path=args.master,
                       coverage=json.loads(args.coverage.read_text(encoding='utf-8-sig')) if args.coverage else None)
    # Exclusive creation protects earlier audit evidence and all source files.
    with args.report.open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2, allow_nan=False)
        out.write('\n')
    summary = {k: v for k, v in report.items() if k not in {'rows', 'limitations'}}
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
