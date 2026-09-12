"""T5-SELF-* : prove the AUDIT'S OWN arithmetic before it is used as truth.

Every closed-form Greek is cross-checked against (a) a central finite
difference of the audit's own price function and (b) scipy.stats.norm, and
the parity/symmetry identities are asserted directly.

Run:
  venv\\Scripts\\python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/test_t5_reference_selfcheck.py -q
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from t5_reference_bs import (  # noqa: E402
    FIXTURES, bs_merton, norm_cdf, norm_pdf,
    fd_delta, fd_gamma, fd_vega_full, fd_theta_year,
    binomial_american, binomial_european,
)

# Tolerances -- justified in T5_valuation.md SS "tolerance".
REL_FD_DELTA = 1e-6
REL_FD_GAMMA = 1e-4     # second-order FD loses ~half the digits
REL_FD_VEGA = 1e-6
REL_FD_THETA = 1e-5
REL_ANALYTIC = 1e-12    # identity-level, closed form vs closed form


def relerr(a: float, b: float) -> float:
    scale = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / scale


def test_selfcheck_normcdf_against_scipy():
    scipy_stats = pytest.importorskip("scipy.stats")
    for x in (-8.0, -3.5, -1.0, -0.01, 0.0, 0.01, 1.0, 3.5, 8.0):
        assert relerr(norm_cdf(x), float(scipy_stats.norm.cdf(x))) < 1e-12, x
        assert relerr(norm_pdf(x), float(scipy_stats.norm.pdf(x))) < 1e-12, x


@pytest.mark.parametrize("f", FIXTURES, ids=[f.fid for f in FIXTURES])
def test_selfcheck_greeks_match_finite_difference(f):
    g = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, f.right)
    args = (f.S, f.K, f.T, f.r, f.sigma, f.q, f.right)

    assert relerr(g.delta, fd_delta(*args)) < REL_FD_DELTA
    assert relerr(g.gamma, fd_gamma(*args)) < REL_FD_GAMMA
    assert relerr(g.vega_full, fd_vega_full(*args)) < REL_FD_VEGA
    assert relerr(g.theta_year, fd_theta_year(*args)) < REL_FD_THETA


@pytest.mark.parametrize("f", FIXTURES, ids=[f.fid for f in FIXTURES])
def test_selfcheck_price_matches_european_binomial(f):
    """European binomial with many steps must converge to the closed form."""
    b = binomial_european(f.S, f.K, f.T, f.r, f.sigma, f.q, f.right, steps=1200)
    g = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, f.right)
    assert abs(b - g.price) < 0.01, (f.fid, b, g.price)


PARITY_PAIRS = [
    # (call fixture id, put fixture id) -- identical S,K,T,r,sigma,q
    ("T5-F1", "T5-F4"),
    ("T5-F3", "T5-F7"),
    ("T5-F8", "T5-F6"),
]


@pytest.mark.parametrize("cid,pid", PARITY_PAIRS)
def test_selfcheck_put_call_parity(cid, pid):
    fc = next(f for f in FIXTURES if f.fid == cid)
    fp = next(f for f in FIXTURES if f.fid == pid)
    assert (fc.S, fc.K, fc.T, fc.r, fc.sigma, fc.q) == \
           (fp.S, fp.K, fp.T, fp.r, fp.sigma, fp.q)
    c = bs_merton(fc.S, fc.K, fc.T, fc.r, fc.sigma, fc.q, "call")
    p = bs_merton(fp.S, fp.K, fp.T, fp.r, fp.sigma, fp.q, "put")

    lhs = c.price - p.price
    rhs = fc.S * math.exp(-fc.q * fc.T) - fc.K * math.exp(-fc.r * fc.T)
    assert relerr(lhs, rhs) < REL_ANALYTIC, (cid, pid, lhs, rhs)

    # delta_call - delta_put = e^{-qT}
    assert relerr(c.delta - p.delta, math.exp(-fc.q * fc.T)) < REL_ANALYTIC

    # gamma and vega identical across sides
    assert relerr(c.gamma, p.gamma) < REL_ANALYTIC
    assert relerr(c.vega_full, p.vega_full) < REL_ANALYTIC


@pytest.mark.parametrize("f", FIXTURES, ids=[f.fid for f in FIXTURES])
def test_selfcheck_delta_bounds_and_signs(f):
    g = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, f.right)
    dfq = math.exp(-f.q * f.T)
    if f.right == "call":
        assert 0.0 < g.delta < dfq + 1e-15
    else:
        assert -dfq - 1e-15 < g.delta < 0.0
    assert g.gamma > 0.0
    assert g.vega_full > 0.0
    assert g.price > 0.0


def test_selfcheck_american_premium_on_deep_itm_put():
    """T5-F6 must show a MATERIAL American premium -- this is the fixture
    that SS11.4 requires the engine to flag.

    Measured: European 36.3973, American 40.0000 (= immediate exercise
    K-S = 40), premium 3.6027 = 9.90%.
    """
    f = next(x for x in FIXTURES if x.fid == "T5-F6")
    euro = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, "put").price
    amer = binomial_american(f.S, f.K, f.T, f.r, f.sigma, f.q, "put", steps=1500)
    premium = amer - euro
    assert premium > 0.0
    # >5% of the European price: an economically material approximation,
    # an order of magnitude above the ~1% seen at/near the money.
    assert premium / euro > 0.05, (euro, amer, premium)


def test_selfcheck_deep_itm_put_european_price_is_below_intrinsic():
    """The load-bearing defect condition: for T5-F6 the European (BS) value
    is BELOW the immediate-exercise value. Any engine reporting the BS
    number as the contract's value reports a price a holder can beat, today,
    by exercising. This is what SS11.4's 'sufficiently ITM puts' clause is
    about."""
    f = next(x for x in FIXTURES if x.fid == "T5-F6")
    euro = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, "put").price
    intrinsic = f.K - f.S
    assert euro < intrinsic, (euro, intrinsic)
    assert intrinsic - euro > 3.0, (euro, intrinsic)


def test_selfcheck_atm_american_premium_is_an_order_of_magnitude_smaller():
    """Control: the ATM short-dated put's American premium (0.82%) is an
    order of magnitude below the deep-ITM case (9.90%), so the deep-ITM
    flag is discriminating on something real rather than flagging all puts.

    NOTE: the audit's first draft asserted <0.5% here and FAILED at 0.816%.
    The audit arithmetic was correct; the audit's own threshold was wrong
    and was widened. No engine code informed this change.
    """
    f = next(x for x in FIXTURES if x.fid == "T5-F4")
    euro = bs_merton(f.S, f.K, f.T, f.r, f.sigma, f.q, "put").price
    amer = binomial_american(f.S, f.K, f.T, f.r, f.sigma, f.q, "put", steps=1500)
    atm_rel = (amer - euro) / euro
    assert atm_rel < 0.02, atm_rel

    g = next(x for x in FIXTURES if x.fid == "T5-F6")
    deep_euro = bs_merton(g.S, g.K, g.T, g.r, g.sigma, g.q, "put").price
    deep_amer = binomial_american(g.S, g.K, g.T, g.r, g.sigma, g.q, "put", steps=1500)
    deep_rel = (deep_amer - deep_euro) / deep_euro
    assert deep_rel > 5.0 * atm_rel, (atm_rel, deep_rel)
