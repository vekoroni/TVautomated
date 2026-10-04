"""Infrastructure adapters for the Macro/Gamma Exposure bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping
from uuid import uuid4

import pandas as pd

from macro_domain.gamma_exposure import GammaExposureConfig, GammaExposureResult
from scripts.compute_greeks_bs import compute_greeks_from_row

from .contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from .registry import CanonicalRegistry
from .session_clock import is_xnys_session, session_bounds


GEX_SCHEMA_VERSION = "gamma_exposure_v1"
GEX_ADJUSTMENT = "RAW_OPTION_CONTRACT_GEX"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{uuid4().hex}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


GOVERNED_CONSTANTS_PATH = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"


@dataclass(frozen=True, slots=True)
class ChainResolutionPolicy:
    """Governed window for rolling to a neighbouring stored chain session."""

    forward_roll_max_sessions: int
    backward_roll_max_sessions: int
    threshold_version: str = "UNCONFIGURED"


@dataclass(frozen=True, slots=True)
class ChainResolution:
    """What chain session was asked for, what was found, and how far away."""

    requested_session: date
    resolved_session: date | None
    direction: str
    sessions_rolled: int

    @property
    def available(self) -> bool:
        return self.resolved_session is not None

    @property
    def fallback_used(self) -> bool:
        return self.direction != "EXACT"


def load_chain_resolution_policy(
    path: Path | str = GOVERNED_CONSTANTS_PATH,
) -> ChainResolutionPolicy:
    """Load the governed roll window fail-closed; never guess a window."""

    payload = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    if payload.get("schema_version") != "governed_constants_v1":
        raise ValueError("unsupported governed constants schema")
    values = payload.get("gex_chain_resolution")
    if not isinstance(values, Mapping):
        raise ValueError("governed constants omit gex_chain_resolution")
    if values.get("threshold_version") != "gex_chain_resolution_v1":
        raise ValueError("unsupported gex chain resolution threshold version")

    def sessions(name: str) -> int:
        value = int(values[name])
        if value < 0:
            raise ValueError(f"gex chain resolution {name} must not be negative")
        return value

    return ChainResolutionPolicy(
        forward_roll_max_sessions=sessions("forward_roll_max_sessions"),
        backward_roll_max_sessions=sessions("backward_roll_max_sessions"),
        threshold_version=str(values["threshold_version"]),
    )


def _xnys_walk(anchor: date, *, step: int, limit: int) -> Iterable[tuple[int, date]]:
    """Yield (sessions_rolled, session) away from an anchor of any kind.

    The anchor itself is never yielded and need not be a session, so a weekend
    or holiday request still rolls correctly.
    """

    rolled = 0
    candidate = anchor
    while rolled < limit:
        candidate += timedelta(days=step)
        if not is_xnys_session(candidate):
            continue
        rolled += 1
        yield rolled, candidate


class PhantomOptionChainRepository:
    """Read-only adapter over the existing Phantom chain store."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def _connection(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        uri = f"file:{self.database_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        # GROUP BY / ORDER BY must not depend on an OS temp directory that a
        # restricted production service account may be unable to write.
        connection.execute("PRAGMA temp_store = MEMORY")
        return connection

    def latest_common_session(self, tickers: Iterable[str]) -> date:
        names = tuple(sorted({str(value).strip().upper() for value in tickers if str(value).strip()}))
        if not names:
            raise ValueError("at least one ticker is required")
        placeholders = ",".join("?" for _ in names)
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT quote_date
                FROM chain_snapshots
                WHERE ticker IN ({placeholders})
                GROUP BY quote_date
                HAVING COUNT(DISTINCT ticker) = ?
                ORDER BY quote_date DESC
                LIMIT 1
                """,
                (*names, len(names)),
            ).fetchone()
        if row is None:
            raise ValueError(f"no common completed option session for {','.join(names)}")
        return date.fromisoformat(str(row[0])[:10])

    def has_chain(self, tickers: Iterable[str], session_date: date) -> bool:
        """True when every requested ticker has a stored chain for the session."""

        names = tuple(sorted({str(value).strip().upper() for value in tickers if str(value).strip()}))
        if not names:
            raise ValueError("at least one ticker is required")
        placeholders = ",".join("?" for _ in names)
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(DISTINCT ticker)
                FROM chain_snapshots
                WHERE ticker IN ({placeholders}) AND quote_date=?
                """,
                (*names, session_date.isoformat()),
            ).fetchone()
        return bool(row) and int(row[0]) == len(names)

    def resolve_session(
        self,
        tickers: Iterable[str],
        session_date: date,
        *,
        policy: ChainResolutionPolicy | None = None,
    ) -> ChainResolution:
        """Resolve the requested chain session, rolling forward then backward.

        A roll is reported, never hidden: the caller labels the session actually
        measured so downstream authority checks still compare against reality.
        """

        window = policy or load_chain_resolution_policy()
        if self.has_chain(tickers, session_date):
            return ChainResolution(session_date, session_date, "EXACT", 0)
        for rolled, candidate in _xnys_walk(
            session_date, step=1, limit=window.forward_roll_max_sessions
        ):
            if self.has_chain(tickers, candidate):
                return ChainResolution(session_date, candidate, "FORWARD", rolled)
        for rolled, candidate in _xnys_walk(
            session_date, step=-1, limit=window.backward_roll_max_sessions
        ):
            if self.has_chain(tickers, candidate):
                return ChainResolution(session_date, candidate, "BACKWARD", rolled)
        return ChainResolution(session_date, None, "NONE", 0)

    def read(self, ticker: str, session_date: date, *, dataset_id: str | None = None) -> pd.DataFrame:
        with self._connection() as connection:
            if dataset_id is not None:
                records = connection.execute(
                    "SELECT row_json FROM canonical_option_chain_revisions "
                    "WHERE dataset_id=? AND ticker=? AND quote_date=? ORDER BY option_symbol",
                    (dataset_id, ticker.upper(), session_date.isoformat()),
                ).fetchall()
                frame = pd.DataFrame([json.loads(row[0]) for row in records])
            else:
                frame = pd.read_sql_query(
                    "SELECT * FROM chain_snapshots WHERE ticker=? AND quote_date=? ORDER BY option_symbol",
                    connection,
                    params=(ticker.upper(), session_date.isoformat()),
                )
        if frame.empty:
            raise ValueError(f"chain unavailable for {ticker.upper()}/{session_date.isoformat()}")
        return frame


