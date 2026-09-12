"""DOI-10 trader-facing projection contract.

This domain object is deliberately advisory.  It can explain a contract-family
ranking, but it cannot remove an opportunity, change direction, invalidate a
thesis, size a position, or grant capital.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import math
import re
from typing import Any, Mapping, Sequence

from contracts.lab_evidence_overlay import (
    OVERLAY_ALLOWED_FIELDS,
    PROTECTED_AUTHORITY_FIELDS,
)


DOI_PROJECTION_VERSION = "doi-trader-projection-v1"

_MERGE_IDENTITY_FIELDS = ("run_id", "ticker", "thesis_id", "trade_idea_id")
_STRICT_PROTECTED_MATCH_FIELDS = frozenset({
    *_MERGE_IDENTITY_FIELDS,
    "selected_structure_id", "selected_contract_symbol", "selected_contract_symbols",
    "selected_quote_snapshot_id", "governed_direction", "final_direction",
    "direction", "dir_calc_version", "governed_direction_record_sha256",
    "thesis_state", "liquidity_state", "morning_transition_state",
})
_OCC = re.compile(
    r"^(?P<root>[A-Z0-9.]{1,12})(?P<expiry>\d{6})"
    r"(?P<side>[CP])(?P<strike>\d{8})$"
)


class ProjectionState(str, Enum):
    CALIBRATED = "CALIBRATED"
    DETERMINISTIC = "DETERMINISTIC_UNCALIBRATED"
    NOT_EVALUATED = "NOT_EVALUATED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_INCONSISTENT = "DATA_INCONSISTENT"


@dataclass(frozen=True, slots=True)
class DynamicOptionsProjection:
    state: ProjectionState
    reason: str
    family_id: str = ""
    ranking_id: str = ""
    ranking_mode: str = ""
    policy_id: str = ""
    preferred_assessment_id: str = ""
    preferred_contract_symbol: str = ""
    governed_contract_symbol: str = ""
    contract_alignment: str = "NOT_COMPARABLE"
    p_liquidity_3d: float | None = None
    p_positive_return: float | None = None
    p_target_before_invalidation: float | None = None
    model_uncertainty: float | None = None
    probability_model_id: str = ""
    evidence_cutoff_utc: str = ""
    input_dataset_ids: tuple[str, ...] = ()
    alternatives: tuple[Mapping[str, Any], ...] = ()
    authority: str = "ADVISORY_ONLY"
    decision_authority: str = "NONE"
    execution_authority: str = "HUMAN_ONLY"

    def __post_init__(self) -> None:
        state = self.state if isinstance(self.state, ProjectionState) else ProjectionState(str(self.state))
        object.__setattr__(self, "state", state)
        if not str(self.reason).strip():
            raise ValueError("DOI projection reason is required")
        if self.decision_authority != "NONE" or self.execution_authority != "HUMAN_ONLY":
            raise ValueError("DOI projection cannot possess trading authority")
        if self.authority != "ADVISORY_ONLY":
            raise ValueError("DOI projection must remain advisory")
        for value in (
            self.p_liquidity_3d, self.p_positive_return,
            self.p_target_before_invalidation, self.model_uncertainty,
        ):
            if value is not None and not 0.0 <= float(value) <= 1.0:
                raise ValueError("DOI probability and uncertainty values must be in [0,1]")

    def to_fields(self) -> dict[str, Any]:
        return {
            "doi_projection_version": DOI_PROJECTION_VERSION,
            "doi_projection_state": self.state.value,
            "doi_projection_reason": self.reason,
            "doi_family_id": self.family_id,
            "doi_ranking_id": self.ranking_id,
            "doi_ranking_mode": self.ranking_mode,
            "doi_policy_id": self.policy_id,
            "doi_preferred_assessment_id": self.preferred_assessment_id,
            "doi_preferred_contract_symbol": self.preferred_contract_symbol,
            "doi_governed_contract_symbol": self.governed_contract_symbol,
            "doi_contract_alignment": self.contract_alignment,
            "doi_p_liquidity_3d": self.p_liquidity_3d,
            "doi_p_positive_return": self.p_positive_return,
            "doi_p_target_before_invalidation": self.p_target_before_invalidation,
            "doi_model_uncertainty": self.model_uncertainty,
            "doi_probability_model_id": self.probability_model_id,
            "doi_evidence_cutoff_utc": self.evidence_cutoff_utc,
            "doi_input_dataset_ids_json": json.dumps(list(self.input_dataset_ids), separators=(",", ":")),
            "doi_alternatives_json": json.dumps(list(self.alternatives), separators=(",", ":"), default=str),
            "doi_authority": self.authority,
            "doi_decision_authority": self.decision_authority,
            "doi_execution_authority": self.execution_authority,
        }


def unavailable_projection(reason: str, *, governed_contract: str = "") -> DynamicOptionsProjection:
    return DynamicOptionsProjection(
        state=ProjectionState.DATA_UNAVAILABLE,
        reason=reason,
        governed_contract_symbol=governed_contract,
    )


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip().upper() not in {"", "NONE", "NULL", "NAN"}


def _normalised(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(str(item).strip().upper() for item in value), separators=(",", ":"))
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).upper()
    return str(value or "").strip().upper().replace("O:", "").replace(" ", "")


def governed_contract_identity_fields(
    row: Mapping[str, Any], governed_contract: str,
) -> dict[str, Any]:
    """Reconcile the displayed OCC identity without changing the governed row."""

    symbol = _normalised(governed_contract)
    if not symbol:
        return {
            "doi_governed_contract_identity_state": "MISSING",
            "doi_governed_contract_identity_reason": "NO_GOVERNED_CONTRACT_SYMBOL",
            "doi_governed_contract_parsed_strike": None,
            "doi_governed_contract_parsed_expiry": "",
            "doi_governed_contract_parsed_side": "",
        }
    match = _OCC.fullmatch(symbol)
    if match is None:
        return {
            "doi_governed_contract_identity_state": "MISMATCH",
            "doi_governed_contract_identity_reason": "INVALID_OCC_SYMBOL",
            "doi_governed_contract_parsed_strike": None,
            "doi_governed_contract_parsed_expiry": "",
            "doi_governed_contract_parsed_side": "",
        }
    expiry_token = match.group("expiry")
    try:
        expiry = datetime.strptime(expiry_token, "%y%m%d").date().isoformat()
    except ValueError:
        return {
            "doi_governed_contract_identity_state": "MISMATCH",
            "doi_governed_contract_identity_reason": "INVALID_OCC_EXPIRY",
            "doi_governed_contract_parsed_strike": None,
            "doi_governed_contract_parsed_expiry": "",
            "doi_governed_contract_parsed_side": "",
        }
    strike = int(match.group("strike")) / 1000.0
    side = "CALL" if match.group("side") == "C" else "PUT"
    reasons: list[str] = []
    row_strike = row.get("strike") if _has_value(row.get("strike")) else row.get("contract_strike")
    if _has_value(row_strike):
        try:
            if not math.isclose(float(row_strike), strike, rel_tol=0.0, abs_tol=0.0005):
                reasons.append("STRIKE_MISMATCH")
        except (TypeError, ValueError):
            reasons.append("STRIKE_INVALID")
    row_expiry = row.get("expiry") if _has_value(row.get("expiry")) else row.get("contract_expiry")
    if _has_value(row_expiry) and str(row_expiry).strip()[:10] != expiry:
        reasons.append("EXPIRY_MISMATCH")
    row_side = str(
        row.get("governed_direction") or row.get("canonical_direction")
        or row.get("direction") or ""
    ).strip().upper()
    if row_side in {"CALL", "PUT"} and row_side != side:
        reasons.append("SIDE_MISMATCH")
    return {
        "doi_governed_contract_identity_state": "MISMATCH" if reasons else "MATCH",
        "doi_governed_contract_identity_reason": "|".join(reasons) if reasons else "OCC_IDENTITY_RECONCILED",
        "doi_governed_contract_parsed_strike": strike,
        "doi_governed_contract_parsed_expiry": expiry,
        "doi_governed_contract_parsed_side": side,
    }


def merge_all_opportunities(
    full_rows: Sequence[Mapping[str, Any]],
    actionable_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Overlay accepted actionable evidence without shrinking membership."""
    full = [dict(row) for row in full_rows]
    by_ticker = {str(row.get("ticker") or "").strip().upper(): index for index, row in enumerate(full)}
    if "" in by_ticker or len(by_ticker) != len(full):
        raise ValueError("full opportunity book requires unique non-empty tickers")
    overlaid = 0
    rejected: list[dict[str, str]] = []
    seen_actionable: set[str] = set()
    for raw in actionable_rows:
        row = dict(raw)
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen_actionable:
            rejected.append({
                "ticker": ticker or "<MISSING>",
                "reason": "DUPLICATE_OR_EMPTY_ACTIONABLE_TICKER",
            })
            continue
        seen_actionable.add(ticker)
        if ticker not in by_ticker:
            rejected.append({"ticker": ticker, "reason": "ACTIONABLE_TICKER_ABSENT_FROM_FULL_BOOK"})
            continue
        base = full[by_ticker[ticker]]
        mismatch_fields: list[str] = []
        for field in _MERGE_IDENTITY_FIELDS:
            left, right = base.get(field), row.get(field)
            if not _has_value(left) or not _has_value(right) or _normalised(left) != _normalised(right):
                mismatch_fields.append(field)
        for field in _STRICT_PROTECTED_MATCH_FIELDS - set(_MERGE_IDENTITY_FIELDS):
            if field not in row or not _has_value(row.get(field)):
                continue
            if not _has_value(base.get(field)) or _normalised(base.get(field)) != _normalised(row.get(field)):
                mismatch_fields.append(field)
        if mismatch_fields:
            reason = "ACTIONABLE_IDENTITY_MISMATCH:" + ",".join(sorted(set(mismatch_fields)))
            rejected.append({"ticker": ticker, "reason": reason})
            base["lab_actionable_overlay_state"] = "REJECTED_IDENTITY_MISMATCH"
            base["lab_actionable_overlay_reason"] = reason
            continue

        # The complete book owns every governed/action/capital field.  The
        # accepted handoff may contribute only explicitly allow-listed evidence.
        for field in OVERLAY_ALLOWED_FIELDS:
            if field in row and field not in PROTECTED_AUTHORITY_FIELDS:
                base[field] = row[field]
        base["lab_actionable_handoff_member"] = True
        base["lab_actionable_overlay_state"] = "APPLIED"
        base["lab_actionable_overlay_reason"] = "IDENTITY_MATCHED_ALLOWLIST_ONLY"
        overlaid += 1
    for row in full:
        if row.get("lab_actionable_handoff_member") is not True:
            row["lab_actionable_handoff_member"] = False
    return full, {
        "status": "PASS" if not rejected else "PARTIAL",
        "full_opportunity_count": len(full),
        "actionable_handoff_count": len(actionable_rows),
        "actionable_rows_overlaid": overlaid,
        "actionable_rows_rejected": len(rejected),
        "overlay_exceptions": rejected,
        "population_preserved": len(full) == len(full_rows),
    }
