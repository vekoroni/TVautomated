"""p22_M2_greeks_iv.py -- AVS-TD-001 track M2 (discovery). READ-ONLY.

Subsample check of the IV_matched proxy: for up to N_PER_DATE tickers per weekly
snapshot date that feeds a panel row with a complete h=5 forward window, read
options_greeks_history (indexed ticker, snapshot_date) and take ATM IV at the
expiry whose calendar DTE is nearest h*7/5 (h=5 -> 7, 10 -> 14, 20 -> 28).
ATM = strike nearest underlying_price among quality OK/OK_ADJUSTED_NO_ARB rows
with 0.01 < iv < 5; call and put IV averaged at that strike.
Writes probes/p22_M2_greeks_iv.csv.
"""
import os, sqlite3, time
import numpy as np, pandas as pd

AUD = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
N_PER_DATE = 300
DATES = ["2026-07-17", "2026-07-31", "2026-08-28"]
t0 = time.time()
P = pd.read_csv(os.path.join(AUD, "probes", "p22_M2_panel.csv"), usecols=["ticker", "iv_surf_date", "fwd_ok_5"], low_memory=False)
con = sqlite3.connect(f"file:{os.path.join(AUD, 'db_copies', 'phantom_history.db')}?mode=ro", uri=True)
rows = []
for d in DATES:
    tk = sorted(P[(P.iv_surf_date == d) & (P.fwd_ok_5)].ticker.unique())
    rng = np.random.default_rng(20260913)
    samp = sorted(rng.choice(tk, size=min(N_PER_DATE, len(tk)), replace=False)) if tk else []
    print(d, "eligible tickers", len(tk), "sampled", len(samp))
    for x in samp:
        g = pd.read_sql("select expiration_date, dte, strike, side, underlying_price, iv, quality_status "
                        "from options_greeks_history where ticker=? and snapshot_date=?", con, params=(x, d))
        g = g[g.quality_status.isin(["OK", "OK_ADJUSTED_NO_ARB"]) & (g.iv > 0.01) & (g.iv < 5) & g.underlying_price.notna()]
        if g.empty:
            for h in (5, 10, 20):
                rows.append(dict(ticker=x, snapshot_date=d, h=h, expiry=None, dte=np.nan, atm_iv_greeks=np.nan, n_contracts=0))
            continue
        spot = g.underlying_price.median()
        exp = g.groupby("expiration_date").dte.median()
        for h in (5, 10, 20):
            target = h * 7 / 5
            e = (exp - target).abs().idxmin()
            ge = g[g.expiration_date == e]
            k = ge.strike.iloc[(ge.strike - spot).abs().argsort().iloc[0]]
            atm = ge[ge.strike == k]
            rows.append(dict(ticker=x, snapshot_date=d, h=h, expiry=e, dte=float(exp[e]),
                             atm_iv_greeks=float(atm.iv.mean()), n_contracts=len(atm),
                             moneyness=float(k / spot)))
con.close()
out = pd.DataFrame(rows)
out.to_csv(os.path.join(AUD, "probes", "p22_M2_greeks_iv.csv"), index=False)
print(out.groupby("h").agg(n=("atm_iv_greeks", "count"), med_dte=("dte", "median"), med_iv=("atm_iv_greeks", "median"),
                           dte_abs_err_med=("dte", lambda s: np.nanmedian(np.abs(s - s.name if False else s)))).to_string())
for h in (5, 10, 20):
    s = out[out.h == h]
    print("h", h, "dte distribution:", s.dte.describe().round(1).to_dict())
print(f"done {time.time()-t0:.1f}s rows {len(out)}")
