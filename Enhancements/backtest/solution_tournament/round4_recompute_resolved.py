"""Recompute Round 4 decisions from the frozen, already-resolved contract panel.

This utility never queries a market database.  It is used when entry-time
decision logic changes but the historical contract/quote resolution does not.
"""

from __future__ import annotations

import json

import pandas as pd

import round4_end_to_end_stress as r4


def main() -> int:
    prior = json.loads(r4.RESULTS.read_text(encoding="utf-8"))
    if prior.get("candidate_sha256") != r4.sha256(r4.CANDIDATES):
        raise RuntimeError("resolved panel candidate input does not match current frozen input")
    if prior.get("protocol_sha256") != r4.sha256(r4.PROTOCOL):
        raise RuntimeError("resolved panel protocol does not match current sealed protocol")

    existing = pd.read_csv(r4.DETAIL, low_memory=False)
    raw = existing[existing.expression != "E5_DYNAMIC"].copy()
    derived = ["stress_spread_25", "stress_spread_50", "dropout_draw", "cheap_percentile"]
    raw = raw.drop(columns=[column for column in derived if column in raw], errors="ignore")
    combined = pd.concat([raw, r4.build_dynamic_rows(raw)], ignore_index=True)
    combined = r4.add_stress_columns(combined)
    combined.to_csv(r4.DETAIL, index=False)

    manifest = json.loads(r4.RUN_MANIFEST.read_text(encoding="utf-8"))
    populations = {}
    populations_allowed = r4.run_sets(manifest)
    for population, allowed in populations_allowed.items():
        subset = combined if allowed is None else combined[combined.run_id.astype(str).isin(allowed)]
        scenario_results = {}
        for (horizon, scenario), group in subset.groupby(["horizon", "scenario"]):
            scenario_results.setdefault(str(int(horizon)), {})[scenario] = r4.aggregate_scenario(group)
        populations[population] = {
            "rows": int(len(subset)),
            "sessions": int(subset.session.nunique()),
            "scenarios": scenario_results,
        }

    primary = combined[combined.run_id.astype(str).isin(populations_allowed["exclude_explicit_test_or_dirty"])]
    tail_recall = {}
    for (horizon, direction), group in primary.groupby(["horizon", "direction_rule"]):
        pivot = group[group.expression.isin(["E1_CORE", "E3_CONVEX"])].pivot_table(
            index="candidate_id", columns="expression", values="base_return", aggfunc="first"
        )
        for threshold, label in ((1.0, "100"), (2.0, "200")):
            available = pivot.max(axis=1, skipna=True) >= threshold
            core_capture = pivot.get("E1_CORE", pd.Series(index=pivot.index, dtype=float)) >= threshold
            convex_capture = pivot.get("E3_CONVEX", pd.Series(index=pivot.index, dtype=float)) >= threshold
            tail_recall.setdefault(str(int(horizon)), {}).setdefault(direction, {})[f"ge_{label}pct"] = {
                "available_in_two_lanes": int(available.sum()),
                "core_recall": round(float(core_capture[available].mean()), 4) if available.any() else None,
                "convex_recall": round(float(convex_capture[available].mean()), 4) if available.any() else None,
                "union_recall": round(float((core_capture | convex_capture)[available].mean()), 4)
                if available.any() else None,
            }

    result = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "protocol_sha256": r4.sha256(r4.PROTOCOL),
        "candidate_sha256": r4.sha256(r4.CANDIDATES),
        "detail_sha256": r4.sha256(r4.DETAIL),
        "populations": populations,
        "two_lane_tail_recall": tail_recall,
        "constraints": [
            "No capital allocation is modelled.",
            "No-trade and missing-quote rows are never converted to zero returns.",
            "Midpoint marks are diagnostic only.",
            "Dynamic instrument selection uses entry-time evidence only.",
            "No scenario changes production authority.",
        ],
    }
    r4.RESULTS.write_text(json.dumps(result, indent=2), encoding="utf-8")

    focus = populations["exclude_explicit_test_or_dirty"]["scenarios"]
    lines = [
        "# AVSHUNTER Round 4 — integrated monetisation and stress result",
        "",
        "**State:** Exploratory research only. Production was not changed.",
        "",
        "## Primary population: explicit test/dirty run excluded",
        "",
        "| Horizon | Scenario | Participation | Base mean | Spread +50% | Top 1% removed | Bull | Bear | Reliable |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    selected_scenarios = [
        "D0_CURRENT|E0_RECORDED", "D0_CURRENT|E1_CORE", "D0_CURRENT|E2_VALUE",
        "D0_CURRENT|E4_MATURED_CORE", "D0_CURRENT|E5_DYNAMIC",
        "D1_MEAN_REVERSION_5|E1_CORE", "D1_MEAN_REVERSION_5|E5_DYNAMIC",
        "D2_MOMENTUM_20|E1_CORE", "D2_MOMENTUM_20|E5_DYNAMIC",
    ]
    pct = lambda value: "n/a" if value is None else f"{100 * value:.2f}%"
    for horizon in map(str, r4.HORIZONS):
        for scenario in selected_scenarios:
            item = focus.get(horizon, {}).get(scenario)
            if not item:
                continue
            lines.append(
                f"| {horizon} | {scenario} | {pct(item['participation'])} | {pct(item['base']['mean'])} | "
                f"{pct(item['spread_widen_50']['mean'])} | {pct(item['remove_top_1pct']['mean'])} | "
                f"{pct(item['spy_bull']['mean'])} | {pct(item['spy_bear']['mean'])} | "
                f"{'YES' if item['reliability_gate']['passed'] else 'NO'} |"
            )
    lines += [
        "",
        "## Acceptance rule",
        "",
        "Only a scenario marked reliable may advance toward implementation, and even then it requires replication on additional certified sessions. Failure attribution is recorded in the JSON result rather than hidden by a single aggregate score.",
    ]
    r4.REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(combined), "raw_rows": len(raw), "detail": str(r4.DETAIL)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
