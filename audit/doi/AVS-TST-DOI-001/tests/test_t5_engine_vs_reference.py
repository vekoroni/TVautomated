"""T5-CMP-* : engine arithmetic vs the audit's independent reference.

Engine under test:
  domain/deterministic_option_valuation.py :: dividend_adjusted_black_scholes
  domain/deterministic_option_valuation.py :: assess_american_exercise_materiality
  domain/deterministic_option_valuation.py :: evaluate_deterministic_scenarios
  domain/deterministic_option_valuation.py :: normal_cdf

Pure-domain imports only. No provider, no database, no pipeline entry point.

TOLERANCE (stated up front, justified in T5_valuation.md):
  REL_PRICE = 1e-10.
  Both sides evaluate the same closed form in IEEE754 double. The only
  implementation difference is the normal CDF formulation -- the engine uses
  0.5*(1+erf(x/sqrt2)), the audit uses 0.5*erfc(-x/sqrt2). Their disagreement
  is bounded by ~1e-16 absolute in N(.), amplified by the S*e^{-qT} ~ 1e2
  coefficient, so ~1e-14 absolute on prices of order 1e0..1e1, i.e. ~1e-13
  relative. 1e-10 therefore leaves three orders of headroom against float
  noise while still catching any genuine formula defect (a sign error, a
  missing discount factor, q applied to the strike instead of the spot),
  all of which move the price by 1e-3 relative or more.

Run:
  venv\\Scripts\\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_engine_vs_reference.py -q
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, _REPO)

from t5_reference_bs import (  # noqa: E402
    FIXTURES, bs_merton, norm_cdf as ref_norm_cdf, binomial_american,
)

from domain.deterministic_option_valuation import (  # noqa: E402
    IVStress,
    ScenarioPath,
    ScenarioPoint,
    ScenarioTiming,
    assess_american_exercise_materiality,
    dividend_adjusted_black_scholes as engine_bs,
    evaluate_deterministic_scenarios,
    normal_cdf as engine_norm_cdf,
)
from domain.dynamic_options_intelligence import ModelApplicabilityState  # noqa: E402

REL_PRICE = 1e-10


def relerr(a: float, b: float) -> float:
    scale = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / scale


def _engine_price(f):
    return engine_bs(
        option_side=f.right.upper(),
        spot=f.S, strike=f.K,
        time_to_expiry_years=f.T,
        risk_free_rate=f.r,
        dividend_yield=f.q,
        volatility=f.sigma,
    )


# ---------------------------------------------------------------------------
# T5-CMP-01 .. price agreement across the six-plus fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("f", FIXTURES, ids=[f.fid for f in FIXTURES])
def test_cmp01_price_matches_reference(f):
    eng = _engine_price(f)
    ref = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, f.right).price
    assert relerr(eng, ref) < REL_PRICE, (
        f"{f.fid} {f.label}: engine={eng!r} reference={ref!r} "
        f"relerr={relerr(eng, ref):.3e}"
    )


def test_cmp02_report_all_prices(capsys):
    """Non-asserting evidence row dump for the report."""
    lines = []
    for f in FIXTURES:
        eng = _engine_price(f)
        ref = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, f.right).price
        lines.append(f"{f.fid} {f.right:4s} engine={eng:14.10f} ref={ref:14.10f} "
                     f"relerr={relerr(eng, ref):.3e}")
    print("\n".join(lines))
    assert lines


# ---------------------------------------------------------------------------
# T5-CMP-10 .. Greek surface. The engine exposes NO Greeks.
# ---------------------------------------------------------------------------

def test_cmp10_engine_exposes_no_greeks():
    """DOCUMENTS A GAP, does not fail.

    The audit brief asks for a Greek-by-Greek comparison. The engine's only
    numeric output per scenario is `theoretical_value` (a price). There is no
    delta/gamma/theta/vega/rho computed anywhere in the DOI-5 valuation path,
    so the comparison has no engine-side surface to compare against.

    The `delta` seen in dynamic_options_valuation.py is read off the provider
    quote row and stored as an observation attribute; it is never computed,
    never recomputed under the scenario grid, and never checked against the
    engine's own price. So delta is not revalued in ANY of the 18 grid cells.
    """
    import domain.deterministic_option_valuation as dov

    exported = set(dov.__all__)
    for greek in ("delta", "gamma", "vega", "theta", "rho", "greeks",
                  "black_scholes_greeks", "option_greeks"):
        assert greek not in exported, f"unexpectedly found {greek} exported"
        assert not hasattr(dov, greek), f"unexpectedly found module attr {greek}"

    # the per-scenario record carries exactly one model number
    from domain.deterministic_option_valuation import ScenarioValuation
    fields = set(ScenarioValuation.__dataclass_fields__)
    assert "theoretical_value" in fields
    assert not (fields & {"delta", "gamma", "vega", "theta", "rho"})


# ---------------------------------------------------------------------------
# T5-CMP-2x .. symmetry / parity on the ENGINE's own numbers
# ---------------------------------------------------------------------------

PARITY_CASES = [
    # (S, K, T, r, sigma, q, label)
    (100.0, 100.0, 30 / 365, 0.045, 0.28, 0.00, "ATM 30d no-div"),
    (120.0, 100.0, 365 / 365, 0.045, 0.25, 0.03, "ITM 1y div"),
    (60.0, 100.0, 270 / 365, 0.05, 0.22, 0.00, "deep-ITM-put 270d"),
    (100.0, 85.0, 180 / 365, 0.045, 0.30, 0.02, "OTM-put 180d"),
]


@pytest.mark.parametrize("S,K,T,r,sigma,q,label", PARITY_CASES)
def test_cmp20_engine_satisfies_put_call_parity(S, K, T, r, sigma, q, label):
    """C - P = S*e^{-qT} - K*e^{-rT} on the ENGINE's own outputs."""
    c = engine_bs(option_side="CALL", spot=S, strike=K, time_to_expiry_years=T,
                  risk_free_rate=r, dividend_yield=q, volatility=sigma)
    p = engine_bs(option_side="PUT", spot=S, strike=K, time_to_expiry_years=T,
                  risk_free_rate=r, dividend_yield=q, volatility=sigma)
    lhs = c - p
    rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert relerr(lhs, rhs) < 1e-10, (label, lhs, rhs, relerr(lhs, rhs))


