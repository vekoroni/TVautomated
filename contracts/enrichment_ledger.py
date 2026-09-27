"""Per-run enrichment ledgers: each Evening stage owns an append-only record of its facts.

AVS-PKG-002 P3. The trap engine (5.5), the actuarial pass (8.5) and the trigger layer (8.6)
used to write their per-ticker output back into the package files they had read (a shared
mutable scratchpad across processes). Each stage now appends to its own ledger,
``runs/<run>/enrichment/<stage>_<run>.jsonl``, keyed by run_id and ticker, and readers
resolve facts by that identity. While packages still exist the package patch continues and
readers fall back to it; nothing in this module grants any authority.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

LEDGER_DIRNAME = "enrichment"
LEDGER_CONTRACT_VERSION = "enrichment_ledger_v1"
STAGES = ("trap", "actuarial", "trigger")


def ledger_path(run_dir: Path | str, stage: str) -> Path:
    run_dir = Path(run_dir)
    return run_dir / LEDGER_DIRNAME / f"{stage}_{run_dir.name}.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record(run_id: str, stage: str, item: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(item.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("enrichment record needs a ticker")
    payload = item.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError(f"enrichment record for {ticker} needs a payload mapping")
    return {
        "contract_version": LEDGER_CONTRACT_VERSION,
        "run_id": run_id,
        "stage": stage,
        "ticker": ticker,
        "calculation_version": str(item.get("calculation_version") or ""),
        "input_sha256": str(item.get("input_sha256") or ""),
        "recorded_at_utc": str(item.get("recorded_at_utc") or _now()),
        "payload": dict(payload),
    }


def write_enrichment_ledger(run_dir: Path | str, run_id: str, stage: str,
                            items: Iterable[Mapping[str, Any]], *, append: bool = False) -> Path:
    """Write (or append) records; each line is one immutable fact. Returns the ledger path."""
    if stage not in STAGES:
        raise ValueError(f"unknown enrichment stage: {stage}")
    path = ledger_path(run_dir, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(_record(run_id, stage, item), ensure_ascii=False, default=str) for item in items]
    if append and path.exists():
        with path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
        return path
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def append_enrichment_record(run_dir: Path | str, run_id: str, stage: str, item: Mapping[str, Any]) -> Path:
    return write_enrichment_ledger(run_dir, run_id, stage, [item], append=True)


def read_enrichment_ledger(run_dir: Path | str, stage: str, *, expected_run_id: str | None = None) -> dict[str, Any]:
    """Return {status, run_id, record_count, by_ticker}. The last record per ticker wins.

    status: PRESENT | MISSING | RUN_MISMATCH | INVALID. A run identity mismatch yields no facts.
    """
    run_dir = Path(run_dir)
    path = ledger_path(run_dir, stage)
    wanted = str(expected_run_id or run_dir.name)
    out: dict[str, Any] = {"status": "MISSING", "run_id": wanted, "stage": stage, "path": str(path),
                           "record_count": 0, "by_ticker": {}}
    if not path.is_file():
        return out
    by_ticker: dict[str, dict[str, Any]] = {}
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get("run_id")) != wanted:
                out["status"] = "RUN_MISMATCH"
                out["by_ticker"] = {}
                out["record_count"] = 0
                return out
            if record.get("stage") != stage:
                continue
            count += 1
            by_ticker[str(record.get("ticker") or "").upper()] = dict(record.get("payload") or {})
    except (OSError, ValueError):
        out["status"] = "INVALID"
        return out
    out.update({"status": "PRESENT", "record_count": count, "by_ticker": by_ticker})
    return out


# --------------------------------------------------------------------------- readers with package fallback
def _packages(run_dir: Path) -> Iterable[tuple[str, dict[str, Any]]]:
    pkg_dir = Path(run_dir) / "packages"
    if not pkg_dir.is_dir():
        return
    for path in sorted(pkg_dir.glob("*.package.json")):
        try:
            pkg = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        ticker = str(pkg.get("ticker") or path.name.split(".")[0]).strip().upper()
        if ticker:
            yield ticker, pkg


def load_trap_contexts(run_dir: Path | str) -> dict[str, dict[str, Any]]:
    """{ticker: tle block} with a tle_verdict; ledger first, then the package files."""
    ledger = read_enrichment_ledger(run_dir, "trap")
    if ledger["status"] == "PRESENT":
        return {t: b for t, b in ledger["by_ticker"].items() if isinstance(b, dict) and b.get("tle_verdict")}
    out: dict[str, dict[str, Any]] = {}
    for ticker, pkg in _packages(Path(run_dir)):
        block = pkg.get("tle")
        if isinstance(block, dict) and block.get("tle_verdict"):
            out[ticker] = block
    return out


def load_trigger_blocks(run_dir: Path | str) -> dict[str, dict[str, Any]]:
    """{ticker: triggers block}; ledger first, then the package files."""
    ledger = read_enrichment_ledger(run_dir, "trigger")
    if ledger["status"] == "PRESENT":
        return {t: b for t, b in ledger["by_ticker"].items() if isinstance(b, dict)}
    out: dict[str, dict[str, Any]] = {}
    for ticker, pkg in _packages(Path(run_dir)):
        block = pkg.get("triggers")
        if isinstance(block, dict):
            out[ticker] = block
    return out


def load_actuarial_map(run_dir: Path | str) -> dict[str, dict[str, Any]]:
    """{ticker: actuarial block} for tickers the enrichment pass actually enriched (``enriched_by``)."""
    ledger = read_enrichment_ledger(run_dir, "actuarial")
    if ledger["status"] == "PRESENT":
        return {t: b for t, b in ledger["by_ticker"].items() if isinstance(b, dict) and b.get("enriched_by")}
    out: dict[str, dict[str, Any]] = {}
    for ticker, pkg in _packages(Path(run_dir)):
        block = pkg.get("actuarial")
        if isinstance(block, dict) and block.get("enriched_by"):
            out[ticker] = block
    return out


__all__ = [
    "LEDGER_CONTRACT_VERSION", "LEDGER_DIRNAME", "STAGES", "append_enrichment_record", "ledger_path",
    "load_actuarial_map", "load_trap_contexts", "load_trigger_blocks", "read_enrichment_ledger",
    "write_enrichment_ledger",
]
