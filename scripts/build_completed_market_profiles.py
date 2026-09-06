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
    MarketDataCandleNoData,
    MarketDataCandleTransportError,
    MarketDataStockCandleAdapter,
    expected_intraday_timestamps,
    publish_observation_worklist,
    session_bounds,
    session_snapshot,
)
from contracts.dynamic_session_contract import DataExceptionReason, EvidenceState
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


def _quality_diagnostics(
    frame: pd.DataFrame,
    *,
    session_date: date,
    open_utc: datetime,
    close_utc: datetime,
    interval_minutes: int,
) -> tuple[bool, dict[str, Any]]:
    """Evaluate the completed-session profile publication contract."""
    expected = expected_intraday_timestamps(
        session_date=session_date,
        start_utc=open_utc,
        end_utc=close_utc,
        interval_minutes=interval_minutes,
        session_segment="REGULAR",
    )
    timestamps = pd.to_datetime(frame.get("timestamp_utc"), utc=True, errors="coerce")
    regular = frame.copy()
    if "session_segment" in regular:
        regular = regular[regular["session_segment"].astype(str).str.upper().eq("REGULAR")]
        timestamps = pd.to_datetime(regular.get("timestamp_utc"), utc=True, errors="coerce")
    observed = pd.DatetimeIndex(timestamps.dropna().drop_duplicates().sort_values())
    expected_set = set(expected)
    observed_set = set(observed)
    observed_expected = observed_set & expected_set
    coverage = len(observed_expected) / len(expected) if len(expected) else 0.0
    duplicate_count = int(timestamps.duplicated().sum())
    ordered = bool(timestamps.dropna().is_monotonic_increasing)
    first_region = bool(len(expected) and expected[0] in observed_set)
    last_region = bool(len(expected) and expected[-1] in observed_set)
    wrong_session_count = int(sum(value not in expected_set for value in observed_set))
    numeric_valid = True
    if not regular.empty:
        values = regular[["open", "high", "low", "close", "volume"]].apply(
            pd.to_numeric, errors="coerce"
        )
        numeric_valid = bool(
            values.notna().all().all()
            and (values[["open", "high", "low", "close"]] > 0).all().all()
            and (values["volume"] >= 0).all()
            and (values["high"] >= values[["open", "close", "low"]].max(axis=1)).all()
            and (values["low"] <= values[["open", "close", "high"]].min(axis=1)).all()
        )
    statuses = pd.to_numeric(
        regular.get("provider_http_status", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    provider_status_valid = bool(len(statuses) and statuses.between(200, 299).all())
    diagnostics = {
        "expected_regular_bars": int(len(expected)),
        "unique_regular_bars": int(len(observed_expected)),
        "coverage_ratio": round(float(coverage), 8),
        "first_region_present": first_region,
        "last_region_present": last_region,
        "duplicate_count": duplicate_count,
        "ordered": ordered,
        "wrong_session_bar_count": wrong_session_count,
        "numeric_geometry_valid": numeric_valid,
        "provider_status_valid": provider_status_valid,
        "provider_http_statuses": sorted({int(value) for value in statuses}),
    }
    usable = bool(
        coverage >= 0.95
        and first_region
        and last_region
        and duplicate_count == 0
        and ordered
        and wrong_session_count == 0
        and numeric_valid
        and provider_status_valid
    )
    return usable, diagnostics


def build_completed_profiles(
    *,
    run_id: str,
    session_date: date,
    interval_minutes: int = 5,
    base_dir: Path = ROOT,
    fetch_factory: Callable[[date, int], Callable[[str, datetime, datetime], pd.DataFrame]] | None = None,
    max_failure_ratio: float = 0.05,
    min_usable_ratio: float = 0.90,
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
    provider_calls = [0]
    if fetch_factory is None:
        adapter = MarketDataStockCandleAdapter(token)
        def fetch(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
            provider_calls[0] += 1
            return adapter.fetch_range(
                ticker, start, end, session_date=session_date,
                interval_minutes=interval_minutes, session_segment="REGULAR",
            )
    else:
        injected_fetch = fetch_factory(session_date, interval_minutes)
        def fetch(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
            provider_calls[0] += 1
            try:
                return injected_fetch(ticker, start, end)
            except (MarketDataCandleNoData, MarketDataCandleTransportError):
                raise
            except Exception as error:
                from canonical_data.marketdata_stock_candles import MarketDataCandleResponse
                raise MarketDataCandleTransportError(
                    f"injected provider transport failed: {error}",
                    response=MarketDataCandleResponse(
                        payload={"s": "error", "errmsg": str(error)},
                        http_status=0,
                        headers={},
                        acquired_at_utc=datetime.now(timezone.utc),
                    ),
                ) from error
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
    completed = 0; deferred = 0; exceptions: list[dict[str, Any]] = []
    partial_session_count = 0; no_data_count = 0; provider_failure_count = 0
    package_by_ticker = {path.name.removesuffix(".package.json").upper(): path for path in packages}
    future_session = session_date > session_snapshot(datetime.now(timezone.utc)).last_completed_session
    for ticker in tickers:
        path = package_by_ticker[ticker]
        package = json.loads(path.read_text(encoding="utf-8-sig"))
        atr = _atr14(package)
        try:
            if future_session:
                deferred += 1
                _atomic_patch(path, {
                    "market_profile_contract_required": True,
                    "market_profile_evidence": None,
                    "market_profile_evidence_state": EvidenceState.NOT_EVALUATED.value,
                    "market_profile_exception": DataExceptionReason.NOT_YET_OBSERVABLE.value,
                })
                exceptions.append({
                    "ticker": ticker,
                    "classification": "FUTURE_SESSION",
                    "reason": DataExceptionReason.NOT_YET_OBSERVABLE.value,
                })
                continue
            if atr <= 0:
                raise ValueError("ATR14 unavailable for governed profile binning")
            bars_result = resolver.resolve(
                ticker=ticker, session_date=session_date, start_utc=open_utc, end_utc=close_utc,
                fetch_missing=fetch, provider="MARKETDATA", interval_minutes=interval_minutes,
                adjustment_convention="SPLIT_ADJUSTED", evidence_state="COMPLETED_SESSION",
            )
            usable, diagnostics = _quality_diagnostics(
                bars_result.frame,
                session_date=session_date,
                open_utc=open_utc,
                close_utc=close_utc,
                interval_minutes=interval_minutes,
            )
            diagnostics.update({
                "resolution": bars_result.resolution,
                "dataset_ids": list(bars_result.dataset_ids),
                "physical_fetches": bars_result.physical_fetches,
            })
            if not usable:
                partial_session_count += 1
                deferred += 1
                _atomic_patch(path, {
                    "market_profile_contract_required": True,
                    "market_profile_evidence": None,
                    "market_profile_evidence_state": EvidenceState.NOT_EVALUATED.value,
                    "market_profile_exception": DataExceptionReason.INCOMPLETE_SESSION.value,
                    "market_profile_quality": diagnostics,
                })
                exceptions.append({
                    "ticker": ticker,
                    "classification": "PARTIAL_SESSION",
                    "reason": DataExceptionReason.INCOMPLETE_SESSION.value,
                    "diagnostics": diagnostics,
                })
                continue
            input_hashes = tuple(
                record.content_hash for record in (
                    registry.get_dataset(dataset_id) for dataset_id in bars_result.dataset_ids
                ) if record is not None
            )
            evidence = build_profile_evidence(
                ticker=ticker, session_date=session_date, evidence_state="COMPLETED_SESSION",
                bars=bars_result.frame, exchange_tick=0.01, atr14=atr, regular_open_utc=open_utc,
                input_dataset_ids=bars_result.dataset_ids, input_hashes=input_hashes,
                # The profile-stage contract, rather than raw transport
                # completeness alone, owns usability at >=95% coverage with
                # both session edges represented.
                completeness_status="COMPLETE",
                calculated_at_utc=close_utc,
            )
            evidence_record = store.persist(evidence, source_run_id=run_id)
            _atomic_patch(path, {
                "market_profile_contract_required": True,
                "market_profile_evidence": evidence.to_dict(),
                "market_profile_dataset_id": evidence_record.dataset_id,
                "market_profile_evidence_state": EvidenceState.COMPLETED_SESSION.value,
                "market_profile_exception": "",
                "market_profile_quality": diagnostics,
            })
            completed += 1
        except MarketDataCandleNoData as error:
            deferred += 1; no_data_count += 1
            response = error.response
            diagnostics = {
                "provider_http_status": response.http_status,
                "provider_status": str(response.payload.get("s", "")),
                "provider_headers": dict(response.headers),
            }
            _atomic_patch(path, {
                "market_profile_contract_required": True,
                "market_profile_evidence": None,
                "market_profile_evidence_state": EvidenceState.NOT_EVALUATED.value,
                "market_profile_exception": DataExceptionReason.INSUFFICIENT_BARS.value,
                "market_profile_quality": diagnostics,
            })
            exceptions.append({
                "ticker": ticker,
                "classification": "PROVIDER_NO_DATA",
                "reason": DataExceptionReason.INSUFFICIENT_BARS.value,
                "diagnostics": diagnostics,
            })
        except MarketDataCandleTransportError as error:
            provider_failure_count += 1
            response = error.response
            reason = DataExceptionReason.PROVIDER_UNAVAILABLE.value
            if response.http_status in {401, 403}:
                reason = DataExceptionReason.ENTITLEMENT_DENIED.value
            elif response.http_status == 429:
                reason = DataExceptionReason.RATE_LIMITED.value
            _atomic_patch(path, {
                "market_profile_contract_required": True,
                "market_profile_evidence": None,
                "market_profile_evidence_state": EvidenceState.UNAVAILABLE_PROVIDER.value,
                "market_profile_exception": reason,
                "market_profile_quality": {"provider_http_status": response.http_status},
            })
            exceptions.append({"ticker": ticker, "classification": "PROVIDER_FAILURE", "reason": reason})
        except Exception as error:
            _atomic_patch(path, {
                "market_profile_contract_required": True,
                "market_profile_evidence": None,
                "market_profile_exception": f"{type(error).__name__}:{error}",
            })
            exceptions.append({
                "ticker": ticker,
                "classification": "DATA_DEFECT",
                "reason": f"{type(error).__name__}:{error}",
            })
    exception_count = len(exceptions)
    hard_exception_count = exception_count - deferred
    failure_ratio = provider_failure_count / len(tickers) if tickers else 0.0
    usable_ratio = completed / len(tickers) if tickers else 1.0
    provider_systemic_failure = bool(tickers) and failure_ratio > float(max_failure_ratio)
    coverage_failure = bool(tickers) and usable_ratio < float(min_usable_ratio)
    systemic_failure = provider_systemic_failure or coverage_failure
    summary = {
        "run_id": run_id, "session_date": session_date.isoformat(), "interval_minutes": interval_minutes,
        "input_count": len(tickers), "completed": completed, "deferred": deferred,
        "exception_count": exception_count,
        "hard_exception_count": hard_exception_count,
        "partial_session_count": partial_session_count,
        "provider_no_data_count": no_data_count,
        "provider_failure_count": provider_failure_count,
        "physical_provider_requests": provider_calls[0],
        "reconciled": len(tickers) == completed + deferred + hard_exception_count,
        "failure_ratio": round(failure_ratio, 8),
        "max_failure_ratio": float(max_failure_ratio),
        "usable_ratio": round(usable_ratio, 8),
        "min_usable_ratio": float(min_usable_ratio),
        "provider_systemic_failure": provider_systemic_failure,
        "coverage_failure": coverage_failure,
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
    parser.add_argument(
        "--min-usable-ratio",
        type=float,
        default=float(os.environ.get("AVSHUNTER_PROFILE_MIN_USABLE_RATIO", "0.90")),
    )
    args = parser.parse_args()
    session = date.fromisoformat(args.session_date) if args.session_date else session_snapshot(datetime.now(timezone.utc)).last_completed_session
    summary = build_completed_profiles(
        run_id=args.run_id,
        session_date=session,
        interval_minutes=args.interval_minutes,
        max_failure_ratio=args.max_failure_ratio,
        min_usable_ratio=args.min_usable_ratio,
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "exceptions"}, indent=2))
    return 0 if summary["reconciled"] and not summary["systemic_failure"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