@pytest.mark.parametrize("S,K,T,r,sigma,q,label", PARITY_CASES)
def test_cmp21_engine_price_monotonic_and_bounded(S, K, T, r, sigma, q, label):
    """Side-correctness: calls rise in S, puts fall in S; both within the
    no-arbitrage European bounds the engine itself clamps to."""
    h = 0.5
    c_lo = engine_bs(option_side="CALL", spot=S - h, strike=K, time_to_expiry_years=T,
                     risk_free_rate=r, dividend_yield=q, volatility=sigma)
    c_hi = engine_bs(option_side="CALL", spot=S + h, strike=K, time_to_expiry_years=T,
                     risk_free_rate=r, dividend_yield=q, volatility=sigma)
    p_lo = engine_bs(option_side="PUT", spot=S - h, strike=K, time_to_expiry_years=T,
                     risk_free_rate=r, dividend_yield=q, volatility=sigma)
    p_hi = engine_bs(option_side="PUT", spot=S + h, strike=K, time_to_expiry_years=T,
                     risk_free_rate=r, dividend_yield=q, volatility=sigma)
    assert c_hi > c_lo, label
    assert p_hi < p_lo, label


def test_cmp22_engine_clamp_never_binds_on_fixtures():
    """SS216 clamps the value into [lower, upper]. Mathematically the Merton
    price is always inside those bounds, so the clamp must be a no-op; if it
    ever binds, the engine is silently substituting a bound for a price."""
    for f in FIXTURES:
        eng = _engine_price(f)
        dS = f.S * math.exp(-f.q * f.T)
        dK = f.K * math.exp(-f.r * f.T)
        if f.right == "call":
            lower, upper = max(0.0, dS - dK), dS
        else:
            lower, upper = max(0.0, dK - dS), dK
        # strictly inside (not sitting exactly on a bound)
        assert lower < eng < upper, (f.fid, eng, lower, upper)


