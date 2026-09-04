from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from canonical_data.run_plan import RequestedAction, resolve_run_plan
from canonical_data.session_clock import SessionSnapshot, SessionState, session_bounds
from orchestrator.dynamic_validation import (
    FrozenThesis,
    UnderlyingObservation,
    persist_validation_event,
    validate_thesis,
    validate_theses,
)


SESSION = date(2026, 8, 31)


def plan(at: datetime):
    return resolve_run_plan(
        requested_action=RequestedAction.VALIDATE,
        as_of_utc=at,
        evidence_cutoff_utc=at,
        existing_thesis_id="THESIS-AAPL",
        existing_thesis_session=SESSION,
        authorised_tickers=("AAPL",),
        pipeline_run_id="PHASE5",
    )


def thesis(direction="CALL"):
    if direction == "CALL":
        return FrozenThesis(
            "THESIS-AAPL", "AAPL", "CALL", SESSION.isoformat(),
            100.0, 110.0, 95.0, "AAPL260918C00100000",
            trigger=101.0, maximum_entry=106.0,
        )
    return FrozenThesis(
        "THESIS-AAPL", "AAPL", "PUT", SESSION.isoformat(),
        100.0, 90.0, 105.0, "AAPL260918P00100000",
        trigger=99.0, maximum_entry=94.0,
    )


def observation(price):
    return UnderlyingObservation(
        "UNDERLYING-1", "AAPL", price, "2026-09-01T13:30:00Z", "DATASET-1"
    )


def gate(_thesis, _underlying, quote, transition, _plan):
    return {
        "action": "ELIGIBLE" if transition == "THESIS_CONFIRMED" and quote else "NO_TRADE",
        "capital_authority": "EXECUTION_GATE",
    }


def test_underlying_invalidation_stops_all_later_acquisition() -> None:
    calls = []
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 13, tzinfo=timezone.utc)),
        thesis(),
        resolve_underlying=lambda *_: observation(94.0),
        resolve_option_quote=lambda *_: calls.append("option"),
        resolve_developing_profile=lambda *_: calls.append("profile"),
        execution_gate=gate,
    )
    assert event.transition == "THESIS_INVALIDATED"
    assert event.gap_pct == -6.0
    assert calls == []
    assert event.execution_gate_result["action"] == "NO_TRADE"


def test_premarket_uses_underlying_and_option_but_never_fabricates_profile() -> None:
    calls = []
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 12, tzinfo=timezone.utc)),
        thesis(),
        resolve_underlying=lambda *_: observation(102.0),
        resolve_option_quote=lambda *_: (calls.append("option") or {"observation_id": "QUOTE-1"}),
        resolve_developing_profile=lambda *_: calls.append("profile"),
        execution_gate=gate,
    )
    assert event.transition == "THESIS_CONFIRMED"
    assert event.profile_evidence_state == "PENDING_MARKET_OPEN"
    assert event.developing_profile_evidence_id is None
    assert calls == ["option"]


def test_regular_session_fetches_profile_only_after_underlying_survives() -> None:
    calls = []
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 15, tzinfo=timezone.utc)),
        thesis(),
        resolve_underlying=lambda *_: (calls.append("underlying") or observation(102.0)),
        resolve_option_quote=lambda *_: (calls.append("option") or {"observation_id": "QUOTE-1"}),
        resolve_developing_profile=lambda *_: (calls.append("profile") or {"evidence_id": "PROFILE-1"}),
        execution_gate=gate,
    )
    assert calls == ["underlying", "option", "profile"]
    assert event.profile_evidence_state == "DEVELOPING_SESSION"
    assert event.developing_profile_evidence_id == "PROFILE-1"
    assert event.direction == "CALL"
    assert event.selected_contract == "AAPL260918C00100000"
    assert event.can_reverse_direction is False


