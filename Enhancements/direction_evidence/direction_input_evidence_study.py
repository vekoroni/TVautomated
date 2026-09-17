"""Item 4 step 1 (ACK 17 Sep 2026): evidence study of every directional input (read-only).

For each recorded run (one per evidence session; the evening/latest run wins), merge the candidate tables
(discovery candidates, Vanguard signals, EIL-enriched, execution) by ticker. For each input measure, across
sessions, whether it predicts the forward return of the underlying from the evidence-session close:

  A  cross-sectional information coefficient (Spearman) of the input vs the forward log return net of the
     session's cross-sectional median (removes the market's own drift) — "higher input, higher return";
  B  IC of the input vs the THESIS return (forward net return signed by the pipeline's final CALL/PUT) —
     "does the input tell us when the pipeline's call is right";
  C  for categorical direction labels (CALL/PUT, BULLISH/BEARISH, ...): hit rate of the label's sign vs the
     net return sign and mean signed net return.

Horizons 1, 5, 10, 20 sessions. Per-session ICs need >= 30 tickers. t-statistics use an effective session count
reduced for overlapping horizons (n / ceil(h / median session gap)). Stability: same sign in the first and second
half of sessions. Multiple testing: Benjamini-Hochberg at q = 0.10 over all (input, horizon, test) pairs.
Price history integrity: tickers with a one-bar 10x move or sub-cent prices inside the window are excluded.

  venv\\Scripts\\python.exe Enhancements\\direction_evidence\\direction_input_evidence_study.py
"""

from __future__ import annotations

from datetime import date
import glob
import json
import math
import os
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from avshunter.c12_outcome.records import resolve_evidence_session  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session  # noqa: E402

RUNS = ROOT / "data" / "output" / "runs"
PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"
OUT = Path(__file__).resolve().parent
HORIZONS = (1, 5, 10, 20)
MIN_TICKERS = 30
FDR_Q = 0.10
EXCLUDE_TOKENS = ("price", "stop", "target", "strike", "bid", "ask", "mid", "premium", "spot", "breakeven", "invalidation",
                  "timestamp", "_ts", "rank", "row", "index", "version", "hash", "sha", "id", "dte", "expiry", "date",
                  "size", "volume", "oi", "open_interest", "multiplier", "n_obs", "n_observations", "count", "chain_rows",
                  "poc", "value_area", "level", "wall", "max_pain", "outcome", "realised", "realized", "future", "exit")
LABEL_MAP = {"CALL": 1, "PUT": -1, "BULL": 1, "BEAR": -1, "BULLISH": 1, "BEARISH": -1, "LONG": 1, "SHORT": -1,
             "UP": 1, "DOWN": -1, "LONG_CALL": 1, "LONG_PUT": -1}


def run_tables(run_dir: Path) -> pd.DataFrame | None:
    run = run_dir.name
    base_path = run_dir / "superbrain" / f"eil_enriched_{run}.csv"
    if not base_path.exists():
        base_path = run_dir / "options" / f"options_intelligence_{run}.csv"
        if not base_path.exists():
            return None
    base = pd.read_csv(base_path, low_memory=False)
    base["ticker"] = base["ticker"].astype(str).str.upper()
    base = base.drop_duplicates("ticker")
    for rel in (f"discovery/discovery_candidates_ultimate_{run}.csv", "vanguard/vanguard_signals.csv",
                f"execution/execution_v3_5_{run}.csv"):
        path = run_dir / rel
        if not path.exists():
            continue
        extra = pd.read_csv(path, low_memory=False)
        if "ticker" not in extra.columns:
            continue
        extra["ticker"] = extra["ticker"].astype(str).str.upper()
        extra = extra.drop_duplicates("ticker")
        new = ["ticker"] + [c for c in extra.columns if c not in base.columns]
        base = base.merge(extra[new], on="ticker", how="left")
    return base


def evidence_session_for(run_dir: Path, frame: pd.DataFrame) -> date | None:
    meta = {}
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            meta = {}
    thesis = next((t for t in frame.get("thesis_id", pd.Series(dtype=object)).dropna().astype(str) if t.count(":") >= 2), None)
    return resolve_evidence_session(thesis, meta, run_dir.name).session


