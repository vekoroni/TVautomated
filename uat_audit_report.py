"""Create a readable UAT audit report from the machine audit artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "data" / "output" / "runs"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def _latest(pattern: str, folder: Path) -> Optional[Path]:
    matches = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df[column].fillna("").astype(str).value_counts().items()}


def _top(mapping: Mapping[str, Any], limit: int = 12) -> list[tuple[str, Any]]:
    return list(mapping.items())[:limit]


def _fmt_counts(mapping: Mapping[str, Any], empty: str = "None") -> str:
    if not mapping:
        return empty
    return "\n".join(f"- {_clean_text(key)}: {_clean_text(value)}" for key, value in mapping.items())


def _clean_text(value: Any) -> str:
    text = str(value)
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "â€”": "-",
        "â€“": "-",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text.encode("ascii", errors="ignore").decode("ascii")


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                return _as_list(json.loads(text))
            except Exception:
                pass
        return [_clean_text(part.strip()) for part in text.replace("|", ",").split(",") if part.strip()]
    return [_clean_text(value)] if str(value).strip() else []


def _macro_packet_from_json(path: Path) -> dict[str, Any]:
    macro = _read_json(path)
    if not macro:
        return {}
    if "macro_freshness_status" in macro or "macro_data_quality" in macro:
        return macro
    try:
        from scripts.macro_quant_packet import build_macro_quant_packet

        return build_macro_quant_packet(macro, source_path=str(path))
    except Exception:
        return macro


def write_uat_audit_report(
    run_id: str,
    *,
    runs_dir: Path = RUNS_DIR,
    output_dir: Optional[Path] = None,
) -> dict[str, str]:
    run_dir = runs_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run folder not found: {run_dir}")

    diagnostics = output_dir or run_dir / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)

    dropoff_json = diagnostics / f"dropoff_audit_{run_id}.json"
    handoff_json = diagnostics / f"handoff_contract_audit_{run_id}.json"
    eod_csv = run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv"
    shadow_csv = run_dir / "morning_validation" / f"missed_opportunity_shadow_book_{run_id}.csv"
    execution_csv = run_dir / "execution" / f"execution_v3_5_{run_id}.csv"
    macro_packet = _latest("packages/macro_quant_packet_*.json", run_dir) or (run_dir / "packages" / "macro_quant_packet.json")

    dropoff = _read_json(dropoff_json)
    handoff = _read_json(handoff_json)
    candidates = _read_csv(eod_csv)
    shadow = _read_csv(shadow_csv)
    execution = _read_csv(execution_csv)
    macro_source = ""
    macro = _macro_packet_from_json(macro_packet)
    if macro:
        macro_source = str(macro_packet)
    if not macro and not candidates.empty:
        macro = {
            "macro_freshness_status": str(candidates.get("macro_freshness_status", pd.Series([""])).iloc[0] or ""),
            "macro_data_quality": str(candidates.get("macro_data_quality", pd.Series([""])).iloc[0] or ""),
            "macro_active_conflict_flags": str(candidates.get("macro_active_conflict_flags", pd.Series([""])).iloc[0] or ""),
            "macro_resolved_conflict_flags": str(candidates.get("macro_resolved_conflict_flags", pd.Series([""])).iloc[0] or ""),
        }
        macro_source = str(eod_csv)
    if not _as_list(macro.get("macro_active_conflict_flags", [])):
        live_macro = ROOT / "dropbox" / "macro" / "macro_intelligence_latest.json"
        live_macro_packet = _macro_packet_from_json(live_macro)
        if live_macro_packet and _as_list(live_macro_packet.get("macro_active_conflict_flags", [])):
            macro = live_macro_packet
            macro_source = str(live_macro)

    candidate_status_counts = _counts(candidates, "eod_candidate_status")
    candidate_tier_counts = _counts(candidates, "structural_tier")
    shadow_label_counts = _counts(shadow, "shadow_opportunity_label")
    effective_execution_counts = _counts(execution, "effective_execution_verdict")
    capital_counts = _counts(execution, "capital_permission")

    report = {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "handoff_status": handoff.get("overall_status", "UNKNOWN"),
        "handoff_fail_count": int(handoff.get("fail_count", 0) or 0),
        "handoff_warn_count": int(handoff.get("warn_count", 0) or 0),
        "candidate_count": int(len(candidates)),
        "candidate_status_counts": candidate_status_counts,
        "candidate_tier_counts": candidate_tier_counts,
        "execution_effective_counts": effective_execution_counts,
        "execution_capital_counts": capital_counts,
        "dropoff_stage_counts": dropoff.get("dropoff_stage_counts", {}),
        "root_cause_family_counts": dropoff.get("root_cause_family_counts", {}),
        "top_dropoff_reasons": dropoff.get("top_dropoff_reasons", {}),
        "shadow_label_counts": shadow_label_counts,
        "macro_freshness_status": macro.get("macro_freshness_status", ""),
        "macro_data_quality": macro.get("macro_data_quality", ""),
        "macro_active_conflict_flags": _as_list(macro.get("macro_active_conflict_flags", [])),
        "macro_resolved_conflict_flags": _as_list(macro.get("macro_resolved_conflict_flags", [])),
        "macro_source": macro_source,
        "artifacts": {
            "dropoff_audit": str(dropoff_json) if dropoff_json.exists() else "",
            "handoff_contract_audit": str(handoff_json) if handoff_json.exists() else "",
            "eod_candidates": str(eod_csv) if eod_csv.exists() else "",
            "shadow_book": str(shadow_csv) if shadow_csv.exists() else "",
            "execution": str(execution_csv) if execution_csv.exists() else "",
            "macro_packet": macro_source,
        },
    }

    md_lines = [
        f"# AVSHUNTER UAT Audit Report - {run_id}",
        "",
        f"Generated UTC: {report['generated_utc']}",
        "",
        "## Executive Outcome",
        "",
        f"- Handoff audit: {report['handoff_status']} (fail={report['handoff_fail_count']}, warn={report['handoff_warn_count']})",
        f"- EOD candidates: {report['candidate_count']}",
        f"- Macro: freshness={_clean_text(report['macro_freshness_status'] or 'UNKNOWN')} quality={_clean_text(report['macro_data_quality'] or 'UNKNOWN')}",
        "",
        "## EOD Candidate Slate",
        "",
        _fmt_counts(candidate_status_counts),
        "",
        "## Candidate Tiers",
        "",
        _fmt_counts(candidate_tier_counts),
        "",
        "## Execution Authority",
        "",
        _fmt_counts(effective_execution_counts),
        "",
        "## Capital Permission Labels",
        "",
        _fmt_counts(capital_counts),
        "",
        "## Drop-Off Stages",
        "",
        _fmt_counts(dropoff.get("dropoff_stage_counts", {})),
        "",
        "## Root Cause Families",
        "",
        _fmt_counts(dropoff.get("root_cause_family_counts", {})),
        "",
        "## Top Drop-Off Reasons",
        "",
        _fmt_counts(dict(_top(dropoff.get("top_dropoff_reasons", {})))),
        "",
        "## Shadow Book",
        "",
        _fmt_counts(shadow_label_counts),
        "",
        "## Macro Active Flags",
        "",
        _fmt_counts({flag: 1 for flag in report["macro_active_conflict_flags"]}, "No active macro defects reported."),
        "",
        "## Macro Resolved Flags",
        "",
        _fmt_counts({flag: 1 for flag in report["macro_resolved_conflict_flags"]}, "No resolved macro conflicts reported."),
        "",
        "## Artifact Map",
        "",
        _fmt_counts(report["artifacts"]),
        "",
    ]

    md_path = diagnostics / f"uat_audit_report_{run_id}.md"
    json_path = diagnostics / f"uat_audit_report_{run_id}.json"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")

    return {"output_markdown": str(md_path), "output_json": str(json_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a readable AVSHUNTER UAT audit report.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    result = write_uat_audit_report(
        args.run_id,
        runs_dir=Path(args.runs_dir),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
