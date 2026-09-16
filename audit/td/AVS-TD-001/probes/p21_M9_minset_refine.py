"""p21 — Track M9 post-processor over the p20 census outputs (DISCOVERY, read-only).

Reads only p20_M9_*.csv (no artefact is re-loaded, no provider is called) and writes:

  p21_M9_decision_read_kinds.csv     every p20 decision read site with a read-kind label
  p21_M9_minset_decision_fields.csv  refined "smallest field set reproducing current decisions"
  p21_M9_stale_reader_impact.csv     fields whose only readers are stale copies (*old*, *dnu*, 0505)
  p21_M9_family_classification.csv   classification counts per artefact family
  p21_M9_constants_top.csv           constants ranked by artefact importance
  p21_M9_ambiguous_units.csv         AMBIGUOUS_UNIT fields with range and both candidate units
  p21_M9_mtrack_summary.csv          M1-M5 need -> where it exists / MISSING
  p21_M9_packages_families.csv       packages/ representative grouped by top-level key
  p21_M9_stdout.txt                  headline numbers

Read-kind labels for a decision-path read of field k on one source line:
  PASS    dict-literal output key (`"k": ...`) or same-key copy (`out["k"] = row.get("k")`)
  BRANCH  the read sits in a condition / comparison / boolean / arithmetic / min-max-abs expression
  FETCH   the read is assigned to a local (`x = row.get("k")`) or passed as a call argument
          (`_f(row, "k")`, `_first_value(row, "k", ...)`) - it feeds logic downstream
  OTHER   anything else (logging, f-strings, list literals, reason strings)
The refined minimum set = fields with >= 1 BRANCH or FETCH read in the six named decision readers,
restricted to fields that exist as a column in at least one row-level decision artefact.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
LOGF = open(os.path.join(OUT, "p21_M9_stdout.txt"), "w", encoding="utf-8")


def log(s: str) -> None:
    print(s, flush=True)
    LOGF.write(s + "\n")
    LOGF.flush()


census = pd.read_csv(os.path.join(OUT, "p20_M9_field_census.csv"), low_memory=False)
agg = pd.read_csv(os.path.join(OUT, "p20_M9_artefact_aggregate.csv"), low_memory=False)
dec = pd.read_csv(os.path.join(OUT, "p20_M9_decision_reads.csv"), low_memory=False)
mmap = pd.read_csv(os.path.join(OUT, "p20_M9_mtrack_field_map.csv"), low_memory=False)
census["duplicate_of"] = census["duplicate_of"].fillna("")
census["consumed_by"] = census["consumed_by"].fillna("UNREAD")

LAB = "intelligence_lab/lab_signal_book_v3.csv"
ROW_LEVEL_DECISION_ARTEFACTS = [
    LAB,
    "trades/execution_actionable_20260911_115904.csv",
    "trades/execution_gated_20260911_115904.csv",
    "morning_validation/morning_validated_trades_20260911_115904.csv",
    "morning_validation/morning_candidates_20260911_115904.csv",
    "intelligence_lab/final_opportunity_book_20260911_115904.csv",
    "intelligence_lab/lab_triage_view_20260911_115904.csv",
    "options/options_intelligence_20260911_115904.csv",
    "execution/execution_v3_5_20260911_115904.csv",
]

# ---------------------------------------------------------------- 1. read kinds
SIX_NAMED = {
    "execution_gate.py": None,
    "morning_gate.py": [(216, 470), (1518, 1890), (2076, 2744)],
    "contracts/opportunity_tier.py": None,
    "contracts/lab_control.py": [(1707, 2382)],
    "eod_candidate_engine.py": [(443, 730), (1206, 1300), (2830, 2900)],
    "orchestrator/dynamic_dispatcher.py": [(84, 158)],
}
CALLED_VALIDATORS = {
    "contracts/direction_governance.py": [(390, 511)],
    "domain/option_liquidity_execution_guard.py": [(84, 193)],
    "domain/execution_authority.py": [(147, 292)],
}


def in_ranges(file: str, line: int, ranges: dict) -> bool:
    if file not in ranges:
        return False
    r = ranges[file]
    return True if r is None else any(lo <= line <= hi for lo, hi in r)


def read_kind(tok: str, text: str) -> str:
    t = str(text).strip()
    q = r"[\"']" + re.escape(tok) + r"[\"']"
    if re.match(r"^" + q + r"\s*:", t):
        return "PASS"
    # a line that is only the quoted key (plus comma): an argument line of a multi-line call such as
    # execution_gate._first_value(row, "governed_direction", "final_direction", ...) -> feeds logic
    if re.fullmatch(q + r"\s*,?\s*(#.*)?", t):
        return "FETCH"
    if re.match(r"^[A-Za-z_][\w\.]*\[" + q + r"\]\s*=(?!=)", t):
        return "PASS"
    if re.match(r"^(if|elif|while|assert)\b", t) or re.search(r"\b(and|or|not|in|is)\b", t) or \
            re.search(r"(<=|>=|==|!=|<|>)", t) or re.search(r"\b(min|max|abs|float|int|round|sum|len)\(", t) or \
            re.search(r"[\+\-\*/]\s*(\(|[A-Za-z_\d\"'])", t.split("#")[0]) and not t.startswith("#"):
        # exclude pure output construction that happens to contain arithmetic in a f-string
        if re.match(r"^" + q + r"\s*:", t):
            return "PASS"
        return "BRANCH"
    if re.match(r"^[A-Za-z_][\w\.,\s\[\]\"']*\s*=(?!=)\s*", t) or re.match(r"^return\b", t):
        return "FETCH"
    if re.search(r"\w\(\s*[^()]*" + q, t):
        return "FETCH"
    return "OTHER"


dec["kind"] = [read_kind(f, t) for f, t in zip(dec["field"].astype(str), dec["text"].astype(str))]
dec["in_six_named"] = [in_ranges(f, int(l), SIX_NAMED) for f, l in zip(dec["file"], dec["line"])]
dec["in_called_validators"] = [in_ranges(f, int(l), CALLED_VALIDATORS) for f, l in zip(dec["file"], dec["line"])]
dec.to_csv(os.path.join(OUT, "p21_M9_decision_read_kinds.csv"), index=False)

log(f"decision read sites: {len(dec)}; distinct field tokens: {dec['field'].nunique()}")
log("read kinds (all decision ranges): " + str(dec["kind"].value_counts().to_dict()))
log("read kinds (six named readers):   " + str(dec[dec.in_six_named]["kind"].value_counts().to_dict()))

# ---------------------------------------------------------------- 2. refined minimum set
present_in_row_artefacts = set(census[census["artefact"].isin(ROW_LEVEL_DECISION_ARTEFACTS)]["grep_token"].astype(str))
lab_fields = set(census[census["artefact"] == LAB]["grep_token"].astype(str))

rows = []
for tok, g in dec.groupby("field"):
    six = g[g.in_six_named]
    val = g[g.in_called_validators]
    n_branch6 = int((six.kind == "BRANCH").sum())
    n_fetch6 = int((six.kind == "FETCH").sum())
    n_pass6 = int((six.kind == "PASS").sum())
    n_other6 = int((six.kind == "OTHER").sum())
    n_branchv = int((val.kind == "BRANCH").sum())
    n_fetchv = int((val.kind == "FETCH").sum())
    core = (n_branch6 + n_fetch6) > 0
    ext = (n_branchv + n_fetchv) > 0
    tier = "CORE" if core else ("EXT_VALIDATOR" if ext else ("PASS_ONLY" if (n_pass6 + n_other6) > 0 or len(val) else "DOI_OR_BROAD_ONLY"))
    sites6 = ";".join(f"{f}:{l}[{k}]" for f, l, k in zip(six.file, six.line, six.kind) if k in ("BRANCH", "FETCH"))[:400]
    sitesv = ";".join(f"{f}:{l}[{k}]" for f, l, k in zip(val.file, val.line, val.kind) if k in ("BRANCH", "FETCH"))[:300]
    readers = sorted(set(six[six.kind.isin(["BRANCH", "FETCH"])].file))
    rows.append(dict(field=tok, tier=tier, in_row_level_artefact=tok in present_in_row_artefacts, in_lab_book=tok in lab_fields,
                     n_branch_six=n_branch6, n_fetch_six=n_fetch6, n_pass_six=n_pass6, n_other_six=n_other6,
                     n_branch_validators=n_branchv, n_fetch_validators=n_fetchv,
                     readers_six=";".join(readers), evidence_six=sites6, evidence_validators=sitesv))
ms = pd.DataFrame(rows).sort_values(["tier", "field"])
ms.to_csv(os.path.join(OUT, "p21_M9_minset_decision_fields.csv"), index=False)

core = ms[(ms.tier == "CORE") & ms.in_row_level_artefact]
core_noise = ms[(ms.tier == "CORE") & ~ms.in_row_level_artefact]
ext = ms[(ms.tier == "EXT_VALIDATOR") & ms.in_row_level_artefact]
log(f"REFINED MIN SET (CORE: BRANCH/FETCH read in six named readers, present in a row-level decision artefact): {len(core)} fields")
log(f"  of which present in lab book: {int(core.in_lab_book.sum())}")
log(f"  CORE tokens not present in any row-level artefact (value literals / JSON leaves; excluded): {len(core_noise)} -> {', '.join(core_noise.field.head(40))}")
log(f"EXT (only via called validators direction_governance/olm guard/execution_authority): {len(ext)} fields")
log(f"PASS_ONLY (read only as output-dict keys / other inside decision ranges): {int((ms.tier == 'PASS_ONLY').sum())}")
log(f"DOI_OR_BROAD_ONLY (read only in DOI production/ranking or broad lab_control/eod ranges): {int((ms.tier == 'DOI_OR_BROAD_ONLY').sum())}")
for rd, g in core.groupby("readers_six"):
    pass
per_reader = defaultdict(set)
for _, r in core.iterrows():
    for f in str(r.readers_six).split(";"):
        if f:
            per_reader[f].add(r.field)
log("CORE fields per reader: " + str({k: len(v) for k, v in sorted(per_reader.items())}))
log("CORE field list: " + ", ".join(sorted(core.field)))

# ---------------------------------------------------------------- 3. stale-reader impact
STALE_RE = re.compile(r"(old|dnu|0505|copy|backup|\bbak\b|deprecated)", re.I)


def strip_stale(cb: str) -> list[str]:
    if cb == "UNREAD":
        return []
    return [f for f in cb.split(";") if f and not STALE_RE.search(os.path.basename(f))]


census["readers_non_stale"] = census["consumed_by"].apply(strip_stale)
census["only_stale_readers"] = (census["consumed_by"] != "UNREAD") & (census["readers_non_stale"].apply(len) == 0)
imp = census[census.only_stale_readers][["artefact", "field", "consumed_by", "classification", "is_constant", "all_null"]]
imp.to_csv(os.path.join(OUT, "p21_M9_stale_reader_impact.csv"), index=False)
log(f"fields whose ONLY readers are stale copies: {len(imp)} rows over {imp.artefact.nunique()} artefacts; "
    f"lab book: {int((imp.artefact == LAB).sum())} -> {', '.join(imp[imp.artefact == LAB].field)}")

# ---------------------------------------------------------------- 4. family tables


def family(a: str) -> str:
    a = str(a)
    if a.startswith("packages/"):
        return "packages/ (family, rep AAPL)"
    if a.startswith("morning_validation/validation_events"):
        return "validation_events/ (family, rep 1 of 1444)"
    if "/" not in a:
        return "run root"
    return a.split("/")[0] + "/"


census["family"] = census["artefact"].apply(family)
fam_rows = []
for fam, g in census.groupby("family"):
    fr = pd.to_numeric(g["fill_rate"], errors="coerce")
    fam_rows.append(dict(family=fam, n_artefacts=g.artefact.nunique(), n_fields=len(g),
                         LOAD_BEARING=int((g.classification == "LOAD_BEARING").sum()),
                         ADVISORY_USED=int((g.classification == "ADVISORY_USED").sum()),
                         PRODUCED_UNREAD=int((g.classification == "PRODUCED_UNREAD").sum()),
                         DEAD=int((g.classification == "DEAD").sum()),
                         AMBIGUOUS_UNIT=int(g.unit_ambiguous.sum()),
                         constants=int(g.is_constant.sum()), all_null=int(g.all_null.sum()),
                         fill_lt_50pct=int((fr < 0.5).sum()), duplicates=int((g.duplicate_of != "").sum()),
                         unread=int((g.consumed_by == "UNREAD").sum()), no_producer=int((g.producer == "NO_PRODUCER").sum())))
fam = pd.DataFrame(fam_rows).sort_values("n_fields", ascending=False)
fam.to_csv(os.path.join(OUT, "p21_M9_family_classification.csv"), index=False)
log("family table written: " + str(len(fam)) + " families")

tot = census
fr = pd.to_numeric(tot["fill_rate"], errors="coerce")
log(f"GRAND TOTAL rows={len(tot)} artefacts={tot.artefact.nunique()} class={tot.classification.value_counts().to_dict()} "
    f"ambiguous={int(tot.unit_ambiguous.sum())} constants={int(tot.is_constant.sum())} all_null={int(tot.all_null.sum())} "
    f"fill<50%={int((fr < 0.5).sum())} unread={int((tot.consumed_by == 'UNREAD').sum())} no_producer={int((tot.producer == 'NO_PRODUCER').sum())} dup={int((tot.duplicate_of != '').sum())}")
nonfam = tot[~tot.family.str.contains("family")]
fr = pd.to_numeric(nonfam["fill_rate"], errors="coerce")
log(f"TOTAL excl. the two families rows={len(nonfam)} artefacts={nonfam.artefact.nunique()} class={nonfam.classification.value_counts().to_dict()} "
    f"ambiguous={int(nonfam.unit_ambiguous.sum())} constants={int(nonfam.is_constant.sum())} all_null={int(nonfam.all_null.sum())} "
    f"fill<50%={int((fr < 0.5).sum())} unread={int((nonfam.consumed_by == 'UNREAD').sum())} dup={int((nonfam.duplicate_of != '').sum())}")

# ---------------------------------------------------------------- 5. constants by importance
IMPORTANCE = [LAB, "trades/execution_actionable_20260911_115904.csv", "trades/execution_gated_20260911_115904.csv",
              "morning_validation/morning_validated_trades_20260911_115904.csv",
              "intelligence_lab/final_opportunity_book_20260911_115904.csv",
              "morning_validation/morning_candidates_20260911_115904.csv",
              "options/options_intelligence_20260911_115904.csv", "execution/execution_v3_5_20260911_115904.csv",
              "qomega/garch_forecasts_20260911_115904.csv", "options/contracts_tested_20260911_115904.jsonl"]
big = {"trades/execution_gated_20260911_115904.csv", "morning_validation/morning_validated_trades_20260911_115904.csv",
       "intelligence_lab/final_opportunity_book_20260911_115904.csv", "morning_validation/morning_candidates_20260911_115904.csv",
       "options/options_intelligence_20260911_115904.csv", "execution/execution_v3_5_20260911_115904.csv"}
const_big = census[census.artefact.isin(big) & census.is_constant].groupby("grep_token")["artefact"].apply(lambda s: ";".join(sorted(s)))
const_rows = []
for rank, a in enumerate(IMPORTANCE):
    g = census[(census.artefact == a) & census.is_constant]
    for _, r in g.iterrows():
        const_rows.append(dict(importance_rank=rank + 1, artefact=a, field=r.field, value=str(r.example)[:40],
                               classification=r.classification, also_constant_in_1444_row_artefacts=const_big.get(r.grep_token, "")))
cst = pd.DataFrame(const_rows)
cst.to_csv(os.path.join(OUT, "p21_M9_constants_top.csv"), index=False)
labc = cst[cst.artefact == LAB]
log(f"lab constants: {len(labc)}; of which also constant across the 1444-row books (pipeline-wide constant): {int((labc.also_constant_in_1444_row_artefacts != '').sum())}")

# ---------------------------------------------------------------- 6. ambiguous units
amb = census[census.unit_ambiguous][["artefact", "field", "lo", "hi", "unit", "unit_candidates", "classification"]].copy()
amb["importance_rank"] = amb.artefact.apply(lambda a: IMPORTANCE.index(a) + 1 if a in IMPORTANCE else 99)
amb = amb.sort_values(["importance_rank", "field"])
amb.to_csv(os.path.join(OUT, "p21_M9_ambiguous_units.csv"), index=False)
log(f"ambiguous-unit rows total: {len(amb)}; distinct field tokens: {amb.field.nunique()}; in lab book: {int((amb.artefact == LAB).sum())}")

# ---------------------------------------------------------------- 7. M-track summary
CORE_ARTS = ROW_LEVEL_DECISION_ARTEFACTS + ["qomega/garch_forecasts_20260911_115904.csv", "options/contracts_tested_20260911_115904.jsonl",
                                            "packages/<TICKER>.package.json [REP=AAPL.package.json; n_files=1572]",
                                            "ev3_shadow/ev3_stage1_contract_evaluations.parquet",
                                            "options/options_candidates_ranked.csv", "superbrain/eil_enriched_20260911_115904.csv"]
mrows = []
for (track, need), g in mmap.groupby(["track", "need"], sort=False):
    hits = g[g.classification != "MISSING_EVERYWHERE"]
    if hits.empty:
        mrows.append(dict(track=track, need=need, status="MISSING_EVERYWHERE", n_artefacts=0, n_fields=0, best=""))
        continue
    filled = hits[pd.to_numeric(hits.fill_rate, errors="coerce") > 0]
    coreh = filled[filled.artefact.isin(CORE_ARTS)]
    best = coreh.sort_values("fill_rate", ascending=False).head(6)
    mrows.append(dict(track=track, need=need, status="PRESENT" if len(filled) else "PRESENT_BUT_ALL_NULL",
                      n_artefacts=hits.artefact.nunique(), n_fields=hits.field.nunique(),
                      n_filled_rows=len(filled), best="; ".join(f"{os.path.basename(str(a)).split(' [')[0]}:{f} (fill {fr})" for a, f, fr in zip(best.artefact, best.field, best.fill_rate))))
mt = pd.DataFrame(mrows)
mt.to_csv(os.path.join(OUT, "p21_M9_mtrack_summary.csv"), index=False)
log("M-track summary:")
for _, r in mt.iterrows():
    log(f"  {r.track} {r.need}: {r.status} artefacts={r.n_artefacts} fields={r.n_fields} | {str(r.best)[:300]}")

# ---------------------------------------------------------------- 8. packages families
pk = census[census.artefact.str.startswith("packages/")].copy()
pk["top"] = pk.field.astype(str).str.split(r"[\.\[]").str[0]
prow = []
for top, g in pk.groupby("top"):
    fr = pd.to_numeric(g.fill_rate, errors="coerce")
    prow.append(dict(top_level_key=top, n_leaf_fields=len(g), LOAD_BEARING=int((g.classification == "LOAD_BEARING").sum()),
                     ADVISORY_USED=int((g.classification == "ADVISORY_USED").sum()), PRODUCED_UNREAD=int((g.classification == "PRODUCED_UNREAD").sum()),
                     DEAD=int((g.classification == "DEAD").sum()), constants=int(g.is_constant.sum()), all_null=int(g.all_null.sum()),
                     fill_lt_50pct=int((fr < 0.5).sum()), unread=int((g.consumed_by == "UNREAD").sum())))
pf = pd.DataFrame(prow).sort_values("n_leaf_fields", ascending=False)
pf.to_csv(os.path.join(OUT, "p21_M9_packages_families.csv"), index=False)
log(f"packages representative: {len(pk)} leaf fields under {len(pf)} top-level keys; top 12 by size:")
for _, r in pf.head(12).iterrows():
    log(f"  {r.top_level_key}: leaves={r.n_leaf_fields} LB={r.LOAD_BEARING} ADV={r.ADVISORY_USED} PU={r.PRODUCED_UNREAD} DEAD={r.DEAD} unread={r.unread}")
log("done")
