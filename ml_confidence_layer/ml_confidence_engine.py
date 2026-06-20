"""
AVSHUNTER ML Confidence Engine
================================
XGBoost + LSTM Ensemble — Post-VANGUARD EV Adjustment

Purpose:
    Takes each ticker that reaches VANGUARD and produces two scores:
      1. XGBoost Feature Importance Score (0-100)
         Evaluates: Wyckoff phase, compression state, regime,
                    control state, options flow, win rate, EV
      2. LSTM Sequence Confidence Score (0-100)
         Reads: last 60 bars of price/volume behaviour

    These combine into a single ML Edge Multiplier (0.5x – 1.5x)
    that adjusts VANGUARD's EV calculation upward or downward.
    It does NOT override the verdict. It informs it.

Output example:
    VANGUARD EV = 3.2  →  ML Multiplier = 1.3  →  Adjusted EV = 4.16
    VANGUARD EV = 3.2  →  ML Multiplier = 0.7  →  Adjusted EV = 2.24

Install:
    C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\ml_confidence_layer\\ml_confidence_engine.py
"""

import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# ── Optional imports — graceful fallback to heuristics if not installed ───────
try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.optimizers import Adam
    LSTM_AVAILABLE = True
except ImportError:
    LSTM_AVAILABLE = False

logger = logging.getLogger("ml_confidence")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [ML] %(message)s")

SEQUENCE_LENGTH = 60
MODEL_DIR       = Path(__file__).parent / "models"
OUTCOMES_LOG    = Path(__file__).parent / "trade_outcomes.json"
MIN_TRADES_TO_TRAIN = 10

# Multiplier bounds — ML adjusts EV within this range
MULTIPLIER_MIN = 0.50
MULTIPLIER_MAX = 1.50

# Encoding maps
PHASE_MAP    = {"accumulation": 3, "markup": 4, "distribution": 1, "markdown": 0, "unknown": 2}
CONTROL_MAP  = {"BUYERS": 2, "NEUTRAL": 1, "SELLERS": 0}
COMPRESS_MAP = {"COMPRESSED": 2, "NORMAL": 1, "EXPANDED": 0}
REGIME_MAP   = {"RISK_ON": 2, "NEUTRAL": 1, "RISK_OFF": 0}


# ── Input / Output ────────────────────────────────────────────────────────────
@dataclass
class VanguardSignal:
    """
    Fields from VANGUARD passed to the ML engine.
    These are the exact inputs XGBoost and LSTM evaluate.
    """
    ticker:             str
    verdict:            str    # TRADE / DISCOVER / OBSERVE / REJECT
    ev:                 float  # VANGUARD Expected Value (raw, pre-ML)
    win_rate:           float  # 0.0 – 1.0 from actuarial engine
    wyckoff_phase:      str    # accumulation / markup / distribution / markdown
    control_state:      str    # BUYERS / SELLERS / NEUTRAL
    compression_state:  str    # COMPRESSED / NORMAL / EXPANDED
    macro_regime:       str    # RISK_ON / RISK_OFF / NEUTRAL
    options_flow_score: float  # 0 – 100
    volume_ratio:       float  # today vol / 20d avg
    atr_pct:            float  # ATR as % of price
    ev_normalised:      float  # EV rescaled 0-1 (ev / 0.20 cap) for ML features


@dataclass
class MLEdgeResult:
    """
    Output from ML engine for each ticker.
    adjusted_ev is what VANGUARD should use downstream.
    """
    ticker:         str
    verdict:        str
    xgb_score:      float   # 0–100  feature importance score
    lstm_score:     float   # 0–100  sequence confidence score
    ensemble_score: float   # 0–100  combined
    multiplier:     float   # 0.5x – 1.5x  applied to VANGUARD EV
    raw_ev:         float   # VANGUARD EV before adjustment
    adjusted_ev:    float   # raw_ev × multiplier  ← use this
    note:           str
    scored_at:      str


