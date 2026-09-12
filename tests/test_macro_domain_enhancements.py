from __future__ import annotations

from copy import deepcopy
from datetime import date
import importlib
import json
import os
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from contracts.interpreter_macro_context import advisory_fields_for_row
from contracts.macro_file_contract import (
    GEX_BY_STRIKE_FILENAME,
    GEX_MANIFEST_FILENAME,
    GEX_PROXY_FILENAME,
    market_data_directory,
)
from contracts.us_money_index_contract import (
    USMoneyIndexValidationError,
    attach_us_money_index,
    normalise_us_money_index_sidecar,
)
from macro_domain.gamma_exposure import GammaExposureConfig, calculate_gamma_exposure
from macro_domain.us_money_index import evaluate_scenarios
from scripts.build_local_gex import build_local_gex
from scripts.macro_quant_packet import build_macro_quant_packet


def _usmi() -> dict:
    return {
        "contract_version": "avshunter_us_money_index_v1_0",
        "packet_type": "US_MONEY_INDEX_STATE",
        "generated_at_local": "2026-09-06T20:04:00+01:00",
        "market_data_as_of": "2026-09-04T16:00:00-04:00",
        "market_status": "US_CASH_AND_OPTIONS_MARKETS_CLOSED",
        "final_pipeline_state": {
            "US_MONEY_INDEX_STATE": "SELECTIVE_US_CAPITAL_CONCENTRATION",
            "GAMMA_POSITION": "AT_FLIP_BOUNDARY",
        },
        "core_market_snapshot": {
            "sp500_pct": -0.38,
            "sp500_breadth": {"advancers": 177, "decliners": 322},
            "vix": {"spot": 14.53},
        },
        "rates_and_fed": {"treasury_2y_pct": 4.37, "treasury_10y_pct": 4.78},
        "gamma_gex": {"spx_close": 7718.6, "zero_gamma": 7721.0},
        "sector_routing": {
            "CALL": {"SEMICONDUCTORS": {"alignment": "ALIGNED", "priority": 1}},
            "PUT": {"SOFTWARE": {"alignment": "ALIGNED", "priority": 1}},
        },
        "tier_logic": {"tier1_score": {"weights": {"capital_alignment": 0.2}}},
        "execution_permission": "NONE_INTELLIGENCE_ONLY",
    }


def _usmi_v2() -> dict:
    return {
        "contract_version": "avshunter_us_money_index_v2_0",
        "packet_type": "US_MONEY_INDEX_CONSOLIDATED",
        "merge_mode": "AUGMENT_ONLY_DO_NOT_REPLACE",
        "analysis_window": {
            "start": "2026-09-07",
            "end": "2026-09-09",
            "as_of_utc": "2026-09-09T06:27:00Z",
            "as_of_local": "2026-09-09T07:27:00+01:00",
            "market_context": "PRE_US_CASH_SESSION",
        },
        "noise_filter": {},
        "current_state": {
            "US_MONEY_INDEX_STATE": "US_CAPITAL_CONCENTRATION_UNDER_OIL_STRESS",
            "state_confidence": 0.82,
            "regime_change_since_monday": False,
            "monetisation_change_since_monday": True,
            "risk_off_transition": False,
            "risk_off_transmission_score": 56,
        },
        "timeline_since_monday": [{"date": "2026-09-09", "state": "SELECTIVE"}],
        "cross_asset": {
            "equities": {
                "last_us_cash_session": {"sp500_pct": -0.58},
                "current_global_session": {"sp500_futures_pct": 0.1},
            },
            "rates": {"us_2y_pct": 4.39, "us_10y_pct": 4.8},
            "usd_fx": {"usd_jpy": 153.32},
            "liquidity": {"tga_usd_bn": 967.935},
            "oil_inflation": {"brent_usd": 99.02, "wti_usd": 93.95},
            "credit": {"hy_oas_pct": 2.68},
            "volatility": {"vix_spot": 15.72},
        },
        "leadership": {},
        "options_monetisation": {
            "long_call_priority": ["AI_HARDWARE", "ENERGY"],
            "long_put_priority": ["WEAK_SOFTWARE", "AIRLINES"],
        },
        "forward_triggers": {},
        "data_quality": {
            "overall": "GOOD_WITH_KNOWN_LAGS",
            "fresh": ["Oil"],
            "lagged": ["Credit OAS"],
            "unconfirmed": ["Dealer gamma/GEX sign"],
        },
        "geopolitical_escalation": {},
        "hormuz_flow": {},
        "risk_off_confirmation_matrix": {},
        "china_inflation_transmission": {},
        "risk_off_transmission_score": {
            "current_score": 56,
            "components": {
                "confirmed": {"status": "CONFIRMED", "weight": 56, "score": 55},
                "unconfirmed": {"status": "NOT_CONFIRMED", "weight": 44, "score": 0},
            },
        },
        "execution_permission": "NONE_INTELLIGENCE_ONLY",
    }


