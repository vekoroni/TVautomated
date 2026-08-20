"""
prepare_interpreter_session.py
================================
Populates MA_Inputs with all files needed before running the Pipeline Interpreter.
Run this BEFORE starting pipeline_interpreter.py — for both sessions.

TWO MODES:

  EOD SESSION (after evening pipeline completes, before morning validation)
  -------------------------------------------------------------------------
  python prepare_interpreter_session.py --eod

  Pulls from the latest evening run:
    - morning_candidates_<run_id>.csv          (the prep input)
    - eil_enriched_<run_id>.csv
    - execution_v3_5_<run_id>.csv
    - wall_break_scores_<run_id>.csv
    - garch_forecasts_<run_id>.csv
    - missed_opportunity_shadow_book_<run_id>.csv
    - catalyst_truth_<run_id>.csv
    - vanguard_signals_enriched_<run_id>.csv
    - macro_intelligence_latest.json           (from dropbox/macro)
    - avshunter_macro_enrichment_delta.json    (from dropbox/macro)

  MORNING SESSION (after morning_thesis_validator.py --live has run)
  -----------------------------------------------------------------
  python prepare_interpreter_session.py --morning

  Pulls everything from --eod PLUS:
    - morning_validated_trades_<run_id>.csv    (the execution gate file)
    - morning_blocked_review_<run_id>.csv
    - eod_dropoff_audit_<run_id>.csv

  FORCE re-copy even if files already synced:
  python prepare_interpreter_session.py --eod --force
  python prepare_interpreter_session.py --morning --force

After this script completes, start the interpreter:
  python pipeline_interpreter.py
Then paste the newsroom brief:
  /brief
Then run triage:
  /triage
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE          = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
INTERP_DIR    = BASE / "pipeline_interpreter"
MA_INPUTS     = INTERP_DIR / "MA_Inputs"
MA_PIPELINE   = MA_INPUTS / "pipeline_outputs"
MA_MACRO      = MA_INPUTS / "macro"
MA_NEWS       = MA_INPUTS / "news_terminal"
MA_CHARTS     = MA_INPUTS / "charts"

RUNS_DIR      = BASE / "data" / "output" / "runs"
LATEST_JSON   = BASE / "data" / "output" / "latest.json"
DROPBOX_MACRO = BASE / "dropbox" / "macro"

# ── File specifications ───────────────────────────────────────────────────────
# Each entry: (subfolder_in_run, filename_template, required_for_eod, required_for_morning)
EOD_FILES = [
    # subfolder              filename pattern                     EOD    MORNING
    ("morning_validation",   "morning_candidates_{}.csv",         True,  True),
    ("superbrain",           "eil_enriched_{}.csv",               True,  True),
    ("execution",            "execution_v3_5_{}.csv",             True,  True),
    ("superbrain",           "wall_break_scores_{}.csv",          True,  True),
    ("qomega",               "garch_forecasts_{}.csv",            True,  True),
    ("morning_validation",   "missed_opportunity_shadow_book_{}.csv", True, True),
    ("morning_validation",   "catalyst_truth_{}.csv",             True,  True),
    ("vanguard",             "vanguard_signals_enriched_{}.csv",  False, False),  # nice-to-have
    ("superbrain",           "superbrain_enriched_{}.csv",        False, False),  # nice-to-have
]

MORNING_ONLY_FILES = [
    ("morning_validation",   "morning_validated_trades_{}.csv",   True,  True),
    ("morning_validation",   "morning_blocked_review_{}.csv",     False, True),
    ("morning_validation",   "eod_dropoff_audit_{}.csv",          False, True),
]

MACRO_FILES = [
    (DROPBOX_MACRO / "macro_intelligence_latest.json",        "macro_intelligence_latest.json"),
    (DROPBOX_MACRO / "avshunter_macro_enrichment_delta.json", "avshunter_macro_enrichment_delta.json"),
]


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def resolve_run_id() -> str:
    """Read the canonical run_id from latest.json."""
    if not LATEST_JSON.exists():
        print(f"  [{ts()}] ERROR: latest.json not found at {LATEST_JSON}")
        print(f"           Run the evening pipeline first.")
        sys.exit(1)
    try:
        data = json.loads(LATEST_JSON.read_text(encoding="utf-8-sig"))
        run_id = str(data.get("run_id", "")).strip()
        if not run_id:
            print(f"  [{ts()}] ERROR: run_id is empty in latest.json")
            sys.exit(1)
        return run_id
    except Exception as e:
        print(f"  [{ts()}] ERROR reading latest.json: {e}")
        sys.exit(1)


def ensure_dirs():
    for d in [MA_PIPELINE, MA_MACRO, MA_NEWS, MA_CHARTS]:
        d.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dest_dir: Path, force: bool, label: str) -> bool:
    if not src.exists():
        return False
    dest = dest_dir / src.name
    if not force and dest.exists():
        src_mtime  = src.stat().st_mtime
        dest_mtime = dest.stat().st_mtime
        if abs(src_mtime - dest_mtime) < 5 and src.stat().st_size == dest.stat().st_size:
            print(f"  [{ts()}] SKIP   (already current) {src.name}")
            return True
    shutil.copy2(src, dest)
    size_kb = src.stat().st_size // 1024
    print(f"  [{ts()}] COPIED [{label}] {src.name} ({size_kb} KB)")
    return True


def sync_macro_files(force: bool) -> int:
    synced = 0
    print(f"\n  [{ts()}] --- Macro files (dropbox → MA_Inputs/macro/) ---")
    for src_path, dest_name in MACRO_FILES:
        if src_path.exists():
            dest = MA_MACRO / dest_name
            if not force and dest.exists():
                age_h = (datetime.now().timestamp() - src_path.stat().st_mtime) / 3600
                if age_h > 12:
                    print(f"  [{ts()}] WARN   {dest_name} is {age_h:.1f}h old — update macro before running")
            if copy_file(src_path, MA_MACRO, force, "macro"):
                synced += 1
        else:
            print(f"  [{ts()}] MISS   {dest_name} not found at {src_path}")
    return synced


def sync_run_files(run_id: str, file_specs: list, force: bool, session_label: str) -> tuple:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        print(f"  [{ts()}] ERROR: Run directory not found: {run_dir}")
        sys.exit(1)

    copied  = 0
    missing = 0
    print(f"\n  [{ts()}] --- {session_label} files (run {run_id}) ---")

    for subfolder, template, required, _ in file_specs:
        filename = template.format(run_id)
        src = run_dir / subfolder / filename

        # Also try root of run dir as fallback
        if not src.exists():
            src_alt = run_dir / filename
            if src_alt.exists():
                src = src_alt

        if copy_file(src, MA_PIPELINE, force, subfolder):
            copied += 1
        else:
            if required:
                print(f"  [{ts()}] MISS   {filename}  (required)")
                missing += 1
            else:
                print(f"  [{ts()}] SKIP   {filename}  (optional — not present)")

    return copied, missing


def write_session_marker(mode: str, run_id: str):
    """Write a small status file so the interpreter knows what session it is in."""
    marker = {
        "session_mode":  mode,
        "run_id":        run_id,
        "prepared_at":   datetime.now().isoformat(),
        "ready_for":     "EOD_PREP" if mode == "eod" else "MORNING_EXECUTION_REVIEW",
    }
    marker_path = MA_INPUTS / "session_state.json"
    marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    print(f"\n  [{ts()}] Session marker written: {marker_path.name}")


def print_next_steps(mode: str):
    print()
    print("=" * 60)
    if mode == "eod":
        print("  MA_INPUTS READY — EOD PREP SESSION")
        print("=" * 60)
        print()
        print("  Next steps:")
        print()
        print("  1. Start the interpreter:")
        print("     python pipeline_interpreter.py")
        print()
        print("  2. Paste the newsroom brief:")
        print("     /brief")
        print("     (paste brief, press Enter twice)")
        print()
        print("  3. Run triage:")
        print("     /triage")
        print()
        print("  4. Drop chart screenshots into:")
        print(f"     {MA_CHARTS}")
        print("     Name them: TICKER_daily.png")
        print()
        print("  5. Run deep dives for DEEP_DIVE_NOW tickers:")
        print("     /ticker TICKER")
        print()
        print("  6. At 09:45 ET — run morning validation:")
        print("     python morning_thesis_validator.py --tiers A,B,C,WATCH --max-signals 0 --live")
        print()
        print("  7. After validation — re-run this script:")
        print("     python prepare_interpreter_session.py --morning")
    else:
        print("  MA_INPUTS READY — MORNING EXECUTION REVIEW SESSION")
        print("=" * 60)
        print()
        print("  Next steps:")
        print()
        print("  1. Start the interpreter (or /sync if already open):")
        print("     python pipeline_interpreter.py")
        print("     OR inside interpreter: /sync")
        print()
        print("  2. Run triage against validated trades:")
        print("     /triage")
        print()
        print("  3. Cross-reference triage shortlist against")
        print("     morning_validated_trades — GO/GO_LIMIT/PROBE only")
        print()
        print("  4. Deep dive on confirmed names:")
        print("     /ticker TICKER")
        print()
        print("  TRADE ELIGIBILITY GATE:")
        print("  Ticker must appear in morning_validated_trades")
        print("  with verdict GO/GO_LIMIT/PROBE and live_data_mode=LIVE")
        print("  before any trade review begins.")
    print()
    print("  EXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Prepare MA_Inputs for Pipeline Interpreter session"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--eod",     action="store_true", help="EOD prep session (after evening pipeline)")
    group.add_argument("--morning", action="store_true", help="Morning session (after morning_thesis_validator)")
    parser.add_argument("--force",  action="store_true", help="Re-copy even if files are already current")
    args = parser.parse_args()

    mode = "eod" if args.eod else "morning"

    print()
    print("=" * 60)
    label = "EOD PREP" if mode == "eod" else "MORNING EXECUTION REVIEW"
    print(f"  PREPARE INTERPRETER SESSION — {label}")
    print(f"  {datetime.now().strftime('%A %d %B %Y  %H:%M')}")
    print("=" * 60)

    ensure_dirs()

    # 1. Resolve run_id
    run_id = resolve_run_id()
    print(f"\n  [{ts()}] Run ID: {run_id}")

    # 2. Sync macro files (both sessions)
    macro_synced = sync_macro_files(args.force)

    # 3. Sync EOD pipeline files (both sessions need these)
    eod_copied, eod_missing = sync_run_files(
        run_id, EOD_FILES, args.force, "EOD pipeline outputs"
    )

    # 4. If morning session — also sync morning validation outputs
    morning_copied = 0
    morning_missing = 0
    if mode == "morning":
        morning_copied, morning_missing = sync_run_files(
            run_id, MORNING_ONLY_FILES, args.force, "Morning validation outputs"
        )

    # 5. Write session marker
    write_session_marker(mode, run_id)

    # 6. Summary
    total_copied  = macro_synced + eod_copied + morning_copied
    total_missing = eod_missing + morning_missing

    print()
    print(f"  [{ts()}] Files copied:  {total_copied}")
    if total_missing:
        print(f"  [{ts()}] Files missing: {total_missing} required file(s) not found")
        print(f"           Check that the pipeline completed successfully.")
        if mode == "morning":
            print(f"           morning_validated_trades requires morning_thesis_validator to have run.")
    else:
        print(f"  [{ts()}] All required files present")

    # 7. Next steps
    print_next_steps(mode)


if __name__ == "__main__":
    main()
