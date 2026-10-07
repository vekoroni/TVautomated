"""Business rules for the daily regime model (Colab port, v1.8).

1. A prediction is dated by the session whose close it was computed from (the board scores
   row D from the next open), and the newest session gets a live prediction.
2. The regime file is a record of what the model said on each session: an older row is
   never rewritten by a later run; the old re-predicted history is archived, not scored.
No network, no live data.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_daily_regime_model_v1_8.py"


def _module():
    spec = importlib.util.spec_from_file_location("daily_regime_model", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # must not fetch, fit or write on import
    return module


class _EchoModel:
    """Returns the (scaled) first feature as the 'probability', so a test can tell which
    session's row produced each prediction."""
    def fit(self, X, y):
        return self

    def predict_proba(self, X):
        return np.column_stack([1.0 - X[:, 0], X[:, 0]])


def _inputs(n: int = 80):
    sessions = pd.bdate_range("2026-05-01", periods=n)
    features = pd.DataFrame({"session_id": np.arange(n, dtype=float),
                             "other": np.sin(np.arange(n))}, index=sessions)
    spy = pd.Series(np.where(np.arange(n) % 3 == 0, -0.01, 0.01), index=sessions)
    return features, spy


def _decode(prob: float, features: pd.DataFrame, labelled: pd.Index) -> float:
    column = features.loc[labelled, "session_id"]
    return prob * column.std(ddof=0) + column.mean()     # undo StandardScaler on column 0


def test_a_prediction_is_dated_by_the_session_whose_data_it_used():
    m, (features, spy) = _module(), _inputs()
    out = m.predict_by_session(features, spy, make_model=_EchoModel)
    labelled = features.index[:-1]                      # the newest session has no next-day label
    assert len(out["backtest"]) > 0
    for session, prob in out["backtest"]["Regime_Probability"].items():
        assert round(_decode(prob, features, labelled)) == features.loc[session, "session_id"]


def test_the_newest_session_gets_a_live_prediction_from_its_own_close():
    m, (features, spy) = _module(), _inputs()
    out = m.predict_by_session(features, spy, make_model=_EchoModel)
    newest = features.index[-1]
    assert out["live_session"] == newest
    assert round(_decode(out["live_probability"], features, features.index[:-1])) == \
        features.loc[newest, "session_id"]
    assert newest not in out["backtest"].index


def _live_row(m, session: str, probability: float) -> pd.DataFrame:
    return m.regime_rows([pd.Timestamp(session)], [probability], best_t=0.6, best_acc=0.55,
                         hyg=[0.001], vix=[15.0], vix_source="YFINANCE", vix_flag="DIRECT",
                         kind="LIVE", generated_at_utc="2026-10-07T21:30:00Z")


def test_an_older_logged_prediction_is_never_rewritten(tmp_path):
    m = _module()
    log, archive = tmp_path / "avshunter_daily_macro_regime.csv", tmp_path / "archive"
    m.append_live_row(log, _live_row(m, "2026-10-05", 0.62), archive)
    m.append_live_row(log, _live_row(m, "2026-10-06", 0.55), archive)
    first = pd.read_csv(log)
    m.append_live_row(log, _live_row(m, "2026-10-07", 0.40), archive)   # a later run
    m.append_live_row(log, _live_row(m, "2026-10-07", 0.45), archive)   # same-session rerun
    after = pd.read_csv(log)
    assert list(after["Date"]) == ["2026-10-05", "2026-10-06", "2026-10-07"]
    pd.testing.assert_frame_equal(after.iloc[:2].reset_index(drop=True), first)
    assert after.iloc[-1]["Regime_Probability"] == 0.45                  # only its own session replaced


def test_the_old_re_predicted_history_is_archived_not_kept_in_the_scored_file(tmp_path):
    m = _module()
    log, archive = tmp_path / "avshunter_daily_macro_regime.csv", tmp_path / "archive"
    old = pd.DataFrame({"Date": ["2026-10-02", "2026-10-05"], "Regime_Probability": [0.58, 0.64],
                        "Regime": ["Risk-Off", "Risk-On"]})
    old.to_csv(log, index=False)
    m.append_live_row(log, _live_row(m, "2026-10-07", 0.58), archive)
    kept = list(archive.glob("*.csv"))
    assert len(kept) == 1 and pd.read_csv(kept[0]).equals(old)            # archived, not deleted
    assert list(pd.read_csv(log)["Date"]) == ["2026-10-07"]
    assert set(pd.read_csv(log)["Prediction_Kind"]) == {"LIVE"}
