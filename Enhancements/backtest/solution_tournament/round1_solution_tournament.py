"""AVSHUNTER solution tournament, round 1 (research only).

This script does not import or mutate pipeline authority.  It compares alternate
direction, pricing, ranking, and expression routes on the same frozen historical
candidate rows.  All inputs are opened read-only and every result is labelled
exploratory because population H contains only nine independent sessions.

The purpose is failure localisation and alternate-solution discovery before any
production build.  It is not a promotion test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from avshunter.shared.xnys_calendar import is_xnys_session  # noqa: E402


HERE = Path(__file__).resolve().parent
ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
IV_DB = REPO / "data" / "cache" / "iv_history_cache.db"
HORIZONS = (1, 3, 5)
DATA_EDGE = "2026-09-17"
SEED = 19092026
OCC = re.compile(r"(?P<side>[CP])(?P<strike>\d{8})$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sessions_after(start: str, count: int) -> str | None:
    day, found = date.fromisoformat(start), 0
    while found < count:
        day = date.fromordinal(day.toordinal() + 1)
        if is_xnys_session(day):
            found += 1
    result = day.isoformat()
    return result if result <= DATA_EDGE else None


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def db_summary(path: Path, table: str, date_column: str, ticker_column: str) -> dict:
    con = read_only(path)
    try:
        row = con.execute(
            f"SELECT MIN({date_column}), MAX({date_column}), COUNT(DISTINCT {date_column}), "
            f"COUNT(DISTINCT {ticker_column}) FROM {table}"
        ).fetchone()
        table_info = [tuple(r) for r in con.execute(f"PRAGMA table_info({table})")]
    finally:
        con.close()
    return {
        "path": str(path.relative_to(REPO)),
        # The Phantom store is tens of gigabytes.  Hash the schema and bind the
        # file metadata here; individual observations retain their canonical
        # dataset identities elsewhere.  A full-file hash would add no research
        # value and would make each exploratory run unnecessarily expensive.
        "schema_sha256": hashlib.sha256(
            json.dumps(table_info, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
        "bytes": path.stat().st_size,
        "modified_ns": path.stat().st_mtime_ns,
        "table": table,
        "date_min": row[0],
        "date_max": row[1],
        "distinct_dates": int(row[2]),
        "distinct_tickers": int(row[3]),
        "columns": [r[1] for r in table_info],
    }


def run_truth(rows: pd.DataFrame) -> list[dict]:
    result = []
    for run_id in sorted(rows["run_id"].dropna().astype(str).unique()):
        path = REPO / "data" / "output" / "runs" / run_id / "run_meta.json"
        if not path.is_file():
            result.append({"run_id": run_id, "run_meta": "MISSING"})
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        identity = payload.get("code_identity") or {}
        result.append({
            "run_id": run_id,
            "run_meta": "PRESENT",
            "run_kind": payload.get("run_kind"),
            "run_condition": payload.get("run_condition") or (payload.get("dynamic_plan") or {}).get("run_condition"),
            "session_date": payload.get("session_date"),
            "commit": identity.get("commit_hash") or payload.get("baseline_commit_hash"),
            "dirty": identity.get("dirty"),
            "baseline_eligible": payload.get("baseline_eligible"),
        })
    return result


def closes_on(con: sqlite3.Connection, session: str) -> pd.Series:
    found = con.execute(
        "SELECT ticker, close FROM ohlcv_daily WHERE trading_date = ? AND close > 0", (session,)
    ).fetchall()
    return pd.Series({ticker: close for ticker, close in found}, dtype=float)


def trailing_close(con: sqlite3.Connection, session: str, lookback: int) -> pd.Series:
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT trading_date FROM ohlcv_daily WHERE trading_date < ? ORDER BY trading_date DESC LIMIT ?",
        (session, lookback),
    )]
    if len(dates) < lookback:
        return pd.Series(dtype=float)
    return closes_on(con, dates[-1])


def block_bootstrap_mean(frame: pd.DataFrame, column: str, samples: int = 3000) -> dict:
    clean = frame[["session", column]].dropna()
    sessions = clean["session"].unique()
    if clean.empty or len(sessions) < 2:
        return {"n": int(len(clean)), "sessions": int(len(sessions)), "mean": None, "ci90": [None, None]}
    by_session = {s: clean.loc[clean.session == s, column].to_numpy(float) for s in sessions}
    rng = np.random.default_rng(SEED)
    means = np.empty(samples)
    for i in range(samples):
        draw = rng.choice(sessions, size=len(sessions), replace=True)
        means[i] = np.concatenate([by_session[s] for s in draw]).mean()
    return {
        "n": int(len(clean)),
        "sessions": int(len(sessions)),
        "mean": round(float(clean[column].mean()), 6),
        "median": round(float(clean[column].median()), 6),
        "hit_rate": round(float((clean[column] > 0).mean()), 4),
        "ci90": [round(float(v), 6) for v in np.quantile(means, [0.05, 0.95])],
    }


def tail_summary(frame: pd.DataFrame, column: str) -> dict:
    clean = frame[["session", column]].dropna()
    base = block_bootstrap_mean(clean, column)
    values = clean[column]
    positive = values[values > 0].sum()
    base.update({
        "share_ge_50pct": round(float((values >= 0.5).mean()), 4) if len(values) else None,
        "share_ge_100pct": round(float((values >= 1.0).mean()), 4) if len(values) else None,
        "share_ge_200pct": round(float((values >= 2.0).mean()), 4) if len(values) else None,
        "share_ge_500pct": round(float((values >= 5.0).mean()), 4) if len(values) else None,
        "largest_winner": round(float(values.max()), 4) if len(values) else None,
        "tail_contribution_ge_100pct": (
            round(float(values[values >= 1.0].sum() / positive), 4) if positive > 0 else None
        ),
    })
    return base


def parse_strike(symbol: str) -> float | None:
    match = OCC.search(str(symbol).upper())
    return int(match.group("strike")) / 1000.0 if match else None


@dataclass(frozen=True)
class Quote:
    bid: float | None
    ask: float | None


def quote_map(con: sqlite3.Connection, ticker: str, session: str) -> dict[str, Quote]:
    rows = con.execute(
        "SELECT option_symbol, bid, ask FROM chain_snapshots WHERE ticker = ? AND quote_date = ?",
        (ticker, session),
    ).fetchall()
    return {str(symbol): Quote(bid, ask) for symbol, bid, ask in rows}


def rank_top(frame: pd.DataFrame, key: str, ascending: bool = False, n: int = 5) -> pd.DataFrame:
    parts = []
    for _, group in frame.dropna(subset=[key]).groupby("session"):
        parts.append(group.sort_values(key, ascending=ascending).head(n))
    return pd.concat(parts, ignore_index=False) if parts else frame.iloc[0:0]


def main() -> int:
    HERE.mkdir(parents=True, exist_ok=True)
    rows = pd.read_csv(ROWS, low_memory=False)
    rows["session"] = rows["session"].astype(str)
    rows["is_ticket"] = rows["ticket"].astype(str).str.lower().isin(["true", "1"])
    rows["sign_current"] = rows["direction"].map({"CALL": 1.0, "PUT": -1.0})
    rows["strike"] = rows["contract"].map(parse_strike)
    rows["moneyness_abs"] = (rows["strike"] / rows["spot"] - 1.0).abs()
    rows["iv_price_ratio"] = rows["forecast_vol"] / rows["iv"]

    manifest = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "population": "H_PRE_FIX",
        "frozen_rows": {
            "path": str(ROWS.relative_to(REPO)),
            "sha256": sha256(ROWS),
            "rows": int(len(rows)),
            "sessions": sorted(rows["session"].unique().tolist()),
            "distinct_sessions": int(rows["session"].nunique()),
            "distinct_tickers": int(rows["ticker"].nunique()),
            "missing": {c: int(rows[c].isna().sum()) for c in rows.columns},
        },
        "stores": {
            "prices": db_summary(PRICE_DB, "ohlcv_daily", "trading_date", "ticker"),
            "chains": db_summary(CHAIN_DB, "chain_snapshots", "quote_date", "ticker"),
            "iv_history": db_summary(IV_DB, "iv_history", "sample_date", "ticker"),
        },
        "run_truth": run_truth(rows),
        "limitations": [
            "Only nine independent H sessions; session count, not row count, governs inference.",
            "H contains pre-fix candidates and selected contracts.",
            "The tournament tests selected-contract alternatives; full family re-selection is a later round.",
            "No capital allocation is modelled.",
            "Macro has no score, gate, rank, or direction authority.",
            "Results do not change production authority.",
        ],
    }
    (HERE / "round1_input_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    prices = read_only(PRICE_DB)
    chains = read_only(CHAIN_DB)
    close_cache: dict[str, pd.Series] = {}
    prior5_cache: dict[str, pd.Series] = {}
    prior20_cache: dict[str, pd.Series] = {}

    def closes(session: str) -> pd.Series:
        if session not in close_cache:
            close_cache[session] = closes_on(prices, session)
        return close_cache[session]

    records = []
    try:
        for horizon in HORIZONS:
            for session in sorted(rows["session"].unique()):
                end = sessions_after(session, horizon)
                if end is None:
                    continue
                c0, c1 = closes(session), closes(end)
                if session not in prior5_cache:
                    prior5_cache[session] = trailing_close(prices, session, 5)
                    prior20_cache[session] = trailing_close(prices, session, 20)
                p5, p20 = prior5_cache[session], prior20_cache[session]
                sub = rows[rows.session == session].copy()
                sub["end_session"] = end
                sub["underlying_return"] = sub["ticker"].map(c1) / sub["ticker"].map(c0) - 1.0
                sub["ret5_entry"] = sub["ticker"].map(c0) / sub["ticker"].map(p5) - 1.0
                sub["ret20_entry"] = sub["ticker"].map(c0) / sub["ticker"].map(p20) - 1.0
                sub["sign_mom5"] = np.sign(sub["ret5_entry"])
                sub["sign_mom20"] = np.sign(sub["ret20_entry"])
                sub["sign_meanrev5"] = -sub["sign_mom5"]
                sub["sign_consensus"] = np.where(
                    (sub["sign_mom5"] == sub["sign_mom20"]) & (sub["sign_mom5"] != 0),
                    sub["sign_mom5"],
                    np.nan,
                )

                for (ticker, end_session), group in sub.groupby(["ticker", "end_session"]):
                    marks = quote_map(chains, str(ticker), str(end_session))
                    for idx in group.index:
                        quote = marks.get(str(sub.at[idx, "contract"]))
                        bid = quote.bid if quote else None
                        ask = quote.ask if quote else None
                        entry_bid = sub.at[idx, "entry_bid"]
                        entry_ask = sub.at[idx, "entry_ask"]
                        entry_mid = (entry_bid + entry_ask) / 2 if pd.notna(entry_bid) and entry_bid > 0 and entry_ask > 0 else np.nan
                        exit_mid = (bid + ask) / 2 if bid is not None and ask is not None and ask > 0 else np.nan
                        record = sub.loc[idx].to_dict()
                        record.update({
                            "horizon": horizon,
                            "option_ask_to_bid": (bid / entry_ask - 1.0) if bid is not None and entry_ask > 0 else np.nan,
                            "option_mid_to_mid": (exit_mid / entry_mid - 1.0) if entry_mid > 0 and pd.notna(exit_mid) else np.nan,
                        })
                        records.append(record)
    finally:
        prices.close()
        chains.close()

    panel = pd.DataFrame(records)
    panel = panel[panel["underlying_return"].abs() < 1.0]
    for name in ("current", "mom5", "mom20", "meanrev5", "consensus"):
        panel[f"dirret_{name}"] = panel[f"sign_{name}"] * panel["underlying_return"]
    panel.to_csv(HERE / "round1_panel.csv", index=False)

    direction = {}
    for horizon, group in panel.groupby("horizon"):
        direction[str(horizon)] = {
            name: block_bootstrap_mean(group, f"dirret_{name}")
            for name in ("current", "mom5", "mom20", "meanrev5", "consensus")
        }

    pricing_conditions = {
        "all_selected_contracts": lambda f: pd.Series(True, index=f.index),
        "spread_le_5pct": lambda f: f["spread_fraction"] <= 0.05,
        "spread_le_10pct": lambda f: f["spread_fraction"] <= 0.10,
        "spread_le_15pct": lambda f: f["spread_fraction"] <= 0.15,
        "forecast_iv_ratio_ge_075": lambda f: f["iv_price_ratio"] >= 0.75,
        "forecast_iv_ratio_ge_100": lambda f: f["iv_price_ratio"] >= 1.00,
        "forecast_iv_ratio_ge_125": lambda f: f["iv_price_ratio"] >= 1.25,
        "near_money_2_5pct": lambda f: f["moneyness_abs"] <= 0.025,
        "near_money_5pct": lambda f: f["moneyness_abs"] <= 0.05,
        "price_aware_strict": lambda f: (
            (f["iv_price_ratio"] >= 1.0) & (f["spread_fraction"] <= 0.10) & (f["moneyness_abs"] <= 0.05)
        ),
        "price_aware_broad": lambda f: (
            (f["iv_price_ratio"] >= 0.75) & (f["spread_fraction"] <= 0.15) & (f["moneyness_abs"] <= 0.05)
        ),
    }
    pricing = {}
    expression = {}
    ranking = {}
    for horizon, group in panel.groupby("horizon"):
        pricing[str(horizon)] = {
            name: tail_summary(group[condition(group)], "option_ask_to_bid")
            for name, condition in pricing_conditions.items()
        }
        calls = group[group.direction == "CALL"].copy()
        expression[str(horizon)] = {
            "bullish_shares_all_calls": block_bootstrap_mean(calls, "underlying_return"),
            "long_option_all": tail_summary(group, "option_ask_to_bid"),
            "long_option_price_aware_strict": tail_summary(group[pricing_conditions["price_aware_strict"](group)], "option_ask_to_bid"),
            "long_option_price_aware_broad": tail_summary(group[pricing_conditions["price_aware_broad"](group)], "option_ask_to_bid"),
            "no_trade_when_price_not_favourable": {
                "strict_trade_coverage": round(float(pricing_conditions["price_aware_strict"](group).mean()), 4),
                "broad_trade_coverage": round(float(pricing_conditions["price_aware_broad"](group).mean()), 4),
            },
        }
        candidates = group.dropna(subset=["option_ask_to_bid"]).copy()
        candidates["rank_composite"] = (
            candidates.groupby("session")["cautious"].rank(pct=True)
            + candidates.groupby("session")["iv_price_ratio"].rank(pct=True)
            + candidates.groupby("session")["spread_fraction"].rank(pct=True, ascending=False)
            + candidates.groupby("session")["moneyness_abs"].rank(pct=True, ascending=False)
        ) / 4.0
        ranking[str(horizon)] = {
            "cautious_top5": tail_summary(rank_top(candidates, "cautious"), "option_ask_to_bid"),
            "central_top5": tail_summary(rank_top(candidates, "central"), "option_ask_to_bid"),
            "upside_top5": tail_summary(rank_top(candidates, "upside"), "option_ask_to_bid"),
            "iv_cheapness_top5": tail_summary(rank_top(candidates, "iv_price_ratio"), "option_ask_to_bid"),
            "tight_spread_top5": tail_summary(rank_top(candidates, "spread_fraction", ascending=True), "option_ask_to_bid"),
            "exploratory_composite_top5": tail_summary(rank_top(candidates, "rank_composite"), "option_ask_to_bid"),
        }

    result = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "trial_family": "SOLUTION_TOURNAMENT_ROUND1",
        "population": "H_PRE_FIX",
        "input_manifest_sha256": sha256(HERE / "round1_input_manifest.json"),
        "direction_alternatives": direction,
        "pricing_alternatives": pricing,
        "expression_alternatives": expression,
        "ranking_alternatives": ranking,
        "interpretation_constraints": [
            "Nine H sessions are not enough for promotion.",
            "All alternatives are paired on the same recorded selected contracts.",
            "The composite rank is exploratory and was not pre-registered for confirmation.",
            "Shares and options are reported separately; no capital-weighted blend is inferred.",
            "Contract-family re-selection, intraday timing, and tail opportunity recall are later rounds.",
        ],
    }
    (HERE / "round1_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