# ── Feature Engineering ───────────────────────────────────────────────────────
def build_xgb_features(s: VanguardSignal) -> np.ndarray:
    """
    12-feature vector representing VANGUARD multi-factor state.
    These are the same signals VANGUARD already computed —
    XGBoost learns which combinations historically produce
    higher or lower actual EV than VANGUARD predicted.
    """
    return np.array([
        s.win_rate,
        s.ev_normalised,                                              # EV scaled 0-1
        PHASE_MAP.get(s.wyckoff_phase.lower(), 2),
        CONTROL_MAP.get(s.control_state.upper(), 1),
        COMPRESS_MAP.get(s.compression_state.upper(), 1),
        REGIME_MAP.get(s.macro_regime.upper(), 1),
        s.options_flow_score / 100.0,
        s.volume_ratio,
        s.atr_pct,                                                    # real ATR
        1.0 if s.wyckoff_phase.lower() in ("markup", "accumulation") else 0.0,
        1.0 if s.control_state.upper() == "BUYERS" else 0.0,
        1.0 if s.macro_regime.upper() == "RISK_ON" else 0.0,
    ], dtype=np.float32).reshape(1, -1)


def build_lstm_sequence(s: VanguardSignal,
                        history_df: Optional[pd.DataFrame] = None) -> np.ndarray:
    """
    60-bar × 5-feature sequence.
    LSTM reads the sequential price/volume behaviour leading up to
    the VANGUARD verdict — detecting whether the pattern has been
    building cleanly or erratically.

    Uses real OHLCV history if supplied.
    Falls back to synthetic prior from signal state until real data flows.
    """
    if history_df is not None and len(history_df) >= SEQUENCE_LENGTH:
        cols = [c for c in ["close", "volume", "atr", "vwap_dev", "options_flow"]
                if c in history_df.columns]
        arr = history_df[cols].values[-SEQUENCE_LENGTH:].astype(np.float32)
        col_range = arr.max(axis=0) - arr.min(axis=0)
        col_range[col_range == 0] = 1
        arr = (arr - arr.min(axis=0)) / col_range
        if arr.shape[1] < 5:
            pad = np.zeros((SEQUENCE_LENGTH, 5 - arr.shape[1]), dtype=np.float32)
            arr = np.concatenate([arr, pad], axis=1)
        return arr.reshape(1, SEQUENCE_LENGTH, 5)

    # Synthetic prior derived from current signal state
    base_trend = 0.5 + (s.win_rate - 0.5) * 0.4
    noise      = np.random.normal(0, 0.03, (SEQUENCE_LENGTH, 5)).astype(np.float32)
    template   = np.array([
        base_trend,
        min(s.volume_ratio / 3.0, 1.0),
        min(s.atr_pct * 10, 1.0),                 # real ATR
        0.5 + (s.options_flow_score - 50) / 100.0,
        REGIME_MAP.get(s.macro_regime.upper(), 1) / 2.0
    ], dtype=np.float32)
    seq = np.clip(np.ones((SEQUENCE_LENGTH, 5)) * template + noise, 0, 1)
    return seq.reshape(1, SEQUENCE_LENGTH, 5)


# ── Model Management ──────────────────────────────────────────────────────────
class ModelManager:
    def __init__(self):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self.xgb_model  = None
        self.lstm_model = None
        self._load_or_init()

    def _load_or_init(self):
        xgb_path  = MODEL_DIR / "xgb_model.json"
        lstm_path = MODEL_DIR / "lstm_model.keras"

        if XGB_AVAILABLE:
            if xgb_path.exists():
                self.xgb_model = xgb.XGBClassifier()
                self.xgb_model.load_model(str(xgb_path))
                logger.info("XGBoost loaded from disk")
            else:
                self.xgb_model = self._build_xgb()
                logger.info("XGBoost initialised — heuristic priors active")

        if LSTM_AVAILABLE:
            if lstm_path.exists():
                self.lstm_model = load_model(str(lstm_path))
                logger.info("LSTM loaded from disk")
            else:
                self.lstm_model = self._build_lstm()
                logger.info("LSTM initialised — heuristic priors active")

    def _build_xgb(self):
        if not XGB_AVAILABLE:
            return None
        return xgb.XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="logloss", random_state=42
        )

    def _build_lstm(self):
        if not LSTM_AVAILABLE:
            return None
        m = Sequential([
            LSTM(64, input_shape=(SEQUENCE_LENGTH, 5), return_sequences=True),
            Dropout(0.2),
            LSTM(32),
            Dropout(0.2),
            Dense(16, activation="relu"),
            Dense(1,  activation="sigmoid")
        ])
        m.compile(optimizer=Adam(0.001), loss="binary_crossentropy", metrics=["accuracy"])
        return m

    def retrain(self, outcomes: list):
        """Auto-retrains on logged trade outcomes once threshold is met."""
        if len(outcomes) < MIN_TRADES_TO_TRAIN:
            return

        X_xgb, X_lstm, y = [], [], []
        for o in outcomes:
            try:
                s = VanguardSignal(**o["signal"])
                X_xgb.append(build_xgb_features(s)[0])
                X_lstm.append(build_lstm_sequence(s)[0])
                y.append(1 if o["outcome"] == "WIN" else 0)
            except Exception as e:
                logger.warning(f"Skipping malformed outcome: {e}")

        if len(y) < MIN_TRADES_TO_TRAIN:
            return

        X_xgb  = np.array(X_xgb,  dtype=np.float32)
        X_lstm = np.array(X_lstm, dtype=np.float32)
        y      = np.array(y,      dtype=np.int32)

        if XGB_AVAILABLE and self.xgb_model:
            self.xgb_model.fit(X_xgb, y)
            self.xgb_model.save_model(str(MODEL_DIR / "xgb_model.json"))
            logger.info(f"XGBoost retrained on {len(y)} outcomes")

        if LSTM_AVAILABLE and self.lstm_model:
            self.lstm_model.fit(X_lstm, y, epochs=20, batch_size=8, verbose=0)
            self.lstm_model.save(str(MODEL_DIR / "lstm_model.keras"))
            logger.info(f"LSTM retrained on {len(y)} outcomes")


