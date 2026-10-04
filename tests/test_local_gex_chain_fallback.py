"""Business rules for GEX chain resolution when the requested snapshot is absent.

A missing chain snapshot must never hard-fail the pipeline. The build rolls to
the nearest stored session (forward first, then backward) inside the governed
window, and otherwise publishes a labelled GEX_UNAVAILABLE sentinel.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.macro_file_contract import (
    GEX_MANIFEST_FILENAME,
    GEX_PROXY_FILENAME,
)
from macro_domain.gamma_exposure import GammaExposureConfig
from scripts.build_local_gex import build_local_gex


# XNYS sessions around the fixture: 2026-09-04 (Fri), 2026-09-07 Labor Day
# holiday, then 09-08, 09-09, 09-10, 09-11, 09-14, 09-15, 09-16.
STORED_SESSION = date(2026, 9, 4)
CONFIG = GammaExposureConfig(minimum_contracts=10)


def _chain(ticker: str, session: date) -> pd.DataFrame:
    rows = []
    for index, strike in enumerate(range(80, 121, 2)):
        for side in ("call", "put"):
            rows.append({
                "ticker": ticker,
                "quote_date": session.isoformat(),
                "option_symbol": f"{ticker}{index:03d}{side[0]}",
                "side": side,
                "strike": float(strike),
                "dte": 21.0,
                "open_interest": 100 + index,
                "underlying_price": 100.0,
                "gamma": 0.02 if side == "call" else 0.015,
                "iv": 0.25,
            })
    return pd.DataFrame(rows)


def _database(tmp_path: Path, sessions: tuple[date, ...], tickers=("SPY", "QQQ")) -> Path:
    database = tmp_path / "phantom.db"
    with sqlite3.connect(database) as connection:
        first = True
        for session in sessions:
            for ticker in tickers:
                _chain(ticker, session).to_sql(
                    "chain_snapshots",
                    connection,
                    index=False,
                    if_exists="replace" if first else "append",
                )
                first = False
    return database


def _build(tmp_path: Path, database: Path, session: date, **kwargs) -> dict:
    return build_local_gex(
        database_path=database,
        registry_path=tmp_path / "control.sqlite",
        canonical_root=tmp_path / "canonical_gex",
        output_dir=tmp_path / "market_data",
        session=session,
        config=CONFIG,
        **kwargs,
    )


def test_exact_session_is_used_without_a_roll(tmp_path: Path) -> None:
    database = _database(tmp_path, (STORED_SESSION,))
    manifest = _build(tmp_path, database, STORED_SESSION)
    assert manifest["status"] == "COMPLETE"
    assert manifest["session_date"] == "2026-09-04"
    assert manifest["requested_session_date"] == "2026-09-04"
    assert manifest["fallback_used"] is False
    assert manifest["fallback_direction"] == "EXACT"
    assert manifest["sessions_rolled"] == 0


def test_missing_chain_rolls_forward_to_the_nearest_stored_session(tmp_path: Path) -> None:
    """Layer 1 — the derived session is before the only stored chain."""

    database = _database(tmp_path, (STORED_SESSION,))
    manifest = _build(tmp_path, database, date(2026, 9, 2))
    assert manifest["status"] == "COMPLETE"
    # The label states the session actually measured, not the one requested.
    assert manifest["session_date"] == "2026-09-04"
    assert manifest["requested_session_date"] == "2026-09-02"
    assert manifest["fallback_used"] is True
    assert manifest["fallback_direction"] == "FORWARD"
    assert manifest["sessions_rolled"] == 2
    proxy = pd.read_csv(tmp_path / "market_data" / GEX_PROXY_FILENAME)
    assert set(proxy["Ticker"]) == {"SPY", "QQQ"}


def test_no_forward_chain_rolls_backward_to_the_nearest_stored_session(tmp_path: Path) -> None:
    """Layer 2 — nothing ahead, so the nearest earlier chain is used."""

    database = _database(tmp_path, (STORED_SESSION,))
    manifest = _build(tmp_path, database, date(2026, 9, 9))
    assert manifest["status"] == "COMPLETE"
    assert manifest["session_date"] == "2026-09-04"
    assert manifest["requested_session_date"] == "2026-09-09"
    assert manifest["fallback_used"] is True
    assert manifest["fallback_direction"] == "BACKWARD"
    assert manifest["sessions_rolled"] == 2


def test_forward_is_preferred_when_both_directions_have_a_chain(tmp_path: Path) -> None:
    database = _database(tmp_path, (STORED_SESSION, date(2026, 9, 10)))
    manifest = _build(tmp_path, database, date(2026, 9, 9))
    assert manifest["session_date"] == "2026-09-10"
    assert manifest["fallback_direction"] == "FORWARD"
    assert manifest["sessions_rolled"] == 1


def test_roll_requires_every_ticker_at_the_resolved_session(tmp_path: Path) -> None:
    """A session holding only SPY is not a usable chain for an SPY/QQQ build."""

    database = tmp_path / "phantom.db"
    with sqlite3.connect(database) as connection:
        _chain("SPY", date(2026, 9, 10)).to_sql("chain_snapshots", connection, index=False)
        for ticker in ("SPY", "QQQ"):
            _chain(ticker, STORED_SESSION).to_sql(
                "chain_snapshots", connection, index=False, if_exists="append"
            )
    manifest = _build(tmp_path, database, date(2026, 9, 9))
    assert manifest["session_date"] == "2026-09-04"
    assert manifest["fallback_direction"] == "BACKWARD"


def test_no_chain_in_either_direction_publishes_a_labelled_sentinel(tmp_path: Path) -> None:
    """Layer 3 — graceful degradation, never a block."""

    database = _database(tmp_path, (STORED_SESSION,))
    manifest = _build(tmp_path, database, date(2020, 1, 1))
    assert manifest["status"] == "GEX_UNAVAILABLE"
    assert manifest["reason"] == "no_chain_in_store"
    assert manifest["fallback"] is True
    assert manifest["fallback_used"] is True
    assert manifest["fallback_direction"] == "NONE"
    assert manifest["session"] == "2020-01-01"
    assert manifest["tickers"] == {}
    assert manifest["dataset_ids"] == []
    published = json.loads(
        (tmp_path / "market_data" / GEX_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert published["status"] == "GEX_UNAVAILABLE"


def test_sentinel_never_overwrites_a_prior_complete_proxy(tmp_path: Path) -> None:
    """Degradation must not destroy the last good evidence, only relabel status."""

    database = _database(tmp_path, (STORED_SESSION,))
    _build(tmp_path, database, STORED_SESSION)
    good = (tmp_path / "market_data" / GEX_PROXY_FILENAME).read_bytes()
    _build(tmp_path, database, date(2020, 1, 1))
    assert (tmp_path / "market_data" / GEX_PROXY_FILENAME).read_bytes() == good


def test_fallback_disabled_restores_the_hard_fail(tmp_path: Path) -> None:
    """Characterisation of the legacy behaviour, retained behind --no-fallback."""

    database = _database(tmp_path, (STORED_SESSION,))
    with pytest.raises(ValueError, match="chain unavailable for SPY/2026-09-02"):
        _build(tmp_path, database, date(2026, 9, 2), fallback=False)
