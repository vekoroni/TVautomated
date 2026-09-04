"""CDS-3 stage reconciliation and join-boundary enforcement primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, TypeVar

from .errors import WorklistViolation


T = TypeVar("T", bound=Mapping[str, object])


def _ticker(value: object) -> str:
    return str(value or "").strip().upper()


def _unique(values: Iterable[object], *, label: str) -> tuple[str, ...]:
    raw = [_ticker(value) for value in values]
    if any(not value for value in raw):
        raise WorklistViolation(f"{label} contains a blank ticker")
    if len(raw) != len(set(raw)):
        raise WorklistViolation(f"{label} contains duplicate ticker outcomes")
    return tuple(sorted(raw))


@dataclass(frozen=True, slots=True)
class StageOutcomeReconciliation:
    input_tickers: tuple[str, ...]
    survivors: tuple[str, ...]
    drops: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def reconciled(self) -> bool:
        classified = set(self.survivors) | set(self.drops) | set(self.errors)
        return classified == set(self.input_tickers)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "input": len(self.input_tickers),
            "survivors": len(self.survivors),
            "drops": len(self.drops),
            "errors": len(self.errors),
        }


def reconcile_stage_outcomes(
    input_tickers: Iterable[object],
    *,
    survivors: Iterable[object],
    drops: Iterable[object],
    errors: Iterable[object],
) -> StageOutcomeReconciliation:
    """Enforce ``input = survivors + drops + errors`` with one outcome each."""
    inputs = _unique(input_tickers, label="input")
    survived = _unique(survivors, label="survivors")
    dropped = _unique(drops, label="drops")
    failed = _unique(errors, label="errors")
    input_set = set(inputs)
    groups = {
        "survivors": set(survived),
        "drops": set(dropped),
        "errors": set(failed),
    }
    overlaps = (
        (groups["survivors"] & groups["drops"])
        | (groups["survivors"] & groups["errors"])
        | (groups["drops"] & groups["errors"])
    )
    classified = set().union(*groups.values())
    missing = input_set - classified
    unexpected = classified - input_set
    if overlaps or missing or unexpected:
        raise WorklistViolation(
            "stage outcome reconciliation failed: "
            f"overlap={sorted(overlaps)} missing={sorted(missing)} "
            f"unexpected={sorted(unexpected)}"
        )
    return StageOutcomeReconciliation(inputs, survived, dropped, failed)


def filter_rows_to_worklist(
    rows: Iterable[T],
    authorised_tickers: Iterable[object],
    *,
    ticker_field: str = "ticker",
    reject_unexpected: bool = True,
) -> list[T]:
    """Filter a stage/join artifact and fail when it reintroduces a ticker."""
    allowed = {_ticker(value) for value in authorised_tickers if _ticker(value)}
    kept: list[T] = []
    unexpected: set[str] = set()
    for row in rows:
        ticker = _ticker(row.get(ticker_field))
        if ticker in allowed:
            kept.append(row)
        elif ticker:
            unexpected.add(ticker)
    if reject_unexpected and unexpected:
        raise WorklistViolation(
            "artifact contains tickers absent from authorised worklist: "
            + ",".join(sorted(unexpected))
        )
    return kept
