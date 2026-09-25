"""Exact-contract quote join and freshness assessment for the WAR report.

Gap 1 (ACK, 25 Sep 2026): join the selected OCC symbol and run ID to
data/canonical/market_observations/exact_option_quote/<date>/<ticker>/*.json.
The stored ``quote_freshness`` must never be left UNASSESSED, and
``executable_now`` must describe executability AT REPORT GENERATION, not at
capture time. Neither the join nor the freshness call places a capital order;
this context is advisory-only, consumed by a human WAR review.

Revision (ACK, 25 Sep 2026, post-acceptance review): a fresh, two-sided quote
with zero or missing displayed size was being reported EXECUTABLE_NOW. A
fresh quote alone is not proof of executable size. ``quote_quality`` now
requires valid, positive displayed sizes on both sides before it can be
TWO_SIDED — mirroring the SIZE_MISSING / NO_DISPLAYED_SIZE states already
used by domain.broker_quote_observation for the same reason. executable_now
still requires ALL of: TWO_SIDED quality (which now implies real size),
FRESH freshness, and a matched identity; it does not yet encode every
governed execution-context check outside this module's scope (position
limits, account state, etc.) — those remain the assembler's and a human
reviewer's responsibility, and this module's advisory authority is
unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Sequence

from canonical_data.option_identity import normalise_occ_symbol


class QuoteIdentityState(str, Enum):
    MATCHED = "MATCHED"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    RUN_MISMATCH = "RUN_MISMATCH"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


class QuoteQualityState(str, Enum):
    TWO_SIDED = "TWO_SIDED"
    ONE_SIDED = "ONE_SIDED"
    CROSSED = "CROSSED"
    NO_QUOTE = "NO_QUOTE"
    HALTED = "HALTED"
    SIZE_MISSING = "SIZE_MISSING"
    NO_DISPLAYED_SIZE = "NO_DISPLAYED_SIZE"
    INVALID = "INVALID"


class QuoteFreshnessState(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    FUTURE_DATED = "FUTURE_DATED"
    UNASSESSABLE_NO_TIMESTAMP = "UNASSESSABLE_NO_TIMESTAMP"


class ExecutableNowState(str, Enum):
    EXECUTABLE_NOW = "EXECUTABLE_NOW"
    NOT_EXECUTABLE_STALE = "NOT_EXECUTABLE_STALE"
    NOT_EXECUTABLE_QUALITY = "NOT_EXECUTABLE_QUALITY"
    NOT_EXECUTABLE_NO_QUOTE = "NOT_EXECUTABLE_NO_QUOTE"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


@dataclass(frozen=True, slots=True)
class ExactContractQuoteCandidate:
    source_path: str
    source_hash: str
    run_id: str
    ticker: str
    occ_symbol: str
    provider: str
    provider_observed_at_utc: str | None
    bid: str | None
    ask: str | None
    bid_size: str | None
    ask_size: str | None
    delta: str | None
    gamma: str | None
    theta: str | None
    vega: str | None
    quote_quality_raw: str | None


@dataclass(frozen=True, slots=True)
class ExactContractQuoteJoin:
    requested_occ_symbol: str
    requested_run_id: str
    requested_ticker: str
    identity_state: str
    matched_source_path: str | None
    matched_source_hash: str | None
    provider: str | None
    provider_observed_at_utc: str | None
    bid: str | None
    ask: str | None
    bid_size: str | None
    ask_size: str | None
    delta: str | None
    gamma: str | None
    theta: str | None
    vega: str | None
    quote_quality: str
    quote_freshness: str
    quote_age_seconds_at_generation: float | None
    report_generation_time_utc: str
    executable_now: str
    authority: str = "ADVISORY_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dec(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return str(result) if result.is_finite() else None


def _quote_quality(candidate: ExactContractQuoteCandidate) -> QuoteQualityState:
    if str(candidate.quote_quality_raw or "").strip().upper() == "HALTED":
        return QuoteQualityState.HALTED
    bid, ask = _dec(candidate.bid), _dec(candidate.ask)
    if bid is None and ask is None:
        return QuoteQualityState.NO_QUOTE
    try:
        if bid is None or ask is None or Decimal(bid) <= 0 or Decimal(ask) <= 0:
            return QuoteQualityState.ONE_SIDED
        if Decimal(bid) > Decimal(ask):
            return QuoteQualityState.CROSSED
    except InvalidOperation:
        return QuoteQualityState.INVALID
    # A fresh, valid two-sided price alone is not proof of executable size.
    # Both displayed sizes must be present AND strictly positive.
    bid_size, ask_size = _dec(candidate.bid_size), _dec(candidate.ask_size)
    if bid_size is None or ask_size is None:
        return QuoteQualityState.SIZE_MISSING
    try:
        if Decimal(bid_size) <= 0 or Decimal(ask_size) <= 0:
            return QuoteQualityState.NO_DISPLAYED_SIZE
    except InvalidOperation:
        return QuoteQualityState.INVALID
    return QuoteQualityState.TWO_SIDED


def join_exact_contract_quote(
    *,
    requested_occ_symbol: str,
    requested_run_id: str,
    requested_ticker: str,
    candidates: Sequence[ExactContractQuoteCandidate],
    report_generation_time_utc: datetime,
    freshness_seconds: int = 300,
) -> ExactContractQuoteJoin:
    """Join the selected contract to canonical exact_option_quote evidence.

    Matching requires BOTH the OCC symbol and the run ID; a symbol hit from a
    different run is a RUN_MISMATCH, never silently accepted as identity.
    Freshness and executable_now are assessed as of ``report_generation_time_utc``,
    never as of the quote's own capture time. executable_now requires TWO_SIDED
    quality (which now implies validated positive displayed sizes on both
    sides) AND FRESH freshness; it is a narrower claim than "a two-sided quote
    was observed recently" and does not encode governed execution-context
    checks outside this module (position limits, account state, etc.).
    """
    wanted_symbol = normalise_occ_symbol(requested_occ_symbol)
    wanted_run = str(requested_run_id).strip()
    wanted_ticker = str(requested_ticker).strip().upper()
    gen_time = report_generation_time_utc
    if gen_time.tzinfo is None:
        gen_time = gen_time.replace(tzinfo=timezone.utc)
    gen_time = gen_time.astimezone(timezone.utc)

    symbol_hits = [
        c for c in candidates
        if normalise_occ_symbol(c.occ_symbol) == wanted_symbol
        and c.ticker.strip().upper() == wanted_ticker
    ]
    exact_hits = [c for c in symbol_hits if str(c.run_id).strip() == wanted_run]

    def _unmatched(state: QuoteIdentityState) -> ExactContractQuoteJoin:
        return ExactContractQuoteJoin(
            wanted_symbol, wanted_run, wanted_ticker, state.value,
            None, None, None, None, None, None, None, None,
            None, None, None, None,
            QuoteQualityState.NO_QUOTE.value,
            QuoteFreshnessState.UNASSESSABLE_NO_TIMESTAMP.value, None,
            gen_time.isoformat().replace("+00:00", "Z"),
            ExecutableNowState.NOT_ASSESSABLE.value,
        )

    if not symbol_hits:
        return _unmatched(QuoteIdentityState.NOT_FOUND)
    if not exact_hits:
        return _unmatched(QuoteIdentityState.RUN_MISMATCH)
    if len(exact_hits) > 1:
        return _unmatched(QuoteIdentityState.AMBIGUOUS)

    candidate = exact_hits[0]
    quality = _quote_quality(candidate)

    freshness = QuoteFreshnessState.UNASSESSABLE_NO_TIMESTAMP
    age_seconds: float | None = None
    if candidate.provider_observed_at_utc:
        try:
            observed = datetime.fromisoformat(
                candidate.provider_observed_at_utc.strip().replace("Z", "+00:00")
            )
            if observed.tzinfo is None:
                raise ValueError("provider timestamp has no timezone")
            observed = observed.astimezone(timezone.utc)
            age_seconds = (gen_time - observed).total_seconds()
            if age_seconds < 0:
                freshness = QuoteFreshnessState.FUTURE_DATED
            elif age_seconds > freshness_seconds:
                freshness = QuoteFreshnessState.STALE
            else:
                freshness = QuoteFreshnessState.FRESH
        except ValueError:
            freshness = QuoteFreshnessState.UNASSESSABLE_NO_TIMESTAMP
            age_seconds = None

    if freshness in (QuoteFreshnessState.UNASSESSABLE_NO_TIMESTAMP, QuoteFreshnessState.FUTURE_DATED):
        executable = ExecutableNowState.NOT_ASSESSABLE
    elif freshness in (QuoteFreshnessState.STALE, QuoteFreshnessState.EXPIRED):
        executable = ExecutableNowState.NOT_EXECUTABLE_STALE
    elif quality is QuoteQualityState.NO_QUOTE:
        executable = ExecutableNowState.NOT_EXECUTABLE_NO_QUOTE
    elif quality is not QuoteQualityState.TWO_SIDED:
        executable = ExecutableNowState.NOT_EXECUTABLE_QUALITY
    else:
        executable = ExecutableNowState.EXECUTABLE_NOW

    return ExactContractQuoteJoin(
        wanted_symbol, wanted_run, wanted_ticker, QuoteIdentityState.MATCHED.value,
        candidate.source_path, candidate.source_hash, candidate.provider,
        candidate.provider_observed_at_utc,
        _dec(candidate.bid), _dec(candidate.ask), _dec(candidate.bid_size), _dec(candidate.ask_size),
        _dec(candidate.delta), _dec(candidate.gamma), _dec(candidate.theta), _dec(candidate.vega),
        quality.value, freshness.value, age_seconds,
        gen_time.isoformat().replace("+00:00", "Z"), executable.value,
    )


def load_exact_contract_quote_candidate_from_json(
    payload: Mapping[str, Any], *, source_path: str, source_hash: str,
) -> ExactContractQuoteCandidate:
    """Map the real on-disk exact_option_quote JSON schema to this domain's candidate.

    Pure: takes an already-parsed payload, does no filesystem I/O itself.
    Field mapping was read directly off real stored files (run
    20260925_061649: BULL/EWG/SOFI/XLF; run 20260924_085940: BULL) rather than
    guessed: ``symbol`` -> occ_symbol, ``underlying`` -> ticker, ``quote_source``
    -> provider, ``quote_timestamp_utc`` -> provider_observed_at_utc. The
    source file's own ``quote_freshness`` (observed as the literal string
    "UNASSESSED" in every sampled file) and its own ``executable_now`` boolean
    are deliberately NOT copied through: this module re-derives both, which
    is the entire point of Gap 1.
    """
    return ExactContractQuoteCandidate(
        source_path=source_path,
        source_hash=source_hash,
        run_id=str(payload.get("run_id") or ""),
        ticker=str(payload.get("underlying") or "").strip().upper(),
        occ_symbol=str(payload.get("symbol") or ""),
        provider=str(payload.get("quote_source") or "UNKNOWN"),
        provider_observed_at_utc=payload.get("quote_timestamp_utc"),
        bid=payload.get("bid"),
        ask=payload.get("ask"),
        bid_size=payload.get("bid_size"),
        ask_size=payload.get("ask_size"),
        delta=payload.get("delta"),
        gamma=payload.get("gamma"),
        theta=payload.get("theta"),
        vega=payload.get("vega"),
        quote_quality_raw=None,
    )


@dataclass(frozen=True, slots=True)
class SupplementalBrokerObservationRecord:
    """A separately-persistable, explicitly-requested fresh broker read.

    Building this record does NOT write anything to disk — see
    contracts.supplemental_broker_observation_writer for the infrastructure
    adapter that actually persists it atomically, without overwriting the
    historical exact_option_quote snapshot or any prior supplemental record
    at the same path.
    """
    exact_contract_quote_join_ref: str
    fetched_at_utc: str
    provider: str
    provider_observed_at_utc: str | None
    bid: str | None
    ask: str | None
    persisted_as: str
    overwrites_historical_snapshot: bool = False


def build_supplemental_broker_observation_record(
    *,
    historical_join: ExactContractQuoteJoin,
    fresh_observation: Mapping[str, Any],
    fetched_at_utc: datetime,
    persist_path_template: str = (
        "market_observations/exact_option_quote_live_supplement/{ticker}/{run_id}/{ts}.json"
    ),
) -> SupplementalBrokerObservationRecord:
    """Build (but do not write) the record for a supplemental broker observation.

    Renamed from the earlier ``persist_supplemental_broker_observation`` — that
    name claimed a filesystem effect this pure domain function never had. Pass
    the returned record to
    ``contracts.supplemental_broker_observation_writer.persist_supplemental_broker_observation_atomically``
    to actually write it.
    """
    ts = (
        fetched_at_utc.astimezone(timezone.utc)
        .isoformat().replace("+00:00", "Z").replace(":", "")
    )
    path = persist_path_template.format(
        ticker=historical_join.requested_ticker,
        run_id=historical_join.requested_run_id,
        ts=ts,
    )
    return SupplementalBrokerObservationRecord(
        exact_contract_quote_join_ref=(
            f"{historical_join.requested_ticker}:{historical_join.requested_run_id}:"
            f"{historical_join.requested_occ_symbol}"
        ),
        fetched_at_utc=ts,
        provider=str(fresh_observation.get("provider") or "TASTYTRADE"),
        provider_observed_at_utc=fresh_observation.get("provider_updated_at_utc"),
        bid=_dec(fresh_observation.get("bid")),
        ask=_dec(fresh_observation.get("ask")),
        persisted_as=path,
        overwrites_historical_snapshot=False,
    )


__all__ = [
    "QuoteIdentityState", "QuoteQualityState", "QuoteFreshnessState", "ExecutableNowState",
    "ExactContractQuoteCandidate", "ExactContractQuoteJoin", "join_exact_contract_quote",
    "load_exact_contract_quote_candidate_from_json",
    "SupplementalBrokerObservationRecord", "build_supplemental_broker_observation_record",
]
