"""Combine frozen purged S-ACT priorities with independently selected CEX contracts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "Enhancements" / "backtest"
SCORES = HERE / "activity_tournament" / "s_act_model_scores.csv.gz"
CEX = HERE / "contract_execution_tournament" / "cex_selected_rows.csv.gz"
REGISTER = HERE / "SCENARIO_REGISTER_ADDENDUM_CEX_20260920.md"
OUTPUT = HERE / "contract_execution_tournament"
RESULTS = OUTPUT / "cex8_combo_results.json"
REPORT = OUTPUT / "CEX8_ACTIVITY_CONTRACT_COMBO_REPORT_20260920.md"
DETAIL = OUTPUT / "cex8_combo_rows.csv.gz"
LEDGER = OUTPUT / "cex_trial_ledger.jsonl"

TARGET = 0.25
QUANTILES = (0.01, 0.02, 0.05, 0.10, 0.20, 0.30)
CONTRACT_SCENARIOS = ("CEX-0", "CEX-1", "CEX-2-1.0", "CEX-3", "CEX-4", "CEX-5", "CEX-7")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def priority_band(scores: pd.DataFrame, fraction: float) -> pd.DataFrame:
    selected = []
    for _, group in scores.groupby("session", sort=False):
        count = max(1, int(math.ceil(len(group) * fraction)))
        selected.append(group.nlargest(count, "score"))
    return pd.concat(selected, ignore_index=True) if selected else scores.iloc[0:0]


def summarise(selected: pd.DataFrame, baseline: pd.DataFrame) -> dict:
    closed = selected.dropna(subset=["base_return"])
    control = baseline.dropna(subset=["base_return"])
    deltas = closed.groupby("session").base_return.mean() - control.groupby("session").base_return.mean()
    deltas = deltas.dropna()
    t_stat, p_value = stats.ttest_1samp(deltas, 0.0) if len(deltas) >= 2 else (np.nan, np.nan)
    spread50 = float(closed.stress_spread_50.mean()) if len(closed) else None
    passes = bool(
        len(closed) >= 40 and len(deltas) >= 2 and closed.base_return.mean() > 0
        and spread50 is not None and spread50 > 0 and math.isfinite(float(t_stat))
        and abs(float(t_stat)) >= 2 and int((deltas > 0).sum()) >= 2
    )
    return {
        "status": "REPLICATION_CANDIDATE" if passes else "REJECTED_OR_INCONCLUSIVE",
        "n": int(len(closed)), "sessions": int(closed.session.nunique()),
        "ask_bid_mean": float(closed.base_return.mean()) if len(closed) else None,
        "ask_bid_median": float(closed.base_return.median()) if len(closed) else None,
        "hit_25": float((closed.base_return >= TARGET).mean()) if len(closed) else None,
        "limit25_conditional_mean": float(closed.limit25_return.mean()) if len(closed) else None,
        "mid_entry_exit_bid_conditional_mean": float(closed.limit50_return.mean()) if len(closed) else None,
        "spread50_mean": spread50,
        "session_delta_mean_vs_recorded_same_band": float(deltas.mean()) if len(deltas) else None,
        "paired_t": float(t_stat) if math.isfinite(float(t_stat)) else None,
        "paired_p": float(p_value) if math.isfinite(float(p_value)) else None,
        "positive_session_deltas": int((deltas > 0).sum()),
    }


def main() -> int:
    score_rows = pd.read_csv(SCORES, low_memory=False)
    cex_rows = pd.read_csv(CEX, low_memory=False)
    results = {
        "state": "EXPLORATORY_NO_AUTHORITY", "adaptive": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "hashes": {"scores": sha256(SCORES), "cex": sha256(CEX), "register": sha256(REGISTER)},
        "trials": {},
    }
    output_rows = []
    for horizon in (1, 3, 5):
        score_trial = f"S-ACT-9|H{horizon}|F50|PURGED_WALK_FORWARD"
        score = score_rows[score_rows.trial_id == score_trial][
            ["candidate_id", "session", "horizon", "score"]
        ].drop_duplicates(["candidate_id", "horizon"])
        if score.empty:
            continue
        for fraction in QUANTILES:
            band = priority_band(score, fraction)
            choices = {}
            for contract in CONTRACT_SCENARIOS:
                trial = f"{contract}|H{horizon}"
                selected = cex_rows[cex_rows.trial_id == trial].merge(
                    band, on=["candidate_id", "session", "horizon"], how="inner", validate="one_to_one"
                )
                choices[contract] = selected
            baseline = choices["CEX-0"]
            for contract, selected in choices.items():
                trial_id = f"CEX-8|SACT9-Q{int(fraction*100)}|{contract}|H{horizon}"
                results["trials"][trial_id] = summarise(selected, baseline)
                if not selected.empty:
                    selected = selected.copy()
                    selected["combo_trial_id"] = trial_id
                    output_rows.append(selected)
                with LEDGER.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "trial_id": trial_id, "executed_at_utc": datetime.now(timezone.utc).isoformat(),
                        "result": results["trials"][trial_id]["status"], "production_authority": "NONE",
                        "adaptive": True,
                    }, sort_keys=True) + "\n")
    if output_rows:
        pd.concat(output_rows, ignore_index=True).to_csv(DETAIL, index=False, compression="gzip")
    RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")
    ranked = sorted(
        results["trials"].items(),
        key=lambda item: item[1]["ask_bid_mean"] if item[1]["ask_bid_mean"] is not None else -999,
        reverse=True,
    )
    lines = [
        "# CEX-8 Activity + Contract Combination Report — 2026-09-20", "",
        "**State:** adaptive exploratory research; no production authority", "",
        "| Trial | Status | n | Ask→bid | Limit25* | Mid entry* | Spread+50 | Hit ≥25% |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    pct = lambda value: "—" if value is None else f"{value:.1%}"
    for trial, item in ranked:
        lines.append(
            f"| {trial} | {item['status']} | {item['n']} | {pct(item['ask_bid_mean'])} | "
            f"{pct(item['limit25_conditional_mean'])} | {pct(item['mid_entry_exit_bid_conditional_mean'])} | "
            f"{pct(item['spread50_mean'])} | {pct(item['hit_25'])} |"
        )
    lines += [
        "", "*Conditional limit-entry results do not prove fillability.*", "",
        "Lower-priority ticker theses remain monitoring opportunities; this test changes priority and contract expression only.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "trials": len(results["trials"]), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
