from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.macro_quant_packet import (  # noqa: E402
    build_macro_quant_packet,
    macro_quant_columns_for_row,
    merge_preserving_committed,
    missing_macro_quant_packet,
    packet_from_package,
    required_macro_quant_fields,
    resolve_macro_suffix_columns,
)


def _macro(as_of: str) -> dict:
    return {
        "contract_version": "macro_contract_v1_0",
        "as_of_utc": as_of,
        "normalised_at_utc": as_of,
        "macro_state": {
            "regime_state": "SELECTIVE_RISK_ON",
            "risk_on_off_switch": "RISK_ON",
            "macro_conviction": 0.72,
            "liquidity_pulse": "EXPANDING",
            "vol_mode": "CONTANGO",
            "rates_impulse": "RATES_DOWN",
            "usd_state": "NEUTRAL",
            "credit_state": "STABLE",
        },
        "net_liquidity_score": 0.68,
        "vix_level": 16.2,
        "vix_regime_score": 0.62,
        "vix_contango": 0.11,
        "gex_regime_score": 0.74,
        "sector_rotation": {
            "rotation_signal": "TECH_LED_RISK_ON",
            "strongest_sectors": ["Technology", "Industrials"],
            "weakest_sectors": ["Energy"],
        },
        "horizon_routing": {
            "1_5d": {"bullish_prob_pct": 64.0, "size_multiplier": 1.0},
            "6_10d": {"bullish_prob_pct": 58.0, "size_multiplier": 0.7},
            "11_20d": {"bullish_prob_pct": 51.0, "size_multiplier": 0.0},
        },
    }


def test_macro_quant_packet_creation_has_required_fields() -> None:
    now = datetime(2026, 5, 8, 12, tzinfo=timezone.utc)
    packet = build_macro_quant_packet(
        _macro("2026-05-08T06:00:00Z"),
        "macro_intelligence_latest.json",
        now=now,
    )

    assert packet["macro_regime_label"] == "RISK_ON"
    assert packet["macro_freshness_status"] == "FRESH"
    assert packet["macro_data_quality"] == "CONFIRMED"
    assert packet["vix_contango"] == 0.11
    assert packet["vix_structure_label"] == "CONTANGO"
    assert packet["sector_rotation_state"] == "TECH_LED_RISK_ON"
    assert set(required_macro_quant_fields()).issubset(packet.keys())


def test_bond_macro_sidecar_fields_enter_the_row_baton() -> None:
    macro = _macro("2026-05-08T06:00:00Z")
    macro["extras"] = {
        "bond_macro": {
            "bond_macro_flag": "BOND_MACRO_CAUTION",
            "trade_go": True,
            "bond_macro_score": 58,
            "auction_spread_risk": True,
            "credit_warning": False,
            "breakeven_adjustment_pct": 6.0,
        }
    }
    packet = build_macro_quant_packet(macro)
    row = macro_quant_columns_for_row(packet)

    assert row["bond_macro_flag"] == "BOND_MACRO_CAUTION"
    assert row["bond_trade_go"] is True
    assert row["bond_macro_score"] == 58.0
    assert row["auction_spread_risk"] is True
    assert row["credit_warning"] is False
    assert row["breakeven_adjustment_pct"] == 6.0


def test_missing_macro_json_produces_conservative_defaults() -> None:
    packet = missing_macro_quant_packet("missing.json")

    assert packet["macro_freshness_status"] == "MISSING"
    assert packet["macro_data_quality"] == "MISSING"
    assert packet["macro_regime_label"] == "UNKNOWN"
    assert packet["equity_drawer_active"] is True
    assert "MACRO_MISSING_REVIEW_REQUIRED" in packet["macro_execution_caution"]


def test_stale_and_expired_macro_are_labelled() -> None:
    now = datetime(2026, 5, 8, 12, tzinfo=timezone.utc)
    stale = build_macro_quant_packet(_macro("2026-05-07T00:00:00Z"), now=now)
    expired = build_macro_quant_packet(_macro("2026-05-04T00:00:00Z"), now=now)

    assert stale["macro_freshness_status"] == "STALE"
    assert stale["macro_age_hours"] == 36.0
    assert expired["macro_freshness_status"] == "EXPIRED"


def test_resolved_macro_conflict_flags_do_not_create_partial_quality() -> None:
    now = datetime(2026, 5, 8, 12, tzinfo=timezone.utc)
    macro = _macro("2026-05-08T06:00:00Z")
    macro["extras"] = {
        "conflict_flags": [
            "C1: VIX spot conflict — JSON 17.08 vs CSV 17.19; CSV primary applied (17.19)",
            "C7: T10Y2Y minor rounding 0.48 vs 0.490; immaterial; treated as 0.49",
        ]
    }
    packet = build_macro_quant_packet(macro, now=now)

    assert packet["macro_data_quality"] == "CONFIRMED"
    assert packet["macro_active_conflict_flags"] == []


def test_numbered_resolved_and_clear_flags_are_not_active() -> None:
    macro = _macro("2026-05-08T06:00:00Z")
    macro["extras"] = {"conflict_flags": [
        "CONFLICT_005_CLEAR: VVIX consistent at 90.42",
        "CONFLICT_006_RESOLVED: one-day vintage skew; operative value adopted",
    ]}

    packet = build_macro_quant_packet(macro)

    assert packet["macro_data_quality"] == "CONFIRMED"
    assert packet["macro_active_conflict_flags"] == []
    assert len(packet["macro_resolved_conflict_flags"]) == 2
    assert len(packet["macro_resolved_conflict_flags"]) == 2


