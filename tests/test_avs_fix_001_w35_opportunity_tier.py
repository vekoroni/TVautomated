"""AVS-FIX-001 W3.5 (THS-001 §4) — derived opportunity tier.

A tier describes the quality and completeness of the evidence for an
opportunity, so the Lab can order what it already has. It is DERIVED, never
scored: every boundary traces to a governed column.

**The authority tests at the bottom are the ones that matter.** A tier orders
the book; it grants no capital. `final_action` must be identical with and
without tiering, for every fixture and every tier.
"""

from __future__ import annotations

import unittest

from contracts.opportunity_tier import (
    ARMED,
    BLOCK,
    TIER_1,
    TIER_2,
    TIER_3,
    TIER_POLICY_VERSION,
    TIER_SORT_ORDER,
    WATCH,
    derive_tier,
    tier_fields,
    tier_sort_key,
)


def row(direction="CALL", **overrides):
    """A Tier-1 row: everything present and strong. Overrides weaken it."""
    invalidation, target = (95.0, 115.0) if direction == "CALL" else (115.0, 95.0)
    base = {
        "canonical_direction": direction,
        "governed_direction_record_sha256": "a" * 64,
        "invalidation_state": "AVAILABLE",
        "invalidation_price": invalidation,
        "structural_target": target,
        "rr_underlying": 3.0,
        "monetisability_state": "MONETISABLE",
        "monetisability_state_timevalue": "MONETISABLE",
        "spread_pct": 0.10,
        "time_horizon": "1_5d",
        "contract_dte": 14.0,
        "planned_hold_sessions": 5.0,
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "trigger_state": "TRIGGER_READY",
        "contract_repair_status": "CONTRACT_OK",
        "final_action": "MANUAL_REVIEW",
    }
    base.update(overrides)
    return base


class Tier1(unittest.TestCase):
    def test_call_and_put(self) -> None:
        for direction in ("CALL", "PUT"):
            with self.subTest(direction=direction):
                tier, reason = derive_tier(row(direction))
                self.assertEqual(tier, TIER_1)
                self.assertEqual(reason, "ALL_GOVERNED_EVIDENCE_PRESENT_AND_STRONG")


class Tier2SingleNamedWeakness(unittest.TestCase):
    CASES = {
        "R:R between 1.5 and 2.0": ({"rr_underlying": 1.7}, "RR_1.70_BELOW_2.0"),
        "LIMITED not MONETISABLE": (
            {"monetisability_state": "LIMITED"},
            "MONETISABILITY_LIMITED_NOT_MONETISABLE",
        ),
        "monetisable on time value only": (
            {"monetisability_state": "NOT_MONETISABLE",
             "monetisability_state_timevalue": "MONETISABLE"},
            "MONETISABLE_ON_TIMEVALUE_ONLY",
        ),
        "spread above the horizon band": (
            {"spread_pct": 0.20}, "SPREAD_20.00%_ABOVE_HORIZON_BAND",
        ),
        "trigger not ready": (
            {"trigger_state": "REPAIR_AT_OPEN"}, "TRIGGER_REPAIR_AT_OPEN",
        ),
        "DTE below twice the hold": (
            {"contract_dte": 8.0}, "DTE_8_BELOW_2X_HOLD_10",
        ),
    }

    def test_each_weakness_yields_tier_2_and_names_itself(self) -> None:
        for label, (overrides, expected_reason) in self.CASES.items():
            for direction in ("CALL", "PUT"):
                with self.subTest(case=label, direction=direction):
                    tier, reason = derive_tier(row(direction, **overrides))
                    self.assertEqual(tier, TIER_2, label)
                    self.assertEqual(reason, expected_reason)

    def test_the_reason_names_the_single_weakness_not_a_score(self) -> None:
        _, reason = derive_tier(row(rr_underlying=1.7))
        self.assertNotIn(";", reason)


