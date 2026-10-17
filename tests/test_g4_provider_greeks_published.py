"""G4 business rules (ACK approved 17 Oct 2026; implements decision D4 "Heston overwrite retired; provider greeks").

Design: Enhancements/options_valuation_review/G4_HESTON_GREEKS_ROOT_CAUSE_AND_DESIGN_20261017.md.
The provider's Greeks are the published Greeks. A model's Greeks may be shown under their own names with their basis,
and never replace an observation. Missing provider Greeks stay missing.
"""
from __future__ import annotations

import math
import signal
import sys
from pathlib import Path

import pytest
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402
from tests.test_g4_heston_greeks_characterisation import SPOT, provider_put, skewed_chain  # noqa: E402


@pytest.fixture
def no_sigalrm(monkeypatch):
    monkeypatch.delattr(signal, "SIGALRM", raising=False)


@pytest.fixture
def proxy_params(no_sigalrm):
    return oi.calibrate_heston(skewed_chain(), SPOT)


def _bs_delta(right: str, strike: float, t: float, sigma: float, r: float) -> float:
    d1 = (math.log(SPOT / strike) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    return norm.cdf(d1) if right == "C" else norm.cdf(d1) - 1.0


def test_the_published_greeks_are_the_providers_quote_for_that_contract(proxy_params):
    enriched = oi.enrich_contract_with_heston_greeks(provider_put(), proxy_params, SPOT)
    for greek in ("delta", "gamma", "theta", "vega"):
        assert enriched[greek] == provider_put()[greek], greek
    assert oi.contract_greeks_source(enriched) == "PROVIDER_EOD_CHAIN"


def test_model_greeks_appear_only_under_model_names_with_their_basis(proxy_params):
    enriched = oi.enrich_contract_with_heston_greeks(provider_put(), proxy_params, SPOT)
    sigma_atm = math.sqrt(proxy_params["v0"])
    assert enriched["model_atm_delta"] == pytest.approx(_bs_delta("P", 80.0, 35 / 365.0, sigma_atm, oi.RISK_FREE_RATE))
    assert {"model_atm_gamma", "model_atm_theta", "model_atm_vega"} <= set(enriched)
    assert enriched["model_greeks_basis"] == "BS_AT_ATM_VARIANCE_DISPLAY_ONLY"


def test_a_contract_without_provider_greeks_is_published_unavailable_never_model_filled(proxy_params):
    bare = {k: v for k, v in provider_put().items() if k not in ("delta", "gamma", "theta", "vega")}
    for params in (proxy_params, None):
        enriched = oi.enrich_contract_with_heston_greeks(bare, params, SPOT)
        for greek in ("delta", "gamma", "theta", "vega"):
            assert enriched.get(greek) is None, greek
        assert oi.contract_greeks_source(enriched) == "UNAVAILABLE"


@pytest.mark.parametrize("right,strike", [("P", 80.0), ("C", 120.0), ("C", 100.0)])
def test_vanna_and_charm_are_measured_on_the_contracts_own_iv(proxy_params, right, strike):
    """Vanna: change in delta per 1.00 of IV. Charm: change in delta over one calendar day, spot and IV unchanged."""
    contract = {**provider_put(), "right": right, "strike": strike}
    sigma, t, r, h = 0.90, 35 / 365.0, oi.RISK_FREE_RATE, 1e-4
    vanna_fd = (_bs_delta(right, strike, t, sigma + h, r) - _bs_delta(right, strike, t, sigma - h, r)) / (2 * h)
    half_day = 0.5 / 365.0
    charm_fd = _bs_delta(right, strike, t - half_day, sigma, r) - _bs_delta(right, strike, t + half_day, sigma, r)
    for params in (proxy_params, None):
        enriched = oi.enrich_contract_with_heston_greeks(contract, params, SPOT)
        assert enriched["vanna"] == pytest.approx(vanna_fd, rel=1e-3, abs=1e-5)
        assert enriched["charm"] == pytest.approx(charm_fd, rel=2e-2, abs=1e-5)
        assert enriched["vanna_charm_basis"] == "BSM_CONTRACT_IV"


def test_a_platform_that_cannot_time_out_calibration_records_the_proxy_and_the_reason(proxy_params):
    assert proxy_params["method"] == "analytical_proxy"
    assert proxy_params["proxy_reason"] == "TIMEOUT_UNSUPPORTED_ON_PLATFORM"


def test_the_output_row_carries_provider_greeks_and_labelled_model_greeks(proxy_params):
    enriched = oi.enrich_contract_with_heston_greeks(provider_put(), proxy_params, SPOT)
    fields = oi.contract_greek_output_fields(enriched)
    assert fields["contract_delta"] == provider_put()["delta"]
    assert fields["contract_greeks_source"] == "PROVIDER_EOD_CHAIN"
    assert fields["contract_model_atm_delta"] == enriched["model_atm_delta"]
    assert fields["contract_model_greeks_basis"] == "BS_AT_ATM_VARIANCE_DISPLAY_ONLY"
    assert fields["contract_vanna_charm_basis"] == "BSM_CONTRACT_IV"
