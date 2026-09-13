from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3

from canonical_data.benchmark_option_chain import CanonicalBenchmarkOptionChainStore
from canonical_data.marketdata_option_chain import MarketDataOptionChainAdapter
from orchestrator.completed_session_gex import refresh_completed_session_gex


SESSION = date(2026, 9, 11)
UPDATED = int(datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc).timestamp())
EXPIRY = int(datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc).timestamp())


def _payload(ticker: str) -> dict:
    spot = 700.0 if ticker == "SPY" else 600.0
    symbols: list[str] = []
    sides: list[str] = []
    strikes: list[float] = []
    for offset in range(15):
        strike = int(spot - 7 + offset)
        encoded = f"{strike * 1000:08d}"
        symbols.extend([
            f"{ticker}261016C{encoded}",
            f"{ticker}261016P{encoded}",
        ])
        sides.extend(["call", "put"])
        strikes.extend([float(strike), float(strike)])
    count = len(symbols)
    return {
        "s": "ok",
        "optionSymbol": symbols,
        "side": sides,
        "strike": strikes,
        "expiration": [EXPIRY] * count,
        "dte": [35] * count,
        "updated": [UPDATED] * count,
        "bid": [4.0] * count,
        "ask": [4.2] * count,
        "mid": [4.1] * count,
        "bidSize": [10] * count,
        "askSize": [12] * count,
        "last": [4.05] * count,
        "openInterest": [100 + index for index in range(count)],
        "volume": [20] * count,
        "inTheMoney": [False] * count,
        "intrinsicValue": [0.0] * count,
        "extrinsicValue": [4.1] * count,
        "underlyingPrice": [spot] * count,
        "iv": [0.25] * count,
        "delta": [0.50 if side == "call" else -0.50 for side in sides],
        "gamma": [0.02] * count,
        "theta": [-0.05] * count,
        "vega": [0.10] * count,
        "contractMultiplier": [100] * count,
    }


class _Response:
    status_code = 200
    ok = True
    text = ""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def json(self) -> dict:
        return self.payload


class _Transport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(_payload("SPY"))


def test_marketdata_adapter_requests_exact_completed_session() -> None:
    transport = _Transport()
    adapter = MarketDataOptionChainAdapter(
        api_token="test-token", transport=transport
    )
    result = adapter.fetch("spy", session_date=SESSION, dte_max=60)
    assert result["s"] == "ok"
    url, request = transport.calls[0]
    assert url.endswith("/SPY/")
    assert request["params"]["date"] == "2026-09-11"
    assert request["params"]["from"] == "2026-09-12"
    assert request["params"]["to"] == "2026-11-10"
    assert request["params"]["minOpenInterest"] == 0
    assert request["headers"]["Authorization"] == "Token test-token"


def test_benchmark_chain_store_reuses_exact_canonical_dataset(tmp_path: Path) -> None:
    store = CanonicalBenchmarkOptionChainStore(
        registry_path=tmp_path / "control.sqlite",
        payload_root=tmp_path / "payloads",
        run_id="RUN-1",
    )
    calls = 0

    def fetch(_: str) -> dict:
        nonlocal calls
        calls += 1
        return _payload("SPY")

    first = store.get(ticker="SPY", session_date=SESSION, dte_max=60, fetch=fetch)
    second = store.get(ticker="SPY", session_date=SESSION, dte_max=60, fetch=fetch)
    assert first.dataset_id == second.dataset_id
    assert first.resolution == "PROVIDER_FETCH"
    assert second.resolution in {"EXACT_HIT", "SUPERSET_HIT"}
    assert calls == 1


