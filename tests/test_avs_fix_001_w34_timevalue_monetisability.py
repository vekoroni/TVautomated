"""AVS-FIX-001 W3.4 (RCA3-D05, DEC-1) — the advisory time-value valuation.

`monetisability_state` values the contract at its expiry INTRINSIC floor. That
is deliberately conservative and deliberately biased in one direction: it
prices away every day of remaining time value, so it can only ever understate a
position. RCA-003 D-05 measured the cost — rows that reach their target with
real time value left are labelled NOT_MONETISABLE.

`monetisability_state_timevalue` is a SECOND record beside it: Black-Scholes
value of the same contract at `structural_target` on the final session of the
hold, sigma = contract_iv held constant, r = q = 0, against the same 20% floor.

**It is ADVISORY_ONLY and changes nothing downstream.** The authority tests at
the bottom of this file are the ones that matter most.
"""

from __future__ import annotations

from datetime import date
import unittest

from canonical_data.option_identity import build_occ_symbol
from canonical_data.session_clock import advance_xnys_sessions

from contracts.selected_contract_economics import (
    MONETISABILITY_TIMEVALUE_ASSUMPTIONS,
    MONETISABILITY_TIMEVALUE_AUTHORITY,
    MONETISABILITY_TIMEVALUE_MODEL,
    evaluate_long_option_monetisability,
    evaluate_timevalue_monetisability,
)


def hydrated(*, symbol="AAA260918C00100000", bid=0.80, ask=0.85, strike=100.0):
    return {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_structure": "LONG_SINGLE",
        "selected_structure_id": "fixture",
        "selected_contract_symbol": symbol,
        "selected_long_leg": {
            "symbol": symbol, "bid": bid, "ask": ask, "strike": strike,
        },
    }


def evaluate(*, direction, target, ask, strike, iv, dte, hold, bid=0.0):
    start_session = date(2026, 9, 1)
    expiry = advance_xnys_sessions(start_session, int(dte))
    symbol = build_occ_symbol("AAA", expiry, direction, strike)
    hyd = hydrated(symbol=symbol, bid=bid, ask=ask, strike=strike)
    row = {
        "canonical_direction": direction,
        "target_spot": target,
        "selected_quote_timestamp_utc": "2026-09-01T20:00:00Z",
    }
    intrinsic = evaluate_long_option_monetisability(row, hyd)
    timevalue = evaluate_timevalue_monetisability(
        {**row, "contract_iv": iv, "contract_dte": dte, "planned_hold_sessions": hold},
        hyd, intrinsic,
    )
    return intrinsic, timevalue


