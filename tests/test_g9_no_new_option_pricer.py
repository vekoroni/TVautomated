"""G9 guard (ACK approved 17 Oct 2026): no new option pricer outside the one pricing module.

Design: Enhancements/options_valuation_review/G5_G9_ONE_PRICER_ONE_BASIS_DESIGN_20261017.md (status section).
The 17 Oct review found eleven option pricers and three IV solvers; tests/test_ot4_one_valuation_engine.py only checked
the card's display, so nothing failed when a new copy appeared. The owner is domain/option_valuation.py. The existing
copies are listed below with their migration status (moved onto the module in the 24 Oct weekend bundle, or retired
with C8). A new pricer anywhere else fails this test: price it with domain.option_valuation instead.

Detection: a function whose name says it prices or inverts an option, or whose body uses a normal CDF (cdf / erf)
together with log and sqrt (the Black-Scholes shape).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Production code only: top-level modules, the package folders below, and Lane B's scratch folder (not its prev\).
PACKAGES = ["avshunter", "bridge", "canonical_data", "contracts", "domain", "intelligence-lab", "ma_cockpit",
            "macro_board", "macro_domain", "market_structure", "ml_confidence_layer", "news_terminal", "orchestrator",
            "pipeline_interpreter", "scripts", "short_swing", "src", "tools", "vanguard", "worker3", "zero_dte"]
SKIP_DIRS = {"venv", ".venv", "__pycache__", "node_modules", "prev", "tests"}
SCAN_EXTRA = [ROOT / "data" / "scratch" / "workaround"]          # Lane B lives in the scratch folder
NAME = re.compile(r"(black_?scholes|^bs_|_bs_|bsm|implied_vol|solve_iv|calibrated_iv|american_option_price|"
                  r"crr|binomial|_call_price)", re.I)

# (relative path, function) -> status. The owner first; every other entry is an existing copy awaiting migration.
ALLOWED = {
    # owner
    ("domain/option_valuation.py", "european_bsm_value"): "OWNER",
    ("domain/option_valuation.py", "american_crr_value"): "OWNER (tree owned here since 17 Oct, D3)",
    ("domain/option_valuation.py", "american_crr_values"): "OWNER (vectorised tree for Lane B, 17 Oct)",
    ("vanguard/ev_engine_v3.py", "american_option_price"): "FROZEN (Vanguard control; EV3 only; retired with C8)",
    # Lane A copies: move onto the owner in the 24 Oct weekend bundle (design M3-M9) or retire with C8
    ("domain/deterministic_option_valuation.py", "dividend_adjusted_black_scholes"): "MIGRATE 24 Oct (M3)",
    ("empirical_option_ev.py", "_bs_vector"): "MIGRATE 24 Oct (M4)",
    ("empirical_option_ev.py", "calibrated_iv"): "MIGRATE 24 Oct (M4)",
    ("scripts/compute_greeks_bs.py", "black_scholes_price"): "MIGRATE 24 Oct (M5)",
    ("scripts/compute_greeks_bs.py", "solve_implied_vol"): "MIGRATE 24 Oct (M5)",
    ("scripts/avshunter_options_intelligence.py", "bs_price"): "MIGRATE 24 Oct (M6)",
    ("scripts/avshunter_options_intelligence.py", "bs_delta"): "MIGRATE 24 Oct (M6)",
    ("scripts/avshunter_options_intelligence.py", "bs_gamma"): "MIGRATE 24 Oct (M6)",
    ("scripts/avshunter_options_intelligence.py", "bs_theta"): "MIGRATE 24 Oct (M6)",
    ("scripts/avshunter_options_intelligence.py", "bs_vega"): "MIGRATE 24 Oct (M6)",
    ("scripts/avshunter_options_intelligence.py", "bsm_vanna_charm"): "MIGRATE 24 Oct (M6; G4, 17 Oct)",
    ("scripts/avshunter_options_intelligence.py", "calibrate_heston"): "MIGRATE 24 Oct (M6; display-only model)",
    ("scripts/avshunter_options_intelligence.py", "resolve_iv_ownership"): "NOT A PRICER (IV labels; matched by shape)",
    ("scripts/avshunter_options_intelligence.py", "solve_iv"): "RETIRE 24 Oct (M6, dead code)",
    ("scripts/avshunter_options_intelligence.py", "bsm_price_vec"): "RETIRE 24 Oct (M6, dead code)",
    ("scripts/avshunter_options_intelligence.py", "backfill_greeks_vectorised"): "RETIRE 24 Oct (M6, dead code)",
    ("scripts/avshunter_options_intelligence.py", "backfill_mark_from_bsm"): "RETIRE 24 Oct (M6, dead code)",
    ("scripts/avshunter_universe_scanner.py", "_call_price_black_scholes"): "MIGRATE 24 Oct (M7)",
    ("scripts/avshunter_universe_scanner.py", "_implied_volatility_from_call"): "MIGRATE 24 Oct (M7)",
    ("macro_domain/gamma_exposure.py", "_bs_gamma"): "MIGRATE 24 Oct (M8)",
    ("contracts/selected_contract_economics.py", "_black_scholes_value"): "MIGRATE 24 Oct (M9)",
    ("domain/option_path_valuation.py", "_option_mark"): "MIGRATE 24 Oct (C8 research path engine)",
    ("macro_board/scenarios.py", "_bs"): "MIGRATE 24 Oct (macro board display, found 17 Oct)",
    ("macro_board/scenarios.py", "_bs_vec"): "MIGRATE 24 Oct (macro board display, found 17 Oct)",
    # Lane B
    ("data/scratch/workaround/avshunter_options_standalone.py", "bs_value"):
        "Lane B European context value (decision values use the owner since 17 Oct)",
    ("data/scratch/workaround/capture_score.py", "bs"): "MIGRATE 24 Oct (Lane B capture scorer, found 17 Oct)",
    ("data/scratch/workaround/capture_score.py", "solve_iv"): "MIGRATE 24 Oct (Lane B capture scorer, found 17 Oct)",
}


def _files():
    import os
    yield from ROOT.glob("*.py")
    for package in PACKAGES:
        for dirpath, dirnames, filenames in os.walk(ROOT / package):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                if name.endswith(".py"):
                    yield Path(dirpath) / name
    for folder in SCAN_EXTRA:
        if folder.is_dir():
            yield from folder.glob("*.py")


def _looks_like_pricer(fn: ast.FunctionDef, source: str) -> bool:
    if NAME.search(fn.name):
        return True
    body = ast.get_source_segment(source, fn) or ""
    return ("cdf" in body or "erf(" in body) and "log(" in body and "sqrt" in body


def _pricers():
    found = set()
    for path in _files():
        try:
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source)
        except (UnicodeDecodeError, SyntaxError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _looks_like_pricer(node, source):
                found.add((rel, node.name))
    return found


def test_no_option_pricer_exists_outside_the_owner_and_the_listed_copies():
    unexpected = sorted(_pricers() - set(ALLOWED))
    assert not unexpected, ("New option pricer(s) found. Price with domain.option_valuation instead, or get ACK's "
                            f"approval and list them here: {unexpected}")
