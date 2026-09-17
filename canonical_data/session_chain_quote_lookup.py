"""Read-only lookup of one option contract in a stored completed-session chain.

Reuse-only by construction: this adapter never fetches. It does not use
``CanonicalMarketObservationResolver`` because that resolver records every
resolution in the request ledger, requires stage lifecycle authorisation and
can call its fetch callback (a miss, or a refresh of a partially final cache
hit). Here the registry is opened with SQLite ``mode=ro``, the payload is read
from the registered ``storage_uri`` and verified against its content hash, and
a missing observation is a named result -- never a provider request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .option_identity import normalise_occ_symbol


CHAIN_LOOKUP_HIT = "CHAIN_LOOKUP_HIT"
CHAIN_LOOKUP_MISS = "CHAIN_LOOKUP_MISS"
CHAIN_STORE_UNAVAILABLE = "CHAIN_STORE_UNAVAILABLE"
CHAIN_SCHEMA_VERSION = "option_chain_v2"


@dataclass(frozen=True, slots=True)
class ChainQuoteLookupResult:
    state: str
    quote: Mapping[str, Any] | None
    dataset_id: str | None
    session_date: str
    reason: str = ""


class StoredSessionChainQuoteLookup:
    """Callable ``(ticker=, symbol=, session_date=) -> ChainQuoteLookupResult``."""

    def __init__(self, registry_path: Path | str, *, run_id: str) -> None:
        self.registry_path = Path(registry_path)
        self.run_id = str(run_id or "")
        self._chains: dict[tuple[str, str], list[tuple[str, dict[str, dict[str, Any]]]]] = {}

    def _records(self, ticker: str, session: str) -> list[sqlite3.Row]:
        uri = f"file:{self.registry_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT dataset_id, storage_uri, content_hash, source_run_id
                FROM dataset_registry
                WHERE dataset_type = 'OPTION_CHAIN' AND instrument_id = ?
                  AND session_date = ? AND schema_version = ?
                  AND completeness_status = 'COMPLETE'
                ORDER BY (source_run_id = ?) DESC, as_of DESC, registered_at DESC
                """,
                (ticker, session, CHAIN_SCHEMA_VERSION, self.run_id),
            ).fetchall()
        finally:
            connection.close()

    def _chains_for(self, ticker: str, session: str) -> tuple[list, str]:
        key = (ticker, session)
        if key in self._chains:
            return self._chains[key], ""
        chains: list[tuple[str, dict[str, dict[str, Any]]]] = []
        failures: list[str] = []
        for record in self._records(ticker, session):
            try:
                payload = Path(record["storage_uri"]).read_bytes()
            except OSError:
                failures.append("PAYLOAD_UNREADABLE")
                continue
            if hashlib.sha256(payload).hexdigest() != record["content_hash"]:
                failures.append("PAYLOAD_FAILED_INTEGRITY")
                continue
            by_symbol: dict[str, dict[str, Any]] = {}
            for item in json.loads(payload):
                try:
                    by_symbol[normalise_occ_symbol(item.get("symbol"))] = dict(item)
                except (TypeError, ValueError, AttributeError):
                    continue
            chains.append((str(record["dataset_id"]), by_symbol))
        self._chains[key] = chains
        return chains, "|".join(sorted(set(failures)))

    def __call__(self, *, ticker: Any, symbol: Any, session_date: Any) -> ChainQuoteLookupResult:
        session = str(session_date or "").strip()[:10]
        ticker_text = str(ticker or "").strip().upper()
        try:
            session = date.fromisoformat(session).isoformat()
        except ValueError:
            return ChainQuoteLookupResult(CHAIN_LOOKUP_MISS, None, None, session, "SESSION_DATE_UNKNOWN")
        try:
            canonical = normalise_occ_symbol(symbol)
        except (TypeError, ValueError):
            return ChainQuoteLookupResult(CHAIN_LOOKUP_MISS, None, None, session, "INVALID_OCC_SYMBOL")
        if not self.registry_path.is_file():
            return ChainQuoteLookupResult(CHAIN_STORE_UNAVAILABLE, None, None, session, "REGISTRY_NOT_FOUND")
        try:
            chains, failures = self._chains_for(ticker_text, session)
        except sqlite3.Error as error:
            return ChainQuoteLookupResult(
                CHAIN_STORE_UNAVAILABLE, None, None, session, f"REGISTRY_UNREADABLE:{type(error).__name__}"
            )
        for dataset_id, by_symbol in chains:
            quote = by_symbol.get(canonical)
            if quote is not None:
                return ChainQuoteLookupResult(CHAIN_LOOKUP_HIT, quote, dataset_id, session, "")
        if chains:
            reason = "SYMBOL_NOT_IN_STORED_CHAIN"
        elif failures:
            reason = failures
        else:
            reason = "NO_STORED_CHAIN_FOR_SESSION"
        return ChainQuoteLookupResult(CHAIN_LOOKUP_MISS, None, None, session, reason)


__all__ = [
    "CHAIN_LOOKUP_HIT", "CHAIN_LOOKUP_MISS", "CHAIN_STORE_UNAVAILABLE",
    "ChainQuoteLookupResult", "StoredSessionChainQuoteLookup",
]
