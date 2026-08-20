"""
AVSHUNTER MA_Inputs Auto-Sync v1.1 FIXED
=========================================
Purpose:
    Sync AVSHUNTER outputs and /input-style folders into MA_Inputs so the
    interpreter can consume the latest pipeline files.

Key fixes vs v1.0:
    - Adds input/source folder discovery.
    - Supports recursive scanning.
    - Scans .json and .webp as well as CSV/images.
    - Adds macro/catalyst/calendar routing keywords.
    - Allows force sync with --all-hours or --hours 0.
    - Adds clearer diagnostics for unmatched and stale files.

Usage:
    python ma_inputs_sync_v1_1_FIXED.py --sync
    python ma_inputs_sync_v1_1_FIXED.py --path "C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\input" --recursive --all-hours
    python ma_inputs_sync_v1_1_FIXED.py --watch --recursive --hours 48

Pipeline usage:
    from ma_inputs_sync_v1_1_FIXED import sync_to_ma_inputs
    sync_to_ma_inputs(source_dir=str(output_dir), recursive=True, max_age_hours=0)
"""

import argparse
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BASE_USER = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")

# Put MA_Inputs beside this script. Keep this file inside the AVSHUNTER project root.
INTERPRETER_BASE = Path(__file__).resolve().parent
MA_INPUTS_BASE = INTERPRETER_BASE / "MA_Inputs"
MA_PIPELINE_OUT = MA_INPUTS_BASE / "pipeline_outputs"
MA_CHARTS = MA_INPUTS_BASE / "charts"
MA_OPTIONS = MA_INPUTS_BASE / "options_data"
MA_SCREENSHOTS = MA_INPUTS_BASE / "screenshots"
MA_RAW_INPUTS = MA_INPUTS_BASE / "raw_inputs"

# Known folders the script should check when --path is not supplied.
AVSHUNTER_OUTPUT_DIRS = [
    BASE_USER,
    BASE_USER / "input",
    BASE_USER / "inputs",
    BASE_USER / "Input",
    BASE_USER / "Inputs",
    BASE_USER / "MA_Inputs",
    BASE_USER / "outputs",
    BASE_USER / "AVSHUNTER_outputs",
    BASE_USER / "pipeline_outputs",
    BASE_USER / "results",
    BASE_USER / "morning_outputs",
    BASE_USER / "EIL_outputs",
    BASE_USER / "dropbox",
    BASE_USER / "dropbox" / "outputs",
    BASE_USER / "data" / "output",
    BASE_USER / "data" / "outputs",
    BASE_USER / "data" / "output" / "runs",
    # Scan run subdirectories for morning_validation and other per-run outputs
    BASE_USER / "data" / "output" / "runs",  # recursive scan will find nested files
]

# AVSHUNTER_RUN_SUBFOLDERS defines which per-run subdirs to explicitly scan
# when on_pipeline_complete is called after an evening run.
AVSHUNTER_RUN_SUBFOLDERS = [
    "morning_validation",   # morning_candidates, morning_validated_trades, shadow_book
    "superbrain",           # superbrain_enriched, wall_break_scores, eil_enriched
    "execution",            # execution_v3_5
    "qomega",               # garch_forecasts
    "catalysts",            # catalyst_truth
    "options",              # options_intelligence
    "vanguard",             # vanguard_signals_enriched
]

