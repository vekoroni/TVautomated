"""Check zero premium change by reprice source (reads p25_M5_repeats.csv only). RESEARCH_ONLY."""
import os, pandas as pd
H = os.path.dirname(os.path.abspath(__file__))
R = pd.read_csv(os.path.join(H, "p25_M5_repeats.csv"), low_memory=False)
X = R[R.premium_td.notna() & (R.premium_t > 0)].copy()
X["src"] = X.src_t + ">" + X.src_td
X["zero"] = X.delta_premium_total.abs() < 1e-9
X["era"] = X.session_basis_t
g = X.groupby(["src", "era"]).agg(n=("zero", "size"), zero_share=("zero", "mean"))
print(g.round(3))
C = X[(X.src == "chain>chain")]
print("chain>chain by d x dir3")
for c in ["delta_premium_total", "theta_component", "IV_component", "move_component", "residual"]:
    C[c + "_pct"] = C[c] / C.premium_t * 100
print(C.groupby(["d", "dir3"])[["delta_premium_total_pct", "theta_component_pct", "IV_component_pct", "move_component_pct", "residual_pct"]].median().round(2).join(C.groupby(["d", "dir3"]).size().rename("n")))
print(C.groupby(["d"]).agg(n=("ticker","size"), sessions=("session_t", lambda s: sorted(set(s)))).to_string())
out = X.groupby(["src", "era", "d", "dir3"]).agg(n=("zero", "size"), zero_share=("zero", "mean")).reset_index()
out.to_csv(os.path.join(H, "p25_M5_repeats_srccheck.csv"), index=False)
