"""4.4 Outcome census. Read-only. Decisions (ledger + presented candidates in run books), resolved outcomes,
OHLC reconstructability, and bucket population (hidden_state x phase x compression x direction x horizon)."""
import os, json, glob, sqlite3, re, math
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
RUNS = os.path.join(ROOT, "data", "output", "runs")

# ---------- ledger ----------
con = sqlite3.connect("file:" + os.path.join(OUT, "db_copies", "decision_outcome_ledger.sqlite") + "?mode=ro", uri=True)
led = pd.read_sql("select event_id, event_type, run_id, ticker, thesis_id, occurred_at_utc, payload_json from ledger_events", con)
led["direction"] = led.payload_json.map(lambda s: (json.loads(s).get("direction") or "OTHER") if s else "OTHER")
led_ct = led.groupby(["run_id", "event_type", "direction"]).size().reset_index(name="n")
led_ct.to_csv(os.path.join(OUT, "probes", "p31_ledger_events_by_run.csv"), index=False)
cand = led[led.event_type == "CANDIDATE_DECISION"].copy()
pay = cand.payload_json.map(json.loads)
for k in ["target_price", "invalidation_price", "reference_price", "planned_hold_sessions", "thesis_state", "final_action", "decision_stage"]:
    cand[k] = pay.map(lambda d, k=k: d.get(k))
outc = led[led.event_type.isin(["OUTCOME", "OUTCOME_OBSERVATION"])]
print("ledger CANDIDATE_DECISION:", len(cand), "unique (run,ticker,direction):", cand.drop_duplicates(["run_id", "ticker", "direction"]).shape[0])
print("ledger outcomes:", len(outc), outc.event_type.value_counts().to_dict())
print("planned_hold_sessions non-null:", int(cand.planned_hold_sessions.notna().sum()), " target non-null:", int(cand.target_price.notna().sum()), " invalidation non-null:", int(cand.invalidation_price.notna().sum()))
print("ledger candidate direction:", cand.direction.value_counts().to_dict())

# ---------- presented candidates in run books ----------
pcon = sqlite3.connect("file:" + os.path.join(OUT, "db_copies", "historical_prices.sqlite") + "?mode=ro", uri=True)
dates = pd.read_sql("select distinct trading_date from ohlcv_daily where trading_date >= '2026-07-01' order by 1", pcon).trading_date.tolist()


def sessions_after(d, h):
    later = [x for x in dates if x > d]
    return later[:h]


CANDS_SPOT = ["origin_spot", "entry_price", "stock_price", "current_price", "underlying_price", "close", "last_price", "price", "reference_price", "spot", "current_close", "last_close"]
rows = []
runs = sorted([r for r in os.listdir(RUNS) if re.match(r"\d{8}_\d{6}$", r)])
for rid in runs:
    fob = glob.glob(os.path.join(RUNS, rid, "intelligence_lab", "final_opportunity_book_*.csv"))
    if not fob:
        continue
    hdr = pd.read_csv(fob[0], nrows=0).columns.tolist()

    def pick(*names):
        for n in names:
            if n in hdr:
                return n
        return None

    c_dir = pick("governed_direction", "final_direction", "direction", "canonical_direction")
    c_hs = pick("hidden_state_label", "hidden_state")
    c_ph = pick("phase")
    c_ce = pick("compression_energy", "compression_score")
    c_tg = pick("structural_target", "target_price", "target_spot")
    c_inv = pick("invalidation_price", "invalidation_spot", "governed_invalidation_spot", "stop_loss")
    c_hold = pick("hold_period", "planned_hold_sessions", "hold_days", "time_horizon", "hold_window")
    c_vol = pick("garch_forecast_vol", "l3_forward_realised_vol", "forward_realised_vol")
    c_spot = pick(*CANDS_SPOT)
    c_thesis = pick("thesis_id")
    c_verdict = pick("lab_verdict")
    use = [c for c in ["ticker", c_dir, c_hs, c_ph, c_ce, c_tg, c_inv, c_hold, c_vol, c_spot, c_thesis, c_verdict] if c]
    df = pd.read_csv(fob[0], usecols=use, low_memory=False)
    meta = {}
    mp = os.path.join(RUNS, rid, "run_meta.json")
    if os.path.exists(mp):
        try:
            meta = json.load(open(mp, encoding="utf-8"))
        except Exception:
            pass
    dsess = (meta.get("dynamic_plan") or {}).get("last_completed_session")
    if not dsess:
        rdate = rid[:4] + "-" + rid[4:6] + "-" + rid[6:8]
        prior = [x for x in dates if x < rdate]
        dsess = prior[-1] if prior else None
    for _, r in df.iterrows():
        rows.append(dict(run_id=rid, decision_session=dsess, ticker=r["ticker"], direction=(r[c_dir] if c_dir else None),
                         hidden_state=(r[c_hs] if c_hs else None), phase=(r[c_ph] if c_ph else None), compression=(r[c_ce] if c_ce else None),
                         target=(r[c_tg] if c_tg else None), invalidation=(r[c_inv] if c_inv else None), hold=(r[c_hold] if c_hold else None),
                         vol=(r[c_vol] if c_vol else None), spot=(r[c_spot] if c_spot else None), thesis_id=(r[c_thesis] if c_thesis else None),
                         verdict=(r[c_verdict] if c_verdict else None), spot_col=c_spot, hold_col=c_hold))
    print(rid, "book rows", len(df), "cols:", dict(dir=c_dir, hs=c_hs, ph=c_ph, ce=c_ce, tg=c_tg, inv=c_inv, hold=c_hold, vol=c_vol, spot=c_spot))

