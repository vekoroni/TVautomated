from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_macro_json import apply_market_data_overrides, extract_market_data_overrides  # noqa: E402
from scripts.macro_quant_packet import build_macro_quant_packet  # noqa: E402


def _payload() -> dict:
    return {
        "data": {
            "report_json": {
                "vix_term_structure": {"vix_spot": 17.08, "vix9d": None, "vix3m": None},
                "yield_curve": {"slope": 0.48},
            },
            "vix_engine_csv": (
                "Date,VIX,VIX3M,VIX9D,VVIX,VVIX_Stress,VIX_Data_Quality,SPY_IV,IV_Data_Quality,Level,Momentum,Structure,Fear_Phase,Volatility_Edge\n"
                "2026-05-11,18.04,18.04,16.85,137.18,ELEVATED,PROXY,395.98,CONFIRMED,NORMAL,STABLE,FLAT,TRANSITION,NEUTRAL\n"
            ),
            "macro_master_csv": (
                "Date,DGS10,DGS2,Spread_2Y10Y,HY_OAS,IG_BBB_OAS,SOFR,M2_YOY,USSLIND_Status,USSLIND_Quarantined,Regime_FRED,XLC_30d\n"
                "2026-05-11,4.410,3.920,0.490,2.79,0.99,3.600,4.6,\"NORMAL (z=0.00, latest=1.72)\",False,NEUTRAL,2.75\n"
            ),
            "gex_proxy_csv": (
                "Date,Ticker,Net_GEX_Bn,Call_GEX_Bn,Put_GEX_Bn,Regime,Gamma_Flip,GEX_Stress,Spot,Contracts_Used,Top_Key_Levels\n"
                "2026-05-11,SPY,307.3775,1264.8218,-957.4443,POSITIVE,245.0,MEDIUM,737.62,4321,\"[710,735]\"\n"
            ),
            "sectors_csv": (
                "ticker,name,current_price,daily_pct,weekly_pct,monthly_pct,ytd_pct,volume,high_52w,low_52w,pct_from_52w_high\n"
                "XLC,Communication Services (XLC),100,0.1,1.0,2.75,5.0,123,101,90,-1\n"
            ),
        }
    }


def _macro() -> dict:
    return {
        "contract_version": "macro_contract_v1_0",
        "as_of_utc": "2026-05-11T09:15:00+00:00",
        "regime_state": "TRANSITIONAL",
        "risk_on_off_switch": "SELECTIVE_RISK_ON",
        "macro_conviction": 0.55,
        "liquidity_pulse": "STABLE",
        "vol_mode": "SHALLOW_CONTANGO",
        "net_liquidity_score": 0.5,
        "extras": {
            "conflict_flags": [
                "VIX9D missing so term structure inferred",
                "VVIX missing",
                "HY/IG credit spreads missing",
                "GEX missing default neutral",
                "LEI/USSLIND anomaly quarantined",
                "XLC sector ETF missing",
                "Minor yield curve date mismatch",
            ]
        },
    }


def _v4_payload_with_stale_usslind() -> dict:
    payload = _payload()
    payload["data"]["vix_engine_csv"] = (
        "Date,Version,VIX_Proxy,VIX_Direct,VIX9D_Proxy,VIX3M_Proxy,VVIX_Proxy,VVIX_Stress,VIX_Data_Flag\n"
        "2026-08-09,v4.0_yfinance_vix_fred_audit,14.899,14.899,16.85,20.54,90.42,NORMAL,NORMAL\n"
    )
    payload["data"]["macro_master_csv"] = payload["data"]["macro_master_csv"].replace(
        "2026-05-11", "2026-08-09"
    )
    payload["data"]["fred_master_csv"] = ",USSLIND\n2020-02-01,1.72\n"
    return payload


def test_market_data_overrides_extract_confirmed_macro_feeds() -> None:
    overrides = extract_market_data_overrides(_payload())

    assert overrides["vix9d"] == 16.85
    assert overrides["vix3m"] == 18.04
    assert overrides["vvix"] == 137.18
    assert overrides["hy_oas"] == 2.79
    assert overrides["ig_oas"] == 0.99
    assert overrides["gex_score"] == 0.75
    assert overrides["usslind_quarantined"] is False
    assert overrides["xlc_present"] is True


