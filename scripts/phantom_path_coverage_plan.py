"""Read-only exact-contract history coverage and bounded data-request candidates.

This is a maintenance planning diagnostic, not an order, provider fetch, or EV.
Only a missing ticker/session chain is a request candidate. An absent contract in
an existing chain and an unusable quote require investigation, not silent re-fetch.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from canonical_data.session_clock import advance_xnys_sessions, is_xnys_session, session_snapshot

_OCC_TAIL = re.compile(r"(\d{6})[CP]\d{8}$")


def _expiry(symbol: str) -> date | None:
    match = _OCC_TAIL.search(symbol)
    if not match:
        return None
    try:
        return date(2000 + int(match[1][:2]), int(match[1][2:4]), int(match[1][4:6]))
    except ValueError:
        return None


def _read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=20)
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chain_snapshots'").fetchone():
        connection.close()
        raise ValueError("Phantom chain_snapshots table unavailable")
    return connection


def audit_decisions(
    decisions: list[dict[str, str]], phantom_path: Path, *, through_session: date,
    max_sessions: int = 20,
) -> dict:
    """Audit decision-session through bounded later sessions, never beyond cutoff.

    `max_sessions` is a research coverage window, not a compulsory trade hold.
    Morning-selected contracts start no earlier than their validation cutoff.
    """
    if not is_xnys_session(through_session):
        raise ValueError("through_session must be a completed XNYS session")
    if not 1 <= max_sessions <= 60:
        raise ValueError("max_sessions must be between 1 and 60")
    observations: list[dict] = []
    requests: dict[tuple[str, str], set[str]] = defaultdict(set)
    counters: Counter = Counter()
    seen: set[tuple[str, str, str, str]] = set()
    with closing(_read_only(Path(phantom_path))) as connection:
        for row in decisions:
            ticker = str(row.get("ticker") or "").strip().upper()
            symbol = str(row.get("selected_contract_symbol") or "").strip().upper()
            mode = str(row.get("pipeline_mode") or "EOD").strip().upper()
            if mode == "MORNING_VALIDATION":
                cutoff = str(row.get("validation_evidence_cutoff_utc") or "")
                if not row.get("validation_event_id") or len(cutoff) < 10:
                    counters["decisions_missing_validation_lineage"] += 1
                    continue
                session_text = cutoff[:10]
            elif mode == "EOD":
                session_text = str(row.get("evidence_session_date") or "").strip()
            else:
                counters["decisions_unknown_mode"] += 1
                continue
            thesis_id = str(row.get("thesis_id") or row.get("forecast_thesis_id") or "").strip()
            run_id = str(row.get("run_id") or "").strip()
            if not ticker or not session_text or not run_id or not thesis_id:
                counters["decisions_missing_identity"] += 1
                continue
            if not symbol:
                counters["decisions_without_contract"] += 1
                continue
            expiry = _expiry(symbol)
            if expiry is None or not symbol.startswith(ticker.replace(".", "")):
                counters["decisions_unparseable_contract"] += 1
                continue
            try:
                evidence = date.fromisoformat(session_text)
            except ValueError:
                counters["decisions_invalid_session"] += 1
                continue
            if not is_xnys_session(evidence):
                counters["decisions_invalid_session"] += 1
                continue
            key = (run_id, thesis_id, ticker, symbol)
            if key in seen:
                counters["duplicate_decisions"] += 1
                continue
            seen.add(key)
            counters["decisions_audited"] += 1
            for offset in range(max_sessions):
                session = advance_xnys_sessions(evidence, offset)
                if session > through_session:
                    counters["future_session_count"] += 1
                    continue
                if session > expiry:
                    counters["post_expiry_session_count"] += 1
                    continue
                day = session.isoformat()
                quote = connection.execute(
                    "SELECT bid, ask FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=? LIMIT 1",
                    (ticker, day, symbol),
                ).fetchone()
                if quote is not None:
                    bid, ask = quote
                    state = ("TWO_SIDED_QUOTE_OBSERVED" if bid is not None and ask is not None
                             and 0 <= bid <= ask and ask > 0 else "QUOTE_UNUSABLE")
                elif connection.execute(
                    "SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? LIMIT 1",
                    (ticker, day),
                ).fetchone():
                    state = "CONTRACT_ABSENT_IN_CHAIN"
                else:
                    state = "CHAIN_MISSING"
                    requests[(ticker, day)].add(symbol)
                counters[state] += 1
                observations.append({"run_id": run_id, "thesis_id": thesis_id, "ticker": ticker,
                                     "option_symbol": symbol, "session_date": day, "session_offset": offset,
                                     "source_mode": mode, "state": state})
    request_candidates = [
        {"ticker": ticker, "session_date": day, "reason": "CHAIN_MISSING",
         "maintenance_lane": ("WEEKLY_FRIDAY_BASELINE" if date.fromisoformat(day).weekday() == 4
                              else "TARGETED_WEEKDAY_GAP"),
         "affected_contracts": sorted(symbols)}
        for (ticker, day), symbols in sorted(requests.items())
    ]
    return {"schema_version": "phantom_path_coverage_plan_v1", "authority": "AUDIT_ONLY",
            "through_session": through_session.isoformat(), "max_sessions": max_sessions,
            "request_candidates": request_candidates, "observations": observations,
            "summary": dict(sorted(counters.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="Governed run directory")
    parser.add_argument("--phantom-db", type=Path, required=True)
    parser.add_argument("--through-session", type=date.fromisoformat, required=True,
                        help="Last completed XNYS session, YYYY-MM-DD")
    parser.add_argument("--max-sessions", type=int, default=20,
                        help="Research coverage window, not the trade hold (default 20)")
    parser.add_argument("--output", type=Path, help="Optional JSON plan path; stdout otherwise")
    args = parser.parse_args()
    if args.through_session > session_snapshot().last_completed_session:
        parser.error("through-session is later than the last completed XNYS session")
    source = args.run_dir / "intelligence_lab" / "lab_signal_book_v3.csv"
    manifest_path = args.run_dir / "intelligence_lab" / "lab_signal_book_v3.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if manifest.get("run_id") != args.run_dir.name or manifest.get("book_sha256") != digest.hexdigest():
        parser.error("Lab book identity or SHA-256 does not match its governed manifest")
    with source.open(newline="", encoding="utf-8-sig") as handle:
        decisions = list(csv.DictReader(handle))
    if manifest.get("row_count") != len(decisions):
        parser.error("Lab book row count does not match its governed manifest")
    if not decisions or any(row.get("run_id") != args.run_dir.name
                            or row.get("pipeline_mode") not in {"EOD", "MORNING_VALIDATION"}
                            for row in decisions):
        parser.error("Expected a nonempty governed EOD/Morning Lab book for the exact run")
    result = audit_decisions(decisions, args.phantom_db, through_session=args.through_session,
                             max_sessions=args.max_sessions)
    result["source_run_id"] = args.run_dir.name
    result["source_path"] = str(source.resolve())
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        if args.output.exists():
            parser.error("Output exists; refusing overwrite")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
