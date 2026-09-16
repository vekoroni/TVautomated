"""p21_M1_usmi_labels.py -- read-only. Regime-layer label panel vs realised forward sector returns.
Sources (read-only): data/output/runs/*/macro_snapshot.json (extras.us_money_index.source_payload;
sector_rotation.sector_bias_map; sector_lead; sector_avoid), dropbox/macro/avshunter_us_money_index*.json,
dropbox/macro/Archive/avshunter_us_money_index*.json. Prices: db_copies/historical_prices.sqlite via the cached
wide close matrix (_scratch_m1/close_wide.parquet built by p21_M1_universe.py).
Label families:
  A_USMI_ROUTING_4LABEL  options_monetisation.sector_routing.routing (PRIORITY_UPGRADE / ADVERSE_REGIME_RS_REQUIRED /
                         PRIORITY_WATCH / NOT_YET_CONFIRMED)
  B_USMI_PRIORITY_LIST   options_monetisation.long_call_priority / long_put_priority (v2); sector_rotation lists (v1)
  C_SNAPSHOT_BIAS_MAP    macro_snapshot sector_rotation.sector_bias_map (TAILWIND / HEADWIND / NEUTRAL / MIXED)
  D_SNAPSHOT_LEAD_AVOID  macro_snapshot sector_lead / sector_avoid (SPDR sector ETFs)
Route/theme -> GICS sector for A/B is a keyword map written in this probe (derived; NOT the pipeline's _route_key).
t0 = last store session strictly before the as-of date if as-of UTC hour < 20, else the as-of session itself.
Forward sector relative return(h) = EW mean log return of mapped store tickers in the sector (t0 -> t0+h) minus the
all-mapped EW mean, h = 1..15. Hit: CALL side / TAILWIND / LEAD -> relative > 0; PUT side / HEADWIND / AVOID -> < 0.
Identical (t0, family, route, label, sector) observations carried by several runs are counted once.
Outputs: p21_M1_usmi_labels.csv (panel), p21_M1_usmi_label_eval.csv (label x h), p21_M1_usmi_leadlag.csv. RESEARCH_ONLY.
"""
import os, glob, json, time
import numpy as np, pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
PROBES = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
SCR = os.path.join(PROBES, "_scratch_m1")
tc = time.time()
GICS = ["Information Technology", "Health Care", "Industrials", "Consumer Discretionary", "Financials", "Energy",
        "Materials", "Real Estate", "Consumer Staples", "Communication Services", "Utilities"]
ETF2S = {"XLK": "Information Technology", "XLV": "Health Care", "XLI": "Industrials", "XLY": "Consumer Discretionary",
         "XLF": "Financials", "XLE": "Energy", "XLB": "Materials", "XLRE": "Real Estate", "XLP": "Consumer Staples",
         "XLC": "Communication Services", "XLU": "Utilities"}
KW = [("SEMICON", "Information Technology"), ("AI_", "Information Technology"), ("TECH", "Information Technology"),
      ("SOFTWARE", "Information Technology"), ("MEMORY", "Information Technology"), ("OPTICAL", "Information Technology"),
      ("DATA_CENTRE", "Information Technology"), ("CLOUD", "Information Technology"),
      ("ENERGY", "Energy"), ("REFINER", "Energy"), ("OIL", "Energy"), ("LNG", "Energy"),
      ("FINANCIAL", "Financials"), ("AIRLINE", "Industrials"), ("TRANSPORT", "Industrials"), ("DEFENCE", "Industrials"),
      ("INDUSTRIAL", "Industrials"), ("MATERIAL", "Materials"), ("HOMEBUILDER", "Consumer Discretionary"),
      ("HOUSING", "Consumer Discretionary"), ("RETAIL", "Consumer Discretionary"), ("DISCRETIONARY", "Consumer Discretionary"),
      ("CONSUMER", "Consumer Discretionary"), ("REIT", "Real Estate")]


def route_sectors(key):
    k = str(key).upper()
    out = []
    for w, s in KW:
        if w in k and s not in out:
            out.append(s)
    return out  # [] -> UNMAPPED (broad index, small caps, generic cyclicals / RS names)


def side_of(key):
    k = str(key).upper()
    if k.endswith("_PUT"):
        return "PUT"
    if k.endswith("_CALL"):
        return "CALL"
    return "OTHER"


recs = []


def add(src, run, as_of, family, route, label, side, sectors, pid):
    for s in (sectors or ["UNMAPPED"]):
        recs.append({"source_file": src, "run": run, "as_of_utc": as_of, "family": family, "route": route,
                     "label": label, "side": side, "sector": s, "packet_id": pid})


