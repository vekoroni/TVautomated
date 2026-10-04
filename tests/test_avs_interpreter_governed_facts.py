"""Interpreter batch (ACK 2 Oct 2026): XLU-D06, D02, D07/D08, D12, D14.

Root cause shared by all five: the narrative was not fed the governed facts, so the model
inferred or searched for them. Business rules:
- D06: when Morning holds a fresh quote for the same contract, the contract evidence is that
  quote (MORNING_QUOTE), with days-to-expiry from the contract symbol; EOD values travel
  beside it for comparison.
- D07/D08: spot-versus-level sides (gamma flip, call wall, put wall) are computed, signed and
  read deterministically; the model never infers above/below.
- D12: a ticker that is its own sector ETF has no ticker-versus-sector link (N/A), and an
  exact zero is FLAT, never "opposes".
- D14: per-ticker gamma levels carry their chain source, as-of and scope, distinct from the
  market-level Money Index GEX.
- D02: macro rates come from the governed record; any rate figure in the narrative that the
  governed facts do not hold is flagged.
Evidence: run 20260930_083504 XLU desk reports.
"""
import pytest

from pipeline_interpreter.governed_facts import (
    gamma_provenance, level_relations, macro_rates, unverified_rate_claims,
)


def test_level_sides_are_computed_and_read_deterministically():
    out = level_relations({"gamma_flip": 38.2336, "call_wall": 40.0, "put_wall": 25.0}, spot=39.51)
    flip, call, put = out["gamma_flip"], out["call_wall"], out["put_wall"]
    assert flip["side"] == "SPOT_ABOVE_LEVEL" and flip["distance_pct"] == pytest.approx(3.3388, abs=1e-3)
    assert call["side"] == "SPOT_BELOW_LEVEL" and "overhead resistance" in call["reading"]
    assert put["side"] == "SPOT_ABOVE_LEVEL" and "support below" in put["reading"]
    assert out["spot"] == 39.51
    assert level_relations({"call_wall": None}, spot=None)["state"] == "SPOT_UNAVAILABLE"


def test_gamma_levels_carry_their_source_and_scope():
    out = gamma_provenance({"option_chain_dataset_id": "83dea88e", "option_chain_provider": "MARKETDATA",
                            "option_chain_resolution": "PROVIDER_FETCH", "quote_as_of": "2026-09-29T20:00:00Z",
                            "gamma_flip_state": "GRID_REPRICED_CROSSING"})
    assert out["scope"] == "PER_TICKER_OPTION_CHAIN"
    assert "not the market-level" in out["scope_note"]
    assert out["chain_dataset_id"] == "83dea88e" and out["gamma_flip_method"] == "GRID_REPRICED_CROSSING"
    assert gamma_provenance({})["state"] == "SOURCE_NOT_RECORDED"


def test_macro_rates_come_from_the_governed_record():
    out = macro_rates({"macro_context_state": ""}, {"t10y": 5.26, "macro_context_state": "CONFLICTING_SOURCES"})
    assert out["t10y_pct"] == 5.26 and out["macro_context_state"] == "CONFLICTING_SOURCES"
    assert macro_rates({}, None)["state"] == "NOT_IN_GOVERNED_EVIDENCE"


def test_rate_figures_not_in_governed_facts_are_flagged():
    rates = {"t10y_pct": 5.26}
    flagged = unverified_rate_claims(["with ~4.30% on the 10-year per recent research"], rates)
    assert flagged == ["4.30%"]
    assert unverified_rate_claims(["the 10-year at 5.26% weighs on utilities"], rates) == []
    assert unverified_rate_claims(["spread 6.45% is acceptable"], rates) == []      # not a rate claim


def _confluence(row, morning=None):
    from pathlib import Path
    from pipeline_interpreter.confluence_evidence import build_confluence_evidence
    return build_confluence_evidence(row, session_date=None, evidence_cutoff_utc="2026-10-01T20:00:00Z",
                                     historical_prices_path=Path("missing.sqlite"), morning=morning)


EOD_ROW = {"ticker": "XLU", "sector_etf": "XLU", "direction": "PUT", "contract_symbol": "XLU270115P00040000",
           "contract_bid": 1.55, "contract_ask": 1.72, "contract_delta": -0.4567,
           "selected_quote_timestamp_utc": "2026-09-29T20:00:00Z", "target_price": 37.2, "invalidation_price": 44.65}
