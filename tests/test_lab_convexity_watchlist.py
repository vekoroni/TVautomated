"""Saved-input display only: no providers, no permission upgrades, no request pricing."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import socket
import sys

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domain.lab_convexity import build_watchlist
from domain.option_valuation import option_value, return_on_premium
from contracts.lab_review_projection import publish_review_projection, register_review_routes, ReviewIntegrityError
from contracts.lab_convexity_watchlist import read_convexity


def candidate(**changes):
    row = dict(ticker="AAA", direction="CALL", contract_symbol="AAA270115C00100000",
        anticipated_contract_symbol="AAA270115C00100000", expiry="2027-01-15",
        anticipated_valued_at_utc="2026-10-20T14:00:00Z", selected_quote_timestamp_utc="2026-10-20T14:00:00Z",
        contract_bid=4.8, contract_ask=5.0, contract_iv=0.4, contract_oi=1000, contract_volume=0,
        scenario_exit_sessions=10, scenario_target_exit_spot=125, live_price=99,
        invalidation_price=94, thesis_trigger_level=101, scenario_invalidation_return_on_premium=-.5,
        scenario_stall_return_on_premium=-.2, valuation_entry_cost_usd_per_share=5.011,
        valuation_rate_annual=.04, valuation_dividend_yield_annual=0, valuation_model="AMERICAN_CRR",
        valuation_cost_basis="ENTRY_AT_ASK_PLUS_FEE|EXIT_AT_MODEL_LESS_HALF_QUOTED_SPREAD",
        lab_verdict="MANUAL_REVIEW", final_action="MANUAL_REVIEW", execution_authorized=False,
        execution_can_grant_capital=False, final_capital_permission="HUMAN_APPROVAL_REQUIRED",
        thesis__readiness="WAIT_TRIGGER", direction_governance_status="CONFIRMED",
        direction_conflict_status="NO_CONFLICT", execution_viability_state="EXECUTABLE_QUOTE",
        anticipated_time_fit="CONTRACT_OUTLASTS_Q80", geometry_justification="NOT_MEASURED")
    value = option_value("CALL", 125, 100, (87-10*1.4484)/365, .4, rate=.04, dividend_yield=0)["value"]
    row["scenario_target_return_on_premium"] = return_on_premium(value, bid=4.8, ask=5.0)
    row.update(changes)
    return row


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbid(*a, **kw):
        raise AssertionError("No network allowed")
    monkeypatch.setattr(socket.socket, "connect", forbid)


def test_waiting_preserves_source_authority_and_same_target_stress():
    row=candidate(); original=deepcopy(row)
    out=build_watchlist([row]); item=out["groups"]["waiting"][0]
    assert row == original
    assert not item["automatic_execution_authorized"] and not item["source_execution_authorized"]
    assert item["lab_verdict"] == "MANUAL_REVIEW"
    assert item["stress"]["delay_sessions"] == 20
    assert item["stress"]["iv_stressed"] == pytest.approx(.32)
    assert item["stress"]["combined_return"] <= item["target_return"]


def test_go_is_human_review_not_automatic_capital():
    row=candidate(lab_verdict="GO", thesis__readiness="READY_FOR_HUMAN_REVIEW",
                  geometry_justification="JUSTIFIED", morning_execution_lane="MORNING_VALIDATED",
                  morning_execution_permission="GO", morning_entry_action="REVIEW_AND_SIZE_LIMIT")
    item=build_watchlist([row])["groups"]["entry_ready"][0]
    assert item["execution_authorized"] is False
    assert item["final_capital_permission"] == "HUMAN_APPROVAL_REQUIRED"
    row["morning_execution_permission"]="NO_TRADE"
    assert not build_watchlist([row])["groups"]["entry_ready"]


@pytest.mark.parametrize("changes,reason",[
    ({"thesis_trigger_level":126},"TRIGGER_CONSUMES_MOST_MODELLED_MOVE_OR_UNKNOWN"),
    ({"thesis_trigger_level":124},"TRIGGER_CONSUMES_MOST_MODELLED_MOVE_OR_UNKNOWN"),
    ({"contract_oi":10},"RESEARCH_OPEN_INTEREST_LIMIT"),
    ({"contract_bid":1},"RESEARCH_SPREAD_LIMIT"),
    ({"lab_verdict":"BLOCKED"},"BLOCKED_REPAIR_OR_CLOSED"),
    ({"thesis__event_failed_at":"2026-10-19"},"THESIS_EVENT_FAILED"),
    ({"anticipated_time_fit":"CONTRACT_EXPIRES_BEFORE_Q80"},"EXPIRY_BEFORE_Q80_OR_UNKNOWN"),
    ({"valuation_rate_annual":None},"SAVED_VALUATION_INPUTS_INCOMPLETE"),
    ({"anticipated_contract_symbol":"OTHER"},"CONTRACT_LINEAGE_MISMATCH"),
    ({"scenario_target_return_on_premium":10},"SAVED_BASELINE_NOT_REPRODUCED"),
])
def test_unsafe_or_noncomparable_rows_are_named_not_promoted(changes,reason):
    out=build_watchlist([candidate(**changes)])
    assert not any(out["groups"].values())
    assert reason in out["exclusions"][0]["reasons"]


def test_delay_beyond_expiry_is_missing_not_priced_at_expiry():
    row=candidate(scenario_exit_sessions=40)
    v=option_value("CALL",125,100,(87-40*1.4484)/365,.4,rate=.04,dividend_yield=0)["value"]
    row["scenario_target_return_on_premium"]=return_on_premium(v,bid=4.8,ask=5)
    item=build_watchlist([row])["groups"]["waiting"][0]
    assert item["stress"]["state"] == "PARTIAL_DELAY_BEYOND_EXPIRY"
    assert item["stress"]["combined_return"] is None


def test_boolean_not_numeric_and_literal_ticker_preserved():
    out=build_watchlist([candidate(ticker="NAN"),candidate(ticker="SYM"),candidate(contract_iv=True)])
    assert {r["ticker"] for r in out["groups"]["waiting"]} == {"NAN","SYM"}
    assert len(out["exclusions"]) == 1


def test_publication_api_reads_only_and_revision_pin(tmp_path, monkeypatch):
    rows=[candidate()]; source=deepcopy(rows)
    receipt=publish_review_projection({"run_id":"TEST","candidate_count":1,"rows":rows},tmp_path)
    assert rows == source
    def forbid(*a,**kw):raise AssertionError("GET cannot calculate")
    monkeypatch.setattr("domain.lab_convexity.build_watchlist",forbid)
    monkeypatch.setattr("domain.option_valuation.option_value",forbid)
    app=Flask(__name__);register_review_routes(app,tmp_path)
    client=app.test_client()
    result=client.get('/api/lab/TEST/convexity?revision='+receipt['revision'])
    assert result.status_code == 200
    assert result.json['groups']['waiting'][0]['row_key']
    assert client.get('/api/lab/TEST/convexity?revision=wrong').status_code == 409
    path=tmp_path/'TEST/intelligence_lab/review_projection'/receipt['convexity_watchlist']['file']
    path.write_text('{}')
    with pytest.raises(ReviewIntegrityError):read_convexity(tmp_path,'TEST')


def test_missing_artifact_never_rebuilds_on_get(tmp_path):
    receipt=publish_review_projection({"run_id":"TEST","candidate_count":1,"rows":[candidate()]},tmp_path)
    path=tmp_path/'TEST/intelligence_lab/review_projection'/receipt['convexity_watchlist']['file']
    path.unlink()
    app=Flask(__name__);register_review_routes(app,tmp_path)
    assert app.test_client().get('/api/lab/TEST/convexity').status_code == 404
    assert not path.exists()
