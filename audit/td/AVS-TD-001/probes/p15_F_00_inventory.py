"""p15_F_00: read-only inventory for Track F. Columns of interest per artefact, packet paths, package keys, reference sector sources."""
import json, csv, glob, re, sys
from pathlib import Path
import pandas as pd
ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); RUN = "20260911_115904"; R = ROOT/"data/output/runs"/RUN
OUT = ROOT/"audit/td/AVS-TD-001/probes"
arts = {
 "final_opportunity_book": R/f"intelligence_lab/final_opportunity_book_{RUN}.csv",
 "lab_triage_view": R/f"intelligence_lab/lab_triage_view_{RUN}.csv",
 "lab_signal_book_v3": R/"intelligence_lab/lab_signal_book_v3.csv",
 "morning_validated_trades": R/f"morning_validation/morning_validated_trades_{RUN}.csv",
 "morning_candidates": R/f"morning_validation/morning_candidates_{RUN}.csv",
 "execution_gated": R/f"trades/execution_gated_{RUN}.csv",
 "execution_actionable": R/f"trades/execution_actionable_{RUN}.csv",
}
pat = re.compile(r"usmi|macro|gics|sector|industry|contracts_at_budget|capacity|budget|structure_evidence|sb_size|position_size|suggested_contracts|affordab|account_size|contract_ask|governed_direction|^direction$|lab_verdict|morning_execution_permission|hidden_state|^phase$|trigger_primary|regime|opportunity_tier|horizon_cap|direction_factor", re.I)
res = {}
for name, p in arts.items():
    try:
        cols = list(pd.read_csv(p, nrows=0).columns)
    except Exception as e:
        res[name] = {"error": str(e)}; continue
    res[name] = {"n_cols": len(cols), "matched": [c for c in cols if pat.search(c)]}
    print(f"== {name} ({len(cols)} cols): ", res[name]["matched"])
# packet paths
def walk(node, path, key_pred, hits, depth=0):
    if depth > 12: return
    if isinstance(node, dict):
        for k, v in node.items():
            if key_pred(k): hits.append(path + "." + k)
            walk(v, path + "." + k, key_pred, hits, depth+1)
    elif isinstance(node, list):
        for i, v in enumerate(node[:50]):
            walk(v, f"{path}[{i}]", key_pred, hits, depth+1)
for fn in ["macro_snapshot.json", "macro_quant_packet.json", "interpreter/interpreter_macro_context.json"]:
    d = json.loads((R/fn).read_text(encoding="utf-8-sig"))
    hits = []
    walk(d, "$", lambda k: k in {"routing", "sector_routing", "scenarios", "conditions_all", "forward_triggers", "observed_metrics", "observed", "metrics", "options_monetisation", "long_call_priority", "long_put_priority", "us_money_index", "source_payload", "usmi_routing_key"}, hits)
    print(f"== {fn} top keys: {list(d.keys())[:40]}")
    print(f"   paths: {hits[:60]}")
    res[fn] = {"top_keys": list(d.keys()), "paths": hits}
# one package file
pk = sorted((R/"packages").glob("*.package.json"))[0]
d = json.loads(pk.read_text(encoding="utf-8-sig"))
hits = []; walk(d, "$", lambda k: re.search(r"gics|sector|industry", k, re.I) is not None, hits)
print("== package", pk.name, "top keys", list(d.keys())[:30]); print("   sector-ish paths:", hits[:40])
res["package_example"] = {"file": pk.name, "top_keys": list(d.keys()), "paths": hits[:80]}
# universe / reference
for u in sorted((ROOT/"data/universe").glob("*.csv")):
    cols = list(pd.read_csv(u, nrows=0).columns); print("== universe", u.name, cols[:40]); res["universe:"+u.name] = cols
src = (ROOT/"canonical_data/contract_reference.py").read_text(encoding="utf-8", errors="replace")
print("== contract_reference.py mentions sector/gics:", [m.start() for m in re.finditer(r"gics|sector", src, re.I)][:10], "len", len(src))
(OUT/"p15_F_00_inventory.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
