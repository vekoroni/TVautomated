"""Tabulate beh001_eval_v2 output: pooled lines, population split, and estimable types."""
import json
import sys

import pandas as pd

d = json.load(open(sys.argv[1], encoding="utf-8"))
KEY_H = {"1d": ("h20", "h60", "h250"), "1w": ("h13", "h52", "h104"), "1mo": ("h6", "h12", "h24")}
rows = []
for g in d["groups"]:
    for h in KEY_H[g["tf"]]:
        if h not in g:
            continue
        v = g[h]
        rows.append({"test": g["test"], "tf": g["tf"], "scope": g["scope"], "type": g["type"], "dir": g["dir"],
                     "pop": g["population"], "n": g["n"], "scorable": g["scorable"], "not_scor": g["not_scorable"],
                     "cens": g["censored"], "amb": g["ambiguous"], "blocks": g["blocks"], "est": g["estimability"][:3],
                     "h": h, "obs": v["target_obs"], "base": v["target_base"], "excess": v["excess"],
                     "lo": v["excess_lo"], "hi": v["excess_hi"], "stop_obs": v["stop_obs"], "stop_base": v["stop_base"]})
t = pd.DataFrame(rows)
pd.set_option("display.width", 260, "display.max_rows", 500, "display.max_colwidth", 40)
print("META", d["meta"])
print("\n== POOLED (all types), by direction and population ==")
pooled = t[(t.scope == "*")].sort_values(["test", "tf", "dir", "pop", "h"])
print(pooled.drop(columns=["scope", "type"]).to_string(index=False))
print("\n== TYPE LEVEL, ESTIMABLE, longest horizon ==")
last = {tf: hs[-1] for tf, hs in KEY_H.items()}
typ = t[(t.scope != "*") & (t.est == "EST") & (t.h == t.tf.map(last))].sort_values(["test", "tf", "excess"])
print(typ.drop(columns=["pop", "est"]).to_string(index=False))
sig = typ[(typ.lo > 0) | (typ.hi < 0)]
print(f"\nType-level groups with interval excluding zero: {len(sig)} of {len(typ)}")
print(sig[["test", "tf", "scope", "type", "dir", "scorable", "excess", "lo", "hi"]].to_string(index=False))
