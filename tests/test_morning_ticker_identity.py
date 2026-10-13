"""Ticker identity is not a generic missing-value string (Morning NAN regression)."""
import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest

import morning_gate as gate
from domain.station_inspection import StationDefect, enforce, inspect_station


@pytest.mark.parametrize('value,expected', [('NAN','NAN'), (' nan ','NAN'), ('brk.b','BRK.B'),
                                           (None,''), ('',''), ('  ',''), (float('nan'),'')])
def test_ticker_normalization_preserves_literal_symbols(value, expected):
    assert gate._ticker(value) == expected


def test_nonidentity_missing_values_keep_existing_behavior():
    assert gate._s('NAN') == '' and gate._u('NAN') == ''


def test_provider_symbol_matching_accepts_nan():
    from datetime import datetime, timezone
    now = datetime(2026,10,13,14,0,tzinfo=timezone.utc)
    result = gate._parse_marketdata_stock_price(
        {'s':'ok','symbol':['NAN'],'mid':[5.0],'updated':[int(now.timestamp())]}, 'NAN', now_utc=now)
    assert result.get('live_price') == 5.0


def test_morning_station_hook_preserves_nan_and_still_rejects_real_changes(tmp_path):
    source = inspect.getsource(gate.run_morning_gate)
    start = source.index('    import pandas as _pd_station')
    end = source.index('    enforce(_station)') + len('    enforce(_station)')
    block = '\n'.join(line[4:] for line in source[start:end].splitlines())
    rows = [{'ticker':'NAN'}, {'ticker':'AAA'}]
    scope = dict(vars(gate), results=rows, candidates=rows, run_id='NAN_REGRESSION', ROOT=tmp_path, log=gate.log)
    exec(block, scope)
    assert scope['_station']['stop_defects'] == []
    for results in [[{'ticker':'AAA'}], [{'ticker':'NAN'}, {'ticker':'AAA'}, {'ticker':'NEW'}]]:
        scope.update(results=results)
        with pytest.raises(StationDefect):
            exec(block, scope)


def test_missing_ticker_is_still_blocked():
    report = inspect_station('morning', pd.DataFrame([{'ticker':None}]), run_id='R',
                             previous_tickers=set(), accounted_tickers=set())
    with pytest.raises(StationDefect, match='nonblank_tickers'):
        enforce(report)


def test_no_generic_text_normalizer_used_for_ticker_gets():
    tree = ast.parse(Path(gate.__file__).read_text(encoding='utf-8-sig'))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'_u','_s'}:
            for arg in node.args:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == 'get':
                    if arg.args and isinstance(arg.args[0], ast.Constant) and arg.args[0].value == 'ticker':
                        bad.append(node.lineno)
    assert bad == []
