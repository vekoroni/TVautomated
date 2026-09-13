"""AVSHUNTER Canonical Data System (CDS) control-plane primitives.

Provider transports are intentionally lazy.  Importing a CDS contract (for
example from the Pipeline Interpreter) must not pull a network client into
that process's import graph.
"""

from importlib import import_module

from .contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetRequest,
    DatasetResolution,
    DatasetType,
    ResolutionKind,
)
from .daily_adapter import (
    CanonicalDailyHistoryAdapter,
    EnsureHistoryResult,
    MissingDateRange,
    boundary_missing_ranges,
)
from .discovery_publisher import (
    DiscoveryPublication,
    publish_discovery_csv,
    publish_discovery_outcomes,
    read_discovery_outcomes,
)
from .feature_flags import CanonicalFeatureFlags
from .gateway import CanonicalDataGateway
from .historical_prices import (
    DEFAULT_ADJUSTMENT,
    HistoricalPriceDatabase,
    PriceCoverage,
    PriceIngestResult,
    normalise_daily_ohlcv,
)
from .history_bridge import (
    DEFAULT_HISTORY_MAX_STALENESS_DAYS,
    canonical_history_is_fresh,
    history_date_is_fresh,
    history_staleness_days,
    observe_shadow_history,
    read_canonical_history,
    write_through_fetched_history,
)
from .lifecycle import (
    AuthorisationDecision,
    DropClass,
    LifecycleManager,
    LifecycleState,
    TickerLifecycleEvent,
    WorklistReconciliation,
)
from .registry import CanonicalRegistry
from .request_ledger import RequestLedger, RequestResolution
from .option_chain_store import (
    CHAIN_SCHEMA_VERSION,
    CanonicalOptionChainService,
    OptionChainResult,
    resolve_completed_session_date,
)
from .option_identity import OptionIdentity, build_occ_symbol, normalise_occ_symbol, parse_occ_symbol
from .intraday_bars import (
    CanonicalMinuteBarResolver,
    IntradayBatchResult,
    IntradayBarResult,
    IntradayQuality,
    IntradayRequestPlan,
    INTRADAY_BAR_SCHEMA_VERSION,
    assess_intraday_quality,
    expected_intraday_timestamps,
    intraday_schema_version,
    missing_intraday_ranges,
    normalise_intraday_bars,
    normalise_minute_bars,
)
from .session_clock import (
    advance_xnys_sessions,
    FreshnessState,
    SessionSnapshot,
    SessionState,
    evaluate_freshness,
    is_early_close,
    is_xnys_session,
    previous_xnys_session,
    session_bounds,
    session_snapshot,
)
from .option_liquidity_lifecycle import (
    ContractLiquidityState,
    DOI_OUTCOME_SCHEMA_VERSION,
    MonitorState,
    OptionLiquidityLifecycleStore,
    ThesisState,
)
from domain.dynamic_options_intelligence import (
    DOI_DOMAIN_VERSION,
    ContractAssessment,
    ContractEntryState,
    ContractFamily,
    ModelApplicabilityState,
    ObservationAcquisitionDecision,
    OpportunityAcquisitionState,
    OptionObservationKind,
    PreferredContractDecision,
    UnderlyingThesisRef,
    decide_observation_acquisition,
)
from .dynamic_options_bridge import (
    DOI_ACTIVITY_FEATURE_VERSION,
    DOI_OBSERVATION_BRIDGE_VERSION,
    DOI_PCR_FEATURE_VERSION,
    DOI_PHANTOM_PROJECTION_VERSION,
    CanonicalDOIObservationBridge,
    ContractActivityFeatures,
    DOIObservationBundle,
    GovernedOptionObservation,
    PhantomDOIProjectionRepository,
    PhantomHistoricalProjection,
    PutCallContextFeatures,
    extract_contract_activity,
    extract_put_call_context,
)
from domain.contract_family_generation import (
    DOI_FAMILY_POLICY_VERSION,
    ContractFamilyGenerationSummary,
    FamilyCandidateAudit,
    FamilyCandidateState,
    GeneratedContractFamily,
    StructuralExclusionReason,
)
from .dynamic_options_family import (
    DOI_FAMILY_GENERATOR_VERSION,
    ThesisConditionedContractFamilyGenerator,
)
from domain.deterministic_option_valuation import (
    DOI_SCENARIO_ENGINE_VERSION,
    DOI_SCENARIO_UTILITY_VERSION,
    DOI_VALUATION_MODEL_VERSION,
    DeterministicContractValuation,
    IVStress,
    ScenarioPath,
    ScenarioPoint,
    ScenarioTiming,
    ScenarioValuation,
    dividend_adjusted_black_scholes,
    evaluate_deterministic_scenarios,
)
from .dynamic_options_valuation import (
    DOI_DETERMINISTIC_FEATURE_VERSION,
    DOI_DETERMINISTIC_VALUATION_SERVICE_VERSION,
    ContractFamilyValuationResult,
    ContractFamilyValuationSummary,
    ContractValuationResult,
    DeterministicContractValuationService,
    build_xnys_scenario_points,
)
from domain.dynamic_options_lifecycle import (
    DOI_HYSTERESIS_POLICY_VERSION,
    DOI_LIFECYCLE_DOMAIN_VERSION,
    DOI_MATERIAL_CHANGE_POLICY_VERSION,
    ContractEvidenceSnapshot,
    ContractLifecycleTransition,
    ContractRankingDecision,
    ContractTransitionState,
    DOIEvaluationPoint,
    DOILifecycleEvent,
    DOIThesisConditionState,
    DynamicLifecyclePolicy,
    MaterialChangeDecision,
    choose_preferred_contract,
    classify_contract_transition,
    detect_material_change,
    evaluate_thesis_condition,
)
from .dynamic_options_lifecycle import (
    DOI_DYNAMIC_LIFECYCLE_SERVICE_VERSION,
    DynamicLifecycleEvaluationResult,
    DynamicLifecycleSummary,
    DynamicOptionsLifecycleService,
)
from domain.dynamic_options_outcomes import (
    DOI_OUTCOME_CALCULATION_VERSION,
    DOI_OUTCOME_DOMAIN_VERSION,
    DOI_OUTCOME_KIND,
    ChronologicalOutcomeCohorts,
    DOIOutcomeLabel,
    OptionPathObservation,
    OutcomeDataStatus,
    OutcomeLabelPolicy,
    OutcomeLeakageError,
    UnderlyingPathObservation,
    chronological_outcome_cohorts,
    evaluate_assessment_outcome,
)
from .dynamic_options_outcomes import (
    DEFAULT_DOI_OUTCOME_HORIZONS,
    DOI_OUTCOME_CAPTURE_SERVICE_VERSION,
    DynamicOptionsOutcomeCaptureService,
    OutcomeCaptureResult,
    OutcomeCaptureSummary,
    option_path_from_observations,
)
from domain.dynamic_options_probability import (
    DOI_PROBABILITY_DOMAIN_VERSION,
    DOI_PROBABILITY_FEATURE_VERSION,
    DOI_PROBABILITY_POLICY_VERSION,
    ProbabilityAcceptancePolicy,
    ProbabilityFeatureVector,
    ProbabilityInference,
    ProbabilityMetrics,
    ProbabilityModelArtifact,
    ProbabilityModelStatus,
    ProbabilityTarget,
    ProbabilityTrainingExample,
    probability_inference_identity,
    probability_model_identity,
    probability_model_version,
)
from domain.dynamic_options_ranking import (
    DOI_RANKING_DOMAIN_VERSION,
    DOI_RANKING_POLICY_VERSION,
    ContractRankingPolicy,
    FamilyRankingResult,
    RankedContract,
    RankingCandidateEvidence,
    RankingMode,
    RankingPolicyMetrics,
    RankingPolicyStatus,
    RankingReplayCase,
    RankingReplayPolicy,
    RankingWeights,
    family_ranking_identity,
    rank_contract_family,
    ranking_policy_identity,
    tune_ranking_policy,
)
from .stage_publisher import (
    StagePublication,
    publish_observation_worklist,
    publish_options_worklist,
)
from .storage import AtomicPayloadStore, StoredPayload
from .worklist_gate import (
    StageOutcomeReconciliation,
    filter_rows_to_worklist,
    reconcile_stage_outcomes,
)
from .decision_outcome_ledger import (
    DecisionOutcomeLedger,
    LedgerEvent,
    candidate_events_from_rows,
    execution_events_from_rows,
    make_ledger_event,
    outcome_event_from_candidate,
    outcome_event_from_trade,
)
from .outcome_maturation import (
    DEFAULT_OUTCOME_HORIZONS,
    OutcomeMaturationSummary,
    mature_candidate_outcomes,
)
from .gamma_exposure_store import (
    CanonicalGammaExposureStore,
    PhantomOptionChainRepository,
)
from .projection_outbox import (
    PROJECTION_OUTBOX_SCHEMA_VERSION,
    ProjectionDeliveryState,
    ProjectionOutbox,
)
from .phantom_option_projection import (
    PHANTOM_PROJECTION_SCHEMA_VERSION,
    PhantomOptionChainProjector,
    PhantomProjectionResult,
    deliver_phantom_option_events,
)

