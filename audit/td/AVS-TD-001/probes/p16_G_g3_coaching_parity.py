"""p16_G_g3_coaching_parity.py -- Track G / G3 (REQ-WP6-03 coaching parity).  READ-ONLY, regenerates nothing.

Compares 20 sampled coaching values (random.seed(20260912)) against lab_signal_book_v3.csv for run
20260911_115904.  Coaching sources read as stored:
  DOSSIER_MD : dropbox/macro/coaching/trade_edge_dossiers_20260911_115904.md   (build_trade_dossiers.py output)
  DESK_MORN  : dropbox/macro/coaching/desk_gate/desk_gate_20260911_115904_morning.csv (desk_gate.py overlay, 19 rows)
  CORE_INTEL : data/output/runs/20260911_115904/core_intel/core_intel_dossiers_20260911_115904.json
Fields (REQ list): structural_target, invalidation, direction, preferred contract, ask, spread, expected move, verdict.
Equality = exact string equality OR exact float equality after float() of both sides (no tolerance).
Outputs p16_G_g3_coaching_parity.json and .csv beside this file.
"""
from __future__ import annotations
import csv, json, random, re
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUN = "20260911_115904"
R = ROOT / "data/output/runs" / RUN
C = ROOT / "dropbox/macro/coaching"
OUT = Path(__file__).with_suffix(".json")
csv.field_size_limit(1 << 30)

lab = {r["ticker"]: r for r in csv.DictReader((R / "intelligence_lab/lab_signal_book_v3.csv").open(encoding="utf-8-sig", newline=""))}
desk = {r["ticker"]: r for r in csv.DictReader((C / "desk_gate/desk_gate_20260911_115904_morning.csv").open(encoding="utf-8-sig", newline=""))}
ci_doc = json.loads((R / f"core_intel/core_intel_dossiers_{RUN}.json").read_text(encoding="utf-8"))
ci = {d["ticker"]: d for d in ci_doc["dossiers"]}
md = (C / f"trade_edge_dossiers_{RUN}.md").read_text(encoding="utf-8")

# ---- parse the dossier markdown: "The trade as the pipeline states it." line per ticker section ----
LINE = re.compile(r"### (?P<t>[A-Z0-9.\-]+) — (?P<dir>CALL|PUT|[A-Z_]+) — .*?\*\*The trade as the pipeline states it\.\*\* "
                  r"(?P<dir2>CALL|PUT|[A-Z_]+) (?P<contract>\S+) at mid (?P<mid>[-\d.]+) \(ask (?P<ask>[-\d.]+)\), underlying (?P<u>[-\d.]+), "
                  r"invalidation (?P<inv>[-\d.]+), target (?P<tgt>[-\d.]+), DTE (?P<dte>[-\d.]+), delta (?P<delta>[-\d.]+), "
                  r"final action (?P<fa>[A-Z_]+), Morning permission (?P<mp>[A-Z_]+)\.", re.S)
BRIEF = re.compile(r"^\| \d+ \| (?P<t>[A-Z0-9.\-]+) \| (?P<dir>\w+) \| .*? \| (?P<tg>[\d.]+)× \| (?P<wp>[\d.]+) \| (?P<sp>[\d.]+)% \| (?P<ivhv>[\d.]+) \| (?P<th>[\d.]+)% \| (?P<v>[^|]+) \|$", re.M)
MARKET = re.compile(r"### (?P<t>[A-Z0-9.\-]+) — .*?GARCH expected move (?P<m15>[-\d.]+)% / (?P<m610>[-\d.]+)% / (?P<m1120>[-\d.]+)%", re.S)
dmd = {}
for m in LINE.finditer(md):
    dmd[m["t"]] = {"direction": m["dir2"], "contract_symbol": m["contract"], "contract_mid": m["mid"], "contract_ask": m["ask"],
                   "invalidation_price": m["inv"], "structural_target": m["tgt"], "final_action": m["fa"], "morning_execution_permission": m["mp"]}
for m in BRIEF.finditer(md):
    dmd.setdefault(m["t"], {})["spread_pct"] = m["sp"]
for m in MARKET.finditer(md):
    dmd.setdefault(m["t"], {})["garch_expected_move_6_10d"] = m["m610"]
    dmd[m["t"]]["garch_expected_move_1_5d"] = m["m15"]

# ---- field map: (REQ field, lab column, {source: (getter)}) ----
def hold_move_col(r):  # expected move for the row's hold window
    hw = (r.get("hold_window") or "").strip()
    return {"1_5d": "garch_expected_move_1_5d", "6_10d": "garch_expected_move_6_10d", "11_20d": "garch_expected_move_11_20d"}.get(hw, "garch_expected_move_6_10d")
