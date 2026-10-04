"""S3 red/green read-only, as-of canonical OHLCV path tests."""

import json
import sqlite3

from canonical_data.forecast_path_reader import read_price_path
from canonical_data.forecast_outcome_panel import build_outcome_panel_row
from domain.forecast_path_label import label_forecast_path
from domain.ticker_forecast import ForecastDirection, ForecastState, TickerForecast
import pytest


def _db(path):
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE ohlcv_ingest_batches (
                batch_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL
            );
            CREATE TABLE ohlcv_daily (
                ticker TEXT, trading_date TEXT, adjustment_convention TEXT,
                open REAL, high REAL, low REAL, close REAL, bar_status TEXT,
                provider TEXT, observed_at TEXT, current_batch_id TEXT
            );
            CREATE TABLE ohlcv_daily_revisions (
                revision_id INTEGER PRIMARY KEY, ticker TEXT, trading_date TEXT,
                adjustment_convention TEXT, previous_values_json TEXT,
                previous_provider TEXT, previous_batch_id TEXT, revised_at TEXT
            );
        """)
    return path


def _bar(path, *, day, high=104, low=96, status="COMPLETE", batch="B1",
         observed="2026-09-28T21:00:00Z", convention="POLYGON_SPLIT_ADJUSTED"):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO ohlcv_ingest_batches VALUES (?, ?)",
            (batch, observed),
        )
        connection.execute(
            "INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("XYZ", day, convention, 100, high, low, 100, status,
             "POLYGON", observed, batch),
        )


def test_weekend_and_holiday_are_not_missing_sessions(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    _bar(path, day="2026-11-27", observed="2026-11-27T22:00:00Z")
    _bar(path, day="2026-11-30", observed="2026-11-30T22:00:00Z", batch="B2")
    result = read_price_path(
        path, ticker="XYZ", start_session="2026-11-25", horizon_sessions=2,
        label_cutoff_utc="2026-12-01T12:00:00Z",
    )
    assert [(bar.session, bar.trading_date) for bar in result.bars] == [
        (1, "2026-11-27"), (2, "2026-11-30"),
    ]
    assert result.missing_sessions == ()
    assert result.horizon_matured is True
    assert result.read_only is True


def test_revision_after_cutoff_cannot_be_backdated_into_outcome(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    _bar(path, day="2026-09-28", high=120, batch="B2",
         observed="2026-09-30T21:00:00Z")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO ohlcv_ingest_batches VALUES (?, ?)",
                           ("B1", "2026-09-28T21:00:00Z"))
        connection.execute(
            "INSERT INTO ohlcv_daily_revisions VALUES (?,?,?,?,?,?,?,?)",
            (1, "XYZ", "2026-09-28", "POLYGON_SPLIT_ADJUSTED",
             json.dumps(dict(open=100, high=104, low=96, close=100,
                             volume=1000, bar_status="COMPLETE")),
             "POLYGON", "B1", "2026-09-30T21:00:00Z"),
        )
    earlier = read_price_path(
        path, ticker="XYZ", start_session="2026-09-25", horizon_sessions=1,
        label_cutoff_utc="2026-09-29T21:00:00Z",
    )
    later = read_price_path(
        path, ticker="XYZ", start_session="2026-09-25", horizon_sessions=1,
        label_cutoff_utc="2026-10-01T21:00:00Z",
    )
    assert earlier.bars[0].high == 104
    assert earlier.bars[0].batch_id == "B1"
    assert earlier.revision_rewinds == 1
    assert later.bars[0].high == 120
    assert later.bars[0].batch_id == "B2"
    earlier_label = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95, future_bars=[bar.to_label_bar() for bar in earlier.bars],
        horizon_sessions=1, horizon_matured=earlier.horizon_matured,
    )
    later_label = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95, future_bars=[bar.to_label_bar() for bar in later.bars],
        horizon_sessions=1, horizon_matured=later.horizon_matured,
    )
    assert earlier_label.event == "NEITHER"
    assert later_label.event == "TARGET_FIRST"


def test_late_acquired_and_partial_bar_remain_missing(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    _bar(path, day="2026-09-28", observed="2026-10-01T21:00:00Z")
    _bar(path, day="2026-09-29", observed="2026-09-29T21:00:00Z",
         batch="B2", status="PARTIAL")
    result = read_price_path(
        path, ticker="XYZ", start_session="2026-09-25", horizon_sessions=2,
        label_cutoff_utc="2026-09-30T21:00:00Z",
    )
    assert result.bars == ()
    assert result.missing_sessions == (1, 2)
    assert result.horizon_matured is True


def test_adjustment_convention_must_match_exactly(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    _bar(path, day="2026-09-28", convention="UNADJUSTED")
    result = read_price_path(
        path, ticker="XYZ", start_session="2026-09-25", horizon_sessions=1,
        label_cutoff_utc="2026-09-29T21:00:00Z",
    )
    assert result.bars == ()
    assert result.missing_sessions == (1,)


def _forecast(*, target=110, stop=95):
    return TickerForecast(
        run_id="R", thesis_id="T", ticker="XYZ",
        evidence_session="2026-09-25", as_of_utc="2026-09-25T20:30:00Z",
        direction=ForecastDirection.BULL,
        forecast_state=ForecastState.DESCRIPTIVE_ONLY,
        reference_spot=100, target_spot=target, invalidation_spot=stop,
    )


def test_panel_row_binds_forecast_identity_path_lineage_and_outcome(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    _bar(path, day="2026-09-28", high=112,
         observed="2026-09-28T21:00:00Z")
    row = build_outcome_panel_row(
        _forecast(), path, horizon_sessions=5,
        label_cutoff_utc="2026-09-29T21:00:00Z",
    )
    assert (row.run_id, row.thesis_id, row.ticker) == ("R", "T", "XYZ")
    assert row.event == "TARGET_FIRST"
    assert row.event_session == 1
    assert row.data_status == "RESOLVED_EVENT"
    assert row.bar_version_fingerprints and len(row.bar_version_fingerprints) == 1
    assert row.authority == "RESEARCH_ONLY"


def test_panel_keeps_missing_geometry_explicit_and_never_invents_target(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    row = build_outcome_panel_row(
        _forecast(target=None), path, horizon_sessions=5,
        label_cutoff_utc="2026-09-29T21:00:00Z",
    )
    assert row.event == "NOT_LABELLED"
    assert row.data_status == "MISSING_GEOMETRY"
    assert row.bar_version_fingerprints == ()


def test_panel_rejects_label_cutoff_before_frozen_forecast(tmp_path) -> None:
    path = _db(tmp_path / "prices.sqlite")
    with pytest.raises(ValueError, match="forecast"):
        build_outcome_panel_row(
            _forecast(), path, horizon_sessions=5,
            label_cutoff_utc="2026-09-25T19:00:00Z",
        )


def test_panel_rejects_forecast_published_after_first_future_session(tmp_path) -> None:
    from dataclasses import replace

    path = _db(tmp_path / "prices.sqlite")
    late = replace(_forecast(), as_of_utc="2026-09-29T21:00:00Z")
    with pytest.raises(ValueError, match="completed session"):
        build_outcome_panel_row(
            late, path, horizon_sessions=5,
            label_cutoff_utc="2026-09-30T21:00:00Z",
        )


def test_panel_rejects_forecast_published_during_first_future_session(tmp_path) -> None:
    from dataclasses import replace

    path = _db(tmp_path / "prices.sqlite")
    intraday = replace(_forecast(), as_of_utc="2026-09-28T18:00:00Z")
    with pytest.raises(ValueError, match="future session"):
        build_outcome_panel_row(
            intraday, path, horizon_sessions=5,
            label_cutoff_utc="2026-09-30T21:00:00Z",
        )
