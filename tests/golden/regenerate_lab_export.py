#!/usr/bin/env python3
"""
regenerate_lab_export.py — Python port of the Intelligence Lab's client-side
CSV export (intelligence-lab/static/index.html, function exportCSV() and its
helpers), driven off the same intelligence_lab.py:_load_run() payload the
browser receives as RUN_DATA.

WHY THIS EXISTS (Phase 0.2 of CLAUDE_CODE_TASK_lab_fix_sprint.md):
The real export is produced by JavaScript running in a browser after a human
clicks a button. That is not something the automated regression harness in
this sprint can invoke on every commit. This module is a line-for-line
translation of the JS column extractors so the same export can be regenerated
deterministically from the command line, for golden-file diffing across
fixes.

This is NOT the source of truth — the browser export is (see Phase 4.2 UAT,
which diffs this script's output against a real button click). Any
divergence between the two is itself a finding, not something to paper over
here.

USAGE
    python regenerate_lab_export.py <run_id> [--out PATH]

Reproduces the default, no-filter, no-interaction browser state:
  - filters.verdict/dir/camp/exec/eod/morning/optRoute = 'ALL'
  - showAuditRows = False   (isAuditOnlySignal rows excluded)
  - quickFilters.rr/ev = False
  - campaignViewMode = False
  - sortCol = 0 (priority_rank), sortDir = 1 (ascending)
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "intelligence-lab"))

_EMPTY = {"", "NONE", "N/A", "NA", "UNKNOWN", "NULL", "NAN", "UNROUTED"}


# ─────────────────────────────────────────────── JS helper ports (verbatim logic)

def clean_category(v):
    if v is None:
        return ""
    return re.sub(r"\s+", "_", str(v).strip().upper())


def first_signal_value(s, keys):
    """Port of firstSignalValue(s, keys) — static/index.html:1364-1371."""
    for k in keys:
        v = s.get(k)
        c = clean_category(v)
        if v is not None and str(v).strip() != "" and c not in _EMPTY:
            return v
    return ""


def get_opt(s, k):
    """Port of getOpt(s, k) — static/index.html:1085."""
    return s.get(f"opt__{k}") or s.get(k) or ""


def _parse_float(v, default=None):
    try:
        if v is None:
            return default
        s = str(v).strip()
        if s == "" or s.upper() in _EMPTY:
            return default
        return float(s)
    except Exception:
        return default


def get_ev(s):
    """Port of getEv(s) — static/index.html:1109-1125."""
    values = [
        s.get("ev2_ev_conf_adj"), s.get("eil__ev2_ev_conf_adj"),
        s.get("fd_ev_used"), s.get("eil__fd_ev_used"),
        s.get("ev_final"), s.get("eil__ev_final"),
        s.get("ev_net"), s.get("ev"),
    ]
    first_valid = 0.0
    seen = False
    for v in values:
        n = _parse_float(v)
        if n is None:
            continue
        if not seen:
            first_valid = n
            seen = True
        if abs(n) > 0:
            return n
    return first_valid


def get_ev_decision_hint(s):
    return clean_category(first_signal_value(s, [
        "ev2_decision_hint", "ev_decision_hint",
        "eil__ev2_decision_hint", "eil__ev_decision_hint",
        "fd_ev_decision_hint",
    ]))


def has_ev_avoid(s):
    hint = get_ev_decision_hint(s)
    status = clean_category(first_signal_value(s, ["ev_status", "ev2_status", "eil__ev_status"]))
    return hint == "AVOID" or status in ("AVOID", "FAIL", "NEGATIVE_EV")


def has_negative_option_rr(s):
    raw = first_signal_value(s, ["rr_options", "opt__rr_options", "option_rr", "rr"])
    if raw == "" or raw is None:
        return False
    rr = _parse_float(raw)
    return rr is not None and rr < 0


def final_lab_verdict(s):
    """Port of finalLabVerdict(s) — static/index.html:1190-1195."""
    verdict = clean_category(
        s.get("display_final_verdict") or s.get("lab_status") or
        s.get("lab_verdict") or s.get("sb_final_verdict") or "WAIT"
    )
    if has_negative_option_rr(s):
        return "NEGATIVE_RR"
    if verdict in ("GO", "GO_LIMIT", "PROBE", "EOD_EXEC") and has_ev_avoid(s):
        return "EOD_CAUTION"
    return verdict


_CAMPAIGN_MAP = {
    "GO": "READY_EXECUTE", "EOD_EXEC": "READY_EXECUTE", "GO_LIMIT": "READY_LIMIT",
    "PROBE": "READY_PROBE", "EOD_CAUTION": "EXECUTE_WITH_CAUTION", "ARMED": "ARMED",
    "CONTRACT_REPAIR": "CONTRACT_REPAIR", "WAIT": "WATCHLIST", "WATCHLIST": "WATCHLIST",
    "BLOCKED": "BLOCKED",
}


def display_campaign(s):
    v = final_lab_verdict(s)
    return s.get("display_campaign") or _CAMPAIGN_MAP.get(v) or s.get("sb_campaign") or "WATCHLIST"


_EXEC_MODE_MAP = {
    "GO": "BUY_NOW", "EOD_EXEC": "EOD_READY", "GO_LIMIT": "LIMIT_ENTRY",
    "PROBE": "PROBE_ENTRY", "EOD_CAUTION": "MANUAL_REVIEW", "ARMED": "WAIT_TRIGGER",
    "CONTRACT_REPAIR": "REPAIR_CONTRACT", "WAIT": "WAIT", "WATCHLIST": "WATCH_ONLY",
    "BLOCKED": "NO_TRADE",
}


def display_execution_mode(s):
    v = final_lab_verdict(s)
    return (s.get("display_execution_mode") or _EXEC_MODE_MAP.get(v) or
            s.get("sb_execution_mode") or s.get("execution_mode") or "WAIT")


def display_size(s):
    if s.get("position_size_display") or s.get("sb_position_size_display"):
        return s.get("position_size_display") or s.get("sb_position_size_display")
    v = final_lab_verdict(s)
    tradeable = s.get("lab_tradeable") is True or str(s.get("lab_tradeable")).lower() == "true"
    if not tradeable or v in ("ARMED", "WAIT", "WATCHLIST", "BLOCKED", "CONTRACT_REPAIR", "EOD_CAUTION"):
        return "0% - waiting"
    pct = s.get("sb_position_size_pct")
    return f"{pct}%" if pct not in (None, "") else "MANUAL"


def get_live_validation_state(s):
    return clean_category(first_signal_value(s, [
        "live_validation_state", "mv__live_validation_state",
        "mv_live_validation_state", "validation_state", "mv__validation_state",
    ]))


def get_thesis_validity_state(s):
    return clean_category(first_signal_value(s, [
        "thesis_validity_state", "mv__thesis_validity_state", "mv_thesis_validity_state",
    ]))


def get_morning_execution_permission(s):
    return clean_category(first_signal_value(s, [
        "display_morning_execution_permission", "morning_execution_permission",
        "mv__morning_execution_permission", "mv_morning_execution_permission",
        "mv_execution_permission", "mv__execution_permission",
    ]))


def get_morning_execution_route(s):
    return clean_category(first_signal_value(s, [
        "display_morning_execution_route", "morning_execution_route",
        "mv__morning_execution_route", "mv_morning_execution_route",
        "morning_execution_lane", "mv__morning_execution_lane",
    ])) or get_morning_execution_permission(s)


def get_morning_lab_alignment(s):
    return clean_category(first_signal_value(s, [
        "display_morning_lab_alignment_status", "morning_lab_alignment_status",
    ])) or "NO_MORNING_BATON"


def get_eod_candidate_status(s):
    display = clean_category(s.get("display_eod_candidate_status"))
    if display:
        return display
    if not (s.get("has_eod_candidate_manifest_row") is True or
            str(s.get("has_eod_candidate_manifest_row")).lower() == "true"):
        return ""
    return clean_category(first_signal_value(s, [
        "eod_candidate_status", "eod__eod_candidate_status",
        "candidate_status", "eod__candidate_status", "effective_execution_verdict",
    ]))


def get_options_research_route(s):
    return clean_category(first_signal_value(s, [
        "display_options_research_route", "options_research_route", "final_route",
        "eod__options_research_route", "eod__final_route", "opt__final_route",
    ]))


def get_options_research_permission(s):
    return clean_category(first_signal_value(s, [
        "options_research_permission", "eod__options_research_permission",
        "opt__execution_permission",
    ]))


def get_execution_category(s):
    """Port of getExecutionCategory(s) — static/index.html:1288-1312."""
    candidates = [
        s.get("display_execution_category"),
        get_morning_execution_permission(s),
        get_eod_candidate_status(s),
        s.get("execution_category"),
        s.get("morning_execution_lane"),
        s.get("lab_status"),
        s.get("lab_verdict"),
        s.get("eod_candidate_status"),
        s.get("candidate_status"),
        s.get("effective_execution_verdict"),
        s.get("lab_execution_status"),
        s.get("execution_verdict"),
        s.get("sb_execution_mode"),
        s.get("pse_execution_mode"),
        s.get("options_verdict"),
        s.get("sb_final_verdict"),
    ]
    for v in candidates:
        c = clean_category(v)
        if c and c not in ("NONE", "N/A", "NA", "UNKNOWN", "NULL", "NAN"):
            return c
    return "UNCATEGORISED"


def is_audit_only_signal(s):
    """Port of isAuditOnlySignal(s) — static/index.html:1259-1277."""
    if s.get("lab_hidden_by_default") is True or str(s.get("lab_hidden_by_default")).lower() == "true":
        return True
    verdict = final_lab_verdict(s)
    morning_perm = get_morning_execution_permission(s)
    morning_route = get_morning_execution_route(s)
    live_state = get_live_validation_state(s)
    thesis_state = get_thesis_validity_state(s)
    flags = clean_category(first_signal_value(s, ["veto_flags", "conflict_flags", "execution_lock_reason"]))
    return (
        verdict == "BLOCKED" or
        morning_perm == "BLOCKED" or
        morning_route in ("STAND_DOWN", "BLOCKED") or
        live_state in ("REJECTED", "BLOCKED") or
        thesis_state in ("BROKEN", "INVALIDATED", "THESIS_BROKEN") or
        (clean_category(s.get("conflict_state")) == "HARD_CONFLICT" and "MORNING_VALIDATION_BLOCKED" in flags)
    )


_HORIZON_LABELS = {
    "1_5D": "1-5D", "1-5D": "1-5D", "1_TO_5D": "1-5D",
    "6_10D": "6-10D", "6-10D": "6-10D", "6_TO_10D": "6-10D",
    "11_20D": "11-20D", "11-20D": "11-20D", "11_TO_20D": "11-20D",
    "5D": "5D", "10D": "10D", "20D": "20D",
}


def normalise_horizon_label(v):
    raw = str(v or "").strip()
    if not raw:
        return ""
    c = re.sub(r"\s+", "_", raw.upper())
    if c in _EMPTY:
        return ""
    return _HORIZON_LABELS.get(c, raw.replace("_", "-"))


def get_time_horizon(s):
    """Port of getTimeHorizon(s) — static/index.html:1605-1625."""
    routed = normalise_horizon_label(first_signal_value(s, [
        "eod__horizon_bucket", "horizon_bucket", "exe__horizon_bucket", "vg__horizon_bucket",
        "wbs__horizon_bucket", "opt__horizon_bucket",
    ]))
    if routed:
        return routed
    preferred = normalise_horizon_label(first_signal_value(s, [
        "eod__layer2__preferred_horizon", "layer2__preferred_horizon", "exe__layer2__preferred_horizon",
        "vg__layer2__preferred_horizon", "opt__layer2__preferred_horizon",
        "eod__macro_preferred_horizon", "macro_preferred_horizon", "exe__macro_preferred_horizon",
        "vg__macro_preferred_horizon", "opt__macro_preferred_horizon",
    ]))
    if preferred:
        return preferred
    hold = first_signal_value(s, ["hold_label", "opt__hold_label", "exe__hold_label", "vg__hold_label", "doss__opt__hold_label"])
    if hold:
        return re.sub(r"\s*days?\b", "d", str(hold), flags=re.IGNORECASE)
    dte = _parse_float(first_signal_value(s, ["contract_dte", "opt__contract_dte", "exe__contract_dte", "dte", "opt__dte", "vg__dte"]))
    return f"{round(dte)}D DTE" if dte and dte > 0 else "—"


def get_hold_period(s):
    return first_signal_value(s, ["hold_label", "opt__hold_label", "exe__hold_label", "vg__hold_label", "doss__opt__hold_label"]) or "—"


def _max_days_from_label(label):
    nums = re.findall(r"\d+(?:\.\d+)?", str(label or ""))
    return max(float(n) for n in nums) if nums else None


def get_horizon_hold_alignment(s):
    horizon_max = _max_days_from_label(get_time_horizon(s))
    hold_max = _max_days_from_label(get_hold_period(s))
    if horizon_max is None or hold_max is None:
        return "UNKNOWN"
    return "ALIGNED" if hold_max <= horizon_max + 3 else "HOLD LONGER"


def format_price_level(value):
    raw = str(value if value is not None else "").strip()
    if not raw:
        return ""
    n = _parse_float(re.sub(r"[$,]", "", raw))
    if n is None:
        return re.sub(r"_", " ", raw)[:18]
    return f"${n:.2f}"


def get_trigger_price_raw(s):
    return first_signal_value(s, [
        "trigger_price", "eod__trigger_price", "vg__trigger_price", "opt__trigger_price",
        "entry_trigger_price", "trade_trigger_price", "scenario_entry_trigger",
        "eod__scenario_entry_trigger", "vg__scenario_entry_trigger",
        "wbs_phase_b_trigger", "eod__wbs_phase_b_trigger", "vg__wbs_phase_b_trigger",
        "wbs_phase_c_trigger", "eod__wbs_phase_c_trigger", "vg__wbs_phase_c_trigger",
    ])


def get_trigger_display(s):
    explicit = first_signal_value(s, [
        "trigger_price", "eod__trigger_price", "vg__trigger_price", "opt__trigger_price",
        "entry_trigger_price", "trade_trigger_price", "scenario_entry_trigger",
        "eod__scenario_entry_trigger", "vg__scenario_entry_trigger",
    ])
    if explicit:
        return format_price_level(explicit)
    phase_b = first_signal_value(s, ["wbs_phase_b_trigger", "eod__wbs_phase_b_trigger", "vg__wbs_phase_b_trigger"])
    phase_c = first_signal_value(s, ["wbs_phase_c_trigger", "eod__wbs_phase_c_trigger", "vg__wbs_phase_c_trigger"])
    if phase_b or phase_c:
        parts = []
        if phase_b:
            parts.append(f"B {format_price_level(phase_b)}")
        if phase_c:
            parts.append(f"C {format_price_level(phase_c)}")
        return " / ".join(parts)
    trg = _parse_float(first_signal_value(s, ["opt__days_to_trigger", "days_to_trigger", "opt__trigger_days", "trigger_days"]))
    return "-" if trg is None else f"{round(trg)}d"


def get_trigger_evidence_display(s):
    evidence = first_signal_value(s, ["trigger_evidence", "eod__trigger_evidence", "vg__trigger_evidence", "opt__trigger_evidence"])
    if evidence:
        return str(evidence).replace("_", " ")[:18]
    primary = first_signal_value(s, ["trigger_primary", "eod__trigger_primary", "vg__trigger_primary", "opt__trigger_primary"])
    quality = first_signal_value(s, ["trigger_quality", "eod__trigger_quality", "vg__trigger_quality", "opt__trigger_quality"])
    codes = first_signal_value(s, ["trigger_codes", "eod__trigger_codes", "vg__trigger_codes", "opt__trigger_codes"])
    score = _parse_float(first_signal_value(s, ["trigger_score", "eod__trigger_score", "vg__trigger_score", "opt__trigger_score"]))
    quality_label = clean_category(quality)
    has_quality = bool(quality) and quality_label not in ("0", "0.0", "0.00", "FALSE", "NO")
    has_score = score is not None and score > 0
    if primary or has_quality or codes or has_score:
        short_primary = str(primary or codes or "TRIGGER").replace("_", " ")[:14]
        short_quality = f" {str(quality).replace('_', ' ')[:6]}" if has_quality else ""
        score_label = f" {round(score)}" if has_score else ""
        return f"{short_primary}{short_quality}{score_label}".strip()
    catalyst = first_signal_value(s, ["catalyst_type", "eod__catalyst_type", "vg__catalyst_type"])
    catalyst_status = first_signal_value(s, ["catalyst_event_status", "eod__catalyst_event_status", "vg__catalyst_event_status"])
    catalyst_score = _parse_float(first_signal_value(s, ["catalyst_truth_score", "eod__catalyst_truth_score", "vg__catalyst_truth_score"]))
    if catalyst or catalyst_status:
        c_label = str(catalyst or catalyst_status or "CATALYST").replace("_", " ")[:14]
        s_label = "" if catalyst_score is None or catalyst_score <= 0 else f" {round(catalyst_score)}"
        return f"CAT {c_label}{s_label}".strip()
    return ""


# ─────────────────────────────────────────────────── filter / sort (defaults)

def filtered_data(all_sigs):
    """Port of filteredData() under DEFAULT UI state — static/index.html:1710-1741.
    filters.* = 'ALL', showAuditRows = False, quickFilters = False, campaignViewMode = False.
    """
    return [s for s in all_sigs if not is_audit_only_signal(s)]


def default_sort(rows):
    """sortCol = 0 (priority_rank), sortDir = 1 (ascending) — static/index.html:584,1744."""
    def key(s):
        return _parse_float(s.get("priority_rank"), 9999)
    return sorted(rows, key=key)


# ───────────────────────────────────────────────────────────────── export

def build_columns():
    """Port of the `cols` array in exportCSV() — static/index.html:1979-2044."""
    return [
        ("Ticker", lambda s: s.get("ticker")),
        ("Verdict", final_lab_verdict),
        ("Lab_Verdict", final_lab_verdict),
        ("Exec_Category", get_execution_category),
        ("EOD_Status", get_eod_candidate_status),
        ("Morning_Permission", get_morning_execution_permission),
        ("Morning_Route", get_morning_execution_route),
        ("Morning_Lab_Alignment", get_morning_lab_alignment),
        ("Options_Route", get_options_research_route),
        ("Options_Research_Permission", get_options_research_permission),
        ("Effective_Execution_Verdict", lambda s: s.get("effective_execution_verdict") or ""),
        ("EOD_Candidate_Status", lambda s: s.get("eod_candidate_status") or ""),
        ("Campaign", display_campaign),
        ("Direction", lambda s: s.get("direction")),
        ("Conv_Score", lambda s: s.get("sb_conv_score")),
        ("Execution_Mode", display_execution_mode),
        ("Instrument", lambda s: s.get("sb_instrument_now")),
        ("Strike", lambda s: get_opt(s, "contract_strike") or s.get("strike") or ""),
        ("Expiry", lambda s: get_opt(s, "contract_expiry")),
        ("DTE", lambda s: get_opt(s, "contract_dte")),
        ("Time_Horizon", get_time_horizon),
        ("Hold_Period", get_hold_period),
        ("Horizon_Hold_Alignment", get_horizon_hold_alignment),
        ("Horizon_Action", lambda s: first_signal_value(s, ["eod__horizon_action", "horizon_action", "exe__horizon_action", "vg__horizon_action"])),
        ("Horizon_Pressure", lambda s: first_signal_value(s, ["eod__horizon_pressure", "horizon_pressure", "exe__horizon_pressure", "vg__horizon_pressure", "opt__horizon_pressure"])),
        ("Horizon_Source", lambda s: first_signal_value(s, ["eod__horizon_source", "horizon_source", "exe__horizon_source", "vg__horizon_source"])),
        ("Trigger_Price", get_trigger_price_raw),
        ("Trigger_Display", get_trigger_display),
        ("Trigger_Evidence", get_trigger_evidence_display),
        ("Trigger_Primary", lambda s: first_signal_value(s, ["trigger_primary", "eod__trigger_primary", "vg__trigger_primary", "opt__trigger_primary"])),
        ("Trigger_Quality", lambda s: first_signal_value(s, ["trigger_quality", "eod__trigger_quality", "vg__trigger_quality", "opt__trigger_quality"])),
        ("Trigger_Score", lambda s: first_signal_value(s, ["trigger_score", "eod__trigger_score", "vg__trigger_score", "opt__trigger_score"])),
        ("Trigger_Codes", lambda s: first_signal_value(s, ["trigger_codes", "eod__trigger_codes", "vg__trigger_codes", "opt__trigger_codes"])),
        ("Premium_Mid", lambda s: (lambda r: r if (_parse_float(r) or 0) > 0 else "")(get_opt(s, "premium_mid") or get_opt(s, "premium") or s.get("premium_mid") or s.get("premium"))),
        ("RR", lambda s: f"{(_parse_float(s.get('rr')) or 0):.4f}"),
        ("EV", lambda s: f"{get_ev(s):.4f}"),
        ("EV_Decision", lambda s: s.get("ev2_decision_hint") or ""),
        ("EV_Quality", lambda s: s.get("ev2_quality_score") or ""),
        ("Win_Rate_20d", lambda s: s.get("win_rate_20d") or ""),
        ("IVP", lambda s: get_opt(s, "iv_rank") or s.get("ivp") or ""),
        ("IVP_Label", lambda s: get_opt(s, "ivp_label") or ""),
        ("Priority_Rank", lambda s: s.get("priority_rank") if s.get("priority_rank") is not None else ""),
        ("Priority_Score", lambda s: f"{(_parse_float(s.get('priority_score')) or 0):.1f}"),
        ("Phase", lambda s: s.get("phase") or ""),
        ("Regime", lambda s: s.get("regime") or ""),
        ("Structural_Target", lambda s: get_opt(s, "structural_target") or ""),
        ("Days_To_Trigger", lambda s: first_signal_value(s, ["opt__days_to_trigger", "days_to_trigger", "opt__trigger_days", "trigger_days"])),
        ("Hold_Label", lambda s: get_opt(s, "hold_label") or ""),
        ("Position_Size_Pct", display_size),
        ("Vetoes", lambda s: s.get("sb_vetoes") or ""),
        ("Vetoes_Count", lambda s: s.get("sb_vetoes_count") if s.get("sb_vetoes_count") is not None else ""),
        ("Exec_Mode", lambda s: display_execution_mode(s) or ""),
        ("EV_Status", lambda s: s.get("ev_status") or ""),
        ("Win_Rate_Source", lambda s: s.get("win_rate_source") or ""),
        ("WBS_Grade", lambda s: s.get("wbs__wbs_grade") or s.get("wbs__grade") or ""),
        ("WBS_Score", lambda s: s.get("wbs__wbs_score") or s.get("wbs__score") or ""),
        ("Vol_State", lambda s: _vol_state(s)),
        ("EIL_Verdict", lambda s: s.get("eil__verdict") or s.get("eil__eil_verdict") or ""),
        ("EIL_Raw_Verdict", lambda s: s.get("eil_raw_verdict") or ""),
        ("EIL_Composite", lambda s: s.get("eil_composite_score") or s.get("composite") or ""),
        ("MV_Verdict", lambda s: s.get("mv__verdict") or ""),
        ("MV_Drift_Pct", lambda s: s.get("mv__drift_pct") or ""),
        ("Verdict_Reason", lambda s: str(s.get("sb_verdict_reason") or "").replace(",", ";")),
        ("Run_ID", lambda s, run_id=None: run_id),
    ]


def _vol_state(s):
    g = _parse_float(s.get("garch__l3_iv_tailwind_score"))
    if g is None:
        return ""
    if g < -0.03:
        return "CHEAP"
    if g > 0.05:
        return "EXP"
    return "FAIR"


def _esc(v):
    s = "" if v is None else str(v)
    return s


def regenerate(run_id):
    import intelligence_lab as lab
    payload = lab._load_run(run_id, force_reload=True)
    all_sigs = payload.get("signals", [])
    rows = default_sort(filtered_data(all_sigs))

    cols = build_columns()
    header = [label for label, _ in cols]

    out_rows = []
    for s in rows:
        row = []
        for label, fn in cols:
            if label == "Run_ID":
                row.append(_esc(run_id))
            else:
                row.append(_esc(fn(s)))
        out_rows.append(row)
    return header, out_rows


def write_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    Path(path).write_text(buf.getvalue(), encoding="utf-8")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    header, rows = regenerate(a.run_id)
    out = a.out or f"lab_export_regenerated_{a.run_id}.csv"
    write_csv(out, header, rows)
    print(f"wrote {out}: {len(rows)} rows x {len(header)} columns")


if __name__ == "__main__":
    main()
