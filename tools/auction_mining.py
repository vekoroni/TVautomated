"""AVSHUNTER auction and participant mining (research tool, 19 Oct 2026).

Reads the canonical daily price store (read-only) and Polygon intraday bars, and writes,
per ticker, an auction map: one chapter per timeframe (monthly to 30m, plus the last
session's 5m tape proxy), buyer and seller zones with confidence labels, level states,
session TPO facts, auction memory, the cross-timeframe pattern, the combined story and
the up / down / balance branches the trade card and the watch board use.

It never writes to the pipeline's data. Outputs go only to
    data/scratch/workaround/mining/auction/<date>/<TICKER>_auction.json and .md
    data/scratch/workaround/mining/auction/memory/<TICKER>.json   (auction memory)
    data/scratch/workaround/mining/auction/intraday/<TICKER>_<n>m.csv (bar cache)

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe tools\\auction_mining.py ASO CAVA CBRL D
Options: --intraday-sessions 20 (30m history), --no-intraday (daily only),
         --prices-csv <file> (use a ticker pack's prices_ohlcv_daily.csv instead of the store),
         --intraday-csv <file> (30m bars from a file: timestamp_utc,open,high,low,close,volume),
         --out <folder> (override the output root).

Confidence: zones from daily and 30m bars reach PROBABLE at most. CONFIRMED needs tape
(executions and bid/offer replenishment), which no source here supplies. Every number
carries its clock. Participant horizons are inferred, never asserted.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRICE_DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
OUT_ROOT = ROOT / "data" / "scratch" / "workaround" / "mining" / "auction"
VERSION = "auction_mining_v1"
ET = "America/New_York"

# Versioned parameters (research seeds, not calibrated thresholds).
P = {
    "lookback": 20,            # bars for range, profile and event windows
    "profile_bins": 60,
    "value_share": 0.70,
    "climax_range_atr": 1.5, "climax_vol_x": 2.0,
    "absorb_vol_x": 1.5, "absorb_range_atr": 0.6,
    "zone_merge_atr": 0.30, "test_atr": 0.25,
    "balance_migration_atr": 0.25,
    "hvn_pct": 85, "lvn_pct": 15,
    "zone_keep_atr": 6.0,      # zones further than this from price are dropped from the map
    "zone_max_atr": 0.8,       # widest single-event zone
    "merge_max_atr": 1.0,      # widest merged zone
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def r2(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), 2)


# ----------------------------------------------------------------------------- loading
def load_daily(ticker: str, prices_csv: str | None) -> tuple[pd.DataFrame, dict]:
    if prices_csv:
        df = pd.read_csv(prices_csv)
        src = {"source": prices_csv, "kind": "ticker pack csv"}
    else:
        if not PRICE_DB.exists():
            sys.exit(f"Price store not found: {PRICE_DB}")
        with sqlite3.connect(f"file:{PRICE_DB.as_posix()}?mode=ro", uri=True) as con:
            df = pd.read_sql_query(
                "SELECT ticker, trading_date, open, high, low, close, volume, adjustment_convention "
                "FROM ohlcv_daily WHERE bar_status='COMPLETE' AND ticker=? AND trading_date >= ? "
                "ORDER BY trading_date", con, params=[ticker, "2021-01-01"])
        src = {"source": str(PRICE_DB), "kind": "canonical store (read-only)"}
    if "ticker" in df:
        df = df[df["ticker"].astype(str).str.upper() == ticker]
    df = df.sort_values("trading_date").drop_duplicates("trading_date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["trading_date"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    src["rows"] = len(df)
    src["last_session"] = df["trading_date"].iloc[-1] if len(df) else None
    src["price_basis"] = str(df["adjustment_convention"].iloc[-1]) if "adjustment_convention" in df and len(df) else "unknown"
    return df, src


def load_intraday(ticker: str, minutes: int, sessions: int, csv_path: str | None, cache_dir: Path) -> tuple[pd.DataFrame | None, dict]:
    """30m (or 5m) bars, regular and extended hours, as ET timestamps."""
    info = {"minutes": minutes}
    df = None
    if csv_path:
        df = pd.read_csv(csv_path); info["source"] = csv_path
        df["timestamp"] = pd.to_datetime(df.get("timestamp_utc", df.get("timestamp")), utc=True)
    else:
        try:
            sys.path.insert(0, str(ROOT))
            from polygon_data_fetcher import PolygonDataFetcher  # owner of Polygon access
            fetcher = PolygonDataFetcher()
            to_d = datetime.now().date(); from_d = to_d - timedelta(days=int(sessions * 1.6) + 4)
            df = fetcher.fetch_intraday_bars(ticker, minutes, "minute", from_d.isoformat(), to_d.isoformat())
            info["source"] = "Polygon aggregates via polygon_data_fetcher.py"
            if df is not None and len(df):
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                cache_dir.mkdir(parents=True, exist_ok=True)
                df.assign(timestamp_utc=df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))[
                    ["timestamp_utc", "open", "high", "low", "close", "volume"]].to_csv(
                    cache_dir / f"{ticker}_{minutes}m.csv", index=False)
        except Exception as exc:  # missing key, network, import: missing is never neutral
            info["status"] = f"MISSING: {type(exc).__name__}: {exc}"
            return None, info
    if df is None or not len(df):
        info["status"] = info.get("status", "MISSING: no bars returned")
        return None, info
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["et"] = df["timestamp"].dt.tz_convert(ET)
    df["session"] = df["et"].dt.date
    t = df["et"].dt.hour * 60 + df["et"].dt.minute
    df["segment"] = np.where((t >= 570) & (t < 960), "REGULAR", np.where(t < 570, "PRE", "POST"))
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    keep = sorted(df.loc[df.segment == "REGULAR", "session"].unique())[-sessions:]
    df = df[df["session"].isin(keep) | (df["session"] > (keep[-1] if keep else df["session"].max()))]
    info["status"] = "PRESENT"
    info["sessions"] = len(keep)
    info["last_bar_et"] = df["et"].iloc[-1].strftime("%Y-%m-%d %H:%M ET")
    return df.reset_index(drop=True), info


# ----------------------------------------------------------------------------- frames
def resample_daily(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.set_index("date").resample(rule)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum()}).dropna()
    out = out.reset_index().rename(columns={"date": "date"})
    return out


def intraday_frame(intra: pd.DataFrame, minutes: int) -> pd.DataFrame:
    reg = intra[intra.segment == "REGULAR"].copy()
    if minutes == 30:
        out = reg[["et", "open", "high", "low", "close", "volume", "session"]].rename(columns={"et": "date"})
        return out.reset_index(drop=True)
    rows = []
    for s, day in reg.groupby("session"):
        day = day.sort_values("et")
        mins = day["et"].dt.hour * 60 + day["et"].dt.minute - 570
        bucket = (mins // minutes) if minutes == 60 else np.where(mins < 240, 0, 1)  # 4h: 09:30-13:30, 13:30-16:00
        for b, part in day.groupby(np.asarray(bucket)):
            rows.append({"date": part["et"].iloc[0], "open": part["open"].iloc[0], "high": part["high"].max(),
                         "low": part["low"].min(), "close": part["close"].iloc[-1], "volume": part["volume"].sum(),
                         "session": s})
    return pd.DataFrame(rows)


def add_indicators(f: pd.DataFrame) -> pd.DataFrame:
    f = f.copy()
    pc = f["close"].shift(1)
    tr = np.maximum.reduce([f["high"] - f["low"], (f["high"] - pc).abs(), (f["low"] - pc).abs()])
    f["atr"] = pd.Series(tr).rolling(14, min_periods=5).mean().values
    f["vol20"] = f["volume"].rolling(20, min_periods=5).mean().shift(1)
    f["ma20"] = f["close"].rolling(20, min_periods=10).mean()
    f["ma50"] = f["close"].rolling(50, min_periods=20).mean()
    return f


# ----------------------------------------------------------------------------- profile
def profile(df: pd.DataFrame, bins: int = P["profile_bins"]) -> dict | None:
    if df is None or len(df) < 3:
        return None
    lo, hi = float(df["low"].min()), float(df["high"].max())
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1); vol = np.zeros(bins); tpo = np.zeros(bins)
    for row in df.itertuples(index=False):
        a = max(int(np.searchsorted(edges, row.low, "right") - 1), 0)
        b = min(max(int(np.searchsorted(edges, row.high, "left")), a + 1), bins)
        vol[a:b] += row.volume / (b - a); tpo[a:b] += 1
    poc = int(vol.argmax()); total = vol.sum(); s = vol[poc]; li = hi_i = poc
    while s < P["value_share"] * total and (li > 0 or hi_i < bins - 1):
        up = vol[hi_i + 1] if hi_i + 1 < bins else -1; dn = vol[li - 1] if li > 0 else -1
        if up >= dn: hi_i += 1; s += up
        else: li -= 1; s += dn
    t_hi, t_lo = np.percentile(vol, P["hvn_pct"]), np.percentile(vol, P["lvn_pct"])

    def zones(mask):
        out, k = [], 0
        while k < bins:
            if mask[k]:
                j = k
                while j + 1 < bins and mask[j + 1]: j += 1
                out.append([r2(edges[k]), r2(edges[j + 1])]); k = j + 1
            else:
                k += 1
        return out
    mid = (edges[:-1] + edges[1:]) / 2
    top = df["high"].max(); bot = df["low"].min()
    return {"poc": r2(mid[poc]), "val": r2(edges[li]), "vah": r2(edges[hi_i + 1]),
            "hvn": zones(vol >= t_hi), "lvn": zones((vol <= t_lo) & (vol > 0)),
            "poor_high": bool((df["high"] >= top - (hi - lo) / bins).sum() >= 2),
            "poor_low": bool((df["low"] <= bot + (hi - lo) / bins).sum() >= 2),
            "high": r2(top), "low": r2(bot)}


# ----------------------------------------------------------------------------- swings and structure
def swings(f: pd.DataFrame, k: int = 2) -> tuple[list, list]:
    h, l = f["high"].values, f["low"].values; hs, ls = [], []
    for i in range(k, len(f) - k):
        if h[i] == h[i - k:i + k + 1].max(): hs.append((i, h[i]))
        if l[i] == l[i - k:i + k + 1].min(): ls.append((i, l[i]))
    return hs, ls


def structure(f: pd.DataFrame) -> str:
    hs, ls = swings(f.tail(60).reset_index(drop=True))
    if len(hs) < 2 or len(ls) < 2:
        return "insufficient swings"
    hh, hl = hs[-1][1] > hs[-2][1], ls[-1][1] > ls[-2][1]
    last = float(f["close"].iloc[-1]); top2, bot2 = max(hs[-1][1], hs[-2][1]), min(ls[-1][1], ls[-2][1])
    if last > top2: return "breaking out (closing above the last two swing highs)" + ("" if hl else " after lower lows")
    if last < bot2: return "breaking down (closing below the last two swing lows)" + ("" if not hh else " after higher highs")
    if hh and hl: return "uptrend (higher highs and higher lows)"
    if not hh and not hl: return "downtrend (lower highs and lower lows)"
    if hh and not hl: return "expanding range (higher high, lower low)"
    return "contracting range (lower high, higher low)"


# ----------------------------------------------------------------------------- zones
def mine_zones(f: pd.DataFrame, tf: str, prof60: dict | None, prof_prev: dict | None) -> list[dict]:
    """Probable / suspected buyer and seller zones from bars. Never CONFIRMED (no tape)."""
    z = []; N = P["lookback"]; n = len(f)
    h, l, c, o, v = (f[k].values for k in ("high", "low", "close", "open", "volume"))
    atr, v20 = f["atr"].values, f["vol20"].values
    dates = f["date"].astype(str).str[:16].values
    start = max(N + 1, n - 250)

    def add(side, lo, hi, kind, i, ev):
        lo, hi = float(min(lo, hi)), float(max(lo, hi)); a_ = float(atr[-1]); cap = P["zone_max_atr"] * a_
        if hi - lo > cap:                       # keep the defended edge: the low for buyers, the high for sellers
            lo, hi = (lo, lo + cap) if side == "buyers" else (hi - cap, hi)
        z.append({"side": side, "low": lo, "high": hi, "kinds": [kind],
                  "events": [f"{dates[i]} {ev}"], "origin_i": i, "tf": tf})
    for i in range(start, n):
        a = atr[i] if atr[i] and np.isfinite(atr[i]) else (h[i] - l[i]); rng = h[i] - l[i]
        vx = v[i] / v20[i] if v20[i] and np.isfinite(v20[i]) and v20[i] > 0 else np.nan
        lowN, highN = l[i - N:i].min(), h[i - N:i].max()
        if l[i] <= lowN and rng >= P["climax_range_atr"] * a and vx >= P["climax_vol_x"] and c[i] > l[i] + 0.4 * rng:
            add("buyers", l[i], l[i] + 0.3 * rng, "selling climax low", i, f"selling climax: range {rng / a:.1f} ATR, volume {vx:.1f}x, closed off the low")
        if h[i] >= highN and rng >= P["climax_range_atr"] * a and vx >= P["climax_vol_x"] and c[i] < h[i] - 0.4 * rng:
            add("sellers", h[i] - 0.3 * rng, h[i], "buying climax high", i, f"buying climax: range {rng / a:.1f} ATR, volume {vx:.1f}x, closed off the high")
        if l[i] < lowN and c[i] > lowN:
            add("buyers", l[i], lowN, "spring / failed breakdown", i, f"undercut {lowN:.2f} to {l[i]:.2f} and closed back above")
        if h[i] > highN and c[i] < highN:
            add("sellers", highN, h[i], "upthrust / failed breakout", i, f"overshot {highN:.2f} to {h[i]:.2f} and closed back below")
        if i >= 1 and o[i] > h[i - 1] and l[i:].min() > h[i - 1]:
            add("buyers", h[i - 1], min(o[i], l[i]), "open gap support", i, f"gap up from {h[i - 1]:.2f}, still unfilled")
        if i >= 1 and o[i] < l[i - 1] and h[i:].max() < l[i - 1]:
            add("sellers", max(o[i], h[i]), l[i - 1], "open gap resistance", i, f"gap down from {l[i - 1]:.2f}, still unfilled")
        if vx >= P["absorb_vol_x"] and rng <= P["absorb_range_atr"] * a:
            pos = (c[i] - l[i - N:i + 1].min()) / max(h[i - N:i + 1].max() - l[i - N:i + 1].min(), 1e-9)
            if pos < 0.35:
                add("buyers", l[i], h[i], "heavy selling, little decline", i, f"volume {vx:.1f}x on a {rng / a:.1f} ATR bar near the range low (absorption, aggressor side not confirmed)")
            elif pos > 0.65:
                add("sellers", l[i], h[i], "heavy buying, little rise", i, f"volume {vx:.1f}x on a {rng / a:.1f} ATR bar near the range high (absorption, aggressor side not confirmed)")
    # role reversal: a broken swing high retested from above and held, and the mirror
    hs, ls = swings(f.iloc[start - N:].reset_index(drop=True))
    off = start - N
    for j, lvl in hs:
        j += off; after = range(j + 3, n)
        broke = [k for k in after if c[k] > lvl]
        if broke and any(l[k] <= lvl + 0.25 * (atr[k] or 0) and c[k] > lvl for k in range(broke[0] + 1, n)) and c[-1] > lvl:
            add("buyers", lvl - 0.15 * atr[-1], lvl + 0.1 * atr[-1], "old resistance turned support", j, f"swing high {lvl:.2f} broken and retested from above")
    for j, lvl in ls:
        j += off; after = range(j + 3, n)
        broke = [k for k in after if c[k] < lvl]
        if broke and any(h[k] >= lvl - 0.25 * (atr[k] or 0) and c[k] < lvl for k in range(broke[0] + 1, n)) and c[-1] < lvl:
            add("sellers", lvl - 0.1 * atr[-1], lvl + 0.15 * atr[-1], "old support turned resistance", j, f"swing low {lvl:.2f} broken and retested from below")
    price = c[-1]
    if prof60:
        for lo_, hi_ in prof60["hvn"]:
            side = "buyers" if hi_ < price else "sellers" if lo_ > price else None
            if side:
                add(side, lo_, hi_, "high-volume node " + ("below" if side == "buyers" else "above") + " price", n - 1, f"60-bar composite HVN {lo_}-{hi_}")
    if prof_prev:
        if prof_prev["val"] < price:
            add("buyers", prof_prev["val"] - 0.1 * atr[-1], prof_prev["val"] + 0.1 * atr[-1], "prior value-area low", n - 1, f"prior {P['lookback']}-bar VAL {prof_prev['val']}")
        if prof_prev["vah"] > price:
            add("sellers", prof_prev["vah"] - 0.1 * atr[-1], prof_prev["vah"] + 0.1 * atr[-1], "prior value-area high", n - 1, f"prior {P['lookback']}-bar VAH {prof_prev['vah']}")
    return z


def merge_and_grade(z: list[dict], f: pd.DataFrame) -> list[dict]:
    if not z:
        return []
    a = float(f["atr"].iloc[-1]); price = float(f["close"].iloc[-1]); tol = P["zone_merge_atr"] * a
    z = sorted(z, key=lambda d: (d["side"], d["low"])); out = []
    for d in z:
        if out and out[-1]["side"] == d["side"] and d["low"] <= out[-1]["high"] + 0.05 * a and max(out[-1]["high"], d["high"]) - out[-1]["low"] <= P["merge_max_atr"] * a:
            m = out[-1]; m["high"] = max(m["high"], d["high"]); m["low"] = min(m["low"], d["low"])
            m["kinds"] = sorted(set(m["kinds"] + d["kinds"])); m["events"] += d["events"]; m["origin_i"] = min(m["origin_i"], d["origin_i"])
        else:
            out.append(dict(d))
    h, l, c, v, v20 = (f[k].values for k in ("high", "low", "close", "volume", "vol20")); n = len(f)
    graded = []
    for d in out:
        if abs((d["low"] + d["high"]) / 2 - price) > P["zone_keep_atr"] * a:
            continue
        lo, hi = d["low"], d["high"]; tests, held, vols, inside = 0, 0, [], 0; in_visit = False; vis_vol = []
        for k in range(d["origin_i"] + 2, n):
            if d["side"] == "buyers":
                touched = l[k] <= hi + P["test_atr"] * a and h[k] >= lo
            else:
                touched = h[k] >= lo - P["test_atr"] * a and l[k] <= hi
            if k >= n - 20 and lo <= c[k] <= hi: inside += 1
            if touched:
                if not in_visit: tests += 1; in_visit = True; vis_vol = []
                if v20[k] and np.isfinite(v20[k]): vis_vol.append(v[k] / v20[k])
            elif in_visit:                       # the visit ends: did the defending side hold?
                in_visit = False
                held += bool(c[k - 1] > hi if d["side"] == "buyers" else c[k - 1] < lo) or bool(c[k] > hi if d["side"] == "buyers" else c[k] < lo)
                if vis_vol: vols.append(float(np.mean(vis_vol)))
        last_visit_live = in_visit
        through = bool(c[-1] < lo - 0.1 * a) if d["side"] == "buyers" else bool(c[-1] > hi + 0.1 * a)
        if through: state = "traded through (role may flip)"
        elif held >= 2 and held / max(tests, 1) >= 0.5: state = "repeated failure of the other side"
        elif inside >= 3: state = "value built"
        elif tests >= 1 and held >= 1: state = "rejected"
        else: state = "untested"
        vx = float(np.mean(vols)) if vols else None
        structural = any(k for k in d["kinds"] if "node" not in k and "value-area" not in k)
        if held >= 2 and held / max(tests, 1) >= 0.5 and structural and (vx is None or vx >= 0.9): strength = "PROBABLE"
        elif structural or held >= 1: strength = "SUSPECTED"
        else: strength = "SUSPECTED" if "node" in " ".join(d["kinds"]) else "UNKNOWN"
        if through: strength = "UNKNOWN"
        side = d["side"]
        confirm = (f"tests keep closing back above {hi:.2f}; a close above the next seller zone" if side == "buyers"
                   else f"tests keep closing back below {lo:.2f}; a close below the next buyer zone")
        destroy = (f"acceptance below {lo:.2f} (closes below, value building there)" if side == "buyers"
                   else f"acceptance above {hi:.2f} (closes above, value building there)")
        graded.append({"side": side, "zone": [r2(lo), r2(hi)], "hypothesis": "responsive buyers" if side == "buyers" else "responsive sellers",
                       "kinds": d["kinds"], "evidence": d["events"][-4:], "tests": tests, "held": held,
                       "test_volume_x": r2(vx), "level_state": state + (" (being tested now)" if last_visit_live else ""), "strength": strength,
                       "confirms": confirm, "destroys": destroy, "distance_atr": r2(((lo + hi) / 2 - price) / a)})
    return sorted(graded, key=lambda d: -d["zone"][1])


# ----------------------------------------------------------------------------- chapter
def chapter(name: str, f: pd.DataFrame, clock: str, participants: str, question: str) -> dict:
    f = add_indicators(f).reset_index(drop=True)
    N = 12 if name == "monthly" else P["lookback"]
    if len(f) < N + 5:
        return {"timeframe": name, "status": f"not answerable today: only {len(f)} bars", "clock": clock}
    a = float(f["atr"].iloc[-1]); price = float(f["close"].iloc[-1])
    cur = profile(f.tail(N)); prev = profile(f.iloc[-2 * N:-N]) if len(f) >= 2 * N else None
    p60 = profile(f.tail(min(60, len(f))))
    mig = (cur["poc"] - prev["poc"]) if (cur and prev) else 0.0
    if prev is None: mig_note = "no prior window (short history)"
    zones = merge_and_grade(mine_zones(f, name, p60, prev), f)
    buyers = [z for z in zones if z["side"] == "buyers" and z["zone"][1] <= price + 0.1 * a]
    sellers = [z for z in zones if z["side"] == "sellers" and z["zone"][0] >= price - 0.1 * a]
    nb = max(buyers, key=lambda z: z["zone"][1]) if buyers else None
    ns = min(sellers, key=lambda z: z["zone"][0]) if sellers else None
    loc = "above value" if price > cur["vah"] else "below value" if price < cur["val"] else "inside value"
    if abs(mig) < P["balance_migration_atr"] * a and loc == "inside value": cond = "balance"
    elif mig > 0 and loc != "below value": cond = "imbalance up (value migrating higher)"
    elif mig < 0 and loc != "above value": cond = "imbalance down (value migrating lower)"
    else: cond = "transition (price and value disagree)"
    side = 1 if (mig > 0 and price >= cur["poc"]) else -1 if (mig < 0 and price <= cur["poc"]) else 0
    last = f.iloc[-1]; rng = last["high"] - last["low"]
    if rng >= 1.2 * a and ((last["close"] > cur["vah"] and last["close"] > last["open"]) or (last["close"] < cur["val"] and last["close"] < last["open"])):
        act = "initiative (" + ("buyers" if last["close"] > last["open"] else "sellers") + " drove a range-expansion bar outside value)"
    elif (last["high"] > cur["vah"] and last["close"] < cur["vah"]) or (last["low"] < cur["val"] and last["close"] > cur["val"]):
        act = "responsive (" + ("sellers rejected the probe above value" if last["high"] > cur["vah"] and last["close"] < cur["vah"] else "buyers rejected the probe below value") + ")"
    else:
        act = "neither: rotation inside the range"
    t5 = f.tail(5); v5 = (t5["volume"] / t5["vol20"]).mean(); move5 = (t5["close"].iloc[-1] - t5["open"].iloc[0]) / a
    if v5 >= 1.3 and abs(move5) < 0.75:
        er = f"high effort ({v5:.1f}x volume), little result ({move5:+.1f} ATR in 5 bars): absorption, " + ("buyers holding" if move5 <= 0 else "sellers capping")
    elif v5 < 0.8 and abs(move5) >= 1.0:
        er = f"low effort ({v5:.1f}x volume) with result ({move5:+.1f} ATR): drift with little opposition"
    else:
        er = f"effort {v5:.1f}x volume for {move5:+.1f} ATR over 5 bars: in proportion"
    hiN, loN = f["high"].iloc[-N - 1:-1].max(), f["low"].iloc[-N - 1:-1].min(); t3 = f.tail(3)
    trapped = "none detected"
    if (t3["high"] > hiN).any() and price < hiN: trapped = f"buyers who bought the break above {hiN:.2f} (failed breakout, price back below)"
    if (t3["low"] < loN).any() and price > loN: trapped = f"sellers who sold the break below {loN:.2f} (failed breakdown, price back above)"
    rej = []
    for r in f.tail(10).itertuples():
        body_hi, body_lo = max(r.open, r.close), min(r.open, r.close); rr = max(r.high - r.low, 1e-9)
        if (r.high - body_hi) / rr >= 0.5: rej.append(f"{r.high:.2f} (upper tail, {str(r.date)[:10]})")
        if (body_lo - r.low) / rr >= 0.5: rej.append(f"{r.low:.2f} (lower tail, {str(r.date)[:10]})")
    llr = "up" if side > 0 else "down" if side < 0 else ("up" if (ns and nb and (ns["zone"][0] - price) > (price - nb["zone"][1])) else "down" if (ns and nb) else "unclear")
    tgt = (ns["zone"][0] if ns else cur["high"]) if llr == "up" else (nb["zone"][1] if nb else cur["low"]) if llr == "down" else None
    up_t = ns["zone"][1] if ns else max(cur["high"], price); dn_t = nb["zone"][0] if nb else min(cur["low"], price)
    return {
        "timeframe": name, "clock": clock, "bars": len(f), "last_close": r2(price), "atr": r2(a),
        "participants_inferred": participants, "question": question,
        "structure": structure(f), "auction_condition": cond,
        "dominant_side": {1: "buyers", -1: "sellers", 0: "unresolved"}[side], "side_score": side,
        "activity": act, "location": loc,
        "accepted_value": [cur["val"], cur["vah"]], "poc": cur["poc"], "poc_migration": r2(mig),
        "prior_value": [prev["val"], prev["vah"]] if prev else None,
        "rejected_prices": rej[-4:],
        "probable_buyers": nb["zone"] if nb else None, "probable_sellers": ns["zone"] if ns else None,
        "trapped_side": trapped, "effort_vs_result": er,
        "line_of_least_resistance": llr, "next_target": r2(tgt),
        "invalidation": r2(dn_t if llr == "up" else up_t if llr == "down" else None),
        "control_transfer_up": r2(up_t), "control_transfer_down": r2(dn_t),
        "poor_high": cur["poor_high"], "poor_low": cur["poor_low"],
        "profile_60": p60, "zones": zones,
        "evidence_quality": "bars only: zones capped at PROBABLE; Confirmed needs tape",
    }


# ----------------------------------------------------------------------------- session TPO
def session_facts(intra: pd.DataFrame, daily: pd.DataFrame) -> list[dict]:
    """Per regular session from 30m bars: TPO profile via market_structure.profile (owner),
    initial balance, range extension, single prints, poor highs and lows, excess, VWAP,
    opening location and type, day type, value relationship, overnight inventory."""
    try:
        sys.path.insert(0, str(ROOT))
        from market_structure.profile import build_market_profile
        owner = True
    except Exception:
        owner = False
    reg = intra[intra.segment == "REGULAR"]
    d = add_indicators(daily); atr_by_date = dict(zip(d["date"].dt.date, d["atr"]))
    out, prev = [], None
    for s, day in reg.groupby("session"):
        day = day.sort_values("et").reset_index(drop=True)
        if len(day) < 6:
            continue
        atr = atr_by_date.get(s) or (d["atr"].iloc[-1])
        open_et = pd.Timestamp(datetime(s.year, s.month, s.day, 9, 30)).tz_localize(ET)
        poc = val = vah = None; prof_quality = "own composite"
        bins = None
        if owner:
            try:
                bars = pd.DataFrame({"timestamp_utc": day["et"].dt.tz_convert("UTC"), "high": day["high"], "low": day["low"],
                                     "close": day["close"], "volume": day["volume"]})
                mp = build_market_profile(bars, exchange_tick=0.01, atr14=float(atr), regular_open_utc=open_et.tz_convert("UTC").to_pydatetime())
                poc, val, vah, prof_quality, bins = mp.poc, mp.value_area_low, mp.value_area_high, mp.data_quality, mp.bins
            except Exception as exc:
                prof_quality = f"market_structure.profile failed: {exc}"
        if poc is None:
            pr = profile(day.rename(columns={"et": "date"}), 30); poc, val, vah = pr["poc"], pr["val"], pr["vah"]
        ib_hi, ib_lo = day["high"].iloc[:2].max(), day["low"].iloc[:2].min(); hi, lo = day["high"].max(), day["low"].min()
        ext_up, ext_dn = hi > ib_hi + 1e-9, lo < ib_lo - 1e-9; ib = ib_hi - ib_lo; rng = hi - lo
        cl = day["close"].iloc[-1]; op = day["open"].iloc[0]
        singles, poor_hi, poor_lo, excess_hi, excess_lo = [], None, None, None, None
        if bins is not None and len(bins):
            cnt = bins["tpo_count"].values; px = bins["price"].values; nz = np.flatnonzero(cnt > 0)
            if len(nz):
                a0, a1 = nz[0], nz[-1]
                poor_hi = bool(cnt[a1] >= 2); poor_lo = bool(cnt[a0] >= 2)
                k = a1
                while k > a0 and cnt[k] == 1: k -= 1
                excess_hi = int(a1 - k) >= 2
                k = a0
                while k < a1 and cnt[k] == 1: k += 1
                excess_lo = int(k - a0) >= 2
                mids = [i for i in range(a0 + 2, a1 - 1) if cnt[i] == 1 and cnt[i - 1] >= 1 and cnt[i + 1] >= 1]
                runs = []
                for i in mids:
                    if runs and i == runs[-1][-1] + 1: runs[-1].append(i)
                    else: runs.append([i])
                singles = [[r2(px[r[0]]), r2(px[r[-1]])] for r in runs if len(r) >= 2]
        vwap = float((day["close"] * day["volume"]).sum() / max(day["volume"].sum(), 1))
        if ib > 0 and rng <= 1.15 * ib: dtype = "normal day (IB held)"
        elif ext_up and ext_dn: dtype = "neutral day (extension both sides)"
        elif (ext_up or ext_dn) and rng >= 2.0 * ib and (cl >= hi - 0.15 * rng or cl <= lo + 0.15 * rng): dtype = "trend day " + ("up" if ext_up else "down")
        elif ext_up or ext_dn: dtype = "normal variation " + ("up" if ext_up else "down")
        else: dtype = "non-trend"
        b1 = day.iloc[0]; r1 = max(b1["high"] - b1["low"], 1e-9)
        later = day.iloc[1:]
        if abs(op - b1["low"]) <= 0.1 * r1 and later["low"].min() >= b1["low"] and b1["close"] > b1["open"]: otype = "open-drive up"
        elif abs(op - b1["high"]) <= 0.1 * r1 and later["high"].max() <= b1["high"] and b1["close"] < b1["open"]: otype = "open-drive down"
        elif b1["close"] > b1["open"] and (op - b1["low"]) > 0.25 * r1 and later["low"].min() >= b1["low"]: otype = "open-test-drive up"
        elif b1["close"] < b1["open"] and (b1["high"] - op) > 0.25 * r1 and later["high"].max() <= b1["high"]: otype = "open-test-drive down"
        elif (cl - op) * (b1["close"] - b1["open"]) < 0 and abs(cl - op) > 0.5 * r1: otype = "open-rejection-reverse"
        else: otype = "open-auction"
        rel = open_loc = inv = None
        if prev:
            pv_lo, pv_hi = prev["value"]
            if val is not None and vah is not None:
                rel = ("higher value" if val > pv_hi else "lower value" if vah < pv_lo else
                       "overlapping higher" if poc and poc > prev["poc"] else "overlapping lower" if poc and poc < prev["poc"] else "unchanged value")
            open_loc = ("above prior range" if op > prev["high"] else "below prior range" if op < prev["low"] else
                        "above prior value" if op > pv_hi else "below prior value" if op < pv_lo else "inside prior value")
            pre = intra[(intra["session"] == s) & (intra.segment == "PRE")]
            if len(pre):
                last_pre = float(pre["close"].iloc[-1]); inv = ("net long overnight" if last_pre > prev["close"] else "net short overnight" if last_pre < prev["close"] else "flat")
        rec = {"session": str(s), "open": r2(op), "high": r2(hi), "low": r2(lo), "close": r2(cl), "vwap": r2(vwap),
               "poc": r2(poc), "value": [r2(val), r2(vah)], "profile_quality": prof_quality,
               "initial_balance": [r2(ib_lo), r2(ib_hi)], "range_extension": "both" if ext_up and ext_dn else "up" if ext_up else "down" if ext_dn else "none",
               "day_type": dtype, "opening_type": otype, "opening_location": open_loc, "value_relationship": rel,
               "overnight_inventory": inv, "single_prints": singles, "poor_high": poor_hi, "poor_low": poor_lo,
               "excess_high": excess_hi, "excess_low": excess_lo,
               "close_vs_vwap": "above" if cl > vwap else "below"}
        out.append(rec); prev = {"value": [val, vah], "poc": poc, "high": hi, "low": lo, "close": cl}
    return out


# ----------------------------------------------------------------------------- memory
def update_memory(path: Path, ticker: str, chapters: dict, price: float, atr: float, today: str) -> dict:
    mem = {"ticker": ticker, "zones": [], "updated": None}
    if path.exists():
        try: mem = json.loads(path.read_text(encoding="utf-8"))
        except Exception: pass
    seen = []
    for tf in ("weekly", "daily", "4h", "1h"):
        ch = chapters.get(tf) or {}
        for z in ch.get("zones", []):
            if z["strength"] == "UNKNOWN": continue
            seen.append((tf, z))
    for tf, z in seen:
        lo, hi = z["zone"]
        m = next((m for m in mem["zones"] if m["side"] == z["side"] and m["tf"] == tf and not (hi < m["zone"][0] - 0.2 * atr or lo > m["zone"][1] + 0.2 * atr)), None)
        if m is None:
            mem["zones"].append({"side": z["side"], "tf": tf, "zone": z["zone"], "kinds": z["kinds"], "first_seen": today,
                                 "last_seen": today, "tests": z["tests"], "held": z["held"], "status": "open",
                                 "revisits": []})
        else:
            if z["tests"] > m["tests"]:
                m["revisits"].append({"date": today, "held": z["held"] > m["held"]})
            m.update(zone=z["zone"], kinds=sorted(set(m["kinds"] + z["kinds"])), last_seen=today, tests=z["tests"], held=z["held"])
    for m in mem["zones"]:
        lo, hi = m["zone"]
        if m["status"] == "open" and ((m["side"] == "buyers" and price < lo - 0.25 * atr) or (m["side"] == "sellers" and price > hi + 0.25 * atr)):
            m["status"] = f"resolved {today}: traded through"
    for s in (chapters.get("_sessions") or [])[-5:]:
        for sp in s.get("single_prints") or []:
            key = f"single print {s['session']} {sp[0]}-{sp[1]}"
            if not any(m.get("note") == key for m in mem["zones"]):
                mem["zones"].append({"side": "buyers" if sp[1] < price else "sellers", "tf": "30m", "zone": sp, "kinds": ["unrepaired single print"],
                                     "first_seen": today, "last_seen": today, "tests": 0, "held": 0, "status": "open", "revisits": [], "note": key})
    mem["updated"] = today
    mem["unfinished_business"] = [m for m in mem["zones"] if m["status"] == "open"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mem, indent=1, default=str), encoding="utf-8")
    return mem


# ----------------------------------------------------------------------------- story
def pattern(ch: dict) -> tuple[str, str]:
    def s(tf): return (ch.get(tf) or {}).get("side_score", 0) or 0
    w, dly = s("weekly"), s("daily")
    if w * dly < 0:
        return "transition (weekly and daily disagree)", "The campaign is contested: the weekly and daily point opposite ways. Treat as balance until the daily confirms or reverses the weekly."
    campaign = (w + dly) if (w != 0 and dly != 0) else 0      # the campaign needs both horizons; one alone is a lean, not control
    lean = w + dly
    swing = s("4h") + s("1h") if ch.get("1h", {}).get("side_score") is not None else s("daily")
    sess = ch.get("_sessions") or []; last = sess[-1] if sess else None
    session = 0
    if last:
        session = 1 if last["close_vs_vwap"] == "above" and (last["value_relationship"] or "").find("higher") >= 0 else -1 if last["close_vs_vwap"] == "below" and (last["value_relationship"] or "").find("lower") >= 0 else 0
    d = ch.get("daily") or {}
    below_demand = d.get("probable_buyers") is None and d.get("location") == "below value"
    lower = swing + session
    if campaign == 0 and lean != 0:
        side = "up" if lean > 0 else "down"
        return f"leaning {side}, campaign unconfirmed", (f"Only the {'daily' if dly else 'weekly'} shows {'buyers' if lean > 0 else 'sellers'}; the other campaign horizon is unresolved. "
                f"Not an aligned trend: trade only the {side} branch on a close, at reduced conviction, and expect the unresolved horizon to resist.")
    if campaign == 0 and lower == 0: return "balance", "No side controls the campaign or the swing: wait for value to migrate or a boundary to fail; short-dated options bleed here."
    if campaign > 0 and lower > 0: return "aligned up", "Initiative buyers control several horizons: continuation call or LPS entry."
    if campaign < 0 and lower < 0: return "aligned down", "Initiative sellers control several horizons: continuation put or LPSY entry."
    if campaign > 0 and lower < 0 and below_demand: return "higher up, lower down, accepted below demand", "The correction may be becoming a campaign transition: a short-duration put can be right while the weekly is still bullish."
    if campaign > 0 and lower <= 0: return "higher up, lower down", "A pullback inside a bullish campaign: wait for sellers to fail at higher-timeframe demand, then call."
    if campaign < 0 and lower >= 0: return "higher down, lower up", "Short covering, automatic rally or LPSY forming: a call only as a counter-trend trade with a fast exit, or wait for the LPSY and put."
    return "mixed / transition", "Timeframes disagree without a clear hierarchy: treat as balance until one boundary fails."


def branches(ch: dict) -> dict:
    d = ch.get("daily") or {}; price = d.get("last_close")
    up = d.get("control_transfer_up"); dn = d.get("control_transfer_down")
    ups = sorted([z["zone"] for z in d.get("zones", []) if z["side"] == "sellers" and z["zone"][0] > (up or price)], key=lambda z: z[0])[:3]
    dns = sorted([z["zone"] for z in d.get("zones", []) if z["side"] == "buyers" and z["zone"][1] < (dn or price)], key=lambda z: -z[1])[:3]
    return {
        "basis": "daily close (the 15:50 ET confirmation check); a retest confirmation needs cross-ticker evidence (12 Oct rule)",
        "up": {"trigger": f"close above {up}", "level": up, "path_targets": [z[0] for z in ups], "means": "sellers lose control of the swing; shorts above the last breakdown are trapped", "contract": "call (card prices it)"},
        "down": {"trigger": f"close below {dn}", "level": dn, "path_targets": [z[1] for z in dns], "means": "responsive buyers have failed; value can migrate lower", "contract": "put (card prices it)"},
        "balance": {"between": [dn, up], "action": "no option entry; balance bleeds time value", "width_atr": r2((up - dn) / d["atr"]) if up and dn and d.get("atr") else None},
    }


def story(t: str, ch: dict, pat: tuple[str, str], br: dict) -> str:
    w, d = ch.get("weekly") or {}, ch.get("daily") or {}
    h1 = ch.get("1h") or {}; sess = (ch.get("_sessions") or [None])[-1]
    parts = [f"{t}: the campaign (weekly {w.get('dominant_side', '?')}, daily {d.get('dominant_side', '?')}) is in {d.get('auction_condition', '?')}, "
             f"price {d.get('location', '?')} {d.get('accepted_value')} with the POC moving {d.get('poc_migration')}."]
    if h1.get("structure"):
        parts.append(f"The swing (1h) shows {h1['structure']} with {h1.get('dominant_side')} in control and {h1.get('activity')}.")
    if sess:
        parts.append(f"The last session ({sess['session']}) was a {sess['day_type']} with an {sess['opening_type']} open {sess['opening_location'] or ''}, "
                     f"value {sess['value_relationship'] or 'n/a'}, closing {sess['close_vs_vwap']} VWAP {sess['vwap']}.")
    b = d.get("probable_buyers"); s = d.get("probable_sellers")
    parts.append(f"The auction sits between buyers at {b} and sellers at {s}; effort vs result: {d.get('effort_vs_result')}. Trapped: {d.get('trapped_side')}.")
    parts.append(f"Pattern: {pat[0]}. {pat[1]} Up branch: {br['up']['trigger']}; down branch: {br['down']['trigger']}; between them, no entry.")
    return " ".join(parts)


# ----------------------------------------------------------------------------- markdown
def to_md(rep: dict) -> str:
    L = [f"# {rep['ticker']} auction map ({rep['as_of']})", "", rep["story"], "",
         f"**Pattern:** {rep['pattern']['name']}. {rep['pattern']['read']}", "",
         "| Branch | Trigger | Path | Means |", "| --- | --- | --- | --- |"]
    for k in ("up", "down"):
        b = rep["branches"][k]; L.append(f"| {k} | {b['trigger']} | {b['path_targets']} | {b['means']} |")
    L += [f"| balance | between {rep['branches']['balance']['between']} | - | {rep['branches']['balance']['action']} |", "",
          "| Timeframe | Clock | Structure | Condition | Side | Activity | Value | Buyers | Sellers | Trapped | Effort vs result | Up / down |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for tf in ("monthly", "weekly", "daily", "4h", "1h", "30m"):
        c = rep["chapters"].get(tf) or {}
        if "structure" not in c:
            L.append(f"| {tf} | {c.get('clock', '')} | {c.get('status', 'missing')} |  |  |  |  |  |  |  |  |  |"); continue
        L.append(f"| {tf} | {c['clock']} | {c['structure']} | {c['auction_condition']} | {c['dominant_side']} | {c['activity']} | {c['accepted_value']} POC {c['poc']} | {c['probable_buyers']} | {c['probable_sellers']} | {c['trapped_side']} | {c['effort_vs_result']} | {c['control_transfer_up']} / {c['control_transfer_down']} |")
    L += ["", "## Daily zone map", "", "| Zone | Hypothesis | Evidence | Strength | Level state | Confirms | Destroys |", "| --- | --- | --- | --- | --- | --- | --- |"]
    dz = (rep["chapters"].get("daily") or {}).get("zones", [])
    near = sorted([z for z in dz if z["side"] == "sellers" and z["strength"] != "UNKNOWN"], key=lambda z: z["zone"][0])[:4][::-1] + \
           sorted([z for z in dz if z["side"] == "buyers" and z["strength"] != "UNKNOWN"], key=lambda z: -z["zone"][1])[:4]
    for z in near:
        L.append(f"| {z['zone'][0]}-{z['zone'][1]} | {z['hypothesis']} ({', '.join(z['kinds'])}) | {'; '.join(z['evidence'][-2:])}; tests {z['tests']}, held {z['held']} | {z['strength']} | {z['level_state']} | {z['confirms']} | {z['destroys']} |")
    if rep.get("sessions"):
        L += ["", "## Last sessions (30m TPO)", "", "| Session | Open type | Open location | Day type | IB | Value | POC | VWAP | Value vs prior | Singles | Poor high/low | Inventory |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for s in rep["sessions"][-5:]:
            L.append(f"| {s['session']} | {s['opening_type']} | {s['opening_location']} | {s['day_type']} | {s['initial_balance']} | {s['value']} | {s['poc']} | {s['vwap']} | {s['value_relationship']} | {s['single_prints']} | {s['poor_high']}/{s['poor_low']} | {s['overnight_inventory']} |")
    L += ["", "## Unfinished business (auction memory)", ""]
    for m in rep["memory"]["unfinished_business"][:12]:
        L.append(f"- {m['side']} {m['tf']} {m['zone']} ({', '.join(m['kinds'])}), first seen {m['first_seen']}, tests {m['tests']}, revisits {len(m['revisits'])}")
    L += ["", "## Clocks and quality", "", "```json", json.dumps(rep["clocks"], indent=1, default=str), "```",
          "", "Zones from bars reach PROBABLE at most; CONFIRMED needs tape. Participant horizons are inferred."]
    return "\n".join(L)


# ----------------------------------------------------------------------------- main
def run(ticker: str, args) -> dict:
    daily, dsrc = load_daily(ticker, args.prices_csv)
    if len(daily) < 60:
        raise SystemExit(f"{ticker}: only {len(daily)} daily bars")
    out_root = Path(args.out) if args.out else OUT_ROOT
    intra, isrc = (None, {"status": "SKIPPED (--no-intraday)"}) if args.no_intraday else load_intraday(ticker, 30, args.intraday_sessions, args.intraday_csv, out_root / "intraday")
    provisional = []
    if intra is not None:                      # the store can lag a session: build those daily bars from 30m regular-session bars
        store_last = pd.Timestamp(dsrc["last_session"]).date() if dsrc["last_session"] else None
        for sday, day in intra[intra.segment == "REGULAR"].groupby("session"):
            if store_last and sday > store_last and len(day) >= 12:
                day = day.sort_values("et")
                daily = pd.concat([daily, pd.DataFrame([{"ticker": ticker, "trading_date": str(sday), "date": pd.Timestamp(sday),
                    "open": day["open"].iloc[0], "high": day["high"].max(), "low": day["low"].min(), "close": day["close"].iloc[-1],
                    "volume": day["volume"].sum()}])], ignore_index=True)
                provisional.append(str(sday))
    last = daily["trading_date"].iloc[-1]
    clocks = {"daily": {"clock": f"EOD close {last}" + (f" (provisional from 30m bars: {', '.join(provisional)}; store to {dsrc['last_session']})" if provisional else ""), **dsrc, "provisional_sessions": provisional}}
    ch = {
        "monthly": chapter("monthly", resample_daily(daily, "ME"), f"EOD close {last} (month to date)", "strategic valuation and long-cycle positioning", "Where is it in its major cycle?"),
        "weekly": chapter("weekly", resample_daily(daily, "W-FRI"), f"EOD close {last} (week to date)", "larger capital and structural ownership", "Is ownership transferring over weeks?"),
        "daily": chapter("daily", daily[["date", "open", "high", "low", "close", "volume"]], clocks["daily"]["clock"], "portfolio and institutional horizon", "Which campaign controls the stock?"),
    }
    sessions = []
    if not args.no_intraday:
        clocks["intraday_30m"] = isrc
        if intra is not None:
            clk = f"30m bars to {isrc['last_bar_et']}"
            ch["4h"] = chapter("4h", intraday_frame(intra, 240), clk, "swing participants", "Is supply absorbed or distributed across sessions?")
            ch["1h"] = chapter("1h", intraday_frame(intra, 60), clk, "multi-session traders", "Is today continuing or correcting the swing?")
            ch["30m"] = chapter("30m", intraday_frame(intra, 30), clk, "day traders and short-horizon funds", "Where is session value forming?")
            sessions = session_facts(intra, daily)
        else:
            for tf in ("4h", "1h", "30m"):
                ch[tf] = {"timeframe": tf, "status": "not answerable today: needs intraday bars (" + isrc.get("status", "missing") + ")", "clock": "-"}
    ch["_sessions"] = sessions
    ch["5m_and_tape"] = {"timeframe": "5m / tape", "status": "expected script only: written by the card; the board checks it live. Tape and depth are not available (screenshots cap at SUSPECTED)."}
    pat = pattern(ch); br = branches(ch)
    d = ch["daily"]; today = now_utc().strftime("%Y-%m-%d")
    mem = update_memory(out_root / "memory" / f"{ticker}.json", ticker, ch, d["last_close"], d["atr"], today)
    rep = {"ticker": ticker, "version": VERSION, "params": P, "as_of": f"{last} close; built {now_utc().isoformat(timespec='seconds')}",
           "clocks": clocks, "pattern": {"name": pat[0], "read": pat[1]}, "branches": br,
           "story": story(ticker, ch, pat, br),
           "chapters": {k: v for k, v in ch.items() if not k.startswith("_")}, "sessions": sessions, "memory": mem}
    folder = out_root / today; folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{ticker}_auction.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    (folder / f"{ticker}_auction.md").write_text(to_md(rep), encoding="utf-8")
    print(f"{ticker}: {pat[0]} | up {br['up']['level']} / down {br['down']['level']} | {folder / (ticker + '_auction.md')}")
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--intraday-sessions", type=int, default=20)
    ap.add_argument("--no-intraday", action="store_true")
    ap.add_argument("--prices-csv")
    ap.add_argument("--intraday-csv")
    ap.add_argument("--out")
    args = ap.parse_args()
    if (args.prices_csv or args.intraday_csv) and len(args.tickers) > 1:
        sys.exit("--prices-csv / --intraday-csv take one ticker at a time")
    for t in [x.upper().strip() for x in args.tickers]:
        try:
            run(t, args)
        except SystemExit as exc:
            print(exc)
        except Exception as exc:
            print(f"{t}: FAILED {type(exc).__name__}: {exc}")
            raise


if __name__ == "__main__":
    main()
