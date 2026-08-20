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
