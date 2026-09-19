"""Batch 4 - FX extreme-winner forensics (scenario register FX-1/2/3, ACK 19 Sep 2026). Read-only research code.

Population H: closed trades in signal_ticket_backtest_rows.csv (shipped exit), 31 Aug - 16 Sep 2026.
Winners: option return >= +100% (FX-1; >= +200% listed as case studies). Comparison: losers (return < 0) from the
same sessions and direction (FX-2). Calls and puts separately (FX-3).
State at entry is rebuilt point-in-time from the run that issued the candidate (options, Discovery and Vanguard
outputs of that run), bar features from the price store up to the book session, and IV history from the IV cache
strictly before the session. Numeric features: medians, standardised mean difference, Mann-Whitney p.
Categorical: rate in winners vs losers. Small samples: findings are hypotheses for layer A/B, never selection rules.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
HERE = Path(__file__).resolve().parent
ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
RUNS = REPO / "data" / "output" / "runs"
PRICES = REPO / "data" / "canonical" / "historical_prices.sqlite"
IV_CACHE = REPO / "data" / "cache" / "iv_history_cache.db"

OPTION_FIELDS = ["contract_delta", "contract_gamma", "contract_oi", "contract_volume", "horizon_bucket", "sector_etf",
                 "pcr_oi", "iv_rank", "iv_vs_hv", "term_structure", "skew_label", "risk_reversal",
                 "gamma_flip_gap_pct", "options_score", "days_to_catalyst", "layer2__vol_regime",
                 "layer2__adjusted_prob_target_hit"]
DISCOVERY_FIELDS = ["wyckoff_mode", "wyckoff_phase_bucket", "wyckoff_validation_phase_maturity_score",
                    "wyckoff_validation_transition_probability_5_bars", "crabel_state", "crabel_compression",
                    "gap_pct", "pct_from_52w_low", "days_to_trigger"]


def load_run_state(run_id: str) -> pd.DataFrame:
    parts = []
    opt = RUNS / run_id / "options" / f"options_intelligence_{run_id}.csv"
    if opt.is_file():
        o = pd.read_csv(opt, low_memory=False)
        parts.append(o[["ticker"] + [c for c in OPTION_FIELDS if c in o.columns]].drop_duplicates("ticker"))
    for disc in (RUNS / run_id / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv",
                 REPO / "data" / "output" / f"discovery_candidates_ultimate_{run_id}.csv"):
        if disc.is_file():
            d = pd.read_csv(disc, low_memory=False)
            parts.append(d[["ticker"] + [c for c in DISCOVERY_FIELDS if c in d.columns]].drop_duplicates("ticker"))
            break
    out = parts[0] if parts else pd.DataFrame(columns=["ticker"])
    for p in parts[1:]:
        out = out.merge(p, on="ticker", how="outer")
    out["run_id"] = run_id
    return out


def bar_features(sessions) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    f = pd.read_sql_query("SELECT ticker, trading_date, high, low, close, volume FROM ohlcv_daily "
                          "WHERE trading_date >= '2025-07-01' AND trading_date <= '2026-09-18'", con)
    con.close()
    w = {k: f.pivot_table(index="trading_date", columns="ticker", values=k, aggfunc="last").sort_index()
         for k in ("high", "low", "close", "volume")}
    close, high, low, vol = w["close"], w["high"], w["low"], w["volume"]
    prev = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev).abs(), (low - prev).abs()))
    atr_rank = (tr.ewm(span=14, adjust=False).mean() / close).rolling(252, min_periods=60).rank(pct=True)
    bb_rank = (4 * close.rolling(20).std() / close.rolling(20).mean()).rolling(252, min_periods=60).rank(pct=True)
    feats = {"bar_compression_score": -(atr_rank + bb_rank), "bar_volume_ratio_20d": vol / vol.rolling(20).mean().shift(1),
             "bar_ret_5d": close / close.shift(5) - 1, "bar_ret_20d": close / close.shift(20) - 1,
             "bar_rv20": np.log(close / prev).rolling(20).std() * np.sqrt(252)}
    rows = []
    for s in sessions:
        if s in close.index:
            frame = pd.DataFrame({k: v.loc[s] for k, v in feats.items()})
            frame["session"] = s
            rows.append(frame.rename_axis("ticker").reset_index())
    return pd.concat(rows)


def iv_features(tickers, sessions) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{IV_CACHE.as_posix()}?mode=ro", uri=True)
    iv = pd.read_sql_query("SELECT ticker, sample_date, atm_iv FROM iv_history WHERE sample_date >= '2025-08-01' "
                           "AND atm_iv > 0", con)
    con.close()
    iv = iv[iv.ticker.isin(tickers)]
    out = []
    for t, g in iv.groupby("ticker"):
        g = g.sort_values("sample_date")
        for s in sessions:
            past = g[g.sample_date < s]
            today = g[g.sample_date == s]
            if len(past) >= 20 and len(today):
                now = float(today.atm_iv.iloc[0])
                recent = past[past.sample_date >= (pd.Timestamp(s) - pd.Timedelta(days=21)).strftime("%Y-%m-%d")]
                out.append({"ticker": t, "session": s,
                            "iv_true_percentile": float((past.atm_iv < now).mean()),
                            "iv_change_recent": (now / float(recent.atm_iv.iloc[0]) - 1) if len(recent) else np.nan})
    return pd.DataFrame(out)


def compare(win: pd.DataFrame, lose: pd.DataFrame, numeric, categorical) -> dict:
    res = {"numeric": {}, "categorical": {}}
    for c in numeric:
        a, b = pd.to_numeric(win[c], errors="coerce").dropna(), pd.to_numeric(lose[c], errors="coerce").dropna()
        if len(a) < 5 or len(b) < 5:
            continue
        pooled = np.sqrt((a.var() + b.var()) / 2) or np.nan
        res["numeric"][c] = {"n_win": int(len(a)), "median_win": round(float(a.median()), 4),
                             "median_lose": round(float(b.median()), 4),
                             "std_diff": round(float((a.mean() - b.mean()) / pooled), 3) if pooled == pooled else None,
                             "p": round(float(mannwhitneyu(a, b).pvalue), 4)}
    for c in categorical:
        if c not in win:
            continue
        rw, rl = win[c].astype(str).value_counts(normalize=True), lose[c].astype(str).value_counts(normalize=True)
        res["categorical"][c] = {k: {"win": round(float(rw.get(k, 0)), 3), "lose": round(float(rl.get(k, 0)), 3)}
                                 for k in sorted(set(rw.index) | set(rl.index)) if rw.get(k, 0) + rl.get(k, 0) > 0.05}
    return res


def main() -> int:
    rows = pd.read_csv(ROWS, low_memory=False)
    closed = rows[rows.option_state == "CLOSED"].copy()
    closed["strike"] = closed.contract.str[-8:].astype(float) / 1000.0
    sign = np.where(closed.direction == "CALL", 1.0, -1.0)
    closed["moneyness"] = sign * (closed.spot - closed.strike) / closed.spot          # negative = out of the money
    closed["iv_over_forecast"] = closed.iv / closed.forecast_vol
    closed["stop_distance"] = (closed.spot - closed.stop).abs() / closed.spot
    closed["target_distance"] = (closed.target - closed.spot).abs() / closed.spot
    state = pd.concat([load_run_state(r) for r in closed.run_id.unique()])
    closed = closed.merge(state, on=["run_id", "ticker"], how="left")
    sessions = sorted(closed.session.unique())
    closed = closed.merge(bar_features(sessions), on=["ticker", "session"], how="left")
    closed = closed.merge(iv_features(set(closed.ticker), sessions), on=["ticker", "session"], how="left")
    numeric = ["moneyness", "dte", "entry_ask", "spread_fraction", "iv", "forecast_vol", "iv_over_forecast",
               "stop_distance", "target_distance", "cautious", "central", "upside", "contract_delta", "contract_gamma",
               "contract_oi", "contract_volume", "pcr_oi", "iv_rank", "iv_vs_hv", "risk_reversal", "gamma_flip_gap_pct",
               "options_score", "days_to_catalyst", "layer2__adjusted_prob_target_hit",
               "wyckoff_validation_phase_maturity_score", "wyckoff_validation_transition_probability_5_bars",
               "crabel_compression", "gap_pct", "pct_from_52w_low", "days_to_trigger", "bar_compression_score",
               "bar_volume_ratio_20d", "bar_ret_5d", "bar_ret_20d", "bar_rv20", "iv_true_percentile", "iv_change_recent"]
    categorical = ["horizon_bucket", "term_structure", "skew_label", "layer2__vol_regime", "wyckoff_mode",
                   "wyckoff_phase_bucket", "crabel_state", "sector_etf"]
    report = {"population": "H closed (shipped exit)", "closed": int(len(closed)),
              "winners_ge_100": int((closed.option_return >= 1).sum()),
              "winners_ge_200": int((closed.option_return >= 2).sum()), "by_direction": {}}
    for d, g in closed.groupby("direction"):
        win, lose = g[g.option_return >= 1], g[g.option_return < 0]
        report["by_direction"][d] = {"n": int(len(g)), "winners": int(len(win)), "losers": int(len(lose)),
                                     **compare(win, lose, numeric, categorical)}
    cases = closed[closed.option_return >= 2].sort_values("option_return", ascending=False)
    report["cases_ge_200"] = cases[["session", "ticker", "direction", "contract", "option_return", "moneyness", "dte",
                                    "entry_ask", "spread_fraction", "iv_over_forecast", "bar_compression_score",
                                    "bar_volume_ratio_20d", "iv_true_percentile", "layer2__vol_regime",
                                    "wyckoff_phase_bucket", "thesis_sessions"]].round(4).to_dict("records")
    (HERE / "fx_extreme_winner_forensics_H.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    for d, v in report["by_direction"].items():
        print(f"\n== {d}: n {v['n']} winners {v['winners']} losers {v['losers']}")
        ranked = sorted(v["numeric"].items(), key=lambda kv: kv[1]["p"])
        for c, s in ranked[:14]:
            print(f"  {c:48s} win {s['median_win']:>10} lose {s['median_lose']:>10} sd {s['std_diff']:>7} p {s['p']}")
    print("\ncases >= +200%:")
    for c in report["cases_ge_200"]:
        print(" ", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
