"""IA-6 Transformation loss (scenario register family IA, ACK 19 Sep 2026). Read-only research code.

Question: where along the chain does AVSHUNTER's information survive or die?
Stages, each measured at 1 / 3 / 5 sessions after the evening book session (daily chains end 17 Sep 2026):
  U0  universe            every ticker in the price store (no direction: magnitude and drift only)
  S1  Discovery           every recorded candidate, return in its thesis direction
  S2  ranking             cautious-return rank: Spearman vs directional return, top vs bottom quintile
  S3  tickets             the issued top-5 per session
  S4  option expression   the recorded contract, entry at the ask, exit at the bid at +h (no stop) - and the same
                          trade at mid-to-mid, so the spread's cost is separated from the option's own behaviour
  S5  shipped exit        the rows' option return under the shipped exit (stop / target / hold / last usable)
Population H: signal_ticket_backtest_rows.csv (recorded pre-fix books, 31 Aug - 16 Sep 2026).
Limits stated in the report: 9 sessions, one falling regime, pre-fix candidates and contracts.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from avshunter.shared.xnys_calendar import is_xnys_session  # noqa: E402

HERE = Path(__file__).resolve().parent
ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
PRICES = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAINS = REPO / "data" / "phantom" / "phantom_history.db"
HORIZONS = (1, 3, 5)
DATA_EDGE = "2026-09-17"


def sessions_after(start: str, count: int) -> str | None:
    day, found = date.fromisoformat(start), 0
    while found < count:
        day = date.fromordinal(day.toordinal() + 1)
        if is_xnys_session(day):
            found += 1
    out = day.isoformat()
    return out if out <= DATA_EDGE else None


def closes_on(con, session: str) -> pd.Series:
    rows = con.execute("SELECT ticker, close FROM ohlcv_daily WHERE trading_date = ? AND close > 0", (session,)).fetchall()
    return pd.Series({t: c for t, c in rows}, dtype=float)


def main() -> int:
    rows = pd.read_csv(ROWS, low_memory=False)
    rows["sign"] = rows["direction"].map({"CALL": 1.0, "PUT": -1.0})
    rows["is_ticket"] = rows["ticket"].astype(str).isin(["True", "true", "1"])
    prices = sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)
    chains = sqlite3.connect(f"file:{CHAINS.as_posix()}?mode=ro", uri=True)
    sessions = sorted(rows["session"].unique())
    close_cache: dict[str, pd.Series] = {}

    def closes(s):
        if s not in close_cache:
            close_cache[s] = closes_on(prices, s)
        return close_cache[s]

    report = {"population": "H", "sessions": sessions, "candidates": int(len(rows)),
              "tickets": int(rows["is_ticket"].sum()), "horizons": {}}
    for h in HORIZONS:
        universe, recs = [], []
        for s in sessions:
            end = sessions_after(s, h)
            if end is None:
                continue
            c0, c1 = closes(s), closes(end)
            common = c0.index.intersection(c1.index)
            u = (c1[common] / c0[common] - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
            u = u[u.abs() < 1.0]                                      # drop corporate-action artefacts
            universe.append(pd.DataFrame({"ret": u, "session": s}))
            sub = rows[rows["session"] == s].copy()
            sub["ret"] = sub["ticker"].map(c1) / sub["ticker"].map(c0) - 1.0
            sub["end"] = end
            recs.append(sub)
        if not recs:
            continue
        U = pd.concat(universe)
        C = pd.concat(recs)
        C = C[C["ret"].abs() < 1.0].dropna(subset=["ret", "sign"])
        C["dir_ret"] = C["sign"] * C["ret"]
        # S2: ranking information, per session
        ics = [spearmanr(g["cautious"], g["dir_ret"]).correlation for _, g in C.dropna(subset=["cautious"]).groupby("session")
               if len(g) > 30]
        C["q"] = C.groupby("session")["cautious"].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))
        # S4: option marks at +h (entry ask, exit bid / mid-to-mid)
        opt = []
        for (ticker, end), g in C.groupby(["ticker", "end"]):
            marks = {r[0]: (r[1], r[2]) for r in chains.execute(
                "SELECT option_symbol, bid, ask FROM chain_snapshots WHERE ticker = ? AND quote_date = ?", (ticker, end))}
            for idx, row in g.iterrows():
                m = marks.get(row["contract"])
                if not m or not row["entry_ask"] or row["entry_ask"] <= 0:
                    continue
                bid, ask = m
                entry_mid = (row["entry_ask"] + row["entry_bid"]) / 2.0 if row["entry_bid"] and row["entry_bid"] > 0 else None
                exit_mid = (bid + ask) / 2.0 if bid is not None and ask and ask > 0 else None
                opt.append({"idx": idx, "opt_ask_to_bid": (bid or 0.0) / row["entry_ask"] - 1.0,
                            "opt_mid_to_mid": (exit_mid / entry_mid - 1.0) if entry_mid and exit_mid else np.nan})
        O = pd.DataFrame(opt).set_index("idx") if opt else pd.DataFrame(columns=["opt_ask_to_bid", "opt_mid_to_mid"])
        C = C.join(O)

        def stage(frame):
            return {"n": int(len(frame)), "mean_dir_ret_pct": round(frame["dir_ret"].mean() * 100, 3),
                    "hit_rate": round(float((frame["dir_ret"] > 0).mean()), 3),
                    "mean_abs_move_pct": round(frame["ret"].abs().mean() * 100, 3)}

        def option(frame):
            f = frame.dropna(subset=["opt_ask_to_bid"])
            return {"n_marked": int(len(f)),
                    "mean_ask_to_bid_pct": round(f["opt_ask_to_bid"].mean() * 100, 2) if len(f) else None,
                    "median_ask_to_bid_pct": round(f["opt_ask_to_bid"].median() * 100, 2) if len(f) else None,
                    "mean_mid_to_mid_pct": round(f["opt_mid_to_mid"].mean() * 100, 2) if len(f) else None,
                    "share_profitable_ask_to_bid": round(float((f["opt_ask_to_bid"] > 0).mean()), 3) if len(f) else None}

        report["horizons"][h] = {
            "U0_universe": {"n": int(len(U)), "mean_ret_pct": round(U["ret"].mean() * 100, 3),
                            "mean_abs_move_pct": round(U["ret"].abs().mean() * 100, 3)},
            "S1_discovery_all": stage(C),
            "S1_by_direction": {d: stage(g) for d, g in C.groupby("direction")},
            "S2_ranking": {"mean_session_spearman_cautious_vs_dir_ret": round(float(np.nanmean(ics)), 3) if ics else None,
                           "sessions": len(ics),
                           "top_quintile": stage(C[C["q"] == 4]), "bottom_quintile": stage(C[C["q"] == 0])},
            "S3_tickets": stage(C[C["is_ticket"]]),
            "S4_option_all": option(C), "S4_option_top_quintile": option(C[C["q"] == 4]),
            "S4_option_tickets": option(C[C["is_ticket"]]),
        }
    closed = rows[rows["option_state"] == "CLOSED"]
    report["S5_shipped_exit"] = {
        "all_closed": {"n": int(len(closed)), "mean_pct": round(closed["option_return"].mean() * 100, 2),
                       "median_pct": round(closed["option_return"].median() * 100, 2)},
        "tickets_closed": {"n": int(closed["is_ticket"].sum()),
                           "mean_pct": round(closed.loc[closed["is_ticket"], "option_return"].mean() * 100, 2)},
    }
    out = HERE / "ia6_transformation_loss_H.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