def prepare_gex_greeks(chain: pd.DataFrame, config: GammaExposureConfig) -> tuple[pd.DataFrame, dict]:
    """Derive missing historical Greeks on a copy; never rewrite provider evidence.

    Reuses Phantom's local BS calculator. Only unadjusted successful solutions
    from valid two-sided observations are admitted. Coverage gates remain in
    the domain calculation. The calculator assumes zero dividend yield.
    """
    frame = chain.copy()
    calculated = 0
    rejected = 0
    in_scope = pd.to_numeric(frame["dte"], errors="coerce").between(config.dte_min, config.dte_max)
    for index, row in frame.loc[in_scope].iterrows():
        if pd.notna(row.get("gamma")) and pd.notna(row.get("iv")):
            continue
        bid, ask = pd.to_numeric(pd.Series([row.get("bid"), row.get("ask")]), errors="coerce")
        if config.dividend_yield != 0 or not (pd.notna(bid) and pd.notna(ask) and 0 <= bid <= ask and ask > 0):
            rejected += 1
            continue
        inputs = row.to_dict()
        inputs["mid"] = (float(bid) + float(ask)) / 2.0
        result = compute_greeks_from_row(inputs, risk_free_rate=config.risk_free_rate)
        if result.quality_status != "OK":
            rejected += 1
            continue
        for field in ("iv", "delta", "gamma", "theta", "vega"):
            if pd.isna(row.get(field)):
                frame.at[index, field] = getattr(result, field)
        calculated += 1
    return frame, {
        "Greek_Derivation": "PHANTOM_BS_MISSING_ONLY_V1",
        "Greek_Computed_Contracts": calculated,
        "Greek_Unresolved_Contracts": rejected,
        "Greek_Risk_Free_Rate": config.risk_free_rate,
        "Greek_Dividend_Yield": config.dividend_yield,
        "Greek_Model_Disclosure": "European BS approximation; not observed provider Greeks",
    }