class NamedFixtures(unittest.TestCase):
    def test_pnw_call_intrinsic_not_monetisable_timevalue_monetisable(self) -> None:
        """The case AVS-IMP-FIX-001 names.

        PNW CALL, strike 100, ask 0.85, target 100.82, IV 18.7%, 8 DTE at
        target. Intrinsic at target is 0.82 against an 0.85 entry, so the floor
        says the trade cannot pay. With eight days of life left at the target
        it is worth considerably more than its intrinsic value.
        """
        intrinsic, timevalue = evaluate(
            direction="CALL", target=100.82, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        self.assertEqual(intrinsic["monetisability_state"], "NOT_MONETISABLE")
        self.assertEqual(
            intrinsic["monetisability_reason"],
            "STRUCTURAL_TARGET_DOES_NOT_CLEAR_BREAKEVEN",
        )
        self.assertEqual(timevalue["monetisability_state_timevalue"], "MONETISABLE")
        self.assertGreater(timevalue["monetisability_timevalue_profit_pct"], 20.0)

    def test_deep_itm_row_is_monetisable_on_both(self) -> None:
        intrinsic, timevalue = evaluate(
            direction="CALL", target=110.0, ask=9.2, strike=90.0,
            iv=0.25, dte=20, hold=5, bid=9.0,
        )
        self.assertEqual(intrinsic["monetisability_state"], "MONETISABLE")
        self.assertEqual(timevalue["monetisability_state_timevalue"], "MONETISABLE")

    def test_put_mirror(self) -> None:
        intrinsic, timevalue = evaluate(
            direction="PUT", target=99.18, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        self.assertEqual(intrinsic["monetisability_state"], "NOT_MONETISABLE")
        self.assertEqual(timevalue["monetisability_state_timevalue"], "MONETISABLE")

    def test_a_target_far_from_the_strike_is_not_monetisable_either_way(self) -> None:
        intrinsic, timevalue = evaluate(
            direction="CALL", target=80.0, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        self.assertEqual(intrinsic["monetisability_state"], "NOT_MONETISABLE")
        self.assertEqual(timevalue["monetisability_state_timevalue"], "NOT_MONETISABLE")


class LowerBoundProperty(unittest.TestCase):
    """Time value is never below intrinsic. Asserted on every fixture."""

    CASES = [
        ("CALL", 100.82, 0.85, 100.0, 0.187, 8, 0),
        ("CALL", 110.00, 9.20, 90.0, 0.250, 20, 5),
        ("CALL", 80.00, 0.85, 100.0, 0.187, 8, 0),
        ("CALL", 105.00, 2.00, 100.0, 0.400, 30, 10),
        ("PUT", 99.18, 0.85, 100.0, 0.187, 8, 0),
        ("PUT", 90.00, 9.20, 110.0, 0.250, 20, 5),
        ("PUT", 120.00, 0.85, 100.0, 0.187, 8, 0),
        ("PUT", 95.00, 2.00, 100.0, 0.400, 30, 10),
    ]

    def test_timevalue_is_never_below_intrinsic(self) -> None:
        for direction, target, ask, strike, iv, dte, hold in self.CASES:
            with self.subTest(direction=direction, target=target, strike=strike):
                intrinsic, timevalue = evaluate(
                    direction=direction, target=target, ask=ask,
                    strike=strike, iv=iv, dte=dte, hold=hold,
                )
                self.assertEqual(
                    timevalue["monetisability_state_timevalue"],
                    timevalue["monetisability_state_timevalue"].upper(),
                )
                self.assertGreaterEqual(
                    timevalue["monetisability_timevalue_value_per_share"],
                    intrinsic["monetisability_target_intrinsic_per_share"],
                    "a European option with r = q = 0 is never worth less than intrinsic",
                )

    def test_timevalue_profit_is_never_below_intrinsic_profit(self) -> None:
        for direction, target, ask, strike, iv, dte, hold in self.CASES:
            with self.subTest(direction=direction, target=target):
                intrinsic, timevalue = evaluate(
                    direction=direction, target=target, ask=ask,
                    strike=strike, iv=iv, dte=dte, hold=hold,
                )
                self.assertGreaterEqual(
                    timevalue["monetisability_timevalue_profit_pct"],
                    intrinsic["monetisability_target_profit_pct"],
                )

    def test_zero_time_remaining_reduces_to_intrinsic(self) -> None:
        intrinsic, timevalue = evaluate(
            direction="CALL", target=110.0, ask=9.2, strike=90.0,
            iv=0.25, dte=5, hold=5,
        )
        self.assertEqual(timevalue["monetisability_timevalue_years_to_expiry"], 0.0)
        self.assertAlmostEqual(
            timevalue["monetisability_timevalue_value_per_share"],
            intrinsic["monetisability_target_intrinsic_per_share"], places=6,
        )

    def test_a_hold_longer_than_the_contract_does_not_go_negative(self) -> None:
        _, timevalue = evaluate(
            direction="CALL", target=110.0, ask=9.2, strike=90.0,
            iv=0.25, dte=3, hold=10,
        )
        self.assertEqual(timevalue["monetisability_timevalue_years_to_expiry"], 0.0)


class NamedAbsences(unittest.TestCase):
    """Missing input is named, never guessed, and never falls back to intrinsic."""

    def _reason(self, **overrides):
        hyd = hydrated()
        row = {
            "canonical_direction": "CALL", "target_spot": 100.82,
            "selected_quote_timestamp_utc": "2026-09-01T20:00:00Z",
        }
        intrinsic = evaluate_long_option_monetisability(row, hyd)
        inputs = {"contract_iv": 0.187, "contract_dte": 8, "planned_hold_sessions": 0}
        inputs.update(overrides)
        return evaluate_timevalue_monetisability({**row, **inputs}, hyd, intrinsic)

    def test_missing_iv(self) -> None:
        result = self._reason(contract_iv=None)
        self.assertEqual(result["monetisability_state_timevalue"], "NOT_EVALUATED")
        self.assertEqual(result["monetisability_timevalue_reason"], "CONTRACT_IV_UNAVAILABLE")

    def test_missing_dte(self) -> None:
        result = self._reason(contract_dte=None)
        self.assertEqual(result["monetisability_timevalue_reason"], "CONTRACT_DTE_UNAVAILABLE")

    def test_missing_hold(self) -> None:
        result = self._reason(planned_hold_sessions=None)
        self.assertEqual(result["monetisability_timevalue_reason"], "PLANNED_HOLD_UNAVAILABLE")

    def test_a_zero_hold_is_a_value_not_an_absence(self) -> None:
        """0 is falsy; it must not be read as missing."""
        result = self._reason(planned_hold_sessions=0)
        self.assertNotEqual(result["monetisability_timevalue_reason"], "PLANNED_HOLD_UNAVAILABLE")
        self.assertEqual(result["monetisability_state_timevalue"], "MONETISABLE")

    def test_incomplete_intrinsic_record_is_not_evaluated(self) -> None:
        result = evaluate_timevalue_monetisability(
            {"canonical_direction": "CALL", "contract_iv": 0.2,
             "contract_dte": 8, "planned_hold_sessions": 0},
            hydrated(),
            {"monetisability_status": "FAILED", "monetisability_state": "DATA_MISSING"},
        )
        self.assertEqual(result["monetisability_state_timevalue"], "NOT_EVALUATED")
        self.assertEqual(
            result["monetisability_timevalue_reason"], "INTRINSIC_RECORD_INCOMPLETE"
        )

    def test_percentage_form_iv_is_normalised(self) -> None:
        decimal = self._reason(contract_iv=0.187)
        percent = self._reason(contract_iv=18.7)
        self.assertEqual(
            decimal["monetisability_timevalue_value_per_share"],
            percent["monetisability_timevalue_value_per_share"],
        )
        self.assertEqual(percent["monetisability_timevalue_iv_used"], 0.187)


class AuthorityIsUnchanged(unittest.TestCase):
    """The tests that matter most: this column grants and removes nothing."""

    def test_the_record_declares_itself_advisory(self) -> None:
        _, timevalue = evaluate(
            direction="CALL", target=100.82, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        self.assertEqual(
            timevalue["monetisability_timevalue_authority"],
            MONETISABILITY_TIMEVALUE_AUTHORITY,
        )
        self.assertEqual(timevalue["monetisability_timevalue_authority"], "ADVISORY_ONLY")

    def test_the_model_and_its_assumptions_are_named_on_every_row(self) -> None:
        for direction in ("CALL", "PUT"):
            with self.subTest(direction=direction):
                _, timevalue = evaluate(
                    direction=direction, target=100.82 if direction == "CALL" else 99.18,
                    ask=0.85, strike=100.0, iv=0.187, dte=8, hold=0,
                )
                self.assertEqual(
                    timevalue["monetisability_timevalue_model"],
                    MONETISABILITY_TIMEVALUE_MODEL,
                )
                self.assertEqual(timevalue["monetisability_timevalue_model"],
                                 "BS_CONST_IV_R0_Q0")
                self.assertEqual(
                    timevalue["monetisability_timevalue_assumptions"],
                    MONETISABILITY_TIMEVALUE_ASSUMPTIONS,
                )
                self.assertIn("held constant", timevalue["monetisability_timevalue_assumptions"])

    def test_it_writes_only_timevalue_fields(self) -> None:
        """It cannot overwrite the intrinsic record it is handed."""
        _, timevalue = evaluate(
            direction="CALL", target=100.82, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        for field in timevalue:
            self.assertIn("timevalue", field, f"{field} is not a timevalue field")

    def test_it_writes_no_permission_field(self) -> None:
        _, timevalue = evaluate(
            direction="CALL", target=100.82, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        for forbidden in ("final_action", "capital_permission", "monetisability_eligible",
                          "monetisability_state", "execution_viability_state"):
            self.assertNotIn(forbidden, timevalue)

    def test_the_intrinsic_state_is_untouched_by_a_disagreeing_timevalue(self) -> None:
        """PNW: the two disagree. The floor must not move."""
        intrinsic, timevalue = evaluate(
            direction="CALL", target=100.82, ask=0.85, strike=100.0,
            iv=0.187, dte=8, hold=0,
        )
        self.assertEqual(intrinsic["monetisability_state"], "NOT_MONETISABLE")
        self.assertEqual(timevalue["monetisability_state_timevalue"], "MONETISABLE")
        self.assertFalse(intrinsic["monetisability_eligible"])


if __name__ == "__main__":
    unittest.main()
