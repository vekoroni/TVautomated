"""PHANTOM gamma field mechanism."""

from __future__ import annotations

import math
from typing import Any, Dict


def _float(row: Dict[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        try:
            value = row.get(name)
            if value is None or value == "":
                continue
            out = float(value)
            if math.isfinite(out):
                return out
        except Exception:
            continue
    return default


def _direction(row: Dict[str, Any]) -> str:
    value = str(row.get("primary_direction") or row.get("options_direction") or row.get("direction") or "").upper()
    if value in {"CALL", "LONG", "BUY"}:
        return "CALL"
    if value in {"PUT", "SHORT", "SELL"}:
        return "PUT"
    return "UNKNOWN"


def compute_gamma_trajectory(row: Dict[str, Any], db: Any) -> Dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    direction = _direction(row)
    gap = abs(_float(row, "gamma_flip_gap_pct", default=10.0))
    island_strength = _float(row, "gamma_island_strength_share", default=0.0)
    velocity = _float(row, "gamma_velocity_pct", default=0.0)
    contract_gamma = abs(_float(row, "contract_gamma", "gamma", default=0.0))
    oi = _float(row, "contract_oi", "open_interest", default=0.0)

    latest_rows = db.latest_chain_rows(ticker) if ticker else []
    coverage = db.scoring_coverage(ticker) if hasattr(db, 'scoring_coverage') else {'state':'UNVERIFIED'}
    qualified = [r for r in latest_rows if r.get('gamma') is not None
                 and math.isfinite(float(r['gamma'])) and float(r['gamma']) >= 0
                 and r.get('open_interest') is not None
                 and math.isfinite(float(r['open_interest'])) and float(r['open_interest']) >= 0
                 and str(r.get('side','')).lower() in {'call','put'}]
    available = bool(qualified) and coverage.get('state') == 'QUALIFIED'
    symbol = row.get('contract_symbol') or row.get('contract_occ_symbol') or row.get('option_symbol')
    selected = next((r for r in qualified if r.get('option_symbol') == symbol), None) if symbol else None
    contract_gamma = float(selected['gamma']) if selected else 0.0
    oi = float(selected['open_interest']) if selected else 0.0
    net_gex = 0.0
    if latest_rows:
        for r in qualified:
            gamma = float(r["gamma"] or 0.0)
            open_interest = float(r["open_interest"] or 0.0)
            side_sign = 1.0 if str(r["side"]).lower() == "call" else -1.0
            net_gex += gamma * open_interest * side_sign

    direction_sign = 1.0 if direction == "CALL" else (-1.0 if direction == "PUT" else 0.0)
    net_gex_sign = 1.0 if net_gex > 0 else (-1.0 if net_gex < 0 else 0.0)
    aligned = available and direction_sign != 0.0 and net_gex_sign != 0.0 and direction_sign == net_gex_sign

    proximity_score = max(0.0, 45.0 - gap * 6.0)
    island_score = min(20.0, max(0.0, island_strength * 100.0))
    velocity_score = min(15.0, abs(velocity) * 4.0)
    contract_score = min(20.0, contract_gamma * max(1.0, math.log10(max(10.0, oi))) * 100.0)
    score = proximity_score + island_score + velocity_score + contract_score
    if aligned:
        score += 10.0
    score = max(0.0, min(100.0, score))
    signed = score if direction == "CALL" else (-score if direction == "PUT" else 0.0)

    return {
        "gamma_score": round(score, 2) if available else None,
        "gamma_trajectory_signed": round(signed, 2) if available else None,
        "gamma_net_gex_proxy": round(net_gex, 4) if available else None,
        "gamma_direction_aligned": bool(aligned) if available else None,
        "gamma_evidence_available": available,
        "gamma_coverage": coverage,
    }

