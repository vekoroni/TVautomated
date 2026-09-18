"""Application service: ingest recorded books, score outcomes, build the report."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from avshunter.config import ConfigSnapshot
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session

import numpy as np

from . import estimators
from .adapters import books, chains, macro, prices, storage
from .base_rate import BASE_RATE_VERSION, build_panel, matched_incidence, panel_atr
from .conditions import CONDITION_VERSION, ConditionSettings, macro_condition, market_condition
from . import hypotheses as hyp
from .expression import EXPRESSION_VERSION, ExitPlan, contract_expiry, mark_expression, plan_exit
from .geometry import classify
from .model import Bar, ContractState, OutcomeState, TargetState, UnderlyingOutcome
from .passage import evaluate_passage
from .records import prediction_id, provenance_class, resolve_evidence_session

SCORER_VERSION = "c12-outcome-scorer-v1.0.0"

# Policies implemented by this scorer version; configuration must match exactly.
IMPLEMENTED_POLICIES = {
    "outcome.ambiguous_policy": "STOP_FIRST_FOR_ESTIMATION",
    "outcome.stop_fill_policy": "WORSE_OF_LEVEL_AND_OPEN",
    "outcome.first_session_provenance_cutoff": "SESSION_1_CLOSE",
}

# Barrier distances for the matched base rate are measured in ATR over ``outcome.atr_period``.
IMPLEMENTED_DISTANCE_UNIT_PREFIX = "ATR"


def require_implemented_policies(snapshot: ConfigSnapshot) -> None:
    mismatches = {
        key: snapshot.get(key).value
        for key, implemented in IMPLEMENTED_POLICIES.items()
        if snapshot.get(key).value != implemented
    }
    if mismatches:
        raise ValueError(f"configuration requests policies {SCORER_VERSION} does not implement: {mismatches}")
    unit = str(snapshot.get("outcome.base_rate_distance_unit").value)
    expected = f"{IMPLEMENTED_DISTANCE_UNIT_PREFIX}{int(snapshot.get('outcome.atr_period').value)}"
    if unit != expected:
        raise ValueError(f"outcome.base_rate_distance_unit {unit!r} does not match outcome.atr_period ({expected})")


def sessions_before(end: date, count: int) -> date:
    """The session ``count`` sessions before ``end``."""
    day = end
    for _ in range(count):
        day = previous_xnys_session(day)
    return day


def sessions_between(start: date, end: date) -> list[date]:
    out, day = [], start
    while day <= end:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def sessions_after(start: date, end: date, limit: int) -> list[date]:
    out, day = [], start
    while len(out) < limit:
        day += timedelta(days=1)
        if day > end:
            break
        if is_xnys_session(day):
            out.append(day)
    return out


def ingest(connection: sqlite3.Connection, runs_dir: Path, now: datetime) -> dict:
    counts = defaultdict(int)
    for path in books.discover_books(runs_dir):
        counts["books"] += 1
        predictions, sightings = [], []
        for row in books.read_book(path):
            geometry = classify(row.direction, row.reference, row.invalidation, row.target, row.contract_symbol)
            evidence = resolve_evidence_session(row.thesis_id, row.run_meta, row.run_id)
            pid = prediction_id(row.ticker, geometry, evidence.session)
            first = sessions_after(evidence.session, date.max - timedelta(days=10), 1)[0] if evidence.session else None
            provenance = (
                provenance_class(row.book_mtime_utc, evidence.session, first) if evidence.session else "UNRESOLVED"
            )
            predictions.append({
                "prediction_id": pid, "ticker": row.ticker,
                "direction": geometry.direction.value if geometry.direction else None,
                "direction_text": geometry.direction_text,
                "evidence_session": evidence.session.isoformat() if evidence.session else None,
                "evidence_session_source": evidence.source,
                "reference_price": geometry.reference_price, "invalidation_price": geometry.invalidation_price,
                "invalidation_state": geometry.invalidation_state.value,
                "target_price": geometry.target_price, "target_state": geometry.target_state.value,
                "contract_symbol": geometry.contract_symbol, "contract_state": geometry.contract_state.value,
                "first_run_id": row.run_id, "provenance_class": provenance,
                "scorer_version": SCORER_VERSION, "recorded_at_utc": now.isoformat(),
            })
            sightings.append({
                "prediction_id": pid, "run_id": row.run_id,
                "pipeline_mode": row.run_meta.get("pipeline_mode"), "run_condition": row.run_meta.get("run_condition"),
                "book_path": row.book_path, "book_sha256": row.book_sha256,
                "book_mtime_utc": row.book_mtime_utc.isoformat(),
                "entry_bid": row.entry_bid, "entry_ask": row.entry_ask,
                "labels_json": storage.labels_json(row.labels), "ingested_at_utc": now.isoformat(),
            })
        counts["rows"] += len(predictions)
        counts["new_predictions"] += storage.insert_ignore(connection, "prediction_records", predictions)
        counts["new_sightings"] += storage.insert_ignore(connection, "prediction_sightings", sightings)
    connection.commit()
    return dict(counts)


def score(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, now: datetime,
          price_db: Path = prices.DEFAULT_PRICE_DB) -> dict:
    require_implemented_policies(snapshot)
    window = int(snapshot.get("outcome.window_sessions").value)
    terminal = {
        row[0] for row in connection.execute(
            "SELECT prediction_id FROM latest_underlying_outcomes WHERE scorer_version = ? AND terminal = 1",
            (SCORER_VERSION,),
        )
    }
    rows = connection.execute(
        "SELECT prediction_id, ticker, direction_text, evidence_session, reference_price, invalidation_price, "
        "target_price, contract_symbol FROM prediction_records WHERE evidence_session IS NOT NULL AND evidence_session < ?",
        (as_of.isoformat(),),
    ).fetchall()
    pending = [r for r in rows if r[0] not in terminal]
    if not pending:
        return {"pending": 0, "scored": 0}
    earliest = min(date.fromisoformat(r[3]) for r in pending)
    bars_by_ticker = prices.load_bars({r[1] for r in pending}, earliest, as_of, price_db)
    indexed: dict[str, dict[date, Bar]] = {t: {b.session: b for b in bars} for t, bars in bars_by_ticker.items()}
    out_rows = []
    counts = defaultdict(int)
    for pid, ticker, direction_text, evidence, reference, invalidation, target, contract in pending:
        geometry = classify(direction_text, reference, invalidation, target, contract)
        window_sessions = sessions_after(date.fromisoformat(evidence), as_of, window)
        outcome: UnderlyingOutcome = evaluate_passage(geometry, window_sessions, indexed.get(ticker, {}), window)
        counts[outcome.state.value] += 1
        out_rows.append(storage.outcome_row(pid, as_of, SCORER_VERSION, outcome, snapshot.snapshot_id, now))
    written = storage.insert_ignore(connection, "underlying_outcomes", out_rows)
    connection.commit()
    return {"pending": len(pending), "written": written, "states": dict(counts)}


# --- matched base rate (P0-8 §5.4) ---------------------------------------------------

def score_base_rates(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, now: datetime,
                     price_db: Path = prices.DEFAULT_PRICE_DB) -> dict:
    require_implemented_policies(snapshot)
    window = int(snapshot.get("outcome.window_sessions").value)
    atr_period = int(snapshot.get("outcome.atr_period").value)
    complete = {
        row[0] for row in connection.execute(
            "SELECT prediction_id FROM latest_base_rate_outcomes WHERE base_rate_version = ? "
            "AND (observed_sessions >= ? OR state != 'OK')", (BASE_RATE_VERSION, window))
    }
    rows = connection.execute(
        "SELECT prediction_id, ticker, direction_text, evidence_session, reference_price, invalidation_price, "
        "target_price FROM prediction_records WHERE evidence_session IS NOT NULL AND evidence_session < ?",
        (as_of.isoformat(),),
    ).fetchall()
    pending = [r for r in rows if r[0] not in complete]
    if not pending:
        return {"pending": 0, "written": 0}
    earliest = min(date.fromisoformat(r[3]) for r in pending)
    start = sessions_before(earliest, atr_period + 1)
    panel = build_panel(prices.load_all_bars(start, as_of, price_db), sessions_between(start, as_of))
    column = {ticker: index for index, ticker in enumerate(panel.tickers)}
    atr_cache: dict[int, np.ndarray] = {}
    out_rows, counts = [], defaultdict(int)
    for pid, ticker, direction_text, evidence, reference, invalidation, target in pending:
        geometry = classify(direction_text, reference, invalidation, target, None)
        evidence_day = date.fromisoformat(evidence)
        observed = len(sessions_after(evidence_day, as_of, window))
        row = {"prediction_id": pid, "as_of_session": as_of.isoformat(), "base_rate_version": BASE_RATE_VERSION,
               "observed_sessions": observed, "target_atr": None, "stop_atr": None, "atr": None,
               "universe": None, "excluded": None, "target_fractions_json": None, "stop_fractions_json": None,
               "config_snapshot_id": snapshot.snapshot_id, "scored_at_utc": now.isoformat()}
        index = panel.index_of(evidence_day)
        if not geometry.scorable:
            state = "NOT_SCORABLE"
        elif index is None or ticker not in column:
            state = "NO_PRICE_HISTORY"
        else:
            if index not in atr_cache:
                atr_cache[index] = panel_atr(panel, index, atr_period)
            ticker_atr = atr_cache[index][column[ticker]]
            if not np.isfinite(ticker_atr):
                state = "NO_ATR"
            else:
                state = "OK"
                stop_atr = abs(geometry.reference_price - geometry.invalidation_price) / ticker_atr
                target_atr = (abs(geometry.target_price - geometry.reference_price) / ticker_atr
                              if geometry.target_state is TargetState.LEVEL else None)
                matched = matched_incidence(geometry.direction, target_atr, stop_atr, panel, index, observed,
                                            atr_cache[index])
                row.update({"target_atr": target_atr, "stop_atr": float(stop_atr), "atr": float(ticker_atr),
                            "universe": matched.universe, "excluded": matched.excluded,
                            "target_fractions_json": json.dumps(matched.target_fractions),
                            "stop_fractions_json": json.dumps(matched.stop_fractions)})
        row["state"] = state
        counts[state] += 1
        out_rows.append(row)
    written = storage.insert_ignore(connection, "base_rate_outcomes", out_rows)
    connection.commit()
    return {"pending": len(pending), "written": written, "states": dict(counts)}


# --- conditions (P0-8 §6a; analysis only) -------------------------------------------

def condition_settings(snapshot: ConfigSnapshot) -> ConditionSettings:
    def value(key: str):
        return snapshot.get(key).value
    return ConditionSettings(
        market_ticker=str(value("outcome.condition.market_ticker")),
        trend_short_sessions=int(value("outcome.condition.trend_short_sessions")),
        trend_long_sessions=int(value("outcome.condition.trend_long_sessions")),
        vol_sessions=int(value("outcome.condition.vol_sessions")),
        vol_lookback_sessions=int(value("outcome.condition.vol_lookback_sessions")),
        breadth_sessions=int(value("outcome.condition.breadth_sessions")),
        drawdown_lookback_sessions=int(value("outcome.condition.drawdown_lookback_sessions")),
        vol_state_bands=tuple(float(v) for v in value("outcome.condition.vol_state_bands")),
        breadth_state_bands=tuple(float(v) for v in value("outcome.condition.breadth_state_bands")),
    )


def record_conditions(connection: sqlite3.Connection, runs_dir: Path, snapshot: ConfigSnapshot, now: datetime,
                      price_db: Path = prices.DEFAULT_PRICE_DB) -> dict:
    settings = condition_settings(snapshot)
    rows = connection.execute(
        "SELECT p.prediction_id, p.evidence_session, p.first_run_id FROM prediction_records p "
        "WHERE p.evidence_session IS NOT NULL AND NOT EXISTS (SELECT 1 FROM condition_records c "
        "WHERE c.prediction_id = p.prediction_id AND c.condition_version = ?)", (CONDITION_VERSION,),
    ).fetchall()
    if not rows:
        return {"pending": 0, "written": 0}
    evidence_days = sorted({date.fromisoformat(r[1]) for r in rows})
    earliest, latest = evidence_days[0], evidence_days[-1]
    market_start = sessions_before(earliest, settings.market_history_sessions)
    market_bars = prices.load_bars({settings.market_ticker}, market_start, latest, price_db).get(
        settings.market_ticker.upper(), [])
    breadth_start = sessions_before(earliest, settings.breadth_sessions)
    panel = build_panel(prices.load_all_bars(breadth_start, latest, price_db), sessions_between(breadth_start, latest))
    markets = {}
    for day in evidence_days:
        closes = [bar.close for bar in market_bars if bar.session <= day]
        index = panel.index_of(day)
        panel_closes = panel.close[:index + 1] if index is not None else np.empty((0, len(panel.tickers)))
        markets[day] = market_condition(closes, panel_closes, settings)
    snapshots: dict[str, dict | None] = {}
    out_rows, counts = [], defaultdict(int)
    for pid, evidence, run_id in rows:
        day = date.fromisoformat(evidence)
        if run_id not in snapshots:
            snapshots[run_id] = macro.read_run_snapshot(runs_dir, run_id)
        macro_view = macro_condition(snapshots[run_id], run_id, day)
        market = markets[day]
        counts[f"macro_{macro_view.macro_freshness}"] += 1
        counts[f"trend_{market.market_trend_state}"] += 1
        out_rows.append({
            "prediction_id": pid, "condition_version": CONDITION_VERSION,
            "macro_source": macro_view.macro_source, "macro_run_id": macro_view.macro_run_id,
            "macro_as_of_utc": macro_view.macro_as_of_utc, "macro_report_date": macro_view.macro_report_date,
            "macro_freshness": macro_view.macro_freshness, "macro_lag_sessions": macro_view.macro_lag_sessions,
            **{name: _scalar(macro_view.fields[name]) for name in macro_view.fields},
            "ticker_sector": None, "sector_alignment": "MISSING_TICKER_SECTOR",
            "market_trend_state": market.market_trend_state, "market_vol_percentile": market.market_vol_percentile,
            "market_vol_state": market.market_vol_state, "market_breadth": market.market_breadth,
            "market_breadth_state": market.market_breadth_state, "market_drawdown_pct": market.market_drawdown_pct,
            "config_snapshot_id": snapshot.snapshot_id, "recorded_at_utc": now.isoformat(),
        })
    written = storage.insert_ignore(connection, "condition_records", out_rows)
    connection.commit()
    return {"pending": len(rows), "written": written, "labels": dict(counts)}


def _scalar(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


# --- expression marks (P0-8 §3.3, §5.3) ---------------------------------------------

def last_usable_session(expiry: date, buffer_sessions: int) -> date:
    session = expiry if is_xnys_session(expiry) else previous_xnys_session(expiry)
    return sessions_before(session, buffer_sessions)


def quotes_bid_unused(symbol: str, session: date) -> None:
    raise AssertionError("invalid contracts are never marked")


def score_expressions(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, now: datetime,
                      chain_db: Path = chains.DEFAULT_CHAIN_DB) -> dict:
    window = int(snapshot.get("outcome.window_sessions").value)
    buffer_sessions = int(snapshot.get("outcome.contract_exit_buffer").value)
    multiplier = float(snapshot.get("outcome.contract_multiplier").value)
    rows = connection.execute(
        """
        SELECT p.prediction_id, p.ticker, p.direction_text, p.evidence_session, p.reference_price,
               p.invalidation_price, p.target_price, p.contract_symbol,
               o.state, o.resolution_session, o.return_to_exit_pct,
               (SELECT s.entry_ask FROM prediction_sightings s WHERE s.prediction_id = p.prediction_id
                ORDER BY s.book_mtime_utc LIMIT 1) AS entry_ask
        FROM prediction_records p
        LEFT JOIN latest_underlying_outcomes o ON o.prediction_id = p.prediction_id AND o.scorer_version = ?
        WHERE p.evidence_session IS NOT NULL AND p.evidence_session < ? AND p.contract_state != 'MISSING'
          AND NOT EXISTS (SELECT 1 FROM expression_outcomes e WHERE e.prediction_id = p.prediction_id
                          AND e.expression_version = ?)
        """,
        (SCORER_VERSION, as_of.isoformat(), EXPRESSION_VERSION),
    ).fetchall()
    quotes = chains.ChainQuotes(chain_db)
    out_rows, counts = [], defaultdict(int)
    try:
        for (pid, ticker, direction_text, evidence, reference, invalidation, target, contract,
             state, resolution, underlying_return, entry_ask) in rows:
            geometry = classify(direction_text, reference, invalidation, target, contract)
            evidence_day = date.fromisoformat(evidence)
            symbol = geometry.contract_symbol or (str(contract).strip().upper() if contract else None)
            expiry = contract_expiry(symbol) if symbol else None
            underlying_state = OutcomeState(state) if state else None
            if geometry.contract_state is not ContractState.VALID:
                last_usable = None
                outcome = mark_expression(geometry.contract_state, symbol, entry_ask, ExitPlan(None, "PENDING"),
                                          quotes_bid_unused, multiplier)
            elif expiry is None:
                counts["UNPARSEABLE_EXPIRY"] += 1
                continue
            else:
                last_usable = last_usable_session(expiry, buffer_sessions)
                plan = plan_exit(underlying_state, resolution, sessions_after(evidence_day, date.max, window),
                                 last_usable, evidence_day, as_of)
                evidence_ask = quotes.ask(ticker, symbol, evidence_day)
                outcome = mark_expression(geometry.contract_state, symbol, entry_ask, plan,
                                          lambda sym, day, t=ticker: quotes.bid(t, sym, day), multiplier,
                                          evidence_chain_ask=evidence_ask)
            counts[outcome.state] += 1
            if outcome.state == "PENDING":
                continue
            evidence_ask = quotes.ask(ticker, symbol, evidence_day) if geometry.contract_state is ContractState.VALID else None
            out_rows.append({
                "prediction_id": pid, "expression_version": EXPRESSION_VERSION, "as_of_session": as_of.isoformat(),
                "state": outcome.state, "contract_symbol": symbol,
                "expiry": expiry.isoformat() if expiry else None,
                "last_usable_session": last_usable.isoformat() if last_usable else None,
                "exit_session": outcome.exit_session.isoformat() if outcome.exit_session else None,
                "exit_reason": outcome.exit_reason, "entry_ask": outcome.entry_ask, "entry_source": outcome.entry_source,
                "exit_bid": outcome.exit_bid, "pnl_per_contract": outcome.pnl_per_contract,
                "return_on_premium": outcome.return_on_premium, "evidence_session_chain_ask": evidence_ask,
                "underlying_state": state, "underlying_return_to_exit_pct": underlying_return,
                "reason": outcome.reason, "config_snapshot_id": snapshot.snapshot_id, "scored_at_utc": now.isoformat(),
            })
    finally:
        quotes.close()
    written = storage.insert_ignore(connection, "expression_outcomes", out_rows)
    connection.commit()
    return {"candidates": len(rows), "written": written, "states": dict(counts)}


# --- forward hypothesis tests (ACK 17 Sep 2026; plan A Addendum 2) --------------------

def track_hypotheses(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, now: datetime,
                     price_db: Path = prices.DEFAULT_PRICE_DB, settings_override=None) -> dict:
    s = settings_override or hyp.settings_from_snapshot(snapshot)
    if as_of < s.forward_start:
        return {"hypothesis_id": s.hypothesis_id, "new_events": 0, "new_outcomes": 0, "reason": "BEFORE_FORWARD_START"}
    start = sessions_before(s.forward_start, s.lookback_sessions + 1)
    panel = prices.load_price_panel(start, as_of, price_db)
    events, last = [], {}
    for i, session in enumerate(panel.sessions):
        if session < s.forward_start:
            continue
        found = hyp.detect_events(panel, i, s, last)
        for event in found:
            last[event.ticker] = event.event_session
        events.extend(found)
    event_rows = [{"hypothesis_id": s.hypothesis_id, "ticker": e.ticker, "event_session": e.event_session.isoformat(),
                   "direction": e.direction, "held": e.held, "gap_atr": e.gap_atr, "entry_close": e.entry_close,
                   "share_spread": e.share_spread, "config_snapshot_id": snapshot.snapshot_id,
                   "recorded_at_utc": now.isoformat()} for e in events]
    new_events = storage.insert_ignore(connection, "hypothesis_events", event_rows)
    stored = connection.execute(
        "SELECT ticker, event_session, direction, held, gap_atr, entry_close, share_spread FROM hypothesis_events "
        "WHERE hypothesis_id = ?", (s.hypothesis_id,)).fetchall()
    done = {(r[0], r[1], r[2]) for r in connection.execute(
        "SELECT ticker, event_session, horizon FROM hypothesis_outcomes WHERE hypothesis_id = ?", (s.hypothesis_id,))}
    outcome_rows = []
    for ticker, session, direction, held, gap_atr, entry_close, spread in stored:
        event = hyp.GapEvent(ticker, date.fromisoformat(session), direction, held, gap_atr, entry_close, spread)
        for horizon in s.horizons:
            if (ticker, session, horizon) in done:
                continue
            outcome = hyp.score_outcome(panel, event, horizon, s)
            if outcome is None:
                continue
            outcome_rows.append({"hypothesis_id": s.hypothesis_id, "ticker": ticker, "event_session": session,
                                 "horizon": horizon, "exit_session": outcome.exit_session.isoformat(),
                                 "raw_return": outcome.raw_return, "universe_median": outcome.universe_median,
                                 "net_return": outcome.net_return, "state": outcome.state,
                                 "config_snapshot_id": snapshot.snapshot_id, "scored_at_utc": now.isoformat()})
    new_outcomes = storage.insert_ignore(connection, "hypothesis_outcomes", outcome_rows)
    connection.commit()
    return {"hypothesis_id": s.hypothesis_id, "events_detected": len(events), "new_events": new_events,
            "new_outcomes": new_outcomes}


def _hypothesis_section(connection: sqlite3.Connection, snapshot: ConfigSnapshot) -> list[str]:
    s = hyp.settings_from_snapshot(snapshot)
    rows = connection.execute(
        "SELECT e.direction, o.horizon, e.event_session, o.net_return, e.share_spread FROM hypothesis_outcomes o "
        "JOIN hypothesis_events e USING (hypothesis_id, ticker, event_session) WHERE o.hypothesis_id = ? AND o.state = ?",
        (s.hypothesis_id, hyp.SCORED)).fetchall()
    lines = ["", "## Forward hypothesis tests", "",
             f"`{s.hypothesis_id}` — pre-registered forward test from {s.forward_start.isoformat()} "
             f"(SIGNAL_RESEARCH_PLAN_A.md Addendum 2). Primary: {s.primary_direction} events, {s.primary_horizon}-session "
             f"net return expected negative; verdict needs >= {s.min_event_dates} event dates and >= {s.min_events} events, "
             f"clustered t <= {s.pass_t} and |mean| above the median share spread. Measurement only.", "",
             "| Direction | Horizon | Events | Event dates | Mean net (bps) | Clustered t | Median share spread (bps) | Verdict |",
             "|---|---|---|---|---|---|---|---|"]
    for direction in (hyp.EVENT_UP, hyp.EVENT_DOWN):
        for horizon in s.horizons:
            items = [(r[2], r[3], r[4]) for r in rows if r[0] == direction and r[1] == horizon]
            result = hyp.evaluate(items, s)
            primary = direction == s.primary_direction and horizon == s.primary_horizon
            verdict = result["verdict"] if primary else "SECONDARY"
            mean = "n/a" if result["mean"] is None else f"{result['mean'] * 1e4:.1f}"
            t_stat = "n/a" if result["t"] is None else f"{result['t']:.2f}"
            spread = "n/a" if result["median_share_spread"] is None else f"{result['median_share_spread'] * 1e4:.1f}"
            lines.append(f"| {direction} | {horizon} | {result['events']} | {result['event_dates']} | {mean} | "
                         f"{t_stat} | {spread} | {verdict} |")
    return lines


# --- report --------------------------------------------------------------------

GROUP_LABELS = ("tier", "lab_verdict", "final_action", "thesis_state", "ev3_absolute_state")
CONDITION_GROUPS = ("regime_label", "macro_freshness", "risk_on_off_switch", "market_trend_state",
                    "market_vol_state", "market_breadth_state")


def _outcome_from_row(row: sqlite3.Row) -> UnderlyingOutcome:
    return UnderlyingOutcome(
        OutcomeState(row["state"]), row["sessions_observed"], row["resolution_session"], None,
        row["exit_price"], row["return_to_exit_pct"], row["r_multiple"], row["mfe_pct"], row["mae_pct"], row["reason"] or "",
    )


def _pct(values) -> str:
    return " / ".join("n/a" if v != v else f"{v:.1%}" for v in values)


def _signed(values) -> str:
    return " / ".join("n/a" if v != v else f"{v:+.1%}" for v in values)


def _block_mean_interval(values_by_block: dict[str, list[float]], resamples: int, low_q: float, high_q: float):
    blocks = sorted(values_by_block)
    sums = np.array([sum(values_by_block[b]) for b in blocks])
    counts = np.array([len(values_by_block[b]) for b in blocks], dtype=float)
    point = float(sums.sum() / counts.sum())
    rng = np.random.default_rng(0)
    draws = rng.integers(0, len(blocks), size=(resamples, len(blocks)))
    multiplicity = np.stack([np.bincount(row, minlength=len(blocks)) for row in draws]).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        means = (multiplicity @ sums) / (multiplicity @ counts)
    low, high = np.nanquantile(means, [low_q, high_q])
    return float(low), point, float(high)


def _expression_section(connection, resamples, low_q, high_q, min_sessions, summary) -> list[str]:
    rows = connection.execute(
        """
        SELECT e.*, p.evidence_session, p.direction, p.target_state,
               (SELECT labels_json FROM prediction_sightings s WHERE s.prediction_id = p.prediction_id
                ORDER BY s.book_mtime_utc LIMIT 1) AS first_labels
        FROM expression_outcomes e JOIN prediction_records p USING (prediction_id)
        WHERE e.expression_version = ? AND p.provenance_class = 'RECORDED_AT_RUN'
        """, (EXPRESSION_VERSION,)).fetchall()
    lines = ["", "## Expressions: option contract vs underlying (headline predictions)", "",
             "Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, "
             "session-20 timeout, or the contract's last usable session). Underlying return is the same "
             "prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.", ""]
    states = defaultdict(int)
    for row in rows:
        states[row["state"]] += 1
    lines.append("- **expression_state**: " + ", ".join(f"{k} {v}" for k, v in sorted(states.items())))
    reasons = defaultdict(int)
    for row in rows:
        if row["state"] == "MARKED":
            reasons[row["exit_reason"]] += 1
    lines.append("- **exit_reason (marked)**: " + ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    lines += ["", "| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | "
              "Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |",
              "|---|---|---|---|---|---|---|---|"]
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        if row["state"] != "MARKED":
            continue
        labels = json.loads(row["first_labels"] or "{}")
        keys = ["ALL", f"entry_source={row['entry_source']}", f"direction={row['direction']}", f"target_state={row['target_state']}",
                f"underlying_state={row['underlying_state']}", f"exit_reason={row['exit_reason']}"]
        keys += [f"{label}={labels[label]}" for label in ("tier", "lab_verdict") if labels.get(label) not in (None, "")]
        for key in keys:
            groups[key].append(row)
    for group, items in sorted(groups.items()):
        by_block, underlying = defaultdict(list), []
        for row in items:
            by_block[row["evidence_session"]].append(row["return_on_premium"])
            if row["underlying_return_to_exit_pct"] is not None:
                underlying.append(row["underlying_return_to_exit_pct"])
        values = [row["return_on_premium"] for row in items]
        interval = _block_mean_interval(by_block, resamples, low_q, high_q)
        verdict = "OK" if len(by_block) >= min_sessions else "INSUFFICIENT_SESSIONS"
        win = sum(1 for v in values if v > 0) / len(values)
        under = f"{float(np.mean(underlying)):+.1%}" if underlying else "n/a"
        lines.append(f"| {group} | {len(items)} | {len(by_block)} | {win:.0%} | {float(np.median(values)):+.1%} | "
                     f"{_signed(interval)} | {under} | {verdict} |")
        summary.append({"section": "Expressions", "group": group, "marked": len(items), "sessions": len(by_block),
                        "win_rate": win, "median_return_on_premium": float(np.median(values)),
                        "mean_return_on_premium": interval, "verdict": verdict})
    return lines


def build_report(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, output_dir: Path,
                 ledger=None) -> Path:
    connection.row_factory = sqlite3.Row
    window = int(snapshot.get("outcome.window_sessions").value)
    min_sessions = int(snapshot.get("outcome.min_sessions_for_verdict").value)
    resamples = int(snapshot.get("outcome.bootstrap_resamples").value)
    low_q, high_q = (float(q) for q in snapshot.get("outcome.interval_quantiles").value)
    records = connection.execute(
        """
        SELECT p.*, o.state, o.sessions_observed, o.resolution_session, o.exit_price, o.return_to_exit_pct,
               o.r_multiple, o.mfe_pct, o.mae_pct, o.reason,
               b.state AS base_state, b.observed_sessions AS base_observed,
               b.target_fractions_json, b.stop_fractions_json,
               c.regime_label, c.macro_freshness, c.risk_on_off_switch, c.market_trend_state,
               c.market_vol_state, c.market_breadth_state,
               (SELECT labels_json FROM prediction_sightings s WHERE s.prediction_id = p.prediction_id
                ORDER BY s.book_mtime_utc LIMIT 1) AS first_labels
        FROM prediction_records p
        LEFT JOIN latest_underlying_outcomes o ON o.prediction_id = p.prediction_id AND o.scorer_version = ?
        LEFT JOIN latest_base_rate_outcomes b ON b.prediction_id = p.prediction_id AND b.base_rate_version = ?
        LEFT JOIN condition_records c ON c.prediction_id = p.prediction_id AND c.condition_version = ?
        """,
        (SCORER_VERSION, BASE_RATE_VERSION, CONDITION_VERSION),
    ).fetchall()

    coverage = defaultdict(lambda: defaultdict(int))
    timing = defaultdict(lambda: defaultdict(int))
    groups: dict[tuple[str, str, str], dict[str, list]] = defaultdict(lambda: {"observed": [], "base": []})
    for row in records:
        for field in ("provenance_class", "evidence_session_source", "invalidation_state", "target_state",
                      "contract_state", "direction", "base_state", "macro_freshness"):
            coverage[field][str(row[field])] += 1
        if row["state"] is None:
            coverage["outcome_state"]["NOT_YET_SCORED"] += 1
            continue
        coverage["outcome_state"][row["state"]] += 1
        if row["resolution_session"] is not None and row["state"] != OutcomeState.TIMEOUT.value:
            timing[row["state"]][int(row["resolution_session"])] += 1
        block = row["evidence_session"]
        observed_event = estimators.to_event(_outcome_from_row(row), block)
        if observed_event is None or row["base_state"] != "OK":
            continue
        base_events = estimators.base_rate_events(json.loads(row["target_fractions_json"]),
                                                  json.loads(row["stop_fractions_json"]),
                                                  int(row["base_observed"]), block)
        scope = "headline" if row["provenance_class"] == "RECORDED_AT_RUN" else "retrospective"
        labels = json.loads(row["first_labels"] or "{}")
        keys = [("Legacy labels", "ALL"), ("Legacy labels", f"direction={row['direction']}"),
                ("Legacy labels", f"target_state={row['target_state']}")]
        keys += [("Legacy labels", f"{label}={labels[label]}") for label in GROUP_LABELS if labels.get(label) not in (None, "")]
        keys += [("Conditions", f"{name}={row[name]}") for name in CONDITION_GROUPS if row[name] is not None]
        if row["market_trend_state"] is not None:
            keys.append(("Conditions", f"direction={row['direction']} x market_trend_state={row['market_trend_state']}"))
        for section, group in keys:
            groups[(section, scope, group)]["observed"].append(observed_event)
            groups[(section, scope, group)]["base"].extend(base_events)

    lines = [f"# Outcome report — as of {as_of.isoformat()}", "",
             f"Scorer `{SCORER_VERSION}` · base rate `{BASE_RATE_VERSION}` · conditions `{CONDITION_VERSION}` · "
             f"config snapshot `{snapshot.snapshot_id[:16]}` · window {window} sessions · "
             f"verdict requires ≥ {min_sessions} evidence sessions", "",
             "Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. "
             "Condition labels are analysis dimensions only and never feed a gate, score or rank.", "",
             "**How to read:** *Observed* is the cumulative incidence by session "
             f"{window} (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target "
             "distances, in ATR units, to every ticker in the price store on the same evidence session and window "
             "(what chance entry would have done in the same market). *Excess* = observed − base with a session-block "
             "bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of "
             "skill, once the verdict column says OK.", "",
             "## Coverage", ""]
    for field, values in coverage.items():
        lines.append(f"- **{field}**: " + ", ".join(f"{k} {v}" for k, v in sorted(values.items())))
    lines += ["", "Comparisons below include only predictions with both a scored outcome and a matched base rate.", ""]

    header = ["| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | "
              "Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | "
              "Excess stop (low / point / high) | Verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    summary = []
    for section in ("Legacy labels", "Conditions"):
        lines += ["", f"## {section} vs matched base rate", ""] + header
        for (sec, scope, group), payload in sorted(groups.items()):
            if sec != section or not payload["observed"]:
                continue
            paired = estimators.paired_block_bootstrap(payload["observed"], payload["base"], window, resamples, 0, low_q, high_q)
            verdict = "OK" if paired.observed.blocks >= min_sessions else "INSUFFICIENT_SESSIONS"
            obs = paired.observed
            lines.append(
                f"| {scope} | {group} | {len(payload['observed'])} | {obs.blocks} | {_pct(obs.target_by_final_session)} | "
                f"{paired.base_target:.1%} | {_signed(paired.excess_target)} | {_pct(obs.stop_by_final_session)} | "
                f"{paired.base_stop:.1%} | {_signed(paired.excess_stop)} | {verdict} |")
            summary.append({"section": section, "scope": scope, "group": group, "predictions": len(payload["observed"]),
                            "sessions": obs.blocks, "target": obs.target_by_final_session, "base_target": paired.base_target,
                            "excess_target": paired.excess_target, "stop": obs.stop_by_final_session,
                            "base_stop": paired.base_stop, "excess_stop": paired.excess_stop, "verdict": verdict})

    lines += _expression_section(connection, resamples, low_q, high_q, min_sessions, summary)
    lines += _hypothesis_section(connection, snapshot)
    from .signal_service import signal_section
    lines += signal_section(ledger, snapshot)
    lines += ["", "## Resolution timing (session of first touch)", "", "| State | " +
              " | ".join(str(k) for k in range(1, window + 1)) + " |", "|---|" + "---|" * window]
    for state, by_session in sorted(timing.items()):
        lines.append(f"| {state} | " + " | ".join(str(by_session.get(k, 0)) for k in range(1, window + 1)) + " |")
    lines += ["", f"Caveats: {len(summary)} groups compared (expect some intervals to exclude zero by chance); "
              "AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate "
              "universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so "
              "sector alignment is MISSING; macro conviction carries the DM-36 caveat.", ""]
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "outcome_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "outcome_report.json").write_text(json.dumps({
        "as_of": as_of.isoformat(), "scorer_version": SCORER_VERSION, "base_rate_version": BASE_RATE_VERSION,
        "condition_version": CONDITION_VERSION, "config_snapshot_id": snapshot.snapshot_id,
        "coverage": {k: dict(v) for k, v in coverage.items()},
        "timing": {k: dict(v) for k, v in timing.items()}, "groups": summary,
    }, indent=2), encoding="utf-8")
    return report_path
