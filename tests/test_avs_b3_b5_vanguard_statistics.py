"""B3/B5 (invented-values inventory, ACK 3 Oct 2026 "go ahead with B3-B5"): Vanguard statistics say what they are.

Live (verified on run 20261001_211641, vanguard_signals.csv):
- B3: a RELAXED match is published with state_match_similarity 1.0 (1,367 rows at 1.0, only 1,262 EXACT).
- B5a: _scaled_ev_floor lowers the TRADE EV floor to 65% for thin samples - thinner evidence faced an easier bar;
  a Vanguard TRADE verdict also widens the options scope.
- B5b: "high sample" ignored the match method (59 non-exact rows STATISTICAL_MODERATE).
B4 (intraday multipliers) is dormant in production (fails closed without intraday rows) - recorded, not changed.
Business rules:
- A relaxed match carries no similarity measure: published as None (not measured), never 1.0.
- Thin samples never face a lower bar than full samples.
- Only an EXACT match counts as a high sample for the statistical edge labels.
"""
import inspect
from types import SimpleNamespace

from vanguard.layer2_statistical import edge_detector as ed
from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine as ActuarialQuery


def test_relaxed_match_does_not_claim_full_similarity():
    src = inspect.getsource(ActuarialQuery._find_match_ladder_states)
    relaxed = src[src.index('method="RELAXED"'):src.index('method="RELAXED"') + 900]
    assert '"state_match_similarity": 1.0' not in relaxed and "similarity=1.0" not in relaxed


def test_thin_sample_never_faces_a_lower_floor():
    assert ed._scaled_ev_floor(0.001, 50) == 0.001
    assert ed._scaled_ev_floor(0.001, 5000) == 0.001


def _outcomes(method, n=5000, edge=0.12):
    return SimpleNamespace(future_momentum_bucket=None, future_momentum_bucket_confidence=0.0,
                           future_momentum_bucket_sample_size=0, probability_edge=edge,
                           state_match_quality="HIGH_SAMPLE", sample_size=n, n_observations=n,
                           state_match_method=method)


def test_only_exact_matches_count_as_a_high_sample():
    state = SimpleNamespace(early_candidate=0)
    detector = ed.EdgeDetector.__new__(ed.EdgeDetector)
    assert detector._bucket_edge_quality(state, _outcomes("EXACT")) == "STATISTICAL_STRONG"
    for method in ("ANALOGUE", "RELAXED", ""):
        assert detector._bucket_edge_quality(state, _outcomes(method)) not in {"STATISTICAL_STRONG", "STATISTICAL_MODERATE"}
