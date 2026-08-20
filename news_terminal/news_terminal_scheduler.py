"""
AVSHUNTER News Terminal v1.3 — Scheduled Runner
Called by Windows Task Scheduler for automatic daily runs.
Usage: python news_terminal_scheduler.py [morning|midday|evening]
"""
# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER PAUSED — automatic runs disabled to preserve API credits.
# Pipeline is in manual operation mode.
# Reactivate when monetisation begins: remove or comment the two lines below.
# ─────────────────────────────────────────────────────────────────────────────
import sys as _sys
_sys.exit(0)
import sys
import os
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LOG_FILE = Path(__file__).parent / "outputs" / "scheduler.log"

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run_scheduled(session_type: str = None):
    if session_type is None:
        h = datetime.now().hour
        session_type = "morning" if h < 10 else ("midday" if h < 14 else "evening")

    log(f"Scheduled run starting — session: {session_type.upper()}")

    try:
        from news_terminal_engine import get_run_dir, get_timestamp
        from news_terminal_commands import cmd_brief, cmd_mna
        from news_terminal_outputs import write_all_outputs

        # Always run /brief
        log("Running /brief...")
        response = cmd_brief()

        # Run /mna on morning run
        if session_type == "morning":
            log("Running /mna (morning M&A scan)...")
            cmd_mna()

        log(f"Scheduled run complete.")

    except Exception as e:
        log(f"ERROR: {e}")
        raise

if __name__ == "__main__":
    session_arg = sys.argv[1].lower() if len(sys.argv) > 1 else None
    run_scheduled(session_arg)
