import pandas as pd, numpy as np
KEYS=["ticker","cut","timeframe","scope","signal_type","direction"]
def panel(rec, cand):
    R=pd.read_json(rec,lines=True); R=R[(R.timeframe=="1d")&(R.test=="OUTCOME_FROM_DETECTION")]
    C=pd.read_json(cand,lines=True).rename(columns={"tf":"timeframe","type":"signal_type","dir":"direction"})
    live=C[C.state.isin(["DETECTED","ACTIVATED"])]
    # higher-timeframe agreement at the same cut: a live weekly/monthly setup in the same direction
    htf=live[live.timeframe.isin(["1w","1mo"])].groupby(["ticker","cut","direction"]).size().rename("htf_same").reset_index()
    opp=live[live.timeframe.isin(["1w","1mo"])][["ticker","cut","direction"]].drop_duplicates()
    opp["direction"]=opp.direction.map({"BULL":"BEAR","BEAR":"BULL"}); opp["htf_opp"]=1
    D=C[(C.timeframe=="1d")&(C.state=="DETECTED")].drop_duplicates(KEYS)
    D=R.merge(D[KEYS+["close","outcome","invalidation","trigger","age_bars","atr_tf"]],on=KEYS)
    D=D.merge(htf,on=["ticker","cut","direction"],how="left").merge(opp,on=["ticker","cut","direction"],how="left")
    D["htf_same"]=D.htf_same.fillna(0)>0; D["htf_opp"]=D.htf_opp.fillna(0)>0
    D["gain_pct"]=(D.outcome-D.close).abs()/D.close*100; D["loss_pct"]=(D.close-D.invalidation).abs()/D.close*100
    D["ratio"]=D.gain_pct/D.loss_pct.replace(0,np.nan)
    D["trig_atr"]=(D.trigger-D.close).abs()/D.atr_tf.replace(0,np.nan)
    D["loss_atr"]=(D.close-D.invalidation).abs()/D.atr_tf.replace(0,np.nan)
    D["gain_atr"]=(D.outcome-D.close).abs()/D.atr_tf.replace(0,np.nan)
    D["hit"]=D.cause.eq("EVENT")
    D["res"]=np.where(D.hit,D.gain_pct,np.where(D.cause.eq("INVALIDATION"),-D.loss_pct,0))
    return D
B="Enhancements/outcomes/beh001/"
O=panel(B+"eval_v5/duration_records.jsonl",B+"eval_v4/candidates.jsonl")
H=panel(B+"eval_v5_holdout/duration_records.jsonl",B+"eval_v4_holdout/candidates.jsonl")
O.to_pickle(B+"../laneb_O.pkl"); H.to_pickle(B+"../laneb_H.pkl")
print(len(O),len(H))
for name,D in [("orig",O),("hold",H)]:
    print("\n==",name)
    for col,bins in [("trig_atr",[0,.25,.5,1,2,99]),("loss_atr",[0,1,2,3,5,99]),("gain_atr",[0,1,2,4,8,999]),("age_bars",[-1,2,5,10,20,999])]:
        g=D.groupby(pd.cut(D[col],bins),observed=True).agg(n=("hit","size"),hit=("hit","mean"),res=("res","mean")).round(3)
        print(col, g.to_dict("index"))
    print("htf", D.groupby(["htf_same","htf_opp"]).agg(n=("hit","size"),hit=("hit","mean"),res=("res","mean")).round(3).to_dict("index"))
    print("scope", D.groupby("scope").agg(n=("hit","size"),hit=("hit","mean"),res=("res","mean")).round(3).to_dict("index"))
