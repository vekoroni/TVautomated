"""Item 11 (D2-1 Step B, Discovery station) replay on the live 8 Oct run (20261008_220129). Read-only.

Compares the legacy Discovery tier / sort / win probability / quality gate / horizon label with the proposed
thesis-engine replacement (ITEM11_DISCOVERY_TIER_DESIGN_20261010.md):
- tier from the thesis disposition: 0 GO (ready, geometry not refused), 1 READY_NOT_GO, 2 WAITING (adopted, waiting for
  its trigger), 3 NO_ACTIVE_THESIS (not adopted, closed, none);
- order within tier: the governing setup's held-out within-hold rate, then its lane hit rate, then ticker;
- win_probability: the setup's held-out within-hold rate (null when the setup has none), not the composite rescale;
- horizon label from the setup's evidence hold (Options planned_hold_sessions), not from the tier;
- quality gate: survivors >= 15% of the universe and at least one thesis GO, not legacy tier ratios.
Geometry is replayed with assess_trade_geometry on the book's levels (as ot3_live_geometry.py), since the 8 Oct run
predates item 3. Survival: the tier-4 drop removed no ticker in the last 8 runs (lifecycle files), so it is not
replayed per ticker. Writes ot11_discovery_tier_replay.json beside this file.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain.structure_behaviour.trade_lane import load_lanes, setup_rate_fields  # noqa: E402
from domain.trade_geometry import NOT_GO_STATES, assess_trade_geometry  # noqa: E402

RUN = "20261008_220129"
RUN_DIR = ROOT / "data" / "output" / "runs" / RUN
RUNS = ROOT / "data" / "output" / "runs"


def _geometry_by_ticker() -> dict:
    book = json.loads((RUN_DIR / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").read_text(encoding="utf-8"))
    rows = book if isinstance(book, list) else (book.get("rows") or book.get("opportunities"))
    disc = pd.read_csv(RUN_DIR / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv", usecols=["ticker", "ATR_14"])
    atr = dict(zip(disc["ticker"].astype(str).str.upper(), disc["ATR_14"]))
    table = load_lanes()
    n_by = {}
    for lane in ("lane_a_trade_now", "lane_b_early_entry"):
        for tf, entries in table[lane].items():
            if isinstance(entries, list):
                for e in entries:
                    n_by[(lane[5].upper(), f"{tf}|{e['type']}|{e['state']}")] = e["n"]
    out = {}
    for r in rows:
        side = {"CALL": "BULL", "PUT": "BEAR"}.get(str(r.get("direction") or "").upper())
        n = n_by.get((str(r.get("trade_lane") or ""), str(r.get("trade_lane_setup") or "")), [None, None])
        lane = {"trade_lane_hit_original": r.get("trade_lane_hit_original"),
                "trade_lane_hit_holdout": r.get("trade_lane_hit_holdout"),
                "trade_lane_hit_n_original": n[0], "trade_lane_hit_n_holdout": n[1]}
        g = assess_trade_geometry(side=side, readiness=r.get("thesis__readiness"), session_price=r.get("signal_price"),
                                  trigger_level=r.get("thesis_trigger_level"),
                                  target=r.get("target_price") or r.get("structural_target"),
                                  invalidation=r.get("invalidation_price"),
                                  early_warning=r.get("early_warning_invalidation_level"),
                                  atr_daily=atr.get(str(r.get("ticker")).upper()), lane=lane)
        out[str(r.get("ticker")).upper()] = g["geometry_justification"]
    return out


def thesis_tier(readiness: object, geometry: object) -> int:
    readiness = str(readiness or "").upper()
    if readiness == "READY_FOR_HUMAN_REVIEW":
        return 1 if str(geometry or "") in NOT_GO_STATES else 0
    if readiness == "WAIT_TRIGGER":
        return 2
    return 3


def main() -> None:
    d = pd.read_csv(RUN_DIR / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv", low_memory=False)
    d["ticker"] = d["ticker"].astype(str).str.upper()
    geometry = _geometry_by_ticker()
    d["geometry_justification"] = d["ticker"].map(geometry)
    d["tier_new"] = [thesis_tier(r, g) for r, g in zip(d["thesis__readiness"], d["geometry_justification"])]
    # Acceptance through the built owner (domain/thesis_tier.py): tier, win probability, horizon and order.
    from domain.thesis_tier import discovery_horizon, discovery_order, discovery_win_probability, thesis_tier as built_tier
    d["tier_built"] = [built_tier({"thesis__readiness": r, "geometry_justification": g})["tier"]
                       for r, g in zip(d["thesis__readiness"], d["geometry_justification"])]
    d["horizon_built"] = [discovery_horizon(r)["horizon_bucket"] for r in d.to_dict("records")]
    rates = []
    for setup, side in zip(d["trade_lane_setup"], d["trade_lane_side"]):
        if not isinstance(setup, str) or setup.count("|") != 2:
            rates.append(None)
            continue
        tf, signal_type, state = setup.split("|")
        rates.append(setup_rate_fields({"Timeframe": tf, "Signal_Type": signal_type, "Signal_State": state,
                                        "Direction": side})["setup_rate_within_hold"])
    d["win_probability_new"] = pd.to_numeric(pd.Series(rates, index=d.index), errors="coerce")

    old = d.sort_values(["tier", "lift_proxy_score"], ascending=[True, False])["ticker"].tolist()
    new = (d.assign(_r=d["win_probability_new"].fillna(-1), _h=pd.to_numeric(d["trade_lane_hit_holdout"], errors="coerce").fillna(-1))
           .sort_values(["tier_new", "_r", "_h", "ticker"], ascending=[True, False, False, True])["ticker"].tolist())
    overlap = {k: len(set(old[:k]) & set(new[:k])) for k in (50, 100, 200)}

    opt = pd.read_csv(RUN_DIR / "options" / f"options_intelligence_{RUN}.csv", low_memory=False,
                      usecols=["ticker", "planned_hold_sessions", "horizon_bucket"])
    hold = dict(zip(opt["ticker"].astype(str).str.upper(), pd.to_numeric(opt["planned_hold_sessions"], errors="coerce")))

    def bucket(h):
        if h is None or h != h:
            return "NO_EVIDENCE_HOLD"
        return "1_5d" if h <= 5 else "6_10d" if h <= 10 else "11_20d" if h <= 20 else "OVER_20d"
    d["horizon_new"] = d["ticker"].map(lambda t: bucket(hold.get(t)))

    universe = 3325                                                  # lifecycle rows on 8 Oct (scanned universe)
    survivors = len(d)
    old_gate = {"candidate_ratio": round(survivors / universe, 3),
                "early_ratio": round(int((d["tier"] == 0).sum()) / universe, 3),
                "tier1_plus_2": int(d["tier"].isin([1, 2]).sum())}
    new_gate = {"candidate_ratio": round(survivors / universe, 3), "thesis_go": int((d["tier_new"] == 0).sum()),
                "passes": survivors / universe >= 0.15 and int((d["tier_new"] == 0).sum()) >= 1}

    tier4 = {}
    for f in sorted(RUNS.glob("*/discovery/discovery_lifecycle_*.csv"))[-8:]:
        lc = pd.read_csv(f, usecols=["reason_code"])
        tier4[f.parents[1].name] = int((lc["reason_code"] == "ELIG_TIER4_LOW_COMPOSITE").sum())

    wp_old = pd.to_numeric(d["win_probability"], errors="coerce")
    built_order = discovery_order(d.assign(tier=d["tier_built"], win_probability=d["win_probability_new"]))["ticker"].tolist()
    built = {"tier_built_equals_replay": bool((d["tier_built"] == d["tier_new"]).all()),
             "tier_built": d["tier_built"].value_counts().sort_index().to_dict(),
             "order_built_equals_replay": built_order == new,
             "horizon_built_from_discovery_evidence": d["horizon_built"].value_counts().to_dict(),
             "win_probability_built_covered": sum(discovery_win_probability({"setup_rate_within_hold": v})["win_probability"]
                                                  is not None for v in d["win_probability_new"])}
    out = {
        "run": RUN, "survivors": survivors, "tier4_drops_last_8_runs": tier4,
        "tier_old": d["tier"].value_counts().sort_index().to_dict(),
        "tier_new": d["tier_new"].value_counts().sort_index().to_dict(),
        "tier_old_x_new": {f"{a}->{b}": int(n) for (a, b), n in collections.Counter(zip(d["tier"], d["tier_new"])).items()},
        "readiness_by_new_tier": {int(t): g["thesis__readiness"].value_counts(dropna=False).to_dict()
                                  for t, g in d.groupby("tier_new")},
        "geometry_new_tier_0_1": d[d["tier_new"] <= 1]["geometry_justification"].value_counts(dropna=False).to_dict(),
        "order_overlap_top_k": overlap,
        "top10_old": old[:10], "top10_new": new[:10],
        "win_probability_old": {"min": float(wp_old.min()), "median": float(wp_old.median()), "max": float(wp_old.max()),
                                "basis": "COMPOSITE_RESCALED_NOT_A_PROBABILITY"},
        "win_probability_new": {"covered": int(d["win_probability_new"].notna().sum()),
                                "null_no_setup_rate": int(d["win_probability_new"].isna().sum()),
                                "median": float(d["win_probability_new"].median()),
                                "q10": float(d["win_probability_new"].quantile(0.1)),
                                "q90": float(d["win_probability_new"].quantile(0.9))},
        "horizon_old": d["horizon_bucket"].value_counts().to_dict(),
        "horizon_new": d["horizon_new"].value_counts().to_dict(),
        "quality_gate_old": old_gate, "quality_gate_new": new_gate, "acceptance_built": built,
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
