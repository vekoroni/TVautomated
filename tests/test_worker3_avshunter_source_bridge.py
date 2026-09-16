from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from worker3.domain import ContractError, Direction
from worker3.integration.avshunter_source import AvshunterSourceBridge
from worker3.integration.avshunter_source import MAX_LAB_BOOK_BYTES


RUN_ID = "20260906_213931"
SESSION = "2026-09-04"
CHAIN_CALL = "1" * 64
QUOTE_CALL = "2" * 64
CHAIN_PUT = "3" * 64
QUOTE_PUT = "4" * 64
PROFILE_CALL = "5" * 64
EXACT_CALL = "6" * 64


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SourceFixture:
    def __init__(self, root: Path):
        self.root = root
        self.run = root / "data" / "output" / "runs" / RUN_ID
        self.canonical = root / "data" / "canonical"
        self.registry = self.canonical / "control_plane.sqlite"
        self.rows = [
            self.lab_row("AAA", "CALL", CHAIN_CALL, QUOTE_CALL, "AAA261016C00010000"),
            self.lab_row("BBB", "PUT", CHAIN_PUT, QUOTE_PUT, "BBB261016P00020000"),
        ]
        self._create_registry()
        self._register_chain_quote("AAA", CHAIN_CALL, QUOTE_CALL, "AAA261016C00010000")
        self._register_chain_quote("BBB", CHAIN_PUT, QUOTE_PUT, "BBB261016P00020000")
        self._register_profile("AAA")
        self.write_run()

    @staticmethod
    def lab_row(ticker: str, direction: str, chain: str, quote: str, symbol: str) -> dict:
        return {
            "run_id": RUN_ID,
            "lab_schema_version": "lab_signal_book_v2",
            "ticker": ticker,
            "thesis_id": f"{ticker}:{direction}:{SESSION}:OLM2",
            "governed_direction": direction,
            "hold_window": "6_10d",
            "selected_structure_id": f"ECI1:{ticker}",
            "contract_symbol": symbol,
            "option_chain_dataset_id": chain,
            "selected_quote_dataset_id": quote,
            "signal_price": 10.0 if direction == "CALL" else 20.0,
            "structural_target": 12.0 if direction == "CALL" else 17.0,
            "invalidation_price": 9.0 if direction == "CALL" else 22.0,
            "trigger_primary": "RANGE_BREAK_EARLY",
            "trigger_quality": "SINGLE",
            "trigger_score": 1.5,
            "thesis_state": "VALID_THESIS_TRIGGER_PENDING",
            "liquidity_state": "REVIEWABLE_SPREAD",
            "monetisability_state": "MONETISABLE",
            "monetisability_target_profit_pct": 50.0,
            "contract_bid": 0.5,
            "contract_ask": 0.6,
            "contract_mid": 0.55,
            "contract_delta": 0.3 if direction == "CALL" else -0.3,
            "contract_iv": 0.5,
            "contract_open_interest": 100.0,
            "contract_volume": 10.0,
            "sector_etf": "XLE" if ticker == "AAA" else "XLI",
            "industry": "ENERGY" if ticker == "AAA" else "TRANSPORT_TRAVEL",
        }

    def _create_registry(self):
        self.canonical.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.registry)
        con.execute(
            """CREATE TABLE dataset_registry (
                dataset_id TEXT PRIMARY KEY, dataset_type TEXT, instrument_id TEXT,
                session_date TEXT, scope_fingerprint TEXT, scope_json TEXT,
                provider TEXT, adjustment_convention TEXT, schema_version TEXT,
                content_hash TEXT, completeness_status TEXT, storage_uri TEXT,
                observed_at TEXT, as_of TEXT, expires_at TEXT,
                quality_flags_json TEXT, parent_dataset_ids_json TEXT,
                source_run_id TEXT, registered_at TEXT
            )"""
        )
        con.commit()
        con.close()

    def _register(self, dataset_id: str, dataset_type: str, ticker: str,
                  schema: str, payload: dict, path: Path):
        content_hash = _write_json(path, payload)
        con = sqlite3.connect(self.registry)
        con.execute(
            "INSERT INTO dataset_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dataset_id, dataset_type, ticker, SESSION, "scope", "{}", "MARKETDATA",
                "RAW", schema, content_hash, "COMPLETE", str(path),
                "2026-09-04T20:00:00Z", "2026-09-04T20:00:00Z", None,
                "[]", "[]", RUN_ID, "2026-09-06T22:00:00Z",
            ),
        )
        con.commit()
        con.close()

    def _register_chain_quote(self, ticker: str, chain: str, quote: str, symbol: str):
        chain_path = self.canonical / "options" / ticker / f"{chain}.json"
        self._register(chain, "OPTION_CHAIN", ticker, "option_chain_v2", [{"ticker": ticker}], chain_path)
        direction = "CALL" if "C" in symbol[-15:-8] else "PUT"
        quote_payload = {
            "ticker": ticker,
            "recommended_contract": symbol,
            "source_chain_dataset_id": chain,
            "contract_quote_timestamp_utc": "2026-09-04T20:00:00Z",
            "contract_bid": 0.5,
            "contract_ask": 0.6,
            "contract_mid": 0.55,
            "contract_delta": 0.3 if direction == "CALL" else -0.3,
            "contract_gamma": 0.02,
            "contract_theta": -0.01,
            "contract_vega": 0.03,
            "contract_iv": 0.5,
            "contract_oi": 100.0,
            "contract_volume": 10.0,
            "contract_spread_pct": 0.1818181818,
            "contract_quote_quality": "TWO_SIDED",
        }
        quote_path = self.canonical / "live_options" / ticker / f"{quote}.json"
        self._register(quote, "LIVE_OPTION", ticker, "selected_option_quote_v1", quote_payload, quote_path)

    def _register_profile(self, ticker: str):
        payload = {
            "ticker": ticker,
            "observed_at_utc": "2026-09-04T19:55:00Z",
            "poc": 10.1,
            "value_area_high": 10.4,
            "value_area_low": 9.8,
            "profile_type": "SINGLE_DISTRIBUTION",
            "quality": "FIVE_MINUTE_ESTIMATED",
            "uncertainty_score": 0.1,
            "usable": True,
        }
        path = self.canonical / "payloads" / "market_profile" / ticker / f"{PROFILE_CALL}.json"
        self._register(PROFILE_CALL, "MARKET_STRUCTURE", ticker, "market_profile_evidence_v1", payload, path)

    def register_exact_quote(
        self,
        *,
        dataset_id: str = EXACT_CALL,
        source_run_id: str = RUN_ID,
        session: str = "2026-09-05",
    ) -> None:
        row = self.rows[0]
        payload = {
            "ask": row["contract_ask"],
            "bid": row["contract_bid"],
            "delta": row["contract_delta"],
            "gamma": 0.02,
            "implied_vol": row["contract_iv"],
            "mid": row["contract_mid"],
            "open_interest": row["contract_open_interest"],
            "quote_quality": "TWO_SIDED",
            "quote_timestamp_utc": f"{session}T14:00:00Z",
            "run_id": source_run_id,
            "spread_pct": 0.1818181818,
            "symbol": row["contract_symbol"],
            "theta": -0.01,
            "thesis_id": row["thesis_id"],
            "underlying": row["ticker"],
            "vega": 0.03,
            "volume": row["contract_volume"],
        }
        path = self.canonical / "exact_options" / row["ticker"] / f"{dataset_id}.json"
        content_hash = _write_json(path, payload)
        con = sqlite3.connect(self.registry)
        con.execute(
            "INSERT INTO dataset_registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dataset_id, "EXACT_OPTION_QUOTE", row["ticker"], session,
                "scope", "{}", "MARKETDATA", "RAW_OPTION_CONTRACT",
                "exact_option_quote_v2", content_hash, "COMPLETE", str(path),
                f"{session}T14:00:01Z", f"{session}T14:00:00Z", None,
                "[]", "[]", source_run_id, f"{session}T14:00:02Z",
            ),
        )
        con.commit()
        con.close()
        row["selected_quote_dataset_id"] = dataset_id

    def write_run(self, *, status="COMPLETED"):
        meta = {
            "run_meta_schema_version": "run_meta_v2",
            "canonical_run_id": RUN_ID,
            "run_status": status,
            "status_updated_at_utc": "2026-09-06T23:55:59Z",
            "dynamic_plan": {
                "pipeline_run_id": RUN_ID,
                "invocation_id": "inv_fixture",
                "last_completed_session": SESSION,
                "evidence_cutoff_utc": "2026-09-06T21:39:31Z",
                "execution_authority_ceiling": "EOD_PREPARED",
                "plan_hash": "a" * 64,
                "resolved_action": "BUILD_THESIS",
            },
        }
        manifest = {
            "run_id": RUN_ID,
            "created_at_utc": "2026-09-07T00:00:00Z",
            "pipeline_technical_health": "PASS",
            "fatal_flags": [],
        }
        lab = {
            "lab_schema_version": "lab_signal_book_v2",
            "run_id": RUN_ID,
            "created_at_utc": "2026-09-06T23:55:37Z",
            "candidate_count": len(self.rows),
            "source_manifest": {},
            "source_errors": [],
            "reconciliation": {"input_rows": len(self.rows), "output_rows": len(self.rows)},
            "rows": self.rows,
        }
        _write_json(self.run / "run_meta.json", meta)
        _write_json(self.run / "final_run_manifest.json", manifest)
        _write_json(self.run / "intelligence_lab" / f"final_opportunity_book_{RUN_ID}.json", lab)

    def write_macro_context(self, *, session: str = SESSION, authority: str = "MACRO_ADVISORY_ONLY"):
        packet = {
            "schema_version": "interpreter_macro_context_v1",
            "packet_id": "MACRO:fixture",
            "source_fingerprint": "fixture-source-fingerprint",
            "created_at_utc": "2026-09-06T23:50:00Z",
            "as_of_utc": "2026-09-04T20:00:00Z",
            "session_date": session,
            "authority_statement": authority,
            "conflicts": [],
            "quality": "AVAILABLE",
            "freshness": "CURRENT",
            "source_manifest": {
                "core_macro": {"status": "AVAILABLE", "sha256": "6" * 64},
                "bond_macro": {"status": "AVAILABLE", "sha256": "7" * 64},
                "auction_calendar": {"status": "AVAILABLE", "sha256": "8" * 64},
                "enrichment_delta": {"status": "AVAILABLE", "sha256": "9" * 64},
                "us_money_index": {"status": "AVAILABLE", "sha256": "a" * 64},
            },
            "core_macro": {
                "rates_impulse": "RESTRICTIVE_HOLD",
                "extras": {"gex": {"regime": "POSITIVE_GAMMA"}},
            },
            "bond": {"yield_curve": {
                "yield_2y": 4.1, "yield_10y": 4.4, "spread_bps": 30,
                "curve_move_1d": "BEAR_FLATTENING", "curve_state": "FLAT",
                "stale_flag": False,
            }},
            "enrichment": {"as_of_utc": "2026-09-04T20:00:00Z"},
            "sector_rotation": {"sector_bias_map": {
                "ENERGY": "TAILWIND",
                "INDUSTRIALS": "HEADWIND",
            }},
            "ticker_advisories": {
                "AAA": [{
                    "role": "BENEFICIARY",
                    "theme_id": "OIL_STABILITY",
                    "directional_pressure": "CALL_FAVOURED",
                    "event_guards": ["OIL_SHOCK"],
                    "confirmation_required": ["ENERGY RELATIVE STRENGTH HOLDS"],
                    "invalidation_conditions": ["ENERGY RELATIVE STRENGTH BREAKS"],
                }],
                "BBB": [{
                    "role": "VULNERABLE",
                    "theme_id": "RATES_PRESSURE",
                    "directional_pressure": "PUT_FAVOURED",
                    "event_guards": ["RATE_REVERSAL"],
                    "confirmation_required": ["TRANSPORT WEAKNESS PERSISTS"],
                    "invalidation_conditions": ["TRANSPORT RECOVERS"],
                }],
            },
            "us_money_index": {"advisory_context": {"cross_asset": {
                "equities": {
                    "capital_flow_state": "SELECTIVE_CONCENTRATION",
                    "last_us_cash_session": {"breadth_state": "NEGATIVE"},
                },
                "rates": {"state": "RESTRICTIVE_STABLE"},
                "oil_inflation": {"state": "CALM", "wti_usd": 70.0},
                "volatility": {"state": "CONTAINED", "vix_spot": 15.0},
                "credit": {"credit_alert": False},
            }, "forward_triggers": {"event_guards": ["FOMC_SURPRISE"]}},
            "sector_routing": {
                "CALL": {"ENERGY": {"alignment": "ALIGNED", "reason": "USMI_ENERGY_CALL"}},
                "PUT": {"INDUSTRIALS": {"alignment": "ALIGNED", "reason": "USMI_INDUSTRIALS_PUT"}},
            },
            "unverified_metrics": [],
            "generated_at_utc": "2026-09-04T20:00:00Z",
            "state": {"risk_off_transition": False}},
        }
        return _write_json(
            self.run / "interpreter" / "interpreter_macro_context.json", packet
        )


