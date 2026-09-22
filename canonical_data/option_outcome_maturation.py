"""Bounded, provider-free capture of mature exact-contract DOI outcomes.

This module only reads canonical observations and appends hypothetical outcome
labels.  It is deliberately separate from candidate and execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from domain.dynamic_options_intelligence import ContractAssessment
from domain.dynamic_options_outcomes import (
    OptionPathObservation, OutcomeDataStatus, UnderlyingPathObservation,
)

from .dynamic_options_outcomes import (
    DynamicOptionsOutcomeCaptureService, OutcomeCaptureResult,
)
from .historical_prices import DEFAULT_ADJUSTMENT, HistoricalPriceDatabase
from .option_liquidity_lifecycle import OptionLiquidityLifecycleStore
from .phantom_outcome_source import PhantomOutcomeSourceReader


FINAL_STATUSES = frozenset({
    OutcomeDataStatus.COMPLETE,
    OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL,
    OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE,
})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("evaluation_cutoff_utc must be timezone-aware")
    return value.astimezone(timezone.utc)


def read_exact_contract_option_path(
    store: OptionLiquidityLifecycleStore,
    assessment: ContractAssessment,
    *,
    evaluation_cutoff_utc: datetime,
) -> tuple[OptionPathObservation, ...]:
    """Read only the same OCC contract from registered later sessions.

    Dataset session date, not the UTC calendar date of an after-hours quote,
    determines the market session.  Both quote and provider availability must
    respect the evaluation cutoff.
    """

    cutoff = _utc(evaluation_cutoff_utc)
    origin = assessment.evidence_cutoff_utc.astimezone(timezone.utc)
    origin_observation = store.contract_observation(assessment.observation_id)
    if origin_observation is None:
        raise ValueError("origin contract observation is unavailable")
    origin_dataset = store.registry.get_dataset(origin_observation.source_dataset_id)
    if origin_dataset is None:
        raise ValueError("origin canonical dataset is unavailable")
    with store.registry.connection() as connection:
        rows = connection.execute(
            """
            SELECT o.*, d.session_date AS source_session_date
            FROM option_contract_observations AS o
            JOIN dataset_registry AS d ON d.dataset_id = o.source_dataset_id
            WHERE o.contract_symbol = ? AND o.ticker = (
                SELECT ticker FROM doi_contract_families WHERE family_id = ?
            )
            ORDER BY o.quote_as_of, o.observed_at, o.observation_id
            """,
            (assessment.contract_symbol, assessment.family_id),
        ).fetchall()
    result: list[OptionPathObservation] = []
    for row in rows:
        session = date.fromisoformat(row["source_session_date"])
        quote = datetime.fromisoformat(row["quote_as_of"].replace("Z", "+00:00"))
        available = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        if session <= origin_dataset.session_date or quote <= origin:
            continue
        if quote > cutoff or available > cutoff:
            continue
        result.append(OptionPathObservation(
            observation_id=row["observation_id"],
            dataset_id=row["source_dataset_id"],
            contract_symbol=row["contract_symbol"],
            session_date=session,
            quote_at_utc=quote,
            available_at_utc=available,
            bid=row["bid"], ask=row["ask"],
            volume=row["volume"], open_interest=row["open_interest"],
            implied_volatility=row["iv"],
        ))
    return tuple(result)


def read_completed_underlying_path(
    prices: HistoricalPriceDatabase,
    assessment: ContractAssessment,
    *,
    evaluation_cutoff_utc: datetime,
    max_sessions: int = 20,
    ticker: str | None = None,
    reference_session_date: date | None = None,
) -> tuple[UnderlyingPathObservation, ...]:
    """Read completed OHLC rows with their actual canonical availability time."""

    cutoff = _utc(evaluation_cutoff_utc)
    if max_sessions <= 0:
        raise ValueError("max_sessions must be positive")
    symbol = ticker
    if not symbol:
        # The thesis, not the OCC root, is the underlying identity.
        raise ValueError("governed thesis ticker is required")
    with prices.connection() as connection:
        rows = connection.execute(
            """
            SELECT trading_date, high, low, close, observed_at,
                   row_hash, current_batch_id
            FROM ohlcv_daily
            WHERE ticker = ? AND trading_date > ? AND bar_status = 'COMPLETE'
              AND adjustment_convention = ?
            ORDER BY trading_date
            LIMIT ?
            """,
            (symbol.upper(),
             (reference_session_date or assessment.evidence_cutoff_utc.date()).isoformat(),
             DEFAULT_ADJUSTMENT,
             max_sessions + 20),
        ).fetchall()
    result: list[UnderlyingPathObservation] = []
    for row in rows:
        available = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        if available > cutoff:
            continue
        result.append(UnderlyingPathObservation(
            dataset_id=f"CDS_PRICE:{row['current_batch_id']}:{row['row_hash']}",
            session_date=date.fromisoformat(row["trading_date"]),
            available_at_utc=available,
            high=row["high"], low=row["low"], close=row["close"],
        ))
        if len(result) == max_sessions:
            break
    return tuple(result)


def capture_matured_family(
    store: OptionLiquidityLifecycleStore,
    prices: HistoricalPriceDatabase,
    *,
    family_id: str,
    evaluation_cutoff_utc: datetime,
    horizons: Iterable[int] = (1, 5, 10, 20),
    phantom_source_reader: PhantomOutcomeSourceReader | None = None,
) -> OutcomeCaptureResult | None:
    """Append only observable horizon labels; never create daily fake losses."""

    cutoff = _utc(evaluation_cutoff_utc)
    family = store.contract_family(family_id)
    if family is None:
        raise ValueError("DOI contract family does not exist")
    assessments = store.assessments_for_family(family_id)
    if not assessments:
        return None
    requested = tuple(sorted({int(value) for value in horizons}))
    if not requested or requested[0] <= 0:
        raise ValueError("horizons must be positive")
    origin = store.contract_observation(assessments[0].observation_id)
    if origin is None:
        raise ValueError("origin contract observation is unavailable")
    origin_dataset = store.registry.get_dataset(origin.source_dataset_id)
    if origin_dataset is None:
        raise ValueError("origin canonical dataset is unavailable")
    underlying = read_completed_underlying_path(
        prices, assessments[0], evaluation_cutoff_utc=cutoff,
        max_sessions=max(requested), ticker=family.thesis.ticker,
        reference_session_date=origin_dataset.session_date,
    )
    # Recheck mature horizons on later passes: a canonical quote can arrive
    # after an earlier partial or complete observation was recorded.
    due = [horizon for horizon in requested if len(underlying) >= horizon]
    if not due:
        return None
    def option_path_for(assessment: ContractAssessment) -> tuple[OptionPathObservation, ...]:
        registered = read_exact_contract_option_path(
            store, assessment, evaluation_cutoff_utc=cutoff,
        )
        if phantom_source_reader is None:
            return registered
        registered_sessions = {point.session_date for point in registered}
        missing_sessions = tuple(
            point.session_date for point in underlying[:max(due)]
            if point.session_date not in registered_sessions
        )
        if not missing_sessions:
            return registered
        supplemental = phantom_source_reader.read_sessions(
            ticker=family.thesis.ticker,
            contract_symbol=assessment.contract_symbol,
            sessions=missing_sessions,
            assessment_cutoff_utc=assessment.evidence_cutoff_utc,
            evaluation_cutoff_utc=cutoff,
        )
        for verified in supplemental:
            store.record_outcome_source_quote(verified)
        return tuple(sorted(
            (*registered, *(item.observation for item in supplemental)),
            key=lambda point: (point.session_date, point.quote_at_utc,
                               point.observation_id),
        ))
    result = DynamicOptionsOutcomeCaptureService(store).capture_family(
        family_id=family_id,
        evaluation_cutoff_utc=cutoff,
        read_option_path=option_path_for,
        read_underlying_path=lambda assessment: underlying,
        horizons=due,
    )
    return result if result.summary.labels_appended or result.summary.errors else None


@dataclass(frozen=True, slots=True)
class OptionOutcomeBatchSummary:
    families_scanned: int
    families_captured: int
    labels_appended: int
    labels_reused: int
    data_exceptions: int
    retained_prior_on_reader_error: int
    candidate_scan_limit: int
    capture_limit: int
    errors: tuple[str, ...]
    cursor_family_id: str | None
    scan_cycle: int
    coverage_assessments: int
    coverage_expected: int
    coverage_final: int
    coverage_pending: int
    coverage_raw_labels: int
    coverage_by_horizon: dict[int, dict[str, int]]
    population_reconciled: bool
    provider_calls: int = 0
    authority: str = "OBSERVATION_ONLY"
    can_grant_capital: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def capture_matured_option_batch(
    store: OptionLiquidityLifecycleStore,
    prices: HistoricalPriceDatabase,
    *,
    evaluation_cutoff_utc: datetime,
    current_run_id: str,
    candidate_scan_limit: int = 100,
    capture_limit: int = 10,
    horizons: Iterable[int] = (1, 5, 10, 20),
    phantom_source_reader: PhantomOutcomeSourceReader | None = None,
) -> OptionOutcomeBatchSummary:
    """Resume a bounded, cyclic scan from canonical control-plane state."""

    cutoff = _utc(evaluation_cutoff_utc)
    if candidate_scan_limit <= 0 or capture_limit <= 0:
        raise ValueError("batch limits must be positive")
    horizon_values = tuple(sorted({int(value) for value in horizons}))
    if not horizon_values or horizon_values[0] <= 0:
        raise ValueError("horizons must be positive")
    scheduler_key = "MON004:" + ",".join(map(str, horizon_values))
    with store.registry.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS doi_outcome_scan_cursor (
                scheduler_key TEXT PRIMARY KEY,
                evidence_cutoff_utc TEXT NOT NULL,
                family_id TEXT NOT NULL,
                cycle_upper_cutoff TEXT NOT NULL,
                cycle_upper_family TEXT NOT NULL,
                cycle INTEGER NOT NULL CHECK(cycle >= 0),
                updated_at_utc TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_doi_outcome_scan_family
            ON doi_contract_families(evidence_cutoff_utc,family_id)"""
        )
        cursor = connection.execute(
            """SELECT evidence_cutoff_utc,family_id,cycle_upper_cutoff,
                      cycle_upper_family,cycle
            FROM doi_outcome_scan_cursor WHERE scheduler_key = ?""",
            (scheduler_key,),
        ).fetchone()
        cursor_cutoff = cursor["evidence_cutoff_utc"] if cursor else ""
        cursor_family = cursor["family_id"] if cursor else ""
        cycle = int(cursor["cycle"]) if cursor else 0

        def upper_bound():
            return connection.execute(
                """SELECT f.evidence_cutoff_utc,f.family_id
                FROM doi_contract_families AS f
                WHERE f.run_id <> ? AND f.evidence_cutoff_utc < ?
                  AND EXISTS (SELECT 1 FROM doi_contract_assessments AS a
                              WHERE a.family_id = f.family_id)
                ORDER BY f.evidence_cutoff_utc DESC,f.family_id DESC LIMIT 1""",
                (current_run_id, cutoff.isoformat()),
            ).fetchone()

        bound = upper_bound() if not cursor else None
        upper_cutoff = cursor["cycle_upper_cutoff"] if cursor else (
            bound["evidence_cutoff_utc"] if bound else ""
        )
        upper_family = cursor["cycle_upper_family"] if cursor else (
            bound["family_id"] if bound else ""
        )

        def candidates(after_cutoff: str, after_family: str):
            return connection.execute(
            """
            SELECT f.family_id,f.evidence_cutoff_utc FROM doi_contract_families AS f
            WHERE f.run_id <> ? AND f.evidence_cutoff_utc < ?
              AND (f.evidence_cutoff_utc > ? OR
                   (f.evidence_cutoff_utc = ? AND f.family_id > ?))
              AND (f.evidence_cutoff_utc < ? OR
                   (f.evidence_cutoff_utc = ? AND f.family_id <= ?))
              AND EXISTS (
                  SELECT 1 FROM doi_contract_assessments AS a
                  WHERE a.family_id = f.family_id
              )
            ORDER BY f.evidence_cutoff_utc, f.family_id
            LIMIT ?
            """,
            (current_run_id, cutoff.isoformat(), after_cutoff,
             after_cutoff, after_family, upper_cutoff, upper_cutoff,
             upper_family, candidate_scan_limit),
            ).fetchall()

        candidate_rows = tuple(candidates(cursor_cutoff, cursor_family)) if bound or cursor else ()
        if not candidate_rows and cursor:
            cycle += 1
            bound = upper_bound()
            upper_cutoff = bound["evidence_cutoff_utc"] if bound else ""
            upper_family = bound["family_id"] if bound else ""
            candidate_rows = tuple(candidates("", "")) if bound else ()
    scanned = captured = appended = reused = exceptions = retained_prior = 0
    errors: list[str] = []
    for row in candidate_rows:
        family_id, family_cutoff = row["family_id"], row["evidence_cutoff_utc"]
        scanned += 1
        try:
            result = capture_matured_family(
                store, prices, family_id=family_id,
                evaluation_cutoff_utc=cutoff, horizons=horizon_values,
                phantom_source_reader=phantom_source_reader,
            )
            if result is not None:
                captured += 1
                appended += result.summary.labels_appended
                reused += result.summary.labels_reused
                exceptions += result.summary.data_exceptions
                retained_prior += result.summary.retained_prior_on_reader_error
                errors.extend(f"{family_id}:{error}" for error in result.summary.errors)
        except Exception as error:
            exceptions += 1
            errors.append(f"{family_id}:{type(error).__name__}:{error}")
        # Commit after each family. A crash before this write replays that
        # family idempotently; a failed family is revisited next scan cycle.
        with store.registry.connection() as connection:
            connection.execute(
                """INSERT INTO doi_outcome_scan_cursor(
                    scheduler_key,evidence_cutoff_utc,family_id,
                    cycle_upper_cutoff,cycle_upper_family,cycle,updated_at_utc
                ) VALUES (?,?,?,?,?,?,?) ON CONFLICT(scheduler_key) DO UPDATE SET
                    evidence_cutoff_utc=excluded.evidence_cutoff_utc,
                    family_id=excluded.family_id,
                    cycle_upper_cutoff=excluded.cycle_upper_cutoff,
                    cycle_upper_family=excluded.cycle_upper_family,
                    cycle=excluded.cycle,
                    updated_at_utc=excluded.updated_at_utc""",
                (scheduler_key, family_cutoff, family_id,
                 upper_cutoff, upper_family, cycle, cutoff.isoformat()),
            )
        cursor_family = family_id
        if captured >= capture_limit:
            break
    placeholders = ",".join("?" for _ in horizon_values)
    with store.registry.connection() as connection:
        assessments = int(connection.execute(
            "SELECT COUNT(*) FROM doi_contract_assessments"
        ).fetchone()[0])
        horizon_rows = connection.execute(
            f"""SELECT horizon_sessions,COUNT(*) FROM (
                SELECT assessment_id,horizon_sessions FROM doi_outcome_labels
                WHERE horizon_sessions IN ({placeholders}) AND data_status IN (
                    'COMPLETE','COMPLETE_OPTION_PATH_PARTIAL',
                    'COMPLETE_OPTION_RETURN_UNAVAILABLE'
                ) GROUP BY assessment_id,horizon_sessions
            ) GROUP BY horizon_sessions""",
            horizon_values,
        ).fetchall()
        raw_labels = int(connection.execute(
            "SELECT COUNT(*) FROM doi_outcome_labels"
        ).fetchone()[0])
    expected = assessments * len(horizon_values)
    final_by_horizon = {int(row[0]): int(row[1]) for row in horizon_rows}
    coverage_by_horizon = {
        horizon: {
            "expected": assessments,
            "final": final_by_horizon.get(horizon, 0),
            "pending": assessments - final_by_horizon.get(horizon, 0),
        }
        for horizon in horizon_values
    }
    final = sum(values["final"] for values in coverage_by_horizon.values())
    pending = expected - final
    return OptionOutcomeBatchSummary(
        families_scanned=scanned, families_captured=captured,
        labels_appended=appended, labels_reused=reused,
        data_exceptions=exceptions,
        retained_prior_on_reader_error=retained_prior,
        candidate_scan_limit=candidate_scan_limit,
        capture_limit=capture_limit, errors=tuple(errors),
        cursor_family_id=cursor_family or None, scan_cycle=cycle,
        coverage_assessments=assessments, coverage_expected=expected,
        coverage_final=final, coverage_pending=pending,
        coverage_raw_labels=raw_labels,
        coverage_by_horizon=coverage_by_horizon,
        population_reconciled=(0 <= final <= expected and final + pending == expected),
    )


__all__ = [
    "OptionOutcomeBatchSummary", "capture_matured_family",
    "capture_matured_option_batch", "read_completed_underlying_path",
    "read_exact_contract_option_path",
]
