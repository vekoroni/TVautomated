"""p15_F_03b: which node the unanchored _find() in domain/macro_advisory_context.py:13-26 resolves on the stored macro_snapshot.json
for 'routing', 'scenarios' and each scenario metric; compared with the observed value path. Also USMI metric evidence flags."""
import sys, json
sys.dont_write_bytecode = True
from pathlib import Path
ROOT=Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); sys.path.insert(0,str(ROOT)); R=ROOT/"data/output/runs/20260911_115904"; OUT=ROOT/"audit/td/AVS-TD-001/probes"
from domain.macro_advisory_context import _find
snap=json.loads((R/"macro_snapshot.json").read_text(encoding="utf-8-sig"))
def path_of(node,key,path="$"):
    if isinstance(node,dict):
        if key in node: return path+"."+key
        for k,c in node.items():
            r=path_of(c,key,path+"."+k)
            if r: return r
    elif isinstance(node,list):
        for i,c in enumerate(node):
            r=path_of(c,key,f"{path}[{i}]")
            if r: return r
    return None
res={}
for k in ["routing","scenarios","cpi_core_mom_pct","cpi_headline_mom_pct","us_10y_pct","vix","hyg_close","hy_oas_pct","fed_hike_probability_pct","cash_session_breadth"]:
    v=_find(snap,k); res[k]={"find_path":path_of(snap,k),"find_value":(json.dumps(v)[:80] if v is not None else None)}
ca=snap["extras"]["us_money_index"]["source_payload"]["cross_asset"]
res["observed_values"]={"us_10y_pct":ca["rates"].get("us_10y_pct"),"vix_spot":ca["volatility"].get("vix_spot"),"hyg_close":ca["credit"].get("hyg_close"),"hy_oas_pct":ca["credit"].get("hy_oas_pct")}
m=snap["extras"]["us_money_index"].get("metrics") or {}
res["usmi_metrics_n"]=len(m); res["usmi_metrics_usable_for_calculation_true"]=sum(1 for x in m.values() if isinstance(x,dict) and x.get("usable_for_calculation") is True)
res["usmi_metrics_evidence_status"]=sorted({x.get("evidence_status") for x in m.values() if isinstance(x,dict)})
(OUT/"p15_F_03b_find_paths.json").write_text(json.dumps(res,indent=1,default=str),encoding="utf-8")
print(json.dumps(res,indent=1,default=str))