def test_active_macro_conflict_flags_create_partial_quality() -> None:
    now = datetime(2026, 5, 8, 12, tzinfo=timezone.utc)
    macro = _macro("2026-05-08T06:00:00Z")
    macro["extras"] = {
        "conflict_flags": [
            "C8: CRITICAL DATA ERROR — USSLIND carries date 2020-02-01; LEI data marked MISSING/UNRELIABLE and excluded from all calculations",
        ]
    }
    packet = build_macro_quant_packet(macro, now=now)

    assert packet["macro_data_quality"] == "PARTIAL"
    assert len(packet["macro_active_conflict_flags"]) == 1


def test_sector_rotation_alignment_per_ticker() -> None:
    packet = build_macro_quant_packet(_macro("2026-05-08T06:00:00Z"))

    aligned = macro_quant_columns_for_row(packet, {"ticker": "MSFT", "sector": "Technology"})
    conflicted = macro_quant_columns_for_row(packet, {"ticker": "XOM", "sector": "Energy"})
    unknown = macro_quant_columns_for_row(packet, {"ticker": "ABC"})

    assert aligned["ticker_sector_alignment"] == "ALIGNED"
    assert aligned["ticker_sector_alignment_score"] == 100.0
    assert conflicted["ticker_sector_alignment"] == "CONFLICTED"
    assert unknown["ticker_sector_alignment"] == "UNKNOWN"


def test_no_silent_overwrite_of_committed_macro_fields() -> None:
    target = {"macro_regime_label": "RISK_ON", "macro_freshness_status": "FRESH"}
    merged = merge_preserving_committed(
        target,
        {"macro_regime_label": "UNKNOWN", "macro_freshness_status": "STALE"},
    )

    assert merged["macro_regime_label"] == "RISK_ON"
    assert merged["macro_freshness_status"] == "FRESH"
    assert merged["macro_conflicted_fields"]["macro_freshness_status"]["new_value"] == "STALE"


def test_csv_serialisation_uses_json_for_lists_and_dicts() -> None:
    packet = build_macro_quant_packet(_macro("2026-05-08T06:00:00Z"))
    cols = macro_quant_columns_for_row(packet, {"sector": "Technology"})

    assert json.loads(cols["preferred_sectors"]) == ["Technology", "Industrials"]
    clarity = json.loads(cols["bucket_clarity_scores"])
    assert set(clarity) == {"equities", "rates_bonds", "usd_fx", "credit", "commodities"}


def test_macro_fields_survive_dataframe_merge_suffix_resolution() -> None:
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "ticker": "MSFT",
                "macro_regime_label_x": "RISK_ON",
                "macro_regime_label_y": "UNKNOWN",
                "macro_freshness_status_x": "FRESH",
                "macro_freshness_status_y": "MISSING",
                "preferred_sectors_x": json.dumps(["Technology"]),
                "preferred_sectors_y": json.dumps([]),
            }
        ]
    )
    out = resolve_macro_suffix_columns(df)

    assert "macro_regime_label_x" not in out.columns
    assert "macro_regime_label_y" not in out.columns
    assert out.loc[0, "macro_regime_label"] == "RISK_ON"
    assert json.loads(out.loc[0, "preferred_sectors"]) == ["Technology"]


def test_equity_drawer_active_adds_downstream_warning() -> None:
    macro = _macro("2026-05-08T06:00:00Z")
    macro["macro_state"]["rates_impulse"] = "RATES_UP"
    macro["macro_state"]["usd_state"] = "USD_UP"
    macro["macro_state"]["credit_state"] = "TIGHTENING"
    macro["macro_state"]["regime_state"] = "RISK_OFF"
    packet = build_macro_quant_packet(macro)

    assert packet["equity_drawer_active"] is True
    assert "EQUITY_DRAWER_ACTIVE_REQUIRES_STRONG_CONFIRMATION" in packet["macro_execution_caution"]


def test_risk_on_macro_alone_does_not_create_execution_permission() -> None:
    now = datetime(2026, 5, 8, 12, tzinfo=timezone.utc)
    packet = build_macro_quant_packet(_macro("2026-05-08T06:00:00Z"), now=now)

    assert "thesis_decision" not in packet
    assert "execution_mode" not in packet
    assert packet["macro_execution_caution"] == "NONE"


def test_package_json_preserves_macro_quant_packet(tmp_path: Path) -> None:
    packet = build_macro_quant_packet(_macro("2026-05-08T06:00:00Z"))
    pkg = {"ticker": "MSFT", "macro_quant_packet": packet}
    out = tmp_path / "MSFT.package.json"
    out.write_text(json.dumps(pkg), encoding="utf-8")

    loaded = json.loads(out.read_text(encoding="utf-8"))
    restored = packet_from_package(loaded)
    assert restored["macro_regime_label"] == "RISK_ON"
    assert restored["sector_rotation_state"] == "TECH_LED_RISK_ON"


if __name__ == "__main__":
    test_macro_quant_packet_creation_has_required_fields()
    test_missing_macro_json_produces_conservative_defaults()
    test_stale_and_expired_macro_are_labelled()
    test_resolved_macro_conflict_flags_do_not_create_partial_quality()
    test_active_macro_conflict_flags_create_partial_quality()
    test_sector_rotation_alignment_per_ticker()
    test_no_silent_overwrite_of_committed_macro_fields()
    test_csv_serialisation_uses_json_for_lists_and_dicts()
    test_macro_fields_survive_dataframe_merge_suffix_resolution()
    test_equity_drawer_active_adds_downstream_warning()
    test_risk_on_macro_alone_does_not_create_execution_permission()
    with tempfile.TemporaryDirectory() as tmp:
        test_package_json_preserves_macro_quant_packet(Path(tmp))
    print("macro_quant_packet tests passed")
