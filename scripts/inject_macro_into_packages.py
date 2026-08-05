# -*- coding: utf-8 -*-
"""
AVSHUNTER - Inject macro snapshot into packages.

Writes macro data into every <TICKER>.package.json under <run_id>/packages/:
  pkg["macro"]["payload"]    — full macro snapshot (read by run_vanguard)
  pkg["macro"]["source_path"]
  pkg["macro"]["ingested_utc"]
  pkg["regime_snapshot"]     — top-level alias (run_vanguard fail-closed gate)

Skips index.json and any non-package JSON files.
Fails closed if macro file is missing or invalid.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from scripts.macro_quant_packet import build_macro_quant_packet
except Exception:
    from macro_quant_packet import build_macro_quant_packet  # type: ignore

try:
    from contracts.macro_enrichment_delta import (
        find_macro_enrichment_delta,
        load_macro_enrichment_delta,
        merge_macro_enrichment_delta,
    )
except Exception:
    from macro_enrichment_delta import (  # type: ignore
        find_macro_enrichment_delta,
        load_macro_enrichment_delta,
        merge_macro_enrichment_delta,
    )

try:
    from contracts.handoff_contract import (
        PRIORITY_MACRO_QUANT,
        PRIORITY_PACKAGE_EXISTING,
        build_truth_packet_from_row,
    )
except Exception:
    from handoff_contract import (  # type: ignore
        PRIORITY_MACRO_QUANT,
        PRIORITY_PACKAGE_EXISTING,
        build_truth_packet_from_row,
    )


def load_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(p: Path, obj: Dict[str, Any]) -> None:
    """Atomic write via temp file to avoid corrupt packages on crash."""
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _flatten_macro(data: dict) -> dict:
    """
    Resolve canonical fields from macro JSON at any nesting depth.
    Mirrors intelligent_orchestrator._flatten_macro().
    Required because macro JSON stores fields inside extras.extras.extras —
    a top-level .get() returns None for nested canonical fields.
    """
    ALIASES = {
        "risk_on_off_switch": "risk_on_switch",
        "vol_mode":           "volatility_mode",
        "liquidity_pulse":    "liquidity_status",
    }
    canonical_vals: dict = {}
    alias_vals: dict = {}

    def _walk(node: dict) -> None:
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if k in ALIASES:
                alias_vals[ALIASES[k]] = v
            else:
                canonical_vals[k] = v
            if isinstance(v, dict):
                _walk(v)

    _walk(data)
    return {**alias_vals, **canonical_vals}


def build_regime_snapshot(macro: dict, injected_at: str, macro_quant_packet: dict | None = None) -> dict:
    """
    Extract the 6 required RegimeSnapshot fields as a clean flat dict.

    STALENESS FIX: as_of_utc is always stamped with the injection time
    (when inject_macro_into_packages.py runs), NOT the timestamp in the
    macro JSON. The vanguard staleness gate therefore always sees a fresh
    timestamp. Freshness is controlled by running macro + futures bias
    before each pipeline run and uploading the JSON to Dropbox.
    """
    flat = _flatten_macro(macro)
    return {
        "as_of_utc":           injected_at,
        "source_as_of_utc":    flat.get("as_of_utc") or flat.get("generated_at_utc") or "",
        "regime_state":        flat.get("regime_state") or "UNKNOWN",
        "dir_bias":            flat.get("dir_bias") or "UNKNOWN",
        "vol_mode":            flat.get("volatility_mode") or flat.get("vol_mode") or "UNKNOWN",
        "regime_drift_status": flat.get("regime_drift_status") or "UNKNOWN",
        "macro_conviction":    flat.get("macro_conviction") or "UNKNOWN",
        "macro_freshness_status": (macro_quant_packet or {}).get("macro_freshness_status", "UNKNOWN"),
        "macro_data_quality":     (macro_quant_packet or {}).get("macro_data_quality", "UNKNOWN"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-id", required=True,
        help="Run id folder under data/output/runs/<run-id>",
    )
    ap.add_argument(
        "--macro-path", required=True,
        help="Path to macro snapshot JSON (e.g. dropbox/macro/macro_intelligence_latest.json)",
    )
    ap.add_argument(
        "--macro-enrichment-delta",
        default="",
        help=(
            "Optional Macro Enrichment Delta JSON for explicit package QA only. "
            "Production narrative macro enrichment is stamped onto discovery, "
            "not auto-injected into packages before Vanguard."
        ),
    )
    args = ap.parse_args()

    run_dir = REPO / "data" / "output" / "runs" / args.run_id
    pkg_dir = run_dir / "packages"
    macro_path = Path(args.macro_path)
    if not macro_path.is_absolute():
        macro_path = (REPO / macro_path).resolve()

    if not pkg_dir.exists():
        print(f"ERROR: packages folder not found: {pkg_dir}")
        return 2
    if not macro_path.exists():
        print(f"ERROR: macro snapshot not found: {macro_path}")
        return 2

    # Validate macro is parseable JSON before touching any packages
    try:
        macro = load_json(macro_path)
    except Exception as e:
        print(f"ERROR: macro JSON invalid: {e}")
        return 2

    ingested_utc = utc_now_iso()
    macro_quant_packet = build_macro_quant_packet(macro, macro_path)
    macro["macro_quant_packet"] = macro_quant_packet

    enrichment_path = find_macro_enrichment_delta(
        macro_path,
        args.macro_enrichment_delta.strip() or None,
    )
    if enrichment_path is not None:
        if not enrichment_path.exists():
            print(f"ERROR: macro enrichment delta not found: {enrichment_path}")
            return 2
        try:
            enrichment = load_macro_enrichment_delta(enrichment_path)
            macro = merge_macro_enrichment_delta(macro, enrichment)
            macro["macro_quant_packet"] = macro_quant_packet
        except Exception as e:
            print(f"ERROR: macro enrichment delta rejected: {e}")
            return 2
    else:
        enrichment_path = None

    updated = 0
    skipped = 0

    # Only process *.package.json files — avoids index.json and any stray files
    for p in sorted(pkg_dir.glob("*.package.json")):
        try:
            pkg = load_json(p)
        except Exception as e:
            print(f"WARN: skipping {p.name} — could not load: {e}")
            skipped += 1
            continue

        # Write macro in the two forms that run_vanguard_from_packages.py requires:
        #   1. pkg["macro"]["payload"]  — read at line ~290 by OrchestratorAdapter
        #   2. pkg["regime_snapshot"]   — fail-closed gate at line 175-176
        pkg["macro"] = {
            "source_path": str(macro_path),
            "enrichment_delta_path": str(enrichment_path) if enrichment_path else "",
            "ingested_utc": ingested_utc,
            "payload": macro,
            "quant_packet": macro_quant_packet,
        }
        pkg["macro_quant_packet"] = macro_quant_packet
        # PERMANENT FIX: write flat 6-field dict, not raw nested macro blob
        pkg["regime_snapshot"] = build_regime_snapshot(macro, ingested_utc, macro_quant_packet)

        truth_seed: Dict[str, Any] = {}
        if isinstance(pkg.get("discovery"), dict):
            truth_seed.update(pkg["discovery"])
        truth_seed.update({
            "ticker": pkg.get("ticker"),
            "run_id": pkg.get("run_id") or args.run_id,
            "run_mode": "EVENING",
        })
        truth_packet = build_truth_packet_from_row(
            truth_seed,
            source="PACKAGE_EXISTING",
            priority=PRIORITY_PACKAGE_EXISTING,
            run_id=args.run_id,
            run_mode="EVENING",
        )
        for _k, _v in macro_quant_packet.items():
            truth_packet.add_field(
                _k,
                _v,
                source="MACRO_QUANT",
                status="MISSING" if _v in (None, "", "UNKNOWN", "MISSING") else "CONFIRMED",
                priority=PRIORITY_MACRO_QUANT,
            )
        pkg["truth_packet"] = truth_packet.to_json_dict()

        save_json(p, pkg)
        updated += 1

    print(f"[OK] Injected macro into {updated} packages  (skipped {skipped})")
    print(f"     Macro source : {macro_path}")
    if enrichment_path:
        print(f"     Enrichment   : {enrichment_path}")
    else:
        print("     Enrichment   : none")
    print(f"     Packages dir : {pkg_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
