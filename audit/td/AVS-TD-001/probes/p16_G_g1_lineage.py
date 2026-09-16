"""p16_G_g1_lineage.py -- Track G / G1 (REQ-WP6-01 acceptance: every displayed number resolves to a
source dataset ID and a calculation version).  READ-ONLY.

Samples 10 rows (random.seed(20260912)) from lab_signal_book_v3.csv and 10 from
final_opportunity_book_<run>.csv.  "Displayed" = columns of the row that the Lab UI renders:
  (a) field tokens referenced in intelligence-lab/static/index.html (sig.X / s.X / row.X ...),
  (b) LAB_REQUIRED_FIELDS and PHYSICS_FIELDS,
  (c) alias targets and sources in intelligence_lab.py's name-only projection.
A displayed value is "a number" if it parses as float.  For each such number we look for a row-level
dataset id and calculation version via the family map below (row-level columns only), then at the
row's field_provenance_json, then at manifest level.
Outputs p16_G_g1_lineage.json beside this file.
"""
from __future__ import annotations
import csv, json, random, re, sys
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUN = "20260911_115904"
R = ROOT / "data/output/runs" / RUN
OUT = Path(__file__).with_suffix(".json")
sys.path.insert(0, str(ROOT))
csv.field_size_limit(1 << 30)

# ---- displayed column set ------------------------------------------------------------------
html = (ROOT / "intelligence-lab/static/index.html").read_text(encoding="utf-8", errors="replace")
html_tokens = set(re.findall(r"\b(?:sig|s|row|r|signal|d|item|x)\.([a-zA-Z_][a-zA-Z_0-9]*)", html))
ui_src = (ROOT / "intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8", errors="replace")
alias_block = ui_src[ui_src.index("aliases = {"): ui_src.index("for target, sources in aliases.items()")]
alias_tokens = set(re.findall(r"\"([a-zA-Z_][a-zA-Z_0-9]*)\"", alias_block))
phys = ui_src[ui_src.index("PHYSICS_FIELDS = ["): ui_src.index("]", ui_src.index("PHYSICS_FIELDS = ["))]
phys_tokens = set(re.findall(r"\"([a-zA-Z_0-9]+)\"", phys))
from contracts.lab_control import LAB_REQUIRED_FIELDS  # noqa: E402
displayed = html_tokens | alias_tokens | phys_tokens | set(LAB_REQUIRED_FIELDS)

# ---- lineage family map: displayed-field prefix -> (dataset_id column, calc_version column) --
# Only row-level columns actually present on the books are used (checked at runtime).
FAMILY = [
    (re.compile(r"^doi_"), "doi_input_dataset_ids_json", "doi_projection_version"),
    (re.compile(r"^(contract_|current_contract_|premium|spread_pct$|opt__contract_|opt__premium|opt__contract_spread|strike$|opt__strike$|dte$|opt__contract_dte$)"), "selected_quote_dataset_id", None),
    (re.compile(r"^(underlying_nbbo_)"), "underlying_nbbo_dataset_id", None),
    (re.compile(r"^(morning_)"), "morning_quote_dataset_id", None),
    (re.compile(r"^(monetisability_)"), "selected_quote_dataset_id", "monetisability_calculation_version"),
    (re.compile(r"^(rr_|opt__rr)"), None, "rr_calculation_version"),
    (re.compile(r"^(direction_resolution_)"), None, "dir_calc_version"),
    (re.compile(r"^(execution_viability_)"), "selected_quote_dataset_id", "execution_viability_policy_version"),
    (re.compile(r"^(opportunity_tier)"), None, "opportunity_tier_policy_version"),
    (re.compile(r"^(macro_|usmi_)"), "macro_packet_sha256", "usmi_calculation_version"),
    (re.compile(r"^(usmi_)"), "usmi_packet_sha256", "usmi_calculation_version"),
    (re.compile(r"^(option_chain_)"), "option_chain_dataset_id", None),
]
LINEAGE_COLS = re.compile(r"dataset_id|calculation_version|_version$|sha256|schema_version|policy_version|fingerprint|snapshot_id|event_id|evidence_id", re.I)

def is_number(v: str) -> bool:
    v = (v or "").strip()
    if v == "" or v.lower() in {"nan", "none", "null", "true", "false"}:
        return False
    try:
        float(v); return True
    except ValueError:
        return False

def read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))

