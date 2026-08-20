from __future__ import annotations

"""
AVSHUNTER Monetisation Policy Engine v1.0
=========================================

Purpose
-------
This module standardises trade decision logic across the AVSHUNTER pipeline.
It replaces scattered binary vetoes with a structured policy model built around:

1. Fatal blocks       -> true no-trade states
2. Risk taxes         -> trade allowed, but with lower size / lower priority
3. Timing refinements -> adjust entry style, not eligibility
4. Data integrity     -> distinguish unknown from bad edge

Why this exists
---------------
The current pipeline has multiple stages that can quietly demote or reject a
potentially monetisable trade using different score systems and different hard
thresholds. That creates logic drag.

This policy engine gives all downstream scripts one shared language.

Canonical decision flow
-----------------------
A. Is the thesis real?             -> discovery / structure / actuarial layers
B. Is there a contract worth buying? -> options intelligence
C. Is the live entry still worth taking now? -> execution + morning validation

Everything else should mostly affect:
- size
- ranking
- entry style
- urgency
- contract choice

It should not hard-block unless the issue is genuinely fatal.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class DecisionState(str, Enum):
    GO = "GO"
    GO_SMALL = "GO_SMALL"
    GO_LATE = "GO_LATE"
    WAIT = "WAIT"
    BLOCK_DATA = "BLOCK_DATA"
    BLOCK_LIQUIDITY = "BLOCK_LIQUIDITY"
    BLOCK_ECONOMICS = "BLOCK_ECONOMICS"
    BLOCK_STRUCTURE = "BLOCK_STRUCTURE"
    BLOCK_EXECUTION = "BLOCK_EXECUTION"


class Severity(str, Enum):
    FATAL = "FATAL"
    TAX = "TAX"
    TIMING = "TIMING"
    INFO = "INFO"


@dataclass
class RuleEvent:
    rule_id: str
    severity: Severity
    passed: bool
    value: Optional[float] = None
    threshold: Optional[float] = None
    note: str = ""
    bucket: str = "general"
    tax_bps: int = 0


@dataclass
class PolicyInput:
    # Structure / thesis
    thesis_valid: Optional[bool] = None
    structure_confidence: Optional[float] = None
    truth_confidence: Optional[float] = None
    contradictions: int = 0

    # Data quality
    data_complete: bool = True
    stale_data: bool = False
    quote_source_live: bool = False

    # Options economics
    spread_pct: Optional[float] = None
    premium: Optional[float] = None
    theta_drag_pct: Optional[float] = None
    breakeven_pct: Optional[float] = None
    runway_pct: Optional[float] = None
    iv_rank: Optional[float] = None
    delta: Optional[float] = None
    dte: Optional[int] = None

    # Raw trade economics (from options intelligence — for quality floor gate)
    rr_raw:              Optional[float] = None   # R:R from options intelligence
    ev_raw:              Optional[float] = None   # EV ratio from options intelligence

    # Execution / live context
    drift_pct: Optional[float] = None
    nbbo_imbalance: Optional[float] = None
    iv_distortion_score: Optional[float] = None
    gamma_flip_gap_pct: Optional[float] = None

    # Regime / strategy context
    regime_state: str = "UNKNOWN"
    setup_type: str = "UNKNOWN"
    tier: Optional[int] = None
    execution_mode: Optional[str] = None


@dataclass
class PolicyOutput:
    state: DecisionState
    base_size_mult: float
    final_size_mult: float
    priority_score: float
    hard_block_reason: Optional[str]
    rule_events: List[RuleEvent] = field(default_factory=list)
    remediation: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class MonetisationPolicy:
    """
    Shared policy engine.

    Design principles:
    - Separate unknown from bad edge.
    - Use hard blocks only for truly fatal conditions.
    - Convert many previous vetoes into risk taxes.
    - Preserve monetisable trades by reducing size before rejecting.
    """

    # True hard blocks — do not trade without these
    HARD_SPREAD_BLOCK = 0.20
    HARD_DATA_LIVE_SPREAD_BLOCK = 0.15
    HARD_THETA_BLOCK = 0.80
    HARD_RUNWAY_MIN = 0.0
    HARD_BREAKEVEN_RUNWAY_RATIO = 0.90
    HARD_DTE_MIN = 5
    HARD_STRUCTURE_MIN = 45.0
    # ENHANCEMENT 4 (2026-04-16): Minimum contract premium gate.
    # Tastytrade charges $1/contract each side = $2 round-trip.
    # On a $10 premium position that is 20% cost before any slippage —
    # the entire expected edge is consumed. Set floor at $20 so commissions
    # are always ≤ 10% of position value, preserving the structural edge.
    # Only fires when a real premium is present (None = no chain yet, skip).
    HARD_PREMIUM_MIN = 20.0

    # Taxes / sizing penalties
    SOFT_SPREAD_WARN = 0.08
    SOFT_THETA_WARN = 0.45
    SOFT_IVR_HIGH = 0.70
    SOFT_DRIFT_WARN = 0.02
    SOFT_DRIFT_LATE = 0.04
    SOFT_DELTA_LOW = 0.20
    SOFT_DELTA_HIGH = 0.60
    SOFT_GAMMA_TIGHT = 0.25

    def evaluate(self, x: PolicyInput) -> PolicyOutput:
        events: List[RuleEvent] = []
        # Local safe float helper for quality floor (avoids import issues)
        def _safe_float_local(v, fallback=0.0):
            if v is None:
                return fallback
            try:
                f = float(v)
                return f if f == f else fallback  # nan check
            except:
                return fallback
        remediation: List[str] = []
        notes: List[str] = []

        base_size = self._base_size_from_regime(x.regime_state)
        size_mult = base_size
        priority = 50.0
        hard_block: Optional[Tuple[DecisionState, str]] = None
        late_entry_flag = False
        wait_flag = False

        # ------------------------------------------------------------------
        # 1) Data integrity — unknown must not masquerade as bad edge
        # ------------------------------------------------------------------
        if not x.data_complete:
            events.append(RuleEvent("DATA_001", Severity.FATAL, False, note="Required data missing", bucket="data"))
            hard_block = (DecisionState.BLOCK_DATA, "Required data missing")
        elif x.stale_data and not x.quote_source_live:
            events.append(RuleEvent("DATA_002", Severity.FATAL, False, note="Data stale and no live quote", bucket="data"))
            hard_block = (DecisionState.BLOCK_DATA, "Stale data without live quote")
        else:
            events.append(RuleEvent("DATA_000", Severity.INFO, True, note="Data integrity acceptable", bucket="data"))

        # ------------------------------------------------------------------
        # 2) Structure — thesis must be real enough to justify capital
        # ------------------------------------------------------------------
        if hard_block is None:
            if x.thesis_valid is False:
                events.append(RuleEvent("STR_001", Severity.FATAL, False, note="Thesis invalid", bucket="structure"))
                hard_block = (DecisionState.BLOCK_STRUCTURE, "Structure / thesis invalid")
            elif x.structure_confidence is not None and x.structure_confidence < self.HARD_STRUCTURE_MIN:
                events.append(RuleEvent("STR_002", Severity.FATAL, False, value=x.structure_confidence, threshold=self.HARD_STRUCTURE_MIN, note="Structure confidence too low", bucket="structure"))
                hard_block = (DecisionState.BLOCK_STRUCTURE, "Structure confidence too low")
            else:
                events.append(RuleEvent("STR_000", Severity.INFO, True, value=x.structure_confidence, note="Structure acceptable", bucket="structure"))

        if hard_block is None and x.truth_confidence is not None:
            if x.truth_confidence < 55:
                events.append(RuleEvent("STR_003", Severity.TAX, False, value=x.truth_confidence, threshold=55, note="Truth confidence soft penalty", bucket="structure", tax_bps=2000))
                size_mult *= 0.80
                priority -= 6
                remediation.append("Wait for cleaner structure confirmation or better tape alignment.")
            else:
                events.append(RuleEvent("STR_004", Severity.INFO, True, value=x.truth_confidence, threshold=55, note="Truth confidence acceptable", bucket="structure"))

        if hard_block is None and x.contradictions > 0:
            penalty = min(0.03 * x.contradictions, 0.15)
            events.append(RuleEvent("STR_005", Severity.TAX, False, value=float(x.contradictions), threshold=0, note="Contradictions reduce size", bucket="structure", tax_bps=int(penalty * 10000)))
            size_mult *= (1.0 - penalty)
            priority -= 2 * x.contradictions

        # ------------------------------------------------------------------
        # 3) Contract economics — the central monetisation gate
        # ------------------------------------------------------------------
        if hard_block is None:
            if x.dte is not None and x.dte < self.HARD_DTE_MIN:
                events.append(RuleEvent("OPT_001", Severity.FATAL, False, value=float(x.dte), threshold=self.HARD_DTE_MIN, note="DTE too low", bucket="economics"))
                hard_block = (DecisionState.BLOCK_ECONOMICS, "DTE too low for monetisation")
            else:
                events.append(RuleEvent("OPT_000", Severity.INFO, True, value=float(x.dte) if x.dte is not None else None, note="DTE acceptable", bucket="economics"))

        # ENHANCEMENT 4 (2026-04-16): Minimum contract premium gate.
        # OPT_015: premium < $20 → commission cost ≥ 10% of position → edge destroyed.
        # Only fires when a real premium is present; None means no chain was fetched.
        if hard_block is None and x.premium is not None and x.premium > 0:
            if x.premium < self.HARD_PREMIUM_MIN:
                events.append(RuleEvent(
                    "OPT_015", Severity.FATAL, False,
                    value=x.premium, threshold=self.HARD_PREMIUM_MIN,
                    note=f"Premium ${x.premium:.2f} < ${self.HARD_PREMIUM_MIN:.0f} minimum — "
                         f"$2 commission = {200/x.premium:.0f}% of position, destroys edge",
                    bucket="economics"
                ))
                hard_block = (DecisionState.BLOCK_ECONOMICS,
                              f"Premium too low for commission efficiency (${x.premium:.2f} < ${self.HARD_PREMIUM_MIN:.0f})")
            else:
                events.append(RuleEvent("OPT_016", Severity.INFO, True,
                    value=x.premium, threshold=self.HARD_PREMIUM_MIN,
                    note=f"Premium ${x.premium:.2f} — commission-efficient", bucket="economics"))

        # ── Minimum trade quality floor (prevents debris from passing post-theta-fix) ──
        # Block when BOTH RR is negative AND EV is negative:
        # These signals have neither structural reward nor actuarial expectancy.
        # RR alone can be negative on short-dated options; EV alone can be negative
        # in unfavourable regimes — but BOTH negative together is genuinely untradeable.
        if hard_block is None and x.premium is not None:
            _rr_raw  = _safe_float_local(getattr(x, 'rr_raw',  None), 0.0)
            _ev_raw  = _safe_float_local(getattr(x, 'ev_raw',  None), 0.0)
            if _rr_raw < 0 and _ev_raw < 0:
                events.append(RuleEvent("OPT_014", Severity.FATAL, False,
                    value=_rr_raw, threshold=0.0,
                    note="Negative RR and negative EV — no structural or actuarial edge", bucket="economics"))
                hard_block = (DecisionState.BLOCK_ECONOMICS, "Negative RR and negative EV")

        if hard_block is None and x.spread_pct is not None:
            hard_spread = self.HARD_DATA_LIVE_SPREAD_BLOCK if x.quote_source_live else self.HARD_SPREAD_BLOCK
            if x.spread_pct > hard_spread:
                events.append(RuleEvent("OPT_002", Severity.FATAL, False, value=x.spread_pct, threshold=hard_spread, note="Spread too wide", bucket="liquidity"))
                hard_block = (DecisionState.BLOCK_LIQUIDITY, "Spread too wide")
            elif x.spread_pct > self.SOFT_SPREAD_WARN:
                events.append(RuleEvent("OPT_003", Severity.TAX, False, value=x.spread_pct, threshold=self.SOFT_SPREAD_WARN, note="Spread warning", bucket="liquidity", tax_bps=2500))
                size_mult *= 0.75
                priority -= 8
                remediation.append("Use limit orders only and reduce size due to spread cost.")
            else:
                events.append(RuleEvent("OPT_004", Severity.INFO, True, value=x.spread_pct, threshold=self.SOFT_SPREAD_WARN, note="Spread acceptable", bucket="liquidity"))

        if hard_block is None and x.theta_drag_pct is not None:
            if x.theta_drag_pct > self.HARD_THETA_BLOCK:
                events.append(RuleEvent("OPT_005", Severity.FATAL, False, value=x.theta_drag_pct, threshold=self.HARD_THETA_BLOCK, note="Theta drag too high", bucket="economics"))
                hard_block = (DecisionState.BLOCK_ECONOMICS, "Theta drag too high")
            elif x.theta_drag_pct > self.SOFT_THETA_WARN:
                events.append(RuleEvent("OPT_006", Severity.TAX, False, value=x.theta_drag_pct, threshold=self.SOFT_THETA_WARN, note="Theta drag warning", bucket="economics", tax_bps=2000))
                size_mult *= 0.80
                priority -= 5
                remediation.append("Prefer more time or a less expensive contract.")
            else:
                events.append(RuleEvent("OPT_007", Severity.INFO, True, value=x.theta_drag_pct, threshold=self.SOFT_THETA_WARN, note="Theta acceptable", bucket="economics"))

        if hard_block is None and x.runway_pct is not None and x.breakeven_pct is not None:
            ratio = x.runway_pct / max(x.breakeven_pct, 1e-6)
            if x.runway_pct <= self.HARD_RUNWAY_MIN or ratio < self.HARD_BREAKEVEN_RUNWAY_RATIO:
                events.append(RuleEvent("OPT_008", Severity.FATAL, False, value=ratio, threshold=self.HARD_BREAKEVEN_RUNWAY_RATIO, note="Insufficient runway vs breakeven", bucket="economics"))
                hard_block = (DecisionState.BLOCK_ECONOMICS, "Insufficient runway vs breakeven")
            elif ratio < 1.5:
                events.append(RuleEvent("OPT_009", Severity.TAX, False, value=ratio, threshold=1.5, note="Thin runway", bucket="economics", tax_bps=2500))
                size_mult *= 0.75
                priority -= 7
                remediation.append("Select a lower-cost contract or wait for a better entry closer to support / resistance.")
            else:
                events.append(RuleEvent("OPT_010", Severity.INFO, True, value=ratio, threshold=1.5, note="Runway healthy", bucket="economics"))

        if hard_block is None and x.iv_rank is not None and x.iv_rank > self.SOFT_IVR_HIGH:
            events.append(RuleEvent("OPT_011", Severity.TAX, False, value=x.iv_rank, threshold=self.SOFT_IVR_HIGH, note="High IV rank raises entry tax", bucket="economics", tax_bps=1500))
            size_mult *= 0.85
            priority -= 4
            remediation.append("High IV: prefer only the cleanest setups or wait for IV relief.")

        if hard_block is None and x.delta is not None:
            if x.delta < self.SOFT_DELTA_LOW or x.delta > self.SOFT_DELTA_HIGH:
                events.append(RuleEvent("OPT_012", Severity.TAX, False, value=x.delta, threshold=self.SOFT_DELTA_LOW, note="Delta outside preferred monetisation band", bucket="economics", tax_bps=1000))
                size_mult *= 0.90
                priority -= 2
                remediation.append("Re-rank contract choice by delta / DTE rather than forcing current pick.")
            else:
                events.append(RuleEvent("OPT_013", Severity.INFO, True, value=x.delta, note="Delta in preferred range", bucket="economics"))

        # ------------------------------------------------------------------
        # 4) Live execution — refine timing and size before rejecting
        # ------------------------------------------------------------------
        if hard_block is None and x.drift_pct is not None:
            if x.drift_pct > self.SOFT_DRIFT_LATE:
                events.append(RuleEvent("EXE_001", Severity.TIMING, False, value=x.drift_pct, threshold=self.SOFT_DRIFT_LATE, note="Late entry condition", bucket="execution"))
                late_entry_flag = True
                size_mult *= 0.70
                priority -= 5
                remediation.append("Late entry: either size down or re-select strike / delta instead of chasing.")
            elif x.drift_pct > self.SOFT_DRIFT_WARN:
                events.append(RuleEvent("EXE_002", Severity.TAX, False, value=x.drift_pct, threshold=self.SOFT_DRIFT_WARN, note="Entry drift warning", bucket="execution", tax_bps=1500))
                size_mult *= 0.85
                priority -= 3
            else:
                events.append(RuleEvent("EXE_003", Severity.INFO, True, value=x.drift_pct, threshold=self.SOFT_DRIFT_WARN, note="Drift acceptable", bucket="execution"))

        if hard_block is None and x.iv_distortion_score is not None and x.iv_distortion_score > 0.80:
            events.append(RuleEvent("EXE_004", Severity.FATAL, False, value=x.iv_distortion_score, threshold=0.80, note="Live IV distortion too high", bucket="execution"))
            hard_block = (DecisionState.BLOCK_EXECUTION, "Live IV distortion too high")
        elif hard_block is None and x.iv_distortion_score is not None and x.iv_distortion_score > 0.60:
            events.append(RuleEvent("EXE_005", Severity.TAX, False, value=x.iv_distortion_score, threshold=0.60, note="Live IV distortion warning", bucket="execution", tax_bps=2000))
            size_mult *= 0.80
            priority -= 4

        if hard_block is None and x.gamma_flip_gap_pct is not None:
            if abs(x.gamma_flip_gap_pct) < self.SOFT_GAMMA_TIGHT:
                events.append(RuleEvent("EXE_006", Severity.TIMING, False, value=x.gamma_flip_gap_pct, threshold=self.SOFT_GAMMA_TIGHT, note="Too close to gamma flip / wall", bucket="execution"))
                wait_flag = True
                size_mult *= 0.85
                priority -= 3
                remediation.append("Wait for cleaner clearance away from gamma flip / wall.")
            else:
                events.append(RuleEvent("EXE_007", Severity.INFO, True, value=x.gamma_flip_gap_pct, threshold=self.SOFT_GAMMA_TIGHT, note="Gamma gap acceptable", bucket="execution"))

        # ------------------------------------------------------------------
        # 5) Execution mode overlay — preserve existing logic, then modulate size
        # ------------------------------------------------------------------
        execution_mode = getattr(x, "execution_mode", None)

        if hard_block is None and execution_mode:
            execution_mode = str(execution_mode).upper().strip()

            if execution_mode == "PROBE":
                size_mult *= 0.25
                notes.append("Probe Mode - High risk")
            elif execution_mode == "REDUCED_EXECUTE":
                size_mult *= 0.50
                notes.append("Reduced Execute - Medium risk")
            elif execution_mode == "FULL_EXECUTE":
                notes.append("Full Execute - Standard sizing")
            elif execution_mode == "WAIT":
                wait_flag = True
                notes.append("Execution mode WAIT")
            elif execution_mode == "BLOCKED":
                hard_block = (DecisionState.BLOCK_EXECUTION, "Blocked by execution mode")
                notes.append("Execution mode BLOCKED")

        # ------------------------------------------------------------------
        # Final state logic
        # ------------------------------------------------------------------
        size_mult = max(0.10, min(size_mult, 1.00))
        priority = max(0.0, min(priority, 100.0))

        if hard_block is not None:
            state, reason = hard_block
            return PolicyOutput(
                state=state,
                base_size_mult=base_size,
                final_size_mult=0.0,
                priority_score=priority,
                hard_block_reason=reason,
                rule_events=events,
                remediation=remediation,
                notes=notes,
            )

        if wait_flag and size_mult < 0.75:
            state = DecisionState.WAIT
        elif late_entry_flag and size_mult < 0.85:
            state = DecisionState.GO_LATE
        elif size_mult < 0.85:
            state = DecisionState.GO_SMALL
        else:
            state = DecisionState.GO

        return PolicyOutput(
            state=state,
            base_size_mult=base_size,
            final_size_mult=size_mult,
            priority_score=priority,
            hard_block_reason=None,
            rule_events=events,
            remediation=remediation,
            notes=notes,
        )

    @staticmethod
    def _base_size_from_regime(regime_state: str) -> float:
        regime = str(regime_state).upper().strip()
        if regime in {"RISK_OFF", "FLIPPED"}:
            return 0.35
        if regime in {"TRANSITIONAL", "CHOPPY", "CHOPPY_NEUTRAL", "DRIFTING"}:
            return 0.60
        if regime in {"RISK_ON", "TRENDING_BULL", "TRENDING_BEAR", "STABLE"}:
            return 1.00
        return 0.75


# --------------------------------------------------------------------------
# Integration helpers for existing AVSHUNTER scripts
# --------------------------------------------------------------------------

def map_options_row_to_policy_input(row: Dict) -> PolicyInput:
    """
    Translate an options-intelligence / superbrain style row into PolicyInput.
    This keeps integration light-touch.
    """
    def _float(k: str) -> Optional[float]:
        v = row.get(k)
        if v in (None, "", "nan", "NaN", "N/A"):
            return None
        try:
            return float(v)
        except Exception:
            return None

    def _int(k: str) -> Optional[int]:
        v = row.get(k)
        if v in (None, "", "nan", "NaN", "N/A"):
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    quote_source = str(row.get("quote_source") or row.get("md_quote_source") or "").lower()

    # ── theta_drag_pct unit normalisation ──────────────────────────────────────
    # Options intelligence writes theta_drag_pct as 0-100 percentage scale.
    # E.g. 44.47 = 44.47% of premium consumed by theta over hold period.
    # Policy gates use 0-1 decimal (HARD_THETA_BLOCK=0.80 = 80%).
    # Divide by 100 to normalise. Guard: values <= 1.0 assumed already decimal.
    _theta_raw = _float("theta_drag_pct")
    _theta_normalised = (_theta_raw / 100.0) if (_theta_raw is not None and _theta_raw > 1.0) else _theta_raw

    # ── actuarial EV: prefer 20d window; fall back to available horizons ────
    _win_rate = _float("win_rate_20d") or _float("win_rate_10d") or _float("win_rate_5d") or _float("win_rate")
    _ev_pct   = _float("expected_value_20d") or _float("expected_value_10d") or _float("expected_value_5d") or _float("expected_value")

    return PolicyInput(
        thesis_valid = bool(row.get("thesis_valid", True)),
        structure_confidence = _float("structure_confidence") or _float("predictability") or _float("truth_confidence"),
        truth_confidence = _float("truth_confidence"),
        contradictions = _int("contradictions_count") or 0,
        data_complete = not bool(row.get("data_missing", False)),
        stale_data = bool(row.get("stale_data", False)),
        quote_source_live = ("marketdata" in quote_source) or bool(row.get("live_quote", False)),
        spread_pct = _float("spread_pct_live") or _float("spread_pct"),
        premium = _float("contract_premium") or _float("mark"),
        theta_drag_pct = _theta_normalised,
        breakeven_pct = _float("breakeven_pct"),
        runway_pct = _float("runway_pct"),   # DO NOT fallback to gamma_flip_gap_pct — different concepts
        iv_rank = _float("iv_rank"),
        delta = _float("contract_delta") or _float("delta"),
        dte = _int("contract_dte") or _int("dte"),
        rr_raw = _float("rr_options") or _float("rr"),   # raw R:R for quality floor
        ev_raw = _float("ev_adjusted") or _float("ev_adj") or _float("ev"),
        drift_pct = _float("entry_drift_pct") or _float("drift_pct"),
        nbbo_imbalance = _float("obi_score") or _float("nbbo_imbalance"),
        iv_distortion_score = _float("iv_distortion_score"),
        gamma_flip_gap_pct = _float("gamma_flip_gap_pct_live") or _float("gamma_flip_gap_pct"),
        regime_state = str(row.get("regime_state") or row.get("macro_regime") or "UNKNOWN"),
        setup_type = str(row.get("setup_type") or row.get("campaign_type") or "UNKNOWN"),
        tier = _int("tier"),
        execution_mode = row.get("execution_mode"),
    )


def summarise_policy_output(out: PolicyOutput) -> Dict:
    return {
        "mp_state": out.state.value,
        "mp_base_size_mult": round(out.base_size_mult, 4),
        "mp_final_size_mult": round(out.final_size_mult, 4),
        "mp_priority_score": round(out.priority_score, 2),
        "mp_hard_block_reason": out.hard_block_reason or "",
        "mp_rule_hits": len([e for e in out.rule_events if not e.passed]),
        "mp_remediation": " | ".join(out.remediation[:3]),
    }


if __name__ == "__main__":
    # Minimal self-test examples
    engine = MonetisationPolicy()

    good = PolicyInput(
        thesis_valid=True,
        structure_confidence=72,
        truth_confidence=68,
        contradictions=1,
        data_complete=True,
        stale_data=False,
        quote_source_live=True,
        spread_pct=0.05,
        theta_drag_pct=0.22,
        breakeven_pct=2.1,
        runway_pct=5.4,
        iv_rank=0.58,
        delta=0.42,
        dte=28,
        drift_pct=0.012,
        gamma_flip_gap_pct=0.80,
        regime_state="RISK_ON",
        execution_mode="FULL_EXECUTE",
    )

    late = PolicyInput(
        thesis_valid=True,
        structure_confidence=70,
        truth_confidence=64,
        data_complete=True,
        quote_source_live=True,
        spread_pct=0.06,
        theta_drag_pct=0.30,
        breakeven_pct=2.0,
        runway_pct=3.0,
        iv_rank=0.76,
        delta=0.38,
        dte=21,
        drift_pct=0.055,
        gamma_flip_gap_pct=0.22,
        regime_state="TRANSITIONAL",
        execution_mode="PROBE",
    )

    bad = PolicyInput(
        thesis_valid=True,
        structure_confidence=62,
        truth_confidence=61,
        data_complete=True,
        quote_source_live=True,
        spread_pct=0.19,
        theta_drag_pct=0.88,
        breakeven_pct=2.3,
        runway_pct=1.1,
        iv_rank=0.82,
        delta=0.17,
        dte=4,
        regime_state="RISK_OFF",
        execution_mode="BLOCKED",
    )

    for name, case in [("good", good), ("late", late), ("bad", bad)]:
        result = engine.evaluate(case)
        print(name, summarise_policy_output(result))
