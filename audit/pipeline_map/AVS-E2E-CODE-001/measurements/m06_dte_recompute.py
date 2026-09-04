"""m06 - DTE_UNSUITABLE count and the recomputation using the governed
5/10/20-session planned hold.

Claims (s11.4):
  657 Options rows currently labelled DTE_UNSUITABLE;
  only 32 remain unsuitable when the governed 5/10/20-session holds are used;
  in the final book, 145 are labelled unsuitable.

Field identification (from source, read-only):
  contracts/options_liquidity_lifecycle.py
    L36-37   DEFAULT_MONITOR_SESSIONS = 3, DEFAULT_EXIT_BUFFER_SESSIONS = 5
    L107     minimum_required_dte = ceil(remaining_hold_sessions + 3 + 5)
    L292-299 liquidity_state = DTE_UNSUITABLE when dte < minimum_required_dte
             (this test precedes moneyness and spread tests)
  scripts/avshunter_options_intelligence.py
    L3832/3926  hold_days = layer2__recommended_hold_days when > 0
    L4546       remaining_hold_sessions = ctx['hold_days']
    L4104-4112  planned_hold_sessions = 5 / 10 / 20 from horizon_bucket, else None

Recomputation: minimum_required_dte_governed = ceil(planned_hold_sessions + 3 + 5)
and re-apply dte < minimum, holding the published contract dte constant.

Read-only.
"""
import csv
import math
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
OPT = os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")
BOOK = os.path.join(RUN, "intelligence_lab", f"final_opportunity_book_{RID}.csv")
csv.field_size_limit(2**31 - 1)

MONITOR, EXIT_BUFFER = 3, 5


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


COLS = ("ticker", "liquidity_state", "dte", "contract_dte", "minimum_required_dte",
        "remaining_hold_sessions", "planned_hold_sessions", "planned_hold_source",
        "layer2__recommended_hold_days", "horizon_bucket")

with open(OPT, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    missing = [c for c in COLS if c not in hdr]
    idx = {c: hdr.index(c) for c in COLS if c in hdr}
    rows = [r for r in rdr]

print(f"options rows = {len(rows)}; columns absent = {missing}")
states = Counter(r[idx["liquidity_state"]] for r in rows)
print(f"liquidity_state == DTE_UNSUITABLE: {states.get('DTE_UNSUITABLE', 0)} of {len(rows)}")

sel = [r for r in rows if r[idx["liquidity_state"]] == "DTE_UNSUITABLE"]
n = len(sel)

# sanity: does published minimum_required_dte reproduce ceil(remaining_hold+8)?
repro = miss_repro = 0
for r in sel:
    h = num(r[idx["remaining_hold_sessions"]])
    m = num(r[idx["minimum_required_dte"]])
    if h is None or m is None:
        miss_repro += 1
    elif math.ceil(h + MONITOR + EXIT_BUFFER) == int(m):
        repro += 1
print(f"\npublished minimum_required_dte == ceil(remaining_hold_sessions+8): {repro}/{n}"
      f" (inputs missing on {miss_repro})")

hold_dist = Counter(r[idx["remaining_hold_sessions"]] for r in sel)
print("remaining_hold_sessions actually used, over the 657:")
for k, v in hold_dist.most_common(10):
    print(f"  {k!r}: {v}")

phs_dist = Counter(r[idx["planned_hold_sessions"]] for r in sel)
print("planned_hold_sessions (governed) over the 657:")
for k, v in phs_dist.most_common(10):
    print(f"  {k!r}: {v}")

still = 0
undefined = 0
dte_missing = 0
for r in sel:
    dte = num(r[idx["dte"]])
    if dte is None:
        dte = num(r[idx["contract_dte"]])
    phs = num(r[idx["planned_hold_sessions"]])
    if dte is None:
        dte_missing += 1
        continue
    if phs is None:
        undefined += 1
        continue
    if dte < math.ceil(phs + MONITOR + EXIT_BUFFER):
        still += 1

print(f"\ndenominator = {n} DTE_UNSUITABLE rows")
print(f"  contract dte unavailable                     : {dte_missing}")
print(f"  planned_hold_sessions unrouted (None)        : {undefined}")
print(f"  still unsuitable under governed 5/10/20 hold : {still}")
print(f"  would clear                                  : {n - still - undefined - dte_missing}")

# final book
with open(BOOK, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    bh = next(rdr)
    bi = bh.index("liquidity_state")
    bstates = Counter(r[bi] for r in rdr)
print(f"\nfinal book liquidity_state == DTE_UNSUITABLE: {bstates.get('DTE_UNSUITABLE', 0)}"
      f" of {sum(bstates.values())}")
