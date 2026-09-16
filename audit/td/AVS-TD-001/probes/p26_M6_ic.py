"""M6 step 5 - information coefficient on retrospective outcomes and effective breadth after each gate. RESEARCH_ONLY. Read-only.
IC: Spearman(score, dir_ret_sig) and Spearman(score, hit_sym) on reconstructable directed rows, pooled across runs, per direction, for the
population before a gate and for its survivors. n<100 -> INSUFFICIENT_POWER.
Breadth per run: survivors after each successive gate, distinct tickers, and N_eff = n / (1 + (n-1)*rho_bar), rho_bar = average pairwise
correlation of the survivors' daily log returns over the 60 sessions ending on the decision session (from ohlcv_daily), computed as
(Var(sum z) - n) / (n(n-1)) on standardised returns.
Outputs p26_M6_ic.csv, p26_M6_breadth.csv."""
import os, sqlite3
import numpy as np, pandas as pd
from scipy import stats

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
AUD = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
PR = os.path.join(AUD, "probes")
O = pd.read_csv(os.path.join(PR, "p26_M6_outcomes.csv"), low_memory=False)
for c in ("in_book", "hit_sym"):
    O[c] = O[c].map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0})
ls = O.last_stage_reached.fillna("")
disc = ~ls.isin(["UNIVERSE", "SCANNER"]) & ~O.dropoff_stage.fillna("").isin(["BETWEEN_UNIVERSE_AND_DISCOVERY", "BETWEEN_SCANNER_AND_DISCOVERY"])
van = disc & ~ls.eq("VANGUARD_REJECT")
oi = O.oi_verdict.notna()
book = O.in_book == 1
STEPS = [("0_discovery_survivors", disc), ("1_after_vanguard_reject", van), ("2_after_OI_scope", oi), ("3_in_book", book),
         ("4_eil_EXECUTE_any", book & O.eil_signal_verdict.isin(["EXECUTE", "EXECUTE_WITH_CAUTION"])),
         ("5_lab_not_BLOCKED", book & O.lab_verdict.notna() & O.lab_verdict.ne("BLOCKED")),
         ("6_lab_GO_or_GO_LIMIT", book & O.lab_verdict.isin(["GO", "GO_LIMIT"])),
         ("7_opportunity_tier_not_BLOCK", book & O.opportunity_tier.notna() & O.opportunity_tier.ne("BLOCK"))]
SC = ["discovery_composite_score", "scanner_score", "vanguard_probability_edge", "oi_options_score", "composite_score", "priority_score", "options_score",
      "trigger_score", "eil_composite_eod", "ev3_ev_lower_bound_return"]
for s in SC + ["dir_ret_sig"]:
    O[s] = pd.to_numeric(O[s], errors="coerce")
rows = []
res = O.recon.eq("OK")
for step, m in STEPS:
    for d3 in ("CALL", "PUT"):
        mm = m & res & O.direction3.eq(d3)
        for s in SC:
            x = O.loc[mm, [s, "dir_ret_sig", "hit_sym", "ticker"]].dropna(subset=[s, "dir_ret_sig"])
            n = len(x)
            rec = dict(step=step, direction=d3, score=s, n=n, n_tickers=x.ticker.nunique(), power="INSUFFICIENT_POWER" if n < 100 else "n>=100")
            if n >= 3 and x[s].nunique() > 1:
                r = stats.spearmanr(x[s], x.dir_ret_sig)
                rec.update(ic_dir_ret_sig=r.statistic, ic_p=r.pvalue, ic_hit=stats.spearmanr(x[s], x.hit_sym).statistic)
            rows.append(rec)
IC = pd.DataFrame(rows)
IC.to_csv(os.path.join(PR, "p26_M6_ic.csv"), index=False)
pd.set_option("display.width", 250)
print(IC[IC.n >= 100].round(4).to_string(index=False))
print("cells:", len(IC), " n>=100:", int((IC.n >= 100).sum()))

# breadth
con = sqlite3.connect("file:" + os.path.join(AUD, "db_copies", "historical_prices.sqlite") + "?mode=ro", uri=True)
px = pd.read_sql("select ticker, trading_date, close from ohlcv_daily where trading_date >= '2026-04-01'", con)
W = px.pivot_table(index="trading_date", columns="ticker", values="close").sort_index()
LR = np.log(W).diff()
brows = []
for run, g in O.groupby("run_id"):
    ds = g.decision_session.iloc[0]
    win = LR.loc[:ds].tail(60)
    for step, m in STEPS:
        for d3 in ("ALL", "CALL", "PUT", "OTHER"):
            mm = m.loc[g.index] & (True if d3 == "ALL" else g.direction3.eq(d3))
            tk = [t for t in g.loc[mm, "ticker"].unique()]
            n = len(tk)
            cols = [t for t in tk if t in win.columns]
            X = win[cols].dropna(axis=1, thresh=50)
            k = X.shape[1]
            rho = np.nan; neff = np.nan
            if k >= 3:
                Z = (X - X.mean()) / X.std(ddof=1)
                Z = Z.fillna(0.0)
                v = Z.sum(axis=1).var(ddof=1)
                rho = (v - k) / (k * (k - 1))
                neff = n / (1 + (n - 1) * rho) if (1 + (n - 1) * rho) > 0 else np.nan
            brows.append(dict(run_id=run, decision_session=ds, step=step, direction=d3, n_rows=int(mm.sum()), n_tickers=n, n_with_returns=k, rho_bar=rho, n_eff=neff))
BR = pd.DataFrame(brows)
BR.to_csv(os.path.join(PR, "p26_M6_breadth.csv"), index=False)
print(BR[BR.direction == "ALL"].pivot_table(index="run_id", columns="step", values="n_rows").to_string())
print(BR[BR.direction == "ALL"].pivot_table(index="run_id", columns="step", values="n_eff").round(1).to_string())
print(BR[BR.direction == "ALL"].pivot_table(index="run_id", columns="step", values="rho_bar").round(3).to_string())
