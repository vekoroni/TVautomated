from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTERPRETER = ROOT / "pipeline_interpreter"
if str(INTERPRETER) not in sys.path:
    sys.path.insert(0, str(INTERPRETER))

from pipeline_interpreter_commands import (  # noqa: E402
    _classify_battlefield_candidate,
    _lab_monetisation_failure,
    cmd_live,
    cmd_morning,
)


def _morning(state: str = "CONFIRMED", permission: str = "GO", contract: str = "TRADEABLE") -> dict:
    return {
        "live_validation_state": state,
        "morning_execution_permission": permission,
        "contract_tradability_state": contract,
    }


def test_lab_and_morning_authority_contract() -> None:
    aligned = {
        "run_id_match": True,
        "confirmed": ["AAA", "REPAIR"],
        "actionable": ["AAA"],
    }

    verdict, reason, _ = _classify_battlefield_candidate(_morning(), "AAA", aligned)
    assert verdict == "DEEP_DIVE_NOW"
    assert "jointly approved" in reason

    verdict, reason, _ = _classify_battlefield_candidate(_morning(), "OUTSIDE", aligned)
    assert verdict == "REVIEW_LATER"
    assert "LAB_NOT_REVIEWED" in reason

    verdict, reason, _ = _classify_battlefield_candidate(_morning(), "REPAIR", aligned)
    assert verdict == "REVIEW_LATER"
    assert "LAB_NOT_ACTIONABLE" in reason

    verdict, _, _ = _classify_battlefield_candidate(_morning(state="BLOCKED", permission="BLOCKED"), "AAA", aligned)
    assert verdict == "SKIP_TODAY"

    mismatch = {**aligned, "run_id_match": False}
    verdict, reason, _ = _classify_battlefield_candidate(_morning(), "AAA", mismatch)
    assert verdict == "REVIEW_LATER"
    assert "LAB_AUTHORITY_INVALID" in reason


def test_interpreter_does_not_create_a_second_ev_or_rr_gate() -> None:
    assert _lab_monetisation_failure({"EV_Decision": "WEAK", "RR": "2.0"}) == ""
    assert _lab_monetisation_failure({"EV_Decision": "AVOID", "RR": "2.0"}) == ""
    assert _lab_monetisation_failure({"EV_Decision": "MODERATE", "RR": "0"}) == ""
    assert _lab_monetisation_failure({"EV_Decision": "STRONG", "RR": ""}) == ""
    assert _lab_monetisation_failure({"EV_Decision": "MODERATE", "RR": "1.25"}) == ""
    assert _lab_monetisation_failure({"EV_Decision": "STRONG", "RR": "0.01"}) == ""


def test_retired_commands_do_not_create_second_data_or_validation_authority() -> None:
    assert cmd_live("AAA") is None
    assert cmd_morning("ignored.csv") is None
