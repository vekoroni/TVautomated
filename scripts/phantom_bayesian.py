"""PHANTOM Bayesian actuarial bridge."""

from __future__ import annotations

import math
from typing import Any, Dict

try:
    from scipy.stats import beta
except Exception:  # pragma: no cover
    beta = None


def _float(row: Dict[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        try:
            value = row.get(name)
            if value is None or value == "":
                continue
            out = float(value)
            if math.isfinite(out):
                return out
        except Exception:
            continue
    return default


def _normalise_prob(value: float, default: float = 0.5) -> float:
    if value <= 0:
        return default
    if value > 1.0:
        value = value / 100.0
    return max(0.01, min(0.99, value))


def _regime_prior(row: Dict[str, Any]) -> float:
    bull = _float(row, "regime_distribution_bull", default=0.0)
    bear = _float(row, "regime_distribution_bear", default=0.0)
    direction = str(row.get("options_direction") or row.get("direction") or row.get("primary_direction") or "").upper()
    if direction == "CALL":
        return max(0.40, min(0.62, 0.48 + 0.16 * bull - 0.10 * bear))
    if direction == "PUT":
        return max(0.40, min(0.62, 0.48 + 0.16 * bear - 0.10 * bull))
    return 0.48


def compute_bayesian_edge(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return posterior edge and a 0-100 score.

    Uses a Beta-Binomial shrinkage estimator. If exact actuarial evidence is
    missing, the model falls back to a regime prior instead of zero.
    """
    prior_mean = _normalise_prob(
        _float(row, "actuarial_base_win_rate", "actuarial_regime_win_rate", default=0.0),
        default=_regime_prior(row),
    )
    prior_strength = 40.0
    alpha0 = prior_mean * prior_strength
    beta0 = (1.0 - prior_mean) * prior_strength

    observed_wr = _normalise_prob(
        _float(row, "actuarial_win_rate_10d", "win_rate", "historical_win_rate", default=0.0),
        default=prior_mean,
    )
    sample_count = _float(row, "actuarial_sample_count", "sample_count", "n", default=0.0)
    if sample_count < 0:
        sample_count = 0.0
    wins = observed_wr * sample_count
    losses = max(0.0, sample_count - wins)

    alpha = alpha0 + wins
    beta_param = beta0 + losses
    posterior_mean = alpha / (alpha + beta_param)

    market_prob = abs(_float(row, "contract_delta", "delta", default=0.0))
    market_prob = _normalise_prob(market_prob, default=0.50)
    edge_pp = (posterior_mean - market_prob) * 100.0

    ci_low = None
    ci_high = None
    if beta is not None:
        try:
            ci_low = float(beta.ppf(0.05, alpha, beta_param))
            ci_high = float(beta.ppf(0.95, alpha, beta_param))
        except Exception:
            pass

    # Positive actuarial-vs-market edge is what PHANTOM needs. Penalise wide CI.
    uncertainty_penalty = 0.0
    if ci_low is not None and ci_high is not None:
        uncertainty_penalty = min(20.0, max(0.0, (ci_high - ci_low - 0.20) * 100.0))
    score = max(0.0, min(100.0, 50.0 + edge_pp * 2.0 - uncertainty_penalty))
    if sample_count <= 0:
        score = max(score, 45.0)  # unknown is not zero; it is prior-driven review

    return {
        "bayesian_score": round(score, 2),
        "bayesian_edge_pp": round(edge_pp, 2),
        "posterior_win_prob": round(posterior_mean, 4),
        "market_implied_prob": round(market_prob, 4),
        "posterior_ci_low": round(ci_low, 4) if ci_low is not None else "",
        "posterior_ci_high": round(ci_high, 4) if ci_high is not None else "",
        "actuarial_sample_count_used": round(sample_count, 2),
    }

