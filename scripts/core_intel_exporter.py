#!/usr/bin/env python3
"""
CORE INTEL EXPORTER v1.0
------------------------------------------------------------
Read-only post-processing stage that converts Vanguard (and optional Options)
outputs into compact JSON artefacts for GPT CORE-INTEL (contract-driven).

Design goals:
- Non-invasive: reads existing outputs, writes new outputs only.
- Fail-open by default: exporter failure must not break the main pipeline.
- Strict mode available for QA: failures raise non-zero exit.

Inputs (minimum):
- data/output/latest.json
- data/output/runs/{run_id}/vanguard/vanguard_run_summary.json  (or supplied path)
- vanguard_signals.csv path from vanguard_run_summary.json

Outputs:
- data/output/runs/{run_id}/core_intel/core_intel_dossiers_{run_id}.json
- data/output/runs/{run_id}/core_intel/core_intel_menu_{run_id}.json
- data/output/runs/{run_id}/core_intel/core_intel_export_summary_{run_id}.json
- data/output/core_intel_latest.json (pointer)

Usage:
  python scripts/core_intel_exporter.py
  python scripts/core_intel_exporter.py --strict
  python scripts/core_intel_exporter.py --run-id 20260219_165805
  python scripts/core_intel_exporter.py --options-csv path/to/options_intelligence.csv
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except ImportError:
    pd = None


class ContractValidationError(Exception):
    pass


class InputNotFoundError(Exception):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise InputNotFoundError(f"Missing JSON: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _safe_path_from_windows(win_path: str) -> Path:
    try:
        p = Path(win_path)
        return p
    except Exception:
        return Path(win_path.replace("\\", "/"))


def _coerce_numeric(val: Any) -> Optional[float]:
    try:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if s == "" or s.lower() in {"nan", "none", "null"}:
            return None
        return float(s)
    except Exception:
        return None


def _first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


REQUIRED_VANGUARD_COLS = ["ticker", "tier"]

PREFERRED_FIELDS = [
    "tier_label", "composite_score", "phase", "phase_evidence",
    "precor_intent", "crabel_pattern", "active_regime", "compression",
    "days_to_trigger", "l2__n_observations", "l2__win_rate_20d",
    "l2__expected_value_20d", "l2__edge_status", "auction_state",
    "l1__confidence", "pm_action", "pm_score", "sector", "industry",
    # ── Added v1.1: DTE and expiry for time-stop calculations ──────────────────
    "dte", "expiry",
]

ALIASES = {
    "composite_score":         ["composite", "final_score", "score"],
    "phase_evidence":          ["phase_evidence_strength", "phase_strength"],
    "crabel_pattern":          ["crabel", "crabel_state", "compression_pattern"],
    "days_to_trigger":         ["days_to_trig", "dtt"],
    "l2__n_observations":      ["l2_n_obs", "l2__obs", "l2_observations", "n_observations"],
    "l2__win_rate_20d":        ["l2_win_rate", "l2__winrate_20d", "win_rate_20d"],
    "l2__expected_value_20d":  ["l2_ev", "l2__ev_20d", "expected_value_20d"],
    "l2__edge_status":         ["l2_edge", "edge_status", "no_edge_status"],
    "l1__confidence":          ["l1_confidence", "layer1_confidence"],
    # ── Fixes: field name mismatches between premarket_intelligence_ULTIMATE
    #    and core_intel_exporter PREFERRED_FIELDS  (added v1.1)
    "pm_action":               ["action", "premarket_action", "pm_rec"],
    "pm_score":                ["score", "premarket_score", "early_formation_score",
                                "composite_score", "wyckoff_score"],
    "compression":             ["compression_ratio", "compression_score",
                                "crabel_compression", "vol_compression"],
    # ── Additional resilience aliases for fields that have alternate names
    #    in different pipeline versions
    "l2__edge_status":         ["l2_edge", "edge_status", "no_edge_status",
                                "layer2__no_edge_reason", "layer2__failed_gate",
                                "failed_gate", "no_edge_reason", "layer2_edge_status"],
    "l1__confidence":          ["l1_confidence", "layer1_confidence",
                                "l1_conf", "layer1_conf",
                                "layer1__confidence", "layer1__l1_confidence"],
    "auction_state":           ["auction_status", "pre_auction_state",
                                "market_auction_state",
                                "layer1__auction_state", "layer2__auction_state"],
    "dte":                     ["contract_dte", "options_dte", "layer2__dte",
                                "recommended_dte"],
    "expiry":                  ["contract_expiry", "options_expiry",
                                "expiration", "expiry_date"],
    "pm_action":               ["action", "premarket_action", "pm_rec",
                                "final_recommendation", "verdict"],
}


def _resolve_col(df_cols: List[str], wanted: str) -> Optional[str]:
    if wanted in df_cols:
        return wanted
    for alt in ALIASES.get(wanted, []):
        if alt in df_cols:
            return alt
    return None


def _derive_tier(df: "pd.DataFrame") -> "pd.Series":
    """
    Derive a numeric tier column from available Vanguard signal fields when
    the pipeline does not emit an explicit 'tier' column.

    Tier logic (mirrors AVSHUNTER tier conventions):
      Tier 1  — has_edge=True  OR final_recommendation in (EXECUTE, BUY, LONG)
                OR verdict in (EXECUTE, SIGNAL)
      Tier 0  — everything else (MONITOR / OBSERVE / no edge)
    """
    import pandas as _pd

    has_edge   = pd.Series([False] * len(df), index=df.index)
    rec_col    = None
    verd_col   = None

    for c in ["layer2__has_edge", "has_edge"]:
        if c in df.columns:
            has_edge = df[c].astype(str).str.upper().isin(["TRUE", "1", "YES"])
            break

    for c in ["final_recommendation"]:
        if c in df.columns:
            rec_col = df[c].astype(str).str.upper()
            break

    for c in ["verdict"]:
        if c in df.columns:
            verd_col = df[c].astype(str).str.upper()
            break

    tier1_rec  = rec_col.isin(["EXECUTE", "BUY", "LONG", "STRONG_BUY"]) if rec_col is not None else pd.Series([False] * len(df), index=df.index)
    tier1_verd = verd_col.isin(["EXECUTE", "SIGNAL", "ARMED", "CAUTION"])          if verd_col is not None else pd.Series([False] * len(df), index=df.index)

    tier = (has_edge | tier1_rec | tier1_verd).astype(int)
    return tier


def _select_fields(df: "pd.DataFrame") -> Tuple["pd.DataFrame", List[str], Dict[str, str]]:
    warnings: List[str] = []
    colmap: Dict[str, str] = {}

    # ── Auto-derive 'tier' if the pipeline didn't emit it ──────────────────────
    if "tier" not in df.columns:
        df = df.copy()
        df["tier"] = _derive_tier(df)
        warnings.append("tier column derived from has_edge / final_recommendation / verdict (not present in source CSV)")

    df_cols = list(df.columns)
    missing_required = [c for c in REQUIRED_VANGUARD_COLS if c not in df_cols]
    if missing_required:
        raise ContractValidationError(f"Missing required columns: {missing_required}")
    selected = {"ticker": "ticker", "tier": "tier"}
    for canon in PREFERRED_FIELDS:
        actual = _resolve_col(df_cols, canon)
        if actual:
            selected[canon] = actual
            colmap[canon] = actual
        else:
            warnings.append(f"Missing optional field: {canon}")
    keep_actual = list(set(selected.values()))
    df_sel = df[keep_actual].copy()
    reverse_map = {v: k for k, v in selected.items()}
    df_sel.rename(columns=reverse_map, inplace=True)
    return df_sel, warnings, colmap


def _rank_score(row: Dict[str, Any]) -> float:
    def n(x: Any) -> float:
        v = _coerce_numeric(x)
        return float(v) if v is not None else 0.0

    l2_wr = n(row.get("l2__win_rate_20d"))
    l2_ev = n(row.get("l2__expected_value_20d"))
    comp  = n(row.get("composite_score"))
    pm    = n(row.get("pm_score"))
    l1c   = n(row.get("l1__confidence"))
    if 0.0 <= l2_wr <= 1.0:
        l2_wr = l2_wr * 100.0
    edge = str(row.get("l2__edge_status", "")).upper()
    edge_penalty = 20.0 if "NO_EDGE" in edge else 0.0
    primary = (0.40 * l2_wr + 0.20 * l2_ev + 0.20 * comp + 0.10 * l1c + 0.10 * pm) - edge_penalty

    # Options Intelligence supplement - drives ranking when l2/composite data absent
    # Ensures EXECUTE signals with high OIS always outrank STAND_DOWN signals
    ois     = n(row.get("opt__ois"))
    rr      = n(row.get("opt__rr_options"))
    verdict = str(row.get("opt__options_verdict", "")).upper()
    verdict_bonus = {"EXECUTE": 30.0, "ARMED": 15.0, "CAUTION": 5.0}.get(verdict, 0.0)
    rr_norm = max(rr, 0.0) * 10.0  # R:R 3.0 -> 30 pts
    opt_score = (0.40 * ois + 0.40 * rr_norm + 0.20 * verdict_bonus)

    # If primary actuarial score is non-zero, use it with opt as tiebreaker
    # If primary is zero (missing l2/composite), opt_score drives ranking entirely
    if primary != 0.0:
        score = primary + (opt_score * 0.10)
    else:
        score = opt_score

    return float(score)


def _pick_menu(dossiers: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Treat EXECUTE/ARMED options verdicts as Tier 1 equivalents for menu selection
    # even if the Vanguard tier column only shows 0 (no actuarial edge yet)
    def _is_tier1(d: Dict[str, Any]) -> bool:
        if str(d.get("tier")) == "1":
            return True
        verdict = str(d.get("opt__options_verdict", "")).upper()
        return verdict in ("EXECUTE", "ARMED", "CAUTION")

    t1   = [d for d in dossiers if _is_tier1(d)]
    t0   = [d for d in dossiers if not _is_tier1(d)]
    pool = t1 if len(t1) >= 3 else (t1 + t0)
    has_lane = any("lane_tag" in d and d["lane_tag"] for d in pool)
    methodology = ""
    if has_lane:
        lanes = {"MN": [], "SC": [], "CQ": []}
        for d in pool:
            lane = str(d.get("lane_tag", "")).upper().strip()
            if lane in lanes:
                lanes[lane].append(d)
        picks: List[Dict[str, Any]] = []
        for lane in ["MN", "SC", "CQ"]:
            if lanes[lane]:
                lanes[lane].sort(key=lambda x: x.get("_rank_score", 0.0), reverse=True)
                picks.append(lanes[lane][0])
        if len(picks) < 3:
            remaining = [d for d in pool if d not in picks]
            remaining.sort(key=lambda x: x.get("_rank_score", 0.0), reverse=True)
            picks.extend(remaining[:(3 - len(picks))])
        methodology = "Lane-aware selection (MN/SC/CQ) with rank-score fallback."
        selections = picks[:3]
    else:
        pool.sort(key=lambda x: x.get("_rank_score", 0.0), reverse=True)
        methodology = "Top-3 by conservative rank-score (Tier 1 preferred, then Tier 0)."
        selections = pool[:3]
    return {
        "selections": selections,
        "methodology": methodology,
        "pool_counts": {"tier1": len(t1), "tier0": len(t0), "pool": len(pool)},
    }


@dataclass
class ExportResult:
    status: str
    run_id: str
    written_files: List[str]
    warnings: List[str]
    counts: Dict[str, int]
    inputs: Dict[str, str]


def export_core_intel(
    repo_root: Path,
    run_id: Optional[str] = None,
    vanguard_summary_path: Optional[Path] = None,
    options_csv_path: Optional[Path] = None,
    macro_json_path: Optional[Path] = None,
) -> ExportResult:
    if pd is None:
        raise RuntimeError("pandas is required. Install: pip install pandas")

    data_output = repo_root / "data" / "output"
    latest_path = data_output / "latest.json"

    if run_id is None:
        latest = _read_json(latest_path)
        run_id = str(latest.get("run_id", "")).strip()
        if not run_id:
            raise ContractValidationError(f"latest.json missing run_id: {latest_path}")

    run_dir = data_output / "runs" / run_id
    if not run_dir.exists():
        raise InputNotFoundError(f"Run folder not found: {run_dir}")

    if vanguard_summary_path is None:
        candidates = [
            run_dir / "vanguard" / "vanguard_run_summary.json",
            run_dir / "vanguard_run_summary.json",
            data_output / "vanguard_run_summary.json",
        ]
        vanguard_summary_path = _first_existing(candidates)
        if vanguard_summary_path is None:
            raise InputNotFoundError("Could not locate vanguard_run_summary.json")

    v_sum = _read_json(vanguard_summary_path)

    v_csv_str = str(v_sum.get("output_csv", "")).strip()
    v_csv_path: Optional[Path] = None
    if v_csv_str:
        candidate = _safe_path_from_windows(v_csv_str)
        if candidate.exists():
            v_csv_path = candidate
        else:
            fallback = run_dir / "vanguard" / "vanguard_signals.csv"
            if fallback.exists():
                v_csv_path = fallback
            else:
                raise InputNotFoundError(
                    f"Vanguard signals CSV not found. Provided: {candidate} | Fallback: {fallback}"
                )
    else:
        fallback = run_dir / "vanguard" / "vanguard_signals.csv"
        if fallback.exists():
            v_csv_path = fallback
        else:
            raise InputNotFoundError("Vanguard summary missing output_csv and fallback missing.")

    if options_csv_path is None:
        opt_dir = run_dir / "options"
        if opt_dir.exists():
            csvs = sorted(opt_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
            likely = [p for p in csvs if "options_intelligence" in p.name.lower()]
            options_csv_path = (likely[0] if likely else (csvs[0] if csvs else None))

    if macro_json_path is None:
        macro_json_path = repo_root / "dropbox" / "macro" / "macro_intelligence_latest.json"
        if not macro_json_path.exists():
            macro_json_path = None

    df_v = pd.read_csv(v_csv_path)

    # ── Auto-join Discovery candidates CSV to recover enriched fields ──────────
    # Discovery writes fields like composite_score, phase, sector, industry,
    # active_regime, precor_intent, crabel_pattern etc. that Vanguard doesn't
    # re-emit. Left-join on ticker so all Vanguard rows are preserved.
    discovery_csv_path: Optional[Path] = None
    disc_candidates = [
        run_dir / "discovery" / "discovery_candidates.csv",
        run_dir / "discovery" / "candidates.csv",
        run_dir / "discovery" / "discovery_signals.csv",
        run_dir / "candidates.csv",
    ]
    for dc in disc_candidates:
        if dc.exists():
            discovery_csv_path = dc
            break
    if discovery_csv_path is None:
        # fallback: glob for any csv in discovery folder
        disc_dir = run_dir / "discovery"
        if disc_dir.exists():
            disc_csvs = sorted(disc_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
            if disc_csvs:
                discovery_csv_path = disc_csvs[0]

    if discovery_csv_path and discovery_csv_path.exists():
        try:
            df_disc = pd.read_csv(discovery_csv_path)
            if "ticker" in df_disc.columns:
                # Only bring in columns not already in vanguard CSV to avoid conflicts
                new_cols = [c for c in df_disc.columns if c not in df_v.columns or c == "ticker"]
                df_v = df_v.merge(df_disc[new_cols], on="ticker", how="left")
        except Exception as e:
            pass  # non-fatal, continue without discovery join

    df_sel, warn_missing_fields, _colmap = _select_fields(df_v)
    df_merged = df_sel.copy()
    warnings: List[str] = []
    warnings.extend(warn_missing_fields)

    if options_csv_path and options_csv_path.exists():
        try:
            df_o = pd.read_csv(options_csv_path)
            if "ticker" not in df_o.columns:
                warnings.append(f"Options CSV missing ticker column: {options_csv_path.name} (skipping merge)")
            else:
                opt_keep = [c for c in df_o.columns if c.lower() in {
                    "ticker", "options_verdict", "ois", "ivp", "ivp_label",
                    "gamma_flip", "call_wall", "put_wall", "rr_options",
                    "recommended_contract", "expiry", "strike", "delta",
                    "gamma", "theta", "vega", "contract_gamma",
                    "contract_mark_synthetic", "mark_synthetic",
                    "hold_label", "hold_urgency", "theta_constrained",
                    "options_direction", "options_strategy", "options_score",
                    "breakeven_pct", "theta_drag_pct", "vega_risk_pct",
                    "iv_rank", "iv_percentile", "atm_iv", "hv_30d",
                    "pcr_signal", "target_in_play", "stand_down_reason",
                }]
                if "ticker" not in opt_keep:
                    opt_keep.append("ticker")
                df_o2 = df_o[opt_keep].copy()
                for c in list(df_o2.columns):
                    if c != "ticker":
                        df_o2.rename(columns={c: f"opt__{c}"}, inplace=True)
                df_merged = df_merged.merge(df_o2, on="ticker", how="left")
        except Exception as e:
            warnings.append(f"Options merge failed (non-fatal): {e}")
    else:
        warnings.append("Options CSV not found (non-fatal); dossiers will be vanguard-only.")

    macro_obj: Optional[Dict[str, Any]] = None
    if macro_json_path and macro_json_path.exists():
        try:
            macro_obj = _read_json(macro_json_path)
        except Exception as e:
            warnings.append(f"Macro JSON read failed (non-fatal): {e}")

    dossiers: List[Dict[str, Any]] = []
    skipped = 0

    for _, r in df_merged.iterrows():
        ticker = str(r.get("ticker", "")).strip().upper()
        if not ticker:
            skipped += 1
            continue
        d: Dict[str, Any] = {
            "ticker": ticker,
            "tier": int(r.get("tier")) if str(r.get("tier")).strip().isdigit() else r.get("tier"),
        }
        for col in df_merged.columns:
            if col in {"ticker"}:
                continue
            val = r.get(col)
            try:
                if pd.isna(val):
                    val = None
            except Exception:
                pass
            d[col] = val
        d["_rank_score"] = _rank_score(d)

        # ── Near-wall pending alert (added v1.1) ───────────────────────────────
        # Surface CORE_CAMPAIGN / STAGED signals that are wall-blocked but
        # structurally strong, so the Intelligence Lab can alert on re-entry
        # rather than silently dropping them as STAND_DOWN.
        sb_vetoes   = str(d.get("sb_vetoes", "")).upper()
        sb_campaign = str(d.get("sb_campaign", "")).upper()
        sb_verdict  = str(d.get("sb_final_verdict", "")).upper()
        wall_blocked = "V2_AT_WALL" in sb_vetoes or "V2_NO_RUNWAY" in sb_vetoes
        strong_camp  = sb_campaign in ("CORE_CAMPAIGN", "STAGED")
        if wall_blocked and strong_camp and sb_verdict == "STAND_DOWN":
            d["_near_wall_pending"] = True
            d["_pending_alert"] = (
                "WALL-BLOCKED: Monitor for price pullback from wall. "
                "Re-evaluate when runway clears breakeven requirement."
            )
        else:
            d["_near_wall_pending"] = False

        dossiers.append(d)

    def tier_key(x: Dict[str, Any]) -> int:
        try:
            return int(x.get("tier", 9))
        except Exception:
            return 9

    dossiers.sort(key=lambda x: (tier_key(x), -float(x.get("_rank_score", 0.0))))
    menu = _pick_menu(dossiers)

    core_dir = run_dir / "core_intel"
    written_files: List[str] = []

    dossiers_path = core_dir / f"core_intel_dossiers_{run_id}.json"
    menu_path     = core_dir / f"core_intel_menu_{run_id}.json"
    summary_path  = core_dir / f"core_intel_export_summary_{run_id}.json"
    pointer_path  = repo_root / "data" / "output" / "core_intel_latest.json"

    dossiers_obj = {
        "meta": {
            "run_id": run_id,
            "generated_at_utc": _utc_now_iso(),
            "source": "CORE_INTEL_EXPORTER v1.1",
            "macro_attached": bool(macro_obj),
            "options_attached": bool(options_csv_path and options_csv_path.exists()),
        },
        "macro": macro_obj,
        "dossiers": dossiers,
    }

    menu_obj = {
        "meta": {
            "run_id": run_id,
            "generated_at_utc": _utc_now_iso(),
            "source": "CORE_INTEL_EXPORTER v1.1",
        },
        **menu,
    }

    counts_dict = {
        "vanguard_rows":      int(len(df_v)),
        "dossiers_written":   int(len(dossiers)),
        "skipped_rows":       int(skipped),
        "menu_size":          int(len(menu.get("selections", []))),
        # ── Added v1.1 ──────────────────────────────────────────────────────────
        "near_wall_pending":  int(sum(1 for d in dossiers if d.get("_near_wall_pending"))),
    }

    summary_obj = {
        "meta": {"run_id": run_id, "generated_at_utc": _utc_now_iso(), "status": "OK"},
        "inputs": {
            "latest_json":          str((repo_root / "data" / "output" / "latest.json").resolve()),
            "vanguard_summary_json": str(vanguard_summary_path.resolve()),
            "vanguard_signals_csv": str(v_csv_path),
            "options_csv":          str(options_csv_path) if options_csv_path else "",
            "macro_json":           str(macro_json_path) if macro_json_path else "",
        },
        "counts":   counts_dict,
        "warnings": warnings,
    }

    _write_json(dossiers_path, dossiers_obj)
    written_files.append(str(dossiers_path))
    _write_json(menu_path, menu_obj)
    written_files.append(str(menu_path))
    _write_json(summary_path, summary_obj)
    written_files.append(str(summary_path))

    pointer_obj = {
        "run_id":          run_id,
        "written_at_utc":  _utc_now_iso(),
        "core_intel_dir":  str(core_dir),
        "dossiers_file":   str(dossiers_path),
        "menu_file":       str(menu_path),
        "summary_file":    str(summary_path),
    }
    _write_json(pointer_path, pointer_obj)
    written_files.append(str(pointer_path))

    return ExportResult(
        status="OK",
        run_id=run_id,
        written_files=written_files,
        warnings=warnings,
        counts={k: int(v) for k, v in counts_dict.items()},
        inputs=summary_obj["inputs"],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate CORE-INTEL JSON artefacts (read-only exporter).")
    ap.add_argument("--repo-root",        type=str, default=None)
    ap.add_argument("--run-id",           type=str, default=None)
    ap.add_argument("--vanguard-summary", type=str, default=None)
    ap.add_argument("--options-csv",      type=str, default=None)
    ap.add_argument("--macro-json",       type=str, default=None)
    ap.add_argument("--strict",           action="store_true")
    args = ap.parse_args()

    if args.repo_root:
        repo_root = Path(args.repo_root).expanduser().resolve()
    else:
        repo_root = Path(__file__).resolve().parents[1]

    try:
        res = export_core_intel(
            repo_root=repo_root,
            run_id=args.run_id,
            vanguard_summary_path=Path(args.vanguard_summary).expanduser().resolve() if args.vanguard_summary else None,
            options_csv_path=Path(args.options_csv).expanduser().resolve() if args.options_csv else None,
            macro_json_path=Path(args.macro_json).expanduser().resolve() if args.macro_json else None,
        )
        print(f"[CORE_INTEL_EXPORTER] OK run_id={res.run_id}")
        print(f"  Written: {len(res.written_files)} files")
        if res.warnings:
            print(f"  Warnings: {len(res.warnings)} (see export summary JSON)")
        return 0
    except Exception as e:
        print(f"[CORE_INTEL_EXPORTER] FAILED: {e}", file=sys.stderr)
        if args.strict:
            return 2
        return 0


if __name__ == "__main__":
    sys.exit(main())
