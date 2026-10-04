"""Small deterministic CEX-9 contract-and-exit-path feasibility bound."""

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
OUTPUT = HERE / "contract_execution_tournament"
RESULT = OUTPUT / "cex9_path_oracle.json"
REPORT = OUTPUT / "CEX9_PATH_ORACLE_REPORT_20260920.md"


def band(frame: pd.DataFrame, fraction: float) -> pd.DataFrame:
    return pd.concat([
        group.nlargest(max(1, int(np.ceil(len(group) * fraction))), "score")
        for _, group in frame.groupby("session", sort=False)
    ], ignore_index=True)


def main() -> int:
    use = [
        "candidate_id", "session", "run_id", "horizon", "direction_rule", "expression",
        "instrument", "symbol", "entry_session", "base_return", "stress_spread_50",
    ]
    rows = pd.read_csv(ROUND4, usecols=use, low_memory=False)
    rows = rows[
        rows.direction_rule.eq("D0_CURRENT")
        & rows.expression.isin({"E0_RECORDED", "E1_CORE", "E2_VALUE", "E3_CONVEX", "E5_DYNAMIC"})
        & rows.instrument.eq("OPTION") & ~rows.run_id.eq("20260914_214012")
    ].copy()
    rows.sort_values(["candidate_id", "symbol", "horizon", "expression"], inplace=True)
    rows.drop_duplicates(["candidate_id", "symbol", "horizon", "entry_session"], inplace=True)
    score = pd.read_csv(
        SCORES,
        usecols=["candidate_id", "session", "score", "trial_id"],
        low_memory=False,
    )
    score = score[score.trial_id == "S-ACT-9|H1|F50|PURGED_WALK_FORWARD"].drop_duplicates("candidate_id")
    output = {
        "state": "HINDSIGHT_ORACLE_NO_AUTHORITY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "round4_sha256": hashlib.sha256(ROUND4.read_bytes()).hexdigest(),
        "scores_sha256": hashlib.sha256(SCORES.read_bytes()).hexdigest(),
        "bands": {},
    }
    for fraction in (.01, .02, .05, .10, .20):
        selected = band(score, fraction)
        pool = rows.merge(selected[["candidate_id"]], on="candidate_id", how="inner")
        base = pool.dropna(subset=["base_return"])
        base = base.loc[base.groupby("candidate_id").base_return.idxmax()]
        stress = pool.dropna(subset=["stress_spread_50"])
        stress = stress.loc[stress.groupby("candidate_id").stress_spread_50.idxmax()]
        output["bands"][f"Q{int(fraction*100)}"] = {
            "n": int(len(base)), "sessions": int(base.session.nunique()),
            "ask_bid_mean": float(base.base_return.mean()),
            "ask_bid_median": float(base.base_return.median()),
            "hit_25": float((base.base_return >= .25).mean()),
            "spread50_mean": float(stress.stress_spread_50.mean()),
        }
    RESULT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    lines = [
        "# CEX-9 Contract + Exit-Path Oracle — 2026-09-20", "",
        "**State:** hindsight feasibility diagnostic only; impossible as live logic", "",
        "| Priority band | n | Sessions | Ask→bid | Spread+50 | Hit ≥25% |", "|---|---:|---:|---:|---:|---:|",
    ]
    for name, item in output["bands"].items():
        lines.append(
            f"| {name} | {item['n']} | {item['sessions']} | {item['ask_bid_mean']:.1%} | "
            f"{item['spread50_mean']:.1%} | {item['hit_25']:.1%} |"
        )
    lines += [
        "", "The oracle selects both contract and exit horizon (day 1, 3 or 5) after seeing future returns. Positive results prove a path-aware solution may be learnable; they do not validate execution logic.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "result": str(RESULT), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
