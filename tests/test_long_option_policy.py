from __future__ import annotations

import contracts.lab_control as lab_control
import morning_gate
from canonical_data.marketdata_response import _quote as normalise_marketdata_quote
from contracts.long_option_policy import (
    LONG_OPTION_ALLOWED_INSTRUMENTS,
    LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT,
    LONG_OPTION_EXECUTION_POLICY,
    LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT,
    quote_spread_fraction,
)


def test_morning_and_lab_share_one_spread_authority() -> None:
    assert (
        morning_gate.LONG_OPTION_EXECUTION_POLICY
        is LONG_OPTION_EXECUTION_POLICY
    )
    assert (
        lab_control.LAB_EXECUTABLE_SPREAD_MAX_PCT
        == LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT
        == 18.0
    )
    assert (
        lab_control.LAB_ABSOLUTE_SPREAD_MAX_PCT
        == LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT
        == 25.0
    )


def test_lab_instruments_come_from_governed_long_option_policy() -> None:
    assert lab_control.LAB_EXECUTABLE_INSTRUMENTS is LONG_OPTION_ALLOWED_INSTRUMENTS
    assert LONG_OPTION_ALLOWED_INSTRUMENTS == {"LONG_CALL", "LONG_PUT"}


def test_all_quote_normalisers_use_local_mid_denominator() -> None:
    expected = quote_spread_fraction(4.0, 6.0)
    assert expected == 0.4

    # A provider-supplied mid is evidence, not spread authority.  The
    # canonical normaliser must derive its local midpoint from bid and ask.
    _, _, normalised_mid, canonical_spread, quality, _ = normalise_marketdata_quote(
        4.0, 6.0, 99.0
    )
    assert quality == "TWO_SIDED"
    assert normalised_mid == 5.0
    assert canonical_spread == expected
