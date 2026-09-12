"""AVS-TST-DOI-001 T10 task 9: trace every DISPLAYED DOI value on 10 rows
(5 CALL / 5 PUT) back to thesis_id, contract observation dataset id and
model/calculation version.  Read-only.

Displayed DOI fields are those rendered by intelligence-lab/static/index.html
lines 2691-2709 (the 'DOI Ranking' modal pane).
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from canonical_data.dynamic_options_projection import DynamicOptionsProjectionResolver
from contracts.interpreter_handoff import validate_handoff_manifest
from domain.dynamic_options_projection import merge_all_opportunities

RUN = "20260909_071646"
BOOK = ROOT / "data" / "output" / "runs" / RUN / "intelligence_lab" / f"final_opportunity_book_{RUN}.json"
HANDOFF = ROOT / "data" / "output" / "runs" / RUN / "interpreter" / "handoff_manifest.json"
DB = ROOT / "audit" / "doi" / "AVS-TST-DOI-001" / "scratch" / "T10" / "cp_nodoi.sqlite"

# index.html 2691-2709: label -> row field it renders (with its JS fallback)
DISPLAYED = [
    ("Projection State", "doi_projection_state", "'NOT_EVALUATED'"),
    ("Ranking Mode", "doi_ranking_mode", "'NOT EVALUATED'"),
    ("Governed Contract", "doi_governed_contract_symbol", "selected_contract_symbol -> '-'"),
    ("DOI Preferred Contract", "doi_preferred_contract_symbol", "'-'"),
    ("Contract Alignment", "doi_contract_alignment", "'NOT_COMPARABLE'"),
    ("Executable in 3 Sessions", "doi_p_liquidity_3d", "'NOT EVALUATED'"),
    ("Positive Return", "doi_p_positive_return", "'NOT EVALUATED'"),
    ("Target Before Invalidation", "doi_p_target_before_invalidation", "'NOT EVALUATED'"),
    ("Model Uncertainty", "doi_model_uncertainty", "'NOT EVALUATED'"),
    ("Evidence Cutoff", "doi_evidence_cutoff_utc", "'NOT EVALUATED'"),
    ("Model", "doi_probability_model_id", "'NOT EVALUATED'"),
    ("Authority", "doi_authority", "'ADVISORY ONLY'"),
    ("Reason", "doi_projection_reason", "generic sentence"),
    ("Ranked Contract Family", "doi_alternatives_json", "'No ranked alternatives available.'"),
]

OCC = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def parse_occ(symbol):
    m = OCC.match(str(symbol or "").strip().upper())
    if not m:
        return None
    root, yy, mm, dd, cp, strike = m.groups()
    return {"root": root, "expiry": f"20{yy}-{mm}-{dd}", "right": "CALL" if cp == "C" else "PUT",
            "strike": int(strike) / 1000.0}


def direction(r):
    for f in ("governed_direction", "canonical_direction", "final_direction", "direction"):
        v = str(r.get(f) or "").strip().upper()
        if v in {"CALL", "PUT"}:
            return v
    return "OTHER"


payload = json.loads(BOOK.read_text(encoding="utf-8"))
full = payload["rows"]
actionable = [dict(r) for r in validate_handoff_manifest(HANDOFF, require_accepted=True).book_rows]
merged, _ = merge_all_opportunities(full, actionable)
rows = DynamicOptionsProjectionResolver(DB).project_rows(merged)

calls = [r for r in rows if direction(r) == "CALL"]
puts = [r for r in rows if direction(r) == "PUT"]
# prefer the 4 accepted actionable CALLs, then fill
accepted = [r for r in calls if r.get("lab_actionable_handoff_member") is True]
sample = (accepted + [r for r in calls if r not in accepted])[:5] + puts[:5]

print("=" * 100)
print("T10 TASK 9 - EXACT SOURCE RECONCILIATION FOR 10 ROWS (5 CALL / 5 PUT)")
print("=" * 100)

untraceable = collections.Counter()
for r in sample:
    d = direction(r)
    acc = "ACCEPTED-ACTIONABLE" if r.get("lab_actionable_handoff_member") is True else "governed-only"
    print(f"\n### {r.get('ticker')}  [{d}]  {acc}")
    print(f"    thesis_id                = {r.get('thesis_id')}")
    print(f"    trade_idea_id            = {r.get('trade_idea_id')}")
    print(f"    dir_calc_version         = {r.get('dir_calc_version')}")
    print(f"    direction_policy_version = {r.get('direction_policy_version')}")
    print(f"    doi_input_dataset_ids    = {r.get('doi_input_dataset_ids_json')}")
    for label, field, fallback in DISPLAYED:
        value = r.get(field)
        blank = value is None or str(value).strip() in ("", "[]")
        src = "canonical_doi_projection_read_only"
        if field == "doi_governed_contract_symbol":
            src = "row.selected_contract_symbol|contract_symbol|morning_selected_contract_symbol"
        state = "RENDERS JS FALLBACK -> " + fallback if blank else "traceable"
        if blank:
            untraceable[label] += 1
        print(f"      {label:<28} = {str(value)!r:<28} [{state}]")
    # contract identity coherence
    occ = parse_occ(r.get("doi_governed_contract_symbol"))
    if occ:
        s_ok = str(r.get("strike") or "") in ("", "None") or abs(float(r["strike"]) - occ["strike"]) < 1e-6
        e_ok = str(r.get("expiry") or "") in ("", "None") or str(r.get("expiry")) == occ["expiry"]
        d_ok = occ["right"] == d
        print(f"    CONTRACT COHERENCE: symbol={r.get('doi_governed_contract_symbol')} -> "
              f"strike {occ['strike']} exp {occ['expiry']} {occ['right']}")
        print(f"      vs row strike={r.get('strike')} expiry={r.get('expiry')} direction={d}"
              f"   strike_match={s_ok} expiry_match={e_ok} right_match={d_ok}")

print("\n" + "=" * 100)
print("DISPLAYED DOI VALUES WITH NO TRACEABLE SOURCE (fell through to a JS fallback string)")
print("=" * 100)
for label, n in untraceable.items():
    print(f"  {label:<30} {n}/10 rows")

# ---- generalise the contract-coherence check over the whole book -----------
print("\n" + "=" * 100)
print("CONTRACT IDENTITY COHERENCE ACROSS THE WHOLE GOVERNED BOOK")
print("=" * 100)
stats = collections.Counter()
mismatch_examples = []
for r in rows:
    sym = r.get("doi_governed_contract_symbol")
    occ = parse_occ(sym)
    d = direction(r)
    if not occ:
        stats[f"NO_PARSEABLE_SYMBOL::{d}"] += 1
        continue
    strike, expiry = r.get("strike"), str(r.get("expiry") or "")
    try:
        s_ok = strike in (None, "", "None") or abs(float(strike) - occ["strike"]) < 1e-6
    except (TypeError, ValueError):
        s_ok = True
    e_ok = expiry in ("", "None") or expiry == occ["expiry"]
    if s_ok and e_ok:
        stats[f"COHERENT::{d}"] += 1
    else:
        stats[f"MISMATCH::{d}"] += 1
        if len(mismatch_examples) < 12:
            mismatch_examples.append(
                f"{r.get('ticker'):6s} {d:4s} symbol={sym} (strike {occ['strike']}, exp {occ['expiry']}) "
                f"vs row strike={strike} expiry={expiry}  trade_idea_id={r.get('trade_idea_id')}")
for k in sorted(stats):
    print(f"  {k:<32} {stats[k]}")
print("\n  examples:")
for line in mismatch_examples:
    print("   ", line)