@pytest.mark.parametrize(
    ("direction", "price", "expected"),
    [
        ("CALL", 107.0, "ENTRY_RUNWAY_EXHAUSTED"),
        ("CALL", 94.0, "THESIS_INVALIDATED"),
        ("CALL", 102.0, "THESIS_CONFIRMED"),
        ("PUT", 93.0, "ENTRY_RUNWAY_EXHAUSTED"),
        ("PUT", 106.0, "THESIS_INVALIDATED"),
        ("PUT", 98.0, "THESIS_CONFIRMED"),
    ],
)
def test_directional_geometry_is_symmetric(direction, price, expected) -> None:
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 12, tzinfo=timezone.utc)),
        thesis(direction),
        resolve_underlying=lambda *_: observation(price),
        resolve_option_quote=lambda *_: {"observation_id": "QUOTE-1"},
        execution_gate=gate,
    )
    assert event.transition == expected


@pytest.mark.parametrize(
    ("direction", "target", "invalidation"),
    [
        ("CALL", 90.0, 95.0),   # target is not on the profitable side
        ("CALL", 110.0, 105.0), # invalidation is not on the loss side
        ("PUT", 110.0, 105.0),  # target is not on the profitable side
        ("PUT", 90.0, 95.0),    # invalidation is not on the loss side
    ],
)
def test_frozen_directional_thesis_rejects_wrong_sided_geometry(
    direction, target, invalidation
) -> None:
    """Universal thesis geometry protection for both directional sides.

    This deliberately uses the frozen underlying thesis origin, not an option
    strike: contract moneyness may legitimately change while the thesis target
    and invalidation must never reverse around their completed-session origin.
    """
    with pytest.raises(ValueError, match=f"{direction} thesis geometry"):
        FrozenThesis(
            "THESIS-BAD", "AAPL", direction, SESSION.isoformat(),
            100.0, target, invalidation, "AAPL260918C00100000",
        )


def test_missing_underlying_defers_without_option_call() -> None:
    calls = []
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 12, tzinfo=timezone.utc)),
        thesis(),
        resolve_underlying=lambda *_: (_ for _ in ()).throw(RuntimeError("no quote")),
        resolve_option_quote=lambda *_: calls.append("option"),
        execution_gate=gate,
    )
    assert event.transition == "DATA_DEFERRED"
    assert event.current_price is None
    assert calls == []


def test_option_and_advisory_profile_failures_are_isolated() -> None:
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 15, tzinfo=timezone.utc)),
        thesis(),
        resolve_underlying=lambda *_: observation(102.0),
        resolve_option_quote=lambda *_: (_ for _ in ()).throw(RuntimeError("quote")),
        resolve_developing_profile=lambda *_: (_ for _ in ()).throw(RuntimeError("bars")),
        execution_gate=gate,
    )
    assert event.transition == "THESIS_CONFIRMED"
    assert "OPTION_QUOTE_UNAVAILABLE" in event.data_status
    assert "PROFILE_UNAVAILABLE_ADVISORY" in event.data_status
    assert event.profile_evidence_state == "UNAVAILABLE_PROVIDER"
    assert event.execution_gate_result["action"] == "NO_TRADE"


def test_validation_batch_reports_provider_outage_without_losing_good_event() -> None:
    first = thesis()
    second = FrozenThesis(
        "THESIS-MSFT", "MSFT", "CALL", SESSION.isoformat(), 100.0, 110.0,
        95.0, "MSFT260918C00100000", trigger=101.0, maximum_entry=106.0,
    )
    batch_plan = resolve_run_plan(
        requested_action=RequestedAction.VALIDATE,
        as_of_utc=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        existing_thesis_id="BOOK-1", existing_thesis_session=SESSION,
        authorised_tickers=("AAPL", "MSFT"), pipeline_run_id="PHASE5-BATCH",
    )

    def underlying(item, _plan):
        if item.ticker == "MSFT":
            raise RuntimeError("provider")
        return observation(102.0)

    result = validate_theses(
        batch_plan, (first, second), resolve_underlying=underlying,
        resolve_option_quote=lambda *_: {"observation_id": "QUOTE-1"},
        execution_gate=gate, max_failure_ratio=0.25,
    )
    assert len(result.events) == 2
    assert result.deferred_count == 1
    assert result.failure_ratio == 0.5
    assert result.systemic_failure is True


