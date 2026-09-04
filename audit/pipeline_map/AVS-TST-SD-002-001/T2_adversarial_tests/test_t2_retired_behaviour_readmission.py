"""AVS-TST-SD-002-001 / T2 adversarial pack.

For the two groups whose protective assertions were retired by the Phase 8
reconciliation -- the monetisability/OLM group and the options-research
hard-block group -- reintroduce the retired behaviour and establish whether the
*approved* authority (execution viability at the Execution Gate) still blocks
it, or whether the reconciliation left an unguarded path.

Read-only: imports production modules, writes nothing outside the output root.
Every direction-bearing probe runs CALL / PUT / OTHER.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from contracts.direction_governance import resolve_governed_direction  # noqa: E402
from contracts.long_option_policy import evaluate_execution_viability  # noqa: E402
from execution_gate import execution_gate  # noqa: E402

DIRECTIONS = ["CALL", "PUT", "OTHER"]


def _symbol(direction: str) -> str:
    return "AAA260918C00100000" if direction == "CALL" else "AAA260918P00100000"


def _row(
    direction: str = "CALL",
    *,
    monetisability_state: str = "MONETISABLE",
    viability: str | None = "EXECUTABLE_QUOTE",
    bid: float = 4.9,
    ask: float = 5.0,
) -> dict:
    """A row that is otherwise fully eligible for BUY_NOW."""
    side = direction if direction in {"CALL", "PUT"} else "UNRESOLVED"
    row: dict = {
        "ticker": "AAA",
        "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "contract_symbol": _symbol(direction),
        "live_contract_bid": bid,
        "live_contract_ask": ask,
        "live_contract_mid": (bid + ask) / 2.0,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.40,
        "live_iv_rank": 50,
        "signal_price": 100,
        "monetisability_state": monetisability_state,
        "monetisability_reason": "T2",
        "monetisability_contract_symbol": _symbol(direction),
        "selected_contract_side": side,
    }
    if direction in {"CALL", "PUT"}:
        row.update(
            resolve_governed_direction(
                ticker="AAA",
                run_id="20990101_010101",
                discovery_direction=direction,
                governed_direction=direction,
                governed_basis=f"t2={direction}",
                row={},
                decided_at_utc="2099-01-01T01:01:01+00:00",
            )
        )
    if viability is not None:
        row.update(
            {
                "execution_viability_state": viability,
                "execution_viability_reason": "T2",
                "execution_viability_contract_symbol": _symbol(direction),
                "execution_viability_eligible": viability == "EXECUTABLE_QUOTE",
                "execution_viability_reviewable": viability
                in {"EXECUTABLE_QUOTE", "MANUAL_LIQUIDITY_REVIEW"},
            }
        )
    return row


# --------------------------------------------------------------------------
# Group 1 -- monetisability / OLM.
# Retired behaviour: scenario monetisability held capital authority.
# Approved replacement: execution viability from the current quote.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_not_monetisable_with_viable_quote_is_not_blocked(direction: str) -> None:
    """AVS-AR-003 7.10 / F11: the retired authority must NOT block."""
    result = execution_gate(_row(direction, monetisability_state="NOT_MONETISABLE"))
    assert result["gate_reason"] != "NOT_MONETISABLE"
    if direction == "OTHER":
        # Unresolved direction must still be refused, by direction governance.
        assert result["final_action"] != "BUY_NOW"
    else:
        assert result["final_action"] == "BUY_NOW"


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
@pytest.mark.parametrize(
    "state",
    [
        "DATA_MISSING",
        "INVALID_QUOTE",
        "UNSUPPORTED_STRUCTURE",
        "ZERO_BID_REVIEW",
        "BLOCKED_WIDE_SPREAD",
        "MANUAL_LIQUIDITY_REVIEW",
    ],
)
def test_viability_failure_blocks_even_when_scenario_is_monetisable(
    direction: str, state: str
) -> None:
    """F11 second half: viability failure must block with MONETISABLE present."""
    result = execution_gate(
        _row(direction, monetisability_state="MONETISABLE", viability=state)
    )
    assert result["final_action"] != "BUY_NOW", (
        f"{direction}/{state}: a failed execution-viability state reached "
        f"{result['final_action']}"
    )


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_absent_execution_viability_state_must_not_reach_buy_now(direction: str) -> None:
    """THE ADVERSARIAL PROBE.

    Before Phase 2 the Execution Gate refused a GO row whose *capital-relevant
    quote evidence* was missing (``MONETISABILITY_STATE_MISSING`` ->
    CONTRACT_REPAIR).  Phase 2 deleted that guard and did not replace it for the
    new authority.  A row that arrives with no ``execution_viability_state`` at
    all therefore carries no hard current-quote evidence.

    AVS-SD-002 authority invariant: "missing measurements remain null with an
    explicit reason and never become zero"; AVS-AR-003 requires the capital
    owner to fail closed.  This test asserts the fail-closed behaviour.  It is
    EXPECTED TO FAIL against the current tree -- that failure is the defect.
    """
    result = execution_gate(_row(direction, viability=None))
    assert result["final_action"] != "BUY_NOW", (
        "Execution Gate granted BUY_NOW with no execution_viability_state; "
        "the pre-Phase-2 MONETISABILITY_STATE_MISSING guard was removed and "
        "no equivalent guard exists for the replacement authority"
    )


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_wide_spread_quote_is_still_stopped_by_the_gate(direction: str) -> None:
    """A 20%-of-mid spread must not reach BUY_NOW.

    Note the gate's own hard cap moved from 0.15 to
    LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT/100 = 0.18 in this build, so 20% is
    the smallest round figure that is above both.
    """
    bid, ask = 4.5, 5.5  # (5.5-4.5)/5.0 = 20.0% of mid
    row = _row(direction, viability="EXECUTABLE_QUOTE", bid=bid, ask=ask)
    result = execution_gate(row)
    assert result["final_action"] != "BUY_NOW"


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_spread_between_old_and_new_hard_cap_is_a_behaviour_change(direction: str) -> None:
    """16.6% of mid: above the pre-change 0.15 cap, below the new 0.18 cap.

    Documents the unflagged loosening of ExecutionGateConfig.SPREAD_MAX
    (0.15 -> LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT/100 = 0.18).  Before the
    change this band produced CONTRACT_REPAIR / COST_DESTRUCTION; it now
    produces a sized entry.
    """
    bid, ask = 4.585, 5.415  # (0.83)/5.0 = 16.6% of mid
    result = execution_gate(_row(direction, bid=bid, ask=ask))
    assert 0.15 < result["live_spread_pct"] < 0.18
    assert result["final_action"] in {"BUY_NOW", "BUY_SMALL"}
    assert result["final_action"] != "CONTRACT_REPAIR"
    assert "WARN_WIDE_SPREAD" in result["gate_warnings"]


# --------------------------------------------------------------------------
# Group 2 -- options-research hard blocks.
# Retired behaviour: SPREAD_GT_15PCT / ESTIMATED_R_LT_2 / NO_TRIGGER /
# BREAKEVEN_FEASIBILITY_LT_1 / MISSING_CRITICAL_OPTION_FIELDS were hard vetoes
# routing to OPTIONS_BLOCKED.  They are now advisory review flags.
# The question is whether a row carrying them can still reach capital.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_research_advisory_flags_cannot_by_themselves_reach_capital(direction: str) -> None:
    """A contract whose quote is unusable must be stopped by viability.

    The research route may now label it GO_REVIEW, but the hard authority is
    the current-quote viability contract.
    """
    hydrated = {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_structure": "LONG_SINGLE",
        "selected_contract_symbol": _symbol(direction),
        "selected_long_leg": {"bid": 1.60, "ask": 2.40},  # 40% of mid
    }
    viability = evaluate_execution_viability({}, hydrated)
    assert viability["execution_viability_state"] == "BLOCKED_WIDE_SPREAD"
    assert viability["execution_viability_eligible"] is False

    result = execution_gate(
        _row(direction, viability="BLOCKED_WIDE_SPREAD", bid=1.60, ask=2.40)
    )
    assert result["final_action"] != "BUY_NOW"


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_missing_bid_ask_is_stopped_by_viability_not_by_the_retired_veto(
    direction: str,
) -> None:
    hydrated = {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_structure": "LONG_SINGLE",
        "selected_contract_symbol": _symbol(direction),
        "selected_long_leg": {"bid": None, "ask": None},
    }
    viability = evaluate_execution_viability({}, hydrated)
    assert viability["execution_viability_state"] == "DATA_MISSING"
    result = execution_gate(_row(direction, viability="DATA_MISSING"))
    assert result["final_action"] != "BUY_NOW"


def test_other_direction_never_reaches_capital() -> None:
    result = execution_gate(_row("OTHER"))
    assert result["final_action"] != "BUY_NOW"
