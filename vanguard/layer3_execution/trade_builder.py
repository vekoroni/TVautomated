"""
VANGUARD Layer 3 - Trade Builder
Assembles complete trade plan with all scenarios and recommendations
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from ..schemas.trade_schema import TradePlan, TradeScenario
from ..schemas.trade_schema import EdgeAssessment
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..schemas.auction_schema import AuctionVerdict
from .scenario_builder import MultiScenarioBuilder


class TradeBuilder:
    """
    Builds complete trade plan from edge assessment
    
    Outputs:
    - All three scenarios (Aggressive, Moderate, Conservative)
    - Recommended scenario based on user risk profile
    - Pyramiding strategy (optional)
    - Invalidation criteria
    """
    
    def __init__(self):
        self.scenario_builder = MultiScenarioBuilder()
        
    def build_trade_plan(self,
                        ticker: str,
                        current_price: float,
                        edge: EdgeAssessment) -> TradePlan:
        """
        Main entry: Build complete trade plan
        
        Args:
            ticker: Stock symbol
            current_price: Current price
            edge: EdgeAssessment from Layer 2
            
        Returns:
            Complete TradePlan with all scenarios
        """
        
        state = edge.state
        outcomes = edge.outcomes
        auction = edge.auction_verdict
        direction = edge.edge_direction
        
        # Build all scenarios
        scenarios = self.scenario_builder.build_scenarios(
            ticker, current_price, direction, state, outcomes, auction
        )
        
        # Determine recommended scenario
        recommended = self._determine_recommended_scenario(scenarios, auction, state)
        
        # Build pyramiding plan (optional advanced strategy)
        pyramiding = self._build_pyramiding_plan(scenarios, current_price)
        
        # Define invalidation criteria
        invalidation = self._define_invalidation_criteria(
            scenarios, auction, state, outcomes
        )
        
        # Calculate overall metrics
        overall_confidence = self._calculate_overall_confidence(scenarios, edge)
        overall_right_side = self._calculate_overall_right_side_score(scenarios, edge)
        
        # Generate recommendation rationale
        rationale = self._generate_recommendation_rationale(
            recommended, scenarios, auction, state
        )
        
        # Build execution gates — required confirmations before committing capital
        execution_gates = self._build_execution_gates(
            ticker, current_price, direction, state, outcomes, auction, scenarios
        )

        return TradePlan(
            ticker=ticker,
            timestamp=datetime.now().isoformat(),
            current_price=current_price,
            direction=direction,
            
            scenario_aggressive=scenarios['aggressive'],
            scenario_moderate=scenarios['moderate'],
            scenario_conservative=scenarios['conservative'],
            
            pyramiding_plan=pyramiding,
            
            recommended_scenario=recommended,
            recommendation_rationale=rationale,
            
            invalidation_criteria=invalidation,
            
            overall_confidence=overall_confidence,
            overall_right_side_score=overall_right_side,
            
            edge_rationale=edge.rationale,

            # Execution gates — required before committing capital
            execution_gates=execution_gates,

            # Store for reference
            auction_verdict=self._serialize_auction(auction),
            state_vector=self._serialize_state(state),
            actuarial_outcomes=self._serialize_outcomes(outcomes)
        )
        
    def _determine_recommended_scenario(self,
                                       scenarios: Dict[str, TradeScenario],
                                       auction: AuctionVerdict,
                                       state: StateVector) -> str:
        """
        Determine which scenario to recommend based on:
        - Auction state (how ready is market?)
        - State quality (how strong is setup?)
        - Risk tolerance (default: moderate)
        """
        
        # If auction is ALIGNED and all signals strong → Aggressive viable
        if (auction.auction_state == "ALIGNED" and
            auction.acceptance.score >= 75 and
            auction.control.confidence >= 0.70):
            return "AGGRESSIVE"
            
        # If auction is SEARCHING or weak signals → Conservative only
        if (auction.auction_state == "SEARCHING" or
            auction.acceptance.score < 50 or
            auction.control.confidence < 0.55):
            return "CONSERVATIVE"
            
        # Default: Moderate (balanced approach)
        return "MODERATE"
        
    def _build_pyramiding_plan(self,
                               scenarios: Dict[str, TradeScenario],
                               current_price: float) -> Optional[Dict]:
        """
        Build pyramiding strategy (scale in across scenarios)
        
        Example:
        - 25% NOW (aggressive entry)
        - 25% at $100 (moderate trigger)
        - 25% at $102.50 (conservative trigger)
        - 25% at $105 (momentum confirmation)
        """
        
        aggressive = scenarios['aggressive']
        moderate = scenarios['moderate']
        conservative = scenarios['conservative']
        
        # Only build pyramiding if all scenarios are feasible
        if aggressive.status != "AVAILABLE_NOW":
            return None
            
        return {
            'total_position': '100%',
            'initial_entry': {
                'percent': '25%',
                'price': aggressive.entry_optimal,
                'trigger': 'Immediate (Aggressive)'
            },
            'add_on_1': {
                'percent': '25%',
                'price': moderate.entry_optimal,
                'trigger': moderate.entry_trigger
            },
            'add_on_2': {
                'percent': '25%',
                'price': conservative.entry_optimal,
                'trigger': conservative.entry_trigger
            },
            'add_on_3': {
                'percent': '25%',
                'price': conservative.target_1,
                'trigger': f'Momentum confirmation at {conservative.target_1:.2f}'
            },
            'rationale': 'Scale in as confirmation increases, maximize flexibility'
        }
        
    def _define_invalidation_criteria(self,
                                     scenarios: Dict[str, TradeScenario],
                                     auction: AuctionVerdict,
                                     state: StateVector,
                                     outcomes: ActuarialOutcomes) -> list:
        """
        When is the thesis WRONG and we must exit?
        """
        
        criteria = []
        
        # Price-based (from conservative scenario stop)
        conservative_stop = scenarios['conservative'].stop_price
        criteria.append(f"Close below ${conservative_stop:.2f} (structural breakdown)")
        
        # Time-based
        max_hold = outcomes.recommended_hold_days
        criteria.append(f"No progress toward target within {max_hold} trading days")
        
        # Auction-based
        if auction.control.controller in ["BUYERS", "SELLERS"]:
            opposite = "SELLERS" if auction.control.controller == "BUYERS" else "BUYERS"
            criteria.append(f"Control shifts decisively to {opposite} (>70% confidence)")
            
        # Value migration reversal
        if auction.migration.direction != "SIDEWAYS":
            opposite_dir = "DOWN" if auction.migration.direction == "UP" else "UP"
            criteria.append(f"Value migration reverses to {opposite_dir} consistently")
            
        # Catalyst risk (if applicable)
        if state.catalyst_proximity == "HIGH":
            criteria.append(f"Earnings date moves unexpectedly or company pre-announces")
            
        # Volatility spike
        if state.vol_regime == "COMPRESSION":
            criteria.append("Volatility spikes to >90th percentile without price follow-through")
            
        return criteria
        
    def _calculate_overall_confidence(self,
                                     scenarios: Dict[str, TradeScenario],
                                     edge: EdgeAssessment) -> float:
        """
        Overall confidence across all scenarios
        Weight by expected value
        """
        
        # Weight by EV of each scenario
        agg_ev = scenarios['aggressive'].expected_value
        mod_ev = scenarios['moderate'].expected_value
        con_ev = scenarios['conservative'].expected_value
        
        total_ev = agg_ev + mod_ev + con_ev
        
        if total_ev <= 0:
            return edge.confidence
            
        weighted_confidence = (
            scenarios['aggressive'].confidence * (agg_ev / total_ev) +
            scenarios['moderate'].confidence * (mod_ev / total_ev) +
            scenarios['conservative'].confidence * (con_ev / total_ev)
        )
        
        return weighted_confidence
        
    def _calculate_overall_right_side_score(self,
                                           scenarios: Dict[str, TradeScenario],
                                           edge: EdgeAssessment) -> float:
        """
        Overall right-side score
        """
        
        # Average across scenarios, weighted by confidence
        agg = scenarios['aggressive']
        mod = scenarios['moderate']
        con = scenarios['conservative']
        
        total_conf = agg.confidence + mod.confidence + con.confidence
        
        if total_conf == 0:
            return edge.right_side_score
            
        weighted_score = (
            agg.right_side_score * (agg.confidence / total_conf) +
            mod.right_side_score * (mod.confidence / total_conf) +
            con.right_side_score * (con.confidence / total_conf)
        )
        
        return weighted_score
        
    def _generate_recommendation_rationale(self,
                                          recommended: str,
                                          scenarios: Dict[str, TradeScenario],
                                          auction: AuctionVerdict,
                                          state: StateVector) -> str:
        """
        Explain why this scenario is recommended
        """
        
        scenario = scenarios[recommended.lower()]
        
        parts = []
        
        parts.append(f"RECOMMENDED: {recommended} SCENARIO")
        parts.append("")
        parts.append(f"Entry: {scenario.entry_trigger or 'Immediate'}")
        parts.append(f"Price: ${scenario.entry_optimal:.2f}")
        parts.append(f"Win Probability: {scenario.win_probability:.0%}")
        parts.append(f"Expected Value: {scenario.expected_value:.2%}")
        parts.append(f"Position Size: {scenario.recommended_size_pct:.1%} of capital")
        parts.append("")
        parts.append("RATIONALE:")
        
        if recommended == "AGGRESSIVE":
            parts.append("  • Auction signals are strong (alignment + acceptance)")
            parts.append("  • Risk/reward favors early entry (maximum profit potential)")
            parts.append("  • Control is established, value being accepted")
        elif recommended == "MODERATE":
            parts.append("  • Balanced approach: confirmation + profit potential")
            parts.append("  • Wait for trigger reduces risk without sacrificing too much upside")
            parts.append("  • Recommended for most traders (60%+ probability)")
        else:  # CONSERVATIVE
            parts.append("  • Highest probability setup (75%+ win rate)")
            parts.append("  • Reduced profit potential is acceptable for certainty")
            parts.append("  • Recommended when signals are mixed or uncertain")
            
        return "\n".join(parts)
        
    def _build_execution_gates(self,
                               ticker: str,
                               current_price: float,
                               direction: str,
                               state: StateVector,
                               outcomes: ActuarialOutcomes,
                               auction: AuctionVerdict,
                               scenarios: Dict) -> Dict:
        """
        Build required execution gates before capital is committed.

        Philosophy: Vanguard finds edge, execution gates monetise it.
        A TRADE verdict is a CANDIDATE — not a go signal.
        Every gate must be checked at execution time (not at scan time).

        Gates are split into:
          REQUIRED  — must all pass before entry
          PREFERRED — improve confidence but not blocking
          BLOCKING  — any one of these prevents entry

        Each gate has:
          name         — what to check
          condition    — exact criteria
          rationale    — why this gate exists
          source       — where to find the data (broker/scanner/options chain)
        """

        gates = {
            "candidate":   ticker,
            "direction":   direction,
            "horizon":     self._recommend_horizon(state, outcomes),
            "required":    [],
            "preferred":   [],
            "blocking":    [],
            "summary":     "",
        }

        # ── REQUIRED GATES ────────────────────────────────────────────────────

        # G1: VWAP reclaim (intraday structure confirmation)
        if direction == "CALL":
            gates["required"].append({
                "gate":      "G1_VWAP_RECLAIM",
                "condition": "Price must be trading ABOVE 15m VWAP at time of entry",
                "rationale": "VWAP reclaim confirms intraday buyers are in control — "
                             "entering below VWAP means fighting the day's auction",
                "source":    "15m chart / broker VWAP indicator",
                "hard_fail": True,
            })
        else:
            gates["required"].append({
                "gate":      "G1_VWAP_REJECTION",
                "condition": "Price must be trading BELOW 15m VWAP at time of entry",
                "rationale": "VWAP rejection confirms intraday sellers are in control",
                "source":    "15m chart / broker VWAP indicator",
                "hard_fail": True,
            })

        # G2: Spread guard
        spread_threshold = 0.08 if state.vol_regime == "EXPANSION" else 0.05
        gates["required"].append({
            "gate":      "G2_SPREAD_GUARD",
            "condition": f"Options bid-ask spread must be ≤ {spread_threshold:.0%} of mid price",
            "rationale": "Wide spreads destroy EV before the trade even starts — "
                         f"current vol regime ({state.vol_regime}) sets threshold at {spread_threshold:.0%}",
            "source":    "Options chain at time of order",
            "hard_fail": True,
        })

        # G3: Delta band
        if direction == "CALL":
            gates["required"].append({
                "gate":      "G3_DELTA_BAND",
                "condition": "Select strike with delta between 0.35 and 0.55 (near ATM)",
                "rationale": "Sub-0.35 delta = too much theta drag for the horizon. "
                             "Above 0.55 = overpaying for intrinsic — use stock instead",
                "source":    "Options chain — delta column",
                "hard_fail": False,
            })
        else:
            gates["required"].append({
                "gate":      "G3_DELTA_BAND",
                "condition": "Select put with delta between -0.35 and -0.55",
                "rationale": "Same logic as calls — near ATM maximises leverage efficiency",
                "source":    "Options chain — delta column",
                "hard_fail": False,
            })

        # G4: Runway to next structural wall
        conservative_stop = scenarios['conservative'].stop_price
        target_1 = scenarios['conservative'].target_1
        if current_price > 0 and target_1 > 0:
            runway_pct = abs(target_1 - current_price) / current_price
            gates["required"].append({
                "gate":      "G4_RUNWAY",
                "condition": f"Price must have ≥1% clear runway to first target "
                             f"(T1={target_1:.2f}, current runway={runway_pct:.1%})",
                "rationale": "Options have theta cost — entering into a wall means "
                             "paying premium to go nowhere",
                "source":    "Key S/R levels — check chart before entry",
                "hard_fail": runway_pct < 0.01,
            })

        # G5: DTE adequacy
        horizon = self._recommend_horizon(state, outcomes)
        min_dte  = horizon + 7    # minimum: horizon + 7-day buffer
        pref_dte = horizon + 14   # preferred: horizon + 14-day buffer
        gates["required"].append({
            "gate":      "G5_DTE_ADEQUACY",
            "condition": f"Select expiry with ≥{min_dte} DTE (preferred ≥{pref_dte} DTE). "
                         f"Horizon={horizon}d, buffer=7-14d",
            "rationale": "Theta acceleration below 21 DTE can kill a correct directional "
                         "trade — DTE buffer ensures time is not the enemy",
            "source":    "Options chain — expiry dates",
            "hard_fail": False,
        })

        # ── PREFERRED GATES ───────────────────────────────────────────────────

        # P1: IV context
        gates["preferred"].append({
            "gate":      "P1_IV_CONTEXT",
            "condition": "IV rank (IVR) ideally ≤ 50 for buying options "
                         "(not paying peak premium)",
            "rationale": "High IVR means options are expensive — EV shrinks. "
                         "Exception: if EV > 8% the edge absorbs premium cost",
            "source":    "Options chain — IVR / IV percentile",
            "override":  f"Override if EV(20d) ≥ 8% (current EV={outcomes.expected_value_20d:.1%})",
        })

        # P2: Volume confirmation
        gates["preferred"].append({
            "gate":      "P2_VOLUME_CONFIRMATION",
            "condition": "Intraday volume ≥ 70% of 20-day average volume by noon",
            "rationale": "Low-volume moves lack institutional participation — "
                         "breakouts/breakdowns on thin volume fail more often",
            "source":    "Intraday volume bar / scanner",
        })

        # P3: Options flow alignment
        if direction == "CALL":
            gates["preferred"].append({
                "gate":      "P3_OPTIONS_FLOW",
                "condition": "Net options flow positive (more calls than puts by premium)",
                "rationale": "Smart money options flow confirms directional thesis",
                "source":    "Options flow scanner (unusual activity)",
            })
        else:
            gates["preferred"].append({
                "gate":      "P3_OPTIONS_FLOW",
                "condition": "Net options flow negative (more puts than calls by premium)",
                "rationale": "Smart money put activity confirms bearish thesis",
                "source":    "Options flow scanner (unusual activity)",
            })

        # ── BLOCKING CONDITIONS ───────────────────────────────────────────────

        # B1: Earnings proximity
        if state.catalyst_proximity == "HIGH":
            gates["blocking"].append({
                "gate":      "B1_EARNINGS_BLOCK",
                "condition": "BLOCKED — earnings within catalyst window",
                "rationale": "Binary event risk destroys directional edge — "
                             "IV crush post-earnings can wipe gains even if direction is right",
                "override":  "None — wait for earnings to pass",
                "hard_block": True,
            })

        # B2: Macro regime conflict
        if hasattr(state, 'macro_regime') and state.macro_regime == "RISK_OFF":
            if direction == "CALL":
                gates["blocking"].append({
                    "gate":      "B2_MACRO_CONFLICT",
                    "condition": "WARNING — RISK_OFF macro regime conflicts with BULLISH thesis",
                    "rationale": "Macro headwind forces a higher bar for long entries — "
                                 "require STRONG edge quality only (not MODERATE)",
                    "override":  "Acceptable if edge_quality=STRONG and auction=ALIGNED",
                    "hard_block": False,
                })

        # B3: Extreme vol expansion
        if state.vol_regime == "EXPANSION":
            gates["blocking"].append({
                "gate":      "B3_VOL_EXPANSION",
                "condition": "CAUTION — Vol regime is EXPANSION. "
                             "Options are expensive. Widen spread tolerance to 8%.",
                "rationale": "Buying options in extreme expansion = paying top dollar. "
                             "Ensure EV justifies premium cost.",
                "override":  f"Acceptable if EV(20d) ≥ 6% (current={outcomes.expected_value_20d:.1%})",
                "hard_block": False,
            })

        # ── SUMMARY ───────────────────────────────────────────────────────────
        n_required  = len(gates["required"])
        n_preferred = len(gates["preferred"])
        n_blocking  = sum(1 for b in gates["blocking"] if b.get("hard_block"))

        if n_blocking > 0:
            gates["summary"] = (
                f"⛔ {n_blocking} HARD BLOCK(S) — do not enter until resolved. "
                f"{n_required} required gates, {n_preferred} preferred gates."
            )
        else:
            hard_required = sum(1 for g in gates["required"] if g.get("hard_fail"))
            gates["summary"] = (
                f"✓ No hard blocks. Confirm {n_required} required gates "
                f"({hard_required} are hard-fail) + {n_preferred} preferred. "
                f"Horizon: {horizon}d | Direction: {direction}"
            )

        return gates

    def _recommend_horizon(self, state: StateVector, outcomes: ActuarialOutcomes) -> int:
        """
        Recommend hold horizon in trading days based on state and outcomes.
        Returns 5, 10, or 20.
        """
        recommended = getattr(outcomes, 'recommended_hold_days', 20) or 20

        # Shorten in compression — fast move expected
        if state.vol_regime == "COMPRESSION":
            return min(recommended, 10)

        # Shorten in late trend — limited runway
        if state.trend_maturity == "LATE":
            return min(recommended, 10)

        # Use actuarial recommendation otherwise
        return int(recommended)

    def _serialize_auction(self, auction: AuctionVerdict) -> Dict:
        """Convert auction verdict to dict"""
        return {
            'state': auction.auction_state,
            'confidence': auction.confidence,
            'acceptance_score': auction.acceptance.score,
            'control': auction.control.controller,
            'control_confidence': auction.control.confidence
        }
        
    def _serialize_state(self, state: StateVector) -> Dict:
        """Convert state vector to dict"""
        return {
            'hash': state.state_hash,
            'vol_regime': state.vol_regime,
            'trend': state.trend_direction,
            'structure': state.structure_quality
        }
        
    def _serialize_outcomes(self, outcomes: ActuarialOutcomes) -> Dict:
        """Convert outcomes to dict — labels match exact formula used"""
        return {
            'n_observations':       outcomes.n_observations,
            'win_rate_directional': getattr(outcomes, 'win_rate', None),        # P(return > 0)
            'win_rate_target':      outcomes.prob_up_10pct_20d,                 # P(hit +10%)
            'expected_value_20d':   outcomes.expected_value_20d,
            'median_gain_if_up':    getattr(outcomes, 'median_gain_if_up', None),
            'median_loss_if_down':  getattr(outcomes, 'median_loss_if_down', None),
            'confidence':           outcomes.confidence_level,
        }
