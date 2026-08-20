from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.macro_enrichment_delta import (  # noqa: E402
    PROTECTED_MACRO_FIELDS,
    candidate_macro_enrichment_audit,
    interpret_macro_decision_context,
    load_macro_enrichment_delta,
    lookup_macro_exposure,
    merge_macro_enrichment_delta,
    validate_macro_enrichment_delta,
)
from scripts.build_packages_from_discovery import (  # noqa: E402
    dedupe_discovery_rows_by_ticker,
    get_ticker,
    read_discovery_csv,
)


FIXTURE = ROOT / "tests" / "fixtures" / "macro_enrichment_delta_sample.json"


def _base_macro() -> dict:
    return {
        "contract_version": "macro_contract_v1_0",
        "regime_state": "TRANSITIONAL",
        "dir_bias": "NEUTRAL",
        "trend_energy": "LOW",
        "usd_state": "WEAKENING",
        "rates_impulse": "RESTRICTIVE_HOLD",
        "liquidity_pulse": "STABLE",
        "regime_drift_status": "TRANSITIONAL_NEUTRAL",
        "macro_conviction": 0.52,
        "vol_mode": "SHALLOW_CONTANGO",
        "risk_on_off_switch": "SELECTIVE_RISK_ON_REDUCED_SIZE",
        "sector_tilt": "XLK_LEAD_LONG_XLI_LONG_XLY_LONG_XLE_AVOID_XLV_AVOID",
        "net_liquidity_score": 0.5,
        "vix_regime_score": 0.8075,
        "gex_regime_score": 0.5,
        "macro_momentum_score": 0.52,
        "regime_label": "TRANSITIONAL",
        "regime_probability": 0.7,
        "vix_spot": 17.39,
        "macro_filter": "NO_GO",
        "sector_lead": ["XLK", "XLI", "XLY"],
        "sector_avoid": ["XLE", "XLV", "XLU"],
        "size_multiplier": 0.5,
        "trigger_required": True,
        "horizon_routing": {
            "1_5d": {"action": "REDUCED_SIZE_LONG_LEADERSHIP_ONLY", "size_multiplier": 0.5},
            "6_10d": {"action": "REDUCED_SIZE_LONG_LEADERSHIP_ONLY", "size_multiplier": 0.45},
            "11_20d": {"action": "HOLD_REDUCE_AWAIT_REGIME_CLARITY", "size_multiplier": 0.4},
        },
        "sector_rotation": {
            "strongest_sectors": ["Information Technology", "Industrials"],
            "weakest_sectors": ["Energy", "Health Care", "Utilities"],
            "sector_bias_map": {
                "Information Technology": "TAILWIND",
                "Energy": "TAILWIND",
                "Financials": "HEADWIND",
                "Utilities": "HEADWIND",
                "Health Care": "HEADWIND",
            },
        },
        "put_gate": {"current_permission": "RESTRICTED"},
        "macro_quant_packet": {
            "macro_freshness_status": "STALE",
            "macro_data_quality": "PARTIAL",
        },
        "extras": {"conflict_flags": ["BASE_FLAG"]},
    }


def _delta() -> dict:
    return load_macro_enrichment_delta(FIXTURE)


def _protected_snapshot(macro: dict) -> dict:
    return {key: copy.deepcopy(macro.get(key)) for key in PROTECTED_MACRO_FIELDS if key in macro}


def test_macro_enrichment_additive_merge_preserves_base_fields() -> None:
    base = _base_macro()
    before = _protected_snapshot(base)

    merged = merge_macro_enrichment_delta(base, _delta())

    assert _protected_snapshot(merged) == before
    assert merged["extras"]["macro_enrichment_delta"]["batch_id"] == "2026-05-09-AM-NEWS"
    assert "macro_exposure_index" in merged["extras"]


def test_macro_enrichment_does_not_override_no_go_gate() -> None:
    base = _base_macro()
    base["macro_filter"] = "NO_GO"

    merged = merge_macro_enrichment_delta(base, _delta())

    assert merged["macro_filter"] == "NO_GO"


def test_macro_enrichment_does_not_change_size_or_trigger() -> None:
    base = _base_macro()
    before = {
        "size_multiplier": copy.deepcopy(base["size_multiplier"]),
        "trigger_required": copy.deepcopy(base["trigger_required"]),
        "horizon_routing": copy.deepcopy(base["horizon_routing"]),
        "put_gate": copy.deepcopy(base["put_gate"]),
    }

    merged = merge_macro_enrichment_delta(base, _delta())

    assert merged["size_multiplier"] == before["size_multiplier"]
    assert merged["trigger_required"] == before["trigger_required"]
    assert merged["horizon_routing"] == before["horizon_routing"]
    assert merged["put_gate"] == before["put_gate"]


