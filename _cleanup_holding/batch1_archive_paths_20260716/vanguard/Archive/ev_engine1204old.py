# ============================================================
# AVSHUNTER EV ENGINE v1.0
# Centralised Expectancy Engine (Single Source of Truth)
# ============================================================

from dataclasses import dataclass

@dataclass
class EVInputs:
    expected_value_20d: float
    win_rate: float
    delta: float
    theta: float
    iv_percentile: float
    spread_cost: float
    slippage_cost: float
    regime: str


class EVEngine:
    """
    Unified EV Engine
    Computes full expectancy chain from underlying → options → execution
    """

    REGIME_MULTIPLIER = {
        "RISK_ON": 1.1,
        "TRANSITIONAL": 1.0,
        "RISK_OFF": 0.8
    }

    def compute(self, inputs: EVInputs):
        # Step 1: Base EV
        ev_base = inputs.expected_value_20d

        # Step 2: Costs
        trading_cost = inputs.spread_cost + inputs.slippage_cost
        ev_net = ev_base - trading_cost

        # Step 3: Regime Adjustment
        regime_mult = self.REGIME_MULTIPLIER.get(inputs.regime, 1.0)
        ev_regime = ev_net * regime_mult

        # Step 4: Option Translation
        theta_penalty = abs(inputs.theta)
        iv_penalty = 0.0

        if inputs.iv_percentile > 80:
            iv_penalty = 0.02  # IV crush risk

        ev_option = (inputs.delta * ev_regime) - theta_penalty - iv_penalty

        # Step 5: Path Risk
        path_prob = inputs.win_rate
        ev_path = ev_option * path_prob

        # Step 6: Execution Cost
        ev_final = ev_path - trading_cost

        return {
            "ev_base": ev_base,
            "ev_net": ev_net,
            "ev_regime": ev_regime,
            "ev_option": ev_option,
            "ev_path": ev_path,
            "ev_final": ev_final
        }


# ============================================================
# INTEGRATION PATCH — EDGE DETECTOR
# ============================================================

# ADD inside detect_edge AFTER net_ev calculation:

"""
from vanguard.ev_engine import EVEngine, EVInputs

engine = EVEngine()

ev = engine.compute(EVInputs(
    expected_value_20d=outcomes.expected_value_20d,
    win_rate=outcomes.win_rate,
    delta=getattr(state, 'delta', 0.5),
    theta=getattr(state, 'theta', 0.01),
    iv_percentile=getattr(state, 'iv_percentile', 50),
    spread_cost=cost,
    slippage_cost=0.001,
    regime=macro_regime
))

net_ev = ev['ev_final']
"""


# ============================================================
# INTEGRATION PATCH — SCENARIO BUILDER
# ============================================================

# Replace expected_value calculation:

"""
ev_result = engine.compute(EVInputs(...))
expected_value = ev_result['ev_final']
"""


# ============================================================
# INTEGRATION PATCH — EXECUTION RUNNER v3.1
# ============================================================

import pandas as pd
from vanguard.ev_engine import EVEngine, EVInputs


def enhance_execution(df: pd.DataFrame):
    engine = EVEngine()

    results = []

    for _, row in df.iterrows():
        ev = engine.compute(EVInputs(
            expected_value_20d=row.get('expected_value_20d', 0),
            win_rate=row.get('win_rate', 0.5),
            delta=row.get('delta', 0.5),
            theta=row.get('theta', 0.01),
            iv_percentile=row.get('iv_percentile', 50),
            spread_cost=row.get('spread_cost', 0.002),
            slippage_cost=row.get('slippage_cost', 0.001),
            regime=row.get('macro_regime', 'TRANSITIONAL')
        ))

        results.append(ev)

    ev_df = pd.DataFrame(results)
    df = pd.concat([df, ev_df], axis=1)

    # Ranking
    df['ev_rank'] = df['ev_final'].rank(ascending=False)

    # Hard filter
    df['execution_flag'] = df['ev_final'].apply(
        lambda x: 'GO' if x > 0.02 else 'BLOCK'
    )

    return df


# ============================================================
# CLI FIX (YOUR CURRENT ERROR)
# ============================================================

# Update execution_intelligence_runner.py main()

"""
parser.add_argument('--run_id', type=str, required=False)

if args.run_id and not args.input:
    base = f"data/output/runs/{args.run_id}"
    args.input = f"{base}/superbrain/superbrain_enriched_{args.run_id}.csv"
    args.output = f"{base}/execution/execution_v3_1_{args.run_id}.csv"
"""


# ============================================================
# FINAL NOTE
# ============================================================

# This file gives you:
# 1. Central EV Engine
# 2. Integration hooks for Vanguard
# 3. Execution ranking logic
# 4. CLI fix for your runner
