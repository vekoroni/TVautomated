from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_external_intel_review_lane import apply_external_intel_review_lane  # noqa: E402


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _macro() -> dict:
    return {
        "contract_version": "macro_contract_v1_0",
        "regime_state": "TRANSITIONAL",
        "macro_filter": "GO_SELECTIVE",
        "trigger_required": False,
        "put_gate": {"current_permission": "ALLOWED"},
        "sector_lead": ["XLK"],
    }


def _enrichment() -> dict:
    return {
        "contract_version": "macro_enrichment_delta_v1_0",
        "target_macro_contract_version": "macro_contract_v1_0",
        "packet_type": "MACRO_ENRICHMENT_DELTA",
        "merge_mode": "AUGMENT_ONLY_DO_NOT_REPLACE",
        "batch_id": "TEST",
        "source": "TEST",
        "as_of_utc": "2026-05-12T08:30:00Z",
        "report_date": "2026-05-12",
        "ticker_handoff_policy": {
            "allowed_candidate_columns": ["ticker"],
            "do_not_add_candidate_metadata_to_ticker_file": True,
        },
        "merge_controls": {
            "can_override_macro_filter": False,
            "can_change_size_multiplier": False,
            "can_change_trigger_required": False,
            "can_change_horizon_routing": False,
            "can_unblock_put_gate": False,
            "can_override_sector_lead_or_sector_avoid": False,
        },
        "theme_deltas": [
            {
                "theme_id": "AI_SUPPORT",
                "directional_pressure": "BULLISH",
                "beneficiary_universe": ["NVDA"],
                "vulnerable_universe": [],
                "context_universe": ["QQQ"],
                "event_guards": [],
                "confirmation_required": [],
                "invalidation_conditions": [],
                "merge_effect": {},
            }
        ],
        "event_guard_deltas": [],
        "macro_exposure_index_build": {
            "ticker_role_map_hint": {"VULNERABLE": ["DAL"], "CONTEXT_ONLY": ["SPY"]}
        },
        "validation_rules": {},
        "audit": {},
    }


def test_external_intel_preserves_core_membership_and_writes_advisory_lane() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        discovery = root / "discovery.csv"
        macro = root / "macro_intelligence_latest.json"
        enrichment = root / "macro_enrichment_delta.json"
        catalyst = root / "catalyst_calendar_latest.csv"

        _write_csv(
            discovery,
            [
                {"ticker": "AAPL", "precor_intent": "WAIT"},
                {"ticker": "NVDA", "precor_intent": "CALL"},
            ],
        )
        macro.write_text(json.dumps(_macro()), encoding="utf-8")
        enrichment.write_text(json.dumps(_enrichment()), encoding="utf-8")
        _write_csv(
            catalyst,
            [
                {
                    "ticker": "UPS",
                    "catalyst_type": "ENERGY_SHOCK",
                    "catalyst_status": "ASSUMPTION",
                    "catalyst_direction_bias": "LONG_PUT_WATCH",
                    "source_tier": "MARKET_NARRATIVE_DESK",
                },
                {"ticker": "CBK.DE", "catalyst_type": "EUROPE_ONLY"},
            ],
        )

        result = apply_external_intel_review_lane(
            discovery_csv=discovery,
            macro_path=macro,
            catalyst_calendar=catalyst,
            enrichment_path=enrichment,
        )
        rows = _read_csv(discovery)
        by_ticker = {row["ticker"]: row for row in rows}
        review_rows = _read_csv(Path(result["review_output"]))
        review_by_ticker = {row["ticker"]: row for row in review_rows}

    assert result["status"] == "PASS"
    assert "CBK.DE" in result["invalid_external_tickers"]
    assert set(by_ticker) == {"AAPL", "NVDA"}
    assert result["input_rows"] == result["output_rows"] == 2
    assert result["appended_forced_review_rows"] == 0
    assert result["advisory_only_rows"] == 4
    assert result["core_membership_changed"] is False
    assert by_ticker["NVDA"]["external_intel_source"] == "MACRO_ENRICHMENT"
    assert by_ticker["NVDA"]["external_intel_lane"] == "TRUE"
    assert {"UPS", "NVDA", "QQQ", "DAL", "SPY"}.issubset(review_by_ticker)
    assert review_by_ticker["UPS"]["external_intel_source"] == "CATALYST"
    assert review_by_ticker["UPS"]["external_intel_direction_bias"] == "PUT"
    assert review_by_ticker["QQQ"]["external_intel_macro_roles"]
    assert review_by_ticker["UPS"]["precor_intent"] == "WAIT"
    assert review_by_ticker["UPS"]["external_intel_stage_status"] == "ADVISORY_ONLY_NOT_DISCOVERY"


if __name__ == "__main__":
    test_external_intel_preserves_core_membership_and_writes_advisory_lane()
    print("external_intel_review_lane tests passed")
