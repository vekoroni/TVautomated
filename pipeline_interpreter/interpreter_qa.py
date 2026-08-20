"""
interpreter_qa.py
Runs after every /triage and /ticker command.
Checks: data ingestion completeness, output section integrity,
        pipeline-vs-interpreter verdict consistency.
Writes: QA block to console + appends to interpreter_qa_log_YYYYMMDD.csv
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import json

BASE   = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
TODAY  = datetime.now().strftime("%Y%m%d")
QA_LOG = (
    BASE / "pipeline_interpreter" / "MA_Inputs"
    / f"interpreter_qa_log_{TODAY}.csv"
)

REQUIRED_SECTIONS = [
    "MARKET PREDICTION AND FAILURE POINT",
    "MACRO ALIGNMENT",
    "NEWS NARRATIVE OVERLAY",
    "DR. MAGNUS VALE — DIAGNOSIS",
    "DR. MAGNUS VALE — EVIDENCE QUALITY",
    "DR. MAGNUS VALE — TRAPPED PARTICIPANTS",
    "DR. MAGNUS VALE — CHESS MOVE TREE",
    "SOUL OF THE CHART",
    "SOUL OF THE CHART — BULLISH CASE",
    "SOUL OF THE CHART — BEARISH CASE",
    "SOUL OF THE CHART — BEHAVIOURAL VERDICT",
    "THE SCENARIO",
    "EXECUTION PRESCRIPTION",
    "KILL SWITCH",
    "MONETISATION",
    "RISK ASSESSMENT",
    "FINAL VERDICT",
]

REQUIRED_PIPELINE_FIELDS = [
    "ticker", "eil_v3_verdict", "pse_execution_mode", "scs_score",
    "momentum_tier", "wyckoff_phase_bucket", "signal_type",
    "ivp_label", "capital_permission", "fd_verdict",
]

BULLISH_KEYWORDS = {"LONG_CALL", "BULLISH", "CALL", "UPSIDE", "BUY"}
BEARISH_KEYWORDS = {"LONG_PUT", "BEARISH", "PUT", "DOWNSIDE", "SELL", "SHORT"}


def check_triage_qa(
    pipeline_csv: str,
    macro_json: str,
    candidates_csv: str = None,
) -> dict:
    results = {
        "mode": "TRIAGE",
        "timestamp": datetime.now().isoformat(),
        "checks": {},
    }

    # Pipeline CSV
    try:
        df = pd.read_csv(pipeline_csv, low_memory=False)
        dated = TODAY in Path(pipeline_csv).name
        results["checks"]["pipeline_csv"] = {
            "status": "PASS" if dated else "WARN",
            "rows": len(df),
            "dated_today": dated,
            "file": Path(pipeline_csv).name,
        }
    except Exception as e:
        results["checks"]["pipeline_csv"] = {"status": "FAIL", "error": str(e)}

    # Macro JSON
    try:
        with open(macro_json) as f:
            macro = json.load(f)
        report_date = macro.get("report_date", "UNKNOWN")
        dated = report_date == datetime.now().strftime("%Y-%m-%d")
        results["checks"]["macro_json"] = {
            "status": "PASS" if dated else "WARN",
            "report_date": report_date,
            "dated_today": dated,
            "batch_id": macro.get("batch_id", "MISSING"),
        }
    except Exception as e:
        results["checks"]["macro_json"] = {"status": "FAIL", "error": str(e)}

    # Merged candidates (optional)
    if candidates_csv and Path(candidates_csv).exists():
        try:
            cdf = pd.read_csv(candidates_csv, low_memory=False)
            dated = TODAY in Path(candidates_csv).name
            perm_ok = (cdf["execution_permission"] == "NONE_NEWS_TERMINAL_ONLY").all()
            grade_ok = (cdf["capital_grade"] == "NO").all()
            results["checks"]["merged_candidates"] = {
                "status": "PASS" if (dated and perm_ok and grade_ok) else "WARN",
                "rows": len(cdf),
                "dated_today": dated,
                "execution_permission_locked": bool(perm_ok),
                "capital_grade_locked": bool(grade_ok),
            }
        except Exception as e:
            results["checks"]["merged_candidates"] = {"status": "FAIL", "error": str(e)}
    else:
        results["checks"]["merged_candidates"] = {
            "status": "INFO",
            "note": "Not uploaded -- triage ran on pipeline + macro only",
        }

    return results


def check_ticker_qa(
    ticker: str,
    pipeline_row: dict,
    html_output_path: str,
    trade_brief_path: str,
    macro_data: dict,
) -> dict:
    results = {
        "mode": "DEEP_DIVE",
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "checks": {},
    }

    # 1 — Pipeline field completeness
    missing_fields = [
        f for f in REQUIRED_PIPELINE_FIELDS
        if not pipeline_row.get(f)
        or str(pipeline_row.get(f)).strip() in ("", "nan", "None")
    ]
    populated = len(REQUIRED_PIPELINE_FIELDS) - len(missing_fields)
    pct = round(100 * populated / len(REQUIRED_PIPELINE_FIELDS))
    results["checks"]["pipeline_fields"] = {
        "status": "PASS" if pct >= 80 else "WARN",
        "completeness_pct": pct,
        "populated": populated,
        "total_expected": len(REQUIRED_PIPELINE_FIELDS),
        "missing": missing_fields,
    }

    # 2 — HTML output section integrity
    if Path(html_output_path).exists():
        html = Path(html_output_path).read_text(encoding="utf-8", errors="ignore")
        missing_sections = [s for s in REQUIRED_SECTIONS if s not in html]
        results["checks"]["output_sections"] = {
            "status": "PASS" if not missing_sections else "FAIL",
            "sections_present": len(REQUIRED_SECTIONS) - len(missing_sections),
            "sections_total": len(REQUIRED_SECTIONS),
            "missing_sections": missing_sections,
        }
    else:
        results["checks"]["output_sections"] = {
            "status": "FAIL",
            "error": f"HTML output not found: {html_output_path}",
        }

    # 3 — Verdict consistency
    pipeline_verdict = str(pipeline_row.get("eil_v3_verdict", "")).upper()
    pipeline_bias    = str(pipeline_row.get("catalyst_direction_bias", "")).upper()
    pipeline_is_bull = any(k in pipeline_verdict or k in pipeline_bias for k in BULLISH_KEYWORDS)
    pipeline_is_bear = any(k in pipeline_verdict or k in pipeline_bias for k in BEARISH_KEYWORDS)

    if Path(html_output_path).exists():
        html_upper = html.upper()
        fv_idx  = html_upper.find("FINAL VERDICT")
        fv_text = html_upper[fv_idx:fv_idx + 500] if fv_idx > -1 else ""
        interp_is_bull = any(k in fv_text for k in BULLISH_KEYWORDS)
        interp_is_bear = any(k in fv_text for k in BEARISH_KEYWORDS)

        if pipeline_is_bull and interp_is_bear:
            consistent, note = False, "INVERSION: pipeline BULLISH but interpreter BEARISH -- review required"
        elif pipeline_is_bear and interp_is_bull:
            consistent, note = False, "INVERSION: pipeline BEARISH but interpreter BULLISH -- review required"
        else:
            consistent, note = True, "Direction consistent"

        results["checks"]["verdict_consistency"] = {
            "status": "PASS" if consistent else "WARN",
            "pipeline_direction": "BULLISH" if pipeline_is_bull else ("BEARISH" if pipeline_is_bear else "UNKNOWN"),
            "interpreter_direction": "BULLISH" if interp_is_bull else ("BEARISH" if interp_is_bear else "UNKNOWN"),
            "consistent": consistent,
            "note": note,
        }

    # 4 — Date alignment
    pipeline_date = pipeline_row.get("run_date", pipeline_row.get("date", "UNKNOWN"))
    macro_date    = macro_data.get("report_date", "UNKNOWN")
    date_match    = str(pipeline_date)[:10] == str(macro_date)[:10]
    results["checks"]["date_alignment"] = {
        "status": "PASS" if date_match else "WARN",
        "pipeline_date": pipeline_date,
        "macro_date": macro_date,
        "match": date_match,
        "note": "" if date_match else "Pipeline and macro are from different sessions -- stale data risk",
    }

    return results


def print_qa_report(results: dict) -> str:
    ticker  = results.get("ticker", "TRIAGE")
    mode    = results.get("mode", "")
    print("\n" + "═" * 60)
    print(f"  QA REPORT — {ticker} — {mode}")
    print("═" * 60)

    overall = "PASS"
    for name, check in results.get("checks", {}).items():
        status = check.get("status", "UNKNOWN")
        if status == "FAIL":
            overall = "FAIL"
        elif status == "WARN" and overall == "PASS":
            overall = "WARN"

        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "INFO": "ℹ"}.get(status, "?")
        print(f"  {icon} {name:<28} {status}")

        if status in ("WARN", "FAIL"):
            for k, v in check.items():
                if k != "status" and v:
                    print(f"      {k}: {v}")

    print("─" * 60)
    print(f"  QA VERDICT: {overall}")
    if overall == "WARN":
        print("  Review flagged items before execution decision.")
    elif overall == "FAIL":
        print("  Do not proceed — critical QA failure.")
    print("═" * 60 + "\n")

    return overall


def append_qa_log(results: dict):
    row = {
        "timestamp": results.get("timestamp"),
        "mode":      results.get("mode"),
        "ticker":    results.get("ticker", "TRIAGE"),
        "overall":   "PASS",
    }
    for name, check in results.get("checks", {}).items():
        row[f"{name}_status"] = check.get("status", "")

    df = pd.DataFrame([row])
    if QA_LOG.exists():
        existing = pd.read_csv(QA_LOG)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_csv(QA_LOG, index=False)


# ── STORY OF THE TRADE — additions only, appended at bottom ──────────────────
# Critical: REQUIRED_SECTIONS and check_ticker_qa() above are NOT modified.
# Story sections use a separate list so existing ticker QA is unaffected.

REQUIRED_JUNIOR_SECTIONS = [
    "SECTION_1_MACRO",
    "SECTION_2_GAMMA",
    "SECTION_3_LIQUIDITY",
    "SECTION_4_THESIS",
    "SECTION_5_CHART",
    "SECTION_6_OPTIONS",
    "SECTION_7_RISK",
    "SECTION_8_VERDICT",
]

# Gamma section mandatory sub-elements (per architecture §5.1)
_GAMMA_MANDATORY = ["gamma flip", "gamma island", "wall break"]

# Section 5 checkpoint table marker
_CHART_CHECKPOINT_MARKERS = ["checkpoint", "required for thesis", "status"]

# Section 8 sub-box markers
_VERDICT_SUBBOX_MARKERS = ["WHAT_MAKES_US_ENTER", "WHAT_MAKES_US_ABANDON"]


def check_story_interdependencies(html_content: str) -> dict:
    """
    Lightweight check: every REQUIRED_JUNIOR_SECTION in the story HTML
    contains an INTERDEP: line.
    Returns WARN (not FAIL) for any section missing the INTERDEP line.
    """
    import re
    results = {}
    for section_tag in REQUIRED_JUNIOR_SECTIONS:
        m = re.search(
            rf'\[{re.escape(section_tag)}\](.*?)(?=\[SECTION_\d|$)',
            html_content, re.DOTALL | re.IGNORECASE
        )
        content = m.group(1) if m else ""
        has_interdep = bool(re.search(r'INTERDEP:', content, re.IGNORECASE))
        results[section_tag] = {
            "status":       "PASS" if has_interdep else "WARN",
            "has_interdep": has_interdep,
        }
    return results


def check_story_qa(ticker: str, html_output_path: str) -> dict:
    """
    Check story HTML for all 5 story QA requirements.
    Only called after /story and /update — does not affect check_ticker_qa().

    Returns dict with per-check results and overall PASS/WARN/FAIL.
    """
    import re

    results = {
        "mode":      "STORY",
        "ticker":    ticker,
        "timestamp": datetime.now().isoformat(),
        "checks":    {},
        "pass_count":  0,
        "total_checks": 0,
    }

    # Load HTML
    html_path = Path(html_output_path)
    if not html_path.exists():
        results["checks"]["html_file"] = {
            "status": "FAIL",
            "error":  f"Story HTML not found: {html_output_path}",
        }
        results["overall"] = "FAIL"
        return results

    html = html_path.read_text(encoding="utf-8", errors="ignore")

    # Check 1 — All 8 REQUIRED_JUNIOR_SECTIONS present
    missing = [s for s in REQUIRED_JUNIOR_SECTIONS if s not in html]
    c1_status = "PASS" if not missing else "FAIL"
    results["checks"]["junior_sections"] = {
        "status":           c1_status,
        "sections_present": len(REQUIRED_JUNIOR_SECTIONS) - len(missing),
        "sections_total":   len(REQUIRED_JUNIOR_SECTIONS),
        "missing_sections": missing,
    }

    # Check 2 — Each section contains an INTERDEP: line (WARN only)
    interdep = check_story_interdependencies(html)
    missing_interdep = [s for s, r in interdep.items() if not r["has_interdep"]]
    c2_status = "PASS" if not missing_interdep else "WARN"
    results["checks"]["interdependencies"] = {
        "status":           c2_status,
        "missing_interdep": missing_interdep,
        "note":             "WARN only — INTERDEP lines are strongly recommended",
    }

    # Check 3 — Section 2 contains gamma flip, gamma island, wall break structure
    gamma_m = re.search(
        r'\[SECTION_2_GAMMA\](.*?)(?=\[SECTION_\d|$)',
        html, re.DOTALL | re.IGNORECASE
    )
    gamma_content = gamma_m.group(1).lower() if gamma_m else ""
    missing_gamma = [kw for kw in _GAMMA_MANDATORY if kw not in gamma_content]
    c3_status = "PASS" if not missing_gamma else "FAIL"
    results["checks"]["gamma_cascade"] = {
        "status":       c3_status,
        "missing_terms": missing_gamma,
        "required":     _GAMMA_MANDATORY,
    }

    # Check 4 — Section 5 contains a checkpoint table
    chart_m = re.search(
        r'\[SECTION_5_CHART\](.*?)(?=\[SECTION_\d|$)',
        html, re.DOTALL | re.IGNORECASE
    )
    chart_content = chart_m.group(1).lower() if chart_m else ""
    has_checkpoint = all(kw in chart_content for kw in _CHART_CHECKPOINT_MARKERS)
    c4_status = "PASS" if has_checkpoint else "FAIL"
    results["checks"]["chart_checkpoint_table"] = {
        "status":          c4_status,
        "has_table":       has_checkpoint,
        "required_markers": _CHART_CHECKPOINT_MARKERS,
    }

    # Check 5 — Section 8 contains WHAT_MAKES_US_ENTER and WHAT_MAKES_US_ABANDON
    verdict_m = re.search(
        r'\[SECTION_8_VERDICT\](.*?)(?=\[SECTION_\d|$)',
        html, re.DOTALL | re.IGNORECASE
    )
    verdict_content = verdict_m.group(1) if verdict_m else ""
    missing_subboxes = [kw for kw in _VERDICT_SUBBOX_MARKERS if kw not in verdict_content]
    c5_status = "PASS" if not missing_subboxes else "FAIL"
    results["checks"]["verdict_subboxes"] = {
        "status":          c5_status,
        "missing_subboxes": missing_subboxes,
        "required":        _VERDICT_SUBBOX_MARKERS,
    }

    # Tally
    all_statuses = [c["status"] for c in results["checks"].values()]
    results["pass_count"]   = all_statuses.count("PASS")
    results["total_checks"] = len(all_statuses)

    if "FAIL" in all_statuses:
        results["overall"] = "FAIL"
    elif "WARN" in all_statuses:
        results["overall"] = "WARN"
    else:
        results["overall"] = "PASS"

    # Write to QA log (same CSV as existing checks)
    try:
        append_qa_log(results)
    except Exception:
        pass

    return results


# ── COMPONENT 9 — Lab Reconciliation QA — appended at bottom ─────────────────
# Critical: check_ticker_qa(), check_triage_qa(), and REQUIRED_SECTIONS above
# are NOT modified. Lab QA uses a separate function only.

def check_lab_reconciliation_qa(
    lab_rows: list,
    lab_filename: str,
    reconciliation: dict,
    run_id_check: dict,
) -> dict:
    """
    QA checks for the Intelligence Lab reconciliation layer.
    Called after lab export is loaded in cmd_triage() or cmd_lab().

    Checks:
      1. lab_file_loaded  — was a lab export CSV found and parsed?
      2. run_id_alignment — does Lab Run_ID match the pipeline run?
      3. reconciliation   — how many interp_only tickers require review?

    Returns dict with per-check results. Never raises.
    """
    results: dict = {
        "mode":      "LAB_RECONCILIATION",
        "timestamp": datetime.now().isoformat(),
        "checks":    {},
    }

    # 1. Lab file loaded
    results["checks"]["lab_file_loaded"] = {
        "status":   "PASS" if lab_rows else "WARN",
        "filename": lab_filename or "NOT_FOUND",
        "rows":     len(lab_rows) if lab_rows else 0,
    }

    # 2. Run_ID alignment
    if run_id_check:
        results["checks"]["run_id_alignment"] = {
            "status":          "PASS" if run_id_check.get("match") else "WARN",
            "lab_run_id":      run_id_check.get("lab_run_id", "UNKNOWN"),
            "pipeline_run_id": run_id_check.get("pipeline_run_id", "UNKNOWN"),
            "note": (
                ""
                if run_id_check.get("match")
                else "STALE_LAB_DATA — different sessions"
            ),
        }

    # 3. Reconciliation completeness
    if reconciliation:
        interp_only_count = reconciliation.get("interp_only_count", 0)
        results["checks"]["reconciliation"] = {
            "status":      "PASS" if interp_only_count == 0 else "WARN",
            "confirmed":   reconciliation.get("confirmed_count", 0),
            "lab_only":    reconciliation.get("lab_only_count",  0),
            "interp_only": interp_only_count,
            "note": (
                f"{interp_only_count} tickers require manual review"
                if interp_only_count
                else ""
            ),
        }

    return results


# ── Phantom 4: Delta QA — appended at bottom ─────────────────────────────────

def check_delta_qa(ticker: str, delta_result: dict) -> dict:
    """
    QA validation of the morning delta result for a single ticker.
    Called in morning mode after compute_morning_delta().

    Checks:
      1. baseline_present  — evening baseline exists (NO_BASELINE is an exception)
      2. delta_status      — MINIMAL/MODERATE/SIGNIFICANT/EXCEPTION flag
      3. tier1_fields      — any Tier 1 field changes (crowd_stage, p_trigger, kill_switch_warning)

    Architecture principle: MINIMAL is the expected norm under stable conditions.
    SIGNIFICANT/EXCEPTION appearing routinely = upstream scoring weakness, not normal operation.

    Returns dict with per-check results. Never raises.
    """
    results: dict = {
        "mode":      "DELTA_QA",
        "ticker":    ticker,
        "timestamp": datetime.now().isoformat(),
        "checks":    {},
    }

    status         = delta_result.get("status", "UNKNOWN")
    change_count   = delta_result.get("change_count")
    exception_flds = delta_result.get("exception_fields", [])
    narrative      = delta_result.get("narrative", "")

    # 1. Baseline presence
    baseline_ok = status != "NO_BASELINE"
    results["checks"]["baseline_present"] = {
        "status": "PASS" if baseline_ok else "FAIL",
        "note": (
            ""
            if baseline_ok
            else "NO_BASELINE — evening interpreter did not run or baseline lost. Surface explicitly."
        ),
    }

    # 2. Delta severity
    delta_status_qa = "PASS"
    if status == "EXCEPTION":
        delta_status_qa = "FAIL"
    elif status == "SIGNIFICANT":
        delta_status_qa = "WARN"
    elif status == "MODERATE":
        delta_status_qa = "WARN"

    results["checks"]["delta_status"] = {
        "status":          delta_status_qa,
        "delta_class":     status,
        "change_count":    change_count,
        "note":            narrative[:120] if narrative else "",
    }

    # 3. Tier 1 field changes
    results["checks"]["tier1_fields"] = {
        "status":         "FAIL" if exception_flds else "PASS",
        "changed_fields": exception_flds,
        "note": (
            f"Tier 1 change(s): {', '.join(exception_flds)} — review before entry"
            if exception_flds
            else ""
        ),
    }

    return results


def check_delta_qa_batch(delta_report: dict) -> dict:
    """
    Run check_delta_qa for every ticker in a morning_delta_report.json dict.
    Returns aggregated results with overall status.
    """
    batch = {
        "mode":       "DELTA_QA_BATCH",
        "timestamp":  datetime.now().isoformat(),
        "tickers":    {},
        "overall":    "PASS",
    }

    for ticker, delta_result in delta_report.items():
        tqa = check_delta_qa(ticker, delta_result)
        batch["tickers"][ticker] = tqa
        all_statuses = [c.get("status") for c in tqa["checks"].values()]
        if "FAIL" in all_statuses:
            batch["overall"] = "FAIL"
        elif "WARN" in all_statuses and batch["overall"] == "PASS":
            batch["overall"] = "WARN"

    return batch