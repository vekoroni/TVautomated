from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _truthy(value: Any) -> bool:
    return str(value).strip().upper() in {"1", "TRUE", "YES", "Y"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _latest(patterns: Iterable[str], root: Path) -> Optional[Path]:
    candidates: List[Path] = []
    for pattern in patterns:
        candidates.extend(root.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_trade_candidates(run_dir: Path, max_candidates: int = 10) -> List[Dict[str, Any]]:
    """Read AVSHUNTER outputs and produce zero-capital bridge candidates.

    The 6-dim state key comes from execution CSV. The 9-dim key is joined from
    vanguard_signals_enriched.debug_signature and is stored only when it has
    exactly 9 dimensions.
    """
    run_dir = Path(run_dir)
    run_id = run_dir.name
    execution_path = _latest(
        [
            f"morning_validation/morning_validated_trades_{run_id}.csv",
            f"execution/execution_v3_5_{run_id}.csv",
            f"execution/*{run_id}*.csv",
            f"superbrain/superbrain_enriched_{run_id}.csv",
        ],
        run_dir,
    )
    vanguard_path = _latest([f"vanguard/vanguard_signals_enriched_{run_id}.csv"], run_dir)
    if execution_path is None:
        return []

    vanguard_by_ticker: Dict[str, str] = {}
    if vanguard_path and vanguard_path.exists():
        for row in _read_csv(vanguard_path):
            ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
            signature = str(row.get("debug_signature") or "").strip()
            if ticker:
                vanguard_by_ticker[ticker] = signature if len(signature.split("|")) == 9 else ""

    selected: List[Dict[str, Any]] = []
    for row in _read_csv(execution_path):
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        approval = str(row.get("reviewer_approval") or "").strip().upper()
        approved_size = _float(row.get("approved_size_contracts"), 0.0)
        if approval and approval not in {"Y", "YES", "APPROVED", "TRUE"}:
            continue
        if approval and approved_size <= 0:
            continue
        if not approval and not _truthy(row.get("eod_candidate_authorized")):
            continue
        permission = str(row.get("morning_execution_permission") or row.get("execution_permission") or row.get("campaign_verdict") or row.get("effective_execution_verdict") or "").upper()
        if permission not in {"READY_EXECUTE", "MORNING_VALIDATION_REQUIRED", "GO", "GO_LIMIT", "PROBE"}:
            continue
        # Jump risk must be measured and absent to order: a missing flag (no forecast / not
        # assessable) is not "no jump risk" (R1; tests/test_layer3_volatility_leftovers.py C6).
        if str(row.get("l3_jump_risk_flag") or "").strip().upper() not in {"0", "FALSE", "NO", "N"}:
            continue
        if _float(row.get("live_contract_spread_pct") or row.get("contract_spread_pct"), 0.0) >= 25.0:
            continue
        out = dict(row)
        out["run_id"] = run_id
        out["state_key_6dim"] = row.get("layer2__matched_state_key") or row.get("state_key_6dim") or ""
        out["state_key_9dim"] = vanguard_by_ticker.get(ticker, "")
        out["bridge_source_execution_csv"] = str(execution_path)
        out["bridge_source_vanguard_csv"] = str(vanguard_path or "")
        selected.append(out)
        if len(selected) >= max_candidates:
            break
    return selected


def write_would_have_ordered(run_dir: Path, output_path: Path, max_candidates: int = 10) -> Path:
    rows = load_trade_candidates(run_dir, max_candidates=max_candidates)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()}) if rows else ["run_id", "ticker", "state_key_6dim", "state_key_9dim"]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output_path
