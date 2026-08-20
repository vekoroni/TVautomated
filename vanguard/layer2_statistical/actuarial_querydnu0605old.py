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


def _empty_outcomes() -> ActuarialOutcomes:
    """Return a safe, fail-closed ActuarialOutcomes - NEVER returns None"""
    return ActuarialOutcomes(
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
            self.df = pd.read_parquet(self.database_path)
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
            _v6_str = "v6 ✅ future_momentum_bucket" if self._has_v6_cols else "v5 ⚠️  no future_momentum_bucket"
            _aq_log.info(
                "ActuarialDB loaded: %d rows | horizons=%s | %s | %s",
                len(self.df), ",".join(horizon_info), _v6_str,
                self.database_path
            )
            print(f"[OK] Loaded actuarial database: {len(self.df):,} observations "
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

        if similar_states is None or len(similar_states) < 10:
            return _empty_outcomes()

        try:
            base_outcomes = self._calculate_outcomes(similar_states)
        except Exception as e:
            print(f"  Warning: _calculate_outcomes failed: {e}")
            return _empty_outcomes()

        if base_outcomes is None:
            return _empty_outcomes()

        try:
            adjusted_outcomes = self._adjust_for_intraday_context(base_outcomes, state)
        except Exception as e:
            print(f"  Warning: _adjust_for_intraday_context failed: {e}")
            return base_outcomes

        final_outcomes = adjusted_outcomes if adjusted_outcomes is not None else base_outcomes

        # =========================
        # SPRINT 2: ATTACH SIGNAL TYPE + FORWARD MOMENTUM CONFIDENCE
        # =========================
        # signal_type is now a declared field on ActuarialOutcomes (not dynamic).
        # forward_momentum_confidence quantifies what % of matching DB rows had
        # accelerating momentum (momentum_delta > 0) - a quality filter for sizing.

        _attrs           = getattr(similar_states, 'attrs', {})
        _signal_type     = _attrs.get('signal_type', 'NO_EDGE')
        final_outcomes.signal_type = _signal_type

        # Match-method audit fields — read from DataFrame attrs set by _tag_match().
        # Surfaced explicitly by main.py into layer_2_result.
        # A HIGH_SAMPLE from CORE_4D_FALLBACK must not be treated as high-conviction
        # evidence by EIL, PSE, or MVE. These fields make that distinction auditable.
        final_outcomes.state_match_method     = _attrs.get("state_match_method",     "UNKNOWN")
        final_outcomes.state_match_stage      = _attrs.get("state_match_stage",      "UNKNOWN")
        final_outcomes.state_match_dimensions = _attrs.get("state_match_dimensions", "")
        final_outcomes.state_match_quality    = _attrs.get("state_match_quality",    "UNKNOWN")
        final_outcomes.state_match_is_exact   = bool(_attrs.get("state_match_is_exact", False))

        # Forward momentum confidence: fraction of matching rows where future bucket
        # is HIGHER than current bucket (genuine acceleration).
        # Prefers future_momentum_bucket (v6 DB) over raw momentum_delta.
        # Ranges 0.0-1.0. Higher = more DB rows had accelerating momentum.
        _fwd_conf = 0.0
        if _signal_type != 'NO_EDGE' and len(similar_states) > 0:
            if 'future_momentum_bucket' in similar_states.columns and 'momentum_bucket' in similar_states.columns:
                # Bucket order for comparison
                _bucket_rank = {"LOW": 0, "MID": 1, "HIGH": 2, "EXTREME": 3}
                _curr_rank = similar_states['momentum_bucket'].map(_bucket_rank).fillna(0)
                _fut_rank  = similar_states['future_momentum_bucket'].map(_bucket_rank).fillna(0)
                _fwd_conf  = float((_fut_rank > _curr_rank).mean())
            elif 'momentum_delta' in similar_states.columns:
                # Fallback: raw delta > 0
                _fwd_conf = float((similar_states['momentum_delta'] > 0).mean())
        final_outcomes.forward_momentum_confidence = _fwd_conf

        # Also attach momentum_tier for position_sizing_v2_patch
        final_outcomes.momentum_tier = _attrs.get('momentum_tier', 'TIER_4_FLAT')

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
        if extra_attrs:
            for k, v in extra_attrs.items():
                tagged.attrs[k] = v
        return tagged

    def _find_similar_states(self, state: StateVector) -> pd.DataFrame:
        """
        Find historical states matching current state.

        THREE-STAGE matching strategy:

        Stage 0 — V2 Signal-Type Match (NEW — preferred when DB has v2 columns):
          Runs two separate V2 queries based on phase_v2 + momentum_bucket + location_bucket.
          CONTINUATION: phase_v2=CONTINUATION, momentum HIGH/EXTREME, not NEAR_HIGH
          TRANSITION:   phase_v2=EARLY_TRANSITION, momentum LOW/MID, NEAR_LOW/TRANSITION_ZONE
          Returns if matches >= 10, attaches signal_type to result df attrs.

        Stage 1 — Full 7-dimension match (fallback when v2 columns absent/empty):
          vol_regime + trend_direction + trend_maturity + structure_quality
          + catalyst_proximity + atr_pct_bucket + adx_bucket
          Returns if matches >= 1.

        Stage 2 — Core 4-dimension match (floor fallback):
          vol_regime + trend_direction + trend_maturity + structure_quality
          Pre-bucket behaviour — used when bucket columns do not exist in DB.
        """
        df = self.df.copy()

        # =========================
        # NEW: SIGNAL TYPE DETECTION  (Stage 0)
        # =========================

        _has_v2_cols = (
            'phase_v2'         in df.columns and
            'momentum_bucket'  in df.columns and
            'location_bucket'  in df.columns
        )

        _phase_v2   = getattr(state, 'phase_v2',   None)
        _mom_bucket = getattr(state, 'momentum_bucket', None)
        _loc_bucket = getattr(state, 'location_bucket', None)

        if _has_v2_cols and _phase_v2 and _mom_bucket and _loc_bucket:

            # -- CONTINUATION signal ---------------------------------------------
            # v6 DB: uses future_momentum_bucket for exact bucket-transition
            # classification. Tiers ranked by conviction (highest first).
            # Falls back through delta filter - base filter if v6 col absent.
            #
            # TIER 1 EXPLOSIVE  : HIGH/EXTREME - EXTREME  (100% size)
            # TIER 2 SUSTAINING : HIGH         - HIGH     (100% size)
            # TIER 3 BUILDING   : MID          - HIGH/EXTREME (85% size)
            # TIER 4 FLAT       : MID          - MID      (70% size)
            # INVALID (skip)    : HIGH/EXTREME - MID/LOW  (fading - do not enter)
            if (
                _phase_v2 == "CONTINUATION" and
                _mom_bucket in ("HIGH", "EXTREME") and
                _loc_bucket != "NEAR_HIGH"
            ):
                _has_fmb = 'future_momentum_bucket' in df.columns

                _base_mask = (
                    (df['phase_v2'] == "CONTINUATION") &
                    (df['momentum_bucket'].isin(["HIGH", "EXTREME"])) &
                    (df['location_bucket'] != "NEAR_HIGH")
                )

                if _has_fmb:
                    # -- Skip FADING rows entirely (HIGH/EXTREME - MID/LOW) ----
                    # These are in the DB but represent decelerating momentum.
                    # Pooling them with sustaining rows dilutes the edge.
                    _valid_mask = _base_mask & (
                        ~df['future_momentum_bucket'].isin(["MID", "LOW"])
                    )

                    # TIER 1: HIGH/EXTREME - EXTREME (explosive)
                    t1 = df[_valid_mask & df['future_momentum_bucket'].isin(["EXTREME"])]
                    if len(t1) >= 10:
                        return self._tag_match(
                            t1,
                            method="V2_CONTINUATION_TIER_1_EXPLOSIVE",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket"],
                            quality="HIGH",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":           "CONTINUATION",
                                "momentum_tier":         "TIER_1_EXPLOSIVE",
                                "momentum_accelerating": True,
                            },
                        )

                    # TIER 2: HIGH - HIGH (sustaining)
                    t2 = df[_valid_mask & (df['momentum_bucket'] == "HIGH") &
                            (df['future_momentum_bucket'] == "HIGH")]
                    if len(t2) >= 10:
                        return self._tag_match(
                            t2,
                            method="V2_CONTINUATION_TIER_2_SUSTAINING",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket"],
                            quality="HIGH",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":           "CONTINUATION",
                                "momentum_tier":         "TIER_2_SUSTAINING",
                                "momentum_accelerating": True,
                            },
                        )

                    # TIER 3: MID - HIGH/EXTREME (building) - widen base to MID
                    _base_mid_mask = (
                        (df['phase_v2'] == "CONTINUATION") &
                        (df['momentum_bucket'].isin(["MID", "HIGH", "EXTREME"])) &
                        (df['location_bucket'] != "NEAR_HIGH")
                    )
                    t3 = df[_base_mid_mask &
                            (df['momentum_bucket'] == "MID") &
                            df['future_momentum_bucket'].isin(["HIGH", "EXTREME"])]
                    if len(t3) >= 10:
                        return self._tag_match(
                            t3,
                            method="V2_CONTINUATION_TIER_3_BUILDING",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket"],
                            quality="MEDIUM",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":           "CONTINUATION",
                                "momentum_tier":         "TIER_3_BUILDING",
                                "momentum_accelerating": True,
                            },
                        )

                    # TIER 4: MID - MID (flat continuation) - reduced sizing
                    t4 = df[_base_mid_mask &
                            (df['momentum_bucket'] == "MID") &
                            (df['future_momentum_bucket'] == "MID")]
                    if len(t4) >= 10:
                        return self._tag_match(
                            t4,
                            method="V2_CONTINUATION_TIER_4_FLAT",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket"],
                            quality="LOW",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":           "CONTINUATION",
                                "momentum_tier":         "TIER_4_FLAT",
                                "momentum_accelerating": False,
                            },
                        )

                    # Fallback: all valid (non-fading) CONTINUATION rows
                    if len(s0_valid) >= 10:
                        return self._tag_match(
                            s0_valid,
                            method="V2_CONTINUATION_VALID_FALLBACK",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket"],
                            quality="LOW",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":           "CONTINUATION",
                                "momentum_tier":         "TIER_4_FLAT",
                                "momentum_accelerating": False,
                            },
                        )

                else:
                    # No future_momentum_bucket col - fall back to delta filter
                    _has_delta = 'momentum_delta' in df.columns
                    if _has_delta:
                        s0_accel = df[_base_mask & (df['momentum_delta'] > 0)]
                        if len(s0_accel) >= 10:
                            return self._tag_match(
                                s0_accel,
                                method="V2_CONTINUATION_TIER_2_SUSTAINING",
                                stage="STAGE_0_V2_SIGNAL_TYPE",
                                dimensions=["phase_v2", "momentum_bucket", "location_bucket", "momentum_delta"],
                                quality="MEDIUM",
                                is_exact=False,
                                extra_attrs={
                                    "signal_type":           "CONTINUATION",
                                    "momentum_tier":         "TIER_2_SUSTAINING",
                                    "momentum_accelerating": True,
                                },
                            )

                    # Base fallback (Sprint 1) — no future_momentum_bucket column
                    s0 = df[_base_mask]
                    if len(s0) >= 10:
                        return self._tag_match(
                            s0,
                            method="V2_CONTINUATION_BASE_FALLBACK",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket"],
                            quality="LOW",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":           "CONTINUATION",
                                "momentum_tier":         "TIER_4_FLAT",
                                "momentum_accelerating": False,
                            },
                        ) 
            # -- TRANSITION signal
            # Only enter TRANSITION when momentum is genuinely GAINING.
            #
            # TIER 1 ACCELERATING : LOW - HIGH  (skips MID - strong signal, 60% size)
            # TIER 2 BUILDING     : LOW - MID   (standard probe, 50% size)
            # SKIP                : LOW - LOW   (no momentum building - noise)
            elif (
                _phase_v2 == "EARLY_TRANSITION" and
                _mom_bucket in ("LOW", "MID") and
                _loc_bucket in ("TRANSITION_ZONE", "NEAR_LOW")
            ):
                _has_fmb   = 'future_momentum_bucket' in df.columns
                _has_tfv2  = 'transition_flag_v2' in df.columns
                _has_adxd  = 'adx_delta' in df.columns

                _base_trans_mask = (
                    (df['phase_v2'] == "EARLY_TRANSITION") &
                    (df['momentum_bucket'].isin(["LOW", "MID"])) &
                    (df['location_bucket'].isin(["TRANSITION_ZONE", "NEAR_LOW"]))
                )

                # Apply flag cross-check where available
                if _has_tfv2:
                    _base_trans_mask = _base_trans_mask & (df['transition_flag_v2'] == 1)

                if _has_fmb:
                    # -- Skip LOW - LOW rows (no momentum building) ------------
                    _valid_trans = _base_trans_mask & (
                        ~((df['momentum_bucket'] == "LOW") &
                          (df['future_momentum_bucket'] == "LOW"))
                    )

                    # TIER 1: LOW - HIGH (momentum skipping a bucket)
                    t1_trans = df[_valid_trans &
                                  (df['momentum_bucket'] == "LOW") &
                                  (df['future_momentum_bucket'] == "HIGH")]
                    if len(t1_trans) >= 10:
                        return self._tag_match(
                            t1_trans,
                            method="V2_TRANSITION_TIER_1_ACCELERATING",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket", "transition_flag_v2"],
                            quality="HIGH",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":   "TRANSITION",
                                "momentum_tier": "TIER_1_ACCELERATING",
                                "adx_building":  True,
                            },
                        )

                    # TIER 2: LOW - MID (standard build)
                    t2_trans = df[_valid_trans &
                                  (df['momentum_bucket'] == "LOW") &
                                  (df['future_momentum_bucket'] == "MID")]
                    # Further refine with adx_delta if available
                    if _has_adxd and len(t2_trans) >= 10:
                        t2_adx = t2_trans[t2_trans['adx_delta'] > 0]
                        if len(t2_adx) >= 10:
                            return self._tag_match(
                                t2_adx,
                                method="V2_TRANSITION_TIER_2_BUILDING_ADX",
                                stage="STAGE_0_V2_SIGNAL_TYPE",
                                dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket", "transition_flag_v2", "adx_delta"],
                                quality="MEDIUM",
                                is_exact=False,
                                extra_attrs={
                                    "signal_type":   "TRANSITION",
                                    "momentum_tier": "TIER_2_BUILDING",
                                    "adx_building":  True,
                                },
                            )
                    if len(t2_trans) >= 10:
                        return self._tag_match(
                            t2_trans,
                            method="V2_TRANSITION_TIER_2_BUILDING",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket", "transition_flag_v2"],
                            quality="MEDIUM",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":   "TRANSITION",
                                "momentum_tier": "TIER_2_BUILDING",
                                "adx_building":  False,
                            },
                        )

                    # Fallback: all valid TRANSITION rows (any future bucket)
                    if len(s0_trans) >= 10:
                        return self._tag_match(
                            s0_trans,
                            method="V2_TRANSITION_VALID_FALLBACK",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket", "future_momentum_bucket", "transition_flag_v2"],
                            quality="LOW",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":   "TRANSITION",
                                "momentum_tier": "TIER_2_BUILDING",
                                "adx_building":  False,
                            },
                        )

                else:
                    # No future_momentum_bucket - fall back to adx_delta + flag
                    if _has_adxd:
                        s0_adx = df[_base_trans_mask & (df['adx_delta'] > 0)]
                        if len(s0_adx) >= 10:
                            return self._tag_match(
                                s0_adx,
                                method="V2_TRANSITION_ADX_FALLBACK",
                                stage="STAGE_0_V2_SIGNAL_TYPE",
                                dimensions=["phase_v2", "momentum_bucket", "location_bucket", "adx_delta"],
                                quality="MEDIUM",
                                is_exact=False,
                                extra_attrs={
                                    "signal_type":   "TRANSITION",
                                    "momentum_tier": "TIER_2_BUILDING",
                                    "adx_building":  True,
                                },
                            )

                    # Base fallback (Sprint 1) — no future_momentum_bucket column
                    s0 = df[_base_trans_mask]
                    if len(s0) >= 10:
                        return self._tag_match(
                            s0,
                            method="V2_TRANSITION_BASE_FALLBACK",
                            stage="STAGE_0_V2_SIGNAL_TYPE",
                            dimensions=["phase_v2", "momentum_bucket", "location_bucket"],
                            quality="LOW",
                            is_exact=False,
                            extra_attrs={
                                "signal_type":   "TRANSITION",
                                "momentum_tier": "TIER_2_BUILDING",
                                "adx_building":  False,
                            },
                        )

        # -- STAGE 1: Full discriminated match --------------------------------
        s1 = df.copy()
        s1 = s1[s1['vol_regime'] == state.vol_regime]
        s1 = s1[s1['trend_direction'] == state.trend_direction]

        if state.trend_maturity not in ("N/A", None, ""):
            s1 = s1[s1['trend_maturity'].isin([state.trend_maturity, "N/A"])]

        if state.structure_quality != "NEUTRAL":
            s1 = s1[s1['structure_quality'].isin([state.structure_quality, "NEUTRAL"])]

        if hasattr(state, 'catalyst_proximity') and state.catalyst_proximity:
            s1 = s1[s1['catalyst_proximity'] == state.catalyst_proximity]

        if 'atr_pct_bucket' in s1.columns and hasattr(state, 'atr_pct_bucket') and state.atr_pct_bucket:
            s1 = s1[s1['atr_pct_bucket'] == state.atr_pct_bucket]

        if 'adx_bucket' in s1.columns and hasattr(state, 'adx_bucket') and state.adx_bucket:
            s1 = s1[s1['adx_bucket'] == state.adx_bucket]

        wyckoff_bucket = getattr(state, 'wyckoff_phase_bucket', None)
        if ('wyckoff_phase_bucket' in s1.columns
                and wyckoff_bucket
                and wyckoff_bucket != 'UNKNOWN'):
            s1 = s1[s1['wyckoff_phase_bucket'] == wyckoff_bucket]

        macro_regime_state = getattr(state, 'macro_regime', None)
        if ('macro_regime' in s1.columns
                and macro_regime_state
                and macro_regime_state != 'TRANSITIONAL'):
            s1 = s1[s1['macro_regime'].isin([macro_regime_state, 'TRANSITIONAL'])]

        if len(s1) >= 1:
            return self._tag_match(
                s1,
                method="FULL_DISCRIMINATED_MATCH",
                stage="STAGE_1_FULL_7D_MATCH",
                dimensions=[
                    "vol_regime", "trend_direction", "trend_maturity",
                    "structure_quality", "catalyst_proximity",
                    "atr_pct_bucket", "adx_bucket",
                    "wyckoff_phase_bucket", "macro_regime",
                ],
                quality="MEDIUM",
                is_exact=False,
                extra_attrs={
                    "signal_type":   "STRUCTURAL_MATCH",
                    "momentum_tier": "N/A",
                },
            )

        # -- STAGE 2: Core 4-dimension fallback -------------------------------
        s2 = df.copy()
        s2 = s2[s2['vol_regime'] == state.vol_regime]
        s2 = s2[s2['trend_direction'] == state.trend_direction]

        if state.trend_maturity not in ("N/A", None, ""):
            s2 = s2[s2['trend_maturity'].isin([state.trend_maturity, "N/A"])]

        if state.structure_quality != "NEUTRAL":
            s2 = s2[s2['structure_quality'].isin([state.structure_quality, "NEUTRAL"])]

        return self._tag_match(
            s2,
            method="CORE_4D_FALLBACK",
            stage="STAGE_2_CORE_FALLBACK",
            dimensions=[
                "vol_regime", "trend_direction",
                "trend_maturity", "structure_quality",
            ],
            quality="LOW",
            is_exact=False,
            extra_attrs={
                "signal_type":   "BROAD_FALLBACK",
                "momentum_tier": "N/A",
            },
        )
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

