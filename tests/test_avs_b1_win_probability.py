"""B1 (invented-values inventory, ACK 3 Oct 2026 "go ahead with B1"): win_probability is not a probability.

Discovery's win_probability = 40 + 0.25 x composite, clamped 35-75 - a rescaled score. Live consumers (verified in
options intelligence, the production path): 5% of the options research route score (path_score), and the options
layer's own EV fields (win_prob x gain at target). Found while checking: the route score still weighted stop-based
R:R (payoff_score, 15%) after the R:R removal.
Business rules:
- The route score uses neither the composite-derived probability nor R:R; the remaining components are
  renormalised so the GO/ARMED/PROBE thresholds keep their scale.
- The options layer computes no EV from the composite-derived number; its EV fields are not computed (stated).
- Discovery's field is labelled for what it is; a missing value is not 50.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import scripts.avshunter_options_intelligence as oi
from test_options_research_contract import _ctx, _econ, _route


def test_route_score_ignores_win_probability_and_rr():
    base = _route(ctx=_ctx(win_prob=45.0), econ=_econ(rr_options=1.0))
    other = _route(ctx=_ctx(win_prob=70.0), econ=_econ(rr_options=5.0))
    assert base["options_research_score"] == other["options_research_score"]
    assert base["path_score"] is None and base["payoff_score"] is None


def test_remaining_components_are_renormalised():
    r = _route()
    parts = {k: r[k] for k in ("directional_fit_score", "liquidity_score", "breakeven_score", "iv_score",
                               "theta_score", "runway_score")}
    weights = {"directional_fit_score": 0.20, "liquidity_score": 0.15, "breakeven_score": 0.15, "iv_score": 0.10,
               "theta_score": 0.10, "runway_score": 0.10}
    expected = round(sum(weights[k] * parts[k] for k in parts) / sum(weights.values()), 2)
    assert r["options_research_score"] == expected


def test_options_layer_computes_no_ev_from_the_composite():
    import inspect
    src = inspect.getsource(oi)
    assert "ev_structural = win_prob * option_gain - (1-win_prob) * mark" not in src
    assert "win_prob    = float(_f('win_probability', 50) or 50)" not in src


def test_discovery_labels_the_field():
    import inspect
    import avshunter_discovery_ULTIMATE as d
    src = inspect.getsource(d)
    assert "'win_probability_basis': 'COMPOSITE_RESCALED_NOT_A_PROBABILITY'" in src
