"""Market intelligence v5.4.3: a Polygon rate limit must not wipe out the producer (19 Oct 2026).

The 13:35 UK pre-open run got HTTP 429 "Too Many Requests" on its five FX requests; the client gave up at the
first refusal, FX_Spot came back 100% null and the collection guard wrote no outputs at all (overnight
capture, sectors, ETFs). Rule: on 429 wait (Polygon's Retry-After when given, else a short backoff) and try
again a few times; other HTTP errors are not retried. Written before the fix."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "Enhancements" / "colab" / "avshunter_market_intelligence_v5_4_3.py"


@pytest.fixture
def mi(monkeypatch):
    spec = importlib.util.spec_from_file_location("mi_v543_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.COLLECTION_ERRORS.clear()
    slept = []
    monkeypatch.setattr(module.time, "sleep", lambda s: slept.append(s))
    module._slept = slept
    return module


class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload or {}, headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)


def _queue(monkeypatch, mi, responses):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return responses.pop(0)
    monkeypatch.setattr(mi.requests, "get", fake_get)
    return calls


def test_a_rate_limited_request_waits_and_succeeds_on_retry(mi, monkeypatch):
    calls = _queue(monkeypatch, mi, [_Resp(429, headers={"Retry-After": "7"}), _Resp(200, {"results": [{"c": 1}]})])
    data = mi.PolygonExtractor("k").get_data("C:EURUSD")
    assert data == {"results": [{"c": 1}]} and len(calls) == 2
    assert 7 in mi._slept                                              # Polygon's Retry-After is honoured
    assert mi.COLLECTION_ERRORS == []


def test_without_retry_after_it_backs_off_and_gives_up_after_the_last_attempt(mi, monkeypatch):
    calls = _queue(monkeypatch, mi, [_Resp(429) for _ in range(mi.POLYGON_MAX_ATTEMPTS)])
    assert mi.PolygonExtractor("k").get_data("C:GBPUSD") == {}
    assert len(calls) == mi.POLYGON_MAX_ATTEMPTS
    waits = [s for s in mi._slept if s >= 1]
    assert len(waits) == mi.POLYGON_MAX_ATTEMPTS - 1 and waits == sorted(waits)   # growing backoff
    assert len(mi.COLLECTION_ERRORS) == 1 and "429" in mi.COLLECTION_ERRORS[0]


def test_other_http_errors_are_not_retried(mi, monkeypatch):
    calls = _queue(monkeypatch, mi, [_Resp(403)])
    assert mi.PolygonExtractor("k").get_data("I:SPX") == {} and len(calls) == 1
