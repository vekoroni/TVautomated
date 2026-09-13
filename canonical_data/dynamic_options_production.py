"""DOI-11 production integration over canonical completed-session evidence.

The coordinator is intentionally advisory and reuse-only.  It never calls a
provider, never removes an input opportunity and records ticker-level data
exceptions instead of aborting the pipeline population.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from canonical_data.dynamic_options_bridge import CanonicalDOIObservationBridge
from canonical_data.dynamic_options_family import ThesisConditionedContractFamilyGenerator
from canonical_data.dynamic_options_lifecycle import DynamicOptionsLifecycleService
from canonical_data.dynamic_options_ranking import DynamicOptionsContractRankingService
from canonical_data.dynamic_options_valuation import DeterministicContractValuationService
from canonical_data.option_liquidity_lifecycle import (
    MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import OptionObservationKind, UnderlyingThesisRef
from canonical_data.market_rate_observation import load_market_rate, MarketRateObservation
from domain.dynamic_options_lifecycle import DynamicLifecyclePolicy


DOI_PRODUCTION_INTEGRATION_VERSION = "doi-production-integration-v1"


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value)) and str(value).strip() not in {"", "None", "nan"}
    except (TypeError, ValueError):
        return True


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if _present(value):
            return value
    return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _flag(value: Any) -> bool:
    return str(value or "").strip().upper() in {"1", "TRUE", "YES", "Y", "ON"}


def _instant(value: Any) -> datetime | None:
    if not _present(value):
        return None
    try:
        parsed = pd.to_datetime(value, utc=True, errors="raise")
        return parsed.to_pydatetime().astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _geometry(direction: str, origin: float, value: Any, *, target: bool) -> tuple[float | None, str | None]:
    number = _number(value)
    if number is None or number <= 0:
        return None, "MISSING_OR_INVALID"
    sign = 1.0 if direction == "CALL" else -1.0
    valid = sign * (number - origin) > 0 if target else sign * (origin - number) > 0
    return (number, None) if valid else (None, "WRONG_SIDED_REMOVED")


@dataclass(frozen=True, slots=True)
class DOIProductionSummary:
    run_id: str
    input_rows: int
    unique_tickers: int
    retained_opportunities: int
    family_rows: int
    family_candidates_total: int
    bounded_candidates_total: int
    retained_low_open_interest: int
    retained_zero_volume: int
    assessed_families: int
    ranked_families: int
    lifecycle_families: int
    canonical_reuse: int
    physical_fetch_count: int
    exception_count: int
    unassessed_families: int
    unranked_assessed_families: int
    accounted_terminal_rows: int
    population_reconciled: bool
    counts_by_state: Mapping[str, int]
    exceptions: tuple[Mapping[str, Any], ...]
    authority: str = "ADVISORY_ONLY"
    deleted_opportunities: int = 0
    integration_version: str = DOI_PRODUCTION_INTEGRATION_VERSION

    def __post_init__(self) -> None:
        if self.retained_opportunities != self.unique_tickers or self.deleted_opportunities:
            raise ValueError("DOI production integration must preserve every opportunity")
        if self.physical_fetch_count:
            raise ValueError("DOI production integration is canonical-reuse-only")
        if not self.population_reconciled or self.accounted_terminal_rows != self.unique_tickers:
            raise ValueError("DOI terminal population does not reconcile")
        if self.family_rows != self.assessed_families + self.unassessed_families:
            raise ValueError("DOI family assessment population does not reconcile")
        if self.assessed_families != self.ranked_families + self.unranked_assessed_families:
            raise ValueError("DOI assessed/ranked population does not reconcile")

    def to_dict(self) -> dict[str, Any]:
        return {
            **{name: getattr(self, name) for name in self.__dataclass_fields__},
            "counts_by_state": dict(self.counts_by_state),
            "exceptions": list(self.exceptions),
            "population_equation": (
                f"{self.unique_tickers} input = {self.accounted_terminal_rows} "
                "terminal retained/exception rows"
            ),
        }


def run_completed_session_doi(
    *, run_id: str, options_csv: Path | str, registry_path: Path | str,
    report_path: Path | str, max_tickers: int | None = None,
    macro_path: Path | str | None = None,
    governed_constants_path: Path | str | None = None,
) -> DOIProductionSummary:
    source = Path(options_csv)
    if not source.is_file():
        raise FileNotFoundError(source)
    frame = pd.read_csv(source, low_memory=False)
    market_rate = load_market_rate(macro_path) if macro_path else MarketRateObservation(None, "NONE", None, None, "RATE_UNAVAILABLE")
    constants: dict[str, Any] = {}
    if governed_constants_path and Path(governed_constants_path).is_file():
        constants = json.loads(Path(governed_constants_path).read_text(encoding="utf-8-sig"))
    if "ticker" not in frame.columns:
        raise ValueError("DOI source has no ticker column")
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame = frame.loc[frame["ticker"].ne("") & frame["ticker"].ne("NAN")]
    frame = frame.drop_duplicates("ticker", keep="first")
    if max_tickers is not None:
        frame = frame.head(max(0, int(max_tickers)))

    finality_path = source.parent / f"provider_finality_{run_id}.json"
    if not finality_path.is_file():
        raise ValueError("DOI completed-session input has no provider-finality evidence")
    finality_payload = json.loads(finality_path.read_text(encoding="utf-8-sig"))
    finality_rows = finality_payload.get("ticker_assessments")
    if not isinstance(finality_rows, list):
        raise ValueError("provider-finality evidence has no ticker assessments")
    finality_by_ticker = {
        str(item.get("ticker") or "").strip().upper(): item
        for item in finality_rows
        if isinstance(item, Mapping) and str(item.get("ticker") or "").strip()
    }

    registry = CanonicalRegistry(registry_path)
    store = OptionLiquidityLifecycleStore(registry)
    store.initialise()
    bridge = CanonicalDOIObservationBridge(registry_path=registry_path)
    generator = ThesisConditionedContractFamilyGenerator(store)
    preferred_cfg = dict(constants.get("preferred_contract") or {})
    if preferred_cfg and not bool(preferred_cfg.get("approved", False)):
        raise ValueError("preferred-contract hysteresis configuration is not approved")
    margin_abs = float(preferred_cfg.get("margin_abs", 0.05))
    margin_relative = float(preferred_cfg.get("margin_relative", 0.10))
    lifecycle_service = DynamicOptionsLifecycleService(
        store,
        policy=DynamicLifecyclePolicy(
            minimum_utility_margin=margin_abs,
            relative_utility_margin=margin_relative,
            hysteresis_policy_version=str(
                preferred_cfg.get("version") or "hysteresis_v1"
            ),
            hysteresis_approval_id=(
                str(preferred_cfg.get("approval_id") or "").strip() or None
            ),
        ),
    )
    ranker = DynamicOptionsContractRankingService(
        store,
        deterministic_fallback_margin=margin_abs,
        deterministic_fallback_relative_margin=margin_relative,
    )

    states: Counter[str] = Counter()
    exceptions: list[dict[str, Any]] = []
    family_rows = assessed = ranked = lifecycle = reused = 0
    family_candidates_total = bounded_candidates_total = 0
    retained_low_open_interest = retained_zero_volume = 0

    for raw in frame.to_dict(orient="records"):
        ticker = str(raw.get("ticker") or "").strip().upper()
        pipeline_stage = "THESIS_VALIDATION"
        try:
            direction = str(_first(raw, "governed_direction", "canonical_direction", "direction") or "").strip().upper()
            if direction not in {"CALL", "PUT"}:
                states["NOT_APPLICABLE_NON_DIRECTIONAL"] += 1
                continue
            thesis_id = str(_first(raw, "thesis_id") or "").strip()
            if not thesis_id:
                raise ValueError("MISSING_GOVERNED_THESIS_ID")
            spot = _number(_first(raw, "underlying_price", "spot_price", "current_price", "signal_price"))
            hold = _number(_first(raw, "planned_hold_sessions", "hold_sessions"))
            cutoff = _instant(_first(raw, "quote_timestamp_utc", "evidence_cutoff_utc", "selected_quote_timestamp_utc"))
            if spot is None or spot <= 0:
                raise ValueError("MISSING_POSITIVE_ORIGIN_SPOT")
            if hold is None or not 1 <= int(hold) <= 20:
                raise ValueError("MISSING_GOVERNED_HOLD_SESSIONS")
            if cutoff is None:
                raise ValueError("MISSING_POINT_IN_TIME_CUTOFF")
            target, target_warning = _geometry(
                direction, spot, _first(raw, "target_spot", "structural_target", "target_price"), target=True,
            )
            invalidation, invalidation_warning = _geometry(
                direction, spot, _first(raw, "invalidation_spot", "structural_invalidation", "stop_loss"), target=False,
            )
            thesis = UnderlyingThesisRef(
                thesis_id=thesis_id, thesis_version=int(_number(raw.get("thesis_version")) or 1),
                ticker=ticker, governed_direction=direction, origin_spot=spot,
                origin_timestamp_utc=cutoff, target_spot=target,
                invalidation_spot=invalidation, planned_hold_sessions=int(hold),
                planned_hold_source=str(_first(raw, "planned_hold_source") or "HORIZON_ROUTER"),
                evidence_cutoff_utc=cutoff,
            )
            # Options Intelligence/OLM normally owns the governed thesis event
            # and runs before DOI. Reuse that event when it exists; attempting
            # to append a duplicate lifecycle event here creates a false
            # optimistic-concurrency conflict on every established thesis.
            existing_thesis = store.latest_thesis(thesis.thesis_id)
            if existing_thesis is not None:
                if existing_thesis.ticker != ticker or existing_thesis.direction != direction:
                    raise ValueError("EXISTING_THESIS_IDENTITY_MISMATCH")
            else:
                store.record_thesis_event(
                    thesis_id=thesis.thesis_id,
                    event_key=f"DOI_COMPLETED_SESSION:{cutoff.date().isoformat()}",
                    run_id=run_id, ticker=ticker, direction=direction,
                    thesis_state=ThesisState.ACTIVE, monitor_state=MonitorState.ACTIVE,
                    reason_code="GOVERNED_PIPELINE_THESIS", structural_target=target,
                    invalidation_spot=invalidation, recorded_at=cutoff,
                    metadata={
                        "source": str(source), "target_warning": target_warning,
                        "invalidation_warning": invalidation_warning,
                        "authority": "ADVISORY_ONLY",
                    },
                    calculation_version=DOI_PRODUCTION_INTEGRATION_VERSION,
                )
            observation = bridge.resolve(
                ticker=ticker, session_date=cutoff.date(),
                observation_kind=OptionObservationKind.COMPLETED_SESSION,
                evidence_cutoff_utc=cutoff, acquire_missing=None,
                provider_finality=finality_by_ticker.get(ticker),
            )
            if observation.physical_fetch_count:
                raise ValueError("UNEXPECTED_PROVIDER_FETCH")
            if observation.available:
                reused += 1
            if not observation.normal_completed_session_eligible:
                finality = observation.provider_finality or {}
                states["PROVIDER_FINALITY_EXCEPTION_RETAINED"] += 1
                exceptions.append({
                    "ticker": ticker,
                    "error_type": "ProviderFinalityException",
                    "reason": str(
                        finality.get("finality_state")
                        or "PROVIDER_SESSION_EVIDENCE_INSUFFICIENT"
                    ),
                    "finality_reasons": list(finality.get("reasons") or ()),
                    "retained": True,
                })
                continue
            pipeline_stage = "FAMILY_GENERATION"
            generated = generator.generate(
                thesis=thesis, observation=observation, run_id=run_id,
                current_spot=spot, evaluation_cutoff_utc=cutoff,
            )
            family_rows += 1
            family_candidates_total += generated.summary.family_candidates
            bounded_candidates_total += len(generated.display_symbols)
            retained_low_open_interest += generated.summary.retained_low_open_interest
            retained_zero_volume += generated.summary.retained_zero_volume
            if not observation.available or not generated.family.candidate_symbols:
                states["FAMILY_DATA_INSUFFICIENT"] += 1
                continue
            pipeline_stage = "DETERMINISTIC_VALUATION"
            rate = market_rate.rate_annual_fraction
            if rate is None:
                rate = _number(_first(raw, "ev3_rate_used", "risk_free_rate"))
            if rate is None or not -0.05 <= rate <= 0.25:
                states["FAMILY_NOT_VALUED_RATE_UNAVAILABLE"] += 1
                continue
            dividend_raw = _number(_first(raw, "ev3_dividend_yield_used", "dividend_yield"))
            dividend_available = dividend_raw is not None and dividend_raw >= 0.0
            dividend = dividend_raw if dividend_available else 0.0
            valuation = DeterministicContractValuationService(
                store, risk_free_rate=rate, dividend_yield=max(0.0, dividend),
                dividend_yield_available=dividend_available,
                market_rate_observation=market_rate,
                governed_constants=constants,
            ).evaluate_family(
                generated_family=generated, observation=observation,
                # The full structural taxonomy remains immutable in the
                # family. Production valuation/ranking uses its deterministic,
                # diversified bounded set so a 300-contract chain cannot add
                # hours of per-contract persistence to the evening run.
                contract_symbols=generated.display_symbols,
                ex_dividend_within_horizon=_flag(_first(
                    raw, "ex_dividend_within_horizon", "dividend_within_horizon"
                )),
                corporate_action_flag=_flag(_first(
                    raw, "corporate_action_flag", "corporate_action_within_horizon"
                )),
                annual_forecast_vol=_number(_first(
                    raw, "l3_forward_realised_vol", "forecast_vol_annual_fraction",
                    "forward_realised_vol"
                )),
            )
            assessed += 1
            pipeline_stage = "LIFECYCLE_EVALUATION"
            lifecycle_result = lifecycle_service.evaluate_completed_session(
                generated_family=generated, valuation_result=valuation,
                evaluation_session=cutoff.date(), horizon_end_date=None,
                event_key=f"DOI_COMPLETED_SESSION:{cutoff.date().isoformat()}",
                current_spot=spot,
            )
            lifecycle += 1
            previous = (
                lifecycle_result.preferred_decision.selected_contract_symbol
                if lifecycle_result.preferred_decision else None
            )
            pipeline_stage = "FAMILY_RANKING"
            ranker.rank_family(family_id=generated.family.family_id, previous_contract_symbol=previous)
            ranked += 1
            states["RANKED_DETERMINISTIC"] += 1
        except Exception as error:  # ticker exception boundary is intentional
            states["DATA_EXCEPTION_RETAINED"] += 1
            exceptions.append({
                "ticker": ticker, "error_type": type(error).__name__,
                "reason": str(error), "retained": True,
                "pipeline_stage": pipeline_stage,
            })

    accounted_terminal_rows = sum(states.values())
    summary = DOIProductionSummary(
        run_id=run_id, input_rows=len(pd.read_csv(source, usecols=["ticker"])),
        unique_tickers=len(frame), retained_opportunities=len(frame),
        family_rows=family_rows,
        family_candidates_total=family_candidates_total,
        bounded_candidates_total=bounded_candidates_total,
        retained_low_open_interest=retained_low_open_interest,
        retained_zero_volume=retained_zero_volume,
        assessed_families=assessed,
        ranked_families=ranked, lifecycle_families=lifecycle,
        canonical_reuse=reused, physical_fetch_count=0,
        exception_count=len(exceptions),
        unassessed_families=family_rows - assessed,
        unranked_assessed_families=assessed - ranked,
        accounted_terminal_rows=accounted_terminal_rows,
        population_reconciled=(accounted_terminal_rows == len(frame)),
        counts_by_state=dict(states),
        exceptions=tuple(exceptions),
    )
    target = Path(report_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(summary.to_dict(), indent=2, default=str), encoding="utf-8")
    temporary.replace(target)
    return summary


__all__ = ["DOI_PRODUCTION_INTEGRATION_VERSION", "DOIProductionSummary", "run_completed_session_doi"]
