from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import unittest

from worker3.domain import Direction, EvidenceBundle, Identity, Observation, ContractError
from worker3.market_environment import build_trade_plan, project_market_environment


def _packet() -> dict:
    return {
        "schema_version": "interpreter_macro_context_v1",
        "packet_id": "MACRO:fixture",
        "source_fingerprint": "source-fixture",
        "session_date": "2026-09-09",
        "as_of_utc": "2026-09-09T20:00:00Z",
        "authority_statement": "MACRO_ADVISORY_ONLY",
        "conflicts": ["CURVE_LABEL_CONFLICT"],
        "core_macro": {"rates_impulse": "RESTRICTIVE_HOLD"},
        "bond": {"yield_curve": {
            "yield_2y": 4.39, "yield_10y": 4.80, "spread_bps": 41,
            "curve_move_1d": "BEAR_STEEPENING", "curve_state": "FLAT",
            "stale_flag": True,
        }},
        "volatility": {},
        "us_money_index": {"advisory_context": {"cross_asset": {
            "equities": {
                "capital_flow_state": "SELECTIVE_AI_AND_ENERGY_CONCENTRATION",
                "small_cap_confirmation": "FAILED_LAST_US_CASH_SESSION",
                "last_us_cash_session": {
                    "breadth_state": "NEGATIVE", "sp500_pct": -0.58,
                    "sp500_decliners_to_advancers": 2.4,
                },
            },
            "rates": {"us_2y_pct": 4.39, "us_10y_pct": 4.8},
            "oil_inflation": {
                "state": "ACUTE_PERSISTENT", "wti_usd": 93.95,
                "brent_usd": 99.02, "inflation_transmission": "ACTIVE",
            },
            "volatility": {"vix_spot": 15.72, "state": "CONTAINED_ELEVATED", "panic_state": False},
            "credit": {"credit_alert": False},
        }}, "state": {"risk_off_transition": False}},
    }


def _hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _bundle(direction: Direction = Direction.CALL) -> EvidenceBundle:
    identity = Identity(
        run_id="20260909_071646", invocation_id="inv", trading_session="2026-09-09",
        ticker="AAA", thesis_id="AAA:CALL:2026-09-09", direction=direction,
        planned_hold_sessions=10,
    )
    source_hash = "a" * 64
    def obs(field, value, unit="state"):
        return Observation(
            evidence_id=f"lab:{field}", field=field, value=value, unit=unit,
            source_id="lab", source_hash=source_hash,
            observed_at="2026-09-09T20:00:00Z", available_at="2026-09-09T20:01:00Z",
            ticker="AAA",
        )
    return EvidenceBundle(identity, "2026-09-09T20:02:00Z", (
        obs("signal_price", 100.0, "USD/share"),
        obs("structural_target", 112.0, "USD/share"),
        obs("invalidation_price", 94.0, "USD/share"),
        obs("trigger_primary", "RANGE_BREAK_EARLY"),
        obs("trigger_quality", "SINGLE"),
        obs("thesis_state", "VALID_THESIS_TRIGGER_PENDING"),
    ))


class MarketEnvironmentTests(unittest.TestCase):
    def test_projects_all_four_advisory_domains(self):
        packet = _packet()
        result = project_market_environment(
            packet=packet, packet_sha256=_hash(packet), run_id="20260909_071646",
            evidence_cutoff_utc="2026-09-09T20:02:00Z",
        )
        states = {domain.domain: domain.state for domain in result.domains}
        self.assertEqual(states["EQUITY_PARTICIPATION"], "SELECTIVE_AI_AND_ENERGY_CONCENTRATION")
        self.assertEqual(states["RATES"], "RATES_PRESSURE")
        self.assertEqual(states["OIL"], "SHOCK")
        self.assertEqual(states["RISK_APPETITE"], "CAUTIOUS")
        self.assertEqual(result.authority, "ADVISORY_ONLY")
        self.assertEqual(result.contradictions, ("CURVE_LABEL_CONFLICT",))
        self.assertLess(len(json.dumps(result.to_payload()).encode()), 30_000)

    def test_missing_data_remains_unavailable(self):
        packet = _packet()
        packet["us_money_index"] = {}
        packet["bond"] = {}
        packet["core_macro"] = {}
        result = project_market_environment(
            packet=packet, packet_sha256=_hash(packet), run_id="run",
            evidence_cutoff_utc="2026-09-09T20:02:00Z",
        )
        self.assertTrue(all(domain.state == "UNAVAILABLE" for domain in result.domains))
        values = [fact.value for domain in result.domains for fact in domain.facts]
        self.assertFalse(any(type(value) in (int, float) and value == 0 for value in values))

    def test_future_macro_evidence_fails_closed(self):
        packet = _packet()
        packet["as_of_utc"] = "2026-09-10T20:00:00Z"
        with self.assertRaisesRegex(ContractError, "later than"):
            project_market_environment(
                packet=packet, packet_sha256=_hash(packet), run_id="run",
                evidence_cutoff_utc="2026-09-09T20:02:00Z",
            )

    def test_non_advisory_packet_is_rejected(self):
        packet = _packet()
        packet["authority_statement"] = "MACRO_DECIDES_GO"
        with self.assertRaisesRegex(ContractError, "advisory-only"):
            project_market_environment(
                packet=packet, packet_sha256=_hash(packet), run_id="run",
                evidence_cutoff_utc="2026-09-09T20:02:00Z",
            )

    def test_trade_plan_preserves_candidate_and_governed_levels(self):
        result = build_trade_plan(_bundle())
        self.assertTrue(result.candidate_retained)
        self.assertEqual(result.entry_posture, "TRIGGER_OBSERVED")
        self.assertEqual(result.current_reference_price, 100.0)
        self.assertEqual(result.entry_reference_price, 100.0)
        self.assertEqual(result.structural_target, 112.0)
        self.assertEqual(result.thesis_invalidation_price, 94.0)
        self.assertEqual(result.authority, "ADVISORY_ONLY")
        self.assertNotIn("execution_permission", result.to_payload())

    def test_trade_plan_does_not_discard_invalidated_or_incomplete_thesis(self):
        bundle = _bundle()
        changed = tuple(
            replace(obs, value="THESIS_INVALIDATED") if obs.field == "thesis_state" else obs
            for obs in bundle.observations
            if obs.field != "invalidation_price"
        )
        result = build_trade_plan(replace(bundle, observations=changed))
        self.assertTrue(result.candidate_retained)
        self.assertEqual(result.entry_posture, "THESIS_REQUIRES_REVIEW")
        self.assertIn("invalidation_price", result.data_gaps)


if __name__ == "__main__":
    unittest.main()
