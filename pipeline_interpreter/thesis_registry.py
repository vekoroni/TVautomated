"""
AVSHUNTER Pipeline Interpreter — Thesis Registry
Cross-session thesis lifecycle management.
Zero dependency on the Anthropic API — pure file I/O.
"""
import json
from datetime import date, datetime
from pathlib import Path

BASE_DIR     = Path(__file__).parent
MA_INPUTS    = BASE_DIR / "MA_Inputs"
REGISTRY_DIR = MA_INPUTS / "thesis_registry"

# ── Internal helpers ──────────────────────────────────────────────────────────

def _registry_path(ticker: str) -> Path:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    return REGISTRY_DIR / f"{ticker.upper()}_thesis_registry.json"

def _load_registry(ticker: str) -> dict:
    path = _registry_path(ticker)
    if not path.exists():
        return {"theses": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"theses": []}

def _save_registry(ticker: str, data: dict) -> None:
    """Atomic write via temp file to prevent corruption."""
    path = _registry_path(ticker)
    tmp  = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)

def _direction_short(direction: str) -> str:
    """Map full direction strings to short badge form used in thesis_id."""
    d = direction.upper()
    if "PUT" in d or "BEAR" in d:
        return "PUT"
    if "CALL" in d or "BULL" in d:
        return "CALL"
    return d[:4]

def _strike_lower(strike_zone: str) -> str:
    """Extract lower bound number from a strike zone string ('72-73' → '72', '540' → '540')."""
    return str(strike_zone).replace(" ", "").split("-")[0]

def _build_thesis_id(ticker: str, direction: str, strike_zone: str, date_str: str) -> str:
    # e.g. WFC_PUT_72_20260522
    return f"{ticker.upper()}_{_direction_short(direction)}_{_strike_lower(strike_zone)}_{date_str}"

# ── Public API ────────────────────────────────────────────────────────────────

def get_active_thesis(ticker: str) -> dict | None:
    """Return the active thesis dict for ticker, or None if no active thesis exists."""
    data = _load_registry(ticker)
    for t in data["theses"]:
        if t.get("active"):
            return t
    return None


def create_thesis(
    ticker: str,
    direction: str,
    horizon: str,
    strike_zone: str,
    pipeline_run_id: str,
    kill_switch_level: float,
    probe_trigger: float,
    armed_trigger: float,
) -> str:
    """
    Create a new thesis entry for ticker. Returns thesis_id.
    Any previously active thesis must be closed by the caller before calling this —
    this function does not automatically close existing active theses.
    """
    today     = date.today().strftime("%Y%m%d")
    ts        = datetime.now().strftime("%Y%m%d_%H%M")
    thesis_id = _build_thesis_id(ticker, direction, strike_zone, today)

    entry = {
        "thesis_id":            thesis_id,
        "ticker":               ticker.upper(),
        "direction":            direction,
        "horizon":              horizon,
        "strike_zone":          strike_zone,
        "first_run_date":       date.today().strftime("%Y-%m-%d"),
        "first_run_ts":         ts,
        "latest_story_ts":      ts,
        "latest_story_path":    "",
        "state_chain":          [],
        "kill_switch_level":    float(kill_switch_level),
        "probe_trigger":        float(probe_trigger),
        "armed_trigger":        float(armed_trigger),
        "kill_switch_breached": False,
        "pipeline_run_id":      pipeline_run_id,
        "active":               True,
    }

    data = _load_registry(ticker)
    data["theses"].append(entry)
    _save_registry(ticker, data)
    return thesis_id


def update_thesis(
    ticker: str,
    thesis_id: str,
    ts: str,
    verdict: str,
    trade_state: str,
    trigger_proximity: str,
    story_path: str,
    latest_story_path: str,
) -> None:
    """Append a new state_chain node and update latest_story_ts / latest_story_path."""
    data = _load_registry(ticker)
    for t in data["theses"]:
        if t["thesis_id"] == thesis_id:
            node = {
                "ts":                ts,
                "verdict":           verdict,
                "trade_state":       trade_state,
                "trigger_proximity": trigger_proximity,
                "story_path":        story_path,
            }
            t["state_chain"].append(node)
            t["latest_story_ts"]   = ts
            t["latest_story_path"] = latest_story_path
            break
    _save_registry(ticker, data)


