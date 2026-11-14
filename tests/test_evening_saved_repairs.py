"""Saved-data repairs preserve measured facts and never manufacture authority."""
from contextlib import contextmanager
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from phantom_database import PhantomDatabase
from phantom_engine import score_row
from scripts.finalize_phantom_weekly_snapshot import derive_iv_history


def chain(ticker='NAN', day='2026-11-10', symbol='A', **extra):
    return dict(ticker=ticker, quote_date=day, option_symbol=symbol, side='call',
                strike=100., dte=30., underlying_price=100., iv=.3, delta=.5,
                gamma=.02, theta=-.04, vega=.1, open_interest=10, volume=2,
                bid=3., mid=3.1, ask=3.2, source='marketdata.app', **extra)


def database(tmp_path):
    db = PhantomDatabase(tmp_path / 'phantom.db', ROOT)
    db.initialise()
    return db


def iv_cache(path):
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE iv_history(ticker TEXT,sample_date TEXT,atm_iv REAL,source TEXT,updated_at TEXT,PRIMARY KEY(ticker,sample_date))')
        c.execute('CREATE TABLE iv_cache_meta(ticker TEXT PRIMARY KEY,last_full_build TEXT,last_refresh TEXT)')
    return path


def test_scoring_preload_keeps_exact_scores_without_raw_payloads_or_future_rows(tmp_path):
    db = database(tmp_path)
    db.upsert_chain_rows([chain(symbol='A', raw_json='x' * 20000),
                          chain(symbol='B', raw_json='y' * 20000)])
    row = dict(ticker='NAN', direction='CALL', contract_iv=.4,
               contract_dte=30, contract_strike=100, contract_gamma=.02)
    expected = score_row(row, db, '20261110_test')
    assert db.ensure_scoring_index(min_free_gib=0)
    assert not db.ensure_scoring_index(min_free_gib=0)
    with db.connect() as c:
        plan = c.execute('EXPLAIN QUERY PLAN SELECT iv FROM chain_snapshots WHERE ticker=? AND iv IS NOT NULL AND dte BETWEEN ? AND ? AND quote_date<=? ORDER BY quote_date,option_symbol', ('NAN',7,60,'2026-11-10')).fetchall()
        assert any('COVERING INDEX idx_chain_scoring_iv' in r[3] for r in plan)
    statements = []
    original = db.connect
    @contextmanager
    def traced():
        with original() as conn:
            conn.set_trace_callback(statements.append)
            yield conn
    db.connect = traced
    db.preload_tickers(['NAN'], as_of='2026-11-10')
    assert score_row(row, db, '20261110_test') == expected
    assert all('raw_json' not in r for r in db.latest_chain_rows('NAN'))
    assert not any('SELECT cs.*' in s for s in statements)
    db.preload_tickers(['NAN'], as_of='2026-11-10')
    assert len(db.historical_iv_values('NAN')) == 2  # no duplicate preload
    db.upsert_chain_rows([chain(day='2026-11-11', symbol='FUTURE')])
    db.preload_tickers(['NAN'], as_of='2026-11-10')
    assert {r['quote_date'] for r in db.latest_chain_rows('NAN')} == {'2026-11-10'}
    assert len(db.historical_iv_values('NAN')) == 2


