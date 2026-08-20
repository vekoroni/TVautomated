"""
VANGUARD Layer 2 - Edge Detector  [PATCHED v2.1]
================================================

PATCH NOTES vs original edge_detector.py
-----------------------------------------
BUG-01 (CRITICAL): Gate 5 — `net_ev = ev['ev_final']` referenced undefined variable `ev`.
       This caused a NameError at runtime, silently preventing any trade from reaching
       the EIL. The variable `ev` was never assigned in detect_edge().

       FIX: Gate 5 now calls EVEngineV2 (the single EV authority) to compute net_ev.
       Falls back to actuarial outcomes.expected_value_20d - cost if EVEngineV2
       is unavailable, matching the original intent.

BUG-02: Gate 5 comment said "FIX 2: Use P(return>0) directional win rate" but the
       underlying EV source was broken (undefined variable). The win_rate logic itself
       was correct — preserved as-is.

ZERO REGRESSION GUARANTEE:
  All gate logic, threshold constants, verdict constructors, direction/confidence/
  right_side_score calculations are UNCHANGED from the original. Only Gate 5's
  net_ev source is fixed. All other gates (0–4) are byte-for-byte identical.

PRESERVED:
  - REGIME_EV_FLOORS, EXHAUSTION_PROXIMITY, EARNINGS_BLACKOUT_DAYS constants
  - _check_trend_exhaustion(), _check_options_viability() — unchanged
  - _determine_direction(), _calculate_confidence(), _calculate_right_side_score()
  - _generate_rationale(), _no_edge(), _has_edge(), _setup_forming() — unchanged
  - All imports and class structure — unchanged
"""

from typing import Dict
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..schemas.auction_schema import AuctionVerdict
from ..schemas.trade_schema import EdgeAssessment
from ..config import EDGE_DETECTION_THRESHOLDS

# ── EVEngineV2 import (new single EV authority) ───────────────────────────────
try:
    from ev_engine_v2 import EVEngineV2, ev_inputs_from_row
    _EV_ENGINE_V2 = EVEngineV2()
except ImportError:
    _EV_ENGINE_V2 = None


# ========================= TRADING COST MODEL ================================

def calculate_trading_costs(ticker: str = None, liquidity_tier: str = 'NORMAL') -> float:
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

REGIME_EV_FLOORS = {
    "RISK_ON":       (0.025, 0.38),
    "TRANSITIONAL":  (0.035, 0.42),
    "RISK_OFF":      (0.055, 0.48),
}

REGIME_SETUP_FORMING_FLOORS = {
    "RISK_ON":       (0.000, 0.33),
    "TRANSITIONAL":  (0.005, 0.35),
    "RISK_OFF":      (0.015, 0.40),
}

# ========================= TREND EXHAUSTION THRESHOLDS =======================

EXHAUSTION_PROXIMITY = {
    "RISK_ON":       -0.04,
    "TRANSITIONAL":  -0.06,
    "RISK_OFF":      -0.10,
}

EXHAUSTION_MIN_ADX = 22.0

# ========================= OPTIONS VIABILITY THRESHOLDS ======================

EARNINGS_BLACKOUT_DAYS = 10
EARNINGS_REENTRY_DAYS  = 3
LIQUIDITY_MIN_CONDITION = "LOW"
IV_SPIKE_PERCENTILE     = 85


# =============================================================================
#  EDGE DETECTOR CLASS
# =============================================================================

