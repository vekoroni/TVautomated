"""Round 3 direction tournament with a sealed chronological holdout."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

HERE = Path(__file__).resolve().parent
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
H_ROWS = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
PROTOCOL = HERE / "ROUND3_DIRECTION_PROTOCOL_20260919.md"
OUTPUT = HERE / "round3_direction_results.json"
DETAIL = HERE / "round3_direction_holdout_rows.csv"
REPORT = HERE / "ROUND3_DIRECTION_REPORT_20260919.md"
HORIZONS = (1, 3, 5)
FEATURES = [
    "ret5", "ret20", "rs20", "atr_pct", "atr_rank", "bb_width", "bb_rank",
    "compression", "volume_ratio", "dist_low", "dist_high", "spy5", "spy20",
]
TRAIN_END = "2024-11-29"
CAL_START, CAL_END = "2025-01-15", "2025-11-28"
HOLDOUT_START = "2026-01-15"
SEED = 19092026


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_wide() -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{PRICE_DB.as_posix()}?mode=ro", uri=True)
    try:
        frame = pd.read_sql_query(
            "SELECT ticker,trading_date,high,low,close,volume FROM ohlcv_daily "
            "WHERE trading_date >= '2020-09-01' AND trading_date <= '2026-09-17'",
            con,
        )
    finally:
        con.close()
    return {
        column: frame.pivot_table(index="trading_date", columns="ticker", values=column, aggfunc="last")
        .sort_index().astype("float32")
        for column in ("high", "low", "close", "volume")
    }


def rolling_rank(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=60).rank(pct=True)


def feature_frames(wide: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    close, high, low, volume = wide["close"], wide["high"], wide["low"], wide["volume"]
    previous = close.shift(1)
    tr = pd.concat(
        [(high - low).stack(), (high - previous).abs().stack(), (low - previous).abs().stack()], axis=1
    ).max(axis=1).unstack()
    atr_pct = tr.ewm(span=14, adjust=False).mean() / close
    bb_width = 4.0 * close.rolling(20).std() / close.rolling(20).mean()
    ret5, ret20 = close / close.shift(5) - 1.0, close / close.shift(20) - 1.0
    spy5 = ret5["SPY"] if "SPY" in ret5 else ret5.median(axis=1)
    spy20 = ret20["SPY"] if "SPY" in ret20 else ret20.median(axis=1)
    atr_rank, bb_rank = rolling_rank(atr_pct, 252), rolling_rank(bb_width, 252)
    frames = {
        "ret5": ret5,
        "ret20": ret20,
        "rs20": ret20.sub(spy20, axis=0),
        "atr_pct": atr_pct,
        "atr_rank": atr_rank,
        "bb_width": bb_width,
        "bb_rank": bb_rank,
        "compression": -(atr_rank + bb_rank),
        "volume_ratio": volume / volume.rolling(20).mean().shift(1),
        "dist_low": close / close.rolling(252, min_periods=120).min() - 1.0,
        "dist_high": close / close.rolling(252, min_periods=120).max() - 1.0,
        "spy5": pd.DataFrame(np.repeat(spy5.to_numpy()[:, None], close.shape[1], axis=1), index=close.index, columns=close.columns),
        "spy20": pd.DataFrame(np.repeat(spy20.to_numpy()[:, None], close.shape[1], axis=1), index=close.index, columns=close.columns),
    }
    tradeable = (close > 5) & ((close * volume).rolling(20).mean() > 5e6)
    return {name: values.where(tradeable) for name, values in frames.items()}, tradeable


def sampled_dates(index: pd.Index) -> list[str]:
    return [value for value in index if value >= "2021-10-01"][::5]


def build_dataset(
    features: dict[str, pd.DataFrame],
    wide: dict[str, pd.DataFrame],
    tradeable: pd.DataFrame,
    horizon: int,
    dates: list[str] | None = None,
) -> pd.DataFrame:
    close = wide["close"]
    forward = close.shift(-horizon) / close - 1.0
    market = forward.median(axis=1)
    records = []
    evaluation_dates = sampled_dates(close.index) if dates is None else [value for value in dates if value in close.index]
    for session in evaluation_dates:
        block = pd.DataFrame({name: frame.loc[session] for name, frame in features.items()})
        block["future_return"] = forward.loc[session]
        block["market_return"] = market.loc[session]
        block["tradeable"] = tradeable.loc[session]
        block = block[block.tradeable & block.future_return.notna()]
        if block.empty:
            continue
        block["session"] = session
        block["ticker"] = block.index.astype(str)
        records.append(block.reset_index(drop=True))
    result = pd.concat(records, ignore_index=True)
    result["target"] = (result.future_return > 0).astype(int)
    result["market_adjusted"] = result.future_return - result.market_return
    return result


def make_models() -> dict[str, Pipeline]:
    logistic = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(C=0.1, max_iter=300, random_state=SEED)),
    ])
    boosted = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(
            max_leaf_nodes=15, learning_rate=0.05, max_iter=80,
            l2_regularization=1.0, random_state=SEED,
        )),
    ])
    return {"LOGISTIC_V1": logistic, "HGB_V1": boosted}


def bootstrap(frame: pd.DataFrame, column: str, samples: int = 3000) -> dict:
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
    })
    if len(sessions) < 2:
        return result
    groups = {s: clean.loc[clean.session == s, column].to_numpy(float) for s in sessions}
    rng = np.random.default_rng(SEED)
    means = np.empty(samples)
    for index in range(samples):
        draw = rng.choice(sessions, len(sessions), replace=True)
        means[index] = np.concatenate([groups[s] for s in draw]).mean()
    result["ci90"] = [round(float(v), 6) for v in np.quantile(means, [0.05, 0.95])]
    return result


def score_rule(frame: pd.DataFrame, name: str, sign: pd.Series, probability: pd.Series | None = None) -> dict:
    work = frame.copy()
    work["signed_return"] = sign * work.future_return
    work["signed_market_adjusted"] = sign * work.market_adjusted
    result = {
        "direction_mix_call": round(float((sign > 0).mean()), 4),
        "signed_return": bootstrap(work, "signed_return"),
        "signed_market_adjusted": bootstrap(work, "signed_market_adjusted"),
    }
    if probability is not None:
        result["brier"] = round(float(brier_score_loss(work.target, probability)), 6)
        result["roc_auc"] = round(float(roc_auc_score(work.target, probability)), 6)
        confidence = (probability - 0.5).abs()
        high = confidence.groupby(work.session).rank(pct=True, method="first") >= 0.80
        high_frame = work[high].copy()
        result["high_confidence"] = {
            "coverage": round(float(high.mean()), 4),
            "signed_return": bootstrap(high_frame, "signed_return"),
            "signed_market_adjusted": bootstrap(high_frame, "signed_market_adjusted"),
        }
    return result


def deterministic_scores(frame: pd.DataFrame) -> dict[str, pd.Series]:
    to_sign = lambda values: pd.Series(np.where(values >= 0, 1.0, -1.0), index=frame.index)
    return {
        "ALWAYS_CALL": pd.Series(1.0, index=frame.index),
        "MOMENTUM_20": to_sign(frame.ret20),
        "MEAN_REVERSION_5": -to_sign(frame.ret5),
        "SPY_REGIME": to_sign(frame.spy20),
    }


def h_comparison(h_rows: pd.DataFrame, feature_data: pd.DataFrame, predictions: dict[str, pd.Series]) -> dict:
    base = h_rows[["session", "ticker", "direction"]].copy()
    base["current_sign"] = base.direction.map({"CALL": 1.0, "PUT": -1.0})
    joined = base.merge(feature_data, on=["session", "ticker"], how="inner")
    result = {"matched": int(len(joined)), "sessions": int(joined.session.nunique()), "rules": {}}
    current = joined.current_sign
    result["rules"]["CURRENT_H"] = score_rule(joined, "CURRENT_H", current)
    for name, sign_series in predictions.items():
        mapping = feature_data[["session", "ticker"]].copy()
        mapping["sign"] = sign_series.to_numpy()
        aligned = joined[["session", "ticker"]].merge(mapping, on=["session", "ticker"], how="left")["sign"]
        aligned.index = joined.index
        result["rules"][name] = score_rule(joined, name, aligned)
    return result


def main() -> int:
    wide = load_wide()
    features, tradeable = feature_frames(wide)
    h_rows = pd.read_csv(H_ROWS, low_memory=False)
    h_rows["session"] = h_rows.session.astype(str)
    all_results = {}
    holdout_details = []
    h_results = {}
    for horizon in HORIZONS:
        data = build_dataset(features, wide, tradeable, horizon)
        train = data[data.session <= TRAIN_END].copy()
        calibration = data[(data.session >= CAL_START) & (data.session <= CAL_END)].copy()
        holdout = data[data.session >= HOLDOUT_START].copy()
        models = make_models()
        model_probabilities = {}
        for name, model in models.items():
            model.fit(train[FEATURES], train.target)
            model_probabilities[name] = {
                "calibration": pd.Series(model.predict_proba(calibration[FEATURES])[:, 1], index=calibration.index),
                "holdout": pd.Series(model.predict_proba(holdout[FEATURES])[:, 1], index=holdout.index),
            }
        split_results = {}
        for split_name, split_frame in (("calibration_2025", calibration), ("holdout_2026", holdout)):
            rules = {
                name: score_rule(split_frame, name, sign)
                for name, sign in deterministic_scores(split_frame).items()
            }
            for name in models:
                probability = model_probabilities[name]["calibration" if split_name.startswith("calibration") else "holdout"]
                sign = pd.Series(np.where(probability >= 0.5, 1.0, -1.0), index=split_frame.index)
                rules[name] = score_rule(split_frame, name, sign, probability)
                if split_name == "holdout_2026":
                    detail = split_frame[["session", "ticker", "future_return", "market_adjusted"]].copy()
                    detail["horizon"] = horizon
                    detail["model"] = name
                    detail["probability_up"] = probability
                    detail["sign"] = sign
                    holdout_details.append(detail)
            split_results[split_name] = {
                "rows": int(len(split_frame)),
                "sessions": int(split_frame.session.nunique()),
                "rules": rules,
            }
        all_results[str(horizon)] = {
            "train_rows": int(len(train)),
            "train_sessions": int(train.session.nunique()),
            "splits": split_results,
        }

        h_sessions = sorted(set(h_rows.session.unique()))
        h_data = build_dataset(features, wide, tradeable, horizon, dates=h_sessions)
        h_data = h_data[h_data.session >= HOLDOUT_START].copy()
        predictions = deterministic_scores(h_data)
        for name in models:
            probability = pd.Series(models[name].predict_proba(h_data[FEATURES])[:, 1], index=h_data.index)
            predictions[name] = pd.Series(np.where(probability >= 0.5, 1.0, -1.0), index=h_data.index)
        h_results[str(horizon)] = h_comparison(h_rows, h_data, predictions)

    detail_frame = pd.concat(holdout_details, ignore_index=True)
    detail_frame.to_csv(DETAIL, index=False)
    result = {
        "research_state": "EXPLORATORY_NO_AUTHORITY",
        "protocol_sha256": sha256(PROTOCOL),
        "price_db_metadata": {"bytes": PRICE_DB.stat().st_size, "modified_ns": PRICE_DB.stat().st_mtime_ns},
        "splits": {
            "train_end": TRAIN_END, "calibration": [CAL_START, CAL_END], "holdout_start": HOLDOUT_START,
        },
        "universe_results": all_results,
        "h_candidate_comparison": h_results,
        "constraints": [
            "The 2026 holdout was opened only after the protocol was written.",
            "No model or threshold was tuned on holdout results.",
            "Direction results do not imply option profitability.",
            "No production model is activated.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "# AVSHUNTER solution tournament — Round 3 direction holdout",
        "",
        "**State:** Exploratory research only. The sealed 2026 holdout has now been opened under the frozen protocol.",
        "",
        "## Universe holdout result",
        "",
        "| Horizon | Rule | Signed return | 90% CI | Hit rate | Market-adjusted | CALL mix | AUC |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for horizon in map(str, HORIZONS):
        rules = all_results[horizon]["splits"]["holdout_2026"]["rules"]
        for name, item in rules.items():
            pct = lambda value: "n/a" if value is None else f"{100 * value:.3f}%"
            ci = item["signed_return"]["ci90"]
            ci_text = "n/a" if ci[0] is None else f"{pct(ci[0])}…{pct(ci[1])}"
            lines.append(
                f"| {horizon} | {name} | {pct(item['signed_return']['mean'])} | {ci_text} | "
                f"{pct(item['signed_return']['hit_rate'])} | {pct(item['signed_market_adjusted']['mean'])} | "
                f"{pct(item['direction_mix_call'])} | {item.get('roc_auc', 'n/a')} |"
            )
    lines += [
        "",
        "## Decision rule",
        "",
        "A model advances only if its held-out result is consistently positive across horizons and improves on deterministic baselines without collapsing to one direction. No option-expression conclusion is inferred from this table.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "report": str(REPORT), "detail": str(DETAIL)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
