"""Read-only, point-in-time Phantom revisions for hypothetical option outcomes.

This reader neither updates Phantom nor turns a future quote into a trading
observation. A revision is usable only when its immutable row hash, projection
receipt, and canonical dataset registry agree at the evaluation cutoff.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from domain.data_projection import PHANTOM_OPTION_CHAIN_PROJECTION
from domain.dynamic_options_outcomes import OptionPathObservation


class PhantomOutcomeProvenanceError(ValueError):
    """A projected row cannot be reconciled to canonical source evidence."""


@dataclass(frozen=True, slots=True)
class VerifiedPhantomOutcomeQuote:
    observation: OptionPathObservation
    event_id: str
    row_content_hash: str
    dataset_content_hash: str
    projected_at_utc: datetime


def _utc(value: str | datetime, field: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError) as error:
        raise PhantomOutcomeProvenanceError(f"invalid {field}") from error


def _read_only(path: Path) -> sqlite3.Connection:
    resolved = Path(path).resolve(strict=True)
    connection = sqlite3.connect(
        f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=3,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


class PhantomOutcomeSourceReader:
    def __init__(self, registry_path: Path, phantom_path: Path):
        self.registry_path = Path(registry_path)
        self.phantom_path = Path(phantom_path)

    def read_sessions(
        self, *, ticker: str, contract_symbol: str, sessions: tuple[date, ...],
        assessment_cutoff_utc: datetime, evaluation_cutoff_utc: datetime,
    ) -> tuple[VerifiedPhantomOutcomeQuote, ...]:
        origin = _utc(assessment_cutoff_utc, "assessment_cutoff_utc")
        cutoff = _utc(evaluation_cutoff_utc, "evaluation_cutoff_utc")
        if cutoff <= origin:
            return ()
        result: list[VerifiedPhantomOutcomeQuote] = []
        dataset_cache: dict[str, sqlite3.Row | None] = {}
        with closing(_read_only(self.registry_path)) as registry, closing(
            _read_only(self.phantom_path)
        ) as phantom:
            for session in sorted(set(sessions)):
                rows = phantom.execute(
                    """SELECT r.*, p.projection_name,p.content_hash AS receipt_hash,
                              p.projected_at_utc AS receipt_projected_at,
                              p.dataset_id AS receipt_dataset_id,
                              p.ticker AS receipt_ticker,
                              p.session_date AS receipt_session
                    FROM canonical_option_chain_revisions AS r
                    LEFT JOIN canonical_projection_receipts AS p
                      ON p.event_id=r.event_id
                    WHERE r.ticker=? AND r.quote_date=? AND r.option_symbol=?
                    ORDER BY r.dataset_as_of_utc DESC,r.projected_at_utc DESC,r.dataset_id DESC""",
                    (ticker, session.isoformat(), contract_symbol),
                ).fetchall()
                eligible: list[tuple[datetime, VerifiedPhantomOutcomeQuote]] = []
                for row in rows:
                    dataset_id = row["dataset_id"]
                    if dataset_id not in dataset_cache:
                        dataset_cache[dataset_id] = registry.execute(
                            "SELECT * FROM dataset_registry WHERE dataset_id=?",
                            (dataset_id,),
                        ).fetchone()
                    dataset = dataset_cache[dataset_id]
                    if dataset is None:
                        raise PhantomOutcomeProvenanceError("revision dataset is not registered")
                    payload = json.loads(row["row_json"])
                    as_of = _utc(row["dataset_as_of_utc"], "dataset_as_of_utc")
                    projected = _utc(row["projected_at_utc"], "projected_at_utc")
                    receipt_projected = _utc(
                        row["receipt_projected_at"], "receipt_projected_at"
                    )
                    quote = datetime.fromtimestamp(
                        int(payload["updated_ts"]), tz=timezone.utc
                    ) if payload.get("updated_ts") is not None else None
                    if quote is None:
                        raise PhantomOutcomeProvenanceError("provider quote time is missing")
                    created = _utc(payload["created_at_utc"], "source_created_at_utc")
                    available = max(
                        projected, receipt_projected, created,
                        _utc(dataset["observed_at"], "dataset_observed_at"),
                        _utc(dataset["registered_at"], "dataset_registered_at"),
                    )
                    if quote > cutoff or available > cutoff or as_of > cutoff:
                        continue
                    if quote <= origin or quote.astimezone(
                        ZoneInfo("America/New_York")
                    ).date() != session:
                        raise PhantomOutcomeProvenanceError(
                            "provider quote time conflicts with session identity"
                        )
                    if hashlib.sha256(row["row_json"].encode("utf-8")).hexdigest() != row["row_content_hash"]:
                        raise PhantomOutcomeProvenanceError("Phantom revision row hash mismatch")
                    if (
                        dataset["dataset_type"] != "OPTION_CHAIN"
                        or dataset["instrument_id"] != ticker
                        or dataset["session_date"] != session.isoformat()
                        or dataset["provider"] != "MARKETDATA"
                        or dataset["completeness_status"] != "COMPLETE"
                        or row["projection_name"] != PHANTOM_OPTION_CHAIN_PROJECTION
                        or row["receipt_dataset_id"] != dataset_id
                        or row["receipt_ticker"] != ticker
                        or row["receipt_session"] != session.isoformat()
                        or row["receipt_hash"] != dataset["content_hash"]
                        or payload.get("ticker") != ticker
                        or payload.get("quote_date") != session.isoformat()
                        or payload.get("option_symbol") != contract_symbol
                        or payload.get("source") != "MARKETDATA"
                    ):
                        raise PhantomOutcomeProvenanceError(
                            "Phantom revision, receipt and registry disagree"
                        )
                    source_key = hashlib.sha256(
                        f"{dataset_id}|{contract_symbol}|{row['row_content_hash']}".encode("utf-8")
                    ).hexdigest()
                    observation = OptionPathObservation(
                        observation_id=f"PHANTOM_REV:{source_key}",
                        dataset_id=dataset_id,
                        contract_symbol=contract_symbol,
                        session_date=session,
                        quote_at_utc=quote,
                        available_at_utc=available,
                        bid=payload.get("bid"), ask=payload.get("ask"),
                        volume=payload.get("volume"),
                        open_interest=payload.get("open_interest"),
                        implied_volatility=payload.get("iv"),
                    )
                    eligible.append((as_of, VerifiedPhantomOutcomeQuote(
                        observation=observation, event_id=row["event_id"],
                        row_content_hash=row["row_content_hash"],
                        dataset_content_hash=dataset["content_hash"],
                        projected_at_utc=projected,
                    )))
                if eligible:
                    eligible.sort(key=lambda entry: (entry[0], entry[1].projected_at_utc))
                    if (len(eligible) > 1 and eligible[-1][0] == eligible[-2][0]
                            and eligible[-1][1].row_content_hash != eligible[-2][1].row_content_hash):
                        raise PhantomOutcomeProvenanceError(
                            "conflicting revisions at the same source as-of time"
                        )
                    result.append(eligible[-1][1])
        return tuple(result)


__all__ = [
    "PhantomOutcomeProvenanceError", "PhantomOutcomeSourceReader",
    "VerifiedPhantomOutcomeQuote",
]
