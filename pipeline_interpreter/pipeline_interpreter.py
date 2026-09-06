"""
AVSHUNTER Pipeline Interpreter v1.0 â€” Interactive Entry Point
"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
# When this legacy entry point is imported as ``pipeline_interpreter`` from a
# sys.path that points at this directory, expose the directory as a package
# path as well.  This keeps governed imports such as
# ``pipeline_interpreter.ma_inputs_sync`` deterministic during mixed legacy/v2
# sessions without changing the interactive launcher.
__path__ = [str(Path(__file__).resolve().parent)]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HEADER = """
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                                                                          â•‘
â•‘   PIPELINE INTERPRETER v1.0                                              â•‘
â•‘   Dr. Magnus Vale  Ã—  Soul of the Chart  Ã—  AVSHUNTER                   â•‘
â•‘                                                                          â•‘
â•‘   STAGE 1  /triage    Rank and prioritise all candidates (fast)          â•‘
â•‘   STAGE 2  /ticker    Full deep dive â€” one ticker at a time              â•‘
â•‘   STAGE 2  /chart     Add chart images to the deep dive                  â•‘
â•‘                                                                          â•‘
â•‘   The machine discovers.  The narrative diagnoses.                       â•‘
â•‘   The market permits.     The trader executes.                           â•‘
â•‘                                                                          â•‘
â•‘   EXECUTION PERMISSION: NONE â€” PIPELINE INTERPRETER ONLY                â•‘
â•‘                                                                          â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"""

def main():
    print(HEADER)
    date_str=datetime.now().strftime("%A %d %B %Y  |  %H:%M ET")
    print(f"\n  {date_str}")
    print(f"  Output directory: {Path(__file__).parent / 'outputs'}")
    print(f"\n  Start here: /triage  â†’  then /ticker TICKER for each priority name")
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
            print(f"\n  âš  Error: {e}\n")

if __name__=="__main__":
    main()

