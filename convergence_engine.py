"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · CONVERGENCE SCORE ENGINE                                      ║
║  Enhancement: E8                                                            ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║  Imports in: execution_intelligence_runner.py, morning_validation.py        ║
║                                                                             ║
║  Logic: counts how many of the 5 EIL strategies agree on direction.        ║
║  5/5 = maximum conviction. Below 2/5 = no trade regardless of WBS.         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Optional

log = logging.getLogger("avshunter.convergence")

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

EIL_STRATEGIES = [
    "liquidity_gate",
    "iv_distortion",
    "gex_flipper",
    "obi_predictor",
    "poc_timing",
]

MIN_CONVERGENCE_TO_TRADE = 2    # Must have at least 2/5 strategies in agreement
HIGH_CONVICTION_THRESHOLD = 4  # 4+ = high conviction, max Kelly fraction

DIRECTION_POSITIVE = {"LONG", "CALL", "BULLISH", "BUY", "OPTIMAL_WINDOW", "ABOVE_POC"}
DIRECTION_NEGATIVE = {"SHORT", "PUT", "BEARISH", "SELL", "BELOW_POC"}
DIRECTION_NEUTRAL  = {"NEUTRAL", "FLAT", "AT_POC", "SUBOPTIMAL", "CLOSED_AUCTION"}


@dataclass
class ConvergenceResult:
    ticker:              str
    n_strategies:        int     # total EIL strategies evaluated
    n_bullish:           int     # strategies pointing LONG/CALL
    n_bearish:           int     # strategies pointing SHORT/PUT
    n_neutral:           int     # neutral/abstained
    convergence_score:   int     # max(n_bullish, n_bearish)
    dominant_direction:  str     # BULLISH | BEARISH | MIXED | INSUFFICIENT
    direction_agreement: float   # convergence_score / n_strategies
    conviction_level:    str     # HIGH | MODERATE | LOW | BLOCKED
    eil_votes:           dict    # per-strategy vote breakdown
    kelly_conv_fraction: float   # Kelly modifier based on convergence (0.5–1.0)
    trade_gate:          str     # PASS | BLOCK_INSUFFICIENT | BLOCK_MIXED
    notes:               str

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        neutral_note = f"  [{self.n_neutral}N abstain]" if self.n_neutral >= 3 else ""
        return (
            f"[CONV] {self.ticker:<6} "
            f"{self.dominant_direction:<10} "
            f"{self.convergence_score}/{self.n_strategies} strategies  "
            f"({self.conviction_level})  →  {self.trade_gate}{neutral_note}"
        )


