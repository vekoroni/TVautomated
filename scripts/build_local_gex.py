#!/usr/bin/env python3
"""Build canonical swing-horizon GEX from locally stored MarketData chains."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Mapping
from uuid import uuid4

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.gamma_exposure_store import (  # noqa: E402
    CanonicalGammaExposureStore,
    PhantomOptionChainRepository,
)
from contracts.macro_file_contract import (  # noqa: E402
    GEX_BY_STRIKE_FILENAME,
    GEX_ERRORS_FILENAME,
    GEX_MANIFEST_FILENAME,
    GEX_PROXY_FILENAME,
    market_data_directory,
)
from macro_domain.gamma_exposure import GammaExposureConfig, calculate_gamma_exposure  # noqa: E402


DEFAULT_OUTPUT_DIR = market_data_directory(ROOT)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{uuid4().hex}")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{uuid4().hex}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


def build_local_gex(
    *,
    database_path: Path,
    registry_path: Path,
    canonical_root: Path,
    output_dir: Path,
    tickers: tuple[str, ...] = ("SPY", "QQQ"),
    session: date | None = None,
    run_id: str | None = None,
    config: GammaExposureConfig | None = None,
    source_option_dataset_ids: Mapping[str, str] | None = None,
) -> dict:
    cfg = config or GammaExposureConfig()
    invocation = run_id or f"LOCAL_GEX_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    repository = PhantomOptionChainRepository(database_path)
    session_date = session or repository.latest_common_session(tickers)
    store = CanonicalGammaExposureStore(registry_path=registry_path, payload_root=canonical_root)
    summaries: list[dict] = []
    strike_frames: list[pd.DataFrame] = []
    dataset_ids: list[str] = []
    for ticker in tickers:
        chain = repository.read(ticker, session_date)
        result = calculate_gamma_exposure(
            chain,
            ticker=ticker,
            session_date=session_date.isoformat(),
            config=cfg,
        )
        source_dataset_id = (
            source_option_dataset_ids.get(ticker)
            if source_option_dataset_ids is not None else None
        )
        record = store.persist(
            result,
            run_id=invocation,
            config=cfg,
            parent_dataset_ids=(source_dataset_id,) if source_dataset_id else None,
        )
        summary = dict(result.summary)
        summary["Run_Id"] = invocation
        summary["Dataset_Id"] = record.dataset_id
        summaries.append(summary)
        strike = result.by_strike.copy()
        strike["Run_Id"] = invocation
        strike["Dataset_Id"] = record.dataset_id
        strike_frames.append(strike)
        dataset_ids.append(record.dataset_id)

    summary_frame = pd.DataFrame(summaries)
    strike_frame = pd.concat(strike_frames, ignore_index=True)
    proxy_path = output_dir / GEX_PROXY_FILENAME
    strike_path = output_dir / GEX_BY_STRIKE_FILENAME
    _atomic_csv(proxy_path, summary_frame)
    _atomic_csv(strike_path, strike_frame)
    manifest = {
        "contract_version": "avshunter_local_gex_manifest_v1",
        "run_id": invocation,
        "session_date": session_date.isoformat(),
        "scope": cfg.scope_name,
        "source": str(database_path.resolve()),
        "provider_requests": 0,
        "dataset_ids": dataset_ids,
        "source_option_dataset_ids": dict(source_option_dataset_ids or {}),
        "tickers": list(tickers),
        "proxy_path": str(proxy_path.resolve()),
        "proxy_sha256": hashlib.sha256(proxy_path.read_bytes()).hexdigest(),
        "by_strike_path": str(strike_path.resolve()),
        "by_strike_sha256": hashlib.sha256(strike_path.read_bytes()).hexdigest(),
        "status": "COMPLETE",
    }
    _atomic_json(output_dir / GEX_MANIFEST_FILENAME, manifest)
    errors_path = output_dir / GEX_ERRORS_FILENAME
    temporary_errors = errors_path.with_suffix(f".tmp-{uuid4().hex}.txt")
    temporary_errors.write_text("", encoding="utf-8")
    os.replace(temporary_errors, errors_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(ROOT / "data" / "phantom" / "phantom_history.db"))
    parser.add_argument("--registry", default=str(ROOT / "data" / "canonical" / "control_plane.sqlite"))
    parser.add_argument("--canonical-root", default=str(ROOT / "data" / "canonical" / "gamma_exposure"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--session", default="latest-completed")
    parser.add_argument("--tickers", default="SPY,QQQ")
    args = parser.parse_args()
    session = None if args.session == "latest-completed" else date.fromisoformat(args.session)
    tickers = tuple(value.strip().upper() for value in args.tickers.split(",") if value.strip())
    try:
        manifest = build_local_gex(
            database_path=Path(args.database),
            registry_path=Path(args.registry),
            canonical_root=Path(args.canonical_root),
            output_dir=Path(args.output_dir),
            tickers=tickers,
            session=session,
        )
    except Exception as error:
        print(f"LOCAL GEX FAILED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
