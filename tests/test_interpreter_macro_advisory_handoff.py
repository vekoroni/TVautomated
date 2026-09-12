from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTERPRETER = ROOT / "pipeline_interpreter"
if str(INTERPRETER) not in sys.path:
    sys.path.insert(0, str(INTERPRETER))

from contracts.interpreter_macro_context import (  # noqa: E402
    AUTHORITY_STATEMENT,
    FORBIDDEN_AUTHORITY_KEYS,
    advisory_fields_for_row,
    materialize_interpreter_macro_context,
)
from pipeline_interpreter.macro_context import MacroPacketError, load_macro_packet  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sources(root: Path) -> None:
    enrichment = {
        "as_of_utc": "2026-08-31T07:00:00Z",
        "narrative_overlay": {"overlay_summary": "Rates firm; technology selective."},
        "event_guard_deltas": [{"event_id": "PAYROLLS_GUARD"}],
        "macro_exposure_index": {
            "ABC": [{
                "theme_id": "RATE_THEME",
                "directional_pressure": "SELECTIVE",
                "event_guards": ["PAYROLLS_GUARD"],
                "role": "BENEFICIARY",
                "final_action": "BUY_NOW",
            }],
        },
    }
    core = {
        "as_of_utc": "2026-08-31T07:00:00Z",
        "regime_state": "TRANSITIONAL",
        "liquidity_pulse": "CONTRACTING",
        "size_multiplier": 0.25,
        "sector_rotation": {"sector_bias_map": {"Technology": "FAVOURED"}},
        "extras": {
            "rates": {"t10y": 4.7},
            "volatility": {"regime": "LOW"},
        },
        "macro_quant_packet": {
            "macro_generated_at_utc": "2026-08-31T07:00:00Z",
            "macro_freshness_status": "FRESH",
            "macro_data_quality": "COMPLETE",
            "macro_regime_label": "TRANSITIONAL",
            "macro_active_conflict_flags": [],
        },
    }
    bond = {
        "generated_at": "2026-08-31T07:01:00Z",
        "yield_curve": {"curve_state": "FLAT"},
        "auction": {"calendar_rows": []},
        "composite": {"summary": "Bond context neutral.", "trade_go": False},
    }
    _write_json(root / "macro_intelligence_latest.json", core)
    _write_json(root / "bond_macro_state.json", bond)
    _write_json(root / "avshunter_macro_enrichment_delta.json", enrichment)
    _write_json(root / "avshunter_macro_enrichment_delta808.json", {"legacy": True})
    (root / "auction_calendar.csv").write_text(
        "date,tenor,type,offering_usd_bn\n2026-09-01,10Y,NOTE,42\n",
        encoding="utf-8",
    )


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_all_canonical_sources_are_snapshotted_and_authority_is_removed(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "20260831_070000"
    macro = tmp_path / "macro"
    run.mkdir(parents=True)
    macro.mkdir()
    _sources(macro)

    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-08-31", macro_dir=macro
    )
    packet = result["packet"]
    assert set(packet["source_manifest"]) == {
        "core_macro", "bond_macro", "auction_calendar", "enrichment_delta",
        "us_money_index",
    }
    assert packet["source_manifest"]["us_money_index"]["status"] == "MISSING"
    assert packet["us_money_index"] == {}
    assert all(
        item["status"] == "VALID"
        for name, item in packet["source_manifest"].items()
        if name != "us_money_index"
    )
    assert "avshunter_macro_enrichment_delta808.json" not in json.dumps(packet)
    assert not (set(_keys(packet)) & FORBIDDEN_AUTHORITY_KEYS)
    assert packet["authority_statement"] == AUTHORITY_STATEMENT
    packet_path = Path(result["packet_path"])
    assert hashlib.sha256(packet_path.read_bytes()).hexdigest() == result["reference"]["sha256"]

    fields = advisory_fields_for_row(
        packet, {"ticker": "ABC", "sector": "Technology"},
        packet_sha256=result["reference"]["sha256"],
    )
    assert fields["macro_sector_alignment"] == "FAVOURED"
    assert fields["macro_ticker_alignment"] == "BENEFICIARY"
    assert "RATE_THEME" in fields["macro_active_themes"]
    assert fields["macro_data_role"] == "ADVISORY_ONLY"


def test_updated_macro_changes_the_source_fingerprint(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "20260831_070000"
    macro = tmp_path / "macro"
    run.mkdir(parents=True)
    macro.mkdir()
    _sources(macro)
    first = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-08-31", macro_dir=macro
    )
    core_path = macro / "macro_intelligence_latest.json"
    core = json.loads(core_path.read_text(encoding="utf-8"))
    core["regime_state"] = "RISK_OFF"
    _write_json(core_path, core)
    second = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-08-31", macro_dir=macro
    )
    assert first["reference"]["source_fingerprint"] != second["reference"]["source_fingerprint"]
    assert first["reference"]["packet_id"] != second["reference"]["packet_id"]


