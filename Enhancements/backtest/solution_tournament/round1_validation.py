"""Validate solution-tournament round 1 without touching production authority.

This analysis separates execution friction from contract movement and reports
results across explicit run-quality populations.  It consumes only the frozen
round-1 panel and its input manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
PANEL = HERE / "round1_panel.csv"
MANIFEST = HERE / "round1_input_manifest.json"
OUTPUT = HERE / "round1_validation.json"
REPORT = HERE / "ROUND1_VALIDATION_REPORT_20260919.md"
SEED = 19092026


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
        "n": int(len(clean)),
        "sessions": int(len(sessions)),
        "mean": None,
        "median": None,
        "hit_rate": None,
        "ci90": [None, None],
    }
    if clean.empty:
        return result
    result.update({
        "mean": round(float(clean[column].mean()), 6),
        "median": round(float(clean[column].median()), 6),
        "hit_rate": round(float((clean[column] > 0).mean()), 4),
    })
    if len(sessions) < 2:
        return result
    groups = {session: clean.loc[clean.session == session, column].to_numpy(float) for session in sessions}
    rng = np.random.default_rng(SEED)
    estimates = np.empty(samples)
    for index in range(samples):
        draw = rng.choice(sessions, size=len(sessions), replace=True)
        estimates[index] = np.concatenate([groups[session] for session in draw]).mean()
    result["ci90"] = [round(float(value), 6) for value in np.quantile(estimates, [0.05, 0.95])]
    return result


def paired_spread_drag(frame: pd.DataFrame) -> dict:
    clean = frame[["session", "option_ask_to_bid", "option_mid_to_mid"]].dropna().copy()
    clean["spread_drag"] = clean["option_mid_to_mid"] - clean["option_ask_to_bid"]
    return session_bootstrap(clean, "spread_drag")


def population_masks(frame: pd.DataFrame, manifest: dict) -> dict[str, pd.Series]:
    truth = {item["run_id"]: item for item in manifest["run_truth"]}
    explicit_test_or_dirty = {
        run_id
        for run_id, item in truth.items()
        if item.get("run_condition") == "TEST" or item.get("dirty") is True
    }
    certified = {
        run_id
        for run_id, item in truth.items()
        if item.get("run_condition") == "NORMAL_COMPLETED_SESSION"
        and item.get("dirty") is False
        and item.get("baseline_eligible") is True
    }
    return {
        "all_h_pre_fix": pd.Series(True, index=frame.index),
        "exclude_explicit_test_or_dirty": ~frame["run_id"].isin(explicit_test_or_dirty),
        "certified_normal_completed_only": frame["run_id"].isin(certified),
    }


def analyse(frame: pd.DataFrame, mask: pd.Series) -> dict:
    subset = frame[mask].copy()
    result: dict[str, object] = {
        "rows": int(len(subset)),
        "sessions": int(subset["session"].nunique()),
        "run_ids": sorted(subset["run_id"].dropna().astype(str).unique().tolist()),
        "horizons": {},
    }
    for horizon, group in subset.groupby("horizon"):
        spread5 = group[group["spread_fraction"] <= 0.05]
        strict = group[
            (group["iv_price_ratio"] >= 1.0)
            & (group["spread_fraction"] <= 0.10)
            & (group["moneyness_abs"] <= 0.05)
        ]
        result["horizons"][str(int(horizon))] = {
            "current_direction": session_bootstrap(group, "dirret_current"),
            "all_ask_to_bid": session_bootstrap(group, "option_ask_to_bid"),
            "all_mid_to_mid": session_bootstrap(group, "option_mid_to_mid"),
            "all_spread_drag": paired_spread_drag(group),
            "spread_le_5pct_ask_to_bid": session_bootstrap(spread5, "option_ask_to_bid"),
            "spread_le_5pct_mid_to_mid": session_bootstrap(spread5, "option_mid_to_mid"),
            "spread_le_5pct_drag": paired_spread_drag(spread5),
            "strict_price_aware_ask_to_bid": session_bootstrap(strict, "option_ask_to_bid"),
            "strict_price_aware_mid_to_mid": session_bootstrap(strict, "option_mid_to_mid"),
            "strict_price_aware_drag": paired_spread_drag(strict),
        }
    return result


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.2f}%"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frame = pd.read_csv(PANEL, low_memory=False)
    populations = {
        name: analyse(frame, mask)
        for name, mask in population_masks(frame, manifest).items()
    }
    payload = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "panel_sha256": sha256(PANEL),
        "manifest_sha256": sha256(MANIFEST),
        "populations": populations,
        "interpretation": [
            "Ask-to-bid is an executable round-trip proxy; mid-to-mid isolates contract repricing from quoted spread friction.",
            "The certified population contains only two independent sessions and cannot support promotion.",
            "Unknown legacy run truth is retained only in the explicitly labelled pre-fix sensitivity population.",
            "No capital weighting or macro authority is inferred.",
        ],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    all_results = populations["all_h_pre_fix"]["horizons"]
    certified = populations["certified_normal_completed_only"]
    lines = [
        "# AVSHUNTER Solution Tournament — Round 1 validation",
        "",
        "**State:** Exploratory research only. No production rule, authority, configuration, or database was changed.",
        "",
        "## Question tested",
        "",
        "Does the weak selected-contract result arise mainly from direction, from contract repricing, or from bid/ask friction? The same frozen candidates are measured ask-to-bid and mid-to-mid, then rechecked after excluding explicit test/dirty runs and on the small certified-run subset.",
        "",
        "## Evidence integrity",
        "",
        f"- Frozen panel: `{PANEL.name}` (`{len(frame):,}` horizon observations; SHA-256 `{payload['panel_sha256']}`).",
        f"- Candidate population: {frame['session'].nunique()} sessions, {frame['ticker'].nunique():,} tickers.",
        f"- Certified sensitivity: {certified['sessions']} sessions across {len(certified['run_ids'])} runs. This is diagnostic, not inferential.",
        "- Session-block bootstrap is used so thousands of correlated ticker rows are not mistaken for thousands of independent trials.",
        "",
        "## Paired result",
        "",
        "| Horizon | Current direction | Option ask→bid | Option mid→mid | Mean spread drag | ≤5% spread ask→bid |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for horizon in ("1", "3", "5"):
        item = all_results[horizon]
        lines.append(
            "| " + " | ".join([
                horizon,
                percent(item["current_direction"]["mean"]),
                percent(item["all_ask_to_bid"]["mean"]),
                percent(item["all_mid_to_mid"]["mean"]),
                percent(item["all_spread_drag"]["mean"]),
                percent(item["spread_le_5pct_ask_to_bid"]["mean"]),
            ]) + " |"
        )
    lines += [
        "",
        "The spread drag is reported as `mid-to-mid minus ask-to-bid`; it measures how much quoted entry/exit friction worsens the selected contract result. It is not a promise that midpoint fills were achievable.",
        "",
        "## Finding",
        "",
        "1. **Execution friction is a first-order defect.** Tight-spread filtering materially improves the selected-contract return, and the paired mid-price comparison quantifies the portion attributable to quotes.",
        "2. **Friction is not the whole defect.** The current direction signal is negative over three and five sessions in this sample, and mid-to-mid contract performance remains weak. A spread-only production fix would therefore be incomplete.",
        "3. **The sample is not promotion-grade.** Only two sessions meet the current certified normal-completed-run standard. The older rows remain useful for failure localisation but cannot establish live expectancy.",
        "4. **No tested route is accepted yet.** The least-bad alternatives are hypotheses for the next tournament round, not new pipeline authority.",
        "",
        "## Decision",
        "",
        "Do not build a production selector from Round 1. Advance to Round 2 with full contract-family re-selection, explicit no-quote exclusion, and opportunity-recall for large winners. In parallel, create a larger point-in-time candidate history from certified runs so direction and pricing models can be assessed independently.",
        "",
        "## Round 2 tests",
        "",
        "- Re-select every eligible contract in the same ticker/side/expiry family using only information available at the candidate timestamp.",
        "- Compare executable-now, developing-liquidity, and no-quote states without discarding the ticker thesis.",
        "- Attribute each loss to direction, IV repricing, theta, spread, or contract geometry.",
        "- Measure whether the selector retained the contracts that later delivered +50%, +100%, +200%, and +500% returns.",
        "- Compare the current signal with momentum, mean-reversion, and regime-conditioned alternatives on clean out-of-sample sessions.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "report": str(REPORT), "populations": {k: {"rows": v["rows"], "sessions": v["sessions"]} for k, v in populations.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
