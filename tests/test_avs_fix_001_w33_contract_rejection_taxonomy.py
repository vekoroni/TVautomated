"""AVS-FIX-001 W3.3 (THS-001 §3.1, RCA-003 §2) — per-contract rejection taxonomy.

`select_best_contract` returns None the moment a filter stage empties, so the
artefact records that no contract was selected and nothing about why. RCA-003
had to reconstruct the funnel from stored chains to establish that the median
blocked ticker had *exactly one* contract inside its delta band — selection was
not choosing badly, it was being handed a single candidate.

`contracts/contract_rejection.classify_chain` runs the same bands over the same
chain and reports the whole funnel. It selects nothing and changes no gate.
"""

from __future__ import annotations

import unittest

from contracts.contract_rejection import (
    ACCEPTED,
    GATE_ORDER,
    REJECT_DELTA_BAND,
    REJECT_DTE_BAND,
    REJECT_NO_CHAIN,
    REJECT_SPREAD,
    REJECT_STALE_QUOTE,
    REJECT_WRONG_SIDE,
    TAXONOMY_VERSION,
    classify_chain,
    classify_contract,
)

BANDS = dict(dte_min=7, dte_max=21, delta_min=0.40, delta_max=0.60, spread_limit=0.15)


def contract(symbol, *, right="C", dte=14, delta=0.50, spread=0.10, mid=1.20,
             quality="TWO_SIDED", bid=1.15, ask=1.25, flags=()):
    return {
        "symbol": symbol, "right": right, "dte": dte, "delta": delta,
        "spread_pct": spread, "mid": mid, "mark": mid, "bid": bid, "ask": ask,
        "quote_quality": quality, "quality_flags": flags,
    }


class SingleContractClassification(unittest.TestCase):
    def test_a_clean_contract_is_accepted(self) -> None:
        result = classify_contract(contract("OK"), direction="CALL", **BANDS)
        self.assertIsNone(result["gate_failed"])

    def test_each_gate_in_order(self) -> None:
        cases = [
            (contract("W", right="P"), REJECT_WRONG_SIDE),
            (contract("D", dte=40), REJECT_DTE_BAND),
            (contract("X", delta=0.10), REJECT_DELTA_BAND),
            (contract("Q", quality="INVALID"), REJECT_STALE_QUOTE),
            (contract("S", spread=0.30), REJECT_SPREAD),
        ]
        for row, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    classify_contract(row, direction="CALL", **BANDS)["gate_failed"],
                    expected,
                )

    def test_the_first_failing_gate_wins(self) -> None:
        """A contract failing DTE and spread is attributed to DTE only.

        Otherwise the counts double-count and the funnel stops summing.
        """
        row = contract("BOTH", dte=40, spread=0.90)
        self.assertEqual(
            classify_contract(row, direction="CALL", **BANDS)["gate_failed"],
            REJECT_DTE_BAND,
        )

    def test_a_crossed_book_is_a_stale_quote(self) -> None:
        row = contract("CROSS", bid=1.30, ask=1.20)
        self.assertEqual(
            classify_contract(row, direction="CALL", **BANDS)["gate_failed"],
            REJECT_STALE_QUOTE,
        )

    def test_a_zero_mark_is_a_stale_quote(self) -> None:
        row = contract("NOMARK", mid=0.0)
        self.assertEqual(
            classify_contract(row, direction="CALL", **BANDS)["gate_failed"],
            REJECT_STALE_QUOTE,
        )

    def test_negative_delta_puts_use_absolute_value(self) -> None:
        row = contract("P1", right="P", delta=-0.50)
        self.assertIsNone(
            classify_contract(row, direction="PUT", **BANDS)["gate_failed"]
        )

    def test_evidence_is_recorded_for_every_contract(self) -> None:
        result = classify_contract(contract("EV"), direction="CALL", **BANDS)
        self.assertEqual(
            set(result), {"symbol", "dte", "delta", "spread_pct", "mid", "gate_failed"}
        )


class TheFunnelShapeFromTheSpecification(unittest.TestCase):
    """The exact shape AVS-IMP-FIX-001 W3.3 names.

    A ticker with 74 side-correct contracts, 20 in the DTE band, 1 in the delta
    band, and 0 passing spread.
    """

    @staticmethod
    def _chain():
        rows = []
        # 20 in the DTE band; of those, 1 in the delta band, failing spread.
        rows.append(contract("IN-BAND-SPREAD", dte=14, delta=0.50, spread=0.40))
        for index in range(19):
            rows.append(contract(f"DTE-OK-DELTA-BAD-{index}", dte=14, delta=0.10))
        # 54 more side-correct contracts outside the DTE band.
        for index in range(54):
            rows.append(contract(f"DTE-BAD-{index}", dte=45, delta=0.50))
        # 30 puts, which are not side-correct for a CALL thesis.
        for index in range(30):
            rows.append(contract(f"PUT-{index}", right="P"))
        return rows

    def setUp(self) -> None:
        self.result = classify_chain(self._chain(), direction="CALL", **BANDS)

    def test_the_funnel_counts_are_exact(self) -> None:
        funnel = self.result["funnel"]
        self.assertEqual(funnel["chain_rows"], 104)
        self.assertEqual(funnel["side_correct"], 74)
        self.assertEqual(funnel["in_dte_band"], 20)
        self.assertEqual(funnel["in_delta_band"], 1)
        self.assertEqual(funnel["passing_spread"], 0)

    def test_the_primary_reason_is_the_gate_that_reached_zero(self) -> None:
        self.assertEqual(self.result["primary_rejection_reason"], REJECT_SPREAD)

    def test_the_secondary_reason_is_the_next_biggest_eliminator(self) -> None:
        self.assertEqual(self.result["secondary_rejection_reason"], REJECT_DTE_BAND)

    def test_the_near_miss_is_named(self) -> None:
        self.assertEqual(self.result["best_alternative_symbol"], "IN-BAND-SPREAD")
        self.assertEqual(self.result["best_alternative_spread_pct"], 0.40)

    def test_only_side_correct_contracts_are_recorded(self) -> None:
        self.assertEqual(self.result["contracts_tested_count"], 74)
        self.assertEqual(self.result["contracts_side_correct_count"], 74)
        for entry in self.result["contracts_tested"]:
            self.assertNotEqual(entry["gate_failed"], REJECT_WRONG_SIDE)

    def test_the_gate_counts_sum_to_the_chain(self) -> None:
        counts = self.result["gate_counts"]
        self.assertEqual(sum(counts.values()), 104)
        self.assertEqual(counts[REJECT_WRONG_SIDE], 30)
        self.assertEqual(counts[REJECT_DTE_BAND], 54)
        self.assertEqual(counts[REJECT_DELTA_BAND], 19)
        self.assertEqual(counts[REJECT_SPREAD], 1)
        self.assertEqual(counts[ACCEPTED], 0)


