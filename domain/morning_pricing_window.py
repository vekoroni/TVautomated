"""Pure start-time guard: Morning prices at any time during XNYS market hours.

Outside the preferred window the start is labelled, not refused. Outside market hours it
fails closed. No requests, scheduling or data writes.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds

POLICY_PATH = Path(__file__).resolve().parents[1] / "config/morning_pricing_policy_v1.json"


class MorningPricingWindowClosed(RuntimeError):
    """No Morning pricing/publication may start for this invocation."""


def require_morning_pricing_start(execution_mode: str, decision_clock_utc: datetime,
                                  *, policy_path: Path = POLICY_PATH) -> dict:
    mode = str(execution_mode or "").strip().upper()
    if mode not in {"PREOPEN_THESIS_CHECK", "POSTOPEN_CONTRACT_REFRESH"}:
        raise ValueError(f"unsupported Morning execution_mode: {mode}")
    if decision_clock_utc.tzinfo is None or decision_clock_utc.utcoffset() is None:
        raise ValueError("Morning pricing guard requires an aware decision clock")
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8-sig"))
    if (policy["version"] != "morning_pricing_policy_v2"
            or policy["timezone"] != "America/New_York"
            or policy["guard_scope"] != "PRICING_START_NOT_BATCH_COMPLETION"
            or policy["market_hours_basis"] != "XNYS_REGULAR_SESSION_OPEN_TO_CLOSE_INCLUDING_EARLY_CLOSES"
            or policy["outside_preferred_window_action"] != "PRICE_AND_LABEL"
            or policy["outside_market_hours_action"] != "STOP_BEFORE_PRICING"):
        raise ValueError("unsupported Morning pricing policy")
    def minute(value):
        parsed = datetime.strptime(value, "%H:%M")
        return parsed.hour * 60 + parsed.minute
    first = minute(policy["preferred_start_et"])
    last = minute(policy["preferred_last_start_minute_et"])
    if not first <= last:
        raise ValueError("Morning preferred window must not cross midnight")
    now_et = decision_clock_utc.astimezone(ZoneInfo(policy["timezone"]))
    metadata = {"policy_version": policy["version"], "observed_at_et": now_et.isoformat(),
                "observed_at_utc": decision_clock_utc.astimezone(timezone.utc).isoformat(),
                "guard_scope": policy["guard_scope"]}
    if mode == "PREOPEN_THESIS_CHECK":
        return {**metadata, "state": "NOT_APPLICABLE_PREOPEN"}
    # ACK 14 Nov 2026: any start during market hours is priced. The preferred
    # window is a label on the run, never a refusal. Only a start outside the
    # regular session (weekend, holiday, before the open, at or after the close,
    # early closes included) stops before pricing.
    if not is_xnys_session(now_et.date()):
        reason = "NOT_XNYS_SESSION"
    else:
        open_utc, close_utc = session_bounds(now_et.date())
        if decision_clock_utc < open_utc:
            reason = "BEFORE_MARKET_OPEN"
        elif decision_clock_utc >= close_utc:
            reason = "AT_OR_AFTER_MARKET_CLOSE"
        else:
            clock_minute = now_et.hour * 60 + now_et.minute
            state = ("BEFORE_PREFERRED_WINDOW" if clock_minute < first
                     else "AFTER_PREFERRED_WINDOW" if clock_minute > last else "DEFAULT_WINDOW")
            return {**metadata, "state": state,
                    "preferred_window_et": f"{policy['preferred_start_et']}-{policy['preferred_last_start_minute_et']}"}
    raise MorningPricingWindowClosed(
        f"MORNING_PRICING_WINDOW_CLOSED:{reason}; observed={now_et.isoformat()}; "
        "required=XNYS market hours (open to close, early closes included). "
        "No pricing or handoff started; do not reuse an old Morning result as current."
    )