def close_thesis(ticker: str, thesis_id: str, reason: str) -> None:
    """Set active=False, record closure reason and timestamp."""
    data = _load_registry(ticker)
    for t in data["theses"]:
        if t["thesis_id"] == thesis_id:
            t["active"]         = False
            t["closure_reason"] = reason
            t["closure_ts"]     = datetime.now().strftime("%Y%m%d_%H%M")
            if reason == "kill_switch_breached":
                t["kill_switch_breached"] = True
            break
    _save_registry(ticker, data)


def get_latest_story_path(ticker: str) -> str | None:
    """
    Return latest_story_path from the active thesis, or None.
    This is the Option B cross-session retrieval mechanism used by /update.
    """
    thesis = get_active_thesis(ticker)
    if thesis and thesis.get("latest_story_path"):
        return thesis["latest_story_path"]
    return None


def get_carry_forward_tickers() -> list[str]:
    """Return sorted list of tickers that have at least one active thesis."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    tickers = []
    for path in sorted(REGISTRY_DIR.glob("*_thesis_registry.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if any(t.get("active") for t in data.get("theses", [])):
                ticker = path.name.replace("_thesis_registry.json", "")
                tickers.append(ticker)
        except (json.JSONDecodeError, OSError):
            continue
    return tickers


def should_close_thesis(ticker: str, current_price: float) -> bool:
    """
    Return True if current_price has breached kill_switch_level for the active thesis.
    PUT/BEAR theses: breached if price moves UP to or above kill_switch_level.
    CALL/BULL theses: breached if price moves DOWN to or below kill_switch_level.
    """
    thesis = get_active_thesis(ticker)
    if not thesis or current_price <= 0:
        return False
    ks = float(thesis.get("kill_switch_level", 0))
    if ks <= 0:
        return False
    direction = thesis.get("direction", "").upper()
    if "PUT" in direction or "BEAR" in direction:
        return current_price >= ks
    # CALL / BULL — kill switch is below
    return current_price <= ks


# ── §Phantom 4: Evening Baseline + Morning Delta Engine ──────────────────────

_BASELINE_FIELDS = [
    "crowd_stage", "p_trigger_hit", "kill_switch_warning",
    "edge_quality", "garch_status", "entry_quality",
    "junior_section_statuses", "catalyst_override",
    "highest_severity",
]

_DELTA_THRESHOLDS = {
    "MINIMAL":     (0, 2),
    "MODERATE":    (3, 5),
    "SIGNIFICANT": (6, float("inf")),
}

BASELINE_DIR = MA_INPUTS / "thesis_baselines"


def _baseline_path(ticker: str) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    return BASELINE_DIR / f"{ticker.upper()}_evening_baseline.json"


def save_evening_baseline(ticker: str, snapshot: dict) -> bool:
    """
    Persist the evening interpreter snapshot as the baseline for morning comparison.
    snapshot should contain the interpreter sidecar fields.
    Always write — if write fails, log ERROR and return False.
    Evening mode MUST always produce a baseline (never silently skip).
    """
    if not ticker or not snapshot:
        return False
    path = _baseline_path(ticker)
    payload = {
        "ticker":      str(ticker).upper(),
        "saved_at":    datetime.now().isoformat(),
        "mode":        "EVENING",
        "snapshot":    {k: snapshot.get(k) for k in _BASELINE_FIELDS if k in snapshot},
        "_all_fields": dict(snapshot),  # preserve full payload for debugging
    }
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except (OSError, json.JSONDecodeError) as e:
        print(f"  [BASELINE] ERROR: Failed to save baseline for {ticker}: {e}")
        return False


def load_evening_baseline(ticker: str) -> dict | None:
    """
    Load the last saved evening baseline for a ticker.
    Returns None if no baseline exists — callers must surface NO_BASELINE.
    """
    path = _baseline_path(ticker)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (OSError, json.JSONDecodeError):
        return None


def compute_morning_delta(
    ticker: str,
    morning_snapshot: dict,
) -> dict:
    """
    Compare morning interpreter snapshot against evening baseline.

    Delta classifications:
      MINIMAL     — 0-2 field changes; expected norm under stable conditions
      MODERATE    — 3-5 changes; worth reviewing before entry
      SIGNIFICANT — 6+ changes; investigate root cause upstream
      EXCEPTION   — Tier 1 change (crowd_stage, p_trigger, kill_switch_warning)
                    or rank shift >2; always surfaces in morning output

    Returns dict: { status, change_count, delta_fields, exception_fields,
                    baseline_ts, morning_ts, narrative }

    Architecture principle: MINIMAL delta is the expected norm.
    If SIGNIFICANT/EXCEPTION appears routinely, evening scoring is weak —
    investigate upstream, do not tune thresholds.
    """
    baseline_data = load_evening_baseline(ticker)

    if baseline_data is None:
        return {
            "status":          "NO_BASELINE",
            "change_count":    None,
            "delta_fields":    [],
            "exception_fields": [],
            "baseline_ts":     None,
            "morning_ts":      datetime.now().isoformat(),
            "narrative":       "NO_BASELINE — evening interpreter did not run or baseline was lost. "
                               "Surface explicitly — never treat as normal cold start.",
        }

    baseline_snap = baseline_data.get("snapshot", {})
    baseline_ts   = baseline_data.get("saved_at", "UNKNOWN")

    _TIER1_FIELDS = {"crowd_stage", "p_trigger_hit", "kill_switch_warning"}

    delta_fields: list[dict] = []
    exception_fields: list[str] = []

    for field in _BASELINE_FIELDS:
        ev_val = baseline_snap.get(field)
        am_val = morning_snapshot.get(field)

        # Skip if both sides are None/missing
        if ev_val is None and am_val is None:
            continue

        # Skip complex nested fields (section statuses) for change counting
        if isinstance(ev_val, dict) or isinstance(am_val, dict):
            continue

        if str(ev_val) != str(am_val):
            delta_fields.append({
                "field":    field,
                "evening":  ev_val,
                "morning":  am_val,
                "tier1":    field in _TIER1_FIELDS,
            })
            if field in _TIER1_FIELDS:
                exception_fields.append(field)

    change_count = len(delta_fields)

    # Classify
    if exception_fields:
        status = "EXCEPTION"
    elif change_count == 0:
        status = "MINIMAL"
    elif change_count <= 2:
        status = "MINIMAL"
    elif change_count <= 5:
        status = "MODERATE"
    else:
        status = "SIGNIFICANT"

    # Narrative
    if status == "NO_BASELINE":
        narrative = "NO_BASELINE"
    elif status == "EXCEPTION":
        narrative = (
            f"EXCEPTION delta — Tier 1 field change(s): {', '.join(exception_fields)}. "
            f"Review before any entry decision. Total changes: {change_count}."
        )
    elif status == "SIGNIFICANT":
        narrative = (
            f"SIGNIFICANT delta — {change_count} field changes. "
            "Investigate evening scoring quality upstream before entry."
        )
    elif status == "MODERATE":
        narrative = f"MODERATE delta — {change_count} field changes. Review before entry."
    else:
        narrative = f"MINIMAL delta — {change_count} change(s). Expected norm."

    return {
        "status":           status,
        "change_count":     change_count,
        "delta_fields":     delta_fields,
        "exception_fields": exception_fields,
        "baseline_ts":      baseline_ts,
        "morning_ts":       datetime.now().isoformat(),
        "narrative":        narrative,
    }