def forward_returns(tickers, session: date) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    con.execute("CREATE TEMP TABLE w(t TEXT PRIMARY KEY)")
    con.executemany("INSERT OR IGNORE INTO w VALUES (?)", [(t,) for t in tickers])
    bars = pd.read_sql_query(
        "SELECT o.ticker, o.trading_date, o.close FROM ohlcv_daily o JOIN w ON w.t = o.ticker "
        "WHERE o.bar_status = 'COMPLETE' AND o.trading_date >= ? AND o.trading_date <= date(?, '+45 days') "
        "ORDER BY o.ticker, o.trading_date", con, params=(session.isoformat(), session.isoformat()))
    con.close()
    out = {}
    for ticker, g in bars.groupby("ticker"):
        g = g.reset_index(drop=True)
        if g.empty or g.loc[0, "trading_date"] != session.isoformat():
            continue
        closes = g["close"].to_numpy()
        steps = np.abs(np.diff(np.log(closes))) if len(closes) > 1 else np.array([])
        row = {}
        for h in HORIZONS:
            if len(closes) > h and closes[0] >= 0.01 and np.all(closes[:h + 1] >= 0.01) and not np.any(steps[:h] >= math.log(10)):
                row[f"fwd_{h}"] = math.log(closes[h] / closes[0])
        out[ticker] = row
    return pd.DataFrame.from_dict(out, orient="index")


def usable_numeric(frame: pd.DataFrame):
    cols = []
    for c in frame.columns:
        low = c.lower()
        if c.startswith("fwd_") or any(tok in low for tok in EXCLUDE_TOKENS):
            continue
        s = pd.to_numeric(frame[c], errors="coerce")
        if s.notna().mean() >= 0.3 and s.nunique() > 2:
            cols.append(c)
    return cols


def directional_labels(frame: pd.DataFrame):
    cols = []
    for c in frame.columns:
        if frame[c].dtype != object or c.startswith("fwd_"):
            continue
        mapped = frame[c].astype(str).str.upper().str.strip().map(LABEL_MAP)
        if mapped.notna().mean() >= 0.3 and mapped.dropna().nunique() == 2:
            cols.append(c)
    return cols


