"""p22 - Track M9: collapse fallback alias chains in the six named decision readers (read-only).

Parses the readers with `ast` and collects every call to a first-non-empty helper
(_first_value, _first, _first_text, _first_number, _first_present, _coalesce, _pick) whose
arguments are string constants; each such call is one LOGICAL input with N alias field names.
Writes p22_M9_alias_chains.csv and prints the de-aliased size of the p21 CORE set.
"""
import ast, os, re, sys
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.dirname(os.path.abspath(__file__))
READERS = ["execution_gate.py", "morning_gate.py", "contracts/opportunity_tier.py", "contracts/lab_control.py",
           "eod_candidate_engine.py", "orchestrator/dynamic_dispatcher.py"]
HELPERS = {"_first_value", "_first", "_first_text", "_first_number", "_first_present", "_coalesce", "_pick", "_first_non_empty", "_first_nonempty"}
rows = []
for rel in READERS:
    src = open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore").read().lstrip("﻿")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if name in HELPERS:
                keys = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                if len(keys) >= 2:
                    rows.append(dict(reader=rel, line=node.lineno, helper=name, n_aliases=len(keys), aliases=";".join(keys)))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, "p22_M9_alias_chains.csv"), index=False)
print(f"alias-chain call sites: {len(df)} in {df.reader.nunique() if len(df) else 0} readers; helpers used: {df.helper.value_counts().to_dict() if len(df) else {}}")
# union-find over alias groups
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
for al in df.aliases:
    ks = al.split(";")
    for k in ks[1:]:
        union(ks[0], k)
core = pd.read_csv(os.path.join(OUT, "p21_M9_minset_decision_fields.csv"))
core = core[(core.tier == "CORE") & core.in_row_level_artefact]
groups = {}
for f in core.field:
    groups.setdefault(find(f) if f in parent else f, []).append(f)
n_logical = len(groups)
multi = {k: v for k, v in groups.items() if len(v) > 1}
print(f"CORE fields: {len(core)}; logical inputs after collapsing alias chains: {n_logical}; alias groups with >1 CORE member: {len(multi)}")
for k, v in sorted(multi.items(), key=lambda kv: -len(kv[1])):
    print(f"  group[{len(v)}]: {', '.join(sorted(v))}")
lab = core[core.in_lab_book]
lab_groups = {}
for f in lab.field:
    lab_groups.setdefault(find(f) if f in parent else f, []).append(f)
print(f"CORE fields present in lab book: {len(lab)}; logical inputs: {len(lab_groups)}")
pd.DataFrame([dict(group_root=k, n=len(v), members=";".join(sorted(v))) for k, v in groups.items()]).sort_values("n", ascending=False).to_csv(os.path.join(OUT, "p22_M9_core_logical_inputs.csv"), index=False)
