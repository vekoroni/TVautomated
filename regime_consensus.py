"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · REGIME CONSENSUS SCORE (RCS)                                  ║
║  Enhancements: E5 (Unified RCS), E6 (Macro Statisticalisation),            ║
║                E7 (EIL Strategy Regime Gate)                               ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║  Reads from: dropbox/macro/macro_intelligence_latest.json                  ║
║  Injects into: all 5 EIL strategy files + Kelly sizer                     ║
║                                                                             ║
║  Usage:                                                                     ║
║    from regime_consensus import RegimeConsensus                             ║
║    rcs = RegimeConsensus(macro_json_path)                                  ║
║    result = rcs.compute()                                                  ║
║    multiplier = rcs.get_kelly_multiplier()  # 1.0 / 0.7 / 0.4             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, asdict
# FIX-TIMEZONE (2026-04-23): timezone was only imported inside compute() at L244,
# causing NameError in _neutral_result() which also uses timezone.utc.
# Move to module-level so all methods have access.
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("avshunter.regime_consensus")

# ─── WEIGHTS (E5) ─────────────────────────────────────────────────────────────
# Must sum to 1.0

SIGNAL_WEIGHTS = {
    "net_liquidity":  0.30,   # WALCL - TGA - RRP (FRED) — your primary macro edge
    "vix_regime":     0.25,   # VIX level + trend (inverse: low VIX = high score)
    "gex_aggregate":  0.25,   # Net GEX across universe from options intelligence
    "macro_momentum": 0.20,   # ISM/NFP/CPI composite
}

# ─── REGIME THRESHOLDS ────────────────────────────────────────────────────────

RISK_ON_THRESHOLD  = 65.0   # RCS >= 65 → RISK_ON
RISK_OFF_THRESHOLD = 40.0   # RCS < 40  → RISK_OFF
# Between: NEUTRAL

# ─── KELLY MULTIPLIERS (E7) ───────────────────────────────────────────────────

REGIME_KELLY_MULTIPLIERS = {
    "RISK_ON":  1.0,    # Full Kelly
    "NEUTRAL":  0.7,    # 70% Kelly
    "RISK_OFF": 0.4,    # 40% Kelly — or skip directional entirely
}

# ─── MACRO JSON SCHEMA (E6) ───────────────────────────────────────────────────
# Expected keys in macro_intelligence_latest.json.
# GPT synthesis pipeline should write these structured scores (0.0–1.0).
# Legacy free-text fields are tolerated but scored via fallback heuristics.

STRUCTURED_MACRO_KEYS = {
    # Net liquidity
    "net_liquidity_score":    None,   # preferred: pre-scored 0–1
    "net_liquidity_delta_4w": None,   # fallback: raw $ billions delta

    # VIX
    "vix_regime_score":       None,   # preferred: pre-scored 0–1
    "vix_current":            None,   # fallback: raw VIX value

    # GEX
    "gex_regime_score":       None,   # preferred: pre-scored 0–1
    "gex_net_aggregate":      None,   # fallback: raw $ GEX value

    # Macro momentum
    "macro_momentum_score":   None,   # preferred: pre-scored 0–1
    "ism_manufacturing":      None,   # fallback component
    "nfp_delta_3m":           None,   # fallback component
}


# ─── RESULT DATACLASS ─────────────────────────────────────────────────────────

@dataclass
class RCSResult:
    rcs:              float        # 0–100 composite score
    label:            str          # RISK_ON | NEUTRAL | RISK_OFF
    kelly_multiplier: float        # 1.0 | 0.7 | 0.4
    components:       dict         # individual signal scores
    raw_inputs:       dict         # raw values read from macro JSON
    macro_source:     str          # path of macro JSON read
    computed_at:      str          # UTC timestamp
    schema_mode:      str          # "structured" | "legacy_fallback"
    warnings:         list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        c = self.components
        return (
            f"[RCS] {self.label} ({self.rcs:.1f}/100) | "
            f"liq={c.get('net_liquidity',0):.2f} "
            f"vix={c.get('vix_regime',0):.2f} "
            f"gex={c.get('gex_aggregate',0):.2f} "
            f"mom={c.get('macro_momentum',0):.2f} | "
            f"kelly_mult={self.kelly_multiplier:.1f}×"
        )

    def to_injection_dict(self) -> dict:
        """
        Returns flat dict ready to be written into every EIL dossier JSON.
        Keys prefixed with rcs_ for clear namespacing.
        """
        return {
            "rcs_score":            self.rcs,
            "rcs_label":            self.label,
            "rcs_kelly_multiplier": self.kelly_multiplier,
            "rcs_computed_at":      self.computed_at,
            "rcs_net_liquidity":    self.components.get("net_liquidity", 0),
            "rcs_vix_regime":       self.components.get("vix_regime", 0),
            "rcs_gex_aggregate":    self.components.get("gex_aggregate", 0),
            "rcs_macro_momentum":   self.components.get("macro_momentum", 0),
            "rcs_schema_mode":      self.schema_mode,
        }


