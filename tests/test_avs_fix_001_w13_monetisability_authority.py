"""AVS-FIX-001 W1.3 (QT-D07) — monetisability_authority on every Lab row.

Run 20260905_151448: `monetisability_authority` was 0/294 non-null and
`monetisability_calculation_version` 267/294, while `monetisability_state` was
294/294. Two independent causes:

* The Lab's F29 shape — the field was allow-listed in FINAL_BOOK_FIELDS but had
  no `first(sig, …)` assignment, so a correctly-set producer value was dropped.
* `eod_candidate_engine._eod_selected_contract_monetisability` has five
  early-return paths (FAILED / DATA_MISSING) whose `base` carried neither
  field. Those are the 27 rows.

A blank authority column invites the reader to assume the number is not
advisory. It always is.
"""

from __future__ import annotations

import unittest

import eod_candidate_engine as eod
from contracts.lab_control import (
    FINAL_BOOK_FIELDS,
    MONETISABILITY_AUTHORITY,
    MONETISABILITY_CALCULATION_VERSION,
)
from contracts.selected_contract_economics import evaluate_long_option_monetisability

#: The four states the Lab book showed on 20260905_151448.
MONETISABILITY_STATES = ("MONETISABLE", "LIMITED", "NOT_MONETISABLE", "DATA_MISSING")


class EveryOutcomeCarriesTheAuthority(unittest.TestCase):
    def test_economics_stamps_both_fields_on_every_failure_path(self) -> None:
        cases = {
            "not hydrated": ({}, {"selected_structure_hydration_status": "PENDING"}),
            "not long single": ({}, {
                "selected_structure_hydration_status": "COMPLETE",
                "selected_structure": "VERTICAL",
            }),
            "no direction": ({}, {
                "selected_structure_hydration_status": "COMPLETE",
                "selected_structure": "LONG_SINGLE",
            }),
        }
        for name, (row, hydrated) in cases.items():
            with self.subTest(case=name):
                result = evaluate_long_option_monetisability(row, hydrated)
                self.assertEqual(
                    result["monetisability_authority"], MONETISABILITY_AUTHORITY
                )
                self.assertEqual(
                    result["monetisability_calculation_version"],
                    MONETISABILITY_CALCULATION_VERSION,
                )
                self.assertEqual(result["monetisability_status"], "FAILED")

    def test_eod_early_returns_stamp_both_fields(self) -> None:
        """The five FAILED paths that produced the 27 null rows."""
        cases = {
            "governed direction missing": ({"ticker": "AAA"}, "STRANGLE"),
            "unresolved direction": ({"ticker": "AAA"}, "UNRESOLVED"),
            "selected contract missing": ({"ticker": "AAA"}, "CALL"),
            "quote identity missing": (
                {"ticker": "AAA", "recommended_contract": "AAA260918C00100000"}, "CALL"
            ),
        }
        for name, (row, direction) in cases.items():
            with self.subTest(case=name):
                result = eod._eod_selected_contract_monetisability(row, direction)
                self.assertEqual(
                    result["monetisability_authority"], MONETISABILITY_AUTHORITY, name
                )
                self.assertEqual(
                    result["monetisability_calculation_version"],
                    MONETISABILITY_CALCULATION_VERSION,
                    name,
                )
                self.assertEqual(result["monetisability_status"], "FAILED")

    def test_the_authority_is_never_a_permission(self) -> None:
        result = eod._eod_selected_contract_monetisability({"ticker": "AAA"}, "CALL")
        self.assertIn("ADVISORY", result["monetisability_authority"])
        self.assertFalse(result["monetisability_eligible"])
        self.assertNotIn("final_action", result)
        self.assertNotIn("capital_permission", result)


class LabProjectionIsComplete(unittest.TestCase):
    def test_the_field_is_allow_listed(self) -> None:
        self.assertIn("monetisability_authority", FINAL_BOOK_FIELDS)
        self.assertIn("monetisability_calculation_version", FINAL_BOOK_FIELDS)

    def test_the_field_has_a_first_assignment(self) -> None:
        """The F29 shape: allow-listed but never assigned is the defect."""
        import inspect

        import contracts.lab_control as lab_control

        source = inspect.getsource(lab_control)
        self.assertIn('"monetisability_authority": first(', source)

    def test_all_four_states_project_a_non_null_authority(self) -> None:
        """100% non-null across the four monetisability states."""
        import contracts.lab_control as lab_control

        for state in MONETISABILITY_STATES:
            with self.subTest(state=state):
                signal = {
                    "ticker": "AAA",
                    "monetisability_state": state,
                    "monetisability_status": (
                        "FAILED" if state == "DATA_MISSING" else "COMPLETE"
                    ),
                }
                value = lab_control.first(
                    signal,
                    "monetisability_authority",
                    default=lab_control.MONETISABILITY_AUTHORITY,
                )
                self.assertTrue(value)
                self.assertEqual(value, MONETISABILITY_AUTHORITY)

    def test_a_producer_value_still_wins_over_the_default(self) -> None:
        import contracts.lab_control as lab_control

        value = lab_control.first(
            {"monetisability_authority": "ADVISORY_SCENARIO_ONLY"},
            "monetisability_authority",
            default="UNUSED",
        )
        self.assertEqual(value, "ADVISORY_SCENARIO_ONLY")


if __name__ == "__main__":
    unittest.main()
