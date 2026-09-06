"""
AVSHUNTER M&A Cockpit v1.0 â€” Scheduled Runner
Usage: python ma_cockpit_scheduler.py [morning|midday|evening]
"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

LOG_FILE = Path(__file__).parent / "outputs" / "ma_scheduler.log"

def log(msg:str):
    ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line=f"[{ts}] {msg}"; print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE,"a",encoding="utf-8") as f: f.write(line+"\n")

def run_scheduled(session_type:str=None):
    if session_type is None:
        h=datetime.now().hour
        session_type="morning" if h<10 else ("midday" if h<14 else "evening")
    log(f"Scheduled M&A scan starting â€” {session_type.upper()}")
    try:
        from ma_cockpit_commands import cmd_scan, cmd_activist
        cmd_scan()
        if session_type=="morning":
            log("Running activist scan (morning)...")
            cmd_activist()
        log("Scheduled M&A scan complete.")
    except Exception as e:
        log(f"ERROR: {e}"); raise

if __name__=="__main__":
    run_scheduled(sys.argv[1].lower() if len(sys.argv)>1 else None)

