from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json

import pytest

from canonical_data.narrow_refresh import execute_narrow_refresh
from contracts.quote_change_evidence import (
    ComparisonStatus,
    QuoteSnapshot,
    compare_exact_option_quotes,
)
from contracts.selected_contract_economics import hydrate_selected_structure
from morning_handoff_finalizer import _publish_msi_handoff


SYMBOL = "AAA260918C00100000"


def _snapshot(*, bid: float, ask: float, bid_size: int, ask_size: int, now: datetime) -> QuoteSnapshot:
    return QuoteSnapshot(
        contract_symbol=SYMBOL, dataset_id=f"D:{bid}:{ask}",
        timestamp_utc=now, session_date=date(2026, 8, 30),
        bid=bid, ask=ask, mid=(bid + ask) / 2,
        spread_pct=(ask - bid) / ((bid + ask) / 2),
        bid_size=bid_size, ask_size=ask_size, source="MARKETDATA",
    )


def test_exact_contract_quote_changes_are_computed_not_copied() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    result = compare_exact_option_quotes(
        ticker="AAA", thesis_id="T", trade_idea_id="I", selected_structure_id="S",
        morning=_snapshot(bid=4.0, ask=4.4, bid_size=10, ask_size=12, now=now),
        current=_snapshot(bid=4.5, ask=4.9, bid_size=16, ask_size=20, now=now),
        now=now,
    )
    assert result["comparison_status"] == ComparisonStatus.SAME_CONTRACT.value
    assert result["bid_change"] == 0.5
    assert result["ask_change"] == 0.5
    assert result["bid_size_change"] == 6
    assert result["ask_size_change"] == 8


def test_contract_change_never_emits_misleading_price_delta() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    current = _snapshot(bid=1.0, ask=1.2, bid_size=30, ask_size=40, now=now)
    current = replace(current, contract_symbol="AAA260918C00110000")
    result = compare_exact_option_quotes(
        ticker="AAA", thesis_id="T", trade_idea_id="I", selected_structure_id="S",
        morning=_snapshot(bid=4.0, ask=4.4, bid_size=10, ask_size=12, now=now),
        current=current, now=now,
    )
    assert result["comparison_status"] == ComparisonStatus.CONTRACT_CHANGED.value
    assert result["bid_change"] is None


def test_selected_contract_hydration_preserves_displayed_sizes() -> None:
    quote = {
        "live_contract_bid": 4.0, "live_contract_ask": 4.4,
        "live_contract_mid": 4.2, "live_contract_bid_size": 10,
        "live_contract_ask_size": 12, "contract_bid_size_quality": "OBSERVED_POSITIVE",
        "contract_ask_size_quality": "OBSERVED_POSITIVE", "contract_quote_quality": "TWO_SIDED",
        "live_contract_iv": 0.3, "live_contract_delta": 0.45,
        "live_contract_oi": 100, "live_contract_volume": 20,
        "live_contract_multiplier": 100, "live_options_source": "MARKETDATA",
        "live_options_fetched_at": "2026-08-30T12:00:00+00:00",
    }
    result = hydrate_selected_structure(
        SYMBOL, lambda _: quote, ticker="AAA", direction="CALL", instrument="LONG_CALL",
        fetched_at_utc="2026-08-30T12:00:00+00:00",
    )
    assert result["live_contract_bid_size"] == 10
    assert result["live_contract_ask_size"] == 12
    assert result["contract_size_quality"] == "OBSERVED"


