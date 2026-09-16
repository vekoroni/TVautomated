"""D4 — OI/volume retention vs removal; rejection reasons; control_plane observations; CALL/PUT split."""
from __future__ import annotations
import json, sys, re
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d4_lifecycle.json"


def run_level(run: str) -> dict:
    res = {"run": run}
    # contracts_tested: per-contract lists carry symbol/dte/delta/spread_pct/mid/gate_failed only
    ck = Counter(); gates = Counter(); fam = 0; per_dir = Counter(); tested_total = 0
    with open(art(run, "options/contracts_tested_<run>.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line); fam += 1
            per_dir[str(d.get("direction"))] += 1
            for c in d.get("contracts_tested", []):
                ck.update(c.keys()); gates[c.get("gate_failed")] += 1; tested_total += 1
    res["contracts_tested"] = {"families": fam, "by_direction": dict(per_dir), "contract_keys": dict(ck), "gate_failed_counts": dict(gates), "contracts_listed": tested_total,
                              "oi_or_volume_field_present": any(k in ck for k in ("open_interest", "oi", "volume"))}
    # rejection log
    rej = read_csv(art(run, "options/contract_rejection_log_<run>.csv"))
    res["rejection_log_rows"] = len(rej)
    res["rejection_reasons"] = vc(rej["rejection_reason"])
    res["rejection_stage"] = vc(rej["rejection_stage"])
    toks = Counter()
    for r in rej["rejection_reason"].astype(str):
        for t in re.split(r"[;,]", r):
            toks[t.strip()] += 1
    res["rejection_reason_tokens"] = dict(toks)
    oi_vol_tokens = [t for t in toks if re.search(r"\bOI\b|OPEN_INTEREST|VOLUME|\bVOL\b", t, re.I)]
    res["rejection_tokens_mentioning_oi_or_volume"] = oi_vol_tokens
    # join rejections to direction via options_intelligence
    oi_hdr = header(art(run, "options/options_intelligence_<run>.csv"))
    dcol = next(c for c in ("governed_direction", "canonical_direction", "options_direction", "direction") if c in oi_hdr)
    ocols = ["ticker", dcol] + [c for c in ("contract_oi", "contract_volume", "liquidity_state", "executable_now", "current_quote_executable", "recommended_contract", "contract_bid", "contract_ask", "liquidity_reasons", "contract_review_flags", "execution_permission") if c in oi_hdr]
    oi = read_csv(art(run, "options/options_intelligence_<run>.csv"), usecols=ocols).drop_duplicates("ticker", keep="first")
    oi["ticker"] = oi["ticker"].astype(str).str.upper()
    b = direction_bucket(oi[dcol])
    res["oi_selected_contract"] = {}
    if "contract_oi" in oi and "contract_volume" in oi:
        oi_n = pd.to_numeric(oi["contract_oi"], errors="coerce"); vol = pd.to_numeric(oi["contract_volume"], errors="coerce")
        thin = (oi_n < 100) | (vol == 0)
        has = oi["recommended_contract"].notna() & oi["recommended_contract"].astype(str).str.strip().ne("") if "recommended_contract" in oi else pd.Series(True, index=oi.index)
        for k in ("ALL", "CALL", "PUT", "OTHER"):
            m = pd.Series(True, index=oi.index) if k == "ALL" else (b == k)
            sub = {"rows": int(m.sum()), "with_contract": int((m & has).sum()), "oi_lt_100": int((m & has & (oi_n < 100)).sum()), "vol_eq_0": int((m & has & (vol == 0)).sum()), "thin_either": int((m & has & thin).sum())}
            if "liquidity_state" in oi:
                sub["liquidity_state_of_thin"] = vc(oi.loc[m & has & thin, "liquidity_state"])
                sub["liquidity_state_all"] = vc(oi.loc[m & has, "liquidity_state"])
            res["oi_selected_contract"][k] = sub
    rj = rej.merge(oi[["ticker", dcol]], on="ticker", how="left")
    res["rejection_by_direction"] = vc(direction_bucket(rj[dcol]))
    res["rejection_reason_by_direction"] = {k: vc(rj.loc[direction_bucket(rj[dcol]) == k, "rejection_reason"]) for k in ("CALL", "PUT", "OTHER")}
    # DOI report numbers
    doi = json.load(open(art(run, "options/dynamic_options_intelligence_<run>.json")))
    res["doi_report"] = {k: doi.get(k) for k in ("family_rows", "family_candidates_total", "bounded_candidates_total", "retained_low_open_interest", "retained_zero_volume", "deleted_opportunities")}
    osum = json.load(open(art(run, "options/options_intelligence_summary_<run>.json")))
    res["repair_selector_diagnostics"] = osum.get("repair_selector_diagnostics")
    return res


def control_plane() -> dict:
    res = {}
    with ro_conn("control_plane.sqlite") as c:
        res["observations_by_run"] = c.execute("SELECT run_id, COUNT(*) FROM option_contract_observations GROUP BY 1 ORDER BY 1").fetchall()
        res["liquidity_states"] = c.execute("SELECT liquidity_state, COUNT(*) FROM option_contract_observations GROUP BY 1").fetchall()
        q = """SELECT run_id, option_side, liquidity_state,
                      SUM(open_interest < 100) AS oi_lt_100, SUM(volume = 0) AS vol_0,
                      SUM(open_interest < 100 OR volume = 0) AS thin, SUM(open_interest IS NULL) AS oi_null, SUM(volume IS NULL) AS vol_null, COUNT(*) AS n
               FROM option_contract_observations WHERE run_id IN (?,?) GROUP BY 1,2,3 ORDER BY 1,2,3"""
        res["thin_by_run_side_state"] = c.execute(q, (PRIMARY, COMPARISON)).fetchall()
        res["thin_all_runs_by_state"] = c.execute("SELECT liquidity_state, SUM(open_interest < 100 OR volume = 0), COUNT(*) FROM option_contract_observations GROUP BY 1").fetchall()
        res["correction_state"] = c.execute("SELECT correction_state, COUNT(*) FROM option_contract_observations GROUP BY 1").fetchall()
        res["supersedes_nonnull"] = c.execute("SELECT COUNT(*) FROM option_contract_observations WHERE supersedes_event_id IS NOT NULL").fetchone()[0]
        res["calc_versions"] = c.execute("SELECT calculation_version, COUNT(*) FROM option_contract_observations GROUP BY 1").fetchall()
        res["maturation_is_probability"] = c.execute("SELECT maturation_score_is_probability, COUNT(*) FROM option_contract_observations GROUP BY 1").fetchall()
    return res


if __name__ == "__main__":
    out = {r: run_level(r) for r in (PRIMARY, COMPARISON)}
    out["control_plane"] = control_plane()
    dump(out, OUT)
    for r in (PRIMARY, COMPARISON):
        v = out[r]
        print(r, "rej tokens OI/vol:", v["rejection_tokens_mentioning_oi_or_volume"], "\n selected:", json.dumps(v["oi_selected_contract"], default=str)[:1500])
    print(json.dumps(out["control_plane"], indent=1, default=str)[:4000])
