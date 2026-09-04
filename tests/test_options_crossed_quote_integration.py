from __future__ import annotations

from pathlib import Path

import pandas as pd

from canonical_data.marketdata_response import _quote
from contracts.options_liquidity_lifecycle import classify_current_executability
from scripts import avshunter_options_intelligence as oi


def _ctx() -> dict:
    return {
        "ticker": "DRVN",
        "spot": 16.0,
        "entry": 16.0,
        "structural_target": 19.0,
        "stop": 14.5,
        "atr": 0.8,
        "hold_days": 5,
        "direction": "CALL",
        "preferred_strategy": "LONG_CALL",
        "dte_window": (7, 14, 30),
        "dte_config": {"delta_min": 0.20, "delta_max": 0.50, "spread_max": 0.35},
        "phase": "C",
        "win_prob": 62.0,
    }


def _row(**overrides) -> dict:
    row = {
        "underlying": "DRVN",
        "symbol": "DRVN260918C00017500",
        "right": "C",
        "strike": 17.5,
        "expiration_date": "2026-09-18",
        "dte": 19.0,
        "bid": 0.30,
        "ask": 0.0,
        "mark": 0.15,
        "spread_pct": -2.0,
        "quote_quality": "INVALID",
        "quality_flags": ["CROSSED_QUOTE"],
        "quote_fields_complete": False,
        "mark_synthetic": True,
        "open_interest": 0,
        "volume": 0,
        "implied_vol": 0.60,
        "delta": 0.30,
        "gamma": 0.02,
        "theta": -0.02,
        "vega": 0.04,
        "bid_size": 0,
        "ask_size": 0,
        "bid_size_quality": "OBSERVED_ZERO",
        "ask_size_quality": "OBSERVED_ZERO",
        "quote_timestamp_utc": "2026-08-28T19:59:00Z",
        "quote_timestamp_source": "marketdata.app.updated",
        "contract_multiplier": 100,
        "contract_multiplier_source": "marketdata.app",
        "md_quote_source": "marketdata.app_incomplete",
    }
    row.update(overrides)
    return row


def test_canonical_crossed_quote_never_emits_negative_spread() -> None:
    bid, ask, mid, spread, quality, flags = _quote(0.30, 0.0, 0.15)
    assert (bid, ask, mid) == (0.30, 0.0, 0.15)
    assert spread is None
    assert quality == "INVALID"
    assert "CROSSED_QUOTE" in flags


def test_chain_adapter_preserves_invalid_quote_lineage() -> None:
    payload = [{**_row(), "mid": 0.15}]
    frame = oi._chain_v2_to_options_frame(payload)
    record = frame.iloc[0]
    assert record["quote_quality"] == "INVALID"
    assert "CROSSED_QUOTE" in record["quality_flags"]
    assert bool(record["mark_synthetic"]) is True
    assert bool(record["quote_fields_complete"]) is False


def test_primary_selector_excludes_drvn_crossed_quote() -> None:
    assert oi.select_best_contract(pd.DataFrame([_row()]), _ctx()) is None


def test_primary_selector_chooses_valid_alternative_and_carries_lineage() -> None:
    valid = _row(
        symbol="DRVN260918C00016000",
        strike=16.0,
        bid=0.95,
        ask=1.05,
        mark=1.0,
        spread_pct=0.10,
        quote_quality="TWO_SIDED",
        quality_flags=[],
        quote_fields_complete=True,
        mark_synthetic=False,
        open_interest=2,
        volume=0,
        delta=0.45,
    )
    selected = oi.select_best_contract(pd.DataFrame([_row(), valid]), _ctx())
    assert selected is not None
    assert selected["symbol"] == "DRVN260918C00016000"
    assert selected["underlying"] == "DRVN"
    assert selected["quote_quality"] == "TWO_SIDED"
    assert selected["selection_reason"] == "BEST_CURRENT_LONG_OPTION_QUOTE"
    assert selected["oi_used_as_hard_gate"] is False
    assert selected["volume_used_as_hard_gate"] is False


def test_stale_crossed_quote_is_invalid_not_merely_stale() -> None:
    result = classify_current_executability(
        bid=0.30,
        ask=0.0,
        quote_age_seconds=901,
        dte=19,
        minimum_required_dte=10,
        moneyness_treatment="PREFERRED_EXECUTION",
    )
    assert result["liquidity_state"] == "INVALID_QUOTE"
    assert "MALFORMED_ONE_SIDED_QUOTE" in result["liquidity_reasons"]


