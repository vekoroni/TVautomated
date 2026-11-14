"""Crossing scenario, cost interface (AVS-TRADE-001 design v4 section 9; ACK 14 Nov 2026).

Business rules:
- A threshold is compared with the unrounded net return: a return just under +30% that rounds to 0.3000 has not
  crossed; an exact +30% has.
- A wider exit spread lowers only the exit proceeds. The entry ask and both fees are unchanged.
- Existing callers of the cost owner get exactly the numbers they got before.
"""
import math

import pytest

from domain import option_valuation as ov

FEE_OPEN = float(ov.valuation_policy()["fee_usd_per_contract_open"]) / 100.0
FEE_CLOSE = float(ov.valuation_policy()["fee_usd_per_contract_close"]) / 100.0


def _value_for_return(target, bid, ask):
    """The model value that gives exactly `target` net return at this quote."""
    return (1.0 + target) * (ask + FEE_OPEN) + (ask - bid) / 2.0 + FEE_CLOSE


def test_raw_return_is_not_rounded_and_the_rounded_helper_is_its_four_place_wrapper():
    value = _value_for_return(0.29996, 1.90, 2.00)
    raw = ov.net_return_on_premium_raw(value, bid=1.90, ask=2.00)
    assert raw == pytest.approx(0.29996, abs=1e-9) and raw < 0.30
    assert ov.return_on_premium(value, bid=1.90, ask=2.00) == 0.3      # rounds up: must not be used for a threshold
    assert ov.return_on_premium(value, bid=1.90, ask=2.00) == round(raw, 4)


def test_an_exact_threshold_return_is_at_the_threshold():
    raw = ov.net_return_on_premium_raw(_value_for_return(0.30, 1.90, 2.00), bid=1.90, ask=2.00)
    assert raw == pytest.approx(0.30, abs=1e-12)


@pytest.mark.parametrize("value,bid,ask", [(2.75, 1.90, 2.00), (0.40, 0.35, 0.45), (5.0, None, 3.0), (0.0, 0.5, 0.6)])
def test_existing_callers_get_identical_numbers(value, bid, ask):
    half = max(ask - bid, 0.0) / 2.0 if bid is not None else 0.0
    proceeds = max(value - half - FEE_CLOSE, 0.0)
    assert ov.exit_proceeds_usd_per_share(value, bid=bid, ask=ask) == proceeds
    assert ov.return_on_premium(value, bid=bid, ask=ask) == round(proceeds / (ask + FEE_OPEN) - 1.0, 4)


def test_a_wider_exit_spread_lowers_only_the_exit_proceeds():
    base = ov.exit_proceeds_usd_per_share(3.0, bid=1.80, ask=2.00)
    wide = ov.exit_proceeds_usd_per_share(3.0, bid=1.80, ask=2.00, exit_spread_multiple=2.0)
    assert base - wide == pytest.approx(0.10)                      # one more half-spread of 0.10
    assert ov.entry_cost_usd_per_share(2.00) == 2.00 + FEE_OPEN    # entry untouched
    raw_base = ov.net_return_on_premium_raw(3.0, bid=1.80, ask=2.00)
    raw_wide = ov.net_return_on_premium_raw(3.0, bid=1.80, ask=2.00, exit_spread_multiple=2.0)
    assert raw_wide == pytest.approx(raw_base - 0.10 / (2.00 + FEE_OPEN))


@pytest.mark.parametrize("multiple", [-0.5, float("nan"), float("inf")])
def test_an_invalid_spread_multiple_is_refused(multiple):
    with pytest.raises(ValueError):
        ov.net_return_on_premium_raw(3.0, bid=1.80, ask=2.00, exit_spread_multiple=multiple)


@pytest.mark.parametrize("value,bid,ask", [(None, 1.0, 1.1), (float("nan"), 1.0, 1.1), (2.0, 1.2, 1.1), (2.0, -0.1, 1.1),
                                           (2.0, 1.0, 0.0), (-1.0, 1.0, 1.1)])
def test_an_unusable_input_gives_no_return_never_a_number(value, bid, ask):
    assert ov.net_return_on_premium_raw(value, bid=bid, ask=ask) is None
    assert ov.return_on_premium(value, bid=bid, ask=ask) is None
