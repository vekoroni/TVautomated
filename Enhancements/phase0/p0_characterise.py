"""Phase 0 characterisation of run 20261006_060401 (DISCOVERY_VANGUARD_REDESIGN_20261007.md §12).

Read-only. Two steps:
  extract  : read the frozen run's files once and write a compact per-ticker / per-candidate extract
             (tests/fixtures/phase0/) so tests never touch live data/.
  measure  : compute every Phase 0 number from the extract only (funnel, story mismatches, compression /
             direction / target agreement, trigger-layer counts) -> p0_characterisation.json.
The measure functions are imported by tests/test_phase0_characterisation.py, which pins today's values.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = "20261006_060401"
RUN_DIR = ROOT / "data" / "output" / "runs" / RUN
FIX = ROOT / "tests" / "fixtures" / "phase0"
OUT = Path(__file__).resolve().parent / "p0_characterisation.json"

DISC_COLS = ["ticker", "thesis__side", "direction", "thesis_event_candidate_id", "thesis_event_timeframe",
             "trade_lane", "trade_lane_setup", "structural_target", "structural_target_source",
             "thesis_outcome_level", "legacy_structural_target", "asymmetry_target1", "bull_target", "bear_target",
             "governed_invalidation_spot", "legacy_direction", "fusion_direction", "precor_intent",
             "precor_intent_raw", "dominant_trend", "discovery_direction_preliminary", "crabel_state",
             "crabel_pattern", "crabel_bucket", "crabel_score", "crabel_compression", "compression_ratio",
             "beh__primary_trigger", "tier"]
LAB_COLS = ["ticker", "lab_verdict", "gate_reason", "final_direction", "trigger_price", "trigger_price_source",
            "trigger_primary", "target_price", "anticipated_level", "invalidation_price", "selected_contract_symbol",
            "contract_symbol"]
MORN_COLS = ["ticker", "contract_symbol", "selected_contract_symbol", "contract_symbol_original", "trigger_price",
             "morning_gate_verdict", "final_route", "trigger_codes", "trigger_primary", "trigger_go_eligible"]
BEH_COLS = ["Ticker", "Timeframe", "Candidate_ID", "Signal_Type", "Signal_State", "Direction", "Trigger_Level",
            "Invalidation_Level", "Outcome_Level", "Crabel_Compression"]


def _one(folder: str, prefix: str) -> Path:
    hits = sorted((RUN_DIR / folder).glob(f"{prefix}*{RUN}*.csv"))
    if not hits:
        raise FileNotFoundError(f"{folder}/{prefix}")
    return hits[0]


def _read(path: Path, cols) -> pd.DataFrame:
    return pd.read_csv(path, usecols=lambda c: c in set(cols), low_memory=False, dtype=str)


def extract() -> None:
    FIX.mkdir(parents=True, exist_ok=True)
    disc = _read(_one("discovery", "discovery_candidates_ultimate"), DISC_COLS)
    beh = _read(_one("discovery", "behavioural_candidates"), BEH_COLS)
    expr = _read(_one("options", "options_candidate_expressions"),
                 ["Candidate_ID", "Ticker", "Expression_Status", "contract__symbol", "Handoff_Rank"])
    opt = _read(RUN_DIR / "options" / f"options_intelligence_{RUN}.csv", ["ticker", "contract_occ_symbol", "final_direction"])
    morn = _read(RUN_DIR / "morning_validation" / f"morning_validated_trades_{RUN}.csv", MORN_COLS)
    lab = _read(RUN_DIR / "intelligence_lab" / f"final_opportunity_book_{RUN}.csv", LAB_COLS)
    van = _read(RUN_DIR / "vanguard" / "vanguard_signals.csv", ["ticker", "side_block_reason"])
    rej = _read(RUN_DIR / "vanguard" / "vanguard_rejects.csv", ["ticker", "reason_code"])
    life = pd.read_csv(_one("discovery", "discovery_lifecycle"), dtype=str, low_memory=False)
    for name, df in (("discovery", disc), ("behavioural", beh), ("expressions", expr), ("options", opt),
                     ("morning", morn), ("lab", lab), ("vanguard", van), ("vanguard_rejects", rej),
                     ("lifecycle", life)):
        df.to_parquet(FIX / f"{name}.parquet", index=False)
    (FIX / "SOURCE.json").write_text(json.dumps({"run_id": RUN, "extracted_from": str(RUN_DIR),
                                                 "note": "read-only extract for Phase 0 characterisation tests"},
                                                indent=2))


def load(fix: Path = FIX) -> dict:
    return {p.stem: pd.read_parquet(p) for p in fix.glob("*.parquet")}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _differs(a: pd.Series, b: pd.Series, rel: float = 1e-4) -> pd.Series:
    a, b = _num(a), _num(b)
    both = a.notna() & b.notna()
    return both & ((a - b).abs() > rel * b.abs().clip(lower=1e-9))


def funnel(d: dict) -> dict:
    disc, van, rej, opt, lab = d["discovery"], d["vanguard"], d["vanguard_rejects"], d["options"], d["lab"]
    go = lab["lab_verdict"].isin(["GO", "GO_LIMIT"])
    return {
        "discovery_tickers": int(disc["ticker"].nunique()),
        "vanguard_pass": int(van["ticker"].nunique()), "vanguard_reject": int(rej["ticker"].nunique()),
        "vanguard_reject_reasons": rej["reason_code"].value_counts().to_dict(),
        "options_tickers": int(opt["ticker"].nunique()), "lab_tickers": int(lab["ticker"].nunique()),
        "lab_verdicts": lab["lab_verdict"].value_counts().to_dict(),
        "lab_go_or_go_limit": int(go.sum()),
        "lab_gate_reasons_not_go_top": lab.loc[~go, "gate_reason"].fillna("<none>").str.split(";").str[0]
        .value_counts().head(12).to_dict(),
        "discovery_side": disc["thesis__side"].value_counts().to_dict(),
        "side_block_reason": van["side_block_reason"].value_counts().to_dict(),
    }


def story_mismatch(d: dict) -> dict:
    disc, beh, lab, morn, opt, expr = (d[k] for k in ("discovery", "behavioural", "lab", "morning", "options",
                                                      "expressions"))
    cand = beh.drop_duplicates("Candidate_ID").set_index("Candidate_ID")
    t = disc[disc["thesis_event_candidate_id"].notna()].copy()
    t = t.join(cand[["Trigger_Level", "Invalidation_Level", "Outcome_Level", "Timeframe", "Signal_Type"]],
               on="thesis_event_candidate_id")
    t = t.merge(lab, on="ticker", how="left", suffixes=("", "_lab")).merge(
        morn[["ticker", "trigger_price", "contract_symbol", "contract_symbol_original"]].rename(
            columns={"trigger_price": "trigger_price_morning", "contract_symbol": "contract_morning"}),
        on="ticker", how="left").merge(opt[["ticker", "contract_occ_symbol"]], on="ticker", how="left")
    in_lab = t["lab_verdict"].notna()
    lt = t[in_lab]
    setup_tf = lt["trade_lane_setup"].fillna("").str.split("|").str[0]
    setup_sig = lt["trade_lane_setup"].fillna("").str.split("|").str[1]
    ex = expr.set_index("Candidate_ID")
    lt = lt.join(ex[["Expression_Status", "contract__symbol", "Handoff_Rank"]], on="thesis_event_candidate_id")
    status = lt["Expression_Status"].fillna("").str.split(":").str[0]
    go = lt["lab_verdict"].isin(["GO", "GO_LIMIT"])
    return {
        "directed_thesis_candidates_in_lab": int(len(lt)),
        "setup_shown_differs_from_thesis": int(((setup_tf != lt["Timeframe"]) | (setup_sig != lt["Signal_Type"])).sum()),
        "setup_differs_on_go": int((((setup_tf != lt["Timeframe"]) | (setup_sig != lt["Signal_Type"])) & go).sum()),
        "target_discovery_vs_outcome_level_differs": int(_differs(lt["structural_target"], lt["Outcome_Level"]).sum()),
        "target_discovery_vs_outcome_level_comparable": int((_num(lt["structural_target"]).notna()
                                                             & _num(lt["Outcome_Level"]).notna()).sum()),
        "target_source": lt["structural_target_source"].value_counts().to_dict(),
        "trigger_lab_vs_candidate_differs": int(_differs(lt["trigger_price"], lt["Trigger_Level"]).sum()),
        "trigger_lab_vs_candidate_comparable": int((_num(lt["trigger_price"]).notna()
                                                    & _num(lt["Trigger_Level"]).notna()).sum()),
        "trigger_price_source": lt["trigger_price_source"].value_counts().to_dict(),
        "invalidation_lab_vs_candidate_differs": int(_differs(lt["invalidation_price"], lt["Invalidation_Level"]).sum()),
        "thesis_candidate_expression_status": status.value_counts().to_dict(),
        "thesis_candidate_rank_median": float(_num(lt["Handoff_Rank"]).median()),
        "contract_options_vs_morning_differs": int((lt["contract_occ_symbol"].notna() & lt["contract_morning"].notna()
                                                    & (lt["contract_occ_symbol"] != lt["contract_morning"])).sum()),
        "contract_repaired_in_morning": int(lt["contract_symbol_original"].notna().sum()),
        "contract_expression_vs_lab_differs": int((lt["contract__symbol"].notna() & lt["selected_contract_symbol"].notna()
                                                   & (lt["contract__symbol"] != lt["selected_contract_symbol"])).sum()),
    }


def _engine_1d_state(beh: pd.DataFrame) -> pd.Series:
    one = beh[beh["Timeframe"] == "1d"].drop_duplicates("Ticker").set_index("Ticker")["Crabel_Compression"]
    return one.fillna("").str.split(";").str[0].str.strip()


def compression_agreement(d: dict) -> dict:
    disc = d["discovery"].set_index("ticker")
    eng = _engine_1d_state(d["behavioural"])
    trig = d["morning"].set_index("ticker")["trigger_codes"].fillna("")
    f = pd.DataFrame(index=disc.index)
    f["discovery_crabel"] = disc["crabel_pattern"].fillna("").ne("")
    f["precor_state"] = disc["crabel_state"].map({"COILING": True, "CRABEL_READY": True, "NONE": False})
    f["engine_1d"] = eng.reindex(f.index).map({"CONTRACTING": True, "NONE": False})
    f["trigger_layer_T1"] = trig.reindex(f.index).str.contains("VOL_COMPRESSION").where(trig.reindex(f.index).notna())
    names = list(f.columns)
    pairs = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            m = f[[a, b]].dropna()
            pairs[f"{a}__vs__{b}"] = {"n": int(len(m)), "agree": int((m[a] == m[b]).sum()),
                                      "a_only": int((m[a] & ~m[b].astype(bool)).sum()),
                                      "b_only": int((~m[a].astype(bool) & m[b]).sum())}
    return {"producers": {n: {"compressed": int((f[n] == True).sum()), "not": int((f[n] == False).sum()),  # noqa: E712
                              "not_measured": int(f[n].isna().sum())} for n in names},
            "pairwise": pairs,
            "all_measured_and_all_agree": int(f.dropna().nunique(axis=1).eq(1).sum()),
            "all_measured": int(len(f.dropna())),
            "crabel_bucket": disc["crabel_bucket"].value_counts().to_dict()}


def _side(v: str) -> str:
    v = str(v or "").upper()
    if v in {"BULL", "CALL", "BULLISH", "LONG"} or "BUY" in v or "ACCUM" in v:
        return "BULL"
    if v in {"BEAR", "PUT", "BEARISH", "SHORT"} or "SELL" in v or "DISTRIB" in v:
        return "BEAR"
    return "NONE"


def direction_agreement(d: dict) -> dict:
    disc = d["discovery"]
    prods = ["thesis__side", "legacy_direction", "fusion_direction", "precor_intent", "precor_intent_raw",
             "dominant_trend", "discovery_direction_preliminary"]
    s = pd.DataFrame({p: disc[p].map(_side) for p in prods if p in disc})
    out = {"by_producer": {p: s[p].value_counts().to_dict() for p in s}}
    ref = s["thesis__side"]
    for p in s.columns[1:]:
        both = (ref != "NONE") & (s[p] != "NONE")
        out[f"thesis_vs_{p}"] = {"both_directed": int(both.sum()), "same": int((both & (ref == s[p])).sum()),
                                 "opposite": int((both & (ref != s[p])).sum())}
    return out


def target_agreement(d: dict) -> dict:
    disc, lab = d["discovery"], d["lab"]
    t = disc.merge(lab[["ticker", "anticipated_level", "target_price"]], on="ticker", how="left")
    ref = "thesis_outcome_level"
    out = {}
    for p in ["structural_target", "legacy_structural_target", "asymmetry_target1", "anticipated_level", "target_price"]:
        comp = _num(t[ref]).notna() & _num(t[p]).notna()
        out[f"{ref}_vs_{p}"] = {"comparable": int(comp.sum()), "differs": int(_differs(t[ref], t[p]).sum()),
                                "median_abs_pct_gap": float(((_num(t[p]) - _num(t[ref])).abs() / _num(t[ref]))
                                                            [comp].median() * 100) if comp.any() else None}
    return out


def trigger_layer_counts(d: dict) -> dict:
    m = d["morning"]
    tc = m["trigger_codes"].fillna("")
    return {"rows": int(len(m)), "trigger_primary": m["trigger_primary"].fillna("<na>").value_counts().to_dict(),
            "codes_containing": {k: int(tc.str.contains(k, regex=False).sum())
                                 for k in ("VOL_COMPRESSION", "RANGE_BREAK_EARLY", "RANGE_BREAK", "VWAP_RECLAIM",
                                           "VWAP_LOSS", "TRAP")},
            "go_eligible": m["trigger_go_eligible"].fillna("<na>").value_counts().to_dict()}


def lifecycle(d: dict) -> dict:
    life = d["lifecycle"]
    cols = [c for c in life.columns if re.search(r"reason|status|outcome|disposition", c, re.I)]
    return {c: life[c].fillna("<na>").value_counts().head(15).to_dict() for c in cols}


def candidate_funnel(d: dict) -> dict:
    """Candidate-level dispositions (not ticker-level): engine records -> expression lane statuses."""
    beh, expr = d["behavioural"], d["expressions"]
    b = beh.drop_duplicates("Candidate_ID")
    directed = b["Direction"].isin(["BULL", "BEAR"])
    status = expr["Expression_Status"].fillna("<none>")
    family = status.str.split(":").str[0]
    return {
        "engine_candidate_records": int(len(b)),
        "engine_tickers": int(b["Ticker"].nunique()),
        "engine_states": b["Signal_State"].fillna("<none>").value_counts().to_dict(),
        "engine_undirected": int((~directed).sum()),
        "expression_lane_records": int(len(expr)),
        "expression_status_family": family.value_counts().to_dict(),
        "not_routed_detail": status[family == "NOT_ROUTED"].value_counts().to_dict(),
        "contract_found_tickers": int(expr.loc[family == "CONTRACT_FOUND", "Ticker"].nunique()),
    }


def measure(fix: Path = FIX) -> dict:
    d = load(fix)
    return {"run_id": RUN, "funnel": funnel(d), "candidate_funnel": candidate_funnel(d),
            "story_mismatch": story_mismatch(d),
            "compression_agreement": compression_agreement(d), "direction_agreement": direction_agreement(d),
            "target_agreement": target_agreement(d), "trigger_layer": trigger_layer_counts(d),
            "discovery_lifecycle": lifecycle(d)}


if __name__ == "__main__":
    if "extract" in sys.argv:
        extract()
    res = measure()
    OUT.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str)[:6000])