def test_research_contract_blocks_crossed_quote_without_liquidity_bonus() -> None:
    result = oi.build_options_research_contract(
        ctx=_ctx(),
        signal_row=pd.Series({"trigger_quality": "STRONG"}),
        contract={**_row(), "expiry": "2026-09-18", "oi": 0},
        iv_ctx={"atm_iv": 0.60, "iv_percentile": 0.30},
        econ={"breakeven_price": 17.65, "rr_options": 3.0, "theta_drag_pct": 15.0},
        ois_score=80.0,
        verdict="EXECUTE",
        stand_down_reason="",
        walls={"call_wall": 20.0, "put_wall": 12.0},
    )
    assert "INVALID_CROSSED_QUOTE" in result["hard_vetoes"]
    assert result["liquidity_score"] == 0.0
    assert result["final_route"] == oi.OPTIONS_BLOCKED_ROUTE


class _Response:
    status_code = 200
    ok = True

    @staticmethod
    def json() -> dict:
        return {
            "s": "ok",
            "bid": [0.30],
            "ask": [0.0],
            "mid": [0.15],
            "iv": [0.60],
            "delta": [0.30],
        }


class _Session:
    @staticmethod
    def get(*args, **kwargs):
        return _Response()


def test_invalid_exact_quote_refresh_does_not_overwrite_contract(monkeypatch) -> None:
    monkeypatch.setattr(oi, "_MD_AVAILABLE", True)
    monkeypatch.setattr(oi, "_canonical_offline_replay_enabled", lambda: False)
    monkeypatch.setattr(oi, "MD_SESSION", _Session())
    original = {
        "underlying": "DRVN",
        "symbol": "DRVN260918C00016000",
        "expiration_date": "2026-09-18",
        "right": "C",
        "strike": 16.0,
        "bid": 0.95,
        "ask": 1.05,
        "mark": 1.0,
        "mark_synthetic": True,
    }
    enriched = oi.enrich_contract_with_real_quotes(original)
    assert enriched["bid"] == 0.95
    assert enriched["ask"] == 1.05
    assert enriched["mark"] == 1.0
    assert enriched["quote_refresh_status"] == "REJECTED_INVALID_QUOTE"
    assert "CROSSED_QUOTE" in enriched["quote_refresh_flags"]


class _RegistryMustNotWrite:
    def register_dataset(self, *args, **kwargs):
        raise AssertionError("invalid selected quote reached canonical registry")


class _LifecycleStore:
    def __init__(self) -> None:
        self.registry = _RegistryMustNotWrite()
        self.events: list[dict] = []

    @staticmethod
    def latest_thesis(thesis_id):
        return None

    def record_thesis_event(self, **kwargs):
        self.events.append(kwargs)
        return None

    def record_contract_observation(self, **kwargs):
        raise AssertionError("invalid selected quote reached contract observations")


def test_persistence_degrades_invalid_selected_quote_to_thesis_only(monkeypatch, tmp_path: Path) -> None:
    store = _LifecycleStore()
    monkeypatch.setattr(oi, "_CDS_LIQUIDITY_STORE", store)
    monkeypatch.setattr(oi, "_REPO_ROOT", tmp_path)
    result = {
        "thesis_id": "DRVN:CALL:2026-08-28",
        "ticker": "DRVN",
        "options_direction": "CALL",
        "thesis_state": "ACTIVE",
        "liquidity_state": "INVALID_QUOTE",
        "recommended_contract": "DRVN260918C00017500",
        "option_chain_dataset_id": "CHAIN-DRVN",
        "quote_as_of": "2026-08-28T19:59:00Z",
        "contract_expiry": "2026-09-18",
        "contract_strike": 17.5,
        "contract_dte": 19,
        "underlying_price": 16.0,
        "contract_bid": 0.30,
        "contract_ask": 0.0,
        "contract_mid": 0.15,
        "contract_spread_pct": -2.0,
        "contract_quote_quality": "INVALID",
        "contract_quality_flags": '["CROSSED_QUOTE"]',
        "structural_target": 19.0,
        "invalidation_spot": 14.5,
    }
    oi._persist_options_lifecycle_result(result, "RUN-DRVN")
    assert result["liquidity_persistence_status"] == "THESIS_ONLY_INVALID_SELECTED_QUOTE"
    assert result["executable_now"] is False
    assert len(store.events) == 1

