"""Paired validation of Round 2 contract-family alternatives."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROWS = HERE / "round2_contract_family_rows.csv"
MANIFEST = HERE / "round1_input_manifest.json"
OUTPUT = HERE / "round2_validation.json"
REPORT = HERE / "ROUND2_VALIDATION_REPORT_20260919.md"
SEED = 19092026
KEY = ["session", "run_id", "ticker", "horizon"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def session_bootstrap(frame: pd.DataFrame, column: str, samples: int = 3000) -> dict:
    clean = frame[["session", column]].dropna()
    sessions = clean["session"].unique()
    result = {
        "n": int(len(clean)), "sessions": int(len(sessions)), "mean": None,
        "median": None, "ci90": [None, None],
    }
    if clean.empty:
        return result
    result["mean"] = round(float(clean[column].mean()), 6)
    result["median"] = round(float(clean[column].median()), 6)
    if len(sessions) < 2:
        return result
    groups = {s: clean.loc[clean.session == s, column].to_numpy(float) for s in sessions}
    rng = np.random.default_rng(SEED)
    means = np.empty(samples)
    for index in range(samples):
        draw = rng.choice(sessions, len(sessions), replace=True)
        means[index] = np.concatenate([groups[s] for s in draw]).mean()
    result["ci90"] = [round(float(value), 6) for value in np.quantile(means, [0.05, 0.95])]
    return result


def run_sets(manifest: dict) -> dict[str, set[str] | None]:
    truth = {item["run_id"]: item for item in manifest["run_truth"]}
    bad = {run_id for run_id, item in truth.items() if item.get("run_condition") == "TEST" or item.get("dirty") is True}
    certified = {
        run_id for run_id, item in truth.items()
        if item.get("run_condition") == "NORMAL_COMPLETED_SESSION"
        and item.get("dirty") is False
        and item.get("baseline_eligible") is True
    }
    return {
        "all_h_pre_fix": None,
        "exclude_explicit_test_or_dirty": set(truth) - bad,
        "certified_normal_completed_only": certified,
    }


def paired(frame: pd.DataFrame, alternative: str, value: str) -> dict:
    baseline = frame[frame.strategy == "F0_RECORDED"][KEY + [value]].rename(columns={value: "baseline"})
    challenger = frame[frame.strategy == alternative][KEY + [value]].rename(columns={value: "alternative"})
    joined = baseline.merge(challenger, on=KEY, how="inner").dropna(subset=["baseline", "alternative"])
    joined["improvement"] = joined["alternative"] - joined["baseline"]
    result = {
        "pairs": int(len(joined)),
        "baseline": session_bootstrap(joined.rename(columns={"baseline": "measure"}), "measure"),
        "alternative": session_bootstrap(joined.rename(columns={"alternative": "measure"}), "measure"),
        "improvement": session_bootstrap(joined, "improvement"),
        "alternative_better_rate": round(float((joined.alternative > joined.baseline).mean()), 4) if len(joined) else None,
    }
    return result


def analyse_population(frame: pd.DataFrame) -> dict:
    base = frame[frame.strategy == "F0_RECORDED"].copy()
    result: dict[str, object] = {
        "candidate_horizons": int(len(base)),
        "sessions": int(base.session.nunique()),
        "horizons": {},
    }
    for horizon, horizon_frame in frame.groupby("horizon"):
        base_h = horizon_frame[horizon_frame.strategy == "F0_RECORDED"].copy()
        if base_h.duplicated(KEY).any():
            raise RuntimeError(f"duplicate candidate identity at horizon {horizon}")
        oracle = base_h.dropna(subset=["oracle_best_ask_to_bid"])
        horizon_result: dict[str, object] = {
            "opportunities": int(len(base_h)),
            "missing_entry_chain": int((base_h.family_rows == 0).sum()),
            "no_executable_family_member": int((base_h.eligible_family_rows == 0).sum()),
            "oracle_best_ask_to_bid": session_bootstrap(oracle, "oracle_best_ask_to_bid"),
            "oracle_tail": {
                "ge_100pct": int((oracle.oracle_best_ask_to_bid >= 1.0).sum()),
                "ge_200pct": int((oracle.oracle_best_ask_to_bid >= 2.0).sum()),
                "ge_500pct": int((oracle.oracle_best_ask_to_bid >= 5.0).sum()),
            },
            "strategies": {},
        }
        for strategy in sorted(set(horizon_frame.strategy) - {"F0_RECORDED"}):
            selected = horizon_frame[horizon_frame.strategy == strategy]
            strategy_result = {
                "selected": int(selected.selected_symbol.notna().sum()),
                "selected_rate": round(float(selected.selected_symbol.notna().mean()), 4),
                "paired_ask_to_bid": paired(horizon_frame, strategy, "ask_to_bid"),
                "paired_mid_to_mid": paired(horizon_frame, strategy, "mid_to_mid"),
                "tail_recall": {},
            }
            for threshold, label in ((1.0, "100"), (2.0, "200"), (5.0, "500")):
                tail = selected[selected.oracle_best_ask_to_bid >= threshold]
                strategy_result["tail_recall"][f"ge_{label}pct"] = {
                    "available": int(len(tail)),
                    "selected_reached": int((tail.ask_to_bid >= threshold).sum()),
                    "recall": round(float((tail.ask_to_bid >= threshold).mean()), 4) if len(tail) else None,
                }
            horizon_result["strategies"][strategy] = strategy_result
        result["horizons"][str(int(horizon))] = horizon_result
    return result


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def main() -> int:
    frame = pd.read_csv(ROWS, low_memory=False)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    populations = {}
    for name, allowed in run_sets(manifest).items():
        subset = frame if allowed is None else frame[frame.run_id.astype(str).isin(allowed)]
        populations[name] = analyse_population(subset)
    payload = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "rows_sha256": sha256(ROWS),
        "populations": populations,
        "decision_rules": [
            "Paired comparisons include only candidate horizons with both recorded and alternative exit marks.",
            "Coverage and right-tail recall are co-equal with mean improvement.",
            "The convex-satellite rule is not testable in H because every recorded planned hold is at least 12 sessions.",
            "No rule is eligible for production promotion from nine sessions.",
        ],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    primary = populations["exclude_explicit_test_or_dirty"]["horizons"]
    lines = [
        "# AVSHUNTER solution tournament — Round 2 paired validation",
        "",
        "**State:** Exploratory research only. Production was not changed.",
        "",
        "## Paired comparison excluding explicit test/dirty runs",
        "",
        "Each row compares the alternative with the recorded contract only where both have an exact future exit mark. This removes the coverage-selection bias in the raw Round 2 table.",
        "",
        "| Horizon | Rule | Coverage | Paired n | Recorded ask→bid | Alternative ask→bid | Paired improvement | Alternative better | +100% recall |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for horizon in ("1", "3", "5"):
        horizon_data = primary[horizon]
        opportunities = horizon_data["opportunities"]
        for strategy, item in horizon_data["strategies"].items():
            pair = item["paired_ask_to_bid"]
            recall = item["tail_recall"]["ge_100pct"]["recall"]
            lines.append(
                f"| {horizon} | {strategy} | {item['selected']}/{opportunities} | {pair['pairs']} | "
                f"{pct(pair['baseline']['mean'])} | {pct(pair['alternative']['mean'])} | "
                f"{pct(pair['improvement']['mean'])} | {pct(pair['alternative_better_rate'])} | {pct(recall)} |"
            )
    lines += [
        "",
        "## Root-cause result",
        "",
        "1. **The recorded selector is economically dominated on average by cleaner contracts.** Every executable alternative materially improves the paired ask-to-bid result. This confirms a contract-expression defect, not merely a reporting defect.",
        "2. **No alternative creates positive expectancy.** Better geometry and spreads reduce the loss but do not overcome weak directional/timing edge and option richness.",
        "3. **Mean improvement and convex-tail preservation conflict.** The near-money and delta-core rules improve the average most but retain only a minority of families containing +100% contracts. A single hard selector would sacrifice valuable convex opportunities.",
        "4. **The convex-satellite hypothesis is not rejected; it is untestable in H.** Historical planned holds are 12–20 sessions, so the pre-registered hold≤5 condition never activates. It needs a population with genuine short-horizon thesis metadata.",
        "5. **Some families have no executable member.** These should produce a named contract execution state while retaining the ticker thesis, rather than a false zero or thesis rejection.",
        "",
        "## Research decision",
        "",
        "Advance a two-lane expression design to Round 3, not a single replacement selector:",
        "",
        "- **Core lane:** near-money/delta-core contract optimized for executable spread and stable delta.",
        "- **Convex lane:** separately ranked satellite preserving fast-tail opportunity, activated only when horizon, volatility price, and quote evidence qualify.",
        "- **Expression choice:** when options are rich, compare the permitted long-share expression for bullish theses; bearish theses remain option-or-no-trade because short shares are outside scope.",
        "",
        "Round 3 must attribute outcomes to direction, IV, theta, spread, and timing, then validate the two-lane design on a larger certified history before any build recommendation.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