def test_direct_iv_derivation_acknowledges_only_committed_outputs(tmp_path, monkeypatch):
    db = database(tmp_path)
    db.upsert_chain_rows([chain()])
    cache = iv_cache(tmp_path / 'iv.db')
    derive_iv_history(db.db_path, cache, '2026-11-10', ['NAN'], execute=False)
    with sqlite3.connect(db.db_path) as c:
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0] == 'PENDING_IV'
    import scripts.finalize_phantom_weekly_snapshot as module
    original = module._write_iv_cache
    monkeypatch.setattr(module, '_write_iv_cache', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('cache failed')))
    with pytest.raises(RuntimeError, match='cache failed'):
        derive_iv_history(db.db_path, cache, '2026-11-10', ['NAN'], execute=True)
    with sqlite3.connect(db.db_path) as c:
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0] == 'PENDING_IV'
    monkeypatch.setattr(module, '_write_iv_cache', lambda *a, **k: None)
    with pytest.raises(RuntimeError, match='receipt mismatch'):
        derive_iv_history(db.db_path, cache, '2026-11-10', ['NAN'], execute=True)
    with sqlite3.connect(db.db_path) as c:
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0] == 'PENDING_IV'
    monkeypatch.setattr(module, '_write_iv_cache', original)
    derive_iv_history(db.db_path, cache, '2026-11-10', ['NAN'], execute=True)
    with sqlite3.connect(db.db_path) as c:
        assert c.execute('SELECT status FROM phantom_maintenance_pairs').fetchone()[0] == 'COMPLETE'


def test_index_disk_guard_does_not_change_chain_facts(tmp_path):
    db=database(tmp_path)
    db.upsert_chain_rows([chain()])
    with pytest.raises(RuntimeError,match='disk reserve'):
        db.ensure_scoring_index(min_free_gib=10**9)
    with sqlite3.connect(db.db_path) as c:
        assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='idx_chain_scoring_iv'").fetchone()[0] == 0
        assert c.execute('SELECT iv,underlying_price FROM chain_snapshots').fetchone() == (.3,100.)


def test_invalid_atm_inputs_are_terminal_unavailable_not_silently_complete(tmp_path):
    db = database(tmp_path)
    invalid = chain(); invalid['underlying_price'] = None
    db.upsert_chain_rows([invalid])
    derive_iv_history(db.db_path, iv_cache(tmp_path/'iv.db'), '2026-11-10', ['NAN'], execute=True)
    with sqlite3.connect(db.db_path) as c:
        assert c.execute('SELECT status,last_error FROM phantom_maintenance_pairs').fetchone() == ('IV_UNAVAILABLE', 'NO_VALID_ATM_INPUT')


def test_horizon_patch_preserves_or_recovers_measured_contract_hold_only(tmp_path, monkeypatch):
    import intelligent_orchestrator as io
    run = '20261110_test'
    folder = tmp_path/run/'horizon'; folder.mkdir(parents=True)
    pd.DataFrame([dict(ticker=t, horizon_action='GO', horizon_size_multiplier=1.,
                       horizon_block_reason='', horizon_source='TEST', router_version='test')
                  for t in ('NAN','SYM','LEGACY','UNKNOWN')]).to_csv(folder/f'horizon_1_5d_{run}.csv', index=False)
    target = tmp_path/'oi.csv'
    basis = 'VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80:k=1.5|vol=.3|move=.1'
    pd.DataFrame([
        dict(ticker='NAN', planned_hold_sessions=21, planned_hold_source=basis,
             evidence_runway_basis='GOVERNED_WINDOW_NO_LEVEL_EVIDENCE'),
        dict(ticker='SYM', contract_runway_hold_sessions=14, contract_runway_basis=basis),
        dict(ticker='LEGACY', planned_hold_sessions=20, planned_hold_source='HORIZON_BUCKET_ENDPOINT_V1'),
        dict(ticker='UNKNOWN', contract_runway_hold_sessions=20, contract_runway_basis='NO_RUNWAY_ESTIMATE'),
    ]).to_csv(target,index=False)
    monkeypatch.setattr(io.cfg,'RUNS_DIR',tmp_path)
    assert io.patch_horizon_fields_into_csv(run,target,'test')
    out=pd.read_csv(target,keep_default_na=False).set_index('ticker')
    assert float(out.loc['NAN','planned_hold_sessions']) == 21
    assert out.loc['NAN','planned_hold_source'] == basis
    assert float(out.loc['SYM','planned_hold_sessions']) == 14
    assert out.loc['SYM','planned_hold_source'] == basis
    assert out.loc['LEGACY','planned_hold_sessions'] == ''
    assert out.loc['UNKNOWN','planned_hold_sessions'] == ''
