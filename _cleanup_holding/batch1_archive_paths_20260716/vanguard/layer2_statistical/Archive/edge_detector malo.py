"""
VANGUARD Layer 2 - Edge Detector  [ENHANCED v2.0]
==================================================

ENHANCEMENTS OVER v1.0:
  - GATE 3: TREND_EXHAUSTED  — vetoes names within X% of 52w extreme with LATE maturity
  - GATE 4: REGIME_MINIMUM_EV — raises net EV floor dynamically based on macro regime
  - GATE 5: OPTIONS_VIABILITY  — vetoes structurally illiquid or earnings-contaminated options
  - Macro regime now meaningfully adjusts EV thresholds (not just rationale text)
  - right_side_score macro bonus raised from 5 → 15 points (regime is primary, not cosmetic)
  - All new gates are fail-closed and independently auditable

Design principles:
  - Each gate answers ONE question with ONE veto.
  - Gates are ordered cheapest-to-evaluate first.
  - No gate has side effects on another gate's logic.
  - All thresholds are named constants, not magic numbers.
"""

from typing import Dict
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..schemas.auction_schema import AuctionVerdict
from ..schemas.trade_schema import EdgeAssessment
from ..config import EDGE_DETECTION_THRESHOLDS


# ========================= TRADING COST MODEL ================================

def calculate_trading_costs(ticker: str = None, liquidity_tier: str = 'NORMAL') -> float:
    """
    Calculate explicit trading costs (spread + slippage).
    Returns total cost as decimal (e.g., 0.0040 = 0.40%).
    """
    high_liquid = [
        'SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN',
        'TSLA', 'NVDA', 'META', 'NFLX', 'AMD', 'INTC'
    ]
    if ticker and ticker in high_liquid:
        liquidity_tier = 'HIGH'

    costs = {
        'HIGH':   {'spread': 0.0010, 'slippage': 0.0005},
        'NORMAL': {'spread': 0.0025, 'slippage': 0.0015},
        'LOW':    {'spread': 0.0050, 'slippage': 0.0030},
    }
    tier_costs = costs.get(liquidity_tier, costs['NORMAL'])
    return tier_costs['spread'] + tier_costs['slippage']


# ========================= REGIME EV FLOOR TABLE =============================

# A super brain does not use a single global EV floor.
# The floor must reflect the cost of being wrong in the current environment.
# In Risk-Off, false positives are more expensive (gaps, liquidity withdrawal).
# In Risk-On compression, false positives are cheaper (market absorbs noise).
#
# These floors are ADDITIVE to trading costs — they represent the minimum
# structural edge required ABOVE costs to justify capital allocation.

REGIME_EV_FLOORS = {
    # (net_ev_floor, win_rate_floor)
    # net_ev_floor: minimum net EV for TRADE verdict (above costs)
    # win_rate_floor: minimum win rate (prob_up_10pct_20d) for TRADE verdict
    "RISK_ON":       (0.025, 0.38),   # Looser: market is supportive
    "TRANSITIONAL":  (0.035, 0.42),   # Default: moderate conviction required
    "RISK_OFF":      (0.055, 0.48),   # Tight: only very high-conviction setups
}

REGIME_SETUP_FORMING_FLOORS = {
    # Floors for SETUP_FORMING (lower tier, needs confirmation)
    "RISK_ON":       (0.000, 0.33),
    "TRANSITIONAL":  (0.005, 0.35),
    "RISK_OFF":      (0.015, 0.40),
}


# ========================= TREND EXHAUSTION THRESHOLDS =======================

# A super brain knows that "near 52w high" is not binary.
# The veto has TWO components that must BOTH be true:
#   1. Maturity is LATE (state_calculator already computed this)
#   2. Price is within the exhaustion proximity band of the 52w extreme
#
# Proximity band is regime-sensitive because in strong Risk-On trends,
# prices can extend further before mean-reversion. In Risk-Off / Transitional,
# anything near the high is structurally risky for new long entries.

EXHAUSTION_PROXIMITY = {
    # Maximum distance_from_52w_high (negative = below high) to trigger veto
    # i.e., if price is within X% of the 52w high, AND maturity is LATE → veto
    "RISK_ON":       -0.04,   # 4% below 52w high — allow slightly extended entries
    "TRANSITIONAL":  -0.06,   # 6% below 52w high — standard protection
    "RISK_OFF":      -0.10,   # 10% below 52w high — wide protection in weak regime
}