class CanonicalGammaExposureStore:
    """Persist immutable derived GEX payloads and register their lineage."""

    def __init__(self, *, registry_path: Path | str, payload_root: Path | str) -> None:
        self.registry = CanonicalRegistry(Path(registry_path))
        self.registry.initialise()
        self.payload_root = Path(payload_root)

    def _parent_ids(self, ticker: str, session_date: date) -> tuple[str, ...]:
        return tuple(
            record.dataset_id
            for record in self.registry.list_dataset_records(
                DatasetType.OPTION_CHAIN, instrument_id=ticker
            )
            if record.session_date == session_date
        )

    def _validated_parent_ids(
        self,
        ticker: str,
        session_date: date,
        parent_dataset_ids: Iterable[str] | None,
    ) -> tuple[str, ...]:
        if parent_dataset_ids is None:
            return self._parent_ids(ticker, session_date)
        resolved = tuple(dict.fromkeys(
            str(dataset_id).strip()
            for dataset_id in parent_dataset_ids
            if str(dataset_id).strip()
        ))
        if not resolved:
            raise ValueError("GEX requires an option-chain parent dataset")
        for dataset_id in resolved:
            record = self.registry.get_dataset(dataset_id)
            if record is None:
                raise ValueError(f"GEX parent dataset is not registered: {dataset_id}")
            if (
                record.dataset_type is not DatasetType.OPTION_CHAIN
                or record.instrument_id != ticker.upper()
                or record.session_date != session_date
                or record.completeness_status is not CompletenessStatus.COMPLETE
            ):
                raise ValueError(
                    f"GEX parent dataset is outside the calculated chain scope: {dataset_id}"
                )
        return resolved

    def persist(
        self,
        result: GammaExposureResult,
        *,
        run_id: str,
        config: GammaExposureConfig,
        parent_dataset_ids: Iterable[str] | None = None,
    ) -> DatasetRecord:
        session_date = date.fromisoformat(result.session_date)
        target_dir = self.payload_root / result.session_date / result.ticker
        target_dir.mkdir(parents=True, exist_ok=True)
        by_strike = target_dir / f"{config.scope_name.lower()}_by_strike.parquet"
        temporary = by_strike.with_suffix(f".tmp-{uuid4().hex}.parquet")
        result.by_strike.to_parquet(temporary, index=False)
        os.replace(temporary, by_strike)
        by_strike_hash = _sha256(by_strike)
        parents = self._validated_parent_ids(
            result.ticker,
            session_date,
            parent_dataset_ids,
        )
        summary = dict(result.summary)
        summary.update({
            "By_Strike_Path": str(by_strike.resolve()),
            "By_Strike_SHA256": by_strike_hash,
            "Parent_Dataset_IDs": list(parents),
        })
        summary_path = target_dir / f"{config.scope_name.lower()}_summary.json"
        _atomic_json(summary_path, summary)
        content_hash = _sha256(summary_path)
        dataset_id = hashlib.sha256(
            f"{DatasetType.GAMMA_EXPOSURE.value}|{result.ticker}|{result.session_date}|{config.scope_name}|{content_hash}".encode()
        ).hexdigest()
        _, close_utc = session_bounds(session_date)
        record = DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=DatasetType.GAMMA_EXPOSURE,
            instrument_id=result.ticker,
            session_date=session_date,
            scope=DataScope(
                start_date=session_date,
                end_date=session_date,
                dte_min=config.dte_min,
                dte_max=config.dte_max,
                sides=("CALL", "PUT"),
                extra=(("scope", config.scope_name),),
            ),
            provider="DERIVED_LOCAL",
            adjustment_convention=GEX_ADJUSTMENT,
            schema_version=GEX_SCHEMA_VERSION,
            content_hash=content_hash,
            completeness_status=CompletenessStatus.COMPLETE,
            storage_uri=str(summary_path.resolve()),
            observed_at=datetime.now(timezone.utc),
            as_of=close_utc,
            quality_flags=tuple(filter(None, str(summary.get("Quality_Flags") or "").split("|"))),
            parent_dataset_ids=tuple(summary["Parent_Dataset_IDs"]),
            source_run_id=run_id,
        )
        self.registry.register_dataset(record)
        return record


__all__ = [
    "CanonicalGammaExposureStore",
    "GEX_ADJUSTMENT",
    "GEX_SCHEMA_VERSION",
    "PhantomOptionChainRepository",
]
