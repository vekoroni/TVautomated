"""Agent E (OLM increment retest) - design SS8.3 observability diagnostics.

Retests the six required aggregate run-summary diagnostics against the
current scripts/avshunter_options_intelligence.py, now that
select_repair_alternative_contracts() accepts an optional `diagnostics`
mutable-dict out-parameter and the run-level summary builder aggregates it
via _aggregate_repair_selector_diagnostics().

Run with: venv/Scripts/python.exe audit/olm_fix_test/agentE_diagnostics_retest.py
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


def mixed_fixture_rows():
    return [
        # retained, OI < 50 (report as retained_oi_below_50)
        base_row(symbol="RET_LOWOI", open_interest=5, volume=2, delta=0.30, strike=101.0),
        # retained, zero volume (report as retained_zero_volume)
        base_row(symbol="RET_ZEROVOL", open_interest=200, volume=0, delta=0.31, strike=101.5),
        # rejected: zero bid -> invalid/missing quote
        base_row(symbol="REJ_ZEROBID", bid=0.0, ask=2.05, delta=0.32, strike=99.0, open_interest=9000),
        # rejected: wide spread (mid=1.5, half-spread=0.5 -> spread_pct=0.333, over default limit)
        base_row(symbol="REJ_WIDESPREAD", bid=1.0, ask=2.0, delta=0.33, strike=103.0, open_interest=9000),
        # rejected: missing delta -> dte/delta/geometry bucket
        base_row(symbol="REJ_BADDELTA", delta=None, strike=98.0, open_interest=9000),
        # rejected: DTE out of window -> dte/delta/geometry bucket
        base_row(symbol="REJ_OUT_OF_DTE", dte=200, strike=97.0, open_interest=9000),
    ]


def diagnostics_dict_check():
    rows = mixed_fixture_rows()
    diagnostics = oi._new_repair_selector_diagnostics()
    result = oi.select_repair_alternative_contracts(
        pd.DataFrame(rows), CTX, limit=6, diagnostics=diagnostics
    )
    record(
        "diagnostics_dict_populated_by_direct_call",
        diagnostics=diagnostics,
        retained_symbols=[c["symbol"] for c in result],
        retained_count=len(result),
    )
    return diagnostics, result


def per_row_fields_check():
    rows = mixed_fixture_rows()
    diagnostics = oi._new_repair_selector_diagnostics()
    result = oi.select_repair_alternative_contracts(
        pd.DataFrame(rows), CTX, limit=6, diagnostics=diagnostics
    )
    fields = oi._repair_selector_diagnostic_fields(diagnostics)
    record("repair_selector_diagnostic_fields_output", fields=fields)
    return fields


def aggregate_summary_check():
    # Simulate two separate row-level results, as would appear in `results`
    # passed to _aggregate_repair_selector_diagnostics() from the run-level
    # summary builder (options_intelligence_summary_*.json path).
    rows_a = mixed_fixture_rows()
    diag_a = oi._new_repair_selector_diagnostics()
    oi.select_repair_alternative_contracts(pd.DataFrame(rows_a), CTX, limit=6, diagnostics=diag_a)
    fields_a = oi._repair_selector_diagnostic_fields(diag_a)

    rows_b = [base_row(symbol="B_RET_LOWOI2", open_interest=1, volume=5, delta=0.30, strike=101.0)]
    diag_b = oi._new_repair_selector_diagnostics()
    oi.select_repair_alternative_contracts(pd.DataFrame(rows_b), CTX, limit=6, diagnostics=diag_b)
    fields_b = oi._repair_selector_diagnostic_fields(diag_b)

    # A "result" row in the real pipeline is a dict of pandas-row output
    # fields merged with repair_alt_fields (which includes these
    # repair_selector_* keys per the diff at lines ~6347 and ~6590).
    fake_results = [dict(fields_a), dict(fields_b)]
    aggregate = oi._aggregate_repair_selector_diagnostics(fake_results)
    record("run_level_aggregate_summary", per_row_fields=[fields_a, fields_b], aggregate=aggregate)
    return aggregate


def summary_json_field_check():
    import inspect
    src = inspect.getsource(oi)
    has_aggregate_call = "repair_selector_diagnostics" in src and "_aggregate_repair_selector_diagnostics(results)" in src
    # Locate the literal summary dict assembly line for citation.
    idx = src.find("'repair_selector_diagnostics': _aggregate_repair_selector_diagnostics(results)")
    line_no = src.count("\n", 0, idx) + 1 if idx != -1 else None
    record(
        "run_summary_json_builder_wiring",
        found_in_summary_dict_literal=has_aggregate_call,
        approx_source_line=line_no,
    )
    return has_aggregate_call, line_no


if __name__ == "__main__":
    diagnostics_dict_check()
    per_row_fields_check()
    aggregate_summary_check()
    summary_json_field_check()

    out_path = Path(__file__).parent / "agentE_diagnostics_retest_output.json"
    out_path.write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(f"\n\nWrote {out_path}")
