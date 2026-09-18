"""Application service for the normal completed-session GEX refresh."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
from typing import Callable, Mapping, Any

from canonical_data.benchmark_option_chain import CanonicalBenchmarkOptionChainStore, OPEN_RECORD_MARK
from canonical_data.marketdata_option_chain import MarketDataOptionChainAdapter
from canonical_data.macro_gex_overlay import (
    apply_completed_gex_overlay,
    invalidate_gex_overlay,
)
from canonical_data.phantom_option_projection import deliver_phantom_option_events
from canonical_data.projection_outbox import ProjectionOutbox
from scripts.build_local_gex import build_local_gex


def _assert_benchmark_projection_receipts(
    phantom_path: Path,
    *,
    dataset_ids: list[str],
    session_date: date,
) -> None:
    """Prove the exact benchmark chains reached Phantom before GEX is built."""

    with sqlite3.connect(phantom_path) as connection:
        rows = connection.execute(
            "SELECT dataset_id,ticker,session_date,rows_projected "
            "FROM canonical_projection_receipts WHERE dataset_id IN (?,?)",
            tuple(dataset_ids),
        ).fetchall()
    receipts = {
        str(dataset_id): (str(ticker), str(session), int(row_count))
        for dataset_id, ticker, session, row_count in rows
    }
    expected_session = session_date.isoformat()
    if set(receipts) != set(dataset_ids):
        missing = sorted(set(dataset_ids) - set(receipts))
        raise RuntimeError(
            "completed benchmark option chains were not projected to Phantom: "
            + ",".join(missing)
        )
    projected_tickers = set()
    for dataset_id in dataset_ids:
        ticker, observed_session, row_count = receipts[dataset_id]
        if observed_session != expected_session or row_count <= 0:
            raise RuntimeError(
                f"invalid Phantom projection receipt for {dataset_id}: "
                f"session={observed_session} rows={row_count}"
            )
        projected_tickers.add(ticker)
    if projected_tickers != {"SPY", "QQQ"}:
        raise RuntimeError(
            "completed benchmark projection population is not exactly SPY/QQQ"
        )


def refresh_completed_session_gex(
    *,
    repository_root: Path | str,
    run_id: str,
    session_date: date,
    fetch_chain: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Acquire SPY/QQQ, project them, derive GEX, and refresh macro advisory."""

    root = Path(repository_root)
    registry_path = root / "data" / "canonical" / "control_plane.sqlite"
    phantom_path = root / "data" / "phantom" / "phantom_history.db"
    macro_path = root / "dropbox" / "macro" / "macro_intelligence_latest.json"
    market_dir = root / "dropbox" / "market_data"
    chain_store = CanonicalBenchmarkOptionChainStore(
        registry_path=registry_path,
        payload_root=root / "data" / "canonical" / "market_observations",
        run_id=run_id,
    )
    adapter = None if fetch_chain else MarketDataOptionChainAdapter()
    dataset_ids: list[str] = []
    datasets_by_ticker: dict[str, str] = {}
    resolutions: dict[str, str] = {}
    try:
        for ticker in ("SPY", "QQQ"):
            callback = fetch_chain or (
                lambda name, _adapter=adapter: _adapter.fetch(
                    name,
                    session_date=session_date,
                    dte_max=60,
                    min_open_interest=0,
                )
            )
            result = chain_store.get(
                ticker=ticker,
                session_date=session_date,
                dte_max=60,
                fetch=callback,
            )
            if not result.dataset_id:
                raise RuntimeError(f"{ticker} completed option chain was not resolved")
            dataset_ids.append(result.dataset_id)
            datasets_by_ticker[ticker] = result.dataset_id
            resolutions[ticker] = result.resolution
        delivered = deliver_phantom_option_events(
            registry_path=registry_path,
            phantom_database_path=phantom_path,
            limit=100_000,
        )
        _assert_benchmark_projection_receipts(
            phantom_path,
            dataset_ids=dataset_ids,
            session_date=session_date,
        )
        manifest = build_local_gex(
            database_path=phantom_path,
            registry_path=registry_path,
            canonical_root=root / "data" / "canonical" / "gamma_exposure",
            output_dir=market_dir,
            session=session_date,
            run_id=f"{run_id}:completed-gex",
            source_option_dataset_ids=datasets_by_ticker,
        )
        overlay = apply_completed_gex_overlay(
            macro_path=macro_path,
            proxy_path=market_dir / "avshunter_gex_proxy.csv",
            manifest_path=market_dir / "avshunter_gex_run_manifest.json",
            required_session=session_date,
        )
        return {
            "contract_version": "completed-session-gex-refresh-v1",
            "status": "COMPLETE",
            "session_date": session_date.isoformat(),
            "dataset_ids": dataset_ids,
            "resolutions": resolutions,
            "projection_events_delivered": len(delivered),
            "gex_dataset_ids": list(manifest.get("dataset_ids") or ()),
            "macro_overlay": overlay,
            "projection_health": ProjectionOutbox(registry_path).health_summary(),
            "authority": "ADVISORY_ONLY",
        }
    except Exception as error:
        invalidate_gex_overlay(
            macro_path=macro_path,
            required_session=session_date,
            reason=f"{type(error).__name__}: {error}",
        )
        return {
            "contract_version": "completed-session-gex-refresh-v1",
            "status": "UNAVAILABLE",
            "session_date": session_date.isoformat(),
            "dataset_ids": dataset_ids,
            "resolutions": resolutions,
            "error": f"{type(error).__name__}: {error}",
            "authority": "ADVISORY_ONLY",
        }