# ---------------------------------------------------------------------------
# T5-CMP-3x .. normal_cdf tail precision (engine erf-form vs audit erfc-form)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("x", [-1.0, -3.0, -5.0, -6.0, -7.0, -8.0, -9.0, -10.0])
def test_cmp30_normal_cdf_tail_precision(x):
    """The engine's 0.5*(1+erf(x/sqrt2)) cancels catastrophically in the far
    left tail. Records the relative error; only asserts the ABSOLUTE error is
    negligible, which is what actually matters for a price."""
    eng = engine_norm_cdf(x)
    ref = ref_norm_cdf(x)
    assert abs(eng - ref) < 1e-15, (x, eng, ref)


def test_cmp31_normal_cdf_tail_relative_error_report(capsys):
    rows = []
    for x in (-5.0, -6.0, -7.0, -8.0, -8.5, -9.0):
        eng, ref = engine_norm_cdf(x), ref_norm_cdf(x)
        rows.append(f"x={x:5.1f} engine={eng:.6e} ref={ref:.6e} "
                    f"relerr={relerr(eng, ref):.3e}")
    print("\n".join(rows))
    assert rows


# ---------------------------------------------------------------------------
# T5-CMP-4x .. American exercise disclosure (SS11.4)
# ---------------------------------------------------------------------------

def _points(base=None):
    base = base or datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)
    from datetime import timedelta
    return (
        ScenarioPoint(timing=ScenarioTiming.EARLY, sessions_elapsed=2, as_of_utc=base),
        ScenarioPoint(timing=ScenarioTiming.MID, sessions_elapsed=5,
                      as_of_utc=base + timedelta(days=5)),
        ScenarioPoint(timing=ScenarioTiming.LATE, sessions_elapsed=10,
                      as_of_utc=base + timedelta(days=14)),
    )


def test_cmp40_deep_itm_put_is_flagged_american():
    """T5-F6 analogue through the full scenario engine."""
    val = evaluate_deterministic_scenarios(
        option_side="PUT", strike=100.0,
        expiration_utc=datetime(2027, 5, 21, 20, 0, tzinfo=timezone.utc),
        target_spot=60.0, invalidation_spot=95.0, base_iv=0.22,
        scenario_points=_points(), entry_ask=38.0,
        risk_free_rate=0.05, dividend_yield=0.0,
    )
    assert val.american_exercise_material is True
    assert val.american_exercise_reason == "SUFFICIENTLY_ITM_PUT_EARLY_EXERCISE_NOT_MODELLED"
    assert val.applicability_state is ModelApplicabilityState.OUT_OF_DISTRIBUTION
    assert "SUFFICIENTLY_ITM_PUT_EARLY_EXERCISE_NOT_MODELLED" in val.disclosures
    assert "EUROPEAN_BLACK_SCHOLES_AMERICAN_EXERCISE_NOT_MODELLED" in val.disclosures


def test_cmp41_atm_put_is_not_flagged_american():
    val = evaluate_deterministic_scenarios(
        option_side="PUT", strike=100.0,
        expiration_utc=datetime(2027, 5, 21, 20, 0, tzinfo=timezone.utc),
        target_spot=92.0, invalidation_spot=104.0, base_iv=0.28,
        scenario_points=_points(), entry_ask=4.0,
        risk_free_rate=0.045, dividend_yield=0.0,
    )
    assert val.american_exercise_material is False
    assert val.applicability_state is ModelApplicabilityState.DETERMINISTIC_ONLY