def _chain(ticker: str = "SPY", session: str = "2026-09-04") -> pd.DataFrame:
    rows = []
    spot = 100.0
    for index, strike in enumerate(range(80, 121, 2)):
        for side in ("call", "put"):
            rows.append({
                "ticker": ticker,
                "quote_date": session,
                "option_symbol": f"{ticker}{index:03d}{side[0]}",
                "side": side,
                "strike": float(strike),
                "dte": 21.0,
                "open_interest": 100 + index,
                "underlying_price": spot,
                "gamma": 0.02 if side == "call" else 0.015,
                "iv": 0.25,
            })
    return pd.DataFrame(rows)


def test_usmi_normalises_as_advisory_and_disables_embedded_policy() -> None:
    packet = normalise_us_money_index_sidecar(_usmi())
    assert packet["authority"] == "ADVISORY_ONLY"
    assert packet["execution_permission"] == "NONE_INTELLIGENCE_ONLY"
    assert packet["quality_status"] == "PARTIAL_UNVERIFIED"
    assert packet["policy_activation"] == "DISABLED_UNTIL_SEPARATELY_TESTED"
    assert packet["proposed_policy"]


def test_usmi_rejects_authority_injection() -> None:
    source = _usmi()
    source["final_action"] = "BUY_NOW"
    with pytest.raises(USMoneyIndexValidationError, match="authority fields"):
        normalise_us_money_index_sidecar(source)


def test_usmi_v2_validates_and_adapts_every_domain_block() -> None:
    packet = normalise_us_money_index_sidecar(_usmi_v2())
    assert packet["contract_version"] == "us_money_index_v1_0"
    assert packet["source_contract_version"] == "avshunter_us_money_index_v2_0"
    assert packet["market_as_of_session"] == "2026-09-09"
    assert packet["state"]["US_MONEY_INDEX_STATE"] == "US_CAPITAL_CONCENTRATION_UNDER_OIL_STRESS"
    assert packet["sector_routing"]["CALL"]["SEMICONDUCTORS"]["priority"] == 1
    assert packet["sector_routing"]["PUT"]["SOFTWARE"]["priority"] == 1
    assert packet["metrics"]["vix_spot"]["usable_for_calculation"] is False
    assert packet["quality_status"] == "PARTIAL_UNVERIFIED"
    assert packet["quality_issues"] == ["RISK_SCORE_ROUNDING_COMPONENTS_55_HEADLINE_56"]
    assert set(packet["advisory_context"]) == {
        "noise_filter", "timeline_since_monday", "cross_asset", "leadership",
        "options_monetisation", "forward_triggers", "data_quality",
        "geopolitical_escalation", "hormuz_flow", "risk_off_confirmation_matrix",
        "china_inflation_transmission", "risk_off_transmission_score",
    }