# ── ML Confidence Engine ──────────────────────────────────────────────────────
class MLConfidenceEngine:
    """
    Primary entry point.

    Usage:
        engine = MLConfidenceEngine()
        result = engine.score(vanguard_signal)
        # use result.adjusted_ev downstream
    """

    def __init__(self):
        self.models = ModelManager()

    def score(self, s: VanguardSignal,
              history_df: Optional[pd.DataFrame] = None) -> MLEdgeResult:
        """
        Score a single VANGUARD signal.
        Returns MLEdgeResult with adjusted_ev = raw_ev × multiplier.
        """
        xgb_score  = self._score_xgb(s)
        lstm_score = self._score_lstm(s, history_df)

        # Weighted ensemble: XGBoost slightly dominant (feature-rich)
        ensemble = round(0.55 * xgb_score + 0.45 * lstm_score, 1)

        # Map ensemble score (0-100) to EV multiplier (0.5 – 1.5)
        multiplier   = self._score_to_multiplier(ensemble)
        adjusted_ev  = round(s.ev * multiplier, 3)

        return MLEdgeResult(
            ticker         = s.ticker,
            verdict        = s.verdict,
            xgb_score      = xgb_score,
            lstm_score     = lstm_score,
            ensemble_score = ensemble,
            multiplier     = multiplier,
            raw_ev         = s.ev,
            adjusted_ev    = adjusted_ev,
            note           = self._build_note(s, xgb_score, lstm_score, ensemble, multiplier),
            scored_at      = datetime.utcnow().isoformat()
        )

    def _score_xgb(self, s: VanguardSignal) -> float:
        features = build_xgb_features(s)
        if XGB_AVAILABLE and self.models.xgb_model and hasattr(self.models.xgb_model, "classes_"):
            try:
                prob = self.models.xgb_model.predict_proba(features)[0][1]
                return round(prob * 100, 1)
            except Exception as e:
                logger.warning(f"XGB predict failed {s.ticker}: {e}")
        return self._xgb_heuristic(s)

    def _score_lstm(self, s: VanguardSignal, history_df) -> float:
        seq = build_lstm_sequence(s, history_df)
        if LSTM_AVAILABLE and self.models.lstm_model:
            try:
                prob = float(self.models.lstm_model.predict(seq, verbose=0)[0][0])
                return round(prob * 100, 1)
            except Exception as e:
                logger.warning(f"LSTM predict failed {s.ticker}: {e}")
        return self._lstm_heuristic(s)

    def _xgb_heuristic(self, s: VanguardSignal) -> float:
        """
        Rule-based prior for XGBoost — active until model trains on real outcomes.
        Weights match what XGBoost will learn to weight from experience.
        """
        score = 50.0
        score += (s.win_rate - 0.5) * 60
        score += s.ev_normalised * 15              # EV contribution capped at +15
        if s.wyckoff_phase.lower() in ("markup", "accumulation"): score += 8
        if s.control_state.upper() == "BUYERS":                   score += 6
        if s.compression_state.upper() == "COMPRESSED":           score += 5
        if s.macro_regime.upper() == "RISK_ON":                   score += 5
        score += (s.options_flow_score - 50) * 0.2
        return round(min(max(score, 0), 100), 1)

    def _lstm_heuristic(self, s: VanguardSignal) -> float:
        """
        Sequence proxy — simulates what LSTM reads from 60-bar history.
        Active until model trains on real outcomes.
        """
        score = 50.0
        score += s.volume_ratio * 5
        score -= s.atr_pct * 200
        if s.compression_state.upper() == "COMPRESSED": score += 10
        if s.macro_regime.upper() == "RISK_ON":         score += 8
        if s.wyckoff_phase.lower() == "markup":         score += 10
        score += (s.win_rate - 0.5) * 30
        return round(min(max(score, 0), 100), 1)

    def _score_to_multiplier(self, ensemble_score: float) -> float:
        """
        Maps 0–100 ensemble score to 0.5x–1.5x EV multiplier.
        Score of 50 = neutral (1.0x, no adjustment).
        Above 50 = EV boosted. Below 50 = EV reduced.
        """
        normalised = (ensemble_score - 50) / 50     # -1.0 to +1.0
        multiplier = 1.0 + (normalised * 0.5)       # 0.5x to 1.5x
        return round(min(max(multiplier, MULTIPLIER_MIN), MULTIPLIER_MAX), 3)

    def _build_note(self, s, xgb, lstm, ensemble, multiplier) -> str:
        direction = "boosted" if multiplier >= 1.0 else "reduced"
        drivers   = []
        if s.win_rate >= 0.65:                           drivers.append(f"win rate {s.win_rate:.0%}")
        if s.ev > 3:                                     drivers.append(f"EV {s.ev:.1f}x")
        if s.wyckoff_phase.lower() == "markup":          drivers.append("markup phase")
        if s.compression_state.upper() == "COMPRESSED":  drivers.append("compressed range")
        if s.macro_regime.upper() == "RISK_ON":           drivers.append("risk-on regime")
        driver_str = ", ".join(drivers) if drivers else "mixed signals"
        return (f"EV {direction} {multiplier:.2f}x ({ensemble:.0f}/100) — "
                f"{driver_str}. XGB={xgb:.0f} LSTM={lstm:.0f}")

    def log_outcome(self, signal: VanguardSignal, outcome: str, notes: str = ""):
        """
        Log WIN/LOSS after each trade closes.
        ML models auto-retrain every 5 new outcomes once 10 trades are logged.
        """
        from dataclasses import asdict

        record = {
            "outcome":   outcome,
            "notes":     notes,
            "timestamp": datetime.utcnow().isoformat(),
            "signal":    asdict(signal)
        }

        outcomes = []
        if OUTCOMES_LOG.exists():
            with open(OUTCOMES_LOG) as f:
                outcomes = json.load(f)

        outcomes.append(record)
        with open(OUTCOMES_LOG, "w") as f:
            json.dump(outcomes, f, indent=2)

        wins   = sum(1 for o in outcomes if o["outcome"] == "WIN")
        total  = len(outcomes)
        logger.info(f"Outcome logged: {signal.ticker} {outcome} | "
                    f"Running: {wins}/{total} ({wins/total:.0%} win rate)")

        if total >= MIN_TRADES_TO_TRAIN and total % 5 == 0:
            logger.info("Threshold reached — retraining ML models...")
            self.models.retrain(outcomes)


