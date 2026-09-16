import json, glob, os, numpy as np, pandas as pd, random
from scipy.stats import norm
os.chdir(r'C:\Users\ACKVerissimo\AVSHUNTER-Intelligence')
OI=pd.read_csv('data/output/runs/20260914_214012/options/options_intelligence_20260914_214012.csv',low_memory=False)
OI=OI.drop_duplicates('ticker').set_index('ticker')
base='data/canonical/market_observations/option_chain/2026-09-14/'
def load(t):
    fs=glob.glob(base+t+'/*.json')
    if not fs: return None
    df=pd.DataFrame(json.load(open(fs[0])))
    return df
def pipeline(df,spot):  # replica of compute_gex + compute_oi_walls
    sub=df.dropna(subset=['gamma']).copy()
    sign=np.where(sub['right'].str.upper()=='C',1.0,-1.0)
    gex=sign*sub['gamma']*sub['open_interest'].fillna(0)*spot*100
    g=pd.DataFrame({'strike':sub.strike.values,'gex':gex.values}).groupby('strike',as_index=False).sum().sort_values('strike')
    x,y=g.strike.values,g.gex.values; s=np.sign(y); flip=None
    for i in range(len(s)-1):
        if s[i]*s[i+1]<0 and (y[i+1]-y[i])!=0:
            flip=float(x[i]-y[i]*(x[i+1]-x[i])/(y[i+1]-y[i])); break
    fb=False
    if flip is None: flip=float(x[np.argmin(np.abs(y))]); fb=True
    c=df[df.right=='C'].groupby('strike').open_interest.sum(); p=df[df.right=='P'].groupby('strike').open_interest.sum()
    return flip,fb,float(c.idxmax()),float(p.idxmax()),g
def indep(df,spot,r=0.045):
    d=df.copy()
    d=d[(d.dte>0)]
    sgn=np.where(d.right=='C',1,-1); oi=d.open_interest.fillna(0).values
    gam=d.gamma.values.astype(float)
    net_provider=np.nansum(sgn*gam*oi*100*spot*spot*0.01)
    # walls by GEX
    d['gexd']=sgn*np.nan_to_num(gam)*oi*100*spot*spot*0.01
    cw=d[d.right=='C'].groupby('strike').gexd.sum(); pw=d[d.right=='P'].groupby('strike').gexd.sum()
    # repriced flip
    iv=d.implied_vol.values.astype(float); K=d.strike.values; T=np.clip(d.dte.values/365.0,1/365,None)
    ok=np.isfinite(iv)&(iv>0.01)&(iv<5)&(oi>0)
    grid=np.linspace(0.6*spot,1.4*spot,321); prof=[]
    for S in grid:
        d1=(np.log(S/K[ok])+(r+0.5*iv[ok]**2)*T[ok])/(iv[ok]*np.sqrt(T[ok]))
        g=norm.pdf(d1)/(S*iv[ok]*np.sqrt(T[ok]))
        prof.append(np.sum(sgn[ok]*g*oi[ok]*100*S*S*0.01))
    prof=np.array(prof)
    net_bs_spot=np.interp(spot,grid,prof)
    flips=[grid[i]-prof[i]*(grid[i+1]-grid[i])/(prof[i+1]-prof[i]) for i in range(len(grid)-1) if prof[i]*prof[i+1]<0]
    flip=min(flips,key=lambda f:abs(f-spot)) if flips else None
    return dict(net_gex_1pct_provider=net_provider,net_gex_1pct_bs=net_bs_spot,flip_bs=flip,n_flips=len(flips),
                gex_call_wall=float(cw.idxmax()) if len(cw) else None, gex_put_wall=float(pw.idxmin()) if len(pw) else None)
named=['NVDA','TSLA','AMD','IWM','AAPL','A']
tick=[t for t in OI.index if os.path.isdir(base+str(t))]
random.seed(1); sample=named+random.sample([t for t in tick if t not in named],120)
rows=[]; prof=[]
for t in sample:
    df=load(t)
    if df is None or df.empty: continue
    for c in ['gamma','open_interest','implied_vol','strike','dte','underlying_price']: df[c]=pd.to_numeric(df[c],errors='coerce')
    spot=float(OI.loc[t,'underlying_price']) if pd.notna(OI.loc[t,'underlying_price']) else float(df.underlying_price.median())
    prof.append(dict(ticker=t,n=len(df),gamma_null=df.gamma.isna().mean(),gamma_zero=(df.gamma==0).mean(),oi_zero=(df.open_interest.fillna(0)==0).mean(),
        iv_min=df.implied_vol.min(),iv_med=df.implied_vol.median(),iv_tiny=(df.implied_vol<0.01).mean(),dte_max=df.dte.max(),n_exp=df.expiration_date.nunique(),
        up_nuniq=df.underlying_price.nunique(),kmin=df.strike.min()/spot,kmax=df.strike.max()/spot))
    pf,fb,ocw,opw,g=pipeline(df,spot); ind=indep(df,spot)
    rows.append(dict(ticker=t,spot=spot,pub_flip=OI.loc[t,'gamma_flip'],rep_flip=pf,rep_fallback=fb,pub_cw=OI.loc[t,'call_wall'],rep_cw=ocw,pub_pw=OI.loc[t,'put_wall'],rep_pw=opw,**ind))
R=pd.DataFrame(rows); P=pd.DataFrame(prof)
pd.set_option('display.width',250); pd.set_option('display.max_columns',30)
print(R.head(6).to_string()); 
R['pub_gap']=(R.pub_flip-R.spot).abs()/R.spot*100
R['bs_gap']=(R.flip_bs-R.spot).abs()/R.spot*100
R['flip_match']=(R.pub_flip-R.rep_flip).abs()<1e-3
R['cw_match']=R.pub_cw==R.rep_cw; R['pw_match']=R.pub_pw==R.rep_pw
print('N',len(R),'replica flip match%',R.flip_match.mean()*100,'cw match%',R.cw_match.mean()*100,'pw match%',R.pw_match.mean()*100,'fallback%',R.rep_fallback.mean()*100)
print('pub flip gap % quantiles',R.pub_gap.quantile([.1,.25,.5,.75,.9]).round(1).to_dict())
print('pub flip below 0.5*spot %',(R.pub_flip<0.5*R.spot).mean()*100)
print('BS flip found %',R.flip_bs.notna().mean()*100,'bs gap quantiles',R.bs_gap.quantile([.1,.25,.5,.75,.9]).round(1).to_dict())
print('pub vs bs flip abs diff % spot median',((R.pub_flip-R.flip_bs).abs()/R.spot*100).median())
print('net gex sign (bs at spot) pos%',(R.net_gex_1pct_bs>0).mean()*100,' provider pos%',(R.net_gex_1pct_provider>0).mean()*100)
print('regime disagreement: spot>pub_flip (implied positive) vs bs net sign', ((R.spot>R.pub_flip)!=(R.net_gex_1pct_bs>0)).mean()*100)
print('gex call wall == OI call wall %',(R.gex_call_wall==R.pub_cw).mean()*100,' put %',(R.gex_put_wall==R.pub_pw).mean()*100)
print('call wall below spot %',(R.pub_cw<R.spot).mean()*100,' put wall above spot %',(R.pub_pw>R.spot).mean()*100)
print(P.describe().round(3).to_string())
R.to_csv(r'C:\Users\ACKVER~1\AppData\Local\Temp\claude\C--Users-ACKVerissimo-AVSHUNTER-Intelligence\469536f4-3029-496c-90f4-5b8e9428f532\scratchpad\recompute.csv',index=False)