def _contract_present(phantom_path: Path, ticker: str, session_date: date, symbol: str) -> bool:
    if not phantom_path.is_file():
        return False
    with sqlite3.connect(f"file:{phantom_path.as_posix()}?mode=ro", uri=True) as connection:
        try:
            row = connection.execute(
                "SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=? LIMIT 1",
                (ticker, session_date.isoformat(), symbol),
            ).fetchone()
        except sqlite3.OperationalError:          # store not initialised yet
            return False
    return row is not None


def _projected_dataset_ids(phantom_path: Path, dataset_ids: list[str], session_date: date) -> set[str]:
    if not dataset_ids or not phantom_path.is_file():
        return set()
    marks = ",".join("?" for _ in dataset_ids)
    with sqlite3.connect(phantom_path) as connection:
        rows = connection.execute(
            f"SELECT dataset_id, session_date, rows_projected FROM canonical_projection_receipts "
            f"WHERE dataset_id IN ({marks})",
            tuple(dataset_ids),
        ).fetchall()
    return {str(d) for d, s, n in rows if str(s) == session_date.isoformat() and int(n) > 0}


def capture_open_record_chains(
    *,
    repository_root: Path | str,
    run_id: str,
    session_date: date,
    records,
    max_requests: int,
    fetch_chain: Callable[[str, int], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Keep a daily mark for every open ticket until it exits (P0-4, ACK 18 Sep 2026).

    ``records``: ``signal_ledger.OpenRecord`` items. A ticker is fetched only when one of its open contracts has no
    row for ``session_date`` in the Phantom store (never re-fetched, never overwritten). The request window reaches
    the latest open expiry for the ticker. At most ``max_requests`` provider requests. Data capture only: no
    candidate, rank or decision is created or changed; failures are reported, never raised.
    """

    root = Path(repository_root)
    registry_path = root / "data" / "canonical" / "control_plane.sqlite"
    phantom_path = root / "data" / "phantom" / "phantom_history.db"
    needed: dict[str, int] = {}
    already: set[str] = set()
    for record in records:
        if _contract_present(phantom_path, record.ticker, session_date, record.contract_symbol):
            already.add(record.ticker)
            continue
        window = max(60, (record.expiry - session_date).days + 1)
        needed[record.ticker] = max(needed.get(record.ticker, 0), window)
    already -= set(needed)
    result: dict[str, Any] = {
        "contract_version": "open-record-chain-capture-v1",
        "session_date": session_date.isoformat(),
        "open_records": len(list(records)),
        "needed": sorted(needed),
        "already_present": sorted(already),
        "captured": [],
        "over_budget": [],
        "failed": {},
        "requests_used": 0,
        "dataset_ids": [],
        "authority": "DATA_CAPTURE_ONLY",
    }
    if not needed:
        result["status"] = "NOTHING_TO_CAPTURE"
        return result
    if fetch_chain is None:
        adapter = MarketDataOptionChainAdapter()
        fetch_chain = lambda name, dte_max: adapter.fetch(       # noqa: E731
            name, session_date=session_date, dte_max=dte_max, min_open_interest=0)
    store = CanonicalBenchmarkOptionChainStore(
        registry_path=registry_path,
        payload_root=root / "data" / "canonical" / "market_observations",
        run_id=run_id,
        purpose=OPEN_RECORD_MARK,
    )
    fetched_by_ticker: dict[str, str] = {}
    for ticker in sorted(needed):
        if result["requests_used"] >= max_requests:
            result["over_budget"].append(ticker)
            continue

        def counted(name: str, _window=needed[ticker]) -> Mapping[str, Any]:
            result["requests_used"] += 1
            return fetch_chain(name, _window)

        try:
            chain = store.get(ticker=ticker, session_date=session_date, dte_max=needed[ticker], fetch=counted)
            fetched_by_ticker[ticker] = chain.dataset_id
        except Exception as error:      # noqa: BLE001 - reported per ticker
            result["failed"][ticker] = f"{type(error).__name__}: {error}"
    if fetched_by_ticker:
        try:
            deliver_phantom_option_events(
                registry_path=registry_path, phantom_database_path=phantom_path, limit=100_000)
            projected = _projected_dataset_ids(phantom_path, list(fetched_by_ticker.values()), session_date)
        except Exception as error:      # noqa: BLE001
            projected = set()
            result["projection_error"] = f"{type(error).__name__}: {error}"
        for ticker, dataset_id in fetched_by_ticker.items():
            if dataset_id in projected:
                result["captured"].append(ticker)
            else:
                result["failed"][ticker] = "NOT_PROJECTED_TO_PHANTOM"
        result["dataset_ids"] = sorted(fetched_by_ticker.values())
    result["captured"].sort()
    result["status"] = "COMPLETE" if not result["failed"] and not result["over_budget"] else "PARTIAL"
    return result


__all__ = ["capture_open_record_chains", "refresh_completed_session_gex"]
