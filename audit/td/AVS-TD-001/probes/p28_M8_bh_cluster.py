import pandas as pd, numpy as np
from scipy import stats
C = pd.read_csv(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\probes\p28_M8_cells.csv")
E = C[C.status=="ELIGIBLE"].copy(); m=len(E)
def bh(p):
    p=np.asarray(p); o=np.argsort(p); r=p[o]*len(p)/(np.arange(len(p))+1); a=np.minimum(np.minimum.accumulate(r[::-1])[::-1],1); out=np.empty(len(p)); out[o]=a; return out
E["p_bh_cluster"]=bh(E.p_cluster_session.fillna(1).values)
print("m",m,"survive raw-BH",int((E.p_bh<=0.05).sum()),"survive cluster-BH",int((E.p_bh_cluster<=0.05).sum()))
print("survivors raw-BH by variable/direction/outcome:"); print(E[E.p_bh<=0.05].groupby(["variable","direction","outcome"]).size().to_string())
print("survivors cluster-BH by variable/direction/outcome:"); print(E[E.p_bh_cluster<=0.05].groupby(["variable","direction","outcome"]).size().to_string())
cols=["variable","stratum","level","outcome","n","rate","base_rate","diff","p_raw","p_cluster_session","p_bh","p_bh_cluster","haircut_bh","haircut_bonferroni","sessions_in_cell"]
pd.set_option("display.width",300)
print(E[E.p_bh_cluster<=0.05].sort_values("p_cluster_session")[cols].to_string(index=False,float_format=lambda x:f"{x:.3g}"))
E.to_csv(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\probes\p28_M8_bh_cluster.csv",index=False)
