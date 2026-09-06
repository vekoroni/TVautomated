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
    MonitorState,
    OptionLiquidityLifecycleStore,
    ThesisState,
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
    "MonitorState",
    "ThesisState",
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


def __getattr__(name: str):
    """Load provider adapters only when a provider-owning stage requests one."""
    target = _LAZY_PROVIDER_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
