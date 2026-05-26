"""PHANTOM production scoring engine."""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from phantom_bayesian import compute_bayesian_edge
from phantom_criticality import compute_criticality
from phantom_database import PhantomDatabase
from phantom_gamma_field import compute_gamma_trajectory
from phantom_info_flow import compute_info_flow
from phantom_iv_surface import compute_iv_surface


# PHANTOM_AUTHORITY_MODE controls whether Phantom overwrites
# execution_permission or operates in advisory mode.
# Set to "FULL_PROMOTION" after phantom_history.db is
# validated with at least one week of live trading data.
PHANTOM_AUTHORITY_MODE = "ADVISORY_PROMOTION"


TRUE_HARD_VETO_KEYWORDS = {
    "EARNINGS_WITHIN_DTE",
    "EARNINGS_INSIDE_DTE",
    "CATALYST_INSIDE_DTE",
    "FDA_BINARY_EVENT",
    "BINARY_EVENT_INSIDE_DTE",
    "HALT_RISK",
    "NO_CHAIN",
    "NO_OPTIONS_CHAIN",
    "NO_CONTRACT_DATA",
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _parse_vetoes(row: Dict[str, Any]) -> List[str]:
    raw_values = [row.get("options_hard_vetoes"), row.get("hard_vetoes")]
    out: List[str] = []
    for raw in raw_values:
        if raw is None or raw == "":
            continue
        if isinstance(raw, list):
            out.extend([str(x).upper() for x in raw])
            continue
        text = str(raw).strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                out.extend([str(x).upper() for x in parsed])
            elif isinstance(parsed, dict):
                out.extend([str(k).upper() for k, v in parsed.items() if v])
            else:
                out.append(str(parsed).upper())
        except Exception:
            out.extend([p.strip().upper() for p in text.replace(";", ",").split(",") if p.strip()])
    return sorted(set(out))


def _has_selected_contract(row: Dict[str, Any]) -> bool:
    dte = _float(row.get("contract_dte"), _float(row.get("dte"), 0.0))
    strike = _float(row.get("contract_strike"), _float(row.get("strike"), 0.0))
    return dte > 0 and strike > 0


def _true_hard_veto(row: Dict[str, Any]) -> Tuple[bool, str]:
    vetoes = _parse_vetoes(row)
    for veto in vetoes:
        if any(key in veto for key in TRUE_HARD_VETO_KEYWORDS):
            return True, veto
    if _upper(row.get("catalyst_inside_dte")) in {"TRUE", "1", "YES"}:
        return True, "CATALYST_INSIDE_DTE"
    if not _has_selected_contract(row):
        verdict = _upper(row.get("options_verdict"))
        reason = _upper(row.get("options_route_verdict")) + " " + _upper(row.get("negative_factors"))
        if verdict in {"STAND_DOWN", "BLOCKED"} and ("NO CONTRACT" in reason or "NO_CHAIN" in reason):
            return True, "NO_SELECTED_CONTRACT"
    direction = _upper(row.get("primary_direction") or row.get("options_direction") or row.get("direction"))
    if direction not in {"CALL", "PUT", "LONG", "SHORT", "BUY", "SELL"}:
        return True, "MISSING_PRIMARY_DIRECTION"
    return False, ""


def _decision(score: float) -> str:
    if score >= 85:
        return "CONVICTION"
    if score >= 70:
        return "HIGH"
    if score >= 55:
        return "MODERATE"
    if score >= 40:
        return "WATCH"
    return "PASS"


def _weights(row: Dict[str, Any]) -> Dict[str, float]:
    regime = _upper(row.get("macro_regime_label") or row.get("regime"))
    if "TRANSITIONAL" in regime:
        return {"iv": 0.24, "gamma": 0.25, "bayes": 0.24, "info": 0.12, "critical": 0.15}
    return {"iv": 0.22, "gamma": 0.24, "bayes": 0.25, "info": 0.13, "critical": 0.16}


def _composite(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    product = 1.0
    for key, weight in weights.items():
        s = max(0.0, min(1.0, scores.get(key, 0.0) / 100.0))
        product *= max(0.0, 1.0 - weight * s)
    return max(0.0, min(100.0, 100.0 * (1.0 - product)))


def score_row(row: Dict[str, Any], db: PhantomDatabase, run_id: str) -> Dict[str, Any]:
    iv = compute_iv_surface(row, db)
    gamma = compute_gamma_trajectory(row, db)
    bayes = compute_bayesian_edge(row)
    info = compute_info_flow(row)
    critical = compute_criticality(row)

    scores = {
        "iv": iv["iv_entropy_score"],
        "gamma": gamma["gamma_score"],
        "bayes": bayes["bayesian_score"],
        "info": info["info_flow_score"],
        "critical": critical["criticality_score"],
    }
    weights = _weights(row)
    score = _composite(scores, weights)
    convergence = sum(1 for value in scores.values() if value >= 70.0)
    decision = _decision(score)
    hard_veto, hard_veto_reason = _true_hard_veto(row)

    ois_original = _float(row.get("options_score"), 0.0)
    ois_adjustment = 15.0 if score >= 70.0 and not hard_veto else 0.0
    ois_adjusted = min(100.0, ois_original + ois_adjustment)

    payload: Dict[str, Any] = {
        "run_id": run_id,
        "ticker": row.get("ticker"),
        "score_date": str(date.today()),
        "phantom_score": round(score, 2),
        "phantom_decision": decision,
        "phantom_iv_entropy": iv["iv_entropy_score"],
        "phantom_gamma_trajectory": gamma["gamma_trajectory_signed"],
        "phantom_bayesian_edge": bayes["bayesian_edge_pp"],
        "phantom_info_flow": info["info_flow_score"],
        "phantom_criticality": critical["criticality_order_parameter"],
        "phantom_convergence_count": convergence,
        "phantom_ois_adjustment": ois_adjustment,
        "options_score_phantom_adjusted": round(ois_adjusted, 2),
        "phantom_hard_veto_respected": bool(hard_veto),
        "phantom_hard_veto_reason": hard_veto_reason,
        "phantom_data_quality": "|".join(sorted(set([iv.get("iv_data_quality", ""), info.get("info_flow_source", "")]))),
    }
    payload.update({f"phantom_{k}": v for k, v in iv.items() if k not in payload})
    payload.update({f"phantom_{k}": v for k, v in gamma.items() if k not in payload})
    payload.update({f"phantom_{k}": v for k, v in bayes.items() if k not in payload})
    payload.update({f"phantom_{k}": v for k, v in info.items() if k not in payload})

    promotion = "NONE"
    reason = ""
    if hard_veto:
        reason = f"Hard veto respected: {hard_veto_reason}"
    elif score >= 85.0:
        promotion = "EXECUTE"
        reason = "PHANTOM CONVICTION: multi-mechanism mispricing; OIS adjusted"
    elif score >= 70.0:
        promotion = "EXECUTE"
        reason = "PHANTOM HIGH: score >=70; OIS adjusted"
    elif score >= 55.0:
        promotion = "ARMED"
        reason = "PHANTOM MODERATE: promote watch/stand-down to ARMED review"
    else:
        reason = "PHANTOM did not meet promotion threshold"

    payload["phantom_promoted_verdict"] = promotion
    payload["phantom_promotion_reason"] = reason
    return payload


def apply_payload(row: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k, v in payload.items():
        out[k] = v

    promotion = payload.get("phantom_promoted_verdict")
    hard_veto = bool(payload.get("phantom_hard_veto_respected"))
    if payload.get("phantom_ois_adjustment", 0) > 0:
        out["options_score_original"] = row.get("options_score")
        out["options_score"] = payload.get("options_score_phantom_adjusted")
    if not hard_veto and promotion in {"EXECUTE", "ARMED"}:
        # ADVISORY_PROMOTION mode:
        # Phantom signals its verdict but does NOT overwrite
        # execution_permission. Morning validator retains
        # full authority. Promote to FULL_PROMOTION after
        # phantom_history.db is validated (post-Monday).
        out["options_verdict_original"] = row.get("options_verdict")
        out["options_route_verdict"] = f"PHANTOM_{promotion}"
        # execution_permission intentionally NOT overwritten
        out["phantom_execution_authority"] = "ADVISORY_PROMOTION"
        out["phantom_advisory_note"] = (
            f"Phantom {promotion}: {payload.get('phantom_promotion_reason','')}. "
            "Advisory only — DB_SURFACE validation pending. "
            "Morning validator retains execution authority."
        )
        factors = str(row.get("positive_factors") or "")
        note = payload.get("phantom_promotion_reason", "")
        out["positive_factors"] = (factors + " | PHANTOM_ADVISORY: " + note).strip(" |")
    else:
        out["phantom_execution_authority"] = (
            "NO_OVERRIDE_HARD_VETO" if hard_veto else "NO_PROMOTION"
        )
    return out


def run_phantom(input_csv: Path, output_csv: Path, run_id: str, db_path: Path, repo_root: Path) -> Dict[str, Any]:
    db = PhantomDatabase(db_path=db_path, repo_root=repo_root)
    db.initialise()
    df = pd.read_csv(input_csv, low_memory=False)
    records = df.to_dict(orient="records")

    unique_tickers = list({str(r.get("ticker") or "").upper() for r in records if r.get("ticker")})
    db.preload_tickers(unique_tickers)

    rows_out: List[Dict[str, Any]] = []
    promoted = 0
    hard_vetoes = 0
    scores: List[float] = []
    score_payloads: List[tuple] = []

    for record in records:
        payload = score_row(record, db, run_id)
        score_payloads.append((str(record.get("ticker") or ""), payload))
        if payload.get("phantom_promoted_verdict") in {"EXECUTE", "ARMED"} and not payload.get("phantom_hard_veto_respected"):
            promoted += 1
        if payload.get("phantom_hard_veto_respected"):
            hard_vetoes += 1
        scores.append(float(payload.get("phantom_score") or 0.0))
        rows_out.append(apply_payload(record, payload))

    db.batch_write_phantom_scores(run_id, score_payloads)

    out_df = pd.DataFrame(rows_out)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_csv, index=False)
    summary = {
        "run_id": run_id,
        "rows_processed": len(out_df),
        "promoted_count": promoted,
        "hard_veto_respected_count": hard_vetoes,
        "score_min": min(scores) if scores else 0,
        "score_max": max(scores) if scores else 0,
        "score_mean": sum(scores) / len(scores) if scores else 0,
        "output_csv": str(output_csv),
    }
    db.write_run_audit(run_id, str(input_csv), str(output_csv), len(out_df), promoted, hard_vetoes, summary)
    summary_path = output_csv.parent / f"phantom_summary_{run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run PHANTOM scoring for one AVSHUNTER run.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--input-csv", default="")
    p.add_argument("--output-csv", default="")
    p.add_argument("--db-path", default="")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    repo_root = Path(args.repo_root)
    input_csv = Path(args.input_csv) if args.input_csv else repo_root / "data" / "output" / "runs" / args.run_id / "options" / f"options_intelligence_{args.run_id}.csv"
    output_csv = Path(args.output_csv) if args.output_csv else repo_root / "data" / "output" / "runs" / args.run_id / "options" / f"options_intelligence_phantom_{args.run_id}.csv"
    db_path = Path(args.db_path) if args.db_path else repo_root / "data" / "phantom" / "phantom_history.db"
    if not input_csv.exists():
        raise SystemExit(f"PHANTOM input CSV not found: {input_csv}")
    summary = run_phantom(input_csv, output_csv, args.run_id, db_path, repo_root)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

