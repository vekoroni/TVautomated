"""
AVSHUNTER — Options Think Tank: M4 VIX Governor
================================================
Version : 1.0.1
Date    : 2026-04-27
Deploy  : C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\  (root)

PURPOSE
-------
Portfolio-level capital allocation cap and strategy bias based on VIX regime.

Two distinct roles:
  1. CAPITAL ALLOCATION CAP — maximum % of portfolio to deploy at each VIX tier
  2. STRATEGY PREFERENCE    — whether to favour selling or buying premium

VIX TIER TABLE
--------------
  VIX > 40   : EXTREME     50% max   SELL_PREMIUM   long_option_mult=0.60
  VIX 30-40  : ELEVATED    40% max   SELL_PREMIUM   long_option_mult=0.75
  VIX 20-30  : TRANSITION  35% max   MIXED          long_option_mult=0.90
  VIX 15-20  : NORMAL      30% max   MIXED          long_option_mult=1.00
  VIX 10-15  : COMPLACENT  25% max   BUY_PREMIUM    long_option_mult=1.15

KEY NUANCE (critical for long options strategy)
-----------------------------------------------
High VIX = opportunity BUT you pay inflated premium for long calls/puts.
  long_option_mult < 1.0 in high VIX: signal that you're buying expensive vol.
  long_option_mult > 1.0 in low VIX:  signal that vol is cheap — buy it.

The M7 strategy_router uses long_option_mult to score LONG_CALL/LONG_PUT
signals higher in complacent regimes and lower in extreme regimes.

VIX DATA SOURCE
---------------
Primary:   macro_intelligence_latest.json → extras.extras.extras.volatility.vix_spot
           (actual VIX spot price — confirmed path from live macro JSON)
Secondary: vix_regime_score reverse-map (fallback, ±2pt approximation)
Fallback:  FRED API — series VIXCLS
           GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS
           No API key required. Returns CSV with last VIX close.

The governor also reads volatility_mode from the macro JSON if available
to cross-check the tier classification.

INTEGRATION
-----------
Call vix_governor_from_env() to get VIXGovernorResult using the best
available data source. Apply apply_to_portfolio() to get per-run
capital budget.

No dependency on other M-modules — can run standalone.
"""
from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("M4_VIX_GOVERNOR")


# ── VIX tier table ─────────────────────────────────────────────────────────────
# (floor, label, max_allocation, strategy_pref, long_option_mult, max_positions)
VIX_TIERS = [
    (40.0, "EXTREME",    0.50, "SELL_PREMIUM", 0.60, 6),
    (30.0, "ELEVATED",   0.40, "SELL_PREMIUM", 0.75, 8),
    (20.0, "TRANSITION", 0.35, "MIXED",        0.90, 10),
    (15.0, "NORMAL",     0.30, "MIXED",        1.00, 12),
    ( 0.0, "COMPLACENT", 0.25, "BUY_PREMIUM",  1.15, 12),
]


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VIXGovernorResult:
    vix_level:          float
    regime:             str            # EXTREME | ELEVATED | TRANSITION | NORMAL | COMPLACENT
    max_allocation:     float          # 0.0–1.0 decimal (0.50 = 50% of capital)
    strategy_pref:      str            # SELL_PREMIUM | MIXED | BUY_PREMIUM
    long_option_mult:   float          # multiplier for LONG_CALL/LONG_PUT sizing
    max_positions:      int            # position count cap
    data_source:        str            # FRED | MACRO_JSON | SYNTHETIC
    capital_available:  float = 0.0   # populated by apply_to_portfolio()
    positions_remaining:int   = 0     # populated by apply_to_portfolio()


@dataclass
class PortfolioBudget:
    capital_available:   float    # $ or fraction of total capital
    positions_remaining: int
    strategy_pref:       str
    long_option_mult:    float
    regime:              str
    vix_level:           float


# ─────────────────────────────────────────────────────────────────────────────
# VIX DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_vix_fred() -> Optional[float]:
    """
    Fetch latest VIX close from FRED (no API key required).
    Returns None on any failure — caller falls back to macro JSON.
    """
    try:
        import urllib.request
        import csv
        import io

        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
        with urllib.request.urlopen(url, timeout=10) as resp:
            text = resp.read().decode("utf-8")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        # Last row with a real value (some rows have "." for missing)
        for row in reversed(rows):
            if len(row) == 2 and row[1] not in (".", ""):
                try:
                    return float(row[1])
                except ValueError:
                    continue
    except Exception as e:
        log.debug("FRED VIX fetch failed: %s", e)
    return None