def test_market_data_overrides_clear_stale_partial_flags() -> None:
    macro = apply_market_data_overrides(_macro(), _payload())
    packet = build_macro_quant_packet(macro)

    assert macro["vix_spot"] == 18.04
    assert macro["gex_regime_score"] == 0.75
    assert macro["credit_state"] == "BENIGN"
    assert macro["extras"]["vvix"] == 137.18
    assert macro["extras"]["credit"]["hy_oas"] == 2.79
    assert macro["extras"]["gex"]["regime"] == "POSITIVE"
    assert macro["extras"]["lei_usslind"]["quarantined"] is False
    assert macro["extras"]["sector_etf_coverage"]["xlc_present"] is True
    assert packet["macro_data_quality"] == "CONFIRMED"
    assert packet["macro_active_conflict_flags"] == []


def test_v4_vix_aliases_and_stale_usslind_quarantine() -> None:
    payload = _v4_payload_with_stale_usslind()
    overrides = extract_market_data_overrides(payload)
    macro = apply_market_data_overrides(_macro(), payload)
    packet = build_macro_quant_packet(macro)

    assert overrides["vix"] == 14.899
    assert overrides["vix9d"] == 16.85
    assert overrides["vix3m"] == 20.54
    assert overrides["vvix"] == 90.42
    assert overrides["vix_data_quality"] == "NORMAL"
    assert overrides["usslind_source_date"] == "2020-02-01"
    assert overrides["usslind_age_days"] > 180
    assert overrides["usslind_quarantined"] is True
    assert macro["extras"]["macro_market_data_quality"]["vix_term_structure"] == "CONFIRMED"
    assert macro["extras"]["macro_market_data_quality"]["vvix"] == "CONFIRMED"
    assert macro["extras"]["macro_market_data_quality"]["lei_usslind"] == "QUARANTINED"
    assert not any("VIX9D/VIX3M missing" in flag for flag in macro["extras"]["conflict_flags"])
    assert not any("VVIX missing" in flag for flag in macro["extras"]["conflict_flags"])
    assert packet["macro_data_quality"] == "PARTIAL"


def _dual_spy_gex_payload(*, live_status: str, reverse: bool = False) -> dict:
    payload = _payload()
    header = (
        "Run_Id,Date,As_Of,Ticker,Snapshot_UTC,Data_Mode,Net_GEX_Bn,Regime,"
        "Gamma_Flip,GEX_Stress,Contracts_Used,Data_Status\n"
    )
    rows = [
        "hist-run,2026-08-31,2026-08-31T20:00:00Z,SPY,2026-08-31T20:01:00Z,"
        "HISTORICAL,-11.0,NEGATIVE,610.0,HIGH,900,OK\n",
        f"live-run,2026-09-01,2026-09-01T14:00:00Z,SPY,2026-09-01T14:01:00Z,"
        f"LIVE,22.0,POSITIVE,620.0,LOW,1200,{live_status}\n",
    ]
    if reverse:
        rows.reverse()
    payload["data"]["gex_proxy_csv"] = header + "".join(rows)
    return payload


def test_gex_primary_prefers_ok_live_spy_independent_of_row_order() -> None:
    forward = extract_market_data_overrides(
        _dual_spy_gex_payload(live_status="OK", reverse=False)
    )
    reverse = extract_market_data_overrides(
        _dual_spy_gex_payload(live_status="OK", reverse=True)
    )

    for overrides in (forward, reverse):
        assert overrides["gex_net_bn"] == 22.0
        assert overrides["gex_regime"] == "POSITIVE"
        assert overrides["gex_data_mode"] == "LIVE"
        assert overrides["gex_data_status"] == "OK"
        assert overrides["gex_run_id"] == "live-run"


def test_gex_primary_falls_back_to_ok_historical_when_live_not_ok() -> None:
    overrides = extract_market_data_overrides(
        _dual_spy_gex_payload(live_status="MISSING", reverse=False)
    )

    assert overrides["gex_net_bn"] == -11.0
    assert overrides["gex_regime"] == "NEGATIVE"
    assert overrides["gex_data_mode"] == "HISTORICAL"
    assert overrides["gex_data_status"] == "OK"
    assert overrides["gex_run_id"] == "hist-run"


def test_gex_primary_preserves_spy_diagnostic_when_no_row_is_ok() -> None:
    payload = _dual_spy_gex_payload(live_status="MISSING", reverse=True)
    payload["data"]["gex_proxy_csv"] = payload["data"]["gex_proxy_csv"].replace(
        "900,OK", "900,MISSING"
    )
    overrides = extract_market_data_overrides(payload)

    assert overrides["gex_data_mode"] == "LIVE"
    assert overrides["gex_data_status"] == "MISSING"
    assert overrides["gex_run_id"] == "live-run"