def test_usmi_v2_rejects_timestamp_or_merge_contract_drift() -> None:
    wrong_time = _usmi_v2()
    wrong_time["analysis_window"]["as_of_local"] = "2026-09-09T08:27:00+01:00"
    with pytest.raises(USMoneyIndexValidationError, match="same instant"):
        normalise_us_money_index_sidecar(wrong_time)

    wrong_merge = _usmi_v2()
    wrong_merge["merge_mode"] = "REPLACE"
    with pytest.raises(USMoneyIndexValidationError, match="merge_mode"):
        normalise_us_money_index_sidecar(wrong_merge)


def test_macro_builder_prompt_consumes_v2_as_bounded_advisory() -> None:
    macro_builder = importlib.import_module("build_macro_json")
    packet = normalise_us_money_index_sidecar(_usmi_v2())
    prompt = macro_builder.format_data_for_prompt({
        "data": {"us_money_index_advisory": packet},
    })
    assert "US MONEY INDEX CONSOLIDATED ADVISORY" in prompt
    assert "US_CAPITAL_CONCENTRATION_UNDER_OIL_STRESS" in prompt
    assert "AUTHORITY: ADVISORY_ONLY" in prompt
    assert "must not replace canonical market-data values" in prompt
    assert '"source_payload"' not in prompt


def test_newer_valid_usmi_forces_macro_refresh(tmp_path: Path) -> None:
    macro_builder = importlib.import_module("build_macro_json")
    output = tmp_path / "macro_intelligence_latest.json"
    sidecar = tmp_path / "avshunter_us_money_index.json"
    output.write_text("{}", encoding="utf-8")
    sidecar.write_text(json.dumps(_usmi_v2()), encoding="utf-8")
    os.utime(output, (1000, 1000))
    os.utime(sidecar, (2000, 2000))
    assert macro_builder.optional_input_newer_than_output(sidecar, output) is True
    os.utime(sidecar, (500, 500))
    assert macro_builder.optional_input_newer_than_output(sidecar, output) is False


def test_usmi_attachment_does_not_change_core_authority_fields() -> None:
    macro = {
        "contract_version": "macro_contract_v1_0",
        "final_action": "WATCH",
        "capital_permission": False,
        "direction": "PUT",
        "extras": {},
    }
    packet = normalise_us_money_index_sidecar(_usmi())
    attached = attach_us_money_index(macro, packet)
    for key in ("final_action", "capital_permission", "direction"):
        assert attached[key] == macro[key]


def test_quant_packet_carries_usmi_without_changing_macro_authority() -> None:
    sidecar = normalise_us_money_index_sidecar(_usmi())
    macro = attach_us_money_index({
        "contract_version": "macro_contract_v1_0",
        "as_of_utc": "2026-09-04T20:00:00Z",
        "report_date": "2026-09-04",
        "regime_state": "TRANSITIONAL",
        "macro_conviction": 0.5,
        "extras": {},
    }, sidecar)
    packet = build_macro_quant_packet(macro)
    assert packet["usmi_packet_id"] == sidecar["packet_id"]
    assert packet["usmi_state"] == "SELECTIVE_US_CAPITAL_CONCENTRATION"
    assert packet["macro_authority"] == "ADVISORY_ONLY"


def test_interpreter_row_exposes_lineaged_advisory_only_fields() -> None:
    sidecar = normalise_us_money_index_sidecar(_usmi())
    packet = {
        "packet_id": "MACRO:1",
        "source_fingerprint": "abc",
        "us_money_index": sidecar,
        "sector_rotation": {},
        "macro_quant_packet": {},
        "bond": {},
        "auction_calendar": {},
    }
    fields = advisory_fields_for_row(
        packet,
        {"ticker": "NVDA", "sector": "SEMICONDUCTORS", "direction": "CALL"},
        packet_sha256="macrohash",
    )
    assert fields["usmi_sector_alignment"] == "ALIGNED"
    assert fields["usmi_alignment_priority"] == 1
    assert fields["usmi_authority"] == "ADVISORY_ONLY"


