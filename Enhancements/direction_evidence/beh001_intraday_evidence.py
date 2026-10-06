"""BEH-001 step 4 (ACK 5 Oct 2026): intraday setup evidence, built and tested like the daily panels.

Rules fixed before results are read:
- Data: stored regular-session 5-minute bars in the canonical intraday store, 2025-09-02 to 2026-10-02 (Polygon
  history backfill plus the recorded sessions). Per session the COMPLETE record is preferred, else PARTIAL; thin
  names are included - a missing 5-minute bar means no trades in that window, not missing data.
- Population: tickers with at least MIN_SESSIONS stored sessions. Panels by a stable hash of the ticker
  (md5 parity): original and holdout never share a ticker.
- Cuts: every STEP XNYS sessions. At a cut the engine sees daily bars up to the cut (read-only daily store) and the
  last 20 sessions of 5-minute bars up to and including the cut session - the most any intraday timeframe uses.
  Forward bars never enter it.
- Engine: domain.structure_behaviour.engine.analyse_ticker (HISTORICAL_REPLAY). Candidates on 60m/15m/5m,
  DETECTED or ACTIVATED, directed, with their levels.
- Forward: the 5-minute bars after the cut session, resampled with the engine's resample_intraday to the setup's
  timeframe, over a fixed window: 60m 33 bars (about 5 sessions), 15m 52 bars (2 sessions), 5m 78 bars (1 session).
- Tests as daily: ACTIVATION (DETECTED, trigger before invalidation), OUTCOME (ACTIVATED, level before invalidation),
  OUTCOME_FROM_DETECTION (DETECTED with a level, level before invalidation). C12 classify + evaluate_passage;
  censored is never success or failure.
- Output: one JSON line per scored test (panel, ticker, cut, timeframe, signal_type, state, direction, test, cause,
  time_bars, age_bars) and a summary JSON: hit rate (EVENT share of resolved+censored) by panel x timeframe x
  signal_type x test, and holdout timing calibration against original q50/q80. Status: IN_SAMPLE_REPLAY_NOT_VALIDATED
  until the summary is reviewed. Display and measurement only; never a gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from avshunter.c12_outcome.geometry import classify  # noqa: E402
from avshunter.c12_outcome.model import Bar, OutcomeState  # noqa: E402
from avshunter.c12_outcome.passage import evaluate_passage  # noqa: E402
from domain.structure_behaviour.engine import resample_intraday  # noqa: E402

REGISTRY = ROOT / "data" / "canonical" / "control_plane.sqlite"
START, END = "2025-09-02", "2026-10-02"
MIN_SESSIONS = 120
STEP = 10   # every 10 sessions, as the daily panels (fixed after the 20-ticker pilot timing, before any hit rate was read)
HISTORY_SESSIONS = 20
MINUTES = {"60m": 60, "15m": 15, "5m": 5}
WINDOW = {"60m": 33, "15m": 52, "5m": 78}
LIVE = {"DETECTED", "ACTIVATED"}


def panel_of(ticker: str) -> str:
    return "original" if int(hashlib.md5(ticker.upper().encode()).hexdigest(), 16) % 2 == 0 else "holdout"


def _ny_date(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, utc=True).dt.tz_convert("America/New_York").dt.date


def forward_bars(bars_5m: pd.DataFrame, *, after_session: str, timeframe: str) -> pd.DataFrame:
    """Own-timeframe bars after the cut session (engine resampling), capped at the timeframe's window."""
    cut = date.fromisoformat(str(after_session)[:10])
    after = bars_5m[_ny_date(bars_5m["timestamp_utc"]) > cut]
    if after.empty:
        return after
    out = after if timeframe == "5m" else resample_intraday(after.reset_index(drop=True), MINUTES[timeframe])
    return out.reset_index(drop=True).head(WINDOW[timeframe])


