"""Read-only provider-finality replay over stored canonical option sessions."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import CanonicalRegistry
from canonical_data.provider_finality import assess_completed_option_worklist


def _session_records(database: Path, session: date) -> dict[str, str]:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            """
            SELECT instrument_id, dataset_id
            FROM dataset_registry
            WHERE dataset_type = 'OPTION_CHAIN' AND session_date = ?
            ORDER BY registered_at, dataset_id
            """,
            (session.isoformat(),),
        ).fetchall()
    # The latest immutable registration for a ticker supersedes earlier
    # acquisitions, without deleting their evidence.
    return {str(ticker).upper(): str(dataset_id) for ticker, dataset_id in rows}


def replay_session(session: date) -> dict[str, object]:
    registry_path = ROOT / "data" / "canonical" / "control_plane.sqlite"
    chains = _session_records(registry_path, session)
    assessed = datetime.combine(
        session + timedelta(days=1), time(1, 0), tzinfo=timezone.utc
    )
    result = assess_completed_option_worklist(
        registry=CanonicalRegistry(registry_path),
        expected_tickers=tuple(chains),
        chain_dataset_ids=chains,
        requested_session=session,
        last_completed_session=session,
        assessed_at_utc=assessed,
        historical_price_database_path=(
            ROOT / "data" / "canonical" / "historical_prices.sqlite"
        ),
    )
    payload = result.to_dict()
    assessments = payload.pop("ticker_assessments")
    payload["ticker_assessment_count"] = len(assessments)
    payload["ticker_exception_count"] = sum(
        1
        for item in assessments
        if item.get("finality_state") != "PROVIDER_SESSION_COMPLETE"
    )
    payload["ticker_exception_examples"] = [
        item
        for item in assessments
        if item.get("finality_state") != "PROVIDER_SESSION_COMPLETE"
    ][:50]
    payload["session_date"] = session.isoformat()
    payload["source"] = "CANONICAL_REPLAY_NO_PROVIDER_CALLS"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    sessions = [date.fromisoformat(value) for value in args.sessions]
    if len(sessions) != 2 or len(set(sessions)) != 2:
        raise ValueError("exactly two distinct stored sessions are required")
    results = [replay_session(session) for session in sessions]
    document = {
        "schema_version": "provider_finality_replay_v1",
        "sessions": results,
        "threshold_decision": (
            "ACCEPTED_FOR_STAGE1"
            if all(
                item["provider_completeness_evidence"][
                    "normal_completed_session_eligible"
                ]
                for item in results
            )
            else "REJECTED_REQUIRES_POLICY_REVIEW"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "output": str(output),
        "threshold_decision": document["threshold_decision"],
        "sessions": [
            {
                "session": item["session_date"],
                "chains": item["provider_completeness_evidence"]["chains_expected"],
                "complete": item["provider_completeness_evidence"]["complete_chains"],
                "eligible": item["provider_completeness_evidence"]["normal_completed_session_eligible"],
            }
            for item in results
        ],
    }, indent=2))
    return 0 if document["threshold_decision"] == "ACCEPTED_FOR_STAGE1" else 2


if __name__ == "__main__":
    raise SystemExit(main())