def from_usmi_payload(sp, src, run, as_of, pid):
    om = sp.get("options_monetisation") or {}
    srt = om.get("sector_routing")
    sr = srt.get("routing") if isinstance(srt, dict) else None
    if isinstance(sr, dict):
        for route, lab in sr.items():
            add(src, run, as_of, "A_USMI_ROUTING_4LABEL", route, lab, side_of(route), route_sectors(route), pid)
    for fld, sd in (("long_call_priority", "CALL"), ("long_put_priority", "PUT")):
        v = om.get(fld)
        if isinstance(v, list):
            for route in v:
                add(src, run, as_of, "B_USMI_PRIORITY_LIST", route, f"{sd}_PRIORITY", sd, route_sectors(route), pid)
    rot = sp.get("sector_rotation") or {}
    if isinstance(rot, dict) and "priority_long_call_sectors" in rot:
        for fld, v in rot.items():
            sd = "PUT" if "put" in fld else "CALL"
            for route in (v or []):
                add(src, run, as_of, "B_USMI_PRIORITY_LIST", route, f"{sd}_PRIORITY", sd, route_sectors(route), pid)


run_census = []
for p in sorted(glob.glob(os.path.join(ROOT, "data", "output", "runs", "*", "macro_snapshot.json"))):
    run = os.path.basename(os.path.dirname(p))
    try:
        m = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        run_census.append({"run": run, "readable": False, "err": str(e)[:80]})
        continue
    u = ((m.get("extras") or {}).get("us_money_index")) or {}
    rel = os.path.relpath(p, ROOT)
    n0 = len(recs)
    if u:
        as_of = u.get("market_data_as_of_utc") or u.get("generated_at_utc")
        from_usmi_payload(u.get("source_payload") or {}, rel, run, as_of, u.get("packet_id"))
    nu = len(recs) - n0
    bm = (m.get("sector_rotation") or {}).get("sector_bias_map") or {}
    for s, lab in bm.items():
        if s in GICS:
            add(rel, run, m.get("as_of_utc"), "C_SNAPSHOT_BIAS_MAP", s, lab,
                {"TAILWIND": "CALL", "HEADWIND": "PUT"}.get(lab, "OTHER"), [s], m.get("report_date"))
    for fld, lab, sd in (("sector_lead", "LEAD", "CALL"), ("sector_avoid", "AVOID", "PUT")):
        for e in (m.get(fld) or []):
            add(rel, run, m.get("as_of_utc"), "D_SNAPSHOT_LEAD_AVOID", e, lab, sd, [ETF2S[e]] if e in ETF2S else [], m.get("report_date"))
    run_census.append({"run": run, "readable": True, "usmi_present": bool(u), "usmi_packet_id": u.get("packet_id"),
                       "usmi_label_rows": nu, "bias_map_n": len(bm), "as_of_utc": m.get("as_of_utc")})
drop = sorted(glob.glob(os.path.join(ROOT, "dropbox", "macro", "avshunter_us_money_index*.json"))) + \
    sorted(glob.glob(os.path.join(ROOT, "dropbox", "macro", "Archive", "avshunter_us_money_index*.json")))
for p in drop:
    sp = json.load(open(p, encoding="utf-8"))
    aw = sp.get("analysis_window") or {}
    as_of = aw.get("as_of_utc") or sp.get("market_data_as_of") or sp.get("generated_at_local")
    n0 = len(recs)
    from_usmi_payload(sp, os.path.relpath(p, ROOT), "DROPBOX", as_of, None)
    run_census.append({"run": "DROPBOX:" + os.path.basename(p), "readable": True, "usmi_present": True, "usmi_label_rows": len(recs) - n0, "as_of_utc": as_of})
pd.DataFrame(run_census).to_csv(os.path.join(SCR, "label_source_census.csv"), index=False)

L = pd.DataFrame(recs)
L["as_of_ts"] = pd.to_datetime(L["as_of_utc"], utc=True, errors="coerce", format="mixed")
wide = pd.read_parquet(os.path.join(SCR, "close_wide.parquet"))
wide = wide.where(wide > 0)
sess = wide.index


def t0_of(ts):
    if pd.isna(ts):
        return pd.NaT
    d = pd.Timestamp(ts.date())
    cand = sess[sess <= d] if ts.hour >= 20 else sess[sess < d]
    return cand[-1] if len(cand) else pd.NaT


L["t0_session"] = L["as_of_ts"].map(t0_of)
L["fwd_sessions_available"] = L["t0_session"].map(lambda t: int(len(sess) - 1 - sess.get_loc(t)) if pd.notna(t) else np.nan)
L["dedup_key"] = (L["t0_session"].astype(str) + "|" + L["family"] + "|" + L["route"].astype(str) + "|" +
                  L["label"].astype(str) + "|" + L["sector"])
L["is_first_occurrence"] = ~L.duplicated("dedup_key")
L.drop(columns=["as_of_ts"]).to_csv(os.path.join(PROBES, "p21_M1_usmi_labels.csv"), index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 400); pd.set_option("display.max_columns", 40)
print("label panel rows", len(L), "unique", int(L["is_first_occurrence"].sum()))
print(pd.DataFrame(run_census).to_string())
print(L[L.is_first_occurrence].groupby(["family", "label"]).agg(
    n=("sector", "size"), n_unmapped=("sector", lambda s: int((s == "UNMAPPED").sum())), t0_min=("t0_session", "min"),
    t0_max=("t0_session", "max"), fwd_min=("fwd_sessions_available", "min"), fwd_max=("fwd_sessions_available", "max")).to_string())

