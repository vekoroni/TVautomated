"""
AVSHUNTER Morning Gate v1.0
============================
Three checks only. Replaces morning_thesis_validator.py entirely.

CHECK 1: Invalidation intact     — price has not opened through EOD invalidation level
CHECK 2: Macro regime unchanged  — no overnight regime flip
CHECK 3: Contract liquid         — live bid/ask present, spread under threshold

If CHECK 1 fails  → BLOCK. Thesis broken. No trade.
If CHECK 2 fails  → FLAG. Trader reviews macro context before entry.
If CHECK 3 fails  → FLAG. Contract repair required before entry.

All other context (VWAP, ORB, delta, IV rank, crowd arrival, horizon,
Fung-Hsieh, direction arbitration) is written as display fields only.
They NEVER gate the verdict.

Output: morning_validated_trades_{run_id}.csv
Columns: ticker, direction, verdict, block_reason, flag_reason,
         live_price, invalidation_price, contract_symbol,
         live_bid, live_ask, live_spread_pct, macro_regime_eod,
         macro_regime_now, regime_changed, size_modifier,
         [all EOD fields preserved]

Usage:
    python morning_gate.py
    python morning_gate.py --run-id 20260526_094003
    python morning_gate.py --run-id 20260526_094003 --spread-threshold 20
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MORNING_GATE] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("morning_gate")

ROOT         = Path(__file__).resolve().parent
RUNS_DIR     = ROOT / "data" / "output" / "runs"
MACRO_DIR    = ROOT / "dropbox" / "macro"
MACRO_PATH   = MACRO_DIR / "macro_intelligence_latest.json"

POLYGON_API_KEY    = os.getenv("POLYGON_API_KEY", "rM5gfljE3Dls1RSYpTFZjhLcG8ekTGL0").strip()
MARKETDATA_API_KEY = os.getenv("MARKETDATA_API_KEY", "eVRtV3kxVWQyY1VmTDhFekMwMVBJbTBhTjhEWndoUExXNTFtRURjMHRBND0").strip()

DEFAULT_SPREAD_THRESHOLD = 25.0  # percent — above this flags contract repair
LIVE_FETCH_WORKERS       = 4
LIVE_FETCH_TIMEOUT       = 10.0  # seconds per ticker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _f(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(str(value).replace("$", "").replace("%", "").replace(",", "").strip())
        return default if v != v else v  # NaN check
    except Exception:
        return default


def _s(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.upper() in {"NAN", "NONE", "NULL", "N/A", ""} else s


def _u(value: Any) -> str:
    return _s(value).upper()


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        log.warning("No rows to write.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _latest_run_id() -> Optional[str]:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8-sig"))
            rid = data.get("run_id") or data.get("latest_run_id")
            if rid:
                return str(rid).strip()
        except Exception:
            pass
    if RUNS_DIR.exists():
        dirs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
        return dirs[-1] if dirs else None
    return None


# ---------------------------------------------------------------------------
# Live data fetch — equity price only (Polygon)
# ---------------------------------------------------------------------------

def _fetch_live_price(ticker: str) -> Dict[str, Any]:
    """Fetch live equity snapshot from Polygon. Returns dict with live_price etc."""
    import urllib.request
    url = (
        f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/"
        f"{ticker}?apiKey={POLYGON_API_KEY}"
    )
    try:
        with urllib.request.urlopen(url, timeout=LIVE_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        ticker_data = data.get("ticker", {})
        day  = ticker_data.get("day", {})
        prev = ticker_data.get("prevDay", {})
        return {
            "live_price":      _f(ticker_data.get("lastTrade", {}).get("p"))
                               or _f(day.get("c")),
            "live_open":       _f(day.get("o")),
            "live_high":       _f(day.get("h")),
            "live_low":        _f(day.get("l")),
            "live_prev_close": _f(prev.get("c")),
            "live_volume":     _f(day.get("v")),
            "live_vwap":       _f(day.get("vw")),
            "live_data_source": "POLYGON_SNAPSHOT",
            "live_fetched_at": _utc_now(),
        }
    except Exception as exc:
        return {"live_fetch_error": str(exc), "live_data_source": "POLYGON_FAILED"}


def _fetch_live_contract(occ_symbol: str) -> Dict[str, Any]:
    """Fetch live options quote from MarketData.app."""
    import urllib.request
    encoded = occ_symbol.replace(" ", "%20")
    url = (
        f"https://api.marketdata.app/v1/options/quotes/{encoded}/"
        f"?token={MARKETDATA_API_KEY}"
    )
    try:
        with urllib.request.urlopen(url, timeout=LIVE_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        if data.get("s") == "ok" and data.get("bid"):
            bid = _f(data["bid"][0]) if isinstance(data["bid"], list) else _f(data["bid"])
            ask = _f(data["ask"][0]) if isinstance(data["ask"], list) else _f(data["ask"])
            mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
            spread_pct = (
                (ask - bid) / mid * 100.0
                if bid is not None and ask is not None and mid and mid > 0
                else None
            )
            return {
                "live_contract_bid":        bid,
                "live_contract_ask":        ask,
                "live_contract_mid":        mid,
                "live_contract_spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
                "live_contract_iv":         _f(data.get("iv", [None])[0] if isinstance(data.get("iv"), list) else data.get("iv")),
                "live_contract_delta":      _f(data.get("delta", [None])[0] if isinstance(data.get("delta"), list) else data.get("delta")),
                "live_options_source":      "MARKETDATA",
                "live_options_fetched_at":  _utc_now(),
            }
        return {"live_options_source": "MARKETDATA_NO_QUOTE"}
    except Exception as exc:
        return {"live_options_source": "MARKETDATA_FAILED", "live_options_error": str(exc)}


def _fetch_all_live(candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Fetch live equity and options data for all candidates concurrently."""
    results: Dict[str, Dict[str, Any]] = {}

    def fetch_one(row: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        ticker = _u(row.get("ticker", ""))
        live   = _fetch_live_price(ticker)
        time.sleep(0.1)
        occ = _s(
            row.get("evening_contract_symbol")
            or row.get("contract_symbol")
            or row.get("recommended_contract")
        )
        if occ:
            contract_live = _fetch_live_contract(occ)
            live.update(contract_live)
        return ticker, live

    with ThreadPoolExecutor(max_workers=LIVE_FETCH_WORKERS) as ex:
        futures = {ex.submit(fetch_one, row): row for row in candidates}
        for future in as_completed(futures):
            try:
                ticker, data = future.result()
                results[ticker] = data
                price = data.get("live_price", "N/A")
                log.info("  %-6s  price=%-10s  options=%s",
                         ticker, price, data.get("live_options_source", "NONE"))
            except Exception as exc:
                log.warning("Live fetch failed: %s", exc)

    return results


# ---------------------------------------------------------------------------
# Macro regime check
# ---------------------------------------------------------------------------

def _load_macro_regime() -> str:
    """Load current macro regime from latest macro JSON. Returns regime string."""
    if not MACRO_PATH.exists():
        return "UNKNOWN"
    try:
        data = json.loads(MACRO_PATH.read_text(encoding="utf-8-sig"))
        return _u(
            data.get("regime_state")
            or data.get("regime_label")
            or data.get("macro_regime")
            or "UNKNOWN"
        )
    except Exception:
        return "UNKNOWN"


def _regime_flipped(eod_regime: str, current_regime: str) -> bool:
    """
    True only on a material directional flip.
    TRANSITIONAL variants of the same base direction are NOT flips.
    """
    if not eod_regime or not current_regime:
        return False
    if eod_regime == current_regime:
        return False

    def _base(r: str) -> str:
        r = r.upper()
        if "BULL" in r:
            return "BULLISH"
        if "BEAR" in r:
            return "BEARISH"
        if "NEUTRAL" in r:
            return "NEUTRAL"
        return r

    return _base(eod_regime) != _base(current_regime)


# ---------------------------------------------------------------------------
# CHECK 1 — Invalidation intact
# ---------------------------------------------------------------------------

def _check_invalidation(row: Dict[str, Any], live_price: Optional[float]) -> tuple[bool, str]:
    """
    Returns (passed, reason).
    passed=True means invalidation is intact — thesis still valid.
    """
    if live_price is None:
        return True, "No live price — cannot check invalidation, proceeding"

    invalidation = _f(
        row.get("evening_invalidation_price")
        or row.get("invalidation_price")
        or row.get("invalidation_level")
    )
    if not invalidation or invalidation <= 0:
        return True, "No invalidation level set — EOD structure assumed intact"

    direction = _u(
        row.get("evening_direction")
        or row.get("canonical_direction")
        or row.get("resolved_direction")
        or row.get("direction")
    )

    if direction == "CALL" and live_price <= invalidation:
        return False, f"CALL thesis broken — price {live_price:.2f} at or below invalidation {invalidation:.2f}"
    if direction == "PUT" and live_price >= invalidation:
        return False, f"PUT thesis broken — price {live_price:.2f} at or above invalidation {invalidation:.2f}"

    return True, f"Invalidation intact — price {live_price:.2f} vs level {invalidation:.2f}"


# ---------------------------------------------------------------------------
# CHECK 2 — Macro regime unchanged
# ---------------------------------------------------------------------------

def _check_macro(row: Dict[str, Any], current_regime: str) -> tuple[bool, str]:
    """
    Returns (passed, reason).
    passed=True means no material regime flip overnight.
    """
    eod_regime = _u(
        row.get("morning_macro_regime_state")
        or row.get("macro_regime")
        or row.get("regime_state")
        or row.get("evening_regime_state")
    )

    if not eod_regime or eod_regime == "UNKNOWN":
        return True, f"EOD regime not recorded — current regime is {current_regime}"

    if _regime_flipped(eod_regime, current_regime):
        return False, f"Regime flipped overnight: {eod_regime} → {current_regime}"

    return True, f"Regime unchanged: {eod_regime} → {current_regime}"


# ---------------------------------------------------------------------------
# CHECK 3 — Contract liquid
# ---------------------------------------------------------------------------

def _check_contract(
    live_data: Dict[str, Any],
    spread_threshold: float,
    row: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    """
    Returns (passed, reason).
    passed=True means contract has a live quote with acceptable spread.
    """
    bid = _f(live_data.get("live_contract_bid"))
    ask = _f(live_data.get("live_contract_ask"))
    spread_pct = _f(live_data.get("live_contract_spread_pct"))

    if bid is None or ask is None:
        return False, "No live contract quote — repair contract before entry"

    if bid <= 0 or ask <= 0:
        return False, f"Contract quote invalid — bid={bid} ask={ask}"

    if spread_pct is not None and spread_pct > spread_threshold:
        return False, f"Spread too wide — {spread_pct:.1f}% exceeds {spread_threshold:.0f}% threshold"

    # ── Greek sub-conditions (require row context) ──────────────────
    if row is not None:
        delta = _f(live_data.get("live_contract_delta"))
        if delta is not None:
            abs_delta = abs(delta)
            if abs_delta < 0.20:
                return False, (f"Delta too low — abs(delta)={abs_delta:.3f} < 0.20 (contract too far OTM, no directional edge)")
            if abs_delta > 0.70:
                return False, (f"Delta too high — abs(delta)={abs_delta:.3f} > 0.70 (contract deep ITM, not intended instrument profile)")
        live_iv = _f(live_data.get("live_contract_iv"))
        if live_iv is not None:
            if live_iv <= 0:
                return False, (f"IV invalid — live_iv={live_iv:.4f} (zero or negative IV indicates broken/stale quote)")
            if live_iv > 2.50:
                return False, (f"IV invalid — live_iv={live_iv:.1%} > 250% (extreme IV indicates broken quote)")
        if live_iv is not None:
            eod_iv = _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv"))
            if eod_iv is not None and eod_iv > 0:
                iv_compression_ratio = live_iv / eod_iv
                if iv_compression_ratio < 0.70:
                    return False, (f"IV compression — live_iv={live_iv:.1%} is {(1 - iv_compression_ratio):.1%} below EOD iv={eod_iv:.1%}. Premium actively deflating — FLAG for trader review.")

    return True, f"Contract liquid — bid={bid:.2f} ask={ask:.2f} spread={spread_pct:.1f}%"


# ---------------------------------------------------------------------------
# Core gate function
# ---------------------------------------------------------------------------

def run_gate(
    row: Dict[str, Any],
    live_data: Dict[str, Any],
    current_regime: str,
    spread_threshold: float,
) -> Dict[str, Any]:
    """
    Run three checks. Write verdict. Return enriched row.
    BLOCK   = check 1 failed — thesis broken, no trade
    FLAG    = check 2 or 3 failed — trader must review before entry
    GO      = all three passed — trade eligible, trader decides
    """
    out = dict(row)
    live_price = _f(live_data.get("live_price"))

    # Stamp live data
    for k, v in live_data.items():
        out[k] = v

    # Run checks
    inv_pass,  inv_reason  = _check_invalidation(row, live_price)
    macro_pass, macro_reason = _check_macro(row, current_regime)
    contract_pass, contract_reason = _check_contract(live_data, spread_threshold, row)

    # Regime display fields
    eod_regime = _u(
        row.get("morning_macro_regime_state")
        or row.get("macro_regime")
        or row.get("regime_state")
    )
    out["macro_regime_eod"]     = eod_regime
    out["macro_regime_now"]     = current_regime
    out["regime_changed"]       = "TRUE" if not macro_pass else "FALSE"
    out["gate_checked_at_utc"]  = _utc_now()

    # Check results
    out["check_invalidation_pass"]   = "TRUE" if inv_pass else "FALSE"
    out["check_invalidation_reason"] = inv_reason
    out["check_macro_pass"]          = "TRUE" if macro_pass else "FALSE"
    out["check_macro_reason"]        = macro_reason
    out["check_contract_pass"]       = "TRUE" if contract_pass else "FALSE"
    out["check_contract_reason"]     = contract_reason

    # Greek gate diagnostics
    out["greek_gate_delta"]            = live_data.get("live_contract_delta", "")
    out["greek_gate_iv_live"]          = live_data.get("live_contract_iv", "")
    out["greek_gate_iv_eod"]           = (
        _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv")) or ""
    )
    out["greek_gate_iv_compression"]   = (
        round(
            _f(live_data.get("live_contract_iv"), 0) /
            _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv"), 1),
            4
        )
        if _f(live_data.get("live_contract_iv"))
        and _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv"))
        else ""
    )

    # Verdict
    block_reasons = []
    flag_reasons  = []

    if not inv_pass:
        block_reasons.append(inv_reason)
    if not macro_pass:
        flag_reasons.append(macro_reason)
    if not contract_pass:
        flag_reasons.append(contract_reason)

    if block_reasons:
        verdict = "BLOCK"
    elif flag_reasons:
        verdict = "FLAG"
    else:
        verdict = "GO"

    out["verdict"]      = verdict
    out["block_reason"] = "; ".join(block_reasons)
    out["flag_reason"]  = "; ".join(flag_reasons)

    # Lab compatibility aliases — field names the Intelligence Lab reads
    out["execution_permission"]         = verdict
    out["morning_execution_permission"] = verdict
    out["live_validation_state"]        = "CONFIRMED" if verdict == "GO" else verdict

    return out


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_morning_gate(
    run_id: str,
    spread_threshold: float = DEFAULT_SPREAD_THRESHOLD,
) -> List[Dict[str, Any]]:

    run_dir    = RUNS_DIR / run_id
    mv_dir     = run_dir / "morning_validation"
    input_path = mv_dir / f"morning_candidates_{run_id}.csv"
    output_path = mv_dir / f"morning_validated_trades_{run_id}.csv"
    summary_path = mv_dir / f"morning_gate_summary_{run_id}.json"

    if not input_path.exists():
        log.error("morning_candidates not found: %s", input_path)
        raise FileNotFoundError(str(input_path))

    candidates = _read_csv(input_path)
    log.info("Loaded %d candidates from %s", len(candidates), input_path.name)

    # Load current macro regime
    current_regime = _load_macro_regime()
    log.info("Current macro regime: %s", current_regime)

    # Fetch all live data
    log.info("Fetching live data for %d tickers...", len(candidates))
    live_map = _fetch_all_live(candidates)

    # Run gate
    results: List[Dict[str, Any]] = []
    for row in candidates:
        ticker    = _u(row.get("ticker", ""))
        live_data = live_map.get(ticker, {})
        result    = run_gate(row, live_data, current_regime, spread_threshold)
        results.append(result)

    # Write output
    _write_csv(output_path, results)
    log.info("Output written: %s", output_path)

    # Summary
    go_list    = [r for r in results if r["verdict"] == "GO"]
    flag_list  = [r for r in results if r["verdict"] == "FLAG"]
    block_list = [r for r in results if r["verdict"] == "BLOCK"]

    summary = {
        "run_id":           run_id,
        "validated_at_utc": _utc_now(),
        "input_candidates": len(candidates),
        "go_count":         len(go_list),
        "flag_count":       len(flag_list),
        "block_count":      len(block_list),
        "current_regime":   current_regime,
        "go_tickers":       [r.get("ticker") for r in go_list],
        "flag_tickers":     [r.get("ticker") for r in flag_list],
        "block_tickers":    [r.get("ticker") for r in block_list],
        "output_path":      str(output_path),
    }
    _write_json(summary_path, summary)

    # Print
    print("\n" + "=" * 60)
    print("  MORNING GATE RESULTS")
    print("=" * 60)
    print(f"  Run ID  : {run_id}")
    print(f"  Regime  : {current_regime}")
    print(f"  Total   : {len(candidates)}")
    print(f"  GO      : {len(go_list)}")
    print(f"  FLAG    : {len(flag_list)}  (trader reviews before entry)")
    print(f"  BLOCK   : {len(block_list)}  (thesis broken — no trade)")
    print()

    if go_list:
        # Group GO list by sector for manual macro alignment review
        sector_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in go_list:
            sector = _s(
                r.get("gics_sector")
                or r.get("sector_name")
                or r.get("sector")
                or r.get("gics_sector_name")
                or "UNKNOWN"
            ).upper() or "UNKNOWN"
            sector_map.setdefault(sector, []).append(r)

        print("  GO LIST — BY SECTOR:")
        for sector in sorted(sector_map.keys()):
            tickers = sector_map[sector]
            print(f"\n  [{sector}]  ({len(tickers)} tickers)")
            for r in sorted(tickers, key=lambda x: -(float(_s(x.get("scs_score") or x.get("priority_score") or "0") or 0))):
                tier      = _s(r.get("structural_tier") or r.get("tier") or "?")
                scs       = _s(r.get("scs_score") or r.get("priority_score") or "?")
                direction = _s(r.get("evening_direction") or r.get("direction") or "?")
                print(f"    {r['ticker']:<6} [{tier}]  {direction}  SCS={scs}  {r['check_contract_reason']}")

    if flag_list:
        print()
        print("  FLAG LIST (review before entry):")
        for r in flag_list:
            print(f"    {r['ticker']:<6}  {r['flag_reason']}")

    print()
    print(f"  Output: {output_path}")
    print("=" * 60 + "\n")

    print(json.dumps(summary, indent=2))

    # Score integrity check — runs automatically after every gate run
    try:
        import sys
        _interp_dir = ROOT.parent / "pipeline_interpreter"
        if str(_interp_dir) not in sys.path:
            sys.path.insert(0, str(_interp_dir))
        from score_integrity_check import check_score_integrity
        integrity = check_score_integrity(run_id)
        log.info(
            "Score integrity: compared=%d mismatches=%d rate=%.1f%% pass=%s",
            integrity.get("compared", 0),
            integrity.get("mismatches", 0),
            integrity.get("mismatch_rate", 0) * 100,
            integrity.get("integrity_pass", "UNKNOWN"),
        )
        if integrity.get("decommission_flag"):
            log.warning("TRIAGE DECOMMISSION FLAG SET — see data/output/TRIAGE_DECOMMISSION_NOTICE.json")
    except Exception as exc:
        log.warning("Score integrity check failed (non-fatal): %s", exc)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER Morning Gate — three checks only")
    parser.add_argument("--run-id", default=None, help="Run ID. Auto-resolves from latest.json if omitted.")
    parser.add_argument("--spread-threshold", type=float, default=DEFAULT_SPREAD_THRESHOLD,
                        help=f"Contract spread %% threshold for FLAG (default {DEFAULT_SPREAD_THRESHOLD})")
    args = parser.parse_args()

    run_id = args.run_id or _latest_run_id()
    if not run_id:
        log.error("Cannot resolve run_id. Pass --run-id or run the evening pipeline first.")
        return 1

    log.info("Morning Gate starting — run_id=%s", run_id)
    run_morning_gate(run_id=run_id, spread_threshold=args.spread_threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