class Tier3TwoOrMoreWeaknesses(unittest.TestCase):
    def test_two_weaknesses_yield_tier_3(self) -> None:
        for direction in ("CALL", "PUT"):
            with self.subTest(direction=direction):
                tier, reason = derive_tier(
                    row(direction, rr_underlying=1.7, spread_pct=0.20)
                )
                self.assertEqual(tier, TIER_3)
                self.assertIn("RR_1.70_BELOW_2.0", reason)
                self.assertIn("ABOVE_HORIZON_BAND", reason)

    def test_all_weaknesses_are_named(self) -> None:
        _, reason = derive_tier(
            row(rr_underlying=1.7, spread_pct=0.20, trigger_state="REPAIR_AT_OPEN")
        )
        self.assertEqual(len(reason.split(";")), 3)


class ArmedNeedsANamedPromoter(unittest.TestCase):
    NOT_MONETISABLE = {
        "monetisability_state": "NOT_MONETISABLE",
        "monetisability_state_timevalue": "NOT_MONETISABLE",
    }

    def test_an_alternative_contract_promotes_to_armed(self) -> None:
        for direction in ("CALL", "PUT"):
            with self.subTest(direction=direction):
                tier, reason = derive_tier(row(
                    direction, **self.NOT_MONETISABLE,
                    best_alternative_symbol="AAA260918C00100000",
                    best_alternative_spread_pct=0.17,
                ))
                self.assertEqual(tier, ARMED)
                self.assertIn("ALTERNATIVE_CONTRACT_AVAILABLE", reason)
                self.assertIn("AAA260918C00100000", reason)

    def test_a_repair_route_promotes_to_armed(self) -> None:
        tier, reason = derive_tier(row(
            **self.NOT_MONETISABLE, contract_repair_status="CONTRACT_REPAIR_REQUIRED"
        ))
        self.assertEqual(tier, ARMED)
        self.assertEqual(reason, "CONTRACT_REPAIR_ROUTE_AVAILABLE")

    def test_elevated_iv_promotes_to_armed(self) -> None:
        tier, reason = derive_tier(row(**self.NOT_MONETISABLE, iv_rank=82))
        self.assertEqual(tier, ARMED)
        self.assertIn("IV_RANK_82", reason)

    def test_without_a_promoter_it_is_watch_not_armed(self) -> None:
        """THS-001 §4: ARMED without a named promoter is a bin, not a state."""
        tier, reason = derive_tier(row(**self.NOT_MONETISABLE))
        self.assertEqual(tier, WATCH)
        self.assertEqual(reason, "EQUITY_VALID_OPTIONS_NOT_MONETISABLE_NO_PROMOTER")

    def test_data_missing_without_a_promoter_is_watch(self) -> None:
        tier, reason = derive_tier(row(
            monetisability_state="DATA_MISSING",
            monetisability_state_timevalue="NOT_EVALUATED",
        ))
        self.assertEqual(tier, WATCH)
        self.assertEqual(reason, "DATA_MISSING_AWAITING_RE_RESOLUTION")


class BlockIsTheHardVetoListUnchanged(unittest.TestCase):
    CASES = {
        "direction unresolved": ({"canonical_direction": "UNRESOLVED"},
                                 "DIRECTION_NOT_RESOLVED"),
        "strangle": ({"canonical_direction": "STRANGLE"}, "DIRECTION_NOT_RESOLVED"),
        "no direction": ({"canonical_direction": None}, "DIRECTION_NOT_RESOLVED"),
        "no lineage hash": ({"governed_direction_record_sha256": ""},
                            "DIRECTION_LINEAGE_HASH_MISSING"),
        "invalidation not available": ({"invalidation_state": "MISSING"},
                                       "GOVERNED_INVALIDATION_NOT_AVAILABLE"),
        "invalidation absent": ({"invalidation_price": None},
                                "GOVERNED_INVALIDATION_MISSING"),
        "target unresolved": ({"structural_target": None},
                              "STRUCTURAL_TARGET_UNRESOLVED"),
        "target zero": ({"structural_target": 0.0}, "STRUCTURAL_TARGET_UNRESOLVED"),
        "pathological spread": ({"execution_viability_state": "PATHOLOGICAL_SPREAD"},
                                "EXECUTION_VIABILITY_PATHOLOGICAL_SPREAD"),
        "spread above ceiling": ({"spread_pct": 0.60},
                                 "SPREAD_ABOVE_REVIEWABLE_CEILING"),
    }

    def test_each_veto_blocks_and_names_itself(self) -> None:
        for label, (overrides, expected) in self.CASES.items():
            with self.subTest(case=label):
                tier, reason = derive_tier(row(**overrides))
                self.assertEqual(tier, BLOCK, label)
                self.assertEqual(reason, expected)

    def test_a_target_on_the_wrong_side_blocks(self) -> None:
        # CALL with a target below its invalidation.
        tier, reason = derive_tier(row("CALL", structural_target=90.0))
        self.assertEqual(tier, BLOCK)
        self.assertEqual(reason, "TARGET_ON_WRONG_SIDE_OF_INVALIDATION")
        tier, reason = derive_tier(row("PUT", structural_target=120.0))
        self.assertEqual(tier, BLOCK)
        self.assertEqual(reason, "TARGET_ON_WRONG_SIDE_OF_INVALIDATION")

    def test_a_monetisable_row_cannot_escape_a_hard_veto(self) -> None:
        tier, _ = derive_tier(row(
            monetisability_state="MONETISABLE", invalidation_state="MISSING"
        ))
        self.assertEqual(tier, BLOCK)


