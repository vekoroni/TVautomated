"""
AVSHUNTER News Terminal v1.3 — Interactive Entry Point
Run this file to open the interactive terminal.
"""
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

HEADER = """
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║          █████╗ ██╗   ██╗███████╗██╗  ██╗██╗   ██╗███╗   ██╗           ║
║         ██╔══██╗██║   ██║██╔════╝██║  ██║██║   ██║████╗  ██║           ║
║         ███████║██║   ██║███████╗███████║██║   ██║██╔██╗ ██║           ║
║         ██╔══██║╚██╗ ██╔╝╚════██║██╔══██║██║   ██║██║╚██╗██║           ║
║         ██║  ██║ ╚████╔╝ ███████║██║  ██║╚██████╔╝██║ ╚████║           ║
║         ╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝          ║
║                                                                          ║
║              NEWS TERMINAL v1.3 — Intelligence Layer                    ║
║              EXECUTION PERMISSION: NONE — NEWS TERMINAL ONLY            ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝"""

def get_session_label():
    h = datetime.now().hour
    return "MORNING" if h < 10 else ("MIDDAY" if h < 14 else "EVENING")

def main():
    print(HEADER)
    date_str = datetime.now().strftime("%A %d %B %Y  |  %H:%M ET")
    session_label = get_session_label()
    print(f"\n  {date_str}  |  {session_label} Session")
    print(f"  Output directory: {Path(__file__).parent / 'outputs' / 'daily'}")
    print(f"\n  Type /menu for commands  |  /brief to start  |  /exit to close\n")

    from news_terminal_commands import route_command, MENU

    while True:
        try:
            raw = input("  > ").strip()
            if not raw:
                continue
            if not raw.startswith("/"):
                print("  Commands start with /  (type /menu for help)")
                continue
            result = route_command(raw)
            if result == "EXIT":
                print("\n  Session closed. All files saved.")
                print(f"  EXECUTION PERMISSION: NONE — NEWS TERMINAL ONLY\n")
                break
        except KeyboardInterrupt:
            print("\n\n  Interrupted. Type /exit to close cleanly.\n")
        except EOFError:
            break
        except Exception as e:
            print(f"\n  ⚠ Error: {e}\n")

if __name__ == "__main__":
    main()
