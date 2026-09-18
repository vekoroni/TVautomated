"""Reselected contract: quote and liquidity from the session's stored chain.

Business rule (ACK, 17 Sep 2026): when the Lab reselects a contract for the
governed direction (CONTRACT_RESELECTED_FOR_DIRECTION), the reselected
contract's quote is established from the canonical option chain already stored
for the run's completed session -- never from a provider call.

* Hit with bid > 0 and ask > 0: the row's contract quote (bid, ask, mid, spread,
  sizes, quote timestamp, DTE, greeks, OI, volume) is that stored observation,
  its source and dataset id are recorded, the not-established flag is cleared,
  and liquidity is classified by the existing owner exactly as for a normally
  selected EOD contract (same DTE requirement, moneyness and executability
  classifiers, same session-aligned quote treatment).
* Symbol not stored, or not two-sided: today's behaviour is kept (quote and
  liquidity missing with reason, row stays MANUAL_REVIEW) and the lookup
  outcome is recorded (CHAIN_LOOKUP_MISS / CHAIN_QUOTE_NOT_TWO_SIDED /
  CHAIN_STORE_UNAVAILABLE).
* The store is read-only: no network, no provider fetch, no registry write.
"""
from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from contracts.lab_control import opportunity_book_row
from domain.option_contract_liquidity import LifecycleInputs, evaluate_options_liquidity_lifecycle
from tests.test_book_integrity_e3_e4_e5_e7 import CALL_OCC, PUT_OCC, _sig

NOT_ESTABLISHED = "CONTRACT_QUOTE_NOT_ESTABLISHED_FOR_RESELECTED_CONTRACT"
SESSION = "2026-09-04"


def _chain_row(symbol: str = PUT_OCC, **overrides) -> dict:
    row = {
        "symbol": symbol, "underlying": "AAPL", "right": "P", "strike": 95.0,
        "expiration_date": "2026-09-18", "dte": 14.0,
        "bid": 1.00, "ask": 1.08, "mid": 1.04, "spread_pct": 0.0769,
        "bid_size": 12, "ask_size": 20, "bid_size_quality": "OBSERVED_POSITIVE",
        "ask_size_quality": "OBSERVED_POSITIVE", "quote_quality": "TWO_SIDED",
        "quote_timestamp_utc": "2026-09-04T20:00:00Z", "quote_source": "MARKETDATA",
        "delta": -0.42, "gamma": 0.05, "theta": -0.04, "vega": 0.09, "implied_vol": 0.33,
        "open_interest": 1250.0, "volume": 310.0, "underlying_price": 100.0,
        "quality_flags": "", "last": None, "contract_multiplier": None,
    }
    row.update(overrides)
    return row


class _FakeLookup:
    """Injected adapter double; records calls, never fetches."""

    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _hit(quote: dict):
    from canonical_data.session_chain_quote_lookup import CHAIN_LOOKUP_HIT, ChainQuoteLookupResult

    return ChainQuoteLookupResult(
        state=CHAIN_LOOKUP_HIT, quote=quote, dataset_id="DS-CHAIN-AAPL-0904",
        session_date=SESSION, reason="",
    )


def _miss(state: str = "CHAIN_LOOKUP_MISS", reason: str = "SYMBOL_NOT_IN_STORED_CHAIN"):
    from canonical_data.session_chain_quote_lookup import ChainQuoteLookupResult

    return ChainQuoteLookupResult(state=state, quote=None, dataset_id=None, session_date=SESSION, reason=reason)


def _reselected_sig(**extra) -> dict:
    return _sig(
        "PUT", contract_symbol=CALL_OCC, recommended_contract=PUT_OCC,
        evidence_session_date=SESSION, planned_hold_sessions=5.0,
        thesis_state="ACTIVE", morning_transition_state="EOD_PENDING_MORNING_REQUOTE",
        lifecycle_contract_version="OPTIONS-LIQUIDITY-LIFECYCLE-V2",
        liquidity_state="QUOTE_TIMESTAMP_UNAVAILABLE", **extra,
    )


# ─── Hit: quote and liquidity established from the stored chain ─────────────