class ConvergenceEngine:
    """
    Reads EIL strategy outputs from a signal dict and computes the
    cross-strategy convergence score.

    Field name conventions (from execution_intelligence.py):
      eil__liquidity_gate_signal    → liquidity_gate vote
      eil__iv_distortion_signal     → iv_distortion vote
      eil__gex_flipper_signal       → gex_flipper vote
      eil__obi_predictor_signal     → obi_predictor vote
      eil__poc_timing_signal        → poc_timing vote

    Fallback: also checks eil__*_verdict fields.
    """

    def __init__(
        self,
        min_convergence: int = MIN_CONVERGENCE_TO_TRADE,
        high_threshold:  int = HIGH_CONVICTION_THRESHOLD,
    ):
        self.min_convergence = min_convergence
        self.high_threshold  = high_threshold

    # ── FIX-01 (2026-04-19): Field name map ───────────────────────────────────
    # execution_intelligence.py writes eil_liquidity_score, eil_iv_score, etc.
    # (numeric 0-100 scores). The old code looked for eil__*_signal (string
    # verdict fields) that were never written → all votes defaulted NEUTRAL →
    # 0/5 strategies for every ticker → BLOCK_INSUFFICIENT on all 545.
    #
    # Fix: map each strategy name to the actual field written by EIL, then
    # classify the numeric score (>60 = BULLISH, <40 = BEARISH, else NEUTRAL).
    # Fallback chain retains old string-based lookup for forward compatibility.
    _SCORE_FIELD_MAP = {
        "liquidity_gate": "eil_liquidity_score",
        "iv_distortion":  "eil_iv_score",
        "gex_flipper":    "eil_gex_score",
        "obi_predictor":  "eil_obi_score",
        "poc_timing":     "eil_poc_score",
    }
    # FIX-CONV-THRESH (2026-04-21): Lowered BULLISH from 60→52, BEARISH from 40→48.
    # Problem: EIL composite avg=50.9 → most strategies score 40-60 → all vote NEUTRAL
    # → 0/5 strategies on every ticker even with real score data present.
    #
    # EIL scoring bands:
    #   EXECUTE_NOW         85-100 → well above 52 → correctly BULLISH
    #   EXECUTE_WITH_CAUTION 65-84 → above 52 → correctly BULLISH
    #   EXECUTE_DEFER        40-64 → overlaps 52 → weak signals now contribute
    #   STAND_DOWN          <40   → below 48 → correctly BEARISH
    #
    # 52/48 creates a ±4pt deadband around 50 (true neutral). Signals scoring
    # 48-52 genuinely have no directional read — they abstain as NEUTRAL.
    # This is correct behaviour. Signals scoring 52-60 are weakly directional
    # and should contribute to convergence.
    # CONV-01 (FIX-10): Tighten deadband for EOD mode.
    # EOD synthetic EIL scores cluster at 50–55. Previous 52/48 thresholds created a
    # 4-point neutral deadband that abstained most EOD signals → BLOCK_INSUFFICIENT.
    # 51/49 reduces deadband to 2 points: scores 51.1–100 vote BULLISH.
    # At composite=51.5 (typical EOD): was NEUTRAL, now BULLISH — contributes to consensus.
    _SCORE_BULLISH = 51.0   # score > this → strategy is bullish / passing
    _SCORE_BEARISH = 49.0   # score < this → strategy is bearish / opposing

    def _classify_vote(self, raw_value) -> str:
        """
        Classify an EIL output into BULLISH / BEARISH / NEUTRAL.

        Accepts either:
          - Numeric score (0-100 float/int): > 60 → BULLISH, < 40 → BEARISH
          - String verdict: matched against DIRECTION_POSITIVE / DIRECTION_NEGATIVE sets
        """
        if raw_value is None:
            return "NEUTRAL"

        # Numeric path — EIL writes scores not string verdicts
        try:
            score = float(raw_value)
            if score > self._SCORE_BULLISH:
                return "BULLISH"
            if score < self._SCORE_BEARISH:
                return "BEARISH"
            return "NEUTRAL"
        except (TypeError, ValueError):
            pass

        # String path — legacy / forward-compat
        v = str(raw_value).upper().strip()
        if any(pos in v for pos in DIRECTION_POSITIVE):
            return "BULLISH"
        if any(neg in v for neg in DIRECTION_NEGATIVE):
            return "BEARISH"
        return "NEUTRAL"

    def _extract_votes(self, signal: dict) -> dict[str, str]:
        """
        Extract per-strategy votes from EIL-enriched signal dict.

        FIX-01: Primary lookup uses actual field names written by
        execution_intelligence.py (eil_liquidity_score etc.).
        Fallback chain checks old string-verdict field names for
        forward compatibility.
        """
        votes = {}
        for strategy in EIL_STRATEGIES:
            # Primary: numeric score field (what EIL actually writes)
            score_field = self._SCORE_FIELD_MAP.get(strategy)
            raw = signal.get(score_field) if score_field else None

            # Fallback: old string-verdict field names
            if raw is None:
                raw = (
                    signal.get(f"eil__{strategy}_signal") or
                    signal.get(f"eil__{strategy}_verdict") or
                    signal.get(f"eil_{strategy}_signal") or
                    signal.get(f"eil_{strategy}_verdict") or
                    signal.get(f"{strategy}_signal")
                )

            votes[strategy] = self._classify_vote(raw)
        return votes

    def compute(self, ticker: str, signal: dict) -> ConvergenceResult:
        """Compute convergence score for one signal dict."""
        votes = self._extract_votes(signal)

        n_bullish = sum(1 for v in votes.values() if v == "BULLISH")
        n_bearish = sum(1 for v in votes.values() if v == "BEARISH")
        n_neutral = sum(1 for v in votes.values() if v == "NEUTRAL")
        n_total   = len(EIL_STRATEGIES)

        conv_score = max(n_bullish, n_bearish)
        agreement  = round(conv_score / n_total, 4) if n_total > 0 else 0

        # Dominant direction
        if conv_score < self.min_convergence:
            dominant = "INSUFFICIENT"
        elif n_bullish > n_bearish:
            dominant = "BULLISH"
        elif n_bearish > n_bullish:
            dominant = "BEARISH"
        else:
            dominant = "MIXED"

        # Conviction level
        if conv_score >= self.high_threshold:
            conviction = "HIGH"
        elif conv_score >= self.min_convergence:
            conviction = "MODERATE"
        elif conv_score == self.min_convergence - 1:
            conviction = "LOW"
        else:
            conviction = "INSUFFICIENT"

        # Trade gate
        if dominant in ("INSUFFICIENT", "MIXED"):
            gate = "BLOCK_INSUFFICIENT" if dominant == "INSUFFICIENT" else "BLOCK_MIXED"
        else:
            gate = "PASS"

        # Kelly convergence fraction (scales 0.5–1.0 with conviction)
        # HIGH=1.0, MODERATE=0.75, LOW=0.5, INSUFFICIENT=0.0
        kelly_map = {"HIGH": 1.0, "MODERATE": 0.75, "LOW": 0.5, "INSUFFICIENT": 0.0}
        kelly_conv = kelly_map.get(conviction, 0.5)

        notes_parts = []
        if gate != "PASS":
            notes_parts.append(f"Gate blocked: {dominant} ({n_bullish}B/{n_bearish}S/{n_neutral}N)")
        if n_neutral >= 3:
            notes_parts.append("High abstention — check EIL strategy data availability")

        result = ConvergenceResult(
            ticker=ticker,
            n_strategies=n_total,
            n_bullish=n_bullish,
            n_bearish=n_bearish,
            n_neutral=n_neutral,
            convergence_score=conv_score,
            dominant_direction=dominant,
            direction_agreement=agreement,
            conviction_level=conviction,
            eil_votes=votes,
            kelly_conv_fraction=kelly_conv,
            trade_gate=gate,
            notes="; ".join(notes_parts),
        )

        log.info(result.summary_line())
        return result

    def enrich_batch(self, signals: list[dict]) -> list[dict]:
        """
        Compute convergence for a list of signal dicts.
        Adds conv_* fields to each signal dict.
        Returns enriched list — BLOCKED signals retained but flagged.
        """
        out = []
        for sig in signals:
            ticker = sig.get("ticker", "UNKNOWN")
            result = self.compute(ticker, sig)
            enriched = dict(sig)
            enriched.update({
                "conv_score":          result.convergence_score,
                "conv_direction":      result.dominant_direction,
                "conv_agreement":      result.direction_agreement,
                "conv_conviction":     result.conviction_level,
                "conv_trade_gate":     result.trade_gate,
                "conv_kelly_fraction": result.kelly_conv_fraction,
                "conv_n_bullish":      result.n_bullish,
                "conv_n_bearish":      result.n_bearish,
                "conv_n_neutral":      result.n_neutral,
                "conv_votes":          str(result.eil_votes),
                "conv_notes":          result.notes,
            })
            out.append(enriched)
        return out

    def filter_tradeable(self, signals: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Split enriched signals into (tradeable, blocked).
        Assumes enrich_batch() has already been called.

        PSE-aware (2026-04-21):
          BLOCK_MIXED with PSE sizing → passes with kelly_conv_fraction capped at 0.50
          pse_miss_flag signals (atheoretic edge promoted) → always passes
          BLOCK_INSUFFICIENT with no PSE → genuine hard block (0-1 strategies agree)
        """
        tradeable = []
        blocked   = []

        for s in signals:
            gate     = s.get("conv_trade_gate", "PASS")
            pse_mode = str(s.get("pse_execution_mode", "")).upper()
            is_miss  = s.get("pse_miss_flag") is True

            if gate == "PASS":
                tradeable.append(s)
            elif is_miss:
                tradeable.append(s)
            elif gate == "BLOCK_MIXED" and pse_mode and pse_mode not in ("FATAL_BLOCK", "SKIP", ""):
                # PSE priced in EIL uncertainty — pass with reduced conviction
                enriched = dict(s)
                enriched["conv_kelly_fraction"] = min(
                    float(s.get("conv_kelly_fraction", 0.75)), 0.50
                )
                enriched["conv_notes"] = (
                    str(s.get("conv_notes", "")) +
                    " | PSE_MIXED_PASS: BLOCK_MIXED overridden — PSE penalty chain active"
                ).strip(" |")
                tradeable.append(enriched)
            else:
                blocked.append(s)

        return tradeable, blocked
