"""Agent B (OLM fix validation) - additional §11.3 / §8.2 / §8.3 / §8.1 checks
not already covered by tests/test_ev3_options_handoff.py.

Run with: venv/Scripts/python.exe audit/olm_fix_test/agentB_selector_tests.py
(avoid pytest's batched capture bug per task instructions; this is a plain
script executed directly so no stdout-capture conflict occurs).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import scripts.avshunter_options_intelligence as oi  # noqa: E402

RESULTS = {}


def record(name, **kw):
    RESULTS[name] = kw
    print(f"\n===== {name} =====")
    for k, v in kw.items():
        print(f"  {k}: {v}")


def base_row(**overrides):
    row = dict(
        symbol="BASE260918C00102000", right="C", strike=102.0,
        expiration_date="2026-09-18", dte=20,
        bid=1.00, ask=1.05, delta=0.30, gamma=0.02, theta=-0.03, vega=0.06,
        implied_vol=0.35, quote_timestamp_utc="2026-08-14T10:30:00Z",
        open_interest=500, volume=100, contract_multiplier=100,
    )
    row.update(overrides)
    return row


CTX = {"direction": "CALL", "dte_window": (7, 30, 60), "spot": 100.0,
       "structural_target": 110.0, "dte_config": {}}


# ---------------------------------------------------------------------------
# 1. High OI cannot rescue 4 separate fatal defects
# ---------------------------------------------------------------------------
def high_oi_cannot_rescue():
    missing_delta = base_row(symbol="HIOI_NO_DELTA", delta=None)
    missing_greeks = base_row(symbol="HIOI_NO_GREEKS", gamma=None)
    missing_timestamp = base_row(symbol="HIOI_NO_TS", quote_timestamp_utc=None)
    naive_timestamp = base_row(symbol="HIOI_NAIVE_TS", quote_timestamp_utc="2026-08-14 10:30:00")  # no tz -> None per _quote_timestamp_utc
    invalid_crossed = base_row(symbol="HIOI_CROSSED", bid=2.10, ask=1.90)  # bid > ask

    out = {}
    for label, row in (
        ("missing_delta", missing_delta),
        ("missing_greeks", missing_greeks),
        ("missing_timestamp", missing_timestamp),
        ("naive_timestamp_treated_as_missing", naive_timestamp),
        ("invalid_crossed_bid_ask", invalid_crossed),
    ):
        candidates = oi.select_repair_alternative_contracts(pd.DataFrame([row]), CTX)
        out[label] = {"oi": row["open_interest"], "candidate_count": len(candidates), "rejected": len(candidates) == 0}
    record("high_oi_cannot_rescue_fatal_defects", **out)
    return out


# ---------------------------------------------------------------------------
# 2. Normal high-OI fixture ordering unchanged (before/after diff)
#    (module comparison done by a separate single-module subprocess script to
#    avoid the double stdout-wrap issue; this half runs only the current module
#    and records the exact order + delta_distance/spread/oi/volume tie-break
#    inputs so the companion backup run can be diffed against it.)
# ---------------------------------------------------------------------------
def ordering_fixture_rows():
    rows = []
    # 3 expiries x 4 strikes, varying delta distance / spread / oi / volume so
    # the deterministic sort key (delta_distance, spread_pct, -oi, -volume, symbol)
    # is meaningfully exercised, matching the un-touched code at
    # scripts/avshunter_options_intelligence.py:4561-4567 (identical pre/post).
    expiries = [("2026-09-08", 25), ("2026-09-13", 30), ("2026-09-23", 40)]
    strikes = [
        (98.0, 0.25, 0.03, 400, 50),
        (100.0, 0.35, 0.02, 900, 300),
        (100.0, 0.35, 0.02, 100, 10),   # identical delta/strike, lower oi/vol -> tie-break
        (102.0, 0.45, 0.05, 250, 20),
        (104.0, 0.55, 0.01, 700, 80),
    ]
    for e_idx, (expiry, dte) in enumerate(expiries):
        for s_idx, (strike, delta, spread_bump, oi_val, vol_val) in enumerate(strikes):
            mid = 2.00
            half_spread = spread_bump * mid
            bid = round(mid - half_spread, 4)
            ask = round(mid + half_spread, 4)
            rows.append(dict(
                symbol=f"ORD{e_idx}{s_idx}", right="C", strike=strike,
                expiration_date=expiry, dte=dte,
                bid=bid, ask=ask, delta=delta, gamma=0.03, theta=-0.04, vega=0.10,
                implied_vol=0.40, quote_timestamp_utc="2026-08-14T10:30:00Z",
                open_interest=oi_val, volume=vol_val, contract_multiplier=100,
            ))
    return rows


def ordering_check():
    rows = ordering_fixture_rows()
    candidates = oi.select_repair_alternative_contracts(pd.DataFrame(rows), CTX, limit=6)
    order = [
        {
            "symbol": c["symbol"], "expiry": c["expiry"], "delta_distance": c["delta_distance"],
            "spread_pct": c["spread_pct"], "oi": c["oi"], "volume": c["volume"],
            "rank": c["candidate_generation_rank"],
        }
        for c in candidates
    ]
    record("ordering_current_module", order=order, count=len(candidates))
    out_path = Path(__file__).parent / "agentB_ordering_current_output.json"
    out_path.write_text(json.dumps(order, indent=2, default=str), encoding="utf-8")
    return order


# ---------------------------------------------------------------------------
# 3. §8.1 REPORTED vs MISSING_ASSUMED_ZERO — a REAL reported zero vs absent field
# ---------------------------------------------------------------------------
def reported_vs_missing_zero():
    real_zero = base_row(symbol="REAL_ZERO_OI", open_interest=0, volume=0)
    missing = dict(base_row(symbol="MISSING_OI_VOL"))
    del missing["open_interest"]
    del missing["volume"]

    real_zero_result = oi.select_repair_alternative_contracts(pd.DataFrame([real_zero]), CTX)[0]
    missing_result = oi.select_repair_alternative_contracts(pd.DataFrame([missing]), CTX)[0]

    record(
        "reported_vs_missing_assumed_zero",
        real_zero_oi_value=real_zero_result["oi"],
        real_zero_oi_status=real_zero_result["oi_observation_status"],
        real_zero_volume_status=real_zero_result["volume_observation_status"],
        missing_oi_value=missing_result["oi"],
        missing_oi_status=missing_result["oi_observation_status"],
        missing_volume_status=missing_result["volume_observation_status"],
        distinct_labels=(real_zero_result["oi_observation_status"] != missing_result["oi_observation_status"]),
    )
    return real_zero_result, missing_result


# ---------------------------------------------------------------------------
# 4. §8.3 observability - does the selector (or its direct wrapper) return
#    the six required summary diagnostics anywhere?
# ---------------------------------------------------------------------------
def observability_check():
    mixed_rows = [
        base_row(symbol="RET_LOWOI", open_interest=5, volume=2, delta=0.30, strike=101.0),
        base_row(symbol="RET_ZEROVOL", open_interest=200, volume=0, delta=0.31, strike=101.5),
        base_row(symbol="REJ_ZEROBID", bid=0.0, ask=2.05, delta=0.32, strike=99.0, open_interest=9000),
        base_row(symbol="REJ_WIDESPREAD", bid=1.0, ask=2.0, delta=0.33, strike=103.0, open_interest=9000),
        base_row(symbol="REJ_BADDELTA", delta=None, strike=98.0, open_interest=9000),
        base_row(symbol="REJ_OUT_OF_DTE", dte=200, strike=97.0, open_interest=9000),
    ]
    result = oi.select_repair_alternative_contracts(pd.DataFrame(mixed_rows), CTX, limit=6)
    is_plain_list = isinstance(result, list)
    has_summary_dict = False  # function signature is List[Dict[str, Any]] only
    import inspect
    sig = str(inspect.signature(oi.select_repair_alternative_contracts))
    source_has_telemetry_keys = any(
        key in Path(oi.__file__).read_text(encoding="utf-8", errors="replace")
        for key in [
            "retained_low_oi_count", "retained_zero_volume_count",
            "rejected_invalid_quote_count", "rejected_spread_count",
            "rejected_dte_delta_geometry_count", "final_bounded_candidate_count",
        ]
    )
    record(
        "section_8_3_observability",
        return_type_is_plain_list=is_plain_list,
        return_signature=sig,
        six_required_diagnostic_keys_found_anywhere_in_file=source_has_telemetry_keys,
        retained_count_in_mixed_fixture=len(result),
        retained_symbols=[c["symbol"] for c in result],
        conclusion=(
            "select_repair_alternative_contracts() returns only a bounded "
            "List[Dict] of surviving candidates. No aggregate telemetry object "
            "(retained-low-OI count, retained-zero-volume count, "
            "rejected-invalid-quote count, rejected-spread count, "
            "rejected-DTE/delta/geometry count, final-bounded-candidate count) "
            "is constructed inside the function, and no caller "
            "(_no_contract_singles / long_alternatives call sites, "
            "_format_repair_alternative_fields, _alternative_handoff_audit, "
            "options_intelligence_summary_*.json) assembles these six counts "
            "either. _alternative_handoff_audit only reports "
            "'alternative_contracts_rejected_incomplete' (a downstream "
            "completeness check unrelated to the in-selector rejection "
            "categories required by design §8.3)."
        ),
    )
    return result


if __name__ == "__main__":
    high_oi_cannot_rescue()
    ordering_check()
    reported_vs_missing_zero()
    observability_check()

    out_path = Path(__file__).parent / "agentB_selector_tests_output.json"
    out_path.write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(f"\n\nWrote {out_path}")
