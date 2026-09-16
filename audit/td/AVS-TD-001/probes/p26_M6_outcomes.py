"""M6 step 2 - retrospective outcome for EVERY dropoff-audit ticker on the 22 book runs (removed and surviving). Read-only.
Reference price S0 = close on the run's decision_session (p31_presented_candidates.decision_session) from ohlcv_daily.
Hold h: eod_horizon_bucket / discovery lifecycle horizon (1_5d->5, 6_10d->10, 11_20d->20), else 10 (stated assumption).
sigma_a: qomega/garch_forecasts_<run>.csv l3_forward_realised_vol where the ticker is in it (book tickers only);
otherwise trailing 20-session close-to-close realised vol annualised (sqrt 252) from ohlcv_daily up to decision_session
(sigma_src = RV20_FALLBACK) - garch sigma does not exist for removed tickers.
Symmetric vol-budget barrier (ALG-08 target form, symmetric invalidation because removed rows carry no invalidation):
 up = S0*(1+1.5*sigma*sqrt(h/252)), dn = S0*(1-1.5*sigma*sqrt(h/252)).
Directed rows: TARGET_FIRST / INVALIDATION_FIRST / TIMEOUT / AMBIGUOUS; hit_sym = TARGET_FIRST; side_correct = terminal close in direction.
All rows: touch_any (either barrier), abs_move_sig = |terminal log-return| / (sigma*sqrt(h/252)).
Also joins p32 label_V / side_correct for presented rows (row's own invalidation).
Output p26_M6_outcomes.csv."""
import os, math, sqlite3
import numpy as np, pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUNS = os.path.join(ROOT, "data", "output", "runs")
AUD = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
PR = os.path.join(AUD, "probes")
K = 1.5
HMAP = {"1_5d": 5, "6_10d": 10, "11_20d": 20, "1-5d": 5, "6-10d": 10, "11-20d": 20, "1-10d": 10}

P31 = pd.read_csv(os.path.join(PR, "p31_presented_candidates.csv"), usecols=["run_id", "decision_session"], low_memory=False)
DS = P31.groupby("run_id").decision_session.first().to_dict()
con = sqlite3.connect("file:" + os.path.join(AUD, "db_copies", "historical_prices.sqlite") + "?mode=ro", uri=True)
px = pd.read_sql("select ticker, trading_date, high, low, close from ohlcv_daily where trading_date >= '2026-05-15'", con)
px = px.sort_values(["ticker", "trading_date"])
G = {t: (d.trading_date.values, d.high.values.astype(float), d.low.values.astype(float), d.close.values.astype(float)) for t, d in px.groupby("ticker")}

BOOKCOLS = ["ticker", "governed_direction", "direction", "lab_verdict", "opportunity_tier", "opportunity_tier_reason", "eil_signal_verdict",
            "morning_execution_permission", "liquidity_state", "execution_viability_state", "quote_freshness", "usmi_sector_alignment",
            "final_action", "campaign_verdict", "composite_score", "priority_score", "options_score", "trigger_score", "eil_composite_eod",
            "ev3_ev_lower_bound_return", "lab_rank", "priority_rank", "verdict"]
AUDCOLS = ["ticker", "last_stage_reached", "dropoff_stage", "dropoff_reason", "discovery_direction", "eod_direction", "discovery_tier_label",
           "discovery_intent", "discovery_composite_score", "scanner_score", "vanguard_expected_options_scope", "vanguard_probability_edge",
           "oi_verdict", "oi_options_score", "oi_spread_pct", "oi_oi", "eil_v3_verdict", "audit_flags", "eod_horizon_bucket", "eod_slate_rank",
           "discovery_macro_caution", "discovery_macro_quality", "eod_contract_spread_pct", "eod_contract_oi"]

L = pd.read_csv(os.path.join(PR, "p32_labels.csv"), usecols=["run_id", "ticker", "direction", "label_V", "side_correct", "terminal_return"], low_memory=False)
L = L.drop_duplicates(["run_id", "ticker", "direction"]).rename(columns={"direction": "p32_direction", "side_correct": "p32_side_correct", "terminal_return": "p32_terminal_return"})

