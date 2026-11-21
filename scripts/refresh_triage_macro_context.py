"""Run-MacroInputs.ps1 step after the board (AVS-MACRO-TRIAGE-001 T3, ACK 20 Nov 2026): refresh the board macro
context for the hand-off of the board's next session, or say it was skipped when that hand-off does not exist yet.

Exit 0 = written or skipped; exit 2 = not written (the reason is printed; the board and the macro run are unaffected).
Same as: python -m macro_board.triage_context --next-session
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_board import triage_context  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(triage_context.main(["--next-session", *sys.argv[1:]]))
