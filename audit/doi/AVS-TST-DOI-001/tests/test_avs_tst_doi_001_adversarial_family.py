"""AVS-TST-DOI-001 — independent adversarial fixtures for DOI-3 and DOI-4.

Written by the independent tester. It does NOT modify any existing test; it
subclasses the project's own harness so the fixtures are built exactly the way
production builds them, then attacks the guarantees the design makes.

Covers prompt tracks:
  T3.5  null-vs-zero (invariant 7): bid/ask/oi/volume all None must yield a
        data-insufficient monitor state, never a zero-valued economic row.
  T4.1  only the governed side enters the family (invariant 14).
  T4.2  only the six structural exclusions apply (§10) - an OI floor, spread
        cap or delta band would show up as a structural exclusion here.
  T4.3  a chain where EVERY contract is expired or crossed still leaves the
        ticker visible with zero eligible contracts.
  T4.4  a one-sided quote stays monitorable but is never entry-acceptable.
  T4.6  the DTE-outlives-hold check uses the exchange calendar, including a
        hold that spans a holiday weekend (invariant 9).

Run:
  venv\\Scripts\\python.exe -m pytest -q ^
    audit\\doi\\AVS-TST-DOI-001\\tests\\test_avs_tst_doi_001_adversarial_family.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from canonical_data.dynamic_options_family import (  # noqa: E402
    ThesisConditionedContractFamilyGenerator,
)
from canonical_data.session_clock import xnys_sessions_between  # noqa: E402
from domain.contract_family_generation import (  # noqa: E402
    FamilyCandidateState,
    StructuralExclusionReason,
)

from test_dynamic_options_contract_family import (  # noqa: E402
    CUTOFF,
    RUN_ID,
    DynamicOptionsContractFamilyTests,
)

# The six structural exclusions the design permits (§10). NEGATIVE_QUOTE and
# CROSSED_QUOTE are the implementation's split of design exclusion 5;
# IDENTITY_FIELD_MISMATCH and DUPLICATE_CONTRACT_AMBIGUOUS are identity-
# integrity variants of design exclusions 3 and 6.
PERMITTED_EXCLUSIONS = {
    StructuralExclusionReason.WRONG_OPTION_SIDE,
    StructuralExclusionReason.EXPIRED_CONTRACT,
    StructuralExclusionReason.INVALID_OCC_IDENTITY,
    StructuralExclusionReason.INSUFFICIENT_SESSION_RUNWAY,
    StructuralExclusionReason.NEGATIVE_QUOTE,
    StructuralExclusionReason.CROSSED_QUOTE,
    StructuralExclusionReason.IMPOSSIBLE_STRIKE_OR_EXPIRY,
    StructuralExclusionReason.IDENTITY_FIELD_MISMATCH,
    StructuralExclusionReason.DUPLICATE_CONTRACT_AMBIGUOUS,
}


class AdversarialFamilyTests(DynamicOptionsContractFamilyTests):
    """Reuses setUp/_thesis/_register/_observation/_base from the project harness."""

    # The inherited test methods run too; that is deliberate - it proves the
    # harness behaves identically under this subclass.

    def _generate(self, rows, direction="CALL", **kwargs):
        thesis = self._thesis(direction)
        observation = self._observation(rows)
        generator = ThesisConditionedContractFamilyGenerator(self.store, **kwargs)
        return generator.generate(
            thesis=thesis,
            observation=observation,
            run_id=RUN_ID,
            current_spot=100.0,
            evaluation_cutoff_utc=CUTOFF,
        )

    # ---------------------------------------------------------------- T3.5 --
    def test_t3_5_all_null_quote_is_data_insufficient_not_economic_zero(self) -> None:
        """bid/ask/oi/volume all None must never become 0.0 anywhere."""
        rows = [
            self._base("CALL", 105.0, bid=None, ask=None, volume=None, open_interest=None),
            self._base("CALL", 110.0, bid=None, ask=None, volume=None, open_interest=None),
        ]
        generated = self._generate(rows)

        self.assertEqual(len(generated.taxonomy), 2)
        for audit in generated.taxonomy:
            with self.subTest(symbol=audit.contract_symbol):
                # Not structurally excluded - a missing quote is not impossible.
                self.assertNotEqual(audit.state, FamilyCandidateState.EXCLUDED_STRUCTURAL)
                self.assertEqual(audit.state, FamilyCandidateState.MONITOR_NO_QUOTE)
                # THE INVARIANT: nulls stay null.
                self.assertIsNone(audit.bid, "bid was coerced away from None")
                self.assertIsNone(audit.ask, "ask was coerced away from None")
                self.assertIsNone(audit.volume, "volume was coerced away from None")
                self.assertIsNone(
                    audit.open_interest, "open_interest was coerced away from None"
                )
                self.assertNotEqual(audit.bid, 0.0)
                self.assertNotEqual(audit.open_interest, 0.0)
                # And the reason is disclosed rather than silently dropped.
                self.assertIn("CURRENT_QUOTE_MISSING", audit.monitor_reasons)
                self.assertIn("OPEN_INTEREST_MISSING", audit.monitor_reasons)
                self.assertIn("VOLUME_MISSING", audit.monitor_reasons)

        # The ticker survives with the family intact.
        self.assertEqual(generated.summary.source_observations, 2)
        self.assertEqual(generated.summary.family_candidates, 2)
        self.assertEqual(generated.summary.structural_exclusions, 0)

    # ---------------------------------------------------------------- T4.1 --
    def test_t4_1_put_thesis_admits_no_call_contract(self) -> None:
        rows = [
            self._base("PUT", 95.0),
            self._base("PUT", 90.0),
            self._base("CALL", 105.0),   # wrong side - must be excluded
            self._base("CALL", 110.0),   # wrong side - must be excluded
        ]
        generated = self._generate(rows, direction="PUT")

        admitted_sides = {
            audit.option_side for audit in generated.taxonomy if audit.is_family_candidate
        }
        self.assertEqual(admitted_sides, {"PUT"}, "a CALL entered a PUT family")

        wrong_side = [
            audit for audit in generated.taxonomy
            if StructuralExclusionReason.WRONG_OPTION_SIDE in audit.structural_exclusions
        ]
        self.assertEqual(len(wrong_side), 2)
        # Excluded observations remain in the audit with their reason (§10).
        for audit in wrong_side:
            self.assertFalse(audit.display_eligible)
            self.assertEqual(audit.state, FamilyCandidateState.EXCLUDED_STRUCTURAL)
        self.assertEqual(generated.summary.direction, "PUT")

    def test_t4_1_call_thesis_admits_no_put_contract(self) -> None:
        rows = [
            self._base("CALL", 105.0),
            self._base("PUT", 95.0),
        ]
        generated = self._generate(rows, direction="CALL")
        admitted_sides = {
            audit.option_side for audit in generated.taxonomy if audit.is_family_candidate
        }
        self.assertEqual(admitted_sides, {"CALL"}, "a PUT entered a CALL family")

    # ---------------------------------------------------------------- T4.2 --
    def test_t4_2_low_oi_zero_volume_wide_spread_are_never_structural_exclusions(self) -> None:
        """The specific reversal of the delta 0.40-0.60 preselection."""
        rows = [
            self._base("CALL", 105.0, open_interest=0, volume=0),        # dead
            self._base("CALL", 110.0, open_interest=1, volume=0),        # near dead
            self._base("CALL", 115.0, bid=0.05, ask=9.95),               # 99% spread
            self._base("CALL", 120.0, open_interest=None, volume=None),  # unknown
            self._base("CALL", 125.0, bid=0.01, ask=0.02),               # deep OTM penny
        ]
        generated = self._generate(rows)

        self.assertEqual(
            generated.summary.structural_exclusions, 0,
            "a non-structural condition produced a structural exclusion",
        )
        self.assertEqual(generated.summary.family_candidates, 5)
        for audit in generated.taxonomy:
            for reason in audit.structural_exclusions:
                self.assertIn(reason, PERMITTED_EXCLUSIONS)
        # And they are counted as retentions, per §18.
        self.assertGreaterEqual(generated.summary.retained_zero_volume, 2)
        self.assertGreaterEqual(generated.summary.retained_low_open_interest, 2)

    # ---------------------------------------------------------------- T4.3 --
    def test_t4_3_wholly_unusable_chain_leaves_ticker_visible_with_zero_eligible(self) -> None:
        rows = [
            # every contract expired
            self._base("CALL", 105.0, expiration_date="2026-01-16",
                       symbol="ABC260116C00105000"),
            self._base("CALL", 110.0, expiration_date="2026-01-16",
                       symbol="ABC260116C00110000"),
            # and one crossed quote
            self._base("CALL", 115.0, bid=5.0, ask=1.0),
        ]
        generated = self._generate(rows)

        self.assertEqual(generated.summary.source_observations, 3)
        self.assertEqual(
            generated.summary.family_candidates, 0,
            "an unusable contract was admitted",
        )
        self.assertEqual(generated.summary.structural_exclusions, 3)
        # THE POINT: the audit still holds all three, with reasons.
        self.assertEqual(len(generated.taxonomy), 3)
        for audit in generated.taxonomy:
            self.assertTrue(audit.structural_exclusions)
            for reason in audit.structural_exclusions:
                self.assertIn(reason, PERMITTED_EXCLUSIONS)
        # The family row itself is persisted - the ticker did not vanish.
        self.assertIsNotNone(generated.family)
        self.assertEqual(generated.display_symbols, ())

    # ---------------------------------------------------------------- T4.4 --
    def test_t4_4_one_sided_quote_is_monitorable_but_never_entry_acceptable(self) -> None:
        rows = [
            self._base("CALL", 105.0, bid=1.0, ask=None),   # bid only
            self._base("CALL", 110.0, bid=None, ask=1.4),   # ask only
            self._base("CALL", 115.0),                      # two-sided control
        ]
        generated = self._generate(rows)

        one_sided = [
            audit for audit in generated.taxonomy
            if audit.state == FamilyCandidateState.MONITOR_ONE_SIDED
        ]
        self.assertEqual(len(one_sided), 2)
        for audit in one_sided:
            self.assertTrue(audit.is_family_candidate, "one-sided quote was discarded")
            self.assertIn("ONE_SIDED_QUOTE", audit.monitor_reasons)
            self.assertNotEqual(audit.state, FamilyCandidateState.ELIGIBLE_TWO_SIDED)
            # A one-sided quote must not be presented as presently executable.
            self.assertNotEqual(audit.quote_state, "TWO_SIDED")

        two_sided = [
            audit for audit in generated.taxonomy
            if audit.state == FamilyCandidateState.ELIGIBLE_TWO_SIDED
        ]
        self.assertEqual(len(two_sided), 1)

    # ---------------------------------------------------------------- T4.6 --
    def test_t4_6_session_runway_uses_exchange_calendar_over_a_holiday(self) -> None:
        """A 10-session hold across Thanksgiving must not be 10 calendar days."""
        # 2026-11-20 (Fri) forward. US Thanksgiving 2026 falls on 2026-11-26.
        start = date(2026, 11, 20)
        ten_calendar_days = date(2026, 11, 30)
        sessions_in_that_window = xnys_sessions_between(start, ten_calendar_days)

        self.assertLess(
            sessions_in_that_window, 10,
            "10 calendar days across Thanksgiving must contain fewer than 10 sessions; "
            "if this is 10 the calendar is being ignored",
        )
        # Thanksgiving itself is not a session.
        self.assertEqual(xnys_sessions_between(date(2026, 11, 25), date(2026, 11, 27)), 1)
        # Christmas Day 2026 (Friday) is not a session.
        self.assertEqual(xnys_sessions_between(date(2026, 12, 24), date(2026, 12, 28)), 1)

    def test_t4_6_insufficient_runway_is_computed_in_sessions_not_days(self) -> None:
        """A contract expiring inside hold+buffer must be excluded on sessions."""
        # thesis planned_hold is set by the harness; buffer defaults to 8.
        near_expiry = self._base(
            "CALL", 105.0, expiration_date="2026-09-18",
            symbol="ABC260918C00105000",
        )
        far_expiry = self._base(
            "CALL", 110.0, expiration_date="2027-01-15",
            symbol="ABC270115C00110000",
        )
        generated = self._generate([near_expiry, far_expiry])

        by_symbol = {audit.contract_symbol: audit for audit in generated.taxonomy}
        near = [a for a in generated.taxonomy if a.expiry == date(2026, 9, 18)][0]
        far = [a for a in generated.taxonomy if a.expiry == date(2027, 1, 15)][0]

        self.assertIn(
            StructuralExclusionReason.INSUFFICIENT_SESSION_RUNWAY,
            near.structural_exclusions,
        )
        self.assertEqual(far.structural_exclusions, ())
        # remaining_sessions must be a session count, not a calendar-day count.
        self.assertEqual(
            near.remaining_sessions,
            xnys_sessions_between(CUTOFF.date(), date(2026, 9, 18)),
        )
        self.assertLess(
            near.remaining_sessions,
            (date(2026, 9, 18) - CUTOFF.date()).days,
            "remaining_sessions equals calendar days - the calendar is not being used",
        )
        self.assertGreaterEqual(near.required_sessions, 1)
        self.assertTrue(by_symbol)


if __name__ == "__main__":
    import unittest

    unittest.main()
