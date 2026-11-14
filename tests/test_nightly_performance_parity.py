"""Offline contracts for performance-only changes; no pipeline entry points."""
from __future__ import annotations

import ast
import copy
import logging
import os
import socket
import sys
import types
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def functions(path, names, namespace=None):
    """Load only named definitions: importing the Discovery CLI configures logs."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert len(nodes) == len(names), (path, names)
    env = dict(pd=pd, np=np, Path=Path, datetime=datetime, date=date, timezone=timezone,
               timedelta=timedelta, os=os, logging=logging, lru_cache=lru_cache, copy=copy)
    env.update(namespace or {})
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), env)
    return env


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network forbidden in saved-data performance tests")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def discovery_env(monkeypatch, frame, fail_write=False):
    calls = []
    bridge = types.ModuleType("canonical_data.history_bridge")
    bridge.DEFAULT_HISTORY_MAX_STALENESS_DAYS = 5
    bridge.canonical_history_is_fresh = lambda df: True
    bridge.read_canonical_history = lambda *a, **k: None
    bridge.observe_shadow_history = lambda *a, **k: None
    def write(ticker, data, **kwargs):
        calls.append(kwargs["source_kind"])
        if fail_write:
            raise RuntimeError("local commit failed")
    bridge.write_through_fetched_history = write
    monkeypatch.setitem(sys.modules, "canonical_data.history_bridge", bridge)
    class Fetcher:
        def fetch_daily_bars(self, ticker, start, end, *, persist_history=True):
            if persist_history:
                try:
                    write(ticker, frame, source_kind="POLYGON_DATA_FETCHER")
                except RuntimeError:
                    return None
            return frame.copy()
    env = functions(ROOT / "avshunter_discovery_ULTIMATE.py", ["load_bars"], {
        "PolygonDataFetcher": Fetcher,
        "REQUIRED_COLS": {"date", "open", "high", "low", "close", "volume"},
    })
    return env["load_bars"], Fetcher, calls


def prices():
    return pd.DataFrame({"date": pd.date_range("2026-10-01", periods=25),
                         "open": 10., "high": 12., "low": 9., "close": 11., "volume": 100})


def test_discovery_commits_fetched_prices_once_and_keeps_polygon_origin(monkeypatch, tmp_path):
    load, fetcher, writes = discovery_env(monkeypatch, prices())
    result = load(tmp_path, "NAN", fetcher(), True, 400)
    assert writes == ["POLYGON_DATA_FETCHER"]
    pd.testing.assert_frame_equal(result, prices())
    assert result.attrs["data_as_of"] == "2026-10-25"


def test_alternative_fetcher_still_requires_discovery_commit(monkeypatch, tmp_path):
    load, _, writes = discovery_env(monkeypatch, prices())
    class Alternative:
        def fetch_daily_bars(self, ticker, start, end):
            return prices()
    assert load(tmp_path, "SYM", Alternative(), True, 400) is not None
    assert writes == ["DISCOVERY_INCREMENTAL_REFRESH"]


def test_failed_production_commit_never_becomes_fresh_data(monkeypatch, tmp_path):
    load, fetcher, writes = discovery_env(monkeypatch, prices(), fail_write=True)
    assert load(tmp_path, "SYM", fetcher(), True, 400) is None
    assert not (tmp_path / "SYM.csv").exists()


def test_fetcher_keeps_commit_ownership_if_discovery_bridge_import_is_unavailable(monkeypatch, tmp_path):
    load, fetcher, writes = discovery_env(monkeypatch, prices())
    del sys.modules["canonical_data.history_bridge"].DEFAULT_HISTORY_MAX_STALENESS_DAYS
    result = load(tmp_path, "SYM", fetcher(), True, 400)
    assert result is not None
    assert writes == ["POLYGON_DATA_FETCHER"]


def test_profile_session_grid_is_reused_without_weakening_diagnostics():
    calls = []
    stamps = pd.date_range("2026-11-10 14:30", periods=78, freq="5min", tz="UTC")
    def expected(**kwargs):
        calls.append(kwargs)
        return stamps
    path = ROOT / "scripts/build_completed_market_profiles.py"
    names = ["_quality_diagnostics"]
    if "def _session_grid(" in path.read_text(encoding="utf-8"):
        names.insert(0, "_session_grid")
    env = functions(path, names, {"expected_intraday_timestamps": expected})
    frame = pd.DataFrame({"timestamp_utc": stamps, "open": 10., "high": 12., "low": 9.,
                          "close": 11., "volume": 10., "provider_http_status": 200})
    kwargs = dict(session_date=date(2026, 11, 10), open_utc=stamps[0].to_pydatetime(),
                  close_utc=(stamps[-1] + pd.Timedelta(minutes=5)).to_pydatetime(), interval_minutes=5)
    good = env["_quality_diagnostics"](frame, **kwargs)
    bad = env["_quality_diagnostics"](frame.iloc[:-1], **kwargs)
    assert good[0] and not bad[0]
    assert not bad[1]["last_region_present"]
    assert len(calls) == 1


def test_profile_atr_frame_path_is_exactly_the_records_path():
    atr = functions(ROOT / "scripts/build_completed_market_profiles.py", ["_atr14"])["_atr14"]
    frame = prices()
    assert atr({"daily_df": frame}) == atr({"daily_df": frame.to_dict("records")})


def test_candidate_context_prepared_once_and_nested_mutations_do_not_leak():
    from scripts.options_candidate_lane import evaluate_candidate_expressions
    calls = []
    records = [{"Candidate_ID": str(i), "Ticker": "NAN", "Handoff_Rank": i,
                "Direction": "BULL", "Outcome_Level": 15 + i, "Invalidation_Level": 9} for i in range(3)]
    def parse(row):
        calls.append(row)
        return {"horizon_bucket": "6_10d", "nested": {"seen": []}}
    def select(chain, ctx):
        assert ctx["nested"]["seen"] == []
        ctx["nested"]["seen"].append(1)
        return {"symbol": "SAVED", "target": ctx["structural_target"]}
    out = evaluate_candidate_expressions(records, {"NAN": {}}, {"NAN": {"option_chain_dataset_id": "ds"}},
                                         fetch_chain=lambda t: prices(), parse_context=parse, select_contract=select)
    assert len(out) == 3 and all(r["Expression_Status"] == "CONTRACT_FOUND" for r in out)
    assert len(calls) == 1
    assert [r["contract__target"] for r in out] == [15., 16., 17.]


def test_vanguard_retains_exact_cohort_membership():
    from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine
    engine = ActuarialQueryEngine.__new__(ActuarialQueryEngine)
    engine.df = pd.DataFrame({"a": ["A", "B"] * 50, "b": ["X"] * 100})
    engine._match_norm_cache = {}
    actual = engine._filter_by_dims(engine.df, {"a": "A", "b": "X"}, ["a", "b"])
    pd.testing.assert_frame_equal(actual, engine.df.iloc[::2])


def test_vanguard_missing_dimensions_still_mean_empty():
    from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine
    engine = ActuarialQueryEngine.__new__(ActuarialQueryEngine)
    engine.df = prices()
    engine._match_norm_cache = {}
    assert engine._filter_by_dims(engine.df, {}, ["absent"]).empty


@pytest.mark.parametrize("index", [[0, 1, 2, 3], [2, 2, 1, 1], [5, 2, 8, 0]])
@pytest.mark.parametrize("values", [{"a": "A", "b": "X"}, {"a": "ABSENT", "b": "X"}, {"a": None, "b": "X"}])
def test_vanguard_membership_and_order_match_legacy_with_missing_and_duplicate_labels(index, values):
    from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine
    engine = ActuarialQueryEngine.__new__(ActuarialQueryEngine)
    engine.df = pd.DataFrame({"a": ["A", "B", None, "A"], "b": ["X", "X", "X", "Y"]}, index=index)
    engine._match_norm_cache = {}
    mask = None
    for dim in ["a", "b"]:
        if values[dim] is not None:
            current = engine._normalised_match_series(dim).eq(values[dim])
            mask = current if mask is None else mask & current
    expected = engine.df.loc[mask]
    actual = engine._filter_by_dims(engine.df, values, ["a", "b"])
    pd.testing.assert_frame_equal(actual, expected)


def test_failed_context_parses_are_retried_and_preserve_error_rows():
    from scripts.options_candidate_lane import evaluate_candidate_expressions
    records = [{"Candidate_ID": str(i), "Ticker": "SYM", "Handoff_Rank": i, "Direction": "BULL"} for i in range(3)]
    calls = []
    def parse(row):
        calls.append(1)
        raise ValueError("saved invalid input")
    rows = evaluate_candidate_expressions(records, {"SYM": {}}, {"SYM": {"option_chain_dataset_id": "ds"}},
              fetch_chain=lambda t: None, parse_context=parse, select_contract=lambda c, x: None)
    assert calls == [1, 1, 1]
    assert [r["Expression_Status"] for r in rows] == ["ERROR:ValueError"] * 3


@pytest.mark.parametrize("persist", [True, False])
def test_production_fetcher_preserves_saved_prices_and_default_write_contract(persist):
    import requests
    calls = []
    bridge = types.ModuleType("canonical_data.history_bridge")
    bridge.write_through_fetched_history = lambda *a, **k: calls.append(k)
    from unittest.mock import patch
    raw = {"status": "OK", "results": [{"t": 1794268800000, "o": 10., "h": 12., "l": 9., "c": 11., "v": 100}]}
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return raw
    # Extract just the method, not the module's credential/logging bootstrap.
    tree = ast.parse((ROOT / "polygon_data_fetcher.py").read_text(encoding="utf-8-sig"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PolygonDataFetcher")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "fetch_daily_bars")
    unit = ast.Module(body=[method], type_ignores=[])
    env = dict(pd=pd, os=os, Optional=__import__("typing").Optional, requests=requests, logger=logging.getLogger("offline"))
    exec(compile(ast.fix_missing_locations(unit), "saved_fetcher", "exec"), env)
    owner = types.SimpleNamespace(rate_limiter=types.SimpleNamespace(wait_if_needed=lambda: None),
                 session=types.SimpleNamespace(get=lambda *a, **k: Response()), base_url="https://offline.invalid", api_key="not-a-key")
    with patch.dict(sys.modules, {"canonical_data.history_bridge": bridge}):
        kwargs = {} if persist else {"persist_history": False}
        result = env["fetch_daily_bars"](owner, "SYM", "2026-11-10", "2026-11-10", **kwargs)
    assert result["close"].tolist() == [11.]
    assert len(calls) == int(persist)
