from __future__ import annotations

import ast
import math
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


def _load_functions(path: Path, names: set[str], globals_: dict[str, Any]) -> dict[str, Any]:
    """Compile selected production helpers without importing heavy pipeline dependencies."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = dict(globals_)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def _test_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or str(value).strip().lower() in {"", "nan", "none", "null", "n/a"}:
            return default
        result = float(value)
        return default if math.isnan(result) or math.isinf(result) else result
    except Exception:
        return default


class _QuoteResponse:
    def __init__(self, payload: dict, *, ok: bool = True) -> None:
        self._payload = payload
        self.ok = ok

    def json(self) -> dict:
        return self._payload


class PreEveningProductionRepairTests(unittest.TestCase):
    def _nbbo_helpers(self, session: Mock, api_key: str = "test-token") -> dict[str, Any]:
        return _load_functions(
            ROOT / "scripts" / "avshunter_options_intelligence.py",
            {"_md_first_value", "_fetch_underlying_nbbo_fields", "_resolve_underlying_nbbo_fields"},
            {
                "Any": Any,
                "Dict": Dict,
                "MARKETDATA_API_KEY": api_key,
                "MD_SESSION": session,
                "_canonical_offline_replay_enabled": lambda: False,
                "_oi_float": _test_float,
                "_quote_timestamp_utc": lambda value: f"utc:{value}" if value is not None else None,
            },
        )

    def test_nbbo_fields_are_extracted_from_marketdata_arrays(self) -> None:
        session = Mock()
        session.get.return_value = _QuoteResponse(
            {
                "s": "ok",
                "bidSize": [2400],
                "askSize": [1600],
                "updated": [1_788_000_000],
            }
        )
        fetch = self._nbbo_helpers(session)["_fetch_underlying_nbbo_fields"]

        result = fetch("TEST")

        self.assertEqual(result["l2_bid_size"], 2400.0)
        self.assertEqual(result["l2_ask_size"], 1600.0)
        self.assertEqual(result["l2_quote_source"], "MARKETDATA_STOCK_NBBO")
        self.assertEqual(result["l2_quote_timestamp_utc"], "utc:1788000000")
        session.get.assert_called_once()
        self.assertTrue(session.get.call_args.args[0].endswith("/stocks/quotes/TEST/"))

    def test_nbbo_reuses_complete_upstream_data_without_api_call(self) -> None:
        session = Mock()
        resolve = self._nbbo_helpers(session)["_resolve_underlying_nbbo_fields"]
        row = {
            "l2_bid_size": 900,
            "l2_ask_size": 1100,
            "l2_quote_source": "CANONICAL_REUSE",
            "l2_quote_timestamp_utc": "2026-08-27T15:30:00+00:00",
        }

        result = resolve("TEST", row)

        self.assertEqual(
            result,
            {
                "l2_bid_size": 900.0,
                "l2_ask_size": 1100.0,
                "l2_quote_source": "CANONICAL_REUSE",
                "l2_quote_timestamp_utc": "2026-08-27T15:30:00+00:00",
            },
        )
        session.get.assert_not_called()

    def test_nbbo_failure_is_explicit_and_non_fatal(self) -> None:
        session = Mock()
        session.get.return_value = _QuoteResponse({}, ok=False)
        fetch = self._nbbo_helpers(session)["_fetch_underlying_nbbo_fields"]

        result = fetch("TEST")

        self.assertIsNone(result["l2_bid_size"])
        self.assertIsNone(result["l2_ask_size"])
        self.assertEqual(result["l2_quote_source"], "UNAVAILABLE")

    def test_process_ticker_serialises_resolved_nbbo_fields(self) -> None:
        path = ROOT / "scripts" / "avshunter_options_intelligence.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        process_ticker = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "process_ticker"
        )
        nbbo_assignments = [
            node for node in ast.walk(process_ticker)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "nbbo_fields" for target in node.targets)
        ]
        nbbo_unpacks = [
            value
            for node in ast.walk(process_ticker)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if key is None and isinstance(value, ast.Name) and value.id == "nbbo_fields"
        ]
        invalid_result_writes = [
            node for node in ast.walk(process_ticker)
            if isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "result"
        ]

        self.assertEqual(len(nbbo_assignments), 1)
        self.assertGreaterEqual(len(nbbo_unpacks), 1)
        self.assertEqual(invalid_result_writes, [])

    def test_options_to_eil_handoff_preserves_all_nbbo_fields(self) -> None:
        source = (
            ROOT / "scripts" / "avshunter_options_intelligence.py"
        ).read_text(encoding="utf-8-sig")
        handoff_start = source.index("options_fields = [")
        handoff_end = source.index("avail_fields =", handoff_start)
        handoff_contract = source[handoff_start:handoff_end]

        for field in (
            "l2_bid_size",
            "l2_ask_size",
            "l2_quote_source",
            "l2_quote_timestamp_utc",
        ):
            with self.subTest(field=field):
                self.assertIn(repr(field), handoff_contract)

    def test_governed_us_share_classes_are_valid_package_tickers(self) -> None:
        ensure = _load_functions(
            ROOT / "scripts" / "build_packages_from_discovery.py",
            {"ensure_us_ticker_sane"},
            {},
        )["ensure_us_ticker_sane"]

        for ticker in ("BRK.A", "BRK.B", "BF.B", "HEI.A", "TEST.C"):
            with self.subTest(ticker=ticker):
                ensure(ticker)

    def test_foreign_or_malformed_dot_suffixes_remain_blocked(self) -> None:
        ensure = _load_functions(
            ROOT / "scripts" / "build_packages_from_discovery.py",
            {"ensure_us_ticker_sane"},
            {},
        )["ensure_us_ticker_sane"]

        for ticker in ("SHOP.TO", "VOD.L", "ABC.V", "BRK.B.X"):
            with self.subTest(ticker=ticker):
                with self.assertRaisesRegex(ValueError, "Universe contamination"):
                    ensure(ticker)

    def test_cds2_freshness_boundary_reproduces_and_blocks_stale_short_circuit(self) -> None:
        helpers = _load_functions(
            ROOT / "canonical_data" / "history_bridge.py",
            {"history_staleness_days", "history_date_is_fresh"},
            {
                "date": date,
                "datetime": datetime,
                "timezone": timezone,
                "DEFAULT_HISTORY_MAX_STALENESS_DAYS": 5,
            },
        )
        staleness = helpers["history_staleness_days"]
        is_fresh = helpers["history_date_is_fresh"]

        self.assertEqual(
            staleness("2026-08-21", reference_date=date(2026, 8, 27)), 6
        )
        self.assertFalse(
            is_fresh("2026-08-21", reference_date=date(2026, 8, 27))
        )
        self.assertTrue(
            is_fresh("2026-08-24", reference_date=date(2026, 8, 27))
        )

    def test_cds2_consumers_require_freshness_before_cache_reuse(self) -> None:
        discovery = (
            ROOT / "avshunter_discovery_ULTIMATE.py"
        ).read_text(encoding="utf-8-sig")
        backfill_source = (
            ROOT / "scripts" / "backfill_timeseries_into_packages.py"
        ).read_text(encoding="utf-8-sig")

        self.assertIn("canonical_history_is_fresh(canonical)", discovery)
        self.assertIn("DISCOVERY_INCREMENTAL_REFRESH", discovery)
        self.assertIn("canonical_history_is_fresh(canonical)", backfill_source)
        self.assertIn("STALE_REFRESH_REQUIRED", backfill_source)
        self.assertIn("REFRESHED_FROM_PROVIDER_TAIL", backfill_source)

    def test_systemic_backfill_failures_abort_before_vanguard(self) -> None:
        helpers = _load_functions(
            ROOT / "intelligent_orchestrator.py",
            {"_parse_backfill_counts", "_backfill_failure_is_systemic"},
            {"re": __import__("re"), "Tuple": Tuple, "Optional": Optional},
        )
        classify = helpers["_backfill_failure_is_systemic"]

        systemic, ok_count, fail_count, ratio = classify(
            "Backfilled OK   : 8\nFailed          : 1615\n"
        )
        self.assertTrue(systemic)
        self.assertEqual((ok_count, fail_count), (8, 1615))
        self.assertGreater(ratio, 0.99)

        isolated, _, _, isolated_ratio = classify(
            "Backfilled OK   : 995\nFailed          : 5\n"
        )
        self.assertFalse(isolated)
        self.assertEqual(isolated_ratio, 0.005)

        unknown, _, _, unknown_ratio = classify("partial failure without counts")
        self.assertTrue(unknown)
        self.assertIsNone(unknown_ratio)


if __name__ == "__main__":
    unittest.main()
