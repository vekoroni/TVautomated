from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import morning_gate
from canonical_data.macro_packet_archive import (
    archive_macro_packet,
    load_macro_packet_by_id,
)
from domain.run_planning import (
    OperatorMode,
    RequestedAction,
    RunCondition,
    RunPlanningContext,
    resolve_plan,
    resolve_run_condition,
)
from domain.session_authority import SessionFacts, SessionPhase
from scripts.macro_quant_packet import build_macro_quant_packet


def _context(phase: SessionPhase, **changes) -> RunPlanningContext:
    values = dict(
        as_of_utc=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        evidence_cutoff_utc=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        session_facts=SessionFacts(
            phase=phase,
            last_completed_session=date(2026, 9, 11),
            current_session=date(2026, 9, 14),
        ),
        existing_thesis_id="thesis-1",
        existing_thesis_session=date(2026, 9, 11),
        authorised_tickers=("AAA",),
        pipeline_run_id="RUN-1",
    )
    values.update(changes)
    return RunPlanningContext(**values)


def test_run_condition_vocabulary_is_central_and_complete() -> None:
    assert {item.value for item in RunCondition} == {
        "NORMAL_COMPLETED_SESSION",
        "FORCED_INTRASESSION",
        "PREOPEN_THESIS_CHECK",
        "POSTOPEN_CONTRACT_REFRESH",
        "REPLAY",
        "TEST",
    }


@pytest.mark.parametrize(
    ("phase", "mode", "expected"),
    [
        (SessionPhase.PREMARKET, OperatorMode.STANDARD, "PREOPEN_THESIS_CHECK"),
        (SessionPhase.REGULAR, OperatorMode.STANDARD, "POSTOPEN_CONTRACT_REFRESH"),
        (SessionPhase.REGULAR, OperatorMode.FORCE, "FORCED_INTRASESSION"),
        (SessionPhase.AFTER_HOURS, OperatorMode.REPLAY, "REPLAY"),
        (SessionPhase.AFTER_HOURS, OperatorMode.TEST, "TEST"),
    ],
)
def test_run_condition_resolution(phase, mode, expected) -> None:
    assert resolve_run_condition(
        requested_action=RequestedAction.VALIDATE,
        session_phase=phase,
        operator_mode=mode,
    ).value == expected


def test_preopen_plan_has_no_option_quote_requirement() -> None:
    plan = resolve_plan(
        requested_action=RequestedAction.VALIDATE,
        context=_context(SessionPhase.PREMARKET),
    )
    assert plan.run_condition == "PREOPEN_THESIS_CHECK"
    assert "SURVIVOR_OPTION_REFRESH" not in plan.stages_to_run
    assert {item.dataset_type for item in plan.datasets_required} == {"UNDERLYING_NBBO"}


def test_postopen_plan_refreshes_contract() -> None:
    plan = resolve_plan(
        requested_action=RequestedAction.VALIDATE,
        context=_context(SessionPhase.REGULAR),
    )
    assert plan.run_condition == "POSTOPEN_CONTRACT_REFRESH"
    assert "SURVIVOR_OPTION_REFRESH" in plan.stages_to_run
    assert "EXACT_OPTION_QUOTE" in {item.dataset_type for item in plan.datasets_required}


def test_preopen_fetch_never_calls_options_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        morning_gate,
        "_fetch_live_price",
        lambda ticker: {"live_price": 101.0, "live_data_source": "FIXTURE"},
    )
    monkeypatch.setattr(
        morning_gate,
        "_fetch_live_contract",
        lambda symbol: pytest.fail("option quote provider called during pre-open"),
    )
    monkeypatch.setattr(
        morning_gate,
        "_fetch_options_skew",
        lambda ticker: pytest.fail("option chain provider called during pre-open"),
    )
    row = {
        "ticker": "AAA",
        "contract_symbol": "AAA260918C00100000",
        "quote_source_dataset_id": "prior-chain",
        "contract_quote_timestamp": "2026-09-11T19:59:00Z",
    }
    result = morning_gate._fetch_all_live(
        [row], execution_mode="PREOPEN_THESIS_CHECK"
    )["AAA"]
    assert result["morning_quote_evidence_state"] == "HISTORICAL"
    assert result["quote_fetch_timestamp_utc"] == ""


def test_provider_timestamp_never_falls_back_to_fetch_time() -> None:
    assert morning_gate._normalise_provider_timestamp(None) is None
    assert morning_gate._normalise_provider_timestamp(0) == "1970-01-01T00:00:00Z"
    source = Path(morning_gate.__file__).read_text(encoding="utf-8")
    assert 'live.get("live_options_fetched_at")\n                or _utc_now()' not in source
    assert 'last_quote.get("t") or _utc_now()' not in source


def test_macro_packet_archive_is_idempotent_and_replay_is_by_id(tmp_path: Path) -> None:
    packet = build_macro_quant_packet(
        {
            "contract_version": "macro_contract_v1_0",
            "as_of_utc": "2026-09-11T20:00:00Z",
            "report_date": "2026-09-11",
            "regime_state": "TRANSITIONAL",
            "dir_bias": "NEUTRAL",
        },
        "fixture.json",
        now=datetime(2026, 9, 11, 20, tzinfo=timezone.utc),
    )
    first = archive_macro_packet(packet, tmp_path)
    second = archive_macro_packet(packet, tmp_path)
    assert first == second
    assert load_macro_packet_by_id(packet["macro_packet_id"], tmp_path) == packet
    assert len(list(tmp_path.glob("*.json"))) == 1

