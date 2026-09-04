"""Run EV Engine v3 as governed production evidence (legacy path compatible)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vanguard.ev_engine_v3 import (  # noqa: E402
    EV3BarrierCache,
    EV3Policy,
    evaluate_contract,
    not_applicable_result,
    policy_as_dict,
    select_contract,
    EV3_EVALUATED_STATUS,
)


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_dataframe_write(frame: pd.DataFrame, path: Path) -> None:
    """Write a CSV or parquet artifact atomically in its destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp{path.suffix}")
    try:
        if path.suffix.lower() == ".parquet":
            frame.to_parquet(temporary, index=False)
        else:
            frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json_write(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _candidate_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the selected contract plus complete JSON alternatives."""
    candidates: list[dict[str, Any]] = []
    selected_symbol = (
        source.get("contract_occ_symbol")
        or source.get("recommended_contract")
        or source.get("contract_symbol")
    )
    if selected_symbol is not None and not pd.isna(selected_symbol) and str(selected_symbol).strip():
        candidates.append(dict(source))

    raw = source.get("alternative_contracts_json")
    alternatives: list[dict[str, Any]] = []
    if raw is not None and not (isinstance(raw, float) and pd.isna(raw)) and str(raw).strip():
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                alternatives = [x for x in parsed if isinstance(x, dict)]
        except (TypeError, ValueError, json.JSONDecodeError):
            alternatives = []

    aliases = {
        "symbol": "contract_symbol",
        "strike": "contract_strike",
        "expiry": "contract_expiry",
        "dte": "contract_dte",
        "bid": "contract_bid",
        "ask": "contract_ask",
        "delta": "contract_delta",
        "gamma": "contract_gamma",
        "theta": "contract_theta",
        "vega": "contract_vega",
        "iv": "contract_iv",
        "oi": "contract_oi",
        "volume": "contract_volume",
        "quote_timestamp_utc": "contract_quote_timestamp_utc",
        "contract_multiplier": "contract_multiplier",
        "structure": "contract_structure",
        "candidate_generation_rank": "ev3_candidate_generation_rank",
        "candidate_policy_version": "ev3_candidate_policy_version",
    }
    for alternative in alternatives:
        candidate = dict(source)
        for source_name, target_name in aliases.items():
            if source_name in alternative:
                candidate[target_name] = alternative[source_name]
        if "quote_timestamp_utc" in alternative:
            # The canonical adapter checks the top-level selected-quote alias
            # first, so replace both aliases for an alternative candidate.
            candidate["quote_timestamp_utc"] = alternative["quote_timestamp_utc"]
        for nested_name in ("long_leg", "short_leg", "strike_width", "entry_debit_mid"):
            if nested_name in alternative:
                candidate[nested_name] = alternative[nested_name]
        candidates.append(candidate)
    return candidates


def run_shadow(
    input_path: Path,
    barrier_path: Path,
    output_dir: Path,
    *,
    phase: str = "EOD",
    now_utc: str | None = None,
) -> dict[str, Any]:
    frame = _load(input_path)
    cache = EV3BarrierCache.load(barrier_path)
    policy = EV3Policy()
    rows: list[dict[str, Any]] = []
    contract_evaluations: list[dict[str, Any]] = []
    for index, source in frame.iterrows():
        source_dict = source.to_dict()
        candidates = _candidate_rows(source_dict)
        if not candidates:
            result = not_applicable_result(
                "NOT_APPLICABLE_NO_SELECTED_CONTRACT",
                "Options Intelligence supplied neither a selected contract nor a complete alternative",
            )
            evaluations = []
            result["ev3_selection_reason"] = "NO_SELECTED_OR_ALTERNATIVE_CONTRACT"
            result["ev3_candidates_received"] = 0
            result["ev3_candidates_evaluated"] = 0
            result["ev3_candidates_valid"] = 0
        elif len(candidates) == 1:
            result = evaluate_contract(
                candidates[0], cache, policy=policy, phase=phase, now_utc=now_utc
            )
            evaluations = [dict(result)]
            result["ev3_selection_reason"] = "SELECTED_CONTRACT_ONLY"
            result["ev3_candidates_received"] = 1
            result["ev3_candidates_evaluated"] = 1
            result["ev3_candidates_valid"] = int(result.get("ev3_status") == EV3_EVALUATED_STATUS)
        else:
            result, evaluations = select_contract(
                candidates, cache, policy=policy, phase=phase, now_utc=now_utc
            )
        result["source_row_index"] = index
        result["ticker"] = source.get("ticker", source.get("symbol", ""))
        rows.append(result)
        for ordinal, evaluation in enumerate(evaluations, start=1):
            evaluation = dict(evaluation)
            evaluation["source_row_index"] = index
            evaluation["candidate_ordinal"] = ordinal
            evaluation["ticker"] = result["ticker"]
            contract_evaluations.append(evaluation)
    results = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "ev3_stage1_shadow_results.parquet"
    rejection_path = output_dir / "ev3_stage1_shadow_rejections.csv"
    ranked_path = output_dir / "ev3_stage1_shadow_ranked.csv"
    evaluations_path = output_dir / "ev3_stage1_contract_evaluations.parquet"
    audit_path = output_dir / "ev3_stage1_shadow_audit.json"
    _atomic_dataframe_write(results, result_path)
    rejected = results[results["ev3_status"] == "REJECTED"].copy()
    _atomic_dataframe_write(rejected, rejection_path)
    ranked = results[results["ev3_status"] == EV3_EVALUATED_STATUS].copy()
    if "ev3_ev_lower_bound_return" in ranked.columns:
        ranked = ranked.sort_values("ev3_ev_lower_bound_return", ascending=False)
    _atomic_dataframe_write(ranked, ranked_path)
    _atomic_dataframe_write(pd.DataFrame(contract_evaluations), evaluations_path)
    reason_counts = results["ev3_reason_code"].value_counts(dropna=False).to_dict()
    state_counts = results["ev3_absolute_state"].value_counts(dropna=False).to_dict()
    evaluation_frame = pd.DataFrame(contract_evaluations)
    evaluation_reason_counts = (
        evaluation_frame["ev3_reason_code"].value_counts(dropna=False).to_dict()
        if "ev3_reason_code" in evaluation_frame.columns
        else {}
    )
    structure_counts = (
        evaluation_frame["ev3_structure"].value_counts(dropna=False).to_dict()
        if "ev3_structure" in evaluation_frame.columns
        else {}
    )
    state_match_counts = (
        results["ev3_state_match_type"].value_counts(dropna=False).to_dict()
        if "ev3_state_match_type" in results.columns
        else {}
    )
    audit = {
        "stage": "EV-2B",
        "artifact_contract_version": "ev3-production-evidence-v0.6.0",
        "mode": "PRODUCTION_EVIDENCE",
        "production_consumer_enabled": True,
        "production_authority": False,
        "capital_eligibility_enabled": False,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": phase.upper(),
        "evaluation_now_utc": now_utc,
        "input_path": str(input_path.resolve()),
        "input_sha256": _sha256(input_path),
        "barrier_path": str(barrier_path.resolve()),
        "barrier_sha256": _sha256(barrier_path),
        "engine_source_sha256": _sha256(REPO_ROOT / "vanguard" / "ev_engine_v3.py"),
        "runner_source_sha256": _sha256(Path(__file__)),
        "rows_received": int(len(frame)),
        "rows_evaluated": int((results["ev3_status"] == EV3_EVALUATED_STATUS).sum()),
        "rows_rejected": int((results["ev3_status"] == "REJECTED").sum()),
        "rows_not_applicable": int((results["ev3_status"] == "NOT_APPLICABLE").sum()),
        "contract_candidates_received": int(sum(len(_candidate_rows(row)) for row in frame.to_dict("records"))),
        "contract_evaluations_written": int(len(contract_evaluations)),
        "reason_counts": {str(k): int(v) for k, v in reason_counts.items()},
        "contract_evaluation_reason_counts": {
            str(k): int(v) for k, v in evaluation_reason_counts.items()
        },
        "contract_evaluation_structure_counts": {
            str(k): int(v) for k, v in structure_counts.items()
        },
        "absolute_state_counts": {str(k): int(v) for k, v in state_counts.items()},
        "state_match_counts": {str(k): int(v) for k, v in state_match_counts.items()},
        "policy": policy_as_dict(policy),
        "limitations": [
            "Long CALL/PUT and same-expiry bull-call/bear-put debit spreads",
            "Vertical short-leg assignment and discrete ex-dividend event risk are reported but not separately modelled",
            "Barrier cache supports exact 5, 10, and 20 session holds plus audited core-aligned 5-of-7 state fallback",
            "EV3 is production evidence but remains non-authoritative until outcome calibration passes",
        ],
        "outputs": {
            "results": str(result_path.resolve()),
            "results_sha256": _sha256(result_path),
            "rejections": str(rejection_path.resolve()),
            "rejections_sha256": _sha256(rejection_path),
            "ranked": str(ranked_path.resolve()),
            "ranked_sha256": _sha256(ranked_path),
            "contract_evaluations": str(evaluations_path.resolve()),
            "contract_evaluations_sha256": _sha256(evaluations_path),
        },
    }
    _atomic_json_write(audit, audit_path)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--barrier-cache", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--phase", choices=("EOD", "MORNING"), default="EOD")
    parser.add_argument("--now-utc", help="Fixed timezone-aware evaluation timestamp for reproducibility")
    args = parser.parse_args()
    audit = run_shadow(
        args.input, args.barrier_cache, args.output_dir,
        phase=args.phase, now_utc=args.now_utc,
    )
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