# ─── REGIME CONSENSUS ENGINE ──────────────────────────────────────────────────

class RegimeConsensus:
    """
    Computes unified Regime Consensus Score (RCS) from macro_intelligence_latest.json.

    Supports two modes (E6):
      - structured: macro JSON contains pre-scored 0–1 values per signal
      - legacy_fallback: raw values parsed and normalised internally

    Intent: eventually all macro should be structured (removing GPT narrative
    variance). Legacy fallback maintains backward compatibility.
    """

    def __init__(
        self,
        macro_json_path: str | Path,
        weights: Optional[dict] = None,
    ):
        self.macro_path = Path(macro_json_path)
        self.weights    = weights or SIGNAL_WEIGHTS
        self._result:  Optional[RCSResult] = None

    def compute(self) -> RCSResult:
        """
        Read macro JSON, score each signal, compute weighted RCS.
        Caches result — call compute() once per pipeline run.
        """
        warnings   = []
        raw_inputs = {}
        components = {}
        schema_mode = "structured"

        # ── Load macro JSON ───────────────────────────────────────────────────
        if not self.macro_path.exists():
            warnings.append(f"Macro JSON not found: {self.macro_path} — defaulting to NEUTRAL")
            log.warning(warnings[-1])
            return self._neutral_result(warnings)

        try:
            with open(self.macro_path) as f:
                macro = json.load(f)
        except Exception as e:
            warnings.append(f"Failed to parse macro JSON: {e}")
            return self._neutral_result(warnings)

        # FIX-04 (2026-04-19): Macro JSON has triple-nested extras structure.
        # Recursively search all nesting levels for structured score fields
        # so RCS does not fall back to legacy_fallback when fields exist but
        # are buried inside extras.extras.extras.
        def _find_field(node, key):
            """Recursively find first occurrence of key in nested dict."""
            if not isinstance(node, dict):
                return None
            if key in node:
                return node[key]
            for v in node.values():
                if isinstance(v, dict):
                    result = _find_field(v, key)
                    if result is not None:
                        return result
            return None

        # Overlay found fields onto top-level macro dict so existing logic works
        for _key in ["net_liquidity_score", "vix_regime_score",
                     "gex_regime_score", "macro_momentum_score",
                     "vix_spot", "vix_5d_avg", "conviction_score",
                     "macro_conviction", "vix_contango", "liquidity_status"]:
            if macro.get(_key) is None:
                _found = _find_field(macro.get("extras", {}), _key)
                if _found is not None:
                    macro[_key] = _found

        # FIX-04: Derive the 4 structured score fields from raw macro data
        # when the macro rebuild script has not yet been updated to write them.
        # These derivations are applied ONLY when the structured field is absent.
        if macro.get("net_liquidity_score") is None:
            _liq = str(macro.get("liquidity_pulse") or
                       macro.get("liquidity_status") or "").upper()
            if "IMPROVING" in _liq or "EXPANSION" in _liq:
                macro["net_liquidity_score"] = 0.70
            elif "STABLE" in _liq:
                macro["net_liquidity_score"] = 0.50
            elif "CONTRACTING" in _liq or "DETERIORATING" in _liq:
                macro["net_liquidity_score"] = 0.30
            # else leave None → falls through to legacy delta fallback

        if macro.get("vix_regime_score") is None:
            _vix = macro.get("vix_spot")
            if _vix is not None:
                try:
                    # 0=fearful(high VIX), 1=complacent(low VIX)
                    macro["vix_regime_score"] = float(
                        max(0.0, min(1.0, 1.0 - (float(_vix) - 12.0) / 28.0))
                    )
                except (TypeError, ValueError):
                    pass

        if macro.get("macro_momentum_score") is None:
            _conv = (macro.get("macro_conviction") or
                     macro.get("conviction_score"))
            if _conv is not None:
                try:
                    macro["macro_momentum_score"] = float(
                        max(0.0, min(1.0, float(_conv)))
                    )
                except (TypeError, ValueError):
                    pass

        if macro.get("gex_regime_score") is None:
            # GEX feed not yet connected — use neutral (0.5) as placeholder
            # Will be overridden when GEX pipeline is live
            macro["gex_regime_score"] = 0.50

        # FIX-07: Macro freshness check — haircut conviction when stale
        try:
            from datetime import datetime, timezone, timedelta
            _norm_at = (macro.get("normalised_at_utc") or
                        macro.get("as_of_utc") or
                        macro.get("generated_at_utc") or "")
            if _norm_at:
                _norm_dt = datetime.fromisoformat(
                    str(_norm_at).replace("Z", "+00:00"))
                _age_h = (datetime.now(timezone.utc) - _norm_dt).total_seconds() / 3600
                if _age_h > 20:
                    log.warning(
                        f"[RCS] Macro is {_age_h:.1f}h old (> 20h threshold). "
                        f"Applying 0.85× conviction haircut."
                    )
                    for _sk in ["net_liquidity_score", "vix_regime_score",
                                "gex_regime_score", "macro_momentum_score"]:
                        if macro.get(_sk) is not None:
                            macro[_sk] = float(macro[_sk]) * 0.85
        except Exception as _age_err:
            log.debug(f"[RCS] Freshness check skipped: {_age_err}")

        raw_inputs = {k: macro.get(k) for k in STRUCTURED_MACRO_KEYS}

        # ── Score each signal ─────────────────────────────────────────────────

        # 1. Net liquidity
        if macro.get("net_liquidity_score") is not None:
            components["net_liquidity"] = np.clip(float(macro["net_liquidity_score"]), 0, 1)
        else:
            schema_mode = "legacy_fallback"
            nl = macro.get("net_liquidity_delta_4w", 0) or 0
            # Normalise: ±$200B range maps to 0–1
            components["net_liquidity"] = float(np.clip((nl + 200) / 400, 0, 1))
            warnings.append("net_liquidity: using raw delta fallback — add net_liquidity_score to macro JSON")

        # 2. VIX regime (inverse — low VIX = bullish = high score)
        if macro.get("vix_regime_score") is not None:
            components["vix_regime"] = np.clip(float(macro["vix_regime_score"]), 0, 1)
        else:
            schema_mode = "legacy_fallback"
            vix = macro.get("vix_current", 20) or 20
            # VIX 12 → score 1.0, VIX 52 → score 0.0
            components["vix_regime"] = float(np.clip(1 - (float(vix) - 12) / 40, 0, 1))
            warnings.append("vix_regime: using raw VIX fallback — add vix_regime_score to macro JSON")

        # 3. GEX aggregate (positive GEX = dealers long = suppression = mild bullish)
        if macro.get("gex_regime_score") is not None:
            components["gex_aggregate"] = np.clip(float(macro["gex_regime_score"]), 0, 1)
        else:
            schema_mode = "legacy_fallback"
            gex = macro.get("gex_net_aggregate", 0) or 0
            # Normalise: ±$1B range
            components["gex_aggregate"] = float(np.clip((float(gex) + 1e9) / 2e9, 0, 1))
            warnings.append("gex_aggregate: using raw GEX fallback — add gex_regime_score to macro JSON")

        # 4. Macro momentum (ISM/NFP composite)
        if macro.get("macro_momentum_score") is not None:
            components["macro_momentum"] = np.clip(float(macro["macro_momentum_score"]), 0, 1)
        else:
            schema_mode = "legacy_fallback"
            # Try to compute from ISM + NFP if available
            ism   = macro.get("ism_manufacturing")
            nfp   = macro.get("nfp_delta_3m")
            sub_scores = []
            if ism is not None:
                sub_scores.append(np.clip((float(ism) - 42) / 18, 0, 1))  # 42→0, 60→1
            if nfp is not None:
                sub_scores.append(np.clip((float(nfp) + 100) / 400, 0, 1)) # -100k→0, 300k→1
            components["macro_momentum"] = float(np.mean(sub_scores)) if sub_scores else 0.5
            warnings.append("macro_momentum: using component fallback — add macro_momentum_score to macro JSON")

        # ── Weighted RCS ──────────────────────────────────────────────────────
        rcs = sum(
            components[signal] * self.weights[signal]
            for signal in self.weights
            if signal in components
        ) * 100

        rcs = round(float(rcs), 2)

        # ── Label ─────────────────────────────────────────────────────────────
        if rcs >= RISK_ON_THRESHOLD:
            label = "RISK_ON"
        elif rcs < RISK_OFF_THRESHOLD:
            label = "RISK_OFF"
        else:
            label = "NEUTRAL"

        kelly_mult = REGIME_KELLY_MULTIPLIERS[label]

        result = RCSResult(
            rcs=rcs,
            label=label,
            kelly_multiplier=kelly_mult,
            components={k: round(float(v), 4) for k, v in components.items()},
            raw_inputs={k: v for k, v in raw_inputs.items() if v is not None},
            macro_source=str(self.macro_path),
            computed_at=datetime.now(timezone.utc).isoformat(),
            schema_mode=schema_mode,
            warnings=warnings,
        )

        self._result = result
        log.info(result.summary_line())

        if warnings:
            log.warning(
                f"RCS schema warnings ({len(warnings)}): migrate macro JSON to structured scoring. "
                f"See E6 implementation guide."
            )

        return result

    def get_result(self) -> Optional[RCSResult]:
        """Return cached result (call compute() first)."""
        return self._result

    def get_kelly_multiplier(self) -> float:
        """Convenience: returns the regime Kelly multiplier (1.0/0.7/0.4)."""
        if self._result is None:
            self.compute()
        return self._result.kelly_multiplier

    def get_label(self) -> str:
        """Convenience: returns regime label string."""
        if self._result is None:
            self.compute()
        return self._result.label

    def _neutral_result(self, warnings: list) -> RCSResult:
        """Return a safe NEUTRAL result when macro data is unavailable."""
        return RCSResult(
            rcs=50.0, label="NEUTRAL", kelly_multiplier=0.7,
            components={k: 0.5 for k in self.weights},
            raw_inputs={}, macro_source=str(self.macro_path),
            computed_at=datetime.now(timezone.utc).isoformat(),
            schema_mode="unavailable", warnings=warnings,
        )

    def save_to_run(self, run_id: str, base_dir: Path) -> None:
        """
        Write RCS result into the run's superbrain folder for Intel Lab pickup.
        """
        if self._result is None:
            log.warning("No RCS result to save — call compute() first")
            return

        out_dir = base_dir / "data" / "output" / "runs" / run_id / "superbrain"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"rcs_{run_id}.json"

        with open(out_path, "w") as f:
            json.dump(self._result.to_dict(), f, indent=2)

        log.info(f"RCS saved: {out_path}")


