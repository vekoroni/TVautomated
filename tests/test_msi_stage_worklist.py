from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from canonical_data import (
    CanonicalRegistry,
    DatasetType,
    LifecycleManager,
    LifecycleState,
    publish_observation_worklist,
)


def _active_options(registry: CanonicalRegistry, run_id: str, ticker: str) -> None:
    lifecycle = LifecycleManager(registry)
    event = lifecycle.register(
        run_id,
        ticker,
        allowed_capabilities=(DatasetType.OPTION_CHAIN,),
    )
    event = lifecycle.transition(
        run_id,
        ticker,
        LifecycleState.ACTIVE_CORE,
        stage="PACKAGES",
        reason_code="TEST",
        expected_version=event.version,
        allowed_capabilities=(DatasetType.OPTION_CHAIN,),
    )
    lifecycle.transition(
        run_id,
        ticker,
        LifecycleState.ACTIVE_OPTIONS,
        stage="OPTIONS",
        reason_code="TEST",
        expected_version=event.version,
        allowed_capabilities=(DatasetType.OPTION_CHAIN,),
    )


def test_morning_observation_worklist_advances_only_active_tickers(tmp_path: Path) -> None:
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    registry.register_run("R1", "MORNING", date(2026, 8, 30))
    _active_options(registry, "R1", "AAA")
    _active_options(registry, "R1", "DROP")
    lifecycle = LifecycleManager(registry)
    event = lifecycle.latest("R1", "DROP")
    lifecycle.transition(
        "R1",
        "DROP",
        LifecycleState.DROPPED_STAGE,
        stage="OPTIONS",
        reason_code="NO_LONGER_ELIGIBLE",
        expected_version=event.version,
    )

    result = publish_observation_worklist(
        registry,
        run_id="R1",
        stage="MORNING_GATE",
        tickers=("AAA", "DROP"),
        dataset_types=(DatasetType.EXACT_OPTION_QUOTE, DatasetType.UNDERLYING_NBBO),
    )

    assert result.authorised_count == 1
    assert result.excluded_count == 1
    assert lifecycle.stage_worklist_tickers(
        "R1", "MORNING_GATE", DatasetType.EXACT_OPTION_QUOTE
    ) == ("AAA",)
    assert lifecycle.stage_worklist_tickers(
        "R1", "MORNING_GATE", DatasetType.UNDERLYING_NBBO
    ) == ("AAA",)


def test_same_run_worklist_cannot_expand_silently(tmp_path: Path) -> None:
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    registry.register_run("R1", "MORNING", date(2026, 8, 30))
    _active_options(registry, "R1", "AAA")
    _active_options(registry, "R1", "BBB")
    publish_observation_worklist(
        registry,
        run_id="R1",
        stage="MORNING_GATE",
        tickers=("AAA",),
        dataset_types=(DatasetType.EXACT_OPTION_QUOTE,),
    )
    with pytest.raises(ValueError, match="worklist changed"):
        publish_observation_worklist(
            registry,
            run_id="R1",
            stage="MORNING_GATE",
            tickers=("AAA", "BBB"),
            dataset_types=(DatasetType.EXACT_OPTION_QUOTE,),
        )


def test_explicit_monotonic_expansion_preserves_existing_authority(tmp_path: Path) -> None:
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    registry.register_run("R1", "MORNING", date(2026, 8, 30))
    _active_options(registry, "R1", "AAA")
    _active_options(registry, "R1", "BBB")
    publish_observation_worklist(
        registry,
        run_id="R1",
        stage="MARKET_STRUCTURE",
        tickers=("AAA",),
        dataset_types=(DatasetType.INTRADAY_BAR,),
    )

    result = publish_observation_worklist(
        registry,
        run_id="R1",
        stage="MARKET_STRUCTURE",
        tickers=("AAA", "BBB"),
        dataset_types=(DatasetType.INTRADAY_BAR,),
        allow_monotonic_expansion=True,
    )

    assert result.reconciled is True
    assert result.authorised_count == 2
    lifecycle = LifecycleManager(registry)
    assert lifecycle.stage_worklist_tickers(
        "R1", "MARKET_STRUCTURE", DatasetType.INTRADAY_BAR
    ) == ("AAA", "BBB")


def test_monotonic_expansion_never_allows_replacement_or_shrink(tmp_path: Path) -> None:
    registry = CanonicalRegistry(tmp_path / "control.sqlite")
    registry.initialise()
    registry.register_run("R1", "MORNING", date(2026, 8, 30))
    _active_options(registry, "R1", "AAA")
    _active_options(registry, "R1", "BBB")
    publish_observation_worklist(
        registry,
        run_id="R1",
        stage="MARKET_STRUCTURE",
        tickers=("AAA",),
        dataset_types=(DatasetType.INTRADAY_BAR,),
    )

    with pytest.raises(ValueError, match="worklist changed"):
        publish_observation_worklist(
            registry,
            run_id="R1",
            stage="MARKET_STRUCTURE",
            tickers=("BBB",),
            dataset_types=(DatasetType.INTRADAY_BAR,),
            allow_monotonic_expansion=True,
        )