def score(*, direction: str, close: float, invalidation: float, target: float, fwd: pd.DataFrame,
          window: int) -> tuple[str, int] | None:
    """C12 passage on own-timeframe bars: (EVENT | INVALIDATION | CENSORED, bars); None if not scorable."""
    geometry = classify(direction, close, invalidation, target, None)
    if not geometry.scorable or geometry.target_state.value != "LEVEL":
        return None
    labels = list(range(1, len(fwd) + 1))
    bars = {k: Bar(k, float(r.open), float(r.high), float(r.low), float(r.close))
            for k, r in zip(labels, fwd.itertuples(index=False))}
    res = evaluate_passage(geometry, labels, bars, window)
    if res.state is OutcomeState.TARGET_FIRST:
        return "EVENT", int(res.resolution_session)
    if res.state in (OutcomeState.STOP_FIRST, OutcomeState.AMBIGUOUS):
        return "INVALIDATION", int(res.resolution_session)
    return "CENSORED", int(res.sessions_observed)


def session_index(registry: Path = REGISTRY) -> dict[str, dict[str, str]]:
    """ticker -> session -> payload path (COMPLETE preferred over PARTIAL), 5-minute regular bars only."""
    uri = f"file:{Path(registry).as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=60) as c:
        rows = c.execute(
            "SELECT instrument_id, session_date, storage_uri, completeness_status, scope_json FROM dataset_registry "
            "WHERE dataset_type='INTRADAY_BAR' AND session_date BETWEEN ? AND ?", (START, END)).fetchall()
    best: dict[str, dict[str, tuple[int, str]]] = defaultdict(dict)
    for ticker, session, uri_, status, scope in rows:
        extra = dict(json.loads(scope or "{}").get("extra") or [])
        if extra.get("interval") != "5min" or extra.get("session_segment") != "REGULAR":
            continue
        rank = 1 if status == "COMPLETE" else 0
        if session not in best[ticker] or rank > best[ticker][session][0]:
            best[ticker][session] = (rank, uri_)
    return {t: {s: v[1] for s, v in sess.items()} for t, sess in best.items()}


def _load_5m(paths: dict[str, str]) -> pd.DataFrame:
    frames = []
    for session in sorted(paths):
        try:
            f = pd.read_parquet(paths[session], columns=["timestamp_utc", "open", "high", "low", "close", "volume"])
        except Exception:
            continue
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=["timestamp_utc", "open", "high", "low", "close", "volume"])
    out = pd.concat(frames, ignore_index=True)
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True)
    return out.drop_duplicates("timestamp_utc").sort_values("timestamp_utc").reset_index(drop=True)


def _worker(args) -> list[dict]:
    ticker, paths, cuts = args
    from dir002_replay import read_bars
    from domain.structure_behaviour.engine import analyse_ticker
    from domain.structure_behaviour.policy import load_policy
    policy = load_policy()
    bars = _load_5m(paths)
    if bars.empty:
        return []
    days = _ny_date(bars["timestamp_utc"])
    daily_all = read_bars(ticker)
    out: list[dict] = []
    stored = sorted(paths)
    for cut in cuts:
        if cut not in paths:
            continue
        hist_sessions = [s for s in stored if s <= cut][-HISTORY_SESSIONS:]
        hist = bars[days.astype(str).isin(hist_sessions)].reset_index(drop=True)
        daily = daily_all[daily_all["date"].astype(str) <= cut].reset_index(drop=True)
        if len(hist) == 0 or len(daily) < 30:
            continue
        try:
            result = analyse_ticker(ticker, daily, hist, policy, intraday_status="HISTORICAL_REPLAY")
        except Exception as exc:
            out.append({"ticker": ticker, "cut": cut, "engine_error": type(exc).__name__})
            continue
        close = float(hist["close"].iloc[-1])
        for tf in MINUTES:
            fwd = None
            for c in (result.get("readings", {}).get(tf, {}) or {}).get("candidates", []) or []:
                state, direction = str(c.get("Signal_State") or ""), str(c.get("Direction") or "")
                if state not in LIVE or direction not in ("BULL", "BEAR"):
                    continue
                tests = []
                outcome, trigger = c.get("Outcome_Level"), c.get("Trigger_Level")
                if state == "DETECTED":
                    if trigger is not None:
                        tests.append(("ACTIVATION", trigger))
                    if outcome is not None:
                        tests.append(("OUTCOME_FROM_DETECTION", outcome))
                elif outcome is not None:
                    tests.append(("OUTCOME", outcome))
                if not tests or c.get("Invalidation_Level") is None:
                    continue
                if fwd is None:
                    fwd = forward_bars(bars, after_session=cut, timeframe=tf)
                for test, target in tests:
                    try:
                        scored = score(direction=direction, close=close, invalidation=float(c["Invalidation_Level"]),
                                       target=float(target), fwd=fwd, window=WINDOW[tf])
                    except (TypeError, ValueError):
                        scored = None
                    if scored is None:
                        continue
                    out.append({"panel": panel_of(ticker), "ticker": ticker, "cut": cut, "timeframe": tf,
                                "signal_type": c.get("Signal_Type"), "state": state, "direction": direction,
                                "test": test, "cause": scored[0], "time_bars": scored[1],
                                "age_bars": c.get("Age_Bars")})
    return out


