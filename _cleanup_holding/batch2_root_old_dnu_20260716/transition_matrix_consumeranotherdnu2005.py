"""
transition_matrix_consumer.py
==============================
AVSHUNTER — Transition Matrix Consumer v1.0.0

Loads the pre-built stratified transition matrices and exposes a query
interface consumed by kelly_sizer.py and morning_thesis_validator.py.

Integration points
------------------
  kelly_sizer.py (size_batch):
      trf = tmc.get_transition_risk_factor(phase, regime, tier)
      regime_multiplier_adjusted = regime_multiplier * (1.0 - trf)

  morning_thesis_validator.py (validate_candidate):
      trf_result = tmc.get_transition_risk_factor(phase, regime, tier)
      validation_score_adjusted = score * (1.0 - trf_result["trf"])
      row["trf_phase_risk"] = trf_result["trf"]
      row["trf_source"]     = trf_result["trf_source"]
      row["trf_sparse"]     = trf_result["sparse"]

Fallback hierarchy (most → least specific)
------------------------------------------
  1. regime × tier   e.g. regime_RISK_ON_tier_MID
  2. regime only     e.g. regime_RISK_ON
  3. tier only       e.g. tier_MID
  4. global
  5. neutral trf=0.0 (if matrix missing or phase not found)

Sparse cell handling
--------------------
  EARLY_TRANSITION in EXTREME/HIGH tier has near-zero observations.
  Consumer falls back one level rather than trusting a noisy probability.

Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger("avshunter.transition_matrix_consumer")

# ---------------------------------------------------------------------------
# Default path — matches orchestrator cfg line 376 + alias written by builder
# ---------------------------------------------------------------------------
_DEFAULT_MATRIX_PATH = Path(
    r"C:\Users\ACKVerissimo\vanguard\data\transition_matrix"
    r"\transition_matrix_consolidated_latest.csv"
)

# Sparse cells confirmed from the 20260520 build run.
# Key: (phase, regime, tier) — ALL means "not stratified at this dimension"
_KNOWN_SPARSE: set[tuple[str, str, str]] = {
    ("EARLY_TRANSITION", "ALL",          "EXTREME"),
    ("EARLY_TRANSITION", "ALL",          "HIGH"),
    ("EARLY_TRANSITION", "RISK_OFF",     "EXTREME"),
    ("EARLY_TRANSITION", "RISK_OFF",     "HIGH"),
    ("EARLY_TRANSITION", "RISK_ON",      "EXTREME"),
    ("EARLY_TRANSITION", "RISK_ON",      "HIGH"),
    ("EARLY_TRANSITION", "TRANSITIONAL", "EXTREME"),
    ("EARLY_TRANSITION", "TRANSITIONAL", "HIGH"),
}

# Neutral result returned when matrix unavailable or no match found
_NEUTRAL = {
    "trf": 0.0,
    "trf_source": "NEUTRAL_FALLBACK",
    "sparse": False,
    "phase": "",
    "regime": "",
    "tier": "",
}


class TransitionMatrixConsumer:
    """
    Read-only runtime consumer for the pre-built transition matrices.

    Usage
    -----
        tmc = TransitionMatrixConsumer()
        result = tmc.get_transition_risk_factor(
            phase="CONTINUATION",
            regime="RISK_ON",
            tier="MID",
        )
        # result = {"trf": 0.12, "trf_source": "regime_RISK_ON_tier_MID", "sparse": False, ...}

        # Apply to Kelly sizing:
        adj_multiplier = regime_multiplier * (1.0 - result["trf"])

        # Apply to morning validation score:
        adj_score = validation_score * (1.0 - result["trf"])
    """

    def __init__(self, matrix_path: Optional[Path] = None):
        self._path = Path(matrix_path) if matrix_path else _DEFAULT_MATRIX_PATH
        self._df: Optional[pd.DataFrame] = None
        self._loaded = False
        self._load()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            log.warning(
                "[TMC] Matrix file not found: %s — all lookups will return neutral trf=0.0",
                self._path,
            )
            self._loaded = False
            return
        try:
            df = pd.read_csv(self._path, dtype=str)
            # Normalise all string columns
            for col in ["phase_current", "phase_next", "regime", "tier", "stratification"]:
                if col in df.columns:
                    df[col] = df[col].fillna("").str.strip().str.upper()
            # Numeric columns
            for col in ["transition_risk_factor", "transition_probability", "transition_count"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            if "sparse" in df.columns:
                df["sparse"] = df["sparse"].str.upper().isin({"TRUE", "1", "YES"})
            self._df = df
            self._loaded = True
            log.info("[TMC] Loaded %d rows from %s", len(df), self._path)
        except Exception as exc:
            log.warning("[TMC] Failed to load matrix: %s — neutral fallback active", exc)
            self._loaded = False

    def reload(self) -> None:
        """Force reload from disk — call after a new matrix build."""
        self._load()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ── Core lookup ───────────────────────────────────────────────────────────

    def get_transition_risk_factor(
        self,
        phase: str,
        regime: str = "ALL",
        tier: str = "ALL",
    ) -> dict:
        """
        Return transition_risk_factor for the given phase/regime/tier combination.

        Parameters
        ----------
        phase  : current phase label e.g. "CONTINUATION", "EXHAUSTION", "EARLY_TRANSITION"
        regime : macro regime label e.g. "RISK_ON", "RISK_OFF", "TRANSITIONAL"
        tier   : momentum tier e.g. "MID", "LOW", "HIGH", "EXTREME"

        Returns
        -------
        dict with keys:
            trf        : float in [0.0, 1.0] — 0.0 = no risk adjustment, 1.0 = full block
            trf_source : str — which stratification level was used
            sparse     : bool — True if cell had < 30 observations
            phase      : str — normalised phase used
            regime     : str — normalised regime used
            tier       : str — normalised tier used
        """
        if not self._loaded or self._df is None:
            return dict(_NEUTRAL, phase=phase, regime=regime, tier=tier)

        p = str(phase).strip().upper()
        r = str(regime).strip().upper()
        t = str(tier).strip().upper()

        # Sparse check — fall back one level before lookup
        def _is_sparse(ph: str, re: str, ti: str) -> bool:
            return (ph, re, ti) in _KNOWN_SPARSE

        # Try fallback levels in order
        candidates = [
            (f"regime_{r}_tier_{t}", r, t),
            (f"regime_{r}",          r, "ALL"),
            (f"tier_{t}",            "ALL", t),
            ("global",               "ALL", "ALL"),
        ]

        df = self._df
        for strat_label, r_used, t_used in candidates:
            # Skip if this combination is known sparse — try next level
            if _is_sparse(p, r_used, t_used):
                log.debug("[TMC] Sparse cell skipped: phase=%s regime=%s tier=%s", p, r_used, t_used)
                continue

            mask = (
                (df["stratification"] == strat_label.upper()) &
                (df["phase_current"] == p)
            )
            subset = df[mask]
            if subset.empty:
                continue

            # trf is the same for all rows with this phase_current in this stratification
            # (it's derived per phase_current, not per phase_next)
            trf_val = float(subset["transition_risk_factor"].iloc[0])
            sparse_val = bool(subset["sparse"].iloc[0]) if "sparse" in subset.columns else False

            return {
                "trf": round(trf_val, 6),
                "trf_source": strat_label,
                "sparse": sparse_val,
                "phase": p,
                "regime": r_used,
                "tier": t_used,
            }

        # Nothing matched — neutral
        log.debug("[TMC] No match for phase=%s regime=%s tier=%s — neutral", p, r, t)
        return dict(_NEUTRAL, phase=p, regime=r, tier=t)

    # ── Kelly integration helper ──────────────────────────────────────────────

    def adjust_kelly_multiplier(
        self,
        regime_multiplier: float,
        phase: str,
        regime: str = "ALL",
        tier: str = "ALL",
    ) -> dict:
        """
        Adjust an existing regime_multiplier by the transition risk factor.

        Kelly_adjusted = Kelly_base × regime_multiplier × (1 - trf)

        In practice: pass this result's `adjusted_multiplier` as
        `regime_multiplier` to KellySizer.size_trade().

        Returns
        -------
        dict with:
            adjusted_multiplier : float — regime_multiplier × (1 - trf)
            trf                 : float
            trf_source          : str
            sparse              : bool
        """
        result = self.get_transition_risk_factor(phase, regime, tier)
        trf = result["trf"]
        adjusted = round(regime_multiplier * (1.0 - trf), 6)
        return {
            "adjusted_multiplier": adjusted,
            "original_multiplier": regime_multiplier,
            "trf": trf,
            "trf_source": result["trf_source"],
            "sparse": result["sparse"],
        }

    # ── Morning validator score helper ────────────────────────────────────────

    def adjust_validation_score(
        self,
        score: float,
        phase: str,
        regime: str = "ALL",
        tier: str = "ALL",
    ) -> dict:
        """
        Adjust a morning validation score by the transition risk factor.

        score_adjusted = score × (1 - trf)

        Returns
        -------
        dict with:
            score_adjusted : float
            score_original : float
            trf            : float
            trf_source     : str
            sparse         : bool
        """
        result = self.get_transition_risk_factor(phase, regime, tier)
        trf = result["trf"]
        adjusted = round(score * (1.0 - trf), 4)
        return {
            "score_adjusted": adjusted,
            "score_original": score,
            "trf": trf,
            "trf_source": result["trf_source"],
            "sparse": result["sparse"],
        }

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return metadata about the loaded matrix."""
        if not self._loaded or self._df is None:
            return {"loaded": False, "path": str(self._path)}
        df = self._df
        return {
            "loaded": True,
            "path": str(self._path),
            "total_rows": len(df),
            "stratification_levels": sorted(df["stratification"].unique().tolist()) if "stratification" in df.columns else [],
            "phase_states": sorted(df["phase_current"].unique().tolist()) if "phase_current" in df.columns else [],
            "regime_states": sorted(df["regime"].unique().tolist()) if "regime" in df.columns else [],
            "tier_states": sorted(df["tier"].unique().tolist()) if "tier" in df.columns else [],
        }


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly
# ---------------------------------------------------------------------------
# Lazy-initialised on first use so import doesn't fail if matrix not yet built.

