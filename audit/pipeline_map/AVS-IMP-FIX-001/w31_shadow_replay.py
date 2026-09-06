"""AVS-FIX-001 W3.1 — DEC-2 shadow replay. Measurement only, no production change.

    python audit/pipeline_map/AVS-IMP-FIX-001/w31_shadow_replay.py <run_id> [...]

For every BLOCK_SPREAD ticker in a completed run, this reloads that ticker's
STORED OPTION_CHAIN payload from the canonical store and re-runs contract
selection with the delta band widened by +/-0.10 and the DTE band by +/-7
days. **The spread gate is unchanged** — that is the whole point of DEC-2: it
asks how many candidates the pipeline lost to band tightness rather than to
illiquidity.

Every recovered contract is then pushed through the production functions, not
a reimplementation:

    scripts.avshunter_options_intelligence.compute_trade_economics
    contracts.selected_contract_economics.evaluate_long_option_monetisability

No provider call is made and nothing is written back into the run. The output
is a JSON report and a console summary; the number it produces is what sizes
W3.2, and it is written into DECISIONS_FOR_ACK as the DEC-2 answer.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
for candidate in (REPO, REPO / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import avshunter_options_intelligence as oi          # noqa: E402
from contracts.selected_contract_economics import (  # noqa: E402
    evaluate_long_option_monetisability,
)

CONTROL_PLANE = REPO / "data" / "canonical" / "control_plane.sqlite"
RUNS = REPO / "data" / "output" / "runs"

DELTA_WIDENING = 0.10
DTE_WIDENING = 7


# --------------------------------------------------------------------------

def load_chain_index(run_id: str) -> dict[str, Path]:
    """instrument -> stored OPTION_CHAIN payload path, for this run."""
    connection = sqlite3.connect(f"file:{CONTROL_PLANE}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT instrument_id, storage_uri FROM dataset_registry "
        "WHERE dataset_type='OPTION_CHAIN' AND source_run_id=?",
        (run_id,),
    ).fetchall()
    connection.close()
    return {str(instrument).upper(): Path(uri) for instrument, uri in rows}


def load_chain(path: Path) -> pd.DataFrame | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or not payload:
        return None
    frame = pd.DataFrame(payload)
    for column in ("delta", "dte", "spread_pct", "bid", "ask", "mid", "strike",
                   "implied_vol", "theta", "vega", "gamma", "open_interest",
                   "volume", "underlying_price"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def side_of(row: pd.Series) -> str:
    text = str(row.get("right") or "").strip().upper()
    if text.startswith("C"):
        return "CALL"
    if text.startswith("P"):
        return "PUT"
    return ""


def select_widened(chain: pd.DataFrame, *, direction: str, horizon: str) -> pd.DataFrame:
    """Production geometry with the delta and DTE bands widened; spread as-is."""
    config = oi.DTE_CONFIG.get(oi.normalise_horizon_key(horizon), oi.DTE_CONFIG["1_5d"])
    spread_limit = oi.horizon_spread_limit(horizon)

    side = chain.apply(side_of, axis=1)
    frame = chain[side.eq(direction)].copy()
    if frame.empty:
        return frame

    delta = frame["delta"].abs()
    frame = frame[
        delta.between(
            max(0.0, config["delta_min"] - DELTA_WIDENING),
            min(1.0, config["delta_max"] + DELTA_WIDENING),
        )
        & frame["dte"].between(
            max(1, config["dte_min"] - DTE_WIDENING),
            config["dte_max"] + DTE_WIDENING,
        )
        # The spread gate is deliberately NOT widened.
        & frame["spread_pct"].le(spread_limit)
        & frame["ask"].gt(0)
    ].copy()
    if frame.empty:
        return frame

    target_delta = (config["delta_min"] + config["delta_max"]) / 2.0
    frame["_delta_distance"] = (frame["delta"].abs() - target_delta).abs()
    return frame.sort_values(["_delta_distance", "spread_pct"])


def run_economics(contract: pd.Series, row: pd.Series, direction: str) -> dict[str, Any]:
    # compute_trade_economics reads these by subscript, so every one is
    # supplied from the row where the run recorded it and from a documented
    # neutral default otherwise. The defaults affect only the EV terms, not the
    # premium/breakeven/RR arithmetic this replay reports.
    spot = float(row.get("underlying_price") or contract.get("underlying_price") or 0.0)
    ctx = {
        "spot": spot,
        "entry": float(row.get("entry") or spot),
        "structural_target": row.get("structural_target"),
        "hold_days": float(row.get("planned_hold_sessions") or 5),
        "direction": direction,
        "intent": str(row.get("intent") or "ENTER"),
        "phase": str(row.get("phase") or "UNKNOWN"),
        "tier": str(row.get("tier") or "UNKNOWN"),
        "trend": str(row.get("trend") or "UNKNOWN"),
        "regime": str(row.get("regime") or row.get("macro_regime_label") or "UNKNOWN"),
        "win_prob": float(row.get("win_prob") or row.get("layer2__adjusted_prob_target_hit") or 0.5),
    }
    contract_dict = {
        "mark": float(contract.get("mid") or contract.get("ask") or 0.0),
        "strike": float(contract.get("strike") or 0.0),
        "theta": float(contract.get("theta") or -0.01),
        "vega": float(contract.get("vega") or 0.05),
        "delta": float(contract.get("delta") or 0.35),
        "dte": float(contract.get("dte") or 30),
    }
    iv_ctx = {
        "ivp_label": str(row.get("iv_regime") or "UNKNOWN"),
        "iv_regime": str(row.get("iv_regime") or "UNKNOWN"),
        "iv_percentile": row.get("iv_percentile"),
        "ivp_252d": row.get("ivp_252d"),
        "iv_vs_hv": row.get("iv_vs_hv"),
        "skew_label": str(row.get("skew_label") or "UNKNOWN"),
        "term_structure": str(row.get("term_structure") or "UNKNOWN"),
        "risk_reversal": row.get("risk_reversal"),
        "iv_direction": str(row.get("iv_direction") or "STABLE"),
        "iv_direction_pct": row.get("iv_direction_pct") or 0.0,
    }
    try:
        return oi.compute_trade_economics(contract_dict, ctx, iv_ctx)
    except Exception as error:                        # pragma: no cover
        return {"economics_state": "ERROR",
                "economics_reason": f"{type(error).__name__}:{error}"}


def run_monetisability(contract: pd.Series, row: pd.Series, direction: str) -> dict[str, Any]:
    hydrated = {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_structure": "LONG_SINGLE",
        "selected_structure_id": f"shadow::{contract.get('symbol')}",
        "selected_contract_symbol": str(contract.get("symbol") or ""),
        "selected_long_leg": {
            "symbol": str(contract.get("symbol") or ""),
            "bid": float(contract.get("bid") or 0.0),
            "ask": float(contract.get("ask") or 0.0),
            "strike": float(contract.get("strike") or 0.0),
        },
    }
    return evaluate_long_option_monetisability(
        {"canonical_direction": direction, "target_spot": row.get("structural_target")},
        hydrated,
    )


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap the tickers replayed (0 = all)")
    args = parser.parse_args(argv)

    options_path = RUNS / args.run_id / "options" / f"options_intelligence_{args.run_id}.csv"
    if not options_path.exists():
        print(f"options artefact not found: {options_path}", file=sys.stderr)
        return 1
    options = pd.read_csv(options_path, low_memory=False)

    reason = options.get("stand_down_reason", pd.Series([""] * len(options))).astype(str)
    blocked = options[reason.str.contains("BLOCK_SPREAD", na=False)].copy()
    direction_column = (
        "final_direction" if "final_direction" in blocked.columns else "direction"
    )

    chains = load_chain_index(args.run_id)

    counters: Counter[str] = Counter()
    by_direction: dict[str, Counter[str]] = {
        "CALL": Counter(), "PUT": Counter(), "OTHER": Counter()
    }
    recovered_rows: list[dict[str, Any]] = []

    rows = blocked if not args.limit else blocked.head(args.limit)
    for _, row in rows.iterrows():
        ticker = str(row.get("ticker") or "").upper()
        direction = str(row.get(direction_column) or "").upper()
        bucket = direction if direction in ("CALL", "PUT") else "OTHER"
        counters["blocked_rows"] += 1
        by_direction[bucket]["blocked_rows"] += 1

        if direction not in ("CALL", "PUT"):
            # RG-07: an OTHER row stands down and never selects a contract. It
            # is counted and skipped, never "recovered".
            counters["skipped_non_directional"] += 1
            by_direction[bucket]["skipped_non_directional"] += 1
            continue

        path = chains.get(ticker)
        if path is None or not path.exists():
            counters["no_stored_chain"] += 1
            by_direction[bucket]["no_stored_chain"] += 1
            continue
        chain = load_chain(path)
        if chain is None:
            counters["chain_unreadable"] += 1
            by_direction[bucket]["chain_unreadable"] += 1
            continue

        counters["chain_available"] += 1
        by_direction[bucket]["chain_available"] += 1

        candidates = select_widened(
            chain, direction=direction, horizon=row.get("horizon_bucket")
        )
        if candidates.empty:
            counters["no_candidate_after_widening"] += 1
            by_direction[bucket]["no_candidate_after_widening"] += 1
            continue

        counters["recovered_by_spread"] += 1
        by_direction[bucket]["recovered_by_spread"] += 1
        best = candidates.iloc[0]

        economics = run_economics(best, row, direction)
        economics_ok = str(economics.get("economics_state") or "").upper() not in {
            "NOT_EVALUATED", "ERROR", ""
        }
        if economics_ok:
            counters["passes_economics"] += 1
            by_direction[bucket]["passes_economics"] += 1
        else:
            counters[f"economics_{economics.get('economics_reason', 'UNKNOWN')}"] += 1

        monetisability = run_monetisability(best, row, direction)
        state = str(monetisability.get("monetisability_state") or "UNKNOWN")
        counters[f"monetisability_{state}"] += 1
        by_direction[bucket][f"monetisability_{state}"] += 1
        if state in ("MONETISABLE", "LIMITED"):
            counters["monetisable_or_limited"] += 1
            by_direction[bucket]["monetisable_or_limited"] += 1

        recovered_rows.append({
            "ticker": ticker,
            "direction": direction,
            "horizon": row.get("horizon_bucket"),
            "original_spread_pct": row.get("contract_spread_pct"),
            "recovered_symbol": best.get("symbol"),
            "recovered_delta": best.get("delta"),
            "recovered_dte": best.get("dte"),
            "recovered_spread_pct": best.get("spread_pct"),
            "candidates_found": int(len(candidates)),
            "economics_state": economics.get("economics_state"),
            "economics_reason": economics.get("economics_reason"),
            "rr_options": economics.get("rr_options"),
            "monetisability_state": state,
            "monetisability_reason": monetisability.get("monetisability_reason"),
        })

    report = {
        "run_id": args.run_id,
        "parameters": {
            "delta_widening": DELTA_WIDENING,
            "dte_widening_days": DTE_WIDENING,
            "spread_gate": "UNCHANGED (per-horizon band, AVS-FIX-001 W1.6)",
        },
        "totals": dict(counters),
        "by_direction": {k: dict(v) for k, v in by_direction.items()},
        "recovered": recovered_rows,
    }

    print("=" * 92)
    print(f"AVS-FIX-001 W3.1 DEC-2 shadow replay - run {args.run_id}")
    print(f"delta band +/-{DELTA_WIDENING}, DTE band +/-{DTE_WIDENING}d, "
          f"spread gate UNCHANGED")
    print("=" * 92)
    order = [
        "blocked_rows", "skipped_non_directional", "no_stored_chain",
        "chain_unreadable", "chain_available", "no_candidate_after_widening",
        "recovered_by_spread", "passes_economics", "monetisable_or_limited",
        "monetisability_MONETISABLE", "monetisability_LIMITED",
        "monetisability_NOT_MONETISABLE", "monetisability_DATA_MISSING",
    ]
    for key in order:
        if key in counters or key.startswith("monetisability_"):
            print(f"  {key:34s} {counters.get(key, 0):6d}   "
                  f"CALL={by_direction['CALL'].get(key, 0):5d}  "
                  f"PUT={by_direction['PUT'].get(key, 0):5d}  "
                  f"OTHER={by_direction['OTHER'].get(key, 0):4d}")
    other = {k: v for k, v in counters.items() if k not in order}
    if other:
        print("  other counters:", json.dumps(other, sort_keys=True))

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(f"  json: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
