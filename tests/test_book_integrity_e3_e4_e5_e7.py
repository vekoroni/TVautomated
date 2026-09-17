"""WP2 / WP3 / WP4 (part) — opportunity-book integrity: defects E3, E4, E5, E7.

Business rules (Enhancements/expression_forensics/EXPRESSION_FORENSIC_AND_TDD_APPROACH_20260917.md
sections 2, 3, 5; data-quality rules DQ-1 ... DQ-4; ACK decision S2):

* E3 / DQ-1  A contract price that was not observed stays missing in the EOD
             candidate book. It is never written as 0.0.
* E4 / DQ-3  Every contract price, greek and size in the book belongs to the
             contract symbol written in the same row. When the Lab reselects a
             contract for the direction and cannot establish that contract's
             own quote, the quote is missing and the reason is recorded. A 0.0
             ask is not a price.
* E5 / DQ-2  A contract on the wrong side of the governed direction never
             reaches the book as the option expression. The option expression
             is removed with an explicit state; the row (share expression) stays.
* E7 / DQ-4  The invalidation written to the book lies on the thesis side of the
             reference price (below for CALL, above for PUT); a wrong-side level
             is missing, with the reason recorded, and never replaced silently.

Characterisation of the defective behaviour (all passing on 202836b before the
fix) is recorded in the commit message; these tests replace it.
Directions covered throughout: CALL, PUT and a non-directional row.
"""
from __future__ import annotations

import csv
import math
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from contracts.direction_governance import resolve_governed_direction
from contracts.lab_control import opportunity_book_row, write_final_opportunity_book
from eod_candidate_engine import build_candidate_manifest
from tests.test_eod_options_research_handoff import _row as _eod_row

CALL_OCC = "AAPL260918C00100000"
PUT_OCC = "AAPL260918P00095000"


# ─── E3: EOD candidate book ─────────────────────────────────────────────────

