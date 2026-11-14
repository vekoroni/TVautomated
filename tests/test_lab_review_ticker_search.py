"""Five-ticker lookup reads only the frozen review projection."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.lab_review_projection import (publish_review_projection, read_review_rows,
                                            register_review_routes, ReviewRevisionConflict)


@pytest.fixture
def published(tmp_path):
    rows = [{'ticker': f'OTHER{i}', 'sector': 'Energy', 'lab_verdict': 'MANUAL_REVIEW',
             'lab_rank': i + 1} for i in range(60)]
    rows += [{'ticker': ticker, 'sector': 'Technology', 'direction': 'CALL',
              'lab_verdict': 'MANUAL_REVIEW', 'lab_rank': 100 + i,
              'thesis_id': ticker + '-THESIS'}
             for i, ticker in enumerate(['AAPL', 'MSFT', 'NVDA', 'BRK.B', 'NAN'])]
    book = {'run_id': 'SEARCH_TEST', 'candidate_count': len(rows), 'rows': rows}
    original = deepcopy(book)
    receipt = publish_review_projection(book, tmp_path)
    assert book == original
    return tmp_path, receipt, book


def test_five_tickers_across_pages_and_case(published):
    root, receipt, _ = published
    result = read_review_rows(root, 'SEARCH_TEST', revision=receipt['revision'],
                              tickers=[' aapl ', 'msft', 'nvda', 'brk.b', 'nan'])
    assert [r['ticker'] for r in result['rows']] == ['AAPL', 'MSFT', 'NVDA', 'BRK.B', 'NAN']
    assert result['filtered_rows'] == 5 and result['total_rows'] == 65
    assert result['ticker_filter'] == ['AAPL', 'MSFT', 'NVDA', 'BRK.B', 'NAN']
    assert [r['lab_rank'] for r in result['rows']] == [100, 101, 102, 103, 104]


def test_duplicate_and_exact_missing_symbols(published):
    root, _, _ = published
    result = read_review_rows(root, 'SEARCH_TEST', tickers=['AAPL', 'aapl', 'AAP', 'MISSING'])
    assert result['ticker_filter'] == ['AAPL', 'AAP', 'MISSING']
    assert [r['ticker'] for r in result['rows']] == ['AAPL']


@pytest.mark.parametrize('symbols', [[], ['A', 'B', 'C', 'D', 'E', 'F'], [''],
                                    ['AAPL', 1], ["AAPL'); DROP TABLE rows;--"], 'AAPL'])
def test_invalid_search_is_rejected(published, symbols):
    root, _, _ = published
    with pytest.raises(ValueError):
        read_review_rows(root, 'SEARCH_TEST', tickers=symbols)


def test_revision_pin_and_independent_sector_filter(published):
    root, receipt, book = published
    assert read_review_rows(root, 'SEARCH_TEST', tickers=['AAPL'], sector='Energy')['rows'] == []
    book['rows'][0]['lab_rank'] = 999
    publish_review_projection(book, root)
    with pytest.raises(ReviewRevisionConflict):
        read_review_rows(root, 'SEARCH_TEST', revision=receipt['revision'], tickers=['AAPL'])


def test_route_returns_only_requested_frozen_rows(published):
    root, receipt, _ = published
    app = Flask(__name__)
    register_review_routes(app, lambda: root)
    client = app.test_client()
    reply = client.get('/api/lab/SEARCH_TEST/rows', query_string={
        'tickers': 'AAPL,MSFT', 'revision': receipt['revision']})
    assert reply.status_code == 200
    assert [r['ticker'] for r in reply.json['rows']] == ['AAPL', 'MSFT']
    assert reply.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/lab/SEARCH_TEST/rows?tickers=A,B,C,D,E,F').status_code == 400


def test_search_preserves_multiple_theses_and_existing_review_order(published):
    root, _, book = published
    book['rows'].append({'ticker': 'AAPL', 'sector': 'Technology', 'direction': 'PUT',
                         'thesis_id': 'AAPL-SECOND', 'lab_verdict': 'GO', 'lab_rank': 200})
    book['candidate_count'] = len(book['rows'])
    publish_review_projection(book, root)
    rows = read_review_rows(root, 'SEARCH_TEST', tickers=['AAPL'])['rows']
    assert [r['direction'] for r in rows] == ['PUT', 'CALL']
    assert [r['lab_rank'] for r in rows] == [200, 100]
