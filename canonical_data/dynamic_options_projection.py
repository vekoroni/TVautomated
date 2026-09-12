"""Read-only DOI-10 projection from canonical ranking evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from contextlib import closing
from typing import Any, Iterable, Mapping

from domain.dynamic_options_projection import (
    DynamicOptionsProjection, ProjectionState, governed_contract_identity_fields,
    unavailable_projection,
)


class DynamicOptionsProjectionResolver:
    """Resolve the latest append-only DOI assessment without mutating storage."""

    def __init__(self, database: Path | str):
        self.database = Path(database)

    @staticmethod
    def _contract(row: Mapping[str, Any]) -> str:
        return str(
            row.get("selected_contract_symbol") or row.get("contract_symbol")
            or row.get("morning_selected_contract_symbol") or ""
        ).strip().upper().replace("O:", "").replace(" ", "")

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def _project_row(
        self, raw: Mapping[str, Any], connection: sqlite3.Connection,
        *, tables_valid: bool,
    ) -> dict[str, Any]:
        row = dict(raw)
        governed = self._contract(row)
        identity = governed_contract_identity_fields(row, governed)
        if identity["doi_governed_contract_identity_state"] == "MISMATCH":
            row.update(DynamicOptionsProjection(
                state=ProjectionState.DATA_INCONSISTENT,
                reason="GOVERNED_CONTRACT_IDENTITY_MISMATCH",
                governed_contract_symbol=governed,
            ).to_fields())
            row.update(identity)
            return row
        if not tables_valid:
            row.update(unavailable_projection("DOI_TABLES_NOT_ACTIVATED", governed_contract=governed).to_fields())
            row.update(identity)
            return row
        thesis_id = str(row.get("thesis_id") or "").strip()
        ticker = str(row.get("ticker") or "").strip().upper()
        direction = str(row.get("governed_direction") or row.get("canonical_direction") or row.get("direction") or "").strip().upper()
        family = connection.execute(
            "SELECT * FROM doi_contract_families WHERE thesis_id=? AND ticker=? AND governed_direction=? ORDER BY evidence_cutoff_utc DESC LIMIT 1",
            (thesis_id, ticker, direction),
        ).fetchone()
        if family is None:
            projection = DynamicOptionsProjection(
                state=ProjectionState.NOT_EVALUATED, reason="NO_DOI_FAMILY_FOR_GOVERNED_THESIS",
                governed_contract_symbol=governed,
            )
            row.update(projection.to_fields())
            row.update(identity)
            return row
        ranking_row = connection.execute(
            "SELECT * FROM doi_family_rankings WHERE family_id=? ORDER BY evidence_cutoff_utc DESC LIMIT 1",
            (family["family_id"],),
        ).fetchone()
        if ranking_row is None:
            projection = DynamicOptionsProjection(
                state=ProjectionState.NOT_EVALUATED, reason="DOI_FAMILY_NOT_RANKED",
                family_id=family["family_id"], governed_contract_symbol=governed,
                evidence_cutoff_utc=family["evidence_cutoff_utc"],
            )
            row.update(projection.to_fields())
            row.update(identity)
            return row
        ranking = json.loads(ranking_row["payload_json"])
        selected_id = str(ranking.get("selected_assessment_id") or "")
        selected = connection.execute(
            "SELECT * FROM doi_contract_assessments WHERE assessment_id=?", (selected_id,)
        ).fetchone() if selected_id else None
        selected_keys = set(selected.keys()) if selected is not None else set()
        selected_metadata = (
            json.loads(selected["metadata_json"])
            if selected is not None and "metadata_json" in selected_keys and selected["metadata_json"]
            else {}
        )
        economics_v2 = selected_metadata.get("contract_assessment_v2", {}) if isinstance(selected_metadata, Mapping) else {}
        reachability = selected_metadata.get("reachability_assessment_v1", {}) if isinstance(selected_metadata, Mapping) else {}
        preferred = str(ranking.get("selected_contract_symbol") or "").strip().upper().replace("O:", "").replace(" ", "")
        alignment = "NO_CURRENT_CONTRACT" if not governed else ("MATCH" if governed == preferred else "DIFFERENT_ADVISORY")
        alternatives = tuple({
            "rank": item.get("rank"), "contract_symbol": item.get("contract_symbol"),
            "score": item.get("score"), "score_kind": item.get("score_kind"),
            "explanation": item.get("explanation"), "selected": item.get("selected", False),
        } for item in ranking.get("ranked_contracts", []))
        calibrated = str(ranking.get("mode") or "") == "CALIBRATED_POLICY"
        projection = DynamicOptionsProjection(
            state=ProjectionState.CALIBRATED if calibrated else ProjectionState.DETERMINISTIC,
            reason=str(ranking.get("selection_reason") or "DOI_RANKING_AVAILABLE"),
            family_id=str(family["family_id"]), ranking_id=str(ranking_row["ranking_id"]),
            ranking_mode=str(ranking.get("mode") or ""), policy_id=str(ranking.get("policy_id") or ""),
            preferred_assessment_id=selected_id, preferred_contract_symbol=preferred,
            governed_contract_symbol=governed, contract_alignment=alignment,
            p_liquidity_3d=float(selected["p_liquidity_3d"]) if selected and selected["p_liquidity_3d"] is not None else None,
            p_positive_return=float(selected["p_positive_return_before_horizon"]) if selected and selected["p_positive_return_before_horizon"] is not None else None,
            p_target_before_invalidation=float(selected["p_target_before_invalidation"]) if selected and selected["p_target_before_invalidation"] is not None else None,
            model_uncertainty=float(selected["model_uncertainty"]) if selected and selected["model_uncertainty"] is not None else None,
            probability_model_id=str(selected["model_version"] or "") if selected else "",
            evidence_cutoff_utc=str(ranking["evidence_cutoff_utc"]),
            input_dataset_ids=tuple(ranking.get("input_dataset_ids") or ()), alternatives=alternatives,
        )
        row.update(projection.to_fields())
        row.update({
            "doi_ranking_score": (
                selected["ranking_score_uncalibrated"]
                if selected is not None and "ranking_score_uncalibrated" in selected_keys else None
            ),
            "doi_ranking_score_kind": selected_metadata.get("ranking_score_kind", "DETERMINISTIC_UTILITY") if selected else "",
            "doi_calibration_state": selected_metadata.get("calibration_state", "NOT_AVAILABLE") if selected else "NOT_AVAILABLE",
            "doi_monetisability_state": economics_v2.get("monetisability_state"),
            "doi_monetisability_reason": economics_v2.get("monetisability_reason"),
            "doi_convexity_score": economics_v2.get("convexity_score"),
            "doi_convexity_label": economics_v2.get("convexity_label"),
            "doi_spread_fraction_mid": economics_v2.get("spread_fraction_mid"),
            "doi_scenarios_json": json.dumps(economics_v2.get("scenarios") or [], separators=(",", ":")),
            "doi_reach_ratio": reachability.get("reach_ratio"),
            "doi_reachable_target_spot": reachability.get("reachable_target_spot"),
            "doi_assessment_calculation_version": (
                selected["calculation_version"]
                if selected is not None and "calculation_version" in selected_keys else ""
            ),
        })
        row.update(identity)
        return row

    def project_row(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        return self.project_rows((raw,))[0]

    def project_rows(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        source = [dict(row) for row in rows]
        if not self.database.is_file():
            output = []
            for row in source:
                governed = self._contract(row)
                identity = governed_contract_identity_fields(row, governed)
                projection = DynamicOptionsProjection(
                    state=ProjectionState.DATA_INCONSISTENT,
                    reason="GOVERNED_CONTRACT_IDENTITY_MISMATCH",
                    governed_contract_symbol=governed,
                ) if identity["doi_governed_contract_identity_state"] == "MISMATCH" else unavailable_projection(
                    "CANONICAL_DOI_STORE_MISSING", governed_contract=governed
                )
                output.append({**row, **projection.to_fields(), **identity})
            return output
        uri = self.database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            required = {"doi_contract_families", "doi_contract_assessments", "doi_family_rankings"}
            valid = required <= self._tables(connection)
            return [self._project_row(row, connection, tables_valid=valid) for row in source]