def test_hit_establishes_the_reselected_contracts_quote_with_recorded_source() -> None:
    lookup = _FakeLookup(_hit(_chain_row()))
    row = opportunity_book_row(_reselected_sig(), "RUN-BI", 1, contract_quote_lookup=lookup)
    assert lookup.calls == [{"ticker": "AAPL", "symbol": PUT_OCC, "session_date": SESSION}]
    assert row["contract_symbol"] == PUT_OCC
    assert row["contract_bid"] == 1.00
    assert row["contract_ask"] == 1.08
    assert row["contract_mid"] == 1.04
    assert row["premium_mid"] == 1.04
    assert row["spread_pct_of_mid"] == pytest.approx(7.6923, abs=1e-3)
    assert row["contract_bid_size"] == 12
    assert row["contract_ask_size"] == 20
    assert row["selected_quote_timestamp_utc"] == "2026-09-04T20:00:00Z"
    assert row["quote_as_of"] == "2026-09-04T20:00:00Z"
    assert row["dte"] == 14.0
    assert row["contract_delta"] == -0.42
    assert row["contract_gamma"] == 0.05
    assert row["contract_theta"] == -0.04
    assert row["contract_vega"] == 0.09
    assert row["contract_iv"] == 0.33
    assert row["contract_oi"] == 1250.0
    assert row["contract_volume"] == 310.0
    assert row["contract_source"] == "CANONICAL_CHAIN_SESSION_LOOKUP"
    assert row["selected_quote_dataset_id"] == "DS-CHAIN-AAPL-0904"
    assert NOT_ESTABLISHED not in (row["lab_coherence_flags"] or "")
    # The reselection itself remains recorded.
    assert f"CONTRACT_RESELECTED_FOR_DIRECTION:{CALL_OCC}->{PUT_OCC}" in row["lab_coherence_flags"]


def test_hit_classifies_liquidity_exactly_as_the_normal_eod_path() -> None:
    lookup = _FakeLookup(_hit(_chain_row()))
    row = opportunity_book_row(_reselected_sig(), "RUN-BI", 1, contract_quote_lookup=lookup)
    # The normal EOD Options path: composite lifecycle owner, session-aligned
    # quote (no provider quote age), spot from the same chain observation.
    normal = evaluate_options_liquidity_lifecycle(LifecycleInputs(
        side="PUT", spot=100.0, strike=95.0, delta=-0.42, bid=1.00, ask=1.08, dte=14.0,
        remaining_hold_sessions=5.0, forecast_vol_annual=0.30, thesis_spot=100.0,
        current_spot=100.0, structural_target=90.0, invalidation_spot=105.0,
        quote_age_seconds=None, listed_market=True,
    ))
    for field in ("recovery_disposition", "moneyness_state", "delta_band", "minimum_required_dte"):
        assert row[field] == normal[field], field
    assert row["executable_now"] in (normal["executable_now"], str(normal["executable_now"]))
    # Same label as the normal EOD path writes (18 Sep 2026): a stored quote with a provider timestamp awaits
    # the morning re-quote; it is not "timestamp unavailable".
    assert normal["liquidity_state"] == "QUOTE_TIMESTAMP_UNAVAILABLE"
    assert row["liquidity_state"] == "EOD_QUOTE_PENDING_MORNING_REQUOTE"
    assert row["dte_buffer_sessions"] == pytest.approx(14.0 - normal["minimum_required_dte"])
    assert row["quote_freshness"] == "SESSION_ALIGNED"


def test_hit_with_dte_below_the_hold_requirement_is_classified_not_hidden() -> None:
    lookup = _FakeLookup(_hit(_chain_row(dte=6.0)))
    row = opportunity_book_row(_reselected_sig(), "RUN-BI", 1, contract_quote_lookup=lookup)
    assert row["liquidity_state"] == "DTE_UNSUITABLE"
    assert row["recovery_disposition"] == "CONTRACT_REPAIR"


def test_hit_without_the_hold_input_is_named_incomplete_like_the_normal_path() -> None:
    sig = _reselected_sig()
    sig.pop("planned_hold_sessions")
    row = opportunity_book_row(sig, "RUN-BI", 1, contract_quote_lookup=_FakeLookup(_hit(_chain_row())))
    assert row["contract_ask"] == 1.08
    assert row["liquidity_state"] == "LIFECYCLE_DATA_INCOMPLETE"


# ─── Not two-sided / miss: today's behaviour, outcome recorded ──────────────

