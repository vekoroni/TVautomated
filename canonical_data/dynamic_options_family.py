"""DOI-4 thesis-conditioned contract-family generator.

This application service consumes an immutable governed thesis and a canonical
option-chain observation.  It admits every structurally possible long contract
of the governed side, preserves temporarily inactive contracts as monitorable,
and persists both the complete audit and a bounded, diversified display set.
It performs no provider acquisition, valuation, ranking, or trade decision.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import math
from typing import Any, Iterable

import pandas as pd

from domain.contract_family_generation import (
    DOI_FAMILY_POLICY_VERSION,
    ContractFamilyGenerationSummary,
    FamilyCandidateAudit,
    FamilyCandidateState,
    GeneratedContractFamily,
    StructuralExclusionReason,
    audits_to_payload,
)
from domain.dynamic_options_intelligence import (
    ContractFamily,
    ModelApplicabilityState,
    UnderlyingThesisRef,
)

from .contracts import DatasetType
from .dynamic_options_bridge import GovernedOptionObservation
from .option_identity import normalise_occ_symbol, parse_occ_symbol
from .option_liquidity_lifecycle import OptionLiquidityLifecycleStore
from .session_clock import xnys_sessions_between


DOI_FAMILY_GENERATOR_VERSION = "doi-contract-family-generator-v1"


def _value(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name in row.index:
            value = row.get(name)
            if value is not None and not pd.isna(value):
                return value
    return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _side(value: Any) -> str | None:
    token = str(value or "").strip().upper()
    if token in {"C", "CALL", "LONG_CALL"}:
        return "CALL"
    if token in {"P", "PUT", "LONG_PUT"}:
        return "PUT"
    return None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="raise", utc=True)
        return parsed.date()
    except (TypeError, ValueError, OverflowError):
        return None


def _quote_state(bid: float | None, ask: float | None) -> str:
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return "TWO_SIDED"
    if (bid is not None and bid > 0) or (ask is not None and ask > 0):
        return "ONE_SIDED"
    return "NO_QUOTE"


def _moneyness_bucket(side: str | None, strike: float | None, spot: float | None) -> str:
    if side is None or strike is None or spot is None or spot <= 0:
        return "UNKNOWN"
    distance = (strike / spot) - 1.0
    if abs(distance) <= 0.03:
        return "ATM"
    itm = distance < 0 if side == "CALL" else distance > 0
    return "ITM" if itm else "OTM"


def _expiry_bucket(remaining: int | None, required: int) -> str:
    if remaining is None:
        return "UNKNOWN"
    if remaining <= required + 5:
        return "NEAR"
    if remaining <= required * 2:
        return "MID"
    return "LONG"


def _target_reachability(
    side: str | None, strike: float | None, target: float | None
) -> str:
    if side is None or strike is None or target is None:
        return "UNKNOWN"
    reachable = strike <= target if side == "CALL" else strike >= target
    return "WITHIN_TARGET" if reachable else "BEYOND_TARGET"


def _display_key(item: FamilyCandidateAudit) -> tuple[Any, ...]:
    quote_order = {"TWO_SIDED": 0, "ONE_SIDED": 1, "NO_QUOTE": 2}
    reach_order = {"WITHIN_TARGET": 0, "UNKNOWN": 1, "BEYOND_TARGET": 2}
    money_order = {"ATM": 0, "ITM": 1, "OTM": 2, "UNKNOWN": 3}
    return (
        quote_order.get(item.quote_state, 9),
        reach_order.get(item.target_reachability, 9),
        money_order.get(item.moneyness_bucket, 9),
        abs((item.remaining_sessions or item.required_sessions) - item.required_sessions),
        item.contract_symbol or "",
    )


def _bounded_display(
    audits: Iterable[FamilyCandidateAudit], maximum: int
) -> tuple[str, ...]:
    candidates = [item for item in audits if item.is_family_candidate]
    if maximum <= 0 or not candidates:
        return ()
    ordered = sorted(candidates, key=_display_key)
    groups: dict[tuple[str, str, str, str], list[FamilyCandidateAudit]] = defaultdict(list)
    for item in ordered:
        groups[(
            item.quote_state,
            item.moneyness_bucket,
            item.expiry_bucket,
            item.target_reachability,
        )].append(item)
    selected: list[str] = []
    # Take one representative from each evidence/geometry stratum first. This
    # is display diversification, not a preferred-contract ranking.
    for key in sorted(groups):
        symbol = groups[key][0].contract_symbol
        if symbol and symbol not in selected:
            selected.append(symbol)
        if len(selected) == maximum:
            return tuple(selected)
    for item in ordered:
        if item.contract_symbol and item.contract_symbol not in selected:
            selected.append(item.contract_symbol)
        if len(selected) == maximum:
            break
    return tuple(selected)


class ThesisConditionedContractFamilyGenerator:
    def __init__(
        self,
        store: OptionLiquidityLifecycleStore,
        *,
        expiry_buffer_sessions: int = 8,
        max_display_candidates: int = 12,
        family_policy_version: str = DOI_FAMILY_POLICY_VERSION,
    ) -> None:
        if expiry_buffer_sessions < 0:
            raise ValueError("expiry_buffer_sessions cannot be negative")
        if max_display_candidates < 1:
            raise ValueError("max_display_candidates must be positive")
        self.store = store
        self.expiry_buffer_sessions = int(expiry_buffer_sessions)
        self.max_display_candidates = int(max_display_candidates)
        self.family_policy_version = str(family_policy_version).strip()
        if not self.family_policy_version:
            raise ValueError("family_policy_version is required")

    def _empty_result(
        self,
        *,
        thesis: UnderlyingThesisRef,
        run_id: str,
        cutoff: datetime,
        reason: str,
        source_dataset_ids: tuple[str, ...] = (),
    ) -> GeneratedContractFamily:
        summary = ContractFamilyGenerationSummary(
            source_observations=0,
            family_candidates=0,
            structural_exclusions=0,
            two_sided_candidates=0,
            monitor_one_sided=0,
            monitor_no_quote=0,
            retained_low_open_interest=0,
            retained_zero_volume=0,
            displayed_candidates=0,
            direction=thesis.governed_direction,
            counts_by_exclusion={},
        )
        metadata = {
            "generator_version": DOI_FAMILY_GENERATOR_VERSION,
            "generation_state": "CONTRACT_DATA_INSUFFICIENT",
            "generation_reason": reason,
            "complete_candidate_taxonomy": [],
            "display_symbols": [],
            "summary": summary.to_dict(),
            "expiry_buffer_sessions": self.expiry_buffer_sessions,
            "display_policy": "DIVERSIFIED_COVERAGE_NOT_RANKING",
        }
        family = ContractFamily.create(
            thesis=thesis,
            run_id=run_id,
            family_policy_version=self.family_policy_version,
            evidence_cutoff_utc=cutoff,
            candidate_symbols=(),
            source_dataset_ids=source_dataset_ids,
            family_state=ModelApplicabilityState.DATA_INSUFFICIENT,
            created_at=cutoff,
            metadata=metadata,
        )
        persisted = self.store.record_contract_family(family).record
        return GeneratedContractFamily(persisted, (), (), summary)

    def generate(
        self,
        *,
        thesis: UnderlyingThesisRef,
        observation: GovernedOptionObservation,
        run_id: str,
        current_spot: float | None = None,
        expected_move_pct: float | None = None,
        evaluation_cutoff_utc: datetime | None = None,
    ) -> GeneratedContractFamily:
        cutoff = (
            evaluation_cutoff_utc
            or observation.as_of_utc
            or thesis.evidence_cutoff_utc
        )
        if cutoff.tzinfo is None:
            raise ValueError("family evidence cutoff must be timezone-aware")
        cutoff = cutoff.astimezone(timezone.utc)
        if observation.as_of_utc is not None and observation.as_of_utc > cutoff:
            raise ValueError("family cutoff cannot precede its option observation")
        if not observation.available:
            return self._empty_result(
                thesis=thesis,
                run_id=run_id,
                cutoff=max(cutoff, thesis.evidence_cutoff_utc),
                reason=observation.resolution or "CANONICAL_CHAIN_UNAVAILABLE",
            )
        if observation.ticker != thesis.ticker:
            raise ValueError("option observation ticker conflicts with governed thesis")
        if cutoff < thesis.evidence_cutoff_utc:
            return self._empty_result(
                thesis=thesis,
                run_id=run_id,
                cutoff=thesis.evidence_cutoff_utc,
                reason="OPTION_OBSERVATION_PREDATES_THESIS",
            )
        assert observation.dataset_id is not None
        dataset = self.store.registry.get_dataset(observation.dataset_id)
        if dataset is None:
            raise ValueError("option observation dataset is not registered")
        if (
            dataset.instrument_id != thesis.ticker
            or dataset.dataset_type is not DatasetType.OPTION_CHAIN
            or dataset.provider != "MARKETDATA"
        ):
            raise ValueError("option observation violates canonical chain lineage")
        session_date = dataset.session_date
        frame = observation.frame.reset_index(drop=True)
        spot = _number(current_spot)
        if spot is None:
            spot_values = pd.to_numeric(
                frame.get("underlying_price", pd.Series(dtype="float64")),
                errors="coerce",
            ).dropna()
            spot = _number(spot_values.iloc[0]) if not spot_values.empty else thesis.origin_spot
        required_sessions = thesis.planned_hold_sessions + self.expiry_buffer_sessions

        normalised: list[str | None] = []
        for _, row in frame.iterrows():
            raw = _value(row, "symbol", "option_symbol", "contract_symbol")
            try:
                normalised.append(normalise_occ_symbol(raw))
            except ValueError:
                normalised.append(None)
        duplicate_symbols = {
            symbol for symbol, count in Counter(value for value in normalised if value).items()
            if count > 1
        }

        audits: list[FamilyCandidateAudit] = []
        for row_number, (_, row) in enumerate(frame.iterrows()):
            raw_value = _value(row, "symbol", "option_symbol", "contract_symbol")
            raw_symbol = "" if raw_value is None else str(raw_value).strip()
            symbol = normalised[row_number]
            identity = None
            exclusions: list[StructuralExclusionReason] = []
            if symbol is None:
                exclusions.append(StructuralExclusionReason.INVALID_OCC_IDENTITY)
            else:
                identity = parse_occ_symbol(symbol)
                if symbol in duplicate_symbols:
                    exclusions.append(
                        StructuralExclusionReason.DUPLICATE_CONTRACT_AMBIGUOUS
                    )
            parsed_side = identity.side if identity else None
            if parsed_side is not None and parsed_side != thesis.governed_direction:
                exclusions.append(StructuralExclusionReason.WRONG_OPTION_SIDE)

            row_side_raw = _value(row, "right", "side", "option_side")
            row_side = _side(row_side_raw)
            if row_side_raw is not None and (
                row_side is None or (parsed_side is not None and row_side != parsed_side)
            ):
                exclusions.append(StructuralExclusionReason.IDENTITY_FIELD_MISMATCH)

            expiry = identity.expiry if identity else None
            strike = identity.strike if identity else None
            row_expiry_raw = _value(row, "expiration_date", "expiration", "expiry")
            if row_expiry_raw is not None:
                row_expiry = _date(row_expiry_raw)
                if row_expiry is None:
                    exclusions.append(StructuralExclusionReason.IMPOSSIBLE_STRIKE_OR_EXPIRY)
                elif expiry is not None and row_expiry != expiry:
                    exclusions.append(StructuralExclusionReason.IDENTITY_FIELD_MISMATCH)
            row_strike_raw = _value(row, "strike")
            if row_strike_raw is not None:
                row_strike = _number(row_strike_raw)
                if row_strike is None or row_strike <= 0:
                    exclusions.append(StructuralExclusionReason.IMPOSSIBLE_STRIKE_OR_EXPIRY)
                elif strike is not None and not math.isclose(row_strike, strike, abs_tol=0.0005):
                    exclusions.append(StructuralExclusionReason.IDENTITY_FIELD_MISMATCH)
            if strike is not None and strike <= 0:
                exclusions.append(StructuralExclusionReason.IMPOSSIBLE_STRIKE_OR_EXPIRY)

            remaining = xnys_sessions_between(session_date, expiry) if expiry else None
            if expiry is not None and expiry < session_date:
                exclusions.append(StructuralExclusionReason.EXPIRED_CONTRACT)
            if remaining is not None and remaining < required_sessions:
                exclusions.append(StructuralExclusionReason.INSUFFICIENT_SESSION_RUNWAY)

            bid = _number(_value(row, "bid"))
            ask = _number(_value(row, "ask"))
            if (bid is not None and bid < 0) or (ask is not None and ask < 0):
                exclusions.append(StructuralExclusionReason.NEGATIVE_QUOTE)
            if bid is not None and ask is not None and ask < bid:
                exclusions.append(StructuralExclusionReason.CROSSED_QUOTE)
            quote_state = _quote_state(bid, ask)
            volume = _number(_value(row, "volume"))
            open_interest = _number(_value(row, "open_interest"))
            monitor: list[str] = []
            if open_interest is None:
                monitor.append("OPEN_INTEREST_MISSING")
            elif open_interest < 50:
                monitor.append("LOW_OPEN_INTEREST")
            if volume is None:
                monitor.append("VOLUME_MISSING")
            elif volume == 0:
                monitor.append("ZERO_VOLUME")
            if quote_state == "ONE_SIDED":
                monitor.append("ONE_SIDED_QUOTE")
            elif quote_state == "NO_QUOTE":
                monitor.append("CURRENT_QUOTE_MISSING")

            unique_exclusions = tuple(dict.fromkeys(exclusions))
            if unique_exclusions:
                state = FamilyCandidateState.EXCLUDED_STRUCTURAL
            elif quote_state == "TWO_SIDED":
                state = FamilyCandidateState.ELIGIBLE_TWO_SIDED
            elif quote_state == "ONE_SIDED":
                state = FamilyCandidateState.MONITOR_ONE_SIDED
            else:
                state = FamilyCandidateState.MONITOR_NO_QUOTE
            audit_id = hashlib.sha256(
                f"{observation.dataset_id}|{row_number}|{raw_symbol}".encode("utf-8")
            ).hexdigest()
            audits.append(
                FamilyCandidateAudit(
                    audit_id=audit_id,
                    source_row_index=row_number,
                    raw_contract_symbol=raw_symbol,
                    contract_symbol=symbol,
                    option_side=parsed_side,
                    expiry=expiry,
                    strike=strike,
                    remaining_sessions=remaining,
                    required_sessions=required_sessions,
                    bid=bid,
                    ask=ask,
                    volume=volume,
                    open_interest=open_interest,
                    state=state,
                    structural_exclusions=unique_exclusions,
                    monitor_reasons=tuple(dict.fromkeys(monitor)),
                    quote_state=quote_state,
                    moneyness_bucket=_moneyness_bucket(parsed_side, strike, spot),
                    expiry_bucket=_expiry_bucket(remaining, required_sessions),
                    target_reachability=_target_reachability(
                        parsed_side, strike, thesis.target_spot
                    ),
                    display_eligible=False,
                )
            )

        display_symbols = _bounded_display(audits, self.max_display_candidates)
        audits = [
            replace(item, display_eligible=item.contract_symbol in display_symbols)
            for item in audits
        ]
        candidates = [item for item in audits if item.is_family_candidate]
        exclusions = [item for item in audits if not item.is_family_candidate]
        exclusion_counts = Counter(
            reason.value for item in exclusions for reason in item.structural_exclusions
        )
        summary = ContractFamilyGenerationSummary(
            source_observations=len(audits),
            family_candidates=len(candidates),
            structural_exclusions=len(exclusions),
            two_sided_candidates=sum(
                item.state is FamilyCandidateState.ELIGIBLE_TWO_SIDED for item in candidates
            ),
            monitor_one_sided=sum(
                item.state is FamilyCandidateState.MONITOR_ONE_SIDED for item in candidates
            ),
            monitor_no_quote=sum(
                item.state is FamilyCandidateState.MONITOR_NO_QUOTE for item in candidates
            ),
            retained_low_open_interest=sum(
                item.open_interest is None or item.open_interest < 50 for item in candidates
            ),
            retained_zero_volume=sum(item.volume == 0 for item in candidates),
            displayed_candidates=len(display_symbols),
            direction=thesis.governed_direction,
            counts_by_exclusion=dict(sorted(exclusion_counts.items())),
        )
        candidate_symbols = tuple(
            sorted(item.contract_symbol for item in candidates if item.contract_symbol)
        )
        metadata = {
            "generator_version": DOI_FAMILY_GENERATOR_VERSION,
            "generation_state": (
                "FAMILY_GENERATED" if candidates else "NO_STRUCTURALLY_VALID_CONTRACT"
            ),
            "complete_candidate_taxonomy": audits_to_payload(audits),
            "display_symbols": list(display_symbols),
            "summary": summary.to_dict(),
            "expiry_buffer_sessions": self.expiry_buffer_sessions,
            "max_display_candidates": self.max_display_candidates,
            "display_policy": "DIVERSIFIED_COVERAGE_NOT_RANKING",
            "current_spot": spot,
            "current_spot_source": (
                "CALLER" if _number(current_spot) is not None else "CANONICAL_OR_THESIS"
            ),
            "expected_move_pct": _number(expected_move_pct),
            "structural_exclusions_only": True,
            "low_activity_is_monitorable": True,
        }
        family = ContractFamily.create(
            thesis=thesis,
            run_id=run_id,
            family_policy_version=self.family_policy_version,
            evidence_cutoff_utc=cutoff,
            candidate_symbols=candidate_symbols,
            source_dataset_ids=(observation.dataset_id,),
            family_state=(
                ModelApplicabilityState.DETERMINISTIC_ONLY
                if candidates else ModelApplicabilityState.DATA_INSUFFICIENT
            ),
            created_at=cutoff,
            metadata=metadata,
        )
        persisted = self.store.record_contract_family(family).record
        return GeneratedContractFamily(
            family=persisted,
            taxonomy=tuple(audits),
            display_symbols=display_symbols,
            summary=summary,
        )


__all__ = [
    "DOI_FAMILY_GENERATOR_VERSION",
    "ThesisConditionedContractFamilyGenerator",
]
