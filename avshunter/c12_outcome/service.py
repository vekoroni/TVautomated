"""Application service: ingest recorded books, score outcomes, build the report."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from avshunter.config import ConfigSnapshot
from avshunter.shared.xnys_calendar import is_xnys_session

from . import estimators
from .adapters import books, prices, storage
from .geometry import classify
from .model import Bar, OutcomeState, UnderlyingOutcome
from .passage import evaluate_passage
from .records import prediction_id, provenance_class, resolve_evidence_session

SCORER_VERSION = "c12-outcome-scorer-v1.0.0"

# Policies implemented by this scorer version; configuration must match exactly.
IMPLEMENTED_POLICIES = {
    "outcome.ambiguous_policy": "STOP_FIRST_FOR_ESTIMATION",
    "outcome.stop_fill_policy": "WORSE_OF_LEVEL_AND_OPEN",
    "outcome.first_session_provenance_cutoff": "SESSION_1_CLOSE",
}


def require_implemented_policies(snapshot: ConfigSnapshot) -> None:
    mismatches = {
        key: snapshot.get(key).value
        for key, implemented in IMPLEMENTED_POLICIES.items()
        if snapshot.get(key).value != implemented
    }
    if mismatches:
        raise ValueError(f"configuration requests policies {SCORER_VERSION} does not implement: {mismatches}")


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


# --- report --------------------------------------------------------------------

GROUP_LABELS = ("tier", "lab_verdict", "final_action", "thesis_state", "ev3_absolute_state")


def _outcome_from_row(row: sqlite3.Row) -> UnderlyingOutcome:
    return UnderlyingOutcome(
        OutcomeState(row["state"]), row["sessions_observed"], row["resolution_session"], None,
        row["exit_price"], row["return_to_exit_pct"], row["r_multiple"], row["mfe_pct"], row["mae_pct"], row["reason"] or "",
    )


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
               (SELECT labels_json FROM prediction_sightings s WHERE s.prediction_id = p.prediction_id
                ORDER BY s.book_mtime_utc LIMIT 1) AS first_labels
        FROM prediction_records p
        LEFT JOIN latest_underlying_outcomes o ON o.prediction_id = p.prediction_id AND o.scorer_version = ?
        """,
        (SCORER_VERSION,),
    ).fetchall()

    coverage = defaultdict(lambda: defaultdict(int))
    groups: dict[tuple[str, str], list[tuple[UnderlyingOutcome, str]]] = defaultdict(list)
    for row in records:
        for field in ("provenance_class", "evidence_session_source", "invalidation_state", "target_state", "contract_state", "direction"):
            coverage[field][str(row[field])] += 1
        if row["state"] is None:
            coverage["outcome_state"]["NOT_YET_SCORED"] += 1
            continue
        coverage["outcome_state"][row["state"]] += 1
        outcome = _outcome_from_row(row)
        block = row["evidence_session"]
        headline = row["provenance_class"] == "RECORDED_AT_RUN"
        scope = "headline" if headline else "retrospective"
        groups[(scope, "ALL")].append((outcome, block))
        groups[(scope, f"direction={row['direction']}")].append((outcome, block))
        groups[(scope, f"target_state={row['target_state']}")].append((outcome, block))
        labels = json.loads(row["first_labels"] or "{}")
        for label in GROUP_LABELS:
            if labels.get(label) not in (None, ""):
                groups[(scope, f"{label}={labels[label]}")].append((outcome, block))

    lines = [f"# Outcome report — as of {as_of.isoformat()}", "",
             f"Scorer `{SCORER_VERSION}` · config snapshot `{snapshot.snapshot_id[:16]}` · window {window} sessions · "
             f"verdict requires ≥ {min_sessions} evidence sessions", "",
             "Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded.", "",
             "## Coverage", ""]
    for field, values in coverage.items():
        lines.append(f"- **{field}**: " + ", ".join(f"{k} {v}" for k, v in sorted(values.items())))
    lines += ["", "## Cumulative incidence by session 20 (Aalen-Johansen, session-block bootstrap)", "",
              "| Scope | Group | Predictions | Evidence sessions | Target first (low / point / high) | Stop first (low / point / high) | Verdict |",
              "|---|---|---|---|---|---|---|"]
    summary = []
    for (scope, group), items in sorted(groups.items()):
        events = estimators.events_from(items)
        if not events:
            continue
        interval = estimators.block_bootstrap(events, window, resamples, 0, low_q, high_q)
        verdict = "OK" if interval.blocks >= min_sessions else "INSUFFICIENT_SESSIONS"
        t, s = interval.target_by_final_session, interval.stop_by_final_session
        lines.append(f"| {scope} | {group} | {len(events)} | {interval.blocks} | "
                     f"{t[0]:.1%} / {t[1]:.1%} / {t[2]:.1%} | {s[0]:.1%} / {s[1]:.1%} / {s[2]:.1%} | {verdict} |")
        summary.append({"scope": scope, "group": group, "predictions": len(events), "sessions": interval.blocks,
                        "target": t, "stop": s, "verdict": verdict})
    lines += ["", "Notes: AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored. "
              "Matched base rate and condition labels follow in the next scorer increment.", ""]
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "outcome_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "outcome_report.json").write_text(json.dumps({
        "as_of": as_of.isoformat(), "scorer_version": SCORER_VERSION, "config_snapshot_id": snapshot.snapshot_id,
        "coverage": {k: dict(v) for k, v in coverage.items()}, "groups": summary,
    }, indent=2), encoding="utf-8")
    return report_path
