"""DIR-002 side-assignment calibration (calibration window) and R-5 test (held-out).

Implements AVS_DIR002_SIDE_ASSIGNMENT_CALIBRATION_PREREGISTRATION_20261001.md
exactly. Stage ``calibrate`` reads only cuts <= 2024-12-31. Stage ``heldout``
reads cuts >= 2025-02-03 and requires a frozen, calibrated policy file.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.direction_governance import (  # noqa: E402
    SideAssignmentPolicy,
    assign_thesis_side,
    load_side_assignment_policy,
    side_evidence_vectors,
)

CAL_END = "2024-12-31"
HELD_START = "2025-02-03"
GRID = {
    "event_strength_min": [0.50, 0.55, 0.60, 0.65, 0.70],
    "control_margin_min": [0.10, 0.15, 0.20, 0.25, 0.30],
    "contested_margin": [0.05, 0.10, 0.15, 0.20],
}
FIXED = {"control_full_scale": 0.80, "min_observation_quality": 0.65, "trend_min_bars": 200}
SEED = 20261001
RESAMPLES = 2000


def load_panel(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    frame = pd.DataFrame(rows)
    frame = frame[frame["outcome"] == "SURVIVE"].copy()
    frame["matured"] = (frame["forward_sessions_available"] >= 20) & frame["sigma_d"].gt(0) & frame["ret_20"].notna()
    frame["z20"] = frame["ret_20"] / (frame["sigma_d"] * math.sqrt(20))
    # Amendment A1: drift-adjusted outcome = z20 minus the same-cut mean of
    # all matured survivors (removes market drift from side discrimination).
    cut_mean = frame.loc[frame["matured"]].groupby("cut_date")["z20"].mean()
    frame["xz20"] = frame["z20"] - frame["cut_date"].map(cut_mean)
    cuts = sorted(frame["cut_date"].unique())
    block = {cut: i // 2 for i, cut in enumerate(cuts)}
    frame["block"] = frame["cut_date"].map(block)
    return frame.reset_index(drop=True)


def evidence_inputs(row: pd.Series, any_setup: bool = False):
    structure = {
        "status": row.get("o__side_evidence_status"),
        "trend_history_bars": row.get("o__side_trend_history_bars"),
        "bull": json.loads(row["o__bull_evidence_json"]) if isinstance(row.get("o__bull_evidence_json"), str) else {},
        "bear": json.loads(row["o__bear_evidence_json"]) if isinstance(row.get("o__bear_evidence_json"), str) else {},
    }
    basis = row.get("o__side_intent_basis")
    if any_setup and row.get("o__side_intent") in {"BUY_SETUP", "SELL_SETUP"}:
        basis = "EVENT"
    intent = {"status": row.get("o__side_intent_status"), "intent": row.get("o__side_intent"),
              "mode": row.get("o__side_intent_mode"), "intent_basis": basis}
    return side_evidence_vectors(structure, intent)


_VECTOR_CACHE: dict = {}


def assign_all(frame: pd.DataFrame, policy: SideAssignmentPolicy, any_setup: bool = False) -> pd.DataFrame:
    key = (id(frame), any_setup)
    if key not in _VECTOR_CACHE:  # evidence vectors do not depend on the policy
        _VECTOR_CACHE[key] = [evidence_inputs(row, any_setup) for _, row in frame.iterrows()]
    vectors = _VECTOR_CACHE[key]
    out = [assign_thesis_side(b, r, policy) for b, r in vectors]
    return pd.DataFrame({
        "side": [o["thesis__side"] for o in out],
        "status": [o["thesis__direction_status"] for o in out],
    }, index=frame.index)


def signed(frame: pd.DataFrame, side: pd.Series, column: str = "xz20") -> pd.Series:
    """Signed outcome per row; A1 default is the drift-adjusted excess."""
    sign = side.map({"BULL": 1.0, "BEAR": -1.0, "CALL": 1.0, "PUT": -1.0})
    return sign * frame[column]


def block_bootstrap_mean(values: pd.Series, blocks: pd.Series, seed: int = SEED) -> dict:
    data = pd.DataFrame({"v": values, "b": blocks}).dropna()
    if data.empty:
        return {"n": 0, "blocks": 0, "mean": None, "lo95": None, "hi95": None}
    grouped = data.groupby("b")["v"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(grouped), size=(RESAMPLES, len(grouped)))
    sums = grouped["sum"].to_numpy()[idx].sum(axis=1)
    counts = grouped["count"].to_numpy()[idx].sum(axis=1)
    means = sums / np.where(counts > 0, counts, np.nan)
    return {"n": int(len(data)), "blocks": int(len(grouped)), "mean": float(data["v"].mean()),
            "lo95": float(np.nanpercentile(means, 2.5)), "hi95": float(np.nanpercentile(means, 97.5))}


def paired_difference(new: pd.Series, legacy: pd.Series, blocks: pd.Series, seed: int = SEED) -> dict:
    frame = pd.DataFrame({"new": new, "legacy": legacy, "b": blocks})
    agg = frame.groupby("b").agg(new_sum=("new", "sum"), new_n=("new", "count"),
                                 leg_sum=("legacy", "sum"), leg_n=("legacy", "count"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(agg), size=(RESAMPLES, len(agg)))
    arr = {c: agg[c].to_numpy()[idx].sum(axis=1) for c in agg.columns}
    diff = arr["new_sum"] / np.where(arr["new_n"] > 0, arr["new_n"], np.nan) - arr["leg_sum"] / np.where(arr["leg_n"] > 0, arr["leg_n"], np.nan)
    point = frame["new"].mean() - frame["legacy"].mean()
    return {"diff": float(point), "lo95": float(np.nanpercentile(diff, 2.5)),
            "hi95": float(np.nanpercentile(diff, 97.5)), "blocks": int(len(agg)),
            "n_new": int(frame["new"].count()), "n_legacy": int(frame["legacy"].count())}


def calibrate(frame: pd.DataFrame) -> dict:
    cal = frame[(frame["cut_date"] <= CAL_END) & frame["matured"]].copy()
    legacy_side = cal["o__legacy_direction"].map({"CALL": "BULL", "PUT": "BEAR"})
    raw_side = cal["o__precor_intent_raw"].map({"BUY_SETUP": "BULL", "SELL_SETUP": "BEAR"})
    # Amendment A1: legacy cases not routed through an asymmetric reconciliation.
    sym_cases = (cal["o__legacy_direction"].isin(["CALL", "PUT"]) & cal["o__precor_phase"].eq("C")
                 & legacy_side.eq(raw_side))
    results = []
    for e, c, m in itertools.product(*GRID.values()):
        policy = SideAssignmentPolicy(version="side_assign_v1", event_strength_min=e, control_margin_min=c,
                                      contested_margin=m, **FIXED)
        assigned = assign_all(cal, policy)
        directed = assigned["side"].isin(["BULL", "BEAR"])
        opposite = sym_cases & directed & (assigned["side"] != legacy_side)
        agree = sym_cases & (assigned["side"] == legacy_side)
        stat = block_bootstrap_mean(signed(cal, assigned["side"]).where(directed), cal["block"])
        results.append({
            "event_strength_min": e, "control_margin_min": c, "contested_margin": m,
            "sym_cases": int(sym_cases.sum()),
            "opposite_side_rate": float(opposite.sum() / max(1, sym_cases.sum())),
            "agreement_rate": float(agree.sum() / max(1, sym_cases.sum())),
            "directed": int(directed.sum()), "rows": int(len(cal)),
            "mean_signed_z20": stat["mean"], "lo95": stat["lo95"], "hi95": stat["hi95"],
            "status_counts": assigned["status"].value_counts().to_dict(),
        })
    eligible = [r for r in results if r["opposite_side_rate"] <= 0.05 and r["lo95"] is not None]
    best = None
    if eligible:
        top = max(r["lo95"] for r in eligible)
        ties = [r for r in eligible if r["lo95"] >= top - 0.005]
        best = sorted(ties, key=lambda r: (r["event_strength_min"], r["control_margin_min"], r["contested_margin"]),
                      reverse=True)[0]
    legacy_stat = block_bootstrap_mean(signed(cal, cal["o__legacy_direction"]).where(
        cal["o__legacy_direction"].isin(["CALL", "PUT"])), cal["block"])
    raw_legacy = block_bootstrap_mean(signed(cal, cal["o__legacy_direction"], "z20").where(
        cal["o__legacy_direction"].isin(["CALL", "PUT"])), cal["block"])
    return {"amendment": "A1", "calibration_rows": int(len(cal)), "grid": results, "selected": best,
            "eligible_count": len(eligible), "legacy_reference_excess": legacy_stat,
            "legacy_reference_raw": raw_legacy}


def held_out(frame: pd.DataFrame, policy: SideAssignmentPolicy) -> dict:
    held = frame[(frame["cut_date"] >= HELD_START) & frame["matured"]].copy()
    report: dict = {"rows": int(len(held)), "policy": policy.__dict__}
    variants = {"event_anchored": assign_all(held, policy), "any_setup_transparency": assign_all(held, policy, True)}
    legacy = held["o__legacy_direction"]
    legacy_side = legacy.map({"CALL": "BULL", "PUT": "BEAR"})
    barrier = 1.0  # ±1σ√20 first passage, in z units
    for name, assigned in variants.items():
        new_side = assigned["side"]
        sub: dict = {"status_counts": assigned["status"].value_counts().to_dict()}
        for side_name, legacy_token in (("BULL", "CALL"), ("BEAR", "PUT"), ("ALL", None)):
            new_mask = new_side.isin(["BULL", "BEAR"]) if side_name == "ALL" else new_side.eq(side_name)
            leg_mask = legacy.isin(["CALL", "PUT"]) if side_name == "ALL" else legacy.eq(legacy_token)
            new_vals = signed(held, new_side).where(new_mask)
            leg_vals = signed(held, legacy).where(leg_mask)
            new_raw = signed(held, new_side, "z20").where(new_mask)
            leg_raw = signed(held, legacy, "z20").where(leg_mask)
            first = held["first_passage_1sig"]
            def passage(side_series, mask, favourable=True):
                up = first.eq("UP"); dn = first.eq("DOWN")
                fav = (side_series.isin(["BULL", "CALL"]) & up) | (side_series.isin(["BEAR", "PUT"]) & dn)
                adv = (side_series.isin(["BULL", "CALL"]) & dn) | (side_series.isin(["BEAR", "PUT"]) & up)
                target = fav if favourable else adv
                return float(target[mask].mean()) if mask.any() else None
            entry = {
                "coverage_new": int(new_mask.sum()), "coverage_legacy": int(leg_mask.sum()),
                "new": block_bootstrap_mean(new_vals, held["block"]),
                "legacy": block_bootstrap_mean(leg_vals, held["block"]),
                "paired": paired_difference(new_vals, leg_vals, held["block"]),
                "raw_new": block_bootstrap_mean(new_raw, held["block"]),
                "raw_legacy": block_bootstrap_mean(leg_raw, held["block"]),
                "paired_raw": paired_difference(new_raw, leg_raw, held["block"]),
                "favourable_first_new": passage(new_side, new_mask),
                "favourable_first_legacy": passage(legacy, leg_mask),
                "adverse_first_new": passage(new_side, new_mask, False),
                "adverse_first_legacy": passage(legacy, leg_mask, False),
                "adverse_outcome_rate_new": float((new_vals <= -barrier).sum() / max(1, new_mask.sum())),
                "adverse_outcome_rate_legacy": float((leg_vals <= -barrier).sum() / max(1, leg_mask.sum())),
            }
            for h in (5, 10):
                z = held[f"ret_{h}"] / (held["sigma_d"] * math.sqrt(h))
                sign_new = new_side.map({"BULL": 1.0, "BEAR": -1.0})
                sign_leg = legacy.map({"CALL": 1.0, "PUT": -1.0})
                entry[f"mean_signed_z{h}_new"] = float((sign_new * z)[new_mask].mean()) if new_mask.any() else None
                entry[f"mean_signed_z{h}_legacy"] = float((sign_leg * z)[leg_mask].mean()) if leg_mask.any() else None
            p = entry["paired"]
            enough = (entry["coverage_new"] >= 200 and entry["new"]["blocks"] >= 20)
            entry["non_inferiority"] = (
                "NOT_ESTIMABLE" if not enough else ("PASS" if p["lo95"] >= -0.05 else "FAIL")
            )
            sub[side_name] = entry
        big = held["z20"].abs() >= 2.0
        correct_legacy = signed(held, legacy) > 0
        missed = big & correct_legacy & legacy.isin(["CALL", "PUT"]) & new_side.eq("UNASSIGNED")
        sub["missed_large_winners"] = int(missed.sum())
        sub["large_winner_opportunities_legacy_correct"] = int((big & correct_legacy).sum())
        sub["transitions"] = {
            "changed_side": int((new_side.isin(["BULL", "BEAR"]) & legacy_side.notna() & (new_side != legacy_side)).sum()),
            "same_side": int((new_side == legacy_side).sum()),
            "newly_directed": int((new_side.isin(["BULL", "BEAR"]) & legacy_side.isna()).sum()),
            "newly_unassigned": int((new_side.eq("UNASSIGNED") & legacy_side.notna()).sum()),
            "both_undirected": int((new_side.eq("UNASSIGNED") & legacy_side.isna()).sum()),
        }
        report[name] = sub
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["calibrate", "heldout"])
    parser.add_argument("--panel", default=str(ROOT / "Enhancements/outcomes/dir002/panel_v1.jsonl"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    frame = load_panel(Path(args.panel))
    if args.stage == "calibrate":
        result = calibrate(frame)
    else:
        raw = json.loads((ROOT / "config/dir002_side_assignment_v1.json").read_text(encoding="utf-8"))
        if raw["calibration"]["status"] != "CALIBRATED_CALIBRATION_WINDOW":
            raise SystemExit("Held-out stage requires the frozen calibrated policy")
        result = held_out(frame, load_side_assignment_policy())
    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result.get("selected") or {k: v for k, v in result.items() if k != "grid"}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
