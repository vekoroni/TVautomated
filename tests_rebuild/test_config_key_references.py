"""P0-2 §5 test 6: every configuration key read by code exists; every registry key has a consumer.

Keys whose consumers are delivered by later Phase 0 workstreams are listed in
PENDING_CONSUMERS with the workstream; the list may only shrink.
"""

from __future__ import annotations

import ast
from pathlib import Path

from avshunter.config.adapters import load_registry

PACKAGE = Path(__file__).resolve().parents[1] / "avshunter"

PENDING_CONSUMERS = {
    "market_data.capture_panel_source": "P0-4",
    "market_data.benchmark_tickers": "P0-4",
    "market_data.capture_coverage_threshold": "P0-4",
    "market_data.history_max_staleness": "P0-4",
    "market_data.chain.from_offset": "P0-4",
    "market_data.chain.to_offset": "P0-4",
    "market_data.chain.strike_limit": "P0-4",
    "market_data.chain.min_open_interest": "P0-4",
    "market_data.daily_credit_budget": "P0-4",
    "market_data.backfill_daily_credit_cap": "P0-4",
    "market_data.provider_settlement_delay": "P0-4",
}


def _string_constants() -> set[str]:
    found: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
    return found


def test_registry_keys_have_consumers_and_referenced_keys_exist():
    registry = load_registry()
    keys = set(registry.keys)
    latest = {}
    for entry in registry.entries():
        latest[entry.config_key] = entry
    # A key whose latest version is RETIRED has, by design, no live consumer (append-only retirement).
    retired = {key for key, entry in latest.items() if entry.validation_state.value == "RETIRED"}
    constants = _string_constants()
    referenced = {c for c in constants if c in keys}
    looks_like_key = {c for c in constants if c.count(".") >= 1 and c.split(".", 1)[0] in {"run", "legacy", "market_data", "eligibility", "ranking", "valuation", "thesis", "expression", "tradeability"} and " " not in c and "/" not in c and not c.endswith(".py")}
    missing = sorted(looks_like_key - keys)
    assert not missing, f"code reads configuration keys that are not registered: {missing}"
    orphans = sorted(keys - referenced - set(PENDING_CONSUMERS) - retired)
    still_read = sorted(retired & referenced)
    assert not still_read, f"code still reads RETIRED configuration keys: {still_read}"
    assert not orphans, f"registry keys without a consumer: {orphans}"
    stale_pending = sorted(set(PENDING_CONSUMERS) & referenced)
    assert not stale_pending, f"remove from PENDING_CONSUMERS (now consumed): {stale_pending}"
