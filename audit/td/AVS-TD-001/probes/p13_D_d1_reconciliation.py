"""D1 — population reconciliation input = presented + named exceptions, both runs."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d1_reconciliation.json"


def reconcile(run: str) -> dict:
    R = run_dir(run)
    res = {"run": run}
    # Stage 0: discovery input / lifecycle
    lc = read_csv(art(run, "discovery/discovery_lifecycle_<run>.csv"))
    res["lifecycle_rows"] = len(lc)
    res["lifecycle_unique_tickers"] = int(lc["ticker"].nunique()) if "ticker" in lc else None
    res["lifecycle_state_counts"] = vc(lc["lifecycle_state"])
    res["lifecycle_reason_counts"] = vc(lc["reason_code"])
    res["lifecycle_reason_missing_on_dropped"] = int(
        ((lc["lifecycle_state"].astype(str).str.upper() != "SURVIVED") & (~lc["lifecycle_state"].astype(str).str.contains("SURVIV|PASS|PUBLISH", case=False))
         & lc["reason_code"].isna()).sum())
    cds = json.load(open(art(run, "canonical/cds3_discovery_publication_<run>.json")))
    res["cds3"] = {k: cds[k] for k in ("input_count", "survivor_count", "drop_count", "package_worklist_count", "reconciled")}
    disc = read_csv(art(run, "discovery/discovery_candidates_ultimate_<run>.csv"), usecols=["ticker"])
    res["discovery_survivors_rows"] = len(disc)
    res["discovery_survivors_unique"] = int(disc["ticker"].nunique())
    pk = [p for p in (R / "packages").iterdir() if p.name.endswith(".package.json")]
    res["package_files"] = len(pk)
    res["package_index_present"] = (R / "packages" / "index.json").exists()
    pk_tickers = {p.name[:-len(".package.json")] for p in pk}
    res["packages_minus_discovery"] = sorted(pk_tickers - set(disc["ticker"]))[:20]
    res["discovery_minus_packages"] = sorted(set(disc["ticker"]) - pk_tickers)[:20]
    # Vanguard
    vg = read_csv(R / "vanguard" / "vanguard_signals.csv", usecols=["ticker"])
    res["vanguard_rows"] = len(vg)
    res["vanguard_unique"] = int(vg["ticker"].nunique())
    vr = read_csv(R / "vanguard" / "vanguard_rejects.csv")
    res["vanguard_rejects_rows"] = len(vr)
    res["vanguard_rejects_unique"] = int(vr["ticker"].nunique())
    res["vanguard_reject_reasons"] = vc(vr["reason_code"])
    res["vanguard_identity"] = {"packages": len(pk), "passed_unique+rejects_unique": res["vanguard_unique"] + res["vanguard_rejects_unique"]}
    # vanguard_signals_enriched NOT_SCOPED
    vse_path = art(run, "options/vanguard_signals_enriched_<run>.csv")
    hdr = header(vse_path)
    scope_cols = [c for c in hdr if "scope" in c.lower() or "options_status" in c.lower() or c.lower() in ("options_route", "oi_status")]
    vse = read_csv(vse_path, usecols=["ticker"] + scope_cols)
    res["vse_rows"] = len(vse); res["vse_unique"] = int(vse["ticker"].nunique())
    res["vse_scope_cols"] = scope_cols
    res["vse_scope_counts"] = {c: vc(vse[c]) for c in scope_cols if vse[c].nunique() < 40}
    ns_tickers = set()
    for c in scope_cols:
        m = vse[c].astype(str).str.contains("NOT_SCOPED", na=False)
        if m.any():
            ns_tickers |= set(vse.loc[m, "ticker"])
    res["vse_not_scoped_unique_tickers"] = len(ns_tickers)
    # Options intelligence
    oi_hdr = header(art(run, "options/options_intelligence_<run>.csv"))
    oi_cols = [c for c in ("ticker", "governed_direction", "canonical_direction", "direction", "options_direction", "thesis_id", "execution_permission", "trigger_state") if c in oi_hdr]
    oi = read_csv(art(run, "options/options_intelligence_<run>.csv"), usecols=oi_cols)
    res["oi_rows"] = len(oi); res["oi_unique"] = int(oi["ticker"].nunique())
    res["vanguard_to_options_identity"] = {"vanguard_unique": res["vanguard_unique"], "oi_unique": res["oi_unique"], "not_scoped": len(ns_tickers), "gap": res["vanguard_unique"] - res["oi_unique"] - len(ns_tickers)}
    sess = art(run, "options/options_session_exceptions_<run>.csv")
    res["options_session_exceptions"] = len(read_csv(sess)) if sess.exists() else None
    # EIL / execution
    eil = read_csv(art(run, "superbrain/eil_enriched_<run>.csv"), usecols=["ticker"])
    res["eil_rows"] = len(eil); res["eil_unique"] = int(eil["ticker"].nunique())
    ex = read_csv(art(run, "execution/execution_v3_5_<run>.csv"), usecols=["ticker"])
    res["execution_rows"] = len(ex); res["execution_unique"] = int(ex["ticker"].nunique())
    eod = read_csv(art(run, "morning_validation/eod_dropoff_audit_<run>.csv"), usecols=["ticker"])
    res["eod_dropoff_unique"] = int(eod["ticker"].nunique()); res["eod_dropoff_rows"] = len(eod)
    mc = read_csv(art(run, "morning_validation/morning_candidates_<run>.csv"), usecols=["ticker"])
    res["morning_candidates_unique"] = int(mc["ticker"].nunique())
    fob_hdr = header(art(run, "intelligence_lab/final_opportunity_book_<run>.csv"))
    fob_cols = [c for c in ("ticker", "governed_direction", "final_direction", "canonical_direction", "direction", "lab_execution_status", "gate_reason", "execution_eligibility_state", "morning_execution_permission", "morning_execution_route", "morning_execution_lane") if c in fob_hdr]
    fob = read_csv(art(run, "intelligence_lab/final_opportunity_book_<run>.csv"), usecols=fob_cols)
    res["fob_rows"] = len(fob); res["fob_unique"] = int(fob["ticker"].nunique())
    dcol = "governed_direction" if "governed_direction" in fob else "direction"
    res["fob_direction_col"] = dcol
    res["fob_direction_split"] = vc(direction_bucket(fob[dcol]))
    res["fob_raw_direction_values"] = vc(fob[dcol])
    for c in ("lab_execution_status", "execution_eligibility_state", "morning_execution_permission", "morning_execution_lane"):
        if c in fob:
            res[f"fob_{c}"] = vc(fob[c])
    v3p = R / "intelligence_lab" / "lab_signal_book_v3.csv"
    if v3p.exists():
        v3 = read_csv(v3p, usecols=[c for c in ("ticker", "governed_direction", "direction") if c in header(v3p)])
        res["v3_rows"] = len(v3)
        res["v3_direction_split"] = vc(direction_bucket(v3["governed_direction" if "governed_direction" in v3 else "direction"]))
        # named exceptions for fob -> v3 : rows with non-GO status
        if "lab_execution_status" in fob:
            res["fob_to_v3_identity"] = {"fob": len(fob), "v3": len(v3), "fob_non_v3_with_status": int((~fob["ticker"].isin(v3["ticker"])).sum()),
                                         "status_of_non_v3": vc(fob.loc[~fob["ticker"].isin(v3["ticker"]), "lab_execution_status"])}
    else:
        res["v3_rows"] = None
    mvt = art(run, "morning_validation/morning_validated_trades_<run>.csv")
    if mvt.exists():
        mh = header(mvt)
        mcols = [c for c in ("ticker", "morning_permission", "morning_state", "governed_direction", "effective_execution_verdict") if c in mh]
        m = read_csv(mvt, usecols=mcols)
        res["mvt_rows"] = len(m)
        for c in mcols[1:]:
            res[f"mvt_{c}"] = vc(m[c])
    # Dropoff audit attribution of the 3,320
    da = read_csv(art(run, "diagnostics/dropoff_audit_<run>.csv"), usecols=["ticker", "last_stage_reached", "dropoff_stage", "dropoff_reason", "audit_layer", "root_cause_family", "morning_state"])
    res["dropoff_rows"] = len(da); res["dropoff_unique"] = int(da["ticker"].nunique())
    res["dropoff_last_stage"] = vc(da["last_stage_reached"])
    res["dropoff_stage"] = vc(da["dropoff_stage"])
    res["dropoff_root_cause"] = vc(da["root_cause_family"])
    res["dropoff_reason_top"] = dict(list(vc(da["dropoff_reason"]).items())[:30])
    unexplained = da[da["dropoff_reason"].isna() | da["dropoff_reason"].astype(str).str.strip().isin(["", "nan", "UNCLASSIFIED", "UNKNOWN"]) | da["root_cause_family"].astype(str).eq("UNCLASSIFIED")]
    res["dropoff_unexplained_rows"] = len(unexplained)
    res["dropoff_unexplained_by_stage"] = vc(unexplained["dropoff_stage"])
    res["dropoff_unexplained_reason_values"] = vc(unexplained["dropoff_reason"])
    res["dropoff_unexplained_sample"] = sorted(unexplained["ticker"].astype(str))[:15]
    # Are "unexplained" tickers in the final book?
    res["dropoff_unexplained_in_fob"] = int(unexplained["ticker"].isin(fob["ticker"]).sum())
    res["dropoff_universe_vs_lifecycle"] = {"dropoff_tickers": len(set(da["ticker"])), "lifecycle_tickers": len(set(lc["ticker"])), "symdiff": len(set(da["ticker"]) ^ set(lc["ticker"]))}
    # Run's own counts
    man = json.load(open(R / "final_run_manifest.json"))
    res["manifest_row_counts"] = man.get("row_counts")
    pi = json.load(open(art(run, "pipeline_integrity_<run>.json")))
    res["pipeline_integrity_eil_total_rows"] = pi.get("eil_total_rows")
    osum = json.load(open(art(run, "options/options_intelligence_summary_<run>.json")))
    res["options_summary"] = {k: osum.get(k) for k in ("signals_scoped", "signals_processed", "execute", "armed", "stand_down", "route_counts")}
    res["options_summary_cds_chain"] = osum.get("cds_chain_telemetry")
    doi = json.load(open(art(run, "options/dynamic_options_intelligence_<run>.json")))
    res["doi_counts"] = {k: doi.get(k) for k in ("input_rows", "unique_tickers", "retained_opportunities", "family_rows", "counts_by_state", "exception_count")}
    # Identity ladder
    ladder = []
    def step(name, inp, out, named, note=""):
        ladder.append({"transition": name, "input": inp, "presented": out, "named_exceptions": named, "gap": inp - out - named, "note": note})
    step("discovery input -> survivors", res["cds3"]["input_count"], res["discovery_survivors_unique"], sum(v for k, v in res["lifecycle_reason_counts"].items()) - 0, "named = lifecycle reason_code rows (see lifecycle_state_counts to separate survivors)")
    step("survivors -> packages", res["discovery_survivors_unique"], len(pk), 0)
    step("packages -> vanguard passed", len(pk), res["vanguard_unique"], res["vanguard_rejects_unique"], "vanguard_rejects.csv")
    step("vanguard passed -> options scoped", res["vanguard_unique"], res["oi_unique"], len(ns_tickers), "NOT_SCOPED tickers in vanguard_signals_enriched")
    step("options -> EIL", res["oi_unique"], res["eil_unique"], 0)
    step("EIL -> execution", res["eil_unique"], res["execution_unique"], 0)
    step("execution -> EOD dropoff/morning candidates", res["execution_unique"], res["morning_candidates_unique"], 0)
    step("morning candidates -> Lab final book", res["morning_candidates_unique"], res["fob_unique"], 0)
    if res.get("v3_rows") is not None:
        step("Lab final book -> lab_signal_book_v3 (GO)", res["fob_unique"], res["v3_rows"], res["fob_to_v3_identity"]["fob_non_v3_with_status"] if "fob_to_v3_identity" in res else 0, "named = non-GO lab_execution_status rows")
    res["ladder"] = ladder
    return res


if __name__ == "__main__":
    out = {r: reconcile(r) for r in (PRIMARY, COMPARISON)}
    dump(out, OUT)
    for r, v in out.items():
        print("\n==", r)
        for s in v["ladder"]:
            print(s)
        print("dropoff stage", v["dropoff_stage"]); print("unexplained", v["dropoff_unexplained_rows"], v["dropoff_unexplained_by_stage"])
        print("fob split", v["fob_direction_split"], "lifecycle states", v["lifecycle_state_counts"])
