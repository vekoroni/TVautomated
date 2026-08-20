"""
AVSHUNTER Pipeline Interpreter — Component 9
Intelligence Lab Reconciliation Layer

Standalone module. Zero imports from pipeline_interpreter_engine,
pipeline_interpreter_commands, or any other interpreter module.
Standard library only: csv, json, pathlib, datetime.
"""
import csv
import json
from pathlib import Path
from datetime import datetime

# ── Tolerance constants ───────────────────────────────────────────────────────
IVP_TOLERANCE     = 5.0    # ±5 IVP points before flagging
PREMIUM_TOLERANCE = 0.10   # ±10% of pipeline premium before flagging

# ── Lab CSV column → Pipeline CSV column mapping ──────────────────────────────
# Left: Lab column name.  Right: pipeline row key.
FIELD_MAP = {
    "Direction":     "direction",
    "Verdict":       "eil_v3_verdict",
    "IVP":           "ivp",
    "Strike":        "preferred_strike",
    "EV":            "ev_score",
    "WBS_Grade":     "wbs_grade",
    "Priority_Rank": "triage_rank",
    "Premium_Mid":   "premium",
}

# ── Severity rules per field ──────────────────────────────────────────────────
# FLAG = surfaces in RISK ASSESSMENT + EVIDENCE QUALITY
# WARN = surfaces in EVIDENCE QUALITY only
FIELD_SEVERITY = {
    "Direction":     "FLAG",
    "Verdict":       "FLAG",
    "IVP":           "WARN",
    "Strike":        "FLAG",
    "EV":            "WARN",
    "WBS_Grade":     "WARN",
    "Priority_Rank": "WARN",
    "Premium_Mid":   "WARN",
}

# ── Fields surfaced in LAB_CONTEXT block ─────────────────────────────────────
_LAB_CONTEXT_FIELDS = [
    "Verdict", "Lab_Verdict", "Direction", "Conv_Score",
    "Strike", "Premium_Mid", "RR", "EV", "IVP", "IVP_Label",
    "Priority_Rank", "Priority_Score", "WBS_Grade", "EIL_Verdict",
    "Exec_Category", "Vol_State", "Run_ID",
]


# ── §3.2  load_lab_export ─────────────────────────────────────────────────────

# ── lab_triage_view field → canonical lab row field mapping ──────────────────
# lab_triage_view_*.csv uses lowercase field names; normalise to canonical form
_LTV_FIELD_MAP = {
    "ticker":           "Ticker",
    "direction":        "Direction",
    "canonical_direction": "Direction",  # fallback if direction empty
    "lab_verdict":      "Verdict",
    "lab_rank":         "Priority_Rank",
    "priority_score":   "Priority_Score",
    "contract_symbol":  "Contract",
    "morning_selected_contract_symbol": "Contract",
    "alternative_contract_1": "Alternative_Contract_1",
    "contract_repair_status": "Contract_Repair_Status",
    "contract_repair_reason": "Contract_Repair_Reason",
    "strike":           "Strike",
    "premium_mid":      "Premium_Mid",
    "ev_predicted":     "EV",
    "run_id":           "Run_ID",
    "execution_category": "Exec_Category",
    "lab_tradeable":    "Lab_Verdict",
    "dte":              "dte",
}


def _normalise_lab_triage_view_row(r: dict) -> dict:
    """
    Remap a lab_triage_view row to canonical lab export field names
    so all downstream functions (get_lab_row, validate_lab_field_alignment)
    work without modification.
    """
    out: dict = {}
    for src, dst in _LTV_FIELD_MAP.items():
        v = r.get(src, "")
        if v and not out.get(dst):  # first non-empty wins
            out[dst] = str(v).strip()
    # Ticker must always be uppercase
    if out.get("Ticker"):
        out["Ticker"] = out["Ticker"].upper()
    # Preserve all original fields too (for build_lab_context_block)
    for k, v in r.items():
        if k not in out:
            out[k] = v
    return out


