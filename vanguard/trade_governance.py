"""
VANGUARD — Trade Governance Engine
====================================
Runs on every daily pass for each open Trade Contract.
Answers 5 invalidation questions — NOT the entry question.

RULE: Scanner logic cannot override campaign logic.
      Only explicit thesis breach triggers exit.

The 5 Invalidation Questions
------------------------------
Q1. Price Invalidation   — Has price violated the entry stop level?
Q2. Macro Regime Flip    — Has the macro regime changed from entry?
Q3. Vol Regime Shift     — Has volatility regime changed materially?
Q4. Structure Collapse   — Has structure quality degraded severely?
Q5. Horizon Expiry       — Has the signal half-life expired?

Breach Severity
----------------
HARD breach  → immediate EXIT  (price violation, macro flip)
SOFT breach  → TIGHTEN first   (vol shift, structure degraded)
2x SOFT      → EXIT

Verdict
--------
0 breaches        → HOLD
1 soft breach     → TIGHTEN
1 hard breach     → EXIT
2+ soft breaches  → EXIT
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from .trade_contract import (
    load_contract, save_contract, close_contract,
    list_open_contracts, GOV_LOG_DIR
)


# ── THRESHOLDS ────────────────────────────────────────────────────────────────

# How many trading days after entry before governance auto-expires the contract
HORIZON_TRADING_DAY_BUFFER = 2   # Allow 2 extra days past horizon before expiry

# Vol regime changes that constitute a SOFT breach
# Entry vol → current vol combinations that are material shifts
MATERIAL_VOL_SHIFTS = {
    ("COMPRESSION", "EXPANSION"),
    ("EXPANSION",   "COMPRESSION"),
}

# Macro regime changes that constitute a HARD breach
HARD_MACRO_FLIPS = {
    ("RISK_ON",  "RISK_OFF"),
    ("RISK_OFF", "RISK_ON"),
}


# ── GOVERNANCE ENGINE ─────────────────────────────────────────────────────────

class TradeGovernanceEngine:
    """
    Evaluates each open Trade Contract on every daily run.
    Never asks: 'Would I enter this trade today?'
    Always asks: 'Has the original thesis been invalidated?'
    """

    def evaluate_all(
        self,
        current_states: dict,   # {ticker: StateVector} from today's Vanguard run
        current_prices: dict,   # {ticker: float} latest prices
    ) -> dict:
        """
        Evaluate all open contracts.
        Returns dict: {ticker: governance_result}
        Also writes daily governance log.
        """
        results = {}
        contracts = list_open_contracts()

        if not contracts:
            print("[GOVERNANCE] No open contracts to evaluate.")
            return results

        print(f"\n[GOVERNANCE] Evaluating {len(contracts)} open contract(s)...")

        for contract_path in contracts:
            ticker = contract_path.stem.split("_")[0]
            contract = load_contract(contract_path)

            current_state = current_states.get(ticker)
            current_price = current_prices.get(ticker)

            result = self._evaluate_contract(
                contract, contract_path, current_state, current_price
            )
            results[ticker] = result

        # Write daily governance log
        self._write_governance_log(results)

        return results

    def evaluate_single(
        self,
        ticker: str,
        current_state,          # StateVector or None
        current_price: float,
    ) -> Optional[dict]:
        """
        Evaluate one ticker's open contract.
        Returns governance result dict, or None if no open contract.
        """
        from .trade_contract import find_open_contract
        contract_path = find_open_contract(ticker)
        if not contract_path:
            return None

        contract = load_contract(contract_path)
        return self._evaluate_contract(contract, contract_path, current_state, current_price)

    # ── CORE EVALUATION ───────────────────────────────────────────────────────

    def _evaluate_contract(
        self,
        contract: dict,
        contract_path: Path,
        current_state,
        current_price: Optional[float],
    ) -> dict:
        """Run all 5 invalidation questions and determine verdict."""

        ticker       = contract["ticker"]
        entry_date   = contract["entry_date"]
        horizon_type = contract["horizon_type"]
        days_held    = contract.get("days_in_trade", 0) + 1

        hard_breaches = []
        soft_breaches = []
        passing       = []

        # ── Q1: Price Invalidation (HARD) ─────────────────────────────────────
        q1 = self._check_price_invalidation(contract, current_price)
        if q1["breach"]:
            hard_breaches.append(q1)
        else:
            passing.append(q1)

        # ── Q2: Macro Regime Flip (HARD) ──────────────────────────────────────
        q2 = self._check_macro_flip(contract, current_state)
        if q2["breach"]:
            soft_breaches.append(q2)
        else:
            passing.append(q2)

        # ── Q3: Vol Regime Shift (SOFT) ───────────────────────────────────────
        q3 = self._check_vol_shift(contract, current_state)
        if q3["breach"]:
            soft_breaches.append(q3)
        else:
            passing.append(q3)

        # ── Q4: Structure Collapse (SOFT) ─────────────────────────────────────
        q4 = self._check_structure_collapse(contract, current_state)
        if q4["breach"]:
            soft_breaches.append(q4)
        else:
            passing.append(q4)

        # ── Q5: Horizon Expiry (HARD) ─────────────────────────────────────────
        q5 = self._check_horizon_expiry(contract, days_held)
        if q5["breach"]:
            hard_breaches.append(q5)
        else:
            passing.append(q5)

        # ── VERDICT LOGIC ─────────────────────────────────────────────────────
        if hard_breaches:
            verdict  = "EXIT"
            reason   = f"HARD breach: {hard_breaches[0]['reason']}"
        elif len(soft_breaches) >= 2:
            verdict  = "EXIT"
            reason   = f"2x SOFT breach: {' | '.join(b['reason'] for b in soft_breaches)}"
        elif len(soft_breaches) == 1:
            verdict  = "TIGHTEN"
            reason   = f"SOFT breach: {soft_breaches[0]['reason']}"
        else:
            verdict  = "HOLD"
            reason   = "No invalidation conditions met — thesis intact"

        # ── BUILD RESULT ──────────────────────────────────────────────────────
        daily_check = {
            "date":          datetime.now().strftime("%Y%m%d"),
            "days_in_trade": days_held,
            "current_price": current_price,
            "verdict":       verdict,
            "reason":        reason,
            "hard_breaches": [b["reason"] for b in hard_breaches],
            "soft_breaches": [b["reason"] for b in soft_breaches],
            "passing_gates": [p["gate"] for p in passing],
        }

        # ── UPDATE CONTRACT ───────────────────────────────────────────────────
        contract["days_in_trade"] = days_held
        contract["status"]        = verdict
        contract["governance_history"].append(daily_check)

        if verdict == "EXIT":
            close_contract(contract, contract_path, reason)
        else:
            save_contract(contract, contract_path)

        # ── PRINT SUMMARY ─────────────────────────────────────────────────────
        icon = {"HOLD": "✓", "TIGHTEN": "⚠", "EXIT": "✗"}[verdict]
        print(f"  [{icon}] {ticker} ({horizon_type}, Day {days_held}) → {verdict} | {reason}")

        return {
            "ticker":        ticker,
            "verdict":       verdict,
            "reason":        reason,
            "days_in_trade": days_held,
            "daily_check":   daily_check,
            "contract":      contract,
        }

    # ── Q1: PRICE INVALIDATION ────────────────────────────────────────────────

    def _check_price_invalidation(self, contract: dict, current_price: Optional[float]) -> dict:
        gate = "Q1_PRICE_INVALIDATION"

        if current_price is None:
            return {"gate": gate, "breach": False,
                    "reason": "Q1 PASS: No price data — cannot evaluate, holding"}

        invalidation_price = contract.get("invalidation_price", 0)
        direction          = contract.get("direction", "CALL")
        entry_price        = contract.get("entry_price", 0)

        if direction == "CALL":
            # Long thesis: invalidated if price falls below stop
            if invalidation_price > 0 and current_price < invalidation_price:
                return {
                    "gate": gate, "breach": True, "severity": "HARD",
                    "reason": (
                        f"Q1 BREACH: Price {current_price:.2f} below invalidation "
                        f"{invalidation_price:.2f} (entry {entry_price:.2f}) — long thesis broken"
                    )
                }
        elif direction == "PUT":
            # Short thesis: invalidated if price rises above stop
            if invalidation_price > 0 and current_price > invalidation_price:
                return {
                    "gate": gate, "breach": True, "severity": "HARD",
                    "reason": (
                        f"Q1 BREACH: Price {current_price:.2f} above invalidation "
                        f"{invalidation_price:.2f} (entry {entry_price:.2f}) — short thesis broken"
                    )
                }

        return {"gate": gate, "breach": False,
                "reason": f"Q1 PASS: Price {current_price:.2f} within thesis bounds"}

    # ── Q2: MACRO REGIME FLIP ─────────────────────────────────────────────────

    def _check_macro_flip(self, contract: dict, current_state) -> dict:
        gate = "Q2_MACRO_REGIME"

        entry_macro   = contract.get("entry_macro_regime", "TRANSITIONAL")
        current_macro = getattr(current_state, "macro_regime", None) if current_state else None

        if current_macro is None:
            return {"gate": gate, "breach": False,
                    "reason": "Q2 PASS: No macro data available — cannot evaluate, holding"}

        if current_macro == entry_macro:
            return {"gate": gate, "breach": False,
                    "reason": f"Q2 PASS: Macro regime unchanged ({entry_macro})"}

        # Macro never closes or invalidates a ticker thesis. Preserve every
        # transition as an advisory review item for the human trader.
        return {
            "gate": gate, "breach": True, "severity": "ADVISORY",
            "reason": (
                f"Q2 ADVISORY: Macro changed {entry_macro} → {current_macro}. "
                "Review sector rotation and expression; price/structure retain authority."
            )
        }

    # ── Q3: VOL REGIME SHIFT ──────────────────────────────────────────────────

    def _check_vol_shift(self, contract: dict, current_state) -> dict:
        gate = "Q3_VOL_REGIME"

        entry_vol   = contract.get("entry_vol_regime", "NORMAL")
        current_vol = getattr(current_state, "vol_regime", None) if current_state else None

        if current_vol is None:
            return {"gate": gate, "breach": False,
                    "reason": "Q3 PASS: No vol data — cannot evaluate, holding"}

        if current_vol == entry_vol:
            return {"gate": gate, "breach": False,
                    "reason": f"Q3 PASS: Vol regime unchanged ({entry_vol})"}

        transition = (entry_vol, current_vol)
        if transition in MATERIAL_VOL_SHIFTS:
            return {
                "gate": gate, "breach": True, "severity": "SOFT",
                "reason": (
                    f"Q3 SOFT: Vol regime shifted materially {entry_vol} → {current_vol}. "
                    f"Entry pricing assumptions no longer valid — tighten stop."
                )
            }

        return {"gate": gate, "breach": False,
                "reason": f"Q3 PASS: Vol shift {entry_vol} → {current_vol} not material"}

    # ── Q4: STRUCTURE COLLAPSE ────────────────────────────────────────────────

    def _check_structure_collapse(self, contract: dict, current_state) -> dict:
        gate = "Q4_STRUCTURE_QUALITY"

        entry_structure   = contract.get("entry_structure_quality", "NEUTRAL")
        current_structure = getattr(current_state, "structure_quality", None) if current_state else None

        if current_structure is None:
            return {"gate": gate, "breach": False,
                    "reason": "Q4 PASS: No structure data — cannot evaluate, holding"}

        # Only breach if structure entered as STRONG and has collapsed to WEAK
        if entry_structure == "STRONG" and current_structure == "WEAK":
            return {
                "gate": gate, "breach": True, "severity": "SOFT",
                "reason": (
                    f"Q4 SOFT: Structure collapsed STRONG → WEAK. "
                    f"Auction-based thesis foundation degraded — tighten stop."
                )
            }

        # NEUTRAL → WEAK is a warning but not a breach
        if entry_structure == "NEUTRAL" and current_structure == "WEAK":
            return {"gate": gate, "breach": False,
                    "reason": f"Q4 PASS: Structure {entry_structure} → {current_structure} (watch)"}

        return {"gate": gate, "breach": False,
                "reason": f"Q4 PASS: Structure {entry_structure} → {current_structure}"}

    # ── Q5: HORIZON EXPIRY ────────────────────────────────────────────────────

    def _check_horizon_expiry(self, contract: dict, days_held: int) -> dict:
        gate = "Q5_HORIZON_EXPIRY"

        horizon_map = {"5D": 5, "10D": 10, "20D": 20, "90D": 90}
        horizon_type = contract.get("horizon_type", "20D")
        max_days     = horizon_map.get(horizon_type.upper(), 20) + HORIZON_TRADING_DAY_BUFFER

        if days_held >= max_days:
            return {
                "gate": gate, "breach": True, "severity": "HARD",
                "reason": (
                    f"Q5 BREACH: Signal half-life expired. "
                    f"{days_held} trading days held vs {horizon_type} horizon "
                    f"(+{HORIZON_TRADING_DAY_BUFFER}d buffer). Model authority ended."
                )
            }

        days_remaining = max_days - days_held
        return {"gate": gate, "breach": False,
                "reason": f"Q5 PASS: {days_remaining} trading days remaining in {horizon_type} window"}

    # ── GOVERNANCE LOG ────────────────────────────────────────────────────────

    def _write_governance_log(self, results: dict):
        """Write daily governance summary to governance_log/."""
        if not results:
            return
        date_str  = datetime.now().strftime("%Y%m%d")
        log_path  = GOV_LOG_DIR / f"governance_{date_str}.json"
        summary   = {
            "date":    date_str,
            "results": {
                ticker: {
                    "verdict":       r["verdict"],
                    "reason":        r["reason"],
                    "days_in_trade": r["days_in_trade"],
                }
                for ticker, r in results.items()
            }
        }
        log_path.write_text(json.dumps(summary, indent=2))
        print(f"[GOVERNANCE] Log written → {log_path.name}")