def test_plain_ticker_csv_still_ingests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tickers.csv"
        path.write_text("ticker\nINTC\nAMAT\nNVDA\n", encoding="utf-8")

        rows = read_discovery_csv(path)

    assert [get_ticker(row) for row in rows] == ["INTC", "AMAT", "NVDA"]
    assert set(rows[0].keys()) == {"ticker"}


def test_plain_ticker_can_match_macro_exposure_index() -> None:
    merged = merge_macro_enrichment_delta(_base_macro(), _delta())

    exposures = lookup_macro_exposure(merged, "INTC")

    assert exposures
    assert exposures[0]["theme_id"] == "AI_CAPEX_SEMICONDUCTOR_MOMENTUM"
    assert exposures[0]["role"] == "BENEFICIARY"


def test_context_and_hint_tickers_match_macro_exposure_index() -> None:
    delta = _delta()
    delta["theme_deltas"][0]["context_universe"] = ["SPY"]
    delta["macro_exposure_index_build"] = {
        "ticker_role_map_hint": {
            "CONTEXT_ONLY": ["QQQ"],
            "VULNERABLE": ["DAL"],
        }
    }
    merged = merge_macro_enrichment_delta(_base_macro(), delta)

    assert lookup_macro_exposure(merged, "SPY")[0]["role"] == "CONTEXT_ONLY"
    assert lookup_macro_exposure(merged, "QQQ")[0]["role"] == "CONTEXT_ONLY"
    assert lookup_macro_exposure(merged, "DAL")[0]["role"] == "VULNERABLE"


def test_plain_ticker_gets_vanguard_safe_enrichment_audit() -> None:
    merged = merge_macro_enrichment_delta(_base_macro(), _delta())

    audit = candidate_macro_enrichment_audit(merged, "INTC")

    assert audit["macro_enrichment_theme_count"] >= 1
    assert "AI_CAPEX_SEMICONDUCTOR_MOMENTUM" in audit["macro_enrichment_theme_ids"]
    assert audit["macro_enrichment_gate_preserved"] is True
    assert audit["macro_enrichment_pressure_label"] in {
        "BENEFICIARY_CONTEXT",
        "REQUIRES_CONFIRMATION",
    }
    assert "plain-ingested" in audit["macro_enrichment_audit_note"]


def test_energy_enrichment_conflict_with_base_sector_avoid() -> None:
    base = _base_macro()
    before_avoid = copy.deepcopy(base["sector_avoid"])

    merged = merge_macro_enrichment_delta(base, _delta())

    assert merged["sector_avoid"] == before_avoid
    assert "ENERGY_THEME_VS_BASE_XLE_AVOID" in merged["extras"]["macro_enrichment_conflict_flags"]
    assert "BASE_FLAG" in merged["extras"]["conflict_flags"]


def test_ai_enrichment_strengthens_existing_tech_leadership() -> None:
    merged = merge_macro_enrichment_delta(_base_macro(), _delta())

    relationships = merged["extras"]["macro_enrichment_theme_relationships"]

    assert relationships["AI_CAPEX_SEMICONDUCTOR_MOMENTUM"] == "STRENGTHENS_EXISTING_TECH_LEADERSHIP"
    assert merged["macro_filter"] == "NO_GO"
    assert merged["size_multiplier"] == 0.5


def test_event_guards_are_available_without_overriding_macro() -> None:
    base = _base_macro()
    before_horizon = copy.deepcopy(base["horizon_routing"])

    merged = merge_macro_enrichment_delta(base, _delta())
    guard_ids = {
        guard["event_id"]
        for guard in merged["extras"]["macro_enrichment_event_guards"]
    }

    assert {
        "US_CPI_2026_05_12",
        "IRAN_HORMUZ_FLOW_RISK",
        "US_RETAIL_SALES_CONFIRMATION",
        "US_CHINA_MEETING_OUTCOME",
    }.issubset(guard_ids)
    assert merged["horizon_routing"] == before_horizon


