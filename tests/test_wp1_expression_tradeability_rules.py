"""WP1 business rules for contract selection and thesis targets (ACK 17 Sep 2026, deploy today).

Evidence: Enhancements/expression_forensics/EXPRESSION_FORENSIC_AND_TDD_APPROACH_20260917.md (E1, E2, E6) and
WP1_EXPRESSION_REALITY_DESIGN.md §5 (round-trip cost equals the entry spread; volume and open interest add
little once the spread is known, so they stay ranking evidence, not gates).

  T1 a contract without a two-sided quote (bid > 0 and ask > 0) is not a tradeable expression;
  T2 a contract whose spread (governed definition (ask - bid) / mid) exceeds the horizon spread limit is not
     a tradeable expression — the same authority the terminal gate uses;
  T3 a contract with no measurable spread is not a tradeable expression;
  T4 when two contracts qualify, a tight-spread contract is chosen over one excluded for spread, even off delta;
  T5 when nothing qualifies, no contract is returned and the rejection taxonomy names the reason;
  T6 a thesis target is positive and on the correct side of entry, or absent with a recorded reason
     (the 3R PUT formula must not produce a non-positive target).
"""

from __future__ import annotations

import pandas as pd
import pytest

from contracts.contract_rejection import REJECT_SPREAD
from scripts import avshunter_options_intelligence as oi

from tests.test_wp1_select_best_contract_characterisation import _ctx, _row


def _select(rows, **ctx):
    return oi.select_best_contract(pd.DataFrame(rows), _ctx(**ctx))


def test_t1_contract_without_two_sided_quote_is_not_tradeable():
    one_sided = _row("WPONE261016C00100000", 100.0, bid=None, ask=None, mark=1.50, spread_pct=None,
                     quote_quality="INCOMPLETE", quote_fields_complete=False)
    zero_bid = _row("WPONE261016C00105000", 105.0, bid=0.0, ask=1.20, mark=0.60, spread_pct=None,
                    quote_quality="ONE_SIDED", quote_fields_complete=False)
    assert _select([one_sided]) is None
    assert _select([zero_bid]) is None


def test_t2_contract_above_spread_limit_goes_to_manual_review_not_tradeable():
    """ACK 18 Sep 2026: the horizon informs contract choice, never gates it: nothing inside the limit -> the best contract is shown for manual review with the reason."""
    wide = _row("WPONE261016C00100000", 100.0, bid=1.00, ask=3.00, delta=0.50)       # spread 100% of mid
    selected = _select([wide])
    assert selected["spread_above_limit"] is True
    assert selected["selection_reason"] == "BEST_AVAILABLE_SPREAD_ABOVE_LIMIT_MANUAL_REVIEW"


def test_t3_contract_without_measurable_spread_is_not_tradeable():
    unmeasured = _row("WPONE261016C00100000", 100.0, delta=0.50)
    unmeasured["spread_pct"] = None
    assert _select([unmeasured]) is None


def test_t4_tight_spread_contract_chosen_over_wide_one_even_off_delta():
    wide_on_target_delta = _row("WPONE261016C00100000", 100.0, bid=1.00, ask=2.40, delta=0.50,
                                open_interest=5000, volume=2000)
    tight_off_delta = _row("WPONE261016C00095000", 95.0, bid=4.95, ask=5.00, delta=0.70,
                           open_interest=5000, volume=2000)
    chosen = _select([wide_on_target_delta, tight_off_delta])
    assert chosen is not None and chosen["symbol"] == "WPONE261016C00095000"


def test_t5_no_qualifying_contract_is_reported_by_the_taxonomy():
    wide = _row("WPONE261016C00100000", 100.0, bid=1.00, ask=3.00, delta=0.50)
    chain = pd.DataFrame([wide])
    assert oi.select_best_contract(chain, _ctx())["spread_above_limit"] is True
    taxonomy = oi.contract_rejection_taxonomy(chain, _ctx())
    assert REJECT_SPREAD in str(taxonomy)


@pytest.mark.parametrize(
    "direction, entry, discovery, l1_far, stop_dist, expected, state",
    [
        ("PUT", 10.0, None, None, 4.0, None, "TARGET_3R_NON_POSITIVE"),          # 10 - 12 = -2
        ("PUT", 10.0, None, None, 3.4, None, "TARGET_3R_NON_POSITIVE"),          # 10 - 10.2 = -0.2
        ("PUT", 10.0, None, None, 2.0, 4.0, "TARGET_3R"),
        ("PUT", 10.0, 8.0, None, 2.0, 8.0, "DISCOVERY_TARGET"),
        ("PUT", 10.0, 12.0, 9.0, 2.0, 9.0, "L1_FAR"),                            # discovery on wrong side
        ("CALL", 10.0, None, None, 1.0, 13.0, "TARGET_3R"),
        ("CALL", 10.0, 9.0, None, 1.0, 13.0, "TARGET_3R"),                       # discovery on wrong side
        ("CALL", 10.0, None, None, None, None, "NO_TARGET_SOURCE"),
    ],
)
def test_t6_structural_target_positive_and_on_the_correct_side(direction, entry, discovery, l1_far, stop_dist,
                                                               expected, state):
    target, target_state = oi._governed_structural_target(direction, entry, discovery, l1_far, stop_dist)
    assert target == (pytest.approx(expected) if expected is not None else None)
    assert target_state == state
