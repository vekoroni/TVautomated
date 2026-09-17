"""Read recorded legacy opportunity books (read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

LABEL_COLUMNS = (
    "lab_rank", "priority_rank", "tier", "lab_verdict", "final_action", "thesis_state",
    "ev3_absolute_state", "ev_status", "ev2_ev_status", "ev_source", "dte", "direction_confidence",
    "trigger_go_eligible", "monetisability_state", "lab_execution_status",
)


@dataclass(frozen=True, slots=True)
class BookRow:
    run_id: str
    book_path: str
    book_sha256: str
    book_mtime_utc: datetime
    run_meta: dict
    ticker: str
    direction: Any
    thesis_id: Any
    reference: Any
    invalidation: Any
    target: Any
    contract_symbol: Any
    entry_bid: Any
    entry_ask: Any
    labels: dict = field(default_factory=dict)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _first(row: dict, *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        if str(value).strip() == "":
            continue
        return value
    return None


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def discover_books(runs_dir: Path) -> list[Path]:
    return sorted(runs_dir.glob("*/intelligence_lab/final_opportunity_book_*.csv"))


def read_book(path: Path) -> Iterator[BookRow]:
    run_dir = path.parents[1]
    run_id = run_dir.name
    meta_path = run_dir / "run_meta.json"
    try:
        run_meta = json.loads(meta_path.read_text(encoding="utf-8-sig")) if meta_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        run_meta = {}
    sha = _sha256(path)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    frame = pd.read_csv(path, low_memory=False)
    for record in frame.to_dict(orient="records"):
        ticker = str(record.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        yield BookRow(
            run_id=run_id,
            book_path=str(path),
            book_sha256=sha,
            book_mtime_utc=mtime,
            run_meta=run_meta,
            ticker=ticker,
            direction=_first(record, "final_direction", "direction"),
            thesis_id=_first(record, "thesis_id"),
            reference=_first(record, "underlying_price", "signal_price"),
            invalidation=_first(record, "invalidation_price"),
            target=_first(record, "target_price", "structural_target"),
            contract_symbol=_first(record, "contract_symbol"),
            entry_bid=_first(record, "contract_bid"),
            entry_ask=_first(record, "contract_ask"),
            labels={name: _clean(record.get(name)) for name in LABEL_COLUMNS if name in record},
        )
