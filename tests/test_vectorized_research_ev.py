"""The production-scale research accelerator must reproduce the reference pricer."""

from domain.option_path_valuation import (
    LongOptionQuote, PathSession, PhysicalPathSet, WeightedPath,
    value_long_option_paths,
)
from domain.research_path_baseline import RelativePath
from domain.vectorized_research_ev import value_research_contract


def _compare(right, target, stop, iv_multiplier, commission, slippage):
    paths = (
        RelativePath("a", "2026-01-01", "2026-01-02", ((1.0, 1.08, .99, 1.04), (1.04, 1.12, 1.01, 1.10))),
        RelativePath("b", "2026-01-01", "2026-01-02", ((1.0, 1.01, .93, .95), (.95, .98, .88, .90))),
        RelativePath("c", "2026-01-01", "2026-01-02", ((1.0, 1.02, .98, 1.01), (1.01, 1.03, .97, 1.00))),
    )
    iv = .4
    physical = PhysicalPathSet(
        "run", "thesis", "XYZ", "BULL" if right == "CALL" else "BEAR", 100,
        target, stop, "research", "STATISTICALLY_UNRELIABLE", "UNCALIBRATED_RESEARCH",
        tuple(WeightedPath(path.path_id, 1 / 3,
                           tuple(PathSession(day, *(100 * ratio for ratio in bar), iv * iv_multiplier)
                                 for day, bar in enumerate(path.bars, 1)))
              for path in paths),
    )
    quote = LongOptionQuote("XYZ", right, 100, 4, 3.5, 100, 0, 0, 10, 2,
                            commission, (4 - 3.5) * slippage)
    reference = value_long_option_paths(physical, quote, research_only=True)
    actual = value_research_contract(
        paths, spot=100, target=target, stop=stop, right=right, strike=100,
        ask=4, bid=3.5, implied_vol=iv, multiplier=100, expiry_sessions=10,
        last_exit_session=2, iv_multiplier=iv_multiplier,
        commission_usd_round_trip=commission,
        extra_slippage_fraction_of_spread_each_side=slippage,
    )
    assert actual["state"] == reference["state"]
    assert actual["exit_policy"] == reference["exit_policy"]
    assert actual["ev_fraction"] == __import__("pytest").approx(reference["ev_fraction"], abs=1e-12)
    assert actual["ev_usd"] == __import__("pytest").approx(reference["ev_usd"], abs=1e-9)
    for key in reference["event_weights"]:
        assert actual["event_weights"][key] == __import__("pytest").approx(reference["event_weights"][key])
    assert actual["per_path_return_fraction"] == __import__("pytest").approx(reference["per_path_return_fraction"], abs=1e-12)


def test_call_first_barriers_and_base():
    _compare("CALL", 108, 94, 1.0, 0, 0)


def test_put_first_barriers_and_adverse():
    _compare("PUT", 92, 106, .8, 2, .25)


def test_call_time_only():
    _compare("CALL", None, None, .8, 2, .25)


def test_put_time_only():
    _compare("PUT", None, None, 1.0, 0, 0)
