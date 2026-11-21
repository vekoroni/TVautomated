"""Reachable advisory scale; not a probability or promotion calibration."""
import math

SCORE_VERSION='phantom_noisy_or_ceiling_normalised_v2'
PROMOTIONS_ENABLED=False

def legacy_composite(scores,weights):
    product=1.
    for key,weight in weights.items():
        if not math.isfinite(weight) or not 0<=weight<=1:raise ValueError('Invalid Phantom weight')
        try:value=float(scores.get(key))
        except (ValueError,TypeError):value=0.
        if not math.isfinite(value):value=0.
        value=max(0.,min(1.,value/100.))
        product*=1-weight*value
    return max(0.,min(100.,100*(1-product)))

def ceiling(weights):return legacy_composite({k:100 for k in weights},weights)

def composite(scores,weights):
    maximum=ceiling(weights)
    # Use the full configured ceiling, never the available-component ceiling.
    return max(0.,min(100.,100*legacy_composite(scores,weights)/maximum)) if maximum>0 else 0.

def qualified_score(value):
    if value is None or isinstance(value,bool):return None
    try:n=float(value)
    except (ValueError,TypeError):return None
    return n if math.isfinite(n) and 0<=n<=100 else None