class AvshunterSourceBridgeTests(unittest.TestCase):
    def test_v4_book_and_rows_prepare_both_directions_and_stamp_true_version(self):
        path = self.fixture.run / "intelligence_lab" / f"final_opportunity_book_{RUN_ID}.json"
        document = json.loads(path.read_text())
        document["lab_schema_version"] = "lab_signal_book_v4"
        for row in document["rows"]:
            row["lab_schema_version"] = "lab_signal_book_v4"
        _write_json(path, document)
        prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual([e.status for e in prepared.entries], ["EVIDENCE_PREPARED", "EVIDENCE_PREPARED"])
        for entry in prepared.entries:
            observation = next(o for o in entry.bundle.observations if o.field == "signal_price")
            self.assertEqual(observation.calculation_version, "lab_signal_book_v4")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = SourceFixture(Path(self.temp.name))
        self.bridge = AvshunterSourceBridge(self.fixture.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_call_and_put_prepare_without_provider_or_writer(self):
        prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual([e.status for e in prepared.entries], ["EVIDENCE_PREPARED", "EVIDENCE_PREPARED"])
        self.assertEqual(prepared.entries[0].bundle.identity.direction, Direction.CALL)
        self.assertEqual(prepared.entries[1].bundle.identity.direction, Direction.PUT)
        self.assertEqual(prepared.entries[0].bundle.identity.planned_hold_sessions, 10)
        self.assertEqual(prepared.summary()["provider_requests"], 0)
        self.assertEqual(prepared.summary()["production_writes"], 0)
        self.assertEqual(prepared.summary()["market_environment_status"], "UNAVAILABLE")
        self.assertEqual(prepared.summary()["macro_ticker_context_requested"], 2)
        self.assertEqual(prepared.summary()["macro_ticker_context_invalid"], 2)
        self.assertTrue(prepared.summary()["macro_ticker_context_reconciled"])
        for entry in prepared.entries:
            fields = {observation.field for observation in entry.bundle.observations}
            self.assertIn("market_environment", fields)
            self.assertIn("macro_ticker_context", fields)
            self.assertIn("trade_plan", fields)

    def test_source_bridge_uses_finite_production_lab_book_ceiling(self):
        import worker3.integration.avshunter_source as source_module
        original = source_module.read_lab_document
        observed_limits = []

        def recording_read(*args, **kwargs):
            observed_limits.append(kwargs.get("max_bytes"))
            return original(*args, **kwargs)

        with patch.object(source_module, "read_lab_document", side_effect=recording_read):
            context, _lab, _rows, _repairs = self.bridge.load_context(RUN_ID)
        self.assertEqual(context.run_id, RUN_ID)
        self.assertEqual(observed_limits, [MAX_LAB_BOOK_BYTES])
        self.assertGreater(MAX_LAB_BOOK_BYTES, 107_710_588)
        self.assertLessEqual(MAX_LAB_BOOK_BYTES, 256_000_000)

    def test_run_frozen_macro_is_loaded_once_and_attached_to_every_ticker(self):
        expected_hash = self.fixture.write_macro_context()
        import worker3.integration.avshunter_source as source_module
        original = source_module._read_json
        macro_reads = []

        def recording_read(path):
            if path.name == "interpreter_macro_context.json":
                macro_reads.append(path)
            return original(path)

        with patch.object(source_module, "_read_json", side_effect=recording_read):
            prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual(len(macro_reads), 1)
        self.assertEqual(prepared.market_environment_status, "AVAILABLE")
        self.assertIsNone(prepared.market_environment_error)
        environments = []
        plans = []
        contexts = []
        for entry in prepared.entries:
            environment = next(o for o in entry.bundle.observations if o.field == "market_environment")
            ticker_context = next(o for o in entry.bundle.observations if o.field == "macro_ticker_context")
            plan = next(o for o in entry.bundle.observations if o.field == "trade_plan")
            self.assertEqual(environment.source_hash, expected_hash)
            self.assertEqual(environment.scope, "CONTEXT")
            self.assertEqual(ticker_context.source_hash, expected_hash)
            self.assertEqual(ticker_context.scope, "TICKER")
            environments.append(environment.value)
            contexts.append(json.loads(ticker_context.value))
            plans.append(json.loads(plan.value))
        self.assertEqual(environments[0], environments[1])
        self.assertEqual([context["ticker"] for context in contexts], ["AAA", "BBB"])
        self.assertEqual([context["governed_direction"] for context in contexts], ["CALL", "PUT"])
        self.assertTrue(all(context["applicability"]["alignment"] == "TAILWIND" for context in contexts))
        self.assertTrue(all(context["candidate_retained"] for context in contexts))
        self.assertTrue(all(context["authority"] == "ADVISORY_ONLY" for context in contexts))
        self.assertEqual([plan["ticker"] for plan in plans], ["AAA", "BBB"])
        self.assertTrue(all(plan["candidate_retained"] for plan in plans))
        self.assertTrue(all(plan["authority"] == "ADVISORY_ONLY" for plan in plans))
        self.assertEqual(prepared.summary()["macro_ticker_context_available"], 2)
        self.assertEqual(prepared.summary()["macro_ticker_context_exact_ticker"], 2)
        self.assertEqual(prepared.summary()["macro_ticker_context_sector_only"], 0)
        self.assertGreater(prepared.summary()["macro_ticker_context_bytes_total"], 0)
        self.assertEqual(prepared.summary()["macro_ticker_context_omitted_items_total"], 0)
        self.assertTrue(prepared.summary()["macro_ticker_context_reconciled"])

    def test_invalid_macro_is_disclosed_without_discarding_tickers(self):
        self.fixture.write_macro_context(authority="MACRO_DECIDES_GO")
        prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual([entry.status for entry in prepared.entries], [
            "EVIDENCE_PREPARED", "EVIDENCE_PREPARED",
        ])
        self.assertEqual(prepared.market_environment_status, "UNAVAILABLE")
        self.assertIn("not advisory-only", prepared.market_environment_error)
        for entry in prepared.entries:
            environment = next(o for o in entry.bundle.observations if o.field == "market_environment")
            ticker_context = next(o for o in entry.bundle.observations if o.field == "macro_ticker_context")
            self.assertEqual(environment.status, "UNAVAILABLE")
            self.assertIsNone(environment.value)
            self.assertEqual(ticker_context.status, "UNAVAILABLE")
        self.assertEqual(prepared.summary()["macro_ticker_context_invalid"], 2)

    def test_macro_session_mismatch_is_non_authoritative_and_disclosed(self):
        self.fixture.write_macro_context(session="2026-09-03")
        prepared = self.bridge.prepare_run(RUN_ID, tickers=("AAA",))
        self.assertEqual(prepared.entries[0].status, "EVIDENCE_PREPARED")
        self.assertIn("trading session differs", prepared.market_environment_error)

    def test_ticker_projection_failure_does_not_discard_valid_candidate(self):
        self.fixture.write_macro_context()
        path = self.fixture.run / "interpreter" / "interpreter_macro_context.json"
        packet = json.loads(path.read_text(encoding="utf-8"))
        packet["source_fingerprint"] = ""
        _write_json(path, packet)
        prepared = self.bridge.prepare_run(RUN_ID, tickers=("AAA",))
        self.assertEqual(prepared.market_environment_status, "AVAILABLE")
        self.assertEqual(prepared.entries[0].status, "EVIDENCE_PREPARED")
        context = next(
            item for item in prepared.entries[0].bundle.observations
            if item.field == "macro_ticker_context"
        )
        reason = next(
            item for item in prepared.entries[0].bundle.observations
            if item.field == "macro_ticker_context_unavailable_reason"
        )
        self.assertEqual(context.status, "UNAVAILABLE")
        self.assertIn("source identity is incomplete", reason.value)
        self.assertEqual(prepared.summary()["macro_ticker_context_invalid"], 1)
        self.assertTrue(prepared.summary()["macro_ticker_context_reconciled"])

    def test_worker_advisory_attachment_is_restart_deterministic(self):
        self.fixture.write_macro_context()
        first = self.bridge.prepare_run(RUN_ID)
        second = self.bridge.prepare_run(RUN_ID)
        self.assertEqual(
            [entry.bundle.evidence_hash for entry in first.entries],
            [entry.bundle.evidence_hash for entry in second.entries],
        )

    def test_missing_profile_is_explicit_unavailable_not_zero(self):
        entry = self.bridge.prepare_run(RUN_ID, tickers=("BBB",)).entries[0]
        obs = next(o for o in entry.bundle.observations if o.field == "completed_profile_status")
        self.assertEqual(obs.status, "UNAVAILABLE")
        self.assertIsNone(obs.value)

    def test_partial_one_sided_quote_is_preserved_as_evidence(self):
        con = sqlite3.connect(self.fixture.registry)
        con.execute(
            "UPDATE dataset_registry SET completeness_status='PARTIAL' WHERE dataset_id=?",
            (QUOTE_PUT,),
        )
        con.commit()
        con.close()
        entry = self.bridge.prepare_run(RUN_ID, tickers=("BBB",)).entries[0]
        self.assertEqual(entry.status, "EVIDENCE_PREPARED")
        completeness = next(o for o in entry.bundle.observations if o.field == "quote_dataset_completeness")
        self.assertEqual(completeness.value, "PARTIAL")

    def test_same_run_morning_exact_quote_is_normalised_and_preserved(self):
        self.fixture.register_exact_quote()
        self.fixture.write_run(status="ACCEPTED")
        entry = self.bridge.prepare_run(RUN_ID, tickers=("AAA",)).entries[0]
        self.assertEqual(entry.status, "EVIDENCE_PREPARED")
        observations = {item.field: item for item in entry.bundle.observations}
        self.assertEqual(observations["bid"].value, 0.5)
        self.assertEqual(observations["ask"].value, 0.6)
        self.assertEqual(observations["implied_volatility"].value, 0.5)
        self.assertEqual(
            observations["quote_dataset_completeness"].calculation_version,
            "exact_option_quote_v2",
        )

    def test_morning_exact_quote_from_another_run_is_isolated(self):
        self.fixture.register_exact_quote(source_run_id="ANOTHER_RUN")
        self.fixture.write_run(status="ACCEPTED")
        entry = self.bridge.prepare_run(RUN_ID, tickers=("AAA",)).entries[0]
        self.assertEqual(entry.status, "DATA_EXCEPTION")
        self.assertIn("another run", entry.reason)

    def test_morning_exact_quote_after_bundle_cutoff_is_isolated(self):
        self.fixture.register_exact_quote(session="2026-09-08")
        self.fixture.write_run(status="ACCEPTED")
        entry = self.bridge.prepare_run(RUN_ID, tickers=("AAA",)).entries[0]
        self.assertEqual(entry.status, "DATA_EXCEPTION")
        self.assertIn("outside the governed run window", entry.reason)

    def test_successful_terminal_run_states_are_eligible(self):
        for status in ("COMPLETED", "ACCEPTED"):
            with self.subTest(status=status):
                self.fixture.write_run(status=status)
                context, _lab, _rows, _repairs = self.bridge.load_context(RUN_ID)
                self.assertEqual(context.run_id, RUN_ID)

    def test_nonterminal_aborted_and_unknown_run_states_are_blocked(self):
        for status in ("IN_PROGRESS", "ABORTED", "RUNNING", ""):
            with self.subTest(status=status):
                self.fixture.write_run(status=status)
                with self.assertRaisesRegex(ContractError, "successful terminal"):
                    self.bridge.prepare_run(RUN_ID)

    def test_accepted_run_still_requires_healthy_final_manifest(self):
        manifest_path = self.fixture.run / "final_run_manifest.json"
        for technical_health, fatal_flags in (("FAIL", []), ("PASS", ["BROKEN_STAGE"])):
            with self.subTest(
                technical_health=technical_health,
                fatal_flags=fatal_flags,
            ):
                self.fixture.write_run(status="ACCEPTED")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["pipeline_technical_health"] = technical_health
                manifest["fatal_flags"] = fatal_flags
                _write_json(manifest_path, manifest)
                with self.assertRaisesRegex(ContractError, "technical-health|fatal-flag"):
                    self.bridge.prepare_run(RUN_ID)

    def test_contract_side_conflict_is_isolated(self):
        self.fixture.rows[1]["contract_symbol"] = "BBB261016C00020000"
        self.fixture.write_run()
        prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual(prepared.entries[0].status, "EVIDENCE_PREPARED")
        self.assertEqual(prepared.entries[1].status, "DATA_EXCEPTION")
        self.assertIn("contradicts governed direction", prepared.entries[1].reason)

    def test_quote_mismatch_is_isolated(self):
        self.fixture.rows[1]["contract_ask"] = 9.99
        self.fixture.write_run()
        prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual(prepared.entries[0].status, "EVIDENCE_PREPARED")
        self.assertEqual(prepared.entries[1].status, "DATA_EXCEPTION")
        self.assertIn("Lab/canonical selected quote mismatch", prepared.entries[1].reason)

    def test_payload_hash_mismatch_is_isolated(self):
        path = self.fixture.canonical / "live_options" / "BBB" / f"{QUOTE_PUT}.json"
        path.write_text("{}", encoding="utf-8")
        prepared = self.bridge.prepare_run(RUN_ID)
        self.assertEqual(prepared.entries[0].status, "EVIDENCE_PREPARED")
        self.assertEqual(prepared.entries[1].status, "DATA_EXCEPTION")
        self.assertIn("hash mismatch", prepared.entries[1].reason)

    def test_duplicate_or_noncanonical_worklist_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "duplicate"):
            self.bridge.prepare_run(RUN_ID, tickers=("AAA", "AAA"))
        with self.assertRaisesRegex(ContractError, "uppercase"):
            self.bridge.prepare_run(RUN_ID, tickers=("aaa",))

    def test_missing_contract_is_not_fabricated(self):
        row = self.fixture.rows[0]
        row["selected_structure_id"] = ""
        row["contract_symbol"] = ""
        row["selected_quote_dataset_id"] = ""
        self.fixture.write_run()
        entry = self.bridge.prepare_run(RUN_ID, tickers=("AAA",)).entries[0]
        self.assertEqual(entry.status, "EVIDENCE_PREPARED")
        self.assertIsNone(entry.bundle.identity.contract_id)
        self.assertFalse(any(o.scope == "CONTRACT" for o in entry.bundle.observations))


if __name__ == "__main__":
    unittest.main()