def test_narrow_refresh_calls_injected_owner_once_and_builds_compatible_overlay() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    bundle = {
        "run_id": "R", "ticker": "AAA", "bundle_id": "a4df6c91-a473-4d61-a1e6-61d74ae05b3e",
        "thesis_id": "T", "trade_idea_id": "I", "selected_structure_id": "S",
        "selected_contract_symbol": SYMBOL,
        "governed_record": {
            "session_date": now.date().isoformat(), "morning_contract_symbol": SYMBOL,
            "morning_quote_dataset_id": "BASE", "morning_quote_timestamp_utc": timestamp,
            "morning_contract_bid": 4.0, "morning_contract_ask": 4.4,
            "morning_contract_mid": 4.2, "morning_contract_bid_size": 10,
            "morning_contract_ask_size": 12,
        },
    }
    calls = []
    def fetch(ticker: str, contract: str):
        calls.append((ticker, contract))
        return {
            "current_quote_dataset_id": "CUR", "current_quote_timestamp_utc": timestamp,
            "current_contract_bid": 4.2, "current_contract_ask": 4.6,
            "current_contract_mid": 4.4, "current_contract_bid_size": 15,
            "current_contract_ask_size": 18, "current_quote_source": "MARKETDATA",
            "session_date": now.date().isoformat(),
        }
    result = execute_narrow_refresh(bundle, fetch_current=fetch)
    assert calls == [("AAA", SYMBOL)]
    assert result["provider_calls_made"] == 1
    assert result["overlay"]["bundle_id"] == bundle["bundle_id"]
    assert result["overlay"]["fields"]["contract_mid_change"] == pytest.approx(0.2)


def test_full_flag_morning_publication_passes_production_readiness(tmp_path, monkeypatch) -> None:
    for name in (
        "MSI_V2_CAPTURE", "MSI_CDS_RESOLVER", "MSI_MINUTE_BARS",
        "MSI_STRUCTURE", "MSI_LAB_V3_VIEW", "MSI_MACRO_ADVISORY",
        "MSI_INTERPRETER_RESOLVER",
    ):
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("MSI_SCREEN_ADAPTER", "0")
    run_id = "20260830_120000"
    run_root = tmp_path / run_id
    run_root.mkdir()
    (run_root / "run_meta.json").write_text(
        json.dumps({
            "run_kind": "PRODUCTION", "run_status": "COMPLETED",
            "msi_config_hash": "TEST_HASH",
            "msi_feature_flags": {
                "v2_capture": True, "cds_resolver": True, "minute_bars": True,
                "structure": True, "lab_v3_view": True, "macro_advisory": True,
                "interpreter_resolver": True, "screen_adapter": False,
            },
        }),
        encoding="utf-8",
    )
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    row = {
        "run_id": run_id, "pipeline_mode": "MORNING_VALIDATION", "ticker": "AAA",
        "thesis_id": "T", "trade_idea_id": "I", "selected_structure_id": "S",
        "selected_contract_symbol": SYMBOL, "selected_quote_snapshot_id": "Q",
        "governed_direction": "CALL", "thesis_state": "TRADEABLE_NOW",
        "olm_guard_disposition": "ELIGIBLE", "final_action": "BUY_NOW",
        "capital_permission": "CAPITAL_ALLOWED", "contract_bid_size": 10,
        "contract_ask_size": 12, "contract_size_quality": "OBSERVED",
        "morning_contract_symbol": SYMBOL, "morning_quote_dataset_id": "BASE",
        "morning_quote_timestamp_utc": timestamp, "morning_contract_bid": 4.0,
        "morning_contract_ask": 4.4, "morning_contract_mid": 4.2,
        "current_contract_symbol": SYMBOL, "current_quote_dataset_id": "CUR",
        "current_quote_timestamp_utc": timestamp, "current_contract_bid": 4.1,
        "current_contract_ask": 4.5, "current_contract_mid": 4.3,
        "underlying_nbbo_bid": 99.9, "underlying_nbbo_ask": 100.1,
        "underlying_nbbo_mid": 100.0, "underlying_nbbo_bid_size": 500,
        "underlying_nbbo_ask_size": 600, "underlying_nbbo_timestamp_utc": timestamp,
    }
    validation_dir = run_root / "validation"
    validation_dir.mkdir()
    (validation_dir / "AAA.json").write_text(
        json.dumps({
            "validation_event_id": "VALIDATION:AAA",
            "run_id": run_id,
            "ticker": "AAA",
            "thesis_id": "T",
            "direction": "CALL",
            "selected_contract": SYMBOL,
            "evidence_cutoff_utc": timestamp,
            "transition": "THESIS_CONFIRMED",
        }),
        encoding="utf-8",
    )
    result = _publish_msi_handoff(
        run_id=run_id, run_dir=run_root, lab_rows=[row], completed_at_utc=timestamp,
    )
    assert result["production_readiness"]["status"] == "PASS"
