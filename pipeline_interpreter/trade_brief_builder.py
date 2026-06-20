"""
AVSHUNTER Trade Brief Builder
==============================
Takes a fully-enriched interpreter row (including dcr_* and alt_*
fields from Sprint 2) and produces a structured trade brief.

The interpreter always produces a trade. The three possible
outcomes are:

  TRADE_NOW     - gate is GO, direction confirmed, contract liquid
  TRADE_ON_CONDITION - direction clear, waiting for one trigger
  NO_EDGE       - both directions have equal evidence (rare),
                  skip this ticker

There is no AVOID or DO_NOT_ENTER output. If the pipeline
misdiagnosed, the alternative trade is the recommendation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _s(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.upper() in {"NAN", "NONE", "NULL", "N/A", ""} else s


def _f(v: Any) -> Optional[float]:
    try:
        val = float(str(v).replace("$", "").replace("%", "").strip())
        return None if val != val else val
    except Exception:
        return None


def build_trade_brief(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a structured trade brief from a fully-enriched row.
    Called after direction_conflict_resolver and
    alternative_contract_selector have run (Sprint 2).

    Returns a trade_brief dict that is attached to the interpreter
    context and printed at the end of every ticker analysis.
    """

    ticker = _s(row.get("ticker", "UNKNOWN")).upper()

    # ── Direction ─────────────────────────────────────────────────
    # Use dominant direction from conflict resolver if available,
    # otherwise fall back to pipeline direction
    dcr_dominant   = _s(row.get("dcr_dominant_direction"))
    dcr_misdiag    = str(row.get("dcr_misdiagnosed", "")).upper() == "TRUE"
    pipeline_dir   = _s(
        row.get("evening_direction")
        or row.get("canonical_direction")
        or row.get("direction")
    ).upper()

    if dcr_dominant and dcr_dominant != "UNCLEAR":
        direction = dcr_dominant
        direction_source = "CONFLICT_RESOLVER" if dcr_misdiag else "PIPELINE_CONFIRMED"
    elif pipeline_dir:
        direction = pipeline_dir
        direction_source = "PIPELINE"
    else:
        direction = "UNCLEAR"
        direction_source = "UNKNOWN"

    # ── Contract ──────────────────────────────────────────────────
    # If repair selected a better contract, show that before the stale EOD contract.
    repair_contract = _s(
        row.get("morning_selected_contract_symbol")
        or row.get("live_selected_contract_symbol")
        or row.get("alternative_contract_1")
    )
    if repair_contract:
        contract        = repair_contract
        contract_bid    = _f(row.get("live_contract_bid") or row.get("contract_bid"))
        contract_ask    = _f(row.get("live_contract_ask") or row.get("contract_ask"))
        contract_mid    = _f(row.get("live_contract_mid") or row.get("contract_mid"))
        contract_delta  = _f(row.get("live_delta") or row.get("contract_delta"))
        contract_iv     = _f(row.get("live_iv") or row.get("contract_iv"))
        contract_source = "REPAIR_ALTERNATIVE"
    elif dcr_misdiag and _s(row.get("alt_contract_symbol")):
        contract        = _s(row.get("alt_contract_symbol"))
        contract_bid    = _f(row.get("alt_bid"))
        contract_ask    = _f(row.get("alt_ask"))
        contract_mid    = _f(row.get("alt_mid"))
        contract_delta  = _f(row.get("alt_delta"))
        contract_iv     = _f(row.get("alt_iv"))
        contract_source = "ALTERNATIVE"
    else:
        contract        = _s(
            row.get("evening_contract_symbol")
            or row.get("contract_symbol")
            or row.get("recommended_contract")
        )
        contract_bid    = _f(row.get("live_contract_bid"))
        contract_ask    = _f(row.get("live_contract_ask"))
        contract_mid    = _f(row.get("live_contract_mid"))
        contract_delta  = _f(row.get("live_delta") or row.get("contract_delta"))
        contract_iv     = _f(row.get("live_iv") or row.get("contract_iv"))
        contract_source = "PIPELINE"

    # ── Gate verdict ──────────────────────────────────────────────
    gate_verdict = _s(
        row.get("verdict")
        or row.get("morning_execution_permission")
        or row.get("execution_permission")
    ).upper()

    # ── Entry condition ───────────────────────────────────────────
    # Build from available price levels
    live_price     = _f(row.get("live_price") or row.get("last_price"))
    invalidation   = _f(
        row.get("evening_invalidation_price")
        or row.get("invalidation_price")
        or row.get("invalidation_level")
    )
    ema9           = _f(row.get("ema9_daily") or row.get("ema9"))
    vwap           = _f(row.get("live_vwap") or row.get("vwap"))

    # Entry condition: price must hold above EMA9 (CALL) or below EMA9 (PUT)
    if direction == "CALL" and ema9:
        entry_condition = (
            f"Price holds above ${ema9:.2f} (EMA9 daily). "
            f"Prefer entry on pullback toward EMA9 while IV stable."
        )
    elif direction == "PUT" and ema9:
        entry_condition = (
            f"Price breaks below ${ema9:.2f} (EMA9 daily) on volume. "
            f"Confirm close below before entry."
        )
    elif vwap and live_price:
        side = "above" if direction == "CALL" else "below"
        entry_condition = f"Price must hold {side} VWAP ${vwap:.2f}."
    else:
        entry_condition = "Manual entry assessment required - key levels not available."

    # ── Target levels ─────────────────────────────────────────────
    exit_t1 = _f(row.get("exit_t1") or row.get("target_1") or row.get("t1"))
    exit_t2 = _f(row.get("exit_t2") or row.get("target_2") or row.get("t2"))

    # ── Recommended action ────────────────────────────────────────
    if direction == "UNCLEAR":
        action = "NO_EDGE"
        action_reason = "Evidence equally split across directions. Skip this ticker."
    elif gate_verdict == "GO" and contract:
        action = "TRADE_NOW"
        action_reason = (
            f"Gate GO. {direction_source}. "
            f"Contract {contract} available with live quote."
        )
    elif gate_verdict in ("FLAG",) and contract:
        action = "TRADE_ON_CONDITION"
        action_reason = (
            f"Gate FLAG - trader review required before entry. "
            f"Direction {direction} confirmed by {direction_source}."
        )
    elif not contract:
        action = "TRADE_ON_CONDITION"
        action_reason = (
            f"No contract selected yet. Direction {direction} confirmed. "
            f"Select contract at open then re-run gate."
        )
    else:
        action = "TRADE_ON_CONDITION"
        action_reason = f"Gate {gate_verdict}. Await trigger before entry."

    # ── Confidence ────────────────────────────────────────────────
    dcr_call_score = _f(row.get("dcr_call_score", 0)) or 0.0
    dcr_put_score  = _f(row.get("dcr_put_score", 0)) or 0.0
    total_score    = dcr_call_score + dcr_put_score
    if total_score > 0:
        dominant_score = max(dcr_call_score, dcr_put_score)
        confidence_pct = round((dominant_score / total_score) * 100, 1)
    else:
        confidence_pct = None

    # ── Assemble brief ────────────────────────────────────────────
    brief = {
        "ticker":               ticker,
        "action":               action,
        "direction":            direction,
        "direction_source":     direction_source,
        "misdiagnosed":         dcr_misdiag,
        "contract":             contract,
        "contract_source":      contract_source,
        "contract_bid":         contract_bid,
        "contract_ask":         contract_ask,
        "contract_mid":         contract_mid,
        "contract_delta":       contract_delta,
        "contract_iv":          contract_iv,
        "gate_verdict":         gate_verdict,
        "entry_condition":      entry_condition,
        "invalidation":         invalidation,
        "exit_t1":              exit_t1,
        "exit_t2":              exit_t2,
        "live_price":           live_price,
        "action_reason":        action_reason,
        "confidence_pct":       confidence_pct,
    }
    return brief


