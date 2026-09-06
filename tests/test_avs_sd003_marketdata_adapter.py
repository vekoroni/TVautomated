from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

from canonical_data import (
    MarketDataCandleNoData,
    MarketDataCandleResponse,
    MarketDataStockCandleAdapter,
    session_bounds,
)
from canonical_data.marketdata_stock_candles import parse_marketdata_stock_candles
from scripts.build_completed_market_profiles import _quality_diagnostics


SESSION = date(2026, 9, 3)
PREFLIGHT = (
    Path(__file__).parents[1]
    / "audit"
    / "preflight"
    / "AVS-PRE-001_20260904_075820"
    / "01_responses.jsonl"
)


def _preflight_record(probe: str, ticker: str) -> dict:
    for line in PREFLIGHT.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("probe") == probe and record.get("ticker") == ticker:
            return record
    raise AssertionError(f"missing sanitized preflight record {probe}/{ticker}")


def _full_payload(session: date = SESSION) -> dict:
    open_utc, close_utc = session_bounds(session)
    timestamps = pd.date_range(open_utc, close_utc, freq="5min", inclusive="left")
    prices = [100.0 + index * 0.01 for index in range(len(timestamps))]
    return {
        "s": "ok",
        "t": [int(value.timestamp()) for value in timestamps],
        "o": prices,
        "h": [value + 0.2 for value in prices],
        "l": [value - 0.2 for value in prices],
        "c": [value + 0.05 for value in prices],
        "v": [1000 + index for index in range(len(timestamps))],
    }


def test_real_preflight_utc_shape_is_partial_not_full_session() -> None:
    record = _preflight_record("P1", "SPY")
    payload = json.loads(record["body_first_2kb"])
    frame = parse_marketdata_stock_candles(
        payload,
        ticker="SPY",
        session_date=SESSION,
        interval_minutes=5,
        provider_http_status=record["http_status"],
        provider_headers=record["response_headers"],
    )
    open_utc, close_utc = session_bounds(SESSION)
    usable, diagnostics = _quality_diagnostics(
        frame,
        session_date=SESSION,
        open_utc=open_utc,
        close_utc=close_utc,
        interval_minutes=5,
    )
    assert len(frame) == 30
    assert usable is False
    assert diagnostics["coverage_ratio"] == pytest.approx(30 / 78)
    assert diagnostics["first_region_present"] is False


def test_adapter_serializes_exchange_wall_clock_and_retains_response_evidence() -> None:
    captured: dict = {}

    def request(url, params, headers, timeout):
        captured.update(url=url, params=dict(params), headers=dict(headers), timeout=timeout)
        return MarketDataCandleResponse(
            payload=_full_payload(),
            http_status=203,
            headers={
                "x-api-ratelimit-limit": "100000",
                "x-api-ratelimit-remaining": "94967",
                "x-api-ratelimit-reset": "1788528600",
            },
            acquired_at_utc=datetime(2026, 9, 4, 8, 4, tzinfo=timezone.utc),
        )

    open_utc, close_utc = session_bounds(SESSION)
    frame = MarketDataStockCandleAdapter("token", request_json=request).fetch_range(
        "SPY", open_utc, close_utc - timedelta(minutes=5),
        session_date=SESSION, interval_minutes=5
    )
    assert captured["params"]["from"] == "2026-09-03T09:30:00"
    assert captured["params"]["to"] == "2026-09-03T16:00:00"
    assert "Z" not in captured["params"]["from"]
    assert len(frame) == 78
    assert set(frame["session_segment"]) == {"REGULAR"}
    assert set(frame["provider_http_status"]) == {203}
    assert set(frame["provider_rate_limit_remaining"]) == {"94967"}
    assert frame.attrs["provider_status"] == "ok"


def test_real_preflight_404_no_data_is_a_deferred_provider_result() -> None:
    record = _preflight_record("P6", "ZZZZ")
    payload = json.loads(record["body_first_2kb"])

    def request(*_args):
        return MarketDataCandleResponse(
            payload=payload,
            http_status=record["http_status"],
            headers=record["response_headers"],
            acquired_at_utc=datetime(2026, 9, 4, 8, 1, tzinfo=timezone.utc),
        )

    open_utc, close_utc = session_bounds(SESSION)
    with pytest.raises(MarketDataCandleNoData) as captured:
        MarketDataStockCandleAdapter("token", request_json=request).fetch_range(
            "ZZZZ", open_utc, close_utc, session_date=SESSION, interval_minutes=5
        )
    assert captured.value.response.http_status == 404
    assert captured.value.reason_code == "PROVIDER_NO_DATA"


def test_session_segment_is_derived_per_bar() -> None:
    stamps = pd.to_datetime(
        ["2026-09-03T12:00:00Z", "2026-09-03T13:30:00Z", "2026-09-03T20:00:00Z"]
    )
    payload = {
        "s": "ok",
        "t": [int(value.timestamp()) for value in stamps],
        "o": [100, 101, 102], "h": [101, 102, 103], "l": [99, 100, 101],
        "c": [100.5, 101.5, 102.5], "v": [10, 20, 30],
    }
    frame = parse_marketdata_stock_candles(
        payload, ticker="SPY", session_date=SESSION, interval_minutes=5,
        session_segment="REGULAR",
    )
    assert frame["session_segment"].tolist() == ["PREMARKET", "REGULAR", "AFTER_HOURS"]


def test_early_close_uses_governed_exchange_bounds() -> None:
    early = date(2026, 11, 27)
    captured = {}

    def request(_url, params, _headers, _timeout):
        captured.update(params)
        return MarketDataCandleResponse(
            payload=_full_payload(early), http_status=203, headers={},
            acquired_at_utc=datetime(2026, 11, 28, tzinfo=timezone.utc),
        )

    open_utc, close_utc = session_bounds(early)
    frame = MarketDataStockCandleAdapter("token", request_json=request).fetch_range(
        "SPY", open_utc, close_utc - timedelta(minutes=5),
        session_date=early, interval_minutes=5
    )
    assert captured["to"] == "2026-11-27T13:00:00"
    assert len(frame) == 42


def test_adapter_maps_inclusive_final_bar_to_exclusive_provider_boundary() -> None:
    captured = {}

    def request(_url, params, _headers, _timeout):
        captured.update(params)
        return _full_payload()

    open_utc, close_utc = session_bounds(SESSION)
    MarketDataStockCandleAdapter("token", request_json=request).fetch_range(
        "SPY", close_utc - timedelta(minutes=5), close_utc - timedelta(minutes=5),
        session_date=SESSION, interval_minutes=5,
    )
    assert captured["from"] == "2026-09-03T15:55:00"
    assert captured["to"] == "2026-09-03T16:00:00"
