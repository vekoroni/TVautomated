"""Governed canonical/Phantom observation bridge for DOI-3.

Current option facts are resolved from the canonical registry and remain the
only raw-data authority.  Phantom is opened read-only and contributes a
lineage-bound historical projection; it cannot replace current bid/ask facts
or trigger a provider request.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

import pandas as pd

from domain.dynamic_options_intelligence import (
    DOI_DECISION_AUTHORITY,
    ObservationAcquisitionDecision,
    OpportunityAcquisitionState,
    OptionObservationKind,
    decide_observation_acquisition,
)

from .contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType, parse_utc
from .option_identity import normalise_occ_symbol, parse_occ_symbol
from .registry import CanonicalRegistry


DOI_OBSERVATION_BRIDGE_VERSION = "doi-observation-bridge-v1"
DOI_ACTIVITY_FEATURE_VERSION = "doi-contract-activity-v1"
DOI_PCR_FEATURE_VERSION = "doi-scoped-pcr-v1"
DOI_PHANTOM_PROJECTION_VERSION = "doi-phantom-projection-v1"
MARKETDATA_PROVIDER = "MARKETDATA"


@dataclass(frozen=True, slots=True)
class GovernedOptionObservation:
    ticker: str
    observation_kind: OptionObservationKind
    dataset_id: str | None
    provider: str
    as_of_utc: datetime | None
    frame: pd.DataFrame
    resolution: str
    acquisition: ObservationAcquisitionDecision
    physical_fetch_count: int
    quality_flags: tuple[str, ...] = ()
    provider_finality: Mapping[str, Any] | None = None
    decision_authority: str = DOI_DECISION_AUTHORITY

    @property
    def available(self) -> bool:
        return self.dataset_id is not None and not self.frame.empty

    @property
    def normal_completed_session_eligible(self) -> bool:
        return bool(
            self.provider_finality
            and self.provider_finality.get("normal_completed_session_eligible") is True
        )


@dataclass(frozen=True, slots=True)
class ContractActivityFeatures:
    contract_symbol: str
    bid: float | None
    ask: float | None
    bid_size: float | None
    ask_size: float | None
    spread_fraction: float | None
    volume: float | None
    open_interest: float | None
    volume_oi_turnover: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    spot: float | None
    strike: float | None
    distance_to_strike_pct: float | None
    quote_update_rate: float | None
    snapshot_only: bool
    feature_version: str = DOI_ACTIVITY_FEATURE_VERSION


@dataclass(frozen=True, slots=True)
class PutCallContextFeatures:
    total_volume_pcr: float | None
    total_oi_pcr: float | None
    expiry_volume_pcr: float | None
    expiry_oi_pcr: float | None
    near_money_volume_pcr: float | None
    near_money_oi_pcr: float | None
    target_region_volume_pcr: float | None
    target_region_oi_pcr: float | None
    delta_bucket_volume_pcr: float | None
    delta_bucket_oi_pcr: float | None
    total_volume_pcr_change: float | None
    put_call_iv_skew: float | None
    premium_flow_imbalance: float | None
    signed_order_flow_available: bool
    feature_version: str = DOI_PCR_FEATURE_VERSION


@dataclass(frozen=True, slots=True)
class PhantomHistoricalProjection:
    projection_id: str
    canonical_dataset_id: str
    ticker: str
    side: str
    evidence_cutoff_utc: datetime
    available: bool
    applicability: str
    observation_count: int
    session_count: int
    median_spread_fraction: float | None
    executable_quote_rate: float | None
    median_volume: float | None
    median_open_interest: float | None
    median_volume_oi_turnover: float | None
    median_iv: float | None
    median_abs_delta: float | None
    source: str = "PHANTOM_READ_ONLY_PROJECTION"
    feature_version: str = DOI_PHANTOM_PROJECTION_VERSION
    decision_authority: str = DOI_DECISION_AUTHORITY


@dataclass(frozen=True, slots=True)
class DOIObservationBundle:
    observation: GovernedOptionObservation
    activity: ContractActivityFeatures | None
    put_call_context: PutCallContextFeatures | None
    phantom_history: PhantomHistoricalProjection | None
    input_dataset_ids: tuple[str, ...]
    bridge_version: str = DOI_OBSERVATION_BRIDGE_VERSION
    decision_authority: str = DOI_DECISION_AUTHORITY


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _series(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series([None] * len(frame), index=frame.index, dtype="object")


def _normalise_side(value: Any) -> str | None:
    token = str(value or "").strip().upper()
    if token in {"C", "CALL", "LONG_CALL"}:
        return "CALL"
    if token in {"P", "PUT", "LONG_PUT"}:
        return "PUT"
    return None


def _symbols(frame: pd.DataFrame) -> pd.Series:
    raw = _series(frame, "symbol", "option_symbol", "contract_symbol")
    def clean(value: Any) -> str | None:
        try:
            return normalise_occ_symbol(value)
        except ValueError:
            return None
    return raw.map(clean)


def _sides(frame: pd.DataFrame) -> pd.Series:
    raw = _series(frame, "right", "side", "option_side")
    return raw.map(_normalise_side)


def _expiry(frame: pd.DataFrame) -> pd.Series:
    if "expiration_ts" in frame.columns:
        return pd.to_datetime(
            frame["expiration_ts"], errors="coerce", unit="s", utc=True
        ).dt.date
    raw = _series(frame, "expiration_date", "expiration", "expiry")
    return pd.to_datetime(raw, errors="coerce", utc=True).dt.date


def _numeric(frame: pd.DataFrame, *names: str) -> pd.Series:
    return pd.to_numeric(_series(frame, *names), errors="coerce")


def _pcr(frame: pd.DataFrame, metric: str) -> float | None:
    if frame.empty:
        return None
    sides = _sides(frame)
    values = _numeric(frame, metric)
    calls = float(values[sides == "CALL"].sum(min_count=1))
    puts = float(values[sides == "PUT"].sum(min_count=1))
    if not math.isfinite(calls) or calls <= 0 or not math.isfinite(puts):
        return None
    return puts / calls


def extract_contract_activity(
    frame: pd.DataFrame, contract_symbol: str
) -> ContractActivityFeatures:
    canonical = normalise_occ_symbol(contract_symbol)
    matches = frame.loc[_symbols(frame) == canonical]
    if len(matches) != 1:
        raise ValueError(
            f"canonical observation must contain exactly one {canonical} row"
        )
    row = matches.iloc[0]
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"))
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    spread = (
        (ask - bid) / mid
        if mid is not None and mid > 0 and ask is not None and bid is not None and ask >= bid
        else None
    )
    volume = _number(row.get("volume"))
    oi = _number(row.get("open_interest"))
    turnover = volume / oi if volume is not None and oi is not None and oi > 0 else None
    spot = _number(row.get("underlying_price"))
    strike = _number(row.get("strike"))
    distance = (
        ((strike / spot) - 1.0) * 100.0
        if spot is not None and spot > 0 and strike is not None
        else None
    )
    iv = _number(row.get("implied_vol"))
    if iv is None:
        iv = _number(row.get("iv"))
    return ContractActivityFeatures(
        contract_symbol=canonical,
        bid=bid,
        ask=ask,
        bid_size=_number(row.get("bid_size")),
        ask_size=_number(row.get("ask_size")),
        spread_fraction=spread,
        volume=volume,
        open_interest=oi,
        volume_oi_turnover=turnover,
        iv=iv,
        delta=_number(row.get("delta")),
        gamma=_number(row.get("gamma")),
        theta=_number(row.get("theta")),
        vega=_number(row.get("vega")),
        spot=spot,
        strike=strike,
        distance_to_strike_pct=distance,
        # Canonical MarketData payloads are snapshots. Without quote-event
        # history or prints, update rate and signed flow must remain unknown.
        quote_update_rate=None,
        snapshot_only=True,
    )


def extract_put_call_context(
    frame: pd.DataFrame,
    *,
    selected_contract_symbol: str | None = None,
    target_spot: float | None = None,
    previous_frame: pd.DataFrame | None = None,
    near_money_pct: float = 5.0,
    target_region_pct: float = 5.0,
    delta_bucket_width: float = 0.10,
) -> PutCallContextFeatures:
    sides = _sides(frame)
    spots = _numeric(frame, "underlying_price")
    strikes = _numeric(frame, "strike")
    spot = _number(spots.dropna().iloc[0]) if not spots.dropna().empty else None
    selected_expiry = None
    selected_abs_delta = None
    if selected_contract_symbol:
        canonical = normalise_occ_symbol(selected_contract_symbol)
        selected = frame.loc[_symbols(frame) == canonical]
        if len(selected) == 1:
            selected_expiry = parse_occ_symbol(canonical).expiry
            selected_abs_delta = abs(_number(selected.iloc[0].get("delta")) or 0.0)
    expiries = _expiry(frame)
    expiry_frame = frame.loc[expiries == selected_expiry] if selected_expiry else frame.iloc[0:0]
    if spot is not None and spot > 0:
        near_mask = ((strikes / spot) - 1.0).abs() <= near_money_pct / 100.0
        near_frame = frame.loc[near_mask]
    else:
        near_frame = frame.iloc[0:0]
    target = _number(target_spot)
    if target is not None and target > 0:
        target_mask = ((strikes / target) - 1.0).abs() <= target_region_pct / 100.0
        target_frame = frame.loc[target_mask]
    else:
        target_frame = frame.iloc[0:0]
    deltas = _numeric(frame, "delta").abs()
    if selected_abs_delta is not None:
        delta_frame = frame.loc[(deltas - selected_abs_delta).abs() <= delta_bucket_width]
    else:
        delta_frame = frame.iloc[0:0]
    put_iv = _numeric(frame.loc[sides == "PUT"], "implied_vol", "iv").median()
    call_iv = _numeric(frame.loc[sides == "CALL"], "implied_vol", "iv").median()
    iv_skew = (
        float(put_iv - call_iv)
        if pd.notna(put_iv) and pd.notna(call_iv)
        else None
    )
    total_volume = _pcr(frame, "volume")
    previous_volume = _pcr(previous_frame, "volume") if previous_frame is not None else None
    change = (
        total_volume - previous_volume
        if total_volume is not None and previous_volume is not None
        else None
    )
    return PutCallContextFeatures(
        total_volume_pcr=total_volume,
        total_oi_pcr=_pcr(frame, "open_interest"),
        expiry_volume_pcr=_pcr(expiry_frame, "volume"),
        expiry_oi_pcr=_pcr(expiry_frame, "open_interest"),
        near_money_volume_pcr=_pcr(near_frame, "volume"),
        near_money_oi_pcr=_pcr(near_frame, "open_interest"),
        target_region_volume_pcr=_pcr(target_frame, "volume"),
        target_region_oi_pcr=_pcr(target_frame, "open_interest"),
        delta_bucket_volume_pcr=_pcr(delta_frame, "volume"),
        delta_bucket_oi_pcr=_pcr(delta_frame, "open_interest"),
        total_volume_pcr_change=change,
        put_call_iv_skew=iv_skew,
        premium_flow_imbalance=None,
        signed_order_flow_available=False,
    )


class PhantomDOIProjectionRepository:
    """Read-only historical analytics projection over Phantom snapshots."""

    def __init__(self, database_path: Path | str, registry: CanonicalRegistry) -> None:
        self.database_path = Path(database_path)
        self.registry = registry

    def _empty(
        self, *, canonical_dataset_id: str, ticker: str, side: str,
        cutoff: datetime, applicability: str,
    ) -> PhantomHistoricalProjection:
        identity = f"{canonical_dataset_id}|{ticker}|{side}|{cutoff.isoformat()}|{applicability}"
        return PhantomHistoricalProjection(
            projection_id=hashlib.sha256(identity.encode()).hexdigest(),
            canonical_dataset_id=canonical_dataset_id,
            ticker=ticker,
            side=side,
            evidence_cutoff_utc=cutoff,
            available=False,
            applicability=applicability,
            observation_count=0,
            session_count=0,
            median_spread_fraction=None,
            executable_quote_rate=None,
            median_volume=None,
            median_open_interest=None,
            median_volume_oi_turnover=None,
            median_iv=None,
            median_abs_delta=None,
        )

    def project(
        self,
        *,
        canonical_dataset_id: str,
        ticker: str,
        side: str,
        evidence_cutoff_utc: datetime,
        dte: float | None = None,
        delta: float | None = None,
        max_rows: int = 5000,
    ) -> PhantomHistoricalProjection:
        record = self.registry.get_dataset(canonical_dataset_id)
        symbol = str(ticker).strip().upper()
        option_side = _normalise_side(side)
        cutoff = parse_utc(evidence_cutoff_utc)
        if record is None:
            raise ValueError("Phantom projection requires a registered canonical dataset")
        if record.instrument_id != symbol or record.dataset_type not in {
            DatasetType.OPTION_CHAIN, DatasetType.LIVE_OPTION, DatasetType.EXACT_OPTION_QUOTE
        }:
            raise ValueError("canonical dataset does not match the requested option evidence")
        if option_side is None or cutoff is None:
            raise ValueError("valid side and timezone-aware evidence cutoff are required")
        if not self.database_path.is_file():
            return self._empty(
                canonical_dataset_id=canonical_dataset_id, ticker=symbol,
                side=option_side, cutoff=cutoff, applicability="PHANTOM_UNAVAILABLE",
            )
        uri = f"file:{self.database_path.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA temp_store = MEMORY")
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chain_snapshots'"
            ).fetchone()
            if not exists:
                return self._empty(
                    canonical_dataset_id=canonical_dataset_id, ticker=symbol,
                    side=option_side, cutoff=cutoff, applicability="PHANTOM_SCHEMA_UNAVAILABLE",
                )
            sql = """
                SELECT quote_date, bid, ask, volume, open_interest, iv, delta, dte
                FROM chain_snapshots
                WHERE ticker = ? AND UPPER(side) IN (?, ?)
                  AND quote_date < ?
            """
            params: list[Any] = [
                symbol, option_side, option_side[0], cutoff.date().isoformat()
            ]
            if dte is not None and math.isfinite(float(dte)):
                sql += " AND dte BETWEEN ? AND ?"
                params.extend([max(0.0, float(dte) - 5.0), float(dte) + 5.0])
            if delta is not None and math.isfinite(float(delta)):
                sql += " AND ABS(ABS(delta) - ?) <= 0.10"
                params.append(abs(float(delta)))
            sql += " ORDER BY quote_date DESC LIMIT ?"
            params.append(int(max_rows))
            history = pd.read_sql_query(sql, connection, params=params)
        if history.empty:
            return self._empty(
                canonical_dataset_id=canonical_dataset_id, ticker=symbol,
                side=option_side, cutoff=cutoff, applicability="HISTORY_INSUFFICIENT",
            )
        bid = pd.to_numeric(history["bid"], errors="coerce")
        ask = pd.to_numeric(history["ask"], errors="coerce")
        mid = (bid + ask) / 2.0
        valid = (bid >= 0) & (ask >= bid) & (mid > 0)
        spread = ((ask - bid) / mid).where(valid)
        executable = (bid > 0) & (ask >= bid)
        volume = pd.to_numeric(history["volume"], errors="coerce")
        oi = pd.to_numeric(history["open_interest"], errors="coerce")
        turnover = (volume / oi).where(oi > 0)
        iv = pd.to_numeric(history["iv"], errors="coerce")
        abs_delta = pd.to_numeric(history["delta"], errors="coerce").abs()
        identity = (
            f"{canonical_dataset_id}|{symbol}|{option_side}|{cutoff.isoformat()}|"
            f"{dte}|{delta}|{len(history)}"
        )
        return PhantomHistoricalProjection(
            projection_id=hashlib.sha256(identity.encode()).hexdigest(),
            canonical_dataset_id=canonical_dataset_id,
            ticker=symbol,
            side=option_side,
            evidence_cutoff_utc=cutoff,
            available=True,
            applicability="AVAILABLE",
            observation_count=len(history),
            session_count=int(history["quote_date"].nunique()),
            median_spread_fraction=_number(spread.median()),
            executable_quote_rate=_number(executable.mean()),
            median_volume=_number(volume.median()),
            median_open_interest=_number(oi.median()),
            median_volume_oi_turnover=_number(turnover.median()),
            median_iv=_number(iv.median()),
            median_abs_delta=_number(abs_delta.median()),
        )


class CanonicalDOIObservationBridge:
    """Resolve canonical evidence first and invoke acquisition only on a miss."""

    def __init__(
        self,
        *,
        registry_path: Path | str,
        phantom_database_path: Path | str | None = None,
    ) -> None:
        self.registry = CanonicalRegistry(Path(registry_path))
        self.registry.initialise()
        self.phantom = (
            PhantomDOIProjectionRepository(phantom_database_path, self.registry)
            if phantom_database_path is not None else None
        )
        self._acquisition_attempts: set[tuple[Any, ...]] = set()

    @staticmethod
    def _read(record: DatasetRecord) -> pd.DataFrame:
        path = Path(record.storage_uri)
        if not path.is_file():
            raise ValueError(f"canonical payload is missing: {path}")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record.content_hash:
            raise ValueError(f"canonical payload failed integrity: {path}")
        if path.suffix.lower() == ".parquet":
            frame = pd.read_parquet(path)
        else:
            decoded = json.loads(payload)
            if isinstance(decoded, list):
                frame = pd.DataFrame(decoded)
            elif isinstance(decoded, Mapping):
                frame = pd.DataFrame([decoded])
            else:
                raise ValueError("canonical option payload is not tabular")
        if frame.empty:
            raise ValueError("canonical option payload is empty")
        return frame

    def _candidate_record(
        self,
        *,
        ticker: str,
        session_date: date,
        observation_kind: OptionObservationKind,
        cutoff: datetime,
        contract_symbol: str | None,
        required_scope: DataScope | None,
    ) -> DatasetRecord | None:
        types = (
            (DatasetType.OPTION_CHAIN,)
            if observation_kind is OptionObservationKind.COMPLETED_SESSION
            else (DatasetType.EXACT_OPTION_QUOTE, DatasetType.LIVE_OPTION)
        )
        candidates: list[DatasetRecord] = []
        for dataset_type in types:
            candidates.extend(
                self.registry.list_dataset_records(dataset_type, instrument_id=ticker)
            )
        candidates = [
            record for record in candidates
            if record.session_date == session_date
            and record.provider == MARKETDATA_PROVIDER
            and record.completeness_status in {
                CompletenessStatus.COMPLETE, CompletenessStatus.PARTIAL
            }
            and record.as_of <= cutoff
            and (required_scope is None or record.scope.covers(required_scope))
        ]
        candidates.sort(
            key=lambda item: (
                item.as_of,
                item.completeness_status is CompletenessStatus.COMPLETE,
                item.dataset_id,
            ), reverse=True,
        )
        canonical_symbol = normalise_occ_symbol(contract_symbol) if contract_symbol else None
        for record in candidates:
            try:
                frame = self._read(record)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if canonical_symbol is None or canonical_symbol in set(_symbols(frame).dropna()):
                return record
        return None

    def resolve(
        self,
        *,
        ticker: str,
        session_date: date,
        observation_kind: OptionObservationKind | str,
        evidence_cutoff_utc: datetime,
        contract_symbol: str | None = None,
        required_scope: DataScope | None = None,
        opportunity_state: OpportunityAcquisitionState | str = OpportunityAcquisitionState.ACTIVE,
        underlying_reactivated: bool = False,
        manual_refresh: bool = False,
        acquire_missing: Callable[[], Any] | None = None,
        provider_finality: Mapping[str, Any] | None = None,
    ) -> GovernedOptionObservation:
        symbol = str(ticker).strip().upper()
        kind = (
            observation_kind
            if isinstance(observation_kind, OptionObservationKind)
            else OptionObservationKind(str(observation_kind).strip().upper())
        )
        cutoff = parse_utc(evidence_cutoff_utc)
        if not symbol or cutoff is None:
            raise ValueError("ticker and timezone-aware evidence cutoff are required")
        record = self._candidate_record(
            ticker=symbol, session_date=session_date, observation_kind=kind,
            cutoff=cutoff, contract_symbol=contract_symbol,
            required_scope=required_scope,
        )
        acquisition = decide_observation_acquisition(
            opportunity_state=opportunity_state,
            canonical_evidence_available=record is not None,
            underlying_reactivated=underlying_reactivated,
            manual_refresh=manual_refresh,
        )
        key = (
            symbol, session_date.isoformat(), kind.value,
            normalise_occ_symbol(contract_symbol) if contract_symbol else "",
            required_scope.fingerprint if required_scope is not None else "ANY_SCOPE",
            cutoff.isoformat(), bool(manual_refresh),
        )
        physical_fetch_count = 0
        result_resolution = ""
        if acquisition.should_fetch and acquire_missing is not None and key not in self._acquisition_attempts:
            self._acquisition_attempts.add(key)
            result = acquire_missing()
            result_resolution = str(
                getattr(result, "resolution", "")
                or (result.get("resolution") if isinstance(result, Mapping) else "")
            ).strip().upper()
            # A governed resolver callback can itself return a canonical hit.
            # Count only a demonstrated provider fetch as a physical request;
            # a bare test/adapter result is conservatively treated as one.
            physical_fetch_count = 1 if (
                not result_resolution
                or result_resolution in {"PROVIDER_FETCH", "PROVIDER_EMPTY", "PROVIDER_ERROR"}
            ) else 0
            dataset_id = getattr(result, "dataset_id", None)
            if dataset_id is None and isinstance(result, Mapping):
                dataset_id = result.get("dataset_id")
            fetched = self.registry.get_dataset(str(dataset_id)) if dataset_id else None
            if fetched is not None:
                expected_types = (
                    {DatasetType.OPTION_CHAIN}
                    if kind is OptionObservationKind.COMPLETED_SESSION
                    else {DatasetType.EXACT_OPTION_QUOTE, DatasetType.LIVE_OPTION}
                )
                if fetched.provider != MARKETDATA_PROVIDER:
                    raise ValueError("acquired option evidence is not canonical MarketData")
                if (
                    fetched.instrument_id != symbol
                    or fetched.session_date != session_date
                    or fetched.dataset_type not in expected_types
                    or fetched.as_of > cutoff
                    or (
                        required_scope is not None
                        and not fetched.scope.covers(required_scope)
                    )
                ):
                    raise ValueError("acquired option evidence violates ticker/cutoff scope")
                fetched_frame = self._read(fetched)
                if contract_symbol and normalise_occ_symbol(contract_symbol) not in set(
                    _symbols(fetched_frame).dropna()
                ):
                    raise ValueError("acquired option evidence does not contain exact contract")
                record = fetched
        if record is None:
            resolution = (
                result_resolution
                or (
                    "ACQUISITION_ALREADY_ATTEMPTED"
                    if key in self._acquisition_attempts and physical_fetch_count == 0
                    else acquisition.reason
                )
            )
            return GovernedOptionObservation(
                ticker=symbol, observation_kind=kind, dataset_id=None,
                provider="CANONICAL", as_of_utc=None, frame=pd.DataFrame(),
                resolution=resolution, acquisition=acquisition,
                physical_fetch_count=physical_fetch_count,
                provider_finality=provider_finality,
            )
        return GovernedOptionObservation(
            ticker=symbol, observation_kind=kind, dataset_id=record.dataset_id,
            provider=record.provider, as_of_utc=record.as_of,
            frame=self._read(record), resolution=(
                "PROVIDER_FETCH" if physical_fetch_count else "CANONICAL_REUSE"
            ), acquisition=acquisition, physical_fetch_count=physical_fetch_count,
            quality_flags=record.quality_flags,
            provider_finality=provider_finality,
        )

    def build_bundle(
        self,
        observation: GovernedOptionObservation,
        *,
        selected_contract_symbol: str | None = None,
        target_spot: float | None = None,
        previous_frame: pd.DataFrame | None = None,
    ) -> DOIObservationBundle:
        if not observation.available:
            return DOIObservationBundle(
                observation=observation, activity=None, put_call_context=None,
                phantom_history=None, input_dataset_ids=(),
            )
        activity = (
            extract_contract_activity(observation.frame, selected_contract_symbol)
            if selected_contract_symbol else None
        )
        context = extract_put_call_context(
            observation.frame, selected_contract_symbol=selected_contract_symbol,
            target_spot=target_spot, previous_frame=previous_frame,
        )
        phantom = None
        if self.phantom is not None and observation.dataset_id is not None:
            side = (
                parse_occ_symbol(selected_contract_symbol).side
                if selected_contract_symbol else "CALL"
            )
            phantom = self.phantom.project(
                canonical_dataset_id=observation.dataset_id,
                ticker=observation.ticker,
                side=side,
                evidence_cutoff_utc=observation.as_of_utc or datetime.now(timezone.utc),
                dte=(
                    _number(
                        observation.frame.loc[
                            _symbols(observation.frame) == normalise_occ_symbol(selected_contract_symbol)
                        ].iloc[0].get("dte")
                    ) if selected_contract_symbol else None
                ),
                delta=activity.delta if activity else None,
            )
        return DOIObservationBundle(
            observation=observation, activity=activity,
            put_call_context=context, phantom_history=phantom,
            input_dataset_ids=(observation.dataset_id,) if observation.dataset_id else (),
        )


__all__ = [
    "DOI_OBSERVATION_BRIDGE_VERSION", "DOI_ACTIVITY_FEATURE_VERSION",
    "DOI_PCR_FEATURE_VERSION", "DOI_PHANTOM_PROJECTION_VERSION",
    "GovernedOptionObservation", "ContractActivityFeatures",
    "PutCallContextFeatures", "PhantomHistoricalProjection",
    "DOIObservationBundle", "CanonicalDOIObservationBridge",
    "PhantomDOIProjectionRepository", "extract_contract_activity",
    "extract_put_call_context",
]