FIELDS = {
    "structural_target": {"lab": "structural_target", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("structural_target"), "DESK_MORN": lambda t: desk.get(t, {}).get("target_price")},
    "invalidation": {"lab": "invalidation_price", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("invalidation_price"), "DESK_MORN": lambda t: desk.get(t, {}).get("invalidation_price")},
    "direction": {"lab": "final_direction", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("direction"), "DESK_MORN": lambda t: desk.get(t, {}).get("direction"), "CORE_INTEL": lambda t: ci.get(t, {}).get("opt__options_direction")},
    "preferred_contract": {"lab": "contract_symbol", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("contract_symbol"), "DESK_MORN": lambda t: desk.get(t, {}).get("contract_symbol"), "CORE_INTEL": lambda t: ci.get(t, {}).get("opt__recommended_contract")},
    "ask": {"lab": "contract_ask", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("contract_ask"), "DESK_MORN": lambda t: desk.get(t, {}).get("contract_ask")},
    "spread": {"lab": "spread_pct", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("spread_pct"), "DESK_MORN": lambda t: desk.get(t, {}).get("spread_pct")},
    "expected_move": {"lab": "garch_expected_move_6_10d", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("garch_expected_move_6_10d"), "DESK_MORN": lambda t: desk.get(t, {}).get("garch_expected_move_6_10d")},
    "verdict": {"lab": "lab_verdict", "DOSSIER_MD": lambda t: dmd.get(t, {}).get("morning_execution_permission"), "DESK_MORN": lambda t: desk.get(t, {}).get("lab_verdict")},
}
universe = [(t, f, s) for t in sorted(lab) for f, spec in FIELDS.items() for s in ("DOSSIER_MD", "DESK_MORN", "CORE_INTEL") if s in spec]
random.seed(20260912)
picks = random.sample(universe, 20)

def eq(a, b):
    if a is None or b is None:
        return False
    a, b = str(a).strip(), str(b).strip()
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False

rows = []
for t, f, s in picks:
    labv = lab[t].get(FIELDS[f]["lab"])
    cv = FIELDS[f][s](t)
    d = lab[t].get("final_direction") or "OTHER"
    rows.append({"ticker": t, "direction": d if d in ("CALL", "PUT") else "OTHER", "field": f, "lab_column": FIELDS[f]["lab"], "lab_value": labv,
                 "coaching_source": s, "coaching_value": cv, "equal": eq(labv, cv),
                 "note": ("verdict vocabularies differ (lab_verdict vs morning_execution_permission)" if f == "verdict" and s == "DOSSIER_MD" else "")})
# full-population parity per field/source (all 19 tickers) as context
full = {}
for f, spec in FIELDS.items():
    for s in ("DOSSIER_MD", "DESK_MORN", "CORE_INTEL"):
        if s not in spec:
            continue
        cnt = {"CALL": [0, 0], "PUT": [0, 0], "OTHER": [0, 0]}
        for t in lab:
            d = lab[t].get("final_direction"); d = d if d in ("CALL", "PUT") else "OTHER"
            cnt[d][1] += 1; cnt[d][0] += int(eq(lab[t].get(spec["lab"]), spec[s](t)))
        full[f"{f}|{s}"] = {k: f"{v[0]}/{v[1]}" for k, v in cnt.items() if v[1]}
res = {"run": RUN, "lab_rows": len(lab), "desk_morning_rows": len(desk), "core_intel_dossiers": len(ci), "dossier_md_sections_parsed": len(dmd),
       "core_intel_meta": ci_doc.get("meta"), "sample_20": rows, "sample_equal": sum(r["equal"] for r in rows),
       "sample_by_dir": {d: {"n": sum(1 for r in rows if r["direction"] == d), "equal": sum(1 for r in rows if r["direction"] == d and r["equal"])} for d in ("CALL", "PUT", "OTHER")},
       "full_population_parity": full,
       "core_intel_ticker_coverage_of_lab": sum(1 for t in lab if t in ci), "desk_morning_coverage_of_lab": sum(1 for t in lab if t in desk)}
OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
with Path(__file__).with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(json.dumps({k: v for k, v in res.items() if k != "sample_20"}, indent=1, default=str))
for r in rows:
    print(f"{'OK ' if r['equal'] else 'DIFF'} {r['ticker']:5} {r['direction']:4} {r['field']:18} {r['coaching_source']:10} lab={r['lab_value']!r} coaching={r['coaching_value']!r} {r['note']}")
