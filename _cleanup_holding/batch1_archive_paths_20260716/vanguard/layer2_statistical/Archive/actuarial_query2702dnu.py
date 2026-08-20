"""
SIMPLIFIED Actuarial Query Engine
Matches state vectors to historical outcomes using Polygon database columns

UPDATED: Multi-horizon outcomes (5d, 10d, 20d) now computed and returned.
         Options layer uses win_rate_for_hold(hold_days) for accurate EV.
         All existing fields preserved — fully backward compatible.
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
        self.database_path = database_path or ACTUARIAL_DATABASE_PATH
        self.df = None
        self._has_5d_cols  = False
        self._has_10d_cols = False
        self._load_database()

    def _load_database(self):
        """Load actuarial database and detect available horizon columns."""
        # ── DEBUG: Show exactly which path Vanguard is using at runtime ──────
        print(f"[DEBUG] ACTUARIAL_DATABASE_PATH config value : {ACTUARIAL_DATABASE_PATH}")
        print(f"[DEBUG] ActuarialQueryEngine resolved path   : {self.database_path}")
        print(f"[DEBUG] Path exists on disk                  : {Path(self.database_path).exists() if self.database_path else False}")
        # ─────────────────────────────────────────────────────────────────────
        if not self.database_path or not Path(self.database_path).exists():
            print(f"Warning: Could not load actuarial database from {self.database_path}")
            self.df = None
            return
        try:
            self.df = pd.read_parquet(self.database_path)
            # Detect whether multi-horizon columns have been added
            self._has_5d_cols  = "outcome_5d_return"  in self.df.columns
            self._has_10d_cols = "outcome_10d_return" in self.df.columns
            horizon_info = []
            if self._has_5d_cols:  horizon_info.append("5d")
            if self._has_10d_cols: horizon_info.append("10d")
            horizon_info.append("20d")
            print(f"✓ Loaded actuarial database: {len(self.df):,} observations "
                  f"| Horizons: {', '.join(horizon_info)}")
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

        return adjusted_outcomes if adjusted_outcomes is not None else base_outcomes

    def _find_similar_states(self, state: StateVector) -> pd.DataFrame:
        """
        Find historical states matching current state.
        Uses Polygon database columns: vol_regime, trend_direction,
        trend_maturity, structure_quality.
        """
        df = self.df.copy()

        df = df[df['vol_regime'] == state.vol_regime]
        df = df[df['trend_direction'] == state.trend_direction]

        if state.trend_maturity != "N/A":
            df = df[df['trend_maturity'].isin([state.trend_maturity, "N/A"])]

        if state.structure_quality != "NEUTRAL":
            df = df[df['structure_quality'].isin([state.structure_quality, "NEUTRAL"])]

        # FIX: catalyst_proximity is baked into the state hash — must also filter here
        if hasattr(state, 'catalyst_proximity') and state.catalyst_proximity:
            df = df[df['catalyst_proximity'] == state.catalyst_proximity]

        # TIGHTER STATE: adx_bucket — filter by trend strength regime
        # Prevents weak-trend rows mixing with strong-trend rows in same hash bucket
        if 'adx_bucket' in df.columns:
            from .state_calculator import StateVectorCalculator
            adx_bucket = StateVectorCalculator._adx_bucket(getattr(state, 'adx', 0))
            df = df[df['adx_bucket'] == adx_bucket]

        # TIGHTER STATE: atr_pct_bucket — filter by volatility intensity
        # Prevents low-vol setups pooling with high-vol setups in same regime
        if 'atr_pct_bucket' in df.columns:
            from .state_calculator import StateVectorCalculator
            atr_bucket = StateVectorCalculator._atr_percentile_bucket(
                getattr(state, 'atr_percentile', 50)
            )
            df = df[df['atr_pct_bucket'] == atr_bucket]

        # ── DEBUG: Show match count after all filters ─────────────────────────
        print(f"[DEBUG] _find_similar_states filters applied:")
        print(f"        vol_regime={state.vol_regime}, trend_direction={state.trend_direction}, "
              f"trend_maturity={state.trend_maturity}, structure_quality={state.structure_quality}, "
              f"catalyst_proximity={getattr(state, 'catalyst_proximity', 'N/A')}, "
              f"adx={getattr(state, 'adx', 'N/A')}, "
              f"atr_pct={getattr(state, 'atr_percentile', 'N/A')}")
        print(f"        Matches: {len(df)}")
        # ─────────────────────────────────────────────────────────────────────

        return df

    def _calculate_outcomes(self, similar_states: pd.DataFrame) -> ActuarialOutcomes:
        """
        Calculate probabilistic outcomes from similar historical states.
        Computes all available horizons (5d, 10d, 20d).
        """
        n_obs = len(similar_states)

        # ── 20-DAY OUTCOMES (always available) ────────────────────────────────
        prob_up_10pct    = similar_states['outcome_hit_10pct_up'].mean()
        prob_down_5pct   = similar_states['outcome_hit_5pct_down_before_10up'].mean()
        prob_trend_cont  = (similar_states['outcome_20d_return'] > 0).mean()

        wins_20d = similar_states[similar_states['outcome_20d_return'] > 0]
        loss_20d = similar_states[similar_states['outcome_20d_return'] <= 0]

        median_gain_20d     = wins_20d['outcome_20d_return'].median() if len(wins_20d) > 0 else 0.05
        median_loss_20d     = loss_20d['outcome_20d_return'].median() if len(loss_20d) > 0 else -0.03
        median_drawdown_20d = similar_states['outcome_max_drawdown_20d'].median()
        median_days         = similar_states['outcome_days_to_10pct'].median()

        ev_20d   = (prob_up_10pct * median_gain_20d) + ((1 - prob_up_10pct) * median_loss_20d)
        rets_20d = similar_states['outcome_20d_return']
        sharpe_20d = (rets_20d.mean() / rets_20d.std()) if rets_20d.std() > 0 else 0.0
        win_rate_20d = (rets_20d > 0).mean()

        avg_win_20d  = wins_20d['outcome_20d_return'].mean() if len(wins_20d) > 0 else 0.05
        avg_loss_20d = abs(loss_20d['outcome_20d_return'].mean()) if len(loss_20d) > 0 else 0.03
        win_loss_ratio = avg_win_20d / avg_loss_20d if avg_loss_20d > 0 else 1.0

        kelly = (prob_up_10pct * avg_win_20d - (1 - prob_up_10pct) * avg_loss_20d) / avg_win_20d if avg_win_20d > 0 else 0.1
        kelly = max(0.0, min(kelly, 0.25))

        recommended_hold = int(median_days) if prob_up_10pct > 0.5 else 20
        outcome_dist     = similar_states['outcome_category'].value_counts(normalize=True).to_dict()
        confidence       = min(1.0, n_obs / 50)

        # ── 5-DAY OUTCOMES (available after database upgrade) ─────────────────
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

        # ── 10-DAY OUTCOMES (available after database upgrade) ────────────────
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

        return ActuarialOutcomes(
            # ── 20d (original fields) ─────────────────────────────────────────
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
            # ── 5d (new) ──────────────────────────────────────────────────────
            win_rate_5d=wr_5d,
            expected_value_5d=ev_5d,
            prob_up_5pct_5d=prob_5pct_5d,
            median_gain_if_up_5d=med_gain_5d,
            median_loss_if_down_5d=med_loss_5d,
            median_max_drawdown_5d=med_dd_5d,
            sharpe_ratio_5d=sharpe_5d,
            # ── 10d (new) ─────────────────────────────────────────────────────
            win_rate_10d=wr_10d,
            expected_value_10d=ev_10d,
            prob_up_7pct_10d=prob_7pct_10d,
            median_gain_if_up_10d=med_gain_10d,
            median_loss_if_down_10d=med_loss_10d,
            median_max_drawdown_10d=med_dd_10d,
            sharpe_ratio_10d=sharpe_10d,
        )

    def _adjust_for_intraday_context(self, base_outcomes: ActuarialOutcomes, state: StateVector) -> ActuarialOutcomes:
        """
        HYBRID APPROACH: Adjust daily database probabilities based on intraday context.
        Adjustments applied uniformly across all horizons.
        """
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
            adjustment_notes.append(f"EV20d: {base_outcomes.expected_value_20d:.1%} → {adj_ev_20d:.1%} ({ev_change:+.0f}%)")

        adjustment_summary = f"{adjustment_factor:.2f}x: " + ", ".join(adjustment_notes) if adjustment_notes else None

        return ActuarialOutcomes(
            # ── 20d ───────────────────────────────────────────────────────────
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
            win_rate=prob_target,
            avg_win_loss_ratio=base_outcomes.avg_win_loss_ratio,
            kelly_fraction=min(0.25, base_outcomes.kelly_fraction * adjustment_factor),
            recommended_hold_days=base_outcomes.recommended_hold_days,
            outcome_distribution=base_outcomes.outcome_distribution,
            # ── 5d ────────────────────────────────────────────────────────────
            win_rate_5d=adj_wr_5d,
            expected_value_5d=adj_ev_5d,
            prob_up_5pct_5d=min(0.95, base_outcomes.prob_up_5pct_5d * adjustment_factor) if base_outcomes.prob_up_5pct_5d > 0 else 0.0,
            median_gain_if_up_5d=base_outcomes.median_gain_if_up_5d * adjustment_factor,
            median_loss_if_down_5d=base_outcomes.median_loss_if_down_5d,
            median_max_drawdown_5d=base_outcomes.median_max_drawdown_5d,
            sharpe_ratio_5d=base_outcomes.sharpe_ratio_5d * adjustment_factor,
            # ── 10d ───────────────────────────────────────────────────────────
            win_rate_10d=adj_wr_10d,
            expected_value_10d=adj_ev_10d,
            prob_up_7pct_10d=min(0.95, base_outcomes.prob_up_7pct_10d * adjustment_factor) if base_outcomes.prob_up_7pct_10d > 0 else 0.0,
            median_gain_if_up_10d=base_outcomes.median_gain_if_up_10d * adjustment_factor,
            median_loss_if_down_10d=base_outcomes.median_loss_if_down_10d,
            median_max_drawdown_10d=base_outcomes.median_max_drawdown_10d,
            sharpe_ratio_10d=base_outcomes.sharpe_ratio_10d * adjustment_factor,
            insufficient_data_reason=adjustment_summary,
        )
