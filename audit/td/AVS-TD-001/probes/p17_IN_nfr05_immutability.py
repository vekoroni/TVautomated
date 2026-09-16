"""p17 NFR-05: assessment immutability tested on artefacts (control_plane copy, read-only).

Runs A=20260910_150045 -> B=20260911_115904.  Split CALL / PUT / OTHER (option_side or thesis_id side).
Checks:
 1. triggers preventing UPDATE/DELETE on option_contract_observations / option_contract_selection_events
 2. selection event -> observation identity: selected_observation_id resolves, same contract_symbol, same run
 3. (ticker, side) present in both runs: contract unchanged vs changed; for changed, B's first selection
    event carries previous_contract_symbol == A's symbol and economics_recomputed = 1
 4. within B, theses with >1 selection event (EOD + morning requote): new observation id per new quote?
 5. same provider quote (contract_symbol, quote_as_of) recorded in both runs under different observation_id
    with differing economics fields (spread_pct, delta, iv, liquidity_state)
 6. economics_recomputed distinct values; correction/supersession columns
 7. doi_contract_assessments rows (assessment_id persistence)
Output p17_IN_nfr05_immutability.json and p17_IN_nfr05_immutability.csv.
"""
import csv, json, sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = ROOT / "audit/td/AVS-TD-001/probes"
DB = ROOT / "audit/td/AVS-TD-001/db_copies/control_plane.sqlite"
A, B = "20260910_150045", "20260911_115904"
con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
res = {}
res["triggers"] = [dict(r) for r in con.execute(
    "select name, tbl_name from sqlite_master where type='trigger' and tbl_name in "
    "('option_contract_observations','option_contract_selection_events','doi_contract_assessments')")]

def side_of(thesis_id, option_side=None):
    s = (option_side or "").upper()
    if s in ("CALL", "PUT"):
        return s
    t = str(thesis_id or "").upper()
    return "CALL" if ":CALL:" in t else "PUT" if ":PUT:" in t else "OTHER"

obs = {r["observation_id"]: dict(r) for r in con.execute(
    "select observation_id, thesis_id, run_id, ticker, contract_symbol, option_side, quote_as_of, observed_at, "
    "spread_pct, delta, iv, bid, ask, liquidity_state, payload_hash, calculation_version, supersedes_event_id, correction_state "
    "from option_contract_observations where run_id in (?,?)", (A, B))}
sel = [dict(r) for r in con.execute(
    "select selection_event_id, event_key, thesis_id, run_id, previous_contract_symbol, selected_contract_symbol, "
    "selected_observation_id, selection_reason, selection_version, economics_recomputed, selected_at, metadata_json, supersedes_event_id "
    "from option_contract_selection_events where run_id in (?,?)", (A, B))]
res["rows"] = {"observations": Counter((o["run_id"], side_of(o["thesis_id"], o["option_side"])) for o in obs.values()),
               "selection_events": Counter((s["run_id"], side_of(s["thesis_id"])) for s in sel)}

# 2. identity join
c2 = Counter()
for s in sel:
    sd = side_of(s["thesis_id"])
    o = obs.get(s["selected_observation_id"])
    if o is None:
        o2 = con.execute("select contract_symbol, run_id from option_contract_observations where observation_id=?",
                         (s["selected_observation_id"],)).fetchone()
        c2[(sd, "OBSERVATION_IN_OTHER_RUN" if o2 else "OBSERVATION_MISSING")] += 1
        if o2 and o2["contract_symbol"] != s["selected_contract_symbol"]:
            c2[(sd, "SYMBOL_MISMATCH_OTHER_RUN")] += 1
        continue
    c2[(sd, "RESOLVES")] += 1
    if o["contract_symbol"] != s["selected_contract_symbol"]:
        c2[(sd, "SYMBOL_MISMATCH")] += 1
    if o["run_id"] != s["run_id"]:
        c2[(sd, "RUN_MISMATCH")] += 1
    if s["previous_contract_symbol"] and s["previous_contract_symbol"] != s["selected_contract_symbol"] and not s["economics_recomputed"]:
        c2[(sd, "CHANGED_WITHOUT_RECOMPUTE")] += 1
res["selection_to_observation"] = c2

# 3. cross-run contract change
def last_selection(run):
    best = {}
    for s in sel:
        if s["run_id"] != run:
            continue
        o = obs.get(s["selected_observation_id"]) or {}
        tk = (o.get("ticker") or s["thesis_id"].split(":")[0], side_of(s["thesis_id"]))
        key = (s["selected_at"], s["selection_version"])
        if tk not in best or key > best[tk][0]:
            best[tk] = (key, s)
    return {k: v[1] for k, v in best.items()}
def first_selection(run):
    best = {}
    for s in sel:
        if s["run_id"] != run:
            continue
        o = obs.get(s["selected_observation_id"]) or {}
        tk = (o.get("ticker") or s["thesis_id"].split(":")[0], side_of(s["thesis_id"]))
        key = (s["selected_at"], s["selection_version"])
        if tk not in best or key < best[tk][0]:
            best[tk] = (key, s)
    return {k: v[1] for k, v in best.items()}
