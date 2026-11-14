"""Lane B's liquidity tier now comes from the shared owner (AVS-TRADE-001 design v4 section 8; ACK 14 Nov 2026).

Business rule: exactly one Lane B output changes. A crossed quote (bid above ask) is graded C with the reason
CROSSED_QUOTE; before, it was graded on its negative spread and could come out A. Every other quote gets the same
tier, the same reason text and the same spread figure as before, including the boundary tolerance and any settings
the caller passes.
"""
import itertools
import sys
from pathlib import Path

import pytest

WORK = Path(__file__).resolve().parents[1] / "data" / "scratch" / "workaround"
sys.path.insert(0, str(WORK))
import build_lab_handoff as blh  # noqa: E402


def legacy_tier(bid, ask, oi, settings=blh.DEFAULTS):
    """The function exactly as it was on 4010d4d (characterisation oracle)."""
    bid, ask, oi = blh.num(bid), blh.num(ask), blh.num(oi)
    if ask is None or ask <= 0:
        return "C", "NO_ASK", None
    if bid is None or bid <= 0:
        return "C", "NO_BID", None
    mid = (bid + ask) / 2.0
    width = ask - bid
    pct = width / mid * 100.0
    if oi is None:
        return "C", "OI_NOT_RECORDED", pct
    if oi < settings["tier_min_oi"]:
        return "C", f"OI_{blh.g(oi)}_UNDER_{blh.g(settings['tier_min_oi'])}", pct
    if pct > settings["tier_b_spread_pct"] + 1e-9:
        return "C", f"SPREAD_{pct:.1f}PCT_OVER_{blh.g(settings['tier_b_spread_pct'])}", pct
    if pct > settings["tier_a_spread_pct"] + 1e-9:
        return "B", f"SPREAD_{pct:.1f}PCT", pct
    if mid < settings["tier_low_premium"] and width > settings["tier_low_premium_max_width"] + 1e-9:
        return "B", f"PREMIUM_UNDER_{blh.g(settings['tier_low_premium'])}_SPREAD_{width:.2f}_WIDE", pct
    return "A", f"SPREAD_{pct:.1f}PCT", pct


BIDS = [None, "", "abc", True, 0, 0.0, -1, 0.05, 0.95, 1.0, 1.2, 1.36, 1.9, 2.0, 3.0, 3.8, "3.8", 10.0, float("nan")]
ASKS = [None, "", 0, -1, 0.5, 1.0, 1.1, 1.3, 1.32, 1.5, 2.1, 2.2, 2.3, 4.0, "4.0", 12.0, float("inf")]
OIS = [None, "", 0, 50, 99, 100, 817, "817"]


def test_every_non_crossed_quote_is_graded_exactly_as_before():
    checked = 0
    for bid, ask, oi in itertools.product(BIDS, ASKS, OIS):
        b, a = blh.num(bid), blh.num(ask)
        if b is not None and a is not None and b > 0 and a > 0 and b > a:
            continue                                            # crossed: the one intended change, tested below
        assert blh.liquidity_tier(bid, ask, oi) == legacy_tier(bid, ask, oi), (bid, ask, oi)
        checked += 1
    assert checked > 1500


def test_a_crossed_quote_is_graded_c_with_its_reason_and_no_spread_figure():
    assert legacy_tier(2.20, 2.00, 817)[0] == "A"               # the defect: a negative spread passed every test
    assert blh.liquidity_tier(2.20, 2.00, 817) == ("C", "CROSSED_QUOTE", None)
    assert blh.liquidity_tier(2.20, 2.00, None) == ("C", "CROSSED_QUOTE", None)


def test_the_callers_settings_and_the_boundary_tolerance_are_honoured():
    strict = {**blh.DEFAULTS, "tier_a_spread_pct": 3.0, "tier_min_oi": 1000}
    for bid, ask, oi in [(2.0, 2.1, 817), (2.0, 2.1, 5000), (1.9, 2.1, 5000), (1.8, 2.2, 5000)]:
        assert blh.liquidity_tier(bid, ask, oi, strict) == legacy_tier(bid, ask, oi, strict)
    assert blh.liquidity_tier(1.90, 2.10, 817)[0] == "A"        # exactly 10% of mid
    assert blh.liquidity_tier(1.80, 2.20, 817)[0] == "B"        # exactly 20% of mid


def test_lane_bs_default_thresholds_are_the_governed_ones():
    from domain.option_contract_liquidity import liquidity_tier_settings
    governed = liquidity_tier_settings()
    assert (blh.DEFAULTS["tier_a_spread_pct"], blh.DEFAULTS["tier_b_spread_pct"], blh.DEFAULTS["tier_min_oi"],
            blh.DEFAULTS["tier_low_premium"], blh.DEFAULTS["tier_low_premium_max_width"]) == (
        governed["a_spread_pct"], governed["b_spread_pct"], governed["min_oi"], governed["low_premium"],
        governed["low_premium_max_width"])