out = []
for run, ds in sorted(DS.items()):
    A = pd.read_csv(os.path.join(RUNS, run, "diagnostics", f"dropoff_audit_{run}.csv"), low_memory=False, usecols=lambda c: c in AUDCOLS)
    A = A.drop_duplicates("ticker")
    lc = os.path.join(RUNS, run, "discovery", f"discovery_lifecycle_{run}.csv")
    if os.path.exists(lc):
        LC = pd.read_csv(lc, usecols=["ticker", "horizon_bucket"]).drop_duplicates("ticker")
        A = A.merge(LC.rename(columns={"horizon_bucket": "disc_horizon"}), on="ticker", how="left")
    else:
        A["disc_horizon"] = np.nan
    B = pd.read_csv(os.path.join(RUNS, run, "intelligence_lab", f"final_opportunity_book_{run}.csv"), low_memory=False, usecols=lambda c: c in BOOKCOLS)
    B = B.drop_duplicates("ticker")
    B["book_direction"] = B["governed_direction"] if "governed_direction" in B else B["direction"]
    B = B.drop(columns=[c for c in ("governed_direction", "direction") if c in B])
    B["in_book"] = True
    A = A.merge(B, on="ticker", how="left")
    A["in_book"] = A.in_book.fillna(False).astype(bool)
    gf = os.path.join(RUNS, run, "qomega", f"garch_forecasts_{run}.csv")
    GA = pd.read_csv(gf, usecols=["ticker", "l3_forward_realised_vol"]).drop_duplicates("ticker") if os.path.exists(gf) else pd.DataFrame(columns=["ticker", "l3_forward_realised_vol"])
    A = A.merge(GA, on="ticker", how="left")
    A["run_id"] = run; A["decision_session"] = ds
    for r in A.itertuples(index=False):
        dirn = r.book_direction if isinstance(r.book_direction, str) else (r.eod_direction if isinstance(r.eod_direction, str) else r.discovery_direction)
        dirn = str(dirn).upper() if isinstance(dirn, str) else "NONE"
        hb = r.eod_horizon_bucket if isinstance(r.eod_horizon_bucket, str) and r.eod_horizon_bucket in HMAP else r.disc_horizon
        h = HMAP.get(hb, 10); h_src = "ROW" if hb in HMAP else "DEFAULT_10"
        rec = dict(r._asdict()); rec.update(direction3=dirn if dirn in ("CALL", "PUT") else "OTHER", direction_raw=dirn, h=h, h_src=h_src)
        g = G.get(r.ticker)
        if g is None:
            rec["recon"] = "NO_PRICE_SERIES"; out.append(rec); continue
        dts, hi, lo, cl = g
        i0 = np.searchsorted(dts, ds, side="right") - 1
        if i0 < 0 or dts[i0] != ds:
            rec["recon"] = "NO_BAR_ON_DECISION_SESSION"; out.append(rec); continue
        if i0 + h >= len(dts):
            rec["recon"] = "WINDOW_NOT_ELAPSED"; out.append(rec); continue
        S0 = cl[i0]
        sig = r.l3_forward_realised_vol; ssrc = "GARCH"
        if not (isinstance(sig, float) and np.isfinite(sig) and sig > 0):
            if i0 >= 20:
                lr = np.diff(np.log(cl[i0 - 20:i0 + 1])); sig = float(np.std(lr, ddof=1) * math.sqrt(252)); ssrc = "RV20_FALLBACK"
            else:
                rec["recon"] = "NO_SIGMA"; out.append(rec); continue
        if not (S0 > 0 and sig > 0):
            rec["recon"] = "BAD_PRICE_OR_SIGMA"; out.append(rec); continue
        sh = sig * math.sqrt(h / 252.0)
        up, dn = S0 * (1 + K * sh), S0 * (1 - K * sh)
        wh, wl, wc = hi[i0 + 1:i0 + 1 + h], lo[i0 + 1:i0 + 1 + h], cl[i0 + 1:i0 + 1 + h]
        first_up = next((j for j in range(h) if wh[j] >= up), None)
        first_dn = next((j for j in range(h) if wl[j] <= dn), None)
        term = math.log(wc[-1] / S0)
        rec.update(recon="OK", S0=S0, sigma=sig, sigma_src=ssrc, touch_any=(first_up is not None) or (first_dn is not None),
                   abs_move_sig=abs(term) / sh, term_logret=term)
        if dirn in ("CALL", "PUT"):
            fav, adv = (first_up, first_dn) if dirn == "CALL" else (first_dn, first_up)
            if fav is not None and (adv is None or fav < adv):
                lab = "TARGET_FIRST"
            elif adv is not None and (fav is None or adv < fav):
                lab = "INVALIDATION_FIRST"
            elif fav is not None and adv is not None:
                lab = "AMBIGUOUS"
            else:
                lab = "TIMEOUT"
            sgn = 1 if dirn == "CALL" else -1
            rec.update(label_sym=lab, hit_sym=lab == "TARGET_FIRST", side_correct=sgn * term > 0, dir_ret_sig=sgn * term / sh)
        out.append(rec)
    print(run, ds, len(A))

O = pd.DataFrame(out)
O = O.merge(L, left_on=["run_id", "ticker"], right_on=["run_id", "ticker"], how="left")
O.to_csv(os.path.join(PR, "p26_M6_outcomes.csv"), index=False)
print(O.recon.value_counts().to_string())
ok = O[O.recon == "OK"]
print(pd.crosstab([ok.in_book, ok.direction3], ok.sigma_src).to_string())
print(pd.crosstab(ok.run_id, ok.in_book).to_string())
b = ok[ok.label_V.notna() & ok.direction3.isin(["CALL", "PUT"])]
print("agreement hit_sym vs p32 label_V==TARGET_FIRST:", round(((b.label_V == "TARGET_FIRST") == b.hit_sym).mean(), 4), "n", len(b))
print("agreement side_correct vs p32:", round((b.p32_side_correct.astype(str) == b.side_correct.astype(str)).mean(), 4))
