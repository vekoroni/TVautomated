"""G4 history correction for option_contract_observations (ACK approved 17 Oct 2026).

Design: Enhancements/options_valuation_review/G4_HESTON_GREEKS_ROOT_CAUSE_AND_DESIGN_20261017.md §5.5 / §8.3(a).

Before G4, Options Intelligence overwrote the selected contract's provider delta with the Heston ATM-variance model
delta, registered that contract as a LIVE_OPTION dataset and the store recorded it as a MARKETDATA observation. This
tool appends one correction per affected observation, append-only: the provider delta from the MarketData option
chain the selected quote came from (scope extra source_chain_dataset_id), matched by contract and identical quote
timestamp. Anything that cannot be matched exactly is skipped and counted, never guessed.

Default is a dry run (no writes). --apply writes the corrections, one registered CORRECTION run per corrected run (<run_id>_G4).
No provider calls. Do not run while a pipeline is writing the control plane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.contracts import DatasetType, parse_utc  # noqa: E402
from canonical_data.option_liquidity_lifecycle import MARKETDATA_PROVIDER, OptionLiquidityLifecycleStore  # noqa: E402
from canonical_data.registry import CanonicalRegistry  # noqa: E402

CORRECTION_REASON = "G4_MODEL_DELTA_RECORDED_AS_PROVIDER"
DEFAULT_RUN_SUFFIX = "G4"
DELTA_TOLERANCE = 1e-9
DEFAULT_REGISTRY = ROOT / "data" / "canonical" / "control_plane.sqlite"


def _symbol(value: Any) -> str:
    return str(value or "").replace(" ", "").upper()


def _chain_quotes(record) -> dict[tuple[str, str], dict]:
    """(symbol, quote time) -> provider delta, from a registered chain payload whose content hash is verified."""
    payload = Path(record.storage_uri).read_bytes()
    if hashlib.sha256(payload).hexdigest() != record.content_hash:
        raise ValueError("CHAIN_INTEGRITY_FAILED")
    rows = json.loads(payload)
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("data") or []
    quotes: dict[tuple[str, str], dict] = {}
    for quote in rows:
        at = parse_utc(quote.get("quote_timestamp_utc"))
        if at is not None:
            quotes[(_symbol(quote.get("symbol")), at.isoformat())] = {"delta": quote.get("delta")}
    return quotes


def plan_corrections(registry: CanonicalRegistry) -> tuple[list[dict], Counter]:
    """Observations recorded from a LIVE_OPTION dataset whose delta differs from the source chain's provider delta."""
    with registry.connection() as connection:
        rows = [dict(r) for r in connection.execute(
            """
            SELECT o.observation_id, o.run_id, r.session_date, o.ticker, o.contract_symbol, o.quote_as_of, o.delta,
                   d.dataset_id AS live_dataset_id, d.scope_json
            FROM option_contract_observations AS o
            JOIN dataset_registry AS d ON d.dataset_id = o.source_dataset_id
            JOIN run_registry AS r ON r.run_id = o.run_id
            WHERE d.dataset_type = 'LIVE_OPTION' AND o.supersedes_event_id IS NULL
            ORDER BY o.quote_as_of, o.observation_id
            """
        )]
        # One pass, not a correlated subquery: the supersedes index may not exist yet on the live store.
        superseded = {r[0] for r in connection.execute(
            "SELECT supersedes_event_id FROM option_contract_observations WHERE supersedes_event_id IS NOT NULL")}
    rows = [r for r in rows if r["observation_id"] not in superseded]
    planned: list[dict] = []
    skipped: Counter = Counter()
    for row in rows:
        row["chain_id"] = (json.loads(row["scope_json"]).get("extra") or {}).get("source_chain_dataset_id")
    # One chain payload in memory at a time: rows are grouped by their source chain.
    rows.sort(key=lambda r: (r["chain_id"] or "", r["quote_as_of"], r["observation_id"]))
    loaded_id: str | None = None
    loaded: Any = None
    for row in rows:
        chain_id = row["chain_id"]
        if not chain_id:
            skipped["NO_SOURCE_CHAIN_LINEAGE"] += 1
            continue
        chain = registry.get_dataset(chain_id)
        if (chain is None or chain.dataset_type is not DatasetType.OPTION_CHAIN
                or chain.provider != MARKETDATA_PROVIDER or chain.instrument_id != row["ticker"]):
            skipped["CHAIN_NOT_ADMISSIBLE"] += 1
            continue
        if chain_id != loaded_id:
            try:
                loaded = _chain_quotes(chain)
            except (OSError, ValueError):
                loaded = None
            loaded_id = chain_id
        quotes = loaded
        if quotes is None:
            skipped["CHAIN_UNREADABLE_OR_INTEGRITY_FAILED"] += 1
            continue
        quote = quotes.get((_symbol(row["contract_symbol"]), parse_utc(row["quote_as_of"]).isoformat()))
        if quote is None:
            skipped["NO_CHAIN_QUOTE_AT_QUOTE_TIME"] += 1
            continue
        provider = quote.get("delta")
        if provider is None:
            skipped["NO_PROVIDER_DELTA"] += 1
            continue
        if row["delta"] is None:
            skipped["RECORDED_DELTA_MISSING"] += 1
            continue
        if abs(float(row["delta"]) - float(provider)) <= DELTA_TOLERANCE:
            skipped["ALREADY_PROVIDER_DELTA"] += 1
            continue
        planned.append({
            "observation_id": row["observation_id"],
            "run_id": row["run_id"],
            "session_date": row["session_date"],
            "ticker": row["ticker"],
            "contract_symbol": row["contract_symbol"],
            "quote_as_of": row["quote_as_of"],
            "recorded_delta": float(row["delta"]),
            "provider_delta": float(provider),
            "chain_dataset_id": chain_id,
            "live_dataset_id": row["live_dataset_id"],
        })
    planned.sort(key=lambda p: (p["quote_as_of"], p["observation_id"]))
    return planned, skipped


