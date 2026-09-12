"""AVS-TST-DOI-001 T10: fragility of the DOI-10 identity reconciliation.

domain/dynamic_options_projection.py:108-110 keys the whole ALL-OPPORTUNITIES
merge on TICKER ALONE and raises when a ticker repeats.  intelligence-lab/
intelligence_lab.py:317-320 swallows that raise with a bare `except Exception:
pass` and silently returns the un-overlaid v2 book.  These probes show what the
governed book must never contain for DOI-10 to keep working.  Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from domain.dynamic_options_projection import merge_all_opportunities


def case(name, full, actionable):
    try:
        rows, rec = merge_all_opportunities(full, actionable)
        print(f"  {name:<62} OK   n={len(rows)} overlaid={rec['actionable_rows_overlaid']}")
    except Exception as error:
        print(f"  {name:<62} RAISE {type(error).__name__}: {error}")


print("=" * 96)
print("T10 - DOI-10 merge identity reconciliation: what breaks the ALL OPPORTUNITIES overlay")
print("=" * 96)

base = [
    {"run_id": "R", "ticker": "AAA", "thesis_id": "AAA:CALL:d:OLM2",
     "trade_idea_id": "R:AAA:CALL:LONG_CALL:10:2026-09-18", "governed_direction": "CALL"},
    {"run_id": "R", "ticker": "BBB", "thesis_id": "BBB:PUT:d:OLM2",
     "trade_idea_id": "R:BBB:PUT:LONG_PUT:20:2026-09-18", "governed_direction": "PUT"},
]
act = [dict(base[0], final_action="BUY_SMALL")]

case("baseline (unique tickers)", base, act)

# 1. same ticker carrying a CALL and a PUT thesis (a legitimate population)
two_sided = base + [
    {"run_id": "R", "ticker": "AAA", "thesis_id": "AAA:PUT:d:OLM2",
     "trade_idea_id": "R:AAA:PUT:LONG_PUT:9:2026-09-18", "governed_direction": "PUT"}]
case("same ticker with both a CALL and a PUT thesis", two_sided, act)

# 2. a STRANGLE / UNRESOLVED row alongside a directional one
strangle = base + [
    {"run_id": "R", "ticker": "AAA", "thesis_id": "AAA:STRANGLE:d:OLM2",
     "trade_idea_id": "R:AAA:STRANGLE:STRANGLE:10:2026-09-18", "governed_direction": "STRANGLE"}]
case("same ticker with a STRANGLE row alongside a directional row", strangle, act)

# 3. a row whose ticker is blank
blank = base + [{"run_id": "R", "ticker": "", "thesis_id": "?", "governed_direction": "CALL"}]
case("one row with an empty ticker", blank, act)

# 4. identity mismatch on thesis_id -> whole merge aborts, not just that row
bad = [dict(base[0], thesis_id="AAA:CALL:OTHERDAY:OLM2")]
case("ONE actionable row disagreeing on thesis_id", base, bad)

# 5. identity check is skipped when either side is blank
blank_side = [dict(base[0], thesis_id="", trade_idea_id="")]
case("actionable row with BLANK thesis_id/trade_idea_id (check skipped)", base, blank_side)

# 6. direction is never part of the reconciliation key
wrong_dir = [dict(base[0], governed_direction="PUT", canonical_direction="PUT",
                  final_direction="PUT", direction="PUT")]
rows, rec = merge_all_opportunities(base, wrong_dir)
print(f"  {'actionable row whose DIRECTION contradicts the governed row':<62} "
      f"OK   overlaid={rec['actionable_rows_overlaid']}  "
      f"AAA governed_direction is now {rows[0]['governed_direction']!r}")

print("\nCONCLUSIONS")
print("  * merge_all_opportunities keys on ticker only (dynamic_options_projection.py:108).")
print("  * A duplicate ticker aborts the ENTIRE overlay, not the offending row.")
print("  * intelligence_lab.py:317-320 catches that and silently serves the un-overlaid v2 book.")
print("  * direction is NOT part of the four-field identity check, so an actionable row")
print("    can overwrite governed_direction/final_direction/canonical_direction unchecked.")
