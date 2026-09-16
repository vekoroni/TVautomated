"""p15_F_03: scenario evaluator. Independent evaluation of packet forward_triggers.scenarios.*.conditions_all (free-text clauses)
against observed values in the same packet; compare to stored usmi_scenario / failed_clause; run both production evaluators on the
stored packet; run the REQ-WP5-02 fixture (CPI m/m 0.4, 10Y 4.95; and missing metric) through both production evaluators."""
import sys, json, re
sys.dont_write_bytecode = True
from pathlib import Path
import pandas as pd
ROOT=Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"); sys.path.insert(0,str(ROOT)); RUN="20260911_115904"; R=ROOT/"data/output/runs"/RUN; OUT=ROOT/"audit/td/AVS-TD-001/probes"
from macro_domain.us_money_index import evaluate_scenarios
from domain.macro_advisory_context import project_usmi_context
snap=json.loads((R/"macro_snapshot.json").read_text(encoding="utf-8-sig")); u=snap["extras"]["us_money_index"]; sp=u["source_payload"]
scen=sp["forward_triggers"]["scenarios"]
ca=sp["cross_asset"]
# observed values with their timestamps as present in the packet (None = metric not observed in packet)
obs={
 "cpi_core_mom_pct":(None,None),"cpi_headline_mom_pct":(None,None),
 "us_10y_pct":(ca["rates"].get("us_10y_pct"), ca["rates"].get("as_of") or ca["rates"].get("date") or u.get("market_data_as_of_utc")),
 "vix":(ca["volatility"].get("vix_spot"), ca["volatility"].get("vix_date")),
 "hyg_close":(ca["credit"].get("hyg_close"), ca["credit"].get("hyg_close_date")),
 "hy_oas_pct":(ca["credit"].get("hy_oas_pct"), ca["credit"].get("as_of") or ca["credit"].get("date")),
 "cash_session_breadth":(None,None),"fed_hike_probability_pct":(None,None),
}
def val(v):
    try: return float(v)
    except: return None
def atom(txt):
    t=txt.strip()
    m=re.match(r"^(\w+)\s+in\s+([\[\(])\s*([\d.]+)\s*,\s*([\d.]+)\s*([\]\)])$",t)
    if m:
        k,lo_b,lo,hi,hi_b=m.groups(); x=val(obs.get(k,(None,))[0])
        if x is None: return None,k
        ok=(x>=float(lo) if lo_b=="[" else x>float(lo)) and (x<=float(hi) if hi_b=="]" else x<float(hi)); return ok,k
    m=re.match(r"^(\w+)\s*(>=|<=|>|<|=)\s*([\d.]+)$",t)
    if m:
        k,op,v=m.groups(); x=val(obs.get(k,(None,))[0])
        if x is None: return None,k
        return {">=":x>=float(v),"<=":x<=float(v),">":x>float(v),"<":x<float(v),"=":x==float(v)}[op],k
    m=re.match(r"^(\w+)\s+([A-Z_]+)$",t)
    if m:
        k,state=m.groups(); x=obs.get(k,(None,))[0]
        if x is None: return None,k
        return str(x).upper()==state,k
    return None,"UNPARSEABLE:"+t
def clause(txt):
    parts=[p for p in re.split(r"\s+OR\s+",txt)]
    res=[atom(p) for p in parts]
    if any(r[0] is True for r in res): return True,None
    missing=[r[1] for r in res if r[0] is None]
    if missing: return None,missing
    return False,None
out=[]; sat=[]; first_unres=None
for sid,sd in scen.items():
    if not isinstance(sd,dict): continue
    status="SATISFIED"; detail=""
    for c in sd["conditions_all"]:
        ok,miss=clause(c)
        out.append({"scenario":sid,"clause":c,"result":ok,"missing":miss,"observed":{k:obs[k] for k in obs if k in c}})
        if ok is False and status=="SATISFIED": status="FAILED"; detail=c
        if ok is None and status=="SATISFIED": status="UNRESOLVED_MISSING"; detail=f"{c} missing {miss}"
    if status=="SATISFIED": sat.append(sid)
    out.append({"scenario":sid,"clause":"<SCENARIO>","result":status,"missing":detail,"observed":""})