def test_end_to_end_completed_session_refresh_updates_phantom_gex_and_macro(
    tmp_path: Path,
) -> None:
    macro_dir = tmp_path / "dropbox" / "macro"
    macro_dir.mkdir(parents=True)
    macro_path = macro_dir / "macro_intelligence_latest.json"
    macro_path.write_text(
        json.dumps({
            "contract_version": "macro_contract_v1_0",
            "gex_regime_score": 0.1,
            "gex_available": True,
            "extras": {"gex": {"session_date": "2026-09-04"}},
            "conflict_flags": [],
        }),
        encoding="utf-8",
    )

    result = refresh_completed_session_gex(
        repository_root=tmp_path,
        run_id="RUN-1",
        session_date=SESSION,
        fetch_chain=lambda ticker: _payload(ticker),
    )
    assert result["status"] == "COMPLETE", result.get("error")
    assert result["session_date"] == SESSION.isoformat()
    assert len(result["dataset_ids"]) == 2
    with sqlite3.connect(tmp_path / "data" / "phantom" / "phantom_history.db") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM canonical_option_chain_revisions"
        ).fetchone()[0] == 60
        receipts = connection.execute(
            "SELECT dataset_id,ticker,session_date,rows_projected "
            "FROM canonical_projection_receipts ORDER BY ticker"
        ).fetchall()
        assert {row[0] for row in receipts} == set(result["dataset_ids"])
        assert {row[1] for row in receipts} == {"SPY", "QQQ"}
        assert {row[2] for row in receipts} == {SESSION.isoformat()}
        assert {row[3] for row in receipts} == {30}
        assert connection.execute(
            "SELECT COUNT(DISTINCT ticker) FROM chain_snapshots WHERE quote_date=?",
            (SESSION.isoformat(),),
        ).fetchone()[0] == 2
    macro = json.loads(macro_path.read_text(encoding="utf-8"))
    assert macro["gex_available"] is True
    assert macro["extras"]["gex"]["session_date"] == SESSION.isoformat()
    assert macro["extras"]["gex"]["authority"] == "ADVISORY_ONLY"
    manifest = json.loads(
        (tmp_path / "dropbox" / "market_data" / "avshunter_gex_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["session_date"] == SESSION.isoformat()
    assert manifest["source_option_dataset_ids"] == {
        "SPY": result["dataset_ids"][0],
        "QQQ": result["dataset_ids"][1],
    }
    registry_path = tmp_path / "data" / "canonical" / "control_plane.sqlite"
    with sqlite3.connect(registry_path) as connection:
        parent_rows = connection.execute(
            "SELECT instrument_id,parent_dataset_ids_json "
            "FROM dataset_registry WHERE dataset_type='GAMMA_EXPOSURE'"
        ).fetchall()
    assert {
        ticker: json.loads(parent_json)
        for ticker, parent_json in parent_rows
    } == {
        "SPY": [result["dataset_ids"][0]],
        "QQQ": [result["dataset_ids"][1]],
    }


def test_failed_required_session_refresh_clears_prior_gex_without_blocking_core(
    tmp_path: Path,
) -> None:
    macro_dir = tmp_path / "dropbox" / "macro"
    macro_dir.mkdir(parents=True)
    macro_path = macro_dir / "macro_intelligence_latest.json"
    macro_path.write_text(
        json.dumps({
            "contract_version": "macro_contract_v1_0",
            "gex_regime_score": 0.70,
            "gex_available": True,
            "extras": {
                "gex": {
                    "session_date": "2026-09-04",
                    "net_gex_bn": 12.5,
                }
            },
            "conflict_flags": [],
        }),
        encoding="utf-8",
    )

    def unavailable(_: str) -> dict:
        raise RuntimeError("provider unavailable")

    result = refresh_completed_session_gex(
        repository_root=tmp_path,
        run_id="RUN-FAIL",
        session_date=SESSION,
        fetch_chain=unavailable,
    )
    assert result["status"] == "UNAVAILABLE"
    assert result["authority"] == "ADVISORY_ONLY"
    macro = json.loads(macro_path.read_text(encoding="utf-8"))
    assert macro["gex_available"] is False
    assert macro["gex_regime_score"] is None
    assert macro["extras"]["gex"]["session_date"] == SESSION.isoformat()
    assert macro["extras"]["gex"]["state"] == "UNAVAILABLE_REQUIRED_SESSION"
