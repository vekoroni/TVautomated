"""p14_EH_e3_partition_metrics: offline test of the ALG-09 partition builder and
metric helpers (Track E3). No data files touched. Output: p14_EH_e3_partition_metrics_out.json

Part A: canonical_data.outcome_learning.build_temporal_partition_plan with synthetic
        date-ordered records (label window 20 sessions) -> check train < val < test,
        embargo >= 20 sessions at each boundary, no label-window straddle, order-invariance.
Part B: classwise ECE (10 fixed bins) and multiclass Brier for one synthetic stratum,
        computed independently and through the production binary helpers
        canonical_data.dynamic_options_probability._calibration_bins/_metrics.
        (There is no production multiclass Brier/classwise-ECE function; the Annex
        multiclass Brier equals the mean of the three one-vs-rest binary Briers.)
Part C: domain.outcome_learning.assess_model_activation boundary behaviour.
"""
import json, os, sys, random, math
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", "..", "..", ".."))
sys.path.insert(0, REPO)
from domain.outcome_learning import (OutcomeLearningRecord, LearningActivationPolicy, assess_model_activation)
from canonical_data.outcome_learning import build_temporal_partition_plan
from canonical_data import dynamic_options_probability as dop

out = {}
# ---------- Part A: partitions ----------
sessions = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-01-02", periods=160)]
LABEL_WINDOW = 20
def rec(i, session, direction):
    outcome_session = sessions[min(len(sessions) - 1, sessions.index(session) + LABEL_WINDOW)]
    return OutcomeLearningRecord.create(
        candidate_event_id=f"cand_{i}", outcome_event_id=f"out_{i}", run_id="SYN", ticker=f"T{i%7}",
        thesis_id=f"th_{i}", preferred_assessment_id=None, direction=direction, decision_session=session,
        planned_hold_sessions=10, hold_bucket="6-10", horizon_sessions=20, hidden_state_label="S1",
        phase="P1", compression_bucket="MID", competing_event_label="TARGET_FIRST",
        underlying_directional_return=0.01, underlying_mfe=0.02, underlying_mae=-0.01,
        option_data_status="UNDERLYING_ONLY", terminal_option_return=None, option_mfe=None, option_mae=None,
        first_two_sided_session=None, family_member_outperformance_state="NOT_EVALUATED",
        attribution="THESIS", feature_cutoff_utc=f"{session}T21:00:00Z",
        outcome_cutoff_utc=f"{outcome_session}T23:59:59Z", baseline_eligible=True, fit_eligible=True,
        exclusion_reasons=(), source_dataset_ids=("ds",))
records = []
i = 0
for s in sessions[:140]:
    for d in ("CALL", "PUT"):
        records.append(rec(i, s, d)); i += 1
by_id = {r.record_id: r for r in records}
plan = build_temporal_partition_plan(records, purge_embargo_sessions=20)
def sess(ids): return sorted({by_id[x].decision_session for x in ids})
tr, va, te, em, ov = sess(plan.training_record_ids), sess(plan.validation_record_ids), sess(plan.test_record_ids), sess(plan.excluded_embargo_record_ids), sess(plan.excluded_boundary_overlap_record_ids)
idx = {s: k for k, s in enumerate(sessions)}
def gap(a, b): return idx[b[0]] - idx[a[-1]] if a and b else None
partA = {
    "state": plan.state, "purge_embargo_sessions": plan.purge_embargo_sessions,
    "n_records": len(records), "n_train": len(plan.training_record_ids), "n_val": len(plan.validation_record_ids),
    "n_test": len(plan.test_record_ids), "n_embargo": len(plan.excluded_embargo_record_ids), "n_overlap": len(plan.excluded_boundary_overlap_record_ids),
    "train_sessions": [tr[0], tr[-1]] if tr else None, "val_sessions": [va[0], va[-1]] if va else None, "test_sessions": [te[0], te[-1]] if te else None,
    "training_cutoff_session": plan.training_cutoff_session, "validation_cutoff_session": plan.validation_cutoff_session,
    "date_ordered_train_lt_val_lt_test": bool(tr and va and te and tr[-1] < va[0] and va[-1] < te[0]),
    "gap_train_to_val_sessions": gap(tr, va), "gap_val_to_test_sessions": gap(va, te),
    "embargo_ge_20_both_boundaries": bool(gap(tr, va) is not None and gap(tr, va) >= 20 and gap(va, te) is not None and gap(va, te) >= 20),
    "no_train_outcome_reaches_val": all(by_id[x].outcome_cutoff_utc[:10] < va[0] for x in plan.training_record_ids) if va else None,
    "no_val_outcome_reaches_test": all(by_id[x].outcome_cutoff_utc[:10] < te[0] for x in plan.validation_record_ids) if te else None,
    "all_records_accounted": len(plan.training_record_ids) + len(plan.validation_record_ids) + len(plan.test_record_ids) + len(plan.excluded_embargo_record_ids) + len(plan.excluded_boundary_overlap_record_ids) == len(records),
}
shuffled = list(records); random.Random(7).shuffle(shuffled)
plan2 = build_temporal_partition_plan(shuffled, purge_embargo_sessions=20)
partA["order_invariant"] = plan2.to_dict() == plan.to_dict()
small = build_temporal_partition_plan(records[:2 * 30], purge_embargo_sessions=20)
partA["30_sessions_state"] = small.state
partA["embargo_unit_note"] = "embargo counted in DISTINCT decision sessions present in the data (index positions), not exchange-calendar sessions; with dense daily data the two coincide"
out["partA_partition"] = partA

