"""
AVSHUNTER ML Confidence Layer
==============================
XGBoost + LSTM Ensemble — Post-VANGUARD Position Sizing Intelligence

Placement in pipeline:
  VANGUARD TRADE verdict
        ↓
  [THIS MODULE] XGBoost + LSTM Confidence Scoring
        ↓
  Final Output: Verdict + ML Score + Adjusted Position Size ($200 base)

Install: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\ml_confidence_layer\\
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

# ── Optional heavy imports (graceful fallback if not installed) ───────────────
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

# ── Config ────────────────────────────────────────────────────────────────────
BASE_CAPITAL        = 200.0   # $200 test account
RISK_PCT_PER_TRADE  = 0.05    # 5% = $10 max risk per trade
SEQUENCE_LENGTH     = 60      # LSTM lookback bars
MODEL_DIR           = Path(__file__).parent / "models"
OUTCOMES_LOG        = Path(__file__).parent / "trade_outcomes.json"
MIN_TRADES_TO_TRAIN = 10      # real trades needed before ML self-trains

XGB_WEIGHT  = 0.55
LSTM_WEIGHT = 0.45

# ML confidence → position size multiplier
CONFIDENCE_TIERS = [
    (85, 1.50),   # HIGH        ≥85%  → 1.5x size  ($15 risk)
    (70, 1.00),   # STANDARD    ≥70%  → 1.0x size  ($10 risk)
    (55, 0.75),   # MODERATE    ≥55%  → 0.75x size ($7.50 risk)
    (40, 0.50),   # CAUTIOUS    ≥40%  → 0.50x size ($5 risk)
    (0,  0.25),   # MINIMAL     <40%  → 0.25x size ($2.50 risk)
]

TIER_LABELS = {1.50: "HIGH", 1.00: "STANDARD", 0.75: "MODERATE", 0.50: "CAUTIOUS", 0.25: "MINIMAL"}

# ── Encoding maps ─────────────────────────────────────────────────────────────
PHASE_MAP    = {"accumulation": 3, "markup": 4, "distribution": 1, "markdown": 0, "unknown": 2}
CONTROL_MAP  = {"BUYERS": 2, "NEUTRAL": 1, "SELLERS": 0}
COMPRESS_MAP = {"COMPRESSED": 2, "NORMAL": 1, "EXPANDED": 0}
REGIME_MAP   = {"RISK_ON": 2, "NEUTRAL": 1, "RISK_OFF": 0}


# ── Data Classes ──────────────────────────────────────────────────────────────
@dataclass
class VanguardInput:
    """VANGUARD TRADE verdict fields consumed by ML layer"""
    ticker:             str
    verdict:            str    # TRADE / DISCOVER / OBSERVE / REJECT
    win_rate:           float  # 0.0–1.0
    expected_value:     float  # EV multiplier
    wyckoff_phase:      str    # accumulation / markup / distribution / markdown
    control_state:      str    # BUYERS / SELLERS / NEUTRAL
    compression_state:  str    # COMPRESSED / NORMAL / EXPANDED
    macro_regime:       str    # RISK_ON / RISK_OFF / NEUTRAL
    options_flow_score: float  # 0–100
    price:              float
    volume_ratio:       float  # today vol / 20d avg
    atr_pct:            float  # ATR as % of price
    timestamp:          str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class MLConfidenceResult:
    """Output returned for every scored TRADE verdict"""
    ticker:             str
    verdict:            str
    xgb_score:          float   # 0–100
    lstm_score:         float   # 0–100
    ensemble_score:     float   # 0–100  ← primary confidence metric
    confidence_tier:    str     # HIGH / STANDARD / MODERATE / CAUTIOUS / MINIMAL
    size_multiplier:    float
    base_risk_usd:      float   # $10 (5% of $200)
    adjusted_risk_usd:  float   # base_risk × multiplier
    max_contracts:      int     # floor(adjusted_risk / option_premium_proxy)
    ml_note:            str
    timestamp:          str


# ── Feature Engineering ───────────────────────────────────────────────────────
def build_xgb_features(v: VanguardInput) -> np.ndarray:
    """12-feature vector for XGBoost"""
    return np.array([
        v.win_rate,
        v.expected_value,
        PHASE_MAP.get(v.wyckoff_phase.lower(), 2),
        CONTROL_MAP.get(v.control_state.upper(), 1),
        COMPRESS_MAP.get(v.compression_state.upper(), 1),
        REGIME_MAP.get(v.macro_regime.upper(), 1),
        v.options_flow_score / 100.0,
        v.volume_ratio,
        v.atr_pct,
        min(v.price, 500) / 500.0,
        1.0 if v.compression_state.upper() == "COMPRESSED" else 0.0,
        1.0 if v.macro_regime.upper() == "RISK_ON" else 0.0,
    ], dtype=np.float32).reshape(1, -1)


def build_lstm_sequence(v: VanguardInput,
                        history_df: Optional[pd.DataFrame] = None) -> np.ndarray:
    """
    60-bar × 5-feature sequence for LSTM.
    Uses real OHLCV history if supplied; otherwise synthesises from signal state.
    """
    if history_df is not None and len(history_df) >= SEQUENCE_LENGTH:
        cols = [c for c in ["close", "volume", "atr", "vwap_dev", "options_flow"]
                if c in history_df.columns]
        arr = history_df[cols].values[-SEQUENCE_LENGTH:].astype(np.float32)
        col_range = arr.max(axis=0) - arr.min(axis=0)
        col_range[col_range == 0] = 1
        arr = (arr - arr.min(axis=0)) / col_range
        # pad to 5 features if fewer columns available
        if arr.shape[1] < 5:
            pad = np.zeros((SEQUENCE_LENGTH, 5 - arr.shape[1]), dtype=np.float32)
            arr = np.concatenate([arr, pad], axis=1)
        return arr.reshape(1, SEQUENCE_LENGTH, 5)

    # Synthetic prior — directional from current state
    base_trend = 0.5 + (v.win_rate - 0.5) * 0.4
    noise = np.random.normal(0, 0.03, (SEQUENCE_LENGTH, 5)).astype(np.float32)
    template = np.array([
        base_trend,
        min(v.volume_ratio / 3.0, 1.0),
        min(v.atr_pct * 10, 1.0),
        0.5 + (v.options_flow_score - 50) / 100.0,
        REGIME_MAP.get(v.macro_regime.upper(), 1) / 2.0
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
                logger.info("XGBoost model loaded from disk")
            else:
                self.xgb_model = self._build_xgb()
                logger.info("XGBoost initialised — using heuristic priors until trained")

        if LSTM_AVAILABLE:
            if lstm_path.exists():
                self.lstm_model = load_model(str(lstm_path))
                logger.info("LSTM model loaded from disk")
            else:
                self.lstm_model = self._build_lstm()
                logger.info("LSTM initialised — using heuristic priors until trained")

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
        if len(outcomes) < MIN_TRADES_TO_TRAIN:
            logger.info(f"Need {MIN_TRADES_TO_TRAIN} outcomes to retrain — have {len(outcomes)}")
            return

        X_xgb, X_lstm, y = [], [], []
        for o in outcomes:
            try:
                v = VanguardInput(**o["input"])
                X_xgb.append(build_xgb_features(v)[0])
                X_lstm.append(build_lstm_sequence(v)[0])
                y.append(1 if o["outcome"] == "WIN" else 0)
            except Exception as e:
                logger.warning(f"Skipping malformed outcome record: {e}")

        if len(y) < MIN_TRADES_TO_TRAIN:
            return

        X_xgb  = np.array(X_xgb,  dtype=np.float32)
        X_lstm = np.array(X_lstm, dtype=np.float32)
        y      = np.array(y,      dtype=np.int32)

        if XGB_AVAILABLE and self.xgb_model:
            self.xgb_model.fit(X_xgb, y)
            self.xgb_model.save_model(str(MODEL_DIR / "xgb_model.json"))
            logger.info(f"XGBoost retrained on {len(y)} trades")

        if LSTM_AVAILABLE and self.lstm_model:
            self.lstm_model.fit(X_lstm, y, epochs=20, batch_size=8, verbose=0)
            self.lstm_model.save(str(MODEL_DIR / "lstm_model.keras"))
            logger.info(f"LSTM retrained on {len(y)} trades")


# ── Main Scoring Engine ───────────────────────────────────────────────────────
class MLConfidenceEngine:
    """
    Primary entry point.
    Call score(vanguard_input) on every VANGUARD TRADE verdict.
    Call log_outcome() when each trade closes.
    """

    def __init__(self):
        self.models = ModelManager()

    def score(self, v: VanguardInput,
              history_df: Optional[pd.DataFrame] = None) -> MLConfidenceResult:
        """Score a single VANGUARD verdict. Only TRADE verdicts get full scoring."""

        if v.verdict != "TRADE":
            return self._passthrough(v)

        xgb_score  = self._score_xgb(v)
        lstm_score = self._score_lstm(v, history_df)
        ensemble   = round(XGB_WEIGHT * xgb_score + LSTM_WEIGHT * lstm_score, 1)

        tier, multiplier = self._get_tier(ensemble)
        base_risk        = BASE_CAPITAL * RISK_PCT_PER_TRADE
        adjusted_risk    = round(base_risk * multiplier, 2)

        # Options contract sizing proxy — assume avg premium $0.50–$2.00 per contract * 100 shares
        avg_premium_proxy = max(v.price * 0.02, 50)   # 2% of stock price × 100, min $50
        max_contracts     = max(1, int(adjusted_risk / avg_premium_proxy * 100))

        return MLConfidenceResult(
            ticker            = v.ticker,
            verdict           = v.verdict,
            xgb_score         = xgb_score,
            lstm_score        = lstm_score,
            ensemble_score    = ensemble,
            confidence_tier   = tier,
            size_multiplier   = multiplier,
            base_risk_usd     = base_risk,
            adjusted_risk_usd = adjusted_risk,
            max_contracts     = max_contracts,
            ml_note           = self._build_note(v, xgb_score, lstm_score, ensemble, tier),
            timestamp         = datetime.utcnow().isoformat()
        )

    def _score_xgb(self, v: VanguardInput) -> float:
        features = build_xgb_features(v)
        if XGB_AVAILABLE and self.models.xgb_model and hasattr(self.models.xgb_model, "classes_"):
            try:
                prob = self.models.xgb_model.predict_proba(features)[0][1]
                return round(prob * 100, 1)
            except Exception as e:
                logger.warning(f"XGB predict failed for {v.ticker}: {e}")
        return self._xgb_heuristic(v)

    def _score_lstm(self, v: VanguardInput, history_df) -> float:
        seq = build_lstm_sequence(v, history_df)
        if LSTM_AVAILABLE and self.models.lstm_model:
            try:
                prob = float(self.models.lstm_model.predict(seq, verbose=0)[0][0])
                return round(prob * 100, 1)
            except Exception as e:
                logger.warning(f"LSTM predict failed for {v.ticker}: {e}")
        return self._lstm_heuristic(v)

    def _xgb_heuristic(self, v: VanguardInput) -> float:
        """Rule-based XGBoost proxy — active until model trains on real outcomes"""
        s = 50.0
        s += (v.win_rate - 0.5) * 60
        s += min(v.expected_value * 3, 15)
        if v.wyckoff_phase.lower() in ("markup", "accumulation"): s += 8
        if v.control_state.upper() == "BUYERS":                   s += 6
        if v.compression_state.upper() == "COMPRESSED":           s += 5
        if v.macro_regime.upper() == "RISK_ON":                   s += 5
        s += (v.options_flow_score - 50) * 0.2
        return round(min(max(s, 0), 100), 1)

    def _lstm_heuristic(self, v: VanguardInput) -> float:
        """Sequence proxy — active until model trains on real outcomes"""
        s = 50.0
        s += v.volume_ratio * 5
        s -= v.atr_pct * 200
        if v.compression_state.upper() == "COMPRESSED": s += 10
        if v.macro_regime.upper() == "RISK_ON":         s += 8
        if v.wyckoff_phase.lower() == "markup":         s += 10
        s += (v.win_rate - 0.5) * 30
        return round(min(max(s, 0), 100), 1)

    def _get_tier(self, score: float):
        for threshold, multiplier in CONFIDENCE_TIERS:
            if score >= threshold:
                return TIER_LABELS[multiplier], multiplier
        return "MINIMAL", 0.25

    def _passthrough(self, v: VanguardInput) -> MLConfidenceResult:
        return MLConfidenceResult(
            ticker=v.ticker, verdict=v.verdict,
            xgb_score=0, lstm_score=0, ensemble_score=0,
            confidence_tier="N/A", size_multiplier=0,
            base_risk_usd=0, adjusted_risk_usd=0, max_contracts=0,
            ml_note=f"Verdict {v.verdict} — ML scoring inactive",
            timestamp=datetime.utcnow().isoformat()
        )

    def _build_note(self, v, xgb, lstm, ensemble, tier) -> str:
        drivers = []
        if v.win_rate >= 0.65:                                drivers.append(f"win rate {v.win_rate:.0%}")
        if v.expected_value > 3:                              drivers.append(f"EV {v.expected_value:.1f}x")
        if v.wyckoff_phase.lower() == "markup":               drivers.append("markup phase confirmed")
        if v.compression_state.upper() == "COMPRESSED":      drivers.append("compressed range")
        if v.macro_regime.upper() == "RISK_ON":               drivers.append("risk-on regime")
        if v.options_flow_score > 70:                         drivers.append(f"strong options flow {v.options_flow_score:.0f}")
        driver_str = ", ".join(drivers) if drivers else "mixed signals"
        return (f"{tier} conviction ({ensemble:.0f}/100) — {driver_str}. "
                f"XGB={xgb:.0f} LSTM={lstm:.0f}")

    def log_outcome(self, ticker: str, vanguard_input: VanguardInput,
                    outcome: str, pnl_usd: float,
                    exit_price: float, notes: str = ""):
        """
        CALL THIS AFTER EVERY TRADE CLOSES.
        outcome = 'WIN' or 'LOSS'
        Auto-retrains XGBoost + LSTM every 5 new outcomes after threshold reached.
        """
        record = {
            "ticker":      ticker,
            "outcome":     outcome,
            "pnl_usd":     pnl_usd,
            "exit_price":  exit_price,
            "notes":       notes,
            "timestamp":   datetime.utcnow().isoformat(),
            "input":       asdict(vanguard_input)
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
        win_rt = wins / total if total > 0 else 0
        logger.info(f"Outcome logged: {ticker} {outcome} ${pnl_usd:+.2f} | "
                    f"Running: {wins}/{total} ({win_rt:.0%} win rate)")

        # Auto-retrain every 5 new trades once threshold met
        if total >= MIN_TRADES_TO_TRAIN and total % 5 == 0:
            logger.info("Auto-retraining ML models on latest outcomes...")
            self.models.retrain(outcomes)