def test_production_mode_uses_only_the_run_frozen_macro_snapshot(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "20260831_070000"
    macro = tmp_path / "macro"
    run.mkdir(parents=True)
    macro.mkdir()
    _sources(macro)
    live = json.loads((macro / "macro_intelligence_latest.json").read_text(encoding="utf-8"))
    live["regime_state"] = "LATE_MUTABLE_DROPBOX_VALUE"
    _write_json(macro / "macro_intelligence_latest.json", live)
    frozen = {
        **live,
        "regime_state": "RUN_FROZEN_VALUE",
        "extras": {
            **live.get("extras", {}),
            "bond_macro": {
                "generated_at": "2026-08-31T07:01:00Z",
                "yield_curve": {"curve_state": "FLAT"},
                "auction": {"calendar_rows": []},
                "zn_futures": {}, "credit_stress": {}, "composite": {},
            },
        },
    }
    _write_json(run / "macro_snapshot.json", frozen)
    result = materialize_interpreter_macro_context(
        run_dir=run,
        session_date="2026-08-31",
        macro_dir=macro,
        prefer_run_snapshot=True,
    )
    packet = result["packet"]
    assert packet["regime_state"] == "RUN_FROZEN_VALUE"
    assert "LATE_MUTABLE_DROPBOX_VALUE" not in json.dumps(packet)
    assert packet["source_manifest"]["core_macro"]["status"] == "RUN_SNAPSHOT"
    assert packet["source_manifest"]["bond_macro"]["status"] == "EMBEDDED_RUN_SNAPSHOT"
    assert packet["source_manifest"]["us_money_index"]["status"] == "MISSING_IN_RUN_SNAPSHOT"


def test_current_enrichment_contract_builds_ticker_advisories(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "20260831_070000"
    macro = tmp_path / "macro"
    run.mkdir(parents=True)
    macro.mkdir()
    _sources(macro)
    _write_json(macro / "avshunter_macro_enrichment_delta.json", {
        "as_of_utc": "2026-08-31T07:00:00Z",
        "theme_deltas": [{
            "theme_id": "RATES_PRESSURE",
            "theme_name": "Rates pressure",
            "directional_pressure": "PUT_FAVOURED",
            "beneficiary_universe": ["UUP"],
            "vulnerable_universe": ["IWM"],
            "context_universe": ["SPY"],
            "event_guards": ["RATES_GUARD"],
        }],
        "macro_exposure_index_build": {
            "normalised_catalyst_records": [{
                "ticker": "IWM",
                "event_category": "SMALL_CAP_STRESS",
                "ticker_role": "MANUAL_REVIEW_CANDIDATE",
                "catalyst_direction_bias": "LONG_PUT_WATCH",
                "execution_permission": "NONE_NEWS_TERMINAL_ONLY",
            }],
        },
    })

    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-08-31", macro_dir=macro
    )
    packet = result["packet"]
    assert packet["ticker_advisories"]["IWM"][0]["role"] == "VULNERABLE"
    assert packet["ticker_advisories"]["IWM"][1]["theme_id"] == "SMALL_CAP_STRESS"
    assert "execution_permission" not in set(_keys(packet))
    fields = advisory_fields_for_row(
        packet, {"ticker": "IWM", "sector": "Financials"},
        packet_sha256=result["reference"]["sha256"],
    )
    assert "VULNERABLE" in fields["macro_ticker_alignment"]
    assert "RATES_PRESSURE" in fields["macro_active_themes"]


def test_interpreter_loads_exact_ticker_context_and_rejects_tampering(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "20260831_070000"
    macro = tmp_path / "macro"
    run.mkdir(parents=True)
    macro.mkdir()
    _sources(macro)
    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-08-31", macro_dir=macro
    )
    context = load_macro_packet(result["reference"], run_root=run, ticker="ABC")
    assert context.advisory["ticker_advisory"][0]["theme_id"] == "RATE_THEME"
    assert context.authority_statement == AUTHORITY_STATEMENT

    packet_path = Path(result["packet_path"])
    packet_path.write_text(packet_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(MacroPacketError, match="HASH_MISMATCH"):
        load_macro_packet(result["reference"], run_root=run, ticker="ABC")


def test_missing_optional_sidecars_produces_a_packet_not_trade_authority(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "20260831_070000"
    macro = tmp_path / "macro"
    run.mkdir(parents=True)
    macro.mkdir()
    _write_json(macro / "macro_intelligence_latest.json", {
        "as_of_utc": "2026-08-31T07:00:00Z",
        "macro_quant_packet": {
            "macro_freshness_status": "FRESH", "macro_data_quality": "PARTIAL"
        },
    })
    result = materialize_interpreter_macro_context(
        run_dir=run, session_date="2026-08-31", macro_dir=macro
    )
    packet = result["packet"]
    assert packet["source_manifest"]["bond_macro"]["status"] == "MISSING"
    assert packet["source_manifest"]["auction_calendar"]["status"] == "MISSING"
    assert packet["quality"] == "PARTIAL"
    assert packet["authority_statement"] == AUTHORITY_STATEMENT
