"""ETF identity is dated disclosure, never a selector or a guessed alias."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def registry(tmp_path, rows):
    from canonical_data.instrument_identity import load_registry
    path = tmp_path / 'master.csv'
    fields = ['ticker', 'instrument_type', 'classification_source', 'classification_asof',
              'valid_from', 'valid_to', 'classification_status']
    with path.open('w', newline='', encoding='utf-8') as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows({**dict.fromkeys(fields, ''), 'classification_source': 'saved_fixture',
                         'classification_asof': '2026-09-22', 'valid_from': '2026-09-23', **r} for r in rows)
    return load_registry(path, board_path=None)


def test_literal_nan_and_sym_are_identities_not_missing_values(tmp_path):
    reg = registry(tmp_path, [{'ticker': s, 'instrument_type': 'EQUITY'} for s in ('NAN', 'SYM')])
    for ticker in ('NAN', 'SYM'):
        found = reg.fields(ticker, '2026-11-11')
        assert found['instrument_type'] == 'EQUITY'
        assert found['instrument_identity_state'] == 'SOURCE_REPORTED'
        assert len(found['instrument_identity_source_sha256']) == 64


def test_future_expired_and_overlapping_metadata_cannot_be_silently_selected(tmp_path):
    reg = registry(tmp_path, [
        {'ticker': 'FUT', 'instrument_type': 'EQUITY', 'classification_asof': '2026-12-01'},
        {'ticker': 'OLD', 'instrument_type': 'EQUITY', 'valid_to': '2026-10-01'},
        {'ticker': 'DUP', 'instrument_type': 'EQUITY'},
        {'ticker': 'DUP', 'instrument_type': 'SECTOR_ETF'},
    ])
    for ticker in ('FUT', 'OLD'):
        assert reg.fields(ticker, '2026-11-11')['instrument_identity_state'] == 'NO_ASOF_CLASSIFICATION'
    assert reg.fields('DUP', '2026-11-11')['instrument_identity_state'] == 'AMBIGUOUS_MASTER_ROWS'
    assert reg.fields('FUT', '2026-11-11')['instrument_type'] is None
    assert reg.fields('OLD', None)['instrument_identity_state'] == 'NO_REFERENCE_DATE'


def test_legacy_volatility_type_does_not_assert_etn_or_exact_leverage(tmp_path):
    reg = registry(tmp_path, [{'ticker': 'VOL', 'instrument_type': 'LEVERAGED_VOL_ETF'}])
    found = reg.fields('VOL', '2026-11-11')
    assert found['instrument_type'] == 'LEVERAGED_VOL_ETF'
    assert found['instrument_wrapper'] is None
    assert found['instrument_leveraged'] is None
    assert found['instrument_volatility'] is True
    assert found['instrument_identity_state'] == 'REVIEW_REQUIRED'
    assert found['instrument_review_policy'] == 'RESEARCH_ONLY'
    assert found['instrument_policy_authority'] == 'DISPLAY_ONLY'


def test_undated_legacy_master_labels_cannot_become_point_in_time_facts(tmp_path):
    reg = registry(tmp_path, [{'ticker': 'LEG', 'instrument_type': 'EQUITY',
                              'classification_asof': '', 'valid_from': ''}])
    found = reg.fields('LEG', '2026-11-11')
    assert found['instrument_identity_state'] == 'UNASSESSED_CLASSIFICATION_DATES'
    assert found['instrument_type'] is None
    assert found['instrument_review_policy'] == 'UNASSESSED'


def test_current_board_risk_group_sets_review_policy_without_inventing_identity(tmp_path):
    from canonical_data.instrument_identity import load_registry
    registry(tmp_path, [{'ticker': 'SPY', 'instrument_type': 'EQUITY_INDEX_ETF'}])
    board = tmp_path / 'board.json'
    board.write_text(json.dumps({'universe': [{'group': 'Leveraged & inverse', 'tickers': ['SQQQ']}]}),
                     encoding='utf-8')
    reg = load_registry(tmp_path / 'master.csv', board_path=board)
    found = reg.fields('SQQQ', '2026-11-11')
    assert found['instrument_identity_state'] == 'MASTER_ROW_NOT_FOUND'
    assert found['instrument_type'] is None
    assert found['instrument_inverse'] is None
    assert found['instrument_review_policy'] == 'RESEARCH_ONLY'
    assert found['instrument_review_policy_reason'] == 'CURRENT_BOARD_RISK_GROUP:Leveraged & inverse'
    assert len(found['instrument_policy_source_sha256']) == 64


def test_missing_scanner_name_is_not_classified_from_board_membership(tmp_path):
    from canonical_data.instrument_identity import reconcile_membership
    reg = registry(tmp_path, [{'ticker': 'SPY', 'instrument_type': 'EQUITY_INDEX_ETF'}])
    result = reconcile_membership(reg, ['SPY', 'ARKG'], ['SPY', 'ARKG', 'TQQQ'], as_of='2026-11-11')
    indexed = {r['ticker']: r for r in result['rows']}
    assert indexed['ARKG']['instrument_type'] is None
    assert indexed['ARKG']['instrument_identity_state'] == 'MASTER_ROW_NOT_FOUND'
    assert indexed['TQQQ']['in_saved_book'] is False
    assert all(r['saved_chain_state'] == 'NOT_ASSESSED' for r in result['rows'])
    assert result['book_tickers_missing_master'] == ['ARKG']


def test_saved_coverage_requires_exact_date_and_scope(tmp_path):
    from canonical_data.instrument_identity import reconcile_membership
    reg = registry(tmp_path, [{'ticker': 'SPY', 'instrument_type': 'EQUITY_INDEX_ETF'}])
    report = reconcile_membership(reg, ['SPY'], ['SPY', 'ARKG'], as_of='2026-11-11',
        coverage={'as_of': '2026-11-11', 'scope': 'standard;7-60DTE;OI>=1', 'tickers': ['SPY']})
    assert [r['saved_chain_state'] for r in report['rows']] == ['NO_SAVED_CHAIN_FOR_SCOPE', 'SAVED_CHAIN_PRESENT']
    wrong = reconcile_membership(reg, ['SPY'], [], as_of='2026-11-11',
        coverage={'as_of': '2026-11-10', 'scope': 'standard', 'tickers': ['SPY']})
    assert wrong['rows'][0]['saved_chain_state'] == 'NOT_ASSESSED'


def test_identity_attachment_never_changes_existing_facts_or_order(tmp_path):
    from canonical_data.instrument_identity import attach_identities
    reg = registry(tmp_path, [{'ticker': 'SPXS', 'instrument_type': 'LEVERAGED_INVERSE_ETF'}])
    rows = [{'ticker': 'SPXS', 'lab_rank': 7, 'direction': 'PUT', 'contract_symbol': 'saved',
             'lab_verdict': 'MANUAL_REVIEW'}, {'ticker': 'NAN', 'lab_rank': 8}]
    frozen = deepcopy(rows)
    result = attach_identities(rows, reg, as_of='2026-11-11')
    assert rows == frozen
    for before, after in zip(rows, result):
        assert all(after[k] == v for k, v in before.items())
    assert result[0]['instrument_review_policy'] == 'RESEARCH_ONLY'


def test_projection_roundtrips_identity_without_reclassification(tmp_path):
    from canonical_data.instrument_identity import attach_identities, IDENTITY_FIELDS
    from contracts.lab_review_projection import publish_review_projection, read_review_rows, read_review_card
    reg = registry(tmp_path, [{'ticker': 'SPY', 'instrument_type': 'EQUITY_INDEX_ETF'}])
    rows = attach_identities([{'ticker': 'SPY', 'lab_rank': 2, 'thesis_id': 'T1', 'direction': 'CALL'}],
                             reg, as_of='2026-11-11')
    book = {'run_id': 'ETF_OFFLINE', 'candidate_count': 1, 'rows': rows}
    frozen = deepcopy(book)
    receipt = publish_review_projection(book, tmp_path / 'projection')
    home = read_review_rows(tmp_path / 'projection', 'ETF_OFFLINE')['rows'][0]
    card = read_review_card(tmp_path / 'projection', 'ETF_OFFLINE', home['row_key'], receipt['revision'])
    assert all(card['fields'][f] == rows[0][f] for f in IDENTITY_FIELDS)
    assert home['instrument_type'] == 'EQUITY_INDEX_ETF'
    assert home['lab_rank'] == 2
    assert book == frozen


def test_real_materializer_adds_only_identity_fields_and_keeps_canonical_rank(tmp_path, monkeypatch):
    from canonical_data.instrument_identity import IDENTITY_FIELDS
    from contracts import lab_control
    reg = registry(tmp_path, [{'ticker': 'SPXS', 'instrument_type': 'LEVERAGED_INVERSE_ETF'}])
    signals = [{'ticker': 'SPXS', 'final_direction': 'PUT', 'trade_lane': 'B'},
               {'ticker': 'NAN', 'final_direction': 'CALL', 'trade_lane': 'A'}]
    frozen = deepcopy(signals)
    monkeypatch.setattr(lab_control, 'load_registry', lambda: reg)
    monkeypatch.setattr(lab_control, 'utc_now', lambda: '2026-11-11T23:00:00Z')
    original = lab_control.attach_identities
    monkeypatch.setattr(lab_control, 'attach_identities', lambda rows, *a, **k: rows)
    manifest = {'decision_clock': '2026-11-11T23:00:00Z'}
    before = lab_control.build_final_opportunity_book('ETF_TEST', signals, manifest)
    monkeypatch.setattr(lab_control, 'attach_identities', original)
    after = lab_control.build_final_opportunity_book('ETF_TEST', signals, manifest)
    assert signals == frozen
    for old, new in zip(before, after):
        assert {k: v for k, v in old.items() if k not in IDENTITY_FIELDS} == {
            k: v for k, v in new.items() if k not in IDENTITY_FIELDS}
    assert next(r for r in after if r['ticker'] == 'SPXS')['instrument_review_policy'] == 'RESEARCH_ONLY'


def test_master_is_never_loaded_by_the_presentation_reader():
    import ast
    path = Path(__file__).resolve().parents[1] / 'contracts/lab_review_projection.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == 'load_registry' for n in ast.walk(tree))


def test_inventory_rejects_ambiguous_duplicate_headers_before_reconciliation(tmp_path):
    import pytest
    from scripts.etf_identity_inventory import inventory
    source = tmp_path / 'ambiguous.csv'
    source.write_text('ticker,ticker\nSPY,QQQ\n', encoding='utf-8')
    with pytest.raises(ValueError, match='DUPLICATE_HEADERS_AMBIGUOUS'):
        inventory(source, tmp_path / 'unused.json', as_of='2026-11-11')
