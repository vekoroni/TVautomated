"""Phase 0 characterisation: Discovery recall losses on run 20261006_060401 (READ-ONLY).

Reads the run's Discovery lifecycle and behavioural-candidate files, the canonical daily price store
(SQLite opened with mode=ro) and replays the BEH-001 engine on stored daily bars cut at 2026-10-05.
No provider/network call, no pipeline run, no write outside Enhancements/phase0/.

Usage:  venv\\Scripts\\python.exe -B Enhancements\\phase0\\p0_recall_losses.py [--no-errors-replay]
Writes: Enhancements/phase0/p0_recall_losses_evidence.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUN = "20261006_060401"
RUN_DIR = ROOT / "data" / "output" / "runs" / RUN
LIFECYCLE = RUN_DIR / "discovery" / f"discovery_lifecycle_{RUN}.csv"
CANDIDATES = RUN_DIR / "discovery" / f"behavioural_candidates_{RUN}.csv"
AUG_UNIVERSE = RUN_DIR / "universe" / f"scanner_augmented_universe_{RUN}.csv"
BASE_UNIVERSE = ROOT / "data" / "universe" / "polygon_liquid_universe.csv"
PRICE_DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
CUTOFF = "2026-10-05"
OUT = Path(__file__).resolve().parent / "p0_recall_losses_evidence.json"
DAILY_FAMILY = ("1mo", "1w", "1d")
LIVE = ("DETECTED", "ACTIVATED")


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def daily_bars(con, ticker: str) -> pd.DataFrame:
    frame = pd.read_sql(
        "SELECT trading_date AS date, open, high, low, close, volume FROM ohlcv_daily "
        "WHERE ticker=? AND adjustment_convention='POLYGON_SPLIT_ADJUSTED' AND bar_status='COMPLETE' "
        "AND trading_date<=? ORDER BY trading_date", con, params=(ticker, CUTOFF))
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def atr14(df: pd.DataFrame) -> float | None:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    value = tr.rolling(14).mean().iloc[-1] if len(df) >= 14 else np.nan
    return None if pd.isna(value) else float(value)


def replay(con, ticker: str, policy, bars: int | None = None) -> dict:
    """Discovery's BEH-001 reading and lane on daily bars only (intraday absent)."""
    from domain.structure_behaviour.engine import analyse_ticker
    from domain.structure_behaviour.trade_lane import select_governing
    df = daily_bars(con, ticker)
    if bars is not None:
        df = df.tail(bars).reset_index(drop=True)
    if df.empty:
        return {"ticker": ticker, "bars": 0}
    beh = analyse_ticker(ticker, df, None, policy, intraday_status="HISTORICAL_REPLAY")
    side = beh["handoff"]["thesis__side"]
    lane, _ = select_governing(beh["candidates"], price=float(df["close"].iloc[-1]), atr_daily=atr14(df), side=side)
    directed_live = {tf: sum(1 for c in beh["readings"][tf]["candidates"]
                             if c["Signal_State"] in LIVE and c["Direction"] in ("BULL", "BEAR"))
                     for tf in DAILY_FAMILY}
    return {"ticker": ticker, "bars": len(df), "last": str(df["date"].iloc[-1].date()),
            "status": {tf: beh["readings"][tf]["Status"] for tf in DAILY_FAMILY},
            "directed_live": directed_live, "any_directed_live": sum(directed_live.values()) > 0,
            "side": side, "lane": lane["trade_lane"], "lane_basis": lane["trade_lane_basis"],
            "levels_passed": lane.get("trade_lane_levels_passed")}


def summarise(rows: list[dict]) -> dict:
    rows = [r for r in rows if r.get("bars")]
    return {"n": len(rows),
            "daily_1d_evaluated": sum(r["status"]["1d"] == "EVALUATED" for r in rows),
            "with_directed_live_daily_family": sum(r["any_directed_live"] for r in rows),
            "lanes": pd.Series([r["lane"] for r in rows]).value_counts().to_dict(),
            "lane_basis": pd.Series([r["lane_basis"] for r in rows]).value_counts().to_dict(),
            "status_1d": pd.Series([r["status"]["1d"] for r in rows]).value_counts().to_dict()}


