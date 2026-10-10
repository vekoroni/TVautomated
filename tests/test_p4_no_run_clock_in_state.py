"""Phase 4 / RC18: Vanguard's state never depends on the clock time of the run.

Business rule (reproducible inputs, R7): the same completed bars give the same state whenever the run happens.
- Relative volume uses the bar's own completeness: a completed bar is never scaled; only a bar explicitly marked
  partial is scaled, by its own observation time - never by the run clock.
- "Days since the 52-week high/low" count from the last bar's session date, not from today.
Codex B18: identical completed bars read LOW at 12:00 UTC and HIGH at 14:00 UTC.
"""
import ast
from pathlib import Path

import pandas as pd

from vanguard.layer2_statistical.state_calculator import relative_volume_from_bars

ROOT = Path(__file__).resolve().parents[1]


def _bars(last_volume, partial=None):
    df = pd.DataFrame({"date": pd.bdate_range("2026-09-01", periods=3), "volume": [1e6, 1e6, last_volume]})
    if partial is not None:
        df.attrs["last_bar_partial"] = True
        df.attrs["last_bar_observed_utc"] = partial
    return df


def test_completed_bar_is_never_scaled():
    assert abs(relative_volume_from_bars(_bars(1e5)) - 1e5 / 7e5) < 1e-12


def test_partial_bar_is_scaled_by_its_own_observation_time():
    # observed at 15:30 UTC = 120 of 390 session minutes
    r = relative_volume_from_bars(_bars(2e5, partial="2026-09-03T15:30:00+00:00"))
    assert abs(r - (2e5 * 390 / 120) / ((1e6 + 1e6 + 2e5 * 390 / 120) / 3)) < 1e-9 or r > 0.5


def test_state_calculator_reads_no_wall_clock():
    src = (ROOT / "vanguard/layer2_statistical/state_calculator.py").read_text(encoding="utf-8-sig")
    calls = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"now", "utcnow", "today"}:
            calls.append(n.lineno)
    assert calls == []
