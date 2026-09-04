"""Immutable canonical intraday bars and governed missing-range resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

import pandas as pd

from .contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetRequest, DatasetType, ResolutionKind
from .errors import FetchNotAuthorised
from .feature_flags import CanonicalFeatureFlags
from .gateway import CanonicalDataGateway
from .lifecycle import LifecycleManager
from .registry import CanonicalRegistry
from .request_ledger import RequestLedger, RequestResolution
from .session_clock import is_xnys_session, session_bounds


INTRADAY_BAR_SCHEMA_VERSION = "underlying_intraday_bar_v1"
INTRADAY_BAR_SCHEMA_V2 = "underlying_intraday_bar_v2"
INTRADAY_ADJUSTMENT = "UNADJUSTED"
SUPPORTED_INTERVALS = (1, 5, 15, 30)


def intraday_schema_version(interval_minutes: int) -> str:
    interval = int(interval_minutes)
    return INTRADAY_BAR_SCHEMA_VERSION if interval == 1 else f"{INTRADAY_BAR_SCHEMA_V2}_{interval}min"


@dataclass(frozen=True, slots=True)
class IntradayQuality:
    expected_count: int
    observed_count: int
    duplicate_count: int
    missing_count: int
    unexpected_count: int
    coverage_ratio: float
    max_gap_minutes: int
    completeness_status: str
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntradayRequestPlan:
    requested_count: int
    observable_count: int
    cached_count: int
    missing_count: int
    missing_ranges: tuple[tuple[datetime, datetime], ...]
    estimated_physical_requests: int
    deferred_count: int


@dataclass(frozen=True, slots=True)
class IntradayBarResult:
    frame: pd.DataFrame
    resolution: str
    dataset_ids: tuple[str, ...]
    physical_fetches: int
    request_plan: IntradayRequestPlan | None = None
    quality: IntradayQuality | None = None


@dataclass(frozen=True, slots=True)
class IntradayBatchResult:
    results: dict[str, IntradayBarResult]
    exceptions: dict[str, str]
    requested: tuple[str, ...]
    succeeded: tuple[str, ...]
    blocked: tuple[str, ...]
    failed: tuple[str, ...]


def _utc_minute(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("intraday timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def normalise_intraday_bars(
    frame: pd.DataFrame,
    *,
    ticker: str,
    interval_minutes: int,
    session_date: date | None = None,
    session_segment: str = "REGULAR",
    adjustment_convention: str = INTRADAY_ADJUSTMENT,
    provider: str = "UNKNOWN",
    acquired_at_utc: datetime | None = None,
) -> pd.DataFrame:
    """Validate and enrich bars without aggregating provider candles."""
    interval = int(interval_minutes)
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"unsupported intraday interval: {interval}; expected one of {SUPPORTED_INTERVALS}")
    rename = {"t": "timestamp_utc", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap_provider", "n": "trade_count"}
    result = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns}).copy()
    required = {"timestamp_utc", "open", "high", "low", "close", "volume"}
    missing = required - set(result.columns)
    if missing:
        raise ValueError(f"intraday bars missing fields: {sorted(missing)}")
    result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], errors="raise", utc=True).dt.floor("min")
    for name in ("open", "high", "low", "close", "volume", "vwap_provider", "trade_count"):
        if name in result:
            result[name] = pd.to_numeric(result[name], errors="coerce")
    if result[list(required - {"timestamp_utc"})].isna().any().any():
        raise ValueError("intraday bars contain invalid required numeric values")
    if (result["volume"] < 0).any() or (result[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("intraday bars contain negative volume or non-positive price")
    if ((result["high"] < result[["open", "close", "low"]].max(axis=1)) | (result["low"] > result[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("intraday bars violate OHLC bounds")
    result["ticker"] = ticker.strip().upper()
    first_date = result["timestamp_utc"].iloc[0].date().isoformat() if len(result) else None
    result["session_date"] = session_date.isoformat() if session_date else first_date
    result["interval_minutes"] = interval
    result["session_segment"] = session_segment.strip().upper()
    result["adjustment_convention"] = adjustment_convention.strip().upper()
    result["provider"] = provider.strip().upper()
    result["corporate_action_on_session"] = result.get("corporate_action_on_session", False)
    if "provider_observed_at_utc" not in result:
        result["provider_observed_at_utc"] = result["timestamp_utc"]
    result["provider_observed_at_utc"] = pd.to_datetime(result["provider_observed_at_utc"], errors="raise", utc=True)
    result["observed_at"] = result["provider_observed_at_utc"]
    acquired = acquired_at_utc or datetime.now(timezone.utc)
    if acquired.tzinfo is None:
        raise ValueError("acquired_at_utc must be timezone-aware")
    if "acquired_at_utc" not in result:
        result["acquired_at_utc"] = acquired.astimezone(timezone.utc)
    result["acquired_at_utc"] = pd.to_datetime(result["acquired_at_utc"], errors="raise", utc=True)
    result = result.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
    typical = (result["high"] + result["low"] + result["close"]) / 3.0
    regular = result["session_segment"].eq("REGULAR")
    numerator = (typical.where(regular, 0.0) * result["volume"].where(regular, 0.0)).cumsum()
    denominator = result["volume"].where(regular, 0.0).cumsum()
    result["vwap_canonical"] = numerator.div(denominator.where(denominator > 0))
    return result


def normalise_minute_bars(frame: pd.DataFrame, *, ticker: str, session_segment: str = "REGULAR") -> pd.DataFrame:
    """Backward-compatible one-minute entry point."""
    return normalise_intraday_bars(frame, ticker=ticker, interval_minutes=1, session_segment=session_segment)


def expected_intraday_timestamps(
    *, session_date: date, start_utc: datetime, end_utc: datetime,
    interval_minutes: int, session_segment: str = "REGULAR",
) -> pd.DatetimeIndex:
    """Return bar-open timestamps for an inclusive request range."""
    start, end = _utc_minute(start_utc), _utc_minute(end_utc)
    interval = int(interval_minutes)
    if start > end:
        return pd.DatetimeIndex([], tz="UTC")
    inclusive_end = end
    if session_segment.strip().upper() == "REGULAR" and is_xnys_session(session_date):
        regular_open, regular_close = session_bounds(session_date)
        if start <= regular_open and end >= regular_close:
            start = max(start, regular_open)
            inclusive_end = regular_close - timedelta(minutes=interval)
    return pd.date_range(start, inclusive_end, freq=f"{interval}min")


def missing_intraday_ranges(
    expected: pd.DatetimeIndex,
    available: set[pd.Timestamp],
    *, interval_minutes: int,
    max_intervals_per_request: int = 500,
) -> tuple[tuple[datetime, datetime], ...]:
    missing = [value for value in expected if value not in available]
    if not missing:
        return ()
    step = pd.Timedelta(minutes=interval_minutes)
    contiguous: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start = prior = missing[0]
    for value in missing[1:]:
        if value - prior != step:
            contiguous.append((start, prior)); start = value
        prior = value
    contiguous.append((start, prior))
    ranges: list[tuple[datetime, datetime]] = []
    limit = max(1, int(max_intervals_per_request))
    for range_start, range_end in contiguous:
        cursor = range_start
        while cursor <= range_end:
            chunk_end = min(range_end, cursor + step * (limit - 1))
            ranges.append((cursor.to_pydatetime(), chunk_end.to_pydatetime()))
            cursor = chunk_end + step
    return tuple(ranges)


def assess_intraday_quality(frame: pd.DataFrame, expected: pd.DatetimeIndex, *, interval_minutes: int) -> IntradayQuality:
    timestamps = pd.to_datetime(frame.get("timestamp_utc", pd.Series(dtype="datetime64[ns, UTC]")), utc=True)
    duplicate_count = int(timestamps.duplicated(keep=False).sum())
    observed = set(pd.DatetimeIndex(timestamps.drop_duplicates()))
    expected_set = set(expected)
    missing = sorted(expected_set - observed)
    unexpected = sorted(observed - expected_set)
    observed_expected = len(expected_set & observed)
    expected_count = len(expected_set)
    coverage = observed_expected / expected_count if expected_count else 1.0
    max_gap = 0
    if missing:
        step = pd.Timedelta(minutes=interval_minutes); run = longest = 1
        for prior, current in zip(missing, missing[1:]):
            run = run + 1 if current - prior == step else 1; longest = max(longest, run)
        max_gap = longest * interval_minutes
    flags = tuple(name for condition, name in (
        (duplicate_count > 0, "DUPLICATE_TIMESTAMPS"),
        (bool(missing), "MISSING_INTERVALS"),
        (bool(unexpected), "OUTSIDE_REQUEST_SCOPE"),
    ) if condition)
    status = "INVALID_DUPLICATES" if duplicate_count else ("PARTIAL_GAPS" if missing else "COMPLETE")
    return IntradayQuality(expected_count, observed_expected, duplicate_count, len(missing), len(unexpected), round(coverage, 8), max_gap, status, flags)


class CanonicalMinuteBarResolver:
    """Interval-aware resolver; the historic class name is retained for callers."""

    def __init__(self, *, registry_path: Path, payload_root: Path, run_id: str,
                 invocation_id: str | None = None, evidence_cutoff_utc: datetime | None = None,
                 exchange_calendar: str = "XNYS", requesting_stage: str = "MARKET_STRUCTURE",
                 flags: CanonicalFeatureFlags | None = None) -> None:
        self.registry = CanonicalRegistry(registry_path); self.registry.initialise()
        self.lifecycle = LifecycleManager(self.registry); self.ledger = RequestLedger(self.registry)
        self.flags = flags or CanonicalFeatureFlags.from_environment()
        self.gateway = CanonicalDataGateway(self.registry, self.lifecycle, self.ledger, flags=self.flags)
        self.payload_root = Path(payload_root); self.run_id = run_id
        self.invocation_id = invocation_id or run_id
        self.evidence_cutoff_utc = evidence_cutoff_utc
        self.exchange_calendar = exchange_calendar
        self.requesting_stage = str(requesting_stage).strip().upper()
        if not self.requesting_stage:
            raise ValueError("requesting_stage is required")

    @staticmethod
    def _scope(start: datetime, end: datetime, *, interval_minutes: int = 1,
               session_segment: str = "REGULAR", evidence_state: str = "DEVELOPING_SESSION") -> DataScope:
        return DataScope(fields=("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"), extra=(
            ("interval", f"{int(interval_minutes)}min"), ("start_utc", start.isoformat()),
            ("end_utc", end.isoformat()), ("session_segment", session_segment.strip().upper()),
            ("evidence_state", evidence_state.strip().upper()),
        ))

    @staticmethod
    def _read(record: DatasetRecord) -> pd.DataFrame:
        path = Path(record.storage_uri); payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.content_hash:
            raise ValueError(f"intraday-bar integrity failure: {path}")
        frame = pd.read_parquet(path)
        if "timestamp_utc" in frame:
            frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        frame["dataset_id"] = record.dataset_id
        frame["content_hash"] = record.content_hash
        frame["completeness_status"] = record.completeness_status.value
        return frame

    def _persist(self, request: DatasetRequest, frame: pd.DataFrame, provider: str, quality: IntradayQuality) -> DatasetRecord:
        target_dir = self.payload_root / "intraday_bar" / request.session_date.isoformat() / request.instrument_id
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target_dir / f".{uuid4().hex}.tmp.parquet"; frame.to_parquet(temporary, index=False)
        payload = temporary.read_bytes(); content_hash = hashlib.sha256(payload).hexdigest()
        target = target_dir / f"{content_hash}.parquet"
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == content_hash:
            temporary.unlink()
        else:
            os.replace(temporary, target)
        as_of = pd.to_datetime(frame["provider_observed_at_utc"], utc=True).max().to_pydatetime()
        observed = pd.to_datetime(frame["acquired_at_utc"], utc=True).max().to_pydatetime()
        dataset_id = hashlib.sha256(f"{DatasetType.INTRADAY_BAR.value}|{request.instrument_id}|{request.scope.fingerprint}|{content_hash}".encode()).hexdigest()
        status = CompletenessStatus.COMPLETE if quality.completeness_status == "COMPLETE" else CompletenessStatus.PARTIAL
        record = DatasetRecord(dataset_id, DatasetType.INTRADAY_BAR, request.instrument_id, request.session_date,
                               request.scope, provider, content_hash, status, str(target.resolve()), observed, as_of,
                               adjustment_convention=request.adjustment_convention, schema_version=request.schema_version,
                               quality_flags=quality.quality_flags, source_run_id=self.run_id)
        self.registry.register_dataset(record); return record

    def plan(self, *, session_date: date, start_utc: datetime, end_utc: datetime, interval_minutes: int,
             available: set[pd.Timestamp], session_segment: str = "REGULAR",
             max_intervals_per_request: int = 500) -> tuple[IntradayRequestPlan, pd.DatetimeIndex]:
        requested = expected_intraday_timestamps(session_date=session_date, start_utc=start_utc, end_utc=end_utc,
                                                 interval_minutes=interval_minutes, session_segment=session_segment)
        cutoff = pd.Timestamp(_utc_minute(self.evidence_cutoff_utc)) if self.evidence_cutoff_utc else None
        observable = requested if cutoff is None else requested[requested <= cutoff]
        ranges = missing_intraday_ranges(observable, available, interval_minutes=interval_minutes,
                                         max_intervals_per_request=max_intervals_per_request)
        cached_count = len(set(observable) & available)
        plan = IntradayRequestPlan(len(requested), len(observable), cached_count, len(observable) - cached_count,
                                   ranges, len(ranges), len(requested) - len(observable))
        return plan, observable

    def resolve(self, *, ticker: str, session_date: date, start_utc: datetime, end_utc: datetime,
                fetch_missing: Callable[[str, datetime, datetime], pd.DataFrame], provider: str,
                session_segment: str = "REGULAR", evidence_state: str = "DEVELOPING_SESSION",
                interval_minutes: int = 1, adjustment_convention: str = INTRADAY_ADJUSTMENT,
                max_intervals_per_request: int = 500) -> IntradayBarResult:
        if start_utc.tzinfo is None or end_utc.tzinfo is None or start_utc > end_utc:
            raise ValueError("valid timezone-aware intraday interval required")
        interval = int(interval_minutes)
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(f"unsupported intraday interval: {interval}")
        start, end = _utc_minute(start_utc), _utc_minute(end_utc)
        schema = intraday_schema_version(interval)
        scope = self._scope(start, end, interval_minutes=interval, session_segment=session_segment, evidence_state=evidence_state)
        request = DatasetRequest(self.run_id, self.requesting_stage, DatasetType.INTRADAY_BAR, ticker, session_date,
                                 scope=scope, accepted_providers=(provider,), adjustment_convention=adjustment_convention,
                                 schema_version=schema, invocation_id=self.invocation_id,
                                 evidence_cutoff_utc=self.evidence_cutoff_utc or end,
                                 exchange_calendar=self.exchange_calendar, evidence_state=evidence_state)
        resolution = self.gateway.resolve(request)
        records = list(resolution.records)
        if resolution.kind in {ResolutionKind.EXACT_HIT, ResolutionKind.SUPERSET_HIT}:
            frame = pd.concat([self._read(record) for record in records], ignore_index=True)
            frame = frame[(frame["timestamp_utc"] >= start) & (frame["timestamp_utc"] <= end)].reset_index(drop=True)
            expected = expected_intraday_timestamps(session_date=session_date, start_utc=start, end_utc=end,
                                                    interval_minutes=interval, session_segment=session_segment)
            quality = assess_intraday_quality(frame, expected, interval_minutes=interval)
            plan = IntradayRequestPlan(len(expected), len(expected), len(expected), 0, (), 0, 0)
            return IntradayBarResult(frame, resolution.kind.value, tuple(r.dataset_id for r in records), 0, plan, quality)

        records = [r for r in self.registry.list_dataset_records(DatasetType.INTRADAY_BAR, instrument_id=ticker)
                   if r.session_date == session_date and r.schema_version == schema
                   and r.adjustment_convention == adjustment_convention and r.provider == provider.strip().upper()]
        frames = [self._read(record) for record in records]
        available = set(pd.to_datetime(pd.concat(frames, ignore_index=True)["timestamp_utc"], utc=True)) if frames else set()
        plan, observable = self.plan(session_date=session_date, start_utc=start, end_utc=end, interval_minutes=interval,
                                     available=available, session_segment=session_segment,
                                     max_intervals_per_request=max_intervals_per_request)
        if not len(observable):
            empty = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            return IntradayBarResult(empty, "DEFERRED_NOT_OBSERVABLE", tuple(r.dataset_id for r in records), 0,
                                     plan, assess_intraday_quality(empty, observable, interval_minutes=interval))
        if plan.missing_ranges and self.flags.offline_replay:
            existing = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            return IntradayBarResult(existing, "OFFLINE_PARTIAL", tuple(r.dataset_id for r in records), 0,
                                     plan, assess_intraday_quality(existing, observable, interval_minutes=interval))

        new_records: list[DatasetRecord] = []; physical_fetches = 0
        for gap_start, gap_end in plan.missing_ranges:
            gap_scope = self._scope(gap_start, gap_end, interval_minutes=interval,
                                    session_segment=session_segment, evidence_state=evidence_state)
            gap_request = DatasetRequest(self.run_id, self.requesting_stage, DatasetType.INTRADAY_BAR, ticker, session_date,
                                         scope=gap_scope, accepted_providers=(provider,), adjustment_convention=adjustment_convention,
                                         schema_version=schema, invocation_id=self.invocation_id,
                                         evidence_cutoff_utc=self.evidence_cutoff_utc or end,
                                         exchange_calendar=self.exchange_calendar, evidence_state=evidence_state)
            ledger_id = self.ledger.start(gap_request, provider=provider)
            try:
                fetched = normalise_intraday_bars(fetch_missing(ticker, gap_start, gap_end), ticker=ticker,
                                                  interval_minutes=interval, session_date=session_date,
                                                  session_segment=session_segment,
                                                  adjustment_convention=adjustment_convention, provider=provider)
                fetched = fetched[(fetched["timestamp_utc"] >= gap_start) & (fetched["timestamp_utc"] <= gap_end)].reset_index(drop=True)
                gap_expected = pd.date_range(gap_start, gap_end, freq=f"{interval}min")
                quality = assess_intraday_quality(fetched, gap_expected, interval_minutes=interval)
                if quality.duplicate_count:
                    raise ValueError("provider returned duplicate intraday timestamps")
                if quality.missing_count:
                    raise ValueError(f"provider omitted {quality.missing_count} requested intraday intervals")
                record = self._persist(gap_request, fetched, provider, quality)
                fetched["dataset_id"] = record.dataset_id
                fetched["content_hash"] = record.content_hash
                fetched["completeness_status"] = record.completeness_status.value
                new_records.append(record); frames.append(fetched); physical_fetches += 1
                self.ledger.finish(ledger_id, RequestResolution.PROVIDER_FETCH, dataset_id=record.dataset_id, physical_request_count=1)
            except Exception as error:
                self.ledger.finish(ledger_id, RequestResolution.PROVIDER_ERROR, physical_request_count=1,
                                   reason=f"{type(error).__name__}:{error}")
                raise
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not combined.empty:
            combined["timestamp_utc"] = pd.to_datetime(combined["timestamp_utc"], utc=True)
            combined = combined[combined["timestamp_utc"].isin(observable)].sort_values("timestamp_utc", kind="stable")
            combined = combined.drop_duplicates("timestamp_utc", keep="last").reset_index(drop=True)
        quality = assess_intraday_quality(combined, observable, interval_minutes=interval)
        if quality.missing_count:
            raise ValueError(f"canonical intraday assembly is missing {quality.missing_count} intervals")
        ids = tuple(r.dataset_id for r in records + new_records)
        return IntradayBarResult(combined, "PROVIDER_FETCH" if physical_fetches else "CACHE_ASSEMBLED",
                                 ids, physical_fetches, plan, quality)

    def resolve_many(self, *, tickers: Iterable[str], session_date: date, start_utc: datetime, end_utc: datetime,
                     fetch_missing_for_ticker: Callable[[str, datetime, datetime], pd.DataFrame], provider: str,
                     **kwargs: object) -> IntradayBatchResult:
        """Isolate provider/data defects per ticker while preserving authority."""
        requested = tuple(sorted({str(t).strip().upper() for t in tickers if str(t).strip()}))
        results: dict[str, IntradayBarResult] = {}; exceptions: dict[str, str] = {}
        blocked: list[str] = []; failed: list[str] = []
        for ticker in requested:
            try:
                results[ticker] = self.resolve(ticker=ticker, session_date=session_date, start_utc=start_utc,
                                               end_utc=end_utc, fetch_missing=fetch_missing_for_ticker,
                                               provider=provider, **kwargs)
            except FetchNotAuthorised as error:
                blocked.append(ticker); exceptions[ticker] = f"{type(error).__name__}:{error}"
            except Exception as error:
                failed.append(ticker); exceptions[ticker] = f"{type(error).__name__}:{error}"
        return IntradayBatchResult(results, exceptions, requested, tuple(sorted(results)), tuple(blocked), tuple(failed))
