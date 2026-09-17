"""Realised volatility estimators (pure; WP1 volatility step, ACK 17 Sep 2026).

All estimators return per-session volatility of log price. Nothing here annualises implicitly:
``annualise`` makes the day-count basis explicit so comparisons with implied volatility state it.
Missing or non-positive prices raise ``MissingPriceData``; they are never replaced by a neutral value.

Estimator formulas (constants are part of the published formulas, not tunable thresholds):
- close-to-close: sample standard deviation of log returns;
- Parkinson (1980): sqrt(mean(ln(H/L)^2) / (4 ln 2));
- Garman-Klass (1980): sqrt(mean(0.5 ln(H/L)^2 - (2 ln 2 - 1) ln(C/O)^2));
- Yang-Zhang (2000): overnight variance + k * open-to-close variance + (1 - k) * Rogers-Satchell,
  k = 0.34 / (1.34 + (n + 1) / (n - 1));
- EWMA (RiskMetrics form): variance_t = decay * variance_(t-1) + (1 - decay) * r_t^2.
"""

from __future__ import annotations

import math
from typing import Sequence

LN2 = math.log(2.0)
YZ_ALPHA = 0.34
YZ_BETA = 1.34


class MissingPriceData(ValueError):
    """Raised when an estimator does not have complete, positive prices."""


def _positive(values: Sequence[float], name: str, minimum: int) -> list[float]:
    out = [float(v) for v in values]
    if len(out) < minimum:
        raise MissingPriceData(f"{name}: need at least {minimum} values, got {len(out)}")
    for value in out:
        if not math.isfinite(value) or value <= 0:
            raise MissingPriceData(f"{name}: non-positive or missing value {value!r}")
    return out


def _sample_variance(values: Sequence[float]) -> float:
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def log_returns(closes: Sequence[float]) -> list[float]:
    prices = _positive(closes, "closes", 2)
    return [math.log(b / a) for a, b in zip(prices, prices[1:])]


def close_to_close(closes: Sequence[float]) -> float:
    returns = log_returns(closes)
    if len(returns) < 2:
        raise MissingPriceData("close_to_close: need at least 3 closes")
    return math.sqrt(_sample_variance(returns))


def parkinson(highs: Sequence[float], lows: Sequence[float]) -> float:
    h, l = _positive(highs, "highs", 1), _positive(lows, "lows", 1)
    if len(h) != len(l):
        raise MissingPriceData("parkinson: highs and lows differ in length")
    return math.sqrt(sum(math.log(a / b) ** 2 for a, b in zip(h, l)) / len(h) / (4 * LN2))


def garman_klass(opens: Sequence[float], highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> float:
    o, h, l, c = (_positive(x, n, 1) for x, n in ((opens, "opens"), (highs, "highs"), (lows, "lows"), (closes, "closes")))
    if not len(o) == len(h) == len(l) == len(c):
        raise MissingPriceData("garman_klass: series differ in length")
    terms = [0.5 * math.log(hi / lo) ** 2 - (2 * LN2 - 1) * math.log(cl / op) ** 2 for op, hi, lo, cl in zip(o, h, l, c)]
    return math.sqrt(max(sum(terms) / len(terms), 0.0))


def yang_zhang(opens: Sequence[float], highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
               previous_closes: Sequence[float]) -> float:
    o, h, l, c, pc = (_positive(x, n, 2) for x, n in ((opens, "opens"), (highs, "highs"), (lows, "lows"),
                                                     (closes, "closes"), (previous_closes, "previous_closes")))
    n = len(o)
    if not n == len(h) == len(l) == len(c) == len(pc):
        raise MissingPriceData("yang_zhang: series differ in length")
    overnight = [math.log(op / p) for op, p in zip(o, pc)]
    open_close = [math.log(cl / op) for op, cl in zip(o, c)]
    rogers_satchell = sum(math.log(hi / cl) * math.log(hi / op) + math.log(lo / cl) * math.log(lo / op)
                          for op, hi, lo, cl in zip(o, h, l, c)) / n
    k = YZ_ALPHA / (YZ_BETA + (n + 1) / (n - 1))
    variance = _sample_variance(overnight) + k * _sample_variance(open_close) + (1 - k) * rogers_satchell
    return math.sqrt(max(variance, 0.0))


def ewma_forecast(returns: Sequence[float], decay: float) -> float:
    values = [float(r) for r in returns]
    if not values or any(not math.isfinite(v) for v in values):
        raise MissingPriceData("ewma_forecast: missing returns")
    variance = values[0] ** 2
    for r in values[1:]:
        variance = decay * variance + (1 - decay) * r * r
    return math.sqrt(variance)


def annualise(per_session_vol: float, sessions_per_year: float) -> float:
    return per_session_vol * math.sqrt(sessions_per_year)
