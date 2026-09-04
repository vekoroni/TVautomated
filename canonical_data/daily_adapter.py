"""Incremental Polygon boundary-range adapter for canonical daily history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from .historical_prices import HistoricalPriceDatabase, PriceIngestResult


class DailyBarFetcher(Protocol):
    def fetch_daily_bars(
        self, ticker: str, from_date: str, to_date: str, adjusted: bool = True
    ) -> pd.DataFrame | None: ...


@dataclass(frozen=True, slots=True)
class MissingDateRange:
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class EnsureHistoryResult:
    ticker: str
    frame: pd.DataFrame
    missing_ranges: tuple[MissingDateRange, ...]
    physical_request_count: int
    ingest_results: tuple[PriceIngestResult, ...]


def boundary_missing_ranges(
    frame: pd.DataFrame, start_date: date, end_date: date
) -> tuple[MissingDateRange, ...]:
    """Find missing head/tail ranges without inventing exchange holidays."""
    if start_date > end_date:
        raise ValueError("start_date is after end_date")
    if frame.empty:
        return (MissingDateRange(start_date, end_date),)
    first = pd.Timestamp(frame["date"].min()).date()
    last = pd.Timestamp(frame["date"].max()).date()
    ranges: list[MissingDateRange] = []
    if first > start_date:
        head_end = first - timedelta(days=1)
        if start_date <= head_end:
            ranges.append(MissingDateRange(start_date, head_end))
    if last < end_date:
        tail_start = last + timedelta(days=1)
        if tail_start <= end_date:
            ranges.append(MissingDateRange(tail_start, end_date))
    return tuple(ranges)


class CanonicalDailyHistoryAdapter:
    def __init__(self, database: HistoricalPriceDatabase, fetcher: DailyBarFetcher):
        self.database = database
        self.fetcher = fetcher

    def ensure_range(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        *,
        allow_fetch: bool = False,
        source_run_id: str | None = None,
    ) -> EnsureHistoryResult:
        """Fetch only missing boundary ranges and immediately commit each result."""
        self.database.initialise()
        current = self.database.read(
            ticker, start_date=start_date, end_date=end_date
        )
        missing = boundary_missing_ranges(current, start_date, end_date)
        if not allow_fetch or not missing:
            return EnsureHistoryResult(ticker.upper(), current, missing, 0, ())

        ingests: list[PriceIngestResult] = []
        requests = 0
        for gap in missing:
            fetched = self.fetcher.fetch_daily_bars(
                ticker,
                gap.start_date.isoformat(),
                gap.end_date.isoformat(),
                adjusted=True,
            )
            requests += 1
            if fetched is None or fetched.empty:
                continue
            ingests.append(
                self.database.ingest(
                    ticker,
                    fetched,
                    provider="POLYGON",
                    source_kind="CANONICAL_MISSING_RANGE_FETCH",
                    source_run_id=source_run_id,
                )
            )
        resolved = self.database.read(
            ticker, start_date=start_date, end_date=end_date
        )
        remaining = boundary_missing_ranges(resolved, start_date, end_date)
        return EnsureHistoryResult(
            ticker.upper(), resolved, remaining, requests, tuple(ingests)
        )
