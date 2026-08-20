"""
AVSHUNTER — Options Think Tank: M1 IV Engine
=============================================
Version : 1.0.0
Date    : 2026-04-27
Deploy  : C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\  (root)

PURPOSE
-------
Computes three core IV metrics per ticker from pipeline row data:
  1. IV snapshot     — current IV, RV_20d, VRP (IV − RV)
  2. Expected Move   — ±$ and ±% move for the contract DTE
  3. VRP Signal      — SELL_EDGE / BUY_EDGE / NEUTRAL

These feed:
  - M7 strategy_router.py  (primary strategy bias input)
  - EIL iv_distortion.py   (already receives contract_iv — this enriches it)
  - Intelligence Lab        (display: iv_engine_vrp, iv_engine_expected_move)

DATA SOURCES (all already flowing in pipeline)
-----------------------------------------------
  contract_iv       : from avshunter_options_intelligence.py (MarketData.app/Polygon)
  hv_30d            : 20/30-day historical vol, computed in options_intelligence
  underlying_price  : Polygon snapshot
  contract_dte      : from options_intelligence contract selection
  atm_iv            : ATM IV from options_intelligence iv_context

VRP SIGNAL LOGIC
----------------
  VRP = IV − RV_20d
  VRP > +5  → SELL_EDGE  (IV rich vs realised — sell premium favoured)
  VRP < -3  → BUY_EDGE   (RV rich vs IV — buy options, cheap vol)
  else      → NEUTRAL

EXPECTED MOVE (1-SD for contract DTE)
--------------------------------------
  EM_$ = Stock_Price × IV × √(DTE / 365)
  EM_% = EM_$ / Stock_Price × 100

INTEGRATION
-----------
Call iv_engine_from_row(row) to produce IVEngineResult from a superbrain row.
Output fields are written back to the row with 'iv_engine_' prefix.
No external API calls — consumes only fields already in the pipeline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ── VRP thresholds ─────────────────────────────────────────────────────────────
VRP_SELL_THRESHOLD =  5.0   # IV > RV by 5+ vol pts → premium selling edge
VRP_BUY_THRESHOLD  = -3.0   # RV > IV by 3+ vol pts → cheap vol, buy edge


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IVEngineResult:
    ticker:              str
    iv_current:          float          # ATM IV, annualised decimal (e.g. 0.25 = 25%)
    iv_current_pct:      float          # iv_current × 100 for display
    rv_20d:              float          # 20-day realised vol, annualised decimal
    rv_20d_pct:          float          # rv_20d × 100 for display
    vrp:                 float          # IV − RV in vol pts (e.g. 5.2)
    vrp_signal:          str            # SELL_EDGE | BUY_EDGE | NEUTRAL
    expected_move_usd:   float          # ±$ 1-SD move for contract DTE
    expected_move_pct:   float          # ±% 1-SD move for contract DTE
    dte:                 int
    stock_price:         float
    data_quality:        str            # FULL | PARTIAL | SYNTHETIC
    notes:               str = ""


# ─────────────────────────────────────────────────────────────────────────────
# CORE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class IVEngine:
    """
    Stateless IV analytics engine.
    All methods are pure functions — no API calls, no side effects.
    """

    def expected_move(self, stock_price: float, iv: float, dte: int) -> tuple[float, float]:
        """
        Compute 1-SD expected move for given DTE.

        Args:
            stock_price : underlying last price
            iv          : implied volatility as decimal (0.25 = 25%)
            dte         : days to expiry

        Returns:
            (expected_move_usd, expected_move_pct)
        """
        if stock_price <= 0 or iv <= 0 or dte <= 0:
            return 0.0, 0.0
        em_usd = stock_price * iv * math.sqrt(dte / 365.0)
        em_pct = em_usd / stock_price * 100.0
        return round(em_usd, 2), round(em_pct, 2)

    def vrp_signal(self, vrp: float) -> str:
        """
        Classify VRP into strategy bias signal.

        VRP = IV − RV. Positive = IV expensive vs realised history.
        Negative = IV cheap vs realised history.
        """
        if vrp >= VRP_SELL_THRESHOLD:
            return "SELL_EDGE"
        if vrp <= VRP_BUY_THRESHOLD:
            return "BUY_EDGE"
        return "NEUTRAL"

    def snapshot(
        self,
        ticker:      str,
        iv:          float,           # annualised decimal
        hv_30d:      Optional[float], # annualised decimal from pipeline
        stock_price: float,
        dte:         int,
    ) -> IVEngineResult:
        """
        Compute full IV snapshot from pipeline fields.

        iv     : contract_iv or atm_iv (annualised decimal, e.g. 0.25)
        hv_30d : historical vol from options_intelligence (annualised decimal)
        """
        notes = []
        data_quality = "FULL"

        # RV: use hv_30d from pipeline — already annualised decimal
        if hv_30d and hv_30d > 0:
            rv = hv_30d
        else:
            # Synthetic: approximate from IV with typical VRP assumption
            rv = iv * 0.85   # IV tends to overstate RV by ~15% on average
            notes.append("RV synthetic (hv_30d absent — using IV×0.85)")
            data_quality = "SYNTHETIC"

        vrp = round((iv - rv) * 100, 2)   # convert to vol pts for display
        signal = self.vrp_signal(vrp)
        em_usd, em_pct = self.expected_move(stock_price, iv, dte)

        return IVEngineResult(
            ticker            = ticker,
            iv_current        = round(iv, 6),
            iv_current_pct    = round(iv * 100, 2),
            rv_20d            = round(rv, 6),
            rv_20d_pct        = round(rv * 100, 2),
            vrp               = vrp,
            vrp_signal        = signal,
            expected_move_usd = em_usd,
            expected_move_pct = em_pct,
            dte               = dte,
            stock_price       = stock_price,
            data_quality      = data_quality,
            notes             = " | ".join(notes),
        )


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION — row-level entry point
# ─────────────────────────────────────────────────────────────────────────────

_engine = IVEngine()


def iv_engine_from_row(row: dict) -> Optional[IVEngineResult]:
    """
    Produce IVEngineResult from a superbrain / eil_enriched row dict.

    Field resolution order (matches pipeline column names):
      IV:    atm_iv → contract_iv → implied_vol
      RV:    hv_30d
      Price: underlying_price → signal_price → current_price
      DTE:   contract_dte → dte

    Returns None if essential data (IV + price) is missing.
    Writes result fields back to row with 'iv_engine_' prefix as side effect.
    """
    def _f(key: str, default: float = 0.0) -> float:
        try:
            v = row.get(key, default)
            if v is None: return default
            f = float(v)
            return default if f != f else f   # NaN guard
        except (TypeError, ValueError):
            return default

    def _fnn(key: str) -> Optional[float]:
        v = _f(key, 0.0)
        return v if v and v > 0 else None

    ticker      = str(row.get("ticker", "UNKNOWN")).strip().upper()
    stock_price = _fnn("underlying_price") or _fnn("signal_price") or _fnn("current_price") or 0.0
    dte_raw     = _fnn("contract_dte") or _fnn("dte") or 0.0
    dte         = int(dte_raw)

    # IV — prefer ATM IV over contract IV (ATM is less strike-specific)
    iv_raw = _fnn("atm_iv") or _fnn("contract_iv") or _fnn("implied_vol")

    if not iv_raw or not stock_price:
        return None

    # Normalise: pipeline stores IV as decimal (0.25) not percentage (25)
    # Guard against accidentally receiving percentage form
    iv = iv_raw if iv_raw < 5.0 else iv_raw / 100.0

    hv_raw = _fnn("hv_30d")
    hv = (hv_raw if hv_raw < 5.0 else hv_raw / 100.0) if hv_raw else None

    if dte <= 0:
        dte = 30   # default DTE when contract_dte absent

    result = _engine.snapshot(
        ticker      = ticker,
        iv          = iv,
        hv_30d      = hv,
        stock_price = stock_price,
        dte         = dte,
    )

    # Write back to row with iv_engine_ prefix
    row["iv_engine_iv_pct"]          = result.iv_current_pct
    row["iv_engine_rv_pct"]          = result.rv_20d_pct
    row["iv_engine_vrp"]             = result.vrp
    row["iv_engine_vrp_signal"]      = result.vrp_signal
    row["iv_engine_expected_move_$"] = result.expected_move_usd
    row["iv_engine_expected_move_%"] = result.expected_move_pct
    row["iv_engine_data_quality"]    = result.data_quality

    return result


def iv_engine_columns() -> list[str]:
    """Return the list of column names written to row by iv_engine_from_row()."""
    return [
        "iv_engine_iv_pct",
        "iv_engine_rv_pct",
        "iv_engine_vrp",
        "iv_engine_vrp_signal",
        "iv_engine_expected_move_$",
        "iv_engine_expected_move_%",
        "iv_engine_data_quality",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  M1 IV Engine v1.0.0 — Smoke Test")
    print("=" * 60 + "\n")

    test_cases = [
        # (ticker, iv_pct, hv_pct, price, dte, expected_signal)
        ("DIA",  16.5,  12.0, 494.22, 30, "NEUTRAL"),     # VRP = +4.5 → NEUTRAL (below +5.0 threshold)
        ("XLP",  22.0,  10.0,  79.50, 45, "SELL_EDGE"),   # VRP = +12 → SELL_EDGE
        ("ABT",  18.0,  22.0,  91.20, 30, "BUY_EDGE"),    # VRP = -4  → BUY_EDGE
        ("SPY",  12.0,  11.5, 520.00, 7,  "NEUTRAL"),     # VRP = +0.5 → NEUTRAL
    ]

    engine = IVEngine()
    all_pass = True

    for ticker, iv_pct, hv_pct, price, dte, expected in test_cases:
        r = engine.snapshot(
            ticker      = ticker,
            iv          = iv_pct / 100,
            hv_30d      = hv_pct / 100,
            stock_price = price,
            dte         = dte,
        )
        status = "PASS" if r.vrp_signal == expected else "FAIL"
        if status == "FAIL": all_pass = False
        print(f"  {status}  {ticker:<6} IV={r.iv_current_pct:.1f}%  "
              f"RV={r.rv_20d_pct:.1f}%  VRP={r.vrp:+.1f}  "
              f"Signal={r.vrp_signal:<10}  "
              f"EM=±${r.expected_move_usd:.2f} (±{r.expected_move_pct:.1f}%)")

    print()

    # Row integration test
    test_row = {
        "ticker":           "DIA",
        "atm_iv":           0.165,
        "hv_30d":           0.12,
        "underlying_price": 494.22,
        "contract_dte":     30,
    }
    result = iv_engine_from_row(test_row)
    assert result is not None, "iv_engine_from_row returned None"
    assert "iv_engine_vrp" in test_row, "vrp not written back to row"
    assert test_row["iv_engine_vrp_signal"] in ("SELL_EDGE", "BUY_EDGE", "NEUTRAL")
    print(f"  Row integration: PASS  vrp={test_row['iv_engine_vrp']:+.1f}  "
          f"signal={test_row['iv_engine_vrp_signal']}")

    print()
    print(f"  All tests {'PASSED' if all_pass else 'FAILED'}")
    print()
