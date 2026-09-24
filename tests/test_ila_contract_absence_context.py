"""An absent selected option has a cause, not an invented zero or a lost ticker."""

from domain.contract_observation_status import project_contract_observation_status
import csv
from pathlib import Path


def test_direction_not_governed_means_chain_not_requested():
    row = {"ticker": "ABT", "governed_direction": "UNRESOLVED", "contract_symbol": ""}
    options = {"contract_repair_reason": "No governed long CALL/PUT direction; chain request suppressed"}
    result = project_contract_observation_status(row, options)
    assert result["contract_absence_state"] == "NO_GOVERNED_LONG_DIRECTION"
    assert result["contract_chain_request_state"] == "NOT_REQUESTED"


def test_provider_empty_is_not_same_as_chain_not_requested():
    row = {"ticker": "AEHL", "governed_direction": "PUT", "contract_symbol": ""}
    options = {"contract_rejection_reason": "CHAIN_FETCH_FAILED"}
    result = project_contract_observation_status(row, options)
    assert result["contract_absence_state"] == "PROVIDER_CHAIN_UNAVAILABLE"
    assert result["contract_chain_request_state"] == "REQUESTED_NO_USABLE_CHAIN"


def test_quoted_chain_rejected_for_spread_remains_visible():
    row = {"ticker": "BWIN", "governed_direction": "CALL", "contract_symbol": "", "lab_verdict": "CONTRACT_REPAIR"}
    options = {"contract_rejection_reason": "NO_CONTRACT_PASSED_QUALITY_GATES",
               "primary_rejection_reason": "REJECT_SPREAD",
               "contracts_funnel_chain_rows": "64", "contracts_funnel_quote_usable": "2",
               "contracts_funnel_passing_spread": "0"}
    result = project_contract_observation_status(row, options)
    assert result["contract_absence_state"] == "SPREAD_REVIEW_NO_SELECTED_CONTRACT"
    assert result["contract_chain_request_state"] == "CHAIN_OBSERVED"
    assert result["contract_observed_chain_rows"] == 64
    assert result["contract_usable_quote_count"] == 2
    assert result["contract_passing_spread_count"] == 0
    assert row["lab_verdict"] == "CONTRACT_REPAIR"


def test_selected_contract_is_not_marked_absent():
    row = {"ticker": "SLV", "contract_symbol": "SLV261030C00062500"}
    result = project_contract_observation_status(row, {})
    assert result["contract_absence_state"] == "SELECTED_CONTRACT_AVAILABLE"


def test_missing_options_source_is_diagnostic_not_provider_failure():
    result = project_contract_observation_status({"ticker": "ZZZ", "contract_symbol": ""}, None)
    assert result["contract_absence_state"] == "OPTIONS_SOURCE_MISSING"


def test_stored_run_distinguishes_provider_spread_and_no_request():
    root = Path(__file__).resolve().parents[1]
    path = root / "data/output/runs/20260922_223221/options/options_intelligence_20260922_223221.csv"
    if not path.exists():
        return  # Portable source checkout has no production run.
    csv.field_size_limit(10_000_000)
    wanted = {"AEHL", "BWIN", "ABT"}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = {row["ticker"]: row for row in csv.DictReader(handle) if row["ticker"] in wanted}
    assert set(rows) == wanted
    directions = {"AEHL": "PUT", "BWIN": "CALL", "ABT": "UNRESOLVED"}
    states = {symbol: project_contract_observation_status(
        {"ticker": symbol, "governed_direction": directions[symbol], "contract_symbol": ""}, rows[symbol],
    )["contract_absence_state"] for symbol in wanted}
    assert states == {
        "AEHL": "PROVIDER_CHAIN_UNAVAILABLE",
        "BWIN": "SPREAD_REVIEW_NO_SELECTED_CONTRACT",
        "ABT": "NO_GOVERNED_LONG_DIRECTION",
    }


def test_lab_mounts_run_matched_options_explanation_without_authority_mutation():
    html = (Path(__file__).resolve().parents[1] / "intelligence-lab/static/index.html").read_text(encoding="utf-8")
    backend = (Path(__file__).resolve().parents[1] / "intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8")
    assert "_row.update(project_contract_observation_status(" in backend
    assert "s.contract_absence_state" in html
    assert "s.contract_chain_request_state" in html
