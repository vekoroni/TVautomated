"""Read-only reconciliation of future canonical option-chain provenance.

The normal Evening path already registers complete chains and enqueues Phantom
projection. This check shows whether those future-data receipts and exact-row
revisions actually arrived; it never treats mutable chain_snapshots as proof.
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import closing
from pathlib import Path

from domain.data_projection import PHANTOM_OPTION_CHAIN_PROJECTION
from tools.avs_mon004_canary import connect_read_only


def classify_projection(
    *, dataset_hash: str, delivery_state: str | None,
    receipt_hash: str | None, rows_projected: int | None,
    revision_count: int,
) -> str:
    if delivery_state is None:
        return "NO_PROJECTION_EVENT"
    if delivery_state != "COMPLETED":
        return f"DELIVERY_{delivery_state}"
    if receipt_hash is None:
        return "COMPLETED_WITHOUT_RECEIPT"
    if receipt_hash != dataset_hash:
        return "RECEIPT_HASH_MISMATCH"
    if not rows_projected or revision_count != rows_projected:
        return "REVISION_COUNT_MISMATCH"
    return "RECONCILED_RECEIPT_AND_ROW_COUNT"


def reconcile(
    registry_path: Path, phantom_path: Path, *, latest_sessions: int = 5,
) -> dict:
    if latest_sessions < 1 or latest_sessions > 30:
        raise ValueError("latest_sessions must be between 1 and 30")
    with closing(connect_read_only(registry_path)) as registry, \
            closing(connect_read_only(phantom_path)) as phantom:
        sessions = [row[0] for row in registry.execute(
            """SELECT DISTINCT session_date FROM dataset_registry
            WHERE dataset_type='OPTION_CHAIN' AND completeness_status='COMPLETE'
            ORDER BY session_date DESC LIMIT ?""", (latest_sessions,),
        )]
        if not sessions:
            return {"sessions": [], "datasets": 0, "by_state": {},
                    "production_access": "read-only"}
        placeholders = ",".join("?" for _ in sessions)
        datasets = registry.execute(
            f"""SELECT d.dataset_id,d.session_date,d.instrument_id,d.content_hash,
                    o.event_id,o.delivery_state
            FROM dataset_registry AS d
            LEFT JOIN projection_outbox AS o ON o.dataset_id=d.dataset_id
                AND o.projection_name=?
            WHERE d.dataset_type='OPTION_CHAIN'
                AND d.completeness_status='COMPLETE'
                AND d.session_date IN ({placeholders})
            ORDER BY d.session_date,d.instrument_id,d.dataset_id""",
            (PHANTOM_OPTION_CHAIN_PROJECTION, *sessions),
        ).fetchall()
        states: Counter[str] = Counter()
        by_session: dict[str, Counter[str]] = {}
        examples: list[dict] = []
        for item in datasets:
            receipt = phantom.execute(
                """SELECT content_hash,rows_projected FROM canonical_projection_receipts
                WHERE event_id=?""", (item["event_id"],),
            ).fetchone() if item["event_id"] else None
            revisions = phantom.execute(
                """SELECT COUNT(*) FROM canonical_option_chain_revisions
                WHERE dataset_id=?""", (item["dataset_id"],),
            ).fetchone()[0]
            state = classify_projection(
                dataset_hash=item["content_hash"],
                delivery_state=item["delivery_state"],
                receipt_hash=receipt["content_hash"] if receipt else None,
                rows_projected=receipt["rows_projected"] if receipt else None,
                revision_count=revisions,
            )
            states[state] += 1
            by_session.setdefault(item["session_date"], Counter())[state] += 1
            if state != "RECONCILED_RECEIPT_AND_ROW_COUNT" and len(examples) < 25:
                examples.append({"session": item["session_date"],
                                 "ticker": item["instrument_id"],
                                 "dataset_id": item["dataset_id"],
                                 "state": state})
        return {
            "sessions": sessions,
            "datasets": len(datasets),
            "by_state": dict(states),
            "by_session": {key: dict(value) for key, value in by_session.items()},
            "exceptions_sample": examples,
            "authority": "provenance health only; not a trading gate or outcome label",
            "limitation": "aggregate receipt/count reconciliation; individual row hashes are checked by the outcome reader at use",
            "production_access": "read-only",
        }


if __name__ == "__main__":
    print(json.dumps(reconcile(
        Path("data/canonical/control_plane.sqlite"),
        Path("data/phantom/phantom_history.db"),
    ), indent=2, sort_keys=True))
