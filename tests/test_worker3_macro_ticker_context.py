from __future__ import annotations

import hashlib
import json
import unittest

from worker3.domain import ContractError
from worker3.macro_ticker_context import (
    MAX_CONTEXT_BYTES,
    macro_ticker_context_diagnostics,
    project_macro_ticker_context,
)
from worker3.market_environment import project_market_environment


RUN = "20260911_170000"
SESSION = "2026-09-10"
CUTOFF = "2026-09-11T17:00:00Z"


def _hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _packet() -> dict:
    hashes = {name: str(index) * 64 for index, name in enumerate(
        ("core_macro", "bond_macro", "auction_calendar", "enrichment_delta", "us_money_index"), 1
    )}
    return {
        "schema_version": "interpreter_macro_context_v1",
        "packet_id": "MACRO:fixture",
        "source_fingerprint": "source-fixture",
        "session_date": SESSION,
        "created_at_utc": "2026-09-11T16:59:00Z",
        "as_of_utc": "2026-09-10T20:00:00Z",
        "freshness": "FRESH",
        "quality": "PARTIAL",
        "authority_statement": "MACRO_ADVISORY_ONLY",
        "conflicts": ["CURVE_LABEL_CONFLICT"],
        "source_manifest": {
            name: {"status": "EMBEDDED_RUN_SNAPSHOT", "embedded_sha256": source_hash}
            for name, source_hash in hashes.items()
        },
        "core_macro": {
            "rates_impulse": "RESTRICTIVE_HOLD",
            "extras": {"gex": {"regime": "POSITIVE_GAMMA", "data_status": "OK"}},
        },
        "bond": {
            "as_of_date": "2026-09-10",
            "yield_curve": {
                "yield_2y": 4.1,
                "yield_10y": 4.4,
                "spread_bps": 30,
                "curve_move_1d": "BEAR_FLATTENING",
                "curve_state": "FLAT",
                "as_of_date": "2026-09-08",
                "stale_flag": True,
            },
        },
        "enrichment": {"as_of_utc": "2026-09-10T06:00:00Z"},
        "sector_rotation": {
            "sector_bias_map": {
                "Energy": "TAILWIND",
                "Information Technology": "MIXED",
            },
        },
        "ticker_advisories": {
            "AAA": [{
                "theme_id": "OIL_SHOCK",
                "role": "BENEFICIARY",
                "directional_pressure": "LONG_CALL_WATCH",
                "event_guards": ["OIL_REVERSAL_GUARD"],
                "confirmation_required": ["Brent holds above the governed reference"],
                "invalidation_conditions": ["Energy leadership reverses"],
            }],
            "BBB": [{
                "theme_id": "FUEL_COST_PRESSURE",
                "role": "VULNERABLE",
                "directional_pressure": "LONG_PUT_WATCH",
                "event_guards": ["FUEL_PRESSURE_GUARD"],
            }],
        },
        "us_money_index": {
            "generated_at_utc": "2026-09-10T19:00:00Z",
            "market_data_as_of_utc": "2026-09-10T18:00:00Z",
            "unverified_metrics": ["dealer_gex"],
            "sector_routing": {
                "CALL": {
                    "ENERGY": {
                        "alignment": "ALIGNED",
                        "reason": "USMI_ENERGY_LEADERSHIP",
                    },
                },
                "PUT": {
                    "TRANSPORT_TRAVEL": {
                        "alignment": "ALIGNED",
                        "reason": "USMI_FUEL_COST_PRESSURE",
                    },
                },
            },
            "advisory_context": {
                "forward_triggers": {"event_guards": ["US_CPI_GUARD"]},
                "cross_asset": {
                    "equities": {
                        "capital_flow_state": "SELECTIVE_CONCENTRATION",
                        "last_us_cash_session": {"breadth_state": "NEGATIVE"},
                    },
                    "rates": {"state": "RESTRICTIVE_STABLE"},
                    "oil_inflation": {"state": "ACUTE_SHOCK", "wti_usd": 95.0},
                    "volatility": {"state": "CONTAINED", "vix_spot": 16.0},
                    "credit": {"credit_alert": False},
                },
            },
            "state": {"risk_off_transition": False},
        },
    }


def _row(ticker: str = "AAA", direction: str = "CALL", *, sector: str = "XLE",
         industry: str = "Energy") -> dict:
    return {
        "run_id": RUN,
        "lab_schema_version": "lab_signal_book_v2",
        "ticker": ticker,
        "governed_direction": direction,
        "sector_etf": sector,
        "industry": industry,
    }


