"""
VANGUARD Integration - Orchestrator Adapter
Converts Master Orchestrator output into VanguardInput format

STABILITY PHASE — FAIL-CLOSED CONTRACT ENFORCEMENT
- Enforces Orchestrator → Vanguard contract gate before returning SchemaVanguardInput
- Blocks contaminated tickers, stale/missing regime snapshot, insufficient OHLCV history (EMA200 integrity), and corrupt data
- Writes deterministic JSONL audit log
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, List

import pandas as pd

# Prefer relative import inside the package for stability
from ..schemas.vanguard_contract import (
    VanguardInput as ContractVanguardInput,
    RegimeSnapshot,
    validate_vanguard_input,
    write_validation_log,
    CONTRACT_VERSION,
)

from ..schemas.input_schema import (
    VanguardInput as SchemaVanguardInput,
    CalendarData,
    OptionsData,
    TechnicalData,
    MicrostructureData,
    MacroData,
)


class OrchestratorAdapter:
    """
    Adapts Master Orchestrator output to VANGUARD input format.

    The Orchestrator provides:
    - OHLCV data
    - Options flow (UOA, GEX, IV)
    - Calendar data (earnings)
    - Technical indicators
    - Market context

    This adapter transforms that into SchemaVanguardInput, BUT ONLY AFTER
    passing the strict ContractVanguardInput validator (fail-closed).
    """

    def __init__(self, audit_log_path: str = r"AVSHUNTER-Intelligence\reports\vanguard_contract_audit.jsonl"):
        self.audit_log_path = audit_log_path

    def adapt(self, orchestrator_output: Dict[str, Any]) -> SchemaVanguardInput:
        """
        Main entry: Convert Orchestrator output to SchemaVanguardInput.

        Fail-closed requirements (hard gate):
        - orchestrator_output must include: ticker, current_price, technical_data.ohlcv
        - orchestrator_output must include: regime_snapshot (strict fields required by contract)
        """

        # Fail-closed: required top-level keys
        ticker = orchestrator_output["ticker"]
        current_price = orchestrator_output["current_price"]

        # Build each data package (per your existing schema)
        calendar = self._build_calendar_data(orchestrator_output.get("calendar_data", {}))
        options = self._build_options_data(orchestrator_output.get("options_data", {}))
        technical = self._build_technical_data(orchestrator_output.get("technical_data", {}))
        microstructure = self._build_microstructure_data(orchestrator_output.get("microstructure_data", {}))
        macro = self._build_macro_data(orchestrator_output.get("macro_data", {}))

        # Assess data quality (informational; does NOT override fail-closed contract gate)
        data_quality = self._assess_data_quality(calendar, options, technical, microstructure, macro)
        missing_fields = self._identify_missing_fields(orchestrator_output)

        # ------------------------------------------------------------------
        # FAIL-CLOSED CONTRACT GATE (the stability spine)
        # ------------------------------------------------------------------

        # Daily OHLCV source of truth for contract: TechnicalData.ohlcv
        daily_df = technical.ohlcv

        # Intraday optional: not provided by your current schema; keep explicit None
        intraday_df = None

        # Fail-closed: regime snapshot MUST exist and MUST include required fields
        # Canonical key for stability: orchestrator_output["regime_snapshot"]
        regime_dict = orchestrator_output["regime_snapshot"]

        regime = RegimeSnapshot(
            as_of_utc=regime_dict["as_of_utc"],
            regime_state=regime_dict["regime_state"],
            dir_bias=regime_dict["dir_bias"],
            vol_mode=regime_dict["vol_mode"],
            regime_drift_status=regime_dict["regime_drift_status"],
            macro_conviction=regime_dict["macro_conviction"],
        )

        metadata = orchestrator_output.get("metadata", {"source": "master_orchestrator"})

        contract_in = ContractVanguardInput(
            contract_version=CONTRACT_VERSION,
            ticker=ticker,
            daily_df=daily_df,
            intraday_df=intraday_df,
            regime=regime,
            metadata=metadata,
        )

        result = validate_vanguard_input(contract_in)

        # Deterministic audit log (append-only)
        write_validation_log(result, contract_in, self.audit_log_path)

        # Hard stop: invalid data cannot propagate
        result.raise_if_failed()

        # ------------------------------------------------------------------

        return SchemaVanguardInput(
            ticker=ticker,
            analysis_timestamp=datetime.now(),
            current_price=current_price,
            calendar=calendar,
            options=options,
            technical=technical,
            microstructure=microstructure,
            macro=macro,
            data_quality_score=data_quality,
            missing_data_fields=missing_fields,
            avshunter_signal=orchestrator_output.get("avshunter_signal", None),
        )

    def _build_calendar_data(self, calendar_dict: Dict[str, Any]) -> CalendarData:
        """Build CalendarData from Orchestrator calendar info."""
        earnings_date = None
        days_to_earnings = None

        if calendar_dict.get("next_earnings_date"):
            earnings_date = pd.to_datetime(calendar_dict["next_earnings_date"])
            days_to_earnings = (earnings_date - pd.Timestamp.now()).days

        return CalendarData(
            next_earnings_date=earnings_date,
            days_to_earnings=days_to_earnings,
            earnings_time=calendar_dict.get("earnings_time", None),
            events=calendar_dict.get("events", []),
            sector=calendar_dict.get("sector", None),
            sector_momentum=calendar_dict.get("sector_momentum", None),
        )

    def _build_options_data(self, options_dict: Dict[str, Any]) -> OptionsData:
        """Build OptionsData from Orchestrator options analysis."""
        uoa_df = pd.DataFrame(options_dict["uoa"]) if options_dict.get("uoa") else pd.DataFrame()
        gex_df = pd.DataFrame(options_dict["gex_by_strike"]) if options_dict.get("gex_by_strike") else pd.DataFrame()
        iv_term_df = pd.DataFrame(options_dict["iv_term_structure"]) if options_dict.get("iv_term_structure") else pd.DataFrame()
        smile_df = pd.DataFrame(options_dict["smile_proxy"]) if options_dict.get("smile_proxy") else pd.DataFrame()
        vanna_charm_df = pd.DataFrame(options_dict["vanna_charm"]) if options_dict.get("vanna_charm") else pd.DataFrame()

        return OptionsData(
            uoa=uoa_df,
            gex_by_strike=gex_df,
            iv_term_structure=iv_term_df,
            smile_proxy=smile_df,
            vanna_charm=vanna_charm_df,
            daily_dollar_volume=options_dict.get("daily_dollar_volume", 0.0),
            total_options_volume=options_dict.get("total_options_volume", 0),
        )

    def _build_technical_data(self, tech_dict: Dict[str, Any]) -> TechnicalData:
        """Build TechnicalData from Orchestrator technical analysis."""
        ohlcv_df = tech_dict["ohlcv"] if tech_dict.get("ohlcv") is not None else pd.DataFrame()

        volume_profile_df = pd.DataFrame(tech_dict["volume_profile"]) if tech_dict.get("volume_profile") else pd.DataFrame()

        support_levels = tech_dict.get("support_levels", [])
        resistance_levels = tech_dict.get("resistance_levels", [])
        atr_history = tech_dict.get("atr_history", [])
        bb_width_history = tech_dict.get("bb_width_history", [])

        return TechnicalData(
            ohlcv=ohlcv_df,
            vwap_15m=tech_dict.get("vwap_15m", 0.0),
            vwap_1h=tech_dict.get("vwap_1h", 0.0),
            vwap_4h=tech_dict.get("vwap_4h", 0.0),
            vwap_daily=tech_dict.get("vwap_daily", 0.0),
            ema9=tech_dict.get("ema9", 0.0),
            ema21=tech_dict.get("ema21", 0.0),
            ema50=tech_dict.get("ema50", 0.0),
            ema200=tech_dict.get("ema200", 0.0),
            atr_current=tech_dict.get("atr_current", 0.0),
            atr_history=atr_history,
            adx=tech_dict.get("adx", 0.0),
            rsi=tech_dict.get("rsi", 50.0),
            bb_upper=tech_dict.get("bb_upper", 0.0),
            bb_mid=tech_dict.get("bb_mid", 0.0),
            bb_lower=tech_dict.get("bb_lower", 0.0),
            bb_width=tech_dict.get("bb_width", 0.0),
            bb_width_history=bb_width_history,
            keltner_upper=tech_dict.get("keltner_upper", 0.0),
            keltner_mid=tech_dict.get("keltner_mid", 0.0),
            keltner_lower=tech_dict.get("keltner_lower", 0.0),
            volume_profile=volume_profile_df,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            failed_breakout_count=tech_dict.get("failed_breakout_count", 0),
            last_breakout_attempt_date=tech_dict.get("last_breakout_attempt_date", None),
            high_52w=tech_dict.get("high_52w", 0.0),
            low_52w=tech_dict.get("low_52w", 0.0),
            date_52w_high=tech_dict.get("date_52w_high", None),
            date_52w_low=tech_dict.get("date_52w_low", None),
            trend_length_days=tech_dict.get("trend_length_days", 0),
            wyckoff_phase=tech_dict.get("wyckoff_phase", None),
            wyckoff_events=tech_dict.get("wyckoff_events", []),
            intraday_position=tech_dict.get("intraday_position", "UNKNOWN"),
            volume_profile_context=tech_dict.get("volume_profile_context", "BALANCED"),
            control_dynamics=tech_dict.get("control_dynamics", "NEUTRAL"),
            intraday_support=tech_dict.get("intraday_support", 0.0),
            intraday_resistance=tech_dict.get("intraday_resistance", 0.0),
        )

    def _build_microstructure_data(self, micro_dict: Dict[str, Any]) -> MicrostructureData:
        """Build MicrostructureData from Orchestrator microstructure analysis."""
        tns_df = pd.DataFrame(micro_dict["time_and_sales"]) if micro_dict.get("time_and_sales") else pd.DataFrame()

        return MicrostructureData(
            noii=micro_dict.get("noii", {}),
            tns=micro_dict.get("tns_pattern", {}),
            dark_pool=micro_dict.get("dark_pool", None),
            blocks=micro_dict.get("blocks", None),
            time_and_sales=tns_df,
        )

    def _build_macro_data(self, macro_dict: Dict[str, Any]) -> MacroData:
        """Build MacroData from Orchestrator macro context."""
        vix_history = macro_dict.get("vix_history", [])

        return MacroData(
            vix=macro_dict.get("vix", 15.0),
            vix_history=vix_history,
            spy_price=macro_dict.get("spy_price", 0.0),
            spy_trend=macro_dict.get("spy_trend", "UNKNOWN"),
            sector_etf_price=macro_dict.get("sector_etf_price", 0.0),
            sector_relative_strength=macro_dict.get("sector_relative_strength", 0.0),
        )

    def _assess_data_quality(self, calendar, options, technical, microstructure, macro) -> float:
        """Assess overall data quality (0–1). Informational only."""
        quality = 1.0

        if len(technical.ohlcv) < 50:
            quality *= 0.7

        if technical.vwap_daily == 0.0:
            quality *= 0.9

        if len(options.uoa) == 0:
            quality *= 0.8

        if len(microstructure.time_and_sales) == 0:
            quality *= 0.9

        return float(quality)

    def _identify_missing_fields(self, orchestrator_output: Dict[str, Any]) -> List[str]:
        """Identify which critical fields are missing (informational)."""
        missing: List[str] = []

        if "calendar_data" not in orchestrator_output:
            missing.append("calendar_data")

        if "options_data" not in orchestrator_output:
            missing.append("options_data")

        if "technical_data" not in orchestrator_output:
            missing.append("technical_data")
        else:
            if "ohlcv" not in orchestrator_output["technical_data"]:
                missing.append("ohlcv")

        # Regime snapshot is a hard requirement for the contract gate
        if "regime_snapshot" not in orchestrator_output:
            missing.append("regime_snapshot")

        return missing
