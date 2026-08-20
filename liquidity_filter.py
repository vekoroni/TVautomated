"""
AVSHUNTER — Options Think Tank: M3 Liquidity Filter
====================================================
Version : 1.0.0
Date    : 2026-04-27
Deploy  : C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\  (root)

PURPOSE
-------
Standalone liquidity evaluation module for options contracts.
Produces a continuous LiquidityResult score (0–1) and a verdict
(LIQUID / BORDERLINE / REJECT) from spread/mid, OI, and volume.

This is the OPTIONS THINK TANK layer — sits ABOVE the EIL S1
liquidity_gate.py which runs at execution time. This module runs
earlier in the pipeline at signal assembly time to filter contracts
before they reach EIL at all.

RELATIONSHIP TO EIL S1 LIQUIDITY GATE
--------------------------------------
EIL S1 (liquidity_gate.py v2.1):
  - Runs at execution time (Pass 2, per-row)
  - Has time-of-day awareness (OPTIMAL_WINDOW / CLOSED_AUCTION)
  - Has EV-aware exec_edge gate (when option-level move available)
  - Hard blocks: spread > 20% OR OI < 100

This module (M3):
  - Runs at signal assembly / pre-filter time
  - No time-of-day dependency
  - Produces a continuous score for the sizing chain
  - Hard rejects: spread > 20% OR OI < 100 (same thresholds — consistent)
  - Outputs liquidity_score (0–1) as a multiplier for M7 strategy_router

VERDICT MATRIX (aligned with EIL S1 v2.1)
------------------------------------------
  spread/mid ≤  5%  AND OI ≥ 500  → LIQUID      score ≥ 0.80
  spread/mid ≤ 10%  AND OI ≥ 100  → BORDERLINE  score 0.50–0.79
  spread/mid ≤ 20%  AND OI ≥ 100  → BORDERLINE  score 0.30–0.49
  spread/mid > 20%  OR  OI < 100  → REJECT       score 0.0  (hard reject)

SPREAD FORMULA
--------------
  spread_pct = (ask − bid) / mid × 100
  This is (ask−bid)/mid NOT (ask−bid)/ask — mid is the correct denominator.
  The pipeline stores contract_spread_pct as a decimal fraction (0.157 = 15.7%).

DATA SOURCES
------------
  contract_spread_pct : from avshunter_options_intelligence (decimal fraction)
  contract_oi         : open interest from Polygon
  contract_premium    : mark price (used if spread not available)
  contract_volume     : daily volume from Polygon
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── Thresholds — aligned with EIL S1 v2.1 ─────────────────────────────────────
SPREAD_HARD_REJECT  = 20.0    # spread/mid % — hard reject above this
SPREAD_LIQUID       =  5.0    # spread/mid % — clean / full liquidity
SPREAD_BORDERLINE   = 10.0    # spread/mid % — borderline (use limit order)
# 10–20%: wide borderline

OI_HARD_REJECT      = 100     # hard reject below this
OI_LIQUID           = 500     # adequate depth

# Scoring weights
W_SPREAD  = 0.60   # spread is primary — roundtrip cost is what destroys edge
W_OI      = 0.30   # OI governs exit liquidity
W_VOLUME  = 0.10   # daily volume confirms activity


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LiquidityResult:
    ticker:              str
    option_symbol:       Optional[str]
    spread_pct:          Optional[float]   # (ask−bid)/mid × 100
    roundtrip_cost_usd:  Optional[float]   # (ask−bid) × 100 per contract
    open_interest:       Optional[int]
    volume:              Optional[int]
    spread_score:        float             # 0–1
    oi_score:            float             # 0–1
    volume_score:        float             # 0–1
    liquidity_score:     float             # 0–1 composite
    verdict:             str               # LIQUID | BORDERLINE | REJECT
    hard_reject:         bool
    reject_reason:       Optional[str]
    size_multiplier:     float             # for M7 sizing chain


# ─────────────────────────────────────────────────────────────────────────────
# CORE FILTER
# ─────────────────────────────────────────────────────────────────────────────

class LiquidityFilter:
    """
    Stateless liquidity evaluation.
    Call evaluate() per contract or liquidity_from_row() for pipeline integration.
    """

    def evaluate(
        self,
        ticker:         str,
        spread_pct:     Optional[float],   # (ask−bid)/mid × 100
        open_interest:  Optional[int],
        volume:         Optional[int]      = None,
        mid_price:      Optional[float]    = None,   # for roundtrip cost calc
        option_symbol:  Optional[str]      = None,
    ) -> LiquidityResult:

        # ── Hard reject checks ────────────────────────────────────────────────
        if open_interest is not None and open_interest < OI_HARD_REJECT:
            return self._reject(ticker, option_symbol, spread_pct, open_interest, volume,
                                mid_price, f"OI={open_interest} < {OI_HARD_REJECT} minimum")

        if spread_pct is not None and spread_pct > SPREAD_HARD_REJECT:
            return self._reject(ticker, option_symbol, spread_pct, open_interest, volume,
                                mid_price, f"spread {spread_pct:.1f}% > {SPREAD_HARD_REJECT}% limit")

        # ── Spread score ──────────────────────────────────────────────────────
        if spread_pct is not None:
            if spread_pct <= SPREAD_LIQUID:
                spread_score = 1.0
            elif spread_pct <= SPREAD_BORDERLINE:
                # Linear decay: 5% → 1.0, 10% → 0.60
                spread_score = 1.0 - (spread_pct - SPREAD_LIQUID) / (SPREAD_BORDERLINE - SPREAD_LIQUID) * 0.40
            else:
                # 10–20%: borderline zone
                spread_score = 0.60 - (spread_pct - SPREAD_BORDERLINE) / (SPREAD_HARD_REJECT - SPREAD_BORDERLINE) * 0.40
            spread_score = round(max(0.0, min(1.0, spread_score)), 3)
        else:
            spread_score = 0.70   # unknown — conservative default

        # ── OI score ──────────────────────────────────────────────────────────
        if open_interest is not None:
            oi_score = round(min(1.0, open_interest / OI_LIQUID), 3)
        else:
            oi_score = 0.50   # unknown

        # ── Volume score ──────────────────────────────────────────────────────
        if volume is not None and volume > 0:
            volume_score = round(min(1.0, volume / 200.0), 3)
        else:
            volume_score = 0.30   # unknown / zero

        # ── Composite ─────────────────────────────────────────────────────────
        liquidity_score = round(
            W_SPREAD * spread_score + W_OI * oi_score + W_VOLUME * volume_score, 3
        )

        # ── Verdict ───────────────────────────────────────────────────────────
        if liquidity_score >= 0.80 and (spread_pct or 100) <= SPREAD_LIQUID:
            verdict = "LIQUID"
        elif liquidity_score >= 0.40:
            verdict = "BORDERLINE"
        else:
            verdict = "BORDERLINE"   # low score but not hard-rejected

        # Size multiplier: LIQUID=1.0, BORDERLINE scales with score
        size_mult = round(min(1.0, liquidity_score / 0.80), 3) if liquidity_score < 0.80 else 1.0

        # Roundtrip cost
        roundtrip = None
        if spread_pct is not None and mid_price is not None and mid_price > 0:
            spread_usd = mid_price * (spread_pct / 100.0)
            roundtrip  = round(spread_usd * 100, 2)   # per contract (100 shares)

        return LiquidityResult(
            ticker             = ticker,
            option_symbol      = option_symbol,
            spread_pct         = round(spread_pct, 2) if spread_pct is not None else None,
            roundtrip_cost_usd = roundtrip,
            open_interest      = open_interest,
            volume             = volume,
            spread_score       = spread_score,
            oi_score           = oi_score,
            volume_score       = volume_score,
            liquidity_score    = liquidity_score,
            verdict            = verdict,
            hard_reject        = False,
            reject_reason      = None,
            size_multiplier    = size_mult,
        )

    def _reject(self, ticker, symbol, spread_pct, oi, vol, mid, reason) -> LiquidityResult:
        roundtrip = None
        if spread_pct is not None and mid is not None and mid > 0:
            roundtrip = round(mid * (spread_pct / 100.0) * 100, 2)
        return LiquidityResult(
            ticker             = ticker,
            option_symbol      = symbol,
            spread_pct         = round(spread_pct, 2) if spread_pct is not None else None,
            roundtrip_cost_usd = roundtrip,
            open_interest      = oi,
            volume             = vol,
            spread_score       = 0.0,
            oi_score           = 0.0,
            volume_score       = 0.0,
            liquidity_score    = 0.0,
            verdict            = "REJECT",
            hard_reject        = True,
            reject_reason      = reason,
            size_multiplier    = 0.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

_filter = LiquidityFilter()


def liquidity_from_row(row: dict) -> Optional[LiquidityResult]:
    """
    Evaluate liquidity from a superbrain / eil_enriched row dict.

    contract_spread_pct is stored as a decimal fraction (0.157 = 15.7%).
    This function converts it to percentage for the filter.

    Writes result fields back to row with 'liq_' prefix as side effect.
    Returns None if no options data present.
    """
    def _f(key: str, default: float = 0.0) -> float:
        try:
            v = row.get(key, default)
            if v is None: return default
            f = float(v)
            return default if f != f else f
        except (TypeError, ValueError):
            return default

    def _i(key: str) -> Optional[int]:
        try:
            v = row.get(key)
            return int(float(v)) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _fnn(key: str) -> Optional[float]:
        v = _f(key, 0.0)
        return v if v and v > 0 else None

    ticker = str(row.get("ticker", "UNKNOWN")).strip().upper()

    # Spread — contract_spread_pct is decimal fraction in pipeline
    spread_dec = _fnn("contract_spread_pct")
    spread_pct = spread_dec * 100.0 if spread_dec else None

    oi        = _i("contract_oi") or _i("open_interest")
    vol       = _i("contract_volume") or _i("volume")
    mid       = _fnn("contract_premium") or _fnn("premium")
    symbol    = str(row.get("contract_occ_symbol") or row.get("recommended_contract") or "")

    if spread_pct is None and oi is None:
        return None   # no options data — skip

    result = _filter.evaluate(
        ticker        = ticker,
        spread_pct    = spread_pct,
        open_interest = oi,
        volume        = vol,
        mid_price     = mid,
        option_symbol = symbol or None,
    )

    # Write back to row
    row["liq_spread_pct"]         = result.spread_pct
    row["liq_roundtrip_usd"]      = result.roundtrip_cost_usd
    row["liq_oi"]                 = result.open_interest
    row["liq_score"]              = result.liquidity_score
    row["liq_verdict"]            = result.verdict
    row["liq_hard_reject"]        = result.hard_reject
    row["liq_reject_reason"]      = result.reject_reason
    row["liq_size_multiplier"]    = result.size_multiplier

    return result


def liquidity_columns() -> list[str]:
    """Return column names written to row by liquidity_from_row()."""
    return [
        "liq_spread_pct", "liq_roundtrip_usd", "liq_oi",
        "liq_score", "liq_verdict", "liq_hard_reject",
        "liq_reject_reason", "liq_size_multiplier",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  M3 Liquidity Filter v1.0.0 — Smoke Test")
    print("=" * 60 + "\n")

    f = LiquidityFilter()

    cases = [
        # (ticker, spread_pct, oi, vol, mid, expected_verdict)
        ("SPY",  2.5, 5000, 800,  2.00, "LIQUID"),
        ("DIA",  15.8, 313, 50,   8.25, "BORDERLINE"),
        ("XLP",  25.0,  80, 10,   1.20, "REJECT"),     # both: spread >20% AND OI <100
        ("ABT",  18.0, 220, 30,   2.10, "BORDERLINE"),
        ("WCN",  10.0, 600, 120,  5.50, "BORDERLINE"),
        ("NVDA",  4.0, 2000, 500,  5.00, "LIQUID"),
    ]

    all_pass = True
    for ticker, sp, oi, vol, mid, expected in cases:
        r = f.evaluate(ticker, sp, oi, vol, mid)
        status = "PASS" if r.verdict == expected else "FAIL"
        if status == "FAIL": all_pass = False
        rt = f"${r.roundtrip_cost_usd:.2f}" if r.roundtrip_cost_usd else "N/A"
        print(f"  {status}  {ticker:<6} spread={sp:>5.1f}%  OI={oi:>4}  "
              f"score={r.liquidity_score:.3f}  mult={r.size_multiplier:.2f}  "
              f"RT={rt:>7}  → {r.verdict}")

    print()

    # Row integration test
    test_row = {
        "ticker":              "DIA",
        "contract_spread_pct": 0.1576,   # decimal fraction
        "contract_oi":         313,
        "contract_premium":    8.25,
        "contract_volume":     50,
    }
    result = liquidity_from_row(test_row)
    assert result is not None
    assert "liq_score" in test_row
    assert test_row["liq_verdict"] in ("LIQUID", "BORDERLINE", "REJECT")
    print(f"  Row integration: PASS  "
          f"spread={test_row['liq_spread_pct']:.1f}%  "
          f"score={test_row['liq_score']:.3f}  "
          f"verdict={test_row['liq_verdict']}")

    print()
    print(f"  All tests {'PASSED' if all_pass else 'FAILED'}")
    print()