FILE_ROUTING = [
    {
        "label": "pipeline_output",
        "destination": MA_PIPELINE_OUT,
        "extensions": [".csv", ".json", ".parquet", ".xlsx"],
        "keywords": [
            # Phase 10 outputs — primary handoff files
            "morning_candidates",           # EOD probe slate (Phase 10)
            "morning_validated_trades",     # Morning validation output — the execution gate
            "morning_validated",
            "morning_validation", "morning_val",
            "missed_opportunity_shadow_book",  # Shadow book tracker
            "eod_dropoff_audit",
            "morning_blocked_review",
            # Horizon split files
            "horizon_1_5d", "horizon_6_10d", "horizon_11_20d",
            # Phase 8 outputs
            "superbrain_enriched", "superbrain",
            "wall_break_scores",
            "eil_enriched",             # EIL enriched — richest signal file
            "execution_v3_5",           # Execution v3.5
            "execution_intelligence", "execution_v", "execution_decision",
            # Phase 9 GARCH
            "garch_forecasts", "garch",
            # Phase 7 options intelligence
            "options_intelligence", "olis_output",
            # Phase 6 Vanguard
            "vanguard_signals_enriched", "vanguard_signals",
            "vanguard_enriched", "vanguard_output", "vanguard",
            # Phase 10 catalyst
            "catalyst_truth", "catalyst_truth_summary", "catalyst_calendar", "catalyst",
            # Macro and enrichment
            "macro_enrichment", "macro_delta", "macro_intelligence", "market_narrative",
            "mna", "m_and_a", "ma_events", "event_intelligence", "corporate_events",
            # PSE / sizing
            "pse", "position_sizing",
            # Legacy / manual
            "execute_tickers",
            "top_trades", "avshunter_top", "candidate", "candidates", "watchlist",
            "master_dashboard", "master_dash", "final_decision", "avshunter_master",
            "avshunter_all_data", "pipeline_output", "discovery_output", "discovery",
        ]
    },
    {
        "label": "options_data",
        "destination": MA_OPTIONS,
        "extensions": [".csv", ".json", ".parquet", ".xlsx"],
        "keywords": [
            "gex", "gex_by_strike", "gamma", "gamma_wall", "call_wall", "put_wall",
            "oi_walls", "open_interest", "maxpain", "max_pain",
            "term_structure", "termstructure", "vanna", "charm", "vanna_charm",
            "uoa", "uoa_flows", "unusual_options", "chain_context", "options_snapshot",
            "options_clean", "iv_surface", "skew", "put_call", "option_chain", "options_chain",
        ],
    },
    {
        "label": "chart",
        "destination": MA_CHARTS,
        "extensions": [".png", ".jpg", ".jpeg", ".webp"],
        "keywords": [
            "daily", "weekly", "monthly", "intraday", "1h", "15m", "5m", "chart", "_chart",
            "wyckoff", "price_action", "candlestick", "technical",
        ],
    },
    {
        "label": "screenshot",
        "destination": MA_SCREENSHOTS,
        "extensions": [".png", ".jpg", ".jpeg", ".webp"],
        "keywords": [
            "screenshot", "snap", "capture", "dashboard", "lab", "intelligence_lab",
            "chain", "options_chain", "walls", "gex_chart",
        ],
    },
    {
        "label": "raw_input",
        "destination": MA_RAW_INPUTS,
        "extensions": [".csv", ".json", ".parquet", ".xlsx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp", ".pdf"],
        "keywords": ["input", "upload", "source", "raw"],
    },
]

SUPPORTED_EXTENSIONS = sorted({ext for rule in FILE_ROUTING for ext in rule["extensions"]})


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _matches_rule(filepath: Path, rule: dict) -> bool:
    name_lower = filepath.name.lower()
    ext = filepath.suffix.lower()
    if ext not in rule["extensions"]:
        return False
    return any(keyword in name_lower for keyword in rule["keywords"])


def _route_file(filepath: Path) -> Tuple[Optional[Path], Optional[str]]:
    for rule in FILE_ROUTING:
        if _matches_rule(filepath, rule):
            return rule["destination"], rule["label"]
    return None, None


def _is_fresh(filepath: Path, max_age_hours: int) -> bool:
    # 0 or negative means no freshness filter.
    if max_age_hours <= 0:
        return True
    try:
        age_seconds = time.time() - filepath.stat().st_mtime
        return age_seconds <= max_age_hours * 3600
    except OSError:
        return False


def _already_synced(src: Path, dest_dir: Path) -> bool:
    dest = dest_dir / src.name
    if not dest.exists():
        return False
    try:
        return src.stat().st_size == dest.stat().st_size and abs(src.stat().st_mtime - dest.stat().st_mtime) < 2
    except OSError:
        return False


def _iter_files(scan_dir: Path, recursive: bool) -> Iterable[Path]:
    pattern = "**/*" if recursive else "*"
    for path in scan_dir.glob(pattern):
        if not path.is_file():
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def sync_file(filepath: Path, verbose: bool = True, force: bool = False) -> bool:
    filepath = Path(filepath)
    dest_dir, label = _route_file(filepath)
    if not dest_dir:
        if verbose:
            print(f"  [{_ts()}] UNMATCHED {filepath.name} — no routing keyword matched")
        return False

    if not force and _already_synced(filepath, dest_dir):
        if verbose:
            print(f"  [{_ts()}] SKIPPED already synced {filepath.name}")
        return False

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filepath, dest_dir / filepath.name)
        if verbose:
            print(f"  [{_ts()}] SYNCED [{label}] {filepath.name} -> {dest_dir}")
        return True
    except OSError as exc:
        if verbose:
            print(f"  [{_ts()}] ERROR copying {filepath.name}: {exc}")
        return False


