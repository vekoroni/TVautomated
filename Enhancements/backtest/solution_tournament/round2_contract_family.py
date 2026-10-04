"""Round 2: point-in-time contract-family alternative tournament.

Research only.  Reads frozen candidate rows and Phantom chains in SQLite
read-only mode.  It does not import or alter production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from avshunter.shared.xnys_calendar import is_xnys_session  # noqa: E402


HERE = Path(__file__).resolve().parent
ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
PROTOCOL = HERE / "ROUND2_PROTOCOL_20260919.md"
MANIFEST = HERE / "round1_input_manifest.json"
OUTPUT_ROWS = HERE / "round2_contract_family_rows.csv"
OUTPUT_JSON = HERE / "round2_contract_family_results.json"
OUTPUT_REPORT = HERE / "ROUND2_CONTRACT_FAMILY_REPORT_20260919.md"
HORIZONS = (1, 3, 5)
DATA_EDGE = "2026-09-17"
SEED = 19092026


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
    answer = day.isoformat()
    return answer if answer <= DATA_EDGE else None


def spread_fraction(bid: pd.Series, ask: pd.Series) -> pd.Series:
    mid = (bid + ask) / 2.0
    return (ask - bid) / mid


def session_bootstrap(frame: pd.DataFrame, column: str, samples: int = 3000) -> dict:
    clean = frame[["session", column]].dropna()
    sessions = clean["session"].unique()
    result = {
        "n": int(len(clean)),
        "sessions": int(len(sessions)),
        "mean": None,
        "median": None,
        "hit_rate": None,
        "ci90": [None, None],
    }
    if clean.empty:
        return result
    result.update({
        "mean": round(float(clean[column].mean()), 6),
        "median": round(float(clean[column].median()), 6),
        "hit_rate": round(float((clean[column] > 0).mean()), 4),
        "share_ge_50pct": round(float((clean[column] >= 0.5).mean()), 4),
        "share_ge_100pct": round(float((clean[column] >= 1.0).mean()), 4),
        "share_ge_200pct": round(float((clean[column] >= 2.0).mean()), 4),
        "share_ge_500pct": round(float((clean[column] >= 5.0).mean()), 4),
    })
    if len(sessions) < 2:
        return result
    groups = {session: clean.loc[clean.session == session, column].to_numpy(float) for session in sessions}
    rng = np.random.default_rng(SEED)
    estimates = np.empty(samples)
    for index in range(samples):
        draw = rng.choice(sessions, size=len(sessions), replace=True)
        estimates[index] = np.concatenate([groups[session] for session in draw]).mean()
    result["ci90"] = [round(float(value), 6) for value in np.quantile(estimates, [0.05, 0.95])]
    return result


def rank01(series: pd.Series, ascending: bool = True) -> pd.Series:
    if series.notna().sum() <= 1:
        return pd.Series(0.5, index=series.index)
    return series.rank(pct=True, ascending=ascending, method="average")


def normalize_chain(frame: pd.DataFrame, spot: float, forecast_vol: float, hold: int) -> pd.DataFrame:
    if frame.empty:
        result = frame.copy()
        result["common_eligible"] = pd.Series(dtype=bool)
        return result
    result = frame.copy()
    result["bid"] = pd.to_numeric(result["bid"], errors="coerce")
    result["ask"] = pd.to_numeric(result["ask"], errors="coerce")
    result["mid"] = (result["bid"] + result["ask"]) / 2.0
    result["spread_fraction"] = spread_fraction(result["bid"], result["ask"])
    result["moneyness_abs"] = (pd.to_numeric(result["strike"], errors="coerce") / spot - 1.0).abs()
    result["abs_delta"] = pd.to_numeric(result["delta"], errors="coerce").abs()
    result["iv"] = pd.to_numeric(result["iv"], errors="coerce")
    result["cheapness"] = forecast_vol / result["iv"]
    result["activity"] = np.log1p(
        pd.to_numeric(result["volume"], errors="coerce").fillna(0).clip(lower=0)
        + pd.to_numeric(result["open_interest"], errors="coerce").fillna(0).clip(lower=0)
    )
    runway_floor = max(7, math.ceil(max(0, hold) * 7 / 5) + 2)
    valid_delta = result["abs_delta"].between(0.15, 0.85) | result["abs_delta"].isna()
    result["common_eligible"] = (
        (result["bid"] > 0)
        & (result["ask"] >= result["bid"])
        & (result["mid"] > 0)
        & pd.to_numeric(result["dte"], errors="coerce").between(runway_floor, 120)
        & (result["moneyness_abs"] <= 0.20)
        & valid_delta
    )
    return result


def choose(frame: pd.DataFrame, strategy: str, hold: int) -> pd.Series | None:
    if frame.empty or "common_eligible" not in frame:
        return None
    eligible = frame[frame["common_eligible"]].copy()
    if eligible.empty:
        return None
    eligible["delta_distance"] = (eligible["abs_delta"] - 0.45).abs().fillna(1.0)
    if strategy == "F1_TIGHTEST_SPREAD":
        ranked = eligible.sort_values(["spread_fraction", "delta_distance", "moneyness_abs", "dte"])
    elif strategy == "F2_NEAR_MONEY":
        ranked = eligible[(eligible["moneyness_abs"] <= 0.025) & (eligible["spread_fraction"] <= 0.15)]
        ranked = ranked.sort_values(["moneyness_abs", "spread_fraction", "delta_distance", "dte"])
    elif strategy == "F3_DELTA_CORE":
        ranked = eligible[eligible["abs_delta"].between(0.35, 0.55) & (eligible["spread_fraction"] <= 0.15)]
        ranked = ranked.sort_values(["spread_fraction", "delta_distance", "moneyness_abs", "dte"])
    elif strategy == "F4_VALUE_COMPOSITE":
        ranked = eligible[(eligible["spread_fraction"] <= 0.15) & eligible["iv"].gt(0)].copy()
        if not ranked.empty:
            ranked["utility"] = (
                0.40 * rank01(ranked["cheapness"], ascending=True)
                + 0.30 * rank01(ranked["spread_fraction"], ascending=False)
                + 0.20 * rank01(ranked["moneyness_abs"], ascending=False)
                + 0.10 * rank01(ranked["activity"], ascending=True)
            )
            ranked = ranked.sort_values(["utility", "spread_fraction", "moneyness_abs"], ascending=[False, True, True])
    elif strategy == "F5_CONVEX_SATELLITE":
        if hold > 5:
            return None
        ranked = eligible[
            pd.to_numeric(eligible["dte"], errors="coerce").between(7, 21)
            & (eligible["moneyness_abs"] <= 0.02)
            & (eligible["spread_fraction"] <= 0.10)
            & eligible["iv"].gt(0)
            & ((eligible["iv"] / eligible["forecast_vol"]) <= 1.0)
        ]
        ranked = ranked.sort_values(["moneyness_abs", "spread_fraction", "delta_distance", "dte"])
    else:
        raise ValueError(f"unknown strategy: {strategy}")
    return None if ranked.empty else ranked.iloc[0]


@dataclass(frozen=True)
class Mark:
    bid: float | None
    ask: float | None


def outcome(entry_bid: float, entry_ask: float, mark: Mark | None) -> tuple[float | None, float | None]:
    if mark is None or mark.bid is None or mark.ask is None or mark.ask <= 0:
        return None, None
    ask_bid = mark.bid / entry_ask - 1.0 if entry_ask > 0 else None
    entry_mid = (entry_bid + entry_ask) / 2.0
    exit_mid = (mark.bid + mark.ask) / 2.0
    mid_mid = exit_mid / entry_mid - 1.0 if entry_mid > 0 else None
    return ask_bid, mid_mid


def load_chain(con: sqlite3.Connection, ticker: str, session: str, side: str | None = None) -> pd.DataFrame:
    columns = "option_symbol,side,strike,dte,bid,ask,open_interest,volume,iv,delta"
    params: tuple[object, ...]
    if side:
        sql = f"SELECT {columns} FROM chain_snapshots WHERE ticker=? AND quote_date=? AND lower(side)=?"
        params = (ticker, session, side.lower())
    else:
        sql = f"SELECT {columns} FROM chain_snapshots WHERE ticker=? AND quote_date=?"
        params = (ticker, session)
    return pd.read_sql_query(sql, con, params=params)


def population_sets(manifest: dict) -> dict[str, set[str] | None]:
    truth = {item["run_id"]: item for item in manifest["run_truth"]}
    explicit_bad = {
        run_id for run_id, item in truth.items()
        if item.get("run_condition") == "TEST" or item.get("dirty") is True
    }
    certified = {
        run_id for run_id, item in truth.items()
        if item.get("run_condition") == "NORMAL_COMPLETED_SESSION"
        and item.get("dirty") is False
        and item.get("baseline_eligible") is True
    }
    all_runs = set(truth)
    return {
        "all_h_pre_fix": None,
        "exclude_explicit_test_or_dirty": all_runs - explicit_bad,
        "certified_normal_completed_only": certified,
    }


def aggregate(frame: pd.DataFrame, allowed_runs: set[str] | None) -> dict:
    data = frame if allowed_runs is None else frame[frame["run_id"].isin(allowed_runs)]
    result: dict[str, object] = {
        "rows": int(len(data)),
        "sessions": int(data["session"].nunique()),
        "runs": sorted(data["run_id"].unique().tolist()),
        "horizons": {},
    }
    for horizon, group in data.groupby("horizon"):
        strategies = {}
        for strategy, selected in group.groupby("strategy"):
            opportunities = group[group["strategy"] == strategy]
            record = {
                "opportunities": int(len(opportunities)),
                "selected": int(opportunities["selected_symbol"].notna().sum()),
                "exit_marked": int(opportunities["ask_to_bid"].notna().sum()),
                "ask_to_bid": session_bootstrap(selected, "ask_to_bid"),
                "mid_to_mid": session_bootstrap(selected, "mid_to_mid"),
                "same_as_recorded_rate": round(float(selected["same_as_recorded"].mean()), 4)
                if selected["same_as_recorded"].notna().any() else None,
            }
            for threshold, label in ((1.0, "100"), (2.0, "200"), (5.0, "500")):
                oracle = selected[selected["oracle_best_ask_to_bid"] >= threshold]
                record[f"oracle_families_ge_{label}pct"] = int(len(oracle))
                record[f"recall_ge_{label}pct"] = (
                    round(float((oracle["ask_to_bid"] >= threshold).mean()), 4) if len(oracle) else None
                )
            strategies[strategy] = record
        result["horizons"][str(int(horizon))] = strategies
    return result


def main() -> int:
    rows = pd.read_csv(ROWS, low_memory=False)
    rows["session"] = rows["session"].astype(str)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    strategies = (
        "F0_RECORDED",
        "F1_TIGHTEST_SPREAD",
        "F2_NEAR_MONEY",
        "F3_DELTA_CORE",
        "F4_VALUE_COMPOSITE",
        "F5_CONVEX_SATELLITE",
    )
    con = sqlite3.connect(f"file:{CHAIN_DB.as_posix()}?mode=ro", uri=True)
    records: list[dict] = []
    try:
        for _, candidate in rows.iterrows():
            session = str(candidate["session"])
            ticker = str(candidate["ticker"])
            direction = str(candidate["direction"]).upper()
            side = "call" if direction == "CALL" else "put"
            spot = float(candidate["spot"])
            forecast = float(candidate["forecast_vol"])
            hold = int(candidate["hold"])
            entry_chain = normalize_chain(load_chain(con, ticker, session, side), spot, forecast, hold)
            if not entry_chain.empty:
                entry_chain["forecast_vol"] = forecast
            choices: dict[str, pd.Series | None] = {
                strategy: choose(entry_chain, strategy, hold)
                for strategy in strategies if strategy != "F0_RECORDED"
            }
            recorded = None
            if not entry_chain.empty:
                match = entry_chain[entry_chain["option_symbol"] == str(candidate["contract"])]
                if not match.empty:
                    recorded = match.iloc[0]
            for horizon in HORIZONS:
                end = sessions_after(session, horizon)
                if end is None:
                    continue
                end_chain = load_chain(con, ticker, end, side)
                mark_map = {
                    str(row.option_symbol): Mark(
                        float(row.bid) if pd.notna(row.bid) else None,
                        float(row.ask) if pd.notna(row.ask) else None,
                    )
                    for row in end_chain.itertuples()
                }
                oracle_returns = []
                for row in entry_chain[entry_chain["common_eligible"]].itertuples():
                    ask_bid, _ = outcome(float(row.bid), float(row.ask), mark_map.get(str(row.option_symbol)))
                    if ask_bid is not None:
                        oracle_returns.append(ask_bid)
                oracle_best = max(oracle_returns) if oracle_returns else None
                for strategy in strategies:
                    selected = recorded if strategy == "F0_RECORDED" else choices.get(strategy)
                    if selected is None:
                        symbol = None
                        entry_bid = entry_ask = entry_spread = selected_dte = selected_delta = selected_iv = None
                        ask_bid = mid_mid = None
                    else:
                        symbol = str(selected["option_symbol"])
                        entry_bid = float(selected["bid"])
                        entry_ask = float(selected["ask"])
                        entry_spread = float(selected["spread_fraction"])
                        selected_dte = float(selected["dte"])
                        selected_delta = float(selected["delta"]) if pd.notna(selected["delta"]) else None
                        selected_iv = float(selected["iv"]) if pd.notna(selected["iv"]) else None
                        ask_bid, mid_mid = outcome(entry_bid, entry_ask, mark_map.get(symbol))
                    records.append({
                        "session": session,
                        "run_id": str(candidate["run_id"]),
                        "ticker": ticker,
                        "direction": direction,
                        "hold": hold,
                        "horizon": horizon,
                        "end_session": end,
                        "strategy": strategy,
                        "family_rows": int(len(entry_chain)),
                        "eligible_family_rows": int(entry_chain["common_eligible"].sum()) if not entry_chain.empty else 0,
                        "recorded_symbol": str(candidate["contract"]),
                        "selected_symbol": symbol,
                        "same_as_recorded": symbol == str(candidate["contract"]) if symbol else None,
                        "entry_bid": entry_bid,
                        "entry_ask": entry_ask,
                        "entry_spread": entry_spread,
                        "selected_dte": selected_dte,
                        "selected_delta": selected_delta,
                        "selected_iv": selected_iv,
                        "ask_to_bid": ask_bid,
                        "mid_to_mid": mid_mid,
                        "oracle_best_ask_to_bid": oracle_best,
                    })
    finally:
        con.close()

    output = pd.DataFrame(records)
    output.to_csv(OUTPUT_ROWS, index=False)
    results = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "protocol_sha256": sha256(PROTOCOL),
        "candidate_rows_sha256": sha256(ROWS),
        "rows_file_sha256": sha256(OUTPUT_ROWS),
        "populations": {
            name: aggregate(output, runs)
            for name, runs in population_sets(manifest).items()
        },
        "constraints": [
            "Entry selection uses the exact same-session chain only.",
            "Oracle results are not tradable and measure only family opportunity availability.",
            "Midpoint results are diagnostic, not executable.",
            "Nine sessions cannot promote a production rule.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")

    primary = results["populations"]["exclude_explicit_test_or_dirty"]["horizons"]
    lines = [
        "# AVSHUNTER solution tournament — Round 2 contract-family result",
        "",
        "**State:** Exploratory research only. No production code, authority, configuration, or database was changed.",
        "",
        "## Executable results excluding explicit test/dirty runs",
        "",
        "| Horizon | Rule | Selected / opportunities | Ask→bid mean | Mid→mid mean | Hit rate | +100% oracle recall |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in ("1", "3", "5"):
        for strategy in strategies:
            item = primary.get(horizon, {}).get(strategy)
            if not item:
                continue
            ask_stats = item["ask_to_bid"]
            mid_stats = item["mid_to_mid"]
            pct = lambda value: "n/a" if value is None else f"{100 * value:.2f}%"
            lines.append(
                f"| {horizon} | {strategy} | {item['selected']}/{item['opportunities']} | "
                f"{pct(ask_stats['mean'])} | {pct(mid_stats['mean'])} | {pct(ask_stats['hit_rate'])} | "
                f"{pct(item['recall_ge_100pct'])} |"
            )
    lines += [
        "",
        "## Interpretation rules",
        "",
        "- The oracle is an upper bound using future knowledge and cannot be traded.",
        "- A low recall rate means the rule discarded right-tail contracts even if its mean improved.",
        "- No apparent winner is eligible for production until repeated on a larger certified history and held-out sessions.",
    ]
    OUTPUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": len(output),
        "sessions": int(output["session"].nunique()),
        "output": str(OUTPUT_JSON),
        "report": str(OUTPUT_REPORT),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
