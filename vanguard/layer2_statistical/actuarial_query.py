"""
SIMPLIFIED Actuarial Query Engine
Matches state vectors to historical outcomes using Polygon database columns

UPDATED: Multi-horizon outcomes (5d, 10d, 20d) now computed and returned.
         Options layer uses win_rate_for_hold(hold_days) for accurate EV.
         All existing fields preserved -- fully backward compatible.
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..config import ACTUARIAL_DATABASE_PATH


MATCH_EXACT_DIMS = [
    # Core 6 — always present, always populated in StateVector
    "vol_regime",
    "trend_direction",
    "structure_quality",
    "phase_v2",
    "momentum_bucket",
    "location_bucket",
    # Extended 3 — present in DB v6 after 9-dim enrichment (2026-05-20)
    # Missing from StateVector fall back gracefully via _available_match_dims().
    "wyckoff_phase_bucket",
    "trend_maturity",
    "iv_regime",
    # crabel_state — present in DB; computed from vol/adx proxy in state_calculator
    "crabel_state",
]
MATCH_RELAXED_DIMS = [
    "vol_regime",
    "trend_direction",
    "structure_quality",
    "wyckoff_phase_bucket",
]
MATCH_SIMILARITY_WEIGHTS = {
    "vol_regime":          0.20,
    "trend_direction":     0.18,
    "structure_quality":   0.15,
    "phase_v2":            0.12,
    "momentum_bucket":     0.10,
    "location_bucket":     0.08,
    "wyckoff_phase_bucket": 0.08,
    "trend_maturity":      0.05,
    "iv_regime":           0.04,
}
ANALOGUE_MIN_SIMILARITY = 0.70
ANALOGUE_MIN_SAMPLES = 100

ACTUARIAL_QUERY_COLUMNS = [
    # Core match dimensions
    "vol_regime",
    "trend_direction",
    "structure_quality",
    "phase_v2",
    "momentum_bucket",
    "location_bucket",
    # Extended 9-dim match dimensions (added 2026-05-20)
    "wyckoff_phase_bucket",
    "trend_maturity",
    "iv_regime",
    "crabel_state",
    "horizon_bucket",
    # Structural/bucket discriminators retained for compatibility
    "catalyst_proximity",
    "atr_pct_bucket",
    "adx_bucket",
    "macro_regime",
    # Multi-horizon outcomes and calibration inputs.
    "outcome_5d_return",
    "outcome_10d_return",
    "outcome_20d_return",
    "outcome_max_drawdown_5d",
    "outcome_max_drawdown_10d",
    "outcome_max_drawdown_20d",
    "outcome_hit_5pct_up_5d",
    "outcome_hit_7pct_up_10d",
    "outcome_hit_10pct_up",
    "outcome_hit_5pct_down_before_10up",
    "outcome_days_to_10pct",
    "outcome_category",
    # v6 forward-state diagnostics.
    "future_momentum_bucket",
    "transition_flag_v2",
    "momentum_delta",
    "atr_delta",
    "adx_delta",
    "early_candidate",
]

ACTUARIAL_CATEGORY_COLUMNS = [
    "vol_regime",
    "trend_direction",
    "structure_quality",
    "phase_v2",
    "momentum_bucket",
    "location_bucket",
    "wyckoff_phase_bucket",
    "trend_maturity",
    "iv_regime",
    "crabel_state",
    "horizon_bucket",
    "catalyst_proximity",
    "atr_pct_bucket",
    "adx_bucket",
    "macro_regime",
    "outcome_category",
    "future_momentum_bucket",
]

SAMPLE_CONFIDENCE_THRESHOLDS = {
    "1_5D":  {"HIGH": 100, "MEDIUM_HIGH": 50,  "MEDIUM": 30, "LOW": 10},
    "6_10D": {"HIGH": 120, "MEDIUM_HIGH": 60,  "MEDIUM": 30, "LOW": 10},
    "11_20D": {"HIGH": 150, "MEDIUM_HIGH": 75, "MEDIUM": 40, "LOW": 15},
    "1_3M":  {"HIGH": 200, "MEDIUM_HIGH": 100, "MEDIUM": 50, "LOW": 20},
}

CONFIDENCE_WEIGHTS = {
    "EXACT": {
        "HIGH": 1.00,
        "MEDIUM_HIGH": 0.90,
        "MEDIUM": 0.80,
        "LOW": 0.65,
        "THIN": 0.50,
        "UNKNOWN": 0.30,
    },
    "RELAXED": {
        "HIGH": 0.85,
        "MEDIUM_HIGH": 0.75,
        "MEDIUM": 0.65,
        "LOW": 0.50,
        "THIN": 0.40,
        "UNKNOWN": 0.30,
    },
}


def _empty_outcomes(match_attrs: Optional[dict] = None) -> ActuarialOutcomes:
    """Return a safe, fail-closed ActuarialOutcomes - NEVER returns None.
    Match-method fields default to UNKNOWN so audit logs are unambiguous.
    This path means the match ladder could not validate a historical sample.
    """
    out = ActuarialOutcomes(
        n_observations=0,
        confidence_level=0.0,
        lookback_period="N/A",
        prob_up_10pct_20d=0.0,
        prob_down_5pct_before_up_10pct=0.0,
        prob_trend_continues_20d=0.0,
        median_gain_if_up=0.0,
        median_loss_if_down=0.0,
        median_max_drawdown=0.0,
        median_days_to_target=0.0,
        expected_value_20d=0.0,
        sharpe_ratio=0.0,
        win_rate=0.0,
        avg_win_loss_ratio=0.0,
        kelly_fraction=0.0,
        recommended_hold_days=0,
        outcome_distribution={},
        insufficient_data_reason="No actuarial data available"
    )
    attrs = match_attrs or {}
    out.state_match_method     = attrs.get("state_match_method", "UNKNOWN")
    out.state_match_stage      = attrs.get("state_match_stage", "UNKNOWN")
    out.state_match_dimensions = attrs.get("state_match_dimensions", "")
    out.state_match_quality    = attrs.get("state_match_quality", "INSUFFICIENT_SAMPLE")
    out.state_match_similarity = float(attrs.get("state_match_similarity", 0.0) or 0.0)
    out.state_match_is_exact   = bool(attrs.get("state_match_is_exact", False))
    out.sample_size            = int(attrs.get("sample_size", 0) or 0)
    out.sample_confidence_bucket = attrs.get("sample_confidence_bucket", "UNKNOWN")
    out.confidence_penalty     = float(attrs.get("confidence_penalty", 0.30) or 0.30)
    out.confidence_weight      = float(attrs.get("confidence_weight", out.confidence_penalty) or out.confidence_penalty)
    out.matched_state_key      = attrs.get("matched_state_key", "")
    out.original_state_key     = attrs.get("original_state_key", "")
    out.fallback_reason        = attrs.get("fallback_reason", "No actuarial data available")
    return out


class ActuarialQueryEngine:
    """
    Query historical database for state-specific probabilities.
    SIMPLIFIED VERSION - works with Polygon-built database.
    FIXED: query() NEVER returns None.
    UPDATED: Returns multi-horizon outcomes (5d, 10d, 20d).
    """

    def __init__(self, database_path: str = None):
        # DEFECT 5 FIX: Explicit path resolution with version validation.
        # Priority: caller-supplied path > ACTUARIAL_DATABASE_PATH from config.
        # Logs which DB file is loaded so audit trail is unambiguous.
        _raw_path = database_path or ACTUARIAL_DATABASE_PATH
        _db_obj   = Path(str(_raw_path))

        # -- D5 FIX: v6 auto-upgrade ------------------------------------------
        # If the configured path points to v5 (or any non-v6 version) and a v6
        # file exists in the same directory, automatically upgrade to v6.
        # This ensures future_momentum_bucket tiers are available without
        # requiring every caller to hardcode the v6 filename.
        # Override order: explicit database_path arg > v6 auto-detect > config.
        if database_path is None:
            _v6_candidate = _db_obj.parent / _db_obj.name.replace(
                "actuarial_database", "actuarial_database_v6"
            ).replace("_v5", "_v6").replace("_v4", "_v6")
            # Only auto-upgrade if name changed (avoids infinite rename loop)
            if _v6_candidate != _db_obj and _v6_candidate.exists():
                import warnings as _w
                _w.warn(
                    f"ActuarialQueryEngine: auto-upgrading DB from "
                    f"{_db_obj.name} → {_v6_candidate.name} "
                    f"(v6 adds future_momentum_bucket). "
                    f"Set database_path explicitly to suppress this.",
                    UserWarning, stacklevel=2
                )
                _db_obj = _v6_candidate
            # Also check for plain _v6 suffix variant
            elif not _db_obj.exists():
                _v6_alt = _db_obj.parent / "actuarial_database_v6.parquet"
                if _v6_alt.exists():
                    _db_obj = _v6_alt

        self.database_path = str(_db_obj)
        self.df = None
        self._has_5d_cols   = False
        self._has_10d_cols  = False
        self._has_v6_cols   = False   # future_momentum_bucket presence flag
        self._match_norm_cache = {}
        # Validate path exists before attempting load - fail fast with context
        _db_path_obj = _db_obj
        if not _db_path_obj.exists():
            raise FileNotFoundError(
                f"ActuarialQueryEngine: database not found at '{self.database_path}'. "
                f"Check ACTUARIAL_DATABASE_PATH in config or pass database_path explicitly. "
                f"Expected v6: actuarial_database_v6.parquet"
            )
        import os
        _db_filename = os.path.basename(self.database_path)
        if 'v6' not in _db_filename and 'v6' not in self.database_path:
            import warnings
            warnings.warn(
                f"ActuarialQueryEngine loaded '{_db_filename}' — "
                f"this does not appear to be the v6 database. "
                f"Stage 0 future_momentum_bucket tiers will fall back to v5 behaviour. "
                f"Update ACTUARIAL_DATABASE_PATH to actuarial_database_v6.parquet.",
                UserWarning, stacklevel=2
            )
        self._load_database()

    def _load_database(self):
        """Load actuarial database and detect available horizon columns."""
        if not self.database_path or not Path(self.database_path).exists():
            print(f"Warning: Could not load actuarial database from {self.database_path}")
            self.df = None
            return
        try:
            available_columns = None
            try:
                import pyarrow.parquet as pq
                available_columns = set(pq.read_schema(self.database_path).names)
            except Exception:
                available_columns = None

            if available_columns:
                query_columns = [
                    col for col in ACTUARIAL_QUERY_COLUMNS
                    if col in available_columns
                ]
                self.df = pd.read_parquet(self.database_path, columns=query_columns)
            else:
                self.df = pd.read_parquet(self.database_path)

            for col in ACTUARIAL_CATEGORY_COLUMNS:
                if col in self.df.columns:
                    try:
                        self.df[col] = self.df[col].astype("category")
                    except Exception:
                        pass

            self._match_norm_cache = {}
            # Detect whether multi-horizon columns have been added
            self._has_5d_cols  = "outcome_5d_return"       in self.df.columns
            self._has_10d_cols = "outcome_10d_return"      in self.df.columns
            self._has_v6_cols  = "future_momentum_bucket"  in self.df.columns
            horizon_info = []
            if self._has_5d_cols:  horizon_info.append("5d")
            if self._has_10d_cols: horizon_info.append("10d")
            horizon_info.append("20d")
            # DEFECT 5 FIX: emit DB version to audit log so operators can
            # confirm v6 is loaded - one source of truth at load time
            import logging as _logging
            _aq_log = _logging.getLogger(__name__)
            _v6_str = "v6 [OK] future_momentum_bucket" if self._has_v6_cols else "v5 [WARN] no future_momentum_bucket"
            _aq_log.info(
                "ActuarialDB loaded: %d rows | %d query columns | horizons=%s | %s | %s",
                len(self.df), len(self.df.columns), ",".join(horizon_info),
                _v6_str, self.database_path
            )
            print(f"[OK] Loaded actuarial database: {len(self.df):,} observations "
                  f"| Query columns: {len(self.df.columns)} "
                  f"| Horizons: {', '.join(horizon_info)} | {_v6_str}")
        except Exception as e:
            print(f"Warning: Could not load actuarial database: {e}")
            self.df = None

    def query(self, state: StateVector) -> ActuarialOutcomes:
        """
        Query database for historical outcomes matching this state.
        WITH HYBRID ADJUSTMENTS based on intraday context.

        Returns ActuarialOutcomes with multi-horizon fields populated
        where database columns are available. NEVER returns None.
        """
        if self.df is None or len(self.df) == 0:
            return _empty_outcomes()

        try:
            similar_states = self._find_similar_states(state)
        except Exception as e:
            print(f"  Warning: _find_similar_states failed: {e}")
            return _empty_outcomes()

        _match_attrs = getattr(similar_states, 'attrs', {}) if similar_states is not None else {}
        if similar_states is None or len(similar_states) < 10:
            empty = _empty_outcomes(_match_attrs)
            self._attach_dict_to_outcomes(
                empty,
                self._probability_calibration(
                    similar_states if similar_states is not None else pd.DataFrame(),
                    _match_attrs,
                ),
            )
            return empty

        try:
            base_outcomes = self._calculate_outcomes(similar_states)
        except Exception as e:
            print(f"  Warning: _calculate_outcomes failed: {e}")
            return _empty_outcomes(_match_attrs)

        if base_outcomes is None:
            return _empty_outcomes(_match_attrs)

        try:
            adjusted_outcomes = self._adjust_for_intraday_context(base_outcomes, state)
        except Exception as e:
            print(f"  Warning: _adjust_for_intraday_context failed: {e}")
            adjusted_outcomes = base_outcomes

        final_outcomes = adjusted_outcomes if adjusted_outcomes is not None else base_outcomes

        # =========================
        # SPRINT 2: ATTACH SIGNAL TYPE + FORWARD MOMENTUM CONFIDENCE
        # =========================
        # signal_type is now a declared field on ActuarialOutcomes (not dynamic).
        # forward_momentum_confidence quantifies what % of matching DB rows had
        # accelerating momentum (momentum_delta > 0) - a quality filter for sizing.

        _attrs           = getattr(similar_states, 'attrs', {})
        _preferred_horizon = (
            _attrs.get("preferred_horizon")
            or self._select_preferred_horizon_from_outcomes(final_outcomes)
        )
        _confidence_attrs = self._confidence_attrs(
            method=_attrs.get("state_match_method", "UNKNOWN"),
            sample_size=int(_attrs.get("sample_size", final_outcomes.n_observations) or 0),
            preferred_horizon=_preferred_horizon,
            similarity=float(_attrs.get("state_match_similarity", 0.0) or 0.0),
        )
        _calibration_attrs = dict(_attrs)
        _calibration_attrs["preferred_horizon"] = _preferred_horizon
        _calibration_attrs.update(_confidence_attrs)
        _signal_type     = _calibration_attrs.get('signal_type', 'NO_EDGE')
        final_outcomes.signal_type = _signal_type

        # Match-method audit fields — read from DataFrame attrs set by _tag_match().
        # Surfaced explicitly by main.py into layer_2_result.
        # A HIGH_SAMPLE from CORE_4D_FALLBACK must not be treated as high-conviction
        # evidence by EIL, PSE, or MVE. These fields make that distinction auditable.
        final_outcomes.state_match_method     = _calibration_attrs.get("state_match_method",     "UNKNOWN")
        final_outcomes.state_match_stage      = _calibration_attrs.get("state_match_stage",      "UNKNOWN")
        final_outcomes.state_match_dimensions = _calibration_attrs.get("state_match_dimensions", "")
        final_outcomes.state_match_quality    = _calibration_attrs.get("state_match_quality",    "UNKNOWN")
        final_outcomes.state_match_similarity = float(_calibration_attrs.get("state_match_similarity", 0.0) or 0.0)
        final_outcomes.state_match_is_exact   = bool(_calibration_attrs.get("state_match_is_exact", False))
        final_outcomes.sample_size            = int(_calibration_attrs.get("sample_size", final_outcomes.n_observations) or 0)
        final_outcomes.sample_confidence_bucket = _calibration_attrs.get("sample_confidence_bucket", "UNKNOWN")
        final_outcomes.confidence_penalty     = float(_calibration_attrs.get("confidence_penalty", 0.30) or 0.30)
        final_outcomes.confidence_weight      = float(_calibration_attrs.get("confidence_weight", final_outcomes.confidence_penalty) or final_outcomes.confidence_penalty)
        final_outcomes.matched_state_key      = _calibration_attrs.get("matched_state_key", "")
        final_outcomes.original_state_key     = _calibration_attrs.get("original_state_key", "")
        final_outcomes.fallback_reason        = _calibration_attrs.get("fallback_reason", "")
        self._attach_dict_to_outcomes(
            final_outcomes,
            self._probability_calibration(similar_states, _calibration_attrs),
        )

        # Forward momentum confidence: fraction of matching rows where future bucket
        # is HIGHER than current bucket (genuine acceleration).
        # Prefers future_momentum_bucket (v6 DB) over raw momentum_delta.
        # Ranges 0.0-1.0. Higher = more DB rows had accelerating momentum.
        _fwd_conf = 0.0
        if _signal_type != 'NO_EDGE' and len(similar_states) > 0:
            if 'future_momentum_bucket' in similar_states.columns and 'momentum_bucket' in similar_states.columns:
                # Bucket order for comparison
                _bucket_rank = {"LOW": 0, "MID": 1, "HIGH": 2, "EXTREME": 3}
                _curr_rank = pd.to_numeric(
                    similar_states['momentum_bucket'].map(_bucket_rank),
                    errors="coerce",
                ).fillna(0)
                _fut_rank  = pd.to_numeric(
                    similar_states['future_momentum_bucket'].map(_bucket_rank),
                    errors="coerce",
                ).fillna(0)
                _fwd_conf  = float((_fut_rank > _curr_rank).mean())
            elif 'momentum_delta' in similar_states.columns:
                # Fallback: raw delta > 0
                _fwd_conf = float((similar_states['momentum_delta'] > 0).mean())
        final_outcomes.forward_momentum_confidence = _fwd_conf

        # Also attach momentum_tier for position_sizing_v2_patch
        final_outcomes.momentum_tier = _calibration_attrs.get('momentum_tier', 'TIER_4_FLAT')

        # Carry v6 forward-bucket fields from base_outcomes → final_outcomes.
        # _adjust_for_intraday_context creates a new ActuarialOutcomes object that
        # does not copy these fields. Copy them here so they survive intraday adjustment.
        for _v6_field in (
            "future_momentum_bucket",
            "future_momentum_bucket_distribution",
            "future_momentum_bucket_confidence",
            "future_momentum_bucket_sample_size",
            "transition_flag_rate_v2",
            "avg_momentum_delta",
            "avg_atr_delta",
            "avg_adx_delta",
            "early_candidate_rate",
        ):
            _base_val = getattr(base_outcomes, _v6_field, None)
            if _base_val is not None and getattr(final_outcomes, _v6_field, None) is None:
                setattr(final_outcomes, _v6_field, _base_val)

        return final_outcomes

    @staticmethod
    def _tag_match(
        matches: pd.DataFrame,
        *,
        method: str,
        stage: str,
        dimensions: list,
        quality: str,
        is_exact: bool = False,
        extra_attrs: Optional[dict] = None,
    ) -> pd.DataFrame:
        """
        Attach auditable match metadata to the matched historical sample.

        This is the single authoritative place where match-method information
        is written to a DataFrame. All return paths in _find_similar_states()
        must call this — never set .attrs directly on a return.

        A HIGH_SAMPLE from an exact state match is not the same as a
        HIGH_SAMPLE from a broad 4D fallback. This method makes that
        distinction explicit and auditable downstream.

        The attrs are read by query() → attached to final_outcomes →
        surfaced by main.py into layer_2_result as layer2__state_match_* CSV columns.
        """
        tagged = matches.copy()
        tagged.attrs["state_match_method"]     = method
        tagged.attrs["state_match_stage"]      = stage
        tagged.attrs["state_match_dimensions"] = "|".join(dimensions)
        tagged.attrs["state_match_quality"]    = quality
        tagged.attrs["state_match_is_exact"]   = bool(is_exact)
        tagged.attrs["sample_size"]            = int(len(tagged))
        if extra_attrs:
            for k, v in extra_attrs.items():
                tagged.attrs[k] = v
        return tagged

    @staticmethod
    def _normalise_horizon(value) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().upper().replace("_", "")
        if text in ("", "NONE", "N/A", "NA", "NAN", "UNKNOWN"):
            return None
        if text in ("5", "5D", "5DAY", "5DAYS"):
            return "5D"
        if text in ("10", "10D", "10DAY", "10DAYS"):
            return "10D"
        if text in ("20", "20D", "20DAY", "20DAYS"):
            return "20D"
        return text

    @classmethod
    def _normalise_match_value(cls, dim: str, value) -> Optional[str]:
        if dim == "preferred_horizon":
            return cls._normalise_horizon(value)
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        text = str(value).strip().upper()
        if text in ("", "NONE", "N/A", "NA", "NAN", "UNKNOWN"):
            return None
        return text

    @classmethod
    def _state_match_values(cls, state: StateVector) -> dict:
        values = {}
        for dim in MATCH_EXACT_DIMS:
            raw = state.get(dim) if isinstance(state, dict) else getattr(state, dim, None)
            values[dim] = cls._normalise_match_value(dim, raw)
        return values

    @classmethod
    def _available_match_dims(cls, df: pd.DataFrame, values: dict, dims: list) -> list:
        return [dim for dim in dims if dim in df.columns and values.get(dim) is not None]

    @classmethod
    def _state_key(cls, values: dict, dims: list) -> str:
        return "|".join(f"{dim}={values.get(dim) or '*'}" for dim in dims)

    @classmethod
    def _matched_key_from_sample(cls, sample: pd.DataFrame, dims: list) -> str:
        if sample is None or sample.empty:
            return ""
        row = sample.iloc[0]
        return "|".join(
            f"{dim}={cls._normalise_match_value(dim, row.get(dim)) or '*'}"
            for dim in dims
        )

    @staticmethod
    def _sample_quality(sample_size: int) -> str:
        if sample_size >= 300:
            return "HIGH_SAMPLE"
        if sample_size >= 100:
            return "MODERATE_SAMPLE"
        if sample_size >= 30:
            return "LOW_SAMPLE"
        return "INSUFFICIENT_SAMPLE"

    @staticmethod
    def _horizon_sample_min(preferred_horizon: Optional[str], relaxed: bool = False) -> int:
        horizon = ActuarialQueryEngine._normalise_horizon(preferred_horizon) or "10D"
        if relaxed:
            return {"5D": 60, "10D": 100, "20D": 150}.get(horizon, 100)
        return {"5D": 30, "10D": 60, "20D": 100}.get(horizon, 60)

    @staticmethod
    def _confidence_horizon_group(preferred_horizon: Optional[str]) -> str:
        horizon = ActuarialQueryEngine._normalise_horizon(preferred_horizon) or "20D"
        if horizon == "5D":
            return "1_5D"
        if horizon == "10D":
            return "6_10D"
        if horizon == "20D":
            return "11_20D"
        return "1_3M"

    @classmethod
    def _sample_confidence_bucket(cls, sample_size: int, preferred_horizon: Optional[str]) -> str:
        if sample_size <= 0:
            return "UNKNOWN"
        thresholds = SAMPLE_CONFIDENCE_THRESHOLDS[cls._confidence_horizon_group(preferred_horizon)]
        for bucket in ("HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW"):
            if sample_size >= thresholds[bucket]:
                return bucket
        return "THIN"

    @staticmethod
    def _confidence_weight(method: str, sample_bucket: str, similarity: Optional[float]) -> float:
        method = (method or "UNKNOWN").upper()
        sample_bucket = (sample_bucket or "UNKNOWN").upper()
        if method == "UNKNOWN":
            return 0.30
        if method == "ANALOGUE":
            sim = float(similarity or 0.0)
            if sim >= 0.85 and sample_bucket in ("HIGH", "MEDIUM_HIGH"):
                return 0.70
            if sim >= 0.80:
                return 0.60
            if sim >= 0.70:
                return 0.50
            return 0.35
        return CONFIDENCE_WEIGHTS.get(method, {}).get(sample_bucket, 0.30)

    @classmethod
    def _confidence_attrs(
        cls,
        *,
        method: str,
        sample_size: int,
        preferred_horizon: Optional[str],
        similarity: Optional[float],
    ) -> dict:
        bucket = cls._sample_confidence_bucket(sample_size, preferred_horizon)
        if (method or "").upper() == "UNKNOWN":
            bucket = "UNKNOWN"
        weight = cls._confidence_weight(method, bucket, similarity)
        return {
            "sample_confidence_bucket": bucket,
            "confidence_penalty": weight,
            "confidence_weight": weight,
        }

    @staticmethod
    def _probability_verdict(edge: float) -> str:
        if edge >= 0.10:
            return "STRONG_EDGE"
        if edge >= 0.05:
            return "MODEST_EDGE"
        if edge > 0.0:
            return "WEAK_EDGE"
        if edge == 0.0:
            return "NO_STAT_EDGE"
        return "NEGATIVE_EDGE"

    @staticmethod
    def _mean_numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
        if df is None or df.empty or column not in df.columns:
            return float(default)
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        return float(series.mean()) if not series.empty else float(default)

    @staticmethod
    def _median_numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> float:
        if df is None or df.empty or column not in df.columns:
            return float(default)
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        return float(series.median()) if not series.empty else float(default)

    @staticmethod
    def _prob_up(df: pd.DataFrame, column: str) -> float:
        if df is None or df.empty or column not in df.columns:
            return 0.0
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        return float((series > 0).mean()) if not series.empty else 0.0

    @staticmethod
    def _prob_down(df: pd.DataFrame, column: str) -> float:
        if df is None or df.empty or column not in df.columns:
            return 0.0
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        return float((series < 0).mean()) if not series.empty else 0.0

    @classmethod
    def _return_col_for_horizon(cls, preferred_horizon: Optional[str]) -> str:
        horizon = cls._normalise_horizon(preferred_horizon) or "20D"
        if horizon == "5D":
            return "outcome_5d_return"
        if horizon == "10D":
            return "outcome_10d_return"
        return "outcome_20d_return"

    @classmethod
    def _target_col_for_horizon(cls, preferred_horizon: Optional[str]) -> str:
        horizon = cls._normalise_horizon(preferred_horizon) or "20D"
        if horizon == "5D":
            return "outcome_hit_5pct_up_5d"
        if horizon == "10D":
            return "outcome_hit_7pct_up_10d"
        return "outcome_hit_10pct_up"

    @classmethod
    def _drawdown_col_for_horizon(cls, preferred_horizon: Optional[str]) -> str:
        horizon = cls._normalise_horizon(preferred_horizon) or "20D"
        if horizon == "5D":
            return "outcome_max_drawdown_5d"
        if horizon == "10D":
            return "outcome_max_drawdown_10d"
        return "outcome_max_drawdown_20d"

    def _probability_calibration(self, sample: pd.DataFrame, attrs: dict) -> dict:
        method = str(attrs.get("state_match_method") or "UNKNOWN").upper()
        preferred_horizon = attrs.get("preferred_horizon") or "20D"
        weight = float(attrs.get("confidence_weight", 0.30) or 0.30)
        target_col = self._target_col_for_horizon(preferred_horizon)
        return_col = self._return_col_for_horizon(preferred_horizon)
        drawdown_col = self._drawdown_col_for_horizon(preferred_horizon)

        population = self.df if self.df is not None else pd.DataFrame()
        baseline_probability = self._mean_numeric(population, target_col, default=0.0)
        baseline_return = self._mean_numeric(population, return_col, default=0.0)

        raw_prob_target_hit = self._mean_numeric(sample, target_col, default=0.0)
        raw_expected_return = self._mean_numeric(sample, return_col, default=0.0)

        if method == "UNKNOWN":
            adjusted_prob = baseline_probability
            adjusted_return = baseline_return
            edge = 0.0
        else:
            adjusted_prob = baseline_probability + weight * (raw_prob_target_hit - baseline_probability)
            adjusted_return = baseline_return + weight * (raw_expected_return - baseline_return)
            edge = adjusted_prob - baseline_probability

        return {
            "raw_prob_up_5d": self._prob_up(sample, "outcome_5d_return"),
            "raw_prob_up_10d": self._prob_up(sample, "outcome_10d_return"),
            "raw_prob_up_20d": self._prob_up(sample, "outcome_20d_return"),
            "raw_prob_down_5d": self._prob_down(sample, "outcome_5d_return"),
            "raw_prob_down_10d": self._prob_down(sample, "outcome_10d_return"),
            "raw_prob_down_20d": self._prob_down(sample, "outcome_20d_return"),
            "raw_prob_target_hit": raw_prob_target_hit,
            "raw_prob_stop_hit": self._mean_numeric(sample, "outcome_hit_5pct_down_before_10up", default=0.0),
            "raw_expected_return": raw_expected_return,
            "raw_expected_drawdown": self._median_numeric(sample, drawdown_col, default=0.0),
            "raw_expected_time_to_target": self._median_numeric(sample, "outcome_days_to_10pct", default=0.0),
            "baseline_probability": baseline_probability,
            "adjusted_prob_target_hit": adjusted_prob,
            "adjusted_expected_return": adjusted_return,
            "probability_edge": edge,
            "probability_verdict": self._probability_verdict(edge),
        }

    @staticmethod
    def _attach_dict_to_outcomes(outcomes: ActuarialOutcomes, values: dict) -> None:
        for key, value in values.items():
            setattr(outcomes, key, value)

    @staticmethod
    def _select_preferred_horizon_from_outcomes(outcomes: ActuarialOutcomes) -> str:
        candidates = [
            ("5D", getattr(outcomes, "expected_value_5d", None), getattr(outcomes, "win_rate_5d", None)),
            ("10D", getattr(outcomes, "expected_value_10d", None), getattr(outcomes, "win_rate_10d", None)),
            ("20D", getattr(outcomes, "expected_value_20d", None), getattr(outcomes, "win_rate", None)),
        ]
        valid = [c for c in candidates if c[1] is not None and c[2] is not None]
        if not valid:
            return "20D"
        return sorted(valid, key=lambda item: (item[1], item[2]), reverse=True)[0][0]

    @staticmethod
    def _signal_type_from_values(values: dict) -> str:
        phase = values.get("phase_v2")
        momentum = values.get("momentum_bucket")
        location = values.get("location_bucket")
        if phase == "CONTINUATION" and momentum in ("HIGH", "EXTREME") and location != "NEAR_HIGH":
            return "CONTINUATION"
        if (
            phase == "EARLY_TRANSITION"
            and momentum in ("LOW", "MID")
            and location in ("TRANSITION_ZONE", "NEAR_LOW")
        ):
            return "TRANSITION"
        return "STRUCTURAL_MATCH"

    @staticmethod
    def _dominant_future_momentum_bucket(sample: pd.DataFrame) -> str:
        if sample is None or sample.empty or "future_momentum_bucket" not in sample.columns:
            return ""
        values = (
            sample["future_momentum_bucket"]
            .dropna()
            .astype(str)
            .str.upper()
            .str.strip()
        )
        values = values[~values.isin(["", "NAN", "NONE", "UNKNOWN", "DATA_WEAK"])]
        if values.empty:
            return ""
        return str(values.mode().iloc[0])

    @classmethod
    def _momentum_tier_from_sample(cls, signal_type: str, values: dict, sample: pd.DataFrame) -> str:
        """
        Convert the active historical match sample into a forward-momentum tier.

        The retired Stage 0/1/2 code used to calculate these tiers, but it sat
        below an early return and never ran. Keep the behaviour in the active
        match ladder so EdgeDetector can distinguish continuation, transition,
        and structural matches without relying on unreachable code.
        """
        future_bucket = cls._dominant_future_momentum_bucket(sample)
        current_momentum = values.get("momentum_bucket")

        if signal_type == "CONTINUATION":
            if future_bucket == "EXTREME":
                return "TIER_1_EXPLOSIVE"
            if future_bucket == "HIGH":
                return "TIER_2_SUSTAINING"
            if future_bucket == "MID":
                return "TIER_3_BUILDING"
            return "TIER_4_FLAT"

        if signal_type == "TRANSITION":
            if future_bucket in ("HIGH", "EXTREME") and current_momentum in ("LOW", "MID"):
                return "TIER_1_ACCELERATING"
            if future_bucket == "MID":
                return "TIER_2_BUILDING"
            if "adx_delta" in sample.columns:
                try:
                    if float(pd.to_numeric(sample["adx_delta"], errors="coerce").dropna().median()) > 0:
                        return "TIER_2_BUILDING"
                except Exception:
                    pass
            return "TIER_4_FLAT"

        return "N/A"

    def _normalised_match_series(self, dim: str) -> Optional[pd.Series]:
        """
        Return a cached normalised match column.

        UAT perf fix: the match ladder runs once per package. Normalising
        5.7M rows with map(lambda...) for every ticker turns Vanguard into a
        multi-hour stage. Cache each normalised dimension once per DB load and
        reuse vectorised equality checks for the whole run.
        """
        if not hasattr(self, "_match_norm_cache") or self._match_norm_cache is None:
            self._match_norm_cache = {}
        if self.df is None or dim not in self.df.columns:
            return None
        if dim not in self._match_norm_cache:
            self._match_norm_cache[dim] = self.df[dim].map(
                lambda value: self._normalise_match_value(dim, value)
            )
        return self._match_norm_cache[dim]

    def _filter_by_dims(self, df: pd.DataFrame, values: dict, dims: list) -> pd.DataFrame:
        if not dims:
            return df.iloc[0:0]
        mask = None
        for dim in dims:
            target = values.get(dim)
            if target is None or dim not in df.columns:
                continue
            series = self._normalised_match_series(dim)
            if series is None:
                continue
            current = series.eq(target)
            mask = current if mask is None else (mask & current)
        if mask is None:
            return df.iloc[0:0]
        return df.loc[mask]

    def _find_match_ladder_states(self, state: StateVector) -> pd.DataFrame:
        """
        Phase 2A Vanguard match ladder:
        EXACT -> RELAXED -> ANALOGUE -> UNKNOWN.
        """
        df = self.df
        values = self._state_match_values(state)
        # preferred_horizon is deliberately not a match dimension in v6.
        # It is selected after outcomes are calculated, then handed forward
        # as layer2__preferred_horizon for routing and options DTE logic.
        preferred_horizon = None
        original_key = self._state_key(values, MATCH_EXACT_DIMS)
        signal_type = self._signal_type_from_values(values)

        exact_dims = self._available_match_dims(df, values, MATCH_EXACT_DIMS)
        exact = self._filter_by_dims(df, values, exact_dims)
        exact_min = self._horizon_sample_min(preferred_horizon, relaxed=False)
        if len(exact) >= exact_min:
            return self._tag_match(
                exact,
                method="EXACT",
                stage="EXACT",
                dimensions=exact_dims,
                quality=self._sample_quality(len(exact)),
                is_exact=True,
                extra_attrs={
                    "signal_type": signal_type,
                    "momentum_tier": self._momentum_tier_from_sample(signal_type, values, exact),
                    "state_match_similarity": 1.0,
                    **self._confidence_attrs(
                        method="EXACT",
                        sample_size=len(exact),
                        preferred_horizon=preferred_horizon,
                        similarity=1.0,
                    ),
                    "preferred_horizon": preferred_horizon or "",
                    "matched_state_key": self._matched_key_from_sample(exact, exact_dims),
                    "original_state_key": original_key,
                    "fallback_reason": "NONE",
                },
            )

        relaxed_dims = self._available_match_dims(df, values, MATCH_RELAXED_DIMS)
        relaxed = self._filter_by_dims(df, values, relaxed_dims)
        relaxed_min = self._horizon_sample_min(preferred_horizon, relaxed=True)
        if len(relaxed) >= relaxed_min:
            return self._tag_match(
                relaxed,
                method="RELAXED",
                stage="RELAXED",
                dimensions=relaxed_dims,
                quality=self._sample_quality(len(relaxed)),
                is_exact=False,
                extra_attrs={
                    "signal_type": signal_type,
                    "momentum_tier": self._momentum_tier_from_sample(signal_type, values, relaxed),
                    "state_match_similarity": 1.0,
                    **self._confidence_attrs(
                        method="RELAXED",
                        sample_size=len(relaxed),
                        preferred_horizon=preferred_horizon,
                        similarity=1.0,
                    ),
                    "preferred_horizon": preferred_horizon or "",
                    "matched_state_key": self._matched_key_from_sample(relaxed, relaxed_dims),
                    "original_state_key": original_key,
                    "fallback_reason": f"EXACT_SAMPLE_BELOW_MIN:{len(exact)}/{exact_min}",
                },
            )

        weighted_dims = [
            dim for dim in MATCH_SIMILARITY_WEIGHTS
            if dim in df.columns and values.get(dim) is not None
        ]
        total_weight = sum(MATCH_SIMILARITY_WEIGHTS[dim] for dim in weighted_dims)
        analogue = df.iloc[0:0].copy()
        analogue_similarity = 0.0

        if total_weight > 0:
            scores = pd.Series(0.0, index=df.index)
            for dim in weighted_dims:
                target = values[dim]
                weight = MATCH_SIMILARITY_WEIGHTS[dim]
                series = self._normalised_match_series(dim)
                if series is None:
                    continue
                matches = series.eq(target)
                scores += matches.astype(float) * weight
            scores = scores / total_weight
            analogue = df[scores >= ANALOGUE_MIN_SIMILARITY].copy()
            if not analogue.empty:
                analogue_similarity = round(float(scores.loc[analogue.index].mean()), 4)

        if len(analogue) >= ANALOGUE_MIN_SAMPLES:
            return self._tag_match(
                analogue,
                method="ANALOGUE",
                stage="ANALOGUE",
                dimensions=weighted_dims,
                quality=self._sample_quality(len(analogue)),
                is_exact=False,
                extra_attrs={
                    "signal_type": signal_type,
                    "momentum_tier": self._momentum_tier_from_sample(signal_type, values, analogue),
                    "state_match_similarity": analogue_similarity,
                    **self._confidence_attrs(
                        method="ANALOGUE",
                        sample_size=len(analogue),
                        preferred_horizon=preferred_horizon,
                        similarity=analogue_similarity,
                    ),
                    "preferred_horizon": preferred_horizon or "",
                    "matched_state_key": f"ANALOGUE>=0.70|mean_similarity={analogue_similarity}",
                    "original_state_key": original_key,
                    "fallback_reason": (
                        f"EXACT_SAMPLE_BELOW_MIN:{len(exact)}/{exact_min};"
                        f"RELAXED_SAMPLE_BELOW_MIN:{len(relaxed)}/{relaxed_min}"
                    ),
                },
            )

        unknown_reason = (
            f"EXACT_SAMPLE_BELOW_MIN:{len(exact)}/{exact_min};"
            f"RELAXED_SAMPLE_BELOW_MIN:{len(relaxed)}/{relaxed_min};"
            f"ANALOGUE_SAMPLE_OR_SIMILARITY_BELOW_MIN:{len(analogue)}/{ANALOGUE_MIN_SAMPLES}"
        )
        return self._tag_match(
            df.iloc[0:0],
            method="UNKNOWN",
            stage="UNKNOWN",
            dimensions=exact_dims or relaxed_dims or weighted_dims,
            quality="INSUFFICIENT_SAMPLE",
            is_exact=False,
            extra_attrs={
                "signal_type": "NO_EDGE",
                "momentum_tier": "N/A",
                "state_match_similarity": 0.0,
                **self._confidence_attrs(
                    method="UNKNOWN",
                    sample_size=0,
                    preferred_horizon=preferred_horizon,
                    similarity=0.0,
                ),
                "preferred_horizon": preferred_horizon or "",
                "matched_state_key": "",
                "original_state_key": original_key,
                "fallback_reason": unknown_reason,
            },
        )

    def _find_similar_states(self, state: StateVector) -> pd.DataFrame:
        """Find historical states using the production match ladder.

        The legacy Stage 0/1/2 matching block was retired because it sat below
        an early return and never executed. Signal type and momentum tier are
        now calculated inside _find_match_ladder_states(), which is the only
        production path.
        """
        return self._find_match_ladder_states(state)

    @staticmethod
    def _future_bucket_stats(matches: pd.DataFrame) -> dict:
        """
        Fix 4+5: Calculate future_momentum_bucket distribution from matched rows.
        Returns 4 fields for ActuarialOutcomes v6 contract.
        """
        if "future_momentum_bucket" not in matches.columns or matches.empty:
            return {
                "future_momentum_bucket":              None,
                "future_momentum_bucket_distribution": {},
                "future_momentum_bucket_confidence":   0.0,
                "future_momentum_bucket_sample_size":  0,
            }
        bucket_counts = matches["future_momentum_bucket"].value_counts(dropna=True)
        if bucket_counts.empty:
            return {
                "future_momentum_bucket":              None,
                "future_momentum_bucket_distribution": {},
                "future_momentum_bucket_confidence":   0.0,
                "future_momentum_bucket_sample_size":  0,
            }
        total = int(bucket_counts.sum())
        return {
            "future_momentum_bucket":              str(bucket_counts.index[0]),
            "future_momentum_bucket_distribution": {
                str(k): round(float(v / total), 4) for k, v in bucket_counts.items()
            },
            "future_momentum_bucket_confidence":   round(float(bucket_counts.iloc[0] / total), 4),
            "future_momentum_bucket_sample_size":  total,
        }

    @staticmethod
    def _transition_delta_stats(matches: pd.DataFrame) -> dict:
        """
        Fix 4+5: Calculate transition/delta diagnostic fields from matched rows.
        Returns 5 fields for ActuarialOutcomes v6 contract.
        """
        def _mean(col):
            if col not in matches.columns:
                return None
            s = matches[col].dropna()
            return round(float(s.mean()), 6) if not s.empty else None

        return {
            "transition_flag_rate_v2": _mean("transition_flag_v2"),
            "avg_momentum_delta":      _mean("momentum_delta"),
            "avg_atr_delta":           _mean("atr_delta"),
            "avg_adx_delta":           _mean("adx_delta"),
            "early_candidate_rate":    _mean("early_candidate"),
        }

    def _calculate_outcomes(self, similar_states: pd.DataFrame) -> ActuarialOutcomes:
        """
        Calculate probabilistic outcomes from similar historical states.
        Computes all available horizons (5d, 10d, 20d).
        """
        n_obs = len(similar_states)

        # ------ 20-DAY OUTCOMES (always available) ------------------------------------------------------------------------------------------------
        prob_up_10pct    = similar_states['outcome_hit_10pct_up'].mean()
        prob_down_5pct   = similar_states['outcome_hit_5pct_down_before_10up'].mean()
        prob_trend_cont  = (similar_states['outcome_20d_return'] > 0).mean()

        wins_20d = similar_states[similar_states['outcome_20d_return'] > 0]
        loss_20d = similar_states[similar_states['outcome_20d_return'] <= 0]

        median_gain_20d     = wins_20d['outcome_20d_return'].median() if len(wins_20d) > 0 else 0.05
        median_loss_20d     = loss_20d['outcome_20d_return'].median() if len(loss_20d) > 0 else -0.03
        median_drawdown_20d = similar_states['outcome_max_drawdown_20d'].median()
        median_days         = similar_states['outcome_days_to_10pct'].median()

        rets_20d     = similar_states['outcome_20d_return']
        win_rate_20d = (rets_20d > 0).mean()   # P(return > 0) -- directional win rate
        sharpe_20d   = (rets_20d.mean() / rets_20d.std()) if rets_20d.std() > 0 else 0.0

        # EV uses directional win rate -- median gain/loss of all winners/losers
        # NOT prob_up_10pct (target hit rate) --- that would understate EV for small winners
        ev_20d = (win_rate_20d * median_gain_20d) + ((1 - win_rate_20d) * median_loss_20d)

        avg_win_20d  = wins_20d['outcome_20d_return'].mean() if len(wins_20d) > 0 else 0.05
        avg_loss_20d = abs(loss_20d['outcome_20d_return'].mean()) if len(loss_20d) > 0 else 0.03
        win_loss_ratio = avg_win_20d / avg_loss_20d if avg_loss_20d > 0 else 1.0

        kelly = (prob_up_10pct * avg_win_20d - (1 - prob_up_10pct) * avg_loss_20d) / avg_win_20d if avg_win_20d > 0 else 0.1
        kelly = max(0.0, min(kelly, 0.25))

        recommended_hold = int(median_days) if prob_up_10pct > 0.5 else 20
        outcome_dist     = similar_states['outcome_category'].value_counts(normalize=True).to_dict()
        confidence       = min(1.0, n_obs / 50)

        # ------ 5-DAY OUTCOMES (available after database upgrade) ---------------------------------------------------
        wr_5d = ev_5d = prob_5pct_5d = 0.0
        med_gain_5d = med_loss_5d = med_dd_5d = sharpe_5d = 0.0

        if self._has_5d_cols and 'outcome_5d_return' in similar_states.columns:
            rets_5d   = similar_states['outcome_5d_return'].dropna()
            wins_5d   = rets_5d[rets_5d > 0]
            losses_5d = rets_5d[rets_5d <= 0]

            wr_5d        = (rets_5d > 0).mean()
            med_gain_5d  = wins_5d.median()   if len(wins_5d)   > 0 else 0.0
            med_loss_5d  = losses_5d.median() if len(losses_5d) > 0 else 0.0
            ev_5d        = (wr_5d * med_gain_5d) + ((1 - wr_5d) * med_loss_5d)
            sharpe_5d    = (rets_5d.mean() / rets_5d.std()) if rets_5d.std() > 0 else 0.0

            if 'outcome_hit_5pct_up_5d' in similar_states.columns:
                prob_5pct_5d = similar_states['outcome_hit_5pct_up_5d'].mean()

            if 'outcome_max_drawdown_5d' in similar_states.columns:
                med_dd_5d = similar_states['outcome_max_drawdown_5d'].median()

        # ------ 10-DAY OUTCOMES (available after database upgrade) ------------------------------------------------
        wr_10d = ev_10d = prob_7pct_10d = 0.0
        med_gain_10d = med_loss_10d = med_dd_10d = sharpe_10d = 0.0

        if self._has_10d_cols and 'outcome_10d_return' in similar_states.columns:
            rets_10d   = similar_states['outcome_10d_return'].dropna()
            wins_10d   = rets_10d[rets_10d > 0]
            losses_10d = rets_10d[rets_10d <= 0]

            wr_10d        = (rets_10d > 0).mean()
            med_gain_10d  = wins_10d.median()   if len(wins_10d)   > 0 else 0.0
            med_loss_10d  = losses_10d.median() if len(losses_10d) > 0 else 0.0
            ev_10d        = (wr_10d * med_gain_10d) + ((1 - wr_10d) * med_loss_10d)
            sharpe_10d    = (rets_10d.mean() / rets_10d.std()) if rets_10d.std() > 0 else 0.0

            if 'outcome_hit_7pct_up_10d' in similar_states.columns:
                prob_7pct_10d = similar_states['outcome_hit_7pct_up_10d'].mean()

            if 'outcome_max_drawdown_10d' in similar_states.columns:
                med_dd_10d = similar_states['outcome_max_drawdown_10d'].median()

        # -- v6 future bucket stats -----------------------------------------
        _fbs = self._future_bucket_stats(similar_states)
        _tds = self._transition_delta_stats(similar_states)

        return ActuarialOutcomes(
            # ------ 20d (original fields) ---------------------------------------------------------------------------------------------------------------------------
            n_observations=n_obs,
            confidence_level=confidence,
            lookback_period="3Y",
            prob_up_10pct_20d=prob_up_10pct,
            prob_down_5pct_before_up_10pct=prob_down_5pct,
            prob_trend_continues_20d=prob_trend_cont,
            median_gain_if_up=median_gain_20d,
            median_loss_if_down=median_loss_20d,
            median_max_drawdown=median_drawdown_20d,
            median_days_to_target=median_days,
            expected_value_20d=ev_20d,
            sharpe_ratio=sharpe_20d,
            win_rate=win_rate_20d,
            avg_win_loss_ratio=win_loss_ratio,
            kelly_fraction=kelly,
            recommended_hold_days=recommended_hold,
            outcome_distribution=outcome_dist,
            # ------ 5d (new) ------------------------------------------------------------------------------------------------------------------------------------------------------------------
            win_rate_5d=wr_5d,
            expected_value_5d=ev_5d,
            prob_up_5pct_5d=prob_5pct_5d,
            median_gain_if_up_5d=med_gain_5d,
            median_loss_if_down_5d=med_loss_5d,
            median_max_drawdown_5d=med_dd_5d,
            sharpe_ratio_5d=sharpe_5d,
            # ------ 10d (new) ---------------------------------------------------------------------------------------------------------------------------------------------------------------
            win_rate_10d=wr_10d,
            expected_value_10d=ev_10d,
            prob_up_7pct_10d=prob_7pct_10d,
            median_gain_if_up_10d=med_gain_10d,
            median_loss_if_down_10d=med_loss_10d,
            median_max_drawdown_10d=med_dd_10d,
            sharpe_ratio_10d=sharpe_10d,
            # -- v6 future bucket fields (Fix 4+5) -----------------------------
            future_momentum_bucket=_fbs['future_momentum_bucket'],
            future_momentum_bucket_distribution=_fbs['future_momentum_bucket_distribution'],
            future_momentum_bucket_confidence=_fbs['future_momentum_bucket_confidence'],
            future_momentum_bucket_sample_size=_fbs['future_momentum_bucket_sample_size'],
            transition_flag_rate_v2=_tds['transition_flag_rate_v2'],
            avg_momentum_delta=_tds['avg_momentum_delta'],
            avg_atr_delta=_tds['avg_atr_delta'],
            avg_adx_delta=_tds['avg_adx_delta'],
            early_candidate_rate=_tds['early_candidate_rate'],
        )

    def _adjust_for_intraday_context(self, base_outcomes: ActuarialOutcomes, state: StateVector) -> ActuarialOutcomes:
        """
        HYBRID APPROACH: Adjust daily database probabilities based on intraday context.
        Adjustments applied uniformly across all horizons.

        FIX 1 (CRITICAL): Fail-closed when intraday_rows=0.
        Without real intraday data the fields intraday_position, volume_profile_context,
        and control_dynamics carry sentinel defaults (UNKNOWN/BALANCED/NEUTRAL).
        Although these produce adjustment_factor=1.0, the triple-barrier EV
        recalculation substitutes prob_up_10pct_20d (target hit rate ~68%) as
        prob_target instead of win_rate (~43%), inflating reported EV by ~50x.
        Gate immediately with base_outcomes to preserve actuarial truth.
        """
        # FAIL-CLOSED: no intraday data - no adjustment, return base unchanged
        intraday_rows = getattr(state, 'intraday_rows', None)
        if intraday_rows is not None and intraday_rows == 0:
            return base_outcomes

        adj_prob_up       = base_outcomes.prob_up_10pct_20d
        adj_prob_down     = base_outcomes.prob_down_5pct_before_up_10pct
        adj_ev_20d        = base_outcomes.expected_value_20d

        intraday_position = getattr(state, 'intraday_position', 'UNKNOWN')
        volume_context    = getattr(state, 'volume_profile_context', 'BALANCED')
        control_dynamics  = getattr(state, 'control_dynamics', 'NEUTRAL')

        adjustment_factor = 1.0
        adjustment_notes  = []

        # ADJUSTMENT 1: Intraday Position
        if intraday_position == 'AT_SUPPORT':
            if state.trend_direction in ['DOWN', 'SIDEWAYS']:
                adjustment_factor *= 1.6
                adjustment_notes.append("AT_SUPPORT (+60%)")
            else:
                adjustment_factor *= 1.3
                adjustment_notes.append("AT_SUPPORT in uptrend (+30%)")
        elif intraday_position == 'AT_RESISTANCE':
            if state.trend_direction == 'UP':
                adjustment_factor *= 1.2
                adjustment_notes.append("AT_RESISTANCE in uptrend (+20%)")
            else:
                adjustment_factor *= 0.7
                adjustment_notes.append("AT_RESISTANCE (-30%)")
        elif intraday_position == 'NEAR_SUPPORT':
            adjustment_factor *= 1.2
            adjustment_notes.append("NEAR_SUPPORT (+20%)")

        # ADJUSTMENT 2: Volume Profile Context
        if volume_context == 'ACCUMULATION':
            adjustment_factor *= 1.3
            adjustment_notes.append("ACCUMULATION (+30%)")
        elif volume_context == 'DISTRIBUTION':
            adjustment_factor *= 0.75
            adjustment_notes.append("DISTRIBUTION (-25%)")

        # ADJUSTMENT 3: Control Dynamics
        if control_dynamics == 'BUYERS_STRENGTHENING':
            adjustment_factor *= 1.2
            adjustment_notes.append("BUYERS_STRENGTHENING (+20%)")
        elif control_dynamics == 'SELLERS_STRENGTHENING':
            adjustment_factor *= 0.8
            adjustment_notes.append("SELLERS_STRENGTHENING (-20%)")

        adjustment_factor = max(0.4, min(adjustment_factor, 2.5))

        adj_prob_up = min(0.95, adj_prob_up * adjustment_factor)

        if adjustment_factor > 1.0:
            adj_prob_down = adj_prob_down * (1 / (1 + (adjustment_factor - 1) * 0.5))
        else:
            adj_prob_down = min(0.95, adj_prob_down * (2 - adjustment_factor))

        # Triple-barrier EV recalculation (20d)
        prob_target  = adj_prob_up
        prob_stop    = adj_prob_down
        prob_expiry  = max(0.0, 1.0 - prob_target - prob_stop)
        total_prob   = prob_target + prob_stop + prob_expiry
        if total_prob > 1.0:
            prob_target /= total_prob
            prob_stop   /= total_prob
            prob_expiry /= total_prob

        gain_target  = base_outcomes.median_gain_if_up * adjustment_factor
        loss_stop    = base_outcomes.median_loss_if_down
        adj_ev_20d   = (prob_target * gain_target) + (prob_stop * loss_stop)

        # Apply same adjustment factor to shorter horizons
        adj_ev_5d  = base_outcomes.expected_value_5d  * adjustment_factor if base_outcomes.expected_value_5d  != 0 else 0.0
        adj_ev_10d = base_outcomes.expected_value_10d * adjustment_factor if base_outcomes.expected_value_10d != 0 else 0.0

        adj_wr_5d  = min(0.95, base_outcomes.win_rate_5d  * adjustment_factor) if base_outcomes.win_rate_5d  > 0 else 0.0
        adj_wr_10d = min(0.95, base_outcomes.win_rate_10d * adjustment_factor) if base_outcomes.win_rate_10d > 0 else 0.0

        if adjustment_notes:
            ev_change = ((adj_ev_20d / base_outcomes.expected_value_20d) - 1) * 100 if base_outcomes.expected_value_20d != 0 else 0
            adjustment_notes.append(f"EV20d: {base_outcomes.expected_value_20d:.1%} -> {adj_ev_20d:.1%} ({ev_change:+.0f}%)")

        adjustment_summary = f"{adjustment_factor:.2f}x: " + ", ".join(adjustment_notes) if adjustment_notes else None

        return ActuarialOutcomes(
            # ------ 20d ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
            n_observations=base_outcomes.n_observations,
            confidence_level=base_outcomes.confidence_level,
            lookback_period=base_outcomes.lookback_period,
            prob_up_10pct_20d=prob_target,
            prob_down_5pct_before_up_10pct=prob_stop,
            prob_trend_continues_20d=base_outcomes.prob_trend_continues_20d,
            median_gain_if_up=gain_target,
            median_loss_if_down=loss_stop,
            median_max_drawdown=base_outcomes.median_max_drawdown,
            median_days_to_target=base_outcomes.median_days_to_target,
            expected_value_20d=adj_ev_20d,
            sharpe_ratio=base_outcomes.sharpe_ratio * adjustment_factor,
            win_rate=base_outcomes.win_rate,  # preserve P(return>0) -- do NOT overwrite with prob_target
            avg_win_loss_ratio=base_outcomes.avg_win_loss_ratio,
            kelly_fraction=min(0.25, base_outcomes.kelly_fraction * adjustment_factor),
            recommended_hold_days=base_outcomes.recommended_hold_days,
            outcome_distribution=base_outcomes.outcome_distribution,
            # ------ 5d ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
            win_rate_5d=adj_wr_5d,
            expected_value_5d=adj_ev_5d,
            prob_up_5pct_5d=min(0.95, base_outcomes.prob_up_5pct_5d * adjustment_factor) if base_outcomes.prob_up_5pct_5d > 0 else 0.0,
            median_gain_if_up_5d=base_outcomes.median_gain_if_up_5d * adjustment_factor,
            median_loss_if_down_5d=base_outcomes.median_loss_if_down_5d,
            median_max_drawdown_5d=base_outcomes.median_max_drawdown_5d,
            sharpe_ratio_5d=base_outcomes.sharpe_ratio_5d * adjustment_factor,
            # ------ 10d ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
            win_rate_10d=adj_wr_10d,
            expected_value_10d=adj_ev_10d,
            prob_up_7pct_10d=min(0.95, base_outcomes.prob_up_7pct_10d * adjustment_factor) if base_outcomes.prob_up_7pct_10d > 0 else 0.0,
            median_gain_if_up_10d=base_outcomes.median_gain_if_up_10d * adjustment_factor,
            median_loss_if_down_10d=base_outcomes.median_loss_if_down_10d,
            median_max_drawdown_10d=base_outcomes.median_max_drawdown_10d,
            sharpe_ratio_10d=base_outcomes.sharpe_ratio_10d * adjustment_factor,
            insufficient_data_reason=adjustment_summary,
        )
