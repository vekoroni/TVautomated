"""
AVSHUNTER M&A Cockpit v1.0 — Interactive Entry Point
"""
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

HEADER = """
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║    ███╗   ███╗ ██╗ █████╗      ██████╗ ██████╗  ██████╗██╗  ██╗██╗████╗ ║
║    ████╗ ████║ ██║██╔══██╗    ██╔════╝██╔═══██╗██╔════╝██║ ██╔╝██║╚══██║ ║
║    ██╔████╔██║ ██║███████║    ██║     ██║   ██║██║     █████╔╝ ██║  ██╔╝ ║
║    ██║╚██╔╝██║ ██║██╔══██║    ██║     ██║   ██║██║     ██╔═██╗ ██║ ██╔╝  ║
║    ██║ ╚═╝ ██║ ██║██║  ██║    ╚██████╗╚██████╔╝╚██████╗██║  ██╗██║██████╗║
║                                                                          ║
║           M&A COCKPIT v1.0 — Corporate Event Intelligence                ║
║           EXECUTION PERMISSION: NONE — M&A COCKPIT ONLY                 ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝"""

def main():
    print(HEADER)
    date_str=datetime.now().strftime("%A %d %B %Y  |  %H:%M ET")
    print(f"\n  {date_str}")
    print(f"  Output directory: {Path(__file__).parent / 'outputs' / 'daily'}")
    print(f"\n  Type /menu for commands  |  /scan to start  |  /exit to close\n")

    from ma_cockpit_commands import route_command, MENU
    while True:
        try:
            raw=input("  MA> ").strip()
            if not raw: continue
            if not raw.startswith("/"):
                print("  Commands start with /  (type /menu for help)")
                continue
            result=route_command(raw)
            if result=="EXIT":
                print("\n  M&A Cockpit closed. All files saved.")
                print(f"  EXECUTION PERMISSION: NONE_MA_COCKPIT_ONLY\n")
                break
        except KeyboardInterrupt:
            print("\n\n  Interrupted. Type /exit to close cleanly.\n")
        except EOFError:
            break
        except Exception as e:
            print(f"\n  ⚠ Error: {e}\n")

if __name__=="__main__":
    main()