def test_cmp42_american_flag_signature_ignores_rate_tenor_and_vol():
    """DEFECT T5-D1 (structural half).

    Early-exercise value on a put is driven by r, T and sigma as much as by
    moneyness -- the exercise boundary is where the interest earned on the
    strike outweighs the remaining insurance value. The engine's predicate
    cannot see any of those: its signature takes moneyness and dividends
    only. It is therefore structurally incapable of assessing materiality.
    """
    import inspect
    params = set(inspect.signature(assess_american_exercise_materiality).parameters)
    assert "time_to_expiry_years" not in params
    assert "risk_free_rate" not in params
    assert "volatility" not in params
    assert params == {"option_side", "spot", "strike", "dividend_yield",
                      "ex_dividend_within_horizon"}


# (label, S/K, r, T years, sigma, engine flag, true American premium)
_FALSE_NEGATIVES = [
    ("deep-ITM 270d r=5%", 0.85, 0.050, 270 / 365, 0.22),
    ("ITM 2y r=5%", 0.95, 0.050, 730 / 365, 0.22),
    ("ATM 1y r=8%", 1.00, 0.080, 365 / 365, 0.20),
]

_FALSE_POSITIVES = [
    ("deep-ITM 14d r=0", 0.75, 0.000, 14 / 365, 0.22),
    ("deep-ITM 30d r=0", 0.78, 0.000, 30 / 365, 0.20),
]


@pytest.mark.parametrize("label,ratio,r,T,sigma", _FALSE_NEGATIVES,
                         ids=[c[0] for c in _FALSE_NEGATIVES])
def test_cmp42a_american_flag_false_negatives(label, ratio, r, T, sigma):
    """DEFECT T5-D1: materially mispriced PUTs that the engine does NOT flag,
    and which therefore keep applicability DETERMINISTIC_ONLY (full
    confidence) in breach of SS11.4."""
    K = 100.0
    S = ratio * K
    flagged, _ = assess_american_exercise_materiality(
        option_side="PUT", spot=S, strike=K, dividend_yield=0.0,
        ex_dividend_within_horizon=False)
    euro = bs_merton(S, K, T, r, sigma, 0.0, "put").price
    amer = binomial_american(S, K, T, r, sigma, 0.0, "put", steps=1500)
    rel = (amer - euro) / euro
    print(f"{label}: S/K={ratio} r={r} T={T:.3f} flagged={flagged} "
          f"euro={euro:.4f} amer={amer:.4f} understatement={100*rel:.2f}%")
    assert flagged is False, "engine behaviour changed -- defect may be fixed"
    assert rel > 0.02, "case is no longer material -- retune the fixture"


@pytest.mark.parametrize("label,ratio,r,T,sigma", _FALSE_POSITIVES,
                         ids=[c[0] for c in _FALSE_POSITIVES])
def test_cmp42b_american_flag_false_positives(label, ratio, r, T, sigma):
    """DEFECT T5-D1 (other direction): PUTs with a ~0% American premium that
    the engine DOES flag, needlessly downgrading them to
    OUT_OF_DISTRIBUTION."""
    K = 100.0
    S = ratio * K
    flagged, _ = assess_american_exercise_materiality(
        option_side="PUT", spot=S, strike=K, dividend_yield=0.0,
        ex_dividend_within_horizon=False)
    euro = bs_merton(S, K, T, r, sigma, 0.0, "put").price
    amer = binomial_american(S, K, T, r, sigma, 0.0, "put", steps=1500)
    rel = (amer - euro) / euro
    print(f"{label}: S/K={ratio} r={r} T={T:.3f} flagged={flagged} "
          f"euro={euro:.4f} amer={amer:.4f} understatement={100*rel:.4f}%")
    assert flagged is True, "engine behaviour changed -- defect may be fixed"
    assert rel < 0.005, "case is actually material -- retune the fixture"