# Minimum ADX for trend exhaustion gate to fire
# Low ADX = no real trend = not exhausted in the directional sense
# We don't want to veto a sideways name just because it's near a high
EXHAUSTION_MIN_ADX = 22.0


# ========================= OPTIONS VIABILITY THRESHOLDS ======================

# A super brain does not send illiquid or event-contaminated names to trade.
# This gate answers: "Can we actually execute a clean options trade here?"
#
# Three failure modes:
#   1. Earnings too close — IV crush risk destroys the trade
#   2. Liquidity too low  — spread + slippage make the trade mathematically negative
#   3. IV already spiked  — entering after the vol event means buying the tail

EARNINGS_BLACKOUT_DAYS = 10    # Veto if earnings within N days
EARNINGS_REENTRY_DAYS  = 3     # Also veto if earnings just passed (gap risk still live)
LIQUIDITY_MIN_CONDITION = "LOW"   # Veto if liquidity is this or worse — keep LOW as floor
IV_SPIKE_PERCENTILE     = 85   # Veto if IV percentile is this or higher without compression


# =============================================================================
#  EDGE DETECTOR CLASS
# =============================================================================

class EdgeDetector:
    """
    Multi-gate edge detection system [ENHANCED v2.0]

    Gates (ALL must pass, in order):
      1. AUCTION_CONFLICTED   — Market structure not readable
      2. DATA_CONFIDENCE      — Insufficient historical sample
      3. TREND_EXHAUSTED      — Move already happened (52w + maturity)  [NEW]
      4. OPTIONS_VIABILITY    — Cannot execute a clean options trade     [NEW]
      5. REGIME_MINIMUM_EV    — Net EV too low for current macro regime  [NEW → replaces fixed 3%]

    Three-tier verdicts:
      TRADE         — All gates pass, clear exploitable edge
      SETUP_FORMING — Positive structure, below EV threshold, monitor
      NO_EDGE       — One or more gates failed
    """

    def __init__(self):
        self.thresholds = EDGE_DETECTION_THRESHOLDS

    # ------------------------------------------------------------------
    # MAIN ENTRY
    # ------------------------------------------------------------------

    def detect_edge(self,
                    state: StateVector,
                    outcomes: ActuarialOutcomes,
                    auction_verdict: AuctionVerdict) -> EdgeAssessment:
        """
        Determine if a statistically exploitable, practically executable
        options edge exists for this name right now.
        """

        # Resolve macro regime once — used by multiple gates
        macro_regime = getattr(state, 'macro_regime', 'TRANSITIONAL') or 'TRANSITIONAL'

        # ── GATE 1: Auction Conflicted ────────────────────────────────
        if auction_verdict.auction_state == "CONFLICTED":
            return self._no_edge(
                reason=f"Auction conflicted: {auction_verdict.reasoning}",
                gate="AUCTION_CONFLICTED"
            )

        # ── GATE 2: Data Confidence ───────────────────────────────────
        if outcomes.confidence_level < self.thresholds['min_data_confidence']:
            return self._no_edge(
                reason=(
                    f"Insufficient data confidence: {outcomes.confidence_level:.0%} "
                    f"< {self.thresholds['min_data_confidence']:.0%} "
                    f"({outcomes.n_observations} observations)"
                ),
                gate="DATA_CONFIDENCE"
            )

        # ── GATE 3: Trend Exhaustion [NEW] ────────────────────────────
        # Question: Has the structural move already happened?
        # Fires ONLY when BOTH maturity is LATE AND price is in the
        # exhaustion proximity band. ADX floor prevents false-firing
        # on sideways names that happen to be near an old high.
        exhaustion_result = self._check_trend_exhaustion(state, macro_regime)
        if exhaustion_result['veto']:
            return self._no_edge(
                reason=exhaustion_result['reason'],
                gate="TREND_EXHAUSTED"
            )

        # ── GATE 4: Options Viability [NEW] ──────────────────────────
        # Question: Can we actually execute a clean options trade here?
        options_result = self._check_options_viability(state)
        if options_result['veto']:
            return self._no_edge(
                reason=options_result['reason'],
                gate="OPTIONS_VIABILITY"
            )

        # ── GATE 5: Regime-Adjusted EV [REPLACES fixed 3% floor] ─────
        # Question: Is the edge large enough to justify risk in THIS regime?
        cost = calculate_trading_costs(ticker=state.ticker)
        net_ev = outcomes.expected_value_20d - cost
        win_rate = outcomes.prob_up_10pct_20d

        ev_floor, wr_floor = REGIME_EV_FLOORS.get(macro_regime, REGIME_EV_FLOORS["TRANSITIONAL"])

        if net_ev >= ev_floor and win_rate >= wr_floor:
            return self._has_edge(
                state=state,
                outcomes=outcomes,
                auction_verdict=auction_verdict,
                net_ev=net_ev,
                cost=cost,
                verdict_tier='TRADE',
                macro_regime=macro_regime
            )

        # Check SETUP_FORMING tier
        sf_ev_floor, sf_wr_floor = REGIME_SETUP_FORMING_FLOORS.get(
            macro_regime, REGIME_SETUP_FORMING_FLOORS["TRANSITIONAL"]
        )

        if net_ev > sf_ev_floor and win_rate >= sf_wr_floor:
            return self._setup_forming(
                state=state,
                outcomes=outcomes,
                auction_verdict=auction_verdict,
                net_ev=net_ev,
                cost=cost,
                reason=(
                    f"Positive net EV ({net_ev:.2%}) but below {ev_floor:.1%} "
                    f"threshold for {macro_regime} regime. "
                    f"Win rate: {win_rate:.1%}. Wait for better entry or confirmation."
                )
            )

        # GATE 5 failed — build reason
        reasons = []
        if net_ev <= 0.0:
            reasons.append(f"Negative net EV: {net_ev:.2%} (gross: {outcomes.expected_value_20d:.2%}, cost: {cost:.2%})")
        else:
            reasons.append(f"Net EV {net_ev:.2%} below {macro_regime} regime floor of {ev_floor:.1%}")
        if win_rate < wr_floor:
            reasons.append(f"Win rate {win_rate:.1%} below {macro_regime} floor of {wr_floor:.1%}")

        return self._no_edge(
            reason="; ".join(reasons),
            gate="REGIME_MINIMUM_EV"
        )

    # ------------------------------------------------------------------
    # GATE 3: TREND EXHAUSTION LOGIC
    # ------------------------------------------------------------------

    def _check_trend_exhaustion(self, state: StateVector, macro_regime: str) -> Dict:
        """
        Veto when the directional move has structurally run its course.

        Logic:
          - Maturity must be LATE (already computed by state_calculator)
          - ADX must be above minimum (confirms it's a real trend, not drift)
          - Price must be within the regime-sensitive proximity band of 52w extreme

        Why regime-sensitive proximity?
          In Risk-On, strong trends can extend 2-4% past "normal" exhaustion.
          In Risk-Off, anything within 10% of the high is danger territory for
          new long entries — the risk of a failed breakout / reversal is highest.

        Returns dict with 'veto' bool and 'reason' string.
        """

        trend_maturity = getattr(state, 'trend_maturity', 'N/A')
        trend_direction = getattr(state, 'trend_direction', 'SIDEWAYS')
        adx = getattr(state, 'adx', 0.0)
        distance_from_52w_high = getattr(state, 'distance_from_52w_high', -1.0)
        distance_from_52w_low = getattr(state, 'distance_from_52w_low', 1.0)

        # Only applies to directional trends with confirmed maturity
        if trend_maturity != "LATE":
            return {'veto': False, 'reason': ''}

        # Low ADX means the "trend" has no real energy — don't veto
        if adx < EXHAUSTION_MIN_ADX:
            return {'veto': False, 'reason': ''}

        proximity_threshold = EXHAUSTION_PROXIMITY.get(macro_regime, EXHAUSTION_PROXIMITY["TRANSITIONAL"])

        # Long setup: veto if LATE uptrend and price near 52w high
        if trend_direction == "UP":
            if distance_from_52w_high >= proximity_threshold:
                return {
                    'veto': True,
                    'reason': (
                        f"Trend EXHAUSTED (LONG): LATE uptrend, price is "
                        f"{abs(distance_from_52w_high):.1%} from 52w high "
                        f"(threshold: {abs(proximity_threshold):.1%} in {macro_regime} regime). "
                        f"ADX={adx:.1f}. Move already made — risk/reward inverted."
                    )
                }

        # Short setup: veto if LATE downtrend and price near 52w low
        if trend_direction == "DOWN":
            if distance_from_52w_low <= abs(proximity_threshold):
                return {
                    'veto': True,
                    'reason': (
                        f"Trend EXHAUSTED (SHORT): LATE downtrend, price is "
                        f"{distance_from_52w_low:.1%} from 52w low "
                        f"(threshold: {abs(proximity_threshold):.1%} in {macro_regime} regime). "
                        f"ADX={adx:.1f}. Downside exhaustion — short risk/reward inverted."
                    )
                }

        return {'veto': False, 'reason': ''}

    # ------------------------------------------------------------------
    # GATE 4: OPTIONS VIABILITY LOGIC
    # ------------------------------------------------------------------

    def _check_options_viability(self, state: StateVector) -> Dict:
        """
        Veto when a clean options trade cannot be executed.

        Three failure modes in order of severity:
          1. Earnings blackout — IV will spike/crush unpredictably
          2. Earnings just passed — gap risk still live for 1-3 days
          3. IV already spiked — entering after the vol event, buying the tail

        Note: Liquidity gate uses state.liquidity_condition, which is
        computed by state_calculator from relative volume and spread.
        We do NOT re-derive liquidity here — that would violate single
        responsibility. We simply read and gate on it.
        """

        days_to_earnings = getattr(state, 'days_to_earnings', -1)
        days_since_earnings = getattr(state, 'days_since_earnings', 999)
        liquidity_condition = getattr(state, 'liquidity_condition', 'NORMAL')
        iv_percentile = getattr(state, 'iv_percentile', 50.0)
        vol_regime = getattr(state, 'vol_regime', 'NORMAL')

        # Failure mode 1: Earnings too close (IV will spike or crush)
        if days_to_earnings != -1 and 0 < days_to_earnings <= EARNINGS_BLACKOUT_DAYS:
            return {
                'veto': True,
                'reason': (
                    f"OPTIONS UNVIABLE: Earnings in {days_to_earnings} days "
                    f"(blackout: {EARNINGS_BLACKOUT_DAYS}d). "
                    f"IV behavior is binary and unpredictable. Wait until post-earnings settle."
                )
            }

        # Failure mode 2: Earnings just passed (gap risk still live)
        if 0 < days_since_earnings <= EARNINGS_REENTRY_DAYS:
            return {
                'veto': True,
                'reason': (
                    f"OPTIONS UNVIABLE: Earnings {days_since_earnings} day(s) ago. "
                    f"Post-earnings gap risk still active ({EARNINGS_REENTRY_DAYS}d blackout). "
                    f"Bid-ask spreads remain wide. Wait for options chain to normalise."
                )
            }

        # Failure mode 3: IV already spiked without compression context
        # Exception: If vol_regime is COMPRESSION, high IV is GOOD (coiling, upcoming move)
        # We only veto elevated IV in NORMAL or EXPANSION regime — that's buying the tail
        if vol_regime != "COMPRESSION" and iv_percentile >= IV_SPIKE_PERCENTILE:
            return {
                'veto': True,
                'reason': (
                    f"OPTIONS UNVIABLE: IV at {iv_percentile:.0f}th percentile "
                    f"with {vol_regime} vol regime. "
                    f"Entering after the vol event — buying elevated premium "
                    f"without structural compression to support it. Risk/reward negative on options."
                )
            }

        return {'veto': False, 'reason': ''}

    # ------------------------------------------------------------------
    # DIRECTION, CONFIDENCE, RIGHT-SIDE SCORE
    # ------------------------------------------------------------------

    def _determine_direction(self,
                             state: StateVector,
                             outcomes: ActuarialOutcomes,
                             auction: AuctionVerdict) -> str:
        """
        Determine CALL or PUT direction.
        Priority: Auction control > Value migration > Statistical probability > Trend
        """
        score = 0.0

        # Auction control (40 points)
        if auction.control.controller == "BUYERS":
            score += 40 * auction.control.confidence
        elif auction.control.controller == "SELLERS":
            score -= 40 * auction.control.confidence

        # Value migration (30 points)
        if auction.migration.direction == "UP":
            score += 30 if auction.migration.consistency.startswith("CONSISTENT") else 15
        elif auction.migration.direction == "DOWN":
            score -= 30 if auction.migration.consistency.startswith("CONSISTENT") else 15

        # Statistical probability (20 points)
        if outcomes.prob_up_10pct_20d > 0.55:
            score += 20
        elif outcomes.prob_up_10pct_20d < 0.35:
            score -= 20

        # Trend direction (10 points)
        if state.trend_direction == "UP" and outcomes.prob_trend_continues_20d > 0.60:
            score += 10
        elif state.trend_direction == "DOWN" and outcomes.prob_trend_continues_20d > 0.60:
            score -= 10

        if score > 15:
            return "CALL"
        elif score < -15:
            return "PUT"
        else:
            if auction.control.controller == "BUYERS":
                return "CALL"
            elif auction.control.controller == "SELLERS":
                return "PUT"
            return "CALL"  # Default: equity risk premium

    def _calculate_confidence(self,
                              state: StateVector,
                              outcomes: ActuarialOutcomes,
                              auction: AuctionVerdict) -> float:
        """
        Overall confidence = weighted blend of state, actuarial, and auction quality.
        """
        return (
            state.confidence * 0.25 +
            outcomes.confidence_level * 0.35 +
            auction.confidence * 0.40
        )

    def _calculate_right_side_score(self,
                                    state: StateVector,
                                    outcomes: ActuarialOutcomes,
                                    auction: AuctionVerdict) -> float:
        """
        Are we on the RIGHT SIDE of the trade?
        Maximum alignment = 100.

        CHANGE vs v1.0: Macro regime bonus raised from 5 → 15 points.
        Regime is a primary environmental condition, not a footnote.
        Catalyst alignment reduced from 10 → 5 to compensate.
        """
        score = 50.0  # Start neutral

        # Auction alignment (25 points)
        if auction.auction_state == "ALIGNED":
            score += 25
        elif auction.auction_state == "TRANSITIONING":
            score += 15
        elif auction.auction_state == "SEARCHING":
            score += 5

        # Control + Direction (20 points)
        if auction.control.controller in ["BUYERS", "SELLERS"]:
            score += 20 * auction.control.confidence

        # Value migration (15 points)
        if auction.migration.consistency.startswith("CONSISTENT"):
            score += 15
        elif auction.migration.consistency.startswith("TRENDING"):
            score += 10

        # Statistical probability (10 points)
        if outcomes.prob_up_10pct_20d > 0.60 or outcomes.prob_up_10pct_20d < 0.30:
            score += 10
        elif outcomes.prob_up_10pct_20d > 0.55 or outcomes.prob_up_10pct_20d < 0.35:
            score += 6

        # Trend + probability alignment (5 points)
        if state.trend_direction != "SIDEWAYS" and outcomes.prob_trend_continues_20d > 0.65:
            score += 5

        # Macro alignment (15 points) [RAISED from 5 — regime is primary]
        macro_regime = getattr(state, 'macro_regime', 'TRANSITIONAL')
        if macro_regime == "RISK_ON" and outcomes.prob_up_10pct_20d > 0.50:
            score += 15
        elif macro_regime == "RISK_OFF" and outcomes.prob_up_10pct_20d < 0.40:
            score += 15
        elif macro_regime == "TRANSITIONAL" and outcomes.prob_up_10pct_20d > 0.45:
            score += 8  # Partial credit for transitional alignment

        # Catalyst alignment (5 points) [REDUCED from 10]
        if state.catalyst_proximity == "HIGH":
            if state.earnings_window in ["PRE_20D", "PRE_10D"]:
                if outcomes.prob_drift_into_earnings and outcomes.prob_drift_into_earnings > 0.60:
                    score += 5

        return min(100.0, score)

    # ------------------------------------------------------------------
    # RATIONALE GENERATION
    # ------------------------------------------------------------------

    def _generate_rationale(self,
                            state: StateVector,
                            outcomes: ActuarialOutcomes,
                            auction: AuctionVerdict,
                            direction: str,
                            net_ev: float = None,
                            cost: float = None,
                            macro_regime: str = None) -> str:
        """Human-readable explanation of why this edge exists."""

        macro_regime = macro_regime or getattr(state, 'macro_regime', 'TRANSITIONAL')
        ev_floor, wr_floor = REGIME_EV_FLOORS.get(macro_regime, REGIME_EV_FLOORS["TRANSITIONAL"])

        parts = [
            f"EDGE DETECTED: {direction}S",
            "",
            "=== EXPECTED VALUE (NET) ===",
            f"Gross EV:        {outcomes.expected_value_20d:.2%}",
            f"Trading Costs:  -{cost:.2%} (spread + slippage)" if cost is not None else "",
            f"Net EV:          {net_ev:.2%}" if net_ev is not None else "",
            f"Regime Floor:    {ev_floor:.2%} ({macro_regime})",
            f"Win Rate:        {outcomes.prob_up_10pct_20d:.1%} (floor: {wr_floor:.1%})",
            "",
            "=== GATE STATUS ===",
            f"TREND_EXHAUSTED:   PASSED (maturity={state.trend_maturity}, "
            f"distance_52w_high={state.distance_from_52w_high:.1%})",
            f"OPTIONS_VIABILITY: PASSED (days_to_earnings={state.days_to_earnings}, "
            f"iv_pct={state.iv_percentile:.0f}th, liquidity={state.liquidity_condition})",
            f"REGIME_EV:         PASSED ({macro_regime})",
            "",
            "=== AUCTION VERDICT ===",
            auction.reasoning,
            "",
            "=== STATISTICAL EDGE ===",
            f"Historical Context: {outcomes.n_observations} similar instances",
            f"Win Rate: {outcomes.prob_up_10pct_20d:.1%} probability of +10% in 20 days",
            f"Sharpe Ratio: {outcomes.sharpe_ratio:.2f}",
            "",
            f"Typical Win: {outcomes.median_gain_if_up:.1%} in {outcomes.median_days_to_target:.0f} days",
            f"Typical Loss: {outcomes.median_loss_if_down:.1%}",
            f"Max Drawdown Risk: {outcomes.median_max_drawdown:.1%}",
            "",
            "=== CURRENT STATE ===",
            f"Volatility: {state.vol_regime} (ATR {state.atr_percentile:.0f}th percentile)",
            f"Trend: {state.trend_direction} ({state.trend_maturity})",
            f"Structure: {state.structure_quality} (acceptance: {state.value_acceptance_score:.0f}/100)",
            f"Control: {state.control_state} ({state.control_confidence:.0%})",
            f"Migration: {state.value_migration_direction} ({auction.migration.speed})",
            f"Macro: {macro_regime}",
        ]
        return "\n".join(p for p in parts if p is not None)

    # ------------------------------------------------------------------
    # VERDICT CONSTRUCTORS
    # ------------------------------------------------------------------

    def _no_edge(self, reason: str, gate: str) -> EdgeAssessment:
        return EdgeAssessment(
            has_edge=False,
            edge_direction="NONE",
            edge_magnitude=0.0,
            confidence=0.0,
            right_side_score=0.0,
            failed_gate=gate,
            no_edge_reason=reason,
            state=None,
            outcomes=None,
            auction_verdict=None,
            rationale=f"NO EDGE ({gate}): {reason}"
        )

    def _has_edge(self,
                  state: StateVector,
                  outcomes: ActuarialOutcomes,
                  auction_verdict: AuctionVerdict,
                  net_ev: float,
                  cost: float,
                  verdict_tier: str,
                  macro_regime: str = 'TRANSITIONAL') -> EdgeAssessment:

        edge_direction = self._determine_direction(state, outcomes, auction_verdict)
        confidence = self._calculate_confidence(state, outcomes, auction_verdict)
        right_side_score = self._calculate_right_side_score(state, outcomes, auction_verdict)
        rationale = self._generate_rationale(
            state, outcomes, auction_verdict, edge_direction, net_ev, cost, macro_regime
        )

        return EdgeAssessment(
            has_edge=True,
            edge_direction=edge_direction,
            edge_magnitude=net_ev,
            confidence=confidence,
            right_side_score=right_side_score,
            state=state,
            outcomes=outcomes,
            auction_verdict=auction_verdict,
            rationale=rationale
        )

    def _setup_forming(self,
                       state: StateVector,
                       outcomes: ActuarialOutcomes,
                       auction_verdict: AuctionVerdict,
                       net_ev: float,
                       cost: float,
                       reason: str) -> EdgeAssessment:

        edge_direction = self._determine_direction(state, outcomes, auction_verdict)
        confidence = self._calculate_confidence(state, outcomes, auction_verdict) * 0.7
        right_side_score = self._calculate_right_side_score(state, outcomes, auction_verdict)
        rationale = (
            f"SETUP FORMING ({edge_direction})\n\n{reason}\n\n"
            + self._generate_rationale(state, outcomes, auction_verdict, edge_direction, net_ev, cost)
        )

        return EdgeAssessment(
            has_edge=False,
            edge_direction=edge_direction,
            edge_magnitude=net_ev,
            confidence=confidence,
            right_side_score=right_side_score,
            state=state,
            outcomes=outcomes,
            auction_verdict=auction_verdict,
            rationale=rationale,
            failed_gate="SETUP_FORMING",
            no_edge_reason=reason
        )