def load_lab_export(ma_lab_dir: Path) -> tuple[list[dict], str]:
    """
    Find and load the most recent avshunter_signals_*.csv from
    MA_Inputs/lab_export/.  If none found, fall back to lab_triage_view_*.csv
    in MA_Inputs/pipeline_outputs/ (which is always present after --eod sync).
    Normalises Ticker column to uppercase on load.
    Returns (rows, filename). Returns ([], "") if none found.
    """
    if not ma_lab_dir.exists():
        return [], ""

    candidates = sorted(
        ma_lab_dir.glob("avshunter_signals_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    # GAP 4 fix: lab_export/ is empty — search pipeline_outputs/ for avshunter_signals_*.csv first
    # (all sync files land in pipeline_outputs/, not lab_export/)
    if not candidates:
        pipeline_outputs = ma_lab_dir.parent / "pipeline_outputs"

        # Priority 1: avshunter_signals_*.csv in pipeline_outputs (true lab export)
        if pipeline_outputs.exists():
            sig_candidates = sorted(
                pipeline_outputs.glob("avshunter_signals_*.csv"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if sig_candidates:
                path = sig_candidates[0]
                rows: list[dict] = []
                try:
                    with open(path, "r", encoding="utf-8-sig", newline="") as f:
                        for r in csv.DictReader(f):
                            r["Ticker"] = str(r.get("Ticker", "")).strip().upper()
                            rows.append(r)
                    return rows, path.name
                except (OSError, csv.Error):
                    pass  # fall through to lab_triage_view fallback

        # Priority 2: lab_triage_view_*.csv — WARNING: same file used as pipeline source.
        # This will produce false CONFIRMED counts. Only use if no avshunter_signals found.
        ltv_candidates = sorted(
            pipeline_outputs.glob("lab_triage_view_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ) if pipeline_outputs.exists() else []
        if ltv_candidates:
            path = ltv_candidates[0]
            rows: list[dict] = []
            try:
                with open(path, "r", encoding="utf-8-sig", newline="") as f:
                    for r in csv.DictReader(f):
                        rows.append(_normalise_lab_triage_view_row(r))
            except (OSError, csv.Error):
                return [], ""
            return rows, f"LAB_TRIAGE_VIEW_FALLBACK:{path.name}"
        return [], ""

    path = candidates[0]
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                # Ticker normalisation happens here only — never mutated elsewhere
                r["Ticker"] = str(r.get("Ticker", "")).strip().upper()
                rows.append(r)
    except (OSError, csv.Error):
        return [], ""

    return rows, path.name


# ── §3.3  reconcile_universes ─────────────────────────────────────────────────

def reconcile_universes(
    lab_rows: list[dict],
    interpreter_tickers: list[str],
) -> dict:
    """
    Three-way comparison between Lab export and Interpreter universe.
    interpreter_tickers: list of uppercase ticker strings from pipeline rows.
    Returns dict with all three lists plus summary counts.
    """
    lab_set    = {r["Ticker"] for r in lab_rows if r.get("Ticker")}
    interp_set = {t.upper().strip() for t in interpreter_tickers if t}

    confirmed   = sorted(lab_set & interp_set)
    lab_only    = sorted(lab_set - interp_set)
    interp_only = sorted(interp_set - lab_set)

    return {
        "confirmed":         confirmed,
        "lab_only":          lab_only,
        "interp_only":       interp_only,
        "confirmed_count":   len(confirmed),
        "lab_only_count":    len(lab_only),
        "interp_only_count": len(interp_only),
    }


# ── §3.4  get_lab_row ────────────────────────────────────────────────────────

def get_lab_row(lab_rows: list[dict], ticker: str) -> dict | None:
    """
    Return the Lab row for a specific ticker, or None.
    Called by /ticker and /story to inject Lab context into prompts.
    """
    ticker = ticker.upper().strip()
    for r in lab_rows:
        if r.get("Ticker") == ticker:
            return r
    return None


# ── §3.5  check_run_id_alignment ─────────────────────────────────────────────

def check_run_id_alignment(
    lab_rows: list[dict],
    pipeline_run_id: str,
) -> dict:
    """
    Verify the Lab export Run_ID matches the pipeline run being interpreted.
    Lab and pipeline must share the same Run_ID for reconciliation to be valid.
    Returns dict: { match: bool, lab_run_id: str, pipeline_run_id: str }
    """
    if not lab_rows:
        return {
            "match":           False,
            "lab_run_id":      "UNKNOWN",
            "pipeline_run_id": str(pipeline_run_id),
        }

    lab_run_id = str(lab_rows[0].get("Run_ID", "")).strip()
    match      = lab_run_id == str(pipeline_run_id).strip()

    return {
        "match":           match,
        "lab_run_id":      lab_run_id,
        "pipeline_run_id": str(pipeline_run_id),
    }


# ── §3.6  validate_lab_field_alignment ───────────────────────────────────────

def validate_lab_field_alignment(
    lab_row: dict,
    pipeline_row: dict,
    ticker: str,
) -> list[dict]:
    """
    Field-level comparison for a single ticker.
    Returns list of conflict dicts — empty list means fully aligned.
    Each conflict: { field, lab_value, pipeline_value, severity }
    """
    conflicts: list[dict] = []

    for lab_field, pipe_field in FIELD_MAP.items():
        lab_val  = str(lab_row.get(lab_field,  "")).strip()
        pipe_val = str(pipeline_row.get(pipe_field, "")).strip()

        # Skip if either side is empty
        if not lab_val or not pipe_val:
            continue

        # Numeric tolerance check — IVP and Premium_Mid
        if lab_field in ("IVP", "Premium_Mid"):
            try:
                lv = float(lab_val)
                pv = float(pipe_val)
                if lab_field == "IVP":
                    tol = IVP_TOLERANCE
                else:
                    tol = abs(pv) * PREMIUM_TOLERANCE  # ±10% of pipeline value
                if abs(lv - pv) <= tol:
                    continue
            except ValueError:
                pass  # fall through to string comparison

        # Direction normalisation — PUT/LONG_PUT and CALL/LONG_CALL are equivalent
        if lab_field == "Direction":
            def _dir_norm(s: str) -> str:
                s = s.upper()
                if "PUT" in s:
                    return "PUT"
                if "CALL" in s:
                    return "CALL"
                return s
            if _dir_norm(lab_val) == _dir_norm(pipe_val):
                continue

        # General string comparison (case-insensitive)
        if lab_val.upper() == pipe_val.upper():
            continue

        conflicts.append({
            "field":          lab_field,
            "lab_value":      lab_val,
            "pipeline_value": pipe_val,
            "severity":       FIELD_SEVERITY.get(lab_field, "WARN"),
        })

    return conflicts


# ── §3.7  build_lab_alignment_block ──────────────────────────────────────────

def build_lab_alignment_block(
    reconciliation: dict,
    lab_filename: str,
    run_id_check: dict = None,
) -> str:
    """
    Build LAB_ALIGNMENT text block for injection into triage prompt.
    """
    lines = [f"LAB_ALIGNMENT ({lab_filename}):"]

    if run_id_check:
        status = (
            "MATCH"
            if run_id_check["match"]
            else "MISMATCH — STALE_LAB_DATA WARNING"
        )
        lines.append(f"  run_id_check: {status}")
        lines.append(f"    lab_run_id:      {run_id_check['lab_run_id']}")
        lines.append(f"    pipeline_run_id: {run_id_check['pipeline_run_id']}")

    lines.append(
        f"  confirmed:    {reconciliation.get('confirmed_count', 0)} tickers"
        f" in both Lab and Interpreter"
    )
    lines.append(
        f"  lab_only:     {reconciliation.get('lab_only_count', 0)} tickers"
        f" in Lab not surfaced by Interpreter"
    )
    lines.append(
        f"  interp_only:  {reconciliation.get('interp_only_count', 0)} tickers"
        f" — REVIEW REQUIRED"
    )

    interp_only = reconciliation.get("interp_only", [])
    if interp_only:
        lines.append(f"    {', '.join(interp_only)}")

    return "\n".join(lines)


# ── §3.8  build_lab_context_block ────────────────────────────────────────────

def build_lab_context_block(lab_row: dict, ticker: str) -> str:
    """
    Build a LAB_CONTEXT block for injection into /ticker and /story prompts.
    Surfaces the key Lab fields alongside the pipeline row.
    """
    ticker = ticker.upper().strip()

    if not lab_row:
        return f"LAB_CONTEXT_{ticker}: NOT_IN_LAB_EXPORT — LAB_NOT_CONFIRMED"

    lines = [f"LAB_CONTEXT_{ticker}:"]
    for field in _LAB_CONTEXT_FIELDS:
        val = lab_row.get(field, "")
        if str(val).strip() not in ("", "nan", "None"):
            lines.append(f"  {field}: {val}")

    return "\n".join(lines)


# ── §3.9  build_field_conflict_block ─────────────────────────────────────────

def build_field_conflict_block(conflicts: list[dict], ticker: str) -> str:
    """
    Format field-level conflicts for injection into /ticker and /story prompts.
    """
    ticker = ticker.upper().strip()

    if not conflicts:
        return f"LAB_FIELD_CONFLICTS_{ticker}: NONE — fully aligned"

    lines = [f"LAB_FIELD_CONFLICTS_{ticker} ({len(conflicts)} conflicts):"]
    for c in conflicts:
        lines.append(
            f"  {c['field']:<16}"
            f" | Lab: {c['lab_value']:<20}"
            f" | Pipeline: {c['pipeline_value']:<20}"
            f" | {c['severity']}"
        )

    flag_count = sum(1 for c in conflicts if c["severity"] == "FLAG")
    if flag_count:
        lines.append(
            f"  {flag_count} FLAG-level conflict(s) — surface in RISK ASSESSMENT"
        )

    return "\n".join(lines)

# CONTRACT-REPAIR-ALT-001: Lab reconciliation preserves repair alternatives.
