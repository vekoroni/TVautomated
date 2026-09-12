"""AVS-TST-DOI-001 T10: exact before/after values for every non-DOI field that
the DOI-10 ALL-OPPORTUNITIES merge mutates. Read-only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from contracts.interpreter_handoff import validate_handoff_manifest
from contracts.lab_evidence_overlay import PROTECTED_AUTHORITY_FIELDS, OVERLAY_ALLOWED_FIELDS
from domain.dynamic_options_projection import merge_all_opportunities

RUN = "20260909_071646"
BOOK = ROOT / "data" / "output" / "runs" / RUN / "intelligence_lab" / f"final_opportunity_book_{RUN}.json"
HANDOFF = ROOT / "data" / "output" / "runs" / RUN / "interpreter" / "handoff_manifest.json"

base_rows = json.loads(BOOK.read_text(encoding="utf-8"))["rows"]
base_by_ticker = {str(r.get("ticker") or "").upper(): dict(r) for r in base_rows}
actionable = [dict(r) for r in validate_handoff_manifest(HANDOFF, require_accepted=True).book_rows]
merged, _ = merge_all_opportunities(json.loads(BOOK.read_text(encoding="utf-8"))["rows"], actionable)

changes: dict[str, list] = {}
for row in merged:
    tk = str(row.get("ticker") or "").upper()
    base = base_by_ticker.get(tk, {})
    for c in set(base) | set(row):
        if c.startswith("doi_") or c == "lab_actionable_handoff_member":
            continue
        b, a = base.get(c), row.get(c)
        if str(b if b is not None else "") != str(a if a is not None else ""):
            changes.setdefault(c, []).append({"ticker": tk, "before": b, "after": a})

print("=" * 78)
print("NON-DOI FIELDS MUTATED BY merge_all_opportunities (DOI-10 ALL OPPORTUNITIES)")
print("=" * 78)
for field in sorted(changes):
    prot = "  <<< PROTECTED_AUTHORITY_FIELD" if field in PROTECTED_AUTHORITY_FIELDS else ""
    allowed = "  [overlay-allowed]" if field in OVERLAY_ALLOWED_FIELDS else ""
    print(f"\n### {field}{prot}{allowed}")
    for item in changes[field]:
        print(f"    {item['ticker']:6s} before={item['before']!r}  ->  after={item['after']!r}")

print("\n" + "=" * 78)
print("SUMMARY")
print("=" * 78)
prot_hit = sorted(set(changes) & set(PROTECTED_AUTHORITY_FIELDS))
not_allowed = sorted(f for f in changes if f not in OVERLAY_ALLOWED_FIELDS)
print(f"fields mutated                      : {len(changes)}")
print(f"PROTECTED_AUTHORITY_FIELDS mutated  : {len(prot_hit)} -> {prot_hit}")
print(f"outside OVERLAY_ALLOWED_FIELDS      : {len(not_allowed)} -> {not_allowed}")

# identity coherence of the 4 accepted rows
print("\n" + "=" * 78)
print("ACCEPTED ACTIONABLE ROW IDENTITY COHERENCE")
print("=" * 78)
for r in actionable:
    print(f"{r.get('ticker'):6s} thesis_id={r.get('thesis_id')}")
    print(f"       trade_idea_id={r.get('trade_idea_id')}")
    print(f"       selected_contract_symbol={r.get('selected_contract_symbol')}")
    print(f"       strike={r.get('selected_strike') or r.get('strike')} "
          f"expiry={r.get('selected_expiry') or r.get('expiry')}")
