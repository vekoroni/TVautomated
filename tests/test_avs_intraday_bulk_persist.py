"""Bulk intraday persistence (ACK 4 Oct 2026, option a) for the Polygon history backfill.

Pilot: 0.23 s per ticker-session through the per-session resolver (about 16 SQLite connections, two ledger rows
and a pandas validation per session) -> about 54 hours for one year. Business rules:
- The bulk path writes exactly the records the per-session path would write: same bars, files, content hashes,
  dataset ids, scope fingerprints and completeness - Discovery's intraday reader sees no difference.
- VWAP restarts at each session open (it is a running total within a session).
- One request-ledger row per physical provider request (a ticker fetch), not one per session.
- Registration happens in one transaction per ticker and stays idempotent.
- Acquisition is still authorised through the ticker's lifecycle.
"""
from __future__ import annotations

from datetime import date
import sqlite3
import time

import pandas as pd
import pytest

from canonical_data import CanonicalFeatureFlags, CanonicalRegistry, DatasetType
from canonical_data.intraday_bars import CanonicalMinuteBarResolver
from canonical_data.session_clock import is_xnys_session, session_bounds

FLAGS = CanonicalFeatureFlags(enabled=True, write_through=True, stage_gating_enforced=False,
                              offline_replay=False, ohlcv_mode="ACTIVE")
STAGE = "INTRADAY_HISTORY_BACKFILL"


def _sessions(n=3, start=date(2026, 6, 1)):
    out, day = [], start
    while len(out) < n:
        if is_xnys_session(day):
            out.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return out


def _frame(session, price=10.0):
    o, c = session_bounds(session)
    t = pd.date_range(o, c, freq="5min", inclusive="left")
    return pd.DataFrame({"timestamp_utc": t, "open": price, "high": price + 0.5, "low": price - 0.5,
                         "close": price + 0.2, "volume": range(1000, 1000 + len(t))})


def _resolver(tmp_path, name):
    registry = CanonicalRegistry(tmp_path / f"{name}.sqlite"); registry.initialise()
    registry.register_run("RUN", STAGE, date(2026, 6, 30))
    resolver = CanonicalMinuteBarResolver(registry_path=tmp_path / f"{name}.sqlite", payload_root=tmp_path / name,
                                          run_id="RUN", requesting_stage=STAGE, flags=FLAGS)
    resolver.lifecycle.register("RUN", "AAA", stage=STAGE, allowed_capabilities=(DatasetType.INTRADAY_BAR,))
    return registry, resolver


ACQUIRED = pd.Timestamp("2026-10-04T21:00:00Z").to_pydatetime()


def test_bulk_records_are_identical_to_the_per_session_path(tmp_path):
    days = _sessions(3)
    frames = {d: _frame(d, 10 + i) for i, d in enumerate(days)}
    reg_a, single = _resolver(tmp_path, "single")
    for d in days:
        o, c = session_bounds(d)
        single.resolve(ticker="AAA", session_date=d, start_utc=o, end_utc=c, provider="POLYGON",
                       fetch_missing=lambda _t, s, e, f=frames[d]: f.assign(acquired_at_utc=ACQUIRED),
                       interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED", evidence_state="COMPLETED_SESSION")
    reg_b, bulk = _resolver(tmp_path, "bulk")
    written = bulk.persist_completed_sessions(ticker="AAA", sessions=frames, provider="POLYGON", interval_minutes=5,
                                              adjustment_convention="SPLIT_ADJUSTED", physical_requests=1,
                                              acquired_at_utc=ACQUIRED)
    key = lambda r: (r.session_date, r.dataset_id, r.content_hash, r.scope.fingerprint, r.completeness_status.value,
                     r.schema_version, r.provider)
    a = sorted(key(r) for r in reg_a.list_dataset_records(DatasetType.INTRADAY_BAR))
    b = sorted(key(r) for r in reg_b.list_dataset_records(DatasetType.INTRADAY_BAR))
    assert len(written) == 3 and a == b


def test_vwap_restarts_at_each_session(tmp_path):
    days = _sessions(2)
    _, bulk = _resolver(tmp_path, "bulk")
    records = bulk.persist_completed_sessions(ticker="AAA", sessions={d: _frame(d, 10 + 10 * i) for i, d in enumerate(days)},
                                              provider="POLYGON", interval_minutes=5,
                                              adjustment_convention="SPLIT_ADJUSTED", physical_requests=1)
    second = CanonicalMinuteBarResolver._read(sorted(records, key=lambda r: r.session_date)[1])
    assert second["vwap_canonical"].iloc[0] == pytest.approx((20.5 + 19.5 + 20.2) / 3.0)


def test_one_ledger_row_per_provider_request(tmp_path):
    registry, bulk = _resolver(tmp_path, "bulk")
    bulk.persist_completed_sessions(ticker="AAA", sessions={d: _frame(d) for d in _sessions(5)}, provider="POLYGON",
                                    interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED", physical_requests=2)
    rows = sqlite3.connect(tmp_path / "bulk.sqlite").execute(
        "SELECT physical_request_count, resolution FROM api_request_ledger WHERE ticker='AAA'").fetchall()
    assert rows == [(2, "PROVIDER_FETCH")]


def test_registration_is_idempotent(tmp_path):
    registry, bulk = _resolver(tmp_path, "bulk")
    sessions = {d: _frame(d) for d in _sessions(2)}
    for _ in range(2):
        bulk.persist_completed_sessions(ticker="AAA", sessions=sessions, provider="POLYGON", interval_minutes=5,
                                        adjustment_convention="SPLIT_ADJUSTED", physical_requests=1,
                                        acquired_at_utc=ACQUIRED)
    assert len(registry.list_dataset_records(DatasetType.INTRADAY_BAR)) == 2


def test_unauthorised_ticker_is_refused(tmp_path):
    from canonical_data.gateway import FetchNotAuthorised
    _, bulk = _resolver(tmp_path, "bulk")
    with pytest.raises(FetchNotAuthorised):
        bulk.persist_completed_sessions(ticker="ZZZ", sessions={d: _frame(d) for d in _sessions(1)}, provider="POLYGON",
                                        interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED", physical_requests=1)


def test_bulk_path_is_fast(tmp_path):
    days = _sessions(60)
    _, bulk = _resolver(tmp_path, "bulk")
    started = time.perf_counter()
    bulk.persist_completed_sessions(ticker="AAA", sessions={d: _frame(d) for d in days}, provider="POLYGON",
                                    interval_minutes=5, adjustment_convention="SPLIT_ADJUSTED", physical_requests=1)
    assert (time.perf_counter() - started) / len(days) < 0.08