@pytest.mark.parametrize("bid, ask", [(0.0, 1.08), (None, 1.08), (1.00, 0.0), (1.00, None)])
def test_zero_or_missing_side_is_not_an_established_quote(bid, ask) -> None:
    lookup = _FakeLookup(_hit(_chain_row(bid=bid, ask=ask)))
    row = opportunity_book_row(_reselected_sig(), "RUN-BI", 1, contract_quote_lookup=lookup)
    for field in ("contract_bid", "contract_ask", "contract_mid", "liquidity_state", "contract_delta"):
        assert row[field] in ("", None), field
    assert NOT_ESTABLISHED in row["lab_coherence_flags"]
    assert "CHAIN_QUOTE_NOT_TWO_SIDED" in row["lab_coherence_flags"]
    assert row["olm_guard_disposition"] == "MANUAL_REVIEW"


@pytest.mark.parametrize("state", ["CHAIN_LOOKUP_MISS", "CHAIN_STORE_UNAVAILABLE"])
def test_miss_keeps_quote_missing_and_row_in_manual_review(state) -> None:
    without = opportunity_book_row(_reselected_sig(), "RUN-BI", 1)
    row = opportunity_book_row(
        _reselected_sig(), "RUN-BI", 1, contract_quote_lookup=_FakeLookup(_miss(state)),
    )
    for field in ("contract_bid", "contract_ask", "liquidity_state", "selected_quote_dataset_id"):
        assert row[field] in ("", None), field
    assert NOT_ESTABLISHED in row["lab_coherence_flags"]
    assert state in row["lab_coherence_flags"]
    assert row["olm_guard_disposition"] == "MANUAL_REVIEW" == without["olm_guard_disposition"]
    assert row["final_action"] == without["final_action"]


@pytest.mark.parametrize("direction, symbol", [("CALL", CALL_OCC), ("PUT", PUT_OCC)])
def test_lookup_is_used_only_for_a_reselected_contract(direction, symbol) -> None:
    lookup = _FakeLookup(_hit(_chain_row()))
    opportunity_book_row(_sig(direction, contract_symbol=symbol), "RUN-BI", 1, contract_quote_lookup=lookup)
    opportunity_book_row(_sig("PUT", contract_symbol=CALL_OCC), "RUN-BI", 1, contract_quote_lookup=lookup)
    assert lookup.calls == []


# ─── Real read-only adapter over a stored registry ──────────────────────────

def _store(tmp_path: Path, rows: list[dict], *, run_id: str = "RUN-BI", session: str = SESSION) -> Path:
    from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
    from canonical_data.registry import CanonicalRegistry

    registry_path = tmp_path / "canonical" / "control_plane.sqlite"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry = CanonicalRegistry(registry_path)
    registry.initialise()
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    payload = tmp_path / "canonical" / "market_observations" / "option_chain" / session / "AAPL" / f"{content_hash}.json"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(encoded)
    session_date = date.fromisoformat(session)
    scope = DataScope(start_date=session_date, end_date=session_date, dte_min=1, dte_max=110,
                      sides=("CALL", "PUT"), extra=(("min_open_interest", "0"),))
    registry.register_dataset(DatasetRecord(
        dataset_id=f"DS-{content_hash[:12]}", dataset_type=DatasetType.OPTION_CHAIN,
        instrument_id="AAPL", session_date=session_date, scope=scope, provider="MARKETDATA",
        content_hash=content_hash, completeness_status=CompletenessStatus.COMPLETE,
        storage_uri=str(payload), observed_at=datetime(2026, 9, 5, 0, 30, tzinfo=timezone.utc),
        as_of=datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc),
        adjustment_convention="RAW_OPTION_CONTRACT", schema_version="option_chain_v2",
        source_run_id=run_id,
    ))
    return registry_path


