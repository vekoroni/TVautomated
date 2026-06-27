"""
AVSHUNTER Morning Gate v1.2
============================
Five checks. Replaces morning_thesis_validator.py entirely.

CHECK 1: Invalidation intact     — price has not opened through EOD invalidation level
CHECK 2: Macro regime unchanged  — no overnight regime flip
CHECK 3: Contract liquid         — live bid/ask present, spread under threshold
CHECK 4: Bond macro clear        — trade_go=False in bond_macro_state.json
CHECK 5: Layer 3 model risk clean — no VOL_HARDCAP / LOW_CONF_HIGH_VOL / THIN_HISTORY / IV_TAILWIND_EXTREME

If CHECK 1 fails  → BLOCK. Thesis broken. No trade.
If CHECK 2 fails  → FLAG. Trader reviews macro context before entry.
If CHECK 3 fails  → FLAG. Contract repair required before entry.
If CHECK 4 fails  → FLAG. Trader reviews bond macro context before entry.
If CHECK 5 fails  → FLAG. Trader reviews Layer 3 model risk before capital decision.

All other context (VWAP, ORB, delta, IV rank, crowd arrival, horizon,
Fung-Hsieh, direction arbitration) is written as display fields only.
They NEVER gate the verdict.

Output: morning_validated_trades_{run_id}.csv
Columns: ticker, direction, verdict, block_reason, flag_reason,
         live_price, invalidation_price, contract_symbol,
         live_bid, live_ask, live_spread_pct, macro_regime_eod,
         macro_regime_now, regime_changed, size_modifier,
         [all EOD fields preserved, including v6 actuarial fields:
          iv_regime, horizon_bucket, crabel_state — display only, never gates]

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
import re
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
BOND_MACRO_PATH        = MACRO_DIR / "bond_macro_state.json"
BOND_MACRO_MAX_AGE_H   = 26  # hours — covers overnight gap to 09:45 ET
MACRO_MAX_AGE_H        = 14  # hours — macro JSON older than this is flagged STALE (display only)
ENRICHMENT_DELTA_PATH  = MACRO_DIR / "avshunter_macro_enrichment_delta.json"
CHINA_EXPOSURE_PATH    = MACRO_DIR / "china_revenue_exposure.json"

# AG-04 GARCH vol regime transition constants
_VIX_REGIME_THRESHOLD_PCT  = 10.0  # VIX move > 10% triggers transition flag
_GARCH_TRANSITION_DISCOUNT = 0.75  # multiplier applied to l3_vol_forecast_conf display field

# AG-03 Options skew constants
_SKEW_EXPIRY_WINDOW_DAYS = 30   # days forward to target expiry for skew chain fetch
_SKEW_CALL_HIGH          = 1.10  # call_iv / put_iv above this = CALL_SKEW_HIGH
_SKEW_PUT_HIGH           = 0.90  # call_iv / put_iv below this = PUT_SKEW_HIGH

POLYGON_API_KEY    = os.getenv("POLYGON_API_KEY", "").strip()
MARKETDATA_API_KEY = os.getenv("MARKETDATA_API_KEY", "").strip()

DEFAULT_SPREAD_THRESHOLD = 25.0  # percent — above this flags contract repair
LIVE_FETCH_WORKERS       = 8     # increased for AG-03 skew fetch (2 extra calls per ticker)
LIVE_FETCH_TIMEOUT       = 10.0  # seconds per ticker

# Layer 3 model-risk capital guardrails. These never break the thesis; they
# convert otherwise-valid trades into FLAG / MODEL_RISK_REVIEW.
MODEL_RISK_VOL_HARDCAP     = 2.50
MODEL_RISK_LOW_CONF        = 65.0
MODEL_RISK_HIGH_VOL        = 1.50
MODEL_RISK_THIN_BARS       = 100
MODEL_RISK_TAILWIND_CAP    = 1.50

# ---------------------------------------------------------------------------
# v6 actuarial schema display fields — pass-through only, never gate logic
# ---------------------------------------------------------------------------
V6_ACTUARIAL_DISPLAY_FIELDS = [
    "iv_regime",       # Volatility regime from v6 actuarial schema
    "horizon_bucket",  # Forward horizon segment: 1_5d / 6_10d / 11_20d
    "crabel_state",    # Short-horizon mean reversion state
]


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


def _layer3_model_risk_guard(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return Layer 3 model-risk diagnostics for Morning Gate."""
    flags = []
    existing = _s(row.get("l3_model_risk_flags"))
    if existing:
        for part in re.split(r"[|,;]", existing):
            flag = part.strip().upper()
            if flag and flag not in flags:
                flags.append(flag)

    vol = _f(row.get("l3_forward_realised_vol"))
    conf = _f(row.get("l3_vol_forecast_conf"))
    n_bars = _f(row.get("l3_n_bars"))
    tailwind = _f(row.get("l3_iv_tailwind_score"))

    def add(flag: str) -> None:
        if flag not in flags:
            flags.append(flag)

    if vol is not None and vol >= MODEL_RISK_VOL_HARDCAP:
        add("VOL_HARDCAP")
    if (
        conf is not None
        and vol is not None
        and conf <= MODEL_RISK_LOW_CONF
        and vol >= MODEL_RISK_HIGH_VOL
    ):
        add("LOW_CONF_HIGH_VOL")
    if n_bars is not None and n_bars < MODEL_RISK_THIN_BARS:
        add("THIN_HISTORY")
    if tailwind is not None and abs(tailwind) > MODEL_RISK_TAILWIND_CAP:
        add("IV_TAILWIND_EXTREME")

    capped_tailwind = ""
    if tailwind is not None:
        capped_tailwind = max(-MODEL_RISK_TAILWIND_CAP, min(MODEL_RISK_TAILWIND_CAP, tailwind))

    details = []
    if vol is not None:
        details.append(f"vol={vol:.4f}")
    if conf is not None:
        details.append(f"conf={conf:.1f}")
    if n_bars is not None:
        details.append(f"n_bars={int(n_bars)}")
    if tailwind is not None:
        details.append(f"iv_tailwind={tailwind:.4f}")

    flag_text = "|".join(flags)
    reason = "Layer 3 model risk clear"
    if flags:
        reason = "Layer 3 model risk guard - " + flag_text
        if details:
            reason += " (" + ", ".join(details) + ")"

    return {
        "passed": not flags,
        "flags": flags,
        "flag_text": flag_text,
        "reason": reason,
        "capped_tailwind": capped_tailwind,
    }