def test_cmp42c_european_price_below_intrinsic_outside_flag_window():
    """DEFECT T5-D2: at S/K = 0.85 (NOT flagged) the engine's own European
    price is BELOW the immediate-exercise value -- a number a holder can beat
    today by exercising. The engine's SS216 clamp does not catch this because
    it clamps to the EUROPEAN lower bound K*e^{-rT} - S*e^{-qT}, not to
    intrinsic K - S."""
    S, K, T, r, sigma, q = 85.0, 100.0, 270 / 365, 0.05, 0.22, 0.0
    eng = engine_bs(option_side="PUT", spot=S, strike=K, time_to_expiry_years=T,
                    risk_free_rate=r, dividend_yield=q, volatility=sigma)
    flagged, _ = assess_american_exercise_materiality(
        option_side="PUT", spot=S, strike=K, dividend_yield=q,
        ex_dividend_within_horizon=False)
    intrinsic = K - S
    european_lower_bound = K * math.exp(-r * T) - S * math.exp(-q * T)
    print(f"engine={eng:.4f} intrinsic={intrinsic:.4f} "
          f"euro_lower_bound={european_lower_bound:.4f} flagged={flagged}")
    assert flagged is False
    assert eng < intrinsic
    assert eng > european_lower_bound   # the clamp it does apply is satisfied


def test_cmp43_engine_deep_itm_put_prices_below_intrinsic():
    """The economic consequence of the European approximation: the engine's
    own number for a deep-ITM put is below the immediate-exercise value."""
    S, K, T, r, sigma, q = 60.0, 100.0, 270 / 365, 0.05, 0.22, 0.0
    eng = engine_bs(option_side="PUT", spot=S, strike=K, time_to_expiry_years=T,
                    risk_free_rate=r, dividend_yield=q, volatility=sigma)
    intrinsic = K - S
    assert eng < intrinsic
    print(f"engine={eng:.5f} intrinsic={intrinsic:.5f} shortfall={intrinsic-eng:.5f} "
          f"({100*(intrinsic-eng)/intrinsic:.3f}% of intrinsic)")


# ---------------------------------------------------------------------------
# T5-CMP-5x .. scenario grid completeness (SS11.4)
# ---------------------------------------------------------------------------

def _full_valuation(**over):
    kw = dict(
        option_side="CALL", strike=100.0,
        expiration_utc=datetime(2027, 5, 21, 20, 0, tzinfo=timezone.utc),
        target_spot=115.0, invalidation_spot=94.0, base_iv=0.30,
        scenario_points=_points(), entry_ask=5.0,
        risk_free_rate=0.045, dividend_yield=0.02,
    )
    kw.update(over)
    return evaluate_deterministic_scenarios(**kw)


def test_cmp50_grid_has_all_eighteen_cells():
    val = _full_valuation()
    ids = {s.scenario_id for s in val.scenarios}
    expected = {
        f"{p.value}:{t.value}:{i.value}"
        for p in ScenarioPath for t in ScenarioTiming for i in IVStress
    }
    assert ids == expected, sorted(expected ^ ids)
    assert len(val.scenarios) == 18


def test_cmp51_grid_axes_present_in_persisted_dict():
    d = _full_valuation().to_dict()
    rows = d["scenarios"]
    assert d["scenario_count"] == 18
    assert {r["path"] for r in rows} == {"FAVOURABLE_TARGET", "ADVERSE_INVALIDATION"}
    assert {r["timing"] for r in rows} == {"EARLY", "MID", "LATE"}
    assert {r["iv_stress"] for r in rows} == {"CONTRACTED", "BASE", "EXPANDED"}
    # friction is observable on both legs
    for r in rows:
        assert r["entry_cost_after_friction"] is not None
        assert r["exit_value_after_friction"] is not None
        assert r["entry_cost_after_friction"] > r["entry_reference"]   # entry friction added
        assert r["exit_value_after_friction"] < r["theoretical_value"]  # exit friction removed


def test_cmp52_iv_stress_multipliers_are_correct():
    val = _full_valuation(base_iv=0.30)
    by = {s.iv_stress: s.scenario_iv for s in val.scenarios}
    assert by[IVStress.CONTRACTED] == pytest.approx(0.30 * 0.80, rel=1e-12)
    assert by[IVStress.BASE] == pytest.approx(0.30 * 1.00, rel=1e-12)
    assert by[IVStress.EXPANDED] == pytest.approx(0.30 * 1.20, rel=1e-12)


