"""
AVSHUNTER - EXECUTION GATE v1.1.0
See full docstring inline.
"""
from __future__ import annotations
import csv, json, logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("avshunter.execution_gate")
GATE_VERSION = "1.1.0"

class ExecutionGateConfig:
    SPREAD_FULL: float = 0.08
    SPREAD_MAX:  float = 0.15
    DELTA_HARD_MIN: float = 0.20
    DELTA_SOFT_MIN: float = 0.30
    DELTA_SOFT_MAX: float = 0.60
    DELTA_HARD_MAX: float = 0.85
    IV_ELEVATED: float = 0.60
    IV_EXTREME:  float = 1.00
    MIN_RUNWAY_PCT: float = 0.015
    TARGET_GAIN_MULTIPLE: float = 2.0
    TRENDING_REGIMES: frozenset = frozenset({"TRENDING_BULL","RISK_ON","RECOVERY","STRONG_BULL"})
    PSE_CONVICTION_MIN: float = 0.01
    PROBE_SIZE_LABEL: str = "BUY_SMALL"

cfg_gate = ExecutionGateConfig()

_STUB_WARNED = False
def get_live_option_data(symbol: str, contract_symbol: str = "") -> dict:
    global _STUB_WARNED
    if not _STUB_WARNED:
        log.warning("execution_gate: get_live_option_data() is the STUB. Wire in MarketData.app or Tastytrade before live trading.")
        _STUB_WARNED = True
    return {}

def _f(row, key, default=0.0):
    try:
        v = row.get(key, default)
        if v is None or str(v).strip().lower() in ("","nan","none","null"): return default
        return float(v)
    except: return default

def _s(row, key, default=""):
    try:
        v = row.get(key, default)
        if v is None: return default
        s = str(v).strip()
        return s.upper() if s else default
    except: return default

def _skip(row, reason, warnings=None):
    return {**row, "final_action":"SKIP","gate_reason":reason,"gate_warnings":",".join(warnings or []),
            "gate_size_penalty":0.0,"gate_conviction_override":False,
            "gate_version":GATE_VERSION,"gate_timestamp_utc":datetime.now(timezone.utc).isoformat()}

def _is_conviction_override(row):
    return (_s(row,"campaign_verdict")=="READY_EXECUTE"
            and _s(row,"kelly_verdict") not in ("NO_TRADE","")
            and _f(row,"pse_final_size") >= cfg_gate.PSE_CONVICTION_MIN)


def _num_value(value, default=0.0):
    try:
        if value is None:
            return default
        text = str(value).strip().replace("%", "")
        if text.lower() in ("", "nan", "none", "null", "n/a"):
            return default
        return float(text)
    except Exception:
        return default


def _first_value(row, *keys, default=""):
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text.upper() not in ("", "NAN", "NONE", "NULL", "N/A"):
            return value
    return default


def _normalise_ratio(value):
    value = _num_value(value, 0.0)
    if value > 5.0:
        return value / 100.0
    return value


def _live_option_data_from_row(row: dict) -> dict:
    bid = _num_value(_first_value(row, "live_contract_bid", "live_bid", "contract_bid"), 0.0)
    ask = _num_value(_first_value(row, "live_contract_ask", "live_ask", "contract_ask"), 0.0)
    if ask <= 0:
        return {}
    mid = _num_value(_first_value(row, "live_contract_mid", "live_mid", "contract_mid"), 0.0)
    if mid <= 0 and bid >= 0:
        mid = (bid + ask) / 2.0
    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "delta": _num_value(_first_value(row, "live_contract_delta", "live_delta", "contract_delta"), 0.0),
        "iv": _normalise_ratio(_first_value(row, "live_contract_iv", "live_iv", "contract_iv")),
        "iv_rank": _num_value(_first_value(row, "live_iv_rank", "iv_rank", "morning_iv_rank"), 50.0),
    }


def _morning_permission(row: dict) -> str:
    perm = _s(row, "morning_execution_permission")
    if not perm:
        perm = _s(row, "execution_permission")
    if not perm:
        perm = _s(row, "verdict")
    if perm == "BLOCK":
        return "BLOCKED"
    if perm == "FLAG":
        contract_pass = _s(row, "check_contract_pass")
        if contract_pass == "FALSE":
            return "CONTRACT_REPAIR"
        return "ARMED"
    return perm


def _preserve(row, action, reason, warnings=None):
    return {
        **row,
        "final_action": action,
        "gate_reason": reason,
        "gate_warnings": ",".join(warnings or []),
        "gate_size_penalty": 0.0,
        "gate_conviction_override": False,
        "gate_version": GATE_VERSION,
        "gate_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "preservation_gate": True,
    }

