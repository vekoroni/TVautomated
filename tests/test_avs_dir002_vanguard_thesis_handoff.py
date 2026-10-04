"""VNG-01: Vanguard observes, but cannot assign, the Discovery thesis side."""

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from vanguard.integration.orchestrator_adapter import OrchestratorAdapter
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts.run_vanguard_from_packages import build_orchestrator_like_payload, signal_to_row


def _bars():
    return [
        {"date": f"2026-09-{day:02d}", "open": 100.0, "high": 101.0,
         "low": 99.0, "close": 100.0, "volume": 1000000}
        for day in range(1, 26)
    ]


def _package(discovery):
    return {
        "ticker": "DIR2", "bar_data_as_of": "2026-09-25",
        "as_of_utc": "2026-10-01T09:00:00Z", "ohlcv_daily": _bars(),
        "discovery": {"ticker": "DIR2", "stock_price": 100.0, **discovery},
    }


def test_adapter_receives_thesis_context_and_evidence_session_not_wall_clock():
    discovery = {
        "thesis__side": "BEAR", "thesis__direction_status": "CONFIRMED_STRUCTURE",
        "thesis__side_assignment_policy_version": "dir_test_v1",
        "sym_bull_invalidation": 95.0, "sym_bear_invalidation": 105.0,
        "sym_bull_target": 115.0, "sym_bear_target": 85.0,
    }
    payload = build_orchestrator_like_payload(_package(discovery))
    assert payload["discovery"]["thesis__side"] == "BEAR"
    result = OrchestratorAdapter().adapt_result(payload)
    assert result.ok, result.error
    ctx = result.v_input.thesis_context
    assert ctx.side == "BEAR"
    assert ctx.direction_status == "CONFIRMED_STRUCTURE"
    assert ctx.policy_version == "dir_test_v1"
    assert ctx.evidence_session == "2026-09-25"
    assert ctx.bull_geometry["invalidation"] == 95.0
    assert ctx.bear_geometry["target"] == 85.0
    assert result.v_input.analysis_timestamp == datetime(2026, 9, 25, tzinfo=timezone.utc)
    row = signal_to_row(
        SimpleNamespace(ticker="DIR2", timestamp="2026-09-25T00:00:00Z"),
        disc=payload["discovery"], thesis_context=ctx,
    )
    assert row["thesis__side"] == "BEAR"
    assert row["thesis_context_status"] == "AVAILABLE"


def test_missing_thesis_context_is_typed_not_evaluated_not_default_call():
    payload = build_orchestrator_like_payload(_package({}))
    result = OrchestratorAdapter().adapt_result(payload)
    assert result.ok, result.error
    ctx = result.v_input.thesis_context
    assert ctx.status == "NOT_EVALUATED"
    assert ctx.reason == "THESIS_CONTEXT_MISSING"
    assert ctx.side is None


def test_vanguard_csv_echo_is_verbatim_and_does_not_infer_side():
    disc = {
        "thesis__side": "UNASSIGNED", "thesis__direction_status": "TREND_ONLY",
        "thesis__side_assignment_policy_version": "dir_test_v1",
    }
    row = signal_to_row(SimpleNamespace(ticker="DIR2", timestamp="2026-09-25T00:00:00Z"), disc=disc)
    for key in disc:
        assert row[key] == disc[key]


def test_adapter_rejects_missing_session_instead_of_using_wall_clock():
    payload = {
        "ticker": "DIR2", "current_price": 100.0,
        "technical_data": {"ohlcv": [{key: value for key, value in bar.items() if key != "date"}
                                      for bar in _bars()]},
    }
    result = OrchestratorAdapter().adapt_result(payload)
    assert result.ok is False
    assert result.reason_codes == ["EVIDENCE_SESSION_MISSING"]


def test_invalid_governed_side_is_not_normalised_into_a_vote():
    payload = build_orchestrator_like_payload(_package({"thesis__side": "BULL|BEAR"}))
    result = OrchestratorAdapter().adapt_result(payload)
    assert result.ok is False
    assert result.reason_codes == ["THESIS_SIDE_INVALID"]


def test_thesis_side_without_policy_identity_is_typed_incomplete():
    payload = build_orchestrator_like_payload(_package({"thesis__side": "BULL"}))
    result = OrchestratorAdapter().adapt_result(payload)
    assert result.ok, result.error
    ctx = result.v_input.thesis_context
    assert ctx.status == "NOT_EVALUATED"
    assert ctx.reason == "THESIS_CONTEXT_INCOMPLETE"
    assert ctx.side is None
    row = signal_to_row(
        SimpleNamespace(ticker="DIR2", timestamp="2026-09-25T00:00:00Z"),
        disc=payload["discovery"], thesis_context=ctx,
    )
    assert row["thesis_context_status"] == "NOT_EVALUATED"
    assert row["thesis_context_reason"] == "THESIS_CONTEXT_INCOMPLETE"


def test_stored_package_adapts_without_fabricating_thesis_or_run_time():
    package_path = Path(__file__).resolve().parents[1] / "data/output/runs/20260926_173730/packages/AAPL.package.json"
    if not package_path.is_file():
        pytest.skip("Retained package not present")
    package = json.loads(package_path.read_text(encoding="utf-8-sig"))
    result = OrchestratorAdapter().adapt_result(build_orchestrator_like_payload(package))
    assert result.ok, result.error
    assert result.v_input.thesis_context.status == "NOT_EVALUATED"
    assert result.v_input.thesis_context.side is None
    assert result.v_input.analysis_timestamp.date().isoformat() == package["bar_data_as_of"]


def test_csv_nan_thesis_values_are_missing_not_an_invalid_direction():
    payload = build_orchestrator_like_payload(_package({
        "thesis__side": float("nan"),
        "thesis__direction_status": float("nan"),
        "thesis__side_assignment_policy_version": float("nan"),
    }))
    result = OrchestratorAdapter().adapt_result(payload)
    assert result.ok, result.error
    assert result.v_input.thesis_context.status == "NOT_EVALUATED"
    assert result.v_input.thesis_context.reason == "THESIS_CONTEXT_MISSING"
