"""Advisory explanation of why an option expression lacks a selected contract.

This read-model context neither selects a contract nor changes a thesis or gate.
Only run-matched Options evidence may explain an absence; unobserved is distinct
from a failed provider response, and missing values are never numeric zero.
"""


def _count(value):
    if value is None or str(value).strip().lower() in {"", "nan", "none", "null"}:
        return None
    try:
        number = float(value)
        return int(number) if number >= 0 and number.is_integer() else None
    except (TypeError, ValueError):
        return None


def project_contract_observation_status(row: dict, options_row: dict | None) -> dict:
    selected = str(row.get("contract_symbol") or row.get("selected_contract_symbol") or "").strip()
    base = {
        "contract_absence_source": "OPTIONS_INTELLIGENCE_RUN_CSV" if options_row else "SOURCE_MISSING",
        "contract_observed_chain_rows": _count((options_row or {}).get("contracts_funnel_chain_rows")),
        "contract_usable_quote_count": _count((options_row or {}).get("contracts_funnel_quote_usable")),
        "contract_passing_spread_count": _count((options_row or {}).get("contracts_funnel_passing_spread")),
    }
    if selected:
        return {**base, "contract_absence_state": "SELECTED_CONTRACT_AVAILABLE",
                "contract_chain_request_state": "SELECTED", "contract_absence_explanation": ""}
    if not options_row:
        return {**base, "contract_absence_state": "OPTIONS_SOURCE_MISSING",
                "contract_chain_request_state": "UNKNOWN",
                "contract_absence_explanation": "The run-matched Options record is unavailable; provider status is unknown."}
    direction = str(row.get("governed_direction") or row.get("direction") or "").upper()
    reason = str(options_row.get("contract_rejection_reason") or "").upper()
    repair = str(options_row.get("contract_repair_reason") or "").upper()
    if direction not in {"CALL", "PUT"} or "CHAIN REQUEST SUPPRESSED" in repair:
        return {**base, "contract_absence_state": "NO_GOVERNED_LONG_DIRECTION",
                "contract_chain_request_state": "NOT_REQUESTED",
                "contract_absence_explanation": "No governed long CALL/PUT direction; an option chain was not requested. Ticker thesis remains visible."}
    if reason == "CHAIN_FETCH_FAILED":
        return {**base, "contract_absence_state": "PROVIDER_CHAIN_UNAVAILABLE",
                "contract_chain_request_state": "REQUESTED_NO_USABLE_CHAIN",
                "contract_absence_explanation": "The option chain was requested but no usable chain was returned; this does not establish that the ticker is defunct."}
    if reason == "NO_CONTRACT_PASSED_QUALITY_GATES":
        spread_reject = str(options_row.get("primary_rejection_reason") or "").upper() == "REJECT_SPREAD"
        if spread_reject and base["contract_usable_quote_count"] and base["contract_passing_spread_count"] == 0:
            return {**base, "contract_absence_state": "SPREAD_REVIEW_NO_SELECTED_CONTRACT",
                    "contract_chain_request_state": "CHAIN_OBSERVED",
                    "contract_absence_explanation": "The chain and quotes exist, but no eligible contract passed the spread rule. Monitor for repricing; no selected-contract Greeks exist."}
        return {**base, "contract_absence_state": "QUALITY_REVIEW_NO_SELECTED_CONTRACT",
                "contract_chain_request_state": "CHAIN_OBSERVED",
                "contract_absence_explanation": "The chain was observed, but no contract passed the selection rules."}
    return {**base, "contract_absence_state": "NO_SELECTED_CONTRACT_UNRESOLVED",
            "contract_chain_request_state": "UNKNOWN",
            "contract_absence_explanation": "No selected contract; the run-matched Options record does not establish why."}