def execution_gate(row: dict) -> dict:
    ticker = _s(row, "ticker", "UNK")
    ts = datetime.now(timezone.utc).isoformat()
    try:
        morning_perm = _morning_permission(row)
        if morning_perm in ("BLOCKED", "BLOCK", "REJECT", "REJECTED"):
            return _preserve(row, "BLOCK", "UPSTREAM_BLOCK")
        if morning_perm == "CONTRACT_REPAIR":
            return _preserve(
                row,
                "CONTRACT_REPAIR",
                _s(row, "check_contract_reason", "CONTRACT_REPAIR_REQUIRED"),
            )
        if morning_perm in ("WAIT", "ARMED"):
            return _preserve(
                row,
                "MANUAL_REVIEW",
                _s(row, "flag_reason", "MORNING_GATE_REVIEW_REQUIRED"),
            )

        contract = _first_value(row, "contract_symbol", "option_symbol", "recommended_contract", default="")
        live = _live_option_data_from_row(row)
        if not live:
            live = get_live_option_data(ticker, str(contract))
        if not live or not isinstance(live, dict):
            return _preserve(row, "CONTRACT_REPAIR", "LIVE_CONTRACT_DATA_MISSING")

        bid = float(live.get("bid", 0) or 0)
        ask = float(live.get("ask", 0) or 0)
        delta = float(live.get("delta", 0) or 0)
        abs_delta = abs(delta)
        iv = _normalise_ratio(live.get("iv", 0) or 0)
        iv_rank = float(live.get("iv_rank", 50) or 50)
        if ask <= 0 or bid < 0:
            return _preserve(row, "CONTRACT_REPAIR", "LIVE_CONTRACT_QUOTE_INVALID")
        mid = (bid + ask) / 2.0
        spread_pct = (ask - bid) / max(ask, 0.001)
        warnings = []
        penalty = 1.0
        conviction_override = _is_conviction_override(row)

        campaign = _s(row, "campaign_verdict")
        execution = _s(row, "execution_verdict")
        if not campaign:
            if morning_perm in ("GO", "GO_LIMIT"):
                campaign = "READY_EXECUTE"
                execution = execution or "BUY_NOW"
            elif morning_perm == "PROBE":
                campaign = "READY_PROBE"
                execution = execution or "BUY_SMALL"
            else:
                return _preserve(row, "MANUAL_REVIEW", "CAMPAIGN_VERDICT_MISSING")
        if campaign == "REJECT" or execution == "SKIP":
            return _preserve(row, "BLOCK", "UPSTREAM_VETO")

        # GATE-01: Spread
        if spread_pct > cfg_gate.SPREAD_MAX:
            log.info("[%s] CONTRACT_REPAIR COST_DESTRUCTION spread=%.1f%%", ticker, spread_pct * 100)
            return _preserve(row, "CONTRACT_REPAIR", "COST_DESTRUCTION", warnings=["WARN_WIDE_SPREAD"])
        if spread_pct > cfg_gate.SPREAD_FULL:
            warnings.append("WARN_WIDE_SPREAD")
            penalty *= 0.5
            log.info("[%s] WARN_WIDE_SPREAD spread=%.1f%% -> 0.5x size", ticker, spread_pct * 100)

        # GATE-02: Delta. Use absolute delta so PUT contracts are not falsely discarded.
        if abs_delta < cfg_gate.DELTA_HARD_MIN or abs_delta > cfg_gate.DELTA_HARD_MAX:
            log.info("[%s] CONTRACT_REPAIR DELTA_EXTREME delta=%.2f", ticker, delta)
            return _preserve(row, "CONTRACT_REPAIR", "DELTA_EXTREME", warnings=warnings)
        if not (cfg_gate.DELTA_SOFT_MIN <= abs_delta <= cfg_gate.DELTA_SOFT_MAX):
            warnings.append("WARN_DELTA_OUTSIDE_CORE")
            penalty *= 0.75
            log.info("[%s] WARN_DELTA_OUTSIDE_CORE delta=%.2f -> 0.75x", ticker, delta)

        # GATE-03: IV, advisory only.
        if iv > cfg_gate.IV_EXTREME:
            warnings.append("WARN_IV_EXTREME")
            penalty *= 0.5
            log.info("[%s] WARN_IV_EXTREME iv=%.1f%% -> 0.5x", ticker, iv * 100)
        elif iv > cfg_gate.IV_ELEVATED:
            if iv_rank > 80:
                warnings.append("WARN_IV_ELEVATED")
                penalty *= 0.75
                log.info("[%s] WARN_IV_ELEVATED iv=%.1f%% rank=%.0f -> 0.75x", ticker, iv * 100, iv_rank)
            else:
                log.info("[%s] iv=%.1f%% iv_rank=%.0f - normal for this name, no penalty", ticker, iv * 100, iv_rank)

        # Spot price
        spot = _f(row, "signal_price")
        if spot <= 0:
            spot = _f(row, "current_price") or _f(row, "underlying_price") or _f(row, "live_price")
        if spot <= 0:
            return _preserve(row, "MANUAL_REVIEW", "UNDERLYING_PRICE_MISSING", warnings=warnings)
        put_wall = _f(row, "put_wall")
        gamma_flip = _f(row, "gamma_flip")
        rcs_label = _s(row, "rcs_label")

        # GATE-04: Runway, soft penalty.
        runway_pct = 0.0
        runway_source = "NONE"
        if put_wall > 0:
            runway_pct = abs((spot - put_wall) / spot)
            runway_source = "PUT_WALL"
        elif gamma_flip > 0 and spot > gamma_flip:
            runway_pct = abs((spot - gamma_flip) / spot)
            runway_source = "GAMMA_FLIP_PROXY"
        if runway_source != "NONE" and runway_pct < cfg_gate.MIN_RUNWAY_PCT:
            warnings.append("WARN_LOW_RUNWAY")
            penalty *= 0.5
            log.info("[%s] WARN_LOW_RUNWAY runway=%.2f%% -> 0.5x", ticker, runway_pct * 100)

        # GATE-05: Gamma flip, trending-day bypass.
        gamma_state = "UNKNOWN"
        if gamma_flip > 0:
            gamma_state = "ABOVE_FLIP" if spot > gamma_flip else "BELOW_FLIP"
        if gamma_state == "ABOVE_FLIP":
            if rcs_label not in cfg_gate.TRENDING_REGIMES:
                warnings.append("WARN_ABOVE_GAMMA")
                penalty *= 0.75
                log.info("[%s] WARN_ABOVE_GAMMA rcs=%s -> 0.75x", ticker, rcs_label)
            else:
                log.info("[%s] Above gamma flip, trending regime %s - bypass", ticker, rcs_label)

        # GATE-06: Target move vs runway.
        target_move_pct = (mid * cfg_gate.TARGET_GAIN_MULTIPLE) / max(spot, 0.001)
        if runway_source != "NONE" and runway_pct > 0 and target_move_pct > runway_pct:
            if conviction_override:
                warnings.append("WARN_TARGET_EXCEEDS_RUNWAY_OVERRIDE")
                log.info(
                    "[%s] target_move=%.2f%% > runway=%.2f%% - conviction override",
                    ticker,
                    target_move_pct * 100,
                    runway_pct * 100,
                )
            else:
                warnings.append("WARN_TARGET_EXCEEDS_RUNWAY")
                penalty *= 0.5
                log.info(
                    "[%s] WARN_TARGET_EXCEEDS_RUNWAY need=%.2f%% runway=%.2f%% -> 0.5x",
                    ticker,
                    target_move_pct * 100,
                    runway_pct * 100,
                )

        penalty = max(round(penalty, 4), 0.25)

        if campaign == "READY_EXECUTE":
            if execution == "BUY_NOW" and penalty >= 0.75 and not warnings:
                final_action = "BUY_NOW"
            elif execution in ("BUY_NOW", "BUY_SMALL"):
                final_action = cfg_gate.PROBE_SIZE_LABEL
            else:
                final_action = cfg_gate.PROBE_SIZE_LABEL if conviction_override else "MANUAL_REVIEW"
        elif campaign == "READY_PROBE":
            if execution in ("BUY_SMALL", "WAIT_RETEST"):
                final_action = cfg_gate.PROBE_SIZE_LABEL
            else:
                final_action = cfg_gate.PROBE_SIZE_LABEL if conviction_override else "MANUAL_REVIEW"
        elif campaign == "WATCH":
            final_action = cfg_gate.PROBE_SIZE_LABEL if (conviction_override and not warnings) else "MANUAL_REVIEW"
        else:
            log.info("[%s] MANUAL_REVIEW campaign=%s execution=%s", ticker, campaign, execution)
            final_action = "MANUAL_REVIEW"

        log.info(
            "[%s] %-15s spread=%.1f%% d=%.2f iv=%.1f%%(r%.0f) run=%.2f%% tgt=%.2f%% g=%s pen=%.2f conv=%s warn=%s",
            ticker,
            final_action,
            spread_pct * 100,
            delta,
            iv * 100,
            iv_rank,
            runway_pct * 100,
            target_move_pct * 100,
            gamma_state,
            penalty,
            conviction_override,
            warnings or ["NONE"],
        )

        return {
            **row,
            "final_action": final_action,
            "gate_reason": "OK",
            "gate_warnings": ",".join(warnings) if warnings else "",
            "gate_size_penalty": penalty,
            "gate_conviction_override": conviction_override,
            "live_bid": round(bid, 4),
            "live_ask": round(ask, 4),
            "live_mid": round(mid, 4),
            "live_spread_pct": round(spread_pct, 4),
            "live_delta": round(delta, 4),
            "live_iv": round(iv, 4),
            "live_iv_rank": round(iv_rank, 1),
            "runway_pct": round(runway_pct, 4),
            "runway_source": runway_source,
            "gamma_state": gamma_state,
            "target_move_pct": round(target_move_pct, 4),
            "gate_version": GATE_VERSION,
            "gate_timestamp_utc": ts,
            "preservation_gate": True,
        }
    except Exception as exc:
        log.exception("[%s] execution_gate raised: %s", ticker, exc)
        return _preserve(row, "MANUAL_REVIEW", f"GATE_EXCEPTION:{type(exc).__name__}")