def test_validation_event_persistence_is_immutable(tmp_path: Path) -> None:
    event = validate_thesis(
        plan(datetime(2026, 9, 1, 12, tzinfo=timezone.utc)),
        thesis(),
        resolve_underlying=lambda *_: observation(102.0),
        resolve_option_quote=lambda *_: {"observation_id": "QUOTE-1"},
        execution_gate=gate,
    )
    path = tmp_path / f"{event.validation_event_id}.json"
    persist_validation_event(event, path)
    persist_validation_event(event, path)
    assert json.loads(path.read_text())["validation_event_id"] == event.validation_event_id
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="different content"):
        persist_validation_event(event, path)


def test_morning_profile_evidence_is_written_to_result_row(monkeypatch) -> None:
    import canonical_data
    import market_structure
    import market_structure.service
    import morning_gate

    open_utc, close_utc = session_bounds(date(2026, 9, 1))
    snapshot = SessionSnapshot(
        SessionState.REGULAR, date(2026, 9, 1), open_utc, close_utc,
        SESSION, open_utc.replace(hour=15),
    )
    monkeypatch.setattr(canonical_data, "session_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(
        canonical_data, "publish_observation_worklist",
        lambda *a, **k: SimpleNamespace(reconciled=True, authorised_count=1),
    )

    class Resolver:
        def __init__(self, **kwargs):
            self.registry = SimpleNamespace(
                get_dataset=lambda _id: SimpleNamespace(content_hash="HASH")
            )

        def resolve(self, **kwargs):
            assert kwargs["provider"] == "MARKETDATA"
            assert kwargs["interval_minutes"] == 5
            assert kwargs["evidence_state"] == "DEVELOPING_SESSION"
            return SimpleNamespace(
                frame=pd.DataFrame(), dataset_ids=("BAR-1",),
                resolution="EXACT_HIT", physical_fetches=0,
            )

    class Store:
        def __init__(self, **kwargs):
            pass

        def persist(self, evidence):
            return SimpleNamespace(dataset_id="MS-1")

    monkeypatch.setattr(canonical_data, "CanonicalMinuteBarResolver", Resolver)
    monkeypatch.setattr(market_structure.service, "CanonicalMarketStructureService", Store)
    monkeypatch.setattr(
        market_structure, "calculate_market_structure_evidence",
        lambda **kwargs: {
            "ms_evidence_id": "EVIDENCE-1",
            "ms_quality_class": "FIVE_MINUTE_ESTIMATED",
            "ms_authority": "ADVISORY_ONLY",
            "ms_can_grant_capital": False,
            "ms_can_reverse_direction": False,
        },
    )
    rows = [{"ticker": "AAPL", "atr14": 2.0, "direction": "CALL"}]
    live = {"AAPL": {"live_price": 102.0}}
    summary = morning_gate._enrich_msi_market_structure(
        run_id="PHASE5", candidates=rows, live_map=live,
        worklist_tickers=("AAPL",), registry=object(), canonical_flags=object(),
    )
    assert summary["calculated"] == 1
    assert rows[0]["ms_evidence_id"] == "EVIDENCE-1"
    assert rows[0]["ms_profile_evidence_state"] == "DEVELOPING_SESSION"
    assert rows[0]["ms_dataset_id"] == "MS-1"


def test_premarket_profile_state_makes_zero_bar_resolver_calls(monkeypatch) -> None:
    import canonical_data
    import morning_gate

    open_utc, close_utc = session_bounds(date(2026, 9, 1))
    snapshot = SessionSnapshot(
        SessionState.PREMARKET, date(2026, 9, 1), open_utc, close_utc,
        SESSION, None,
    )
    monkeypatch.setattr(canonical_data, "session_snapshot", lambda *_: snapshot)
    rows = [{"ticker": "AAPL", "atr14": 2.0, "direction": "CALL"}]
    live = {"AAPL": {"live_price": 102.0}}
    summary = morning_gate._enrich_msi_market_structure(
        run_id="PHASE5", candidates=rows, live_map=live,
        worklist_tickers=("AAPL",), registry=object(), canonical_flags=object(),
    )
    assert summary == {"eligible": 1, "calculated": 0, "unavailable": 0}
    assert rows[0]["ms_profile_evidence_state"] == "PENDING_MARKET_OPEN"
    assert rows[0]["ms_profile_can_grant_capital"] is False