def sync_to_ma_inputs(
    source_dir: Optional[str] = None,
    max_age_hours: int = 24,
    verbose: bool = True,
    recursive: bool = True,
    force: bool = False,
) -> Dict[str, int]:
    counts = {
        "pipeline_output": 0,
        "options_data": 0,
        "chart": 0,
        "screenshot": 0,
        "raw_input": 0,
        "skipped_stale": 0,
        "skipped_synced": 0,
        "unmatched": 0,
        "errors": 0,
    }

    if source_dir:
        scan_dirs = [Path(source_dir).expanduser()]
    else:
        scan_dirs = [path for path in AVSHUNTER_OUTPUT_DIRS if path.exists()]

    # Do not re-scan destination folders as sources; this causes noise and loops.
    scan_dirs = [path for path in scan_dirs if path.exists() and not _is_inside(path, MA_INPUTS_BASE)]

    if not scan_dirs:
        if verbose:
            print(f"  [{_ts()}] No source directories found.")
            print("  Use --path to point directly at the folder you want to sync.")
        return counts

    if verbose:
        mode = "recursive" if recursive else "top-level only"
        age = "all files" if max_age_hours <= 0 else f"files newer than {max_age_hours}h"
        print(f"\n  [{_ts()}] MA_Inputs sync starting ({mode}, {age})")
        for scan_dir in scan_dirs:
            print(f"  Source: {scan_dir}")

    for scan_dir in scan_dirs:
        try:
            files = list(_iter_files(scan_dir, recursive=recursive))
        except OSError as exc:
            counts["errors"] += 1
            if verbose:
                print(f"  [{_ts()}] Cannot scan {scan_dir}: {exc}")
            continue

        for file_path in files:
            if not _is_fresh(file_path, max_age_hours):
                counts["skipped_stale"] += 1
                continue

            dest_dir, label = _route_file(file_path)
            if not dest_dir:
                counts["unmatched"] += 1
                if verbose:
                    print(f"  [{_ts()}] UNMATCHED {file_path.name}")
                continue

            if not force and _already_synced(file_path, dest_dir):
                counts["skipped_synced"] += 1
                continue

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_dir / file_path.name)
                counts[label] = counts.get(label, 0) + 1
                if verbose:
                    print(f"  [{_ts()}] SYNCED [{label}] {file_path.name}")
            except OSError as exc:
                counts["errors"] += 1
                if verbose:
                    print(f"  [{_ts()}] ERROR {file_path.name}: {exc}")

    total = sum(counts[k] for k in ["pipeline_output", "options_data", "chart", "screenshot", "raw_input"])
    if verbose:
        print(f"\n  [{_ts()}] Sync complete.")
        print(f"  Pipeline outputs: {counts['pipeline_output']}")
        print(f"  Options data:     {counts['options_data']}")
        print(f"  Charts:           {counts['chart']}")
        print(f"  Screenshots:      {counts['screenshot']}")
        print(f"  Raw inputs:       {counts['raw_input']}")
        print(f"  Total synced:     {total}")
        print(f"  Unmatched:        {counts['unmatched']}")
        print(f"  Stale skipped:    {counts['skipped_stale']}")
        print(f"  Already synced:   {counts['skipped_synced']}")
        if counts["errors"]:
            print(f"  Errors:           {counts['errors']}")

    return counts


def add_source_path(path: str) -> bool:
    p = Path(path).expanduser()
    if p.exists() and p not in AVSHUNTER_OUTPUT_DIRS:
        AVSHUNTER_OUTPUT_DIRS.append(p)
        return True
    return False


