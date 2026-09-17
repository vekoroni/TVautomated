"""Signal tickets and their forward track record (pure) — ACK 17 Sep 2026.

A ticket is a complete, fixed recommendation written at issue time from the morning Lab book: expression, limit,
stop, target and hold, valued FORWARD from the price and premium at that moment (a move that has started is
re-priced, not rejected; ACK). Delayed option quotes are brought to the issue instant with delta x the underlying
move since the quote. Tickets are judged by return only; the track record decides — through ``evaluate`` — whether
the recommendations deserve trust. Context fields (O2, O4, H9R) are recorded, never used.

Flow: ``prepare`` (thesis position, contract, delayed-quote adjustment, valuation inputs) -> the caller re-values
with the empirical value model -> ``decide`` (preference and cautious return at today's premium) -> ``rank_tickets``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import hashlib
import math
import re
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np

from .expression import contract_expiry
from .model import Bar

OPTION, SHARES = "OPTION", "SHARES"
LONG, SHORT = "LONG", "SHORT"
MORNING_MODE = "MORNING_VALIDATION"
PATH_OK = "OK"
EXECUTABLE_QUOTE = "EXECUTABLE_QUOTE"
QUOTE_CURRENT_SESSION, QUOTE_PRIOR_SESSION = "QUOTE_CURRENT_SESSION", "QUOTE_PRIOR_SESSION"
ADJUSTED = "DELTA_ADJUSTED_TO_ISSUE"
NOT_ADJUSTED_BAR_MISSING, NOT_ADJUSTED_DELTA_MISSING = "NOT_ADJUSTED_BAR_MISSING", "NOT_ADJUSTED_DELTA_MISSING"
EXITED, PENDING = "EXITED", "PENDING"
CLOSED, MARK_UNAVAILABLE, NOT_FILLED = "CLOSED", "MARK_UNAVAILABLE", "NOT_FILLED"
INSUFFICIENT_EVIDENCE, EVIDENCE_SUPPORTS, NOT_SUPPORTED = "INSUFFICIENT_EVIDENCE", "EVIDENCE_SUPPORTS", "NOT_SUPPORTED"
CALENDAR_DAYS_PER_SESSION = 7.0 / 5.0
OCC = re.compile(r"^[A-Z.]+\d{6}(?P<side>[CP])(?P<strike>\d{8})$")


@dataclass(frozen=True, slots=True)
class SignalSettings:
    signal_version: str
    blocked_final_actions: tuple[str, ...]
    required_price_history_state: str
    min_cautious_return: float
    contract_exit_buffer: int
    contract_multiplier: float
    o4_extreme_quantile: float
    min_closed_signals: int
    min_issue_sessions: int
    interval_z: float
    min_dte_cover: float           # days to expiry / planned hold in calendar days
    min_contract_dte_days: int
    max_out_of_the_money: float    # fraction of spot; beyond this the contract is too far out of the money


def settings_from_snapshot(snapshot) -> SignalSettings:
    def value(key: str):
        return snapshot.get(key).value
    return SignalSettings(
        signal_version=str(value("outcome.signal.version")),
        blocked_final_actions=tuple(str(v) for v in value("outcome.signal.blocked_final_actions")),
        required_price_history_state=str(value("outcome.signal.required_price_history_state")),
        min_cautious_return=float(value("outcome.signal.min_cautious_return")),
        contract_exit_buffer=int(value("outcome.contract_exit_buffer")),
        contract_multiplier=float(value("outcome.contract_multiplier")),
        o4_extreme_quantile=float(value("outcome.signal.o4_extreme_quantile")),
        min_closed_signals=int(value("outcome.signal.min_closed_signals")),
        min_issue_sessions=int(value("outcome.signal.min_issue_sessions")),
        interval_z=float(value("outcome.signal.interval_z")),
        min_dte_cover=float(value("outcome.signal.min_dte_cover")),
        min_contract_dte_days=int(value("outcome.signal.min_contract_dte_days")),
        max_out_of_the_money=float(value("outcome.signal.max_out_of_the_money")),
    )


@dataclass(frozen=True, slots=True)
class SignalTicket:
    ticket_id: str
    signal_version: str
    run_id: str
    evidence_session: date
    issue_session: date
    rank: int
    ticker: str
    direction: str                 # CALL | PUT (thesis direction)
    expression: str                # OPTION | SHARES
    side: str                      # LONG | SHORT (SHARES short for PUT; options are always bought)
    contract_symbol: str | None
    expiry: date | None
    last_usable_session: date | None
    limit_price: float             # options: issue-time mid; shares: issue price moved by half the spread
    scored_entry: float            # options: issue-time ask; shares: the limit
    reference_spot: float          # underlying price at issue
    reference_spot_utc: str | None
    stop_spot: float
    target_spot: float
    hold_sessions: int
    r_cautious: float
    r_central: float | None
    r_upside: float | None
    p_target_first: float | None
    p_stop_first: float | None
    share_spread: float | None
    share_r_cautious: float | None  # comparison only (never decides)
    share_r_central: float | None
    value_model_preference: str | None  # OPTION | SHARES | NEITHER | PREFERENCE_UNAVAILABLE (recorded only)
    quote_bid: float | None        # provider quote as received
    quote_ask: float | None
    quote_timestamp_utc: str | None
    quote_state: str               # QUOTE_CURRENT_SESSION | QUOTE_PRIOR_SESSION (flag, never a gate)
    quote_adjustment_state: str    # DELTA_ADJUSTED_TO_ISSUE | NOT_ADJUSTED_* (flag)
    quote_spot_at_quote: float | None
    quote_delta: float | None
    quote_shift: float | None      # premium shift applied to bid and ask
    iv_source: str                 # LIVE_CONTRACT | EVENING_CONTRACT
    o4_pcr_oi: float | None
    o4_percentile: float | None
    o4_stance: str                 # WITH | AGAINST | MIDDLE | UNAVAILABLE (information only)
    o2_state: str                  # UNAVAILABLE until the pipeline records a same-strike call-put IV spread
    h9r_gap_up_event: bool


@dataclass(frozen=True, slots=True)
class Prepared:
    ticker: str
    direction: str
    contract_symbol: str | None
    strike: float | None
    expiry: date | None
    last_usable_session: date | None
    live_spot: float
    live_spot_utc: str | None
    stop: float
    target: float
    hold_sessions: int
    quote_bid: float | None
    quote_ask: float | None
    quote_timestamp_utc: str | None
    quote_state: str
    adjustment_state: str
    spot_at_quote: float | None
    delta: float | None
    shift: float | None
    bid: float | None              # adjusted to issue
    ask: float | None
    option_executable: bool
    iv: float | None
    iv_source: str
    path_inputs: dict              # keyword arguments for empirical_option_ev.compute_path_expression_ev


def replace_ticket(ticket: SignalTicket, **changes) -> SignalTicket:
    return replace(ticket, **changes)


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _session_of(timestamp: str | None) -> date | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def thesis_position(direction: str, price: float, high: float | None, low: float | None, stop: float,
                    target: float) -> str:
    """Where the thesis stands at issue: already invalidated, already at target, or still open."""
    sign = 1.0 if direction == "CALL" else -1.0
    adverse = [x for x in (price, low if sign > 0 else high) if x is not None]
    favourable = [x for x in (price, high if sign > 0 else low) if x is not None]
    if any(sign * (x - stop) <= 0 for x in adverse):
        return "THESIS_INVALIDATED_INTRADAY"
    if any(sign * (x - target) >= 0 for x in favourable):
        return "TARGET_ALREADY_REACHED"
    return "OPEN"


def adjust_delayed_quote(bid: float, ask: float, delta: float | None, spot_at_quote: float | None,
                         live_spot: float) -> tuple[float, float, float | None, str]:
    """Bring a delayed quote to the issue instant: both sides shift by delta x (live spot - spot at quote time)."""
    if spot_at_quote is None:
        return bid, ask, None, NOT_ADJUSTED_BAR_MISSING
    if delta is None:
        return bid, ask, None, NOT_ADJUSTED_DELTA_MISSING
    shift = delta * (live_spot - spot_at_quote)
    return bid + shift, ask + shift, shift, ADJUSTED


def contract_guard(direction: str, strike: float, spot: float, expiry: date | None, hold_sessions: int,
                   issue_session: date, s: SignalSettings) -> str | None:
    """Named rejection when the contract cannot carry the plan, else None (ACK 17 Sep 2026)."""
    if expiry is None:
        return "CONTRACT_UNPARSEABLE"
    days = (expiry - issue_session).days
    if days < s.min_contract_dte_days:
        return "CONTRACT_DTE_BELOW_FLOOR"
    if days < s.min_dte_cover * hold_sessions * CALENDAR_DAYS_PER_SESSION:
        return "CONTRACT_EXPIRES_BEFORE_PLAN"
    sign = 1.0 if direction == "CALL" else -1.0
    moneyness = sign * (spot - strike) / spot          # negative is out of the money
    if moneyness < -s.max_out_of_the_money:
        return "MONEYNESS_TOO_FAR_OUT_OF_THE_MONEY"
    return None


def prepare(book: Mapping, gate: Mapping | None, valuation: Mapping | None, spot_at_quote: float | None,
            s: SignalSettings, *, issue_session: date, last_usable_for: Callable[[date], date],
            rate: float) -> tuple[str | None, Prepared | None]:
    if _text(book.get("pipeline_mode")) != MORNING_MODE:
        return "BOOK_NOT_MORNING_VALIDATED", None
    if gate is None:
        return "MORNING_GATE_ROW_MISSING", None
    if valuation is None:
        return "VALUATION_MISSING", None
    if _text(book.get("final_action")).upper() in s.blocked_final_actions:
        return "FINAL_ACTION_BLOCKED", None
    direction = _text(book.get("final_direction")).upper()
    if direction not in ("CALL", "PUT"):
        return "DIRECTION_NOT_CALL_OR_PUT", None
    if _text(valuation.get("final_direction") or valuation.get("direction")).upper() != direction:
        return "DIRECTION_CHANGED_SINCE_VALUATION", None
    if _text(valuation.get("l3_price_history_state")) != s.required_price_history_state:
        return "PRICE_HISTORY_NOT_INTACT", None
    stop = _num(valuation.get("invalidation_spot"))
    target = _num(valuation.get("structural_target"))
    if target is None:
        target = _num(valuation.get("target_spot"))
    hold = _num(valuation.get("layer2__recommended_hold_days"))
    if stop is None or target is None or stop <= 0 or target <= 0 or (target - stop) * (1 if direction == "CALL" else -1) <= 0:
        return "STOP_OR_TARGET_UNDEFINED", None
    if hold is None or hold < 1:
        return "HOLD_UNDEFINED", None
    live = _num(gate.get("live_price"))
    if live is None or live <= 0:
        return "LIVE_PRICE_MISSING", None
    position = thesis_position(direction, live, _num(gate.get("live_high")), _num(gate.get("live_low")), stop, target)
    if position != "OPEN":
        return position, None
    forecast = _num(valuation.get("l3_forward_realised_vol_raw"))
    if forecast is None or forecast <= 0:
        forecast = None if _text(valuation.get("l3_forecast_state")).startswith("CLIPPED") else _num(
            valuation.get("l3_forward_realised_vol"))
    if forecast is None or forecast <= 0:
        return "FORECAST_UNAVAILABLE", None

    symbol = _text(gate.get("live_contract_symbol") or book.get("morning_selected_contract_symbol")).upper() or None
    strike = expiry = last_usable = None
    bid = ask = raw_bid = raw_ask = delta = shift = iv = None
    quote_ts = _text(gate.get("selected_quote_timestamp_utc") or gate.get("live_contract_quote_timestamp")) or None
    quote_state = QUOTE_CURRENT_SESSION if _session_of(quote_ts) == issue_session else QUOTE_PRIOR_SESSION
    adjustment, iv_source, executable = NOT_ADJUSTED_BAR_MISSING, "LIVE_CONTRACT", False
    match = OCC.match(symbol or "")
    if match and match["side"] == direction[0]:
        strike = int(match["strike"]) / 1000.0
        expiry = contract_expiry(symbol)
        # The contract must outlive the plan: a contract that expires first is closed at the expiry cap with its
        # time value gone (backtest 17 Sep 2026), which no exit rule can repair.
        guard = contract_guard(direction, strike, live, expiry, int(round(hold)), issue_session, s)
        if guard is not None:
            return guard, None
        last_usable = last_usable_for(expiry) if expiry else None
        raw_bid, raw_ask = _num(gate.get("live_contract_bid")), _num(gate.get("live_contract_ask"))
        delta = _num(gate.get("live_contract_delta"))
        iv = _num(gate.get("live_contract_iv"))
        if (iv is None or iv <= 0) and symbol == _text(valuation.get("contract_occ_symbol")).upper():
            iv, iv_source = _num(valuation.get("contract_iv")), "EVENING_CONTRACT"
        if raw_bid is not None and raw_ask is not None:
            bid, ask, shift, adjustment = adjust_delayed_quote(raw_bid, raw_ask, delta, spot_at_quote, live)
        executable = (_text(gate.get("execution_viability_state")) == EXECUTABLE_QUOTE and expiry is not None
                      and last_usable is not None and last_usable > issue_session)
    side = "call" if direction == "CALL" else "put"
    dte = (expiry - issue_session).days if expiry else None
    path_inputs = dict(side=side, spot=live, strike=strike, dte=dte, bid=bid, ask=ask, iv=iv, rate=rate, target=target,
                       invalidation=stop, hold_sessions=int(round(hold)), forecast_vol=forecast,
                       share_spread=_num(valuation.get("emp_share_spread_estimate")))
    return None, Prepared(
        ticker=_text(book.get("ticker")).upper(), direction=direction, contract_symbol=symbol if match else None,
        strike=strike, expiry=expiry, last_usable_session=last_usable, live_spot=live,
        live_spot_utc=_text(gate.get("live_fetched_at")) or None, stop=stop, target=target,
        hold_sessions=int(round(hold)), quote_bid=raw_bid, quote_ask=raw_ask, quote_timestamp_utc=quote_ts,
        quote_state=quote_state, adjustment_state=adjustment, spot_at_quote=spot_at_quote, delta=delta, shift=shift,
        bid=bid, ask=ask, option_executable=executable, iv=iv, iv_source=iv_source, path_inputs=path_inputs)


def decide(p: Prepared, revaluation: Mapping, s: SignalSettings) -> tuple[str | None, dict]:
    """Forward-looking decision at the issue-time premium: is the remaining move still worth buying the option?

    Option-only for the trial (ACK 17 Sep 2026): the share spread estimate is floored at zero, so the share value is
    not a measured alternative; it is recorded beside the ticket and never issues or vetoes one.
    """
    if _text(revaluation.get("emp_path_quality_flag")) != PATH_OK:
        return "REVALUATION_NOT_OK:" + (_text(revaluation.get("emp_path_quality_flag")) or "MISSING"), {}
    cautious = _num(revaluation.get("emp_path_r_cautious"))
    if cautious is None or cautious <= s.min_cautious_return:
        return "CAUTIOUS_RETURN_NOT_POSITIVE", {}
    if not p.option_executable:
        return "OPTION_NOT_EXECUTABLE", {}
    return None, dict(direction=p.direction, expression=OPTION, side=LONG, contract_symbol=p.contract_symbol,
                      expiry=p.expiry, last_usable_session=p.last_usable_session, limit_price=(p.bid + p.ask) / 2.0,
                      scored_entry=p.ask, reference_spot=p.live_spot, reference_spot_utc=p.live_spot_utc,
                      stop_spot=p.stop, target_spot=p.target, hold_sessions=p.hold_sessions, r_cautious=cautious,
                      r_central=_num(revaluation.get("emp_path_r_central")),
                      r_upside=_num(revaluation.get("emp_path_r_upside")),
                      p_target_first=_num(revaluation.get("emp_path_p_target_first_central")),
                      p_stop_first=_num(revaluation.get("emp_path_p_stop_first_central")),
                      share_spread=p.path_inputs.get("share_spread"),
                      share_r_cautious=_num(revaluation.get("emp_share_r_cautious")),
                      share_r_central=_num(revaluation.get("emp_share_r_central")),
                      value_model_preference=_text(revaluation.get("emp_expression_preference")) or None,
                      quote_bid=p.quote_bid, quote_ask=p.quote_ask, quote_timestamp_utc=p.quote_timestamp_utc,
                      quote_state=p.quote_state, quote_adjustment_state=p.adjustment_state,
                      quote_spot_at_quote=p.spot_at_quote, quote_delta=p.delta, quote_shift=p.shift,
                      iv_source=p.iv_source)


def _percentiles(valuations: Mapping[str, Mapping]) -> dict[str, float]:
    values = {t: _num(v.get("pcr_oi")) for t, v in valuations.items()}
    finite = sorted((x, t) for t, x in values.items() if x is not None)
    if len(finite) == 1:
        return {finite[0][1]: 0.5}
    return {t: i / (len(finite) - 1) for i, (_, t) in enumerate(finite)}


def _o4_stance(direction: str, percentile: float | None, q: float) -> str:
    if percentile is None:
        return "UNAVAILABLE"
    if percentile >= 1 - q:            # high put/call open interest predicted underperformance (O4)
        return "AGAINST" if direction == "CALL" else "WITH"
    if percentile <= q:
        return "WITH" if direction == "CALL" else "AGAINST"
    return "MIDDLE"


def _ticket_id(run_id: str, ticker: str, issue_session: date, expression: str, version: str) -> str:
    key = f"{version}|{run_id}|{issue_session.isoformat()}|{ticker}|{expression}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def rank_tickets(decided: Iterable[tuple[str, dict]], valuations: Mapping[str, Mapping], s: SignalSettings, *,
                 run_id: str, evidence_session: date, issue_session: date,
                 h9r_tickers: frozenset[str] | set[str]) -> list[SignalTicket]:
    percentile = _percentiles(valuations)
    drafts = []
    for ticker, fields in decided:
        pct = percentile.get(ticker)
        drafts.append(dict(fields, ticker=ticker, o4_pcr_oi=_num((valuations.get(ticker) or {}).get("pcr_oi")),
                           o4_percentile=pct, o4_stance=_o4_stance(fields["direction"], pct, s.o4_extreme_quantile),
                           o2_state="UNAVAILABLE", h9r_gap_up_event=ticker in h9r_tickers))
    drafts.sort(key=lambda d: (-d["r_cautious"], d["ticker"]))
    return [SignalTicket(ticket_id=_ticket_id(run_id, d["ticker"], issue_session, d["expression"], s.signal_version),
                         signal_version=s.signal_version, run_id=run_id, evidence_session=evidence_session,
                         issue_session=issue_session, rank=i + 1, **d) for i, d in enumerate(drafts)]


# --- exit and marks -----------------------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SignalExit:
    state: str                     # EXITED | PENDING
    reason: str | None             # STOP | TARGET | HOLD_COMPLETE | CONTRACT_LAST_USABLE
    session: date | None
    level: float | None            # the barrier level touched, if any
    fill_price: float | None       # underlying exit price for shares (stop: worse of level and open)


def plan_exit(t: SignalTicket, bars: Sequence[Bar], as_of: date) -> SignalExit:
    """``bars``: complete daily bars from the issue session onward, one per session, in order."""
    sign = 1.0 if t.direction == "CALL" else -1.0
    usable = [b for b in bars if t.issue_session <= b.session <= as_of]
    if not usable or usable[0].session != t.issue_session:
        return SignalExit(PENDING, None, None, None, None)
    issue = usable[0]
    if sign * (issue.close - t.stop_spot) <= 0:
        return SignalExit(EXITED, "STOP", issue.session, t.stop_spot, issue.close)
    for k, bar in enumerate(usable[1:], start=1):
        adverse = bar.low if sign > 0 else bar.high
        favourable = bar.high if sign > 0 else bar.low
        if sign * (adverse - t.stop_spot) <= 0:
            fill = min(t.stop_spot, bar.open) if sign > 0 else max(t.stop_spot, bar.open)
            return SignalExit(EXITED, "STOP", bar.session, t.stop_spot, fill)
        if sign * (favourable - t.target_spot) >= 0:
            return SignalExit(EXITED, "TARGET", bar.session, t.target_spot, t.target_spot)
        if t.last_usable_session is not None and bar.session >= t.last_usable_session:
            return SignalExit(EXITED, "CONTRACT_LAST_USABLE", bar.session, None, bar.close)
        if k >= t.hold_sessions:
            return SignalExit(EXITED, "HOLD_COMPLETE", bar.session, None, bar.close)
    return SignalExit(PENDING, None, None, None, None)


@dataclass(frozen=True, slots=True)
class SignalOutcome:
    state: str                     # CLOSED | MARK_UNAVAILABLE | NOT_FILLED | PENDING
    exit_session: date | None
    exit_reason: str | None
    entry_price: float | None
    exit_price: float | None
    return_on_capital: float | None
    pnl_per_unit: float | None     # per contract (x multiplier) or per share
    reason: str = ""


def mark_signal(t: SignalTicket, plan: SignalExit, bid: float | None, multiplier: float = 100.0) -> SignalOutcome:
    """Options exit at the exit session's end-of-day bid; shares (entered at issue) exit at the plan's fill less half
    the spread."""
    if plan.state == PENDING:
        return SignalOutcome(PENDING, None, None, t.scored_entry, None, None, None)
    if t.expression == OPTION:
        if bid is None:
            return SignalOutcome(MARK_UNAVAILABLE, plan.session, plan.reason, t.scored_entry, None, None, None,
                                 f"no chain row for {t.contract_symbol} on {plan.session.isoformat()}")
        return SignalOutcome(CLOSED, plan.session, plan.reason, t.scored_entry, bid, bid / t.scored_entry - 1.0,
                             (bid - t.scored_entry) * multiplier)
    half = (t.share_spread or 0.0) / 2.0
    if t.side == LONG:
        exit_price = plan.fill_price * (1 - half)
        pnl = exit_price - t.limit_price
    else:
        exit_price = plan.fill_price * (1 + half)
        pnl = t.limit_price - exit_price
    return SignalOutcome(CLOSED, plan.session, plan.reason, t.limit_price, exit_price, pnl / t.limit_price, pnl)


# --- track record -------------------------------------------------------------------------------------------------

def max_drawdown(returns_in_order: Sequence[float]) -> float:
    equity, peak, worst = 1.0, 1.0, 0.0
    for r in returns_in_order:
        equity *= 1.0 + r
        peak = max(peak, equity)
        worst = max(worst, 1.0 - equity / peak)
    return worst


def evaluate(items: Iterable[tuple[date, float]], s: SignalSettings) -> dict:
    """items: (issue session, return on capital) for closed signals. Interval clustered by issue session."""
    rows = [(d, float(r)) for d, r in items if r is not None and math.isfinite(float(r))]
    sessions = sorted({d for d, _ in rows})
    out = {"closed": len(rows), "issue_sessions": len(sessions), "mean": None, "low": None, "high": None,
           "hit_rate": None, "avg_win": None, "avg_loss": None, "worst": None, "verdict": INSUFFICIENT_EVIDENCE}
    if not rows:
        return out
    values = np.array([r for _, r in rows])
    wins, losses = values[values > 0], values[values <= 0]
    out.update(mean=float(values.mean()), hit_rate=float((values > 0).mean()), worst=float(values.min()),
               avg_win=float(wins.mean()) if wins.size else None, avg_loss=float(losses.mean()) if losses.size else None)
    if len(rows) < s.min_closed_signals or len(sessions) < s.min_issue_sessions:
        return out
    residual = values - values.mean()
    sums: dict[date, float] = {}
    for (d, _), e in zip(rows, residual):
        sums[d] = sums.get(d, 0.0) + e
    g = np.array(list(sums.values()))
    se = math.sqrt((len(g) / (len(g) - 1)) * float(g @ g)) / len(values)
    out["low"], out["high"] = out["mean"] - s.interval_z * se, out["mean"] + s.interval_z * se
    out["verdict"] = EVIDENCE_SUPPORTS if out["low"] > 0 else NOT_SUPPORTED
    return out
