"""Fix Spec Fix 2 ripple, decision D5 (24 Sep 2026): position sizing reads the IV percentile it says it wants.

Rule: `_options_multiplier` applies its IV-expensive penalty to `iv_percentile` (0–1). A range-based
`iv_rank` published with `iv_rank_definition='RANGE_IV_HISTORY'` is never read as a percentile;
a legacy `iv_rank` without that marker is the percentile × 100 and remains an accepted fallback,
so sizing behaves exactly as it did before Fix 2 on old and new books alike.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from position_sizing_engine import _options_multiplier  # noqa: E402

BASE = {"spread_pct": 0.05, "options_intelligence_score": 50.0}


def test_percentile_drives_the_penalty_and_a_range_rank_is_not_mistaken_for_it():
    expensive = _options_multiplier({**BASE, "iv_percentile": 0.85, "iv_rank": 20.0, "iv_rank_definition": "RANGE_IV_HISTORY"})
    cheap = _options_multiplier({**BASE, "iv_percentile": 0.20, "iv_rank": 95.0, "iv_rank_definition": "RANGE_IV_HISTORY"})
    assert expensive < cheap                                    # the percentile, not the rank, decided
    assert expensive == _options_multiplier({**BASE, "iv_percentile": 0.85})


def test_legacy_rank_without_definition_marker_is_still_the_percentile_times_100():
    legacy = _options_multiplier({**BASE, "iv_rank": 85.0})
    assert legacy == _options_multiplier({**BASE, "iv_percentile": 0.85})


def test_a_range_rank_alone_does_not_stand_in_for_a_missing_percentile():
    rank_only = _options_multiplier({**BASE, "iv_rank": 95.0, "iv_rank_definition": "RANGE_IV_HISTORY"})
    assert rank_only == _options_multiplier({**BASE})           # no percentile: the module's own default applies
