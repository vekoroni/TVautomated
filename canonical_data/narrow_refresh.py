"""Pipeline-owned, single-call refresh of one governed Interpreter bundle.

The Interpreter can request this operation but cannot supply or import a
provider client.  The Morning/pipeline owner injects the authorised callback.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from contracts.lab_evidence_overlay import build_overlay
from contracts.quote_change_evidence import (
    compare_exact_option_quotes,
    quote_change_overlay_fields,
    quote_snapshot_from_row,
)


class NarrowRefreshError(RuntimeError):
    pass


def execute_narrow_refresh(
    bundle: Mapping[str, Any],
    *,
    fetch_current: Callable[[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Fetch exactly one selected contract and return a compatible overlay."""
    governed = dict(bundle.get("governed_record") or {})
    ticker = str(bundle.get("ticker") or "").strip().upper()
    contract = str(bundle.get("selected_contract_symbol") or "").strip().upper()
    bundle_id = str(bundle.get("bundle_id") or "").strip()
    if not ticker or not contract or not bundle_id:
        raise NarrowRefreshError("NARROW_REFRESH_IDENTITY_INCOMPLETE")
    current = dict(fetch_current(ticker, contract) or {})
    if not current:
        raise NarrowRefreshError("NARROW_REFRESH_EMPTY_RESPONSE")
    current.setdefault("current_contract_symbol", contract)
    merged = {**governed, **current}
    evidence = compare_exact_option_quotes(
        ticker=ticker,
        thesis_id=str(bundle.get("thesis_id") or ""),
        trade_idea_id=str(bundle.get("trade_idea_id") or ""),
        selected_structure_id=str(bundle.get("selected_structure_id") or ""),
        morning=quote_snapshot_from_row(governed, role="MORNING"),
        current=quote_snapshot_from_row(merged, role="CURRENT"),
    )
    overlay = build_overlay(
        run_id=str(bundle.get("run_id") or ""), ticker=ticker,
        bundle_id=bundle_id, fields=quote_change_overlay_fields(evidence),
        source="CDS_NARROW_REFRESH",
    )
    return {
        "status": "COMPLETE",
        "provider_calls_made": 1,
        "comparison_status": evidence["comparison_status"],
        "quote_change_evidence": evidence,
        "overlay": overlay,
    }


__all__ = ["NarrowRefreshError", "execute_narrow_refresh"]