# ─── E7: REGIME GATE DECORATOR ────────────────────────────────────────────────

class RegimeGate:
    """
    Applies regime-based Kelly multiplier to a list of signals.

    Used inside each EIL strategy file:

        gate = RegimeGate(rcs_result)
        signals = gate.apply(signals, direction_field="eil_direction")
    """

    NEUTRAL_STRATEGIES = {"IRON_CONDOR", "STRADDLE", "STRANGLE", "BUTTERFLY"}

    def __init__(self, rcs_result: RCSResult):
        self.rcs    = rcs_result
        self.mult   = rcs_result.kelly_multiplier
        self.label  = rcs_result.label

    def apply(self, signals: list[dict], direction_field: str = "direction") -> list[dict]:
        """
        Enrich each signal with regime gate fields.
        Market-neutral strategies are exempt from size reduction.
        """
        out = []
        for sig in signals:
            direction  = sig.get(direction_field, "")
            strategy   = sig.get("strategy_type", "").upper()
            is_neutral = strategy in self.NEUTRAL_STRATEGIES

            if is_neutral:
                mult = 1.0   # Never penalise market-neutral
                gate = "EXEMPT"
            elif self.label == "RISK_OFF" and direction in ("LONG", "CALL"):
                mult = self.mult
                gate = f"PENALISED_{self.label}"
            elif self.label == "RISK_OFF" and direction in ("SHORT", "PUT"):
                mult = min(1.0, self.mult * 1.2)   # Slight favouring of short side in risk-off
                gate = f"FAVOURED_{self.label}"
            else:
                mult = self.mult
                gate = f"SCALED_{self.label}"

            enriched = dict(sig)
            enriched.update({
                "rcs_score":         self.rcs.rcs,
                "rcs_label":         self.label,
                "regime_gate":       gate,
                "regime_mult":       mult,
                # FIX-REGIME-PSE (2026-04-21): Write regime_state in PSE-readable form.
                # PSE._regime_multiplier() reads row.get("regime_state") and maps it
                # to a size multiplier. Without this, PSE defaults to 0.85× (TRANSITIONAL).
                "regime_state":      self.label,   # RISK_ON | NEUTRAL | RISK_OFF
                "regime_size_mult":  mult,
            })
            out.append(enriched)

        return out