def run_execution_gate(signals, run_id, output_dir):
    if not signals:
        return [], {"status":"NO_INPUT","run_id":run_id}
    log.info("="*60)
    log.info("AVSHUNTER EXECUTION GATE v%s — Run: %s", GATE_VERSION, run_id)
    log.info("Signals in: %d", len(signals))
    log.info("="*60)
    gated = [execution_gate(s) for s in signals]
    counts={}; reasons={}; warn_freq={}
    for s in gated:
        a=s.get("final_action","UNKNOWN"); r=s.get("gate_reason","")
        counts[a]=counts.get(a,0)+1; reasons[r]=reasons.get(r,0)+1
        for w in str(s.get("gate_warnings","")).split(","):
            if w: warn_freq[w]=warn_freq.get(w,0)+1
    actionable = [s for s in gated if s.get("final_action") in ("BUY_NOW","BUY_SMALL")]
    preserved_actions = {"BUY_NOW", "BUY_SMALL", "MANUAL_REVIEW", "CONTRACT_REPAIR"}
    preserved = [s for s in gated if s.get("final_action") in preserved_actions]
    log.info("Actions: %s  Reasons: %s  Warnings: %s  Actionable: %d/%d",
             counts, reasons, warn_freq, len(actionable), len(gated))
    summary = {"run_id":run_id,"gate_version":GATE_VERSION,
               "completed_at":datetime.now(timezone.utc).isoformat(),
               "signals_in":len(signals),"signals_out":len(actionable),"signals_preserved":len(preserved),
               "action_counts":counts,"reason_counts":reasons,
               "warning_frequency":warn_freq,
               "actionable_rate":round(len(actionable)/max(len(gated),1),4)}
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir/f"execution_gated_{run_id}.csv", gated)
    summary["gated_csv"] = str(output_dir/f"execution_gated_{run_id}.csv")
    if actionable:
        _write_csv(output_dir/f"execution_actionable_{run_id}.csv", actionable)
        summary["actionable_csv"] = str(output_dir/f"execution_actionable_{run_id}.csv")
    sp = output_dir/f"execution_gate_summary_{run_id}.json"
    try:
        sp.write_text(json.dumps(summary, indent=2, default=str))
    except Exception as e:
        log.warning("Failed to write summary: %s", e)
    log.info("="*60)
    log.info("EXECUTION GATE COMPLETE — %d actionable", len(actionable))
    log.info("="*60)
    return gated, summary


def _write_csv(path, rows):
    if not rows: return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    try:
        with open(path,"w",newline="",encoding="utf-8") as f:
            w = csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        log.info("Written %d rows -> %s", len(rows), path)
    except Exception as e:
        log.error("Failed to write %s: %s", path, e)

def _read_csv(path):
    path = Path(path)
    if not path.exists(): return []
    try:
        with open(path,newline="",encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.error("Failed to read %s: %s", path, e); return []


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="AVSHUNTER Execution Gate v1.1")
    p.add_argument("--input", required=True)
    p.add_argument("--run_id", required=True)
    p.add_argument("--out_dir", required=True)
    args = p.parse_args()
    sigs = _read_csv(args.input)
    if not sigs:
        print("No signals — check input path.")
    else:
        gated, summary = run_execution_gate(sigs, args.run_id, Path(args.out_dir))
        print(f"\nExecution Gate v{GATE_VERSION} Complete")
        print(f"  Signals in:  {summary['signals_in']}")
        print(f"  Actionable:  {summary['signals_out']}")
        print(f"  Actions:     {summary['action_counts']}")
        print(f"  Warnings:    {summary['warning_frequency']}")
