"""DOI-5 canonical application service for deterministic option scenarios.

This service joins a DOI-4 family to the exact canonical MarketData rows,
persists immutable quote observations, runs the pure DOI-5 valuation domain,
and persists advisory assessments.  It performs no provider request and does
not choose or authorise a contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any, Sequence

import pandas as pd

from domain.contract_family_generation import GeneratedContractFamily
from domain.deterministic_option_valuation import (
    DOI_SCENARIO_ENGINE_VERSION,
    DOI_SCENARIO_UTILITY_VERSION,
    DOI_VALUATION_MODEL_VERSION,
    DeterministicContractValuation,
    ScenarioPoint,
    ScenarioTiming,
    evaluate_deterministic_scenarios,
)
from domain.contract_economics_v2 import evaluate_contract_economics_v2
from domain.volatility_budget import calculate_volatility_budget
from domain.reachability import assess_reachability
from canonical_data.market_rate_observation import MarketRateObservation
from domain.dynamic_options_intelligence import (
    ContractAssessment,
    ContractEntryState,
    ModelApplicabilityState,
)

from .dynamic_options_bridge import GovernedOptionObservation
from .option_identity import normalise_occ_symbol, parse_occ_symbol
from .option_liquidity_lifecycle import (
    ContractLiquidityState,
    OptionLiquidityLifecycleStore,
)
from .session_clock import is_xnys_session, session_bounds


DOI_DETERMINISTIC_VALUATION_SERVICE_VERSION = "doi-deterministic-valuation-service-v1"
DOI_DETERMINISTIC_FEATURE_VERSION = "doi-scenario-input-features-v1"


@dataclass(frozen=True, slots=True)
class ContractValuationResult:
    assessment: ContractAssessment
    valuation: DeterministicContractValuation
    observation_id: str
    observation_reused: bool
    assessment_reused: bool


@dataclass(frozen=True, slots=True)
class ContractFamilyValuationSummary:
    family_candidates: int
    assessed_contracts: int
    scenario_values: int
    utility_available: int
    deterministic_only: int
    out_of_distribution: int
    data_insufficient: int
    two_sided: int
    one_sided: int
    no_quote: int
    direction: str
    physical_fetch_count: int = 0

    def __post_init__(self) -> None:
        if self.assessed_contracts != (
            self.deterministic_only + self.out_of_distribution + self.data_insufficient
        ):
            raise ValueError("assessment applicability population does not reconcile")
        if self.family_candidates != self.assessed_contracts:
            raise ValueError("every family candidate must receive an assessment")
        if self.assessed_contracts != self.two_sided + self.one_sided + self.no_quote:
            raise ValueError("assessment quote-state population does not reconcile")
        if self.physical_fetch_count != 0:
            raise ValueError("DOI-5 valuation cannot perform provider acquisition")

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class ContractFamilyValuationResult:
    family_id: str
    results: tuple[ContractValuationResult, ...]
    summary: ContractFamilyValuationSummary
    service_version: str = DOI_DETERMINISTIC_VALUATION_SERVICE_VERSION


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


def _utc(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="raise", utc=True)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.to_pydatetime().astimezone(timezone.utc)


def _next_session(value: date) -> date:
    candidate = value + timedelta(days=1)
    while not is_xnys_session(candidate):
        candidate += timedelta(days=1)
    return candidate


def _advance_sessions(value: date, count: int) -> date:
    result = value
    for _ in range(int(count)):
        result = _next_session(result)
    return result


def _previous_session(value: date) -> date:
    candidate = value
    while not is_xnys_session(candidate):
        candidate -= timedelta(days=1)
    return candidate


def build_xnys_scenario_points(
    *, start_session: date, planned_hold_sessions: int
) -> tuple[ScenarioPoint, ...]:
    """Build early/mid/late scenario instants at completed XNYS closes."""

    hold = int(planned_hold_sessions)
    if not 1 <= hold <= 20:
        raise ValueError("planned_hold_sessions must be between 1 and 20")
    if not is_xnys_session(start_session):
        raise ValueError("start_session must be an XNYS trading session")
    early = max(1, math.ceil(hold / 3.0))
    middle = max(early, math.ceil((2.0 * hold) / 3.0))
    offsets = {
        ScenarioTiming.EARLY: early,
        ScenarioTiming.MID: middle,
        ScenarioTiming.LATE: hold,
    }
    return tuple(
        ScenarioPoint(
            timing=timing,
            sessions_elapsed=offset,
            as_of_utc=session_bounds(_advance_sessions(start_session, offset))[1],
        )
        for timing, offset in offsets.items()
    )


def _expiration_close(expiration: date) -> datetime:
    return session_bounds(_previous_session(expiration))[1]


def _quote_state(bid: float | None, ask: float | None) -> str:
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return "TWO_SIDED"
    if (bid is not None and bid > 0) or (ask is not None and ask > 0):
        return "ONE_SIDED"
    return "NO_QUOTE"


def _liquidity_state(quote_state: str, bid: float | None) -> ContractLiquidityState:
    if quote_state == "TWO_SIDED":
        return ContractLiquidityState.REVIEWABLE_SPREAD
    if quote_state == "ONE_SIDED" and (bid is None or bid <= 0):
        return ContractLiquidityState.ZERO_BID
    if quote_state == "ONE_SIDED":
        return ContractLiquidityState.LIQUIDITY_PENDING
    return ContractLiquidityState.NO_CURRENT_MARKET


def _entry_state(quote_state: str) -> ContractEntryState:
    if quote_state == "TWO_SIDED":
        return ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED
    if quote_state == "ONE_SIDED":
        return ContractEntryState.CONTRACT_LIQUIDITY_DEVELOPING
    return ContractEntryState.CONTRACT_DATA_INSUFFICIENT


class DeterministicContractValuationService:
    def __init__(
        self,
        store: OptionLiquidityLifecycleStore,
        *,
        risk_free_rate: float,
        dividend_yield: float = 0.0,
        dividend_yield_available: bool = True,
        entry_friction_bps: float = 25.0,
        exit_friction_bps: float = 25.0,
        market_rate_observation: MarketRateObservation | None = None,
        governed_constants: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.risk_free_rate = float(risk_free_rate)
        self.dividend_yield = float(dividend_yield)
        self.dividend_yield_available = bool(dividend_yield_available)
        self.entry_friction_bps = float(entry_friction_bps)
        self.exit_friction_bps = float(exit_friction_bps)
        self.market_rate_observation = market_rate_observation
        self.governed_constants = dict(governed_constants or {})
        for value, name in (
            (self.risk_free_rate, "risk_free_rate"),
            (self.dividend_yield, "dividend_yield"),
            (self.entry_friction_bps, "entry_friction_bps"),
            (self.exit_friction_bps, "exit_friction_bps"),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.dividend_yield < 0:
            raise ValueError("dividend_yield cannot be negative")

    def _calculation_version(
        self, *, ex_dividend_within_horizon: bool, corporate_action_flag: bool
    ) -> str:
        assumptions = json.dumps(
            {
                "risk_free_rate": self.risk_free_rate,
                "dividend_yield": self.dividend_yield,
                "dividend_yield_available": self.dividend_yield_available,
                "entry_friction_bps": self.entry_friction_bps,
                "exit_friction_bps": self.exit_friction_bps,
                "ex_dividend_within_horizon": bool(ex_dividend_within_horizon),
                "corporate_action_flag": bool(corporate_action_flag),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(assumptions.encode("utf-8")).hexdigest()[:12]
        return f"{DOI_SCENARIO_ENGINE_VERSION}:{fingerprint}"

    def evaluate_family(
        self,
        *,
        generated_family: GeneratedContractFamily,
        observation: GovernedOptionObservation,
        contract_symbols: Sequence[str] | None = None,
        ex_dividend_within_horizon: bool = False,
        corporate_action_flag: bool = False,
        annual_forecast_vol: float | None = None,
    ) -> ContractFamilyValuationResult:
        family = generated_family.family
        thesis = family.thesis
        if not observation.available or observation.dataset_id is None or observation.as_of_utc is None:
            raise ValueError("DOI-5 requires an available canonical observation")
        if observation.ticker != thesis.ticker:
            raise ValueError("observation ticker conflicts with contract family")
        if observation.dataset_id not in family.source_dataset_ids:
            raise ValueError("observation dataset is outside family lineage")
        dataset = self.store.registry.get_dataset(observation.dataset_id)
        if dataset is None or dataset.provider != "MARKETDATA":
            raise ValueError("DOI-5 requires registered canonical MarketData evidence")

        evaluation_symbols = tuple(
            sorted(set(contract_symbols if contract_symbols is not None else family.candidate_symbols))
        )
        if not set(evaluation_symbols).issubset(set(family.candidate_symbols)):
            raise ValueError("valuation symbols are outside the governed contract family")
        rows: dict[str, pd.Series] = {}
        for _, row in observation.frame.iterrows():
            try:
                symbol = normalise_occ_symbol(
                    _value(row, "symbol", "option_symbol", "contract_symbol")
                )
            except ValueError:
                continue
            if symbol in evaluation_symbols:
                if symbol in rows:
                    raise ValueError(f"admitted family contract is duplicated: {symbol}")
                rows[symbol] = row
        missing = set(evaluation_symbols) - set(rows)
        if missing:
            raise ValueError(f"family candidates absent from observation: {sorted(missing)}")

        start_session = dataset.session_date
        points = build_xnys_scenario_points(
            start_session=start_session,
            planned_hold_sessions=thesis.planned_hold_sessions,
        )
        calculation_version = self._calculation_version(
            ex_dividend_within_horizon=ex_dividend_within_horizon,
            corporate_action_flag=corporate_action_flag,
        )
        results: list[ContractValuationResult] = []
        quote_counts = {"TWO_SIDED": 0, "ONE_SIDED": 0, "NO_QUOTE": 0}
        for symbol in evaluation_symbols:
            row = rows[symbol]
            identity = parse_occ_symbol(symbol)
            bid = _number(_value(row, "bid"))
            ask = _number(_value(row, "ask"))
            bid_size = _number(_value(row, "bid_size", "bidSize"))
            ask_size = _number(_value(row, "ask_size", "askSize"))
            volume = _number(_value(row, "volume"))
            open_interest = _number(_value(row, "open_interest", "openInterest"))
            iv = _number(_value(
                row, "iv", "implied_vol", "implied_volatility", "impliedVolatility"
            ))
            delta = _number(_value(row, "delta"))
            spot = _number(_value(row, "underlying_price", "spot", "underlyingPrice")) or thesis.origin_spot
            quote_time = _utc(_value(
                row, "quote_timestamp_utc", "quote_as_of", "updated", "last_updated"
            ))
            if quote_time is None:
                raise ValueError(f"MISSING_PROVIDER_QUOTE_TIMESTAMP:{symbol}")
            cutoff = max(family.evidence_cutoff_utc, quote_time)
            quote_state = _quote_state(bid, ask)
            quote_counts[quote_state] += 1
            spread = None
            if bid is not None and ask is not None and bid > 0 and ask > 0:
                midpoint = (bid + ask) / 2.0
                spread = (ask - bid) / midpoint if midpoint > 0 else None
            dte = max(0.0, (_expiration_close(identity.expiry) - quote_time).total_seconds() / 86_400.0)
            observed = self.store.record_contract_observation(
                thesis_id=thesis.thesis_id, run_id=family.run_id,
                ticker=thesis.ticker, contract_symbol=symbol,
                option_side=identity.side, quote_as_of=quote_time,
                source_dataset_id=observation.dataset_id, spot=spot,
                strike=identity.strike, expiration=identity.expiry, dte=dte,
                liquidity_state=_liquidity_state(quote_state, bid),
                observed_at=cutoff, delta=delta, bid=bid, ask=ask,
                bid_size=bid_size, ask_size=ask_size, spread_pct=spread,
                volume=volume, open_interest=open_interest, iv=iv,
                calculation_version=DOI_DETERMINISTIC_VALUATION_SERVICE_VERSION,
            )
            valuation = evaluate_deterministic_scenarios(
                option_side=identity.side, strike=identity.strike,
                expiration_utc=_expiration_close(identity.expiry),
                target_spot=thesis.target_spot,
                invalidation_spot=thesis.invalidation_spot,
                base_iv=iv, scenario_points=points, entry_ask=ask,
                risk_free_rate=self.risk_free_rate,
                dividend_yield=self.dividend_yield,
                entry_friction_bps=self.entry_friction_bps,
                exit_friction_bps=self.exit_friction_bps,
                ex_dividend_within_horizon=ex_dividend_within_horizon,
                corporate_action_flag=corporate_action_flag,
                dividend_yield_available=self.dividend_yield_available,
            )
            vol_cfg = dict(self.governed_constants.get("volatility_budget") or {})
            econ_cfg = dict(self.governed_constants.get("contract_economics") or {})
            budget = calculate_volatility_budget(
                annual_forecast_vol, thesis.planned_hold_sessions,
                bias_multiplier=float(vol_cfg.get("bias_multiplier", 1.0)),
                validation_state=str(vol_cfg.get("validation_state", "UNVALIDATED")),
                multiplier_approved=bool(vol_cfg.get("bias_multiplier_approved", False)),
                validation_report_id=vol_cfg.get("validation_report_id"),
                held_out_validation_passed=bool(
                    vol_cfg.get("held_out_validation_passed", False)
                ),
            )
            reachability = assess_reachability(
                direction=identity.side, origin_spot=thesis.origin_spot,
                structural_target_spot=thesis.target_spot, budget=budget,
                sigma_multiple=float(econ_cfg.get("sigma_multiple", 1.5)),
            )
            sign = 1.0 if identity.side == "CALL" else -1.0
            move = budget.expected_move_fraction
            economics_v2 = evaluate_contract_economics_v2(
                option_side=identity.side, origin_spot=thesis.origin_spot,
                strike=identity.strike, expiration_utc=_expiration_close(identity.expiry),
                base_iv=iv, entry_bid=bid, entry_ask=ask,
                risk_free_rate=self.risk_free_rate, dividend_yield=self.dividend_yield,
                scenario_points=points,
                favourable_1sigma=None if move is None else thesis.origin_spot * (1 + sign * move),
                favourable_2sigma=None if move is None else thesis.origin_spot * (1 + sign * 2 * move),
                reachable_spot=reachability.reachable_target_spot,
                structural_target=thesis.target_spot, invalidation_spot=thesis.invalidation_spot,
                spread_cap=float(econ_cfg.get("friction_spread_cap", .15)),
                max_model_spread=float(econ_cfg.get("friction_max_model_spread", .30)),
                profit_floor=econ_cfg.get("profit_floor"),
                profit_floor_approved=bool(econ_cfg.get("profit_floor_approved", False)),
                profit_floor_approval_id=econ_cfg.get("profit_floor_approval_id"),
                w_flat=float(econ_cfg.get("utility_flat_weight", .5)),
            )
            metadata = {
                "valuation": valuation.to_dict(),
                "quote_state": quote_state,
                "risk_free_rate": self.risk_free_rate,
                "dividend_yield": self.dividend_yield,
                "dividend_yield_available": self.dividend_yield_available,
                "entry_friction_bps": self.entry_friction_bps,
                "exit_friction_bps": self.exit_friction_bps,
                "scenario_weighting": "NONE",
                "utility_is_probability": False,
                "probability_outputs_withheld": True,
                "human_execution_only": True,
                "source_dataset_id": observation.dataset_id,
                "observation_resolution": observation.resolution,
                "upstream_physical_fetch_count": observation.physical_fetch_count,
                "valuation_service_physical_fetch_count": 0,
                "contract_symbol_exact": symbol,
                "volatility_budget_v2": budget.to_dict(),
                "reachability_assessment_v1": reachability.to_dict(),
                "contract_assessment_v2": economics_v2.to_dict(),
                "market_rate_observation": self.market_rate_observation.to_dict() if self.market_rate_observation else None,
                "ranking_score_kind": "DETERMINISTIC_UTILITY",
                "calibration_state": "NOT_AVAILABLE",
            }
            assessment = ContractAssessment.create(
                family_id=family.family_id, thesis_id=thesis.thesis_id,
                run_id=family.run_id, contract_symbol=symbol,
                observation_id=observed.record.observation_id,
                entry_state=_entry_state(quote_state),
                applicability_state=valuation.applicability_state,
                evidence_cutoff_utc=cutoff,
                input_dataset_ids=(observation.dataset_id,),
                calculation_version=calculation_version,
                feature_version=DOI_DETERMINISTIC_FEATURE_VERSION,
                model_version=DOI_VALUATION_MODEL_VERSION,
                ranking_score_uncalibrated=(
                    economics_v2.deterministic_utility
                    if economics_v2.deterministic_utility is not None
                    else valuation.ranking_score_uncalibrated
                ),
                probabilities_calibrated=False,
                metadata=metadata,
            )
            persisted = self.store.record_contract_assessment(assessment)
            results.append(ContractValuationResult(
                assessment=persisted.record, valuation=valuation,
                observation_id=observed.record.observation_id,
                observation_reused=observed.reused_existing,
                assessment_reused=persisted.reused_existing,
            ))

        applicability = [item.assessment.applicability_state for item in results]
        summary = ContractFamilyValuationSummary(
            family_candidates=len(evaluation_symbols),
            assessed_contracts=len(results),
            scenario_values=sum(len(item.valuation.scenarios) for item in results),
            utility_available=sum(item.assessment.ranking_score_uncalibrated is not None for item in results),
            deterministic_only=sum(item is ModelApplicabilityState.DETERMINISTIC_ONLY for item in applicability),
            out_of_distribution=sum(item is ModelApplicabilityState.OUT_OF_DISTRIBUTION for item in applicability),
            data_insufficient=sum(item is ModelApplicabilityState.DATA_INSUFFICIENT for item in applicability),
            two_sided=quote_counts["TWO_SIDED"],
            one_sided=quote_counts["ONE_SIDED"],
            no_quote=quote_counts["NO_QUOTE"],
            direction=thesis.governed_direction,
        )
        return ContractFamilyValuationResult(
            family_id=family.family_id, results=tuple(results), summary=summary
        )


__all__ = [
    "DOI_DETERMINISTIC_VALUATION_SERVICE_VERSION",
    "DOI_DETERMINISTIC_FEATURE_VERSION",
    "ContractValuationResult", "ContractFamilyValuationSummary",
    "ContractFamilyValuationResult", "build_xnys_scenario_points",
    "DeterministicContractValuationService",
]