def _side(value: Any) -> str:
    text = _u(value)
    if text in {"CALL", "PUT"}:
        return text
    if "LONG_CALL" in text or " CALL" in text or text.endswith("CALL"):
        return "CALL"
    if "LONG_PUT" in text or " PUT" in text or text.endswith("PUT"):
        return "PUT"
    return ""


def _contract_side_from_row(row: Dict[str, Any]) -> str:
    selected = _side(row.get("selected_contract_side"))
    if selected:
        return selected
    for key in ("contract_symbol", "recommended_contract", "preferred_contract", "contract_occ_symbol"):
        text = _u(row.get(key))
        if "P0" in text:
            return "PUT"
        if "C0" in text:
            return "CALL"
    delta = _f(row.get("live_contract_delta") or row.get("contract_delta"))
    if delta is not None and delta < 0:
        return "PUT"
    if delta is not None and delta > 0:
        return "CALL"
    return ""


def _append_reason(existing: Any, addition: str) -> str:
    current = _s(existing)
    if not current:
        return addition
    if addition in current:
        return current
    return current + "; " + addition


def _apply_thesis_direction_guard(row: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve locked footprint direction before active Morning Gate checks."""
    out = dict(row)
    footprint = _side(out.get("footprint_direction"))
    if footprint not in {"CALL", "PUT"}:
        return out

    current = _side(
        out.get("evening_direction")
        or out.get("canonical_direction")
        or out.get("resolved_direction")
        or out.get("direction")
    )
    lock_status = _u(out.get("footprint_lock_status"))
    reroute = _u(out.get("direction_reroute_status"))
    locked = lock_status.startswith("LOCKED") or reroute == "MAJOR_CATALYST_DIRECTION_OVERRIDE"
    if not locked:
        return out

    if current and current != footprint:
        for key in ("direction", "canonical_direction", "resolved_direction", "primary_direction", "evening_direction"):
            if key in out:
                out[key] = footprint
        catalyst = _side(out.get("catalyst_direction_bias") or out.get("catalyst_trade_bias"))
        reason = (
            f"Catalyst side {catalyst or 'UNKNOWN'} conflicts with thesis side {footprint}; "
            "thesis preserved, require live confirmation"
        )
        out["direction_reroute_status"] = "CATALYST_CONFLICT_THESIS_PRESERVED"
        out["footprint_lock_status"] = "LOCKED_UNTIL_LIVE_INVALIDATION"
        out["catalyst_direction_conflict_status"] = "CATALYST_CONFLICT_REQUIRES_CONFIRMATION"
        out["catalyst_direction_conflict_reason"] = reason
        out["direction_conflict_status"] = "MITIGATED_REQUIRES_CONFIRMATION"
        out["direction_conflict_gate"] = "VWAP_CONFIRMATION_REQUIRED"
        out["direction_conflict_reason"] = _append_reason(out.get("direction_conflict_reason"), reason)
        out["direction_decision_reason"] = _append_reason(
            out.get("direction_decision_reason"),
            f"GUARD:morning_gate_restored_locked_footprint_{footprint}_from_{current}",
        )
        summary = _s(out.get("thesis_summary"))
        pieces = summary.split(" ", 1)
        if len(pieces) == 2 and pieces[0].upper() in {"CALL", "PUT"}:
            out["thesis_summary"] = footprint + " " + pieces[1]

    contract_side = _contract_side_from_row(out)
    if contract_side and contract_side != footprint:
        out["morning_direction_guard_contract_side_conflict"] = "TRUE"
        out["contract_repair_required"] = "TRUE"
        out["contract_repair_reason"] = _append_reason(out.get("contract_repair_reason"), "SIDE_REPAIR_NEEDED")
    else:
        out["morning_direction_guard_contract_side_conflict"] = "FALSE"

    return out


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
            # AG-01: earnings announcement date from snapshot (no extra API call)
            "live_earnings_announcement": _s(ticker_data.get("earningsAnnouncement", "")),
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


def _iter_repair_alternatives(row: Dict[str, Any], primary_contract: str = "") -> List[str]:
    """Return ordered EOD repair alternatives, de-duped against the primary contract."""
    seen = {_u(primary_contract)}
    out: List[str] = []
    for key in ("alternative_contract_1", "alternative_contract_2", "alternative_contract_3"):
        symbol = _s(row.get(key))
        if not symbol:
            continue
        symbol_key = _u(symbol)
        if symbol_key in seen:
            continue
        seen.add(symbol_key)
        out.append(symbol)
    return out


def _try_live_repair_alternatives(
    row: Dict[str, Any],
    primary_contract: str,
    spread_threshold: float,
) -> Dict[str, Any]:
    """
    Test EOD-generated repair alternatives against live MarketData quotes.
    The first alternative that passes the same contract gate becomes the executable contract.
    """
    attempts: List[str] = []
    for alt_symbol in _iter_repair_alternatives(row, primary_contract):
        alt_live = _fetch_live_contract(alt_symbol)
        alt_pass, alt_reason = _check_contract(alt_live, spread_threshold, row)
        attempts.append(f"{alt_symbol}:{'PASS' if alt_pass else 'FAIL'}:{alt_reason}")
        if alt_pass:
            alt_live.update({
                "live_contract_symbol": alt_symbol,
                "morning_contract_repair_used": "TRUE",
                "morning_repaired_from_contract": primary_contract,
                "morning_repair_contract_symbol": alt_symbol,
                "morning_repair_reason": alt_reason,
                "morning_repair_attempts": " | ".join(attempts),
            })
            return alt_live
    return {"morning_repair_attempts": " | ".join(attempts)} if attempts else {}


def _fetch_all_live(
    candidates: List[Dict[str, Any]],
    spread_threshold: float = DEFAULT_SPREAD_THRESHOLD,
) -> Dict[str, Dict[str, Any]]:
    """Fetch live equity/options data and try EOD repair alternatives when the primary contract fails."""
    results: Dict[str, Dict[str, Any]] = {}

    def fetch_one(row: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        ticker = _u(row.get("ticker", ""))
        live   = _fetch_live_price(ticker)
        time.sleep(0.1)
        occ = _s(
            row.get("evening_contract_symbol")
            or row.get("contract_symbol")
            or row.get("recommended_contract")
            or row.get("preferred_contract")
        )
        if occ:
            contract_live = _fetch_live_contract(occ)
            contract_live["live_contract_symbol"] = occ
            primary_pass, primary_reason = _check_contract(contract_live, spread_threshold, row)
            contract_live["primary_contract_symbol"] = occ
            contract_live["primary_contract_pass"] = "TRUE" if primary_pass else "FALSE"
            contract_live["primary_contract_reason"] = primary_reason
            live.update(contract_live)
            if not primary_pass:
                repair_live = _try_live_repair_alternatives(row, occ, spread_threshold)
                if _s(repair_live.get("morning_contract_repair_used")).upper() == "TRUE":
                    live.update(repair_live)
                elif repair_live.get("morning_repair_attempts"):
                    live["morning_repair_attempts"] = repair_live.get("morning_repair_attempts")
        # AG-03: Options skew fetch (call IV / put IV ratio)
        skew_data = _fetch_options_skew(ticker)
        live.update(skew_data)
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

def _load_macro_state() -> Dict[str, Any]:
    """Load full macro state from macro_intelligence_latest.json.
    Returns a dict with regime_state, vol_mode, macro_conviction, sector_lead,
    sector_avoid, macro_filter, macro_as_of_utc, vix_spot, macro_loaded.
    Never raises — degrades to UNKNOWN on any error."""
    if not MACRO_PATH.exists():
        return {"regime_state": "UNKNOWN", "macro_loaded": False}
    try:
        data = json.loads(MACRO_PATH.read_text(encoding="utf-8-sig"))
        regime = _u(
            data.get("regime_state")
            or data.get("regime_label")
            or data.get("macro_regime")
            or "UNKNOWN"
        )
        sector_lead  = data.get("sector_lead")  or data.get("sector_leads")  or []
        sector_avoid = data.get("sector_avoid") or data.get("sectors_avoid") or []
        return {
            "regime_state":     regime,
            "vol_mode":         _u(data.get("vol_mode") or data.get("volatility_mode") or ""),
            "macro_conviction": _f(data.get("macro_conviction") or data.get("conviction")),
            "sector_lead":      sector_lead  if isinstance(sector_lead,  list) else [sector_lead],
            "sector_avoid":     sector_avoid if isinstance(sector_avoid, list) else [sector_avoid],
            "macro_filter":     _u(data.get("macro_filter") or data.get("trade_filter") or ""),
            "macro_as_of_utc":  _s(data.get("as_of_utc") or data.get("as_of") or data.get("generated_at") or ""),
            "vix_spot":         _f(data.get("vix_spot")),
            "macro_loaded":     True,
        }
    except Exception:
        return {"regime_state": "UNKNOWN", "macro_loaded": False}


def _load_bond_macro() -> Dict[str, Any]:
    """
    Load bond macro state from bond_macro_state.json sidecar.
    Returns empty dict if file missing, unreadable, or stale.
    Never raises — always degrades gracefully.

    Staleness threshold: BOND_MACRO_MAX_AGE_H hours.
    trade_go is returned as a Python bool (not string).
    """
    if not BOND_MACRO_PATH.exists():
        log.warning("bond_macro_state.json not found — bond macro check skipped")
        return {}
    try:
        data = json.loads(BOND_MACRO_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        log.warning("bond_macro_state.json unreadable (%s) — bond macro check skipped", exc)
        return {}

    # Staleness check
    generated_at = _s(data.get("generated_at"))
    if generated_at:
        try:
            from datetime import datetime
            gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if gen_dt.tzinfo is None:
                from datetime import timezone
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
            if age_h > BOND_MACRO_MAX_AGE_H:
                log.warning(
                    "bond_macro_state.json is %.1fh old (threshold %dh) — bond macro check skipped",
                    age_h, BOND_MACRO_MAX_AGE_H,
                )
                return {}
        except Exception:
            pass  # If we can't parse the timestamp, proceed with the data

    composite   = data.get("composite", {})
    yield_curve = data.get("yield_curve", {})
    credit      = data.get("credit_stress", {})
    zn          = data.get("zn_futures", {})
    auction     = data.get("auction", {})

    # Normalise trade_go to Python bool
    raw_trade_go = composite.get("trade_go", True)
    if isinstance(raw_trade_go, str):
        trade_go = raw_trade_go.strip().upper() not in {"FALSE", "0", "NO", ""}
    else:
        trade_go = bool(raw_trade_go)

    return {
        # Gate field
        "bond_trade_go":            trade_go,
        # Composite display fields
        "bond_macro_score":         composite.get("macro_bond_score"),
        "bond_macro_flag":          _s(composite.get("morning_manifest_flag")),
        "bond_primary_warning":     _s(composite.get("primary_warning")),
        "bond_all_warnings":        "; ".join(composite.get("all_warnings", [])),
        "bond_breakeven_adj_pct":   composite.get("breakeven_adjustment_pct"),
        # Yield curve display fields
        "bond_curve_state":         _s(yield_curve.get("curve_state")),
        "bond_spread_bps":          yield_curve.get("spread_bps"),
        "bond_curve_regime":        _s(yield_curve.get("regime_implication")),
        "bond_data_source":         _s(yield_curve.get("data_source")),
        # Credit display fields
        "bond_credit_stress":       _s(credit.get("stress_level")),
        "bond_credit_warning":      credit.get("credit_warning", False),
        # ZN futures display fields
        "bond_zn_direction":        _s(zn.get("zn_direction")),
        "bond_rate_regime_signal":  _s(zn.get("rate_regime_signal")),
        # Auction display fields
        "bond_auction_today":       auction.get("auction_today", False),
        "bond_spread_risk_flag":    auction.get("spread_risk_flag", False),
        # Meta
        "bond_macro_generated_at":  generated_at,
        "bond_macro_loaded":        "TRUE",
    }


def _load_enrichment_delta() -> Dict[str, str]:
    """
    Load ticker bias catalogue from avshunter_macro_enrichment_delta.json.
    Returns dict: {TICKER_UPPER: "BEARISH" | "BULLISH"}
    Only BEARISH and BULLISH are returned; MIXED, NEUTRAL and absent tickers are excluded.
    Actual path: data["market_data_snapshot"]["instrument_snapshot"][ticker]["bias"]
    Graceful: returns {} on any failure.
    """
    if not ENRICHMENT_DELTA_PATH.exists():
        return {}
    try:
        data = json.loads(ENRICHMENT_DELTA_PATH.read_text(encoding="utf-8-sig"))
        instrument_snapshot = data.get("market_data_snapshot", {}).get("instrument_snapshot", {})
        bias_map: Dict[str, str] = {}
        for ticker, ticker_data in instrument_snapshot.items():
            if not isinstance(ticker_data, dict):
                continue
            bias = _u(ticker_data.get("bias", ""))
            if bias in ("BEARISH", "BULLISH"):
                bias_map[_u(ticker)] = bias
        return bias_map
    except Exception as exc:
        log.info("Enrichment delta load skipped: %s", exc)
        return {}


def _load_china_exposure() -> Dict[str, Dict[str, Any]]:
    """Load China revenue exposure lookup from china_revenue_exposure.json.
    Returns dict: {TICKER_UPPER: {china_revenue_pct, china_sensitivity}}
    Graceful: returns {} on any failure."""
    if not CHINA_EXPOSURE_PATH.exists():
        return {}
    try:
        data = json.loads(CHINA_EXPOSURE_PATH.read_text(encoding="utf-8-sig"))
        raw = data.get("tickers", {})
        return {_u(k): v for k, v in raw.items() if isinstance(v, dict)}
    except Exception as exc:
        log.info("China exposure load skipped: %s", exc)
        return {}


def _fetch_options_skew(ticker: str) -> Dict[str, Any]:
    """
    Fetch ATM call and put IV for a ticker from MarketData.app.
    Computes call_iv / put_iv ratio as skew indicator.
    Graceful: returns {skew_available: False} on any failure.
    """
    import urllib.request
    from datetime import timedelta

    today      = datetime.now(timezone.utc).date()
    expiry     = today + timedelta(days=_SKEW_EXPIRY_WINDOW_DAYS)
    expiry_str = expiry.strftime("%Y-%m-%d")

    def get_atm_iv(side: str) -> Optional[float]:
        url = (
            f"https://api.marketdata.app/v1/options/chain/{ticker}/"
            f"?token={MARKETDATA_API_KEY}"
            f"&expiration={expiry_str}&strikeLimit=3&side={side}"
        )
        try:
            with urllib.request.urlopen(url, timeout=LIVE_FETCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            if data.get("s") != "ok":
                return None
            ivs = data.get("iv", [])
            if ivs:
                clean = [float(v) for v in ivs if v is not None and float(v) > 0]
                return sum(clean) / len(clean) if clean else None
        except Exception:
            return None
        return None

    call_iv = get_atm_iv("call")
    time.sleep(0.1)
    put_iv  = get_atm_iv("put")

    if call_iv is not None and put_iv is not None and put_iv > 0:
        skew_ratio = round(call_iv / put_iv, 4)
        skew_flag  = (
            "CALL_SKEW_HIGH" if skew_ratio > _SKEW_CALL_HIGH else
            "PUT_SKEW_HIGH"  if skew_ratio < _SKEW_PUT_HIGH  else
            "SKEW_NEUTRAL"
        )
        return {
            "skew_call_iv":   round(call_iv, 4),
            "skew_put_iv":    round(put_iv,  4),
            "skew_ratio":     skew_ratio,
            "skew_flag":      skew_flag,
            "skew_available": True,
            "skew_expiry":    expiry_str,
        }
    return {"skew_available": False, "skew_flag": "SKEW_UNAVAILABLE"}


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


def _check_bond_macro(bond_state: Dict[str, Any]) -> tuple[bool, str]:
    """
    CHECK 4: Bond macro clear.
    Returns (passed, reason).
    passed=True  → bond macro clean, display fields only
    passed=False → trade_go=False, FLAG the trade (never BLOCK)

    If bond_state is empty (file missing/stale), returns (True, reason)
    so the gate proceeds normally — bond check is advisory infrastructure.
    """
    if not bond_state:
        return True, "Bond macro state unavailable — check skipped"

    if not bond_state.get("bond_trade_go", True):
        warning = _s(bond_state.get("bond_primary_warning")) or "Bond macro headwind active"
        score   = bond_state.get("bond_macro_score", "N/A")
        flag    = _s(bond_state.get("bond_macro_flag")) or "BOND_MACRO_WARN"
        return False, f"Bond macro FLAG — {flag} score={score}: {warning}"

    score = bond_state.get("bond_macro_score", "N/A")
    flag  = _s(bond_state.get("bond_macro_flag")) or "BOND_MACRO_OK"
    return True, f"Bond macro clear — {flag} score={score}"


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
    if row is not None and _u(row.get("morning_direction_guard_contract_side_conflict")) == "TRUE":
        return False, "Contract side conflicts with preserved thesis direction - repair contract before entry"

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
    bond_state: Optional[Dict[str, Any]] = None,
    macro_state: Optional[Dict[str, Any]] = None,
    vix_regime_transition: bool = False,
    vix_move_pct: Optional[float] = None,
    enrichment_bias: Optional[Dict[str, str]] = None,
    china_risk_active: bool = False,
    china_exposure: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run three checks. Write verdict. Return enriched row.
    BLOCK   = check 1 failed — thesis broken, no trade
    FLAG    = check 2, 3, or 4 failed — trader must review before entry
    GO      = all checks passed — trade eligible, trader decides
    """
    out = dict(row)
    live_price = _f(live_data.get("live_price"))

    # Stamp live data
    for k, v in live_data.items():
        out[k] = v

    repaired_contract = _s(live_data.get("morning_repair_contract_symbol"))
    if repaired_contract:
        out["contract_symbol_original"] = _s(
            row.get("contract_symbol")
            or row.get("recommended_contract")
            or row.get("preferred_contract")
        )
        out["contract_symbol"] = repaired_contract
        out["recommended_contract"] = repaired_contract
        out["morning_selected_contract_symbol"] = repaired_contract
        out["contract_repair_resolved_at_open"] = "TRUE"
    else:
        out["contract_repair_resolved_at_open"] = "FALSE"

    out = _apply_thesis_direction_guard(out)

    # Run checks
    inv_pass,  inv_reason  = _check_invalidation(out, live_price)
    macro_pass, macro_reason = _check_macro(out, current_regime)
    contract_pass, contract_reason = _check_contract(live_data, spread_threshold, out)
    bond_pass, bond_reason = _check_bond_macro(bond_state or {})
    model_risk = _layer3_model_risk_guard(out)

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
    out["check_layer3_model_risk_pass"]   = "TRUE" if model_risk["passed"] else "FALSE"
    out["check_layer3_model_risk_reason"] = model_risk["reason"]
    out["l3_model_risk_flags"]            = model_risk["flag_text"]
    out["l3_model_risk_flag_count"]       = len(model_risk["flags"])
    out["l3_model_risk_capital_guard"]    = "TRUE" if model_risk["flags"] else "FALSE"
    if model_risk["capped_tailwind"] != "":
        out["l3_iv_tailwind_score_capped"] = round(model_risk["capped_tailwind"], 4)

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

    # Bond macro display fields — stamped regardless of trade_go verdict
    if bond_state:
        for _bond_field, _bond_val in bond_state.items():
            if _bond_field != "bond_trade_go":  # gate field — not exposed in output
                out[_bond_field] = _bond_val
    out["check_bond_macro_pass"]   = "TRUE" if bond_pass else "FALSE"
    out["check_bond_macro_reason"] = bond_reason

    # CF-01/02/03 + AG-07: Macro context display fields — non-blocking, display only
    if macro_state:
        out["macro_vol_mode"]    = macro_state.get("vol_mode", "")
        out["macro_conviction"]  = macro_state.get("macro_conviction", "")
        out["macro_filter"]      = macro_state.get("macro_filter", "")
        out["macro_as_of_utc"]   = macro_state.get("macro_as_of_utc", "")
        _sl = macro_state.get("sector_lead",  [])
        _sa = macro_state.get("sector_avoid", [])
        out["macro_sector_lead"]  = "; ".join(_sl)  if isinstance(_sl,  list) else _s(_sl)
        out["macro_sector_avoid"] = "; ".join(_sa) if isinstance(_sa, list) else _s(_sa)
        if macro_state.get("vix_spot") is not None:
            out["macro_vix_spot"] = macro_state["vix_spot"]
        # AG-07: Freshness flag — purely informational, never blocks or flags verdict
        _as_of = _s(macro_state.get("macro_as_of_utc"))
        if _as_of:
            try:
                _gen_dt = datetime.fromisoformat(_as_of.replace("Z", "+00:00"))
                if _gen_dt.tzinfo is None:
                    _gen_dt = _gen_dt.replace(tzinfo=timezone.utc)
                _age_h = (datetime.now(timezone.utc) - _gen_dt).total_seconds() / 3600
                out["macro_age_hours_gate"] = round(_age_h, 1)
                out["macro_freshness_flag"] = "STALE" if _age_h > MACRO_MAX_AGE_H else "FRESH"
            except Exception:
                out["macro_age_hours_gate"] = ""
                out["macro_freshness_flag"] = "UNKNOWN"
        else:
            out["macro_age_hours_gate"] = ""
            out["macro_freshness_flag"] = "UNKNOWN"
    else:
        out["macro_vol_mode"]       = ""
        out["macro_conviction"]     = ""
        out["macro_filter"]         = ""
        out["macro_as_of_utc"]      = ""
        out["macro_sector_lead"]    = ""
        out["macro_sector_avoid"]   = ""
        out["macro_age_hours_gate"] = ""
        out["macro_freshness_flag"] = "UNAVAILABLE"

    # AG-02: Volume anomaly flag — uses scanner_rvol (relative vol, already in row)
    # avg_volume_20d does not exist in morning_candidates; scanner_rvol is the proxy
    _rvol = _f(live_data.get("scanner_rvol") or row.get("scanner_rvol"))
    if _rvol is not None:
        out["volume_anomaly_ratio"] = round(_rvol, 2)
        out["volume_anomaly_flag"]  = "ANOMALY" if _rvol >= 2.0 else "NORMAL"
    else:
        out["volume_anomaly_ratio"] = ""
        out["volume_anomaly_flag"]  = "NO_DATA"

    # AG-01: Earnings catalyst calendar — from Polygon snapshot earningsAnnouncement field
    # No extra API call — extracted from existing live price fetch
    try:
        from earnings_calendar_enricher import enrich_from_announcement_str
        _earnings_str = _s(live_data.get("live_earnings_announcement") or row.get("earnings_announcement") or "")
        _earnings_fields = enrich_from_announcement_str(_earnings_str)
        out.update(_earnings_fields)
        # AG-01 Step 3: pre-earnings IV note for Options Intelligence display
        if _earnings_fields.get("earnings_catalyst_flag") == "TRUE":
            _days = _earnings_fields.get("earnings_days_to_event", "?")
            _timing = _earnings_fields.get("earnings_timing", "")
            out["pre_earnings_iv_note"] = (
                f"{_timing}: earnings in {_days} day(s) — IV skew check required before entry"
            )
        else:
            out["pre_earnings_iv_note"] = ""
    except Exception as _ecal_exc:
        out["earnings_timing"]        = "MODULE_ERROR"
        out["earnings_catalyst_flag"] = "FALSE"
        out["pre_earnings_iv_note"]   = ""
        log.debug("Earnings enricher error (non-fatal): %s", _ecal_exc)

    # AG-04: GARCH vol regime transition discount — DISPLAY ONLY, never modifies verdict
    # Original l3_vol_forecast_conf is preserved; adjusted value is the display field
    _raw_conf = _f(out.get("l3_vol_forecast_conf"))
    if vix_regime_transition:
        out["garch_vol_regime_transition"]   = "TRUE"
        out["garch_transition_discount_pct"] = round((1 - _GARCH_TRANSITION_DISCOUNT) * 100, 1)
        if vix_move_pct is not None:
            out["garch_vix_move_pct"] = round(vix_move_pct, 2)
        out["l3_vol_forecast_conf_adjusted"] = (
            round(_raw_conf * _GARCH_TRANSITION_DISCOUNT, 2) if _raw_conf is not None else ""
        )
    else:
        out["garch_vol_regime_transition"]   = "FALSE"
        out["garch_transition_discount_pct"] = 0
        out["l3_vol_forecast_conf_adjusted"] = _raw_conf if _raw_conf is not None else ""

    # AG-08: Enrichment delta bias — DISPLAY ONLY confidence modifier (+/- 5%)
    _ENRICHMENT_BOOST = 5.0
    _ticker_upper = _u(row.get("ticker", ""))
    _enrichment_label = (enrichment_bias or {}).get(_ticker_upper, "")
    if _enrichment_label:
        _raw_score = _f(out.get("scs_score") or out.get("confidence_score") or out.get("conf_pct"))
        _adjustment = _ENRICHMENT_BOOST if _enrichment_label == "BULLISH" else -_ENRICHMENT_BOOST
        out["enrichment_delta_bias"]      = _enrichment_label
        out["enrichment_conf_adjustment"] = _adjustment
        if _raw_score is not None:
            out["enrichment_conf_adjusted"] = round(max(0, min(100, _raw_score + _adjustment)), 2)
        else:
            out["enrichment_conf_adjusted"] = ""
        out["enrichment_delta_note"] = (
            f"Macro terminal bias: {_enrichment_label} "
            f"({'+'  if _enrichment_label == 'BULLISH' else ''}{_adjustment:.0f}% conf modifier)"
        )
    else:
        out["enrichment_delta_bias"]      = ""
        out["enrichment_conf_adjustment"] = 0
        out["enrichment_conf_adjusted"]   = ""
        out["enrichment_delta_note"]      = ""

    # AG-03: Options skew direction alignment — skew fields already stamped via live_data
    _skew_flag = _u(live_data.get("skew_flag", ""))
    _direction = _u(out.get("evening_direction") or out.get("direction") or "")
    if _skew_flag and _skew_flag not in ("SKEW_UNAVAILABLE", "SKEW_NEUTRAL", ""):
        _skew_aligned = (
            (_skew_flag == "CALL_SKEW_HIGH" and "CALL" in _direction) or
            (_skew_flag == "PUT_SKEW_HIGH"  and "PUT"  in _direction)
        )
        out["skew_direction_alignment"] = "ALIGNED" if _skew_aligned else "MISALIGNED"
        out["skew_alignment_note"] = (
            f"IV skew {_skew_flag} {'aligns' if _skew_aligned else 'conflicts'} "
            f"with direction {_direction}"
        )
    else:
        out["skew_direction_alignment"] = ""
        out["skew_alignment_note"]      = ""

    # AG-05: China revenue exposure modifier — DISPLAY ONLY
    _CHINA_CRITICAL_THRESHOLD = 40
    _CHINA_HIGH_THRESHOLD     = 20
    _china_data    = (china_exposure or {}).get(_ticker_upper, {})
    _china_rev_pct = _china_data.get("china_revenue_pct")
    _china_sens    = _s(_china_data.get("china_sensitivity", ""))
    if china_risk_active and _china_rev_pct is not None:
        if _china_rev_pct >= _CHINA_CRITICAL_THRESHOLD:
            _china_modifier = -10.0
            _china_note = (
                f"CHINA CRITICAL: {_china_rev_pct}% revenue exposure. "
                "HK/FXI bearish. -10% conf modifier."
            )
        elif _china_rev_pct >= _CHINA_HIGH_THRESHOLD:
            _china_modifier = -5.0
            _china_note = (
                f"CHINA HIGH: {_china_rev_pct}% revenue exposure. "
                "HK/FXI bearish. -5% conf modifier."
            )
        else:
            _china_modifier = 0.0
            _china_note = f"CHINA LOW: {_china_rev_pct}% revenue exposure. Monitor."
        out["china_revenue_pct"]   = _china_rev_pct
        out["china_sensitivity"]   = _china_sens
        out["china_conf_modifier"] = _china_modifier
        out["china_risk_active"]   = "TRUE"
        out["china_exposure_note"] = _china_note
    else:
        out["china_revenue_pct"]   = _china_rev_pct if _china_rev_pct is not None else ""
        out["china_sensitivity"]   = _china_sens
        out["china_conf_modifier"] = 0
        out["china_risk_active"]   = "TRUE" if china_risk_active else "FALSE"
        out["china_exposure_note"] = ""

    # Verdict and lab-compatible execution permission
    block_reasons = []
    flag_reasons = []

    if not inv_pass:
        block_reasons.append(inv_reason)
    if not macro_pass:
        flag_reasons.append(macro_reason)
    if not contract_pass:
        flag_reasons.append(contract_reason)
    if not model_risk["passed"]:
        flag_reasons.append(model_risk["reason"])
    if not bond_pass:
        flag_reasons.append(bond_reason)

    if block_reasons:
        verdict = "BLOCK"
        permission = "BLOCKED"
        route = "STAND_DOWN"
        lane = "THESIS_INVALIDATED"
        entry_action = "NO_TRADE"
        unlock_condition = "Thesis invalidated by morning price action"
    elif not contract_pass:
        verdict = "FLAG"
        permission = "CONTRACT_REPAIR"
        route = "REPAIR_CONTRACT"
        lane = "CONTRACT_REPAIR"
        entry_action = "SELECT_LIQUID_CONTRACT"
        unlock_condition = contract_reason
    elif not model_risk["passed"]:
        verdict = "FLAG"
        permission = "MODEL_RISK_REVIEW"
        route = "MODEL_RISK_REVIEW"
        lane = "MODEL_RISK_REVIEW"
        entry_action = "MANUAL_REVIEW"
        unlock_condition = model_risk["reason"]
    elif not macro_pass:
        verdict = "FLAG"
        permission = "ARMED"
        route = "MACRO_REVIEW"
        lane = "REVIEW_BEFORE_ENTRY"
        entry_action = "MANUAL_REVIEW"
        unlock_condition = macro_reason
    elif not bond_pass:
        verdict = "FLAG"
        permission = "ARMED"
        route = "BOND_MACRO_REVIEW"
        lane = "REVIEW_BEFORE_ENTRY"
        entry_action = "MANUAL_REVIEW"
        unlock_condition = bond_reason
    elif flag_reasons:
        verdict = "FLAG"
        permission = "ARMED"
        route = "REVIEW_BEFORE_ENTRY"
        lane = "REVIEW_BEFORE_ENTRY"
        entry_action = "MANUAL_REVIEW"
        unlock_condition = "; ".join(flag_reasons)
    else:
        verdict = "GO"
        permission = "GO"
        route = "READY_EXECUTE"
        lane = "LIVE_VALIDATED"
        entry_action = "MANUAL_ENTRY_ALLOWED"
        unlock_condition = "All morning gate checks passed"

    out["verdict"] = verdict
    out["block_reason"] = "; ".join(block_reasons)
    out["flag_reason"] = "; ".join(flag_reasons)

    # Lab compatibility aliases - field names the Intelligence Lab reads.
    out["morning_gate_verdict"] = verdict
    out["execution_permission"] = permission
    out["morning_execution_permission"] = permission
    out["morning_execution_route"] = route
    out["morning_execution_lane"] = lane
    out["morning_entry_action"] = entry_action
    out["morning_unlock_condition"] = unlock_condition
    out["live_validation_state"] = "CONFIRMED" if permission == "GO" else permission

    live_mid = _f(out.get("live_contract_mid"))
    live_spread = _f(out.get("live_contract_spread_pct"))
    if live_mid is not None and live_mid > 0:
        out["premium_mid"] = live_mid
        out["contract_mid"] = live_mid
    if live_spread is not None:
        out["spread_pct"] = live_spread / 100.0 if live_spread > 1 else live_spread
        out["contract_spread_pct"] = out["spread_pct"]

    # v6 actuarial display fields — pass-through from EOD manifest
    # These are informational context for the trader and Intelligence Lab.
    # They NEVER gate the verdict.
    for _v6_field in V6_ACTUARIAL_DISPLAY_FIELDS:
        if _v6_field in row and _v6_field not in out:
            out[_v6_field] = row[_v6_field]

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

    # Load current macro state (CF-01/02/03 — full dict replaces old string-only load)
    macro_state    = _load_macro_state()
    current_regime = macro_state.get("regime_state", "UNKNOWN")
    log.info(
        "Macro state loaded — regime=%s vol_mode=%s conviction=%s loaded=%s",
        current_regime,
        macro_state.get("vol_mode", ""),
        macro_state.get("macro_conviction", ""),
        macro_state.get("macro_loaded", False),
    )

    bond_state = _load_bond_macro()
    if bond_state:
        log.info(
            "Bond macro loaded — trade_go=%s score=%s flag=%s",
            bond_state.get("bond_trade_go"),
            bond_state.get("bond_macro_score"),
            bond_state.get("bond_macro_flag"),
        )
    else:
        log.info("Bond macro state not available — Check 4 will be skipped")

    # AG-08: Enrichment delta bias catalogue
    enrichment_bias = _load_enrichment_delta()
    log.info(
        "Enrichment delta: %d tickers biased (%d BEARISH, %d BULLISH)",
        len(enrichment_bias),
        sum(1 for v in enrichment_bias.values() if v == "BEARISH"),
        sum(1 for v in enrichment_bias.values() if v == "BULLISH"),
    )

    # AG-05: China risk flag — active when FXI or EWH is BEARISH in enrichment delta
    china_risk_active = (
        enrichment_bias.get("FXI") == "BEARISH"
        or enrichment_bias.get("EWH") == "BEARISH"
    )
    china_exposure = _load_china_exposure()
    log.info(
        "China risk: active=%s  exposure_tickers=%d",
        china_risk_active, len(china_exposure),
    )

    # AG-04: VIX regime transition check — display modifier for GARCH confidence
    vix_regime_transition = False
    vix_move_pct: Optional[float] = None
    try:
        _macro_raw = json.loads(MACRO_PATH.read_text(encoding="utf-8-sig"))
        _vix_spot  = _f(_macro_raw.get("vix_spot"))
        _vix_prev  = _f(_macro_raw.get("vix_prev_close"))
        if _vix_spot and _vix_spot > 0 and _vix_prev and _vix_prev > 0:
            vix_move_pct = abs((_vix_spot - _vix_prev) / _vix_prev) * 100
            if vix_move_pct >= _VIX_REGIME_THRESHOLD_PCT:
                vix_regime_transition = True
                log.warning(
                    "VIX REGIME TRANSITION: move=%.1f%% (spot=%.2f prev=%.2f) — "
                    "GARCH confidence discount %.0f%% applied to display fields",
                    vix_move_pct, _vix_spot, _vix_prev,
                    (1 - _GARCH_TRANSITION_DISCOUNT) * 100,
                )
            else:
                log.info("VIX regime stable: move=%.1f%% (below %.0f%% threshold)", vix_move_pct, _VIX_REGIME_THRESHOLD_PCT)
        else:
            log.info("VIX regime check skipped: vix_spot=%s vix_prev_close=%s (one or both absent)", _vix_spot, _vix_prev)
    except Exception as _vix_exc:
        log.info("VIX regime check skipped: %s", _vix_exc)

    # Fetch all live data
    log.info("Fetching live data for %d tickers...", len(candidates))
    live_map = _fetch_all_live(candidates, spread_threshold=spread_threshold)

    # Run gate
    results: List[Dict[str, Any]] = []
    for row in candidates:
        ticker    = _u(row.get("ticker", ""))
        live_data = live_map.get(ticker, {})
        result    = run_gate(
            row, live_data, current_regime, spread_threshold,
            bond_state=bond_state,
            macro_state=macro_state,
            vix_regime_transition=vix_regime_transition,
            vix_move_pct=vix_move_pct,
            enrichment_bias=enrichment_bias,
            china_risk_active=china_risk_active,
            china_exposure=china_exposure,
        )
        results.append(result)

    # Write output
    _write_csv(output_path, results)
    log.info("Output written: %s", output_path)

    # Summary
    go_list    = [r for r in results if r["verdict"] == "GO"]
    flag_list  = [r for r in results if r["verdict"] == "FLAG"]
    block_list = [r for r in results if r["verdict"] == "BLOCK"]

    repair_resolved_count = sum(
        1 for r in results
        if _s(r.get("contract_repair_resolved_at_open")).upper() == "TRUE"
    )

    _sl_summary = macro_state.get("sector_lead",  [])
    _sa_summary = macro_state.get("sector_avoid", [])
    summary = {
        "run_id":           run_id,
        "validated_at_utc": _utc_now(),
        "input_candidates": len(candidates),
        "go_count":         len(go_list),
        "flag_count":       len(flag_list),
        "block_count":      len(block_list),
        "contract_repair_resolved_count": repair_resolved_count,
        "current_regime":      current_regime,
        "macro_vol_mode":      macro_state.get("vol_mode", "UNAVAILABLE"),
        "macro_conviction":    macro_state.get("macro_conviction", "UNAVAILABLE"),
        "macro_filter":        macro_state.get("macro_filter", "UNAVAILABLE"),
        "macro_sector_lead":   "; ".join(_sl_summary)  if isinstance(_sl_summary,  list) else _s(_sl_summary),
        "macro_sector_avoid":  "; ".join(_sa_summary) if isinstance(_sa_summary, list) else _s(_sa_summary),
        "macro_as_of_utc":     macro_state.get("macro_as_of_utc", "UNAVAILABLE"),
        "macro_loaded":        macro_state.get("macro_loaded", False),
        "bond_macro_trade_go":   bond_state.get("bond_trade_go", "UNAVAILABLE"),
        "bond_macro_score":      bond_state.get("bond_macro_score", "UNAVAILABLE"),
        "bond_macro_flag":       bond_state.get("bond_macro_flag", "UNAVAILABLE"),
        "bond_macro_curve":      bond_state.get("bond_curve_state", "UNAVAILABLE"),
        "bond_macro_credit":     bond_state.get("bond_credit_stress", "UNAVAILABLE"),
        "bond_macro_loaded":     bond_state.get("bond_macro_loaded", "FALSE"),
        "go_tickers":       [r.get("ticker") for r in go_list],
        "flag_tickers":     [r.get("ticker") for r in flag_list],
        "block_tickers":    [r.get("ticker") for r in block_list],
        # v6 field coverage — confirms pass-through is working
        "v6_field_coverage": {
            field: {
                "present_in_go":    sum(1 for r in go_list    if _s(r.get(field))),
                "present_in_flag":  sum(1 for r in flag_list  if _s(r.get(field))),
                "present_in_block": sum(1 for r in block_list if _s(r.get(field))),
            }
            for field in V6_ACTUARIAL_DISPLAY_FIELDS
        },
        "output_path":      str(output_path),
    }
    _write_json(summary_path, summary)

    # Print
    print("\n" + "=" * 60)
    print("  MORNING GATE RESULTS")
    print("=" * 60)
    _vol_mode   = macro_state.get("vol_mode", "")      if macro_state else ""
    _conviction = macro_state.get("macro_conviction") if macro_state else None
    _macro_filter = macro_state.get("macro_filter", "") if macro_state else ""
    _regime_line = f"  Regime  : {current_regime}"
    if _vol_mode:
        _regime_line += f"  vol_mode={_vol_mode}"
    if _conviction is not None:
        _regime_line += f"  conviction={_conviction:.2f}"
    if _macro_filter:
        _regime_line += f"  filter={_macro_filter}"
    print(f"  Run ID  : {run_id}")
    print(_regime_line)
    bond_flag  = bond_state.get("bond_macro_flag",  "UNAVAILABLE") if bond_state else "UNAVAILABLE"
    bond_score = bond_state.get("bond_macro_score", "N/A")         if bond_state else "N/A"
    bond_go    = bond_state.get("bond_trade_go",    "N/A")         if bond_state else "N/A"
    print(f"  Bond    : {bond_flag}  score={bond_score}  trade_go={bond_go}")
    print(f"  Total   : {len(candidates)}")
    print(f"  GO      : {len(go_list)}")
    print(f"  FLAG    : {len(flag_list)}  (trader reviews before entry)")
    print(f"  BLOCK   : {len(block_list)}  (thesis broken — no trade)")
    print(f"  REPAIRED: {repair_resolved_count}  (EOD alternatives passed live contract gate)")
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
                or r.get("sector_etf")
                or r.get("scanner_sector")
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
        _interp_dir = ROOT / "pipeline_interpreter"
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

    if not POLYGON_API_KEY or not MARKETDATA_API_KEY:
        log.error("POLYGON_API_KEY and MARKETDATA_API_KEY must be set in .env — aborting")
        return 1

    run_id = args.run_id or _latest_run_id()
    if not run_id:
        log.error("Cannot resolve run_id. Pass --run-id or run the evening pipeline first.")
        return 1

    log.info("Morning Gate starting — run_id=%s", run_id)
    run_morning_gate(run_id=run_id, spread_threshold=args.spread_threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
