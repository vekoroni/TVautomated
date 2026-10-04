"""SQLite adapter for the BEH-001 behavioural candidate ledger (C-03 core, RQ-2).

Append-only, in the house pattern of the Decision and Outcome Ledger (no-update and
no-delete triggers). It records observations of behavioural candidates; it decides
nothing. Candidates are observations made before any thesis exists, so they are not
written to the decision ledger; phase 2 links a candidate to the thesis that uses it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Mapping, MutableMapping, Optional

from domain.structure_behaviour.lifecycle import LEVEL_FIELDS, UNCHANGED, not_trading, transitions

SCHEMA_VERSION = "beh001_candidate_ledger_v1"
# The payload keeps what replays the life cycle; the full reading stays in the run's CSV.
PAYLOAD_FIELDS = ("Candidate_ID", "Ticker", "Timeframe", "Structure_Scope", "Signal_Type", "Signal_State",
                  "Direction", "As_Of", "Trigger_Level", "Invalidation_Level", "Outcome_Level",
                  "Outcome_Definition", "Parent_Candidate_ID", "Age_Bars", "Wyckoff_Phase", "Controller",
                  "Data_Status", "Discovery_Outcome")


def _float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


class BehaviouralCandidateLedger:
    def __init__(self, database_path: Path | str, *, level_tolerance: Optional[float] = None,
                 not_trading_after_sessions: Optional[int] = None):
        self.database_path = Path(database_path)
        if level_tolerance is None or not_trading_after_sessions is None:
            from domain.structure_behaviour.policy import load_policy
            ledger_policy = load_policy()["ledger"]
            level_tolerance = ledger_policy["level_revision_rel_tol"] if level_tolerance is None else level_tolerance
            if not_trading_after_sessions is None:
                not_trading_after_sessions = ledger_policy["not_trading_after_sessions"]
        self.level_tolerance = float(level_tolerance)
        self.not_trading_after_sessions = int(not_trading_after_sessions)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidate_events(
                    event_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    as_of TEXT,
                    ticker TEXT NOT NULL,
                    timeframe TEXT,
                    candidate_id TEXT NOT NULL,
                    signal_type TEXT,
                    direction TEXT,
                    event_type TEXT NOT NULL,
                    signal_state TEXT,
                    previous_state TEXT,
                    trigger_level REAL,
                    invalidation_level REAL,
                    outcome_level REAL,
                    parent_candidate_id TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_candidate_events_id
                    ON candidate_events(candidate_id, recorded_at_utc);
                CREATE INDEX IF NOT EXISTS ix_candidate_events_run
                    ON candidate_events(run_id, ticker);
                CREATE TRIGGER IF NOT EXISTS candidate_events_no_update
                    BEFORE UPDATE ON candidate_events
                    BEGIN SELECT RAISE(ABORT, 'candidate ledger is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS candidate_events_no_delete
                    BEFORE DELETE ON candidate_events
                    BEGIN SELECT RAISE(ABORT, 'candidate ledger is append-only'); END;
                """
            )

    # -- reads ---------------------------------------------------------------------------
    def _latest(self, connection, tickers: Optional[Iterable[str]] = None) -> dict:
        sql = ("SELECT e.* FROM candidate_events e JOIN (SELECT candidate_id, MAX(rowid) AS r "
               "FROM candidate_events GROUP BY candidate_id) m ON e.rowid = m.r")
        rows = connection.execute(sql).fetchall()
        wanted = None if tickers is None else {str(t).upper() for t in tickers}
        latest = {}
        for row in rows:
            if wanted is not None and row["ticker"].upper() not in wanted:
                continue
            latest[row["candidate_id"]] = {
                "event_type": row["event_type"], "signal_state": row["signal_state"], "ticker": row["ticker"],
                "Trigger_Level": row["trigger_level"], "Invalidation_Level": row["invalidation_level"],
                "Outcome_Level": row["outcome_level"], "as_of": row["as_of"]}
        return latest

    def history(self, candidate_id: str) -> List[dict]:
        self.initialise()
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM candidate_events WHERE candidate_id=? ORDER BY rowid",
                                      (candidate_id,)).fetchall()
        return [dict(row) for row in rows]

    def lineage(self, candidate_id: str) -> List[str]:
        """The candidate, its parent, the parent's parent, ... (cycle-safe)."""
        chain = [candidate_id]
        while True:
            first = next(iter(self.history(chain[-1])), None)
            parent = None if first is None else first["parent_candidate_id"]
            if not parent or parent in chain:
                return chain
            chain.append(parent)

    def _first_seen(self, connection, ids: List[str]) -> dict:
        out = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for row in connection.execute(
                    f"SELECT candidate_id, run_id, as_of FROM candidate_events WHERE event_type='FIRST_SEEN' "
                    f"AND candidate_id IN ({marks})", chunk):
                out[row["candidate_id"]] = (row["run_id"], row["as_of"])
        return out

    # -- write ---------------------------------------------------------------------------
    def record_run(self, run_id: str, candidates: List[MutableMapping], read_tickers: Iterable[str],
                   ticker_last_bar: Optional[Mapping[str, str]] = None) -> dict:
        """Append this run's life-cycle events and annotate each candidate in place
        (Lifecycle_Event, First_Seen_Run, First_Seen_As_Of). Re-recording a run adds nothing."""
        self.initialise()
        read = {str(t).upper() for t in read_tickers}
        now = datetime.now(timezone.utc).isoformat()
        counts: dict = {}
        with self._connect() as connection:
            previous = self._latest(connection, read | {str(c.get("Ticker", "")).upper() for c in candidates})
            # Events this run already wrote do not count as "previous" (idempotent re-record).
            already = {r["candidate_id"] for r in connection.execute(
                "SELECT candidate_id FROM candidate_events WHERE run_id=?", (run_id,))}
            stopped = not_trading(ticker_last_bar or {}, self.not_trading_after_sessions)
            for change in transitions(previous, candidates, read, level_tolerance=self.level_tolerance,
                                      stopped=stopped):
                kind = change["event_type"]
                c = change["candidate"]
                cid = c["Candidate_ID"] if c is not None else change["candidate_id"]
                if kind == UNCHANGED or cid in already:
                    if c is not None:
                        c["Lifecycle_Event"] = kind if cid not in already else self._run_event(connection, run_id, cid)
                    counts[kind] = counts.get(kind, 0) + 1
                    continue
                source = c if c is not None else change["last"]
                payload = {k: (c or {}).get(k) for k in PAYLOAD_FIELDS if k in (c or {})}
                connection.execute(
                    "INSERT OR IGNORE INTO candidate_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (hashlib.sha256(f"{run_id}|{cid}|{kind}".encode()).hexdigest(), SCHEMA_VERSION, run_id, now,
                     None if c is None else c.get("As_Of"), cid.split("|")[0], cid.split("|")[1] if "|" in cid else None,
                     cid, cid.split("|")[3] if cid.count("|") >= 4 else None,
                     None if c is None else c.get("Direction"), kind,
                     change["previous_state"] if c is None else c.get("Signal_State"), change["previous_state"],
                     *(_float(source.get(f)) for f in LEVEL_FIELDS),
                     None if c is None else (c.get("Parent_Candidate_ID") or None),
                     json.dumps(payload, sort_keys=True, default=str)))
                if c is not None:
                    c["Lifecycle_Event"] = kind
                counts[kind] = counts.get(kind, 0) + 1
            # Defence: a second row with an ID already seen this run is never left unannotated.
            seen_ids: set = set()
            for c in candidates:
                if c["Candidate_ID"] in seen_ids:
                    c["Lifecycle_Event"] = "DUPLICATE_ID_IN_RUN"
                seen_ids.add(c["Candidate_ID"])
            first = self._first_seen(connection, [c["Candidate_ID"] for c in candidates])
        for c in candidates:
            run, as_of = first.get(c["Candidate_ID"], (None, None))
            c["First_Seen_Run"], c["First_Seen_As_Of"] = run, as_of
        return counts

    @staticmethod
    def _run_event(connection, run_id: str, candidate_id: str) -> str:
        row = connection.execute("SELECT event_type FROM candidate_events WHERE run_id=? AND candidate_id=? "
                                 "ORDER BY rowid DESC LIMIT 1", (run_id, candidate_id)).fetchone()
        return row["event_type"] if row else UNCHANGED