def _vix_from_macro_json(macro_path: Optional[str] = None) -> Optional[float]:
    """
    Derive VIX proxy from macro_intelligence_latest.json.

    vix_regime_score is a 0–1 normalised score. We reverse-map to a
    synthetic VIX level for tier classification:
      vix_regime_score 0.0 → VIX ≈ 40 (extreme fear)
      vix_regime_score 0.5 → VIX ≈ 20 (neutral)
      vix_regime_score 1.0 → VIX ≈ 10 (complacency)
    This is a rough proxy — prefer FRED when available.
    """
    if macro_path is None:
        # Standard pipeline path
        root = os.path.dirname(os.path.abspath(__file__))
        macro_path = os.path.join(root, "data", "macro", "macro_intelligence_latest.json")

    if not os.path.exists(macro_path):
        return None

    try:
        with open(macro_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Priority 1: nested path — extras.extras.extras.volatility.vix_spot
        # This is where the macro pipeline writes the actual VIX spot price.
        try:
            vix_spot = (data.get("extras", {})
                            .get("extras", {})
                            .get("extras", {})
                            .get("volatility", {})
                            .get("vix_spot"))
            if vix_spot is not None:
                return float(vix_spot)
        except (TypeError, AttributeError):
            pass

        # Priority 2: top-level direct field (forward-compatible if macro pipeline
        # ever adds vix_level or vix_close to the flat top-level schema)
        vix_direct = data.get("vix_level") or data.get("vix_close")
        if vix_direct:
            return float(vix_direct)

        # Priority 3: reverse-map from vix_regime_score (less precise — ±2pt error)
        score = data.get("vix_regime_score")
        if score is not None:
            vix_proxy = 40.0 - float(score) * 30.0   # 0→40, 1→10
            return round(max(10.0, min(80.0, vix_proxy)), 1)

        # Priority 4: infer from volatility_mode string
        vol_mode = str(data.get("volatility_mode", "")).upper()
        mapping = {
            "EXTREME":      45.0,
            "ELEVATED":     32.0,
            "TRANSITIONAL": 22.0,
            "NORMAL":       17.0,
            "SUPPRESSED":   12.0,
            "COMPLACENT":   11.0,
        }
        return mapping.get(vol_mode)

    except Exception as e:
        log.debug("Macro JSON VIX parse failed: %s", e)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CORE GOVERNOR
# ─────────────────────────────────────────────────────────────────────────────

class VIXGovernor:
    """
    Stateless VIX regime classifier and capital allocation governor.
    """

    def classify(self, vix: float) -> VIXGovernorResult:
        for floor, regime, alloc, pref, lmult, maxpos in VIX_TIERS:
            if vix >= floor:
                return VIXGovernorResult(
                    vix_level        = round(vix, 2),
                    regime           = regime,
                    max_allocation   = alloc,
                    strategy_pref    = pref,
                    long_option_mult = lmult,
                    max_positions    = maxpos,
                    data_source      = "CLASSIFY",
                )
        # Below 0 — treat as complacent
        return self.classify(10.0)

    def apply_to_portfolio(
        self,
        result:             VIXGovernorResult,
        total_capital:      float,
        current_positions:  int = 0,
    ) -> PortfolioBudget:
        return PortfolioBudget(
            capital_available   = round(total_capital * result.max_allocation, 2),
            positions_remaining = max(0, result.max_positions - current_positions),
            strategy_pref       = result.strategy_pref,
            long_option_mult    = result.long_option_mult,
            regime              = result.regime,
            vix_level           = result.vix_level,
        )


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

_governor = VIXGovernor()


def vix_governor_from_env(macro_path: Optional[str] = None) -> VIXGovernorResult:
    """
    Get VIXGovernorResult using best available data source.

    Priority:
      1. FRED API (live VIX close) — no key required
      2. macro_intelligence_latest.json (vix_regime_score reverse-map)
      3. Synthetic fallback: VIX=20 TRANSITION (conservative neutral)

    Call once per pipeline run (not per ticker).
    """
    # 1. FRED
    vix = _fetch_vix_fred()
    if vix:
        result = _governor.classify(vix)
        result.data_source = "FRED"
        log.info("VIX Governor: %.1f (%s) from FRED", vix, result.regime)
        return result

    # 2. Macro JSON
    vix = _vix_from_macro_json(macro_path)
    if vix:
        result = _governor.classify(vix)
        result.data_source = "MACRO_JSON"
        log.info("VIX Governor: %.1f (%s) from macro JSON", vix, result.regime)
        return result

    # 3. Synthetic fallback
    log.warning("VIX Governor: all data sources failed — using synthetic VIX=20 (TRANSITION)")
    result = _governor.classify(20.0)
    result.data_source = "SYNTHETIC"
    return result


def vix_governor_from_row(row: dict) -> Optional[VIXGovernorResult]:
    """
    Derive VIX governor from a superbrain row if vix-related fields present.
    Writes result fields back to row with 'vix_gov_' prefix as side effect.
    Returns None if no VIX data in row.
    """
    def _f(key: str) -> Optional[float]:
        try:
            v = row.get(key)
            if v is None: return None
            f = float(v)
            return None if f != f or f == 0 else f
        except (TypeError, ValueError):
            return None

    vix = _f("vix_level") or _f("vix_close") or _f("vix")
    if vix is None:
        # Try to derive from vix_regime_score in row
        score = _f("vix_regime_score")
        if score is not None:
            vix = 40.0 - score * 30.0

    if vix is None:
        return None

    result = _governor.classify(vix)
    result.data_source = "ROW"

    row["vix_gov_level"]           = result.vix_level
    row["vix_gov_regime"]          = result.regime
    row["vix_gov_max_alloc"]       = result.max_allocation
    row["vix_gov_strategy_pref"]   = result.strategy_pref
    row["vix_gov_long_option_mult"]= result.long_option_mult

    return result


def vix_governor_columns() -> list[str]:
    return [
        "vix_gov_level", "vix_gov_regime", "vix_gov_max_alloc",
        "vix_gov_strategy_pref", "vix_gov_long_option_mult",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  M4 VIX Governor v1.0.0 — Smoke Test")
    print("=" * 60 + "\n")

    gov = VIXGovernor()

    cases = [
        (45.0, "EXTREME",    0.50, "SELL_PREMIUM", 0.60),
        (35.0, "ELEVATED",   0.40, "SELL_PREMIUM", 0.75),
        (22.0, "TRANSITION", 0.35, "MIXED",        0.90),
        (17.0, "NORMAL",     0.30, "MIXED",        1.00),
        (12.0, "COMPLACENT", 0.25, "BUY_PREMIUM",  1.15),
    ]

    all_pass = True
    for vix, exp_regime, exp_alloc, exp_pref, exp_mult in cases:
        r = gov.classify(vix)
        ok = (r.regime == exp_regime and
              r.max_allocation == exp_alloc and
              r.strategy_pref == exp_pref and
              r.long_option_mult == exp_mult)
        status = "PASS" if ok else "FAIL"
        if not ok: all_pass = False
        print(f"  {status}  VIX={vix:.0f}  {r.regime:<12}  "
              f"alloc={r.max_allocation:.0%}  "
              f"pref={r.strategy_pref:<12}  "
              f"long_mult={r.long_option_mult:.2f}")

    # Portfolio budget test
    print()
    budget = gov.apply_to_portfolio(gov.classify(17.0), total_capital=100_000, current_positions=4)
    assert budget.capital_available == 30_000.0
    assert budget.positions_remaining == 8   # max_positions=12 - 4 current
    print(f"  Portfolio budget (VIX=17, £100k, 4 positions):")
    print(f"    capital_available   = £{budget.capital_available:,.0f}")
    print(f"    positions_remaining = {budget.positions_remaining}")
    print(f"    strategy_pref       = {budget.strategy_pref}")

    # FRED live fetch
    print()
    print("  Live FRED fetch (requires internet)...")
    vix_live = _fetch_vix_fred()
    if vix_live:
        r = gov.classify(vix_live)
        print(f"  FRED VIX: {vix_live:.2f} → {r.regime} "
              f"(alloc={r.max_allocation:.0%}, long_mult={r.long_option_mult:.2f})")
    else:
        print("  FRED fetch unavailable (offline/timeout) — fallback path used")

    print()
    print(f"  All classification tests {'PASSED' if all_pass else 'FAILED'}")
    print()