class OtherDirectionRows(unittest.TestCase):
    """RG-07: OTHER rows stand down. They can only ever be BLOCK."""

    def test_every_other_direction_is_block(self) -> None:
        for direction in ("STRANGLE", "UNRESOLVED", None, "", "OTHER"):
            with self.subTest(direction=direction):
                tier, reason = derive_tier(row(canonical_direction=direction))
                self.assertEqual(tier, BLOCK)
                self.assertEqual(reason, "DIRECTION_NOT_RESOLVED")


class Ordering(unittest.TestCase):
    def test_the_lab_sorts_by_tier_then_risk_reward(self) -> None:
        rows = [
            {"opportunity_tier": TIER_2, "rr_underlying": 5.0},
            {"opportunity_tier": TIER_1, "rr_underlying": 2.1},
            {"opportunity_tier": TIER_1, "rr_underlying": 4.0},
            {"opportunity_tier": BLOCK, "rr_underlying": 9.0},
            {"opportunity_tier": ARMED, "rr_underlying": 1.0},
        ]
        ordered = sorted(rows, key=tier_sort_key)
        self.assertEqual(
            [(r["opportunity_tier"], r["rr_underlying"]) for r in ordered],
            [(TIER_1, 4.0), (TIER_1, 2.1), (TIER_2, 5.0), (ARMED, 1.0), (BLOCK, 9.0)],
        )

    def test_the_sort_order_is_the_documented_one(self) -> None:
        self.assertEqual(TIER_SORT_ORDER, (TIER_1, TIER_2, TIER_3, ARMED, WATCH, BLOCK))


class AuthorityIsUnchanged(unittest.TestCase):
    """The tests that matter most. A tier grants nothing and removes nothing."""

    FIXTURES = [
        ("tier 1", {}),
        ("tier 2", {"rr_underlying": 1.7}),
        ("tier 3", {"rr_underlying": 1.7, "spread_pct": 0.20}),
        ("armed", {"monetisability_state": "NOT_MONETISABLE",
                   "monetisability_state_timevalue": "NOT_MONETISABLE",
                   "best_alternative_symbol": "AAA"}),
        ("watch", {"monetisability_state": "NOT_MONETISABLE",
                   "monetisability_state_timevalue": "NOT_MONETISABLE"}),
        ("block", {"invalidation_state": "MISSING"}),
    ]

    def test_final_action_is_unchanged_for_every_tier(self) -> None:
        for label, overrides in self.FIXTURES:
            for action in ("MANUAL_REVIEW", "BUY_SMALL", "STAND_DOWN", ""):
                with self.subTest(case=label, action=action):
                    fixture = row(final_action=action, **overrides)
                    before = dict(fixture)
                    fields = tier_fields(fixture)
                    self.assertEqual(fixture, before, "derive_tier mutated the row")
                    self.assertNotIn("final_action", fields)
                    self.assertEqual(fixture["final_action"], action)

    def test_it_writes_no_permission_field(self) -> None:
        fields = tier_fields(row())
        self.assertEqual(
            set(fields),
            {"opportunity_tier", "opportunity_tier_reason",
             "opportunity_tier_authority", "opportunity_tier_policy_version"},
        )

    def test_it_declares_itself_advisory_on_every_row(self) -> None:
        for label, overrides in self.FIXTURES:
            with self.subTest(case=label):
                fields = tier_fields(row(**overrides))
                self.assertEqual(fields["opportunity_tier_authority"], "ADVISORY_ONLY")
                self.assertEqual(
                    fields["opportunity_tier_policy_version"], TIER_POLICY_VERSION
                )

    def test_a_monetisable_evening_row_keeps_manual_review(self) -> None:
        """The case AVS-IMP-FIX-001 names: tier assigned, action untouched."""
        fixture = row(monetisability_state="MONETISABLE", final_action="MANUAL_REVIEW")
        fields = tier_fields(fixture)
        self.assertEqual(fields["opportunity_tier"], TIER_1)
        self.assertEqual(fixture["final_action"], "MANUAL_REVIEW")

    def test_tier_is_a_pure_function_of_the_row(self) -> None:
        fixture = row()
        self.assertEqual(derive_tier(fixture), derive_tier(dict(fixture)))


