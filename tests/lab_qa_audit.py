#!/usr/bin/env python3
"""
lab_qa_audit.py — Quant QA audit for AVSHUNTER Intelligence Lab exports.

READ-ONLY. Opens CSVs, writes a report. Touches nothing else.

USAGE
    python lab_qa_audit.py <csv_or_glob> [more...] [--out DIR] [--quiet]

    python lab_qa_audit.py avshunter_signals_20260731_083130_2026-07-31_1640.csv
    python lab_qa_audit.py "D:/lab_exports/avshunter_signals_*.csv" --out audit_20260801

EXIT CODES
    0  no P0 findings
    1  one or more P0 findings
    2  could not run (bad path, unreadable file)

Each check is independent and fails soft: a crash in one check is reported as
CHECK_ERROR and the rest still run.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd

VERSION = "1.0"

# Columns the Interpreter is documented to depend on.
REQUIRED = [
    "Ticker", "Verdict", "Run_ID", "Direction", "Instrument",
    "Strike", "Expiry", "DTE", "Premium_Mid", "RR", "EV",
    "Priority_Rank", "Priority_Score", "Structural_Target",
]

# Documented as required for trade eligibility but historically absent.
EXPECTED_MISSING = ["live_data_mode", "trade_idea_id"]

# Fields whose absence removes a safety signal rather than a data point.
SAFETY_FIELDS = [
    "Vetoes", "Vetoes_Count", "EIL_Verdict", "EIL_Raw_Verdict",
    "EIL_Composite", "Verdict_Reason",
]

RR_TOL = 0.002


# ───────────────────────────────────────────────────────────── infrastructure

class Register:
    def __init__(self):
        self.items: list[dict] = []
        self._n = 0

    def add(self, severity, cls, title, detail, evidence=None,
            confidence=None, consequence=None):
        self._n += 1
        self.items.append({
            "id": f"LABQA-{self._n:03d}",
            "severity": severity,          # P0 | P1 | P2 | INFO
            "class": cls,
            "title": title,
            "detail": detail,
            "evidence": evidence or {},
            "consequence": consequence,
            "confidence_pct": confidence,
        })

    def count(self, sev):
        return sum(1 for i in self.items if i["severity"] == sev)


def _num(df, col):
    """Coerce to numeric without mutating the frame."""
    return pd.to_numeric(df[col], errors="coerce")


def _has(df, *cols):
    return all(c in df.columns for c in cols)


def _is_call(row):
    return "CALL" in str(row.get("Instrument", "")).upper()


# ─────────────────────────────────────────────────────────────────── checks
# Each returns None; each appends to the register.

def chk_schema(df, reg, raw):
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        reg.add("P0", "SCHEMA", "Required columns absent",
                f"{len(missing)} documented-required column(s) missing.",
                {"missing": missing},
                consequence="Interpreter cannot construct a valid request.",
                confidence=99)

    absent = [c for c in EXPECTED_MISSING if c not in df.columns]
    if absent:
        reg.add("P0", "SCHEMA", "Eligibility fields not present in export",
                "Documented trade eligibility requires live_data_mode=LIVE and "
                "immutable identity requires trade_idea_id. Neither is exported.",
                {"absent": absent},
                consequence="The documented eligibility condition cannot be "
                            "enforced from this file. Identity cannot be bound "
                            "to a trade idea.",
                confidence=99)

    for c in SAFETY_FIELDS:
        if c not in df.columns:
            reg.add("P1", "SAFETY_SIGNAL", f"Safety field '{c}' not exported",
                    "Field is architecturally a safety control and is absent.",
                    {"column": c}, confidence=90)


def chk_dead_columns(df, reg, raw):
    n = len(df)
    dead, near = [], []
    for c in df.columns:
        nulls = df[c].isna().sum()
        if nulls == n:
            dead.append(c)
        elif nulls / n >= 0.75:
            near.append({"column": c, "null_pct": round(100 * nulls / n, 1)})

    if dead:
        safety_dead = [c for c in dead if c in SAFETY_FIELDS]
        reg.add("P0" if safety_dead else "P1", "DEAD_COLUMN",
                f"{len(dead)} column(s) are 100% null",
                "Columns present in the header but empty on every row.",
                {"dead_columns": dead, "safety_fields_dead": safety_dead,
                 "row_count": n},
                consequence=(
                    "Veto/EIL/reason fields are empty, so a consumer checking "
                    "Vetoes_Count == 0 as a safety condition passes every row "
                    "unconditionally." if safety_dead else
                    "Downstream consumers receive structurally valid rows with "
                    "no data in these fields."),
                confidence=99)

    if near:
        reg.add("P2", "SPARSE_COLUMN", f"{len(near)} column(s) >=75% null",
                "Sparse but not empty.", {"columns": near}, confidence=95)


def chk_constants(df, reg, raw):
    expected_const = {"Run_ID", "Regime"}
    consts = []
    for c in df.columns:
        if df[c].nunique(dropna=True) == 1 and df[c].notna().any():
            consts.append({"column": c,
                           "value": str(df[c].dropna().iloc[0])})

    unexpected = [c for c in consts if c["column"] not in expected_const]
    numeric_const = [c for c in unexpected
                     if pd.api.types.is_numeric_dtype(df[c["column"]])]

    if numeric_const:
        reg.add("P1", "HARDCODED_DEFAULT",
                f"{len(numeric_const)} numeric column(s) constant on every row",
                "A numeric field identical across all rows usually indicates a "
                "fallback constant rather than a computed value.",
                {"columns": numeric_const, "row_count": len(df)},
                consequence="A scoring input that does not vary carries no "
                            "information and may mask an upstream phase that "
                            "did not run.",
                confidence=80)

    if unexpected:
        reg.add("INFO", "CONSTANT", "Constant columns (all rows identical)",
                "Review whether each is legitimately per-run.",
                {"columns": unexpected}, confidence=99)


def chk_null_encoding(df, reg, raw):
    """Missing encoded as a value inside the valid range is the core hazard."""
    suspects = []
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        s = df[c]
        if s.isna().all():
            continue
        zeros = (s == 0).sum()
        if zeros and zeros / len(s) >= 0.20 and s.isna().sum() == 0:
            suspects.append({"column": c, "zero_pct": round(100 * zeros / len(s), 1),
                             "nulls": 0})
    if suspects:
        reg.add("P1", "NULL_AS_ZERO",
                "Numeric column(s) with many zeros and no nulls",
                "Zero may be encoding 'not computed'. A consumer cannot "
                "distinguish a genuine zero from a missing value.",
                {"columns": suspects},
                consequence="Threshold filters treat missing data as a real "
                            "measurement.",
                confidence=70)


def chk_rr_reconciliation(df, reg, raw):
    if not _has(df, "RR", "Strike", "Structural_Target", "Premium_Mid", "Instrument"):
        return
    d = df.copy()
    d["_call"] = d.apply(_is_call, axis=1)
    strike = _num(d, "Strike")
    tgt = _num(d, "Structural_Target")
    prem = _num(d, "Premium_Mid")
    rr = _num(d, "RR")

    intrinsic = np.where(d["_call"], (tgt - strike), (strike - tgt))
    intrinsic = np.maximum(0.0, intrinsic)
    with np.errstate(divide="ignore", invalid="ignore"):
        rr_calc = np.where(prem > 0, (intrinsic - prem) / prem, np.nan)
    rr_calc = np.clip(rr_calc, 0, None)

    valid = (~np.isnan(rr_calc)) & rr.notna().values
    match = np.isclose(rr_calc, rr.values, atol=RR_TOL) & valid
    n_valid = int(valid.sum())
    n_match = int(match.sum())

    reg.add("INFO", "FORMULA",
            "R:R formula reconciliation",
            "RR = clip((intrinsic_at_target - premium_mid) / premium_mid, 0), "
            "direction-aware.",
            {"rows_checked": n_valid, "rows_matching": n_match,
             "match_pct": round(100 * n_match / n_valid, 1) if n_valid else None},
            confidence=95)

    # The material defect: computable positive RR reported as zero.
    computable = valid & (intrinsic > 0) & (rr_calc > 0)
    zeroed = computable & (rr.values == 0)
    if zeroed.sum():
        z = d.loc[zeroed, ["Ticker", "Instrument", "Strike",
                           "Structural_Target", "Premium_Mid", "RR"]].copy()
        z["RR_computable"] = np.round(rr_calc[zeroed], 3)
        by_dir = {
            "CALL": int((zeroed & d["_call"].values).sum()),
            "PUT": int((zeroed & ~d["_call"].values).sum()),
        }
        tot = {"CALL": int((computable & d["_call"].values).sum()),
               "PUT": int((computable & ~d["_call"].values).sum())}
        rates = {k: (round(100 * by_dir[k] / tot[k], 1) if tot[k] else None)
                 for k in by_dir}
        skew = (rates["CALL"] or 0) - (rates["PUT"] or 0)
        reg.add("P0", "SILENT_ZERO",
                "R:R reported as 0 where it is computable and positive",
                f"{int(zeroed.sum())} row(s) report RR=0 while the exported "
                f"strike/target/premium give a positive R:R.",
                {"affected_rows": int(zeroed.sum()),
                 "zeroed_by_direction": by_dir,
                 "computable_by_direction": tot,
                 "zeroed_pct_by_direction": rates,
                 "directional_skew_pp": round(skew, 1),
                 "examples": z.head(12).to_dict("records")},
                consequence="Any 'RR > 0' filter discards these candidates. "
                            "If the skew is directional, candidate selection "
                            "acquires a directional bias that comes from a data "
                            "defect, not from the strategy.",
                confidence=95)

    # Mismatches that are not the zero case.
    other = valid & (~match) & (rr.values != 0)
    if other.sum():
        o = d.loc[other, ["Ticker", "Instrument", "Strike",
                          "Structural_Target", "Premium_Mid", "RR"]].copy()
        o["RR_computable"] = np.round(rr_calc[other], 3)
        reg.add("P1", "FORMULA_MISMATCH",
                "R:R does not reconcile with exported inputs",
                f"{int(other.sum())} row(s) where RR is non-zero but does not "
                "match the direction-aware formula.",
                {"affected_rows": int(other.sum()),
                 "examples": o.head(10).to_dict("records")},
                consequence="RR and the fields it should derive from disagree; "
                            "one of them is not what it claims to be.",
                confidence=85)


def chk_target_side(df, reg, raw):
    if not _has(df, "Strike", "Structural_Target", "Instrument"):
        return
    d = df.copy()
    d["_call"] = d.apply(_is_call, axis=1)
    strike = _num(d, "Strike")
    tgt = _num(d, "Structural_Target")
    wrong = np.where(d["_call"], tgt <= strike, tgt >= strike)
    wrong = wrong & strike.notna().values & tgt.notna().values

    if wrong.sum():
        cols = [c for c in ["Ticker", "Verdict", "Direction", "Instrument",
                            "Strike", "Structural_Target", "RR", "Priority_Rank"]
                if c in d.columns]
        w = d.loc[wrong, cols]
        go = w[w["Verdict"] == "GO"] if "Verdict" in w.columns else w
        reg.add("P0", "THESIS_CONTRACT_MISMATCH",
                "Structural_Target on the unprofitable side of the strike",
                f"{int(wrong.sum())} row(s) hold a target that the contract "
                "cannot profit from — e.g. a long put with a target above the "
                "strike.",
                {"affected_rows": int(wrong.sum()),
                 "of_which_GO": int(len(go)),
                 "by_verdict": (w["Verdict"].value_counts().to_dict()
                                if "Verdict" in w.columns else {}),
                 "examples": w.head(12).to_dict("records")},
                consequence="Either Structural_Target is overloaded (profit "
                            "target on some rows, invalidation level on others) "
                            "or contract selection mismatched the thesis. Both "
                            "invalidate any R:R computed from this field.",
                confidence=95)


def chk_ev_precision(df, reg, raw):
    if "EV" not in df.columns:
        return
    # Inspect raw strings: -0.0000 is indistinguishable from 0.0000 after parse.
    negzero = []
    if raw is not None:
        hdr = raw[0].split(",")
        if "EV" in hdr:
            i = hdr.index("EV")
            for line in raw[1:]:
                if not line.strip():
                    continue
                parts = line.split(",")
                if len(parts) > i:
                    v = parts[i].strip()
                    if v.startswith("-0.") and float(v or 0) == 0:
                        negzero.append(v)

    ev = _num(df, "EV")
    dp = 0
    if raw is not None:
        hdr = raw[0].split(",")
        if "EV" in hdr:
            i = hdr.index("EV")
            decs = []
            for line in raw[1:]:
                parts = line.split(",")
                if len(parts) > i and "." in parts[i]:
                    decs.append(len(parts[i].split(".")[1]))
            dp = max(decs) if decs else 0

    n_zero = int((ev == 0).sum())
    if negzero:
        reg.add("P0", "SIGN_LOSS",
                "Negative EV rounds to negative zero in the export",
                f"{len(negzero)} row(s) export EV as '-0.0000'. Parsed, this "
                "equals 0.0, so a non-negative filter admits them.",
                {"negative_zero_rows": len(negzero),
                 "exported_decimal_places": dp,
                 "rows_with_EV_zero_after_parse": n_zero},
                consequence="A filter of EV >= 0 admits genuinely negative-EV "
                            "trades. A filter of EV > 0 discards rows whose true "
                            "EV is positive but below the rounding threshold. "
                            "Sign survives only in EV_Decision.",
                confidence=95)
    elif dp and dp <= 4 and n_zero:
        reg.add("P1", "PRECISION_LOSS",
                "EV rounded to few decimal places before threshold comparison",
                f"EV exported to {dp}dp; {n_zero} row(s) land exactly on zero.",
                {"exported_decimal_places": dp, "rows_at_zero": n_zero},
                confidence=80)


def chk_ev_decision_agreement(df, reg, raw):
    if not _has(df, "EV", "EV_Decision"):
        return
    ev = _num(df, "EV")
    tab = pd.crosstab(df["EV_Decision"], np.sign(ev).map(
        {-1.0: "neg", 0.0: "zero", 1.0: "pos"}))
    # Same numeric value classified differently is the signal of interest.
    z = df[ev == 0]
    if len(z) and z["EV_Decision"].nunique() > 1:
        reg.add("P1", "CLASSIFICATION_AMBIGUITY",
                "Identical exported EV maps to different EV_Decision values",
                "Rows with EV parsing to exactly 0 carry more than one decision "
                "label — the decision retains information the number has lost.",
                {"rows_at_zero": int(len(z)),
                 "decisions_at_zero": z["EV_Decision"].value_counts().to_dict(),
                 "crosstab": tab.to_dict()},
                consequence="EV_Decision is the only reliable EV filter. Any "
                            "consumer filtering on the numeric column is wrong.",
                confidence=90)


def chk_priority_order(df, reg, raw):
    if not _has(df, "Priority_Rank", "Priority_Score"):
        return
    d = df.sort_values("Priority_Rank")
    mono = d["Priority_Score"].is_monotonic_decreasing
    if not mono:
        detail = {}
        if "Verdict" in df.columns:
            g = df.groupby("Verdict").agg(
                rank_min=("Priority_Rank", "min"),
                rank_max=("Priority_Rank", "max"),
                score_min=("Priority_Score", "min"),
                score_max=("Priority_Score", "max"),
                n=("Priority_Rank", "size"))
            detail["by_verdict"] = g.to_dict("index")
            within = all(
                grp.sort_values("Priority_Rank")["Priority_Score"]
                   .is_monotonic_decreasing
                for _, grp in df.groupby("Verdict"))
            detail["monotonic_within_verdict"] = bool(within)
        top_rank = df.nsmallest(10, "Priority_Rank")[
            ["Priority_Rank", "Ticker", "Priority_Score"]].to_dict("records")
        top_score = df.nlargest(10, "Priority_Score")[
            ["Priority_Rank", "Ticker", "Priority_Score"]].to_dict("records")
        detail["top10_by_rank"] = top_rank
        detail["top10_by_score"] = top_score
        reg.add("P1", "ORDERING",
                "Priority_Rank is not ordered by Priority_Score",
                "Sorting by rank and sorting by score give different candidate "
                "sets.",
                detail,
                consequence="Two plausible reading conventions produce "
                            "materially different top-N selections. The rule "
                            "must be documented and the consumer verified "
                            "against it.",
                confidence=99)

    # rank contiguity
    r = _num(df, "Priority_Rank").dropna().astype(int)
    if len(r) and (sorted(r) != list(range(1, len(r) + 1))):
        reg.add("P2", "ORDERING", "Priority_Rank is not a contiguous 1..N",
                "Gaps or duplicates in rank.",
                {"n": int(len(r)), "min": int(r.min()), "max": int(r.max()),
                 "duplicates": int(r.duplicated().sum())}, confidence=95)


def chk_iv_consistency(df, reg, raw):
    if not _has(df, "IVP", "IVP_Label"):
        return
    ivp = _num(df, "IVP")
    g = df.assign(_ivp=ivp).groupby("IVP_Label")["_ivp"].agg(["min", "max", "count"])
    overlap = []
    labs = list(g.index)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            a, b = g.loc[labs[i]], g.loc[labs[j]]
            if a["min"] <= b["max"] and b["min"] <= a["max"]:
                overlap.append([labs[i], labs[j]])
    if overlap:
        reg.add("P1", "LABEL_INCONSISTENCY",
                "IVP_Label ranges overlap — not a clean function of IVP",
                "The same IVP value maps to more than one label.",
                {"ranges": g.to_dict("index"), "overlapping_pairs": overlap},
                confidence=90)
    else:
        reg.add("INFO", "LABEL", "IVP_Label is a clean function of IVP",
                "Thresholds inferred from data.",
                {"ranges": g.to_dict("index")}, confidence=95)

    if "Vol_State" in df.columns:
        ct = pd.crosstab(df["Vol_State"], df["IVP_Label"])
        gv = df.assign(_ivp=ivp).groupby("Vol_State")["_ivp"].agg(
            ["min", "max", "count"])
        # Contradiction: a 'cheap' vol state on a high IV percentile.
        contra = 0
        if "CHEAP" in ct.index:
            for col in ct.columns:
                if str(col).upper().startswith("EXP"):
                    contra += int(ct.loc["CHEAP", col])
        if contra:
            reg.add("P1", "SEMANTIC_COLLISION",
                    "Vol_State and IVP_Label contradict on the same row",
                    f"{contra} row(s) are Vol_State=CHEAP while IVP_Label "
                    "indicates expensive. The two fields share a near-identical "
                    "vocabulary in adjacent columns.",
                    {"crosstab": ct.to_dict(),
                     "IVP_range_by_Vol_State": gv.to_dict("index"),
                     "contradicting_rows": contra},
                    consequence="If these are different concepts (realised vol "
                                "regime vs implied vol percentile) the naming is "
                                "unsafe. If they are the same concept, one is "
                                "wrong.",
                    confidence=85)


def chk_verdict_vocab(df, reg, raw):
    cols = [c for c in ["Verdict", "Lab_Verdict", "Exec_Category",
                        "Morning_Permission", "MV_Verdict", "Campaign",
                        "Effective_Execution_Verdict"] if c in df.columns]
    if len(cols) < 2:
        return
    vocab = {c: sorted(map(str, df[c].dropna().unique())) for c in cols}
    counts = {c: df[c].value_counts().to_dict() for c in cols}

    go_counts = {c: int((df[c] == "GO").sum()) for c in cols if "GO" in vocab[c]}
    if len(set(go_counts.values())) > 1:
        reg.add("P1", "VOCAB_INCONSISTENCY",
                "'GO' selects different row counts depending on the column used",
                "Verdict-like columns disagree on which rows are GO.",
                {"go_row_count_by_column": go_counts, "vocabularies": vocab},
                consequence="The filter column choice silently changes the "
                            "candidate population.",
                confidence=95)

    # Perfect collinearity => not an independent check.
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            ct = pd.crosstab(df[a], df[b])
            if ct.shape[0] == ct.shape[1] and (ct.values > 0).sum() == ct.shape[0]:
                reg.add("P1", "FALSE_INDEPENDENCE",
                        f"'{a}' and '{b}' are perfectly collinear",
                        "One is a relabelling of the other, not an independent "
                        "assessment.",
                        {"crosstab": ct.to_dict()},
                        consequence=(
                            "If one of these is treated as independent "
                            "confirmation of the other, it provides none."),
                        confidence=85)


def chk_run_id(df, reg, raw, path):
    if "Run_ID" not in df.columns:
        return
    u = df["Run_ID"].dropna().unique()
    if len(u) != 1:
        reg.add("P0", "IDENTITY", "Export contains more than one Run_ID",
                "Rows from different runs in a single export.",
                {"run_ids": list(map(str, u))},
                consequence="Cross-run evidence contamination.", confidence=99)
        return
    rid = str(u[0])
    base = os.path.basename(path)
    if rid not in base:
        reg.add("P1", "IDENTITY", "Run_ID in content does not appear in filename",
                "Filename and content identity cannot be cross-validated.",
                {"run_id": rid, "filename": base}, confidence=90)
    else:
        reg.add("INFO", "IDENTITY", "Run_ID present in content and filename",
                "Run binding can be enforced from file content.",
                {"run_id": rid}, confidence=99)


def chk_duplicates(df, reg, raw):
    if "Ticker" not in df.columns:
        return
    d = df["Ticker"].duplicated().sum()
    if d:
        reg.add("P0", "DUPLICATE", "Duplicate tickers in export",
                f"{int(d)} duplicate ticker row(s).",
                {"duplicates": df[df["Ticker"].duplicated(keep=False)]
                    ["Ticker"].value_counts().to_dict()},
                consequence="Ambiguous candidate selection.", confidence=99)


def chk_contract_sanity(df, reg, raw):
    issues = {}
    if "Premium_Mid" in df.columns:
        p = _num(df, "Premium_Mid")
        bad = int(((p <= 0) | p.isna()).sum())
        if bad:
            issues["premium_non_positive_or_null"] = bad
    if "DTE" in df.columns:
        dte = _num(df, "DTE")
        bad = int(((dte <= 0) | dte.isna()).sum())
        if bad:
            issues["dte_non_positive_or_null"] = bad
    if _has(df, "DTE", "Expiry"):
        try:
            exp = pd.to_datetime(df["Expiry"], errors="coerce")
            if exp.notna().any():
                span = (exp.max() - exp.min()).days
                issues["expiry_distinct_values"] = int(exp.nunique())
                issues["expiry_span_days"] = int(span)
        except Exception:
            pass
    if "Strike" in df.columns:
        s = _num(df, "Strike")
        bad = int(((s <= 0) | s.isna()).sum())
        if bad:
            issues["strike_non_positive_or_null"] = bad

    if issues:
        sev = "P1" if any(k.endswith("null") or "non_positive" in k
                          for k in issues) else "INFO"
        reg.add(sev, "CONTRACT_SANITY", "Contract field sanity",
                "Basic validity of strike/premium/DTE/expiry.", issues,
                confidence=90)


def chk_filter_sensitivity(df, reg, raw):
    """How much does the candidate population move with filter choice?"""
    if "Verdict" not in df.columns:
        return
    ev = _num(df, "EV") if "EV" in df.columns else None
    rr = _num(df, "RR") if "RR" in df.columns else None
    variants = {"Verdict=='GO'": df["Verdict"] == "GO"}
    if "Exec_Category" in df.columns:
        variants["Exec_Category=='GO'"] = df["Exec_Category"] == "GO"
    variants["Verdict in GO/GO_LIMIT/PROBE/ARMED"] = df["Verdict"].isin(
        ["GO", "GO_LIMIT", "PROBE", "ARMED"])
    if rr is not None:
        variants["GO & RR>0"] = (df["Verdict"] == "GO") & (rr > 0)
    if ev is not None:
        variants["GO & EV>0"] = (df["Verdict"] == "GO") & (ev > 0)
        variants["GO & EV>=0"] = (df["Verdict"] == "GO") & (ev >= 0)
    if rr is not None and ev is not None:
        variants["GO & RR>0 & EV>0"] = (df["Verdict"] == "GO") & (rr > 0) & (ev > 0)

    out = {}
    for k, m in variants.items():
        sel = df[m]
        top = (sel.nsmallest(1, "Priority_Rank")["Ticker"].tolist()
               if "Priority_Rank" in sel.columns and len(sel) else [])
        out[k] = {"n": int(m.sum()), "top_by_rank": top}

    ns = [v["n"] for v in out.values()]
    tops = {tuple(v["top_by_rank"]) for v in out.values() if v["top_by_rank"]}
    spread = (max(ns) / min(ns)) if min(ns) else None
    reg.add("P1" if spread and spread >= 2 else "INFO", "FILTER_SENSITIVITY",
            "Candidate population varies with filter choice",
            f"Population ranges {min(ns)}–{max(ns)} across plausible filter "
            f"definitions.",
            {"variants": out,
             "spread_ratio": round(spread, 2) if spread else None,
             "distinct_top_candidates": len(tops)},
            consequence=("The rank-1 candidate is stable across variants while "
                         "the population beneath it is not — which is why a "
                         "filter defect can stay invisible."
                         if len(tops) == 1 else
                         "Filter choice changes the selected candidate."),
            confidence=95)


CHECKS = [
    ("schema", chk_schema), ("dead_columns", chk_dead_columns),
    ("constants", chk_constants), ("null_encoding", chk_null_encoding),
    ("rr_reconciliation", chk_rr_reconciliation), ("target_side", chk_target_side),
    ("ev_precision", chk_ev_precision),
    ("ev_decision_agreement", chk_ev_decision_agreement),
    ("priority_order", chk_priority_order), ("iv_consistency", chk_iv_consistency),
    ("verdict_vocab", chk_verdict_vocab), ("duplicates", chk_duplicates),
    ("contract_sanity", chk_contract_sanity),
    ("filter_sensitivity", chk_filter_sensitivity),
]


# ───────────────────────────────────────────────────────────────── reporting

def audit_file(path):
    reg = Register()
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        raw = f.read().strip().split("\n")
    df = pd.read_csv(path)

    for name, fn in CHECKS:
        try:
            if name == "run_id":
                continue
            fn(df, reg, raw)
        except Exception:
            reg.add("P2", "CHECK_ERROR", f"Check '{name}' raised",
                    "The check failed; other checks still ran.",
                    {"traceback": traceback.format_exc()[-1200:]}, confidence=99)
    try:
        chk_run_id(df, reg, raw, path)
    except Exception:
        reg.add("P2", "CHECK_ERROR", "Check 'run_id' raised", "",
                {"traceback": traceback.format_exc()[-1200:]}, confidence=99)

    return {
        "file": os.path.abspath(path),
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": list(df.columns),
        "findings": reg.items,
        "summary": {s: reg.count(s) for s in ["P0", "P1", "P2", "INFO"]},
    }


def to_markdown(results):
    L = []
    L.append("# Intelligence Lab — Quant QA Audit Register")
    L.append("")
    L.append(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} "
             f"by `lab_qa_audit.py` v{VERSION}")
    L.append("")
    L.append("READ-ONLY analysis of exported CSVs. No source code was inspected, "
             "so every finding below is an **observation about the data**. "
             "Causes are unverified and require source review.")
    L.append("")

    tot = {"P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    for r in results:
        for k, v in r["summary"].items():
            tot[k] += v

    L.append("## Summary")
    L.append("")
    L.append(f"| Files | P0 | P1 | P2 | Info |")
    L.append(f"|---|---|---|---|---|")
    L.append(f"| {len(results)} | **{tot['P0']}** | {tot['P1']} | {tot['P2']} "
             f"| {tot['INFO']} |")
    L.append("")
    L.append("**Severity rubric** — P0: can make an unsound trade appear sound, "
             "or silently discard a sound one. P1: removes a safety signal or "
             "makes a defect undiagnosable. P2: robustness, no correctness "
             "effect. INFO: characterisation, no defect asserted.")
    L.append("")

    for r in results:
        L.append(f"## `{os.path.basename(r['file'])}`")
        L.append("")
        L.append(f"{r['rows']} rows x {r['columns']} columns")
        L.append("")
        order = {"P0": 0, "P1": 1, "P2": 2, "INFO": 3}
        for f in sorted(r["findings"], key=lambda x: order[x["severity"]]):
            L.append(f"### {f['id']} — [{f['severity']}] {f['title']}")
            L.append("")
            L.append(f"**Class:** `{f['class']}`  ")
            if f.get("confidence_pct") is not None:
                L.append(f"**Confidence:** {f['confidence_pct']}%  ")
            L.append("")
            L.append(f["detail"])
            L.append("")
            if f.get("consequence"):
                L.append(f"**Consequence.** {f['consequence']}")
                L.append("")
            if f["evidence"]:
                L.append("<details><summary>Evidence</summary>")
                L.append("")
                L.append("```json")
                L.append(json.dumps(f["evidence"], indent=2, default=str)[:6000])
                L.append("```")
                L.append("")
                L.append("</details>")
                L.append("")

    L.append("---")
    L.append("")
    L.append("## What this audit does not establish")
    L.append("")
    L.append("- **Cause.** Every finding is a property of the exported data. "
             "Whether it originates upstream, in the Lab merge, or at export "
             "requires source review.")
    L.append("- **Whether findings are systemic.** Run across several exports "
             "from different dates to separate systemic defects from artefacts "
             "of one run.")
    L.append("- **Field intent.** Where a field's meaning is undefined, no test "
             "can decide whether it is wrong.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Quant QA audit for Lab exports.")
    ap.add_argument("paths", nargs="+", help="CSV path(s) or glob(s)")
    ap.add_argument("--out", default=None, help="output directory")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        files.extend(sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p])
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        print("No input files found.", file=sys.stderr)
        return 2

    out = a.out or f"audit_{datetime.now():%Y%m%d}"
    os.makedirs(out, exist_ok=True)

    results = []
    for f in files:
        if not a.quiet:
            print(f"auditing {f} ...")
        try:
            results.append(audit_file(f))
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)

    if not results:
        return 2

    jp = os.path.join(out, "lab_qa_register.json")
    mp = os.path.join(out, "lab_qa_register.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump({"version": VERSION,
                   "generated_utc": datetime.now(timezone.utc).isoformat(),
                   "results": results}, fh, indent=2, default=str)
    with open(mp, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(results))

    p0 = sum(r["summary"]["P0"] for r in results)
    p1 = sum(r["summary"]["P1"] for r in results)
    if not a.quiet:
        print()
        for r in results:
            s = r["summary"]
            print(f"{os.path.basename(r['file'])}: "
                  f"P0={s['P0']} P1={s['P1']} P2={s['P2']} INFO={s['INFO']}")
            for f in r["findings"]:
                if f["severity"] == "P0":
                    print(f"    [P0] {f['title']}")
        print()
        print(f"wrote {mp}")
        print(f"wrote {jp}")
    return 1 if p0 else 0


if __name__ == "__main__":
    sys.exit(main())
