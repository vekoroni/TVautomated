"""Decision-path field coverage (read-only).

For each decision-path field, measures on real run outputs, per stage:
present, null %, zero %, distinct values, dominant-value share, constant flag.
Also reports defaulted-input evidence (physics_defaulted_fields) at the Vanguard stage.

Usage:
  venv\\Scripts\\python.exe Enhancements\\decision_map\\decision_map_coverage.py --run-id 20260914_214012 [--compare 20260913_143230 20260911_115904]
Outputs: Enhancements/decision_map/runs/<run_id>/field_coverage.csv, field_coverage_summary.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]

STAGES = {
    "1_discovery": "discovery/discovery_candidates_ultimate_{run}.csv",
    "2_vanguard": "vanguard/vanguard_signals.csv",
    "3_options": "options/options_intelligence_{run}.csv",
    "4_execution": "execution/execution_v3_5_{run}.csv",
    "5_morning_candidates": "morning_validation/morning_candidates_{run}.csv",
    "6_lab": "intelligence_lab/final_opportunity_book_{run}.csv",
}

# (segment, field)
FIELDS = [
    ("A_direction", "discovery_direction_preliminary"),
    ("A_direction", "direction"),
    ("A_direction", "governed_direction"),
    ("A_direction", "governed_direction_basis"),
    ("A_direction", "direction_resolution_call_score"),
    ("A_direction", "direction_resolution_put_score"),
    ("A_direction", "direction_resolution_path"),
    ("A_direction", "final_direction"),
    ("A_direction", "canonical_direction"),
    ("A_direction", "vanguard_edge_direction"),
    ("A_direction", "layer2__edge_direction"),
    ("A_direction", "directional_force"),
    ("A_direction", "relative_strength_20d"),
    ("A_direction", "catalyst_direction_bias"),
    ("B_geometry", "stock_price"),
    ("B_geometry", "entry_spot"),
    ("B_geometry", "signal_price"),
    ("B_geometry", "underlying_price"),
    ("B_geometry", "ATR_14"),
    ("B_geometry", "structural_stop"),
    ("B_geometry", "governed_invalidation_spot"),
    ("B_geometry", "invalidation_spot"),
    ("B_geometry", "invalidation_price"),
    ("B_geometry", "exit_invalidation_price"),
    ("B_geometry", "structural_target"),
    ("B_geometry", "target_spot"),
    ("B_geometry", "target_price"),
    ("B_geometry", "trigger_price"),
    ("B_geometry", "rr_underlying"),
    ("B_geometry", "expected_move_pct"),
    ("B_geometry", "garch_expected_move_11_20d"),
    ("B_geometry", "planned_hold_sessions"),
    ("C_contract", "contract_symbol"),
    ("C_contract", "strike"),
    ("C_contract", "contract_strike"),
    ("C_contract", "expiry"),
    ("C_contract", "dte"),
    ("C_contract", "contract_dte"),
    ("C_contract", "minimum_required_dte"),
    ("C_contract", "delta_band"),
    ("C_contract", "contract_delta"),
    ("C_contract", "contract_iv"),
    ("C_contract", "iv_rank"),
    ("C_contract", "ivp_label"),
    ("C_contract", "contract_bid"),
    ("C_contract", "contract_ask"),
    ("C_contract", "contract_mid"),
    ("C_contract", "contract_spread_pct"),
    ("C_contract", "spread_fraction_mid"),
    ("C_contract", "quote_freshness"),
    ("C_contract", "contract_repair_status"),
    ("C_contract", "heston_fit_error"),
    ("D_economics", "breakeven_price"),
    ("D_economics", "rr_options"),
    ("D_economics", "monetisability_state"),
    ("D_economics", "monetisability_target_profit_pct"),
    ("D_economics", "ev3_status"),
    ("D_economics", "ev3_p_target"),
    ("D_economics", "win_probability"),
    ("D_economics", "win_prob_predicted"),
    ("D_economics", "layer2__raw_prob_target_hit"),
    ("E_scores", "composite_score"),
    ("E_scores", "options_score"),
    ("E_scores", "convexity_score"),
    ("E_scores", "convexity_campaign"),
    ("E_scores", "campaign_verdict"),
    ("E_scores", "liquidity_friction_score"),
    ("E_scores", "macro_conviction_score"),
    ("E_scores", "sector_conviction_context"),
    ("E_scores", "market_energy_score"),
    ("E_scores", "force_alignment_score"),
    ("E_scores", "priority_score"),
    ("F_verdict", "tier"),
    ("F_verdict", "opportunity_tier"),
    ("F_verdict", "eil_signal_verdict"),
    ("F_verdict", "eod_candidate_status"),
    ("F_verdict", "lab_status"),
    ("F_verdict", "lab_verdict"),
    ("F_verdict", "priority_rank"),
]


def load(run_dir: Path, rel: str, run: str, cols: set) -> pd.DataFrame | None:
    path = run_dir / rel.format(run=run)
    if not path.exists():
        return None
    header = pd.read_csv(path, nrows=0).columns
    use = [c for c in header if c in cols or c == "ticker" or c == "physics_defaulted_fields"]
    return pd.read_csv(path, usecols=use, low_memory=False)


def profile(series: pd.Series) -> dict:
    n = len(series)
    raw = series.astype(str).str.strip()
    null = series.isna() | raw.str.upper().isin(["", "NAN", "NONE", "NULL"])
    num = pd.to_numeric(series, errors="coerce")
    numeric_share = num.notna().sum() / max((~null).sum(), 1)
    zero = (num == 0) & ~null
    vals = series[~null]
    distinct = vals.astype(str).nunique()
    top_share = (vals.astype(str).value_counts(normalize=True).iloc[0] if len(vals) else float("nan"))
    top_val = (vals.astype(str).value_counts().index[0] if len(vals) else "")
    return {
        "rows": n,
        "null_pct": round(null.mean() * 100, 1),
        "zero_pct": round(zero.mean() * 100, 1) if numeric_share > 0.9 else None,
        "distinct": int(distinct),
        "top_value": top_val[:40],
        "top_share_pct": round(top_share * 100, 1) if top_share == top_share else None,
        "constant": bool(len(vals) > 20 and distinct == 1),
        "near_constant": bool(len(vals) > 20 and top_share >= 0.95),
    }


def run_one(run: str) -> pd.DataFrame:
    run_dir = REPO / "data" / "output" / "runs" / run
    cols = {f for _, f in FIELDS}
    frames = {s: load(run_dir, rel, run, cols) for s, rel in STAGES.items()}
    rows = []
    for seg, field in FIELDS:
        for stage, df in frames.items():
            if df is None or field not in df.columns:
                continue
            rows.append({"run_id": run, "segment": seg, "field": field, "stage": stage, **profile(df[field])})
    out = pd.DataFrame(rows)
    # Physics defaulted inputs
    v = frames.get("2_vanguard")
    phys = {}
    if v is not None and "physics_defaulted_fields" in v.columns:
        cnt = Counter()
        for s in v["physics_defaulted_fields"].dropna():
            try:
                cnt.update(json.loads(s))
            except Exception:
                pass
        phys = {k: round(c / len(v) * 100, 1) for k, c in cnt.items()}
    out.attrs["physics_defaulted_pct"] = phys
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--compare", nargs="*", default=[])
    args = ap.parse_args()
    out_dir = REPO / "audit" / "decision_map" / "runs" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    main_df = run_one(args.run_id)
    all_runs = [main_df] + [run_one(r) for r in args.compare]
    full = pd.concat(all_runs, ignore_index=True)
    full.to_csv(out_dir / "field_coverage.csv", index=False)

    # Field never present in any stage
    present = set(main_df["field"])
    missing = [f for _, f in FIELDS if f not in present]

    # Constant across runs?
    const_runs = (full[full["constant"]].groupby(["field", "stage"])["run_id"].nunique().reset_index()
                  .rename(columns={"run_id": "runs_constant"}))

    lines = [f"# Decision-path field coverage — run {args.run_id}", ""]
    if args.compare:
        lines.append(f"Compared with: {', '.join(args.compare)}")
        lines.append("")
    lines += ["## Fields absent from every stage file", "", ", ".join(missing) or "none", ""]
    lines += ["## Constant / near-constant fields (latest run)", "",
              "| Field | Stage | Distinct | Top value | Top share % | Constant in runs |", "|---|---|---:|---|---:|---:|"]
    nc = main_df[main_df["near_constant"]]
    for r in nc.to_dict("records"):
        cr = const_runs[(const_runs.field == r["field"]) & (const_runs.stage == r["stage"])]["runs_constant"]
        lines.append(f"| {r['field']} | {r['stage']} | {r['distinct']} | {r['top_value']} | {r['top_share_pct']} | "
                     f"{int(cr.iloc[0]) if len(cr) else 0}/{len(all_runs)} |")
    lines += ["", "## Vanguard physics inputs defaulted (% of rows)", "",
              json.dumps(main_df.attrs.get("physics_defaulted_pct", {})), ""]
    lines += ["## Per-field profile across stages (latest run)", "",
              "| Segment | Field | Stage | Null % | Zero % | Distinct | Top value (share %) |", "|---|---|---|---:|---:|---:|---|"]
    for r in main_df.to_dict("records"):
        z = "" if r["zero_pct"] is None else r["zero_pct"]
        lines.append(f"| {r['segment']} | {r['field']} | {r['stage']} | {r['null_pct']} | {z} | {r['distinct']} | "
                     f"{r['top_value']} ({r['top_share_pct']}) |")
    (out_dir / "field_coverage_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[coverage] wrote {out_dir}")


if __name__ == "__main__":
    main()
