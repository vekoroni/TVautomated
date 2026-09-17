"""Read-only option quotes from the Phantom chain store (``chain_snapshots``)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

DEFAULT_CHAIN_DB = Path(__file__).resolve().parents[3] / "data" / "phantom" / "phantom_history.db"


class ChainQuotes:
    """Point lookups by primary key (ticker, quote_date, option_symbol); no nearest-date substitution."""

    def __init__(self, path: Path = DEFAULT_CHAIN_DB):
        self._connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        self._cache: dict[tuple[str, str], tuple[float | None, float | None] | None] = {}

    def quote(self, ticker: str, symbol: str, session: date) -> tuple[float | None, float | None] | None:
        key = (symbol, session.isoformat())
        if key not in self._cache:
            row = self._connection.execute(
                "SELECT bid, ask FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND option_symbol = ?",
                (ticker.upper(), key[1], symbol),
            ).fetchone()
            self._cache[key] = None if row is None else (row[0], row[1])
        return self._cache[key]

    def bid(self, ticker: str, symbol: str, session: date) -> float | None:
        quote = self.quote(ticker, symbol, session)
        return None if quote is None else quote[0]

    def ask(self, ticker: str, symbol: str, session: date) -> float | None:
        quote = self.quote(ticker, symbol, session)
        return None if quote is None else quote[1]

    def close(self) -> None:
        self._connection.close()