class EdgeDetector:
    """
    Multi-gate edge detection system [PATCHED v2.1]

    Gates (ALL must pass, in order):
      0. INTRADAY_DATA_INTEGRITY  — downgrade auction confidence if no intraday
      1. AUCTION_CONFLICTED       — market structure not readable
      2. DATA_CONFIDENCE          — insufficient historical sample
      3. TREND_EXHAUSTED          — move already happened
      4. OPTIONS_VIABILITY        — cannot execute a clean options trade
      5. REGIME_MINIMUM_EV        — net EV too low for current macro regime [BUG-01 FIXED]
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

        macro_regime = getattr(state, 'macro_regime', 'TRANSITIONAL') or 'TRANSITIONAL'

        # ── GATE 0: INTRADAY DATA INTEGRITY ──────────────────────────
        intraday_rows = getattr(state, 'intraday_rows', None)
        no_intraday = (intraday_rows is not None and intraday_rows == 0)
        if no_intraday:
            effective_auction_state = "SEARCHING"
            intraday_warning = (
                "[WARNING] intraday_rows=0 — Layer 1 is HTF Auction Context only. "
                "Intraday VWAP, POC, and control dynamics are estimated, not real-time. "
                "Auction confidence downgraded for gate evaluation."
            )
        else:
            effective_auction_state = auction_verdict.auction_state
            intraday_warning = None

        # ── GATE 1: Auction Conflicted ────────────────────────────────
        if effective_auction_state == "CONFLICTED":
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

        # ── GATE 3: Trend Exhaustion ──────────────────────────────────
        exhaustion_result = self._check_trend_exhaustion(state, macro_regime)
        if exhaustion_result['veto']:
            return self._no_edge(
                reason=exhaustion_result['reason'],
                gate="TREND_EXHAUSTED"
            )

        # ── GATE 4: Options Viability ─────────────────────────────────
        options_result = self._check_options_viability(state)
        if options_result['veto']:
            return self._no_edge(
                reason=options_result['reason'],
                gate="OPTIONS_VIABILITY"
            )

        # ── GATE 5: Regime-Adjusted EV [BUG-01 FIXED] ────────────────
        # BUG-01: Original code had `net_ev = ev['ev_final']` where `ev`
        # was never defined. This caused a NameError at runtime.
        #
        # FIX: Compute net_ev from EVEngineV2 (single EV authority).
        # Fallback: actuarial expected_value_20d - trading cost.
        cost = calculate_trading_costs(ticker=state.ticker)

        if _EV_ENGINE_V2 is not None:
            try:
                # Build a minimal row dict from state fields for ev_inputs_from_row
                state_row = {
                    'ticker':           getattr(state, 'ticker', 'UNKNOWN'),
                    'signal_price':     getattr(state, 'price', 100.0),
                    'win_rate_20d':     outcomes.win_rate,         # already 0–1
                    'win_rate_10d':     getattr(outcomes, 'win_rate_10d', 0.0),
                    'win_rate_5d':      getattr(outcomes, 'win_rate_5d', 0.0),
                    'expected_move_20d': outcomes.median_gain_if_up,
                    'expected_move_10d': getattr(outcomes, 'median_gain_if_up_10d', 0.0),
                    'expected_move_5d':  getattr(outcomes, 'median_gain_if_up_5d', 0.0),
                    'regime_state':     macro_regime,
                    'data_quality_score': min(100.0, outcomes.confidence_level * 100),
                    'breakeven_pass_live': True,
                    'runway_pct':       getattr(state, 'runway_pct', 2.0),
                    'spread_pct':       cost,
                    'delta':            getattr(state, 'delta', 0.40),
                    'theta':            getattr(state, 'theta', 0.01),
                    'iv_rank':          getattr(state, 'iv_percentile', 0.50),
                    'composite':        getattr(state, 'value_acceptance_score', 50.0),
                    'survival_prob':    max(0.0, 1.0 - outcomes.prob_down_5pct_before_up_10pct),
                }
                ev_in  = ev_inputs_from_row(state_row)
                ev_res = _EV_ENGINE_V2.evaluate(ev_in)
                net_ev = ev_res.ev_conf_adj
            except Exception as _ev_err:
                # Fallback to actuarial if EVEngineV2 fails
                net_ev = outcomes.expected_value_20d - cost
        else:
            # EVEngineV2 not installed — actuarial fallback (original intent)
            net_ev = outcomes.expected_value_20d - cost

        # FIX 2 preserved: P(return>0) directional win rate, not target hit rate
        win_rate = outcomes.win_rate

        ev_floor, wr_floor = REGIME_EV_FLOORS.get(macro_regime, REGIME_EV_FLOORS["TRANSITIONAL"])

        if net_ev >= ev_floor and win_rate >= wr_floor:
            return self._has_edge(
                state=state,
                outcomes=outcomes,
                auction_verdict=auction_verdict,
                net_ev=net_ev,
                cost=cost,
                verdict_tier='TRADE',
                macro_regime=macro_regime,
                intraday_warning=intraday_warning
            )

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
                ),
                intraday_warning=intraday_warning
            )

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
    # GATE 3: TREND EXHAUSTION (UNCHANGED)
    # ------------------------------------------------------------------

    def _check_trend_exhaustion(self, state: StateVector, macro_regime: str) -> Dict:
        trend_maturity = getattr(state, 'trend_maturity', 'N/A')
        trend_direction = getattr(state, 'trend_direction', 'SIDEWAYS')
        adx = getattr(state, 'adx', 0.0)
        distance_from_52w_high = getattr(state, 'distance_from_52w_high', -1.0)
        distance_from_52w_low = getattr(state, 'distance_from_52w_low', 1.0)

        if trend_maturity != "LATE":
            return {'veto': False, 'reason': ''}
        if adx < EXHAUSTION_MIN_ADX:
            return {'veto': False, 'reason': ''}

        proximity_threshold = EXHAUSTION_PROXIMITY.get(macro_regime, EXHAUSTION_PROXIMITY["TRANSITIONAL"])

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
    # GATE 4: OPTIONS VIABILITY (UNCHANGED)
    # ------------------------------------------------------------------

    def _check_options_viability(self, state: StateVector) -> Dict:
        days_to_earnings = getattr(state, 'days_to_earnings', -1)
        days_since_earnings = getattr(state, 'days_since_earnings', 999)
        liquidity_condition = getattr(state, 'liquidity_condition', 'NORMAL')
        iv_percentile = getattr(state, 'iv_percentile', 50.0)
        vol_regime = getattr(state, 'vol_regime', 'NORMAL')

        if liquidity_condition == LIQUIDITY_MIN_CONDITION:
            return {
                'veto': True,
                'reason': (
                    f"OPTIONS UNVIABLE: Liquidity condition is LOW. "
                    f"Spreads and slippage would destroy EV before the trade starts. "
                    f"Minimum acceptable: NORMAL or HIGH."
                )
            }

        if days_to_earnings != -1 and 0 < days_to_earnings <= EARNINGS_BLACKOUT_DAYS:
            return {
                'veto': True,
                'reason': (
                    f"OPTIONS UNVIABLE: Earnings in {days_to_earnings} days "
                    f"(blackout: {EARNINGS_BLACKOUT_DAYS}d). "
                    f"IV behavior is binary and unpredictable. Wait until post-earnings settle."
                )
            }

        if 0 < days_since_earnings <= EARNINGS_REENTRY_DAYS:
            return {
                'veto': True,
                'reason': (
                    f"OPTIONS UNVIABLE: Earnings {days_since_earnings} day(s) ago. "
                    f"Post-earnings gap risk still active ({EARNINGS_REENTRY_DAYS}d blackout). "
                    f"Bid-ask spreads remain wide. Wait for options chain to normalise."
                )
            }

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
    # DIRECTION, CONFIDENCE, RIGHT-SIDE SCORE (UNCHANGED)
    # ------------------------------------------------------------------

    def _determine_direction(self, state, outcomes, auction):
        score = 0.0
        if auction.control.controller == "BUYERS":
            score += 40 * auction.control.confidence
        elif auction.control.controller == "SELLERS":
            score -= 40 * auction.control.confidence

        if auction.migration.direction == "UP":
            score += 30 if auction.migration.consistency.startswith("CONSISTENT") else 15
        elif auction.migration.direction == "DOWN":
            score -= 30 if auction.migration.consistency.startswith("CONSISTENT") else 15

        if outcomes.prob_up_10pct_20d > 0.55:
            score += 20
        elif outcomes.prob_up_10pct_20d < 0.35:
            score -= 20

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
            return "CALL"

    def _calculate_confidence(self, state, outcomes, auction):
        intraday_rows = getattr(state, 'intraday_rows', None)
        no_intraday = (intraday_rows is not None and intraday_rows == 0)
        auction_conf = auction.confidence * (0.60 if no_intraday else 1.0)
        return (
            state.confidence * 0.25 +
            outcomes.confidence_level * 0.35 +
            auction_conf * 0.40
        )

    def _calculate_right_side_score(self, state, outcomes, auction):
        score = 50.0
        if auction.auction_state == "ALIGNED":
            score += 25
        elif auction.auction_state == "TRANSITIONING":
            score += 15
        elif auction.auction_state == "SEARCHING":
            score += 5

        if auction.control.controller in ["BUYERS", "SELLERS"]:
            score += 20 * auction.control.confidence

        if auction.migration.consistency.startswith("CONSISTENT"):
            score += 15
        elif auction.migration.consistency.startswith("TRENDING"):
            score += 10

        if outcomes.prob_up_10pct_20d > 0.60 or outcomes.prob_up_10pct_20d < 0.30:
            score += 10
        elif outcomes.prob_up_10pct_20d > 0.55 or outcomes.prob_up_10pct_20d < 0.35:
            score += 6

        if state.trend_direction != "SIDEWAYS" and outcomes.prob_trend_continues_20d > 0.65:
            score += 5

        macro_regime = getattr(state, 'macro_regime', 'TRANSITIONAL')
        if macro_regime == "RISK_ON" and outcomes.prob_up_10pct_20d > 0.50:
            score += 15
        elif macro_regime == "RISK_OFF" and outcomes.prob_up_10pct_20d < 0.40:
            score += 15
        elif macro_regime == "TRANSITIONAL" and outcomes.prob_up_10pct_20d > 0.45:
            score += 8

        if state.catalyst_proximity == "HIGH":
            if state.earnings_window in ["PRE_20D", "PRE_10D"]:
                if getattr(outcomes, 'prob_drift_into_earnings', None) and outcomes.prob_drift_into_earnings > 0.60:
                    score += 5

        return min(100.0, score)

    # ------------------------------------------------------------------
    # RATIONALE (UNCHANGED)
    # ------------------------------------------------------------------

    def _generate_rationale(self, state, outcomes, auction, direction,
                             net_ev=None, cost=None, macro_regime=None):
        macro_regime = macro_regime or getattr(state, 'macro_regime', 'TRANSITIONAL')
        ev_floor, wr_floor = REGIME_EV_FLOORS.get(macro_regime, REGIME_EV_FLOORS["TRANSITIONAL"])

        parts = [
            f"EDGE DETECTED: {direction}S", "",
            "=== EXPECTED VALUE (NET) ===",
            f"Gross EV:        {outcomes.expected_value_20d:.2%}",
            f"Trading Costs:  -{cost:.2%} (spread + slippage)" if cost is not None else "",
            f"Net EV:          {net_ev:.2%}" if net_ev is not None else "",
            f"Regime Floor:    {ev_floor:.2%} ({macro_regime})",
            f"Win Rate:        {outcomes.win_rate:.1%} (floor: {wr_floor:.1%}) [P(return>0)]",
            "", "=== GATE STATUS ===",
            f"TREND_EXHAUSTED:   PASSED (maturity={state.trend_maturity}, "
            f"distance_52w_high={state.distance_from_52w_high:.1%})",
            f"OPTIONS_VIABILITY: PASSED (days_to_earnings={state.days_to_earnings}, "
            f"iv_pct={state.iv_percentile:.0f}th, liquidity={state.liquidity_condition})",
            f"REGIME_EV:         PASSED ({macro_regime})",
            "", "=== AUCTION VERDICT ===",
            auction.reasoning, "",
            "=== STATISTICAL EDGE ===",
            f"Historical Context: {outcomes.n_observations} similar instances",
            f"Win Rate: {outcomes.prob_up_10pct_20d:.1%} probability of +10% in 20 days",
            f"Sharpe Ratio: {outcomes.sharpe_ratio:.2f}", "",
            f"Typical Win: {outcomes.median_gain_if_up:.1%} in {outcomes.median_days_to_target:.0f} days",
            f"Typical Loss: {outcomes.median_loss_if_down:.1%}",
            f"Max Drawdown Risk: {outcomes.median_max_drawdown:.1%}",
            "", "=== CURRENT STATE ===",
            f"Volatility: {state.vol_regime} (ATR {state.atr_percentile:.0f}th percentile)",
            f"Trend: {state.trend_direction} ({state.trend_maturity})",
            f"Structure: {state.structure_quality} (acceptance: {state.value_acceptance_score:.0f}/100)",
            f"Control: {state.control_state} ({state.control_confidence:.0%})",
            f"Migration: {state.value_migration_direction} ({auction.migration.speed})",
            f"Macro: {macro_regime}",
        ]
        return "\n".join(p for p in parts if p is not None)

    # ------------------------------------------------------------------
    # VERDICT CONSTRUCTORS (UNCHANGED)
    # ------------------------------------------------------------------

    def _no_edge(self, reason: str, gate: str) -> EdgeAssessment:
        return EdgeAssessment(
            has_edge=False, edge_direction="NONE", edge_magnitude=0.0,
            confidence=0.0, right_side_score=0.0, failed_gate=gate,
            no_edge_reason=reason, state=None, outcomes=None,
            auction_verdict=None, rationale=f"NO EDGE ({gate}): {reason}"
        )

    def _has_edge(self, state, outcomes, auction_verdict, net_ev, cost,
                  verdict_tier, macro_regime='TRANSITIONAL', intraday_warning=None):
        edge_direction = self._determine_direction(state, outcomes, auction_verdict)
        confidence = self._calculate_confidence(state, outcomes, auction_verdict)
        right_side_score = self._calculate_right_side_score(state, outcomes, auction_verdict)
        rationale = self._generate_rationale(
            state, outcomes, auction_verdict, edge_direction, net_ev, cost, macro_regime
        )
        if intraday_warning:
            rationale = intraday_warning + "\n\n" + rationale

        return EdgeAssessment(
            has_edge=True, edge_direction=edge_direction, edge_magnitude=net_ev,
            confidence=confidence, right_side_score=right_side_score,
            state=state, outcomes=outcomes, auction_verdict=auction_verdict,
            rationale=rationale
        )

    def _setup_forming(self, state, outcomes, auction_verdict, net_ev, cost,
                       reason, intraday_warning=None):
        edge_direction = self._determine_direction(state, outcomes, auction_verdict)
        confidence = self._calculate_confidence(state, outcomes, auction_verdict) * 0.7
        right_side_score = self._calculate_right_side_score(state, outcomes, auction_verdict)
        rationale = (
            f"SETUP FORMING ({edge_direction})\n\n{reason}\n\n"
            + self._generate_rationale(state, outcomes, auction_verdict, edge_direction, net_ev, cost)
        )
        if intraday_warning:
            rationale = intraday_warning + "\n\n" + rationale

        return EdgeAssessment(
            has_edge=False, edge_direction=edge_direction, edge_magnitude=net_ev,
            confidence=confidence, right_side_score=right_side_score,
            state=state, outcomes=outcomes, auction_verdict=auction_verdict,
            rationale=rationale, failed_gate="SETUP_FORMING", no_edge_reason=reason
        )
