"""
AVSHUNTER Pipeline Interpreter v1.0 — Interactive Entry Point
"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HEADER = """
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║   PIPELINE INTERPRETER v1.0                                              ║
║   Dr. Magnus Vale  ×  Soul of the Chart  ×  AVSHUNTER                   ║
║                                                                          ║
║   STAGE 1  /triage    Rank and prioritise all candidates (fast)          ║
║   STAGE 2  /ticker    Full deep dive — one ticker at a time              ║
║   STAGE 2  /chart     Add chart images to the deep dive                  ║
║                                                                          ║
║   The machine discovers.  The narrative diagnoses.                       ║
║   The market permits.     The trader executes.                           ║
║                                                                          ║
║   EXECUTION PERMISSION: NONE — PIPELINE INTERPRETER ONLY                ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝"""

def main():
    print(HEADER)
    date_str=datetime.now().strftime("%A %d %B %Y  |  %H:%M ET")
    print(f"\n  {date_str}")
    print(f"  Output directory: {Path(__file__).parent / 'outputs'}")
    print(f"\n  Start here: /triage  →  then /ticker TICKER for each priority name")
    print(f"  Type /menu for all commands  |  /inputs to check MA_Inputs  |  /exit to close\n")

    from pipeline_interpreter_commands import route_command, MENU
    from pipeline_interpreter_engine import run_session_check
    run_session_check()
    while True:
        try:
            raw=input("  PI> ").strip()
            if not raw: continue
            if not raw.startswith("/"):
                print("  Commands start with /  (type /menu for help)")
                continue
            result=route_command(raw)
            if result=="EXIT":
                print("\n  Pipeline Interpreter closed.")
                print(f"  EXECUTION PERMISSION: NONE_PIPELINE_INTERPRETER_ONLY\n")
                break
        except KeyboardInterrupt:
            print("\n\n  Interrupted. Type /exit to close cleanly.\n")
        except EOFError:
            break
        except Exception as e:
            print(f"\n  ⚠ Error: {e}\n")

if __name__=="__main__":
    main()