def apply_corrections(store: OptionLiquidityLifecycleStore, planned: list[dict], *, run_suffix: str) -> int:
    """One correction run per corrected run (<run_id>_<suffix>): the same quote can be recorded by two runs, and the
    store's identity (thesis, run, contract, quote time) must stay unique for each correction."""
    registry = store.registry
    registered: set[str] = set()
    written = 0
    for item in planned:
        run_id = f"{item['run_id']}_{run_suffix}".upper()
        if run_id not in registered:
            with registry.connection() as connection:
                known = connection.execute("SELECT 1 FROM run_registry WHERE run_id = ?", (run_id,)).fetchone()
            if not known:
                registry.register_run(run_id, "CORRECTION", date.fromisoformat(item["session_date"]),
                                      metadata={"purpose": "G4 delta correction", "reason": CORRECTION_REASON,
                                                "corrects_run_id": item["run_id"]})
            registered.add(run_id)
        result = store.record_observation_greek_correction(
            superseded_observation_id=item["observation_id"], delta=item["provider_delta"],
            source_dataset_id=item["chain_dataset_id"], corrected_by_run_id=run_id,
            correction_reason=CORRECTION_REASON,
        )
        written += 0 if result.reused_existing else 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--run-suffix", default=DEFAULT_RUN_SUFFIX)
    parser.add_argument("--apply", action="store_true", help="write the corrections (default: dry run)")
    parser.add_argument("--report", type=Path, help="write the plan summary as JSON")
    args = parser.parse_args(argv)

    registry = CanonicalRegistry(args.registry)
    planned, skipped = plan_corrections(registry)
    errors = [abs(p["recorded_delta"] - p["provider_delta"]) for p in planned]
    summary = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "planned": len(planned),
        "skipped": dict(skipped),
        "abs_delta_error_max": max(errors) if errors else None,
        "over_0_10": sum(e > 0.10 for e in errors),
        "sessions": sorted({p["quote_as_of"][:10] for p in planned}),
    }
    if args.apply:
        store = OptionLiquidityLifecycleStore(registry)
        store.initialise()
        summary["written"] = apply_corrections(store, planned, run_suffix=args.run_suffix)
        summary["correction_runs"] = sorted({f"{p['run_id']}_{args.run_suffix}".upper() for p in planned})
    print(json.dumps(summary, indent=2))
    if args.report:
        args.report.write_text(json.dumps({**summary, "sample": planned[:25]}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
