"""Production stage-worklist publication helpers.

CDS-3 requires the worklist to be persisted before a stage can acquire data.
These helpers advance only the tickers presented by the immediately preceding
artifact and are idempotent for same-run restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from .contracts import DatasetType, iso_utc, utc_now
from .lifecycle import ACTIVE_STATES, DropClass, LifecycleState
from .registry import CanonicalRegistry


@dataclass(frozen=True, slots=True)
class StagePublication:
    run_id: str
    stage: str
    input_count: int
    authorised_count: int
    excluded_count: int
    reconciled: bool


def _normalise(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def publish_options_worklist(
    registry: CanonicalRegistry,
    *,
    run_id: str,
    input_tickers: Iterable[str],
    eligible_tickers: Iterable[str],
) -> StagePublication:
    """Advance the actual Options population and publish chain authority.

    Tickers excluded by Options scope remain equity-only. They are not terminal
    drops and may continue through non-option research lanes, but they cannot
    request an option chain for this run.
    """

    stage = "OPTIONS"
    inputs = _normalise(input_tickers)
    eligible = set(_normalise(eligible_tickers))
    if not eligible <= set(inputs):
        raise ValueError("Options worklist contains tickers absent from its input artifact")

    capabilities = (
        DatasetType.DAILY_OHLCV,
        DatasetType.OPTION_CHAIN,
        DatasetType.CONTRACT_REFERENCE,
    )
    # One transaction is important here: opening a SQLite connection for every
    # one of ~1,500 tickers added minutes to the pre-chain stage. The same legal
    # transition and immutable same-run worklist rules are enforced in bulk.
    with registry.connection() as connection:
        rows = connection.execute(
            """
            SELECT event.* FROM ticker_lifecycle AS event
            JOIN (
                SELECT ticker, MAX(version) AS version
                FROM ticker_lifecycle WHERE run_id = ? GROUP BY ticker
            ) AS latest
              ON latest.ticker = event.ticker AND latest.version = event.version
            WHERE event.run_id = ?
            """,
            (run_id, run_id),
        ).fetchall()
        latest_by_ticker = {row["ticker"]: row for row in rows}
        missing = set(inputs) - set(latest_by_ticker)
        if missing:
            raise ValueError(
                "Options inputs have no CDS lifecycle record: "
                + ",".join(sorted(missing)[:20])
            )

        now = iso_utc(utc_now())
        transition_rows = []
        for ticker in inputs:
            previous = latest_by_ticker[ticker]
            previous_state = LifecycleState(previous["state"])
            target = (
                LifecycleState.ACTIVE_OPTIONS
                if ticker in eligible
                else LifecycleState.ACTIVE_EQUITY_ONLY
            )
            target_capabilities = (
                capabilities if ticker in eligible else (DatasetType.DAILY_OHLCV,)
            )
            target_capability_json = json.dumps(
                sorted(item.value for item in target_capabilities)
            )
            if (
                previous["stage"] == stage
                and previous_state is target
                and previous["allowed_capabilities_json"] == target_capability_json
            ):
                continue
            if previous_state not in ACTIVE_STATES and previous_state is not LifecycleState.DROPPED_STAGE:
                raise ValueError(
                    f"{ticker} cannot enter Options from terminal state {previous_state.value}"
                )
            transition_rows.append(
                (
                    run_id,
                    ticker,
                    target.value,
                    DropClass.NONE.value,
                    stage,
                    (
                        "OPTIONS_SCOPE_ELIGIBLE"
                        if ticker in eligible
                        else "OPTIONS_SCOPE_EXCLUDED_EQUITY_ONLY"
                    ),
                    target_capability_json,
                    int(previous["version"]) + 1,
                    now,
                )
            )
        connection.executemany(
            """
            INSERT INTO ticker_lifecycle(
                run_id, ticker, state, drop_class, stage, reason_code,
                allowed_capabilities_json, version, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            transition_rows,
        )

        existing = {
            row["ticker"]
            for row in connection.execute(
                """
                SELECT ticker FROM stage_worklist
                WHERE run_id = ? AND stage = ? AND dataset_type = ?
                """,
                (run_id, stage, DatasetType.OPTION_CHAIN.value),
            ).fetchall()
        }
        if existing and existing != eligible:
            raise ValueError("same-run Options worklist changed during restart")
        connection.executemany(
            """
            INSERT OR IGNORE INTO stage_worklist(
                run_id, stage, ticker, dataset_type, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                (run_id, stage, ticker, DatasetType.OPTION_CHAIN.value, now)
                for ticker in sorted(eligible)
            ),
        )
        persisted_count = connection.execute(
            """
            SELECT COUNT(*) FROM stage_worklist
            WHERE run_id = ? AND stage = ? AND dataset_type = ?
            """,
            (run_id, stage, DatasetType.OPTION_CHAIN.value),
        ).fetchone()[0]
    reconciled = int(persisted_count) == len(eligible)
    return StagePublication(
        run_id=run_id,
        stage=stage,
        input_count=len(inputs),
        authorised_count=int(persisted_count),
        excluded_count=len(inputs) - len(eligible),
        reconciled=reconciled,
    )


def publish_observation_worklist(
    registry: CanonicalRegistry,
    *,
    run_id: str,
    stage: str,
    tickers: Iterable[str],
    dataset_types: Iterable[DatasetType],
    allow_monotonic_expansion: bool = False,
) -> StagePublication:
    """Publish a governed downstream observation worklist.

    Only tickers whose latest lifecycle state is still active are advanced.
    Terminal or stage-dropped tickers are excluded before any resolver can
    invoke its provider callback.  A same-run restart must reproduce the exact
    worklist for every requested dataset type unless the caller explicitly
    permits a one-way expansion from an earlier subset.  Expansion never
    permits removal or replacement of an already-authorised ticker.
    """

    stage_name = str(stage or "").strip().upper()
    inputs = _normalise(tickers)
    capabilities = tuple(sorted(set(dataset_types), key=lambda item: item.value))
    if not stage_name:
        raise ValueError("stage is required")
    if not capabilities:
        raise ValueError("at least one dataset type is required")

    with registry.connection() as connection:
        rows = connection.execute(
            """
            SELECT event.* FROM ticker_lifecycle AS event
            JOIN (
                SELECT ticker, MAX(version) AS version
                FROM ticker_lifecycle WHERE run_id = ? GROUP BY ticker
            ) AS latest
              ON latest.ticker = event.ticker AND latest.version = event.version
            WHERE event.run_id = ?
            """,
            (run_id, run_id),
        ).fetchall()
        latest_by_ticker = {row["ticker"]: row for row in rows}
        missing = set(inputs) - set(latest_by_ticker)
        if missing:
            raise ValueError(
                "Observation inputs have no CDS lifecycle record: "
                + ",".join(sorted(missing)[:20])
            )
        eligible = {
            ticker
            for ticker in inputs
            if LifecycleState(latest_by_ticker[ticker]["state"]) in ACTIVE_STATES
        }
        now = iso_utc(utc_now())
        capability_json = json.dumps(sorted(item.value for item in capabilities))
        transitions = []
        for ticker in sorted(eligible):
            previous = latest_by_ticker[ticker]
            if (
                previous["stage"] == stage_name
                and previous["allowed_capabilities_json"] == capability_json
            ):
                continue
            transitions.append(
                (
                    run_id,
                    ticker,
                    previous["state"],
                    DropClass.NONE.value,
                    stage_name,
                    f"{stage_name}_OBSERVATION_AUTHORISED",
                    capability_json,
                    int(previous["version"]) + 1,
                    now,
                )
            )
        connection.executemany(
            """
            INSERT INTO ticker_lifecycle(
                run_id, ticker, state, drop_class, stage, reason_code,
                allowed_capabilities_json, version, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            transitions,
        )

        for dataset_type in capabilities:
            existing = {
                row["ticker"]
                for row in connection.execute(
                    """
                    SELECT ticker FROM stage_worklist
                    WHERE run_id = ? AND stage = ? AND dataset_type = ?
                    """,
                    (run_id, stage_name, dataset_type.value),
                ).fetchall()
            }
            monotonic_expansion = bool(
                allow_monotonic_expansion
                and existing
                and existing < eligible
            )
            if existing and existing != eligible and not monotonic_expansion:
                raise ValueError(
                    f"same-run {stage_name}/{dataset_type.value} worklist changed during restart"
                )
            connection.executemany(
                """
                INSERT OR IGNORE INTO stage_worklist(
                    run_id, stage, ticker, dataset_type, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (run_id, stage_name, ticker, dataset_type.value, now)
                    for ticker in sorted(eligible)
                ),
            )
            count = connection.execute(
                """
                SELECT COUNT(*) FROM stage_worklist
                WHERE run_id = ? AND stage = ? AND dataset_type = ?
                """,
                (run_id, stage_name, dataset_type.value),
            ).fetchone()[0]
            if int(count) != len(eligible):
                raise ValueError(
                    f"{stage_name}/{dataset_type.value} worklist reconciliation failed"
                )

    return StagePublication(
        run_id=run_id,
        stage=stage_name,
        input_count=len(inputs),
        authorised_count=len(eligible),
        excluded_count=len(inputs) - len(eligible),
        reconciled=True,
    )
