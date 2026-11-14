"""Dated security-master disclosure. No providers, aliases, selection or writes.

SOURCE_REPORTED is not independent issuer verification. The input master is
preserved, including unresolved labels; consumers must not infer identity from
board membership or from a missing chain receipt.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / 'data/universe/polygon_liquid_universe_security_master_v1.csv'
POLICY = ROOT / 'config/instrument_identity_v1.json'
BOARD = ROOT / 'macro_board/config/macro_board_config_v1.json'
IDENTITY_FIELDS = (
    'instrument_type', 'instrument_identity_state', 'instrument_identity_reason',
    'instrument_identity_source', 'instrument_identity_source_sha256',
    'instrument_identity_asof', 'instrument_identity_reference_date',
    'instrument_identity_valid_from', 'instrument_identity_valid_to',
    'instrument_wrapper', 'instrument_leveraged', 'instrument_inverse',
    'instrument_volatility', 'instrument_review_policy', 'instrument_policy_authority',
    'instrument_policy_version', 'instrument_policy_basis',
    'instrument_review_policy_reason', 'instrument_policy_source', 'instrument_policy_source_sha256',
)


def _ticker(value: Any) -> str:
    # csv.DictReader, not pandas NA inference: NAN and SYM are literal identities.
    return '' if value is None else str(value).strip().upper()


def _day(value: Any) -> date | None:
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


class InstrumentRegistry:
    def __init__(self, rows, *, source, sha256, policy, error=None, risk_groups=None,
                 risk_source=None, risk_sha256=None):
        self.source, self.sha256, self.policy, self.error = source, sha256, policy, error
        self.risk_groups = risk_groups or {}
        self.risk_source, self.risk_sha256 = risk_source, risk_sha256
        self.rows = defaultdict(list)
        for row in rows:
            if _ticker(row.get('ticker')):
                self.rows[_ticker(row['ticker'])].append(dict(row))

    def fields(self, ticker, as_of):
        out = dict.fromkeys(IDENTITY_FIELDS)
        day = _day(as_of)
        group = self.risk_groups.get(_ticker(ticker))
        out.update(instrument_identity_source=self.source,
                   instrument_identity_source_sha256=self.sha256,
                   instrument_identity_reference_date=day.isoformat() if day else None,
                   instrument_policy_authority=self.policy['authority'],
                   instrument_policy_version=self.policy['version'],
                   instrument_policy_basis=self.policy['policy_basis'],
                   instrument_review_policy='RESEARCH_ONLY' if group else 'UNASSESSED',
                   instrument_review_policy_reason=f'CURRENT_BOARD_RISK_GROUP:{group}' if group else 'IDENTITY_UNASSESSED',
                   instrument_policy_source=self.risk_source if group else self.source,
                   instrument_policy_source_sha256=self.risk_sha256 if group else self.sha256)

        def unavailable(state):
            out.update(instrument_identity_state=state, instrument_identity_reason=state)
            return out

        if self.error:
            return unavailable(self.error)
        if day is None:
            return unavailable('NO_REFERENCE_DATE')
        records = self.rows.get(_ticker(ticker), [])
        if not records:
            return unavailable('MASTER_ROW_NOT_FOUND')
        if all(not r.get('valid_from') or not r.get('classification_asof') for r in records):
            return unavailable('UNASSESSED_CLASSIFICATION_DATES')
        applicable = []
        for row in records:
            start, end, known = (_day(row.get(k)) for k in ('valid_from', 'valid_to', 'classification_asof'))
            if start is None or known is None or (row.get('valid_to') and end is None):
                continue
            # valid_to is an exclusive boundary; overlapping rows fail closed below.
            if known <= day and start <= day and (end is None or day < end):
                applicable.append(row)
        if not applicable:
            return unavailable('NO_ASOF_CLASSIFICATION')
        if len(applicable) != 1:
            return unavailable('AMBIGUOUS_MASTER_ROWS')
        row = applicable[0]
        kind = str(row.get('instrument_type') or '').strip().upper()
        vocab = self.policy['types'].get(kind, {})
        reason = vocab.get('review_reason')
        if not vocab:
            reason = 'UNRECOGNISED_MASTER_TYPE'
        if str(row.get('classification_status') or '').endswith('REVIEW'):
            reason = reason or 'MASTER_CLASSIFICATION_REQUIRES_REVIEW'
        out.update(
            instrument_type=kind or None,
            instrument_identity_state='REVIEW_REQUIRED' if reason else 'SOURCE_REPORTED',
            instrument_identity_reason=reason or 'MASTER_REPORTED_NOT_INDEPENDENTLY_VERIFIED',
            instrument_identity_source=f"{self.source}; classification_source={row.get('classification_source') or 'NOT_RECORDED'}",
            instrument_identity_asof=row.get('classification_asof') or None,
            instrument_identity_valid_from=row.get('valid_from') or None,
            instrument_identity_valid_to=row.get('valid_to') or None,
            instrument_wrapper=vocab.get('wrapper'),
            instrument_leveraged=vocab.get('leveraged'),
            instrument_inverse=vocab.get('inverse'),
            instrument_volatility=vocab.get('volatility'),
            instrument_review_policy=(self.policy['special_product_policy'] if vocab.get('research_only') or group
                                      else 'UNASSESSED' if reason else 'STANDARD_REVIEW'),
            instrument_review_policy_reason=(f'CURRENT_BOARD_RISK_GROUP:{group}' if group else
                'MASTER_TYPE_REQUIRES_PRODUCT_SPECIFIC_VALIDATION' if vocab.get('research_only') else
                reason or 'STANDARD_SOURCE_REPORTED_REVIEW'),
        )
        return out


def load_registry(path=MASTER, *, policy_path=POLICY, board_path=BOARD):
    policy = json.loads(Path(policy_path).read_text(encoding='utf-8-sig'))
    if policy['authority'] != 'DISPLAY_ONLY':
        raise ValueError('INSTRUMENT_IDENTITY_AUTHORITY_NOT_APPROVED')
    risk_groups, risk_sha256, risk_source = {}, None, None
    if board_path is not None:
        try:
            board_raw = Path(board_path).read_bytes()
            board = json.loads(board_raw.decode('utf-8-sig'))
        except (OSError, ValueError):
            board = {}
        else:
            risk_sha256, risk_source = hashlib.sha256(board_raw).hexdigest(), str(Path(board_path))
        for group in board.get('universe', []):
            if group.get('group') in policy['research_board_groups']:
                for ticker in group.get('tickers', []):
                    risk_groups[_ticker(ticker)] = group['group']
    kwargs = dict(risk_groups=risk_groups, risk_source=risk_source, risk_sha256=risk_sha256)
    source = str(Path(path))
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        return InstrumentRegistry([], source=source, sha256=None, policy=policy,
                                  error=f'MASTER_UNAVAILABLE:{type(exc).__name__}', **kwargs)
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or not {'ticker', 'instrument_type', 'valid_from', 'classification_asof'}.issubset(rows[0]):
        return InstrumentRegistry([], source=source, sha256=hashlib.sha256(raw).hexdigest(),
                                  policy=policy, error='MASTER_SCHEMA_INVALID_OR_EMPTY', **kwargs)
    return InstrumentRegistry(rows, source=source, sha256=hashlib.sha256(raw).hexdigest(), policy=policy, **kwargs)


def attach_identities(rows, registry, *, as_of=None):
    """Add disclosure fields to copies. Never sort, select, drop or mutate rows."""
    return [{**row, **registry.fields(row.get('ticker'), as_of or row.get('timing_as_of')
             or row.get('bar_data_asof') or row.get('evidence_session_date'))} for row in rows]


def reconcile_membership(registry, book_tickers, board_tickers, *, as_of, coverage=None):
    """A union, not a new eligibility list. Missing scoped data is not NO_CHAIN."""
    book = {_ticker(t) for t in book_tickers if _ticker(t)}
    board = {_ticker(t) for t in board_tickers if _ticker(t)}
    valid_coverage = (isinstance(coverage, Mapping) and _day(as_of) is not None
                      and _day(coverage.get('as_of')) == _day(as_of)
                      and bool(str(coverage.get('scope') or '').strip())
                      and isinstance(coverage.get('tickers'), (list, tuple, set)))
    saved = {_ticker(t) for t in coverage['tickers']} if valid_coverage else set()
    rows = []
    for ticker in sorted(book | board):
        rows.append({'ticker': ticker, 'in_saved_book': ticker in book, 'in_board_universe': ticker in board,
                     **registry.fields(ticker, as_of),
                     'saved_chain_state': ('SAVED_CHAIN_PRESENT' if ticker in saved else 'NO_SAVED_CHAIN_FOR_SCOPE')
                     if valid_coverage else 'NOT_ASSESSED',
                     'saved_chain_scope': coverage['scope'] if valid_coverage else None,
                     'saved_chain_reason': 'EXACT_DATE_SCOPED_RECEIPTS' if valid_coverage else 'NO_MATCHING_DATED_SCOPE_SUPPLIED'})
    return {'schema': 'etf_identity_coverage_v1', 'as_of': str(as_of), 'authority': 'DISPLAY_ONLY',
            'master_sha256': registry.sha256, 'book_unique_tickers': len(book), 'board_unique_tickers': len(board),
            'union_tickers': len(rows), 'identity_states': dict(Counter(r['instrument_identity_state'] for r in rows)),
            'book_tickers_missing_master': sorted(book - registry.rows.keys()),
            'board_tickers_missing_master': sorted(board - registry.rows.keys()), 'rows': rows}