la, fb = last_selection(A), first_selection(B)
c3 = Counter()
examples = []
for tk, sa in la.items():
    sb = fb.get(tk)
    if not sb:
        c3[(tk[1], "ONLY_IN_A")] += 1; continue
    same = sa["selected_contract_symbol"] == sb["selected_contract_symbol"]
    c3[(tk[1], "SAME_CONTRACT" if same else "CONTRACT_CHANGED")] += 1
    oa, ob = obs.get(sa["selected_observation_id"]), obs.get(sb["selected_observation_id"])
    if same:
        c3[(tk[1], "SAME_CONTRACT_NEW_OBSERVATION_ID" if sa["selected_observation_id"] != sb["selected_observation_id"] else "SAME_CONTRACT_REUSED_OBSERVATION_ID")] += 1
        if oa and ob and oa["quote_as_of"] == ob["quote_as_of"]:
            c3[(tk[1], "SAME_CONTRACT_SAME_QUOTE_AS_OF")] += 1
    else:
        c3[(tk[1], "CHANGED_PREV_SYMBOL_LINKS_A" if sb["previous_contract_symbol"] == sa["selected_contract_symbol"] else
                   "CHANGED_PREV_SYMBOL_NULL" if not sb["previous_contract_symbol"] else "CHANGED_PREV_SYMBOL_OTHER")] += 1
        c3[(tk[1], "CHANGED_ECON_RECOMPUTED_FLAG_1" if sb["economics_recomputed"] else "CHANGED_ECON_RECOMPUTED_FLAG_0")] += 1
        c3[(tk[1], "CHANGED_THESIS_ID_DIFFERS" if sa["thesis_id"] != sb["thesis_id"] else "CHANGED_THESIS_ID_SAME")] += 1
        if len(examples) < 5:
            examples.append({"ticker_side": tk, "A": [sa["thesis_id"], sa["selected_contract_symbol"]],
                             "B": [sb["thesis_id"], sb["selected_contract_symbol"], sb["previous_contract_symbol"], sb["selection_reason"]]})
for tk, sb in fb.items():
    if tk not in la:
        c3[(tk[1], "ONLY_IN_B")] += 1
res["cross_run"] = c3
res["cross_run_examples"] = examples

# 4. within B multiple selection events per thesis
byth = defaultdict(list)
for s in sel:
    if s["run_id"] == B:
        byth[s["thesis_id"]].append(s)
c4 = Counter()
for th, ss in byth.items():
    sd = side_of(th)
    c4[(sd, f"events={min(len(ss),4)}")] += 1
    if len(ss) > 1:
        ss = sorted(ss, key=lambda x: (x["selection_version"], x["selected_at"]))
        for p, q in zip(ss, ss[1:]):
            samec = p["selected_contract_symbol"] == q["selected_contract_symbol"]
            sameo = p["selected_observation_id"] == q["selected_observation_id"]
            op, oq = obs.get(p["selected_observation_id"]) or {}, obs.get(q["selected_observation_id"]) or {}
            tag = ("SAMECONTRACT" if samec else "NEWCONTRACT") + ("_SAMEOBS" if sameo else "_NEWOBS")
            if samec and not sameo:
                tag += "_QUOTEASOF_" + ("SAME" if op.get("quote_as_of") == oq.get("quote_as_of") else "DIFF")
            if not samec:
                tag += "_PREVLINK_" + ("OK" if q["previous_contract_symbol"] == p["selected_contract_symbol"] else "BROKEN")
            c4[(sd, tag)] += 1
            c4[(sd, "reasons:" + p["selection_reason"] + ">" + q["selection_reason"])] += 1
res["within_B_sequences"] = c4

# 5. same provider quote under different observation ids
bykey = defaultdict(list)
for o in obs.values():
    bykey[(o["contract_symbol"], o["quote_as_of"])].append(o)
c5 = Counter()
FIELDS = ("spread_pct", "delta", "iv", "bid", "ask", "liquidity_state")
for k, os_ in bykey.items():
    if len(os_) < 2:
        continue
    sd = side_of(os_[0]["thesis_id"], os_[0]["option_side"])
    runs = {o["run_id"] for o in os_}
    c5[(sd, "MULTI_OBS_SAME_QUOTE_" + ("CROSS_RUN" if len(runs) > 1 else "SAME_RUN"))] += 1
    diff = [f for f in FIELDS if len({o[f] for o in os_}) > 1]
    if diff:
        c5[(sd, "FIELDS_DIFFER:" + ",".join(diff))] += 1
    if len({o["payload_hash"] for o in os_}) == 1 and diff:
        c5[(sd, "SAME_PAYLOAD_HASH_DIFFERENT_FIELDS")] += 1
res["same_quote_multi_obs"] = c5

# 6.
res["economics_recomputed_values"] = Counter(s["economics_recomputed"] for s in sel)
res["selection_supersedes_nonnull"] = sum(1 for s in sel if s["supersedes_event_id"])
res["observation_supersedes_nonnull"] = sum(1 for o in obs.values() if o["supersedes_event_id"])
res["observation_calculation_versions"] = Counter(o["calculation_version"] for o in obs.values())
# 7.
for t in ("doi_contract_assessments", "doi_outcome_labels"):
    try:
        res[t + "_rows"] = con.execute(f"select count(*) from {t}").fetchone()[0]
    except Exception as e:
        res[t + "_rows"] = str(e)

def ser(o):
    if isinstance(o, Counter):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): v for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
    return str(o)
def _conv(o):
    if isinstance(o, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): _conv(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_conv(x) for x in o]
    return o
json.dump(_conv(res), open(OUT / "p17_IN_nfr05_immutability.json", "w"), indent=1, default=ser)
with open(OUT / "p17_IN_nfr05_immutability.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["check", "direction", "metric", "n"])
    for tbl, cnt in res["rows"].items():
        for (run, sd), v in cnt.items():
            w.writerow(["rows:" + tbl, sd, run, v])
    for chk in ("selection_to_observation", "cross_run", "within_B_sequences", "same_quote_multi_obs"):
        for k, v in res[chk].items():
            k = k if isinstance(k, tuple) else (k,)
            w.writerow([chk, k[0], k[1], v])
print(json.dumps(_conv(res), indent=1, default=ser))