def test_invalid_enrichment_attempting_protected_override_is_rejected() -> None:
    invalid = _delta()
    invalid["macro_filter"] = "GO"

    result = validate_macro_enrichment_delta(invalid, _base_macro())

    assert result.valid is False
    assert "macro_filter" in result.protected_fields_attempted
    try:
        merge_macro_enrichment_delta(_base_macro(), invalid)
    except ValueError as exc:
        assert "macro_filter" in str(exc)
    else:
        raise AssertionError("protected override was not rejected")


def test_existing_pipeline_dedup_still_works() -> None:
    rows = [
        {"ticker": "INTC"},
        {"ticker": "INTC"},
        {"ticker": "CVX"},
    ]

    deduped, skipped = dedupe_discovery_rows_by_ticker(rows)
    merged = merge_macro_enrichment_delta(_base_macro(), _delta())

    assert skipped == 1
    assert [get_ticker(row) for row in deduped] == ["INTC", "CVX"]
    assert lookup_macro_exposure(merged, "INTC")[0]["theme_id"] == "AI_CAPEX_SEMICONDUCTOR_MOMENTUM"


def test_macro_decision_context_disables_direction_when_fung_hsieh_sub_coin_flip() -> None:
    base = _base_macro()
    base["macro_conviction"] = 0.43
    base["macro_filter"] = "NO_GO"
    base["extras"]["conflict_flags"].append("WARNING: Fung-Hsieh accuracy 0.389 (sub-0.50) - model in NO-GO state.")
    merged = merge_macro_enrichment_delta(base, _delta())

    ctx = interpret_macro_decision_context(
        merged,
        ticker="INTC",
        direction="CALL",
        gics_sector="Information Technology",
    )

    assert ctx["macro_direction_authority"] == "DISABLED"
    assert ctx["macro_direction_vote"] == "ABSTAIN"
    assert ctx["macro_raw_direction_hint"] == "CALL"
    assert ctx["structure_first_required"] is True
    assert ctx["macro_can_invert_direction"] is False
    assert ctx["trade_type_classification"] == "STRUCTURAL_SINGLE_STOCK"


def test_macro_absent_unknown_sector_abstains_without_put_vote() -> None:
    base = _base_macro()
    base["macro_conviction"] = 0.43
    base["macro_filter"] = "NO_GO"
    merged = merge_macro_enrichment_delta(base, _delta())

    ctx = interpret_macro_decision_context(
        merged,
        ticker="NOEXPOSURE",
        direction="CALL",
        gics_sector="",
    )

    assert ctx["macro_alignment_state"] == "MACRO_NOT_APPLICABLE"
    assert ctx["macro_applicability"] == "NOT_APPLICABLE"
    assert ctx["macro_direction_vote"] == "ABSTAIN"
    assert ctx["macro_raw_direction_hint"] == "ABSTAIN"


def test_tailwind_sector_put_requires_elevated_confirmation_not_auto_block() -> None:
    base = _base_macro()
    base["macro_filter"] = "GO"
    base["macro_conviction"] = 0.82
    merged = merge_macro_enrichment_delta(base, _delta())

    ctx = interpret_macro_decision_context(
        merged,
        ticker="CVX",
        direction="PUT",
        gics_sector="Energy",
    )

    assert ctx["macro_alignment_state"] == "PUT_ELEVATED_CONFIRMATION"
    assert ctx["macro_sector_bias"] == "TAILWIND"
    assert "RELATIVE_SECTOR_UNDERPERFORMANCE_REQUIRED" in ctx["macro_confirmation_required"]
    assert ctx["macro_can_invert_direction"] is False


if __name__ == "__main__":
    test_macro_enrichment_additive_merge_preserves_base_fields()
    test_macro_enrichment_does_not_override_no_go_gate()
    test_macro_enrichment_does_not_change_size_or_trigger()
    test_plain_ticker_csv_still_ingests()
    test_plain_ticker_can_match_macro_exposure_index()
    test_context_and_hint_tickers_match_macro_exposure_index()
    test_plain_ticker_gets_vanguard_safe_enrichment_audit()
    test_energy_enrichment_conflict_with_base_sector_avoid()
    test_ai_enrichment_strengthens_existing_tech_leadership()
    test_event_guards_are_available_without_overriding_macro()
    test_invalid_enrichment_attempting_protected_override_is_rejected()
    test_existing_pipeline_dedup_still_works()
    test_macro_decision_context_disables_direction_when_fung_hsieh_sub_coin_flip()
    test_macro_absent_unknown_sector_abstains_without_put_vote()
    test_tailwind_sector_put_requires_elevated_confirmation_not_auto_block()
    print("macro_enrichment_delta tests passed")