class ThreeDirections(unittest.TestCase):
    def test_a_put_thesis_reads_the_put_side(self) -> None:
        chain = [contract("C1"), contract("P1", right="P", delta=-0.50)]
        result = classify_chain(chain, direction="PUT", **BANDS)
        self.assertEqual(result["funnel"]["side_correct"], 1)
        self.assertEqual(result["funnel"]["passing_spread"], 1)

    def test_other_direction_rows_are_not_classified(self) -> None:
        """RG-07: an OTHER row stands down and never selects a contract."""
        for direction in ("STRANGLE", "UNRESOLVED", None, ""):
            with self.subTest(direction=direction):
                result = classify_chain([contract("C1")], direction=direction, **BANDS)
                self.assertEqual(
                    result["primary_rejection_reason"], "NOT_APPLICABLE_NON_DIRECTIONAL"
                )
                self.assertEqual(result["contracts_tested_count"], 0)
                self.assertEqual(result["best_alternative_symbol"], "")


class EdgeCases(unittest.TestCase):
    def test_an_empty_chain_is_named(self) -> None:
        result = classify_chain([], direction="CALL", **BANDS)
        self.assertEqual(result["primary_rejection_reason"], REJECT_NO_CHAIN)
        self.assertEqual(result["contracts_tested_count"], 0)

    def test_a_chain_with_a_passing_contract_has_no_primary_reason(self) -> None:
        result = classify_chain([contract("GOOD")], direction="CALL", **BANDS)
        self.assertEqual(result["primary_rejection_reason"], "")
        self.assertEqual(result["funnel"]["passing_spread"], 1)

    def test_recording_is_capped_but_the_count_is_not(self) -> None:
        chain = [contract(f"C{i}", dte=45) for i in range(500)]
        result = classify_chain(chain, direction="CALL", max_recorded=100, **BANDS)
        self.assertEqual(result["contracts_tested_count"], 500)
        self.assertEqual(len(result["contracts_tested"]), 100)
        self.assertTrue(result["contracts_tested_truncated"])

    def test_the_taxonomy_version_is_stamped(self) -> None:
        result = classify_chain([contract("A")], direction="CALL", **BANDS)
        self.assertEqual(result["taxonomy_version"], TAXONOMY_VERSION)

    def test_every_gate_code_is_in_the_documented_order(self) -> None:
        self.assertEqual(
            GATE_ORDER,
            (REJECT_WRONG_SIDE, REJECT_DTE_BAND, REJECT_DELTA_BAND,
             REJECT_STALE_QUOTE, REJECT_SPREAD),
        )


class InstrumentationOnly(unittest.TestCase):
    """It reports. It selects nothing and grants nothing."""

    def test_no_permission_or_verdict_field_is_produced(self) -> None:
        result = classify_chain([contract("A")], direction="CALL", **BANDS)
        for forbidden in ("final_action", "capital_permission", "options_verdict",
                          "selected_contract_symbol", "monetisability_state"):
            self.assertNotIn(forbidden, result)

    def test_repair_fields_start_unattempted(self) -> None:
        result = classify_chain([contract("A")], direction="CALL", **BANDS)
        self.assertIs(result["repair_attempted"], False)
        self.assertEqual(result["repair_result"], "")

    def test_classification_does_not_mutate_the_chain(self) -> None:
        row = contract("A")
        before = dict(row)
        classify_chain([row], direction="CALL", **BANDS)
        self.assertEqual(row, before)


class SelectorIntegration(unittest.TestCase):
    def test_the_selector_module_exposes_the_taxonomy_pass(self) -> None:
        import sys
        from pathlib import Path

        scripts = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import avshunter_options_intelligence as oi

        self.assertTrue(callable(oi.contract_rejection_taxonomy))
        self.assertTrue(callable(oi.contract_taxonomy_row_fields))
        fields = oi.contract_taxonomy_row_fields(
            classify_chain([contract("A", spread=0.90)], direction="CALL", **BANDS)
        )
        for name in ("contracts_tested_count", "primary_rejection_reason",
                     "best_alternative_symbol", "best_alternative_spread_pct",
                     "repair_attempted", "repair_result"):
            self.assertIn(name, name and fields)
        # The per-contract list is a list; it must not reach a CSV cell.
        self.assertNotIn("contracts_tested", fields)


if __name__ == "__main__":
    unittest.main()
