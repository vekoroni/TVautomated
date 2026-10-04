"""Round 4 integrated monetisation backtest and stress tournament.

All market stores are opened read-only.  Results are research evidence only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

from round2_contract_family import (  # noqa: E402
    Mark,
    choose,
    load_chain,
    normalize_chain,
    outcome,
    sessions_after,
)


CANDIDATES = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
ROUND1_PANEL = HERE / "round1_panel.csv"
RUN_MANIFEST = HERE / "round1_input_manifest.json"
PROTOCOL = HERE / "ROUND4_END_TO_END_STRESS_PROTOCOL_20260919.md"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
DETAIL = HERE / "round4_end_to_end_rows.csv"
RESULTS = HERE / "round4_end_to_end_stress_results.json"
REPORT = HERE / "ROUND4_END_TO_END_STRESS_REPORT_20260919.md"
HORIZONS = (1, 3, 5)
SEED = 19092026


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_fraction(value: str) -> float:
    raw = hashlib.sha256(value.encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, "big") / float(2**64 - 1)


def session_bootstrap(frame: pd.DataFrame, column: str, samples: int = 3000) -> dict:
    clean = frame[["session", column]].dropna()
    sessions = clean.session.unique()
    result = {
        "n": int(len(clean)), "sessions": int(len(sessions)), "mean": None,
        "median": None, "hit_rate": None, "ci90": [None, None],
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
    })
    if len(sessions) < 2:
        return result
    # A session bootstrap resamples whole sessions.  The earlier implementation
    # repeatedly concatenated every row for every draw; that is mathematically
    # correct but needlessly expensive for the integrated stress matrix.  Sums
    # and counts are sufficient statistics for the same weighted mean.
    grouped = clean.groupby("session")[column].agg(["sum", "count"]).reindex(sessions)
    sums = grouped["sum"].to_numpy(float)
    counts = grouped["count"].to_numpy(float)
    rng = np.random.default_rng(SEED)
    draw = rng.integers(0, len(sessions), size=(samples, len(sessions)))
    estimates = sums[draw].sum(axis=1) / counts[draw].sum(axis=1)
    result["ci90"] = [round(float(v), 6) for v in np.quantile(estimates, [0.05, 0.95])]
    return result


def select_convex(frame: pd.DataFrame) -> pd.Series | None:
    if frame.empty or "common_eligible" not in frame:
        return None
    eligible = frame[
        frame.common_eligible
        & frame.abs_delta.between(0.20, 0.35)
        & (frame.moneyness_abs <= 0.10)
        & (frame.spread_fraction <= 0.15)
        & frame.iv.gt(0)
        & ((frame.iv / frame.forecast_vol) <= 1.0)
    ].copy()
    if eligible.empty:
        return None
    eligible["activity_rank"] = eligible.activity.rank(pct=True)
    eligible["cheap_rank"] = (eligible.forecast_vol / eligible.iv).rank(pct=True)
    eligible["convex_score"] = 0.7 * eligible.cheap_rank + 0.3 * eligible.activity_rank
    return eligible.sort_values(["convex_score", "spread_fraction"], ascending=[False, True]).iloc[0]


def selection_payload(row: pd.Series | None, entry_session: str) -> dict:
    if row is None:
        return {
            "symbol": None, "entry_session": entry_session, "entry_bid": None,
            "entry_ask": None, "entry_iv": None, "entry_spread": None,
        }
    return {
        "symbol": str(row.option_symbol),
        "entry_session": entry_session,
        "entry_bid": float(row.bid),
        "entry_ask": float(row.ask),
        "entry_iv": float(row.iv) if pd.notna(row.iv) else None,
        "entry_spread": float(row.spread_fraction),
    }


def stressed_option_return(row: pd.Series, half_spread_factor: float) -> float | None:
    values = [row.entry_bid, row.entry_ask, row.exit_bid, row.exit_ask]
    if any(pd.isna(value) for value in values):
        return None
    entry_mid = (row.entry_bid + row.entry_ask) / 2.0
    exit_mid = (row.exit_bid + row.exit_ask) / 2.0
    entry_half = (row.entry_ask - row.entry_bid) / 2.0
    exit_half = (row.exit_ask - row.exit_bid) / 2.0
    stressed_entry = entry_mid + half_spread_factor * entry_half
    stressed_exit = max(0.0, exit_mid - half_spread_factor * exit_half)
    return stressed_exit / stressed_entry - 1.0 if stressed_entry > 0 else None


def add_stress_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["stress_spread_25"] = result["base_return"]
    result["stress_spread_50"] = result["base_return"]
    option_mask = result.instrument == "OPTION"
    result.loc[option_mask, "stress_spread_25"] = result[option_mask].apply(
        lambda row: stressed_option_return(row, 1.25), axis=1
    )
    result.loc[option_mask, "stress_spread_50"] = result[option_mask].apply(
        lambda row: stressed_option_return(row, 1.50), axis=1
    )
    result["dropout_draw"] = result.apply(
        lambda row: stable_fraction(f"{row.candidate_id}|{row.scenario}|{row.horizon}"), axis=1
    )
    return result


def build_dynamic_rows(raw: pd.DataFrame) -> pd.DataFrame:
    """Build the entry-time instrument decision without future quote leakage."""
    dynamic_rows = []
    core = raw[raw.expression == "E1_CORE"].copy()
    core["cheap_percentile"] = core.groupby(
        ["session", "horizon", "direction_rule"]
    )["iv_over_forecast"].rank(pct=True)
    for row in core.itertuples(index=False):
        payload = row._asdict()
        payload["expression"] = "E5_DYNAMIC"
        payload["scenario"] = f"{row.direction_rule}|E5_DYNAMIC"
        # Selection can use only information known at entry.  In particular,
        # whether a later exit quote exists must not influence the instrument.
        if (
            pd.notna(row.cheap_percentile)
            and row.cheap_percentile <= 0.40
            and row.instrument == "OPTION"
        ):
            pass
        elif row.side == "CALL":
            payload.update({
                "instrument": "SHARES", "symbol": None, "entry_bid": None, "entry_ask": None,
                "entry_iv": None, "entry_spread": None, "exit_bid": None, "exit_ask": None,
                "base_return": row.underlying_return, "mid_to_mid": row.underlying_return,
            })
        else:
            payload.update({
                "instrument": "NO_TRADE", "symbol": None, "entry_bid": None, "entry_ask": None,
                "entry_iv": None, "entry_spread": None, "exit_bid": None, "exit_ask": None,
                "base_return": None, "mid_to_mid": None,
            })
        dynamic_rows.append(payload)
    return pd.DataFrame(dynamic_rows)


def aggregate_scenario(frame: pd.DataFrame) -> dict:
    executed = frame.dropna(subset=["base_return"])
    result = {
        "opportunities": int(len(frame)),
        "executed": int(len(executed)),
        "participation": round(float(len(executed) / len(frame)), 4) if len(frame) else None,
        "instrument_mix": frame.instrument.value_counts(dropna=False).to_dict(),
        "base": session_bootstrap(executed, "base_return"),
        "spread_widen_25": session_bootstrap(executed, "stress_spread_25"),
        "spread_widen_50": session_bootstrap(executed, "stress_spread_50"),
    }
    for threshold, label in ((0.10, "quote_dropout_10"), (0.25, "quote_dropout_25")):
        stressed = executed[(executed.instrument != "OPTION") | (executed.dropout_draw >= threshold)]
        result[label] = {
            "remaining": int(len(stressed)),
            "participation": round(float(len(stressed) / len(frame)), 4) if len(frame) else None,
            "return": session_bootstrap(stressed, "base_return"),
        }
    if len(executed):
        cutoff = executed.base_return.quantile(0.99)
        result["remove_top_1pct"] = session_bootstrap(executed[executed.base_return < cutoff], "base_return")
    else:
        result["remove_top_1pct"] = session_bootstrap(executed, "base_return")
    for column, truth, label in (
        ("spy_bull", True, "spy_bull"), ("spy_bull", False, "spy_bear"),
        ("spy_vol_high", True, "spy_vol_high"), ("spy_vol_high", False, "spy_vol_low"),
    ):
        result[label] = session_bootstrap(executed[executed[column] == truth], "base_return")
    ci = result["base"]["ci90"]
    result["reliability_gate"] = {
        "base_positive": result["base"]["mean"] is not None and result["base"]["mean"] > 0,
        "ci_lower_nonnegative": ci[0] is not None and ci[0] >= 0,
        "spread50_positive": result["spread_widen_50"]["mean"] is not None and result["spread_widen_50"]["mean"] > 0,
        "top1_removed_positive": result["remove_top_1pct"]["mean"] is not None and result["remove_top_1pct"]["mean"] > 0,
        "both_regimes_positive": all(
            result[name]["mean"] is not None and result[name]["mean"] > 0 for name in ("spy_bull", "spy_bear")
        ),
    }
    result["reliability_gate"]["passed"] = all(result["reliability_gate"].values())
    return result


def run_sets(manifest: dict) -> dict[str, set[str] | None]:
    truth = {item["run_id"]: item for item in manifest["run_truth"]}
    bad = {run_id for run_id, item in truth.items() if item.get("run_condition") == "TEST" or item.get("dirty") is True}
    certified = {
        run_id for run_id, item in truth.items()
        if item.get("run_condition") == "NORMAL_COMPLETED_SESSION"
        and item.get("dirty") is False
        and item.get("baseline_eligible") is True
    }
    return {
        "all_h_pre_fix": None,
        "exclude_explicit_test_or_dirty": set(truth) - bad,
        "certified_normal_completed_only": certified,
    }


def main() -> int:
    candidates = pd.read_csv(CANDIDATES, low_memory=False)
    candidates["session"] = candidates.session.astype(str)
    panel = pd.read_csv(ROUND1_PANEL, low_memory=False)
    panel = panel[[
        "session", "run_id", "ticker", "horizon", "underlying_return", "ret5_entry", "ret20_entry"
    ]].drop_duplicates(["session", "run_id", "ticker", "horizon"])
    outcome_lookup = {
        (str(row.session), str(row.run_id), str(row.ticker), int(row.horizon)): float(row.underlying_return)
        for row in panel.itertuples(index=False)
    }
    manifest = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))

    price_con = sqlite3.connect(f"file:{PRICE_DB.as_posix()}?mode=ro", uri=True)
    chain_con = sqlite3.connect(f"file:{CHAIN_DB.as_posix()}?mode=ro", uri=True)
    price_rows = pd.read_sql_query(
        "SELECT ticker,trading_date,close FROM ohlcv_daily WHERE trading_date >= '2026-07-01'",
        price_con,
    )
    price_con.close()
    close_map = {(str(r.ticker), str(r.trading_date)): float(r.close) for r in price_rows.itertuples()}
    spy = price_rows[price_rows.ticker == "SPY"].sort_values("trading_date").copy()
    spy["spy20"] = spy.close / spy.close.shift(20) - 1.0
    spy["spy_rv20"] = np.log(spy.close / spy.close.shift(1)).rolling(20).std() * np.sqrt(252)
    spy_context = spy.set_index("trading_date")[["spy20", "spy_rv20"]].to_dict("index")
    vol_median = float(spy.spy_rv20.dropna().median())

    feature_one = panel[panel.horizon == 1][["session", "run_id", "ticker", "ret5_entry", "ret20_entry"]]
    candidates = candidates.merge(feature_one, on=["session", "run_id", "ticker"], how="left")
    raw_records: list[dict] = []
    try:
        for candidate in candidates.itertuples(index=False):
            candidate_id = f"{candidate.session}|{candidate.run_id}|{candidate.ticker}"
            current_side = "call" if str(candidate.direction).upper() == "CALL" else "put"
            meanrev_side = "put" if float(candidate.ret5_entry) >= 0 else "call"
            momentum_side = "call" if float(candidate.ret20_entry) >= 0 else "put"
            direction_sides = {
                "D0_CURRENT": current_side,
                "D1_MEAN_REVERSION_5": meanrev_side,
                "D2_MOMENTUM_20": momentum_side,
            }
            entry_all = load_chain(chain_con, str(candidate.ticker), str(candidate.session), None)
            side_frames = {}
            selections: dict[tuple[str, str], dict] = {}
            for side in ("call", "put"):
                side_raw = entry_all[entry_all.side.astype(str).str.lower() == side].copy()
                normalized = normalize_chain(
                    side_raw, float(candidate.spot), float(candidate.forecast_vol), int(candidate.hold)
                )
                if not normalized.empty:
                    normalized["forecast_vol"] = float(candidate.forecast_vol)
                side_frames[side] = normalized
                selections[(side, "E1_CORE")] = selection_payload(
                    choose(normalized, "F3_DELTA_CORE", int(candidate.hold)), str(candidate.session)
                )
                selections[(side, "E2_VALUE")] = selection_payload(
                    choose(normalized, "F4_VALUE_COMPOSITE", int(candidate.hold)), str(candidate.session)
                )
                selections[(side, "E3_CONVEX")] = selection_payload(select_convex(normalized), str(candidate.session))
            recorded_match = entry_all[entry_all.option_symbol == str(candidate.contract)]
            recorded = None
            if not recorded_match.empty:
                normalized_recorded = normalize_chain(
                    recorded_match.copy(), float(candidate.spot), float(candidate.forecast_vol), int(candidate.hold)
                )
                if not normalized_recorded.empty:
                    normalized_recorded["forecast_vol"] = float(candidate.forecast_vol)
                    recorded = normalized_recorded.iloc[0]
            selections[(current_side, "E0_RECORDED")] = selection_payload(recorded, str(candidate.session))

            matured = selections[(current_side, "E1_CORE")]
            if matured["symbol"] is None:
                for delay in (1, 2):
                    delayed_session = sessions_after(str(candidate.session), delay)
                    if delayed_session is None:
                        continue
                    delayed_spot = close_map.get((str(candidate.ticker), delayed_session))
                    if not delayed_spot:
                        continue
                    delayed_all = load_chain(chain_con, str(candidate.ticker), delayed_session, current_side)
                    delayed = normalize_chain(
                        delayed_all, delayed_spot, float(candidate.forecast_vol), int(candidate.hold)
                    )
                    if not delayed.empty:
                        delayed["forecast_vol"] = float(candidate.forecast_vol)
                    choice = choose(delayed, "F3_DELTA_CORE", int(candidate.hold))
                    if choice is not None:
                        matured = selection_payload(choice, delayed_session)
                        matured["maturation_delay"] = delay
                        break
            selections[(current_side, "E4_MATURED_CORE")] = matured

            for horizon in HORIZONS:
                end_session = sessions_after(str(candidate.session), horizon)
                if end_session is None:
                    continue
                underlying_return = outcome_lookup.get(
                    (str(candidate.session), str(candidate.run_id), str(candidate.ticker), int(horizon))
                )
                if underlying_return is None:
                    continue
                end_all = load_chain(chain_con, str(candidate.ticker), end_session, None)
                marks = {
                    str(r.option_symbol): Mark(
                        float(r.bid) if pd.notna(r.bid) else None,
                        float(r.ask) if pd.notna(r.ask) else None,
                    )
                    for r in end_all.itertuples()
                }
                spy_state = spy_context.get(str(candidate.session), {})
                for direction_rule, side in direction_sides.items():
                    expressions = ("E1_CORE", "E2_VALUE", "E3_CONVEX")
                    if direction_rule == "D0_CURRENT":
                        expressions = ("E0_RECORDED",) + expressions + ("E4_MATURED_CORE",)
                    for expression in expressions:
                        selected = selections.get((side, expression), selection_payload(None, str(candidate.session)))
                        if selected["entry_session"] >= end_session:
                            ask_bid = mid_mid = None
                            mark = None
                        else:
                            mark = marks.get(str(selected["symbol"])) if selected["symbol"] else None
                            ask_bid, mid_mid = outcome(
                                selected["entry_bid"], selected["entry_ask"], mark
                            ) if selected["symbol"] else (None, None)
                        raw_records.append({
                            "candidate_id": candidate_id,
                            "session": str(candidate.session),
                            "run_id": str(candidate.run_id),
                            "ticker": str(candidate.ticker),
                            "horizon": horizon,
                            "end_session": end_session,
                            "direction_rule": direction_rule,
                            "side": side.upper(),
                            "expression": expression,
                            "scenario": f"{direction_rule}|{expression}",
                            "instrument": "OPTION" if selected["symbol"] else "NO_TRADE",
                            "symbol": selected["symbol"],
                            "entry_session": selected["entry_session"],
                            "entry_bid": selected["entry_bid"],
                            "entry_ask": selected["entry_ask"],
                            "entry_iv": selected["entry_iv"],
                            "forecast_vol": float(candidate.forecast_vol),
                            "iv_over_forecast": (
                                selected["entry_iv"] / float(candidate.forecast_vol)
                                if selected["entry_iv"] is not None and float(candidate.forecast_vol) > 0 else None
                            ),
                            "entry_spread": selected["entry_spread"],
                            "exit_bid": mark.bid if mark else None,
                            "exit_ask": mark.ask if mark else None,
                            "base_return": ask_bid,
                            "mid_to_mid": mid_mid,
                            "underlying_return": underlying_return,
                            "spy_bull": bool(spy_state.get("spy20", 0) >= 0),
                            "spy_vol_high": bool(spy_state.get("spy_rv20", 0) >= vol_median),
                        })
    finally:
        chain_con.close()

    raw = pd.DataFrame(raw_records)
    combined = pd.concat([raw, build_dynamic_rows(raw)], ignore_index=True)
    combined = add_stress_columns(combined)
    combined.to_csv(DETAIL, index=False)

    populations = {}
    for population, allowed in run_sets(manifest).items():
        subset = combined if allowed is None else combined[combined.run_id.isin(allowed)]
        scenario_results = {}
        for (horizon, scenario), group in subset.groupby(["horizon", "scenario"]):
            scenario_results.setdefault(str(int(horizon)), {})[scenario] = aggregate_scenario(group)
        populations[population] = {
            "rows": int(len(subset)), "sessions": int(subset.session.nunique()), "scenarios": scenario_results,
        }

    primary = combined[combined.run_id.isin(run_sets(manifest)["exclude_explicit_test_or_dirty"])]
    tail_recall = {}
    for (horizon, direction), group in primary.groupby(["horizon", "direction_rule"]):
        pivot = group[group.expression.isin(["E1_CORE", "E3_CONVEX"])].pivot_table(
            index="candidate_id", columns="expression", values="base_return", aggfunc="first"
        )
        for threshold, label in ((1.0, "100"), (2.0, "200")):
            available = (pivot.max(axis=1, skipna=True) >= threshold)
            core_capture = (pivot.get("E1_CORE", pd.Series(index=pivot.index, dtype=float)) >= threshold)
            convex_capture = (pivot.get("E3_CONVEX", pd.Series(index=pivot.index, dtype=float)) >= threshold)
            tail_recall.setdefault(str(int(horizon)), {}).setdefault(direction, {})[f"ge_{label}pct"] = {
                "available_in_two_lanes": int(available.sum()),
                "core_recall": round(float(core_capture[available].mean()), 4) if available.any() else None,
                "convex_recall": round(float(convex_capture[available].mean()), 4) if available.any() else None,
                "union_recall": round(float((core_capture | convex_capture)[available].mean()), 4) if available.any() else None,
            }

    result = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "protocol_sha256": sha256(PROTOCOL),
        "candidate_sha256": sha256(CANDIDATES),
        "detail_sha256": sha256(DETAIL),
        "populations": populations,
        "two_lane_tail_recall": tail_recall,
        "constraints": [
            "No capital allocation is modelled.",
            "No-trade and missing-quote rows are never converted to zero returns.",
            "Midpoint marks are diagnostic only.",
            "No scenario changes production authority.",
        ],
    }
    RESULTS.write_text(json.dumps(result, indent=2), encoding="utf-8")

    focus = populations["exclude_explicit_test_or_dirty"]["scenarios"]
    lines = [
        "# AVSHUNTER Round 4 — integrated monetisation and stress result",
        "",
        "**State:** Exploratory research only. Production was not changed.",
        "",
        "## Primary population: explicit test/dirty run excluded",
        "",
        "| Horizon | Scenario | Participation | Base mean | Spread +50% | Top 1% removed | Bull | Bear | Reliable |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    selected_scenarios = [
        "D0_CURRENT|E0_RECORDED", "D0_CURRENT|E1_CORE", "D0_CURRENT|E2_VALUE",
        "D0_CURRENT|E4_MATURED_CORE", "D0_CURRENT|E5_DYNAMIC",
        "D1_MEAN_REVERSION_5|E1_CORE", "D1_MEAN_REVERSION_5|E5_DYNAMIC",
        "D2_MOMENTUM_20|E1_CORE", "D2_MOMENTUM_20|E5_DYNAMIC",
    ]
    pct = lambda value: "n/a" if value is None else f"{100 * value:.2f}%"
    for horizon in map(str, HORIZONS):
        for scenario in selected_scenarios:
            item = focus.get(horizon, {}).get(scenario)
            if not item:
                continue
            lines.append(
                f"| {horizon} | {scenario} | {pct(item['participation'])} | {pct(item['base']['mean'])} | "
                f"{pct(item['spread_widen_50']['mean'])} | {pct(item['remove_top_1pct']['mean'])} | "
                f"{pct(item['spy_bull']['mean'])} | {pct(item['spy_bear']['mean'])} | "
                f"{'YES' if item['reliability_gate']['passed'] else 'NO'} |"
            )
    lines += [
        "",
        "## Acceptance rule",
        "",
        "Only a scenario marked reliable may advance toward implementation, and even then it requires replication on additional certified sessions. Failure attribution is recorded in the JSON result rather than hidden by a single aggregate score.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(combined), "output": str(RESULTS), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
