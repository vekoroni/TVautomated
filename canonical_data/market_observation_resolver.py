"""CDS-owned market observation contracts and provider-independent resolver.

Consumers pass a fetch callback; credentials and endpoint details stay in the
provider adapter.  Every cache decision remains governed by the existing CDS
gateway, lifecycle worklist, immutable registry and request ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from .contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetRequest, DatasetType, ResolutionKind
from .feature_flags import CanonicalFeatureFlags
from .gateway import CanonicalDataGateway
from .lifecycle import LifecycleManager
from .marketdata_response import parse_exact_option_quote, parse_marketdata_option_response
from .option_identity import normalise_occ_symbol
from .registry import CanonicalRegistry
from .request_ledger import RequestLedger, RequestResolution
from .storage import AtomicPayloadStore
from .session_clock import session_bounds


OPTION_CHAIN_V2 = "option_chain_v2"
EXACT_OPTION_QUOTE_V2 = "exact_option_quote_v2"
UNDERLYING_NBBO_QUOTE_V1 = "underlying_nbbo_quote_v1"


@dataclass(frozen=True, slots=True)
class ObservationResult:
    payload: Any
    resolution: str
    dataset_id: str | None
    provider: str


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _utc(value: Any) -> datetime:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("observation timestamp must be timezone-aware")
    return parsed.tz_convert("UTC").to_pydatetime()


def _size(value: Any) -> tuple[int | None, str]:
    if value is None or str(value).strip().upper() in {"", "NONE", "NULL", "NAN"}:
        return None, "MISSING"
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid displayed size {value!r}") from error
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValueError(f"invalid displayed size {value!r}")
    result = int(numeric)
    return result, "OBSERVED_ZERO" if result == 0 else "OBSERVED_POSITIVE"


def normalise_underlying_nbbo(payload: Mapping[str, Any], *, ticker: str, provider: str) -> dict[str, Any]:
    def first(name: str) -> Any:
        value = payload.get(name)
        return value[0] if isinstance(value, (list, tuple)) and value else value
    bid, ask = first("bid"), first("ask")
    try:
        bid, ask = float(bid), float(ask)
    except (TypeError, ValueError) as error:
        raise ValueError("underlying NBBO requires bid and ask") from error
    if not math.isfinite(bid) or not math.isfinite(ask) or bid < 0 or ask <= 0 or bid > ask:
        raise ValueError(f"invalid underlying NBBO bid={bid} ask={ask}")
    bid_size, bid_quality = _size(first("bidSize"))
    ask_size, ask_quality = _size(first("askSize"))
    updated = first("updated")
    as_of = _utc(updated).replace(microsecond=0)
    return {
        "ticker": ticker.strip().upper(), "bid": round(bid, 4), "ask": round(ask, 4),
        "mid": round((bid + ask) / 2.0, 4), "bid_size": bid_size, "ask_size": ask_size,
        "bid_size_quality": bid_quality, "ask_size_quality": ask_quality,
        "provider_updated_utc": as_of.isoformat().replace("+00:00", "Z"),
        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": provider.upper(), "depth_level": "NBBO_ONLY",
    }


class CanonicalMarketObservationResolver:
    def __init__(self, *, registry_path: Path, payload_root: Path, run_id: str,
                 invocation_id: str | None = None,
                 evidence_cutoff_utc: datetime | None = None,
                 exchange_calendar: str = "XNYS",
                 flags: CanonicalFeatureFlags | None = None) -> None:
        self.registry = CanonicalRegistry(registry_path)
        self.registry.initialise()
        self.lifecycle = LifecycleManager(self.registry)
        self.ledger = RequestLedger(self.registry)
        self.flags = flags or CanonicalFeatureFlags.from_environment()
        self.gateway = CanonicalDataGateway(self.registry, self.lifecycle, self.ledger, flags=self.flags)
        self.store = AtomicPayloadStore(payload_root)
        self.run_id = run_id
        self.invocation_id = invocation_id or run_id
        self.evidence_cutoff_utc = evidence_cutoff_utc
        self.exchange_calendar = exchange_calendar

    def _cutoff(self, session_date: date, *, completed: bool) -> datetime:
        if self.evidence_cutoff_utc is not None:
            return self.evidence_cutoff_utc
        return session_bounds(session_date)[1] if completed else datetime.now(timezone.utc)

    def _read_json(self, record: DatasetRecord) -> Any:
        path = Path(record.storage_uri)
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.content_hash:
            raise ValueError(f"canonical observation failed integrity: {path}")
        return json.loads(payload)

    def _persist_json(
        self, *, request: DatasetRequest, payload: Any, provider: str, as_of: datetime,
        quality_flags: tuple[str, ...] = (), parent_dataset_ids: tuple[str, ...] = (),
    ) -> DatasetRecord:
        safe = _json_safe(payload)
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        relative = Path(request.dataset_type.value.lower()) / request.session_date.isoformat() / request.instrument_id / f"{content_hash}.json"
        stored = self.store.write_bytes(relative, encoded)
        dataset_id = hashlib.sha256(
            f"{request.dataset_type.value}|{request.instrument_id}|{request.session_date}|{request.scope.fingerprint}|{content_hash}".encode()
        ).hexdigest()
        record = DatasetRecord(
            dataset_id=dataset_id, dataset_type=request.dataset_type,
            instrument_id=request.instrument_id, session_date=request.session_date,
            scope=request.scope, provider=provider, content_hash=stored.content_hash,
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(stored.path),
            observed_at=datetime.now(timezone.utc), as_of=as_of,
            adjustment_convention=request.adjustment_convention,
            schema_version=request.schema_version, quality_flags=quality_flags,
            parent_dataset_ids=parent_dataset_ids, source_run_id=self.run_id,
        )
        self.registry.register_dataset(record)
        return record

    def _resolve(
        self, request: DatasetRequest, *, provider: str,
        fetch: Callable[[], Any], normalise: Callable[[Any], tuple[Any, datetime, tuple[str, ...]]],
    ) -> ObservationResult:
        resolved = self.gateway.resolve(request)
        if resolved.kind in {ResolutionKind.EXACT_HIT, ResolutionKind.SUPERSET_HIT}:
            record = resolved.records[0]
            return ObservationResult(self._read_json(record), resolved.kind.value, record.dataset_id, record.provider)
        if self.flags.offline_replay:
            return ObservationResult(None, "OFFLINE_CACHE_MISS", None, "CANONICAL")
        ledger_id = self.ledger.start(request, provider=provider)
        try:
            payload, as_of, flags = normalise(fetch())
            record = self._persist_json(request=request, payload=payload, provider=provider, as_of=as_of, quality_flags=flags)
            self.ledger.finish(ledger_id, RequestResolution.PROVIDER_FETCH, dataset_id=record.dataset_id, physical_request_count=1)
            return ObservationResult(payload, "PROVIDER_FETCH", record.dataset_id, provider)
        except Exception as error:
            self.ledger.finish(ledger_id, RequestResolution.PROVIDER_ERROR, physical_request_count=1, reason=f"{type(error).__name__}:{error}")
            raise

    def option_chain(
        self, *, ticker: str, session_date: date, dte_max: int, min_open_interest: int,
        fetch: Callable[[str], Mapping[str, Any]], provider: str = "MARKETDATA",
    ) -> ObservationResult:
        scope = DataScope(start_date=session_date, end_date=session_date, dte_min=1, dte_max=dte_max,
                          sides=("CALL", "PUT"), extra=(("min_open_interest", str(min_open_interest)),))
        request = DatasetRequest(self.run_id, "OPTIONS", DatasetType.OPTION_CHAIN, ticker, session_date,
                                 scope=scope, accepted_providers=(provider,), adjustment_convention="RAW_OPTION_CONTRACT",
                                 schema_version=OPTION_CHAIN_V2, invocation_id=self.invocation_id,
                                 evidence_cutoff_utc=self._cutoff(session_date, completed=True),
                                 exchange_calendar=self.exchange_calendar, evidence_state="COMPLETED_SESSION")
        def normalise(raw: Mapping[str, Any]) -> tuple[Any, datetime, tuple[str, ...]]:
            frame = parse_marketdata_option_response(raw, ticker=ticker, quote_source=provider)
            if frame.empty:
                raise ValueError("empty option chain")
            timestamps = pd.to_datetime(frame["quote_timestamp_utc"], errors="coerce", utc=True).dropna()
            if len(timestamps) / len(frame) < 0.80:
                raise ValueError("option-chain quote timestamp coverage below 80%")
            if float((timestamps.dt.date == session_date).mean()) < 0.80:
                raise ValueError("option-chain quote/session mismatch")
            flags = ("CONTAINS_CROSSED_QUOTES",) if frame["quality_flags"].str.contains("CROSSED_QUOTE").any() else ()
            return frame.to_dict("records"), timestamps.max().to_pydatetime(), flags
        return self._resolve(request, provider=provider, fetch=lambda: fetch(ticker), normalise=normalise)

    def exact_option_quote(
        self, *, ticker: str, symbol: str, session_date: date, freshness_seconds: int,
        fetch: Callable[[str, str], Mapping[str, Any]], thesis_id: str = "", trade_idea_id: str = "",
        selected_structure_id: str = "", leg_identity: str = "LONG_LEG", provider: str = "MARKETDATA",
    ) -> ObservationResult:
        canonical = normalise_occ_symbol(symbol)
        scope = DataScope(extra=(("occ", canonical), ("thesis_id", thesis_id), ("trade_idea_id", trade_idea_id),
                                 ("selected_structure_id", selected_structure_id), ("leg_identity", leg_identity)))
        request = DatasetRequest(self.run_id, "MORNING_GATE", DatasetType.EXACT_OPTION_QUOTE, ticker, session_date,
                                 scope=scope, freshness_seconds=freshness_seconds, accepted_providers=(provider,),
                                 adjustment_convention="RAW_OPTION_CONTRACT", schema_version=EXACT_OPTION_QUOTE_V2,
                                 invocation_id=self.invocation_id,
                                 evidence_cutoff_utc=self._cutoff(session_date, completed=False),
                                 exchange_calendar=self.exchange_calendar, evidence_state="CURRENT_QUOTE")
        def normalise(raw: Mapping[str, Any]) -> tuple[Any, datetime, tuple[str, ...]]:
            quote = parse_exact_option_quote(raw, ticker=ticker, symbol=canonical)
            quote.update({"run_id": self.run_id, "thesis_id": thesis_id, "trade_idea_id": trade_idea_id,
                          "selected_structure_id": selected_structure_id, "leg_identity": leg_identity})
            return quote, _utc(quote["quote_timestamp_utc"]), tuple(filter(None, str(quote.get("quality_flags", "")).split("|")))
        return self._resolve(request, provider=provider, fetch=lambda: fetch(ticker, canonical), normalise=normalise)

    def underlying_nbbo(
        self, *, ticker: str, session_date: date, freshness_seconds: int,
        fetch: Callable[[str], Mapping[str, Any]], provider: str,
    ) -> ObservationResult:
        request = DatasetRequest(self.run_id, "MORNING_GATE", DatasetType.UNDERLYING_NBBO, ticker, session_date,
                                 scope=DataScope(fields=("BID", "ASK", "BID_SIZE", "ASK_SIZE")),
                                 freshness_seconds=freshness_seconds, accepted_providers=(provider,),
                                 adjustment_convention="UNADJUSTED", schema_version=UNDERLYING_NBBO_QUOTE_V1,
                                 invocation_id=self.invocation_id,
                                 evidence_cutoff_utc=self._cutoff(session_date, completed=False),
                                 exchange_calendar=self.exchange_calendar, evidence_state="CURRENT_QUOTE")
        def normalise(raw: Mapping[str, Any]) -> tuple[Any, datetime, tuple[str, ...]]:
            quote = normalise_underlying_nbbo(raw, ticker=ticker, provider=provider)
            return quote, _utc(quote["provider_updated_utc"]), ()
        return self._resolve(request, provider=provider, fetch=lambda: fetch(ticker), normalise=normalise)
