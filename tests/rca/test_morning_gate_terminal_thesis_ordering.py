"""RCA reproduction for audit/rca/terminal_thesis/findings.md.

Defect class: "a terminal thesis accepts no further observations" is
enforced only inside OptionLiquidityLifecycleStore.record_contract_observation
(canonical_data/option_liquidity_lifecycle.py:744-745). Closing a thesis to a
terminal state (record_thesis_event) and appending its final observation
(record_contract_observation) are two separate writes, and ordering between
them is left to caller convention rather than being enforced atomically or at
the close call.

scripts/avshunter_options_intelligence.py::_persist_options_lifecycle_result
was reordered on 2026-08-30 (stage the thesis ACTIVE, append the observation,
close terminal last) specifically to avoid this. morning_gate.py's
_persist_morning_liquidity_result (morning_gate.py:2577-2766) is a second,
independent writer against the same store and was never touched by that fix:
it calls store.record_thesis_event(...) first (morning_gate.py:2627,
unconditionally, including with a terminal thesis_state/monitor_state when
morning_transition_state is THESIS_INVALIDATED or MOVE_ALREADY_REALIZED), and
only afterwards calls store.record_contract_observation(...)
(morning_gate.py:2716) for the same thesis_id in the same call -- with no
terminal-state guard in between. The runway assessment that decides
THESIS_INVALIDATED / MOVE_ALREADY_REALIZED is computed from a live quote
(morning_gate.py:1887-1932), so the live-quote fields required to reach the
record_contract_observation call are routinely present precisely when the
transition is terminal.

This test reproduces that ordering violation directly against
morning_gate._persist_morning_liquidity_result, and confirms its second-order
effect: the terminal close already committed before record_contract_observation
raises, so the thesis is left permanently terminal with zero observations --
the same fingerprint found in the production database for
FLYW:PUT:2026-08-30 (run 20260830_182402) and CART:PUT:2026-08-29
(run 20260829_222259); see findings.md Step 1/Step 3.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canonical_data.errors import DatasetValidationError
from canonical_data.option_liquidity_lifecycle import (
    OptionLiquidityLifecycleStore,
    ThesisState,
)
from canonical_data.registry import CanonicalRegistry
import morning_gate


RUN_ID = "20260830_071747"
SESSION = date(2026, 8, 30)


class MorningGateTerminalThesisOrderingTest(unittest.TestCase):
    """Reproduces 'cannot observe a terminal thesis' via the morning_gate.py
    call site that the 2026-08-30 EOD-path fix did not touch."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = CanonicalRegistry(self.root / "control_plane.sqlite")
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "MORNING", SESSION)
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _terminal_morning_result(self) -> dict:
        return {
            "ticker": "FLYW",
            "direction": "PUT",
            "final_direction": "PUT",
            "thesis_id": "FLYW-PUT-2026-08-30",
            # Same shape as the production failure: the runway assessment
            # decided the thesis is done (DTE_UNSUITABLE / THESIS_INVALIDATED)
            # in the same pass that also produced a live, gradeable quote.
            "morning_transition_state": "THESIS_INVALIDATED",
            "liquidity_state": "DTE_UNSUITABLE",
            "morning_selected_contract_symbol": "O:FLYW260918P00040000",
            "contract_symbol": "O:FLYW260918P00040000",
            "live_options_source": "MARKETDATA",
            "live_options_fetched_at": "2026-08-30T13:00:01Z",
            "live_contract_provider_updated": "2026-08-30T13:00:00Z",
            "live_price": 41.0,
            "live_contract_bid": 0.10,
            "live_contract_ask": 0.15,
            "live_contract_mid": 0.125,
            "live_contract_spread_pct": 33.3,
            "live_contract_delta": -0.05,
            "live_contract_gamma": 0.01,
            "live_contract_theta": -0.01,
            "live_contract_vega": 0.02,
            "live_contract_iv": 0.9,
            "live_contract_oi": 4,
            "live_contract_volume": 1,
            "maturation_score_1d": 5.0,
            "maturation_score_2d": 4.0,
            "maturation_score_3d": 3.0,
            "maturation_score_is_probability": False,
            "atm_distance_sigma": 2.4,
            "remaining_runway_pct": 0.0,
            "selected_contract_economics_ready": True,
            "contract_changed": False,
        }

    def test_invalidated_transition_persists_quote_before_closing_the_thesis(
        self,
    ) -> None:
        result = self._terminal_morning_result()

        with patch.object(morning_gate, "ROOT", self.root):
            morning_gate._persist_morning_liquidity_result(
                result, RUN_ID, self.registry, self.store
            )

        # The ordering violation's second-order effect: record_thesis_event
        # already committed the terminal close (morning_gate.py:2627) before
        # record_contract_observation raised (morning_gate.py:2716), so the
        # thesis is stuck permanently INVALIDATED with no observation ever
        # recorded for it -- matching the FLYW/CART rows in
        # data/canonical/control_plane.sqlite.
        closed = self.store.latest_thesis("FLYW-PUT-2026-08-30")
        self.assertIsNotNone(closed)
        self.assertIs(closed.thesis_state, ThesisState.INVALIDATED)
        self.assertIsNotNone(self.store.latest_observation("FLYW-PUT-2026-08-30"))
        self.assertEqual(result["morning_liquidity_persistence_status"], "PERSISTED_TERMINAL_CLOSED")

    def test_reusing_the_now_terminal_thesis_on_a_second_pass_masks_the_original_ordering_fault(
        self,
    ) -> None:
        """Contributing finding: morning_gate.py has no "already terminal,
        reuse idempotently" guard analogous to the one added to
        _persist_options_lifecycle_result (scripts/avshunter_options_intelligence.py:7669-7695).
        A second Morning Gate pass against the same thesis_id does not hit the
        observation guard again -- it hits record_thesis_event's own
        "terminal thesis cannot be reactivated" guard first, a *different*
        message from the same enforcement family, at a different call site's
        expense (record_thesis_event, morning_gate.py:2627) than the original
        failure (record_contract_observation, morning_gate.py:2716). Both are
        real ordering-violation surfaces; only one produces the exact string
        "cannot observe a terminal thesis" that this RCA was scoped to.
        """
        result = self._terminal_morning_result()
        with patch.object(morning_gate, "ROOT", self.root):
            morning_gate._persist_morning_liquidity_result(
                result, RUN_ID, self.registry, self.store
            )

            second_pass = dict(result)
            second_pass["live_options_fetched_at"] = "2026-08-30T13:05:01Z"
            second_pass["live_contract_provider_updated"] = "2026-08-30T13:05:00Z"
            morning_gate._persist_morning_liquidity_result(
                second_pass, RUN_ID, self.registry, self.store
            )
            self.assertEqual(
                second_pass["morning_liquidity_persistence_status"],
                "TERMINAL_REPLAY_REUSED",
            )


if __name__ == "__main__":
    unittest.main()
