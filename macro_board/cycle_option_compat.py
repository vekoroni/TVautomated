"""Macro-only adapter for the published shared valuer's stable cost interface.

No shared engine, fee, quote, ticker calculation or rounding rule is changed.
Spread stress is applied BEFORE the shared exit-proceeds zero floor. Entry at
the original ask and both governed fees remain owned by domain.option_valuation.
"""
import math


def net_return_on_premium_raw(model_value, *, bid, ask, exit_spread_multiple=1.0):
    """Unrounded conditional macro return; unknown/invalid evidence stays None."""
    try:
        if isinstance(exit_spread_multiple, bool): raise ValueError
        multiple = float(exit_spread_multiple)
        if not math.isfinite(multiple) or multiple < 0: raise ValueError
    except (TypeError, ValueError):
        raise ValueError('exit_spread_multiple must be finite and non-negative') from None
    try:
        if any(v is None or isinstance(v, bool) for v in (model_value, bid, ask)): return None
        model, quoted_bid, quoted_ask = map(float, (model_value, bid, ask))
        if not all(math.isfinite(v) for v in (model, quoted_bid, quoted_ask)): return None
        if model < 0 or quoted_ask <= 0 or not 0 <= quoted_bid <= quoted_ask: return None
    except (TypeError, ValueError):
        return None
    from domain.option_valuation import entry_cost_usd_per_share, exit_proceeds_usd_per_share
    entry = entry_cost_usd_per_share(quoted_ask)
    if not math.isfinite(entry) or entry <= 0: return None
    # The shared helper already deducts one half-spread. Apply ONLY the extra
    # (or reduced) haircut first, so its fee and zero floor are applied once.
    extra_haircut = (multiple - 1.0) * (quoted_ask - quoted_bid) / 2.0
    proceeds = exit_proceeds_usd_per_share(model - extra_haircut, bid=quoted_bid, ask=quoted_ask)
    return proceeds / entry - 1.0
