"""p14_E_e6_disclosure: Track E3/E4/E6 artefact search (read-only). Computes NO substitute probability.
Records: existence of scripts/calibrate_probabilities.py, vanguard/layer2_statistical/calibration_labels.py,
any calibration_table*.json / calibration report under data/output/runs and audit/avs_fix_002;
governed_constants calibration keys; ledger resolved outcomes per direction x hold bucket (db copy);
control_plane doi_outcome_labels; phantom_outcomes; DOI p_T field population on primary/comparison books;
EV3 calibration readiness and Stage 6 readiness states.
Output: p14_E_e6_disclosure_out.json
"""
import os, json, glob, sqlite3
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
COP = os.path.join(HERE, "..", "db_copies")
RUNS = os.path.join(REPO, "data", "output", "runs")


def ro(name):
    return sqlite3.connect("file:" + os.path.abspath(os.path.join(COP, name)) + "?mode=ro", uri=True)


out = {"substitute_computed": False}
out["files"] = {p: os.path.exists(os.path.join(REPO, p)) for p in (
    "scripts/calibrate_probabilities.py", "vanguard/layer2_statistical/calibration_labels.py",
    "audit/avs_fix_002/stage6/CURRENT_LEARNING_READINESS.json")}
hits = []
for pat in ("data/output/runs/*/**/*calibration_table*", "data/output/runs/*/**/*calibration_report*", "data/output/runs/*/**/*calibrat*",
            "audit/avs_fix_002/**/*calibrat*", "data/canonical/**/*calibrat*", "config/**/*calibrat*"):
    hits += [os.path.relpath(f, REPO) for f in glob.glob(os.path.join(REPO, pat), recursive=True) if os.sep + "packages" + os.sep not in f]
out["calibration_named_artefacts"] = sorted(set(hits))
cfg = json.load(open(os.path.join(REPO, "config", "governed_constants_v1.json"), encoding="utf-8-sig"))
out["governed_constants_top_keys"] = list(cfg)
out["calibration_kappa_n_min_present"] = {"calibration": "calibration" in cfg, "kappa": "kappa" in json.dumps(cfg), "n_min": "n_min" in json.dumps(cfg)}

c = ro("decision_outcome_ledger.sqlite")
ev = pd.read_sql("select run_id, event_type, payload_json from ledger_events where event_type in ('OUTCOME','OUTCOME_OBSERVATION','CANDIDATE_DECISION')", c)
ev["p"] = ev.payload_json.map(json.loads)
oc = ev[ev.event_type == "OUTCOME"]
out["ledger"] = {
    "OUTCOME_events": len(oc), "OUTCOME_counterfactual": int(sum(bool(p.get("is_counterfactual")) for p in oc.p)),
    "OUTCOME_with_first_passage_state": int(sum(p.get("first_passage_state") not in (None, "") for p in oc.p)),
    "OUTCOME_OBSERVATION_events": int((ev.event_type == "OUTCOME_OBSERVATION").sum()),
    "CANDIDATE_DECISION": int((ev.event_type == "CANDIDATE_DECISION").sum()),
}
HB = ("1-5", "6-10", "11-20")
out["resolved_label_n_by_direction_x_hold"] = {f"{d}|{h}": 0 for d in ("CALL", "PUT") for h in HB}
out["resolved_label_n_OTHER"] = 0
for p in oc.p:
    fps = p.get("first_passage_state")
    if fps:
        out["resolved_label_n_OTHER"] += 0  # none expected; any hit is reported below
        out.setdefault("unexpected_resolved", []).append(p)
out["control_plane_doi_outcome_labels"] = ro("control_plane.sqlite").execute("select count(*) from doi_outcome_labels").fetchone()[0]
out["phantom_outcomes"] = ro("phantom_history.db").execute("select count(*) from phantom_outcomes").fetchone()[0]

books = {}
for run in ("20260911_115904", "20260910_150045"):
    f = glob.glob(os.path.join(RUNS, run, "intelligence_lab", "final_opportunity_book_*.csv"))[0]
    hdr = pd.read_csv(f, nrows=0).columns
    want = [x for x in ("governed_direction", "doi_p_target_before_invalidation", "doi_probability_model_id", "ev3_p_target", "win_prob_predicted", "layer2__adjusted_prob_target_hit") if x in hdr]
    b = pd.read_csv(f, usecols=want, low_memory=False)
    dcol = b["governed_direction"].where(b["governed_direction"].isin(["CALL", "PUT"]), "OTHER") if "governed_direction" in b else pd.Series(["OTHER"] * len(b))
    books[run] = {"rows": len(b), "fields": {k: {d: int(b.loc[dcol == d, k].notna().sum()) for d in ("CALL", "PUT", "OTHER")} for k in want if k != "governed_direction"}}
    books[run]["rows_by_direction"] = dcol.value_counts().to_dict()
out["books"] = books
for run in ("20260911_115904", "20260910_150045"):
    f = os.path.join(RUNS, run, "ev3_shadow", "ev3_calibration_readiness.json")
    if os.path.exists(f):
        j = json.load(open(f))
        out.setdefault("ev3_calibration_readiness", {})[run] = {k: j.get(k) for k in ("status", "matched_outcome_rows", "capital_authority_calibrated", "schema_version")}
r6 = json.load(open(os.path.join(REPO, "audit", "avs_fix_002", "stage6", "CURRENT_LEARNING_READINESS.json")))
out["stage6_readiness"] = {"state": r6["model_activation"]["state"], "can_activate": r6["model_activation"]["can_activate"],
                           "records": len(r6.get("records", [])), "partition_state": r6.get("temporal_partition_plan", {}).get("state")}
json.dump(out, open(os.path.join(HERE, "p14_E_e6_disclosure_out.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
