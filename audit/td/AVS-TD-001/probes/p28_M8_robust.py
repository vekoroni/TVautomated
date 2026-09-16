"""M8: robustness of the 48 CMH+pooled BH survivors: per-session sign consistency, distinct tickers, complement pairs. Read-only. RESEARCH_ONLY."""
import os
import numpy as np, pandas as pd
OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\probes"
D = pd.read_csv(os.path.join(OUT, "p28_M8_joined.csv"), low_memory=False)
R = pd.read_csv(os.path.join(OUT, "p28_M8_cmh.csv"), low_memory=False)
E = D[D.label_V.isin(["TARGET_FIRST", "INVALIDATION_FIRST", "TIMEOUT"])].copy()
E["TF"] = (E.label_V == "TARGET_FIRST").astype(int)
E["SC"] = E.side_correct.astype(str).str.lower().eq("true").astype(int)
E["stratum"] = E.direction.astype(str) + " " + E.horizon_bucket.astype(str)
S = R[R.survives_both.astype(str).str.lower().eq("true")].copy()
rows = []
for _, r in S.iterrows():
    g = E[E.stratum == r.stratum]
    inc = g[r.variable].astype(str) == str(r.level)
    same = tot = 0
    for s, gs in g.groupby("decision_session"):
        i = gs[r.variable].astype(str) == str(r.level)
        if i.sum() == 0 or (~i).sum() == 0: continue
        d = gs.loc[i, r.outcome].mean() - gs.loc[~i, r.outcome].mean()
        tot += 1; same += int(np.sign(d) == np.sign(r.rd_mh))
    lv = g.loc[inc, r.variable].nunique()
    other_levels = g.loc[~inc, r.variable].astype(str).value_counts()
    rows.append(dict(variable=r.variable, stratum=r.stratum, level=r.level, outcome=r.outcome, n=int(inc.sum()), distinct_tickers=int(g.loc[inc, "ticker"].nunique()),
                     sessions_same_sign=same, sessions_with_contrast=tot, rest_levels=len(other_levels), rest_top_share=float(other_levels.iloc[0] / other_levels.sum()) if len(other_levels) else np.nan,
                     rd_mh=r.rd_mh, rd_mh_after_bh_haircut=r.rd_mh_after_bh_haircut, p_cmh_bh=r.p_cmh_bh, haircut_cmh_bh=r.haircut_cmh_bh, haircut_cmh_bonf=r.haircut_cmh_bonf))
X = pd.DataFrame(rows)
X["mirror_of_two_level_split"] = X.rest_top_share >= 0.95
X.to_csv(os.path.join(OUT, "p28_M8_robust.csv"), index=False)
pd.set_option("display.width", 300)
txt = X.sort_values(["variable", "stratum", "outcome"]).to_string(index=False, float_format=lambda x: f"{x:.3g}")
txt += "\n\nsurvivors %d | all sessions same sign: %d | >=80%% sessions same sign: %d | mirror pairs (rest is one level >=95%%): %d" % (
    len(X), int((X.sessions_same_sign == X.sessions_with_contrast).sum()), int((X.sessions_same_sign >= 0.8 * X.sessions_with_contrast).sum()), int(X.mirror_of_two_level_split.sum()))
txt += "\nsurvivors by direction: " + str(X.stratum.str.split().str[0].value_counts().to_dict()) + " | by outcome: " + str(X.outcome.value_counts().to_dict())
txt += "\nmedian |rd_mh| TF %.4f SC %.4f; median haircut BH %.3f Bonf %.3f" % (X[X.outcome=="TF"].rd_mh.abs().median(), X[X.outcome=="SC"].rd_mh.abs().median(), X.haircut_cmh_bh.median(), X.haircut_cmh_bonf.median())
print(txt)
open(os.path.join(OUT, "p28_M8_robust.txt"), "w", encoding="utf-8").write(txt)
