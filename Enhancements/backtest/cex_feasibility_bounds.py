"""CEX-9 random and hindsight-oracle feasibility bounds (never production logic)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "Enhancements" / "backtest"
ROUND4 = HERE / "solution_tournament" / "round4_end_to_end_rows.csv"
SCORES = HERE / "activity_tournament" / "s_act_model_scores.csv.gz"
RUN_MANIFEST = HERE / "solution_tournament" / "round1_input_manifest.json"
REGISTER = HERE / "SCENARIO_REGISTER_ADDENDUM_CEX_20260920.md"
OUTPUT = HERE / "contract_execution_tournament"
RESULTS = OUTPUT / "cex9_feasibility_bounds.json"
REPORT = OUTPUT / "CEX9_FEASIBILITY_BOUNDS_REPORT_20260920.md"

SEED = 20260920
CURRENT = {"E0_RECORDED", "E1_CORE", "E2_VALUE", "E3_CONVEX", "E5_DYNAMIC"}
QUANTILES = (0.01, 0.02, 0.05, 0.10, 0.20)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def band(scores: pd.DataFrame, fraction: float) -> pd.DataFrame:
    parts = []
    for _, group in scores.groupby("session", sort=False):
        parts.append(group.nlargest(max(1, int(np.ceil(len(group) * fraction))), "score"))
    return pd.concat(parts, ignore_index=True)


def describe(frame: pd.DataFrame, column: str) -> dict:
    values = frame[column].dropna()
    return {
        "n": int(len(values)), "sessions": int(frame.loc[values.index, "session"].nunique()),
        "mean": float(values.mean()) if len(values) else None,
        "median": float(values.median()) if len(values) else None,
        "hit_25": float((values >= .25).mean()) if len(values) else None,
    }


def main() -> int:
    truth = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))["run_truth"]
    excluded = {x["run_id"] for x in truth if x.get("run_condition") == "TEST" or x.get("dirty") is True}
    rows = pd.read_csv(ROUND4, low_memory=False)
    rows = rows[
        rows.direction_rule.eq("D0_CURRENT") & rows.expression.isin(CURRENT)
        & rows.instrument.eq("OPTION") & ~rows.run_id.isin(excluded)
    ].copy()
    rows.sort_values(["candidate_id", "horizon", "symbol", "expression"], inplace=True)
    rows.drop_duplicates(["candidate_id", "horizon", "symbol", "entry_session"], inplace=True)
    scores = pd.read_csv(SCORES, low_memory=False)
    rng = np.random.default_rng(SEED)
    result = {
        "state": "EXPLORATORY_ORACLE_NO_AUTHORITY", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "hashes": {"round4": sha256(ROUND4), "scores": sha256(SCORES), "register": sha256(REGISTER)},
        "warning": "Oracle uses future outcomes and is a feasibility ceiling only.", "bounds": {},
    }
    for horizon in (1, 3, 5):
        score_trial = f"S-ACT-9|H{horizon}|F50|PURGED_WALK_FORWARD"
        scored = scores[scores.trial_id == score_trial][["candidate_id", "session", "horizon", "score"]].drop_duplicates(["candidate_id", "horizon"])
        family = rows[rows.horizon == horizon]
        for fraction in QUANTILES:
            priority = band(scored, fraction)
            pool = family.merge(priority, on=["candidate_id", "session", "horizon"], how="inner")
            base_oracle = pool.loc[pool.groupby("candidate_id").base_return.idxmax().dropna().astype(int)] if pool.base_return.notna().any() else pool.iloc[0:0]
            stress_pool = pool.dropna(subset=["stress_spread_50"])
            stress_oracle = stress_pool.loc[stress_pool.groupby("candidate_id").stress_spread_50.idxmax()] if not stress_pool.empty else stress_pool
            random_means = []
            for _ in range(500):
                sampled = pool.groupby("candidate_id", group_keys=False).sample(n=1, random_state=int(rng.integers(0, 2**31 - 1)))
                random_means.append(float(sampled.base_return.mean()))
            key = f"H{horizon}|Q{int(fraction*100)}"
            result["bounds"][key] = {
                "candidate_families": int(pool.candidate_id.nunique()),
                "base_oracle": describe(base_oracle, "base_return"),
                "spread50_oracle": describe(stress_oracle, "stress_spread_50"),
                "random_contract_mean_p05": float(np.quantile(random_means, .05)) if random_means else None,
                "random_contract_mean_p50": float(np.quantile(random_means, .50)) if random_means else None,
                "random_contract_mean_p95": float(np.quantile(random_means, .95)) if random_means else None,
            }
    # Hindsight ceiling across both contract and exit horizon. The priority score
    # remains the frozen H1 purged S-ACT score; outcomes are used only by oracle.
    h1_scores = scores[
        scores.trial_id == "S-ACT-9|H1|F50|PURGED_WALK_FORWARD"
    ][["candidate_id", "session", "score"]].drop_duplicates("candidate_id")
    result["path_bounds"] = {}
    for fraction in QUANTILES:
        priority = band(h1_scores, fraction)
        pool = rows.merge(priority[["candidate_id"]], on="candidate_id", how="inner")
        usable = pool.dropna(subset=["base_return"])
        oracle = usable.loc[usable.groupby("candidate_id").base_return.idxmax()] if not usable.empty else usable
        stressed = pool.dropna(subset=["stress_spread_50"])
        stress_oracle = stressed.loc[stressed.groupby("candidate_id").stress_spread_50.idxmax()] if not stressed.empty else stressed
        result["path_bounds"][f"Q{int(fraction*100)}"] = {
            "contract_and_exit_oracle": describe(oracle, "base_return"),
            "spread50_contract_and_exit_oracle": describe(stress_oracle, "stress_spread_50"),
        }
    RESULTS.write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# CEX-9 Contract-Family Feasibility Bounds — 2026-09-20", "",
        "**State:** hindsight diagnostic only; no production authority", "",
        "| Band | Families | Oracle ask→bid | Oracle spread+50 | Random median |", "|---|---:|---:|---:|---:|",
    ]
    pct = lambda value: "—" if value is None else f"{value:.1%}"
    for key, item in result["bounds"].items():
        lines.append(
            f"| {key} | {item['candidate_families']} | {pct(item['base_oracle']['mean'])} | "
            f"{pct(item['spread50_oracle']['mean'])} | {pct(item['random_contract_mean_p50'])} |"
        )
    lines += [
        "", "## Contract + exit-horizon oracle across days 1/3/5", "",
        "| Band | n | Oracle ask→bid | Oracle spread+50 | Hit ≥25% |", "|---|---:|---:|---:|---:|",
    ]
    for key, item in result["path_bounds"].items():
        base = item["contract_and_exit_oracle"]
        stress = item["spread50_contract_and_exit_oracle"]
        lines.append(
            f"| {key} | {base['n']} | {pct(base['mean'])} | {pct(stress['mean'])} | {pct(base['hit_25'])} |"
        )
    lines += [
        "", "The oracle is intentionally impossible: it selects contracts and/or exit horizons using future realised return. A positive oracle proves only that the family contains learnable upside; it does not validate any selector.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
