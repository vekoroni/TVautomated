"""In-memory package built by reference (AVS-PKG-002 P2).

A package is a claim about what a run saw. This module makes that claim by citation: it
composes the SAME three owners that write the on-disk package (the package builder, the
macro injector and the canonical backfill) over the sources the run manifest cites, without
writing anything to disk. The result must equal the stored package except declared
wall-clock stamps and the stored package's stale data-contract annotation (finding PKG-F1),
which is what `tests/test_vanguard_reference_input_p2.py` checks.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd

from canonical_data.historical_prices import HistoricalPriceDatabase
from canonical_data.history_bridge import canonical_history_is_fresh, database_path as history_database_path
from contracts.macro_enrichment_delta import (
    find_macro_enrichment_delta, load_macro_enrichment_delta, merge_macro_enrichment_delta,
)
from scripts.backfill_timeseries_into_packages import attach_canonical_bars
from scripts.build_packages_from_discovery import (
    PackageMeta, build_package, dedupe_discovery_rows_by_ticker, enforce_data_contract,
    locate_macro_snapshot, read_discovery_csv,
)
from scripts.data_contract_validator import DataContractValidator
from scripts.inject_macro_into_packages import inject_macro_into_package
from scripts.macro_quant_packet import build_macro_quant_packet

from .canonical_manifest import MANIFEST_FILENAME

#: Keys (dotted paths) that legitimately differ between the stored package and the thin one.
#: Wall-clock stamps, plus the stored package's stale DCV annotation (PKG-F1): the thin
#: package carries the verdict the validator gives over the bars it actually holds.
DECLARED_STAMP_KEYS = frozenset({
    "bar_data_days_old",
    "data_failure",
    "data_contract.dcv_valid", "data_contract.dcv_reason", "data_contract.dcv_confidence",
    "data_contract.dcv_bars", "data_contract.dcv_last_bar",
    "truth_packet.<stamp>",
    "<post_vanguard_patch>",
})
_STAMP_SUFFIXES = ("_utc", "_at", "timestamp")
#: Blocks that later Evening phases patch INTO the stored package after Vanguard has read it
#: (trap engine 5.5, actuarial 8.5, trigger layer 8.6, market profiles). At Vanguard time they
#: hold their build-time values, which is what the thin package carries.
POST_VANGUARD_PATCH_PREFIXES = ("actuarial.", "tle.", "tle", "triggers.", "triggers", "eligible_for_trade",
                                "market_profile_", "data_contract.actuarial_")


@dataclass(frozen=True)
class RunReference:
    """The run-level sources a thin package is built from, loaded once per run."""
    run_dir: Path
    run_id: str
    evidence_session: date
    discovery_csv: Path
    discovery_rows: tuple[dict[str, Any], ...]
    macro_snapshot_path: Path
    macro_snapshot: dict[str, Any]
    runtime_macro_path: Path
    runtime_macro: dict[str, Any]
    enrichment_path: Path | None
    price_db_path: Path
    injected_utc: str = ""   # the injector's stamp recorded by the manifest, if any

    @property
    def ordered_tickers(self) -> list[str]:
        return [str(row.get("ticker") or "").strip().upper() for row in self.discovery_rows]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def load_run_reference(run_dir: Path | str, *, environment: Mapping[str, str] | None = None) -> RunReference:
    """Resolve the cited inputs of a run. Read-only; no provider access."""
    run_dir = Path(run_dir)
    run_id = run_dir.name
    manifest_path = run_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = _read_json(manifest_path)
    sources = manifest.get("sources") or {}
    discovery_csv = Path(str((sources.get("discovery") or {}).get("path") or ""))
    if not discovery_csv.is_file():
        raise FileNotFoundError(f"manifest discovery input missing: {discovery_csv}")
    runtime = sources.get("macro_runtime") or {}
    runtime_macro_path = Path(str(runtime.get("path") or "")) if runtime.get("status") == "PRESENT" else run_dir / "macro_snapshot.json"
    if not runtime_macro_path.is_file():
        raise FileNotFoundError(f"manifest runtime macro missing: {runtime_macro_path}")
    macro_snapshot_path, macro_snapshot = locate_macro_snapshot(None, run_dir)
    rows, _dropped = dedupe_discovery_rows_by_ticker(read_discovery_csv(discovery_csv))
    runtime_macro = _read_json(runtime_macro_path)
    enrichment_path = find_macro_enrichment_delta(runtime_macro_path, None)
    price_db = history_database_path(environment)
    return RunReference(
        run_dir=run_dir, run_id=run_id,
        evidence_session=date.fromisoformat(str(manifest.get("evidence_session"))[:10]),
        discovery_csv=discovery_csv, discovery_rows=tuple(rows),
        macro_snapshot_path=macro_snapshot_path, macro_snapshot=macro_snapshot,
        runtime_macro_path=runtime_macro_path, runtime_macro=runtime_macro,
        enrichment_path=enrichment_path, price_db_path=price_db,
        injected_utc=str(runtime.get("ingested_utc") or ""),
    )


class ThinPackageFactory:
    """Builds thin packages for one run; opens the price database once."""

    def __init__(self, reference: RunReference, *, ingested_utc: str | None = None, today: date | None = None):
        self.reference = reference
        # Injection time: explicit > the stamp the manifest recorded > now. Macro age/freshness
        # in the quant packet are judged at this instant, exactly as the on-disk injector does.
        self.ingested_utc = (ingested_utc or reference.injected_utc
                             or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.today = today or datetime.now(timezone.utc).date()
        injected_at = datetime.fromisoformat(self.ingested_utc.replace("Z", "+00:00"))
        macro = copy.deepcopy(reference.runtime_macro)
        quant = build_macro_quant_packet(macro, reference.runtime_macro_path, now=injected_at)
        macro["macro_quant_packet"] = quant
        if reference.enrichment_path is not None:
            macro = merge_macro_enrichment_delta(macro, load_macro_enrichment_delta(reference.enrichment_path))
            macro["macro_quant_packet"] = quant
        self._runtime_macro = macro
        self._runtime_quant = quant
        self._rows = {str(r.get("ticker") or "").strip().upper(): r for r in reference.discovery_rows}
        self._db = HistoricalPriceDatabase(reference.price_db_path) if reference.price_db_path.is_file() else None
        self._meta = PackageMeta(
            run_id=reference.run_id,
            as_of_utc=str(reference.macro_snapshot.get("as_of_utc") or ""),
            macro_source=str(reference.macro_snapshot_path),
            discovery_csv=str(reference.discovery_csv),
        )

    def tickers(self) -> Iterator[str]:
        yield from self.reference.ordered_tickers

    def build(self, ticker: str) -> dict[str, Any]:
        ticker = ticker.strip().upper()
        row = self._rows.get(ticker)
        if row is None:
            raise KeyError(f"{ticker} is not in the cited discovery input")
        ref = self.reference
        # 1. the package builder, over the build-time macro snapshot (a fresh copy: it mutates)
        pkg = build_package(ticker, dict(row), copy.deepcopy(ref.macro_snapshot), self._meta)
        if not pkg.get("as_of_utc"):
            pkg["as_of_utc"] = self._meta.as_of_utc
        pkg = enforce_data_contract(pkg)   # exactly as the builder's main loop does before writing
        # 2. the macro injector, over the runtime macro the run actually used
        pkg = inject_macro_into_package(
            pkg, macro=copy.deepcopy(self._runtime_macro), macro_path=ref.runtime_macro_path,
            enrichment_path=ref.enrichment_path, ingested_utc=self.ingested_utc,
            macro_quant_packet=copy.deepcopy(self._runtime_quant), run_id=ref.run_id,
        )
        # 3. the canonical backfill, bars up to the evidence session
        pkg.setdefault("data_contract", {}).update({
            "evidence_session_date": ref.evidence_session.isoformat(),
            "evidence_state": "COMPLETED_SESSION",
            "session_authority_version": "SESSION_AUTHORITY_V1",
        })
        frame = self._db.read(ticker, end_date=ref.evidence_session) if self._db is not None else pd.DataFrame()
        # The backfill attaches canonical bars only when they are fresh at the evidence session and
        # long enough; otherwise the package stays bar-less (the manifest already records why).
        # Same rule here, so Vanguard's data-contract gate behaves identically in both modes.
        fresh = (
            not frame.empty
            and len(frame) >= DataContractValidator.MIN_BARS
            and canonical_history_is_fresh(frame, reference_date=ref.evidence_session)
            and pd.to_datetime(frame["date"]).max().date() == ref.evidence_session
        )
        if fresh:
            actuarial = pkg.get("actuarial") if isinstance(pkg.get("actuarial"), dict) else None
            pkg = attach_canonical_bars(pkg, frame, actuarial_snapshot=actuarial, today=self.today)
            pkg["data_failure"] = False
        else:
            pkg["data_failure"] = True
        # The data-contract verdict is computed over what the package actually holds (PKG-F1).
        DataContractValidator.annotate(pkg)
        return pkg


def build_thin_package_from_run(run_dir: Path | str, ticker: str, *, ingested_utc: str | None = None,
                                today: date | None = None) -> dict[str, Any]:
    return ThinPackageFactory(load_run_reference(run_dir), ingested_utc=ingested_utc, today=today).build(ticker)


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}{key}."))
        return out
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        out = {}
        for index, item in enumerate(value):
            out.update(_flatten(item, f"{prefix}{index}."))
        return out
    return {prefix[:-1]: value}


def package_diff_keys(stored: Mapping[str, Any], thin: Mapping[str, Any]) -> set[str]:
    """Dotted paths whose values differ. Truth-packet time stamps collapse to one token."""
    a, b = _flatten(dict(stored)), _flatten(dict(thin))
    out = set()
    for key in set(a) | set(b):
        if a.get(key) != b.get(key):
            leaf = key.rsplit(".", 1)[-1]
            if key.startswith("truth_packet.") and leaf.endswith(_STAMP_SUFFIXES):
                out.add("truth_packet.<stamp>")
            elif key.startswith(POST_VANGUARD_PATCH_PREFIXES):
                out.add("<post_vanguard_patch>")
            else:
                out.add(key)
    return out


__all__ = [
    "DECLARED_STAMP_KEYS", "POST_VANGUARD_PATCH_PREFIXES", "RunReference", "ThinPackageFactory", "build_thin_package_from_run",
    "load_run_reference", "package_diff_keys",
]
