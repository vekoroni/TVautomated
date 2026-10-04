from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import morning_gate


NOW = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)


def _payload(symbol="AAPL", mid=150.25, updated=None):
    if updated is None:
        updated = int((NOW - timedelta(seconds=20)).timestamp())
    return {"s": "ok", "symbol": [symbol], "mid": [mid], "updated": [updated]}


def test_marketdata_price_requires_exact_symbol_and_provider_timestamp():
    observed = morning_gate._parse_marketdata_stock_price(_payload(), "AAPL", now_utc=NOW)
    assert observed["live_price"] == 150.25
    assert observed["live_data_source"] == "MARKETDATA_SMARTMID"
    assert observed["live_price_kind"] == "SMARTMID_MIDPOINT"
    assert observed["live_price_updated_utc"] == "2026-10-01T14:59:40Z"
    assert "live_open" not in observed
    assert "underlying_bid" not in observed

    mismatched = morning_gate._parse_marketdata_stock_price(_payload(symbol="MSFT"), "AAPL", now_utc=NOW)
    assert "live_price" not in mismatched
    assert mismatched["live_fetch_error"] == "SYMBOL_MISMATCH"

    missing_time = morning_gate._parse_marketdata_stock_price(_payload(updated=""), "AAPL", now_utc=NOW)
    assert "live_price" not in missing_time
    assert missing_time["live_fetch_error"] == "MISSING_PROVIDER_TIMESTAMP"


def test_marketdata_price_rejects_stale_future_and_invalid_midpoint():
    stale = morning_gate._parse_marketdata_stock_price(
        _payload(updated=int((NOW - timedelta(minutes=16)).timestamp())), "AAPL", now_utc=NOW
    )
    assert "live_price" not in stale
    assert stale["live_fetch_error"] == "STALE_PROVIDER_PRICE"

    future = morning_gate._parse_marketdata_stock_price(
        _payload(updated=int((NOW + timedelta(minutes=2)).timestamp())), "AAPL", now_utc=NOW
    )
    assert "live_price" not in future
    assert future["live_fetch_error"] == "FUTURE_PROVIDER_TIMESTAMP"

    zero = morning_gate._parse_marketdata_stock_price(_payload(mid=0), "AAPL", now_utc=NOW)
    assert "live_price" not in zero
    assert zero["live_fetch_error"] == "INVALID_MIDPOINT"


def test_morning_price_fetch_uses_marketdata_prices_not_delayed_quotes(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(_payload(updated=int(datetime.now(timezone.utc).timestamp()))).encode()

    seen = []

    def fake_urlopen(request, timeout):
        seen.append((request.full_url, request.headers, timeout))
        return FakeResponse()

    monkeypatch.setattr(morning_gate, "MARKETDATA_API_KEY", "test-token")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = morning_gate._fetch_live_price("AAPL")
    assert result["live_price"] == 150.25
    assert len(seen) == 1
    assert "/v1/stocks/prices/AAPL/" in seen[0][0]
    assert "/stocks/quotes/" not in seen[0][0]
    assert "polygon" not in seen[0][0]


def test_missing_stock_price_cannot_validate_invalidation():
    assert morning_gate._check_invalidation({"direction": "CALL", "invalidation_price": 100}, None)[0] is False


def test_missing_current_price_does_not_reuse_prior_row_price_for_lifecycle():
    row = {
        "ticker": "AAPL", "thesis_id": "thesis-1", "direction": "CALL",
        "live_price": 150.0, "thesis_spot": 149.0, "strike": 150.0,
        "target_price": 160.0, "invalidation_price": 140.0,
        "dte": 30, "planned_hold_sessions": 10, "hv_30d": 0.25,
        "contract_symbol": "AAPL261030C00150000",
    }
    result = morning_gate._morning_liquidity_lifecycle(
        row, {}, contract_changed=False, economics_recompute_complete=False
    )
    assert result["thesis_state"] == "DATA_INCOMPLETE"
    assert "current_spot" in result["liquidity_lifecycle_reason"]
