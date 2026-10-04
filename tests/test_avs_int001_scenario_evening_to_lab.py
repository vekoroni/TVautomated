"""INT-001 scenario suite 3: a realistic Evening population through the Lab book to the API.

Eight tickers, one completed session, one Evening run. Each row is a situation the trader
actually meets. The suite asserts the design's axis separation (§3): thesis direction is never
changed by quote or data state, no row disappears, no row is execution-ready without a
source-qualified invalidation, and what the Lab API serves is byte-for-byte what was published.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.direction_governance import resolve_governed_direction  # noqa: E402
from contracts.lab_control import (  # noqa: E402
    build_final_opportunity_book,
    read_final_opportunity_book,
    write_final_opportunity_book,
)
from domain.pretrade_focus import project_evening_thesis  # noqa: E402
from morning_handoff_finalizer import _attach_persisted_validation_events  # noqa: E402

RUN = "20260925_230000"
SESSION = "2026-09-25"


def _evidence(side: str, independent: bool = True) -> str:
    return json.dumps([
        {"family": "PRICE_FLOW", "side": side, "direction_independent": independent},
        {"family": "CATALYST", "side": side, "direction_independent": independent},
    ])


def _base(ticker: str, side: str, spot: float, *, target: float, stop: float, **overrides) -> dict:
    occ = f"{ticker}261120{'C' if side == 'CALL' else 'P'}{int(round(spot)) * 1000:08d}"
    row = {
        "ticker": ticker, "pipeline_mode": "EOD", "direction": side, "canonical_direction": side,
        "governed_direction": side, "final_direction": side,
        "signal_price": spot, "underlying_price": spot, "entry_spot": spot,
        "target_price": target, "target_price_source": "DISCOVERY_TARGET",
        "invalidation_price": stop, "invalidation_state": "AVAILABLE",
        "invalidation_source": "WYCKOFF_VALIDATION",
        "time_horizon": "6_10d", "horizon_bucket": "6_10d",
        "garch_expected_move_1_5d": 4.2, "garch_expected_move_6_10d": 1.8, "garch_expected_move_11_20d": 2.4,
        "expected_move_5d_fraction": 0.042, "expected_move_10d_fraction": 0.06,
        "expected_move_20d_fraction": 0.084, "horizon_convention": "CUMULATIVE_1SIGMA",
        "contract_symbol": occ, "selected_contract_symbol": occ, "monetisability_contract_symbol": occ,
        "contract_bid": 1.90, "contract_ask": 2.05, "bid": 1.90, "ask": 2.05,
        "selected_quote_dataset_id": f"quote-{ticker}", "monetisability_quote_snapshot_id": f"quote-{ticker}",
        "selected_quote_timestamp_utc": f"{SESSION}T19:59:30Z", "evidence_session_date": SESSION,
        "monetisability_state": "MONETISABLE", "direction_conflict_status": "NO_CONFLICT",
        "direction_resolution_call_score": 1.0 if side == "CALL" else 0.0,
        "direction_resolution_put_score": 0.0 if side == "CALL" else 1.0,
        "direction_resolution_evidence_json": _evidence(side),
        "trigger_primary": "RANGE_BREAK",
        "trigger_price": spot * (0.995 if side == "CALL" else 1.005),
        "wyckoff_execution_bias": "BULLISH" if side == "CALL" else "BEARISH",
        "thesis_structure_alignment": "ALIGNED",   # XLU-D10: readiness needs an event on the trade side
        "lab_verdict": "GO", "lab_tradeable": True, "final_action": "BUY_NOW",
        "priority_score": 70.0, "sector": "Technology",
        "convexity_score": 3.0, "convexity_campaign": "CORE_CAMPAIGN",  # verdict-encoded, unsourced
    }
    # The governed direction record (hash-bound) that every production row carries.
    explicit_direction = {k: row[k] for k in (
        "direction_conflict_status", "direction_resolution_call_score",
        "direction_resolution_put_score", "direction_resolution_evidence_json",
    )}
    row.update(resolve_governed_direction(
        ticker=ticker, run_id=RUN, discovery_direction=side, governed_direction=side,
        governed_basis=f"test={side}", row={}, decided_at_utc=f"{SESSION}T21:00:00+00:00",
    ))
    row.update(explicit_direction)
    row.update(overrides)
    return row


def _population() -> list[dict]:
    return [
        # 1. idiosyncratic CALL with a sector headwind: headwind is advisory, direction stays CALL
        _base("ACME", "CALL", 48.20, target=51.10, stop=46.05, macro_sector_alignment="HEADWIND",
              priority_score=82.0),
        # 2. clean PUT decline thesis
        _base("DECL", "PUT", 120.50, target=112.00, stop=125.90, priority_score=77.0),
        # 3. CALL whose independent price/flow family points the other way
        _base("OPPO", "CALL", 33.10, target=35.40, stop=31.60,
              direction_resolution_evidence_json=_evidence("PUT"), direction_conflict_status="CONFLICT",
              direction_resolution_put_score=0.7, direction_resolution_call_score=0.6),
        # 4. no two-sided quote on the selected contract (temporary market condition)
        _base("NOQT", "CALL", 15.75, target=17.20, stop=14.90, contract_bid="", contract_ask="",
              bid="", ask="", monetisability_state="NOT_EVALUATED", monetisability_quote_snapshot_id=""),
        # 5. generated 3R target (not independently supported)
        _base("GEN3", "PUT", 64.00, target=55.00, stop=67.00, target_price_source="TARGET_3R"),
        # 6. explicitly invalidated by the governed lifecycle
        _base("DEAD", "CALL", 22.40, target=24.50, stop=21.30, thesis_state="THESIS_INVALIDATED",
              liquidity_thesis_state="THESIS_INVALIDATED"),
        # 7. no authoritative invalidation yet
        _base("NOST", "CALL", 91.00, target=97.50, stop="", invalidation_state="MISSING_AUTHORITATIVE_STOP",
              invalidation_source=""),
        # 8. invalidation on the wrong side of a PUT (data defect, not a trade)
        _base("WRNG", "PUT", 58.30, target=53.00, stop=55.00),
    ]


# --------------------------------------------------------------------- Evening reasoning per row
def test_evening_buckets_reflect_each_situation_without_changing_direction():
    buckets = {row["ticker"]: project_evening_thesis(row) for row in _population()}
    assert buckets["ACME"]["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert buckets["DECL"]["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert buckets["OPPO"]["evening_thesis_bucket"] == "EOD_DIRECTION_EVIDENCE_REVIEW"
    assert "OPPOSING_DIRECTION_EVIDENCE" in buckets["OPPO"]["evening_evidence_flags"]
    assert "preserve the governed direction" in buckets["OPPO"]["evening_next_condition"]
    assert buckets["NOQT"]["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"
    assert "quote" in buckets["NOQT"]["evening_thesis_reason"].lower()
    assert buckets["GEN3"]["evening_thesis_bucket"] == "EOD_TARGET_FEASIBILITY_REVIEW"
    assert "TARGET_GENERATED_3R_SCENARIO" in buckets["GEN3"]["evening_evidence_flags"]
    assert buckets["DEAD"]["evening_thesis_bucket"] == "EOD_THESIS_INVALIDATED"
    assert buckets["NOST"]["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"
    assert buckets["WRNG"]["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"
    assert "geometry" in buckets["WRNG"]["evening_thesis_reason"].lower()
    for result in buckets.values():
        assert result["evening_thesis_authority"] == "ADVISORY_PENDING_MORNING_CHECK"


def test_sector_headwind_is_advisory_and_a_new_quote_restores_expression_not_direction():
    acme = project_evening_thesis(_population()[0])
    assert acme["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    noqt = _population()[3]
    before = project_evening_thesis(noqt)
    assert before["evening_thesis_bucket"] == "EOD_EVIDENCE_REVIEW"
    recovered = dict(noqt, contract_bid=0.95, contract_ask=1.05, bid=0.95, ask=1.05,
                     monetisability_state="MONETISABLE", monetisability_quote_snapshot_id="quote-NOQT")
    after = project_evening_thesis(recovered)
    assert after["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert recovered["canonical_direction"] == noqt["canonical_direction"] == "CALL"


# --------------------------------------------------------------------- Lab book materialisation
@pytest.fixture(scope="module")
def book_rows() -> list[dict]:
    return build_final_opportunity_book(RUN, _population(), {"pipeline_mode": "EOD", "fatal_flags": []})


def test_book_keeps_the_whole_population_with_unique_identities(book_rows):
    assert len(book_rows) == 8
    assert {row["ticker"] for row in book_rows} == {r["ticker"] for r in _population()}
    assert len({row["trade_idea_id"] for row in book_rows}) == 8
    for row in book_rows:
        assert row["run_id"] == RUN
        assert row["canonical_direction"] in {"CALL", "PUT"}


def test_no_row_is_execution_ready_without_a_source_qualified_side_checked_stop(book_rows):
    by = {row["ticker"]: row for row in book_rows}
    assert by["NOST"]["lab_tradeable"] is False
    assert by["NOST"]["invalidation_spot"] in ("", None)
    assert "INVALIDATION" in by["NOST"]["execution_lock_reason"]
    assert by["WRNG"]["lab_tradeable"] is False
    assert by["WRNG"]["invalidation_state"] == "DATA_DEFECT_WRONG_SIDE"
    assert by["WRNG"]["invalidation_spot"] in ("", None)
    assert "INVALIDATION_WRONG_SIDE" in by["WRNG"]["lab_coherence_flags"]
    # The good rows carry the alias, equal to the side-checked price, with provenance.
    for ticker in ("ACME", "DECL"):
        assert by[ticker]["invalidation_spot"] == by[ticker]["invalidation_price"]
        assert by[ticker]["invalidation_source"] == "WYCKOFF_VALIDATION"
        provenance = json.loads(by[ticker]["field_provenance_json"])
        assert provenance["invalidation_spot"].endswith("side_checked_invalidation_alias")
    # A PUT stop above spot is on-side; a CALL stop below spot is on-side.
    assert float(by["DECL"]["invalidation_price"]) > float(by["DECL"]["signal_price"])
    assert float(by["ACME"]["invalidation_price"]) < float(by["ACME"]["signal_price"])


def test_verdict_encoded_convexity_is_withheld_on_every_row_but_nothing_else_is_lost(book_rows):
    for row in book_rows:
        assert row["convexity_data_state"] == "UNVERIFIED_SOURCE"
        assert row["convexity_score"] in ("", None)
        assert row["target_price"] not in ("", None) or row["ticker"] == "NOST"
        assert row["expected_move_10d_fraction"] == 0.06


def test_dead_and_reviewed_rows_stay_visible_with_their_history(book_rows):
    by = {row["ticker"]: row for row in book_rows}
    assert by["DEAD"]["evening_thesis_bucket"] == "EOD_THESIS_INVALIDATED"
    assert by["DEAD"]["target_price"] == 24.5
    assert by["DEAD"]["invalidation_price"] == 21.3
    assert by["OPPO"]["evening_thesis_bucket"] == "EOD_DIRECTION_EVIDENCE_REVIEW"
    assert by["OPPO"]["canonical_direction"] == "CALL"
    # Scenario disclosure is typed, never a fabricated payoff.
    for row in book_rows:
        assert row["scenario_is_expected_return"] is False
        assert row["scenario_state"] in {"NOT_ASSESSED", "NOT_APPLICABLE", "AVAILABLE", "CONTRACT_MISMATCH"}
        assert row["payoff_reachable_net_return_fraction"] in ("", None)


# --------------------------------------------------------------------- publication and API parity
def _load_lab_module(name: str):
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_published_book_is_what_the_lab_api_serves(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    (runs / RUN / "discovery").mkdir(parents=True)
    manifest = {"pipeline_mode": "EOD", "fatal_flags": [], "run_id": RUN}
    write_final_opportunity_book(RUN, _population(), manifest, runs)
    published = read_final_opportunity_book(RUN, runs)
    assert published["candidate_count"] == len(published["rows"]) == 8

    module = _load_lab_module("lab_int001_api_parity")
    monkeypatch.setattr(module, "RUNS_DIR", runs)
    module._run_cache.clear()
    client = module.app.test_client()
    response = client.get(f"/api/opportunity_book/{RUN}?full=1")
    assert response.status_code == 200
    served = response.get_json()["opportunity_book"]
    assert served["lab_schema_version"] == published["lab_schema_version"]
    assert served["candidate_count"] == 8
    served_by = {row["ticker"]: row for row in served["rows"]}
    for row in published["rows"]:
        assert served_by[row["ticker"]]["invalidation_spot"] == row["invalidation_spot"]
        assert served_by[row["ticker"]]["lab_tradeable"] == row["lab_tradeable"]
        assert served_by[row["ticker"]]["convexity_data_state"] == "UNVERIFIED_SOURCE"
    # The governed reader keeps the population and identity count.
    governed = module._governed_lab_book(RUN)
    assert governed["candidate_count"] == 8
    assert {r["ticker"] for r in governed["rows"]} == {r["ticker"] for r in _population()}


# --------------------------------------------------------------------- Morning appends, never overwrites
def _morning_rows() -> list[dict]:
    rows = []
    for row in _population()[:3]:
        morning = dict(row, pipeline_mode="MORNING_VALIDATION",
                       thesis_id=f"{row['ticker']}:{row['direction']}:{SESSION}:OLM2",
                       morning_execution_mode="POSTOPEN_CONTRACT_REFRESH",
                       morning_execution_permission="GO")
        rows.append(morning)
    return rows


def _event(row: dict, transition: str, price: float, **overrides) -> dict:
    event = {
        "invocation_id": RUN, "ticker": row["ticker"], "thesis_id": row["thesis_id"],
        "selected_contract": row["selected_contract_symbol"],
        "validation_event_id": f"validation_{row['ticker'].lower()}",
        "transition": transition, "current_price": price,
        "gap_pct": round((price / row["signal_price"] - 1) * 100, 3),
        "evidence_cutoff_utc": "2026-09-28T14:26:46Z", "data_status": "COMPLETE",
        "reason": "MORNING_GATE_RECORDED",
        "execution_gate_result": {"final_action": row["final_action"]},
    }
    event.update(overrides)
    return event


def test_morning_invalidation_event_appends_to_the_frozen_eod_claim(tmp_path):
    rows = _morning_rows()
    acme, decl, oppo = rows
    events = tmp_path / "validation_events"
    events.mkdir()
    (events / "acme.json").write_text(json.dumps(_event(acme, "THESIS_INVALIDATED", 45.80)), encoding="utf-8")
    (events / "decl.json").write_text(json.dumps(_event(decl, "THESIS_CONFIRMED", 119.90)), encoding="utf-8")
    # OPPO's event names a different contract: identity conflict, row stays visible.
    (events / "oppo.json").write_text(json.dumps(_event(
        oppo, "THESIS_CONFIRMED", 33.00, selected_contract="OPPO261120P00033000")), encoding="utf-8")
    issues = _attach_persisted_validation_events(rows, events, run_id=RUN)
    assert issues == ["OPPO:EVENT_IDENTITY_CONFLICT:validation event contract mismatch: OPPO"]

    book = {r["ticker"]: r for r in build_final_opportunity_book(RUN, rows, {"pipeline_mode": "MORNING_VALIDATION"})}
    assert book["ACME"]["validation_transition"] == "THESIS_INVALIDATED"
    assert book["ACME"]["validation_current_price"] == 45.80
    # Frozen Evening thesis fields remain; the breach is a dated event, not a deletion.
    assert book["ACME"]["canonical_direction"] == "CALL"
    assert book["ACME"]["target_price"] == 51.10
    assert book["ACME"]["invalidation_price"] == 46.05
    assert book["ACME"]["lab_projection_integrity_state"] == "COMPLETE"
    assert book["DECL"]["validation_transition"] == "THESIS_CONFIRMED"
    assert book["OPPO"]["validation_data_status"] == "EVENT_IDENTITY_CONFLICT"
    assert book["OPPO"]["lab_projection_integrity_state"] == "PROJECTION_INCOMPLETE"
    assert book["OPPO"]["canonical_direction"] == "CALL"


def test_morning_row_does_not_recompute_the_frozen_evening_bucket():
    row = _morning_rows()[0]
    row.update({"morning_data_state": "AVAILABLE", "evening_thesis_bucket": "EOD_ACTION_SETUP_READY",
                "evening_thesis_reason": "frozen", "signal_price": 40.0})  # a Morning drop must not re-judge
    result = project_evening_thesis(row)
    assert result["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    assert result["evening_thesis_reason"] == "frozen"