def test_scenario_evaluation_is_three_valued_and_advisory() -> None:
    result = evaluate_scenarios(
        {
            "A": {"all": [{"spx_gt": 100}, {"vix_lt": 18}]},
            "B": {"all": [{"spx_lt": 90}, {"breadth_gt": 1}]},
            "default": "UNRESOLVED",
        },
        {"spx": 105, "vix": 15},
    )
    assert result["scenario"] == "A"
    assert result["results"]["B"]["status"] == "UNAVAILABLE"
    assert result["authority"] == "ADVISORY_ONLY"


def test_gamma_calculation_uses_oi_as_evidence_not_a_gate() -> None:
    chain = _chain()
    chain.loc[0, "open_interest"] = 1
    result = calculate_gamma_exposure(
        chain,
        ticker="SPY",
        session_date="2026-09-04",
        config=GammaExposureConfig(minimum_contracts=10),
    )
    assert result.summary["Data_Status"] == "OK"
    assert result.summary["Contracts_Used"] == len(chain)
    assert result.summary["Call_GEX_Bn"] > 0
    assert result.summary["Put_GEX_Bn"] < 0


def test_gamma_rejects_mixed_sessions() -> None:
    chain = _chain()
    chain.loc[0, "quote_date"] = "2026-09-03"
    with pytest.raises(ValueError, match="mixed or incorrect"):
        calculate_gamma_exposure(chain, ticker="SPY", session_date="2026-09-04")


def test_local_gex_build_registers_canonical_and_projects_compatibility(tmp_path: Path) -> None:
    database = tmp_path / "phantom.db"
    with sqlite3.connect(database) as connection:
        _chain().to_sql("chain_snapshots", connection, index=False)
        _chain("QQQ").to_sql("chain_snapshots", connection, index=False, if_exists="append")
    output = tmp_path / "market_data"
    manifest = build_local_gex(
        database_path=database,
        registry_path=tmp_path / "control.sqlite",
        canonical_root=tmp_path / "canonical_gex",
        output_dir=output,
        session=date(2026, 9, 4),
        config=GammaExposureConfig(minimum_contracts=10),
    )
    assert manifest["provider_requests"] == 0
    assert manifest["status"] == "COMPLETE"
    assert len(manifest["dataset_ids"]) == 2
    assert (output / GEX_PROXY_FILENAME).is_file()
    assert (output / GEX_BY_STRIKE_FILENAME).is_file()
    assert (output / GEX_MANIFEST_FILENAME).is_file()
    with sqlite3.connect(tmp_path / "control.sqlite") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM dataset_registry WHERE dataset_type='GAMMA_EXPOSURE'"
        ).fetchone()[0] == 2


def test_local_gex_projection_is_discovered_by_macro_builder(tmp_path: Path) -> None:
    database = tmp_path / "phantom.db"
    with sqlite3.connect(database) as connection:
        _chain().to_sql("chain_snapshots", connection, index=False)
        _chain("QQQ").to_sql("chain_snapshots", connection, index=False, if_exists="append")

    output = market_data_directory(tmp_path)
    build_local_gex(
        database_path=database,
        registry_path=tmp_path / "control.sqlite",
        canonical_root=tmp_path / "canonical_gex",
        output_dir=output,
        session=date(2026, 9, 4),
        config=GammaExposureConfig(minimum_contracts=10),
    )

    macro_builder = importlib.import_module("build_macro_json")
    payload = macro_builder.load_data_payload(
        output,
        update_keys=["gex_proxy_csv"],
        prior_macro={"contract_version": "macro_contract_v1_0"},
    )
    assert Path(payload["files_found_by_key"]["gex_proxy_csv"]) == output / GEX_PROXY_FILENAME
    overrides = macro_builder.extract_market_data_overrides(payload)
    assert overrides["gex_data_status"] == "OK"
    assert overrides["gex_data_mode"] == "HISTORICAL"
    assert overrides["gex_run_id"].startswith("LOCAL_GEX_")
    assert overrides["gex_net_bn"] is not None
