"""D3b — the 38 MISSING_GOVERNED_THESIS_ID tickers: what the options CSV / final book / control plane say about them;
doi_contract_families created_at vs run; thesis_id format census."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d3b_exceptions.json"


def one(run: str) -> dict:
    res = {"run": run}
    doi = json.load(open(art(run, "options/dynamic_options_intelligence_<run>.json")))
    exc = sorted(e["ticker"] for e in doi["exceptions"] if e["reason"] == "MISSING_GOVERNED_THESIS_ID")
    oi = read_csv(art(run, "options/options_intelligence_<run>.csv"), usecols=["ticker", "thesis_id", "thesis_state", "liquidity_state", "liquidity_lifecycle_reason", "recommended_contract", "governed_direction", "contract_quote_timestamp_utc", "quote_timestamp_utc"]).drop_duplicates("ticker")
    sub = oi[oi["ticker"].isin(exc)]
    res["exceptions_n"] = len(exc)
    res["exc_options_csv"] = {"liquidity_state": vc(sub["liquidity_state"]), "liquidity_lifecycle_reason": vc(sub["liquidity_lifecycle_reason"]), "thesis_state": vc(sub["thesis_state"]),
                              "recommended_contract_present": int(sub["recommended_contract"].notna().sum()), "governed_direction": vc(sub["governed_direction"]),
                              "quote_timestamp_present": int(sub["quote_timestamp_utc"].notna().sum())}
    rej = read_csv(art(run, "options/contract_rejection_log_<run>.csv"))
    res["exc_rejection_log"] = vc(rej.loc[rej["ticker"].isin(exc), "rejection_reason"])
    fob = read_csv(art(run, "intelligence_lab/final_opportunity_book_<run>.csv"), usecols=["ticker", "thesis_id", "thesis_state", "governed_direction", "lab_execution_status", "morning_execution_permission", "doi_projection_state"])
    fs = fob[fob["ticker"].isin(exc)]
    res["exc_final_book"] = {"thesis_id_sample": fs["thesis_id"].head(6).tolist(), "thesis_state": vc(fs["thesis_state"]), "lab_execution_status": vc(fs["lab_execution_status"]),
                            "morning_execution_permission": vc(fs["morning_execution_permission"]), "doi_projection_state": vc(fs["doi_projection_state"])}
    # thesis_id format census on the final book
    fmt = fob["thesis_id"].astype(str).str.replace(r"^[A-Z.\-]+:", "T:", regex=True).str.replace(r"\d{8}_\d{6}", "<run>", regex=True).str.replace(r"\d{4}-\d{2}-\d{2}", "<date>", regex=True)
    res["fob_thesis_id_formats"] = vc(fmt)
    ofmt = oi["thesis_id"].astype(str).str.replace(r"^[A-Z.\-]+:", "T:", regex=True).str.replace(r"\d{8}_\d{6}", "<run>", regex=True).str.replace(r"\d{4}-\d{2}-\d{2}", "<date>", regex=True)
    res["options_csv_thesis_id_formats"] = vc(ofmt)
    # do fob and options CSV thesis ids agree where both present?
    j = fob.merge(oi[["ticker", "thesis_id"]].rename(columns={"thesis_id": "oi_thesis"}), on="ticker", how="left")
    both = j["thesis_id"].notna() & j["oi_thesis"].notna()
    res["thesis_agree_where_both_present"] = {"both": int(both.sum()), "equal": int((both & (j["thesis_id"] == j["oi_thesis"])).sum())}
    with ro_conn("control_plane.sqlite") as c:
        res["thesis_events_for_exceptions"] = c.execute(f"SELECT reason_code, thesis_state, COUNT(*) FROM option_thesis_events WHERE run_id=? AND ticker IN ({','.join('?'*len(exc))}) GROUP BY 1,2", (run, *exc)).fetchall() if exc else []
        res["families_for_exceptions"] = c.execute(f"SELECT COUNT(*) FROM doi_contract_families WHERE run_id=? AND ticker IN ({','.join('?'*len(exc))})", (run, *exc)).fetchone()[0] if exc else 0
        res["families_created_at_vs_origin"] = c.execute("SELECT MIN(created_at), MAX(created_at), MIN(origin_timestamp_utc), MAX(origin_timestamp_utc), MIN(evidence_cutoff_utc), MAX(evidence_cutoff_utc), MIN(thesis_evidence_cutoff_utc), MAX(thesis_evidence_cutoff_utc) FROM doi_contract_families WHERE run_id=?", (run,)).fetchone()
        res["families_sample"] = [dict(zip([d[0] for d in c.execute("SELECT * FROM doi_contract_families LIMIT 0").description], r)) for r in c.execute("SELECT * FROM doi_contract_families WHERE run_id=? LIMIT 1", (run,)).fetchall()]
        for r in res["families_sample"]:
            r["candidate_symbols_json"] = str(r["candidate_symbols_json"])[:120]; r["metadata_json"] = str(r["metadata_json"])[:300]
        res["families_thesis_version"] = c.execute("SELECT thesis_version, family_policy_version, COUNT(*) FROM doi_contract_families WHERE run_id=? GROUP BY 1,2", (run,)).fetchall()
    return res


if __name__ == "__main__":
    out = {r: one(r) for r in (PRIMARY, COMPARISON)}
    dump(out, OUT)
    print(json.dumps(out, indent=1, default=str)[:6000])