def _fingerprint(path: Path) -> tuple:
    """Registry, write-ahead log content and payloads.

    SQLite's WAL-index (-shm) and an empty -wal are created by any reader of a
    WAL database; they carry no data. The database, any logged (uncheckpointed)
    content and every payload must be byte-identical.
    """
    files = sorted(
        p for p in path.parent.rglob("*")
        if p.is_file() and not p.name.endswith("-shm")
        and not (p.name.endswith("-wal") and p.stat().st_size == 0)
    )
    return tuple((p.name, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access attempted by a read-only chain lookup")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    import canonical_data.market_observation_resolver as resolver

    def no_resolver(*_args, **_kwargs):
        raise AssertionError("the fetching resolver must not be used for a reuse-only lookup")

    monkeypatch.setattr(resolver.CanonicalMarketObservationResolver, "__init__", no_resolver)


def test_adapter_hit_reads_the_stored_session_chain_without_fetch_or_write(tmp_path, no_network) -> None:
    from canonical_data.session_chain_quote_lookup import CHAIN_LOOKUP_HIT, StoredSessionChainQuoteLookup

    registry_path = _store(tmp_path, [_chain_row(CALL_OCC, right="C", strike=100.0), _chain_row()])
    before = _fingerprint(registry_path)
    lookup = StoredSessionChainQuoteLookup(registry_path, run_id="RUN-BI")
    result = lookup(ticker="AAPL", symbol="O:" + PUT_OCC, session_date=SESSION)
    assert result.state == CHAIN_LOOKUP_HIT
    assert result.quote["symbol"] == PUT_OCC
    assert result.quote["ask"] == 1.08
    assert result.dataset_id.startswith("DS-")
    assert _fingerprint(registry_path) == before


def test_adapter_miss_is_named_and_never_fetches(tmp_path, no_network) -> None:
    from canonical_data.session_chain_quote_lookup import CHAIN_LOOKUP_MISS, StoredSessionChainQuoteLookup

    registry_path = _store(tmp_path, [_chain_row(CALL_OCC, right="C", strike=100.0)])
    before = _fingerprint(registry_path)
    lookup = StoredSessionChainQuoteLookup(registry_path, run_id="RUN-BI")
    absent = lookup(ticker="AAPL", symbol=PUT_OCC, session_date=SESSION)
    assert absent.state == CHAIN_LOOKUP_MISS
    assert absent.reason == "SYMBOL_NOT_IN_STORED_CHAIN"
    other_session = lookup(ticker="AAPL", symbol=PUT_OCC, session_date="2026-09-03")
    assert other_session.state == CHAIN_LOOKUP_MISS
    assert other_session.reason == "NO_STORED_CHAIN_FOR_SESSION"
    unknown = lookup(ticker="AAPL", symbol=PUT_OCC, session_date="")
    assert unknown.state == CHAIN_LOOKUP_MISS
    assert unknown.reason == "SESSION_DATE_UNKNOWN"
    assert _fingerprint(registry_path) == before


def test_adapter_rejects_a_payload_that_fails_integrity(tmp_path, no_network) -> None:
    from canonical_data.session_chain_quote_lookup import CHAIN_LOOKUP_MISS, StoredSessionChainQuoteLookup

    registry_path = _store(tmp_path, [_chain_row()])
    payload = next((tmp_path / "canonical" / "market_observations").rglob("*.json"))
    payload.write_bytes(payload.read_bytes().replace(b"1.08", b"0.08"))
    result = StoredSessionChainQuoteLookup(registry_path, run_id="RUN-BI")(
        ticker="AAPL", symbol=PUT_OCC, session_date=SESSION,
    )
    assert result.state == CHAIN_LOOKUP_MISS
    assert "INTEGRITY" in result.reason


def test_adapter_without_a_registry_is_unavailable_and_creates_nothing(tmp_path, no_network) -> None:
    from canonical_data.session_chain_quote_lookup import CHAIN_STORE_UNAVAILABLE, StoredSessionChainQuoteLookup

    registry_path = tmp_path / "canonical" / "control_plane.sqlite"
    result = StoredSessionChainQuoteLookup(registry_path, run_id="RUN-BI")(
        ticker="AAPL", symbol=PUT_OCC, session_date=SESSION,
    )
    assert result.state == CHAIN_STORE_UNAVAILABLE
    assert not registry_path.exists()
    assert not registry_path.parent.exists()


def test_book_writer_wires_the_read_only_adapter_for_the_run(tmp_path, no_network) -> None:
    from contracts.lab_control import write_final_opportunity_book

    runs_dir = tmp_path / "output" / "runs"
    (runs_dir / "RUN-BI").mkdir(parents=True)
    registry_path = _store(tmp_path, [_chain_row()])
    before = _fingerprint(registry_path)
    book = write_final_opportunity_book(
        "RUN-BI", [_reselected_sig()], {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        runs_dir, sync_interpreter=False,
    )
    row = book["rows"][0]
    assert row["contract_symbol"] == PUT_OCC
    assert float(row["contract_ask"]) == 1.08
    assert row["contract_source"] == "CANONICAL_CHAIN_SESSION_LOOKUP"
    assert row["liquidity_state"] == "EOD_QUOTE_PENDING_MORNING_REQUOTE"
    assert NOT_ESTABLISHED not in (row["lab_coherence_flags"] or "")
    assert _fingerprint(registry_path) == before