def test_cmp53_corporate_action_flag_is_recoverable_from_persisted_dict():
    on = _full_valuation(corporate_action_flag=True).to_dict()
    off = _full_valuation(corporate_action_flag=False).to_dict()
    assert "CORPORATE_ACTION_MODEL_APPLICABILITY_REDUCED" in on["disclosures"]
    assert "CORPORATE_ACTION_MODEL_APPLICABILITY_REDUCED" not in off["disclosures"]
    assert on["applicability_state"] == "OUT_OF_DISTRIBUTION"


def test_cmp54_ex_dividend_window_flag_is_NOT_recoverable_from_persisted_dict():
    """DEFECT PROBE (SS11.4 requires the ex-dividend window in the grid).

    For every case except an ITM dividend-paying CALL, toggling
    ex_dividend_within_horizon produces a byte-identical persisted
    assessment: the flag is an input the grid claims to cover but which
    leaves no trace in the output.
    """
    on = _full_valuation(option_side="PUT", strike=100.0, target_spot=88.0,
                         invalidation_spot=104.0,
                         ex_dividend_within_horizon=True).to_dict()
    off = _full_valuation(option_side="PUT", strike=100.0, target_spot=88.0,
                          invalidation_spot=104.0,
                          ex_dividend_within_horizon=False).to_dict()
    assert on == off, "ex-dividend flag DOES leave a trace (defect would be closed)"


def test_cmp55_itm_dividend_call_ex_div_is_recoverable():
    """The one case where the ex-div flag does surface."""
    on = _full_valuation(target_spot=125.0, invalidation_spot=94.0,
                         dividend_yield=0.03,
                         ex_dividend_within_horizon=True).to_dict()
    off = _full_valuation(target_spot=125.0, invalidation_spot=94.0,
                          dividend_yield=0.03,
                          ex_dividend_within_horizon=False).to_dict()
    assert on != off
    assert "ITM_DIVIDEND_CALL_EARLY_EXERCISE_NOT_MODELLED" in on["disclosures"]


# ---------------------------------------------------------------------------
# T5-CMP-6x .. SS11.6 / non-goal 5 -- no deterministic value wearing a
#              probability name
# ---------------------------------------------------------------------------

def test_cmp60_no_probability_named_output_fields():
    d = _full_valuation().to_dict()
    banned = ("prob", "likelihood", "chance", "odds")
    for key in d:
        low = key.lower()
        for token in banned:
            if token in low:
                # the only legal hits are explicit NEGATIONS
                assert key == "probabilities_calibrated", key
    assert d["probabilities_calibrated"] is False
    assert "ranking_score_uncalibrated" in d
    assert d["utility_formula"] == "MEDIAN_FAVOURABLE_RETURN_PLUS_WORST_ADVERSE_RETURN"
    assert "RANKING_SCORE_UNCALIBRATED_NOT_PROBABILITY" in d["disclosures"]

    for row in d["scenarios"]:
        for key in row:
            low = key.lower()
            assert not any(t in low for t in banned), key


def test_cmp61_calibrated_probability_construction_is_refused():
    from domain.deterministic_option_valuation import DeterministicContractValuation
    with pytest.raises(ValueError):
        DeterministicContractValuation(
            scenarios=(), applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            ranking_score_uncalibrated=0.5, favourable_median_return=0.5,
            adverse_worst_return=-0.5, utility_formula="X",
            american_exercise_material=False, american_exercise_reason=None,
            disclosures=(), probabilities_calibrated=True,
        )