smap = pd.read_csv(os.path.join(PROBES, "p21_M1_sector_map.csv"), index_col="ticker", dtype=str)
lp = np.log(wide.loc["2026-05-01":])
cols = [c for c in lp.columns if c in smap.index and smap.loc[c, "in_store"] == "True" and smap.loc[c, "sector"] in GICS]
secser = smap.loc[cols, "sector"]
H = list(range(1, 16))
U = L[L.is_first_occurrence & (L["sector"] != "UNMAPPED") & L["t0_session"].notna()].copy().reset_index(drop=True)
for h in H:
    fr = lp[cols].shift(-h) - lp[cols]
    fr = fr.where(fr.abs() < 1.0)
    sec_fr = fr.T.groupby(secser).mean().T
    rel = sec_fr.sub(fr.mean(axis=1), axis=0)
    ok = U["fwd_sessions_available"] >= h
    U[f"rel_fwd_{h}"] = [rel.at[t, s] if o else np.nan for t, s, o in zip(U["t0_session"], U["sector"], ok)]
    U[f"abs_fwd_{h}"] = [sec_fr.at[t, s] if o else np.nan for t, s, o in zip(U["t0_session"], U["sector"], ok)]
for back in (5, 10):
    pr = lp[cols] - lp[cols].shift(back)
    pr = pr.where(pr.abs() < 1.0)
    rel_b = pr.T.groupby(secser).mean().T.sub(pr.mean(axis=1), axis=0)
    U[f"rel_prior_{back}"] = [rel_b.at[t, s] for t, s in zip(U["t0_session"], U["sector"])]


def power(n):
    return "OK" if n >= 100 else ("DATA_UNAVAILABLE(n=0)" if n == 0 else f"INSUFFICIENT_POWER(n={n})")


evals = []
for (fam, lab, side), g in L[L.is_first_occurrence].groupby(["family", "label", "side"]):
    gu = U[(U.family == fam) & (U.label == lab) & (U.side == side)]
    for h in H:
        v = gu[f"rel_fwd_{h}"].dropna()
        n = len(v)
        hit = np.nan
        if n and side in ("CALL", "PUT"):
            hit = float((v > 0).mean()) if side == "CALL" else float((v < 0).mean())
        evals.append({"family": fam, "label": lab, "side": side, "h": h, "n_label_obs_total": len(g),
                      "n_unmapped": int((g["sector"] == "UNMAPPED").sum()), "n": n,
                      "n_distinct_t0": int(gu.loc[v.index, "t0_session"].nunique()) if n else 0,
                      "hit_rate": hit, "mean_rel_fwd": v.mean() if n else np.nan, "median_rel_fwd": v.median() if n else np.nan,
                      "mean_abs_fwd": gu.loc[v.index, f"abs_fwd_{h}"].mean() if n else np.nan, "power": power(n)})
E = pd.DataFrame(evals)
E.to_csv(os.path.join(PROBES, "p21_M1_usmi_label_eval.csv"), index=False)

ll = []
for (fam, lab, side), g in U.groupby(["family", "label", "side"]):
    g5 = g.dropna(subset=["rel_fwd_5", "rel_prior_5"])
    if len(g5) < 20 or side not in ("CALL", "PUT"):
        continue
    sg = 1 if side == "CALL" else -1
    ll.append({"family": fam, "label": lab, "side": side, "n": len(g5), "n_distinct_t0": int(g5["t0_session"].nunique()),
               "signed_rel_prior_10": (sg * g5["rel_prior_10"]).mean(), "signed_rel_prior_5": (sg * g5["rel_prior_5"]).mean(),
               "signed_rel_fwd_1": (sg * g5["rel_fwd_1"]).mean(), "signed_rel_fwd_5": (sg * g5["rel_fwd_5"]).mean(),
               "signed_rel_fwd_10": (sg * g5["rel_fwd_10"].dropna()).mean(), "n_fwd_10": int(g5["rel_fwd_10"].notna().sum()),
               "share_prior5_label_direction": float(((sg * g5["rel_prior_5"]) > 0).mean()),
               "share_fwd5_label_direction": float(((sg * g5["rel_fwd_5"]) > 0).mean()),
               "corr_prior5_fwd5": float(np.corrcoef(g5["rel_prior_5"], g5["rel_fwd_5"])[0, 1]),
               "power": power(len(g5))})
LL = pd.DataFrame(ll)
LL.to_csv(os.path.join(PROBES, "p21_M1_usmi_leadlag.csv"), index=False)
U.to_csv(os.path.join(SCR, "label_obs_with_returns.csv"), index=False)
print(E[E.h.isin([1, 3, 5, 10, 15])].round(4).to_string())
print(LL.round(4).to_string())
print("runtime", round(time.time() - tc, 1))