def analyse(rows, label):
    cols = set(rows[0].keys())
    disp_cols = sorted(c for c in cols if c in displayed)
    lineage_cols = sorted(c for c in cols if LINEAGE_COLS.search(c))
    random.seed(20260912)
    idx = sorted(random.sample(range(len(rows)), 10))
    per_row = []
    for i in idx:
        row = rows[i]
        prov = {}
        try:
            prov = json.loads(row.get("field_provenance_json") or "{}")
        except json.JSONDecodeError:
            pass
        nums = [(c, row[c]) for c in disp_cols if is_number(row.get(c, ""))]
        both = ds_only = ver_only = neither = prov_hit = 0
        unresolved = []
        for c, v in nums:
            ds = ver = None
            for pat, dcol, vcol in FAMILY:
                if pat.search(c):
                    ds = dcol if dcol and (row.get(dcol) or "").strip() not in ("", "[]", "{}") else None
                    ver = vcol if vcol and (row.get(vcol) or "").strip() else None
                    break
            if c in prov:
                prov_hit += 1
            if ds and ver: both += 1
            elif ds: ds_only += 1
            elif ver: ver_only += 1
            else:
                neither += 1; unresolved.append(c)
        direction = row.get("final_direction") or row.get("governed_direction") or row.get("canonical_direction") or "OTHER"
        per_row.append({
            "row_index": i, "ticker": row.get("ticker"), "direction": direction,
            "displayed_numbers": len(nums), "resolvable_dataset_and_version": both,
            "dataset_only": ds_only, "version_only": ver_only, "neither": neither,
            "provenance_json_entries_for_displayed_numbers": prov_hit,
            "provenance_json_total_entries": len(prov),
            "provenance_sample": dict(list(prov.items())[:3]),
            "unresolved_sample": unresolved[:12],
            "row_level_lineage_values": {c: (row.get(c) or "")[:60] for c in lineage_cols if c not in ("source_payload_json",)},
        })
    fully = sum(1 for r in per_row if r["displayed_numbers"] and r["resolvable_dataset_and_version"] == r["displayed_numbers"])
    return {
        "book": label, "rows": len(rows), "cols": len(cols),
        "displayed_cols_present": len(disp_cols), "displayed_cols_list_sample": disp_cols[:40],
        "row_level_lineage_columns": lineage_cols,
        "has_field_provenance_json": "field_provenance_json" in cols,
        "rows_fully_resolvable": f"{fully}/10",
        "per_row": per_row,
        "by_direction": {
            d: {"rows": sum(1 for r in per_row if r["direction"] == d),
                "fully_resolvable": sum(1 for r in per_row if r["direction"] == d and r["displayed_numbers"] and r["resolvable_dataset_and_version"] == r["displayed_numbers"])}
            for d in sorted({r["direction"] for r in per_row})},
    }

v3 = read_rows(R / "intelligence_lab/lab_signal_book_v3.csv")
fb = read_rows(R / f"intelligence_lab/final_opportunity_book_{RUN}.csv")
res = {"run": RUN, "displayed_token_counts": {"index_html": len(html_tokens), "ui_aliases": len(alias_tokens), "physics": len(phys_tokens), "lab_required": len(LAB_REQUIRED_FIELDS), "union": len(displayed)}}
res["lab_signal_book_v3"] = analyse(v3, "lab_signal_book_v3.csv")
res["final_opportunity_book"] = analyse(fb, f"final_opportunity_book_{RUN}.csv")

# ---- manifest-level lineage ------------------------------------------------------------------
man = json.loads((R / "intelligence_lab/lab_signal_book_v3.manifest.json").read_text(encoding="utf-8"))
hand = json.loads((R / "interpreter/handoff_manifest.json").read_text(encoding="utf-8"))
res["manifest_lineage"] = {
    "lab_signal_book_v3.manifest.json_keys": sorted(man.keys()),
    "has_per_field_dataset_ids": any("dataset" in k for k in man),
    "has_calculation_version": any("calculation_version" in k for k in man),
    "authority_map_version": man.get("authority_map_version"), "book_sha256": man.get("book_sha256"),
    "handoff_manifest_keys": sorted(hand.keys()),
    "handoff_artifact_roles": [(a.get("role"), a.get("schema_version")) for a in hand.get("artifacts", [])],
    "handoff_has_dataset_ids": any("dataset" in k for k in hand),
}
# ---- validation events -----------------------------------------------------------------------
ve_dir = R / "morning_validation/validation_events"
ve_files = sorted(ve_dir.glob("validation_*.json"))
ve_keys = set(); ve_lineage = {}
for p in ve_files[:200]:
    d = json.loads(p.read_text(encoding="utf-8"))
    ve_keys |= set(d.keys())
    for k in d:
        if LINEAGE_COLS.search(k) or k in ("lineage", "source_dataset_id", "authority_map_version", "book_sha256"):
            ve_lineage.setdefault(k, str(d[k])[:80])
sample_ve = json.loads(ve_files[0].read_text(encoding="utf-8")) if ve_files else {}
res["validation_events"] = {"count": len(ve_files), "keys_union_first200": sorted(ve_keys), "lineage_like_keys": ve_lineage,
                             "sample": {k: (str(v)[:100]) for k, v in sample_ve.items()}}
OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in res.items() if k not in ("lab_signal_book_v3", "final_opportunity_book")}, indent=1)[:3000])
for b in ("lab_signal_book_v3", "final_opportunity_book"):
    x = res[b]
    print(b, "fully_resolvable", x["rows_fully_resolvable"], "displayed_cols_present", x["displayed_cols_present"], "provenance", x["has_field_provenance_json"], x["by_direction"])
    for r in x["per_row"]:
        print("  ", r["ticker"], r["direction"], "nums", r["displayed_numbers"], "both", r["resolvable_dataset_and_version"], "ds", r["dataset_only"], "ver", r["version_only"], "neither", r["neither"], "prov", r["provenance_json_entries_for_displayed_numbers"], "/", r["provenance_json_total_entries"])
    print("  lineage cols:", x["row_level_lineage_columns"])
