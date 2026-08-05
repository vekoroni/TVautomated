"""
VANGUARD Schemas Package
All data structure definitions
"""

from .input_schema import (
    CalendarData,
    OptionsData,
    TechnicalData,
    MicrostructureData,
    MacroData,
    VanguardInput
)

from .auction_schema import (
    MarketProfile,
    VolumeQuality,
    TimeQuality,
    FlowBalance,
    ParticipantQuality,
    AcceptanceState,
    AggressionMetrics,
    EfficiencyMetrics,
    VolumeTrend,
    ControlState,
    MigrationState,
    AuctionVerdict
)

from .state_outcomes_schema import (
    StateVector,
    ActuarialOutcomes,
    ScenarioOutcomes
)

from .trade_schema import (
    EdgeAssessment,
    TradeScenario,
    TradePlan,
    VanguardSignal,
    DailyReport
)

__all__ = [
    # Input
    'CalendarData',
    'OptionsData',
    'TechnicalData',
    'MicrostructureData',
    'MacroData',
    'VanguardInput',
    
    # Auction
    'MarketProfile',
    'VolumeQuality',
    'TimeQuality',
    'FlowBalance',
    'ParticipantQuality',
    'AcceptanceState',
    'AggressionMetrics',
    'EfficiencyMetrics',
    'VolumeTrend',
    'ControlState',
    'MigrationState',
    'AuctionVerdict',
    
    # State & Outcomes
    'StateVector',
    'ActuarialOutcomes',
    'ScenarioOutcomes',
    
    # Trade
    'EdgeAssessment',
    'TradeScenario',
    'TradePlan',
    'VanguardSignal',
    'DailyReport'
]