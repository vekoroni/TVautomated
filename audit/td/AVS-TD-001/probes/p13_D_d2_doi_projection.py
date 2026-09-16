"""D2 — doi_projection_state distribution on the Lab books, CALL/PUT/OTHER."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d2_doi_projection.json"


def analyse(run: str, rel: str, label: str) -> dict:
    p = art(run, rel)
    if not p.exists():
        return {"missing": str(p)}
    hdr = header(p)
    doi_cols = [c for c in hdr if c.startswith("doi_")]
    dcol = next((c for c in ("governed_direction", "final_direction", "direction") if c in hdr), None)
    cols = ["ticker"] + doi_cols + ([dcol] if dcol else []) + [c for c in ("contract_symbol", "morning_selected_contract_symbol", "selected_contract_symbol", "recommended_contract", "preferred_contract") if c in hdr]
    df = read_csv(p, usecols=cols)
    b = direction_bucket(df[dcol]) if dcol else pd.Series("OTHER", index=df.index)
    res = {"file": str(p), "rows": len(df), "direction_col": dcol, "doi_cols": doi_cols}
    for c in ("doi_projection_state", "doi_projection_reason", "doi_contract_alignment", "doi_ranking_mode", "doi_governed_contract_identity_state", "doi_governed_contract_identity_reason", "doi_projection_version", "doi_authority", "doi_decision_authority", "doi_execution_authority", "doi_ranking_score_kind", "doi_calibration_state"):
        if c in df:
            res[c] = {"ALL": vc(df[c]), **{k: vc(df.loc[b == k, c]) for k in ("CALL", "PUT", "OTHER")}}
    for c in ("doi_preferred_contract_symbol", "doi_governed_contract_symbol", "doi_preferred_assessment_id", "doi_family_id", "doi_ranking_id", "doi_p_liquidity_3d", "doi_p_positive_return", "doi_p_target_before_invalidation", "doi_model_uncertainty", "doi_alternatives_json", "doi_evidence_cutoff_utc"):
        if c in df:
            nn = df[c].notna() & df[c].astype(str).str.strip().ne("") & df[c].astype(str).str.strip().ne("[]")
            res[f"nonnull_{c}"] = {"ALL": int(nn.sum()), **{k: int((nn & (b == k)).sum()) for k in ("CALL", "PUT", "OTHER")}}
    # identity mismatch analysis: governed contract vs book contract symbol
    if "doi_governed_contract_symbol" in df and "contract_symbol" in df:
        g = df["doi_governed_contract_symbol"].astype(str).str.strip(); s = df["contract_symbol"].astype(str).str.strip()
        res["governed_vs_contract_symbol_equal"] = int(((g == s) & g.ne("") & g.ne("nan")).sum())
        res["governed_symbol_empty"] = int((g.eq("") | g.eq("nan")).sum())
    if "doi_projection_state" in df and "doi_projection_reason" in df:
        res["state_x_reason"] = {str(k): int(v) for k, v in df.groupby(["doi_projection_state", "doi_projection_reason"], dropna=False).size().items()}
    if "doi_projection_state" in df and "doi_governed_contract_symbol" in df:
        mm = df["doi_projection_state"].astype(str).str.contains("MISMATCH")
        res["mismatch_examples"] = df.loc[mm, ["ticker", "doi_governed_contract_symbol", "contract_symbol"] + [c for c in ("doi_projection_reason", "doi_governed_contract_identity_reason") if c in df]].head(10).to_dict("records")
    return res


if __name__ == "__main__":
    out = {}
    for run in (PRIMARY, COMPARISON):
        out[run] = {
            "final_opportunity_book": analyse(run, "intelligence_lab/final_opportunity_book_<run>.csv", "fob"),
            "lab_triage_view": analyse(run, "intelligence_lab/lab_triage_view_<run>.csv", "triage"),
            "lab_signal_book_v3": analyse(run, "intelligence_lab/lab_signal_book_v3.csv", "v3"),
        }
    dump(out, OUT)
    for run, d in out.items():
        for k, v in d.items():
            print(run, k, v.get("rows"), v.get("doi_projection_state", {}).get("ALL"), v.get("doi_projection_reason", {}).get("ALL"))
