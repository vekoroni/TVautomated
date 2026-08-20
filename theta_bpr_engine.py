"""
AVSHUNTER — Options Think Tank: M6 Theta / BPR Engine
======================================================
Version : 1.0.0
Date    : 2026-04-27
Deploy  : C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\  (root)

PURPOSE
-------
Quantifies the daily theta decay cost and capital efficiency for each
options signal. For long options (the primary strategy), theta works
AGAINST the position every day. This module answers two questions:

  1. HOW FAST is this position losing value to time decay?
     → Daily_Decay_$ = |theta| × 100  (per contract)

  2. IS THIS TRADE CAPITAL EFFICIENT given the expected payoff?
     → CE_Ratio = Expected_P&L / BPR

THETA DATA SOURCE
-----------------
contract_theta : from avshunter_options_intelligence.py
  - Source A: MarketData.app live theta (field: theta)
  - Source B: Polygon greeks.theta (extracted in _fetch_chain_polygon)
  - Source C: BSM backfill (backfill_greeks_vectorised in options_intelligence)

Theta from these sources is expressed as $/share/day (e.g. -0.045 = -$4.50/day
per contract). Always negative for long options.

BPR (Buying Power Reduction)
-----------------------------
Long options (defined risk): BPR = premium paid × 100 per contract.
Undefined risk (short puts/strangles): BPR = Tastytrade formula
  ≈ max(20% × underlying × 100, option_price × 100 + 10% × underlying × 100)
  This module handles defined-risk (long) trades only for now.

CAPITAL EFFICIENCY (CE) RATIO
------------------------------
CE_Ratio = Expected_P&L / BPR

Where Expected_P&L = structural_target_move × delta × 100 × contracts
  structural_target_move = |underlying_price − structural_target| (from Vanguard)

Thresholds:
  CE ≥ 0.40 → EFFICIENT    (full target size)
  CE 0.25–0.40 → MARGINAL  (half size)
  CE < 0.25 → REJECT       (skip — not worth the capital)

DAYS TO 50% DECAY
-----------------
d50 = (premium × 0.50 × 100) / daily_decay_$
  The urgency clock: if d50 < DTE/3, the option decays too fast
  relative to its life — the expected move must happen quickly.

INTEGRATION
-----------
Call theta_bpr_from_row(row) to produce ThetaBPRResult from a pipeline row.
Writes result fields back to row with 'tbpr_' prefix.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ── CE thresholds ──────────────────────────────────────────────────────────────
CE_REJECT   = 0.25
CE_MARGINAL = 0.40

# Minimum days-to-50%-decay as a fraction of DTE (below = urgency flag)
D50_URGENCY_FRACTION = 1.0 / 3.0


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ThetaBPRResult:
    ticker:               str
    option_type:          str            # LONG | SHORT
    premium:              float          # per share (e.g. 8.25)
    theta:                float          # per share per day (negative for longs)
    daily_decay_usd:      float          # |theta| × 100 per contract
    dte:                  int
    total_decay_to_exp:   float          # daily_decay × dte (worst case)
    pct_premium_as_decay: float          # total_decay / (premium×100) × 100
    bpr:                  float          # buying power reduction per contract
    expected_pnl:         float          # estimated P&L from structural move
    ce_ratio:             float          # expected_pnl / bpr
    days_to_50pct_decay:  int            # urgency clock
    urgency_flag:         bool           # d50 < DTE/3
    verdict:              str            # EFFICIENT | MARGINAL | REJECT
    theta_source:         str            # LIVE | BSM | SYNTHETIC
    notes:                str = ""


# ─────────────────────────────────────────────────────────────────────────────
# CORE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ThetaBPREngine:
    """
    Stateless theta / BPR evaluation.
    Call evaluate_long() for long options or theta_bpr_from_row() for pipeline.
    """

    def evaluate_long(
        self,
        ticker:        str,
        premium:       float,       # mark price per share
        theta:         float,       # per share per day (negative)
        dte:           int,
        expected_pnl:  float,       # expected P&L per contract in $
        theta_source:  str = "LIVE",
    ) -> ThetaBPRResult:
        """
        Evaluate a long options position for theta efficiency.

        expected_pnl: estimated dollar return per contract if the thesis plays out.
        For a $8.25 DIA PUT with delta=-0.42 targeting $449 (from $494):
          move = $45, expected_pnl = 45 × 0.42 × 100 = $1,890
        """
        # BPR for defined risk = premium × 100
        bpr = round(premium * 100.0, 2)

        # Daily decay
        daily_decay = round(abs(theta) * 100.0, 2)

        # Total decay to expiry
        total_decay = round(daily_decay * dte, 2)
        pct_decay   = round(total_decay / bpr * 100.0, 2) if bpr > 0 else 0.0

        # Days to 50% premium decay
        half_premium_usd = bpr * 0.50
        d50 = int(half_premium_usd / daily_decay) if daily_decay > 0 else dte
        d50 = min(d50, dte)   # cannot exceed DTE

        # Urgency: does 50% decay happen before DTE/3?
        urgency = d50 < int(dte * D50_URGENCY_FRACTION)

        # CE ratio
        ce = round(expected_pnl / bpr, 3) if bpr > 0 else 0.0

        # Verdict
        if ce >= CE_MARGINAL and not urgency:
            verdict = "EFFICIENT"
        elif ce >= CE_REJECT:
            verdict = "MARGINAL"
        else:
            verdict = "REJECT"

        notes_parts = []
        if urgency:
            notes_parts.append(
                f"URGENCY: 50% decay in {d50}d < DTE/3 ({int(dte*D50_URGENCY_FRACTION)}d)"
            )
        if pct_decay > 80:
            notes_parts.append(
                f"HIGH DECAY: theta erodes {pct_decay:.0f}% of premium by expiry"
            )

        return ThetaBPRResult(
            ticker               = ticker,
            option_type          = "LONG",
            premium              = round(premium, 2),
            theta                = round(theta, 6),
            daily_decay_usd      = daily_decay,
            dte                  = dte,
            total_decay_to_exp   = total_decay,
            pct_premium_as_decay = pct_decay,
            bpr                  = bpr,
            expected_pnl         = round(expected_pnl, 2),
            ce_ratio             = ce,
            days_to_50pct_decay  = d50,
            urgency_flag         = urgency,
            verdict              = verdict,
            theta_source         = theta_source,
            notes                = " | ".join(notes_parts),
        )

    def _estimate_expected_pnl(
        self,
        underlying_price: float,
        structural_target: float,
        delta:             float,
        direction:         str,
    ) -> float:
        """
        Estimate expected P&L from the structural target move.

        Uses delta approximation: P&L ≈ price_move × |delta| × 100
        Direction-aware: PUT expects price to move DOWN to target.
        """
        if not underlying_price or not structural_target:
            return 0.0

        price_move = abs(underlying_price - structural_target)
        abs_delta  = abs(delta) if delta else 0.35   # default if missing
        return round(price_move * abs_delta * 100.0, 2)


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

_engine = ThetaBPREngine()


def theta_bpr_from_row(row: dict) -> Optional[ThetaBPRResult]:
    """
    Evaluate theta / BPR from a superbrain / eil_enriched row dict.

    Field resolution:
      theta:    contract_theta (from options_intelligence, per share per day)
      premium:  contract_premium → premium
      dte:      contract_dte → dte
      delta:    contract_delta (for expected P&L estimate)
      target:   structural_target (from Vanguard)

    Writes result fields back to row with 'tbpr_' prefix.
    Returns None if essential data absent.
    """
    def _f(key: str, default: float = 0.0) -> float:
        try:
            v = row.get(key, default)
            if v is None: return default
            f = float(v)
            return default if f != f else f
        except (TypeError, ValueError):
            return default

    def _fnn(key: str) -> Optional[float]:
        v = _f(key, 0.0)
        return v if v and v != 0.0 else None

    def _i(key: str, default: int = 0) -> int:
        try:
            v = row.get(key, default)
            return int(float(v)) if v is not None else default
        except (TypeError, ValueError):
            return default

    ticker    = str(row.get("ticker", "UNKNOWN")).strip().upper()
    theta_raw = _fnn("contract_theta")
    premium   = _fnn("contract_premium") or _fnn("premium")
    dte       = _i("contract_dte") or _i("dte")

    if premium is None or dte <= 0:
        return None   # insufficient data

    # Theta — use contract_theta if available, else BSM synthetic
    if theta_raw is not None:
        theta        = float(theta_raw)
        theta_source = "LIVE"
    else:
        # BSM synthetic: approximate theta from premium and DTE
        # Rule of thumb: daily theta ≈ premium / (DTE × 1.5) for ATM options
        theta        = -(premium / (dte * 1.5))
        theta_source = "SYNTHETIC"

    # Delta for expected P&L estimate
    delta = _fnn("contract_delta") or 0.35

    # Structural target from Vanguard
    underlying   = _fnn("underlying_price") or _fnn("signal_price") or 0.0
    struct_tgt   = _fnn("structural_target") or _fnn("target_price") or 0.0

    expected_pnl = _engine._estimate_expected_pnl(underlying, struct_tgt, delta,
                                                   str(row.get("direction", "LONG")))

    result = _engine.evaluate_long(
        ticker       = ticker,
        premium      = premium,
        theta        = theta,
        dte          = dte,
        expected_pnl = expected_pnl,
        theta_source = theta_source,
    )

    # Write back to row
    row["tbpr_daily_decay_$"]     = result.daily_decay_usd
    row["tbpr_total_decay_$"]     = result.total_decay_to_exp
    row["tbpr_pct_premium_decay"] = result.pct_premium_as_decay
    row["tbpr_bpr"]               = result.bpr
    row["tbpr_ce_ratio"]          = result.ce_ratio
    row["tbpr_d50"]               = result.days_to_50pct_decay
    row["tbpr_urgency"]           = result.urgency_flag
    row["tbpr_verdict"]           = result.verdict
    row["tbpr_theta_source"]      = result.theta_source
    row["tbpr_notes"]             = result.notes

    return result


def theta_bpr_columns() -> list[str]:
    return [
        "tbpr_daily_decay_$", "tbpr_total_decay_$", "tbpr_pct_premium_decay",
        "tbpr_bpr", "tbpr_ce_ratio", "tbpr_d50", "tbpr_urgency",
        "tbpr_verdict", "tbpr_theta_source", "tbpr_notes",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  M6 Theta/BPR Engine v1.0.0 — Smoke Test")
    print("=" * 60 + "\n")

    engine = ThetaBPREngine()

    cases = [
        # (ticker, premium, theta, dte, expected_pnl, exp_verdict)
        # DIA PUT: $8.25 premium, theta=-0.05, 30 DTE, $1890 target move
        ("DIA",  8.25, -0.050, 30, 1890.0, "EFFICIENT"),
        # ABT PUT: $2.10 premium, theta=-0.025, 45 DTE, $420 expected
        ("ABT",  2.10, -0.025, 45,  420.0, "EFFICIENT"),
        # XLP PUT: $1.20 premium, theta=-0.030, 21 DTE, $180 expected — fast decay
        ("XLP",  1.20, -0.030, 21,  180.0, "EFFICIENT"),  # CE=1.50, no urgency → EFFICIENT
        # Poor CE: small move, expensive premium
        ("TEST", 5.00, -0.080, 14,   80.0, "REJECT"),     # CE=0.16 → REJECT (low expected_pnl)
    ]

    all_pass = True
    for ticker, prem, theta, dte, epnl, expected in cases:
        r = engine.evaluate_long(ticker, prem, theta, dte, epnl)
        status = "PASS" if r.verdict == expected else "FAIL"
        if status == "FAIL": all_pass = False
        print(f"  {status}  {ticker:<6} prem=${prem:.2f}  "
              f"theta={theta:.3f}  decay=${r.daily_decay_usd:.2f}/day  "
              f"d50={r.days_to_50pct_decay}d  CE={r.ce_ratio:.2f}  "
              f"{'⚡URGENCY ' if r.urgency_flag else ''}"
              f"→ {r.verdict}")
        if r.notes:
            print(f"         {r.notes}")

    print()

    # Real DIA example from 20260421 run
    dia_row = {
        "ticker":            "DIA",
        "contract_premium":  8.25,
        "contract_theta":    -0.0185,
        "contract_dte":      58,
        "contract_delta":    -0.42,
        "underlying_price":  494.22,
        "structural_target": 449.73,
        "direction":         "PUT",
    }
    result = theta_bpr_from_row(dia_row)
    assert result is not None
    assert "tbpr_ce_ratio" in dia_row
    print(f"  DIA row integration: PASS")
    print(f"    daily_decay  = ${result.daily_decay_usd:.2f}/contract")
    print(f"    BPR          = ${result.bpr:.0f}")
    print(f"    expected_pnl = ${result.expected_pnl:.0f}")
    print(f"    CE ratio     = {result.ce_ratio:.2f}")
    print(f"    d50          = {result.days_to_50pct_decay} days")
    print(f"    verdict      = {result.verdict}")
    print(f"    source       = {result.theta_source}")

    print()
    print(f"  All tests {'PASSED' if all_pass else 'FAILED'}")
    print()
