"""Build governed completed-session Market Profiles before Vanguard.

The stage is intentionally explicit and independently runnable. It publishes
its authorised worklist, resolves five-minute bars through CDS, persists the
derived advisory evidence, and atomically attaches only the evidence reference
to each existing package.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import (
    CanonicalFeatureFlags,
    CanonicalMinuteBarResolver,
    CanonicalRegistry,
    DatasetType,
    MarketDataStockCandleAdapter,
    publish_observation_worklist,
    session_bounds,
    session_snapshot,
)
from market_structure.completed_profile import CanonicalProfileEvidenceStore, build_profile_evidence


def _load_api_token(base_dir: Path) -> str:
    token = os.environ.get("MARKETDATA_API_KEY", "").strip()
    if token:
        return token
    env_path = base_dir / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("MARKETDATA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _package_paths(run_dir: Path, base_dir: Path = ROOT) -> list[Path]:
    index_path = run_dir / "packages" / "index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    paths = []
    for item in payload.get("packages") or []:
        raw = Path(str(item.get("package_path") or ""))
        path = raw if raw.is_absolute() else base_dir / raw
        if path.exists() and str(item.get("status", "BUILT")).upper() == "BUILT":
            paths.append(path)
    return paths


def _atr14(package: dict[str, Any]) -> float:
    rows = package.get("daily_df") or package.get("ohlcv_daily") or (package.get("timeseries") or {}).get("ohlcv_daily") or []
    if isinstance(rows, dict) and all(key in rows for key in ("h", "l", "c")):
        frame = pd.DataFrame({"high": rows["h"], "low": rows["l"], "close": rows["c"]})
    else:
        frame = pd.DataFrame(rows) if isinstance(rows, list) else pd.DataFrame()
    frame.columns = [str(column).lower() for column in frame.columns]
    if frame.empty or not {"high", "low", "close"} <= set(frame.columns):
        return 0.0
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    true_range = pd.concat((high - low, (high - close.shift()).abs(), (low - close.shift()).abs()), axis=1).max(axis=1)
    value = true_range.rolling(14, min_periods=5).mean().dropna()
    return float(value.iloc[-1]) if len(value) and float(value.iloc[-1]) > 0 else 0.0


def _atomic_patch(path: Path, updates: dict[str, Any]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8-sig")); payload.update(updates)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def build_completed_profiles(
    *,
    run_id: str,
    session_date: date,
    interval_minutes: int = 5,
    base_dir: Path = ROOT,
    fetch_factory: Callable[[date, int], Callable[[str, datetime, datetime], pd.DataFrame]] | None = None,
    max_failure_ratio: float = 0.05,
) -> dict[str, Any]:
    if not 0.0 <= float(max_failure_ratio) <= 1.0:
        raise ValueError("max_failure_ratio must be in [0,1]")
    run_dir = base_dir / "data" / "output" / "runs" / run_id
    packages = _package_paths(run_dir, base_dir)
    tickers = tuple(path.name.removesuffix(".package.json").upper() for path in packages)
    registry_path = base_dir / "data" / "canonical" / "control_plane.sqlite"
    payload_root = base_dir / "data" / "canonical" / "payloads"
    registry = CanonicalRegistry(registry_path); registry.initialise()
    publication = publish_observation_worklist(
        registry, run_id=run_id, stage="COMPLETED_MARKET_PROFILE", tickers=tickers,
        dataset_types=(DatasetType.INTRADAY_BAR, DatasetType.MARKET_STRUCTURE),
    )
    if not publication.reconciled:
        raise RuntimeError("completed Market Profile worklist did not reconcile")

    token = _load_api_token(base_dir)
    if fetch_factory is None:
        adapter = MarketDataStockCandleAdapter(token)
        fetch = lambda ticker, start, end: adapter.fetch_range(
            ticker, start, end, session_date=session_date,
            interval_minutes=interval_minutes, session_segment="REGULAR",
        )
    else:
        fetch = fetch_factory(session_date, interval_minutes)
    flags = CanonicalFeatureFlags(
        enabled=True, write_through=True, stage_gating_enforced=True,
        offline_replay=False, ohlcv_mode="ACTIVE",
    )
    open_utc, close_utc = session_bounds(session_date)
    resolver = CanonicalMinuteBarResolver(
        registry_path=registry_path, payload_root=payload_root, run_id=run_id,
        invocation_id=f"{run_id}:completed-profile:{session_date}:{interval_minutes}",
        evidence_cutoff_utc=close_utc, requesting_stage="COMPLETED_MARKET_PROFILE", flags=flags,
    )
    store = CanonicalProfileEvidenceStore(registry_path=registry_path, payload_root=payload_root)
    completed = 0; deferred = 0; exceptions: list[dict[str, str]] = []; physical_requests = 0
    package_by_ticker = {path.name.removesuffix(".package.json").upper(): path for path in packages}
    for ticker in tickers:
        path = package_by_ticker[ticker]
        package = json.loads(path.read_text(encoding="utf-8-sig"))
        atr = _atr14(package)
        try:
            if atr <= 0:
                raise ValueError("ATR14 unavailable for governed profile binning")
            bars_result = resolver.resolve(
                ticker=ticker, session_date=session_date, start_utc=open_utc, end_utc=close_utc,
                fetch_missing=fetch, provider="MARKETDATA", interval_minutes=interval_minutes,
                adjustment_convention="SPLIT_ADJUSTED", evidence_state="COMPLETED_SESSION",
            )
            physical_requests += bars_result.physical_fetches
            input_hashes = tuple(
                record.content_hash for record in (
                    registry.get_dataset(dataset_id) for dataset_id in bars_result.dataset_ids
                ) if record is not None
            )
            evidence = build_profile_evidence(
                ticker=ticker, session_date=session_date, evidence_state="COMPLETED_SESSION",
                bars=bars_result.frame, exchange_tick=0.01, atr14=atr, regular_open_utc=open_utc,
                input_dataset_ids=bars_result.dataset_ids, input_hashes=input_hashes,
                completeness_status=bars_result.quality.completeness_status if bars_result.quality else "UNAVAILABLE",
                calculated_at_utc=close_utc,
            )
            evidence_record = store.persist(evidence, source_run_id=run_id)
            _atomic_patch(path, {
                "market_profile_contract_required": True,
                "market_profile_evidence": evidence.to_dict(),
                "market_profile_dataset_id": evidence_record.dataset_id,
            })
            completed += 1
        except Exception as error:
            _atomic_patch(path, {
                "market_profile_contract_required": True,
                "market_profile_evidence": None,
                "market_profile_exception": f"{type(error).__name__}:{error}",
            })
            exceptions.append({"ticker": ticker, "reason": f"{type(error).__name__}:{error}"})
    exception_count = len(exceptions)
    failure_ratio = (deferred + exception_count) / len(tickers) if tickers else 0.0
    systemic_failure = bool(tickers) and failure_ratio > float(max_failure_ratio)
    summary = {
        "run_id": run_id, "session_date": session_date.isoformat(), "interval_minutes": interval_minutes,
        "input_count": len(tickers), "completed": completed, "deferred": deferred,
        "exception_count": exception_count, "physical_provider_requests": physical_requests,
        "reconciled": len(tickers) == completed + deferred + exception_count,
        "failure_ratio": round(failure_ratio, 8),
        "max_failure_ratio": float(max_failure_ratio),
        "systemic_failure": systemic_failure,
        "exceptions": exceptions,
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = run_dir / "market_profile" / f"completed_profile_summary_{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2), encoding="utf-8"); os.replace(temporary, output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-date")
    parser.add_argument("--interval-minutes", type=int, default=5, choices=(1, 5, 15, 30))
    parser.add_argument(
        "--max-failure-ratio",
        type=float,
        default=float(os.environ.get("AVSHUNTER_PROFILE_MAX_FAILURE_RATIO", "0.05")),
    )
    args = parser.parse_args()
    session = date.fromisoformat(args.session_date) if args.session_date else session_snapshot(datetime.now(timezone.utc)).last_completed_session
    summary = build_completed_profiles(
        run_id=args.run_id,
        session_date=session,
        interval_minutes=args.interval_minutes,
        max_failure_ratio=args.max_failure_ratio,
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "exceptions"}, indent=2))
    return 0 if summary["reconciled"] and not summary["systemic_failure"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