def format_trade_brief(brief: Dict[str, Any]) -> str:
    """
    Format trade brief as a clean terminal block.
    Called by the interpreter to print after analysis.
    """
    lines = [
        "",
        "-" * 60,
        f"  TRADE BRIEF - {brief['ticker']}",
        "-" * 60,
    ]

    action = brief.get("action", "UNKNOWN")
    if action == "TRADE_NOW":
        lines.append(f"  ACTION     : TRADE NOW")
    elif action == "TRADE_ON_CONDITION":
        lines.append(f"  ACTION     : TRADE ON CONDITION")
    else:
        lines.append(f"  ACTION     : NO EDGE - SKIP")

    lines.append(f"  DIRECTION  : {brief.get('direction', '?')}  [{brief.get('direction_source', '?')}]")

    if brief.get("misdiagnosed"):
        lines.append(f"  NOTE       : Pipeline direction overridden - evidence supports {brief.get('direction')}")

    contract = brief.get("contract")
    if contract:
        mid   = brief.get("contract_mid")
        delta = brief.get("contract_delta")
        iv    = brief.get("contract_iv")
        lines.append(f"  CONTRACT   : {contract}")
        if mid is not None:
            lines.append(f"  MID        : ${mid:.2f}")
        if delta is not None:
            lines.append(f"  DELTA      : {delta:.3f}")
        if iv is not None:
            lines.append(f"  IV         : {iv:.1%}")
    else:
        lines.append("  CONTRACT   : Not yet selected - repair at open")

    lines.append(f"  GATE       : {brief.get('gate_verdict', '?')}")

    entry = brief.get("entry_condition")
    if entry:
        lines.append(f"  ENTRY      : {entry}")

    inv = brief.get("invalidation")
    if inv is not None:
        lines.append(f"  INVALIDATE : ${inv:.2f} - thesis broken above/below this level")

    t1 = brief.get("exit_t1")
    t2 = brief.get("exit_t2")
    if t1 is not None:
        lines.append(f"  TARGET T1  : ${t1:.2f}")
    if t2 is not None:
        lines.append(f"  TARGET T2  : ${t2:.2f}")

    conf = brief.get("confidence_pct")
    if conf is not None:
        lines.append(f"  CONFIDENCE : {conf:.1f}%")

    lines.append(f"  REASON     : {brief.get('action_reason', '')}")
    lines.append("-" * 60)
    lines.append("")

    return "\n".join(lines)

# CONTRACT-REPAIR-ALT-001: Trade brief prefers morning/repair alternatives.