class LabIntegration(unittest.TestCase):
    def test_the_columns_are_allow_listed(self) -> None:
        from contracts.lab_control import FINAL_BOOK_FIELDS

        for field in ("opportunity_tier", "opportunity_tier_reason",
                      "opportunity_tier_authority", "opportunity_tier_policy_version"):
            self.assertIn(field, FINAL_BOOK_FIELDS, field)

    def test_the_lab_derivation_never_raises(self) -> None:
        from contracts.lab_control import _derive_opportunity_tier

        result = _derive_opportunity_tier({})
        self.assertIn("opportunity_tier", result)
        self.assertEqual(result["opportunity_tier_authority"], "ADVISORY_ONLY")


if __name__ == "__main__":
    unittest.main()


class UnevaluableCriteriaAreWeaknessesNotSilence(unittest.TestCase):
    """An absent column must not promote a row by leaving a check unrun.

    On the pre-AVS-FIX-001 book of run 20260905_151448 `trigger_state`,
    `contract_dte`, `planned_hold_sessions` and `monetisability_state_timevalue`
    were all absent. Without this rule 115 of 294 rows read TIER_1, against
    THS-001 §4's own expectation of "tens, not hundreds".
    """

    CASES = {
        "risk reward": ("rr_underlying", "UNEVALUABLE_RISK_REWARD"),
        "time value": ("monetisability_state_timevalue",
                       "UNEVALUABLE_TIMEVALUE_MONETISABILITY"),
        "spread": ("spread_pct", "UNEVALUABLE_SPREAD"),
        "trigger": ("trigger_state", "UNEVALUABLE_TRIGGER_STATE"),
        "dte vs hold": ("contract_dte", "UNEVALUABLE_DTE_VS_HOLD"),
        "hold": ("planned_hold_sessions", "UNEVALUABLE_DTE_VS_HOLD"),
    }

    def test_each_absent_criterion_is_named_as_a_weakness(self) -> None:
        for label, (column, expected) in self.CASES.items():
            with self.subTest(case=label):
                fixture = row()
                fixture.pop(column, None)
                tier, reason = derive_tier(fixture)
                self.assertIn(tier, (TIER_2, TIER_3), label)
                self.assertIn(expected, reason, label)

    def test_a_row_missing_several_criteria_is_tier_3_not_tier_1(self) -> None:
        fixture = row()
        for column in ("trigger_state", "contract_dte", "monetisability_state_timevalue"):
            fixture.pop(column, None)
        tier, reason = derive_tier(fixture)
        self.assertEqual(tier, TIER_3)
        self.assertIn("UNEVALUABLE_TRIGGER_STATE", reason)
        self.assertIn("UNEVALUABLE_DTE_VS_HOLD", reason)
        self.assertIn("UNEVALUABLE_TIMEVALUE_MONETISABILITY", reason)

    def test_tier_1_still_requires_every_criterion_to_be_present(self) -> None:
        tier, _ = derive_tier(row())
        self.assertEqual(tier, TIER_1)
