import pandas as pd, re, sys
R='data/output/runs/20260914_214012/'
for f in ['options/options_intelligence_20260914_214012.csv','superbrain/superbrain_enriched_20260914_214012.csv','superbrain/eil_enriched_20260914_214012.csv','superbrain/wall_break_scores_20260914_214012.csv']:
    df=pd.read_csv(R+f,low_memory=False)
    cols=[c for c in df.columns if re.search(r'gex|gamma|wall|flip|max_pain|pin',c,re.I)]
    print('=====',f,df.shape)
    for c in cols:
        s=df[c]; n=pd.to_numeric(s,errors='coerce')
        if n.notna().sum()>0 and n.notna().sum()>=s.notna().sum()*0.9:
            print(f"{c:40s} null%={s.isna().mean()*100:5.1f} zero%={(n==0).mean()*100:5.1f} nuniq={n.nunique()} min={n.min():.4g} med={n.median():.4g} max={n.max():.4g} neg%={(n<0).mean()*100:.1f}")
        else:
            print(f"{c:40s} null%={s.isna().mean()*100:5.1f} top={s.value_counts(dropna=False).head(5).to_dict()}")
