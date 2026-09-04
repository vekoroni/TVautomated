"""Publish Discovery outcomes into the CDS lifecycle control plane."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from .contracts import DatasetType
from .errors import WorklistViolation
from .lifecycle import LifecycleManager, LifecycleState
from .registry import CanonicalRegistry
from .worklist_gate import reconcile_stage_outcomes


@dataclass(frozen=True, slots=True)
class DiscoveryPublication:
    run_id: str
    input_count: int
    survivor_count: int
    drop_count: int
    error_count: int
    package_worklist_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "input_count": self.input_count,
            "survivor_count": self.survivor_count,
            "drop_count": self.drop_count,
            "error_count": self.error_count,
            "package_worklist_count": self.package_worklist_count,
            "reconciled": self.input_count
            == self.survivor_count + self.drop_count + self.error_count,
        }


def _normalise_rows(rows: Iterable[Mapping[str, object]]) -> list[dict[str, str]]:
    normalised: list[dict[str, str]] = []
    for raw in rows:
        row = {str(key): str(value or "").strip() for key, value in raw.items()}
        row["ticker"] = row.get("ticker", "").upper()
        row["outcome"] = row.get("outcome", "").upper()
        row["lifecycle_state"] = row.get("lifecycle_state", "").upper()
        row["reason_code"] = row.get("reason_code", "").upper()
        if not row["ticker"]:
            raise WorklistViolation("Discovery lifecycle row contains a blank ticker")
        if row["outcome"] not in {"SURVIVE", "DROP", "ERROR"}:
            raise WorklistViolation(
                f"{row['ticker']} has invalid Discovery outcome {row['outcome']!r}"
            )
        normalised.append(row)
    return normalised


def read_discovery_outcomes(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return _normalise_rows(csv.DictReader(handle))


def publish_discovery_outcomes(
    registry: CanonicalRegistry,
    *,
    run_id: str,
    session_date: date,
    rows: Iterable[Mapping[str, object]],
) -> DiscoveryPublication:
    """Persist one Discovery outcome per input and the Packages survivor worklist.

    Publication is deliberately separate from enforcement.  CDS-3 production
    gating remains controlled by ``AVSHUNTER_STAGE_GATING_ENFORCED``.
    """
    outcomes = _normalise_rows(rows)
    tickers = [row["ticker"] for row in outcomes]
    survivors = [row["ticker"] for row in outcomes if row["outcome"] == "SURVIVE"]
    drops = [row["ticker"] for row in outcomes if row["outcome"] == "DROP"]
    errors = [row["ticker"] for row in outcomes if row["outcome"] == "ERROR"]
    reconciliation = reconcile_stage_outcomes(
        tickers, survivors=survivors, drops=drops, errors=errors
    )

    registry.initialise()
    registry.register_run(
        run_id,
        "EVENING",
        session_date,
        metadata={"cds_phase": "CDS-3", "source_stage": "DISCOVERY"},
    )
    lifecycle = LifecycleManager(registry)
    row_by_ticker = {row["ticker"]: row for row in outcomes}

    for ticker in reconciliation.input_tickers:
        row = row_by_ticker[ticker]
        outcome = row["outcome"]
        if outcome == "SURVIVE":
            target_state = LifecycleState.ACTIVE_CORE
            target_stage = "PACKAGES"
            reason = row["reason_code"] or "DISCOVERY_SURVIVOR"
            capabilities = (DatasetType.DAILY_OHLCV,)
        elif outcome == "ERROR":
            target_state = LifecycleState.DEFERRED_CURRENT_RUN
            target_stage = "DISCOVERY"
            reason = row["reason_code"] or "DISCOVERY_ERROR"
            capabilities = ()
        else:
            try:
                target_state = LifecycleState(row["lifecycle_state"])
            except ValueError as error:
                raise WorklistViolation(
                    f"{ticker} has invalid drop state {row['lifecycle_state']!r}"
                ) from error
            if target_state not in {
                LifecycleState.DROPPED_STAGE,
                LifecycleState.DROPPED_TERMINAL_DATA,
                LifecycleState.DROPPED_TERMINAL_LOGIC,
            }:
                raise WorklistViolation(
                    f"{ticker} DROP outcome cannot use {target_state.value}"
                )
            target_stage = "DISCOVERY"
            reason = row["reason_code"] or "DISCOVERY_DROP"
            capabilities = ()

        latest = lifecycle.latest(run_id, ticker)
        if latest is None:
            latest = lifecycle.register(
                run_id,
                ticker,
                stage="DISCOVERY",
                allowed_capabilities=(DatasetType.DAILY_OHLCV,),
            )
        elif (
            latest.state == target_state
            and latest.stage == target_stage
            and latest.reason_code == reason
        ):
            continue
        elif latest.state is not LifecycleState.ACTIVE_DISCOVERY:
            raise WorklistViolation(
                f"{ticker} Discovery republication conflicts with existing "
                f"{latest.state.value}/{latest.stage}/{latest.reason_code}"
            )

        lifecycle.transition(
            run_id,
            ticker,
            target_state,
            stage=target_stage,
            reason_code=reason,
            allowed_capabilities=capabilities,
            expected_version=latest.version,
        )

    package_worklist = lifecycle.create_worklist(
        run_id,
        "PACKAGES",
        DatasetType.DAILY_OHLCV,
        reconciliation.survivors,
    )
    worklist_reconciliation = lifecycle.reconcile_worklist(
        run_id,
        "PACKAGES",
        DatasetType.DAILY_OHLCV,
        reconciliation.survivors,
    )
    if not worklist_reconciliation.reconciled:
        raise WorklistViolation(
            "Packages worklist failed reconciliation: "
            f"missing={list(worklist_reconciliation.missing)} "
            f"unexpected={list(worklist_reconciliation.unexpected)}"
        )

    return DiscoveryPublication(
        run_id=run_id,
        input_count=reconciliation.counts["input"],
        survivor_count=reconciliation.counts["survivors"],
        drop_count=reconciliation.counts["drops"],
        error_count=reconciliation.counts["errors"],
        package_worklist_count=len(package_worklist),
    )


def publish_discovery_csv(
    registry_path: str | Path,
    outcome_path: str | Path,
    *,
    run_id: str,
    session_date: date,
) -> DiscoveryPublication:
    return publish_discovery_outcomes(
        CanonicalRegistry(registry_path),
        run_id=run_id,
        session_date=session_date,
        rows=read_discovery_outcomes(outcome_path),
    )