def main():
    per_session = []   # rows: session, input, kind, horizon, ic_raw, ic_thesis, hit, mean_signed, n
    run_dirs = sorted(p for p in RUNS.iterdir() if p.is_dir() and len(p.name) == 15 and p.name[:8].isdigit())
    chosen = {}
    for run_dir in run_dirs:
        frame = run_tables(run_dir)
        if frame is None:
            continue
        session = evidence_session_for(run_dir, frame)
        if session is None or not is_xnys_session(session):
            continue
        chosen[session] = (run_dir, frame)          # later run for the same session wins
    sessions = sorted(chosen)
    print(f"sessions: {len(sessions)} ({sessions[0]} .. {sessions[-1]})", flush=True)
    for session in sessions:
        run_dir, frame = chosen[session]
        fwd = forward_returns(frame["ticker"].tolist(), session)
        data = frame.set_index("ticker").join(fwd, how="inner")
        if len(data) < MIN_TICKERS:
            continue
        direction = data.get("final_direction", pd.Series(index=data.index, dtype=object)).astype(str).str.upper().map(LABEL_MAP)
        numeric = usable_numeric(data.reset_index())
        labels = directional_labels(data.reset_index())
        for h in HORIZONS:
            col = f"fwd_{h}"
            if col not in data.columns:
                continue
            net = data[col] - data[col].median()
            thesis = net * direction
            for c in numeric:
                x = pd.to_numeric(data[c], errors="coerce")
                ok = x.notna() & net.notna()
                if ok.sum() < MIN_TICKERS or x[ok].nunique() < 3:
                    continue
                ic_raw = stats.spearmanr(x[ok], net[ok]).statistic
                okt = ok & thesis.notna()
                ic_thesis = stats.spearmanr(x[okt], thesis[okt]).statistic if okt.sum() >= MIN_TICKERS else np.nan
                per_session.append({"session": session.isoformat(), "input": c, "kind": "NUMERIC", "horizon": h,
                                    "ic_raw": ic_raw, "ic_thesis": ic_thesis, "n": int(ok.sum()), "run": run_dir.name})
            for c in labels:
                sign = data[c].astype(str).str.upper().str.strip().map(LABEL_MAP)
                ok = sign.notna() & net.notna()
                if ok.sum() < MIN_TICKERS:
                    continue
                signed = sign[ok] * net[ok]
                per_session.append({"session": session.isoformat(), "input": c, "kind": "LABEL", "horizon": h,
                                    "hit": float((signed > 0).mean()), "mean_signed_bps": float(signed.mean() * 1e4),
                                    "n": int(ok.sum()), "run": run_dir.name})
        print(f"{session} {run_dir.name}: tickers {len(data)}, numeric {len(numeric)}, labels {len(labels)}", flush=True)
    ps = pd.DataFrame(per_session)
    ps.to_csv(OUT / "direction_input_per_session.csv", index=False)
    gaps = np.diff(sorted(date.fromisoformat(s).toordinal() for s in ps["session"].unique()))
    median_gap_sessions = max(1.0, float(np.median(gaps)) * 5 / 7) if len(gaps) else 1.0

    summary = []
    for (inp, kind, h), g in ps.groupby(["input", "kind", "horizon"]):
        g = g.sort_values("session")
        overlap = math.ceil(h / median_gap_sessions)
        metrics = ["ic_raw", "ic_thesis"] if kind == "NUMERIC" else ["mean_signed_bps"]
        for m in metrics:
            v = g[m].dropna().to_numpy()
            if len(v) < 6:
                continue
            n_eff = max(2.0, len(v) / overlap)
            sd = v.std(ddof=1)
            t = float(v.mean() / (sd / math.sqrt(n_eff))) if sd > 0 else 0.0
            p = float(2 * stats.t.sf(abs(t), df=max(1, n_eff - 1)))
            half = len(v) // 2
            stable = bool(np.sign(v[:half].mean()) == np.sign(v[half:].mean()) and v[:half].mean() != 0)
            row = {"input": inp, "kind": kind, "horizon": h, "metric": m, "sessions": len(v), "mean": float(v.mean()),
                   "t": t, "p": p, "stable_halves": stable, "first_half": float(v[:half].mean()),
                   "second_half": float(v[half:].mean()), "median_tickers": float(g["n"].median())}
            if kind == "LABEL":
                row["hit_rate_mean"] = float(g["hit"].mean())
            summary.append(row)
    sm = pd.DataFrame(summary)
    sm = sm.sort_values("p").reset_index(drop=True)
    m_tests = len(sm)
    sm["bh_threshold"] = FDR_Q * (np.arange(1, m_tests + 1) / m_tests)
    passed = sm["p"] <= sm["bh_threshold"]
    last = passed[passed].index.max() if passed.any() else -1
    sm["fdr_significant"] = sm.index <= last
    sm["evidence"] = np.where(sm["fdr_significant"] & sm["stable_halves"], "SIGNIFICANT_AND_STABLE",
                              np.where(sm["fdr_significant"], "SIGNIFICANT_UNSTABLE", "NO_EVIDENCE"))
    sm.to_csv(OUT / "direction_input_evidence_summary.csv", index=False)
    payload = {
        "sessions": [s.isoformat() for s in sessions], "tests": m_tests, "fdr_q": FDR_Q,
        "median_session_gap_sessions": median_gap_sessions,
        "evidence_counts": sm["evidence"].value_counts().to_dict(),
        "pipeline_direction": sm[(sm["input"] == "final_direction")].to_dict("records"),
        "top_stable": sm[sm["evidence"] == "SIGNIFICANT_AND_STABLE"].head(40).to_dict("records"),
    }
    (OUT / "direction_input_evidence.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("tests", "evidence_counts")}, indent=1))
    print(pd.DataFrame(payload["pipeline_direction"]).to_string(index=False) if payload["pipeline_direction"] else "no final_direction rows")
    print(sm[sm["evidence"] != "NO_EVIDENCE"].head(30)[["input", "kind", "horizon", "metric", "sessions", "mean", "t", "p", "stable_halves", "evidence"]].to_string(index=False))


if __name__ == "__main__":
    main()
