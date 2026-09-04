from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# score_wall_break is pure Python.  Stub the batch-only pandas dependency so
# this focused regression also runs in lightweight verification environments.
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from wall_break_scorer import score_wall_break


def test_missing_intraday_pcr_never_receives_favourable_default_bonus():
    base = {
        "options_direction": "PUT",
        "gamma_velocity_label": "MOVING_AWAY",
        "contract_vanna": -0.02,
        "gamma_flip_conf": 0.5,
        "gamma_flip_gap_pct": 10,
        "iv_vs_hv": 0.8,
        "underlying_price": 100,
        "put_wall": 90,
    }
    missing = score_wall_break({}, {**base, "pcr_vol_status": "OI_ONLY"})
    supplied = score_wall_break({}, {**base, "pcr_vol_status": "AVAILABLE", "pcr_vol": 1.0})
    assert missing["wbs_pcr_volume_state"] == "UNAVAILABLE"
    assert supplied["wbs_pcr_volume_state"] == "AVAILABLE"
    assert supplied["wbs_f5_momentum"] - missing["wbs_f5_momentum"] == 5.0
    assert "no PCR momentum bonus" in missing["wbs_notes"]
