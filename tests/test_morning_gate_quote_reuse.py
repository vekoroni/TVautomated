"""Morning Gate stored-quote reuse (ACK 17 Sep 2026).

Root cause: the gate treated every ``should_fetch=False`` as a fresh stored quote. In the second same-day morning run
431 contracts whose thesis a prior run had marked MONITOR NOT_REQUIRED / TERMINAL reused an hour-old observation
(CDS_FRESH_QUOTE_HIT), stamped with the current time as its fetch time, and failed execution viability.

Rules:
  R1 a stored observation is reused only while the quote itself is within the freshness window, whatever the fetch
     policy's reason not to poll (monitoring not required, terminal thesis, horizon); an older stored quote never
     stops an operator-requested morning validation from fetching the live quote;
  R2 a reused quote keeps its original acquisition time as the fetch time (never "now").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import morning_gate

OCC = "AAOI261002C00100000"


@dataclass
class _Observation:
    contract_symbol: str = OCC
    bid: float = 6.5
    ask: float = 7.4
    iv: float = 0.87
    delta: float = 0.53
    open_interest: float = 303.0
    volume: float = 105.0
    quote_as_of: datetime = datetime(2026, 9, 17, 16, 22, 45, tzinfo=timezone.utc)
    observed_at: datetime = datetime(2026, 9, 17, 16, 46, 12, tzinfo=timezone.utc)
    source_dataset_id: str = "DATASET"


@dataclass
class _Decision:
    should_fetch: bool
    reason: str
    provider: str | None
    latest_observation: _Observation | None


class _Registry:
    def get_dataset(self, _dataset_id):
        return None


class _Store:
    registry = _Registry()

    def __init__(self, decision: _Decision) -> None:
        self.decision = decision

    def should_fetch(self, *_args, **_kwargs):
        return self.decision


def _fresh() -> _Observation:
    now = datetime.now(timezone.utc)
    return _Observation(quote_as_of=now - timedelta(seconds=10), observed_at=now - timedelta(seconds=5))


def _run(monkeypatch, decision: _Decision, freshness_seconds: int = 60) -> dict:
    calls = {"live": 0}

    def hydrate_live(row, occ):
        calls["live"] += 1
        return {"live_contract_bid": 7.0, "live_contract_ask": 7.3, "live_options_source": "MARKETDATA",
                "live_options_fetched_at": "2026-09-17T17:22:46Z", "selected_contract_symbol": occ}

    def hydrate_cached(occ, fetch, **_kwargs):
        return dict(fetch(occ), selected_contract_symbol=occ)

    monkeypatch.setattr(morning_gate, "_fetch_live_price", lambda ticker: {"live_price": 100.0})
    monkeypatch.setattr(morning_gate, "_hydrate_live_structure", hydrate_live)
    monkeypatch.setattr(morning_gate, "hydrate_selected_structure", hydrate_cached)
    monkeypatch.setattr(morning_gate, "_check_contract", lambda live, spread, row: (True, "OK"))
    monkeypatch.setattr(morning_gate, "_fetch_options_skew", lambda ticker: {})
    monkeypatch.setattr(morning_gate.time, "sleep", lambda _s: None)
    rows = [{"ticker": "AAOI", "thesis_id": "AAOI:CALL:2026-09-16:OLM2", "contract_symbol": OCC}]
    live = morning_gate._fetch_all_live(rows, liquidity_store=_Store(decision),
                                        liquidity_freshness_seconds=freshness_seconds)["AAOI"]
    live["_live_fetches"] = calls["live"]
    return live


def test_r1_monitor_not_required_does_not_reuse_an_old_quote(monkeypatch):
    for reason in ("MONITOR_NOT_REQUIRED", "MONITOR_TERMINAL", "THESIS_INVALIDATED", "HORIZON_EXPIRED"):
        live = _run(monkeypatch, _Decision(False, reason, None, _Observation()))
        assert live["_live_fetches"] == 1, reason
        assert live["live_options_resolution"] == "MARKETDATA_FETCH"
        assert live["live_contract_bid"] == 7.0


def test_r1_fresh_stored_quote_is_reused(monkeypatch):
    for reason in ("FRESH_EXECUTABLE_CONTRACT", "FRESH_CANONICAL_OBSERVATION", "MONITOR_NOT_REQUIRED"):
        live = _run(monkeypatch, _Decision(False, reason, None, _fresh()))
        assert live["_live_fetches"] == 0, reason
        assert live["live_options_resolution"] == "CDS_FRESH_QUOTE_HIT"
        assert live["live_contract_bid"] == 6.5


def test_r2_reused_quote_keeps_its_acquisition_time(monkeypatch):
    observation = _fresh()
    live = _run(monkeypatch, _Decision(False, "FRESH_EXECUTABLE_CONTRACT", None, observation))
    assert live["live_options_fetched_at"] == observation.observed_at.isoformat()