# ─── MACRO JSON SCHEMA HELPER (E6) ────────────────────────────────────────────

MACRO_STRUCTURED_TEMPLATE = {
    "_schema_version": "2.0",
    "_generated_at":   "ISO8601 UTC timestamp",
    "_note": "All *_score fields are 0.0–1.0. Replace legacy free-text fields with these.",

    # Net Liquidity (WALCL - TGA - RRP)
    "net_liquidity_score":    0.0,   # 0=contracting, 1=expanding
    "net_liquidity_delta_4w": 0.0,   # raw $ billions (legacy, keep for reference)
    "net_liquidity_level":    0.0,   # absolute level $ billions

    # VIX
    "vix_regime_score":  0.0,        # 0=fearful(high VIX), 1=complacent(low VIX)
    "vix_current":       20.0,       # raw VIX value
    "vix_trend_5d":      0.0,        # positive=rising, negative=falling

    # GEX
    "gex_regime_score":  0.0,        # 0=negative GEX (amplifying), 1=positive (suppressing)
    "gex_net_aggregate": 0.0,        # raw net GEX $ (legacy)

    # Macro Momentum
    "macro_momentum_score": 0.0,     # 0=contracting, 1=expanding
    "ism_manufacturing":    50.0,    # raw ISM (legacy)
    "nfp_delta_3m":         0.0,     # 3m avg NFP change (legacy)

    # Optional extended fields
    "yield_curve_score":   0.0,      # 0=inverted, 1=steep
    "credit_spread_score": 0.0,      # 0=wide (stress), 1=tight (calm)
}