def _project(packet: dict, row: dict):
    packet_hash = _hash(packet)
    environment = project_market_environment(
        packet=packet,
        packet_sha256=packet_hash,
        run_id=RUN,
        evidence_cutoff_utc=CUTOFF,
    )
    return project_macro_ticker_context(
        packet=packet,
        packet_sha256=packet_hash,
        market_environment=environment,
        lab_row=row,
        run_id=RUN,
        session_date=SESSION,
        evidence_cutoff_utc=CUTOFF,
    )


class MacroTickerContextTests(unittest.TestCase):
    def test_exact_call_mapping_is_typed_advisory_and_retains_candidate(self):
        context = _project(_packet(), _row())
        payload = context.to_payload()
        self.assertEqual(context.applicability_state, "EXACT_TICKER")
        self.assertEqual(context.alignment, "TAILWIND")
        self.assertIn("OIL_SHOCK", context.themes)
        self.assertIn("OIL_REVERSAL_GUARD", context.event_guards)
        self.assertTrue(context.candidate_retained)
        self.assertEqual(payload["authority"], "ADVISORY_ONLY")
        self.assertNotIn("execution_permission", json.dumps(payload))
        self.assertLess(len(json.dumps(payload).encode()), MAX_CONTEXT_BYTES)

    def test_put_uses_same_mapping_without_changing_direction(self):
        context = _project(_packet(), _row(direction="PUT"))
        self.assertEqual(context.governed_direction, "PUT")
        self.assertEqual(context.alignment, "HEADWIND")
        self.assertTrue(context.candidate_retained)

    def test_vulnerable_ticker_supports_existing_put(self):
        context = _project(
            _packet(),
            _row("BBB", "PUT", sector="XLI", industry="TRANSPORT_TRAVEL"),
        )
        self.assertEqual(context.alignment, "TAILWIND")
        self.assertIn("FUEL_COST_PRESSURE", context.themes)

    def test_exact_ticker_does_not_receive_other_ticker_evidence(self):
        context = _project(_packet(), _row())
        encoded = json.dumps(context.to_payload())
        self.assertNotIn("FUEL_COST_PRESSURE", encoded)
        self.assertNotIn("FUEL_PRESSURE_GUARD", encoded)

    def test_missing_mapping_is_unmapped_not_neutral(self):
        context = _project(
            _packet(), _row("ZZZ", "CALL", sector="UNKNOWN", industry="UNKNOWN")
        )
        self.assertEqual(context.applicability_state, "UNMAPPED")
        self.assertEqual(context.alignment, "UNMAPPED")
        self.assertTrue(context.candidate_retained)

    def test_sector_only_mapping_is_disclosed(self):
        context = _project(_packet(), _row("ZZZ", "CALL"))
        self.assertEqual(context.applicability_state, "SECTOR_ONLY")
        self.assertEqual(context.alignment, "TAILWIND")

    def test_stale_unverified_and_global_conflicts_remain_visible_without_false_ticker_conflict(self):
        context = _project(_packet(), _row())
        payload = context.to_payload()
        self.assertEqual(context.context_status, "STALE")
        self.assertIn("bond_macro", context.stale_sources)
        self.assertEqual(context.unverified_metric_count, 1)
        self.assertIn("CURVE_LABEL_CONFLICT", context.contradictions)
        bond = next(item for item in context.source_items if item.name == "bond_macro")
        self.assertEqual(bond.source_as_of, "2026-09-08")
        self.assertEqual(bond.quality, "STALE")
        self.assertEqual(payload["data_quality"]["status"], "STALE")

    def test_applicable_mapped_disagreement_is_ticker_conflicting(self):
        packet = _packet()
        packet["bond"]["yield_curve"]["stale_flag"] = False
        packet["us_money_index"]["unverified_metrics"] = []
        packet["conflicts"] = []
        packet["sector_rotation"]["sector_bias_map"]["Energy"] = "HEADWIND"
        context = _project(packet, _row())
        self.assertEqual(context.alignment, "MIXED")
        self.assertEqual(context.context_status, "CONFLICTING")
        self.assertIn("TICKER_MACRO_ALIGNMENT_MIXED", context.contradictions)

    def test_missing_values_are_not_fabricated_as_zero(self):
        packet = _packet()
        packet["core_macro"]["extras"]["gex"] = {}
        packet["us_money_index"]["advisory_context"]["cross_asset"] = {}
        packet["bond"] = {}
        packet["conflicts"] = []
        context = _project(packet, _row())
        payload = context.to_payload()
        self.assertEqual(payload["transmission"]["gex"]["state"], "UNAVAILABLE")
        self.assertNotEqual(payload["transmission"]["rates"]["state"], 0)

    def test_future_packet_fails_closed(self):
        packet = _packet()
        packet["created_at_utc"] = "2026-09-12T00:00:00Z"
        with self.assertRaisesRegex(ContractError, "later than|after"):
            _project(packet, _row())

    def test_generic_stale_source_status_is_propagated(self):
        packet = _packet()
        packet["bond"]["yield_curve"]["stale_flag"] = False
        packet["source_manifest"]["enrichment_delta"]["status"] = "STALE"
        context = _project(packet, _row())
        source = next(
            item for item in context.source_items if item.name == "enrichment_delta"
        )
        self.assertEqual(context.context_status, "STALE")
        self.assertIn("enrichment_delta", context.stale_sources)
        self.assertEqual(source.quality, "STALE")

    def test_future_nested_source_times_fail_closed(self):
        packet = _packet()
        packet["source_manifest"]["enrichment_delta"]["as_of_utc"] = (
            "2026-09-12T00:00:00Z"
        )
        with self.assertRaisesRegex(ContractError, "later than"):
            _project(packet, _row())
        packet = _packet()
        packet["us_money_index"]["market_data_as_of_utc"] = "2026-09-12T00:00:00Z"
        with self.assertRaisesRegex(ContractError, "later than"):
            _project(packet, _row())

    def test_non_advisory_packet_fails_closed(self):
        packet = _packet()
        packet["authority_statement"] = "MACRO_GRANTS_GO"
        with self.assertRaisesRegex(ContractError, "advisory-only"):
            _project(packet, _row())

    def test_packet_session_mismatch_fails_closed(self):
        packet = _packet()
        packet["session_date"] = "2026-09-09"
        packet_hash = _hash(packet)
        environment = project_market_environment(
            packet=packet, packet_sha256=packet_hash, run_id=RUN,
            evidence_cutoff_utc=CUTOFF,
        )
        with self.assertRaisesRegex(ContractError, "trading session differs"):
            project_macro_ticker_context(
                packet=packet, packet_sha256=packet_hash,
                market_environment=environment, lab_row=_row(), run_id=RUN,
                session_date=SESSION, evidence_cutoff_utc=CUTOFF,
            )

    def test_material_change_changes_context_hash(self):
        packet = _packet()
        first = _project(packet, _row()).context_hash
        packet["ticker_advisories"]["AAA"][0]["event_guards"].append("NEW_GUARD")
        second = _project(packet, _row()).context_hash
        self.assertNotEqual(first, second)

    def test_large_lists_are_compacted_deterministically_and_disclosed(self):
        packet = _packet()
        packet["ticker_advisories"]["AAA"][0]["event_guards"] = [
            f"GUARD_{index:02d}" for index in range(20)
        ]
        context = _project(packet, _row())
        self.assertEqual(len(context.event_guards), 8)
        self.assertGreater(dict(context.omitted_counts)["event_guards"], 0)
        self.assertEqual(tuple(sorted(context.event_guards)), context.event_guards)

    def test_non_directional_thesis_is_not_directionally_interpreted(self):
        context = _project(_packet(), _row(direction="STRANGLE"))
        self.assertEqual(context.governed_direction, "NON_DIRECTIONAL")
        self.assertEqual(context.alignment, "UNMAPPED")
        self.assertTrue(context.candidate_retained)

    def test_aggregate_diagnostics_reconcile_bytes_omissions_and_applicability(self):
        packet = _packet()
        packet["ticker_advisories"]["AAA"][0]["event_guards"] = [
            f"GUARD_{index:02d}" for index in range(20)
        ]
        exact = _project(packet, _row()).to_payload()
        unmapped = _project(
            packet, _row("ZZZ", "CALL", sector="UNKNOWN", industry="UNKNOWN")
        ).to_payload()
        result = macro_ticker_context_diagnostics(
            (exact, unmapped), requested=3, invalid=1
        )
        self.assertTrue(result["macro_ticker_context_reconciled"])
        self.assertEqual(result["macro_ticker_context_requested"], 3)
        self.assertEqual(result["macro_ticker_context_stale"], 2)
        self.assertEqual(result["macro_ticker_context_conflicting"], 0)
        self.assertEqual(result["macro_ticker_context_unmapped"], 0)
        self.assertEqual(result["macro_ticker_context_invalid"], 1)
        self.assertEqual(result["macro_ticker_context_exact_ticker"], 1)
        self.assertEqual(result["macro_ticker_context_applicability_unmapped"], 1)
        self.assertGreater(result["macro_ticker_context_bytes_total"], 0)
        self.assertGreater(result["macro_ticker_context_omitted_items_total"], 0)

    def test_aggregate_diagnostics_reject_population_mismatch(self):
        with self.assertRaisesRegex(ContractError, "does not reconcile"):
            macro_ticker_context_diagnostics((), requested=1, invalid=0)


if __name__ == "__main__":
    unittest.main()