def on_pipeline_complete(
    output_csv_path: str,
    output_dir: Optional[str] = None,
    run_id: Optional[str] = None,
) -> List[str]:
    """
    Called by the orchestrator at Phase 11 after a completed evening run.

    Syncs the specific pipeline output CSV immediately (force=True),
    then sweeps the per-run subdirectories for all Phase 8-10 outputs.

    Parameters
    ----------
    output_csv_path : str
        Path to the primary output file (e.g. morning_candidates CSV).
    output_dir : str, optional
        The run-level output directory (data/output/runs/<run_id>/).
    run_id : str, optional
        The canonical run_id string. Used to locate the run directory if
        output_dir is not supplied.
    """
    synced: List[str] = []

    # 1. Sync the primary file immediately
    p = Path(output_csv_path)
    if p.exists() and sync_file(p, verbose=True, force=True):
        synced.append(p.name)

    # 2. Resolve run directory
    resolved_dir: Optional[Path] = None
    if output_dir:
        resolved_dir = Path(output_dir)
    elif run_id:
        candidate = BASE_USER / "data" / "output" / "runs" / run_id
        if candidate.exists():
            resolved_dir = candidate

    # 3. Sweep per-run subdirectories for Phase 8-10 outputs
    if resolved_dir and resolved_dir.exists():
        total_sub = 0
        for subfolder in AVSHUNTER_RUN_SUBFOLDERS:
            sub_path = resolved_dir / subfolder
            if sub_path.exists():
                result = sync_to_ma_inputs(
                    source_dir=str(sub_path),
                    max_age_hours=2,
                    verbose=False,
                    recursive=False,
                    force=False,
                )
                sub_total = sum(
                    result.get(k, 0)
                    for k in ["pipeline_output", "options_data", "chart", "screenshot", "raw_input"]
                )
                total_sub += sub_total
                if sub_total > 0:
                    print(f"  [MA_Inputs] {subfolder}: synced {sub_total} file(s)")

        # Also do a full recursive sweep of the run root for anything missed
        result2 = sync_to_ma_inputs(
            source_dir=str(resolved_dir),
            max_age_hours=2,
            verbose=False,
            recursive=True,
            force=False,
        )
        total_full = sum(
            result2.get(k, 0)
            for k in ["pipeline_output", "options_data", "chart", "screenshot", "raw_input"]
        )
        if total_full > 0:
            print(f"  [MA_Inputs] Run root sweep: {total_full} additional file(s)")
        print(f"  [MA_Inputs] Pipeline complete sync: {total_sub + total_full} total files to MA_Inputs")
    elif output_dir:
        # Fallback: generic recursive sync on whatever dir was provided
        result = sync_to_ma_inputs(source_dir=output_dir, max_age_hours=2, verbose=True, recursive=True)
        total = sum(result.get(k, 0) for k in ["pipeline_output", "options_data", "chart", "screenshot", "raw_input"])
        if total > 0:
            print(f"  [MA_Inputs] Auto-synced {total} file(s) from {Path(output_dir).name}/")

    return synced


def show_status() -> None:
    print("\n  MA_Inputs Sync Configuration")
    print(f"  {'─' * 60}")
    print(f"  Script base:      {INTERPRETER_BASE}")
    print(f"  MA_Inputs base:   {MA_INPUTS_BASE}")
    print(f"  Supported types:  {', '.join(SUPPORTED_EXTENSIONS)}")

    print("\n  Destination folders:")
    for label, folder in [
        ("pipeline_outputs", MA_PIPELINE_OUT),
        ("options_data", MA_OPTIONS),
        ("charts", MA_CHARTS),
        ("screenshots", MA_SCREENSHOTS),
        ("raw_inputs", MA_RAW_INPUTS),
    ]:
        count = len(list(folder.glob("*"))) if folder.exists() else 0
        print(f"    {label:<20} {folder} ({count} files)")

    print("\n  Source directories:")
    for path in AVSHUNTER_OUTPUT_DIRS:
        status = "EXISTS" if path.exists() else "NOT FOUND"
        print(f"    [{status}] {path}")


def watch_and_sync(interval_seconds: int = 60, max_age_hours: int = 1, recursive: bool = True) -> None:
    print("\n  MA_Inputs Watcher started.")
    print(f"  Syncing every {interval_seconds}s | recursive={recursive} | hours={max_age_hours}")
    print("  Press Ctrl+C to stop.\n")
    try:
        while True:
            result = sync_to_ma_inputs(max_age_hours=max_age_hours, verbose=False, recursive=recursive)
            total = sum(result[k] for k in ["pipeline_output", "options_data", "chart", "screenshot", "raw_input"])
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Watching... synced last pass={total}", end="\r")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n\n  Watcher stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AVSHUNTER MA_Inputs Sync v1.1 FIXED")
    parser.add_argument("--sync", action="store_true", help="Sync now")
    parser.add_argument("--watch", action="store_true", help="Watch and sync continuously")
    parser.add_argument("--status", action="store_true", help="Show configuration status")
    parser.add_argument("--path", type=str, help="Specific source folder to sync from")
    parser.add_argument("--hours", type=int, default=24, help="Only copy files newer than N hours. Use 0 for all files.")
    parser.add_argument("--all-hours", action="store_true", help="Disable freshness filter")
    parser.add_argument("--interval", type=int, default=60, help="Watch interval in seconds")
    parser.add_argument("--recursive", action="store_true", default=True, help="Scan subfolders recursively")
    parser.add_argument("--top-level-only", action="store_true", help="Do not scan subfolders")
    parser.add_argument("--force", action="store_true", help="Copy even if same-size/same-mtime file already exists")
    args = parser.parse_args()

    hours = 0 if args.all_hours else args.hours
    recursive = not args.top_level_only

    if args.status:
        show_status()
    elif args.watch:
        watch_and_sync(interval_seconds=args.interval, max_age_hours=hours, recursive=recursive)
    else:
        if not args.sync and not args.path:
            show_status()
        sync_to_ma_inputs(source_dir=args.path, max_age_hours=hours, recursive=recursive, force=args.force)
