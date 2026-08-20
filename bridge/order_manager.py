from __future__ import annotations

from typing import Any, Dict


def planned_order(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Return a reviewable order intent. This function does not place orders."""
    return {
        "run_id": candidate.get("run_id"),
        "ticker": candidate.get("ticker"),
        "occ_symbol": candidate.get("contract_occ_symbol") or candidate.get("occ_symbol"),
        "action": "BUY_TO_OPEN",
        "limit_reference": "MID",
        "exit_t1_price": candidate.get("exit_t1") or candidate.get("exit_t1_price"),
        "exit_t2_price": candidate.get("exit_t2") or candidate.get("exit_t2_price"),
        "exit_t3_price": candidate.get("exit_t3") or candidate.get("exit_t3_price"),
        "exit_invalidation_price": candidate.get("exit_invalidation_price"),
        "approved_size_contracts": candidate.get("approved_size_contracts"),
        "requires_manual_approval": True,
    }