# ---------- Part B: metrics ----------
rng = np.random.default_rng(11)
N = 300
p = rng.dirichlet((2.0, 1.5, 1.5), size=N)  # columns: TARGET_FIRST, INVALIDATION_FIRST, TIMEOUT
y = np.array([rng.choice(3, p=row) for row in p])
def ece_mine(yc, pc, bins=10):
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        m = (pc >= lo) & ((pc < hi) if b < bins - 1 else (pc <= hi))
        if m.sum():
            total += m.sum() / len(pc) * abs(yc[m].mean() - pc[m].mean())
    return float(total)
onehot = np.eye(3)[y]
brier_mine = float(np.mean(np.sum((p - onehot) ** 2, axis=1) / 3))
base = onehot.mean(axis=0)
brier_base = float(np.mean(np.sum((np.tile(base, (N, 1)) - onehot) ** 2, axis=1) / 3))
partB = {"n": N, "class_counts": onehot.sum(axis=0).tolist(), "brier_multiclass_mine": brier_mine, "brier_base_mine": brier_base,
         "brier_skill_mine": 1 - brier_mine / brier_base, "classwise": {}}
prod_binary_briers = []
for c, name in enumerate(("TARGET_FIRST", "INVALIDATION_FIRST", "TIMEOUT")):
    yc, pc = onehot[:, c], p[:, c]
    mine = ece_mine(yc, pc)
    bins = dop._calibration_bins(yc, pc)
    prod_ece = sum(float(r["count"]) / N * float(r["absolute_gap"]) for r in bins)
    m = dop._metrics(yc, pc, float(base[c]), 0.0, min_temporal_window=25)
    prod_binary_briers.append(m.brier_score)
    partB["classwise"][name] = {"ece_mine": mine, "ece_production_bins": prod_ece, "ece_production_metrics": m.expected_calibration_error,
                                "ece_agree_1e-12": abs(mine - m.expected_calibration_error) < 1e-12, "binary_brier_production": m.brier_score,
                                "binary_brier_mine": float(np.mean((pc - yc) ** 2)), "n_bins_populated": len(bins)}
partB["brier_multiclass_from_production_binary_mean"] = float(np.mean(prod_binary_briers))
partB["brier_multiclass_agree_1e-12"] = abs(float(np.mean(prod_binary_briers)) - brier_mine) < 1e-12
partB["production_multiclass_function_exists"] = False
partB["production_classwise_ece_function_exists"] = "binary only: canonical_data/dynamic_options_probability._calibration_bins/_metrics (DOI module, not ALG-09)"
out["partB_metrics"] = partB

# ---------- Part C: activation gate boundaries ----------
policy_off = LearningActivationPolicy()
policy_on = LearningActivationPolicy(model_activation_enabled=True)
def synth_records(n_per_stratum=120):
    recs = []; k = 0
    for d in ("CALL", "PUT"):
        for hb, hold in (("1-5", 3), ("6-10", 8), ("11-20", 15)):
            for j in range(n_per_stratum):
                s = sessions[j % 140]
                r = rec(k, s, d); k += 1
                r = OutcomeLearningRecord.create(**{**{f: getattr(r, f) for f in r.__slots__ if f != "record_id"}, "hold_bucket": hb, "planned_hold_sessions": hold})
                recs.append(r)
    return recs
recs = synth_records()
good = {"time_ordered_partitions": True, "confidence_intervals_present": True, "stability_report_present": True, "multiclass_log_loss": 0.9,
        "held_out_count": 300, "maximum_overall_ece": 0.10, "maximum_stratum_ece": 0.15, "multiclass_brier_skill": 0.01, "target_roc_auc": 0.51,
        "target_pr_auc": 0.40, "target_base_rate": 0.35, "target_top_quintile_lift": 1.01}
cases = {
    "zero_records_policy_off": assess_model_activation([], expected_observable_outcomes=0, policy=policy_off),
    "good_metrics_policy_off": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_off, held_out_metrics=good),
    "good_metrics_policy_on": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_on, held_out_metrics=good),
    "ece_0.1001": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_on, held_out_metrics={**good, "maximum_overall_ece": 0.1001}),
    "brier_skill_0_tie": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_on, held_out_metrics={**good, "multiclass_brier_skill": 0.0}),
    "roc_0.50_tie": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_on, held_out_metrics={**good, "target_roc_auc": 0.50}),
    "pr_auc_eq_base_rate_tie": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_on, held_out_metrics={**good, "target_pr_auc": 0.35}),
    "lift_1.0_tie": assess_model_activation(recs, expected_observable_outcomes=len(recs), policy=policy_on, held_out_metrics={**good, "target_top_quintile_lift": 1.0}),
    "coverage_0.59": assess_model_activation(recs, expected_observable_outcomes=int(len(recs) / 0.59) + 1, policy=policy_on, held_out_metrics=good),
}
out["partC_gate"] = {k: {"state": v.state.value, "can_activate": v.can_activate, "reasons": list(v.reason_codes), "coverage": round(v.coverage_fraction, 4)} for k, v in cases.items()}
json.dump(out, open(os.path.join(ROOT, "p14_EH_e3_partition_metrics_out.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
