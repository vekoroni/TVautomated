"""Analysis for the historical replay study, exactly as pre-registered in
Enhancements/assessment/AVS_HISTORICAL_REPLAY_STUDY_PREREGISTRATION_20260929.md (incl. the addendum).

Inputs: replay_rows.parquet + replay_paths.npy from ticker_edge_replay_20260929.py.
Steps: (1) derive the trigger and physics layers from the replayed rows with the live functions; (2) signed paths
and the same-session universe baseline; (3) per segment and hold 1..40: lift, option return on the path;
(4) choose the hold on DISCOVERY (<= 2024-12-31), confirm on VALIDATION (2025), report TEST (2026) once;
(5) block bootstrap over non-overlapping 20-trading-session blocks. Read-only; writes CSVs next to the inputs.

  venv\\Scripts\\python.exe Enhancements\\direction_evidence\\ticker_edge_replay_analysis_20260929.py REPLAY_DIR
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import trigger_layer  # noqa: E402
from vanguard.physics_state_engine import calculate_market_physics  # noqa: E402

D = Path(sys.argv[1])
MAXH = 40
DISC_END, VAL_END = "2024-12-31", "2025-12-31"
HALF_SPREAD, RATE, IV_OVER_RV, DTE, ITM = 0.03, 0.04, 1.10, 90, 0.05
rng = np.random.default_rng(29)
pd.set_option("display.width", 260)
pd.set_option("display.max_rows", 400)

rows = pd.read_parquet(D / "replay_rows.parquet")
paths = np.load(D / "replay_paths.npy")          # (n, 3, MAXH): close, high, low relative to entry (long side)
assert len(rows) == len(paths)
# Look-ahead guard: drop every field the scan fills from today's macro/regime/sector files.
LOOKAHEAD = ("macro", "usmi", "regime", "vix", "liquidity_pulse", "rates_impulse", "usd_", "credit_state",
             "dealer_gamma", "sector_rotation", "leading_sectors", "lagging_sectors", "avoid_sectors",
             "preferred_sectors", "ticker_sector_alignment", "horizon_pressure", "vms_", "scanner_", "bond_",
             "prior_adjustment", "prior_label", "catalyst", "news_", "signal_detected", "lss_")
rows = rows[[c for c in rows.columns if not any(t in c.lower() for t in LOOKAHEAD)]]
print("rows", len(rows), "tickers", rows["ticker"].nunique(), "sessions", rows["session"].nunique(), flush=True)

# ---- (1) price inputs for physics, realised vol for the option step (same bars, point in time) --------------------
con = sqlite3.connect(f"file:{(ROOT / 'data/canonical/historical_prices.sqlite').as_posix()}?mode=ro", uri=True)
bars = pd.read_sql_query("select ticker, trading_date d, close, volume from ohlcv_daily where bar_status='COMPLETE' "
                         "order by ticker, trading_date", con)
feat = []
for tk, g in bars.groupby("ticker", sort=False):
    c = g["close"].to_numpy(float)
    v = g["volume"].to_numpy(float)
    if len(c) < 30:
        continue
    lr = np.r_[np.nan, np.diff(np.log(np.where(c > 0, c, np.nan)))]
    s = pd.Series(lr)
    feat.append(pd.DataFrame({
        "ticker": tk, "session": g["d"].to_numpy(),
        "return_5d": c / np.r_[np.full(5, np.nan), c[:-5]] - 1,
        "return_10d": c / np.r_[np.full(10, np.nan), c[:-10]] - 1,
        "avg_volume": pd.Series(v).rolling(20).mean().to_numpy(),
        "rv20": s.rolling(20).std().to_numpy() * np.sqrt(252)}))
feat = pd.concat(feat, ignore_index=True)
rows = rows.reset_index(drop=True).merge(feat, on=["ticker", "session"], how="left")


def plain(r: dict) -> dict:
    out = {}
    for k, v in r.items():
        key = k[3:] if k.startswith(("x__", "l__")) else k
        if isinstance(v, float) and np.isnan(v):
            continue
        out[key] = v
    return out


trig_primary, trig_quality, trig_score, energy, force, align, comp = [], [], [], [], [], [], []
for r in rows.to_dict("records"):
    p = plain(r)
    t = trigger_layer.evaluate_triggers(p)
    trig_primary.append(trigger_layer.trigger_primary(t))
    trig_quality.append(trigger_layer.trigger_quality(t))
    trig_score.append(trigger_layer._trigger_score(t))
    ph = calculate_market_physics(p, macro_context={})
    energy.append(ph.get("market_energy_score"))
    force.append(ph.get("directional_force"))
    align.append(ph.get("force_alignment_score"))
    comp.append(ph.get("compression_energy"))
rows["trigger_primary"], rows["trigger_quality"], rows["trigger_score"] = trig_primary, trig_quality, trig_score
rows["market_energy_score"], rows["directional_force"] = energy, force
rows["force_alignment_score"], rows["compression_energy"] = align, comp
print("trigger primaries:", rows["trigger_primary"].value_counts().to_dict(), flush=True)

# ---- (2) signals, signed paths, universe baseline ------------------------------------------------------------------
direction = rows.get("l__discovery_direction_preliminary", pd.Series("", index=rows.index)).astype(str).str.upper()
rows["direction"] = direction
sgn = np.where(direction == "CALL", 1.0, np.where(direction == "PUT", -1.0, np.nan))
close_long = paths[:, 0, :]
signed = close_long * sgn[:, None]
sess = rows["session"].to_numpy()
base_long = pd.DataFrame(close_long).groupby(sess).transform("mean").to_numpy()   # all replayed rows that session
lift = signed - base_long * sgn[:, None]

# option on the path: ITM 90-day, BS at realised vol x 1.10, ask entry / bid exit
entry = rows["entry"].to_numpy(float)
sigma = np.clip(rows["rv20"].to_numpy(float) * IV_OVER_RV, 0.08, 3.0)
call = direction.to_numpy() == "CALL"
K = entry * np.where(call, 1 - ITM, 1 + ITM)


def bs(S, T, sig):
    T = np.maximum(T, 1e-6)
    d1 = (np.log(S / K) + (RATE + 0.5 * sig ** 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    cv = S * ndtr(d1) - K * np.exp(-RATE * T) * ndtr(d2)
    return np.where(call, cv, cv - S + K * np.exp(-RATE * T))


ask0 = bs(entry, DTE / 365, sigma) * (1 + HALF_SPREAD)
opt = np.full_like(signed, np.nan)
for h in range(1, MAXH + 1):
    S = entry * (1 + close_long[:, h - 1])
    opt[:, h - 1] = bs(S, (DTE - h * 7 / 5) / 365, sigma) * (1 - HALF_SPREAD) / ask0 - 1

is_signal = ~np.isnan(sgn)
period = np.where(sess <= DISC_END, "DISC", np.where(sess <= VAL_END, "VAL", "TEST"))
all_sessions = np.array(sorted(rows["session"].unique()))
block_of = {s: i // 4 for i, s in enumerate(all_sessions)}     # 4 evaluation sessions (every 5th) = 20 trading sessions
block = np.array([block_of[s] for s in sess])


def measure(mask, h, values):
    m = mask & ~np.isnan(values[:, h - 1])
    if m.sum() == 0:
        return np.nan, np.nan, np.nan, 0, 0
    v, b = values[m, h - 1], block[m]
    uniq, inv = np.unique(b, return_inverse=True)
    sums, cnt = np.bincount(inv, weights=v), np.bincount(inv)
    point = sums.sum() / cnt.sum()
    if len(uniq) >= 3:
        pk = rng.integers(0, len(uniq), size=(500, len(uniq)))
        bt = sums[pk].sum(1) / cnt[pk].sum(1)
        lo, hi = np.percentile(bt, [5, 95])
    else:
        lo = hi = np.nan
    return float(point), float(lo), float(hi), int(m.sum()), len(uniq)


# ---- (3) segments ------------------------------------------------------------------------------------------------
segments: dict[str, np.ndarray] = {"ALL_SIGNALS": is_signal}
for d in ("CALL", "PUT"):
    segments[f"direction={d}"] = is_signal & (direction.to_numpy() == d)
CAT = ["l__phase", "l__precor_intent", "l__wyckoff_phase_bucket", "l__wyckoff_mode", "l__wyckoff_setup_quality",
       "l__wyckoff_execution_bias", "l__wyckoff_validation_phase_status", "l__crabel_state", "l__crabel_pattern",
       "l__control_state", "l__dominant_trend", "l__ema_stack", "l__vwap_bias", "l__tier_label",
       "l__horizon_bucket_discovery", "l__signal_type", "l__fusion_rule_fired", "l__dominant_event",
       "trigger_primary", "trigger_quality"]
for a in CAT:
    if a not in rows:
        continue
    vals = rows[a].astype(str).str.upper()
    for v, n in vals[is_signal].value_counts().items():
        if v in ("", "NAN", "NONE") or n < 1000:
            continue
        segments[f"{a.replace('l__', '')}={v}"] = is_signal & (vals.to_numpy() == v)
NUM = ["x__composite", "x__crabel_compression", "x__adx_14", "x__atr_percentile_rank", "x__volume_ratio",
       "x__phase_evidence_strength", "compression_energy", "market_energy_score", "force_alignment_score", "trigger_score"]
for a in NUM:
    if a not in rows:
        continue
    x = pd.to_numeric(rows[a], errors="coerce")
    q = x.where(is_signal).groupby(rows["session"]).rank(pct=True).to_numpy()
    segments[f"{a.replace('x__', '')}:top_third"] = is_signal & (q > 2 / 3)
    segments[f"{a.replace('x__', '')}:bottom_third"] = is_signal & (q <= 1 / 3)
# aligned directional force (signed with the signal)
af = pd.to_numeric(rows["directional_force"], errors="coerce").to_numpy() * sgn
qa = pd.Series(af).where(is_signal).groupby(rows["session"]).rank(pct=True).to_numpy()
# pre-listed combinations
lab = lambda c: rows[c].astype(str).str.upper().to_numpy() if c in rows else np.array([""] * len(rows))  # noqa: E731
dirn, trig, phase, precor, trend, crab = (direction.to_numpy(), lab("trigger_primary"), lab("l__phase"),
                                          lab("l__precor_intent"), lab("l__dominant_trend"), lab("l__crabel_state"))
up_trend = np.char.find(trend.astype(str), "UP") >= 0
down_trend = np.char.find(trend.astype(str), "DOWN") >= 0
for d in ("CALL", "PUT"):
    segments[f"COMBO1 RANGE_BREAK & {d}"] = is_signal & (trig == "RANGE_BREAK") & (dirn == d)
    segments[f"COMBO2 RANGE_BREAK_EARLY & {d}"] = is_signal & (trig == "RANGE_BREAK_EARLY") & (dirn == d)
    segments[f"COMBO3 phase D & {d}"] = is_signal & (phase == "D") & (dirn == d)
segments["COMBO4 BUY_SETUP & CALL & trend up"] = is_signal & (precor == "BUY_SETUP") & (dirn == "CALL") & up_trend
segments["COMBO4 SELL_SETUP & PUT & trend down"] = is_signal & (precor == "SELL_SETUP") & (dirn == "PUT") & down_trend
segments["COMBO5 Crabel READY/COILING & VOL_COMPRESSION"] = (is_signal & np.isin(crab, ["CRABEL_READY", "COILING", "READY"])
                                                             & (trig == "VOL_COMPRESSION"))
segments["COMBO7 aligned directional force top third"] = is_signal & (qa > 2 / 3)
print("segments:", len(segments), flush=True)

# ---- (4) choose hold on DISC, confirm on VAL, report TEST ----------------------------------------------------------
records = []
for name, m in segments.items():
    if m.sum() < 300:
        continue
    best = None
    for h in range(1, MAXH + 1):
        l, lo, hi, n, nb = measure(m & (period == "DISC"), h, lift)
        if n >= 200 and nb >= 5 and not np.isnan(l) and (best is None or l > best[1]):
            best = (h, l, lo, hi, n, nb)
    if best is None:
        continue
    h = best[0]
    rec = {"segment": name, "hold": h, "disc_n": best[4], "disc_blocks": best[5], "disc_lift": best[1],
           "disc_lo": best[2], "disc_hi": best[3]}
    for per in ("DISC", "VAL", "TEST"):
        l, lo, hi, n, nb = measure(m & (period == per), h, lift)
        o, olo, ohi, _, _ = measure(m & (period == per), h, opt)
        pos = opt[m & (period == per), h - 1]
        pos = pos[~np.isnan(pos)]
        uni = opt[is_signal & (period == per), h - 1]
        uni = uni[~np.isnan(uni)]
        rec.update({f"{per.lower()}_n": n, f"{per.lower()}_lift": l, f"{per.lower()}_lift_lo": lo,
                    f"{per.lower()}_lift_hi": hi, f"{per.lower()}_opt_ev": o, f"{per.lower()}_opt_lo": olo,
                    f"{per.lower()}_opt_hi": ohi,
                    f"{per.lower()}_share_opt_pos": float((pos > 0).mean()) if len(pos) else np.nan,
                    f"{per.lower()}_universe_share_opt_pos": float((uni > 0).mean()) if len(uni) else np.nan})
    rec["passes_preregistered"] = bool(
        rec["disc_lo"] > 0 and rec.get("val_lift_lo", -1) > 0 and rec.get("test_lift", -1) > 0
        and rec.get("val_share_opt_pos", 0) - rec.get("val_universe_share_opt_pos", 1) >= 0.05)
    records.append(rec)
res = pd.DataFrame(records).sort_values("disc_lift", ascending=False)
res.to_csv(D / "segment_results.csv", index=False)

# population profile by hold (all signals)
prof = []
for h in range(1, MAXH + 1):
    rec = {"hold": h}
    for per in ("DISC", "VAL", "TEST"):
        l, lo, hi, n, _ = measure(is_signal & (period == per), h, lift)
        o, *_ = measure(is_signal & (period == per), h, opt)
        r, *_ = measure(is_signal & (period == per), h, signed)
        rec.update({f"{per}_n": n, f"{per}_ret": r, f"{per}_lift": l, f"{per}_opt": o})
    prof.append(rec)
pd.DataFrame(prof).to_csv(D / "population_by_hold.csv", index=False)

np.savez_compressed(D / "per_signal_arrays.npz", lift=lift.astype(np.float32), opt=opt.astype(np.float32),
                    signed=signed.astype(np.float32), is_signal=is_signal, period=period, block=block, session=sess,
                    extreme=rows["extreme_forward_gap"].to_numpy(bool), direction=direction.to_numpy())
pd.DataFrame({name: m for name, m in segments.items()}).to_parquet(D / "segment_masks.parquet", index=False)

cols = ["segment", "hold", "disc_n", "disc_lift", "disc_lo", "val_n", "val_lift", "val_lift_lo", "test_n", "test_lift",
        "val_opt_ev", "test_opt_ev", "val_share_opt_pos", "val_universe_share_opt_pos", "passes_preregistered"]
print("\n== Population by hold (every 5th hold) ==")
print(pd.DataFrame(prof).iloc[[0, 1, 2, 4, 9, 14, 19, 29, 39]].round(4).to_string(index=False))
print("\n== Segments (hold chosen on discovery) ==")
print(res[cols].round(4).to_string(index=False))
print("\n== Passing the pre-registered criterion ==")
print(res[res["passes_preregistered"]][cols].round(4).to_string(index=False))
