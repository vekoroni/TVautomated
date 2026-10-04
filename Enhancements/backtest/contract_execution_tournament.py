"""Adaptive CEX contract-selection and execution stress tournament."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "Enhancements" / "backtest"
ROUND4 = HERE / "solution_tournament" / "round4_end_to_end_rows.csv"
RUN_MANIFEST = HERE / "solution_tournament" / "round1_input_manifest.json"
ACTIVITY = HERE / "activity_tournament" / "s_act_features.csv"
REGISTER = HERE / "SCENARIO_REGISTER_ADDENDUM_CEX_20260920.md"
OUTPUT = HERE / "contract_execution_tournament"
DETAIL = OUTPUT / "cex_selected_rows.csv.gz"
RESULTS = OUTPUT / "cex_results.json"
REPORT = OUTPUT / "CEX_BACKTEST_STRESS_REPORT_20260920.md"
LEDGER = OUTPUT / "cex_trial_ledger.jsonl"
MANIFEST = OUTPUT / "cex_execution_manifest.json"

SEED = 20260920
TARGET = 0.25
EXPRESSIONS_CURRENT = {"E0_RECORDED", "E1_CORE", "E2_VALUE", "E3_CONVEX", "E5_DYNAMIC"}
EXPRESSIONS_DELAYED = EXPRESSIONS_CURRENT | {"E4_MATURED_CORE"}
OCC = re.compile(r"(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")

NUMERIC = [
    "entry_spread", "log_entry_ask", "iv_over_forecast", "contract_dte", "moneyness_abs",
    "delay_days", "log_total_oi_pcr", "abs_log_total_oi_pcr",
    "log_dw_oi_pcr", "abs_log_dw_oi_pcr", "log_total_volume_pcr", "abs_log_total_volume_pcr",
]
CATEGORICAL = ["expression", "side", "activity_agreement"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()


def pcr(numerator: pd.Series, denominator: pd.Series, floor: float = 50.0) -> pd.Series:
    result = numerator / denominator
    return result.where(denominator >= floor).clip(lower=1e-6, upper=1e6)


def prepare() -> pd.DataFrame:
    truth = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))["run_truth"]
    excluded = {x["run_id"] for x in truth if x.get("run_condition") == "TEST" or x.get("dirty") is True}
    rows = pd.read_csv(ROUND4, low_memory=False)
    rows = rows[
        rows.direction_rule.eq("D0_CURRENT")
        & rows.expression.isin(EXPRESSIONS_DELAYED)
        & rows.instrument.eq("OPTION")
        & ~rows.run_id.isin(excluded)
    ].copy()
    rows = rows.dropna(subset=["symbol", "entry_ask", "entry_bid"])
    rows["session"] = rows.session.astype(str)
    rows["entry_session"] = rows.entry_session.astype(str)
    rows["end_session"] = rows.end_session.astype(str)
    rows["entry_mid"] = (rows.entry_bid + rows.entry_ask) / 2.0
    rows["limit25_entry"] = rows.entry_ask - 0.25 * (rows.entry_ask - rows.entry_bid)
    rows["limit50_entry"] = rows.entry_mid
    for name, price in (("limit25_return", "limit25_entry"), ("limit50_return", "limit50_entry")):
        rows[name] = np.where(
            rows.exit_bid.notna() & (rows[price] > 0), rows.exit_bid / rows[price] - 1.0, np.nan
        )
    parsed = rows.symbol.astype(str).str.extract(OCC)
    rows["contract_expiry"] = pd.to_datetime(parsed.expiry, format="%y%m%d", errors="coerce")
    rows["contract_strike"] = pd.to_numeric(parsed.strike, errors="coerce") / 1000.0
    rows["contract_dte"] = (rows.contract_expiry - pd.to_datetime(rows.entry_session)).dt.days
    rows["delay_days"] = (pd.to_datetime(rows.entry_session) - pd.to_datetime(rows.session)).dt.days.clip(lower=0)

    source = pd.read_csv(HERE / "signal_ticket_backtest_rows.csv", usecols=["session", "run_id", "ticker", "spot"])
    source["candidate_id"] = source.session.astype(str) + "|" + source.run_id.astype(str) + "|" + source.ticker.astype(str)
    source = source[["candidate_id", "spot"]].drop_duplicates("candidate_id")
    rows = rows.merge(source, on="candidate_id", how="left", validate="many_to_one")
    rows["moneyness_abs"] = (rows.contract_strike / rows.spot - 1.0).abs()
    rows["log_entry_ask"] = np.log(rows.entry_ask.clip(lower=0.01))

    activity = pd.read_csv(ACTIVITY, low_memory=False)
    activity = activity.drop_duplicates("candidate_id")
    keep = [
        "candidate_id", "put_oi", "call_oi", "put_dw_oi", "call_dw_oi",
        "put_volume", "call_volume",
    ]
    rows = rows.merge(activity[keep], on="candidate_id", how="left", validate="many_to_one")
    for name, numerator, denominator in (
        ("total_oi_pcr", "put_oi", "call_oi"),
        ("dw_oi_pcr", "put_dw_oi", "call_dw_oi"),
        ("total_volume_pcr", "put_volume", "call_volume"),
    ):
        values = pcr(rows[numerator], rows[denominator])
        rows[f"log_{name}"] = np.log(values)
        rows[f"abs_log_{name}"] = rows[f"log_{name}"].abs()
    oi_state = pd.cut(rows.total_oi_pcr if "total_oi_pcr" in rows else np.exp(rows.log_total_oi_pcr), [-np.inf, .7, 1, np.inf], labels=["CALL_HEAVY", "BALANCED", "PUT_HEAVY"])
    volume_state = pd.cut(rows.total_volume_pcr if "total_volume_pcr" in rows else np.exp(rows.log_total_volume_pcr), [-np.inf, .7, 1, np.inf], labels=["CALL_HEAVY", "BALANCED", "PUT_HEAVY"])
    rows["activity_agreement"] = np.where(oi_state.isna() | volume_state.isna(), "MISSING", np.where(oi_state == volume_state, "AGREE", "MIXED"))
    order = {name: index for index, name in enumerate(sorted(EXPRESSIONS_DELAYED))}
    rows["expression_order"] = rows.expression.map(order)
    rows.sort_values(["candidate_id", "horizon", "symbol", "expression_order"], inplace=True)
    rows.drop_duplicates(["candidate_id", "horizon", "symbol", "entry_session"], keep="first", inplace=True)
    return rows


def model(kind: str) -> Pipeline:
    numeric = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())])
    categorical = Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    if kind == "LOGISTIC":
        estimator = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=SEED)
    else:
        estimator = RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=20,
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED,
        )
    return Pipeline([
        ("features", ColumnTransformer([("num", numeric, NUMERIC), ("cat", categorical, CATEGORICAL)])),
        ("model", estimator),
    ])


def deterministic_choice(group: pd.DataFrame, scenario: str) -> pd.Series | None:
    current = group[group.expression.isin(EXPRESSIONS_CURRENT)]
    if scenario == "CEX-0":
        pool = current[current.expression == "E0_RECORDED"]
        return pool.iloc[0] if not pool.empty else None
    if scenario.startswith("CEX-2-"):
        premium = float(scenario.rsplit("-", 1)[1])
        current = current[current.entry_ask >= premium]
    current = current[current.entry_spread.notna()]
    if current.empty:
        return None
    if scenario == "CEX-3":
        utility = (
            -current.entry_spread.fillna(9.0)
            -0.20 * np.log(current.iv_over_forecast.clip(lower=1e-4)).abs().fillna(2.0)
            -0.10 * current.moneyness_abs.fillna(1.0)
            -0.002 * (current.contract_dte - 30).abs().fillna(180)
        )
        return current.loc[utility.idxmax()]
    return current.loc[current.entry_spread.idxmin()]


def trained_choices(frame: pd.DataFrame, kind: str, *, delayed: bool, margin: float | None = None) -> pd.DataFrame:
    outputs = []
    expressions = EXPRESSIONS_DELAYED if delayed else EXPRESSIONS_CURRENT
    for test_session in sorted(frame.session.unique()):
        train = frame[
            (frame.end_session < test_session)
            & frame.base_return.notna()
            & frame.expression.isin(expressions)
        ].copy()
        test = frame[(frame.session == test_session) & frame.expression.isin(expressions)].copy()
        if train.session.nunique() < 2 or len(train) < 100 or train.empty or test.empty:
            continue
        train["target"] = (train.base_return >= TARGET).astype(int)
        if train.target.nunique() < 2:
            continue
        fitted = model(kind)
        fitted.fit(train[NUMERIC + CATEGORICAL], train.target)
        test["model_score"] = fitted.predict_proba(test[NUMERIC + CATEGORICAL])[:, 1]
        for _, group in test.groupby(["candidate_id", "horizon"], sort=False):
            best = group.loc[group.model_score.idxmax()]
            if margin is not None:
                recorded = group[group.expression == "E0_RECORDED"]
                if not recorded.empty and float(best.model_score) - float(recorded.iloc[0].model_score) < margin:
                    best = recorded.iloc[0]
            outputs.append(best)
    return pd.DataFrame(outputs)


def eligible_sessions(frame: pd.DataFrame, horizon: int) -> set[str]:
    sessions = []
    h = frame[frame.horizon == horizon]
    for session in sorted(h.session.unique()):
        train = h[(h.end_session < session) & h.base_return.notna()]
        if train.session.nunique() >= 2 and len(train) >= 100:
            sessions.append(session)
    return set(sessions)


def summary(selected: pd.DataFrame, baseline: pd.DataFrame, opportunities: int) -> dict:
    if selected.empty or "base_return" not in selected.columns:
        return {
            "status": "REJECTED_OR_INCONCLUSIVE", "opportunities": int(opportunities),
            "selected_contracts": 0, "monitor_no_contract": int(opportunities),
            "closed": 0, "sessions": 0, "coverage": 0.0,
            "ask_bid_mean": None, "ask_bid_median": None, "hit_25": None,
            "limit25_conditional_mean": None, "mid_entry_exit_bid_conditional_mean": None,
            "spread25_mean": None, "spread50_mean": None,
            "session_delta_mean": None, "paired_t": None, "paired_p": None,
            "positive_session_deltas": 0,
        }
    closed = selected.dropna(subset=["base_return"])
    base_closed = baseline.dropna(subset=["base_return"])
    session_delta = closed.groupby("session").base_return.mean() - base_closed.groupby("session").base_return.mean()
    session_delta = session_delta.dropna()
    t_stat, p_value = stats.ttest_1samp(session_delta, 0.0) if len(session_delta) >= 2 else (np.nan, np.nan)
    stressed = float(closed.stress_spread_50.mean()) if len(closed) else None
    passes = bool(
        len(closed) >= 40 and len(session_delta) >= 2 and closed.base_return.mean() > 0
        and stressed is not None and stressed > 0 and math.isfinite(float(t_stat))
        and abs(float(t_stat)) >= 2 and (session_delta > 0).sum() >= 2
    )
    return {
        "status": "REPLICATION_CANDIDATE" if passes else "REJECTED_OR_INCONCLUSIVE",
        "opportunities": int(opportunities), "selected_contracts": int(len(selected)),
        "monitor_no_contract": int(max(0, opportunities - selected.candidate_id.nunique())),
        "closed": int(len(closed)), "sessions": int(closed.session.nunique()),
        "coverage": float(selected.candidate_id.nunique() / opportunities) if opportunities else 0.0,
        "ask_bid_mean": float(closed.base_return.mean()) if len(closed) else None,
        "ask_bid_median": float(closed.base_return.median()) if len(closed) else None,
        "hit_25": float((closed.base_return >= TARGET).mean()) if len(closed) else None,
        "limit25_conditional_mean": float(closed.limit25_return.mean()) if len(closed) else None,
        "mid_entry_exit_bid_conditional_mean": float(closed.limit50_return.mean()) if len(closed) else None,
        "spread25_mean": float(closed.stress_spread_25.mean()) if len(closed) else None,
        "spread50_mean": stressed,
        "session_delta_mean": float(session_delta.mean()) if len(session_delta) else None,
        "paired_t": float(t_stat) if math.isfinite(float(t_stat)) else None,
        "paired_p": float(p_value) if math.isfinite(float(p_value)) else None,
        "positive_session_deltas": int((session_delta > 0).sum()),
    }


def append_ledger(record: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = prepare()
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "state": "EXPLORATORY_NO_AUTHORITY",
        "register_sha256": sha256(REGISTER), "round4_sha256": sha256(ROUND4),
        "activity_sha256": sha256(ACTIVITY), "rows": int(len(frame)),
        "sessions": sorted(frame.session.unique().tolist()),
        "warning": "Adaptive batch on previously inspected sessions; later-session replication required.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    results = {"manifest_sha256": sha256(MANIFEST), "state": "EXPLORATORY_NO_AUTHORITY", "trials": {}}
    selected_outputs = []
    deterministic = ["CEX-0", "CEX-1", "CEX-2-0.25", "CEX-2-0.5", "CEX-2-1.0", "CEX-3"]
    for horizon in sorted(frame.horizon.unique()):
        sessions = eligible_sessions(frame, int(horizon))
        all_h = frame[frame.horizon == horizon].copy()
        h = all_h[all_h.session.isin(sessions)].copy()
        opportunities = h.candidate_id.nunique()
        baseline_rows = []
        for _, group in h.groupby(["candidate_id", "horizon"], sort=False):
            chosen = deterministic_choice(group, "CEX-0")
            if chosen is not None:
                baseline_rows.append(chosen)
        baseline = pd.DataFrame(baseline_rows)
        for scenario in deterministic:
            chosen_rows = []
            for _, group in h.groupby(["candidate_id", "horizon"], sort=False):
                chosen = deterministic_choice(group, scenario)
                if chosen is not None:
                    chosen_rows.append(chosen)
            chosen = pd.DataFrame(chosen_rows)
            trial = f"{scenario}|H{int(horizon)}"
            results["trials"][trial] = summary(chosen, baseline, opportunities)
            if not chosen.empty:
                chosen["trial_id"] = trial
                selected_outputs.append(chosen)
        for kind, scenario, delayed, margin in (
            ("LOGISTIC", "CEX-4", False, None),
            ("FOREST", "CEX-5", False, None),
            ("LOGISTIC", "CEX-6-M05", False, 0.05),
            ("LOGISTIC", "CEX-6-M10", False, 0.10),
            ("LOGISTIC", "CEX-7", True, None),
        ):
            chosen = trained_choices(all_h, kind, delayed=delayed, margin=margin)
            chosen = chosen[chosen.session.isin(sessions)] if not chosen.empty else chosen
            trial = f"{scenario}|H{int(horizon)}"
            results["trials"][trial] = summary(chosen, baseline, opportunities)
            if not chosen.empty:
                chosen["trial_id"] = trial
                selected_outputs.append(chosen)
        for trial, item in [(k, v) for k, v in results["trials"].items() if k.endswith(f"|H{int(horizon)}")]:
            append_ledger({
                "trial_id": trial, "executed_at_utc": datetime.now(timezone.utc).isoformat(),
                "manifest_sha256": results["manifest_sha256"], "result": item["status"],
                "production_authority": "NONE",
            })
    if selected_outputs:
        keep = [
            "trial_id", "candidate_id", "session", "ticker", "horizon", "expression", "symbol",
            "entry_session", "entry_bid", "entry_ask", "entry_spread", "exit_bid", "base_return",
            "limit25_return", "limit50_return", "stress_spread_25", "stress_spread_50",
        ]
        pd.concat(selected_outputs, ignore_index=True)[keep].to_csv(DETAIL, index=False, compression="gzip")
    RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")
    ranked = sorted(
        results["trials"].items(),
        key=lambda item: item[1].get("ask_bid_mean") if item[1].get("ask_bid_mean") is not None else -999,
        reverse=True,
    )
    report = [
        "# CEX Contract and Execution Backtest/Stress Report — 2026-09-20", "",
        "**State:** `EXPLORATORY_NO_AUTHORITY` — adaptive evidence, not production acceptance", "",
        "| Trial | Status | Coverage | Ask→bid | Limit25* | Mid entry* | Spread+50 | Hit ≥25% |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for trial, item in ranked:
        pct = lambda value: "—" if value is None else f"{value:.1%}"
        report.append(
            f"| {trial} | {item['status']} | {pct(item['coverage'])} | {pct(item['ask_bid_mean'])} | "
            f"{pct(item['limit25_conditional_mean'])} | {pct(item['mid_entry_exit_bid_conditional_mean'])} | "
            f"{pct(item['spread50_mean'])} | {pct(item['hit_25'])} |"
        )
    report += [
        "", "*Conditional on a hypothetical limit fill; not evidence that the order would have filled.*", "",
        "## Governance conclusion", "",
        "A result is only a replication candidate when executable ask-to-bid and 50%-wider-spread means are positive with session-level consistency. Tickers without a qualifying contract remain monitored; they are not invalidated.",
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "trials": len(results["trials"]), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
