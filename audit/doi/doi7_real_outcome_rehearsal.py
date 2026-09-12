"""DOI-7 rehearsal using frozen canonical A chains in a disposable store."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import sys
import tempfile

import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from canonical_data.dynamic_options_bridge import GovernedOptionObservation
from canonical_data.dynamic_options_family import ThesisConditionedContractFamilyGenerator
from canonical_data.dynamic_options_outcomes import DynamicOptionsOutcomeCaptureService
from canonical_data.dynamic_options_valuation import DeterministicContractValuationService
from canonical_data.historical_prices import HistoricalPriceDatabase
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState, MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ObservationAcquisitionDecision, OptionObservationKind, UnderlyingThesisRef,
)
from domain.dynamic_options_outcomes import OptionPathObservation, UnderlyingPathObservation


SOURCE_CONTROL_PLANE = REPOSITORY_ROOT / "data/canonical/control_plane.sqlite"
SOURCE_HISTORY = REPOSITORY_ROOT / "data/canonical/historical_prices.sqlite"
ORIGIN_DATASET_ID = "936877a39f705fdcbde51fdf67a6fd9c00e52dab8fa161f1831005867c4a1ef2"
FUTURE_DATASET_IDS = (
    "a75ca40958c8d6a56b7e176bf147b523cd9bdaca35b1725cffe46a37ad2bf07f",
    "778fe0d37a39194098d0039a0aab3deae7f3a9a5e1a8b41a3b0b5ad18a50b05e",
)
REHEARSAL_RUN_ID = "20260910_090000"
UTC = timezone.utc


def _frame(dataset) -> pd.DataFrame:
    path = Path(dataset.storage_uri)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))


def _number(value):
    try:
        result = float(value)
        return result if pd.notna(result) else None
    except (TypeError, ValueError):
        return None


def _value(row, *names):
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return None


def _symbol_column(frame: pd.DataFrame) -> str:
    for name in ("symbol", "option_symbol", "contract_symbol"):
        if name in frame.columns:
            return name
    raise RuntimeError("frozen option chain has no symbol column")


def _quote_state(bid, ask) -> ContractLiquidityState:
    if bid is not None and ask is not None and bid > 0 and ask >= bid:
        return ContractLiquidityState.REVIEWABLE_SPREAD
    if bid == 0 and ask is not None:
        return ContractLiquidityState.ZERO_BID
    return ContractLiquidityState.NO_CURRENT_MARKET


def main() -> None:
    source = CanonicalRegistry(SOURCE_CONTROL_PLANE)
    origin_dataset = source.get_dataset(ORIGIN_DATASET_ID)
    future_datasets = [source.get_dataset(item) for item in FUTURE_DATASET_IDS]
    if origin_dataset is None or any(item is None for item in future_datasets):
        raise RuntimeError("frozen DOI-7 canonical datasets are unavailable")
    origin_frame = _frame(origin_dataset)
    future_frames = [(dataset, _frame(dataset)) for dataset in future_datasets]
    origin_spot = _number(_value(origin_frame.iloc[0], "underlying_price", "spot"))
    if origin_spot is None:
        raise RuntimeError("origin chain has no underlying spot")

    with tempfile.TemporaryDirectory(prefix="doi7-real-rehearsal-") as temporary:
        registry = CanonicalRegistry(Path(temporary) / "control_plane.sqlite")
        registry.initialise()
        registry.register_run(REHEARSAL_RUN_ID, "REHEARSAL", origin_dataset.session_date)
        registry.register_dataset(origin_dataset)
        for dataset, _ in future_frames:
            registry.register_dataset(dataset)
        store = OptionLiquidityLifecycleStore(registry)
        store.initialise()
        thesis_id = "A-CALL-DOI7-REHEARSAL"
        target = origin_spot * 1.10
        invalidation = origin_spot * 0.95
        store.record_thesis_event(
            thesis_id=thesis_id, event_key="DOI7-ORIGIN", run_id=REHEARSAL_RUN_ID,
            ticker="A", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="FROZEN_REHEARSAL_THESIS",
            structural_target=target, invalidation_spot=invalidation,
            recorded_at=origin_dataset.as_of,
        )
        thesis = UnderlyingThesisRef(
            thesis_id=thesis_id, thesis_version=1, ticker="A",
            governed_direction="CALL", origin_spot=origin_spot,
            origin_timestamp_utc=origin_dataset.as_of, target_spot=target,
            invalidation_spot=invalidation, planned_hold_sessions=5,
            planned_hold_source="REHEARSAL_FIXED_5_SESSION",
            evidence_cutoff_utc=origin_dataset.as_of,
        )
        observation = GovernedOptionObservation(
            ticker="A", observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=origin_dataset.dataset_id, provider="MARKETDATA",
            as_of_utc=origin_dataset.as_of, frame=origin_frame,
            resolution="FROZEN_CANONICAL_REUSE",
            acquisition=ObservationAcquisitionDecision(False, "REUSE_CANONICAL_EVIDENCE"),
            physical_fetch_count=0,
        )
        generated = ThesisConditionedContractFamilyGenerator(store).generate(
            thesis=thesis, observation=observation, run_id=REHEARSAL_RUN_ID,
        )
        valuation = DeterministicContractValuationService(
            store, risk_free_rate=0.04, dividend_yield=0.01,
        ).evaluate_family(generated_family=generated, observation=observation)

        option_paths: dict[str, list[OptionPathObservation]] = {
            item.assessment.contract_symbol: [] for item in valuation.results
        }
        for dataset, frame in future_frames:
            symbols = _symbol_column(frame)
            indexed = {
                str(row[symbols]).strip().upper(): row
                for _, row in frame.iterrows()
            }
            for symbol in option_paths:
                row = indexed.get(symbol)
                if row is None:
                    continue
                bid = _number(_value(row, "bid"))
                ask = _number(_value(row, "ask"))
                quote_at = dataset.as_of.astimezone(UTC)
                persisted = store.record_contract_observation(
                    thesis_id=thesis_id, run_id=REHEARSAL_RUN_ID, ticker="A",
                    contract_symbol=symbol, option_side="CALL", quote_as_of=quote_at,
                    observed_at=quote_at, source_dataset_id=dataset.dataset_id,
                    spot=_number(_value(row, "underlying_price", "spot")) or origin_spot,
                    strike=_number(_value(row, "strike")) or 1.0,
                    expiration=date.fromisoformat(str(_value(row, "expiration_date", "expiration"))[:10]),
                    dte=max(0.0, float((date.fromisoformat(str(_value(row, "expiration_date", "expiration"))[:10]) - dataset.session_date).days)),
                    liquidity_state=_quote_state(bid, ask), bid=bid, ask=ask,
                    volume=_number(_value(row, "volume")),
                    open_interest=_number(_value(row, "open_interest", "openInterest")),
                    iv=_number(_value(row, "iv", "implied_vol", "implied_volatility")),
                ).record
                option_paths[symbol].append(OptionPathObservation(
                    observation_id=persisted.observation_id,
                    dataset_id=dataset.dataset_id, contract_symbol=symbol,
                    session_date=dataset.session_date, quote_at_utc=quote_at,
                    available_at_utc=quote_at, bid=bid, ask=ask,
                    volume=persisted.volume, open_interest=persisted.open_interest,
                    implied_volatility=persisted.iv,
                ))

        history = HistoricalPriceDatabase(SOURCE_HISTORY).read(
            "A", start_date=origin_dataset.session_date,
            end_date=max(dataset.session_date for dataset, _ in future_frames),
        )
        future_history = history.loc[history["date"].dt.date > origin_dataset.session_date]
        underlying_path = tuple(
            UnderlyingPathObservation(
                dataset_id=f"CDS_DAILY:A:{row.date.date().isoformat()}",
                session_date=row.date.date(),
                available_at_utc=datetime.combine(row.date.date(), time(22, 0), UTC),
                high=float(row.high), low=float(row.low), close=float(row.close),
            )
            for row in future_history.itertuples()
        )
        evaluation_cutoff = datetime.combine(
            max(dataset.session_date for dataset, _ in future_frames), time(23, 0), UTC
        )
        outcome = DynamicOptionsOutcomeCaptureService(store).capture_family(
            family_id=generated.family.family_id,
            evaluation_cutoff_utc=evaluation_cutoff,
            read_option_path=lambda assessment: option_paths[assessment.contract_symbol],
            read_underlying_path=lambda _: underlying_path,
            horizons=(1, 5),
        )
        complete_labels = [
            item for item in outcome.labels if item.data_status.value.startswith("COMPLETE")
        ]
        print(json.dumps({
            "ticker": "A",
            "origin_session": origin_dataset.session_date.isoformat(),
            "future_sessions": [dataset.session_date.isoformat() for dataset, _ in future_frames],
            "origin_dataset_id": origin_dataset.dataset_id,
            "future_dataset_ids": [dataset.dataset_id for dataset, _ in future_frames],
            "family_candidates": generated.summary.family_candidates,
            "assessments": len(valuation.results),
            "contracts_with_future_exact_observation": sum(bool(value) for value in option_paths.values()),
            "underlying_completed_sessions": len(underlying_path),
            "capture_summary": outcome.summary.to_dict(),
            "complete_labels": len(complete_labels),
            "deferred_labels": sum(item.data_status.value == "DEFERRED_NOT_YET_OBSERVABLE" for item in outcome.labels),
            "option_path_partial_labels": sum(item.data_status.value == "COMPLETE_OPTION_PATH_PARTIAL" for item in outcome.labels),
            "authority_violations": sum(
                item.decision_authority != "NONE" or item.can_grant_capital or item.can_close_position
                for item in outcome.labels
            ),
            "provider_fetch_count": 0,
            "production_database_modified": False,
            "executed_at_utc": datetime.now(UTC).isoformat(),
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
