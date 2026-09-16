"""D1b — corrections to p13_D_d1: ticker-grain identity from dropoff_audit, NOT_SCOPED via options_verdict,
discovery named exceptions = dropped rows only, DOI grain identity, CALL/PUT/OTHER split at governed-book grain."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d1b_identity.json"


def one(run: str) -> dict:
    R = run_dir(run); res = {"run": run}
    lc = read_csv(art(run, "discovery/discovery_lifecycle_<run>.csv"))
    surv = lc["lifecycle_state"].eq("ACTIVE_CORE")
    res["discovery"] = {"input": len(lc), "survivors": int(surv.sum()), "dropped_with_reason": int((~surv & lc["reason_code"].notna()).sum()),
                        "dropped_without_reason": int((~surv & lc["reason_code"].isna()).sum()),
                        "gap": len(lc) - int(surv.sum()) - int((~surv & lc["reason_code"].notna()).sum())}
    vse_p = art(run, "options/vanguard_signals_enriched_<run>.csv")
    vse = read_csv(vse_p, usecols=["ticker", "options_verdict", "options_route_verdict", "final_route", "verdict"])
    oi = read_csv(art(run, "options/options_intelligence_<run>.csv"), usecols=["ticker", "governed_direction"])
    vse["in_oi"] = vse["ticker"].isin(oi["ticker"])
    res["vse"] = {"rows": len(vse), "in_options_csv": int(vse["in_oi"].sum()), "not_in_options_csv": int((~vse["in_oi"]).sum()),
                  "options_verdict_of_missing": vc(vse.loc[~vse["in_oi"], "options_verdict"]),
                  "options_verdict_all": vc(vse["options_verdict"]),
                  "final_route_of_missing": vc(vse.loc[~vse["in_oi"], "final_route"])}
    ns = vse["options_verdict"].astype(str).str.upper().eq("NOT_SCOPED")
    res["vse"]["not_scoped_rows"] = int(ns.sum()); res["vse"]["not_scoped_and_missing"] = int((ns & ~vse["in_oi"]).sum())
    res["vse"]["missing_not_labelled_not_scoped"] = int((~ns & ~vse["in_oi"]).sum())
    # ticker-grain attribution from dropoff audit
    da = read_csv(art(run, "diagnostics/dropoff_audit_<run>.csv"), usecols=["ticker", "last_stage_reached", "dropoff_stage", "dropoff_reason", "root_cause_family", "eod_status", "morning_state", "morning_permission"])
    fob = read_csv(art(run, "intelligence_lab/final_opportunity_book_<run>.csv"), usecols=["ticker", "governed_direction", "lab_execution_status"])
    da["in_fob"] = da["ticker"].isin(fob["ticker"])
    res["dropoff_stage_x_in_fob"] = {str(k): int(v) for k, v in da.groupby(["dropoff_stage", "in_fob"]).size().items()}
    res["last_stage_x_in_fob"] = {str(k): int(v) for k, v in da.groupby(["last_stage_reached", "in_fob"]).size().items()}
    res["stage_reason_not_in_fob"] = {str(k): int(v) for k, v in da[~da["in_fob"]].groupby(["dropoff_stage", "root_cause_family"]).size().items()}
    noreason = da[~da["in_fob"] & (da["dropoff_reason"].isna() | da["dropoff_reason"].astype(str).str.strip().eq(""))]
    res["not_in_fob_without_reason"] = len(noreason)
    res["identity_ticker_grain"] = {"input": len(da), "presented_in_fob": int(da["in_fob"].sum()), "named_exceptions_not_in_fob_with_reason": int((~da["in_fob"]).sum()) - len(noreason),
                                    "unexplained": len(noreason)}
    res["identity_ticker_grain"]["gap"] = len(da) - res["identity_ticker_grain"]["presented_in_fob"] - res["identity_ticker_grain"]["named_exceptions_not_in_fob_with_reason"]
    # in-book rows that the dropoff audit labels as OPTIONS_INTELLIGENCE drop-offs (retained with blocking reason)
    res["in_fob_labelled_dropoff"] = {str(k): int(v) for k, v in da[da["in_fob"] & da["dropoff_stage"].ne("AFTER_EOD_BEFORE_MORNING")].groupby(["dropoff_stage", "dropoff_reason"]).size().sort_values(ascending=False).head(12).items()}
    # DOI grain identity from report
    doi = json.load(open(art(run, "options/dynamic_options_intelligence_<run>.json")))
    cs = doi["counts_by_state"]
    res["doi_grain"] = {"input_rows": doi["input_rows"], "family_rows": doi["family_rows"], "non_directional": cs.get("NOT_APPLICABLE_NON_DIRECTIONAL"), "exceptions": doi["exception_count"],
                        "gap": doi["input_rows"] - doi["family_rows"] - cs.get("NOT_APPLICABLE_NON_DIRECTIONAL", 0) - doi["exception_count"], "deleted_opportunities": doi.get("deleted_opportunities")}
    # CALL/PUT/OTHER at governed-book grain, with per-direction identity to v3
    b = direction_bucket(fob["governed_direction"])
    v3p = R / "intelligence_lab" / "lab_signal_book_v3.csv"
    v3t = set(read_csv(v3p, usecols=["ticker"])["ticker"]) if v3p.exists() else set()
    res["book_by_direction"] = {}
    for k in ("CALL", "PUT", "OTHER"):
        m = b == k
        res["book_by_direction"][k] = {"book_rows": int(m.sum()), "raw_values": vc(fob.loc[m, "governed_direction"]), "in_v3": int((m & fob["ticker"].isin(v3t)).sum()),
                                       "lab_execution_status": vc(fob.loc[m, "lab_execution_status"]), "doi_input_rows": int(direction_bucket(oi["governed_direction"]).eq(k).sum())}
    # vanguard signals unique tickers (49,966 rows)
    vg = read_csv(R / "vanguard" / "vanguard_signals.csv", usecols=["ticker"])
    res["vanguard_signals"] = {"rows": len(vg), "unique_tickers": int(vg["ticker"].nunique())}
    man = json.load(open(R / "final_run_manifest.json"))
    res["manifest_row_counts"] = man.get("row_counts")
    return res


if __name__ == "__main__":
    out = {r: one(r) for r in (PRIMARY, COMPARISON)}
    dump(out, OUT)
    for r, v in out.items():
        print(r, json.dumps({k: v[k] for k in ("discovery", "identity_ticker_grain", "doi_grain", "vanguard_signals")}, default=str))
        print("  vse:", json.dumps(v["vse"], default=str)); print("  stage x in_fob:", v["dropoff_stage_x_in_fob"]); print("  by dir:", json.dumps(v["book_by_direction"], default=str)[:1200])