__all__ = [
    "AtomicPayloadStore",
    "AuthorisationDecision",
    "CanonicalDataGateway",
    "CanonicalDailyHistoryAdapter",
    "CanonicalFeatureFlags",
    "CanonicalRegistry",
    "CompletenessStatus",
    "DataScope",
    "DatasetRecord",
    "DatasetRequest",
    "DatasetResolution",
    "DatasetType",
    "DiscoveryPublication",
    "DropClass",
    "HistoricalPriceDatabase",
    "LifecycleManager",
    "LifecycleState",
    "EnsureHistoryResult",
    "MissingDateRange",
    "RequestLedger",
    "RequestResolution",
    "CHAIN_SCHEMA_VERSION",
    "CanonicalOptionChainService",
    "OptionChainResult",
    "OptionLiquidityLifecycleStore",
    "ContractLiquidityState",
    "DOI_OUTCOME_SCHEMA_VERSION",
    "MonitorState",
    "ThesisState",
    "DOI_DOMAIN_VERSION",
    "ContractAssessment",
    "ContractEntryState",
    "ContractFamily",
    "ModelApplicabilityState",
    "ObservationAcquisitionDecision",
    "OpportunityAcquisitionState",
    "OptionObservationKind",
    "PreferredContractDecision",
    "UnderlyingThesisRef",
    "decide_observation_acquisition",
    "DOI_ACTIVITY_FEATURE_VERSION",
    "DOI_OBSERVATION_BRIDGE_VERSION",
    "DOI_PCR_FEATURE_VERSION",
    "DOI_PHANTOM_PROJECTION_VERSION",
    "CanonicalDOIObservationBridge",
    "ContractActivityFeatures",
    "DOIObservationBundle",
    "GovernedOptionObservation",
    "PhantomDOIProjectionRepository",
    "PhantomHistoricalProjection",
    "PutCallContextFeatures",
    "extract_contract_activity",
    "extract_put_call_context",
    "DOI_FAMILY_POLICY_VERSION",
    "DOI_FAMILY_GENERATOR_VERSION",
    "ContractFamilyGenerationSummary",
    "FamilyCandidateAudit",
    "FamilyCandidateState",
    "GeneratedContractFamily",
    "StructuralExclusionReason",
    "ThesisConditionedContractFamilyGenerator",
    "DOI_SCENARIO_ENGINE_VERSION",
    "DOI_SCENARIO_UTILITY_VERSION",
    "DOI_VALUATION_MODEL_VERSION",
    "DOI_DETERMINISTIC_FEATURE_VERSION",
    "DOI_DETERMINISTIC_VALUATION_SERVICE_VERSION",
    "DeterministicContractValuation",
    "IVStress",
    "ScenarioPath",
    "ScenarioPoint",
    "ScenarioTiming",
    "ScenarioValuation",
    "dividend_adjusted_black_scholes",
    "evaluate_deterministic_scenarios",
    "ContractFamilyValuationResult",
    "ContractFamilyValuationSummary",
    "ContractValuationResult",
    "DeterministicContractValuationService",
    "build_xnys_scenario_points",
    "DOI_HYSTERESIS_POLICY_VERSION",
    "DOI_LIFECYCLE_DOMAIN_VERSION",
    "DOI_MATERIAL_CHANGE_POLICY_VERSION",
    "DOI_DYNAMIC_LIFECYCLE_SERVICE_VERSION",
    "ContractEvidenceSnapshot",
    "ContractLifecycleTransition",
    "ContractRankingDecision",
    "ContractTransitionState",
    "DOIEvaluationPoint",
    "DOILifecycleEvent",
    "DOIThesisConditionState",
    "DynamicLifecyclePolicy",
    "MaterialChangeDecision",
    "choose_preferred_contract",
    "classify_contract_transition",
    "detect_material_change",
    "evaluate_thesis_condition",
    "DynamicLifecycleEvaluationResult",
    "DynamicLifecycleSummary",
    "DynamicOptionsLifecycleService",
    "DOI_OUTCOME_CALCULATION_VERSION",
    "DOI_OUTCOME_DOMAIN_VERSION",
    "DOI_OUTCOME_KIND",
    "DEFAULT_DOI_OUTCOME_HORIZONS",
    "DOI_OUTCOME_CAPTURE_SERVICE_VERSION",
    "ChronologicalOutcomeCohorts",
    "DOIOutcomeLabel",
    "OptionPathObservation",
    "OutcomeDataStatus",
    "OutcomeLabelPolicy",
    "OutcomeLeakageError",
    "UnderlyingPathObservation",
    "chronological_outcome_cohorts",
    "evaluate_assessment_outcome",
    "DynamicOptionsOutcomeCaptureService",
    "OutcomeCaptureResult",
    "OutcomeCaptureSummary",
    "option_path_from_observations",
    "DOI_PROBABILITY_DOMAIN_VERSION",
    "DOI_PROBABILITY_FEATURE_VERSION",
    "DOI_PROBABILITY_POLICY_VERSION",
    "DOI_PROBABILITY_SCHEMA_VERSION",
    "DOI_PROBABILITY_SERVICE_VERSION",
    "ProbabilityAcceptancePolicy",
    "ProbabilityFeatureVector",
    "ProbabilityInference",
    "ProbabilityMetrics",
    "ProbabilityModelArtifact",
    "ProbabilityModelStatus",
    "ProbabilityTarget",
    "ProbabilityTrainingExample",
    "ChronologicalModelCohorts",
    "DynamicOptionsProbabilityRepository",
    "DynamicOptionsProbabilityService",
    "build_probability_feature_vector",
    "chronological_model_cohorts",
    "infer_probability",
    "outcome_target_value",
    "probability_inference_identity",
    "probability_model_identity",
    "probability_model_version",
    "train_probability_model",
    "DOI_RANKING_DOMAIN_VERSION",
    "DOI_RANKING_POLICY_VERSION",
    "DOI_RANKING_SCHEMA_VERSION",
    "DOI_RANKING_SERVICE_VERSION",
    "ContractRankingPolicy",
    "DynamicOptionsContractRankingService",
    "DynamicOptionsRankingRepository",
    "FamilyRankingResult",
    "RankedContract",
    "RankingCandidateEvidence",
    "RankingMode",
    "RankingPolicyMetrics",
    "RankingPolicyStatus",
    "RankingReplayCase",
    "RankingReplayPolicy",
    "RankingServiceResult",
    "RankingWeights",
    "family_ranking_identity",
    "rank_contract_family",
    "ranking_policy_identity",
    "tune_ranking_policy",
    "resolve_completed_session_date",
    "StagePublication",
    "publish_observation_worklist",
    "publish_options_worklist",
    "ResolutionKind",
    "StoredPayload",
    "TickerLifecycleEvent",
    "WorklistReconciliation",
    "DEFAULT_ADJUSTMENT",
    "PriceCoverage",
    "PriceIngestResult",
    "normalise_daily_ohlcv",
    "boundary_missing_ranges",
    "DEFAULT_HISTORY_MAX_STALENESS_DAYS",
    "canonical_history_is_fresh",
    "history_date_is_fresh",
    "history_staleness_days",
    "observe_shadow_history",
    "read_canonical_history",
    "write_through_fetched_history",
    "StageOutcomeReconciliation",
    "filter_rows_to_worklist",
    "reconcile_stage_outcomes",
    "publish_discovery_csv",
    "publish_discovery_outcomes",
    "read_discovery_outcomes",
    "CanonicalGammaExposureStore",
    "PhantomOptionChainRepository",
    "PROJECTION_OUTBOX_SCHEMA_VERSION",
    "ProjectionDeliveryState",
    "ProjectionOutbox",
    "PHANTOM_PROJECTION_SCHEMA_VERSION",
    "PhantomOptionChainProjector",
    "PhantomProjectionResult",
    "deliver_phantom_option_events",
    "OptionIdentity", "build_occ_symbol", "normalise_occ_symbol", "parse_occ_symbol",
    "parse_exact_option_quote", "parse_marketdata_option_response",
    "CanonicalMarketObservationResolver", "ObservationResult", "OPTION_CHAIN_V2",
    "EXACT_OPTION_QUOTE_V2", "UNDERLYING_NBBO_QUOTE_V1", "normalise_underlying_nbbo",
    "CanonicalMinuteBarResolver", "IntradayBatchResult", "IntradayBarResult",
    "IntradayQuality", "IntradayRequestPlan", "INTRADAY_BAR_SCHEMA_VERSION",
    "assess_intraday_quality", "expected_intraday_timestamps", "intraday_schema_version",
    "missing_intraday_ranges", "normalise_intraday_bars", "normalise_minute_bars",
    "MARKETDATA_PROVIDER", "MarketDataCandleResponse", "MarketDataCandleNoData",
    "MarketDataCandleTransportError", "MarketDataStockCandleAdapter",
    "parse_marketdata_stock_candles",
    "FreshnessState", "SessionSnapshot", "SessionState",
    "evaluate_freshness", "is_early_close", "is_xnys_session", "previous_xnys_session",
    "session_bounds", "session_snapshot",
    "DecisionOutcomeLedger", "LedgerEvent", "candidate_events_from_rows",
    "execution_events_from_rows", "make_ledger_event", "outcome_event_from_candidate",
    "outcome_event_from_trade",
    "DEFAULT_OUTCOME_HORIZONS", "OutcomeMaturationSummary",
    "mature_candidate_outcomes",
]


