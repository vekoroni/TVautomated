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
from .adapters import books, macro, prices, storage
from .base_rate import BASE_RATE_VERSION, build_panel, matched_incidence, panel_atr
from .conditions import CONDITION_VERSION, ConditionSettings, macro_condition, market_condition
from .geometry import classify
from .model import Bar, OutcomeState, TargetState, UnderlyingOutcome
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


def build_report(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, output_dir: Path) -> Path:
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