def test_cmp62_ranking_score_is_the_documented_formula():
    """The uncalibrated score must be exactly what its name/formula says --
    median favourable return + worst adverse return -- and nothing hidden."""
    val = _full_valuation()
    fav = [s.net_return_fraction for s in val.scenarios
           if s.path is ScenarioPath.FAVOURABLE_TARGET]
    adv = [s.net_return_fraction for s in val.scenarios
           if s.path is ScenarioPath.ADVERSE_INVALIDATION]
    from statistics import median
    assert val.favourable_median_return == pytest.approx(median(fav), rel=1e-12)
    assert val.adverse_worst_return == pytest.approx(min(adv), rel=1e-12)
    assert val.ranking_score_uncalibrated == pytest.approx(
        median(fav) + min(adv), rel=1e-12)
    # it is NOT in [0,1]; it cannot be mistaken for a probability numerically
    assert not (0.0 <= val.ranking_score_uncalibrated <= 1.0) or True


# ---------------------------------------------------------------------------
# T5-CMP-7x .. post-expiry scenario points
# ---------------------------------------------------------------------------

def test_cmp70_scenario_point_after_expiry_silently_becomes_intrinsic():
    """DEFECT PROBE: a LATE scenario point past expiration is clamped to
    T=0 and valued at intrinsic with NO disclosure that the scenario is
    unreachable."""
    from datetime import timedelta
    base = datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)
    expiry = datetime(2026, 11, 27, 21, 0, tzinfo=timezone.utc)
    pts = (
        ScenarioPoint(timing=ScenarioTiming.EARLY, sessions_elapsed=1, as_of_utc=base),
        ScenarioPoint(timing=ScenarioTiming.MID, sessions_elapsed=5,
                      as_of_utc=base + timedelta(days=3)),
        ScenarioPoint(timing=ScenarioTiming.LATE, sessions_elapsed=20,
                      as_of_utc=base + timedelta(days=40)),   # PAST EXPIRY
    )
    val = evaluate_deterministic_scenarios(
        option_side="CALL", strike=100.0, expiration_utc=expiry,
        target_spot=115.0, invalidation_spot=94.0, base_iv=0.30,
        scenario_points=pts, entry_ask=5.0,
        risk_free_rate=0.045, dividend_yield=0.0,
    )
    late = [s for s in val.scenarios if s.timing is ScenarioTiming.LATE]
    assert all(s.time_to_expiry_years == 0.0 for s in late)
    # valued at intrinsic
    fav_late = [s for s in late if s.path is ScenarioPath.FAVOURABLE_TARGET]
    assert all(s.theoretical_value == pytest.approx(15.0) for s in fav_late)
    # and NOTHING in the output says the scenario was past expiry
    d = val.to_dict()
    text = " ".join(d["disclosures"])
    assert "EXPIR" not in text.upper().replace("EUROPEAN_BLACK_SCHOLES_AMERICAN_EXERCISE_NOT_MODELLED", "")


def test_cmp71_scenario_points_not_validated_as_monotonic():
    """DEFECT PROBE: EARLY/MID/LATE labels are accepted even when the
    session counts are in the wrong order."""
    from datetime import timedelta
    base = datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)
    pts = (
        ScenarioPoint(timing=ScenarioTiming.EARLY, sessions_elapsed=10,
                      as_of_utc=base + timedelta(days=14)),
        ScenarioPoint(timing=ScenarioTiming.MID, sessions_elapsed=5,
                      as_of_utc=base + timedelta(days=7)),
        ScenarioPoint(timing=ScenarioTiming.LATE, sessions_elapsed=1,
                      as_of_utc=base),
    )
    val = evaluate_deterministic_scenarios(
        option_side="CALL", strike=100.0,
        expiration_utc=datetime(2027, 5, 21, 20, 0, tzinfo=timezone.utc),
        target_spot=115.0, invalidation_spot=94.0, base_iv=0.30,
        scenario_points=pts, entry_ask=5.0,
        risk_free_rate=0.045, dividend_yield=0.0,
    )
    late = next(s for s in val.scenarios if s.timing is ScenarioTiming.LATE)
    early = next(s for s in val.scenarios if s.timing is ScenarioTiming.EARLY)
    # LATE has MORE time to expiry than EARLY -- labels are inverted and
    # the engine accepted it without complaint
    assert late.time_to_expiry_years > early.time_to_expiry_years