MORNING = {"fields": {"live_contract_symbol": "XLU270115P00040000", "live_contract_bid": 1.8,
                      "live_contract_ask": 1.92, "live_contract_delta": -0.5112,
                      "live_contract_quote_timestamp": "2026-10-01T15:32:04Z", "quote_freshness": "FRESH",
                      "live_price": 39.51, "validation_transition": "PENDING_TRIGGER"},
           "evidence_cutoff_utc": "2026-10-01T16:06:49Z", "bundle_id": "m", "refresh_required": False}


def test_contract_evidence_uses_the_fresh_morning_quote():
    contract = _confluence(EOD_ROW, MORNING)["contract"]
    assert contract["evidence_ref"] == "MORNING_QUOTE"
    assert contract["quote_is_live_executable"] is True
    assert contract["spread_pct_ask"] == pytest.approx((1.92 - 1.8) / 1.92 * 100, abs=1e-3)
    assert contract["delta"] == -0.5112 and contract["quote_timestamp_utc"] == "2026-10-01T15:32:04Z"
    assert contract["eod_spread_pct_ask"] == pytest.approx((1.72 - 1.55) / 1.72 * 100, abs=1e-3)
    assert contract["days_to_expiry"] == (__import__("datetime").date(2027, 1, 15) - __import__("datetime").date(2026, 10, 1)).days


def test_without_morning_the_contract_evidence_stays_labelled_eod():
    contract = _confluence(EOD_ROW)["contract"]
    assert contract["evidence_ref"] == "EOD_BOOK" and contract["quote_is_live_executable"] is False


def test_sector_etf_has_no_ticker_vs_sector_link():
    from pipeline_interpreter.confluence_evidence import _ticker_link
    assert _ticker_link("XLU", "XLU", 0.0, "PUT") == ("NOT_APPLICABLE_TICKER_IS_SECTOR_ETF", None)
    assert _ticker_link("NEE", "XLU", 0.0, "PUT")[0] == "FLAT"
    assert _ticker_link("NEE", "XLU", -0.01, "PUT")[0] == "SUPPORTS"
    assert _ticker_link("NEE", "XLU", 0.01, "PUT")[0] == "OPPOSES"


def test_digest_carries_the_governed_facts_and_the_prompt_forbids_inference():
    from pipeline_interpreter import desk_provider_common as common
    from pipeline_interpreter.interactive_desk import compile_evidence_digest
    bundle = {"run_id": "R", "ticker": "XLU", "bundle_id": "b", "source_manifest_sha256": "s"}
    row = {**EOD_ROW, "gamma_flip": 38.2336, "call_wall": 40.0, "put_wall": 25.0, "signal_price": 39.71,
           "option_chain_provider": "MARKETDATA"}
    morning = {**MORNING, "fields": {**MORNING["fields"], "t10y": 5.26}}
    digest = compile_evidence_digest(row, bundle, morning, evidence_cutoff_utc="2026-09-30T21:00:00Z",
                                     eod_technical_health="OK", confluence=_confluence(EOD_ROW, morning))
    assert digest["level_relations"]["call_wall"]["side"] == "SPOT_BELOW_LEVEL"
    assert digest["level_relations"]["spot_source"] == "MORNING_LIVE_PRICE"
    assert digest["gamma_provenance"]["chain_provider"] == "MARKETDATA"
    assert digest["macro_rates"]["t10y_pct"] == 5.26
    for template in (common.REPORT_INSTRUCTIONS_TEMPLATE, common.DEEP_REPORT_INSTRUCTIONS_TEMPLATE):
        assert "evidence.level_relations" in template and "evidence.macro_rates" in template
        assert "evidence.gamma_provenance" in template


def test_generated_reports_carry_the_rate_figure_check():
    from pipeline_interpreter.interactive_desk import governed_number_check
    content = {"executive_summary": "Rates headwind with ~4.30% on the 10-year per recent research.",
               "sections": [{"text": "Spread 6.45% is acceptable."}], "evidence_chain_review": [],
               "counter_case": {"text": ""}}
    out = governed_number_check(content, {"macro_rates": {"t10y_pct": 5.26}})
    assert out["state"] == "UNVERIFIED_RATE_FIGURES" and out["unverified_rate_figures"] == ["4.30%"]