P = pd.DataFrame(rows)
P["direction"] = P.direction.where(P.direction.isin(["CALL", "PUT"]), "OTHER")


def hold_sessions(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v)
    m = re.findall(r"\d+", s)
    if not m:
        return None
    return int(m[-1]) if ("-" in s or "_" in s) else int(m[0])


P["hold_sessions"] = P.hold.map(hold_sessions)
P["horizon_bucket"] = pd.cut(P.hold_sessions, [0, 5, 10, 20, 1000], labels=["1-5", "6-10", "11-20", ">20"])
ce = pd.to_numeric(P.compression, errors="coerce")
P["compression_bucket"] = pd.qcut(ce, 3, labels=["LOW", "MID", "HIGH"], duplicates="drop") if ce.notna().sum() > 10 else None


def recon(r):
    if r.direction == "OTHER" or r.hold_sessions is None or r.decision_session is None or pd.isna(r.hold_sessions):
        return "NOT_DIRECTED_OR_NO_HOLD"
    if pd.isna(r.target) or pd.isna(r.invalidation) or pd.isna(r.spot):
        return "MISSING_GEOMETRY"
    w = sessions_after(r.decision_session, int(r.hold_sessions))
    if len(w) == 0:
        return "WINDOW_NOT_STARTED"
    if len(w) < int(r.hold_sessions):
        return "PARTIAL_" + str(len(w)) + "_of_" + str(int(r.hold_sessions))
    return "FULL_WINDOW_AVAILABLE"


P["reconstructable"] = P.apply(recon, axis=1)
P.to_csv(os.path.join(OUT, "probes", "p31_presented_candidates.csv"), index=False)
print("\nPRESENTED rows:", len(P), "runs:", P.run_id.nunique(), "directed:", int((P.direction != "OTHER").sum()))
print("direction:", P.direction.value_counts().to_dict())
print("reconstructable:", P.reconstructable.map(lambda s: "PARTIAL" if s.startswith("PARTIAL") else s).value_counts().to_dict())
D = P[(P.direction != "OTHER")]
print("geometry present (directed):", D[["target", "invalidation", "spot", "vol"]].notna().mean().round(3).to_dict())
print("hold values (directed):", D.hold.astype(str).value_counts().head(12).to_dict())
tick = set(D.ticker.dropna())
cov = pd.read_sql("select ticker, count(*) n from ohlcv_daily where trading_date >= '2026-07-01' group by ticker", pcon)
print("tickers in directed set:", len(tick), "with price rows since Jul:", len(tick & set(cov.ticker)))
keys = ["hidden_state", "phase", "compression_bucket", "direction", "horizon_bucket"]
B = D.groupby(keys, dropna=False, observed=True).size().reset_index(name="n").sort_values("n", ascending=False)
B.to_csv(os.path.join(OUT, "probes", "p31_bucket_population.csv"), index=False)
F = D[D.reconstructable == "FULL_WINDOW_AVAILABLE"]
Bf = F.groupby(keys, dropna=False, observed=True).size().reset_index(name="n").sort_values("n", ascending=False)
Bf.to_csv(os.path.join(OUT, "probes", "p31_bucket_population_fullwindow.csv"), index=False)
for name, T in [("ALL PRESENTED DIRECTED", B), ("FULL WINDOW RECONSTRUCTABLE", Bf)]:
    print("\n" + name + ": buckets=" + str(len(T)) + " n>=200: " + str(int((T.n >= 200).sum())) + " n>=100: " + str(int((T.n >= 100).sum())) + " n>=50: " + str(int((T.n >= 50).sum())) + " modal n=" + str(int(T.n.max())) + " median n=" + str(T.n.median()))
    print(T.head(12).to_string())
for kk in (["direction", "horizon_bucket"], ["hidden_state", "direction"], ["direction"]):
    T = F.groupby(kk, dropna=False, observed=True).size().reset_index(name="n")
    print("\ncoarse", kk, "\n", T.to_string())
U = D.drop_duplicates(["ticker", "direction", "decision_session"])
print("\nunique (ticker,direction,session) directed:", len(U), " full-window:", int((U.reconstructable == "FULL_WINDOW_AVAILABLE").sum()))
Uf = U[U.reconstructable == "FULL_WINDOW_AVAILABLE"]
T = Uf.groupby(keys, dropna=False, observed=True).size().reset_index(name="n").sort_values("n", ascending=False)
T.to_csv(os.path.join(OUT, "probes", "p31_bucket_population_unique_fullwindow.csv"), index=False)
print("UNIQUE full-window buckets=", len(T), " n>=200:", int((T.n >= 200).sum()), " n>=100:", int((T.n >= 100).sum()), " n>=50:", int((T.n >= 50).sum()), " modal:", int(T.n.max()) if len(T) else 0)
print(T.head(10).to_string())