def print_macro_migration_guide() -> None:
    """Prints instructions for migrating macro JSON to structured format (E6)."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  E6: MACRO JSON MIGRATION GUIDE                            ║
╠══════════════════════════════════════════════════════════════╣
║                                                            ║
║  Current:  GPT synthesises free-text → high variance       ║
║  Target:   GPT writes structured JSON scores (0.0–1.0)     ║
║                                                            ║
║  Step 1: Update your GPT macro synthesis prompt to output  ║
║          the structured template (see MACRO_STRUCTURED_    ║
║          TEMPLATE in this file).                           ║
║                                                            ║
║  Step 2: The *_score fields replace the free-text "regime  ║
║          read" with a deterministic float the RCS engine   ║
║          can use directly without fallback heuristics.     ║
║                                                            ║
║  Step 3: Keep legacy fields (vix_current, gex_net_, etc.)  ║
║          as reference — the RCS engine will use structured ║
║          scores when present and fall back gracefully.     ║
║                                                            ║
║  Example GPT prompt addition:                              ║
║    "Output net_liquidity_score as a float from 0.0 (severe ║
║     contraction) to 1.0 (strong expansion) based on the   ║
║     4-week WALCL delta. Do not output explanatory text,    ║
║     only the JSON object."                                 ║
║                                                            ║
╚══════════════════════════════════════════════════════════════╝
""")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Regime Consensus Score — test run")
    parser.add_argument("--macro", type=str, required=True, help="Path to macro_intelligence_latest.json")
    parser.add_argument("--guide", action="store_true", help="Print macro migration guide")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.guide:
        print_macro_migration_guide()

    rcs = RegimeConsensus(args.macro)
    result = rcs.compute()

    print(f"\n{result.summary_line()}")
    print(f"\nComponents:")
    for k, v in result.components.items():
        print(f"  {k:<20} {v:.4f}  (weight={SIGNAL_WEIGHTS.get(k, 0):.2f})")
    print(f"\nKelly multiplier: {result.kelly_multiplier}×")
    print(f"Schema mode:      {result.schema_mode}")
    if result.warnings:
        print(f"\nWarnings:")
        for w in result.warnings:
            print(f"  ⚠  {w}")
