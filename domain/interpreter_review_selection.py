"""Human-selected Interpreter review batch; no ticker-ranking authority.

This pure domain contract does not read files, call providers, or change the
underlying Lab verdict. Publication and evidence binding belong to later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


MAX_REVIEW_TICKERS = 5


class ReviewSelectionError(ValueError):
    """The requested Lab review batch has ambiguous or invalid identity."""


@dataclass(frozen=True)
class ReviewSelection:
    run_id: str
    ticker: str
    source_index: int
    source_action: str


def _ticker(value: object) -> str:
    if not isinstance(value, str):
        raise ReviewSelectionError("ticker must be text")
    ticker = value.strip().upper()
    if not ticker or any(char.isspace() for char in ticker):
        raise ReviewSelectionError("ticker is empty or contains whitespace")
    return ticker


def select_review_batch(
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    tickers: Sequence[str],
) -> tuple[ReviewSelection, ...]:
    """Resolve one to five explicit human choices against a single Lab run.

    The source action is carried through, including BLOCK. Selection means
    request a review, not promote the ticker to execution eligibility.
    """

    if not isinstance(run_id, str) or not run_id.strip():
        raise ReviewSelectionError("run_id is required")
    if isinstance(tickers, (str, bytes)) or not 1 <= len(tickers) <= MAX_REVIEW_TICKERS:
        raise ReviewSelectionError("select one to five distinct tickers")
    chosen = [_ticker(ticker) for ticker in tickers]
    if len(chosen) != len(set(chosen)):
        raise ReviewSelectionError("duplicate ticker in review selection")

    indexed: dict[str, tuple[int, Mapping[str, object]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ReviewSelectionError("Lab source row must be a mapping")
        raw_ticker = row.get("ticker")
        if raw_ticker is None or str(raw_ticker).strip() == "":
            continue
        ticker = _ticker(raw_ticker)
        if ticker not in chosen:
            continue
        if ticker in indexed:
            raise ReviewSelectionError(f"ambiguous duplicate Lab row for {ticker}")
        if row.get("run_id") != run_id:
            raise ReviewSelectionError(f"Lab row for {ticker} belongs to another run")
        indexed[ticker] = (index, row)

    missing = [ticker for ticker in chosen if ticker not in indexed]
    if missing:
        raise ReviewSelectionError(f"ticker absent from selected Lab run: {','.join(missing)}")
    return tuple(
        ReviewSelection(
            run_id=run_id,
            ticker=ticker,
            source_index=indexed[ticker][0],
            source_action=str(indexed[ticker][1].get("final_action") or "UNKNOWN"),
        )
        for ticker in chosen
    )