def reproduce_scan_errors(tickers: list[str]) -> dict:
    """Re-run scan_ticker_ultimate on the frame Discovery would have used (stale CSV cache, else store)."""
    import avshunter_discovery_ULTIMATE as disc
    cfg = disc.UltimateConfig()
    cfg.macro_sector_signals, cfg.vms_context, cfg.beh001_intraday_index = {}, {}, None
    cfg.macro_quant_packet = disc.missing_macro_quant_packet(disc._macro_source_path(""))
    engine = disc.WyckoffEngine(min_bars=20)
    out = {}
    for t in tickers:
        csv = ROOT / "data" / "daily" / f"{t}.csv"
        if csv.exists():
            df = pd.read_csv(csv)
            df.columns = [c.lower().strip() for c in df.columns]
            source = "STALE_CSV"
        else:
            with _ro(PRICE_DB) as con:
                df = daily_bars(con, t)
            source = "CANONICAL"
        try:
            disc.scan_ticker_ultimate(t, df, cfg, engine, eligibility_diagnostic={})
            out[t] = {"source": source, "bars": len(df), "result": "NO_EXCEPTION_ON_REPLAY"}
        except Exception as exc:
            tb = traceback.extract_tb(exc.__traceback__)
            frames = [f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in tb[-4:]]
            out[t] = {"source": source, "bars": len(df), "error": f"{type(exc).__name__}: {exc}"[:300],
                      "frames": frames,
                      "last_date": str(pd.to_datetime(df["date"], format="mixed").max().date()) if "date" in df else None,
                      "date_formats": df["date"].astype(str).str.len().value_counts().to_dict() if "date" in df else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-errors-replay", action="store_true")
    ap.add_argument("--sample", type=int, default=20)
    args = ap.parse_args()
    ev: dict = {"run": RUN, "cutoff": CUTOFF}

    life = pd.read_csv(LIFECYCLE)
    ev["lifecycle_rows"], ev["lifecycle_unique"] = len(life), int(life.ticker.nunique())
    ev["counts"] = {c: life[c].value_counts(dropna=False).rename(str).to_dict()
                    for c in ("outcome", "lifecycle_state", "reason_code")}

    # Universe origin (task 4)
    aug, base = pd.read_csv(AUG_UNIVERSE), pd.read_csv(BASE_UNIVERSE)
    aug_set = list(aug.ticker.astype(str).str.upper().str.strip())
    base_set = set(base.iloc[:, 0].astype(str).str.upper().str.strip())
    ev["universe"] = {"base_file": str(BASE_UNIVERSE.relative_to(ROOT)), "base_n": len(base_set),
                      "augmented_n": len(aug_set), "scanner_injected": [t for t in aug_set if t not in base_set],
                      "universe_not_in_lifecycle": sorted(set(aug_set) - set(life.ticker)),
                      "lifecycle_not_in_universe": sorted(set(life.ticker) - set(aug_set))}

    with _ro(PRICE_DB) as con:
        cov = pd.read_sql(
            "SELECT ticker, COUNT(*) n, MIN(trading_date) first, MAX(trading_date) last FROM ohlcv_daily "
            "WHERE adjustment_convention='POLYGON_SPLIT_ADJUSTED' AND bar_status='COMPLETE' AND trading_date<=? "
            "GROUP BY ticker", con, params=(CUTOFF,))
        batches = pd.read_sql("SELECT ticker, MIN(fetched_at) first_fetch, GROUP_CONCAT(DISTINCT source_kind) kinds "
                              "FROM ohlcv_ingest_batches GROUP BY ticker", con)
    m = life.merge(cov, on="ticker", how="left").merge(batches, on="ticker", how="left")
    m["n"] = m["n"].fillna(0).astype(int)
    m["bars_bucket"] = pd.cut(m.n, [-1, 0, 29, 119, 259, 10 ** 6],
                              labels=["0", "1-29", "30-119", "120-259", ">=260"]).astype(str)
    ev["bars_by_reason"] = pd.crosstab(m.reason_code, m.bars_bucket).to_dict(orient="index")
    ev["survival_rate_by_bars"] = (m.assign(s=m.outcome.eq("SURVIVE")).groupby("bars_bucket")["s"]
                                   .agg(["sum", "count"]).to_dict(orient="index"))
    ev["first_date_by_reason"] = {r: g["first"].value_counts().head(3).to_dict()
                                  for r, g in m.groupby("reason_code")}
    ev["last_date_by_reason"] = {r: {"2026-10-05": int((g["last"] == CUTOFF).sum()),
                                     "older": int(((g["last"] < CUTOFF) & g["last"].notna()).sum()),
                                     "none": int(g["last"].isna().sum())} for r, g in m.groupby("reason_code")}
    short = m[(m.reason_code.isin(["INTRADAY_ONLY_UNTESTED", "NO_LIVE_SETUP"])) & (m.n < 120)]
    ev["short_history_ingest"] = {"n": len(short), "first_fetch_day": short.first_fetch.str[:10].value_counts().to_dict(),
                                  "kinds": short.kinds.value_counts().to_dict()}

    # What the run itself recorded for each group (behavioural candidates)
    cand = pd.read_csv(CANDIDATES, low_memory=False)
    ev["run_candidates"] = {}
    for reason, g in cand.groupby("Discovery_Reason"):
        live = g[g.Signal_State.isin(LIVE) & g.Direction.isin(["BULL", "BEAR"])]
        ev["run_candidates"][reason] = {
            "tickers_with_any_candidate": int(g.Ticker.nunique()),
            "tickers_with_any_daily_family_candidate": int(g[g.Timeframe.isin(DAILY_FAMILY)].Ticker.nunique()),
            "tickers_with_directed_live_daily_family": int(live[live.Timeframe.isin(DAILY_FAMILY)].Ticker.nunique()),
            "tickers_with_directed_live_intraday": int(live[~live.Timeframe.isin(DAILY_FAMILY)].Ticker.nunique()),
            "state_by_timeframe": pd.crosstab(g.Timeframe, g.Signal_State).to_dict(orient="index")}

    # Replays on daily bars (task 2/3)
    from domain.structure_behaviour.policy import load_policy
    policy = load_policy()
    iou = m[m.reason_code == "INTRADAY_ONLY_UNTESTED"]
    nls = m[m.reason_code == "NO_LIVE_SETUP"]
    surv_full = m[(m.reason_code == "DISCOVERY_SURVIVOR") & (m.n >= 260)]
    samples = {
        "IOU_short_history_sample": iou[iou.n < 120].sample(args.sample, random_state=7).ticker.tolist(),
        "IOU_full_history_all": iou[iou.n >= 120].ticker.tolist(),
        "NLS_short_history_sample": nls[nls.n < 120].sample(args.sample, random_state=7).ticker.tolist(),
        "NLS_full_history_all": nls[nls.n >= 120].ticker.tolist(),
        "SURVIVOR_full_history_sample": surv_full.sample(30, random_state=7).ticker.tolist(),
    }
    ev["replay"] = {}
    with _ro(PRICE_DB) as con:
        for name, tickers in samples.items():
            rows = [replay(con, t, policy) for t in tickers]
            ev["replay"][name] = {"summary": summarise(rows), "rows": rows}
        # Counterfactual: the same survivors cut to the 92 bars a short-history ticker has.
        rows = [replay(con, t, policy, bars=92) for t in samples["SURVIVOR_full_history_sample"]]
        ev["replay"]["SURVIVOR_cut_to_92_bars"] = {"summary": summarise(rows), "rows": rows}

    # Insufficient bars / no price data (task 3)
    ins = m[m.reason_code == "ELIG_INSUFFICIENT_BARS"]
    ev["insufficient_bars"] = {"threshold": "UltimateConfig.min_bars = 30", "n": len(ins),
                               "bars_describe": ins.n.describe().round(1).to_dict(),
                               "with_ge_260_bars_in_store": int((ins.n >= 260).sum()),
                               "last_is_cutoff": int((ins["last"] == CUTOFF).sum()),
                               "first_on_or_after_2026_08_01": int((ins["first"] >= "2026-08-01").sum()),
                               "last_before_2026_09_01": int((ins["last"] < "2026-09-01").sum()),
                               "tickers": ins.sort_values("n")[["ticker", "n", "first", "last"]].values.tolist()}
    npd = m[m.reason_code == "NO_PRICE_DATA"]
    ev["no_price_data"] = {"n": len(npd), "in_store": int((npd.n > 0).sum()),
                           "legacy_csv_exists": [t for t in npd.ticker if (ROOT / "data" / "daily" / f"{t}.csv").exists()],
                           "tickers": npd.ticker.tolist()}
    errs = m[m.outcome == "ERROR"]
    ev["scan_errors"] = {"n": len(errs), "store": errs[["ticker", "n", "first", "last"]].values.tolist()}
    if not args.no_errors_replay:
        ev["scan_errors"]["replay"] = reproduce_scan_errors(errs.ticker.tolist())

    OUT.write_text(json.dumps(ev, indent=1, default=str), encoding="utf-8")
    for key in ("counts", "universe", "bars_by_reason", "survival_rate_by_bars", "last_date_by_reason",
                "short_history_ingest"):
        print(key, json.dumps(ev[key], default=str)[:1500])
    for reason, v in ev["run_candidates"].items():
        print("run_candidates", reason, {k: v[k] for k in v if k != "state_by_timeframe"})
    for name, v in ev["replay"].items():
        print("replay", name, json.dumps(v["summary"], default=str))
    print("insufficient_bars", json.dumps({k: v for k, v in ev["insufficient_bars"].items() if k != "tickers"}))
    print("no_price_data", json.dumps(ev["no_price_data"]))
    print("scan_errors", json.dumps(ev["scan_errors"], default=str)[:4000])


if __name__ == "__main__":
    main()
