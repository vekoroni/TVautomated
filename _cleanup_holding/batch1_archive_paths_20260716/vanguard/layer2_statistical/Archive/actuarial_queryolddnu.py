"""
SIMPLIFIED Actuarial Query Engine
Matches state vectors to historical outcomes using Polygon database columns
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
    Query historical database for state-specific probabilities
    SIMPLIFIED VERSION - works with Polygon-built database
    FIXED: query() NEVER returns None
    """

    def __init__(self, database_path: str = None):
        self.database_path = database_path or ACTUARIAL_DATABASE_PATH
        self.df = None
        self._load_database()

    def _load_database(self):
        """Load actuarial database"""
        if not self.database_path or not Path(self.database_path).exists():
            print(f"Warning: Could not load actuarial database from {self.database_path}")
            self.df = None
            return
        try:
            self.df = pd.read_parquet(self.database_path)
            print(f"✓ Loaded actuarial database: {len(self.df)} observations")
        except Exception as e:
            print(f"Warning: Could not load actuarial database: {e}")
            self.df = None

    def query(self, state: StateVector) -> ActuarialOutcomes:
        """
        Query database for historical outcomes matching this state
        WITH HYBRID ADJUSTMENTS based on intraday context

        Args:
            state: Current state vector (with intraday context)

        Returns:
            ActuarialOutcomes with ADJUSTED probabilities (NEVER None)
        """
        # Guard 1: Database not loaded or empty
        if self.df is None or len(self.df) == 0:
            return _empty_outcomes()

        # Find similar states (daily database)
        try:
            similar_states = self._find_similar_states(state)
        except Exception as e:
            print(f"  Warning: _find_similar_states failed: {e}")
            return _empty_outcomes()

        # Guard 2: Not enough matches
        if similar_states is None or len(similar_states) < 10:
            return _empty_outcomes()

        # Calculate BASE outcomes from daily database
        try:
            base_outcomes = self._calculate_outcomes(similar_states)
        except Exception as e:
            print(f"  Warning: _calculate_outcomes failed: {e}")
            return _empty_outcomes()

        if base_outcomes is None:
            return _empty_outcomes()

        # ADJUST probabilities based on intraday context
        try:
            adjusted_outcomes = self._adjust_for_intraday_context(base_outcomes, state)
        except Exception as e:
            print(f"  Warning: _adjust_for_intraday_context failed: {e}")
            return base_outcomes  # Return base if adjustment fails

        if adjusted_outcomes is None:
            return base_outcomes

        return adjusted_outcomes

    def _find_similar_states(self, state: StateVector) -> pd.DataFrame:
        """
        Find historical states matching current state
        Uses Polygon database columns: vol_regime, trend_direction,
        trend_maturity, structure_quality
        """
        df = self.df.copy()

        # Filter by vol regime (exact match)
        df = df[df['vol_regime'] == state.vol_regime]

        # Filter by trend direction (exact match)
        df = df[df['trend_direction'] == state.trend_direction]

        # Filter by trend maturity (exact match or N/A)
        if state.trend_maturity != "N/A":
            df = df[df['trend_maturity'].isin([state.trend_maturity, "N/A"])]

        # Filter by structure quality (wider match)
        if state.structure_quality != "NEUTRAL":
            df = df[df['structure_quality'].isin([state.structure_quality, "NEUTRAL"])]

        return df

    def _calculate_outcomes(self, similar_states: pd.DataFrame) -> ActuarialOutcomes:
        """Calculate probabilistic outcomes from similar historical states"""
        n_obs = len(similar_states)

        # Core probabilities
        prob_up_10pct = similar_states['outcome_hit_10pct_up'].mean()
        prob_down_5pct_first = similar_states['outcome_hit_5pct_down_before_10up'].mean()

        # Trend continuation
        prob_trend_continues = (similar_states['outcome_20d_return'] > 0).mean()

        # Magnitude expectations
        winning_trades = similar_states[similar_states['outcome_20d_return'] > 0]
        losing_trades = similar_states[similar_states['outcome_20d_return'] <= 0]

        median_gain_if_up = winning_trades['outcome_20d_return'].median() if len(winning_trades) > 0 else 0.05
        median_loss_if_down = losing_trades['outcome_20d_return'].median() if len(losing_trades) > 0 else -0.03
        median_max_drawdown = similar_states['outcome_max_drawdown_20d'].median()
        median_days_to_target = similar_states['outcome_days_to_10pct'].median()

        # Expected value
        ev = (prob_up_10pct * median_gain_if_up) + ((1 - prob_up_10pct) * median_loss_if_down)

        # Sharpe ratio
        returns = similar_states['outcome_20d_return']
        sharpe = (returns.mean() / returns.std()) if returns.std() > 0 else 0

        # Win rate
        win_rate = (similar_states['outcome_20d_return'] > 0).mean()

        # Win/loss ratio
        avg_win = winning_trades['outcome_20d_return'].mean() if len(winning_trades) > 0 else 0.05
        avg_loss = abs(losing_trades['outcome_20d_return'].mean()) if len(losing_trades) > 0 else 0.03
        avg_win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1.0

        # Kelly fraction
        kelly = (prob_up_10pct * avg_win - (1 - prob_up_10pct) * avg_loss) / avg_win if avg_win > 0 else 0.1
        kelly = max(0, min(kelly, 0.25))

        # Recommended hold days
        recommended_hold = int(median_days_to_target) if prob_up_10pct > 0.5 else 20

        # Outcome distribution
        outcome_dist = similar_states['outcome_category'].value_counts(normalize=True).to_dict()

        # Confidence level
        confidence = min(1.0, n_obs / 50)

        return ActuarialOutcomes(
            n_observations=n_obs,
            confidence_level=confidence,
            lookback_period="3Y",
            prob_up_10pct_20d=prob_up_10pct,
            prob_down_5pct_before_up_10pct=prob_down_5pct_first,
            prob_trend_continues_20d=prob_trend_continues,
            median_gain_if_up=median_gain_if_up,
            median_loss_if_down=median_loss_if_down,
            median_max_drawdown=median_max_drawdown,
            median_days_to_target=median_days_to_target,
            expected_value_20d=ev,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
            avg_win_loss_ratio=avg_win_loss_ratio,
            kelly_fraction=kelly,
            recommended_hold_days=recommended_hold,
            outcome_distribution=outcome_dist,
            insufficient_data_reason=None
        )

    def _adjust_for_intraday_context(self, base_outcomes: ActuarialOutcomes, state: StateVector) -> ActuarialOutcomes:
        """
        HYBRID APPROACH: Adjust daily database probabilities based on intraday context
        """
        adj_prob_up = base_outcomes.prob_up_10pct_20d
        adj_prob_down_first = base_outcomes.prob_down_5pct_before_up_10pct
        adj_ev = base_outcomes.expected_value_20d

        intraday_position = getattr(state, 'intraday_position', 'UNKNOWN')
        volume_context = getattr(state, 'volume_profile_context', 'BALANCED')
        control_dynamics = getattr(state, 'control_dynamics', 'NEUTRAL')

        adjustment_factor = 1.0
        adjustment_notes = []

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

        # Cap adjustments
        adjustment_factor = max(0.4, min(adjustment_factor, 2.5))

        # Apply probability adjustments
        adj_prob_up = min(0.95, adj_prob_up * adjustment_factor)

        if adjustment_factor > 1.0:
            adj_prob_down_first = adj_prob_down_first * (1 / (1 + (adjustment_factor - 1) * 0.5))
        else:
            adj_prob_down_first = min(0.95, adj_prob_down_first * (2 - adjustment_factor))

        # Triple-barrier EV recalculation
        prob_target = adj_prob_up
        prob_stop = adj_prob_down_first
        prob_expiry = max(0.0, 1.0 - prob_target - prob_stop)

        total_prob = prob_target + prob_stop + prob_expiry
        if total_prob > 1.0:
            prob_target = prob_target / total_prob
            prob_stop = prob_stop / total_prob
            prob_expiry = prob_expiry / total_prob

        gain_target = base_outcomes.median_gain_if_up * adjustment_factor
        loss_stop = base_outcomes.median_loss_if_down
        return_expiry = 0.0

        adj_ev = (prob_target * gain_target) + (prob_stop * loss_stop) + (prob_expiry * return_expiry)

        if adjustment_notes:
            ev_change_pct = ((adj_ev / base_outcomes.expected_value_20d) - 1) * 100 if base_outcomes.expected_value_20d != 0 else 0
            adjustment_notes.append(f"EV: {base_outcomes.expected_value_20d:.1%} → {adj_ev:.1%} ({ev_change_pct:+.0f}%)")

        adjustment_summary = f"{adjustment_factor:.2f}x: " + ", ".join(adjustment_notes) if adjustment_notes else None

        return ActuarialOutcomes(
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
            expected_value_20d=adj_ev,
            sharpe_ratio=base_outcomes.sharpe_ratio * adjustment_factor,
            win_rate=prob_target,
            avg_win_loss_ratio=base_outcomes.avg_win_loss_ratio,
            kelly_fraction=min(0.25, base_outcomes.kelly_fraction * adjustment_factor),
            recommended_hold_days=base_outcomes.recommended_hold_days,
            outcome_distribution=base_outcomes.outcome_distribution,
            insufficient_data_reason=adjustment_summary
        )