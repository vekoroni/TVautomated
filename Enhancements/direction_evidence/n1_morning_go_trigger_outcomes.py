"""N1 acceptance: Morning GO rows, split by trigger eligibility; directional first-touch of +/-1 daily ATR
(and 5/10-session signed return) from the Morning session close. Same-session drift reference."""
import sys, glob, pandas as pd, numpy as np
sys.path.insert(0, 'Enhancements/direction_evidence')
from dir002_replay import read_bars
files = [l.strip() for l in open(sys.argv[1])]
rows = []
for f in files:
    m = pd.read_csv(f, low_memory=False, usecols=lambda c: c in {'ticker','verdict','trigger_go_eligible','candidate_status','resolved_direction','direction','session_date','gate_checked_at_utc'})
    m['run'] = f.split('morning_validated_trades_')[-1][:15]
    rows.append(m)
df = pd.concat(rows, ignore_index=True)
df = df[df.verdict.eq('GO')].copy()
df['side'] = df.get('resolved_direction', df.get('direction')).fillna(df.get('direction'))
df['date'] = pd.to_datetime(df.get('session_date').fillna(df.gate_checked_at_utc.astype(str).str[:10]) if 'session_date' in df else df.gate_checked_at_utc.astype(str).str[:10], errors='coerce')
df['elig'] = df.trigger_go_eligible.astype(str).str.lower().isin(['true','1','1.0']) & df.candidate_status.ne('WATCH_ONLY')
out = []
cache = {}
for r in df.itertuples():
    if r.ticker not in cache: cache[r.ticker] = read_bars(r.ticker)
    b = cache[r.ticker]
    if b.empty or pd.isna(r.date): continue
    idx = b.index[b.date == r.date]
    if not len(idx): continue
    i = idx[0]
    if i < 15: continue
    h,l,c = b.high.values, b.low.values, b.close.values
    atr = np.mean(np.maximum.reduce([h[i-13:i+1]-l[i-13:i+1], abs(h[i-13:i+1]-c[i-14:i]), abs(l[i-13:i+1]-c[i-14:i])]))
    sgn = 1 if str(r.side).upper()=='CALL' else -1
    res = {'run': r.run, 'ticker': r.ticker, 'elig': r.elig, 'date': r.date}
    for k in (5, 10):
        res[f'ret{k}'] = sgn*(c[i+k]/c[i]-1) if i+k < len(c) else np.nan
    t = 'OPEN'
    for j in range(i+1, min(len(c), i+11)):
        up, dn = h[j] >= c[i]+atr, l[j] <= c[i]-atr
        if up and dn: t='AMB'; break
        if up: t = 'WIN' if sgn==1 else 'LOSS'; break
        if dn: t = 'WIN' if sgn==-1 else 'LOSS'; break
    res['touch'] = t
    out.append(res)
o = pd.DataFrame(out)
print('GO rows scored:', len(o), '| runs:', o.run.nunique(), '| sessions:', o.date.nunique())
for e, g in o.groupby('elig'):
    dec = g[g.touch.isin(['WIN','LOSS'])]
    print(f"eligible={e}: n={len(g)} | first-touch 1ATR win {(dec.touch=='WIN').mean():.3f} (n={len(dec)}) | "
          f"mean signed ret5 {g.ret5.mean()*100:.2f}% (n={g.ret5.notna().sum()}) ret10 {g.ret10.mean()*100:.2f}% (n={g.ret10.notna().sum()})")
# block bootstrap by session on win-rate difference
dec = o[o.touch.isin(['WIN','LOSS'])].copy(); dec['w'] = (dec.touch=='WIN').astype(float)
ses = dec.date.unique(); rng = np.random.default_rng(20261003); diffs=[]
for _ in range(2000):
    s = rng.choice(ses, len(ses)); b = pd.concat([dec[dec.date==x] for x in s])
    a, z = b[b.elig].w.mean(), b[~b.elig].w.mean()
    if np.isfinite(a) and np.isfinite(z): diffs.append(a-z)
print('win-rate diff eligible - not: %.3f  95%% [%.3f, %.3f]' % (dec[dec.elig].w.mean()-dec[~dec.elig].w.mean(), np.quantile(diffs,.025), np.quantile(diffs,.975)))
