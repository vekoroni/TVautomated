"""Transparent daily OHLCV behavioural hypotheses, not order-flow truth."""
from dataclasses import dataclass, asdict, replace
from datetime import date
import math

from .domain import ContractError, Observation, canonical, digest, instant, sha, utc


@dataclass(frozen=True, slots=True)
class DailyBar:
    session: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    available_at: str

    def __post_init__(self):
        if date.fromisoformat(self.session).isoformat() != self.session:
            raise ContractError("invalid bar session")
        for name in ("open", "high", "low", "close", "volume"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ContractError("finite numeric OHLCV required")
        if min(self.open, self.high, self.low, self.close) <= 0 or self.volume < 0:
            raise ContractError("invalid price or volume")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ContractError("OHLC geometry invalid")
        object.__setattr__(self, "available_at", utc(self.available_at))
        if instant(self.available_at).date() < date.fromisoformat(self.session):
            raise ContractError("bar available before its session")


@dataclass(frozen=True, slots=True)
class DailyEvidence:
    ticker: str
    source_id: str
    source_hash: str
    adjustment_basis: str
    bars: tuple[DailyBar, ...]
    expected_sessions: tuple[str, ...]
    cutoff: str
    price_currency: str
    volume_unit: str

    def __post_init__(self):
        from .domain import nonempty
        for value in (self.ticker, self.source_id, self.adjustment_basis):
            nonempty(value, "daily evidence provenance")
        sha(self.source_hash)
        if self.price_currency != "USD" or self.volume_unit != "shares":
            raise ContractError("v1 requires explicit USD prices and share volume")
        object.__setattr__(self, "cutoff", utc(self.cutoff))
        if type(self.bars) is not tuple or not self.bars or any(not isinstance(b, DailyBar) for b in self.bars):
            raise ContractError("immutable completed daily bars required")
        if len(self.bars) > 252:
            raise ContractError("v1 history capped at 252 sessions")
        if type(self.expected_sessions) is not tuple:
            raise ContractError("explicit exchange-session coverage required")
        sessions = tuple(b.session for b in self.bars)
        if sessions != tuple(sorted(set(sessions))) or sessions != self.expected_sessions:
            raise ContractError("unordered, duplicate or missing expected sessions")
        if any(instant(b.available_at) > instant(self.cutoff) for b in self.bars):
            raise ContractError("future bar unavailable at cutoff")

    @property
    def evidence_hash(self):
        return digest(asdict(self))


def analyse_behaviour(evidence: DailyEvidence):
    """Three nonoverlapping four-session windows; fixed exploratory v1 policy.

    Full expected-session list and completed-bar availability are supplied by the
    governed collector. This module does not manufacture an exchange calendar.
    """
    if not isinstance(evidence, DailyEvidence):
        raise ContractError("daily evidence required")
    result = {"schema_version": "behaviour_daily_v1", "source_evidence_hash": evidence.evidence_hash,
              "ticker": evidence.ticker, "authority": "ADVISORY_ONLY", "calibrated": False,
              "status": "INSUFFICIENT_DATA", "control": "UNDETERMINED", "campaign": None,
              "hypotheses": [], "events": [], "metrics": {}, "phase": "NOT_ASSIGNED",
              "limitations": ["OHLCV cannot prove participant positions or absorption.",
                              "Window-based hypotheses, not calibrated probabilities or Wyckoff phase labels.",
                              "No execution permission; unchanged governed thesis remains authoritative."]}
    bars = evidence.bars
    if len(bars) < 12:
        return result
    windows = [bars[-12:-8], bars[-8:-4], bars[-4:]]
    highs = [max(b.high for b in w) for w in windows]
    lows = [min(b.low for b in w) for w in windows]
    ranges = [sum(b.high - b.low for b in w) / 4 for w in windows]
    volumes = [sum(b.volume for b in w) / 4 for w in windows]
    moves = [w[-1].close - w[0].open for w in windows]
    total_range = max(highs) - min(lows)
    net = bars[-1].close - bars[-12].open
    displacement = net / total_range if total_range else 0.0
    rising = lows[0] < lows[1] < lows[2] and highs[0] < highs[1] < highs[2]
    falling = lows[0] > lows[1] > lows[2] and highs[0] > highs[1] > highs[2]
    control = "BUYER_CONTROL_PROXY" if rising and displacement >= .25 else "SELLER_CONTROL_PROXY" if falling and displacement <= -.25 else "CONTESTED"
    metrics = {"range_normalized_displacement": displacement,
               "latest_four_session_range_mean": ranges[2], "prior_four_session_range_mean": ranges[1],
               "latest_four_session_volume_mean": volumes[2], "prior_four_session_volume_mean": volumes[1],
               "support_window_low": lows[2], "resistance_window_high": highs[2]}
    result.update(status="ASSESSED", control=control, metrics=metrics)
    if ranges[1] > 0 and ranges[2] <= .7 * ranges[1]:
        result["hypotheses"].append("RANGE_CONTRACTION_PROXY")
    if volumes[1] > 0 and volumes[2] >= 1.2 * volumes[1] and abs(moves[2]) <= .5 * abs(moves[1]) and moves[1] * moves[2] > 0:
        result["hypotheses"].append("HIGHER_EFFORT_LOWER_DIRECTIONAL_REWARD")
        result["hypotheses"].append("POSSIBLE_OPPOSING_ABSORPTION_NOT_CONFIRMED")
    if control != "CONTESTED" and abs(moves[2]) < abs(moves[1]) < abs(moves[0]):
        result["hypotheses"].append("SHORTENING_THRUST_EXHAUSTION_WARNING")
    # Only fully observed two-session follow-through windows count as attempts.
    failures = {"selling": 0, "buying": 0}
    for i in range(1, len(bars) - 2):
        bar = bars[i]; subsequent = bars[i + 1:i + 3]
        kind = "selling" if bar.close < bars[i-1].close else "buying" if bar.close > bars[i-1].close else None
        recovered = kind == "selling" and any(b.close > bar.high for b in subsequent)
        reversed_up = kind == "buying" and any(b.close < bar.low for b in subsequent)
        if recovered or reversed_up:
            failures[kind] += 1
            result["events"].append({"kind": "FAILED_" + kind.upper() + "_FOLLOW_THROUGH_PROXY",
                                     "session": bar.session, "confirmed_by": subsequent[-1].session})
    metrics.update(failed_selling_attempts=failures["selling"], failed_buying_attempts=failures["buying"])
    # Breakout and later successful retest; don't claim origin from slope alone.
    sign = 1 if control == "BUYER_CONTROL_PROXY" else -1 if control == "SELLER_CONTROL_PROXY" else 0
    if sign:
        for i in range(3, len(bars)-1):
            level = max(b.high for b in bars[i-3:i]) if sign == 1 else min(b.low for b in bars[i-3:i])
            if sign * (bars[i].close-level) <= 0:
                continue
            for j in range(i+1, min(i+4, len(bars))):
                test = bars[j]
                touches = test.low <= level if sign == 1 else test.high >= level
                if touches and sign*(test.close-level) > 0 and all(sign*(b.close-level) > 0 for b in bars[j:]):
                    result["campaign"] = {"origin_session": bars[i].session, "test_session": test.session,
                                          "level": level, "elapsed_sessions": len(bars)-1-i,
                                          "basis": "LATEST_SURVIVING_THREE_SESSION_BREAKOUT_RETEST_PROXY"}
                    break
        result["next_confirmation"] = {"condition": "CLOSE_ABOVE" if sign == 1 else "CLOSE_BELOW",
                                       "level": highs[2] if sign == 1 else lows[2],
                                       "meaning": "conditional continuation evidence, not entry permission"}
        result["warning_condition"] = {"condition": "CLOSE_BELOW" if sign == 1 else "CLOSE_ABOVE",
                                       "level": lows[2] if sign == 1 else highs[2]}
    return result


def attach_behaviour(bundle, evidence):
    if evidence.ticker != bundle.identity.ticker or instant(evidence.cutoff) > instant(bundle.evidence_cutoff_utc):
        raise ContractError("behaviour evidence ticker/cutoff mismatch")
    if any(o.field.startswith("behaviour_") for o in bundle.observations):
        raise ContractError("behaviour already attached")
    report = analyse_behaviour(evidence)
    timestamp = max((b.available_at for b in evidence.bars), key=instant)
    observations = [Observation("behaviour:"+evidence.evidence_hash, "behaviour_report", canonical(report),
                    "structured_json", evidence.source_id, evidence.source_hash, timestamp, timestamp,
                    scope="TICKER", ticker=evidence.ticker, calculation_version="behaviour_daily_v1")]
    units = {"range_normalized_displacement": "ratio", "latest_four_session_range_mean": "USD/share",
             "prior_four_session_range_mean": "USD/share", "latest_four_session_volume_mean": "shares/session",
             "prior_four_session_volume_mean": "shares/session", "support_window_low": "USD/share",
             "resistance_window_high": "USD/share", "failed_selling_attempts": "count", "failed_buying_attempts": "count"}
    for field, value in report["metrics"].items():
        observations.append(Observation("behaviour:"+evidence.evidence_hash+":"+field, "behaviour_"+field,
            value, units[field], evidence.source_id, evidence.source_hash, timestamp, timestamp,
            scope="TICKER", ticker=evidence.ticker, calculation_version="behaviour_daily_v1"))
    return replace(bundle, observations=bundle.observations+tuple(observations))
