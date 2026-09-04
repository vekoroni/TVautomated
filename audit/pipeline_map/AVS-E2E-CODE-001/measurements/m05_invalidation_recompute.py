"""m05 - recompute the lifecycle invalidation test using the published governed
invalidation, for the 442 options rows whose remaining_runway_state is
THESIS_INVALIDATED.

Claim (s11.3): "recomputation using the published governed entry/invalidation values
produces zero invalidations for those 442 EOD rows."

Field identification (from source, read-only):
  scripts/avshunter_options_intelligence.py
    L3801-3808  spot = stock_price; entry = entry_price (default spot);
                stop = stop_loss when >0 else entry*0.97
    L4016       ctx['stop'] = that stop
    L4085-4102  published invalidation_spot = raw stop when correctly sided,
                otherwise mirrored about entry (DIRECTION_MIRROR_FROM_STOP_LOSS_V1),
                otherwise None (MISSING_AUTHORITATIVE_STOP)
    L4549       lifecycle is called with invalidation_spot = ctx['stop']  (raw stop)
  contracts/options_liquidity_lifecycle.py
    L418-431    direction = +1 CALL / -1 PUT
                invalidated = direction * (current_spot - invalidation) <= 0
                thesis_spot and current_spot are both ctx['spot'] at the call site.

So the recomputation substitutes the published invalidation_spot for ctx['stop']
in the identical predicate, holding current_spot at ctx['spot'].
ctx['spot'] / ctx['entry'] / ctx['stop'] are not columns of options_intelligence;
they are recovered from the discovery artefact (stock_price / entry_price / stop_loss),
which is the frame the options stage reads.

Read-only.
"""
import csv
import os
from collections import Counter

RUN = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260831_010309"
RID = "20260831_010309"
OPT = os.path.join(RUN, "options", f"options_intelligence_{RID}.csv")
DISC = os.path.join(RUN, "discovery", f"discovery_candidates_ultimate_{RID}.csv")
csv.field_size_limit(2**31 - 1)


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


# --- discovery side: recover ctx spot/entry/stop exactly as the options stage does
disc = {}
with open(DISC, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    it, isp, ien, ist = (hdr.index(c) for c in ("ticker", "stock_price", "entry_price", "stop_loss"))
    for r in rdr:
        spot = num(r[isp]) or 0.0
        entry = num(r[ien])
        entry = entry if entry else spot
        raw = num(r[ist])
        auth = raw is not None and raw > 0
        stop = raw if auth else entry * 0.97
        disc[r[it]] = {"spot": spot, "entry": entry, "raw_stop": raw, "stop": stop, "authoritative": auth}

# --- options side
with open(OPT, "r", encoding="utf-8", newline="") as fh:
    rdr = csv.reader(fh)
    hdr = next(rdr)
    idx = {c: hdr.index(c) for c in
           ("ticker", "remaining_runway_state", "canonical_direction", "side",
            "invalidation_spot", "invalidation_source", "entry_spot", "structural_target",
            "underlying_price")}
    rows = [r for r in rdr]

sel = [r for r in rows if r[idx["remaining_runway_state"]] == "THESIS_INVALIDATED"]
print(f"options rows = {len(rows)}; THESIS_INVALIDATED rows = {len(sel)}")

src = Counter()
no_disc = 0
as_used_invalidated = 0
recomputed_invalidated = 0
recomputed_undefined = 0        # published invalidation absent -> predicate undefined
stop_equals_published = 0
stop_differs = 0
spot_mismatch = 0

for r in sel:
    t = r[idx["ticker"]]
    side = (r[idx["canonical_direction"]] or r[idx["side"]]).upper()
    d = 1.0 if side == "CALL" else -1.0
    pub = num(r[idx["invalidation_spot"]])
    src[r[idx["invalidation_source"]]] += 1
    ctx = disc.get(t)
    if ctx is None:
        no_disc += 1
        continue
    cur = ctx["spot"]
    up = num(r[idx["underlying_price"]])
    if up is not None and cur and abs(up - cur) > 1e-6:
        spot_mismatch += 1
    # predicate as actually used by the lifecycle
    if d * (cur - ctx["stop"]) <= 0:
        as_used_invalidated += 1
    # same predicate with the published governed invalidation
    if pub is None:
        recomputed_undefined += 1
    else:
        if abs(pub - ctx["stop"]) < 1e-9:
            stop_equals_published += 1
        else:
            stop_differs += 1
        if d * (cur - pub) <= 0:
            recomputed_invalidated += 1

n = len(sel)
print(f"\ndenominator = {n} THESIS_INVALIDATED rows")
print(f"rows with no matching discovery ticker            : {no_disc}")
print(f"rows where underlying_price != discovery stock_price: {spot_mismatch}")
print(f"predicate reproduced as-used (invalidated)        : {as_used_invalidated}")
print(f"published invalidation_spot == ctx['stop']        : {stop_equals_published}")
print(f"published invalidation_spot != ctx['stop']        : {stop_differs}")
print(f"published invalidation_spot absent (undefined)    : {recomputed_undefined}")
print(f"RECOMPUTED invalidated with published value       : {recomputed_invalidated}")
print("\ninvalidation_source distribution over those rows:")
for k, v in src.most_common():
    print(f"  {k!r}: {v}")

# whole-file view of invalidation_source for context
allsrc = Counter(r[idx["invalidation_source"]] for r in rows)
print("\ninvalidation_source over all 1248 options rows:")
for k, v in allsrc.most_common():
    print(f"  {k!r}: {v}")
