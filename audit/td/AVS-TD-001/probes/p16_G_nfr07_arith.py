"""p16_G_nfr07_arith.py -- Track G / NFR-07 + REQ-WP6-01 (no arithmetic and no capital field in the Lab
projector).  READ-ONLY.  AST scan of contracts/lab_control.py opportunity_book_row (+ helpers it calls in the
same module that touch numeric domain fields), domain/lab_signal_book_v4.py and domain/presentation.py for
BinOp (+ - * / // % **), AugAssign, and calls to round/abs/max/min/float-arith on price/return/spread-like
names.  Also greps the v4 field list and FINAL_BOOK_FIELDS for capital-allocation fields.
Outputs p16_G_nfr07_arith.json beside this file.
"""
from __future__ import annotations
import ast, json, re, sys
from pathlib import Path

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
OUT = Path(__file__).with_suffix(".json")
sys.path.insert(0, str(ROOT))
DOMAIN_RE = re.compile(r"price|spread|mid|bid|ask|premium|return|move|target|invalidation|stop|strike|iv|hv|vol|delta|theta|gamma|vega|ev|edge|pct|ratio|score|rr|win|prob|payoff|dte|runway|budget|cost", re.I)
OPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**"}

def scan(path: Path, func_names: set[str] | None):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    hits = []
    def walk_func(fn: ast.FunctionDef):
        for node in ast.walk(fn):
            txt = None
            if isinstance(node, ast.BinOp) and type(node.op) in OPS:
                seg = ast.get_source_segment(src, node) or ""
                # skip string concatenation / f-string joins
                if isinstance(node.left, (ast.Constant, ast.JoinedStr)) and isinstance(getattr(node.left, "value", None), str):
                    continue
                if isinstance(node.right, (ast.Constant, ast.JoinedStr)) and isinstance(getattr(node.right, "value", None), str):
                    continue
                txt = f"BinOp {OPS[type(node.op)]}: {seg[:110]}"
            elif isinstance(node, ast.AugAssign) and type(node.op) in OPS:
                txt = f"AugAssign {OPS[type(node.op)]}=: {(ast.get_source_segment(src, node) or '')[:110]}"
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("round", "abs", "max", "min", "sum", "pow"):
                txt = f"Call {node.func.id}(): {(ast.get_source_segment(src, node) or '')[:110]}"
            if txt:
                domain = bool(DOMAIN_RE.search(txt))
                hits.append({"file": str(path.relative_to(ROOT)), "line": node.lineno, "func": fn.name, "hit": txt, "domain_like_name": domain,
                             "source": lines[node.lineno - 1].strip()[:140]})
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and (func_names is None or node.name in func_names):
            walk_func(node)
    return hits

# opportunity_book_row and every module-level helper it calls (one level) that is defined in lab_control
lc = ROOT / "contracts/lab_control.py"
src = lc.read_text(encoding="utf-8"); tree = ast.parse(src)
defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
obr = defs["opportunity_book_row"]
called = {n.func.id for n in ast.walk(obr) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in defs}
scope = {"opportunity_book_row"} | called
res = {"opportunity_book_row_lines": (obr.lineno, obr.end_lineno), "helpers_called_from_opportunity_book_row_in_scope": sorted(called)}
hits_obr = scan(lc, {"opportunity_book_row"})
hits_helpers = scan(lc, called)
hits_v4 = scan(ROOT / "domain/lab_signal_book_v4.py", None)
hits_pres = scan(ROOT / "domain/presentation.py", None)
res["opportunity_book_row_hits"] = hits_obr
res["helper_hits"] = hits_helpers
res["lab_signal_book_v4_hits"] = hits_v4
res["presentation_hits"] = hits_pres
res["counts"] = {"opportunity_book_row_all": len(hits_obr), "opportunity_book_row_domain_like": sum(h["domain_like_name"] for h in hits_obr),
                 "helpers_all": len(hits_helpers), "helpers_domain_like": sum(h["domain_like_name"] for h in hits_helpers),
                 "v4": len(hits_v4), "presentation": len(hits_pres)}
# capital-allocation fields
from domain.lab_signal_book_v4 import project_lab_signal_v4  # noqa: E402
from contracts.lab_control import FINAL_BOOK_FIELDS, LAB_REQUIRED_FIELDS  # noqa: E402
CAP = re.compile(r"capacity_|contracts_at_budget|sb_size_pct|position_size|size_pct|risk_budget|budget_", re.I)
v4_fields = list(project_lab_signal_v4({}).keys())
res["v4_field_list"] = v4_fields
res["v4_capital_fields"] = [f for f in v4_fields if CAP.search(f)]
res["FINAL_BOOK_FIELDS_capital_like"] = [f for f in FINAL_BOOK_FIELDS if CAP.search(f)]
res["lab_control_source_capital_tokens"] = {tok: len(re.findall(tok, src)) for tok in ("capacity_", "contracts_at_budget", "sb_size_pct", "position_size_display", "sb_position_size")}
ui = (ROOT / "intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8")
res["ui_source_capital_tokens"] = {tok: len(re.findall(tok, ui)) for tok in ("capacity_", "contracts_at_budget", "sb_size_pct", "sb_position_size_pct", "position_size_display")}
# v4 required content check (REQ-WP6-01 list) -- which named elements the projector emits
REQ_ELEMENTS = {"thesis_state": "lab_v4_thesis_state", "structure_evidence": "lab_v4_structure_evidence_state", "reach_ratio": "lab_v4_reach_ratio",
                "p_with_source_and_n_or_UNCALIBRATED": None, "scenario_payoffs": None, "monetisability_state": "lab_v4_contract_state", "spread": None,
                "iv_vs_forecast": None, "theta": None, "lifecycle_state": None, "quote_provider_timestamp": "lab_v4_quote_provider_timestamp_utc",
                "refresh_state": None, "macro_alignment": "lab_v4_macro_alignment", "macro_scenario": "lab_v4_macro_scenario", "macro_route": None,
                "what_changed_since_prior_assessment": None}
res["req_wp6_01_elements_present_in_v4"] = {k: (v in v4_fields if v else False) for k, v in REQ_ELEMENTS.items()}
OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("opportunity_book_row_lines", "helpers_called_from_opportunity_book_row_in_scope", "counts", "v4_field_list", "v4_capital_fields", "FINAL_BOOK_FIELDS_capital_like", "lab_control_source_capital_tokens", "ui_source_capital_tokens", "req_wp6_01_elements_present_in_v4")}, indent=1))
for h in hits_obr:
    print(f"OBR {h['file']}:{h['line']} [{'DOMAIN' if h['domain_like_name'] else 'other'}] {h['hit']}")
for h in hits_helpers:
    print(f"HELPER {h['file']}:{h['line']} {h['func']} [{'DOMAIN' if h['domain_like_name'] else 'other'}] {h['hit']}")
for h in hits_v4 + hits_pres:
    print(f"V4/PRES {h['file']}:{h['line']} {h['hit']}")
