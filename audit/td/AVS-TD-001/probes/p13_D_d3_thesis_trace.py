"""D3 — thesis_id trace: DOI input CSV vs governed book; governed_direction_records; control_plane tables."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d3_thesis_trace.json"

DOI_FIELDS = ["ticker", "thesis_id", "legacy_thesis_id", "thesis_version", "governed_direction", "canonical_direction", "direction",
              "planned_hold_sessions", "hold_sessions", "underlying_price", "spot_price", "current_price", "signal_price",
              "quote_timestamp_utc", "evidence_cutoff_utc", "selected_quote_timestamp_utc", "target_spot", "structural_target",
              "target_price", "invalidation_spot", "structural_invalidation", "stop_loss", "ev3_rate_used", "risk_free_rate"]


def trace(run: str) -> dict:
    res = {"run": run}
    oi_path = art(run, "options/options_intelligence_<run>.csv")
    oh = header(oi_path)
    cols = [c for c in DOI_FIELDS if c in oh]
    res["doi_input_columns_present"] = cols
    res["doi_input_columns_absent"] = [c for c in DOI_FIELDS if c not in oh]
    oi = read_csv(oi_path, usecols=cols)
    oi["ticker"] = oi["ticker"].astype(str).str.strip().str.upper()
    res["oi_rows"] = len(oi); res["oi_unique"] = int(oi["ticker"].nunique())
    first = oi.drop_duplicates("ticker", keep="first")  # what run_completed_session_doi does (dynamic_options_production.py:141)
    def present(s):
        return s.notna() & s.astype(str).str.strip().ne("") & ~s.astype(str).str.strip().isin(["None", "nan"])
    res["oi_first_row_thesis_id_present"] = int(present(first["thesis_id"]).sum()) if "thesis_id" in first else None
    res["oi_first_row_thesis_id_missing"] = int((~present(first["thesis_id"])).sum()) if "thesis_id" in first else None
    missing_first = sorted(first.loc[~present(first["thesis_id"]), "ticker"]) if "thesis_id" in first else []
    res["oi_first_row_thesis_id_missing_tickers"] = missing_first
    # any-row presence per ticker
    anyp = oi.assign(p=present(oi["thesis_id"])).groupby("ticker")["p"].any()
    res["oi_any_row_thesis_id_present_tickers"] = int(anyp.sum())
    res["oi_tickers_missing_thesis_in_all_rows"] = sorted(anyp[~anyp].index)
    # direction of the first rows
    dcol = next(c for c in ("governed_direction", "canonical_direction", "direction") if c in first)
    fb = direction_bucket(first[dcol])
    res["oi_first_direction_split"] = vc(fb)
    res["oi_first_thesis_missing_by_direction"] = vc(fb[~present(first["thesis_id"])])
    # other required DOI fields on first rows
    for name, alts in {"spot": ["underlying_price", "spot_price", "current_price", "signal_price"], "hold": ["planned_hold_sessions", "hold_sessions"],
                       "cutoff": ["quote_timestamp_utc", "evidence_cutoff_utc", "selected_quote_timestamp_utc"], "target": ["target_spot", "structural_target", "target_price"],
                       "invalidation": ["invalidation_spot", "structural_invalidation", "stop_loss"]}.items():
        avail = [a for a in alts if a in first]
        ok = pd.Series(False, index=first.index)
        for a in avail:
            ok |= present(first[a])
        res[f"oi_first_{name}_present"] = {"cols": avail, "present": int(ok.sum()), "missing": int((~ok).sum())}
    # DOI report exceptions
    doi = json.load(open(art(run, "options/dynamic_options_intelligence_<run>.json")))
    exc = [e["ticker"] for e in doi.get("exceptions", []) if e.get("reason") == "MISSING_GOVERNED_THESIS_ID"]
    res["doi_report_missing_thesis_exceptions"] = len(exc)
    res["doi_report_exception_tickers"] = sorted(exc)
    res["reconcile_first_row_vs_report"] = {"probe_missing": len(missing_first), "report": len(exc), "probe_minus_report": sorted(set(missing_first) - set(exc)), "report_minus_probe": sorted(set(exc) - set(missing_first))}
    # directional filter: report counts NOT_APPLICABLE_NON_DIRECTIONAL before thesis check
    res["oi_first_nondirectional"] = int((fb == "OTHER").sum())
    res["report_non_directional"] = doi["counts_by_state"].get("NOT_APPLICABLE_NON_DIRECTIONAL")
    # Join to governed book
    fob_path = art(run, "intelligence_lab/final_opportunity_book_<run>.csv")
    fh = header(fob_path)
    fcols = [c for c in ("ticker", "thesis_id", "governed_direction", "final_direction", "direction", "contract_symbol") if c in fh]
    fob = read_csv(fob_path, usecols=fcols)
    fob["ticker"] = fob["ticker"].astype(str).str.strip().str.upper()
    res["fob_rows"] = len(fob); res["fob_thesis_id_present"] = int(present(fob["thesis_id"]).sum())
    j = fob.merge(first[["ticker", "thesis_id", dcol]].rename(columns={"thesis_id": "doi_thesis_id", dcol: "doi_dir"}), on="ticker", how="left")
    jb = direction_bucket(j["governed_direction" if "governed_direction" in j else "direction"])
    j["doi_missing"] = ~present(j["doi_thesis_id"])
    j["differs"] = present(j["doi_thesis_id"]) & present(j["thesis_id"]) & (j["doi_thesis_id"].astype(str) != j["thesis_id"].astype(str))
    j["not_in_doi_input"] = ~j["ticker"].isin(first["ticker"])
    res["join"] = {"fob_rows": len(j), "not_in_doi_input": int(j["not_in_doi_input"].sum()), "doi_thesis_missing": int(j["doi_missing"].sum()), "thesis_differs": int(j["differs"].sum()),
                   "by_direction": {k: {"rows": int((jb == k).sum()), "doi_missing": int((j["doi_missing"] & (jb == k)).sum()), "differs": int((j["differs"] & (jb == k)).sum())} for k in ("CALL", "PUT", "OTHER")}}
    res["join_differs_examples"] = j.loc[j["differs"], ["ticker", "thesis_id", "doi_thesis_id"]].head(10).to_dict("records")
    res["join_missing_examples"] = j.loc[j["doi_missing"], ["ticker", "thesis_id", "doi_thesis_id"]].head(10).to_dict("records")
    # do the DOI exceptions have a thesis_id in the governed book?
    res["exception_tickers_with_fob_thesis"] = int(present(fob.loc[fob["ticker"].isin(exc), "thesis_id"]).sum())
    # thesis_id in any options row vs in fob for exceptions
    res["exception_tickers_any_row_thesis_present"] = int(anyp.reindex(exc).fillna(False).sum())
    # direction agreement between DOI input first row and governed book
    res["direction_disagree_first_row_vs_fob"] = int((direction_bucket(j["doi_dir"]) != jb).sum())
    # governed_direction_records jsonl
    gp = art(run, "options/governed_direction_records_<run>.jsonl")
    n = 0; keys = set(); with_thesis = 0
    with open(gp, encoding="utf-8") as fh_:
        for line in fh_:
            d = json.loads(line); n += 1; keys |= set(d.keys())
            if str(d.get("thesis_id") or "").strip():
                with_thesis += 1
    res["governed_direction_records"] = {"rows": n, "keys": sorted(keys), "with_thesis_id": with_thesis}
    return res


def control_plane() -> dict:
    res = {}
    with ro_conn("control_plane.sqlite") as c:
        res["option_thesis_events_by_run"] = c.execute("SELECT run_id, COUNT(*), SUM(thesis_id IS NOT NULL AND thesis_id<>''), COUNT(DISTINCT thesis_id), COUNT(DISTINCT ticker) FROM option_thesis_events GROUP BY run_id ORDER BY run_id").fetchall()
        res["doi_contract_families_by_run"] = c.execute("SELECT run_id, COUNT(*), SUM(thesis_id IS NOT NULL AND thesis_id<>''), COUNT(DISTINCT thesis_id), COUNT(DISTINCT ticker), MIN(created_at), MAX(created_at) FROM doi_contract_families GROUP BY run_id ORDER BY run_id").fetchall()
        res["doi_contract_families_states"] = c.execute("SELECT family_state, COUNT(*) FROM doi_contract_families GROUP BY 1").fetchall()
        res["doi_contract_families_direction"] = c.execute("SELECT run_id, governed_direction, COUNT(*) FROM doi_contract_families GROUP BY 1,2").fetchall()
        res["doi_contract_assessments"] = c.execute("SELECT COUNT(*) FROM doi_contract_assessments").fetchone()[0]
        res["doi_preferred_contract_decisions"] = c.execute("SELECT COUNT(*) FROM doi_preferred_contract_decisions").fetchone()[0]
        res["option_thesis_events_reason_by_run"] = c.execute("SELECT run_id, reason_code, thesis_state, COUNT(*) FROM option_thesis_events WHERE run_id IN (?,?) GROUP BY 1,2,3", (PRIMARY, COMPARISON)).fetchall()
        # families for the two runs: thesis_id join to option_thesis_events
        res["families_thesis_joined_to_events"] = c.execute("SELECT f.run_id, COUNT(*), SUM(EXISTS(SELECT 1 FROM option_thesis_events e WHERE e.thesis_id=f.thesis_id)) FROM doi_contract_families f WHERE f.run_id IN (?,?) GROUP BY 1", (PRIMARY, COMPARISON)).fetchall()
        res["thesis_id_sample"] = c.execute("SELECT thesis_id, ticker, run_id FROM doi_contract_families WHERE run_id=? LIMIT 3", (PRIMARY,)).fetchall()
    return res


if __name__ == "__main__":
    out = {r: trace(r) for r in (PRIMARY, COMPARISON)}
    out["control_plane"] = control_plane()
    dump(out, OUT)
    for r in (PRIMARY, COMPARISON):
        v = out[r]
        print(r, "first-row thesis missing", v["oi_first_row_thesis_id_missing"], "report", v["doi_report_missing_thesis_exceptions"], v["reconcile_first_row_vs_report"], "join", v["join"], "gdr", v["governed_direction_records"]["with_thesis_id"], "nondir", v["oi_first_nondirectional"], v["report_non_directional"])
    print(json.dumps(out["control_plane"], indent=1, default=str))