def _manifest(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        eil = root / "execution_v3_5_E3.csv"
        out_path = root / "morning_candidates_E3.csv"
        pd.DataFrame(rows).to_csv(eil, index=False)
        out = build_candidate_manifest(eil_path=eil, output_path=out_path, run_id="E3")
        with out_path.open(encoding="utf-8", newline="") as fh:
            written = list(csv.DictReader(fh))
    return out.to_dict("records"), written


def _is_nan(value) -> bool:
    """Missing in the frame (NaN, or None in an object column) — never 0.0."""
    return value is None or (isinstance(value, float) and math.isnan(value))


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_e3_unobserved_contract_prices_stay_missing_in_candidate_book(direction: str) -> None:
    row = _eod_row("AAA", route="OPTIONS_GO_REVIEW")
    row["direction"] = row["options_direction"] = direction
    row.pop("contract_spread_pct")
    records, written = _manifest([row])
    record = {r["ticker"]: r for r in records}["AAA"]
    for field in ("contract_ask", "contract_mid", "premium_eod", "contract_spread_pct"):
        assert _is_nan(record[field]), f"{field} must be missing, got {record[field]!r}"
    csv_row = {r["ticker"]: r for r in written}["AAA"]
    for field in ("contract_ask", "contract_mid", "premium_eod", "contract_spread_pct"):
        assert csv_row[field] == "", f"{field} written as {csv_row[field]!r}"


def test_e3_blank_non_numeric_and_zero_asks_are_not_prices() -> None:
    rows = []
    for ticker, ask in (("BLANK", ""), ("TEXT", "n/a"), ("ZERO", 0.0), ("REAL", 1.25)):
        row = _eod_row(ticker, route="OPTIONS_GO_REVIEW")
        row.update({"contract_ask": ask, "contract_mid": ask, "premium": ask})
        rows.append(row)
    records, _ = _manifest(rows)
    by_ticker = {r["ticker"]: r for r in records}
    for ticker in ("BLANK", "TEXT", "ZERO"):
        assert _is_nan(by_ticker[ticker]["contract_ask"]), ticker
        assert _is_nan(by_ticker[ticker]["contract_mid"]), ticker
        assert _is_nan(by_ticker[ticker]["premium_eod"]), ticker
    assert by_ticker["REAL"]["contract_ask"] == 1.25
    assert by_ticker["REAL"]["contract_mid"] == 1.25
    assert by_ticker["REAL"]["premium_eod"] == 1.25


# ─── Lab book fixtures ──────────────────────────────────────────────────────

def _sig(direction: str, **extra) -> dict:
    governed = resolve_governed_direction(
        ticker="AAPL", run_id="RUN-BI", discovery_direction=direction,
        governed_direction=direction, governed_basis=f"test={direction}", row={},
        decided_at_utc="2026-09-04T08:00:00+00:00",
    ) if direction in {"CALL", "PUT"} else {}
    sig = {
        "ticker": "AAPL",
        "canonical_direction": direction,
        "final_direction": direction,
        "instrument": f"LONG_{direction}",
        "signal_price": 100.0,
        "underlying_price": 100.0,
        "structural_target": 110.0 if direction == "CALL" else 90.0,
        "invalidation_spot": 95.0 if direction == "CALL" else 105.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "GOVERNED_THESIS",
        **governed,
    }
    sig.update(extra)
    return sig


_QUOTE = {
    "contract_bid": 1.0, "contract_ask": 1.1, "contract_mid": 1.05,
    "contract_delta": 0.45, "contract_gamma": 0.03, "contract_theta": -0.02,
    "contract_vega": 0.1, "contract_iv": 0.31, "contract_oi": 900, "contract_volume": 150,
    "contract_bid_size": 25, "contract_ask_size": 40, "contract_spread_pct": 9.5,
    "strike": 100.0, "expiry": "2026-09-18", "dte": 10, "premium_mid": 1.05,
    "breakeven_price": 101.1, "option_gain_at_target": 2.3, "rr_options": 2.0,
}
_CONTRACT_MARKET_FIELDS = (
    "contract_bid", "contract_ask", "contract_mid", "contract_delta", "contract_gamma",
    "contract_theta", "contract_vega", "contract_iv", "contract_oi", "contract_volume",
    "contract_bid_size", "contract_ask_size", "premium_mid", "spread_pct",
    "spread_pct_of_mid", "spread_fraction_mid", "dte", "breakeven_price",
    "option_gain_at_target", "rr_predicted", "rr_premium_expected",
)


# ─── E4: prices belong to the written contract ─────────────────────────────

@pytest.mark.parametrize(
    "direction, original, reselected, strike, expiry",
    [
        ("PUT", CALL_OCC, PUT_OCC, 95.0, "2026-09-18"),
        ("CALL", "AAPL261016P00095000", "AAPL261016C00105000", 105.0, "2026-10-16"),
    ],
)
def test_e4_reselected_contract_never_borrows_the_original_contracts_quote(
    direction, original, reselected, strike, expiry
) -> None:
    row = opportunity_book_row(
        _sig(direction, contract_symbol=original, recommended_contract=reselected, **_QUOTE),
        "RUN-BI", 1,
    )
    assert row["contract_symbol"] == reselected
    for field in _CONTRACT_MARKET_FIELDS:
        assert row[field] in ("", None), f"{field} borrowed from {original}: {row[field]!r}"
    # Strike and expiry are facts of the written symbol itself.
    assert float(row["strike"]) == strike
    assert row["expiry"] == expiry
    assert "CONTRACT_QUOTE_NOT_ESTABLISHED_FOR_RESELECTED_CONTRACT" in row["lab_coherence_flags"]
    assert f"CONTRACT_RESELECTED_FOR_DIRECTION:{original}->{reselected}" in row["lab_coherence_flags"]


@pytest.mark.parametrize("direction, symbol", [("CALL", CALL_OCC), ("PUT", PUT_OCC)])
def test_e4_unchanged_contract_keeps_its_own_quote(direction, symbol) -> None:
    row = opportunity_book_row(_sig(direction, contract_symbol=symbol, **_QUOTE), "RUN-BI", 1)
    assert row["contract_symbol"] == symbol
    assert row["contract_ask"] == 1.1
    assert row["contract_bid"] == 1.0
    assert row["contract_delta"] == 0.45
    assert "CONTRACT_QUOTE_NOT_ESTABLISHED" not in (row["lab_coherence_flags"] or "")


@pytest.mark.parametrize("direction, symbol", [("CALL", CALL_OCC), ("PUT", PUT_OCC)])
def test_e4_zero_ask_is_not_a_price(direction, symbol) -> None:
    row = opportunity_book_row(_sig(direction, contract_symbol=symbol, contract_ask=0.0), "RUN-BI", 1)
    assert row["contract_ask"] in ("", None)
    row = opportunity_book_row(
        _sig(direction, contract_symbol=symbol, contract_ask="0.0", opt__contract_ask=1.2),
        "RUN-BI", 1,
    )
    assert row["contract_ask"] == 1.2


# ─── E5: wrong-side contract never reaches the book as the option expression ─

@pytest.mark.parametrize("direction, wrong_symbol, wrong_side", [("PUT", CALL_OCC, "CALL"), ("CALL", PUT_OCC, "PUT")])
def test_e5_wrong_side_contract_removes_option_expression_and_keeps_share_expression(
    direction, wrong_symbol, wrong_side
) -> None:
    row = opportunity_book_row(
        _sig(direction, contract_symbol=wrong_symbol, lab_verdict="GO", lab_tradeable=True, **_QUOTE),
        "RUN-BI", 1,
    )
    # Option expression removed, explicitly.
    assert row["contract_symbol"] in ("", None)
    assert row["contract_data_state"] == "OPTION_EXPRESSION_REMOVED_CONTRACT_SIDE_CONFLICT"
    assert f"CONTRACT_SYMBOL_SIDE_CONFLICT:{wrong_side}->{direction}" in row["lab_coherence_flags"]
    for field in _CONTRACT_MARKET_FIELDS + ("strike", "expiry"):
        assert row[field] in ("", None), f"{field} of the wrong-side contract reached the book"
    assert row["lab_tradeable"] is False
    # Share expression kept: the row, its direction and its thesis geometry remain.
    assert row["ticker"] == "AAPL"
    assert row["canonical_direction"] == direction
    assert float(row["invalidation_price"]) == (95.0 if direction == "CALL" else 105.0)
    assert float(row["structural_target"]) == (110.0 if direction == "CALL" else 90.0)


def test_e5_non_directional_row_contract_is_not_side_checked() -> None:
    row = opportunity_book_row(_sig("STRANGLE", contract_symbol=CALL_OCC, contract_ask=1.1), "RUN-BI", 1)
    assert row["contract_symbol"] == CALL_OCC
    assert row["contract_data_state"] == "AVAILABLE"


def test_e5_run_source_enrichment_cannot_restore_the_removed_expression(tmp_path) -> None:
    run = tmp_path / "RUN-BI"
    (run / "options").mkdir(parents=True)
    with (run / "options" / "options_intelligence_RUN-BI.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "contract_symbol", "contract_ask", "contract_spread_pct"])
        writer.writeheader()
        writer.writerow({"ticker": "AAPL", "contract_symbol": CALL_OCC, "contract_ask": 1.1, "contract_spread_pct": 0.07})
    book = write_final_opportunity_book(
        "RUN-BI",
        [_sig("PUT", contract_symbol=CALL_OCC)],
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []},
        tmp_path,
        sync_interpreter=False,
    )
    row = book["rows"][0]
    assert row["contract_symbol"] in ("", None)
    assert row["contract_data_state"] == "OPTION_EXPRESSION_REMOVED_CONTRACT_SIDE_CONFLICT"
    assert row.get("contract_ask") in ("", None)
    assert row.get("spread_pct") in ("", None)


# ─── E7: invalidation on the thesis side of the reference price ─────────────

@pytest.mark.parametrize(
    "direction, wrong_level",
    [("CALL", 104.0), ("PUT", 96.0)],
)
def test_e7_wrong_side_legacy_stop_never_becomes_the_book_invalidation(direction, wrong_level) -> None:
    sig = _sig(direction, contract_symbol=CALL_OCC if direction == "CALL" else PUT_OCC)
    sig.pop("invalidation_spot")
    sig["stop_loss"] = wrong_level
    row = opportunity_book_row(sig, "RUN-BI", 1)
    assert row["invalidation_price"] in ("", None)
    assert row["invalidation_state"] == "DATA_DEFECT_WRONG_SIDE"
    assert "INVALIDATION_WRONG_SIDE:stop_loss" in row["lab_coherence_flags"]
    assert row["lab_tradeable"] is False


@pytest.mark.parametrize("direction, wrong_level", [("CALL", 101.0), ("PUT", 99.0)])
def test_e7_wrong_side_governed_level_is_missing_not_replaced_by_a_legacy_stop(direction, wrong_level) -> None:
    right_stop = 95.0 if direction == "CALL" else 105.0
    sig = _sig(direction, invalidation_spot=wrong_level, stop_loss=right_stop)
    row = opportunity_book_row(sig, "RUN-BI", 1)
    assert row["invalidation_price"] in ("", None)
    assert row["invalidation_state"] == "DATA_DEFECT_WRONG_SIDE"
    assert "INVALIDATION_WRONG_SIDE:invalidation_spot" in row["lab_coherence_flags"]


@pytest.mark.parametrize("direction, level", [("CALL", 95.0), ("PUT", 105.0)])
def test_e7_correct_side_invalidation_is_kept(direction, level) -> None:
    row = opportunity_book_row(_sig(direction, invalidation_spot=level), "RUN-BI", 1)
    assert float(row["invalidation_price"]) == level
    assert row["invalidation_state"] == "AVAILABLE"
    assert "INVALIDATION_WRONG_SIDE" not in (row["lab_coherence_flags"] or "")


def test_e7_non_directional_row_invalidation_is_not_side_checked() -> None:
    row = opportunity_book_row(_sig("STRANGLE", invalidation_spot=104.0), "RUN-BI", 1)
    assert float(row["invalidation_price"]) == 104.0


def test_e7_side_rule_has_one_owner() -> None:
    from contracts.thesis_geometry import invalidation_on_thesis_side

    assert invalidation_on_thesis_side("CALL", 95.0, 100.0) is True
    assert invalidation_on_thesis_side("CALL", 100.0, 100.0) is False
    assert invalidation_on_thesis_side("PUT", 105.0, 100.0) is True
    assert invalidation_on_thesis_side("PUT", 95.0, 100.0) is False
    assert invalidation_on_thesis_side("STRANGLE", 95.0, 100.0) is False
    assert invalidation_on_thesis_side("CALL", 0.0, 100.0) is False
    assert invalidation_on_thesis_side("CALL", 95.0, None) is False