_LAZY_PROVIDER_EXPORTS = {
    "MARKETDATA_PROVIDER": (".marketdata_stock_candles", "MARKETDATA_PROVIDER"),
    "MarketDataCandleResponse": (
        ".marketdata_stock_candles", "MarketDataCandleResponse"
    ),
    "MarketDataCandleNoData": (
        ".marketdata_stock_candles", "MarketDataCandleNoData"
    ),
    "MarketDataCandleTransportError": (
        ".marketdata_stock_candles", "MarketDataCandleTransportError"
    ),
    "MarketDataStockCandleAdapter": (
        ".marketdata_stock_candles", "MarketDataStockCandleAdapter"
    ),
    "parse_marketdata_stock_candles": (
        ".marketdata_stock_candles", "parse_marketdata_stock_candles"
    ),
    "parse_exact_option_quote": (".marketdata_response", "parse_exact_option_quote"),
    "parse_marketdata_option_response": (
        ".marketdata_response", "parse_marketdata_option_response"
    ),
    "CanonicalMarketObservationResolver": (
        ".market_observation_resolver", "CanonicalMarketObservationResolver"
    ),
    "ObservationResult": (".market_observation_resolver", "ObservationResult"),
    "OPTION_CHAIN_V2": (".market_observation_resolver", "OPTION_CHAIN_V2"),
    "EXACT_OPTION_QUOTE_V2": (
        ".market_observation_resolver", "EXACT_OPTION_QUOTE_V2"
    ),
    "UNDERLYING_NBBO_QUOTE_V1": (
        ".market_observation_resolver", "UNDERLYING_NBBO_QUOTE_V1"
    ),
    "normalise_underlying_nbbo": (
        ".market_observation_resolver", "normalise_underlying_nbbo"
    ),
}

_LAZY_ANALYTICS_EXPORTS = {
    name: (".dynamic_options_probability", name)
    for name in (
        "DOI_PROBABILITY_SCHEMA_VERSION",
        "DOI_PROBABILITY_SERVICE_VERSION",
        "ChronologicalModelCohorts",
        "DynamicOptionsProbabilityRepository",
        "DynamicOptionsProbabilityService",
        "build_probability_feature_vector",
        "chronological_model_cohorts",
        "infer_probability",
        "outcome_target_value",
        "train_probability_model",
    )
}

_LAZY_ANALYTICS_EXPORTS.update({
    name: (".dynamic_options_ranking", name)
    for name in (
        "DOI_RANKING_SCHEMA_VERSION",
        "DOI_RANKING_SERVICE_VERSION",
        "DynamicOptionsContractRankingService",
        "DynamicOptionsRankingRepository",
        "RankingServiceResult",
    )
})


def __getattr__(name: str):
    """Load provider adapters only when a provider-owning stage requests one."""
    target = _LAZY_PROVIDER_EXPORTS.get(name) or _LAZY_ANALYTICS_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
