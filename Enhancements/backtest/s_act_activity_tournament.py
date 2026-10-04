"""Governed S-ACT option-activity backtest and stress tournament.

This research harness evaluates whether observable option-chain activity adds
out-of-sample information to recorded AVSHUNTER contracts.  It never treats a
put/call ratio as signed order flow and never changes production authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "Enhancements" / "backtest"
ROUND4 = HERE / "solution_tournament" / "round4_end_to_end_rows.csv"
RUN_MANIFEST = HERE / "solution_tournament" / "round1_input_manifest.json"
REGISTER = HERE / "SCENARIO_REGISTER_20260919.md"
ADDENDUM = HERE / "SCENARIO_REGISTER_ADDENDUM_S_ACT_20260920.md"
PHANTOM = REPO / "data" / "phantom" / "phantom_history.db"
OUTPUT = HERE / "activity_tournament"
FEATURES_PATH = OUTPUT / "s_act_features.csv"
SCORES_PATH = OUTPUT / "s_act_model_scores.csv.gz"
RESULTS_PATH = OUTPUT / "s_act_results.json"
REPORT_PATH = OUTPUT / "S_ACT_BACKTEST_STRESS_REPORT_20260920.md"
MANIFEST_PATH = OUTPUT / "s_act_execution_manifest.json"
LEDGER_PATH = OUTPUT / "s_act_trial_ledger.jsonl"

RESEARCH_STATE = "EXPLORATORY_NO_AUTHORITY"
BASE_SCENARIO = "D0_CURRENT|E0_RECORDED"
TARGET_RETURN = 0.25
TOP_FRACTION = 0.20
DENOMINATOR_FLOORS = (1.0, 10.0, 50.0)
RANDOM_SEED = 20260920
MIN_CLOSED = 40
MIN_SESSIONS = 2

SCENARIOS: dict[str, tuple[str, ...]] = {
    "S-ACT-1": ("log_total_oi_pcr", "abs_log_total_oi_pcr"),
    "S-ACT-2": ("log_dw_oi_pcr", "abs_log_dw_oi_pcr"),
    "S-ACT-3": ("log_total_volume_pcr", "abs_log_total_volume_pcr"),
    "S-ACT-4": (
        "log_total_oi_pcr", "abs_log_total_oi_pcr",
        "log_dw_oi_pcr", "abs_log_dw_oi_pcr",
        "log_total_volume_pcr", "abs_log_total_volume_pcr",
        "activity_agreement",
    ),
    "S-ACT-5": (
        "log_expiry_oi_pcr", "abs_log_expiry_oi_pcr",
        "log_expiry_volume_pcr", "abs_log_expiry_volume_pcr",
    ),
    "S-ACT-6": (
        "log_near_oi_pcr", "abs_log_near_oi_pcr",
        "log_near_volume_pcr", "abs_log_near_volume_pcr",
        "log_delta_oi_pcr", "abs_log_delta_oi_pcr",
        "log_delta_volume_pcr", "abs_log_delta_volume_pcr",
    ),
    "S-ACT-7": (
        "log_total_oi_pcr", "abs_log_total_oi_pcr",
        "log_total_volume_pcr", "abs_log_total_volume_pcr",
        "premium_residual", "iv_change", "oi_change_selected",
    ),
    "S-ACT-9": (
        "log_total_oi_pcr", "abs_log_total_oi_pcr",
        "log_dw_oi_pcr", "abs_log_dw_oi_pcr",
        "log_total_volume_pcr", "abs_log_total_volume_pcr",
        "log_expiry_oi_pcr", "abs_log_expiry_oi_pcr",
        "log_expiry_volume_pcr", "abs_log_expiry_volume_pcr",
        "log_near_oi_pcr", "abs_log_near_oi_pcr",
        "log_near_volume_pcr", "abs_log_near_volume_pcr",
        "log_delta_oi_pcr", "abs_log_delta_oi_pcr",
        "log_delta_volume_pcr", "abs_log_delta_volume_pcr",
        "premium_residual", "iv_change", "oi_change_selected",
        "activity_agreement",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_fraction(value: str) -> float:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16) / float(16**12)


def chunks(values: Iterable[str], size: int = 350) -> Iterable[list[str]]:
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def pcr_bucket(value: float | None) -> str:
    if value is None or not math.isfinite(value) or value < 0:
        return "UNKNOWN"
    if value < 0.7:
        return "CALL_HEAVY"
    if value > 1.0:
        return "PUT_HEAVY"
    return "BALANCED"


def ratio(numerator: float, denominator: float, floor: float) -> float | None:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator < floor:
        return None
    return numerator / denominator


def load_population() -> tuple[pd.DataFrame, dict]:
    manifest = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))
    excluded = {
        item["run_id"] for item in manifest["run_truth"]
        if item.get("run_condition") == "TEST" or item.get("dirty") is True
    }
    use = [
        "candidate_id", "session", "run_id", "ticker", "horizon", "end_session",
        "side", "symbol", "entry_session", "entry_bid", "entry_ask", "entry_iv",
        "entry_spread", "base_return", "mid_to_mid", "underlying_return",
        "stress_spread_25", "stress_spread_50", "dropout_draw", "spy_bull", "spy_vol_high",
    ]
    frame = pd.read_csv(ROUND4, usecols=use + ["scenario"], low_memory=False)
    frame = frame[(frame.scenario == BASE_SCENARIO) & ~frame.run_id.isin(excluded)].copy()
    frame.drop(columns=["scenario"], inplace=True)
    frame["session"] = frame.session.astype(str)
    frame["entry_session"] = frame.entry_session.astype(str)
    return frame, manifest


CHAIN_COLUMNS = [
    "ticker", "quote_date", "option_symbol", "expiration_ts", "side", "strike", "dte",
    "bid", "mid", "ask", "open_interest", "volume", "underlying_price", "iv", "delta",
]


def load_chains(con: sqlite3.Connection, session: str, tickers: list[str]) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for batch in chunks(sorted(set(tickers))):
        marks = ",".join("?" for _ in batch)
        sql = f"SELECT {','.join(CHAIN_COLUMNS)} FROM chain_snapshots WHERE quote_date=? AND ticker IN ({marks})"
        pieces.append(pd.read_sql_query(sql, con, params=[session, *batch]))
    if not pieces:
        return pd.DataFrame(columns=CHAIN_COLUMNS)
    result = pd.concat(pieces, ignore_index=True)
    for column in ("strike", "bid", "mid", "ask", "open_interest", "volume", "underlying_price", "iv", "delta"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["side"] = result.side.astype(str).str.lower()
    return result


def trading_sessions(con: sqlite3.Connection) -> list[str]:
    return [str(row[0]) for row in con.execute("SELECT DISTINCT quote_date FROM chain_snapshots ORDER BY quote_date")]


def previous_next_sessions(all_sessions: list[str], sessions: Iterable[str]) -> dict[str, tuple[str | None, str | None]]:
    positions = {session: index for index, session in enumerate(all_sessions)}
    result = {}
    for session in sorted(set(sessions)):
        index = positions.get(session)
        result[session] = (
            all_sessions[index - 1] if index is not None and index > 0 else None,
            all_sessions[index + 1] if index is not None and index + 1 < len(all_sessions) else None,
        )
    return result


def sums(frame: pd.DataFrame) -> dict[str, float]:
    calls = frame.side == "call"
    puts = frame.side == "put"
    oi = frame.open_interest.fillna(0.0).clip(lower=0.0)
    volume = frame.volume.where(frame.volume.notna(), 0.0).clip(lower=0.0)
    weight = frame.delta.abs().fillna(0.0)
    return {
        "call_oi": float(oi[calls].sum()), "put_oi": float(oi[puts].sum()),
        "call_volume": float(volume[calls].sum()), "put_volume": float(volume[puts].sum()),
        "call_dw_oi": float((oi[calls] * weight[calls]).sum()),
        "put_dw_oi": float((oi[puts] * weight[puts]).sum()),
        "reported_volume_contracts": int(frame.volume.notna().sum()),
    }


def selected_row(frame: pd.DataFrame, symbol: str) -> pd.Series | None:
    match = frame[frame.option_symbol.astype(str) == str(symbol)]
    return match.iloc[0] if not match.empty else None


def extract_session_features(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    following: pd.DataFrame,
    candidates: pd.DataFrame,
) -> list[dict]:
    current_groups = {key: group for key, group in current.groupby("ticker", sort=False)}
    prior_groups = {key: group for key, group in previous.groupby("ticker", sort=False)}
    next_groups = {key: group for key, group in following.groupby("ticker", sort=False)}
    records: list[dict] = []
    for candidate in candidates.drop_duplicates("candidate_id").itertuples(index=False):
        chain = current_groups.get(str(candidate.ticker), current.iloc[0:0])
        prior = prior_groups.get(str(candidate.ticker), previous.iloc[0:0])
        next_frame = next_groups.get(str(candidate.ticker), following.iloc[0:0])
        chosen = selected_row(chain, str(candidate.symbol)) if pd.notna(candidate.symbol) else None
        old = selected_row(prior, str(candidate.symbol)) if pd.notna(candidate.symbol) else None
        future = selected_row(next_frame, str(candidate.symbol)) if pd.notna(candidate.symbol) else None
        total = sums(chain)
        spot = _number(chosen.underlying_price) if chosen is not None else None
        expiry = str(chosen.expiration_ts) if chosen is not None else None
        chosen_delta = abs(_number(chosen.delta) or 0.0) if chosen is not None else None
        expiry_frame = chain[chain.expiration_ts.astype(str) == expiry] if expiry else chain.iloc[0:0]
        if spot and spot > 0:
            near_frame = chain[((chain.strike / spot) - 1.0).abs() <= 0.025]
        else:
            near_frame = chain.iloc[0:0]
        if chosen_delta is not None:
            delta_frame = chain[(chain.delta.abs() - chosen_delta).abs() <= 0.10]
        else:
            delta_frame = chain.iloc[0:0]
        old_sums = sums(prior)
        record = {
            "candidate_id": str(candidate.candidate_id), "session": str(candidate.session),
            "ticker": str(candidate.ticker), "symbol": str(candidate.symbol),
            "chain_contracts": int(len(chain)), "selected_contract_present": chosen is not None,
            **total,
            **{f"expiry_{key}": value for key, value in sums(expiry_frame).items()},
            **{f"near_{key}": value for key, value in sums(near_frame).items()},
            **{f"delta_{key}": value for key, value in sums(delta_frame).items()},
            **{f"prior_{key}": value for key, value in old_sums.items()},
            "selected_oi": _number(chosen.open_interest) if chosen is not None else None,
            "selected_volume": _number(chosen.volume) if chosen is not None else None,
            "premium_residual": None, "iv_change": None, "oi_change_selected": None,
            "next_oi_change_selected": None,
        }
        if chosen is not None and old is not None:
            new_mid, old_mid = _number(chosen.mid), _number(old.mid)
            new_spot, old_spot = _number(chosen.underlying_price), _number(old.underlying_price)
            old_delta = _number(old.delta)
            if new_mid is not None and old_mid and new_spot is not None and old_spot and old_delta is not None:
                record["premium_residual"] = new_mid / old_mid - 1.0 - old_delta * (new_spot / old_spot - 1.0)
            new_iv, old_iv = _number(chosen.iv), _number(old.iv)
            if new_iv is not None and old_iv is not None:
                record["iv_change"] = new_iv - old_iv
            new_oi, old_oi = _number(chosen.open_interest), _number(old.open_interest)
            if new_oi is not None and old_oi is not None:
                record["oi_change_selected"] = new_oi - old_oi
        if chosen is not None and future is not None:
            future_oi, new_oi = _number(future.open_interest), _number(chosen.open_interest)
            if future_oi is not None and new_oi is not None:
                record["next_oi_change_selected"] = future_oi - new_oi
        records.append(record)
    return records


def build_features(population: pd.DataFrame) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{PHANTOM.as_posix()}?mode=ro", uri=True)
    records: list[dict] = []
    try:
        neighbours = previous_next_sessions(trading_sessions(con), population.entry_session)
        for session, candidate_rows in population.groupby("entry_session", sort=True):
            tickers = candidate_rows.ticker.astype(str).unique().tolist()
            previous, following = neighbours[str(session)]
            current_frame = load_chains(con, str(session), tickers)
            prior_frame = load_chains(con, previous, tickers) if previous else current_frame.iloc[0:0]
            next_frame = load_chains(con, following, tickers) if following else current_frame.iloc[0:0]
            records.extend(extract_session_features(current_frame, prior_frame, next_frame, candidate_rows))
    finally:
        con.close()
    result = pd.DataFrame(records).drop_duplicates("candidate_id")
    result.to_csv(FEATURES_PATH, index=False)
    return result


def feature_frame(raw: pd.DataFrame, floor: float, lagged_oi: bool = False) -> pd.DataFrame:
    frame = raw.copy()
    oi_prefix = "prior_" if lagged_oi else ""
    ratios = {
        "total_oi_pcr": (f"{oi_prefix}put_oi", f"{oi_prefix}call_oi"),
        "dw_oi_pcr": (f"{oi_prefix}put_dw_oi", f"{oi_prefix}call_dw_oi"),
        "total_volume_pcr": ("put_volume", "call_volume"),
        "expiry_oi_pcr": ("expiry_put_oi", "expiry_call_oi"),
        "expiry_volume_pcr": ("expiry_put_volume", "expiry_call_volume"),
        "near_oi_pcr": ("near_put_oi", "near_call_oi"),
        "near_volume_pcr": ("near_put_volume", "near_call_volume"),
        "delta_oi_pcr": ("delta_put_oi", "delta_call_oi"),
        "delta_volume_pcr": ("delta_put_volume", "delta_call_volume"),
    }
    for name, (num, den) in ratios.items():
        values = [ratio(float(n), float(d), floor) for n, d in zip(frame[num].fillna(0), frame[den].fillna(0))]
        frame[name] = values
        clipped = pd.Series(values, index=frame.index, dtype=float).clip(lower=1e-6, upper=1e6)
        frame[f"log_{name}"] = np.log(clipped)
        frame[f"abs_log_{name}"] = frame[f"log_{name}"].abs()
    frame["activity_agreement"] = [
        "AGREE" if pcr_bucket(o) == pcr_bucket(v) and pcr_bucket(o) != "UNKNOWN"
        else "MISSING" if "UNKNOWN" in (pcr_bucket(o), pcr_bucket(v))
        else "MIXED"
        for o, v in zip(frame.total_oi_pcr, frame.total_volume_pcr)
    ]
    return frame


def make_model(columns: tuple[str, ...]) -> Pipeline:
    categorical = [name for name in columns if name == "activity_agreement"]
    numeric = [name for name in columns if name not in categorical]
    transformers = []
    if numeric:
        transformers.append(("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]), numeric))
    if categorical:
        transformers.append(("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), categorical))
    return Pipeline([
        ("features", ColumnTransformer(transformers)),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED)),
    ])


def loso_scores(frame: pd.DataFrame, scenario: str, columns: tuple[str, ...]) -> pd.DataFrame:
    executed = frame.dropna(subset=["base_return"]).copy()
    executed["target"] = (executed.base_return >= TARGET_RETURN).astype(int)
    records: list[pd.DataFrame] = []
    for held_out in sorted(executed.session.unique()):
        train = executed[executed.session != held_out]
        test = executed[executed.session == held_out].copy()
        if len(train) < MIN_CLOSED or train.target.nunique() < 2 or test.empty:
            continue
        model = make_model(columns)
        model.fit(train[list(columns)], train.target)
        test["score"] = model.predict_proba(test[list(columns)])[:, 1]
        test["scenario_id"] = scenario
        test["held_out_session"] = held_out
        records.append(test)
    return pd.concat(records, ignore_index=True) if records else executed.iloc[0:0].copy()


def walk_forward_scores(
    frame: pd.DataFrame,
    scenario: str,
    columns: tuple[str, ...],
    *,
    volume_dropout: float = 0.0,
) -> pd.DataFrame:
    """Purged walk-forward scores using only outcomes known before each test session."""
    executed = frame.dropna(subset=["base_return"]).copy()
    executed["target"] = (executed.base_return >= TARGET_RETURN).astype(int)
    records: list[pd.DataFrame] = []
    volume_columns = [column for column in columns if "volume" in column]
    for held_out in sorted(executed.session.unique()):
        train = executed[executed.end_session.astype(str) < str(held_out)].copy()
        test = executed[executed.session == held_out].copy()
        if (
            len(train) < MIN_CLOSED or train.target.nunique() < 2 or test.empty
            or train.session.nunique() < 2
        ):
            continue
        model = make_model(columns)
        model.fit(train[list(columns)], train.target)
        inference = test[list(columns)].copy()
        if volume_dropout > 0 and volume_columns:
            missing = test.apply(
                lambda row: stable_fraction(
                    f"volume-dropout|{row.candidate_id}|{row.horizon}|{volume_dropout}"
                ) < volume_dropout,
                axis=1,
            )
            inference.loc[missing, volume_columns] = np.nan
        test["score"] = model.predict_proba(inference)[:, 1]
        test["scenario_id"] = scenario
        test["held_out_session"] = held_out
        records.append(test)
    return pd.concat(records, ignore_index=True) if records else executed.iloc[0:0].copy()


def session_delta(selected: pd.DataFrame, all_rows: pd.DataFrame, column: str) -> pd.Series:
    top = selected.groupby("session")[column].mean()
    baseline = all_rows.groupby("session")[column].mean()
    return (top - baseline).dropna()


def summarise_scores(scored: pd.DataFrame) -> dict:
    if scored.empty:
        return {"status": "NO_EVIDENCE", "reason": "No leave-one-session-out scores."}
    selected_parts = []
    for _, group in scored.groupby("session"):
        count = max(1, int(math.ceil(len(group) * TOP_FRACTION)))
        selected_parts.append(group.nlargest(count, "score"))
    selected = pd.concat(selected_parts, ignore_index=True)
    deltas = session_delta(selected, scored, "base_return")
    t_stat, p_value = (stats.ttest_1samp(deltas, 0.0)) if len(deltas) >= 2 else (np.nan, np.nan)
    auc = roc_auc_score(scored.target, scored.score) if scored.target.nunique() == 2 else None
    stresses = {}
    for name, column in (("base", "base_return"), ("spread_25", "stress_spread_25"), ("spread_50", "stress_spread_50")):
        usable = selected.dropna(subset=[column])
        stresses[name] = {
            "n": int(len(usable)), "mean": float(usable[column].mean()) if len(usable) else None,
            "hit_rate": float((usable[column] >= TARGET_RETURN).mean()) if len(usable) else None,
        }
    dropout = {}
    for fraction in (0.10, 0.25):
        kept = selected[selected.apply(
            lambda row: stable_fraction(f"{row.candidate_id}|{row.horizon}|{fraction}") >= fraction, axis=1
        )]
        dropout[str(fraction)] = {
            "remaining": int(len(kept)), "mean": float(kept.base_return.mean()) if len(kept) else None,
        }
    regime = {}
    for bull in (False, True):
        for high_vol in (False, True):
            group = selected[(selected.spy_bull == bull) & (selected.spy_vol_high == high_vol)]
            regime[f"spy_bull={bull}|vol_high={high_vol}"] = {
                "n": int(len(group)), "mean": float(group.base_return.mean()) if len(group) else None,
            }
    relative_screen = bool(
        len(selected) >= MIN_CLOSED and len(deltas) >= MIN_SESSIONS
        and math.isfinite(float(t_stat)) and abs(float(t_stat)) >= 2.0 and float(deltas.mean()) > 0
    )
    monetisation_candidate = bool(
        relative_screen and float(selected.base_return.mean()) > 0
        and stresses["spread_50"]["mean"] is not None and stresses["spread_50"]["mean"] > 0
    )
    return {
        "status": (
            "MONETISATION_CANDIDATE" if monetisation_candidate
            else "RELATIVE_IMPROVEMENT_ONLY" if relative_screen
            else "NO_RELIABLE_EVIDENCE"
        ),
        "rows_scored": int(len(scored)), "sessions": int(scored.session.nunique()),
        "selected": int(len(selected)), "participation": float(len(selected) / len(scored)),
        "auc": float(auc) if auc is not None else None,
        "brier": float(brier_score_loss(scored.target, scored.score)),
        "selected_mean_return": float(selected.base_return.mean()),
        "baseline_mean_return": float(scored.base_return.mean()),
        "selected_hit_rate_25": float((selected.base_return >= TARGET_RETURN).mean()),
        "baseline_hit_rate_25": float((scored.base_return >= TARGET_RETURN).mean()),
        "session_mean_delta": float(deltas.mean()) if len(deltas) else None,
        "paired_t": float(t_stat) if math.isfinite(float(t_stat)) else None,
        "paired_p": float(p_value) if math.isfinite(float(p_value)) else None,
        "session_delta_signs": {"positive": int((deltas > 0).sum()), "negative": int((deltas < 0).sum())},
        "stress": stresses, "quote_dropout": dropout, "regime": regime,
    }


def append_ledger(payload: dict) -> None:
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def execution_manifest(population: pd.DataFrame) -> dict:
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_state": RESEARCH_STATE,
        "production_authority": "NONE",
        "base_scenario": BASE_SCENARIO,
        "target_return": TARGET_RETURN,
        "top_fraction": TOP_FRACTION,
        "denominator_floors": DENOMINATOR_FLOORS,
        "liquidity_aware_floor": 50.0,
        "primary_population": "all recorded-contract rows except explicit TEST/dirty runs",
        "rows": int(len(population)), "candidate_ids": int(population.candidate_id.nunique()),
        "sessions": sorted(population.session.unique().tolist()),
        "hashes": {
            "scenario_register": sha256(REGISTER), "s_act_addendum": sha256(ADDENDUM),
            "round4_rows": sha256(ROUND4), "run_manifest": sha256(RUN_MANIFEST),
            "phantom_schema": hashlib.sha256("|".join(CHAIN_COLUMNS).encode()).hexdigest(),
        },
        "constraints": [
            "PCR is positioning/activity context, not signed flow.",
            "S-ACT-8 next-session OI is future information and is not used to score entry-session rows.",
            "No result changes production ranking, filtering, direction, or execution authority.",
        ],
    }


def causal_decomposition(scores: pd.DataFrame, population: pd.DataFrame, trial_id: str) -> dict:
    scored = scores[scores.trial_id == trial_id].copy()
    if scored.empty:
        return {"status": "NO_EVIDENCE"}
    selected_parts = []
    for _, group in scored.groupby("session"):
        count = max(1, int(math.ceil(len(group) * TOP_FRACTION)))
        selected_parts.append(group.nlargest(count, "score"))
    selected = pd.concat(selected_parts, ignore_index=True)
    context = population[[
        "candidate_id", "horizon", "side", "mid_to_mid", "underlying_return", "entry_spread",
    ]].drop_duplicates(["candidate_id", "horizon"])
    selected = selected.merge(context, on=["candidate_id", "horizon"], how="left", validate="many_to_one")
    selected["directional_underlying"] = np.where(
        selected.side.astype(str).str.upper() == "CALL",
        selected.underlying_return,
        -selected.underlying_return,
    )
    return {
        "status": "COMPLETE", "n": int(len(selected)), "sessions": int(selected.session.nunique()),
        "ask_to_bid_mean": float(selected.base_return.mean()),
        "mid_to_mid_mean": float(selected.mid_to_mid.mean()),
        "mean_quote_friction_gap": float((selected.mid_to_mid - selected.base_return).mean()),
        "directional_underlying_mean": float(selected.directional_underlying.mean()),
        "directional_underlying_positive_rate": float((selected.directional_underlying > 0).mean()),
        "mid_positive_but_ask_bid_loss_rate": float(
            ((selected.mid_to_mid > 0) & (selected.base_return <= 0)).mean()
        ),
        "direction_right_but_ask_bid_loss_rate": float(
            ((selected.directional_underlying > 0) & (selected.base_return <= 0)).mean()
        ),
        "entry_spread_mean": float(selected.entry_spread.mean()),
        "entry_spread_median": float(selected.entry_spread.median()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse-features", action="store_true",
        help="Reuse the immutable candidate/session feature extract after validating candidate identity coverage.",
    )
    args = parser.parse_args(argv)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    population, _ = load_population()
    manifest = execution_manifest(population)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.reuse_features and FEATURES_PATH.exists():
        features = pd.read_csv(FEATURES_PATH, low_memory=False)
        expected = set(population.candidate_id.astype(str))
        observed = set(features.candidate_id.astype(str))
        if expected != observed:
            raise RuntimeError(
                f"feature reuse identity mismatch: expected={len(expected)} observed={len(observed)}"
            )
    else:
        features = build_features(population)
    joined = population.merge(features, on=["candidate_id", "session", "ticker", "symbol"], how="left")
    all_scores: list[pd.DataFrame] = []
    results: dict = {
        "research_state": RESEARCH_STATE, "manifest_sha256": sha256(MANIFEST_PATH),
        "population": {"rows": int(len(joined)), "sessions": int(joined.session.nunique())},
        "scenarios": {},
        "S-ACT-0": {
            "status": "BASELINE_ONLY", "closed": int(joined.base_return.notna().sum()),
            "mean_return": float(joined.base_return.mean()),
            "hit_rate_25": float((joined.dropna(subset=["base_return"]).base_return >= TARGET_RETURN).mean()),
        },
        "S-ACT-8": {
            "status": "DEFERRED_FUTURE_INFORMATION_ONLY",
            "available_next_oi_changes": int(features.next_oi_change_selected.notna().sum()),
            "reason": "Next-session OI is not observable at the original entry cutoff; using it would leak future information.",
        },
    }
    for floor in DENOMINATOR_FLOORS:
        prepared = feature_frame(joined, floor=floor)
        for horizon in sorted(prepared.horizon.unique()):
            horizon_frame = prepared[prepared.horizon == horizon].copy()
            for scenario, columns in SCENARIOS.items():
                for method, scorer in (("LOSO", loso_scores), ("PURGED_WALK_FORWARD", walk_forward_scores)):
                    trial_id = f"{scenario}|H{int(horizon)}|F{int(floor)}|{method}"
                    scored = scorer(horizon_frame, scenario, columns)
                    summary = summarise_scores(scored)
                    results["scenarios"][trial_id] = summary
                    if not scored.empty:
                        scored = scored[["candidate_id", "session", "ticker", "horizon", "scenario_id", "score", "target", "base_return"]]
                        scored["trial_id"] = trial_id
                        all_scores.append(scored)
                    append_ledger({
                        "trial_id": trial_id, "executed_at_utc": datetime.now(timezone.utc).isoformat(),
                        "scenario": scenario, "horizon": int(horizon), "denominator_floor": floor,
                        "method": method, "result": summary.get("status"),
                        "manifest_sha256": results["manifest_sha256"], "production_authority": "NONE",
                    })

    # Explicit staleness stress: replace contemporaneous OI with the previous available session.
    stale = feature_frame(joined, floor=50.0, lagged_oi=True)
    for horizon in sorted(stale.horizon.unique()):
        horizon_frame = stale[stale.horizon == horizon].copy()
        for scenario in ("S-ACT-1", "S-ACT-2", "S-ACT-4", "S-ACT-9"):
            trial_id = f"{scenario}|H{int(horizon)}|F50|STALE_OI_PURGED_WALK_FORWARD"
            scored = walk_forward_scores(horizon_frame, scenario, SCENARIOS[scenario])
            results["scenarios"][trial_id] = summarise_scores(scored)
            append_ledger({
                "trial_id": trial_id, "executed_at_utc": datetime.now(timezone.utc).isoformat(),
                "scenario": scenario, "horizon": int(horizon), "denominator_floor": 50.0,
                "method": "purged walk-forward with prior-session OI stress",
                "result": results["scenarios"][trial_id].get("status"),
                "manifest_sha256": results["manifest_sha256"], "production_authority": "NONE",
            })

    # Missing-volume stress: erase observable volume evidence at inference only.
    prepared = feature_frame(joined, floor=50.0)
    for horizon in sorted(prepared.horizon.unique()):
        horizon_frame = prepared[prepared.horizon == horizon].copy()
        for scenario in ("S-ACT-3", "S-ACT-4", "S-ACT-9"):
            for dropout in (0.10, 0.25):
                trial_id = f"{scenario}|H{int(horizon)}|F50|VOLUME_DROPOUT_{int(dropout * 100)}|PURGED_WALK_FORWARD"
                scored = walk_forward_scores(
                    horizon_frame, scenario, SCENARIOS[scenario], volume_dropout=dropout
                )
                results["scenarios"][trial_id] = summarise_scores(scored)
                append_ledger({
                    "trial_id": trial_id, "executed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "scenario": scenario, "horizon": int(horizon), "denominator_floor": 50.0,
                    "method": f"purged walk-forward with {int(dropout * 100)}% inference volume dropout",
                    "result": results["scenarios"][trial_id].get("status"),
                    "manifest_sha256": results["manifest_sha256"], "production_authority": "NONE",
                })

    score_output = pd.concat(all_scores, ignore_index=True) if all_scores else pd.DataFrame()
    if not score_output.empty:
        score_output.to_csv(SCORES_PATH, index=False, compression="gzip")
    results["feature_coverage"] = {
        "candidate_features": int(len(features)),
        "selected_contract_present": int(features.selected_contract_present.sum()),
        "premium_residual_available": int(features.premium_residual.notna().sum()),
        "selected_volume_available": int(features.selected_volume.notna().sum()),
        "next_oi_available_but_deferred": int(features.next_oi_change_selected.notna().sum()),
    }
    results["causal_decomposition"] = {
        trial: causal_decomposition(score_output, joined, trial)
        for trial in (
            "S-ACT-9|H1|F50|PURGED_WALK_FORWARD",
            "S-ACT-9|H3|F50|PURGED_WALK_FORWARD",
            "S-ACT-6|H1|F50|PURGED_WALK_FORWARD",
        )
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    ranked = sorted(
        ((key, value) for key, value in results["scenarios"].items() if value.get("selected_mean_return") is not None),
        key=lambda item: item[1].get("session_mean_delta") or -999,
        reverse=True,
    )
    report = [
        "# S-ACT Backtest and Stress Test Report — 2026-09-20", "",
        f"**State:** {RESEARCH_STATE} — no production authority", "",
        "## Scope", "",
        f"- Recorded direction and contract only: `{BASE_SCENARIO}`.",
        f"- {len(joined):,} horizon rows; {joined.candidate_id.nunique():,} candidates; {joined.session.nunique()} sessions.",
        "- Explicit TEST/dirty runs excluded.",
        "- Target: option ask-to-bid return of at least 25%; top-quintile ranking evaluated out of sample by session.",
        "- PCR remains unsigned positioning/activity evidence. No buyer/seller direction is inferred.", "",
        "## Highest purged walk-forward screening results", "",
        "| Trial | Status | AUC | Selected mean | Baseline mean | Session delta | t |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = [(key, value) for key, value in ranked if "PURGED_WALK_FORWARD" in key]
    for key, value in ranked[:20]:
        report.append(
            f"| {key} | {value['status']} | {value.get('auc', float('nan')):.3f} | "
            f"{value['selected_mean_return']:.3f} | {value['baseline_mean_return']:.3f} | "
            f"{value.get('session_mean_delta') or 0:.3f} | {value.get('paired_t') or 0:.2f} |"
        )
    report += [
        "", "## Interpretation controls", "",
        "- A relative screening improvement is not a monetisation result or a production promotion.",
        "- The configurations share only eight source sessions and are not independent trials; PBO/deflated-Sharpe reliability cannot be claimed from configuration count.",
        "- The primary temporal test is purged walk-forward: every training outcome ends before its test session begins.",
        "- S-ACT-8 is deliberately not scored at the original entry time because next-session OI is future information.",
        "- Results must be judged across denominator floors, stale-OI stress, spread widening, quote dropout, and market regimes.",
        "- Any surviving alternative advances to the thesis-conditioned entry/path tournament; it does not change the current pipeline by itself.",
        "", "## Causal decomposition", "",
    ]
    for trial, item in results["causal_decomposition"].items():
        if item.get("status") != "COMPLETE":
            continue
        report += [
            f"### {trial}", "",
            f"- Ask-to-bid mean: {item['ask_to_bid_mean']:.1%}; mid-to-mid mean: {item['mid_to_mid_mean']:.1%}.",
            f"- Mean quote-friction gap: {item['mean_quote_friction_gap']:.1%}; median entry spread: {item['entry_spread_median']:.1%}.",
            f"- Directional underlying positive: {item['directional_underlying_positive_rate']:.1%}.",
            f"- Mid-price gain but executable ask-to-bid loss: {item['mid_positive_but_ask_bid_loss_rate']:.1%}.",
            f"- Direction right but executable ask-to-bid loss: {item['direction_right_but_ask_bid_loss_rate']:.1%}.", "",
        ]
    report += [
        "## Research conclusion", "",
        "- Activity context contains relative ranking information, with printed volume and local expiry/moneyness structure stronger than delta-weighted OI alone.",
        "- It does not solve monetisation by itself: every primary top-quintile alternative remains negative on executable ask-to-bid returns.",
        "- The next registered test must combine activity evidence with contract-family choice, spread/limit-entry feasibility, and liquidity maturation while preserving the ticker thesis for human review.",
    ]
    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "COMPLETE", "report": str(REPORT_PATH), "results": str(RESULTS_PATH),
        "features": str(FEATURES_PATH), "trials": len(results["scenarios"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
