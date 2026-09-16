"""p17 NFR-06: only a fill record creates a position episode — tested on ledger and journal copies (read-only).

Ledger: decision counts and fill counts as separate queries per run and direction; any decision/validation
payload carrying fill-like keys; OUTCOME events whose previous_event_id chains to a decision rather than a fill.
Journal: trades / closed_trades rows, source of each, whether a matching FILL_RECORDED exists in the ledger.
Output p17_IN_nfr06_fills.json / .csv.
"""
import csv, json, sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = ROOT / "audit/td/AVS-TD-001/probes"
L = sqlite3.connect(f"file:{(ROOT/'audit/td/AVS-TD-001/db_copies/decision_outcome_ledger.sqlite').as_posix()}?mode=ro", uri=True)
J = sqlite3.connect(f"file:{(ROOT/'audit/td/AVS-TD-001/db_copies/trade_journal.db').as_posix()}?mode=ro", uri=True)
L.row_factory = J.row_factory = sqlite3.Row
cols = [r[1] for r in L.execute("pragma table_info(ledger_events)")]
res = {"ledger_columns": cols}
def direction(payload):
    try:
        p = json.loads(payload or "{}")
    except Exception:
        return "OTHER", {}
    d = str(p.get("direction") or p.get("governed_direction") or "").upper()
    return ("CALL" if d == "CALL" else "PUT" if d == "PUT" else "OTHER"), p
DEC = ("CANDIDATE_DECISION", "VALIDATION", "EXECUTION_DECISION", "PRESENTATION_DECISION")
FILL = ("FILL_RECORDED",)
q_dec = Counter(); q_fill = Counter(); fill_like = Counter(); outcome_chain = Counter()
events = {}
for r in L.execute("select * from ledger_events"):
    r = dict(r)
    events[r["event_id"]] = r
for r in events.values():
    d, p = direction(r.get("payload_json"))
    if r["event_type"] in DEC:
        q_dec[(r["run_id"], r["event_type"], d)] += 1
        keys = [k for k in p if any(s in k.lower() for s in ("fill", "position", "episode", "entry_price", "filled", "quantity"))]
        if keys:
            fill_like[(r["event_type"], d, ",".join(sorted(keys))[:120])] += 1
    if r["event_type"] in FILL:
        q_fill[(r["run_id"], d)] += 1
    if r["event_type"] == "OUTCOME":
        prev = events.get(r.get("previous_event_id"))
        outcome_chain[(d, prev["event_type"] if prev else "NO_PREVIOUS", str(p.get("is_counterfactual")))] += 1
res["decision_counts_query"] = q_dec
res["fill_counts_query"] = q_fill
res["decision_payloads_with_fill_like_keys"] = fill_like
res["outcome_previous_event_type"] = outcome_chain
tj = {}
for t in ("trades", "closed_trades"):
    tc = [r[1] for r in J.execute(f"pragma table_info({t})")]
    rows = [dict(r) for r in J.execute(f"select * from {t}")]
    info = {"rows": len(rows), "source_column": [c for c in tc if "source" in c.lower()]}
    srcs = Counter(); per = []
    for r in rows:
        src = r.get("journal_entry_source")
        srcs[str(src)] += 1
        th = str(r.get("thesis_id") or r.get("trade_idea_id") or "")
        has_fill = bool(th) and L.execute("select count(*) from ledger_events where thesis_id=? and event_type='FILL_RECORDED'", (th,)).fetchone()[0] > 0 if "thesis_id" in cols else None
        per.append({"trade_id": r.get("trade_id"), "ticker": r.get("ticker"), "direction": r.get("direction") or "OTHER",
                    "run_id": r.get("run_id"), "journal_entry_source": src, "thesis_id": th, "ledger_fill_exists": has_fill,
                    "entry_date": r.get("entry_date"), "entry_premium": r.get("entry_premium"), "contracts": r.get("contracts")})
    info["sources"] = srcs; info["per_row"] = per
    tj[t] = info
res["trade_journal"] = tj
def ser(o):
    if isinstance(o, Counter):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): v for k, v in o.items()}
    return str(o)
def _conv(o):
    if isinstance(o, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): _conv(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_conv(x) for x in o]
    return o
json.dump(_conv(res), open(OUT / "p17_IN_nfr06_fills.json", "w"), indent=1, default=ser)
with open(OUT / "p17_IN_nfr06_fills.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["query", "run_id", "event_type", "direction", "n"])
    for (run, et, d), n in sorted(q_dec.items()):
        w.writerow(["decision", run, et, d, n])
    for (run, d), n in sorted(q_fill.items()):
        w.writerow(["fill", run, "FILL_RECORDED", d, n])
    for (d, pt, cf), n in outcome_chain.items():
        w.writerow(["outcome_previous", "", pt + "|counterfactual=" + cf, d, n])
    for r in tj["closed_trades"]["per_row"]:
        w.writerow(["journal_closed_trade", r["run_id"], str(r["journal_entry_source"]), r["direction"], 1])
print(json.dumps(_conv(res), indent=1, default=ser))
