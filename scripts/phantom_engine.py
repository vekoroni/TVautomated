"""PHANTOM production scoring engine."""

from __future__ import annotations

import argparse
import json
import math
import logging
from datetime import date, datetime
from time import perf_counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from phantom_bayesian import compute_bayesian_edge
from phantom_criticality import compute_criticality
from phantom_database import PhantomDatabase
from phantom_gamma_field import compute_gamma_trajectory
from phantom_info_flow import compute_info_flow
from phantom_iv_surface import compute_iv_surface

import sys
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.actuarial_evidence import wire_frame
from contracts.phantom_advisory_policy import (SCORE_VERSION, PROMOTIONS_ENABLED,
    legacy_composite, ceiling, composite, qualified_score)
from contracts.phantom_prospective_evidence import capture_candidates, capture_predictions


# No FULL_PROMOTION switch exists. Score bands are uncalibrated advisory
# evidence; a separately approved authority implementation would be required.
PHANTOM_AUTHORITY_MODE = "ADVISORY_PROMOTION"
logger = logging.getLogger(__name__)


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
    return composite(scores, weights)


def score_row(row: Dict[str, Any], db: PhantomDatabase, run_id: str) -> Dict[str, Any]:
    iv = compute_iv_surface(row, db)
    gamma = compute_gamma_trajectory(row, db)
    bayes_row = dict(row, run_id=run_id)
    symbol = row.get('contract_symbol') or row.get('contract_occ_symbol') or row.get('option_symbol')
    selected = next((r for r in db.latest_chain_rows(str(row.get('ticker') or ''))
                     if r.get('option_symbol') == symbol), None) if symbol else None
    # Unqualified/stale row-level delta cannot manufacture a market probability.
    delta = selected.get('delta') if selected and iv['iv_evidence_available'] else None
    bayes_row.update(contract_delta=delta, delta=delta)
    bayes = compute_bayesian_edge(bayes_row)
    info = compute_info_flow(row)
    critical = compute_criticality(row)

    scores = {
        "iv": iv["iv_entropy_score"],
        "gamma": gamma["gamma_score"],
        "bayes": bayes["bayesian_score"],
        "info": info["info_flow_score"],
        "critical": critical["criticality_score"],
    }
    scores = {key: qualified_score(value) for key, value in scores.items()}
    weights = _weights(row)
    score = _composite(scores, weights)
    convergence = sum(1 for value in scores.values() if value is not None and value >= 70.0)
    evidence_complete = all(value is not None for value in scores.values())
    any_evidence = any(value is not None for value in scores.values())
    decision = _decision(score) if any_evidence else 'UNASSESSED'
    hard_veto, hard_veto_reason = _true_hard_veto(row)

    ois_original = _float(row.get("options_score"), 0.0)
    # This release never grants promotion or score-bonus authority, including
    # fully evidenced scores above the newly reachable thresholds.
    ois_adjustment = 0.0
    ois_adjusted = min(100.0, ois_original + ois_adjustment)

    payload: Dict[str, Any] = {
        "run_id": run_id,
        "ticker": row.get("ticker"),
        "score_date": str(date.today()),
        "phantom_score": round(score, 2) if any_evidence else None,
        "phantom_score_legacy": round(legacy_composite(scores, weights), 6) if any_evidence else None,
        "phantom_score_legacy_ceiling": round(ceiling(weights), 6),
        "phantom_score_version": SCORE_VERSION,
        "phantom_score_basis": "FULL_CONFIGURED_NOISY_OR_CEILING_NORMALISED_NOT_PROBABILITY",
        "phantom_score_calibrated": False,
        "phantom_promotions_enabled": PROMOTIONS_ENABLED,
        "phantom_evidence_state": "QUALIFIED_ADVISORY_NO_PROMOTION" if evidence_complete else "PARTIAL_NO_PROMOTION",
        "phantom_missing_components": [k for k,v in scores.items() if v is None],
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
    elif not evidence_complete:
        reason = "Missing/unqualified components: " + ', '.join(payload['phantom_missing_components']) + "; no promotion or OIS bonus"
    else:
        reason = "Promotions disabled: advisory-only, score scale and bands not economically calibrated"

    payload["phantom_promoted_verdict"] = promotion
    payload["phantom_promotion_reason"] = reason
    return payload


def apply_payload(row: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add Phantom's evidence to the row (ACK 7 Oct 2026): its own fields only. It never rewrites options_score,
    options_route_verdict or positive_factors - authority without G1-G4 (CLAUDE.md rule 5). Its adjusted score and
    promotion stay visible as phantom evidence (options_score_phantom_adjusted, phantom_promoted_verdict)."""
    out = dict(row)
    for k, v in payload.items():
        out[k] = v
    hard_veto = bool(payload.get("phantom_hard_veto_respected"))
    out["phantom_execution_authority"] = "NO_OVERRIDE_HARD_VETO" if hard_veto else "EVIDENCE_ONLY"
    return out


def resolve_evidence_session(repo_root: Path, run_id: str) -> Tuple[str, str]:
    path = Path(repo_root) / 'data/output/runs' / run_id / 'run_meta.json'
    if path.exists():
        meta = json.loads(path.read_text(encoding='utf-8-sig'))
        session = meta.get('session_date')
        # A present but invalid authority must not silently fall back to wall time.
        return date.fromisoformat(session).isoformat(), 'RUN_META_SESSION_DATE'
    return datetime.strptime(run_id[:8], '%Y%m%d').date().isoformat(), 'RUN_ID_DATE_FALLBACK'


def run_phantom(input_csv: Path, output_csv: Path, run_id: str, db_path: Path, repo_root: Path) -> Dict[str, Any]:
    db = PhantomDatabase(db_path=db_path, repo_root=repo_root)
    db.initialise()
    df = pd.read_csv(input_csv, low_memory=False, keep_default_na=False, na_values=[''])
    evidence_session, session_basis = resolve_evidence_session(repo_root, run_id)
    df, actuarial_receipt = wire_frame(df, Path(repo_root)/'data/output/runs'/run_id, evidence_session)
    records = df.to_dict(orient="records")

    # Finish any local index maintenance before fingerprinting quote inputs;
    # creating an index is not a change to their economic values.
    started = perf_counter()
    index_created = db.ensure_scoring_index()
    index_seconds = perf_counter() - started

    # Freeze the full candidate set and exact-session quote inputs BEFORE the
    # long history preload or scoring. Failures stay visible; never backdate
    # a receipt or grant authority when capture is unavailable.
    candidate_capture = {"status": "FAILED"}
    try:
        candidate_capture = capture_candidates(Path(repo_root)/'data/output/runs'/run_id,
            input_csv, records, run_id=run_id, session=evidence_session,
            database=db_path, score_version=SCORE_VERSION)
    except Exception as exc:
        candidate_capture = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"[:500]}
        logger.warning('PHANTOM prospective candidate capture FAILED: %s', candidate_capture['error'])

    unique_tickers = list({str(r.get("ticker") or "").upper() for r in records if r.get("ticker")})
    preload_started = perf_counter()
    db.preload_tickers(unique_tickers, as_of=evidence_session)
    preload_seconds = perf_counter() - preload_started

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
        if payload.get('phantom_score') is not None:
            scores.append(float(payload['phantom_score']))
        rows_out.append(apply_payload(record, payload))

    prediction_capture = {"status": "BLOCKED_NO_CANDIDATE_CAPTURE"}
    if candidate_capture['status'] == 'CAPTURED':
        try:
            prediction_capture = capture_predictions(Path(repo_root)/'data/output/runs'/run_id,
                candidate_capture, [payload for _, payload in score_payloads], run_id=run_id)
        except Exception as exc:
            prediction_capture = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"[:500]}
            logger.warning('PHANTOM prospective publication capture FAILED: %s', prediction_capture['error'])

    profit_shadow = {"status": "BLOCKED_NO_VERIFIED_PUBLICATION"}
    if prediction_capture['status'] == 'CAPTURED':
        try:
            from contracts.phantom_profit_shadow import evening_cycle
            profit_shadow = evening_cycle(repo_root, run_id, candidate_capture, database=db_path)
            if profit_shadow['status'] not in ('COMPLETE_SHADOW_CAPTURE', 'DISABLED'):
                logger.warning('PHANTOM profit shadow capture incomplete: %s', profit_shadow['status'])
        except Exception as exc:
            profit_shadow = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"[:500]}
            logger.warning('PHANTOM profit shadow FAILED: %s', profit_shadow['error'])

    db.batch_write_phantom_scores(run_id, score_payloads)

    out_df = pd.DataFrame(rows_out)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_csv, index=False)
    summary = {
        "run_id": run_id,
        "rows_processed": len(out_df),
        "score_version": SCORE_VERSION,
        "score_calibrated": False,
        "promotions_enabled": PROMOTIONS_ENABLED,
        "prospective_candidate_capture": candidate_capture,
        "prospective_prediction_capture": prediction_capture,
        "option_profit_shadow": profit_shadow,
        "prospective_capture_state": "CAPTURED" if prediction_capture['status']=='CAPTURED' else "INCOMPLETE",
        "promoted_count": promoted,
        "hard_veto_respected_count": hard_vetoes,
        "unscored_rows": len(rows_out) - len(scores),
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "score_mean": sum(scores) / len(scores) if scores else None,
        "output_csv": str(output_csv),
        "evidence_session": evidence_session,
        "evidence_session_basis": session_basis,
        "actuarial_handoff": actuarial_receipt,
        "preload_seconds": round(preload_seconds, 3),
        "elapsed_seconds": round(perf_counter() - started, 3),
        "provider_calls": 0,
        "scoring_index_created": index_created,
        "scoring_index_seconds": round(index_seconds, 3),
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