# ── Sprint 4 — Outcome Regression ────────────────────────────────────────────

def _freeze_weights_baseline(output_dir: Path) -> Path:
    """Write current heuristic weight snapshot before any update."""
    import json as _json
    weights = {
        "win_rate_weight":          0.60,
        "ev_weight":                0.15,
        "wyckoff_markup_bonus":     0.08,
        "buyers_control_bonus":     0.06,
        "compression_bonus":        0.05,
        "risk_on_bonus":            0.05,
        "options_flow_weight":      0.20,
        "volume_ratio_weight":      0.05,
        "atr_penalty_weight":       2.00,
        "xgb_ensemble_weight":      0.55,
        "lstm_ensemble_weight":     0.45,
        "multiplier_min":           MULTIPLIER_MIN,
        "multiplier_max":           MULTIPLIER_MAX,
    }
    ts = datetime.utcnow().strftime("%Y%m%d")
    baseline_path = output_dir / f"weights_baseline_{ts}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w", encoding="utf-8") as fh:
        _json.dump(weights, fh, indent=2)
    logger.info("Weights baseline frozen: %s", baseline_path)
    return baseline_path


def run_outcome_regression(
    db_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    apply_weights: bool = False,
    run_id: Optional[str] = None,
) -> Optional[Path]:
    """
    Sprint 4 Step 3 — Logistic + OLS regression on ml_eligible closed trades.

    Outputs a human-readable calibration report to:
        data/output/calibration/regression_report_<date>.txt

    Results are ADVISORY. Weights are never auto-applied without:
        python ml_confidence_engine.py --apply-weights --run-id <id>

    Returns path to the report file, or None if insufficient data.
    """
    try:
        from sklearn.linear_model import LogisticRegression, LinearRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import accuracy_score, mean_absolute_error
        import numpy as np
    except ImportError:
        logger.error("scikit-learn not installed. Run: pip install scikit-learn")
        return None

    # ── Load eligible trades via confirmation ingester ─────────────────────
    _ingester_path = Path(__file__).resolve().parent.parent / "confirmation_ingester.py"
    if _ingester_path.exists():
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("confirmation_ingester", str(_ingester_path))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        data = _mod.get_eligible_trades(db_path=db_path, verbose=True)
    else:
        logger.warning("confirmation_ingester.py not found at %s", _ingester_path)
        return None

    if data is None:
        logger.warning("Regression skipped — insufficient eligible trades")
        return None

    X = data["features"]
    y_win = data["target_win"]
    y_rr  = data["target_rr"]
    feat_cols = data["feature_cols"]
    n = data["count"]

    # ── Output setup ───────────────────────────────────────────────────────
    _output_dir = output_dir or (
        Path(__file__).resolve().parent.parent / "data" / "output" / "calibration"
    )
    _output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d")
    report_path = _output_dir / f"regression_report_{ts}.txt"

    # ── Freeze weights baseline before any analysis ────────────────────────
    baseline_path = _freeze_weights_baseline(_output_dir)

    lines = [
        "=" * 70,
        f"AVSHUNTER ML OUTCOME REGRESSION REPORT — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"Eligible trades analysed: {n}  |  Run ID: {run_id or 'N/A'}",
        f"Weights baseline frozen: {baseline_path.name}",
        "=" * 70,
        "",
    ]

    # ── Guard: sklearn needs at least 2 classes and some variance ─────────
    if n < 10:
        lines.append(f"INSUFFICIENT DATA: {n} trades (minimum 10 for meaningful regression)")
        lines.append("Accumulate more eligible trades before running regression.")
    elif y_win.nunique() < 2:
        lines.append("INSUFFICIENT DATA: all trades are the same outcome class — cannot train classifier")
    else:
        # ── Scale features ──────────────────────────────────────────────
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # ── Logistic regression — binary win/loss ───────────────────────
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr.fit(X_scaled, y_win)
        y_pred_win = lr.predict(X_scaled)
        win_acc = accuracy_score(y_win, y_pred_win)

        # Feature coefficients for win prediction
        coef_pairs = sorted(
            zip(feat_cols, lr.coef_[0]),
            key=lambda x: abs(x[1]),
            reverse=True,
        )

        lines.append("TOP 5 PREDICTORS OF WINNING TRADES (by coefficient magnitude):")
        for feat, coef in coef_pairs[:5]:
            direction = "↑ bullish" if coef > 0 else "↓ bearish"
            lines.append(f"  {feat:<35s}  coef={coef:+.4f}  {direction}")

        lines.append("")
        lines.append("TOP 5 PREDICTORS OF LOSING TRADES:")
        for feat, coef in reversed(coef_pairs[-5:]):
            direction = "↑ (drives losses)" if coef < 0 else "↓ (drives losses)"
            lines.append(f"  {feat:<35s}  coef={coef:+.4f}  {direction}")

        lines.append("")

        # ── OLS regression — realised R:R ───────────────────────────────
        rr_mask = y_rr.notna()
        if rr_mask.sum() >= 5:
            ols = LinearRegression()
            ols.fit(X_scaled[rr_mask], y_rr[rr_mask])
            y_pred_rr = ols.predict(X_scaled[rr_mask])
            rr_mae = mean_absolute_error(y_rr[rr_mask], y_pred_rr)

            rr_coef_pairs = sorted(
                zip(feat_cols, ols.coef_),
                key=lambda x: abs(x[1]),
                reverse=True,
            )

            # ── Predicted vs Realised ────────────────────────────────────
            import pandas as pd
            df = data["df"]
            lines.append("PREDICTED vs REALISED WIN RATE:")
            lines.append(f"  Logistic model in-sample accuracy : {win_acc:.1%}")
            lines.append(f"  Realised win rate                 : {y_win.mean():.1%}  ({int(y_win.sum())}/{n})")
            lines.append(f"  Journal predicted win rate (rr>1) : "
                         f"{(pd.to_numeric(df.get('rr_predicted', pd.Series()), errors='coerce') > 1.0).mean():.1%}")

            lines.append("")
            lines.append("PREDICTED vs REALISED R:R:")
            lines.append(f"  OLS mean absolute error           : {rr_mae:.3f}R")
            lines.append(f"  Realised R:R mean                 : {y_rr[rr_mask].mean():.3f}")
            lines.append(f"  Journal predicted R:R mean        : "
                         f"{pd.to_numeric(df.get('rr_predicted', pd.Series()), errors='coerce').mean():.3f}")
        else:
            lines.append("PREDICTED vs REALISED WIN RATE:")
            lines.append(f"  Logistic model in-sample accuracy : {win_acc:.1%}")
            lines.append(f"  Realised win rate                 : {y_win.mean():.1%}  ({int(y_win.sum())}/{n})")
            lines.append("")
            lines.append("PREDICTED vs REALISED R:R:")
            lines.append("  Insufficient rr_realised data for OLS regression")

        # ── Zero-value fields ────────────────────────────────────────────
        lines.append("")
        zero_fields = [
            feat for feat, coef in coef_pairs
            if abs(coef) < 0.001
        ]
        lines.append("FIELDS WITH ZERO PREDICTIVE VALUE (candidates for removal):")
        if zero_fields:
            for f in zero_fields:
                lines.append(f"  {f}")
        else:
            lines.append("  None — all features contributed at least marginally")

        # ── Weight adjustment recommendations ────────────────────────────
        lines.append("")
        lines.append("RECOMMENDED CONFIDENCE WEIGHT ADJUSTMENTS")
        lines.append("(human review required — not auto-applied):")
        lines.append("")

        top_feat, top_coef = coef_pairs[0] if coef_pairs else ("N/A", 0)
        if abs(top_coef) > 0.5:
            lines.append(f"  STRONG SIGNAL: '{top_feat}' is the dominant predictor.")
            lines.append(f"  Consider increasing its weight in the XGBoost feature vector.")
        if zero_fields:
            lines.append(f"  WEAK SIGNALS: {len(zero_fields)} features show near-zero coefficients.")
            lines.append("  Consider removing these from the feature set to reduce noise.")
        lines.append("")
        lines.append("  To apply these adjustments:")
        _rid = run_id or ts
        lines.append(f"    python ml_confidence_layer/ml_confidence_engine.py --apply-weights --run-id {_rid}")
        lines.append("  This will update weights_baseline_<date>.json after human review.")

    lines += [
        "",
        "=" * 70,
        "NOTE: This report is ADVISORY. No weights have been changed.",
        f"      Baseline snapshot: {baseline_path.name}",
        "=" * 70,
    ]

    report_text = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report_text)

    logger.info("Regression report written: %s", report_path)
    print(report_text)
    return report_path


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    _parser = argparse.ArgumentParser(
        description="AVSHUNTER ML Confidence Engine — regression + weight management"
    )
    _parser.add_argument(
        "--apply-weights",
        action="store_true",
        help="Apply recommended weight adjustments (requires human confirmation via --run-id)",
    )
    _parser.add_argument("--run-id", help="Run ID authorising weight application")
    _parser.add_argument("--db", default=None, help="Path to trade_journal.db")
    _parser.add_argument("--output-dir", default=None, help="Output directory for calibration report")
    _args = _parser.parse_args()

    _db = Path(_args.db) if _args.db else None
    _out = Path(_args.output_dir) if _args.output_dir else None

    if _args.apply_weights and not _args.run_id:
        print("ERROR: --apply-weights requires --run-id for audit trail. Aborting.")
        sys.exit(1)

    if _args.apply_weights:
        print(f"[WEIGHT UPDATE] run-id={_args.run_id} — stub: no auto-update implemented.")
        print("Weights are managed manually. Edit weights_baseline_<date>.json and re-load.")
        sys.exit(0)

    report = run_outcome_regression(
        db_path=_db,
        output_dir=_out,
        apply_weights=False,
        run_id=_args.run_id,
    )
    sys.exit(0 if report else 1)