_singleton: Optional[TransitionMatrixConsumer] = None


def get_consumer(matrix_path: Optional[Path] = None) -> TransitionMatrixConsumer:
    """
    Return the module-level singleton consumer.
    Pass matrix_path on first call to override the default path.
    """
    global _singleton
    if _singleton is None:
        _singleton = TransitionMatrixConsumer(matrix_path)
    return _singleton


# ---------------------------------------------------------------------------
# CLI — smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    tmc = TransitionMatrixConsumer()
    print("\n[SUMMARY]")
    print(json.dumps(tmc.summary(), indent=2))

    print("\n[SAMPLE LOOKUPS]")
    test_cases = [
        ("CONTINUATION",    "RISK_ON",      "MID"),
        ("EXHAUSTION",      "RISK_OFF",     "LOW"),
        ("EARLY_TRANSITION","RISK_ON",      "HIGH"),   # sparse — should fall back
        ("CONTINUATION",    "TRANSITIONAL", "EXTREME"),
        ("EXHAUSTION",      "RISK_ON",      "MID"),
        ("UNKNOWN_PHASE",   "RISK_ON",      "MID"),    # no match — neutral
    ]

    for phase, regime, tier in test_cases:
        r = tmc.get_transition_risk_factor(phase, regime, tier)
        print(
            f"  phase={phase:<20} regime={regime:<14} tier={tier:<8} "
            f"→ trf={r['trf']:.4f}  source={r['trf_source']}  sparse={r['sparse']}"
        )

    print("\n[KELLY ADJUSTMENT EXAMPLE]")
    kelly_result = tmc.adjust_kelly_multiplier(
        regime_multiplier=1.0,
        phase="EXHAUSTION",
        regime="RISK_OFF",
        tier="LOW",
    )
    print(json.dumps(kelly_result, indent=2))

    print("\n[SCORE ADJUSTMENT EXAMPLE]")
    score_result = tmc.adjust_validation_score(
        score=72.0,
        phase="CONTINUATION",
        regime="RISK_ON",
        tier="MID",
    )
    print(json.dumps(score_result, indent=2))