pd.DataFrame(out).to_csv(OUT/"p15_F_03_scenario_clauses.csv",index=False)
tester = sat[0] if len(sat)==1 else ("MULTIPLE" if sat else "UNRESOLVED")
book=pd.read_csv(R/f"intelligence_lab/final_opportunity_book_{RUN}.csv", dtype=str, keep_default_na=False, usecols=lambda c: c in {"governed_direction","usmi_scenario","usmi_scenario_failed_clause","failed_clause"})
book["_dir"]=book["governed_direction"].str.upper().where(book["governed_direction"].str.upper().isin(["CALL","PUT"]),"OTHER")
stored={d:book.loc[book["_dir"]==d,"usmi_scenario"].value_counts().to_dict() for d in ("CALL","PUT","OTHER")}
ipkt=json.loads((R/"interpreter/interpreter_macro_context.json").read_text(encoding="utf-8-sig"))
prod_j1_stored=ipkt.get("us_money_index_scenario")
prod_j1_on_source=evaluate_scenarios(scen, {k:v[0] for k,v in obs.items() if v[0] is not None})
prod_j2_on_snapshot=project_usmi_context(packet=snap, sector="Energy", industry="", direction="CALL")
# REQ fixture: ALG-14 structured shape
fix_scen=[{"id":"A","conditions_all":[{"metric":"cpi_mom","op":">=","value":0.4},{"metric":"us_10y","op":">=","value":4.9}]},
          {"id":"B","conditions_all":[{"metric":"cpi_mom","op":"<","value":0.4},{"metric":"us_10y","op":"<","value":4.9}]},
          {"id":"C","conditions_all":[{"metric":"cpi_mom","op":"<=","value":0.2}]}]
fx_ok={"forward_triggers":{"scenarios":fix_scen},"observed":{"cpi_mom":0.4,"us_10y":4.95}}
fx_missing={"forward_triggers":{"scenarios":fix_scen},"observed":{"us_10y":4.95}}
j2_fx_ok=project_usmi_context(packet=fx_ok, sector="Energy", industry="", direction="CALL")
j2_fx_missing=project_usmi_context(packet=fx_missing, sector="Energy", industry="", direction="CALL")
j1_fx_ok=evaluate_scenarios({s["id"]:{"conditions_all":s["conditions_all"]} for s in fix_scen},{"cpi_mom":0.4,"us_10y":4.95})
j1_fx_dictshape=evaluate_scenarios({"A":{"all":[{"cpi_mom_gte":0.4},{"us_10y_gte":4.9}]},"B":{"all":[{"cpi_mom_lt":0.4}]}},{"cpi_mom":0.4,"us_10y":4.95})
j1_fx_missing=evaluate_scenarios({"A":{"all":[{"cpi_mom_gte":0.4},{"us_10y_gte":4.9}]},"B":{"all":[{"cpi_mom_lt":0.4}]}},{"us_10y":4.95})
res={"packet_scenario_ids":[k for k in scen if isinstance(scen[k],dict)],"conditions_all_type":type(scen["A_HOT_CPI_ESCALATION"]["conditions_all"][0]).__name__,
 "observed_used":obs,"tester_satisfied":sat,"tester_result":tester,
 "tester_first_failed_or_missing":{r["scenario"]:r["missing"] for r in out if r["clause"]=="<SCENARIO>"},
 "stored_usmi_scenario_by_dir":stored,"stored_failed_clause_field_present":any(c in book.columns for c in ("usmi_scenario_failed_clause","failed_clause")),
 "normalised_usmi_scenarios(us_money_index_contract.py:424)":ipkt["us_money_index"].get("scenarios"),
 "prod_join1_stored_interpreter_packet":prod_j1_stored,"prod_join1_evaluate_scenarios_on_source_scenarios":prod_j1_on_source,
 "prod_join2_on_snapshot":{k:prod_j2_on_snapshot[k] for k in ("usmi_scenario","usmi_scenario_failed_clause")},
 "fixture_join2_ok":{k:j2_fx_ok[k] for k in ("usmi_scenario","usmi_scenario_failed_clause")},
 "fixture_join2_missing_metric":{k:j2_fx_missing[k] for k in ("usmi_scenario","usmi_scenario_failed_clause")},
 "fixture_join1_alg14_shape":j1_fx_ok,"fixture_join1_suffix_shape":j1_fx_dictshape,"fixture_join1_missing_metric":j1_fx_missing}
(OUT/"p15_F_03_scenario_summary.json").write_text(json.dumps(res,indent=1,default=str),encoding="utf-8")
print(json.dumps(res,indent=1,default=str))