def summarise(records: list[dict]) -> dict:
    df = pd.DataFrame([r for r in records if "cause" in r])
    if df.empty:
        return {"rows": 0}
    keys = ["timeframe", "signal_type", "state", "test"]
    rows = []
    for key, g in df.groupby(keys):
        entry = dict(zip(keys, key))
        for panel in ("original", "holdout"):
            p = g[g.panel == panel]
            entry[f"n_{panel}"] = int(len(p))
            entry[f"hit_{panel}"] = round(float((p.cause == "EVENT").mean()), 4) if len(p) else None
        rows.append(entry)
    timing = {}
    for tf, g in df[df.cause == "EVENT"].groupby("timeframe"):
        o, h = g[g.panel == "original"].time_bars, g[g.panel == "holdout"].time_bars
        if len(o) >= 50 and len(h) >= 50:
            q50, q80 = float(o.quantile(0.5)), float(o.quantile(0.8))
            timing[tf] = {"q50_bars": q50, "q80_bars": q80, "holdout_share_le_q50": round(float((h <= q50).mean()), 4),
                          "holdout_share_le_q80": round(float((h <= q80).mean()), 4), "events_holdout": int(len(h))}
    return {"rows": int(len(df)), "groups": rows, "timing": timing,
            "status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "window_bars": WINDOW, "step_sessions": STEP}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--limit", type=int, default=0, help="first N tickers only (pilot)")
    p.add_argument("--workers", type=int, default=6)
    a = p.parse_args()
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    index = session_index()
    tickers = sorted(t for t, s in index.items() if len(s) >= MIN_SESSIONS)
    if a.limit:
        tickers = tickers[:a.limit]
    all_sessions = sorted({s for t in tickers for s in index[t]})
    cuts = all_sessions[HISTORY_SESSIONS:-2:STEP]
    print(json.dumps({"tickers": len(tickers), "sessions": len(all_sessions), "cuts": len(cuts)}), flush=True)
    started, records = time.time(), []
    path = out_dir / "records.jsonl"
    done: set[str] = set()
    if path.exists():                                   # resumable: a finished ticker is marked and skipped
        kept = []
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("ticker_done"):
                done.add(r["ticker_done"])
            else:
                kept.append(r)
        records = [r for r in kept if r.get("ticker") in done]
        path.write_text("".join(json.dumps(r) + "\n" for r in records)
                        + "".join(json.dumps({"ticker_done": t}) + "\n" for t in sorted(done)), encoding="utf-8")
    todo = [t for t in tickers if t not in done]
    print(json.dumps({"already_done": len(done), "to_do": len(todo)}), flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool, open(path, "a", encoding="utf-8") as f:
        futures = {pool.submit(_worker, (t, index[t], cuts)): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            for r in fut.result():
                f.write(json.dumps(r) + "\n")
                records.append(r)
            f.write(json.dumps({"ticker_done": futures[fut]}) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"{i}/{len(todo)} tickers | {len(records)} records | {(time.time() - started) / 60:.0f} min",
                      flush=True)
    (out_dir / "summary.json").write_text(json.dumps(summarise(records), indent=2), encoding="utf-8")
    print(f"done: {len(records)} records in {(time.time() - started) / 60:.0f} min -> {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
